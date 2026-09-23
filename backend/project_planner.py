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

from .project_copy import (
    code_ident_for_import,
    display_ident,
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
from . import repo_planner
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

#: Verbs that promise a definition rather than a mention.
_DEFINE_VERB = (
    r"implement|define|write|create|build|add|declare|code|develop|start(?:ing)?"
)
#: A construction verb followed closely by a backticked code span is the source
#: telling you the name of the thing to build: "Implement `mse(y_true, y_pred)`
#: returning…", "Implement `TokenStore` with set/get/clear methods". A call form or a
#: PascalCase/snake_case name is unambiguously Python; a bare lowercase word is not
#: ("Create `venv`", "add a `prompt`"), so it is not accepted here. The verb is
#: matched case-insensitively by a scoped flag on purpose: a global IGNORECASE would
#: make the PascalCase branch match any word at all.
_SPANNED_DEFINITION = re.compile(
    rf"\b(?i:{_DEFINE_VERB})\b[^.!?\n]{{0,30}}?"
    rf"`({_IDENT}\s*\(|[A-Z][A-Za-z0-9_]*[A-Z][A-Za-z0-9_]*|[a-z][a-z0-9]*_[a-z0-9_]*)[^`]*`"
)
#: Any code span at all, used to suppress the loose prose pattern below.
_ANY_CODE_SPAN = re.compile(r"`[^`]+`")

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


#: A `def` with its signature, and the test framework's own assertion calls.
_DEF_SIGNATURE = re.compile(r"\bdef\s+([A-Za-z_]\w*)\s*\(([^)]*)\)")
_UNITTEST_ASSERTION = re.compile(r"\bself\s*\.\s*(?:assert\w*|fail)\s*\(")
#: A construction verb and the words that follow it inside the same clause.
_DEMANDED_WINDOW = re.compile(
    r"\b(?:implement|define|write|create|build|add|declare|code|develop)\b([^.?\n]{0,40})",
    re.IGNORECASE,
)
#: Words naming a kind of thing, which is never the thing itself.
_DEMANDED_FILLER = {
    "function", "functions", "method", "methods", "class", "classes", "variable",
    "variables", "module", "modules", "object", "objects", "helper", "helpers",
    "name", "names", "following", "simple", "small", "own", "same", "other",
    "that", "this", "with", "which", "using", "used", "returns", "return",
    "called", "named", "your", "their", "what", "when", "then", "into", "them",
    "raise", "raises", "check", "checks", "test", "tests", "coding", "where",
}


def _demanded_names(text: str) -> set[str]:
    """Names an instruction in this document asks the learner to produce.

    Deliberately broad, because it only ever *protects* a candidate from being
    classified as harness: too wide costs a missed filter, too narrow destroys real
    content. Taking the first word after the verb was wrong — "define a test_login
    function" asks for `test_login`, not `a`.
    """
    out: set[str] = set()
    for window in _DEMANDED_WINDOW.findall(text or ""):
        for word in re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", window):
            if word.lower() not in _DEMANDED_FILLER:
                out.add(word)
    return out


def scaffolding_names(text: str) -> set[str]:
    """Names the document presents as test infrastructure rather than as a deliverable.

    A guided project must not ask the learner to build the harness that checks it, and
    a tutorial's `def test_x(self): self.assertEqual(...)` is that harness. The test is
    structural, not nominal: the definition takes nothing but its bound instance, and
    the code following it calls the test framework's assertions.

    Three things keep it honest, each one a real shape in this repository's material:

    * a name any instruction asks for is never classified — "Implement `assert_equal`
      that raises AssertionError" is the deliverable of the app's own testing unit, and
      a tutorial that says "write a test_login function" means it;
    * a name defined anywhere with real parameters is a deliverable, so a class method
      (`def deposit(self, amount)`) and a test of the same shape cannot be confused;
    * pytest-style module functions (`def test_login():`, no `self`) are *not* caught
      here, because nothing distinguishes them from a learner's own function except the
      name — which is the blacklist this function exists to avoid.
    """
    if not text:
        return set()
    demanded = _demanded_names(text)
    has_real_signature = {
        name for name, params in _DEF_SIGNATURE.findall(text)
        if _bound_instance_only(params) is False
    }
    scaffolding: set[str] = set()
    for match in _DEF_SIGNATURE.finditer(text):
        name, params = match.group(1), match.group(2)
        if name in demanded or name in has_real_signature:
            continue
        if _bound_instance_only(params) is not True:
            continue
        following = text[match.end(): match.end() + 400]
        if _UNITTEST_ASSERTION.search(following):
            scaffolding.add(name)
    return scaffolding - has_real_signature


def _bound_instance_only(params: str) -> bool | None:
    """True for `(self)`/`(cls)` (optionally + *args/**kwargs), False for real
    parameters, None when the signature is not decidable (e.g. a class)."""
    args = [a.strip() for a in (params or "").split(",") if a.strip()]
    if not args:
        return None
    first = args[0].split(":")[0].strip()
    if first not in {"self", "cls"}:
        return False
    rest = [a for a in args[1:] if not a.startswith(("*", "**"))]
    return not rest


def _cap_field(text: str, max_len: int = _FIELD_MAX) -> str:
    """Clamp milestone text fields to the Pydantic model limit."""
    cleaned = (text or "").strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1] + "…"


def looks_like_raw_transcript(text: str) -> bool:
    """True when text looks like unprocessed speech-to-text, not learner copy."""
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if _TRANSCRIPT_FILLER.search(cleaned) or _SPOKEN_FILLER_CHUNKS.search(cleaned):
        return True
    words = cleaned.split()
    # Learner-facing lines must stay short. Spoken monologue is long and breathless.
    if len(words) > 28:
        return True
    if len(cleaned) > 160 and cleaned.count(",") >= 3:
        return True
    if len(cleaned) > 90 and cleaned.count(".") == 0 and cleaned.count("`") == 0:
        return True
    # Repeated short phrases ("we want we want") are common STT artifacts.
    if re.search(r"\b(\w+(?:\s+\w+){0,3})\s+\1\b", cleaned, re.IGNORECASE):
        return True
    return False


def _kind_target_from_milestone(milestone: Milestone) -> tuple[str, str]:
    if not milestone.checks:
        return ("run_ok", "")
    c = milestone.checks[0]
    return (c.kind, c.target)


def scrub_learner_fields(milestone: Milestone) -> Milestone:
    """Replace transcript-like learner copy with a short synthesized instruction.

    Used both at generation time and when projecting a saved project, so already
    stored courses cannot keep dumping YouTube speech into the lesson pane.
    """
    kind, tgt = _kind_target_from_milestone(milestone)
    path = milestone.checks[0].path if milestone.checks else ""
    safe_action = _action_for(kind, tgt, milestone.title, path)
    safe_obs = _observation_for(kind, tgt, milestone.title, path)
    if looks_like_raw_transcript(milestone.microstep.action) or len(milestone.microstep.action.split()) > 28:
        milestone.microstep.action = safe_action
    if looks_like_raw_transcript(milestone.microstep.observation) or len(milestone.microstep.observation.split()) > 28:
        milestone.microstep.observation = safe_obs
    if looks_like_raw_transcript(milestone.hook) or len(milestone.hook.split()) > 12:
        milestone.hook = ""
    if looks_like_raw_transcript(milestone.teach) or len(milestone.teach.split()) > 60:
        milestone.teach = ""
    if looks_like_raw_transcript(milestone.example):
        milestone.example = ""
    return milestone


def scrub_project_learner_copy(project: ProjectCourse) -> ProjectCourse:
    for m in project.milestones:
        scrub_learner_fields(m)
    if looks_like_raw_transcript(project.course_intro) or len(project.course_intro.split()) > 80:
        project.course_intro = ""
    if looks_like_raw_transcript(project.project_goal):
        project.project_goal = _synthesize_project_goal(project.title, project.tech_stack)
    return project


def _synthesize_project_goal(title: str, tech_stack: list[str]) -> str:
    """Learner-facing project goal — never the first raw transcript sentence."""
    name = title.strip() or "this project"
    stack = ", ".join(tech_stack[:4])
    if stack:
        return f"Build “{name}” step by step, using {stack} as in the source tutorial."
    return f"Build “{name}” step by step, following the source tutorial."


def _action_for(kind: str, target: str, title: str = "", path: str = "") -> str:
    """Concise, imperative learner task — never raw source dialogue."""
    if kind == "import":
        return f"Add `import {target}` (or `from {target} import ...`) to your code."
    if kind == "symbol":
        return f"Define `{target}` in your workspace."
    if kind == "symbol_in_file":
        return f"Define `{target}` in `{path}`." if path else f"Define `{target}`."
    if kind == "function_call":
        return f"Call `{target}(...)` in your code."
    if kind == "stdout_contains":
        return "Add a `print(...)` statement that shows your result."
    if kind == "run_ok":
        return "Run your code and confirm it executes without errors."
    if kind == "code_contains":
        token = target.split("|")[0]
        return f"Implement this step so your code references `{token}`."
    return title or "Complete this step in your code."


def _observation_for(kind: str, target: str, title: str, path: str = "") -> str:
    """One short sentence — what this milestone is about."""
    if kind == "import":
        return f"This step brings in `{target}` from the tutorial."
    if kind == "symbol":
        return f"Here you define `{target}` — a core piece of the project."
    if kind == "symbol_in_file":
        return (f"`{path}` is where `{target}` belongs." if path
                else f"Here you define `{target}`.")
    if kind == "function_call":
        return f"Wire up `{target}` so the project actually runs this logic."
    if kind == "stdout_contains":
        return "Time to see output — printing confirms your code works."
    if kind == "run_ok":
        return "Run the project to verify everything works together."
    if kind == "code_contains":
        return f"Build the “{title}” section from the source."
    return f"Next milestone: {title}."


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
    return low in _ACTION_VERBS or low in _STOPWORDS


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


def _extract_target(sentence: str) -> tuple[str, str] | None:
    """Derive a verification (kind, target) from a step sentence.

    Identifier case is preserved for symbols (captured from the original
    sentence with case-insensitive keyword matching) so a check for `GPT`
    matches the learner's real class name — not a lowercased `gpt`.

    Import names are canonicalized (Transformers → transformers) so instructions
    and AST checks match the real package.

    Returns None when the sentence has no concrete, verifiable coding action.
    """
    IC = re.IGNORECASE
    s = sentence.lower()

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
        if not _reject(canonical) and not _is_generic_import_name(canonical):
            return ("import", canonical)
        return None

    m = re.search(rf"\bfrom\s+({_IDENT})\s+import\b", sentence, IC)
    if m:
        canonical = _canonical_import_name(m.group(1))
        if not _reject(canonical) and not _is_generic_import_name(canonical):
            return ("import", canonical)
        return None

    # A code-formatted name after a construction verb is the artifact the source
    # names directly: "Implement `mse(y_true, y_pred)` returning the mean of the
    # squared residuals". Checked *before* the prose pattern below.
    spanned = _SPANNED_DEFINITION.search(sentence)
    if spanned:
        name = spanned.group(1).split("(")[0].strip()
        if name and not _reject(name):
            return ("symbol", name)

    # "the forward method", "the train function" — name precedes the keyword.
    # Suppressed once the sentence has already shown its artifact in code form:
    # "Implement `shout` that uppercases the string returned by the wrapped function"
    # names `shout`, and reading "the wrapped function" as a demand to define
    # `wrapped` would invent a step the source never asked for.
    m = re.search(rf"\b(?:the\s+)({_IDENT})\s+(?:method|function)\b", sentence, IC)
    if m and not _reject(m.group(1)) and not _ANY_CODE_SPAN.search(sentence):
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

    # High-precision: an explicitly named *code* symbol — "a class called GPT",
    # "a variable named total", "a dataclass called GPTConfig". Bare "called X"
    # in lecture speech ("we called this attention") is not a coding step.
    m = re.search(
        rf"\b(?:class|function|method|variable|dataclass|object|module)\s+"
        rf"(?:called|named)\s+({_IDENT})",
        sentence,
        IC,
    )
    if m and not _reject(m.group(1)):
        return ("symbol", m.group(1))
    m = re.search(
        rf"\b(?:define|write|create|implement|add)\s+(?:a\s+|an\s+|the\s+)?"
        rf"(?:class|function|method|variable|dataclass)\s+(?:called\s+|named\s+)?({_IDENT})",
        sentence,
        IC,
    )
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

    # call a specific function — not spoken "we call it X" / "we call this Y".
    m = re.search(rf"\bcall\s+(?:the\s+)?(?:function\s+)?({_IDENT})", sentence, IC)
    if m and _is_callable_target(m.group(1), sentence):
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
        return VerificationCheck(kind="run_ok", target="", description="Your project runs.")
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
    r"saving|plotting|sklearn|pytorch|forward|backward|value object)\b",
    re.IGNORECASE,
)
_INSTRUCTIONAL_HEADING = re.compile(
    r"\b(implement|build|code|function|class|train|grad|backprop|deriv|"
    r"example|exercise|dataset|model|layer|network|forward|backward|"
    r"install|import|debug|fix|write|create|neural|tensor|attention|"
    r"token|parser|api|regression|knn|svm|means|perceptron|tanh|"
    r"micrograd|pytorch|numpy|sklearn|tutorial|algorithm|optim|"
    r"value object|neuron|mlp|dataloader|saving|plotting|linear|"
    r"transformer|logits|loss function|expression graph|expression)\b",
    re.IGNORECASE,
)


def _clean_chapter(title: str) -> str:
    t = re.sub(r"^\s*section\s*\d+\s*:\s*", "", title, flags=re.IGNORECASE)
    t = re.sub(r"^\s*(?:let['’]?s|lets)\s+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*,?\s*\d+\s*ms\b", "", t)              # drop timing annotations "333ms"
    t = re.sub(r"\s*\([^)]*\)\s*$", "", t)                 # drop trailing "(...)"
    t = t.strip(" -–—:•\t")
    return t


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
        "video", "follow", "lecture", "with",
    }
    out: set[str] = set()
    for tok in s.split():
        tok = alias.get(tok, tok)
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
    if not is_implementable_step(title) and not _match_concept_tokens(title):
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
    # 3+4) A heading earns a verification check only when it *instructs*.
    #
    #    Shape alone is not evidence. Every identifier this branch used to mint from a
    #    bare topic heading — over all 202 chapters in the corpus plus six real videos —
    #    was a proper noun: `OpenAI`, `ChatGPT`, `LoRA`, `StackOverflow`. None names a
    #    thing the learner defines; each names a vendor, a product or a technique being
    #    discussed, and a `code_contains` check on it asks for a typed word instead of a
    #    program. "Build the LayerNorm module" is different in kind, not in degree: the
    #    verb says the class is the deliverable, so `LayerNorm` is the right target and
    #    stays exact rather than degrading to the heading's word list.
    #
    #    Measured: refusing to mint from a heading that does not instruct is what
    #    separates a two-hour podcast about LLMs (16 chapters, 1 surviving check, below
    #    the route's floor of two, so it now fails with a clear reason) from a real
    #    build-along (32 chapters, all five milestones kept).
    if _is_instructional_heading(title):
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
        generic = _tokens_from_heading(title)
        if generic:
            return VerificationCheck(
                kind="code_contains",
                target=generic,
                description=_check_description(title, generic),
            )
    return None


_MICRO_OBSERVATIONS = [
    "Next up from the video:",
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
    scaffolding = scaffolding_names(text)
    for sentence in _split_steps(text):
        for window in _windows_for_extraction(sentence):
            if not _is_step(window):
                continue
            target = _extract_target(window)
            if target is None:
                continue
            kind, tgt = target
            if tgt in scaffolding:
                continue      # a test of someone else's code is not a step to build
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
    if getattr(doc, "repo", None) is not None:
        # A repository is not a tutorial that failed to be one. `evaluate_source` reads
        # prose for teaching signals — "in this video we build", a step list, an
        # instructional heading — and a finished program has no reason to contain any of
        # them. The repo route asks the equivalent questions about the object it has
        # instead: is it licensed, is it readable, does it have an order, can each step be
        # graded. `plan_repository` enforces those itself, so dispatching here cannot
        # smuggle a source past a gate.
        return plan_repository(doc, title, course_id)

    text = _gather_source_text(doc)
    outline = _collect_outline(doc)
    chapters = _collect_chapters(doc)
    _assert_source_acceptable(doc, text, outline, title)

    instructional_outline = [h for h in outline if _is_instructional_heading(h) or _chapter_check(h)]
    if len(instructional_outline) >= 2:
        try:
            return _plan_from_chapters(doc, outline, title, course_id)
        except ProjectGroundingError:
            pass

    if _implementation_chapter_count(chapters) >= 3:
        return _plan_from_chapters(doc, chapters, title, course_id)

    # Prefer explicit coding steps in a transcript over coarse description phrases
    # ("build a word frequency counter") so we don't skip import/def milestones.
    prose_concepts = _concepts_from_prose(text, title or doc.title)
    if len(prose_concepts) >= 2 and _count_sentence_targets(text) < 2:
        try:
            return _plan_from_chapters(doc, prose_concepts, title, course_id)
        except ProjectGroundingError:
            pass

    if not text or len(text.strip()) < 40:
        raise ProjectGroundingError(_NOT_ENOUGH_MATERIAL)

    language = _detect_language(text)
    tech_stack = _detect_tech(text)

    sentences = _split_steps(text)
    scaffolding = scaffolding_names(text)
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
            target = _extract_target(window)
            if target is None:
                continue
            kind, tgt = target
            if tgt in scaffolding:
                # The document shows this name checking somebody else's work. Making
                # it a milestone asks the learner to build the harness that grades
                # them, and it steals a step from the artifact the tutorial named.
                continue
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
                f"Create the entry file and start building the project from the video: {project_title}.",
                2000,
            ),
            source_quote=_clip(project_title, 2000),
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
    seen_checks: set[tuple[str, str]] = set()
    for idx, ch in enumerate(chapters):
        if len(milestones) >= 16:
            break
        if _looks_meta_heading(ch):
            continue
        check = _chapter_check(ch)
        if check is None:
            continue
        check_key = (check.kind, check.target.lower())
        if check_key in seen_checks:
            continue
        seen_checks.add(check_key)
        ch_title = ch if len(ch) <= 60 else ch[:57] + "…"
        obs = _MICRO_OBSERVATIONS[idx % len(_MICRO_OBSERVATIONS)]
        milestones.append(
            Milestone(
                id=f"m{order}",
                order=order,
                title=_clip(ch, 60),
                source_grounded_description=_clip(
                    f"The video covers this section: “{ch}”. Implement it in your project.",
                    2000,
                ),
                source_quote=_clip(ch, 2000),
                microstep=Microstep(
                    observation=_clip(obs, 400),
                    action=_clip(_action_for(check.kind, check.target, ch_title), 400),
                    hint=_clip(_chapter_hint(check), 400),
                ),
                why=_clip(
                    "This is a real chapter of the video — building it moves your project toward the source's final result.",
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
                    f"# Built from the video, chapter by chapter. Click NEXT after each milestone.\n\n"
                ),
            )
        ],
        created_at=now,
        updated_at=now,
    )
    return _finalize_planned_project(project)


def plan_repository(doc: SourceDocument, title: str, course_id: str) -> ProjectCourse:
    """Build a course that has the learner re-create a repository, module by module.

    A repository has no narration to plan from, so the outline comes from its import
    graph: a file becomes a milestone once every file it imports is already behind it,
    the check is a name that file really defines (read out of its syntax tree), and the
    learner is asked to write the body themselves. Not one line of the project's source
    is stored in the course — `backend/github_fetch.py` explains the licensing reason,
    and the license gate there is what enforces it. Only the *declaration* is quoted
    (`class Value:`), because that is the contract the learner has to satisfy, not the
    lesson.

    Two claims this route used to make that its checks did not back. The first was that a
    step's file merely declares a name: `Value = None` satisfied a milestone about a
    class, and a directory of such lines passed all 86 structural milestones across 13
    real repositories. A step now demands a declaration where it names one, and demands
    the import its own sentence already asserts - 75 wiring checks across the corpus,
    which takes a stub workspace from completing 13 of 13 repositories to 0 of 13 while
    each repository's own source still finishes.

    The second was the closing `run_ok`, offered as the proof that the pieces fit. It is
    the only check that observes the program at all, and it observes only that the entry
    file ran: a wired-up micrograd whose `__add__` subtracts finishes the course at full
    XP, because nothing here decides what a function returns. The evidence a milestone
    produced is now recorded beside its completion (`project_verifier.evidence_of`)
    rather than folded into it, and the sentence a project ends with is derived from
    that. Closing the remaining gap needs the repository's own tests as the answer key,
    which `github_fetch` keeps out of a course for licensing reasons, so it is a
    capability decision and not a rule to write here.
    """
    from .github_fetch import license_problem  # here, not at import time: no httpx in the planner

    snapshot = doc.repo
    problem = license_problem(snapshot.license)
    if problem:
        raise ProjectGroundingError(
            f"Can't build a course from {snapshot.full_name}: {problem}."
        )
    analyzed = repo_planner.analyze([(f.path, f.content) for f in snapshot.files])
    ordered = repo_planner.dependency_order(
        [f for f in analyzed if not f.unparsable and f.public_names]
    )
    chosen = repo_planner.build_chain(ordered, limit=REPO_MILESTONE_MAX)
    if len(chosen) < 2:
        raise ProjectGroundingError(
            f"{snapshot.full_name} has {len(ordered)} modules a learner could build in "
            "order, and no chain among them worth following. This usually means the "
            "repository is a collection of independent scripts, or one very large file."
        )

    entry = repo_planner.entry_point(chosen)
    # The cycle question has to be asked of the whole repository, not of the eight files
    # this course kept: a path back usually runs through a module nothing grades.
    modules = {f.module: f for f in analyzed}
    planned = {f.module for f in chosen}
    project_title = (title or "").strip() or f"{snapshot.full_name}: how it is built"
    milestones: list[Milestone] = []
    claimed: set[str] = set()
    built: set[str] = set()
    order = 1
    for facts in chosen:
        picks = [d for d in facts.ranked_defines() if d[1].lower() not in claimed][:2]
        if not picks:
            continue
        claimed.update(name.lower() for _kind, name, _lines in picks)
        names = [name for _kind, name, _lines in picks]
        already = sorted(m for m in facts.depends if m in built)
        above = repo_planner.consumers_of(chosen, facts.module)
        # A dependency inside a cycle the milestone budget could not fit. Only the
        # partners the graph really runs a cycle through qualify: `reaches` asks the
        # question, because "these import each other" is a claim about the whole graph.
        cyclic = sorted(m for m in facts.depends
                        if repo_planner.reaches(m, facts.module, modules))
        # A dependency no milestone assigns, whether the budget dropped it or it holds
        # nothing gradeable. Disclosed as its own sentence below, not as a branch here.
        unassigned = sorted(m for m in facts.depends if m not in planned)
        # Four different true things about where this file sits in the graph, said in
        # priority order. The third is the cycle case: flask's `app.py` and `ctx.py`
        # import each other, so an order has to be invented inside that pair, and a
        # milestone that claimed "nothing is underneath this file" about a file that
        # imports three others would be teaching something the repository contradicts.
        if above:
            reason = (
                f"{_brief([f'`{p}`' for p in above])} "
                f"{'import' if len(above) > 1 else 'imports'} `{facts.path}`, so this has "
                "to stand on its own before they can be built."
            )
        elif already:
            reason = (
                f"`{facts.path}` needs "
                f"{_brief([f'`{m}`' for m in already])}, which you have already written."
            )
        elif cyclic:
            reason = (
                f"`{facts.path}` is in one import cycle with "
                f"{_brief([f'`{m}`' for m in cyclic])}, so this order is a judgement about "
                "where to start, not a dependency."
            )
        else:
            reason = "Nothing in the project is underneath this file: it is where the build starts."
        # A separate sentence, because it is a separate fact and the branches above are
        # mutually exclusive while this one is not. Measured across 13 real repositories:
        # 126 imports have no milestone behind them, spread over 40 of the 86 file steps,
        # and *every one* of those 40 also had a true thing to say about its place in the
        # graph - so as a fourth branch this disclosed nothing at all, and the learner met
        # the missing file as a ModuleNotFoundError at the run step. `build_chain` explains
        # why the milestone budget cannot close the gaps instead.
        if unassigned:
            reason += (f" It also imports {_brief([f'`{m}`' for m in unassigned], limit=1)},"
                       " which no step here asks you to write; the real project has those "
                       "files, and your run needs something at each path.")
        checks = [
            VerificationCheck(
                kind="symbol_in_file", target=name, path=facts.path,
                description=f"`{name}` is defined in `{facts.path}`.",
            )
            for name in names
        ] + [
            # Each dependency this step's own sentence already claims is behind the
            # learner is also demanded as an import, because that is the only part of
            # "rebuild it module by module" that can be decided without executing it.
            # Measured without these: a directory of `class X: pass` files passed every
            # structural milestone of all 13 repositories, ran cleanly, and paid full
            # XP. Measured with them: the same stubs fail, and each repository's own
            # source still passes, because the real file does import them - relative,
            # dotted, or bare, all three of which the checker accepts by leaf name.
            VerificationCheck(
                kind="import", target=dep, path=facts.path,
                description=f"`{facts.path}` imports `{dep}`, which you built above.",
            )
            for dep in already
        ] + [
            VerificationCheck(kind="file_exists", target=facts.path,
                              description=f"`{facts.path}` exists in your workspace.")
        ]
        milestones.append(Milestone(
            id=f"m{order}",
            order=order,
            title=_clip(f"Build {facts.path}", 160),
            source_grounded_description=_clip(
                f"{snapshot.full_name} puts {_and_list([f'`{n}`' for n in names])} in "
                f"`{facts.path}`.",
                2000,
            ),
            source_quote=_clip(" · ".join(
                [snapshot.full_name, facts.path]
                + [facts.signatures.get(n, "") for n in names]
            ), 2000),
            microstep=Microstep(
                observation=_clip(
                    f"You are writing `{facts.path}`." if not already else
                    f"{_brief([f'`{m}`' for m in already])} already exist, so this file "
                    "can import them.",
                    400,
                ),
                action=_clip(
                    f"Create `{facts.path}` and define "
                    f"{_and_list([f'`{n}`' for n in names])} in it.",
                    400,
                ),
                hint=_clip(
                    f"`{facts.path}` uses "
                    f"{', '.join(f'`{e}`' for e in sorted(facts.external)[:3]) or 'only the standard library'}"
                    " in the real project — you do not have to use the same things, but "
                    "you do have to define the names above.",
                    400,
                ),
            ),
            why=_clip(reason, 2000),
            checks=checks,
            xp_reward=25,
        ))
        order += 1
        built.add(facts.module)

    milestones.append(Milestone(
        id=f"m{order}",
        order=order,
        title=_clip(f"Run {entry.path}", 160),
        source_grounded_description=(
            "In the real project this is the file that ties the others together. Running "
            "it only tests the whole build if your version imports them: a file that "
            "defines names and imports nothing will run, and prove nothing."
        ),
        source_quote=_clip(f"{snapshot.full_name}@{snapshot.ref} · {entry.path}", 2000),
        microstep=Microstep(
            observation=f"{len(chosen)} modules, built in the order the project needs them.",
            action=_clip(
                f"Make `{entry.path}` import the files above and use what they define, "
                "then run it and read what it does.", 400),
            # Kept inside `project_copy.MAX_HINT`, because a longer hint is silently
            # replaced by generic per-kind copy during the polish every project here goes
            # through - and this is the one sentence that tells the learner how to spell an
            # import the runner can actually resolve.
            hint=_clip(
                "This runs as a script, so `from .mod import X` has no package to resolve "
                f"against — name the files above by their path from the root "
                f"(`{chosen[0].module}`).", 400),
        ),
        why="Running the top of the import graph is the step that can show the pieces fit, "
            "but only if this file imports them. The grader runs what you write here: it "
            "cannot tell that you meant to use the files above and did not.",
        checks=[VerificationCheck(kind="run_ok", target="",
                                  description="Your project runs without errors.")],
        xp_reward=40,
    ))

    workspace = [WorkspaceFile(
        path=entry.path,
        content=f"# {entry.path}\n# Rebuilding {snapshot.full_name}. Write this yourself.\n",
    )]
    now = time.time()
    project = ProjectCourse(
        course_id=course_id,
        title=project_title,
        language="python",
        source_type="github_repo",
        source_url=doc.source_url,
        source_hash=doc.source_hash,
        source_summary=_clip(_repo_manifest(snapshot, chosen), 4000),
        source_excerpt=_clip(_repo_manifest(snapshot, chosen), 20_000),
        project_goal=_clip(
            f"Rebuild {snapshot.full_name} module by module, in the order its own imports "
            f"require. Start at {chosen[0].path} and finish by running {entry.path}.",
            2000,
        ),
        tech_stack=_detect_tech(_repo_manifest(snapshot, chosen)),
        entry_file=entry.path,
        milestones=milestones,
        workspace_files=workspace,
        created_at=now,
        updated_at=now,
    )
    return _finalize_planned_project(project)


REPO_MILESTONE_MAX = 8


def _and_list(items: list[str]) -> str:
    """`x`, `x and y`, `x, y and z` — a milestone names two or three things per step."""
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _brief(items: list[str], limit: int = 2) -> str:
    """Name the first two and count the rest.

    `validate_project` refuses learner-facing lines longer than ~28 words, which is a
    rule worth keeping: a milestone is a card, not a paragraph. A file that imports
    nine others is real (measure_project_quality.py does), so the list has to be
    counted rather than spelled out — and dropping the count would be a lie of the
    other kind.
    """
    if len(items) <= limit:
        return _and_list(items)
    return f"{_and_list(items[:limit])} and {len(items) - limit} more"


def _repo_manifest(snapshot, chosen: list) -> str:
    """The course's only view of the repository: paths, names, edges. Never the code.

    `source_excerpt` feeds `enrich_project` and any later LLM call, so what is in it
    bounds what the model can say. A manifest keeps that inside the same rule the rest
    of this module follows: the API is quotable, the implementation is not.
    """
    lines = [
        f"Repository {snapshot.full_name} ({snapshot.ref}), license {snapshot.license}.",
        snapshot.description,
    ]
    for facts in chosen:
        lines.append(
            f"{facts.path}: defines {', '.join(facts.public_names[:6])}"
            + (f"; imports {', '.join(sorted(facts.depends))}" if facts.depends else "")
            + (f"; uses {', '.join(sorted(facts.external)[:6])}" if facts.external else "")
        )
    return "\n".join(line for line in lines if line)


def _dedupe_milestones(milestones: list) -> list:
    """Drop a milestone that repeats an earlier one.

    Two steps built from the same source quote and the same verification check
    are one step said twice. Left in, they produce duplicate titles such as
    "Print output" appearing twice, which `is_hollow_guided_project` reads as a
    hollow course — so a perfectly good project becomes permanently unopenable
    after it has already been saved.
    """
    seen = set()
    kept = []
    for milestone in milestones:
        check = milestone.checks[0] if milestone.checks else None
        signature = (
            milestone.title.strip().lower(),
            check.kind if check else "",
            (check.target if check else "").strip().lower(),
            (milestone.source_quote or "").strip().lower()[:120],
        )
        if signature in seen:
            continue
        seen.add(signature)
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

    "What this project has" is the workspace *and* every file a step asks the learner
    to write, which for a transcript route is nothing extra and for a repository route
    is most of the course. Reading only `workspace_files` meant that a repository course
    silently lost every import check minted against a file it never seeded - which is how
    the rule that guards single-file projects against the unreachable check quietly
    guarded multi-file projects against having one at all.
    """
    available = _local_module_names(project) | {
        (check.path or "").split("/")[-1].rsplit(".", 1)[0].strip().lower()
        for milestone in milestones for check in (milestone.checks or []) if check.path
    } | {
        (check.target or "").split("/")[-1].rsplit(".", 1)[0].strip().lower()
        for milestone in milestones for check in (milestone.checks or [])
        if check.kind == "file_exists"
    }
    authored = {
        m.group(1).lower()
        for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\.py", project.source_excerpt or "")
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
        return f"Your implementation should use `{first}`."
    return "Implement this section, then click NEXT."


def validate_project(project: ProjectCourse) -> None:
    """Reject courses with transcript leaks, duplicate titles, or hollow milestones."""
    coding = [
        m for m in project.milestones
        if m.checks and m.checks[0].kind
        in ("import", "symbol", "symbol_in_file", "function_call", "code_contains")
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
        for field in (m.microstep.action, m.microstep.observation, m.hook, m.teach):
            if looks_like_raw_transcript(field):
                raise ProjectGroundingError(
                    "Generated lesson content still contains raw transcript speech. "
                    "Try a cleaner transcript or a video with chapter markers."
                )
        if m.microstep.action and len(m.microstep.action) > 220:
            raise ProjectGroundingError(
                "Generated lesson instructions are too long. The source may be too conversational."
            )

    run_ok_titles = [m.title.strip().lower() for m in project.milestones if "run and verify" in m.title.strip().lower()]
    if len(run_ok_titles) > 1:
        raise ProjectGroundingError(_NOT_ENOUGH_MATERIAL)

    if looks_like_raw_transcript(project.project_goal):
        raise ProjectGroundingError(
            "Could not produce a clean project overview from this source."
        )


#: Check kinds that name a thing the learner must produce. They carry the
#: definition of a step, which means two of them can be the same step — unlike a
#: `run_ok` checkpoint, which has no target, so "the same check twice" says nothing
#: about it. A tutorial that says "run it and see" after each function is a normal
#: build-along; refusing two `run_ok` milestones was the first draft of this rule,
#: and it rejected a good project.
SUBSTANTIVE_CHECK_KINDS = frozenset(
    {"import", "symbol", "symbol_in_file", "function_call", "code_contains"}
)


def usability_problem(project: ProjectCourse) -> str | None:
    """Why this saved course cannot be a guided project, or None when it can.

    The signals are structural — what the NEXT gate would verify — rather than
    strings matched against titles, because the titles come from the same transcript
    as the content and a talk reads perfectly well while describing nothing to
    build. Duplicate verification is the sharpest one: an `import collections` check
    *is* the definition of that step, so two milestones naming the same thing are
    one step counted twice. The learner does one piece of work, the gate cascades
    through both, and the progress bar reports six steps for three.
    """
    keys: dict[tuple[str, str], str] = {}
    for m in project.milestones:
        if not m.checks:
            continue
        check = m.checks[0]
        target = (check.target or "").strip().lower()
        if check.kind not in SUBSTANTIVE_CHECK_KINDS or not target:
            continue
        key = (check.kind, target, check.path.strip().lower())
        if key in keys:
            return (
                f"`{m.title}` verifies the same thing as `{keys[key]}` "
                f"({check.kind}: {target}), so the two steps are one step."
            )
        keys[key] = m.title

    titles = [m.title.strip().lower() for m in project.milestones]
    if any(titles.count(t) >= 2 for t in titles if t in {"run and verify", "print output", "print the result"}):
        return "Several milestones only ask you to run the program and print output, with nothing new to write between them."

    run_ok = sum(1 for m in project.milestones if m.checks and m.checks[0].kind == "run_ok")
    if run_ok >= 3:
        return "Most of this course's milestones are run-and-verify checkpoints rather than code to write."

    coding = [
        m for m in project.milestones
        if m.checks and m.checks[0].kind in SUBSTANTIVE_CHECK_KINDS
    ]
    if len(coding) < 2:
        return "This source does not describe enough concrete implementation steps to build along."
    return None


def is_hollow_guided_project(project: ProjectCourse) -> bool:
    """True when a saved course has too little real implementation structure."""
    return usability_problem(project) is not None


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
