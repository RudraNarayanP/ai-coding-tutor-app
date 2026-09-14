"""Source-grounded project planner for the Create Course guided-project feature.

Given an ingested source (transcript / tutorial text / YouTube transcript), this
module extracts an ORDERED sequence of milestones that stay strictly inside the
source. It never invents an unrelated project or generic filler curriculum: every
milestone is derived from an actual sentence/step in the source, and the source
sentence is preserved as `source_quote` for transparency.

If the source cannot be processed into a genuine coding project (e.g. transcript
extraction failed, or the text contains no implementable steps), planning raises
`ProjectGroundingError` with a clear, user-facing message instead of fabricating
a course.

The extractor is deterministic (no network, no LLM) so the pipeline is reliable
and fully testable. An optional LLM enrichment hook can refine wording when a
provider is configured, but the deterministic backbone is always source-grounded.
"""
from __future__ import annotations

import re
import time

from .project_models import (
    Microstep,
    Milestone,
    ProjectCourse,
    VerificationCheck,
    WorkspaceFile,
)
from .source_ingestion import SourceDocument


class ProjectGroundingError(ValueError):
    """Raised when a source cannot be reliably turned into a guided project."""


# Curated technologies we can recognise in a source. Kept intentionally small and
# high-signal so the tech stack reflects the source rather than random words.
KNOWN_TECH = {
    "langchain": "langchain",
    "openai": "openai",
    "anthropic": "anthropic",
    "requests": "requests",
    "httpx": "httpx",
    "flask": "flask",
    "fastapi": "fastapi",
    "django": "django",
    "pandas": "pandas",
    "numpy": "numpy",
    "matplotlib": "matplotlib",
    "pytest": "pytest",
    "sqlite3": "sqlite3",
    "sqlalchemy": "sqlalchemy",
    "pydantic": "pydantic",
    "json": "json",
    "os": "os",
    "sys": "sys",
    "re": "re",
    "math": "math",
    "random": "random",
    "datetime": "datetime",
    "collections": "collections",
    "itertools": "itertools",
    "pathlib": "pathlib",
    "asyncio": "asyncio",
    "dataclasses": "dataclasses",
}

_ACTION_VERBS = (
    "install",
    "import",
    "create",
    "define",
    "write",
    "add",
    "build",
    "configure",
    "set up",
    "setup",
    "initialize",
    "initialise",
    "connect",
    "combine",
    "implement",
    "make",
    "declare",
    "call",
    "run",
    "print",
    "return",
    "test",
    "verify",
    "loop",
    "iterate",
    "parse",
    "load",
    "save",
    "read",
    "compute",
    "calculate",
)

_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"


def _gather_source_text(doc: SourceDocument) -> str:
    """Collect the most transcript-like text available from the source."""
    if doc.plain_text and doc.plain_text.strip():
        return doc.plain_text
    parts: list[str] = []
    for seg in doc.segments:
        if seg.transcript and seg.transcript.strip():
            parts.append(f"{seg.title}. {seg.transcript}")
        elif seg.description_snippet:
            parts.append(f"{seg.title}. {seg.description_snippet}")
        elif seg.title:
            parts.append(seg.title)
    return "\n".join(parts)


def _split_steps(text: str) -> list[str]:
    """Split source text into candidate step sentences, preserving order.

    Handles explicitly numbered steps ("1.", "Step 2:") and ordinary sentences.
    """
    # Normalise whitespace but keep line breaks meaningful.
    raw_lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Split a line into sentences so a dense transcript still yields steps.
        for sentence in re.split(r"(?<=[.!?:])\s+", line):
            sentence = sentence.strip(" -•\t")
            if sentence:
                raw_lines.append(sentence)
    return raw_lines


def _extract_target(sentence: str) -> tuple[str, str] | None:
    """Derive a verification (kind, target) from a step sentence.

    Returns None when the sentence has no concrete, verifiable coding action.
    """
    s = sentence.lower()

    # import / install a package
    m = re.search(rf"\b(?:import|installing|install)\s+(?:the\s+)?(?:package\s+)?({_IDENT})", s)
    if m:
        module = m.group(1)
        # `from X import Y` — prefer the package root X.
        mf = re.search(rf"\bfrom\s+({_IDENT})\s+import\b", s)
        if mf:
            module = mf.group(1)
        return ("import", module)

    m = re.search(rf"\bfrom\s+({_IDENT})\s+import\b", s)
    if m:
        return ("import", m.group(1))

    # define / write / create a function (or method)
    m = re.search(
        rf"\b(?:def|function|method)\b[^A-Za-z0-9_]*({_IDENT})"
        rf"|\b(?:define|write|create|implement|add)\s+(?:a\s+|an\s+|the\s+)?(?:function|method)\s+(?:called\s+|named\s+)?({_IDENT})",
        s,
    )
    if m:
        name = m.group(1) or m.group(2)
        if name and name not in _ACTION_VERBS:
            return ("symbol", name)

    # High-precision: an explicitly named symbol — "a variable called total",
    # "an object named client".
    m = re.search(rf"\b(?:called|named)\s+({_IDENT})", s)
    if m and m.group(1) not in _ACTION_VERBS:
        return ("symbol", m.group(1))

    # "create/build/configure a <type-noun>" → the object itself is the symbol,
    # e.g. "create the chain" → chain, "build a client" → client. The type noun
    # must immediately follow the article so descriptive prose ("build a word
    # frequency counter") does not produce spurious symbols.
    _type_noun = (
        r"variable|object|client|prompt|chain|model|counter|list|dict|dictionary|"
        r"array|instance|app|server|router|agent|pipeline|parser|handler|config|session"
    )
    m = re.search(
        rf"\b(?:create|initialize|initialise|declare|make|build|configure|set\s+up|setup|add)\s+"
        rf"(?:a\s+|an\s+|the\s+)({_type_noun})\b",
        s,
    )
    if m:
        return ("symbol", m.group(1))

    # "store ... in a variable X"
    m = re.search(rf"\bstore\b.*?\bin\s+(?:a\s+|the\s+)?variable\s+(?:called\s+|named\s+)?({_IDENT})", s)
    if m and m.group(1) not in _ACTION_VERBS:
        return ("symbol", m.group(1))

    # call / run a specific function
    m = re.search(rf"\bcall\s+(?:the\s+)?({_IDENT})", s)
    if m and m.group(1) not in _ACTION_VERBS:
        return ("function_call", m.group(1))

    # print / output → verify the program prints something
    if re.search(r"\b(print|output|display|show)\b", s):
        return ("stdout_contains", "")

    # run / execute / test / verify → the program must run cleanly
    if re.search(r"\b(run|execute|test|verify|check that it works)\b", s):
        return ("run_ok", "")

    return None


def _is_step(sentence: str) -> bool:
    s = sentence.lower()
    if re.match(r"^\s*(?:step\s*)?\d+[.):]", s):
        return True
    return any(re.search(rf"\b{re.escape(v)}\b", s) for v in _ACTION_VERBS)


def _short_title(sentence: str, target: tuple[str, str]) -> str:
    kind, tgt = target
    if kind == "import":
        return f"Import {tgt}"
    if kind == "symbol":
        return f"Define {tgt}"
    if kind == "function_call":
        return f"Call {tgt}"
    if kind == "stdout_contains":
        return "Print the result"
    if kind == "run_ok":
        return "Run and verify"
    # Fallback: first few words of the sentence.
    words = re.sub(r"^\s*(?:step\s*)?\d+[.):]\s*", "", sentence).split()
    return " ".join(words[:6]).strip(" .") or "Implement step"


def _check_for(kind: str, target: str) -> VerificationCheck:
    if kind == "import":
        return VerificationCheck(kind="import", target=target, description=f"Your code imports `{target}`.")
    if kind == "symbol":
        return VerificationCheck(kind="symbol", target=target, description=f"Your code defines `{target}`.")
    if kind == "function_call":
        return VerificationCheck(kind="function_call", target=target, description=f"Your code calls `{target}`.")
    if kind == "stdout_contains":
        return VerificationCheck(kind="run_ok", target="", description="Your project runs and prints output.")
    return VerificationCheck(kind="run_ok", target="", description="Your project runs without errors.")


def _detect_tech(text: str) -> list[str]:
    found: list[str] = []
    low = text.lower()
    for key, name in KNOWN_TECH.items():
        if re.search(rf"\b{re.escape(key)}\b", low) and name not in found:
            found.append(name)
    return found


def _detect_language(text: str) -> str:
    low = text.lower()
    # Very light heuristic; Python is the fully-supported verification target.
    if re.search(r"\b(npm|const |=>|node\.js|nodejs|document\.|console\.log)\b", low):
        return "javascript"
    return "python"


def plan_project(doc: SourceDocument, title: str, course_id: str) -> ProjectCourse:
    """Build a source-grounded ProjectCourse from an ingested source document."""
    text = _gather_source_text(doc)
    if not text or len(text.strip()) < 40:
        raise ProjectGroundingError(
            "The source did not contain enough readable text to build a project. "
            "Paste a fuller transcript or tutorial, or provide a video whose transcript is available."
        )

    language = _detect_language(text)
    tech_stack = _detect_tech(text)

    sentences = _split_steps(text)
    milestones: list[Milestone] = []
    seen_targets: set[tuple[str, str]] = set()
    order = 1

    # Milestone 1 — always: set up the persistent project entry file.
    milestones.append(
        Milestone(
            id=f"m{order}",
            order=order,
            title="Set up the project",
            source_grounded_description=(
                f"Create the entry file for this project so you can start building "
                f"the thing the source builds: {title}."
            ),
            source_quote=title,
            microstep=Microstep(
                observation="Your project workspace is ready.",
                action="Create `main.py` and add a comment describing the project goal.",
                hint="Every file you create here persists across the whole course.",
            ),
            why="A guided project keeps one persistent workspace — this is the file you will grow across every milestone.",
            checks=[VerificationCheck(kind="file_exists", target="main.py", description="`main.py` exists in your workspace.")],
            xp_reward=10,
        )
    )
    order += 1

    for sentence in sentences:
        if len(milestones) >= 14:
            break
        if not _is_step(sentence):
            continue
        target = _extract_target(sentence)
        if target is None:
            continue
        kind, tgt = target
        # De-duplicate identical concrete checks (e.g. transcript repeats "import X").
        key = (kind, tgt)
        if kind in ("import", "symbol", "function_call"):
            if key in seen_targets:
                continue
            seen_targets.add(key)

        check = _check_for(kind, tgt)
        clean_sentence = re.sub(r"^\s*(?:step\s*)?\d+[.):]\s*", "", sentence).strip()
        action_text = clean_sentence
        if len(action_text) > 200:
            action_text = action_text[:197] + "…"

        milestones.append(
            Milestone(
                id=f"m{order}",
                order=order,
                title=_short_title(sentence, (kind, tgt)),
                source_grounded_description=clean_sentence,
                source_quote=clean_sentence,
                microstep=Microstep(
                    observation="Next step from the source:",
                    action=action_text,
                    hint=_hint_for(kind, tgt),
                ),
                checks=[check],
                xp_reward=20,
            )
        )
        order += 1

    # Require at least two substantive (non-setup) milestones or we are not
    # confident the source describes a real, implementable project.
    substantive = [m for m in milestones if m.checks and m.checks[0].kind != "file_exists"]
    if len(substantive) < 2:
        raise ProjectGroundingError(
            "This source doesn't describe enough concrete implementation steps to build a guided project. "
            "Provide a hands-on coding tutorial (with steps like importing packages, defining functions, "
            "and running code) so Patchwork can turn it into a project you build."
        )

    # Final milestone — always: run the whole project and verify it works.
    if not any(m.checks and m.checks[0].kind == "run_ok" for m in milestones):
        milestones.append(
            Milestone(
                id=f"m{order}",
                order=order,
                title="Run and verify the project",
                source_grounded_description="Run your complete project and confirm it works end-to-end.",
                source_quote="",
                microstep=Microstep(
                    observation="You've implemented the source's steps.",
                    action="Run your project and make sure it executes without errors.",
                    hint="Use the Run button, then click NEXT to verify.",
                ),
                why="The final milestone verifies the whole project runs — the source's intended outcome.",
                checks=[VerificationCheck(kind="run_ok", target="", description="Your project runs without errors.")],
                xp_reward=30,
            )
        )
        order += 1

    goal = title.strip() or (sentences[0] if sentences else "Build the project from the source")
    summary = text.strip()
    excerpt = summary[:20_000]

    now = time.time()
    project = ProjectCourse(
        course_id=course_id,
        title=title.strip() or doc.title or "Guided Project",
        language=language,
        source_type=doc.source_type,
        source_url=doc.source_url,
        source_hash=doc.source_hash,
        source_summary=summary[:4000],
        source_excerpt=excerpt,
        project_goal=goal[:2000],
        tech_stack=tech_stack,
        entry_file="main.py",
        milestones=milestones,
        workspace_files=[
            WorkspaceFile(
                path="main.py",
                content=(
                    f"# {title.strip() or 'Guided project'}\n"
                    f"# Goal: {goal[:120]}\n"
                    f"# Build this project step by step. Click NEXT when you finish a milestone.\n\n"
                ),
            )
        ],
        created_at=now,
        updated_at=now,
    )
    return project


def _hint_for(kind: str, target: str) -> str:
    if kind == "import":
        return f"Add an `import {target}` (or `from {target} import ...`) statement."
    if kind == "symbol":
        return f"Make sure something named `{target}` is defined at the top level."
    if kind == "function_call":
        return f"Call `{target}(...)` somewhere in your code."
    if kind == "stdout_contains":
        return "Use `print(...)` to show a result."
    return "Make sure the file runs top-to-bottom without raising an error."
