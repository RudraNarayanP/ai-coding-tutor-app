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
    # ML / data-science stacks (common in coding tutorials)
    "torch": "torch",
    "pytorch": "torch",
    "tensorflow": "tensorflow",
    "keras": "keras",
    "transformers": "transformers",
    "tiktoken": "tiktoken",
    "tokenizers": "tokenizers",
    "datasets": "datasets",
    "accelerate": "accelerate",
    "einops": "einops",
    "sklearn": "scikit-learn",
    "scikit-learn": "scikit-learn",
    "scipy": "scipy",
    "tqdm": "tqdm",
    "wandb": "wandb",
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

# Common English/filler words that must never be treated as code identifiers.
_STOPWORDS = {
    "so", "that", "which", "the", "a", "an", "to", "it", "this", "then", "and",
    "for", "of", "in", "on", "is", "are", "with", "your", "our", "we", "you",
    "some", "any", "each", "them", "its", "here", "there", "now", "next", "also",
    "will", "can", "should", "into", "from", "our", "my", "his", "her",
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


def _reject(name: str | None) -> bool:
    """True if a captured identifier is not a usable code symbol."""
    if not name or len(name) < 2:
        return True
    low = name.lower()
    return low in _ACTION_VERBS or low in _STOPWORDS


def _extract_target(sentence: str) -> tuple[str, str] | None:
    """Derive a verification (kind, target) from a step sentence.

    Identifier case is preserved (captured from the original sentence with
    case-insensitive keyword matching) so a check for `GPT` matches the learner's
    real class name — not a lowercased `gpt` that could never match.

    Returns None when the sentence has no concrete, verifiable coding action.
    """
    IC = re.IGNORECASE
    s = sentence.lower()

    # import / install a package (identifier captured with original case).
    m = re.search(rf"\b(?:import|installing|install)\s+(?:the\s+)?(?:package\s+)?({_IDENT})", sentence, IC)
    if m:
        module = m.group(1)
        mf = re.search(rf"\bfrom\s+({_IDENT})\s+import\b", sentence, IC)
        if mf:
            module = mf.group(1)
        # Normalise dotted/aliased imports to the package root.
        return ("import", module.split(".")[0])

    m = re.search(rf"\bfrom\s+({_IDENT})\s+import\b", sentence, IC)
    if m:
        return ("import", m.group(1).split(".")[0])

    # "the forward method", "the train function" — name precedes the keyword.
    m = re.search(rf"\b(?:the\s+)({_IDENT})\s+(?:method|function)\b", sentence, IC)
    if m and not _reject(m.group(1)):
        return ("symbol", m.group(1))

    # "def name", or "define/write a function called name" — name follows keyword.
    m = re.search(
        rf"\bdef\s+({_IDENT})"
        rf"|\b(?:define|write|create|implement|add)\s+(?:a\s+|an\s+|the\s+)?(?:function|method)\s+(?:called\s+|named\s+)?({_IDENT})",
        sentence,
        IC,
    )
    if m:
        name = m.group(1) or m.group(2)
        if not _reject(name):
            return ("symbol", name)

    # High-precision: an explicitly named symbol — "a class called GPT",
    # "a variable named total", "a dataclass called GPTConfig".
    m = re.search(rf"\b(?:called|named)\s+({_IDENT})", sentence, IC)
    if m and not _reject(m.group(1)):
        return ("symbol", m.group(1))

    # "create/build/configure a <type-noun>" → the object itself is the symbol,
    # e.g. "create the chain" → chain. The type noun must immediately follow the
    # article so descriptive prose ("build a word frequency counter") does not
    # produce spurious symbols.
    _type_noun = (
        r"variable|object|client|prompt|chain|model|counter|list|dict|dictionary|"
        r"array|instance|app|server|router|agent|pipeline|parser|handler|config|session|"
        r"optimizer|dataset|dataloader|tokenizer|tensor"
    )
    m = re.search(
        rf"\b(?:create|initialize|initialise|declare|make|build|configure|set\s+up|setup|add)\s+"
        rf"(?:a\s+|an\s+|the\s+)({_type_noun})\b",
        sentence,
        IC,
    )
    if m:
        return ("symbol", m.group(1).lower())

    # "store ... in a variable X"
    m = re.search(rf"\bstore\b.*?\bin\s+(?:a\s+|the\s+)?variable\s+(?:called\s+|named\s+)?({_IDENT})", sentence, IC)
    if m and not _reject(m.group(1)):
        return ("symbol", m.group(1))

    # call / run a specific function
    m = re.search(rf"\bcall\s+(?:the\s+)?({_IDENT})", sentence, IC)
    if m and not _reject(m.group(1)):
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


# Concept → acceptable code token(s) for chapter-based (concept-level) checks.
# Keys are substrings matched against a lowercased chapter title; values are a
# "|"-separated list of tokens any of which satisfy the milestone.
CONCEPT_TOKENS: list[tuple[str, str]] = [
    ("flash attention", "scaled_dot_product_attention|flash"),
    ("self-attention", "attention"),
    ("attention", "attention"),
    ("nn.module", "nn.Module"),
    ("forward pass", "def forward"),
    ("forward", "forward"),
    ("logits", "logits"),
    ("cross entropy", "cross_entropy|CrossEntropyLoss"),
    ("loss", "loss"),
    ("tokeniz", "tiktoken|encode"),
    ("tiktoken", "tiktoken"),
    ("sampling", "topk|multinomial|generate|sample"),
    ("from_pretrained", "from_pretrained"),
    ("huggingface", "from_pretrained|GPT2LMHeadModel"),
    ("checkpoint", "from_pretrained|state_dict"),
    ("parameters", "parameters|state_dict"),
    ("adamw", "AdamW"),
    ("optim", "optim|AdamW"),
    ("data loader", "DataLoader|dataloader"),
    ("dataloader", "DataLoader|dataloader"),
    ("data batches", "DataLoader|batch"),
    ("parameter sharing", "lm_head|wte"),
    ("weight", "weight"),
    ("initializ", "init_weights|normal_|std"),
    ("residual", "residual"),
    ("mixed precision", "autocast|bfloat16"),
    ("bfloat16", "bfloat16"),
    ("float16", "float16|autocast"),
    ("tf32", "tf32|set_float32_matmul_precision"),
    ("tensor core", "matmul"),
    ("torch.compile", "torch.compile|compile"),
    ("compile", "compile"),
    ("gradient clipping", "clip_grad_norm|clip_grad"),
    ("gradient accumulation", "accum"),
    ("learning rate", "lr|learning_rate"),
    ("scheduler", "cosine|warmup|lr"),
    ("warmup", "warmup"),
    ("weight decay", "weight_decay"),
    ("distributed data parallel", "DistributedDataParallel|DDP"),
    ("ddp", "DistributedDataParallel|DDP|dist"),
    ("dataset", "dataset|load"),
    ("fineweb", "fineweb|dataset"),
    ("validation", "val|eval"),
    ("evaluation", "eval"),
    ("hellaswag", "hellaswag|eval"),
    ("device", "device|cuda"),
    ("config", "config|Config"),
    ("hyperparameter", "config|Config"),
]

# Chapters that are meta/non-implementation and shouldn't become build milestones.
_META_CHAPTER = re.compile(
    r"^(intro|introduction|welcome|outro|summary|conclusion|recap|results?|"
    r"shoutout|thanks|corrections?|errata|q&a|questions|final thoughts)\b",
    re.IGNORECASE,
)
_CAMEL = re.compile(r"\b([A-Z][a-zA-Z0-9]*[a-z][a-zA-Z0-9]*(?:\.[A-Za-z0-9_]+)?)\b")
_DOTTED = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_.]*)\b")


def _clean_chapter(title: str) -> str:
    t = re.sub(r"^\s*section\s*\d+\s*:\s*", "", title, flags=re.IGNORECASE)
    t = re.sub(r"^\s*(?:let['’]?s|lets)\s+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*,?\s*\d+\s*ms\b", "", t)              # drop timing annotations "333ms"
    t = re.sub(r"\s*\([^)]*\)\s*$", "", t)                 # drop trailing "(...)"
    t = t.strip(" -–—:•\t")
    return t


def _collect_chapters(doc: SourceDocument) -> list[str]:
    chapters: list[str] = []
    seen: set[str] = set()
    for seg in doc.segments:
        for ch in getattr(seg, "chapters", []) or []:
            cleaned = _clean_chapter(ch)
            key = cleaned.lower()
            if cleaned and key not in seen:
                seen.add(key)
                chapters.append(cleaned)
    return chapters


def _chapter_check(title: str) -> VerificationCheck | None:
    low = title.lower()
    # 1) A concrete import/symbol/call if the chapter names one.
    direct = _extract_target(title)
    if direct and direct[0] in ("import", "symbol", "function_call"):
        return _check_for(direct[0], direct[1])
    # 2) Curated concept → token map (grounded concept-level check).
    for needle, token in CONCEPT_TOKENS:
        if needle in low:
            pretty = token.split("|")[0]
            return VerificationCheck(kind="code_contains", target=token,
                                     description=f"Your code implements **{title}** (references `{pretty}`).")
    # 3) A distinctive CamelCase / dotted identifier in the title is a strong code
    #    signal (e.g. "nn.Module", "DataLoaderLite", "TF32").
    for rx in (_DOTTED, _CAMEL):
        m = rx.search(title)
        if m:
            tok = m.group(1)
            if tok.lower() not in _STOPWORDS:
                return VerificationCheck(kind="code_contains", target=tok,
                                         description=f"Your code implements **{title}** (references `{tok}`).")
    # No concrete code signal — deliberately return None so purely conversational
    # chapters ("my story", "please subscribe") never become hollow milestones.
    return None


_MICRO_OBSERVATIONS = [
    "Next up from the video:",
    "Here's the next piece to build:",
    "Keep the momentum — next section:",
    "Now for the next milestone:",
    "Time to build:",
]


def plan_project(doc: SourceDocument, title: str, course_id: str) -> ProjectCourse:
    """Build a source-grounded ProjectCourse from an ingested source document.

    Prefers creator-authored chapters (authoritative, ordered outline) when the
    source is a chaptered video; otherwise falls back to sentence-level step
    extraction for pasted transcripts/notes.
    """
    chapters = _collect_chapters(doc)
    if len(chapters) >= 4:
        return _plan_from_chapters(doc, chapters, title, course_id)

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


def _plan_from_chapters(doc: SourceDocument, chapters: list[str], title: str, course_id: str) -> ProjectCourse:
    """Build a milestone per creator-authored chapter — an authoritative, ordered
    outline of exactly what the video builds."""
    text = _gather_source_text(doc)
    language = _detect_language(text)
    tech_stack = _detect_tech(text)
    project_title = title.strip() or doc.title or "Guided Project"

    milestones: list[Milestone] = []
    order = 1
    milestones.append(
        Milestone(
            id=f"m{order}",
            order=order,
            title="Set up the project",
            source_grounded_description=f"Create the entry file and start building the project from the video: {project_title}.",
            source_quote=project_title,
            microstep=Microstep(
                observation="Your project workspace is ready.",
                action="Create `main.py` and add a comment with the project goal.",
                hint="Everything you write here persists across the whole course.",
            ),
            why="One persistent workspace — you grow this project across every chapter of the video.",
            checks=[VerificationCheck(kind="file_exists", target="main.py", description="`main.py` exists in your workspace.")],
            xp_reward=10,
        )
    )
    order += 1

    kept = 0
    for idx, ch in enumerate(chapters):
        if len(milestones) >= 16:
            break
        if _META_CHAPTER.match(ch):
            continue
        check = _chapter_check(ch)
        if check is None:
            continue
        obs = _MICRO_OBSERVATIONS[idx % len(_MICRO_OBSERVATIONS)]
        milestones.append(
            Milestone(
                id=f"m{order}",
                order=order,
                title=ch if len(ch) <= 60 else ch[:57] + "…",
                source_grounded_description=f"The video covers this section: “{ch}”. Implement it in your project.",
                source_quote=ch,
                microstep=Microstep(
                    observation=obs,
                    action=f"Build this part: {ch}.",
                    hint=_chapter_hint(check),
                ),
                why=f"This is a real chapter of the video — building it moves your project toward the source's final result.",
                checks=[check],
                xp_reward=25,
            )
        )
        order += 1
        kept += 1

    # Vagueness gate: a video with no implementable chapters is rejected clearly
    # rather than turned into a hollow course.
    if kept < 3:
        raise ProjectGroundingError(
            "This video doesn't break down into enough concrete, buildable steps to make a guided "
            "project (its chapters are too high-level or missing). Try a hands-on coding tutorial with "
            "clear sections, or paste its transcript so Patchwork can ground the project in real steps."
        )

    milestones.append(
        Milestone(
            id=f"m{order}",
            order=order,
            title="Run and verify the project",
            source_grounded_description="Run your complete project and confirm it works end-to-end.",
            source_quote="",
            microstep=Microstep(
                observation="You've built the video's sections.",
                action="Run your project and make sure it executes without errors.",
                hint="Use Run, then click NEXT to verify.",
            ),
            why="The final milestone verifies the whole project runs — the source's intended outcome.",
            checks=[VerificationCheck(kind="run_ok", target="", description="Your project runs without errors.")],
            xp_reward=40,
        )
    )

    now = time.time()
    goal = f"Reproduce the project built in “{project_title}”, one chapter at a time."
    return ProjectCourse(
        course_id=course_id,
        title=project_title,
        language=language,
        source_type=doc.source_type,
        source_url=doc.source_url,
        source_hash=doc.source_hash,
        source_summary=text[:4000],
        source_excerpt=text[:20_000],
        project_goal=goal[:2000],
        tech_stack=tech_stack,
        entry_file="main.py",
        milestones=milestones,
        workspace_files=[
            WorkspaceFile(
                path="main.py",
                content=(
                    f"# {project_title}\n"
                    f"# Built from the video, chapter by chapter. Click NEXT after each milestone.\n\n"
                ),
            )
        ],
        created_at=now,
        updated_at=now,
    )


def _chapter_hint(check: VerificationCheck) -> str:
    if check.kind == "import":
        return f"Add an `import {check.target}` statement."
    if check.kind == "symbol":
        return f"Define `{check.target}` in your code."
    if check.kind == "function_call":
        return f"Call `{check.target}(...)` in your code."
    if check.kind == "code_contains":
        first = check.target.split("|")[0]
        return f"Your implementation should use `{first}`."
    return "Implement this section, then click NEXT."


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
