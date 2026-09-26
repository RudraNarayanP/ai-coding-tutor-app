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
import sys
import time

from .project_copy import (
    beginner_action,
    beginner_observation,
    beginner_teach,
    code_ident_for_import,
    contains_banned_video_phrase,
    display_ident,
    is_weak_learner_action,
    needs_learner_fallback,
    polish_project_copy,
    short_source_excerpt,
)
from .project_models import (
    Microstep,
    Milestone,
    ProjectCourse,
    VerificationCheck,
    WorkspaceFile,
)
from .source_ingestion import SourceDocument
from .source_quality import (
    ProjectGroundingError,
    evaluate_milestones,
    evaluate_source,
    filter_invalid_milestones,
    is_conceptual_heading,
    is_dangling_or_document_task,
    is_implementable_step,
    require_accept,
)


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
    "math": "math",
    "random": "random",
    "datetime": "datetime",
    "collections": "collections",
    "itertools": "itertools",
    "pathlib": "pathlib",
    "asyncio": "asyncio",
    "dataclasses": "dataclasses",
    # Web / JS stacks — the app's own JavaScript path is built from these tutorials,
    # and without them a spoken "import react" is indistinguishable from noise.
    "react": "react",
    "reactdom": "react-dom",
    "vue": "vue",
    "svelte": "svelte",
    "express": "express",
    "axios": "axios",
    "tailwind": "tailwindcss",
    "npm": "npm",
    "flask_sqlalchemy": "flask-sqlalchemy",
    "bootstrap": "bootstrap",
}

# Common English/filler words that must never be treated as code identifiers.
_STOPWORDS = {
    "so", "that", "which", "the", "a", "an", "to", "it", "this", "then", "and",
    "for", "of", "in", "on", "is", "are", "with", "your", "our", "we", "you",
    "some", "any", "each", "them", "its", "here", "there", "now", "next", "also",
    "will", "can", "should", "into", "from", "our", "my", "his", "her",
    "all", "those", "these", "they", "what", "how", "why", "when", "who",
}

# Words that sit after "import the ..." in ordinary English and are never a
# package name. Without this, "import the modules we need" produced a milestone
# checking for `import modules`, which no learner can satisfy.
_GENERIC_IMPORT_NOUNS = {
    "module", "modules", "package", "packages", "library", "libraries",
    "standard", "necessary", "required", "needed", "following", "several",
    "other", "others", "relevant", "basic", "common", "appropriate",
    "corresponding", "respective", "same", "both", "these", "those",
    "code", "file", "files", "function", "functions", "class", "classes",
    "method", "methods", "thing", "stuff", "everything", "something",
}


def _is_generic_import_name(name: str) -> bool:
    root = (name or "").split(".")[0].strip().lower()
    return root in _GENERIC_IMPORT_NOUNS


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
_FIELD_MAX = 2000
_STEP_CHUNK_MAX = 800

# Speech-to-text / filler patterns that must never appear in learner-facing copy.
_TRANSCRIPT_FILLER = re.compile(
    r"\b(uh+|u+m+|er+|ah+|huh|yeah|y'know|you know|sort of|kind of|kinda|sorta|"
    r"i mean|basically|literally|right\?|gonna|wanna|gotta|okay so|alright so)\b",
    re.IGNORECASE,
)
_SPOKEN_FILLER_CHUNKS = re.compile(
    r"\b(it's not going to|what we want|we want is we|some kind of a|"
    r"we call (it|this|that)|as we call it)\b",
    re.IGNORECASE,
)
_NARRATIVE_PRINT = re.compile(
    r"\b(?:when|if|as|while|because|so that|where)\b.+\b(?:print|output|display)\b",
    re.IGNORECASE,
)


def _cap_field(text: str, max_len: int = _FIELD_MAX) -> str:
    """Clamp milestone text fields to the Pydantic model limit."""
    cleaned = (text or "").strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1] + "…"


def _is_multiline_code(text: str) -> bool:
    """Multi-line code (e.g. a Mojo/Python block in action/example) is not a caption dump."""
    lines = [ln for ln in (text or "").split("\n") if ln.strip()]
    if len(lines) < 2:
        return False
    codey = sum(1 for ln in lines if re.search(r"[(){}\[\]=:]|^\s{2,}\S", ln))
    return codey >= max(2, len(lines) // 2)


def looks_like_raw_transcript(text: str) -> bool:
    """True when text looks like unprocessed speech-to-text, not learner copy.

    Beginner multi-step instructions (30–50 words, backticks, numbered lists) must
    survive. Only wipe clear STT/filler dumps.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if _TRANSCRIPT_FILLER.search(cleaned) or _SPOKEN_FILLER_CHUNKS.search(cleaned):
        return True
    if _is_multiline_code(cleaned):
        return False
    structured = bool(
        re.search(r"(?m)^\s*\d+[.)]\s", cleaned)
        or "`" in cleaned
        or re.search(r"(?i)\b(import|from .+ import|def |class |print\()", cleaned)
    )
    words = cleaned.split()
    if len(words) > 70 and not structured:
        return True
    if len(words) > 55 and not structured and cleaned.count(".") == 0:
        return True
    if len(cleaned) > 160 and cleaned.count(",") >= 3 and not structured:
        return True
    if len(cleaned) > 90 and cleaned.count(".") == 0 and cleaned.count("`") == 0 and not structured:
        return True
    # Multi-word STT doubles (case-insensitive): "create a new create a new".
    if re.search(r"\b((?:\w+\s+){1,3}\w+)\s+\1\b", cleaned, re.IGNORECASE):
        return True
    # Single-word doubles only when same-case — avoids "up Up" from title glitches.
    if re.search(r"\b(\w+)\s+\1\b", cleaned):
        return True
    return False


def _kind_target_from_milestone(milestone: Milestone) -> tuple[str, str]:
    if not milestone.checks:
        return ("run_ok", "")
    c = milestone.checks[0]
    return (c.kind, c.target)


def scrub_learner_fields(milestone: Milestone, entry_file: str = "main.py") -> Milestone:
    """Replace transcript-like / weak / banned-video learner copy with beginner instructions.

    Used at generation time and when projecting a saved project, so already-stored
    courses improve on load when they still have jargon, STT dumps, or video refs.
    Non-empty clean AI action/teach/why/hint is preserved.
    """
    kind, tgt = _kind_target_from_milestone(milestone)
    safe_action = _action_for(kind, tgt, milestone.title, entry_file=entry_file)
    safe_obs = _observation_for(kind, tgt, milestone.title)
    action = milestone.microstep.action or ""
    if needs_learner_fallback(action):
        milestone.microstep.action = safe_action
    observation = milestone.microstep.observation or ""
    if needs_learner_fallback(observation, max_len=400):
        milestone.microstep.observation = safe_obs
    hint = milestone.microstep.hint or ""
    if needs_learner_fallback(hint, max_len=280):
        from .project_copy import learner_hint
        milestone.microstep.hint = learner_hint(kind, tgt)
    if (
        looks_like_raw_transcript(milestone.hook)
        or contains_banned_video_phrase(milestone.hook)
        or len((milestone.hook or "").split()) > 24
    ):
        milestone.hook = (milestone.title or "")[:80]
    teach = milestone.teach or ""
    if looks_like_raw_transcript(teach) or contains_banned_video_phrase(teach):
        milestone.teach = ""
    elif len(teach.split()) > 110:
        from .project_copy import _first_sentences
        trimmed = _first_sentences(teach, 3, 900)
        milestone.teach = trimmed if len(trimmed.split()) <= 110 else " ".join(teach.split()[:100]) + "…"
    if not (milestone.teach or "").strip():
        from .project_copy import _ai_teach_fallback
        milestone.teach = _ai_teach_fallback(milestone)
    if not (milestone.teach or "").strip() and kind in {
        "import", "symbol", "function_call", "code_contains",
    }:
        milestone.teach = beginner_teach(kind, tgt, title=milestone.title)
    why = milestone.why or ""
    if not why.strip() or contains_banned_video_phrase(why) or looks_like_raw_transcript(why):
        title = (milestone.title or "the project")[:80]
        milestone.why = (
            f"This step unlocks the next part of “{title}” in the source tutorial."
        )[:2000]
    if looks_like_raw_transcript(milestone.example) or contains_banned_video_phrase(milestone.example):
        milestone.example = ""
    desc = milestone.source_grounded_description or ""
    if contains_banned_video_phrase(desc) or looks_like_raw_transcript(desc):
        from .project_copy import learner_description
        milestone.source_grounded_description = learner_description(
            kind, tgt, title=milestone.title or "", entry_file=entry_file, project_title=""
        )
    return milestone




_WEAK_CHECK_WORDS = {
    "setup", "basic", "user", "import", "loops", "functions", "variables", "implement",
    "create", "build", "write", "add", "the", "and", "for", "with", "this", "that",
    "from", "your", "step", "work", "next", "code", "mojo", "python", "cli", "package",
    "error", "handling", "basics", "statements", "hello", "world", "full", "course",
    "train", "final", "define", "test",
    "class", "def", "return", "true", "false", "none", "pass", "self", "print",
    "var", "let", "fn", "if", "else", "elif", "while", "try", "except", "raise",
    "new", "const", "null", "void", "int", "str", "bool", "type", "main",
}


def _repair_weak_checks(project: ProjectCourse) -> None:
    """Replace hollow title-word check targets with tokens from action/example."""
    for m in project.milestones:
        action = (m.microstep.action or "")
        example = (m.example or "")
        title = (m.title or "")
        src = f"{example} {action}"
        new_checks = []
        for c in (m.checks or []):
            kind = (c.kind or "").lower()
            target = (c.target or "").strip()
            tgt_l = target.lower().rstrip(",:.")
            title_word = (
                bool(target)
                and target[:1].isupper()
                and " " not in target
                and len(target) <= 16
                and tgt_l in title.lower()
            )
            weak = (
                kind in {"code_contains", "symbol", "import", "function_call"}
                and (not tgt_l or tgt_l in _WEAK_CHECK_WORDS or title_word or target.endswith(":"))
            )
            if not weak:
                new_checks.append(c)
                continue
            token = ""
            m2 = re.search(
                r"\b(__init__|backward|_backward|Value|tanh|SIMD|struct|"
                r"loss|grad|parameters|forward|assert|Neuron|Embedding|attention|MLP|Layer)\b",
                src,
            )
            if m2:
                token = m2.group(1)
            if not token:
                m3 = re.search(r"`([^`]+)`", src)
                if m3:
                    frag = m3.group(1)
                    m4 = re.search(r"\b([A-Za-z_][A-Za-z0-9_]{1,})\b", frag)
                    token = (m4.group(1) if m4 else frag.split("(")[0].strip())[:40]
            if not token and example:
                m5 = re.search(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\b", example)
                token = m5.group(1) if m5 else ""
            if token and token.lower().rstrip(",:.") not in _WEAK_CHECK_WORDS:
                try:
                    new_checks.append(
                        c.model_copy(update={"kind": "code_contains", "target": token})
                    )
                except Exception:
                    c.target = token
                    c.kind = "code_contains"
                    new_checks.append(c)
            elif re.search(r"(?i)\b(cli|build|run|package|verify|smoke|final|train)\b", title):
                from .project_models import VerificationCheck
                new_checks.append(
                    VerificationCheck(
                        kind="run_ok",
                        target="",
                        description="Project runs without errors.",
                    )
                )
            else:
                new_checks.append(c)
        if new_checks:
            m.checks = new_checks


def _ensure_actions_name_entry(project: ProjectCourse) -> None:
    """After enrich/scrub, guarantee every action names the workspace entry file."""
    entry = (project.entry_file or "").strip() or "main.py"
    for m in project.milestones:
        action = (m.microstep.action or "").strip()
        if not action:
            continue
        if entry in action:
            continue
        rest = action[0].lower() + action[1:] if action[0].isupper() else action
        if re.match(r"(?i)in\s+`", rest):
            continue
        m.microstep.action = f"In `{entry}`, {rest}"[:400]


def scrub_project_learner_copy(project: ProjectCourse) -> ProjectCourse:
    entry = (project.entry_file or "").strip() or "main.py"
    for m in project.milestones:
        scrub_learner_fields(m, entry_file=entry)
    # Goal/intro are short prose sentences, not microstep instructions: a topic list
    # ("variables, control flow, functions, ...") is normal English, so judge them with
    # _looks_like_raw_prose. The instruction heuristic (>=3 commas => raw) wiped good
    # AI goals/intros and swapped in a template.
    if _looks_like_raw_prose(project.course_intro) or len(project.course_intro.split()) > 80:
        project.course_intro = ""
    if _looks_like_raw_prose(project.project_goal):
        project.project_goal = _synthesize_project_goal(project.title, project.tech_stack)
    _repair_weak_checks(project)
    _ensure_actions_name_entry(project)
    return project


def _looks_like_raw_prose(text: str | None) -> bool:
    """Caption dump detector for goal/intro prose (sentences with lists are fine)."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return False
    if _TRANSCRIPT_FILLER.search(cleaned) or _SPOKEN_FILLER_CHUNKS.search(cleaned):
        return True
    words = cleaned.split()
    stops = cleaned.count(".") + cleaned.count("!") + cleaned.count("?")
    if len(words) > 55 and stops == 0:
        return True
    if re.search(r"\b((?:\w+\s+){1,3}\w+)\s+\1\b", cleaned, re.IGNORECASE):
        return True
    if re.search(r"\b(\w+)\s+\1\b", cleaned):
        return True
    return False


def _synthesize_project_goal(title: str, tech_stack: list[str]) -> str:
    """Learner-facing project goal — never the first raw transcript sentence."""
    name = title.strip() or "this project"
    stack = ", ".join(tech_stack[:4])
    if stack:
        return f"Build “{name}” step by step with {stack}."
    return f"Build “{name}” step by step."


def _action_for(
    kind: str,
    target: str,
    title: str = "",
    source_label: str = "",
    entry_file: str = "main.py",
) -> str:
    """Beginner step-by-step task — what to type/import/check, never pass/fail jargon."""
    return beginner_action(
        kind,
        target,
        entry_file=entry_file or "main.py",
        title=title,
        source_label=source_label,
    )


def _observation_for(kind: str, target: str, title: str) -> str:
    """One short sentence — what this milestone is about."""
    return beginner_observation(kind, target, title=title)


def _chunk_long_step(text: str, max_len: int = _STEP_CHUNK_MAX) -> list[str]:
    """Break dense transcript blobs into smaller step-sized chunks."""
    if len(text) <= max_len:
        return [text]
    chunks: list[str] = []
    words = text.split()
    current: list[str] = []
    length = 0
    for word in words:
        extra = len(word) + (1 if current else 0)
        if current and length + extra > max_len:
            chunks.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += extra
    if current:
        chunks.append(" ".join(current))
    return chunks


def _clip(text: str, max_len: int, suffix: str = "…") -> str:
    """Truncate text to fit Pydantic field limits without breaking validation."""
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    if max_len <= len(suffix):
        return text[:max_len]
    return text[: max_len - len(suffix)] + suffix


def _chunk_long_step(sentence: str, max_len: int = 800) -> list[str]:
    """Break dense transcript blobs into smaller step-sized chunks."""
    sentence = sentence.strip()
    if len(sentence) <= max_len:
        return [sentence]
    chunks: list[str] = []
    words = sentence.split()
    current: list[str] = []
    current_len = 0
    for word in words:
        add_len = len(word) + (1 if current else 0)
        if current and current_len + add_len > max_len:
            chunks.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += add_len
    if current:
        chunks.append(" ".join(current))
    return chunks


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
            if not sentence:
                continue
            for chunk in _chunk_long_step(sentence):
                raw_lines.append(chunk)
    return raw_lines


# Action-like leads used to carve a long unpunctuated caption into windows.
# `from pkg import` is treated as one lead so we don't split on the inner `import`.
_ACTION_LEAD = re.compile(
    r"\b(?:from\s+[A-Za-z_][A-Za-z0-9_]*\s+import|"
    r"import|install(?:ing)?|"
    r"define|create|write|implement|"
    r"call|"
    r"print(?:\s*\(|\s+(?:the\s+)?(?:result|output|value|it)))\b",
    re.IGNORECASE,
)


def _windows_for_extraction(sentence: str) -> list[str]:
    """Split a long caption into per-action windows; leave short sentences intact."""
    text = (sentence or "").strip()
    if not text:
        return []
    if len(text) <= 220:
        return [text]
    starts = [m.start() for m in _ACTION_LEAD.finditer(text)]
    if len(starts) < 2:
        return [text]
    windows: list[str] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            windows.append(chunk)
    return windows or [text]


def _reject(name: str | None) -> bool:
    """True if a captured identifier is not a usable code symbol."""
    if not name or len(name) < 2:
        return True
    low = name.lower()
    return low in _ACTION_VERBS or low in _STOPWORDS or low in _CLOSED_CLASS


#: Closed-class words: determiners, quantifiers, ordinals, pronouns, conjunctions
#: and verbs of speech. Nobody names a package or a function one of these, so a
#: capture that lands here grabbed the word after the verb rather than the thing
#: being written — "create the function first", "import or any npm options".
_CLOSED_CLASS_RAW = {
    "let", "lets", "this", "that", "these", "those", "there", "here", "then",
    "than", "too", "very", "just", "also", "still", "even", "only", "own",
    "same", "other", "others", "another", "such", "each", "every", "both",
    "either", "neither", "few", "many", "much", "more", "most", "less",
    "least", "enough", "several", "couple", "stuff", "things", "something",
    "anything", "nothing", "everything", "whatever", "whoever", "however",
    "because", "since", "unless", "although", "though", "while", "whereas",
    "nor", "or", "so", "yet", "instead", "indeed", "actually", "literally",
    "simply", "exactly", "roughly", "maybe", "perhaps", "mostly", "usually",
    "first", "second", "third", "fourth", "fifth", "next", "last", "final",
    "whole", "entire", "full", "complete", "remaining", "rest", "additional",
    "used", "use", "using", "called", "named", "say", "says", "said", "see",
    "go", "goes", "going", "get", "gets", "got", "makes", "want",
    "wants", "need", "needs", "have", "has", "had", "does", "did", "done",
    "object", "variable", "instance", "value", "name", "type", "number",
    "string", "list", "item", "items", "result", "results", "way", "case",
    "time", "times", "day", "part", "bit", "lot", "bunch", "kind", "sort",
}

#: Anything a learner could legitimately `import` is a name, not filler: "import
#: time" is a milestone, and "time" only landed above because it is also an noun.
_REAL_MODULES = frozenset(getattr(sys, "stdlib_module_names", ())) | frozenset(KNOWN_TECH)

_CLOSED_CLASS = {w for w in _CLOSED_CLASS_RAW if w not in _REAL_MODULES}


def _is_corroborated_package(name: str, corpus: str) -> bool:
    """A package the source really imports — not merely the word after "import".

    Spoken captions put ordinary English where a tutorial puts a module name:
    "import believe it or not a method called", "I'm going to import the entire
    react library", "install additional packages that". A wrong import check is
    worse than a missing one — the learner can never pass it, and the milestone
    stalls the course — so an unfamiliar name must be corroborated first. A real
    statement on its own line, a stdlib or known package, or the same import named
    repeatedly all corroborate; one stray adjective does not.
    """
    if not name:
        return False
    if name.split(".")[0].lower() in _REAL_MODULES or name in KNOWN_TECH.values():
        return True
    if re.search(r"[_.\d]", name):                       # flask_sqlalchemy, gpt2
        return True
    if re.search(r"[a-z][A-Z]|[A-Z]{2,}", name):         # camelCase / ALLCAPS
        return True
    esc = re.escape(name)
    # A code statement, not a sentence that happens to open with the verb: real
    # imports end there or continue with `as`, `(` or a comma.
    if re.search(
        rf"^\s*(?:>>> )?(?:import|from)\s+{esc}\b\s*(?:$|\bas\b|[(,])",
        corpus,
        re.IGNORECASE | re.MULTILINE,
    ):
        return True
    return len(re.findall(rf"\b(?:import|from)\s+{esc}\b", corpus, re.IGNORECASE)) >= 2


def _canonical_import_name(name: str) -> str:
    """Map a captured import token onto the real package name.

    Spoken transcripts often Title-Case packages (`Transformers`). Known tech
    uses the curated canonical name; other Title-Case tokens become pep-8
    lowercase. CamelCase / ALLCAPS identifiers are left alone.
    """
    root = (name or "").split(".")[0]
    if not root:
        return root
    low = root.lower()
    canon = KNOWN_TECH.get(low)
    # Tech-stack labels may be hyphenated (scikit-learn); import names cannot.
    if canon and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", canon):
        return canon
    return code_ident_for_import(root)


#: Words that legitimately follow a named symbol in speech. Anything else after
#: "called X" means the caption split a longer identifier into two words.
_NAME_TAIL = {
    "function", "functions", "class", "classes", "method", "methods", "variable",
    "module", "modules", "object", "dataclass", "that", "which", "what", "to",
    "and", "or", "but", "in", "on", "for", "with", "so", "then", "now", "here",
    "there", "will", "would", "can", "does", "did", "is", "are", "it", "this",
    "we", "you", "they", "he", "she", "of", "as", "at", "by", "from", "returns",
    "return", "takes", "take", "called", "named", "like", "just", "also", "again",
    "out", "up", "down", "over", "about", "we'll", "i'll", "you", "lets",
}


def _name_is_split(sentence: str, end: int) -> bool:
    """True when the captured identifier is only half of the name spoken.

    Captions have no camelCase: "a function called handle submit" is
    `handleSubmit`, and "call the Dot Upper function" is `.upper()`. A check for
    `handle` alone can never pass, and a milestone the learner cannot clear stops
    the whole course, so a split name is dropped rather than guessed at.
    """
    rest = sentence[end:].lstrip()
    m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)", rest)
    if not m:
        return False
    nxt = m.group(1).lower()
    if len(nxt) < 2 or nxt in _NAME_TAIL:
        return False
    # A participle describes the symbol ("sample containing some text"), it is
    # not the second half of its name.
    return not (nxt.endswith("ing") or nxt.endswith("ed"))


def _extract_target(sentence: str, corpus: str = "") -> tuple[str, str] | None:
    """Derive a verification (kind, target) from a step sentence.

    Identifier case is preserved for symbols (captured from the original
    sentence with case-insensitive keyword matching) so a check for `GPT`
    matches the learner's real class name — not a lowercased `gpt`.

    Import names are canonicalized (Transformers → transformers) so instructions
    and AST checks match the real package, and are only accepted when the source
    corroborates them as a package (`corpus` defaults to the sentence itself).

    Returns None when the sentence has no concrete, verifiable coding action.
    """
    IC = re.IGNORECASE
    s = sentence.lower()
    ground = corpus or sentence

    # `from pkg import Name` must win over the inner `import Name` so we don't
    # treat GPT2LMHeadModel as a module — but the from-import must be LOCAL to
    # this match. Searching the whole caption would overwrite `import torch`
    # with a later `from transformers import ...`.
    m = re.search(rf"\b(?:import|installing|install)\s+(?:the\s+)?(?:package\s+)?({_IDENT})", sentence, IC)
    if m:
        module = m.group(1)
        local = sentence[max(0, m.start() - 80) : m.end()]
        mf = re.search(
            rf"\bfrom\s+({_IDENT})\s+import\s+{re.escape(m.group(1))}\b",
            local,
            IC,
        )
        if mf:
            module = mf.group(1)
        canonical = _canonical_import_name(module)
        if (
            not _reject(canonical)
            and not _is_generic_import_name(canonical)
            and _is_corroborated_package(canonical, ground)
        ):
            return ("import", canonical)
        return None

    m = re.search(rf"\bfrom\s+({_IDENT})\s+import\b", sentence, IC)
    if m:
        canonical = _canonical_import_name(m.group(1))
        if (
            not _reject(canonical)
            and not _is_generic_import_name(canonical)
            and _is_corroborated_package(canonical, ground)
        ):
            return ("import", canonical)
        return None

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
        if not _reject(name) and not _name_is_split(sentence, m.end()):
            return ("symbol", name)

    # High-precision: an explicitly named *code* symbol — "a class called GPT",
    # "a variable named total", "a dataclass called GPTConfig". Bare "called X"
    # in lecture speech ("we called this attention") is not a coding step.
    m = re.search(
        rf"\b(?:class|function|method|variable|dataclass|object|module)\s+"
        rf"(?:called|named)\s+({_IDENT})",
        sentence,
        IC,
    )
    if m and not _reject(m.group(1)) and not _name_is_split(sentence, m.end()):
        return ("symbol", m.group(1))
    m = re.search(
        rf"\b(?:define|write|create|implement|add)\s+(?:a\s+|an\s+|the\s+)?"
        rf"(?:class|function|method|variable|dataclass)\s+(?:called\s+|named\s+)?({_IDENT})",
        sentence,
        IC,
    )
    if m and not _reject(m.group(1)) and not _name_is_split(sentence, m.end()):
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
    if m and not _reject(m.group(1)):
        return ("symbol", m.group(1).lower())

    # "store ... in a variable X"
    m = re.search(rf"\bstore\b.*?\bin\s+(?:a\s+|the\s+)?variable\s+(?:called\s+|named\s+)?({_IDENT})", sentence, IC)
    if m and not _reject(m.group(1)):
        return ("symbol", m.group(1))

    # call a specific function — not spoken "we call it X" / "we call this Y".
    m = re.search(rf"\bcall\s+(?:the\s+)?(?:function\s+)?({_IDENT})", sentence, IC)
    if m and _is_callable_target(m.group(1), sentence) and not _name_is_split(sentence, m.end()):
        return ("function_call", m.group(1))

    # print / output → explicit coding instructions only, not narrative lecture.
    if re.search(r"\bprint\s*\(", sentence) and not _NARRATIVE_PRINT.search(sentence):
        return ("stdout_contains", "")
    if re.search(r"^\s*(?:first|next|then|now|finally|let'?s)?[,:]?\s*(?:print|print the result)\b", s):
        return ("stdout_contains", "")
    if re.match(r"^\s*print\b", s) and not _NARRATIVE_PRINT.search(sentence):
        return ("stdout_contains", "")

    # run / execute / verify → explicit coding actions only. Bare "test" is too
    # common in English ("test data", "test set") to treat as a coding step.
    if re.search(
        r"\b(?:run (?:the |your )?(?:code|program|script|project|it)|"
        r"execute(?: it)?|verify (?:it|that)|check that it works)\b",
        s,
    ):
        return ("run_ok", "")

    return None


def _is_callable_target(name: str, sentence: str) -> bool:
    """True when `call X` refers to a real function, not ordinary speech."""
    if _reject(name):
        return False
    if re.search(r"\bcall\s+(?:it|this|that|them)\b", sentence, re.IGNORECASE):
        return False
    # Real code names: snake_case, CamelCase, or an explicit function/method.
    if "_" in name or (name[0].isupper() and any(ch.islower() for ch in name[1:])):
        return True
    if re.search(rf"\b(?:function|method)\s+{re.escape(name)}\b", sentence, re.IGNORECASE):
        return True
    if re.search(rf"\b{re.escape(name)}\s*\(", sentence):
        return True
    # A single lowercase English word is almost always speech, not a function.
    if name.isalpha() and name.islower():
        return False
    return not _reject(name)


def _is_step(sentence: str) -> bool:
    """True only for explicit coding instructions — not narrative transcript."""
    s = sentence.lower().strip()
    if looks_like_raw_transcript(sentence):
        return False
    if re.match(r"^\s*(?:step\s*)?\d+[.):]", s):
        return True
    # Strong structural signals (import/def/class).
    if re.search(r"\b(import|from\s+\w+\s+import|def\s+\w+|class\s+\w+)\b", s):
        return True
    # Imperative tutorial phrasing at the start of a sentence.
    if re.search(
        r"^(?:first|next|then|now|finally|let'?s)\b.*\b"
        r"(import|define|create|implement|add|write|build|install|set up|setup|"
        r"print|call)\b",
        s,
    ):
        # "let's call it X" is lecture speech, not a coding call.
        if re.search(r"\bcall\s+(?:it|this|that)\b", s):
            return False
        return True
    # Direct imperatives at sentence start — but not narrative "when we print...".
    if _NARRATIVE_PRINT.search(sentence):
        return False
    if re.match(
        r"^(?:import|define|create|implement|add|write|build|call|print|install)\b",
        s,
    ):
        if re.match(r"^call\s+(?:it|this|that)\b", s):
            return False
        return True
    return False


def _short_title(sentence: str, target: tuple[str, str]) -> str:
    kind, tgt = target
    if kind == "import":
        return f"Import {display_ident(tgt)}"
    if kind == "symbol":
        return f"Define {tgt}"
    if kind == "function_call":
        return f"Call {tgt}"
    if kind == "stdout_contains":
        m = re.search(r"\bprint(?:ing)?\s+(?:the\s+)?(\w+)", sentence, re.IGNORECASE)
        if m and m.group(1).lower() not in _STOPWORDS:
            return f"Print {m.group(1)}"
        return "Print output"
    if kind == "run_ok":
        return "Run and verify"
    # Fallback: the step's own words, with the narrator's trailing clauses cut.
    words = re.sub(r"^\s*(?:step\s*)?\d+[.):]\s*", "", sentence).split()
    title = _strip_speech_debris(" ".join(words[:8]))
    return title or "Implement step"


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
        if len(key) < 3:
            continue
        if re.search(rf"\b{re.escape(key)}\b", low) and name not in found:
            found.append(name)
    return found


def _detect_language(text: str) -> str:
    low = text.lower()
    # Very light heuristic; Python is the fully-supported verification target.
    if re.search(r"\b(npm|const |=>|node\.js|nodejs|document\.|console\.log)\b", low):
        return "javascript"
    return "python"


# Phrase → acceptable code token(s) for concept-level checks.
# Prefer long, specific phrases. Short needles like "optim"/"test"/"loss" are
# dangerous because they false-match English ("optimization", "test data").
CONCEPT_TOKENS: list[tuple[str, str]] = [
    ("hello world", "print|hello"),
    ("getting user input", "input"),
    ("user input", "input"),
    ("if/else statements", "if|else"),
    ("if/else", "if|else"),
    ("loops & functions", "for|while|fn|def"),
    ("loops and functions", "for|while|fn|def"),
    ("python vs mojo functions", "fn|def"),
    ("importing libraries", "import"),
    ("error handling", "raises|except|Error"),
    ("variable scope", "var|let|scope"),
    ("decorators & metaprogramming", "decorator"),
    ("metaprogramming", "decorator|param"),
    ("local jupyter notebook", "jupyter|notebook"),
    ("jupyter notebook", "jupyter|notebook"),
    ("setting up", "modular|mojo"),
    ("mojo cli", "cli|main"),
    ("variables, declarations, and datatypes", "var|let|Int|String"),
    ("declarations, and datatypes", "var|let|Int|String"),
    ("oop", "struct|class"),
    ("flash attention", "scaled_dot_product_attention|flash"),
    ("self-attention", "attention"),
    ("nn.module", "nn.Module"),
    ("forward pass", "def forward"),
    ("cross entropy", "cross_entropy|CrossEntropyLoss"),
    ("from_pretrained", "from_pretrained"),
    ("huggingface", "from_pretrained|GPT2LMHeadModel"),
    ("tiktoken", "tiktoken"),
    ("tokenization", "tiktoken|encode"),
    ("sampling loop", "topk|multinomial|generate|sample"),
    ("adamw", "AdamW"),
    ("data loader", "DataLoader|dataloader"),
    ("dataloader", "DataLoader|dataloader"),
    ("data batches", "DataLoader|batch"),
    ("parameter sharing", "lm_head|wte"),
    ("parameters of the neural", "parameters|state_dict"),
    ("mixed precision", "autocast|bfloat16"),
    ("bfloat16", "bfloat16"),
    ("float16", "float16|autocast"),
    ("tf32", "tf32|set_float32_matmul_precision"),
    ("tensor core", "matmul"),
    ("torch.compile", "torch.compile|compile"),
    ("gradient clipping", "clip_grad_norm|clip_grad"),
    ("gradient accumulation", "accum"),
    ("learning rate", "lr|learning_rate"),
    ("weight decay", "weight_decay"),
    ("distributed data parallel", "DistributedDataParallel|DDP"),
    ("gradient descent", "backward|grad|parameters"),
    ("backpropagation", "backward|grad"),
    ("backprop", "backward|grad"),
    ("micrograd", "Value|micrograd"),
    ("value object", "Value"),
    ("multi-layer perceptron", "MLP|Neuron|Layer"),
    ("neural net", "MLP|Neuron|nn"),
    ("neural network", "MLP|Neuron|nn"),
    ("linear regression", "LinearRegression|sklearn"),
    ("k nearest", "KNeighbors|knn"),
    ("k-nearest", "KNeighbors|knn"),
    ("k-means", "KMeans|kmeans"),
    ("k means", "KMeans|kmeans"),
    ("support vector", "SVC|SVM|sklearn"),
    ("saving models", "pickle|joblib|dump"),
    ("plotting data", "matplotlib|plt|plot"),
    ("fineweb", "fineweb|dataset"),
    ("hellaswag", "hellaswag|eval"),
    ("logits", "logits"),
    ("tanh", "tanh"),
    ("residual", "residual"),
    ("warmup", "warmup"),
]

# Word-boundary-only needles (never matched as a substring of a longer English word).
_CONCEPT_WORDS: list[tuple[str, str]] = [
    ("attention", "attention"),
    ("logits", "logits"),
    ("tiktoken", "tiktoken"),
    ("checkpoint", "from_pretrained|state_dict"),
    ("adamw", "AdamW"),
    ("dataloader", "DataLoader|dataloader"),
    ("residual", "residual"),
    ("bfloat16", "bfloat16"),
    ("scheduler", "cosine|warmup|lr"),
    ("ddp", "DistributedDataParallel|DDP|dist"),
    ("dataset", "dataset|load"),
    ("hyperparameter", "config|Config"),
    ("micrograd", "Value|micrograd"),
    ("backprop", "backward|grad"),
    ("derivative", "grad|derivative"),
    ("neuron", "Neuron|Linear|tanh"),
    ("knn", "KNeighbors|knn"),
    ("svm", "SVC|SVM|sklearn"),
    ("pytorch", "torch"),
    ("sklearn", "sklearn"),
]

# Chapter heading → the action the learner performs. A chapter is a line in the
# creator's table of contents — "K-Nearest Neighbors Part 2 – Algorithm
# Explanation" — and a milestone has to read as something to do. These needles are
# deliberately specific; short ones ("model", "train", "hook") match too much
# English and are handled by the fallback instead.
CONCEPT_LABELS: list[tuple[str, str]] = [
    (r"setting\s+up|^setup$", "Set up the environment"),
    (r"hello\s+world", "Write Hello World"),
    (r"if/?else", "Implement IF/ELSE"),
    (r"^oop$|\boop\b", "Implement OOP"),
    (r"variables?(?:\s*,\s*declarations?)?(?:\s*,?\s*and\s+datatypes?)?", "Declare variables and datatypes"),
    (r"getting\s+user\s+input|user\s+input", "Read user input"),
    (r"loops?\s*&\s*functions?|loops?\s+and\s+functions?", "Write loops and functions"),
    (r"\bsimd\b", "Use SIMD"),
    (r"micrograd", "Build the micrograd engine"),
    (r"backpropagat", "Implement backpropagation"),
    (r"value object", "Build the Value object"),
    (r"multi-?layer perceptron|\bmlp\b", "Build a multi-layer perceptron"),
    (r"neural nets?|neural network", "Build a neural network"),
    (r"linear regression.*(?:data|load|analy|inspect|explor)", "Load and analyze data for linear regression"),
    (r"linear regression.*(?:model|fit|train|implement)", "Fit a linear regression model"),
    (r"linear regression", "Implement linear regression"),
    (r"logistic regression", "Implement logistic regression"),
    (r"k-?nearest|\bknn\b", "Implement k-nearest neighbors"),
    (r"support vector|\bsvm\b", "Implement a support vector machine"),
    (r"k-?means|clustering", "Implement k-means clustering"),
    (r"gradient descent", "Train with gradient descent"),
    (r"forward pass", "Implement the forward pass"),
    (r"self-?attention|attention head|attention layer", "Implement self-attention"),
    (r"embedding", "Add the embedding layers"),
    (r"text classification", "Classify text with a neural network"),
    (r"tokeni[sz]|tokenizer|tiktoken", "Build the tokenizer"),
    (r"data ?loader|dataloader|loading & looking at data", "Build the data loader"),
    (r"sampling loop|generate text|text generation", "Write the sampling loop"),
    (r"loss function|cross entropy", "Compute the cross entropy loss"),
    (r"optimizer", "Wire up the optimizer"),
    (r"saving and loading|save and load|loading models|saving models|parameters saved", "Save and reload the model"),
    (r"chat ?bot|chatbot", "Build the chat bot"),
    (r"collision", "Detect collisions precisely"),
    (r"\bneat\b|neuroevolution|fitness function", "Evolve the network with NEAT"),
    (r"flappy|pygame|game loop", "Build the game loop"),
    (r"graphics|drawing|render(ing|s) the", "Draw the graphics"),
    (r"flask", "Build the Flask app"),
    (r"rest api|api endpoint|\broutes?\b", "Add the API routes"),
    (r"database|sqlite|sqlalchemy", "Create the database model"),
    (r"deprecat|error handling|validat", "Handle bad input"),
    (r"deploy|deployment", "Deploy the app"),
    (r"component", "Build the component"),
    (r"usestate|\bstate\b", "Manage component state"),
    (r"\bprops\b", "Pass data down with props"),
    (r"styling|\bcss\b|tailwind|bootstrap", "Style the interface"),
    (r"\bforms?\b|\bsubmit\b|input field", "Handle the form input"),
    (r"event handler|onclick|handle ?click", "Wire up the click handler"),
    (r"parameters of the neural", "Collect the parameters of the neural net"),
    (r"map over|list rendering|render the list", "Render a list"),
]

#: Most specific needle first, so a chapter naming several concepts is titled by
#: the one it actually teaches. Specificity is the longest *alternative* in the
#: needle, not its raw length: "neural nets?|neural network" is a longer string
#: than "parameters of the neural" but a weaker match, and ranking by string
#: length titled that chapter "Build a neural network" while its check graded
#: `parameters` — the learner reading one thing and being graded for another.
def _specificity(needle: str) -> int:
    return max(len(part) for part in needle.split("|"))


_CONCEPT_LABELS_BY_SPECIFICITY = sorted(CONCEPT_LABELS, key=lambda kv: -_specificity(kv[0]))

#: Longest a milestone title reads as a label rather than a sentence.
_TITLE_MAX = 56

#: Gerunds that open a chapter heading, mapped to the imperative the learner reads.
_GERUND_VERB = {
    "creating": "Build", "building": "Build", "making": "Make", "coding": "Code",
    "implementing": "Implement", "writing": "Write", "defining": "Define",
    "adding": "Add", "training": "Train", "loading": "Load", "saving": "Save",
    "testing": "Test", "using": "Use", "running": "Run", "moving": "Move",
    "drawing": "Draw", "finishing": "Finish", "setting": "Set up",
    "installing": "Install", "importing": "Import", "configuring": "Configure",
    "deploying": "Deploy", "designing": "Design", "handling": "Handle",
    "connecting": "Connect", "preparing": "Prepare", "exploring": "Explore",
    "checking": "Check", "fixing": "Fix", "debugging": "Debug", "viewing": "View",
    "showing": "Show", "updating": "Update", "deleting": "Delete",
    "removing": "Remove", "starting": "Start", "trying": "Try",
    "classifying": "Classify", "generating": "Generate", "sampling": "Sample",
    "plotting": "Plot", "visualizing": "Visualize", "analysing": "Analyze",
    "analyzing": "Analyze", "scaling": "Scale", "shaping": "Shape",
}

_IMPERATIVE_LEAD = re.compile(
    r"^\s*(?:implement|build|create|write|define|add|train|load|save|test|use|run|"
    r"configure|deploy|make|set up|install|import|handle|connect|draw|move|fix|"
    r"debug|plot|visualize|classify|generate|sample|wire|manage|pass|render|style|"
    r"detect|evolve|compute|finish|check|explore|prepare|start)\b",
    re.IGNORECASE,
)

_IMPLEMENTATION_HINT = re.compile(
    r"implement|nn\.module|forward pass|data loader|dataloader|flash attention|"
    r"adamw|gradient clip|from_pretrained|torch\.compile|cross entropy|"
    r"sampling loop|hyperparameter|tiktoken|define a (?:class|function|dataclass)",
    re.IGNORECASE,
)

_CODE_SIGNAL = re.compile(
    r"\b(?:import\s+[A-Za-z_]\w*|from\s+[A-Za-z_]\w*\s+import|"
    r"def\s+[A-Za-z_]\w*|class\s+[A-Za-z_]\w*|"
    r"define\s+(?:a\s+|an\s+|the\s+)?(?:function|class|method|variable|dataclass)|"
    r"create\s+(?:a\s+|an\s+|the\s+)?(?:function|class|method|variable)|"
    r"pip install)\b",
    re.IGNORECASE,
)

_NOT_ENOUGH_MATERIAL = (
    "This source does not contain enough hands-on coding material to build a guided project. "
    "It reads like a lecture or overview, not a build-along tutorial. "
    "Use a video or transcript that actually implements code — with steps such as importing "
    "libraries, defining functions or classes, and running the program."
)
_META_CHAPTER = re.compile(
    r"^(intro|introduction|welcome|outro|summary|conclusion|recap|results?|"
    r"shoutout|thanks|corrections?|errata|q&a|questions|final thoughts|"
    r"series preview|some final words|notation)\b",
    re.IGNORECASE,
)
# Real code identifiers: inner capitals (DataLoader) or ALLCAPS+digits (TF32).
# Title-Case English ("Biology", "Aliens") must NOT count — that false-accepted podcasts.
_CAMEL = re.compile(r"\b([A-Z][a-z]+[A-Z][A-Za-z0-9]*)\b")
_DIGITAL_ACRONYM = re.compile(r"\b([A-Z]{2,}[0-9]+)\b")
_DOTTED = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_.]*)\b")

_CONVERSATION_SOURCE = re.compile(
    r"\b(podcast|interview|today'?s guest|welcome to the (?:show|podcast)|"
    r"sit(?:ting)? down with|fireside chat|q\s*&\s*a episode)\b",
    re.IGNORECASE,
)

_TEACH_SIGNAL = re.compile(
    r"\b(implement|from scratch|step[- ]by[- ]step|follow along|tutorial|"
    r"walkthrough|let'?s (?:build|write|code|implement|create)|"
    r"hands[- ]on|live coding|build along|coding along|"
    r"github\.com|jupyter|colab|starter code|exercise|"
    r"backpropagat|micrograd|define (?:a |the )?(?:class|function))\b",
    re.IGNORECASE,
)

_JUNK_HEAD_WORDS = {
    "github", "youtube", "http", "https", "www", "com", "watch", "subscribe",
    "tutorial", "course", "lesson", "python", "introduction", "overview",
}

_STRONG_CONCEPT = re.compile(
    r"\b(regression|knn|svm|means|implement|neural|backprop|micrograd|"
    r"attention|tokenizer|dataloader|gradient|derivative|perceptron|"
    r"saving|plotting|sklearn|pytorch|forward|backward|value object|"
    r"hello\s+world|variables?|datatypes?|functions?|loops?|oop|"
    r"classes?|structs?|decorators?|exceptions?|simd|jupyter)\b",
    re.IGNORECASE,
)
_INSTRUCTIONAL_HEADING = re.compile(
    r"\b(implement|build|code|function|class|train|grad|backprop|deriv|"
    r"example|exercise|dataset|model|layer|network|forward|backward|"
    r"install|import|debug|fix|write|create|neural|tensor|attention|"
    r"token|parser|api|regression|knn|svm|means|perceptron|tanh|"
    r"micrograd|pytorch|numpy|sklearn|tutorial|algorithm|optim|"
    r"value object|neuron|mlp|dataloader|saving|plotting|linear|"
    r"transformer|logits|loss function|expression graph|expression|"
    r"hello\s+world|variables?|declarations?|datatypes?|data\s+types?|"
    r"user\s+input|if/?else|conditionals?|loops?|functions?|methods?|"
    r"oop|object[- ]oriented|classes?|structs?|libraries?|exceptions?|"
    r"error\s+handling|decorators?|metaprogramming|jupyter|notebook|"
    r"setting\s+up|setup|cli|simd|ownership|borrow(?:ed|ing)?)\b",
    re.IGNORECASE,
)

#: Language-intro / freeCodeCamp-style syllabus chapters. These rarely contain
#: ML jargon, but they ARE the ordered implementation sequence for the course.
_SYLLABUS_CHAPTER = re.compile(
    r"\b(?:hello\s+world|variables?|declarations?|datatypes?|data\s+types?|"
    r"user\s+input|if/?else|conditionals?|loops?|functions?|methods?|"
    r"classes?|objects?|oop|object[- ]oriented|imports?|libraries?|"
    r"exceptions?|error\s+handling|decorators?|metaprogramming|"
    r"jupyter|notebook|setting\s+up|setup|cli|compilers?|interpreters?|"
    r"structs?|ownership|borrow(?:ed|ing)?|simd|print)\b",
    re.IGNORECASE,
)



def _clean_chapter(title: str) -> str:
    t = re.sub(r"^\s*section\s*\d+\s*:\s*", "", title, flags=re.IGNORECASE)
    t = re.sub(r"^\s*(?:let['’]?s|lets)\s+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*,?\s*\d+\s*ms\b", "", t)              # drop timing annotations "333ms"
    t = re.sub(r"\s*\([^)]*\)\s*$", "", t)                 # drop trailing "(...)"
    t = t.strip(" -–—:•\t")
    return t


def _clip_words(text: str, max_len: int = _TITLE_MAX) -> str:
    """Shorten a label at a word boundary.

    `_clip` cut mid-token, which put "…Shakespear", "previou" and "implemen" in
    front of learners — a truncated identifier reads as a typo in the task.
    """
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if len(text) <= max_len:
        return text
    head = text[:max_len]
    if " " in head:
        head = head.rsplit(" ", 1)[0]
    else:
        head = text[:max_len]
    return head.strip(" ,;:-–—")


def _strip_speech_debris(text: str) -> str:
    """Reduce a spoken phrase to the step it names.

    Captions run on: "train these Transformers um", "create the loss function uh
    so they will give us the correct". The step is the first clause; the rest is
    the narrator thinking out loud.
    """
    t = re.sub(r"^\s*(?:step\s*)?\d+[.):]\s*", "", (text or "").strip())
    t = _SPOKEN_FILLER_CHUNKS.sub(" ", t)
    t = _TRANSCRIPT_FILLER.sub(" ", t)
    t = re.sub(r"\b(?:uh+|um+|er+|ah+)\b", " ", t, flags=re.IGNORECASE)
    # Captions double words, sometimes in pairs: "create a new a new endpoint".
    t = re.sub(r"\b((?:\w+\s+){1,2}\w+)(?:\s+\1\b)+", r"\1", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip(" ,;:-–—")
    # Preserve "if/else" so the speech-clause split does not eat a leading "IF".
    _ifelse_mark = "\x00IFELSE\x00"
    t = re.sub(r"(?i)\bif\s*/\s*else\b", _ifelse_mark, t)
    # A trailing conjunction or copula is the narrator continuing, not the step.
    t = re.split(
        r"\b(?:but|because|which|since|while|although|so that|and so|so we|then we|"
        r"we|you|i|they|it's|this is|that's|is|am|are|here|there|how|what|if)\b",
        t,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip(" ,;:-–—")
    t = t.replace(_ifelse_mark, "IF/ELSE")
    # Captions get cut mid-phrase, leaving a dangling function word on the end.
    while True:
        words = t.split()
        if len(words) > 2 and words[-1].lower().rstrip(".,") in _DANGLING_TAIL:
            t = " ".join(words[:-1])
            continue
        return _clip_words(t)


_DANGLING_TAIL = {
    "a", "an", "the", "and", "or", "to", "of", "in", "on", "for", "with", "as",
    "at", "by", "from", "that", "this", "it", "its", "so", "then", "than",
}


def _dedupe_verb_rest(verb: str, rest: str) -> str:
    """Drop rest words that duplicate the verb's trailing words (Set up + Up)."""
    vw = (verb or "").split()
    rw = (rest or "").split()
    if not vw or not rw:
        return rest or ""
    for n in range(min(len(vw), len(rw)), 0, -1):
        if [w.lower() for w in vw[-n:]] == [w.lower() for w in rw[:n]]:
            return " ".join(rw[n:])
    return rest or ""


def _chapter_title(chapter: str) -> str:
    """A learner-facing action for a chapter, not its table-of-contents label.

    "K-Nearest Neighbors Part 2 – Algorithm Explanation" is what the creator
    titled the segment; what the learner does is implement k-nearest neighbors.
    """
    cleaned = _clean_chapter(chapter)
    low = cleaned.lower()
    for needle, label in _CONCEPT_LABELS_BY_SPECIFICITY:
        if re.search(needle, low):
            return label
    phrase = _strip_speech_debris(cleaned)
    phrase = re.sub(r"\bpart\s*\d+\b", "", phrase, flags=re.IGNORECASE).strip(" -–—:•,")
    if not phrase:
        return ""
    # Short syllabus acronyms (OOP, SIMD, CLI) are real chapters even when len < 4.
    if len(phrase) < 4 and not _SYLLABUS_CHAPTER.search(phrase):
        return ""
    lead = phrase.split()[0].lower().rstrip(",")
    if lead in _GERUND_VERB:
        verb = _GERUND_VERB[lead]
        rest = phrase.split(None, 1)[1] if " " in phrase else ""
        rest = _dedupe_verb_rest(verb, rest)
        if rest:
            return _clip_words(f"{verb} {rest}")
        # Bare "Setting Up" (verb already ate "Up") → concrete learner task.
        if lead == "setting":
            return "Set up the environment"
        return verb
    if _IMPERATIVE_LEAD.match(phrase):
        return phrase[:1].upper() + phrase[1:]
    # Keep ALLCAPS syllabus tokens readable: OOP / SIMD, not oOP / sIMD.
    words = phrase.split()
    if len(words) == 1 and phrase.isupper() and 2 <= len(phrase) <= 6:
        return f"Implement {phrase}"
    return _clip_words(f"Implement {phrase[0].lower() + phrase[1:]}")


def _looks_meta_heading(title: str) -> bool:
    cleaned = _clean_chapter(title)
    if _META_CHAPTER.match(cleaned):
        return True
    if is_conceptual_heading(cleaned):
        return True
    # Playlist-style "Tutorial #1 - Introduction" with no implementable payload.
    if re.search(r"\b(introduction|welcome|outro|conclusion|recap|subscribe)\b", cleaned, re.I):
        if not _STRONG_CONCEPT.search(cleaned):
            return True
    return False


def _is_instructional_heading(title: str) -> bool:
    if _looks_meta_heading(title):
        return False
    if _SYLLABUS_CHAPTER.search(title or ""):
        return True
    if not _INSTRUCTIONAL_HEADING.search(title):
        return False
    # Action verbs like "write" / "build" are not enough — the heading must name
    # something a learner can actually implement.
    return is_implementable_step(title) or bool(_match_concept_tokens(title))


def _collect_chapters(doc: SourceDocument) -> list[str]:
    chapters: list[str] = []
    seen: set[str] = set()
    for seg in getattr(doc, "segments", []) or []:
        for ch in getattr(seg, "chapters", []) or []:
            cleaned = _clean_chapter(ch)
            key = cleaned.lower()
            if cleaned and key not in seen:
                seen.add(key)
                chapters.append(cleaned)
    return chapters


def _collect_outline(doc: SourceDocument) -> list[str]:
    """Ordered skill headings: video chapters, else playlist video titles."""
    chapters = _collect_chapters(doc)
    instructional = [c for c in chapters if _is_instructional_heading(c)]
    if len(instructional) >= 2:
        return chapters
    if getattr(doc, "source_type", "") == "youtube_playlist" and len(getattr(doc, "segments", []) or []) >= 3:
        titles: list[str] = []
        seen: set[str] = set()
        for seg in doc.segments:
            raw = (seg.title or "").strip()
            if not raw or raw.lower() in {"- youtube", "youtube"}:
                continue
            cleaned = _clean_chapter(raw)
            key = cleaned.lower()
            if cleaned and key not in seen:
                seen.add(key)
                titles.append(cleaned)
        if len(titles) >= 3:
            return titles
    return chapters


def _match_concept_tokens(title: str) -> str | None:
    """Longest phrase wins so 'parameters of the neural net' is not just 'neural net'."""
    low = title.lower()
    for needle, token in sorted(CONCEPT_TOKENS, key=lambda item: len(item[0]), reverse=True):
        if needle in low:
            return token
    for needle, token in sorted(_CONCEPT_WORDS, key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(needle)}\b", low):
            return token
    return None


def _tokens_from_heading(title: str) -> str | None:
    """Fallback concept tokens from distinctive words in an instructional heading."""
    known = _match_concept_tokens(title)
    if known:
        return known
    words: list[str] = []
    seen: set[str] = set()
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", title):
        low = word.lower()
        if low in _STOPWORDS or low in _ACTION_VERBS or low in _JUNK_HEAD_WORDS:
            continue
        if low in _CLOSED_CLASS:
            continue
        if low in seen:
            continue
        seen.add(low)
        words.append(word)
    if not words:
        return None
    # Prefer the most specific (longest) content words, keep source order among them.
    ranked = sorted(words, key=len, reverse=True)[:3]
    ordered = [w for w in words if w in ranked]
    return "|".join(ordered)


def _concept_stem(label: str) -> set[str]:
    s = re.sub(r"[^a-z0-9]+", " ", label.lower())
    alias = {"net": "network", "nets": "network", "networks": "network", "nn": "network"}
    drop = {
        "build", "implement", "implementing", "create", "write", "train", "training",
        "the", "a", "an", "how", "to", "engine", "library", "object", "in", "this",
        "video", "follow", "lecture", "with", "these", "those", "that", "some",
        "based", "using", "make", "makes", "add", "does", "have", "let", "lets",
        "directly", "simple", "first", "own", "get", "got", "will", "can",
    }
    out: set[str] = set()
    for tok in s.split():
        tok = alias.get(tok, tok)
        # Fold plurals: "Train Transformers" and "Train the Transformer" are one
        # step, and a caption switches between the two mid-sentence.
        if len(tok) > 4 and tok.endswith("s") and not tok.endswith("ss"):
            tok = tok[:-1]
        if tok in drop or len(tok) < 3:
            continue
        out.add(tok)
    return out


def _stems_overlap(a: set[str], b: set[str]) -> bool:
    if not a or not b:
        return False
    return a <= b or b <= a or (len(a & b) / min(len(a), len(b)) >= 0.6)


def _concepts_from_prose(text: str, title: str) -> list[str]:
    """Extract ordered implementable topics from title + description (no URL allowlist).

    Mere mentions of techniques (neural net, backpropagation, gradient descent)
    are not enough — the source must show build/implement intent. Otherwise a
    conceptual lecture is turned into a fake coding project.
    """
    blob = f"{title}\n{text}"
    if not re.search(
        r"\blet'?s (?:build|implement|write|code|create|reproduce)\b|"
        r"\bwe (?:will |are going to |gonna )?(?:build|implement|reproduce)\b|"
        r"\bhow to (?:build|implement)\b|"
        r"\bimplementing\b|"
        r"\bfrom scratch\b|"
        r"\bfollow(?:ing)? along\b|"
        r"github\.com|"
        r"\bdefine (?:a |the )?(?:class|function|method)\b|"
        r"\breproduce\b",
        blob,
        re.I,
    ):
        return []

    found: list[str] = []
    stems: list[set[str]] = []

    def _add(label: str) -> None:
        cleaned = label.strip()
        if not cleaned or _looks_meta_heading(cleaned) or is_conceptual_heading(cleaned):
            return
        if not is_implementable_step(cleaned):
            return
        stem = _concept_stem(cleaned)
        if not stem:
            return
        if any(_stems_overlap(stem, prev) for prev in stems):
            return
        stems.append(stem)
        found.append(cleaned)

    phrase_labels = [
        (r"micrograd", "Build the micrograd engine"),
        (r"backpropagat", "Implement backpropagation"),
        (r"neural nets?", "Build a neural net"),
        (r"linear regression.*(?:data|load|analy)", "Load and analyze data for linear regression"),
        (r"linear regression", "Implement linear regression"),
        (r"k-?nearest|knn\b", "Implement k-nearest neighbors"),
        (r"support vector|\bsvm\b", "Implement a support vector machine"),
        (r"k-?means", "Implement k-means clustering"),
        (r"value object", "Build the Value object"),
        (r"gradient descent", "Train with gradient descent"),
        (r"from scratch", None),
    ]
    for pattern, label in phrase_labels:
        if label and re.search(pattern, blob, re.I):
            _add(label)

    for match in re.finditer(
        r"\b(?:build|implement(?:ing)?|create|write|train(?:ing)?)\s+"
        r"(?:a |an |the |how to )?"
        r"([A-Za-z][A-Za-z0-9 _-]{2,48})",
        blob,
        re.I,
    ):
        snippet = match.group(0)
        snippet = re.split(r"[,.]| and ", snippet)[0].strip()
        if len(snippet) >= 8:
            _add(snippet)

    return found[:12]


def _assert_source_acceptable(doc: SourceDocument, text: str, outline: list[str], title: str) -> None:
    """Stage 2 quality gate: reject/insufficient before curriculum planning."""
    del text, outline  # gathered again inside evaluate_source from the document
    require_accept(evaluate_source(doc, title))


def _check_description(title: str, token: str) -> str:
    pretty = token.split("|")[0]
    desc = f"Your code implements **{title}** (references `{pretty}`)."
    return desc if len(desc) <= 280 else desc[:277] + "…"


def _chapter_check(title: str) -> VerificationCheck | None:
    if len(title) > 160:
        title = title[:157] + "…"
    low = title.lower()
    if re.search(r"\b(what is|intro to|introduction|history|why |overview)\b", low):
        return None
    syllabus = bool(_SYLLABUS_CHAPTER.search(title))
    if (
        not is_implementable_step(title)
        and not _match_concept_tokens(title)
        and not syllabus
    ):
        return None
    # 1) A concrete import/symbol/call if the chapter names one.
    direct = _extract_target(title)
    if direct and direct[0] in ("import", "symbol", "function_call"):
        return _check_for(direct[0], direct[1])
    # 2) Curated concept → token map for implementation or instructional chapters.
    token = _match_concept_tokens(title)
    if token and (_IMPLEMENTATION_HINT.search(title) or _is_instructional_heading(title)):
        return VerificationCheck(
            kind="code_contains",
            target=token,
            description=_check_description(title, token),
        )
    # 3) Distinctive code identifiers — inner CamelCase or dotted (nn.Module),
    #    not Title-Case English.
    for rx in (_DOTTED, _CAMEL, _DIGITAL_ACRONYM):
        m = rx.search(title)
        if m:
            tok = m.group(1)
            if tok.lower() not in _STOPWORDS and tok.lower() not in _JUNK_HEAD_WORDS:
                return VerificationCheck(
                    kind="code_contains",
                    target=tok,
                    description=_check_description(title, tok),
                )
    # 4) Instructional heading with extractable content words (Karpathy-style
    #    "derivative of a simple function") — still source-grounded, not GPT-2-only.
    if _is_instructional_heading(title) or syllabus:
        generic = _match_concept_tokens(title) or _tokens_from_heading(title)
        if generic:
            return VerificationCheck(
                kind="code_contains",
                target=generic,
                description=_check_description(title, generic),
            )
    return None


_MICRO_OBSERVATIONS = [
    "Next up from the tutorial:",
    "Here's the next piece to build:",
    "Keep the momentum — next section:",
    "Now for the next milestone:",
    "Time to build:",
]

_CELEBRATIONS = [
    "Nailed it! 🎯",
    "Milestone cleared — keep rolling! 🔥",
    "That's another piece of the project done! ✅",
    "Boom. On to the next one! 🚀",
    "Great work — your project just grew! 🌱",
    "Verified and shipped! ⚡",
]


def _count_sentence_targets(text: str) -> int:
    n = 0
    seen: set[tuple[str, str]] = set()
    for sentence in _split_steps(text):
        for window in _windows_for_extraction(sentence):
            if not _is_step(window):
                continue
            target = _extract_target(window, text)
            if target is None:
                continue
            kind, tgt = target
            key = (kind, tgt)
            if kind in ("import", "symbol", "function_call"):
                if key in seen:
                    continue
                seen.add(key)
            n += 1
    return n


def _has_coding_tutorial_signal(text: str) -> bool:
    """True when the source shows real implementation, not just spoken explanation."""
    if not text or len(text.strip()) < 40:
        return False
    return len(_CODE_SIGNAL.findall(text)) >= 2


def _implementation_chapter_count(chapters: list[str]) -> int:
    return sum(1 for ch in chapters if _IMPLEMENTATION_HINT.search(ch))


def _reject_if_not_buildable(text: str, chapters: list[str]) -> None:
    if _implementation_chapter_count(chapters) >= 3:
        return
    if _has_coding_tutorial_signal(text):
        return
    raise ProjectGroundingError(_NOT_ENOUGH_MATERIAL)


def plan_project(doc: SourceDocument, title: str, course_id: str) -> ProjectCourse:
    """Build a source-grounded ProjectCourse from an ingested source document.

    Acceptance is based on instructional usefulness (teach → example → apply),
    not on a polished "course product" brand or a GPT-2-specific chapter map.
    Conversations/podcasts and empty sources fail with a clear reason instead of
    emitting a generic curriculum. Conceptual lecture chapters never become a
    fake coding course.
    """
    text = _gather_source_text(doc)
    outline = _collect_outline(doc)
    chapters = _collect_chapters(doc)
    _assert_source_acceptable(doc, text, outline, title)

    instructional_outline = [h for h in outline if _is_instructional_heading(h) or _chapter_check(h)]
    syllabus_outline = [h for h in (outline or chapters) if _SYLLABUS_CHAPTER.search(h or "")]
    if len(instructional_outline) >= 2 or len(syllabus_outline) >= 5:
        try:
            return _plan_from_chapters(doc, outline or chapters, title, course_id)
        except ProjectGroundingError:
            pass

    if _implementation_chapter_count(chapters) >= 3:
        return _plan_from_chapters(doc, chapters, title, course_id)

    # Prefer explicit coding steps in a transcript over coarse description phrases
    # ("build a word frequency counter") so we don't skip import/def milestones —
    # but a lecture that narrates its code in prose has more real steps in the
    # concepts than in the extractable sentences, and takes the outline path.
    prose_concepts = _concepts_from_prose(text, title or doc.title)
    if len(prose_concepts) >= 2 and _count_sentence_targets(text) <= max(1, len(prose_concepts) // 2):
        try:
            return _plan_from_chapters(doc, prose_concepts, title, course_id)
        except ProjectGroundingError:
            pass

    if not text or len(text.strip()) < 40:
        raise ProjectGroundingError(_NOT_ENOUGH_MATERIAL)

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
            source_grounded_description=_clip(
                f"Create the entry file for this project so you can start building "
                f"the thing the source builds: {title}.",
                2000,
            ),
            source_quote=_clip(title, 2000),
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
        for window in _windows_for_extraction(sentence):
            if len(milestones) >= 14:
                break
            if not _is_step(window):
                continue
            if is_dangling_or_document_task(window):
                continue
            target = _extract_target(window, text)
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
            clean_window = re.sub(r"^\s*(?:step\s*)?\d+[.):]\s*", "", window).strip()
            quote = short_source_excerpt(clean_window, needle=tgt)

            milestones.append(
                Milestone(
                    id=f"m{order}",
                    order=order,
                    title=_short_title(window, (kind, tgt)),
                    source_grounded_description="",  # filled by learner-facing polish
                    source_quote=quote,
                    microstep=Microstep(
                        observation="Next step from the source:",
                        action="",
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
            "Not enough material to ground a course: this source doesn't describe enough "
            "concrete implementation steps. Provide a hands-on coding tutorial (with steps "
            "like importing packages, defining functions, and running code) so Patchwork can "
            "turn it into a project you build."
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

    goal = _synthesize_project_goal(title, tech_stack)
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
    return _finalize_planned_project(project)


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
            source_grounded_description=_clip(
                f"Create the entry file and start building the project from the tutorial: {project_title}.",
                2000,
            ),
            source_quote=_clip(project_title, 2000),
            microstep=Microstep(
                observation="Your project workspace is ready.",
                action="Create `main.py` and add a comment with the project goal.",
                hint="Everything you write here persists across the whole course.",
            ),
            why="One persistent workspace — you grow this project across every chapter of the tutorial.",
            checks=[VerificationCheck(kind="file_exists", target="main.py", description="`main.py` exists in your workspace.")],
            xp_reward=10,
        )
    )
    order += 1

    kept = 0
    seen_titles: set[str] = set()
    for idx, ch in enumerate(chapters):
        if len(milestones) >= 16:
            break
        if _looks_meta_heading(ch):
            continue
        check = _chapter_check(ch)
        if check is None:
            continue
        # Dedupe on what the learner reads, not on the token the check looks for.
        # Keying on the check collapsed a whole series together, because "Creating
        # a Model" and "Text Classification – Model Architecture" both check for
        # `Model` while teaching two different things.
        label = _chapter_title(ch)
        if not label or label.lower() in seen_titles:
            continue
        seen_titles.add(label.lower())
        ch_title = _clip_words(label)
        obs = _MICRO_OBSERVATIONS[idx % len(_MICRO_OBSERVATIONS)]
        milestones.append(
            Milestone(
                id=f"m{order}",
                order=order,
                title=_clip(ch_title, 60),
                source_grounded_description=_clip(
                    f"{ch_title} — the source covers this as “{ch}”.",
                    2000,
                ),
                source_quote=_clip(ch, 2000),
                microstep=Microstep(
                    observation=_clip(
                        _observation_for(check.kind, check.target, ch_title) or obs,
                        400,
                    ),
                    action=_clip(
                        _action_for(check.kind, check.target, ch_title, source_label=ch),
                        400,
                    ),
                    hint=_clip(_chapter_hint(check), 400),
                ),
                teach=_clip(
                    beginner_teach(
                        check.kind, check.target, title=ch_title, source_label=ch,
                    ),
                    1200,
                ),
                why=_clip(
                    "Building this chapter adds the next working piece of the project.",
                    2000,
                ),
                celebrate=_CELEBRATIONS[idx % len(_CELEBRATIONS)],
                checks=[check],
                xp_reward=25,
            )
        )
        order += 1
        kept += 1

    # Vagueness gate: a video with no implementable chapters is rejected clearly
    # rather than turned into a hollow course.
    if kept < 2:
        raise ProjectGroundingError(
            "Not enough material to ground a course: this source doesn't break down into enough "
            "concrete, buildable steps (sections are too high-level, conversational, or missing). "
            "Try a hands-on coding tutorial with clear sections, or paste its transcript."
        )

    milestones.append(
        Milestone(
            id=f"m{order}",
            order=order,
            title="Run and verify the project",
            source_grounded_description="Run your complete project and confirm it works end-to-end.",
            source_quote="",
            microstep=Microstep(
                observation="You've built the tutorial's sections.",
                action="Run your project and make sure it executes without errors.",
                hint="Use Run, then click NEXT to verify.",
            ),
            why="The final milestone verifies the whole project runs — the source's intended outcome.",
            checks=[VerificationCheck(kind="run_ok", target="", description="Your project runs without errors.")],
            xp_reward=40,
        )
    )

    now = time.time()
    # Name what this course actually builds. A four-series mega course plans one
    # series into a single file, and a goal that recites the whole title promises
    # the learner three things they will never be asked to write.
    steps = [
        m.title for m in milestones
        if m.checks and m.checks[0].kind not in {"file_exists", "run_ok"}
    ]
    if steps:
        named = [s[:1].lower() + s[1:] for s in steps[:3]]
        listed = named[0] if len(named) == 1 else " and ".join([", ".join(named[:-1]), named[-1]])
        goal = _clip_words(
            f"Work through “{_clip_words(project_title, 70)}”: {listed}, one milestone at a time.",
            240,
        )
    else:
        goal = _synthesize_project_goal(project_title, tech_stack)
    project = ProjectCourse(
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
                    f"# Built from the tutorial, chapter by chapter. Click NEXT after each milestone.\n"
                    f"# Tip: follow the Do this card — start with imports, then build each section.\n\n"
                ),
            )
        ],
        created_at=now,
        updated_at=now,
    )
    return _finalize_planned_project(project)


def _dedupe_milestones(milestones: list) -> list:
    """Drop a milestone that repeats an earlier one.

    Two steps built from the same source quote and the same verification check
    are one step said twice. Left in, they produce duplicate titles such as
    "Print output" appearing twice, which `is_hollow_guided_project` reads as a
    hollow course — so a perfectly good project becomes permanently unopenable
    after it has already been saved.

    Exact signatures are not enough for transcripts: a narrator says "train the
    Transformer", "train these Transformers", "train Transformers but..." and the
    extractor turns one step into five, each checking a slightly different token.
    A concept stem comparison collapses them; the setup and run milestones are
    structural and never compared.
    """
    seen = set()
    kept = []
    stems: list[tuple[set[str], str]] = []
    for milestone in milestones:
        check = milestone.checks[0] if milestone.checks else None
        if check is None or check.kind in {"file_exists", "run_ok"}:
            kept.append(milestone)
            continue
        signature = (
            milestone.title.strip().lower(),
            check.kind,
            (check.target or "").strip().lower(),
            (milestone.source_quote or "").strip().lower()[:120],
        )
        if signature in seen:
            continue
        stem = _concept_stem(milestone.title)
        # Only steps graded the same way can be the same step said twice: defining
        # `count_words` and calling it share a concept and are two real milestones.
        if stem and any(
            k == check.kind and _stems_overlap(stem, prev) for prev, k in stems
        ):
            continue
        seen.add(signature)
        if stem:
            stems.append((stem, check.kind))
        kept.append(milestone)
    for index, milestone in enumerate(kept, start=1):
        milestone.order = index
    return kept


def _local_module_names(project: ProjectCourse) -> set[str]:
    """Module names that exist as importable files inside this project."""
    names = set()
    for file in project.workspace_files:
        stem = (file.path or "").split("/")[-1].rsplit(".", 1)[0].strip().lower()
        if stem:
            names.add(stem)
    return names


def _drops_unimportable_local_modules(milestones: list, project: ProjectCourse) -> list:
    """Remove milestones that only ask for a local module this project lacks.

    A tutorial that says "create ratelimit.py" then "from ratelimit import ..."
    is two files. The generated project is one file (`main.py`), so an
    `import ratelimit` check can never pass, and the learner stalls on it with no
    way forward. Third-party names (requests, tiktoken) are untouched — they are
    installed, not authored, so they remain legitimate checks.
    """
    available = _local_module_names(project)
    authored = {
        m.group(1).lower()
        for m in re.finditer(
            r"(?:([A-Za-z_][A-Za-z0-9_]*)\.(?:py|jsx?|tsx?|css))|(?:from\s+['\"]\./([A-Za-z_][A-Za-z0-9_-]*)['\"])",
            project.source_excerpt or "",
        )
        for name in m.groups()
        if name
    }
    kept = []
    for milestone in milestones:
        blocking = [
            c for c in (milestone.checks or [])
            if c.kind == "import"
            and (c.target or "").split(".")[0].lower() in authored
            and (c.target or "").split(".")[0].lower() not in available
        ]
        if blocking and len(milestone.checks or []) == len(blocking):
            continue  # the whole step is unreachable in a single-file project
        milestone.checks = [c for c in (milestone.checks or []) if c not in blocking]
        kept.append(milestone)
    for index, milestone in enumerate(kept, start=1):
        milestone.order = index
    return kept


def _finalize_planned_project(project: ProjectCourse) -> ProjectCourse:
    """Stage 3 — drop malformed and repeated milestones; reject if too little remains."""
    project.milestones = filter_invalid_milestones(project.milestones)
    project.milestones = _drops_unimportable_local_modules(_dedupe_milestones(project.milestones), project)
    require_accept(evaluate_milestones(project.milestones, project.project_goal, stage="planning"))
    polish_project_copy(project)
    return project


def _chapter_hint(check: VerificationCheck) -> str:
    if check.kind == "import":
        return f"Add `import {check.target}` at the top of your entry file (or `from {check.target} import ...`)."
    if check.kind == "symbol":
        return f"Define `{check.target}` in your code."
    if check.kind == "function_call":
        return f"Call `{check.target}(...)` in your code."
    if check.kind == "code_contains":
        first = check.target.split("|")[0]
        return (
            f"Implement this section in `main.py`. "
            f"When you're done, `{first}` should appear in your code."
        )
    return "Implement this section, then click NEXT."


def validate_project(project: ProjectCourse) -> None:
    """Reject courses with transcript leaks, duplicate titles, or hollow milestones."""
    coding = [
        m for m in project.milestones
        if m.checks and m.checks[0].kind in ("import", "symbol", "function_call", "code_contains")
    ]
    if len(coding) < 2:
        raise ProjectGroundingError(
            "This source reads like a lecture or explanation, not a hands-on coding tutorial. "
            "Patchwork can only build a guided project from a source that shows real implementation "
            "steps (imports, functions, classes). Try a build-along coding video or paste a tutorial "
            "with concrete steps."
        )

    titles = [m.title.strip().lower() for m in coding]
    dup_titles = {t for t in titles if titles.count(t) > 1}
    if dup_titles:
        raise ProjectGroundingError(
            f"Generated milestones contain duplicate titles ({', '.join(sorted(dup_titles)[:3])}). "
            "Provide a clearer source with distinct implementation steps."
        )

    for m in project.milestones:
        # Instruction field: instruction detector (handles numbered steps / code).
        # Prose fields: prose detector — a sentence with a list is not a caption dump
        # (the instruction heuristic rejected whole AI-reviewed courses for it).
        if looks_like_raw_transcript(m.microstep.action) or any(
            _looks_like_raw_prose(f) for f in (m.microstep.observation, m.hook, m.teach)
        ):
            raise ProjectGroundingError(
                "Generated lesson content still contains raw transcript speech. "
                "Try a cleaner transcript or a video with chapter markers."
            )
        # Actions may carry short code steps (Microstep.action allows 1200). Cap
        # instead of rejecting a whole valid tutorial for a few extra characters.
        if m.microstep.action and len(m.microstep.action) > 1000:
            m.microstep.action = _cap_field(m.microstep.action, 1000)

    run_ok_titles = [m.title.strip().lower() for m in project.milestones if "run and verify" in m.title.strip().lower()]
    if len(run_ok_titles) > 1:
        raise ProjectGroundingError(_NOT_ENOUGH_MATERIAL)

    if _looks_like_raw_prose(project.project_goal):
        raise ProjectGroundingError(
            "Could not produce a clean project overview from this source."
        )


def is_hollow_guided_project(project: ProjectCourse) -> bool:
    """True when a saved course has too little real implementation structure."""
    titles = [m.title.strip().lower() for m in project.milestones]
    if any(titles.count(t) >= 2 for t in titles if t in {"run and verify", "print output", "print the result"}):
        return True
    run_ok = sum(1 for m in project.milestones if m.checks and m.checks[0].kind == "run_ok")
    if run_ok >= 3:
        return True
    coding = [
        m for m in project.milestones
        if m.checks and m.checks[0].kind in ("import", "symbol", "function_call", "code_contains")
    ]
    return len(coding) < 2


def _hint_for(kind: str, target: str) -> str:
    if kind == "import":
        pkg = code_ident_for_import(target)
        return f"Add `import {pkg}` at the top of your entry file (or `from {pkg} import ...`)."
    if kind == "symbol":
        return f"Make sure something named `{target}` is defined at the top level."
    if kind == "function_call":
        return f"Call `{target}(...)` somewhere in your code."
    if kind == "stdout_contains":
        return "Use `print(...)` to show a result."
    return "Make sure the file runs top-to-bottom without raising an error."
