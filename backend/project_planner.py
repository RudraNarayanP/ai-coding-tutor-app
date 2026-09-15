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
    "all", "those", "these", "they", "what", "how", "why", "when", "who",
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

    # print / output → only when it's clearly a coding action, not "show transcript"
    # or "test data".
    if re.search(r"\bprint\s*\(|\bprint\s+(?:the\s+)?(?:result|output|value|it)\b", s):
        return ("stdout_contains", "")

    # run / execute / verify → the program must run cleanly. Bare "test" is too
    # common in English ("test data", "test set") to treat as a coding step.
    if re.search(
        r"\b(?:run (?:the |your )?(?:code|program|script|project|it)|"
        r"execute(?: it)?|verify (?:it|that)|check that it works)\b",
        s,
    ):
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

# Chapters that are meta/non-implementation and shouldn't become build milestones.
_META_CHAPTER = re.compile(
    r"^(intro|introduction|welcome|outro|summary|conclusion|recap|results?|"
    r"shoutout|thanks|corrections?|errata|q&a|questions|final thoughts)\b",
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
    # Playlist-style "Tutorial #1 - Introduction" with no implementable payload.
    if re.search(r"\b(introduction|welcome|outro|conclusion|recap|subscribe)\b", cleaned, re.I):
        if not _INSTRUCTIONAL_HEADING.search(cleaned):
            return True
    return False


def _is_instructional_heading(title: str) -> bool:
    if _looks_meta_heading(title):
        return False
    return bool(_INSTRUCTIONAL_HEADING.search(title))


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
    low = title.lower()
    for needle, token in CONCEPT_TOKENS:
        if needle in low:
            return token
    for needle, token in _CONCEPT_WORDS:
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
        if low in _STOPWORDS or low in _ACTION_VERBS:
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


def _concepts_from_prose(text: str, title: str) -> list[str]:
    """Extract ordered implementable topics from title + description (no URL allowlist)."""
    blob = f"{title}\n{text}"
    found: list[str] = []
    seen: set[str] = set()

    def _add(label: str) -> None:
        key = label.lower().strip()
        if not key or key in seen or _looks_meta_heading(label):
            return
        seen.add(key)
        found.append(label.strip())

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
    """Instructional-usefulness gate: reject conversations; allow informal lessons."""
    heading = f"{title}\n{doc.title}"
    blob = f"{heading}\n{text}"
    if _CONVERSATION_SOURCE.search(heading):
        raise ProjectGroundingError(
            "This source reads like a podcast, interview, or conversation rather than a "
            "teach-and-build lesson. Create Course needs a coding or ML tutorial, walkthrough, "
            "or playlist with examples you can implement."
        )
    teach = bool(_TEACH_SIGNAL.search(blob)) or any(_is_instructional_heading(h) for h in outline)
    if _CONVERSATION_SOURCE.search(blob) and not teach:
        raise ProjectGroundingError(
            "This source reads like a podcast, interview, or conversation rather than a "
            "teach-and-build lesson. Create Course needs a coding or ML tutorial, walkthrough, "
            "or playlist with examples you can implement."
        )
    if (not text or len(text.strip()) < 40) and len(outline) < 2:
        raise ProjectGroundingError(
            "Not enough material to ground a course in this source. YouTube didn't provide a "
            "usable transcript or chapter outline. Paste the transcript, or pick a tutorial "
            "with chapters / a description of what is built."
        )


def _chapter_check(title: str) -> VerificationCheck | None:
    # 1) A concrete import/symbol/call if the chapter names one.
    direct = _extract_target(title)
    if direct and direct[0] in ("import", "symbol", "function_call"):
        return _check_for(direct[0], direct[1])
    # 2) Curated concept → token map (grounded concept-level check).
    token = _match_concept_tokens(title)
    if token:
        pretty = token.split("|")[0]
        return VerificationCheck(
            kind="code_contains",
            target=token,
            description=f"Your code implements **{title}** (references `{pretty}`).",
        )
    # 3) Distinctive code identifiers — inner CamelCase or dotted (nn.Module),
    #    not Title-Case English.
    for rx in (_DOTTED, _CAMEL, _DIGITAL_ACRONYM):
        m = rx.search(title)
        if m:
            tok = m.group(1)
            if tok.lower() not in _STOPWORDS:
                return VerificationCheck(
                    kind="code_contains",
                    target=tok,
                    description=f"Your code implements **{title}** (references `{tok}`).",
                )
    # 4) Instructional heading with extractable content words (Karpathy-style
    #    "derivative of a simple function") — still source-grounded, not GPT-2-only.
    if _is_instructional_heading(title):
        generic = _tokens_from_heading(title)
        if generic:
            pretty = generic.split("|")[0]
            return VerificationCheck(
                kind="code_contains",
                target=generic,
                description=f"Your code implements **{title}** (references `{pretty}`).",
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
    for sentence in _split_steps(text):
        if not _is_step(sentence):
            continue
        target = _extract_target(sentence)
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


def plan_project(doc: SourceDocument, title: str, course_id: str) -> ProjectCourse:
    """Build a source-grounded ProjectCourse from an ingested source document.

    Acceptance is based on instructional usefulness (teach → example → apply),
    not on a polished "course product" brand or a GPT-2-specific chapter map.
    Conversations/podcasts and empty sources fail with a clear reason instead of
    emitting a generic curriculum.
    """
    text = _gather_source_text(doc)
    outline = _collect_outline(doc)
    _assert_source_acceptable(doc, text, outline, title)

    instructional_outline = [h for h in outline if _is_instructional_heading(h) or _chapter_check(h)]
    if len(instructional_outline) >= 2:
        try:
            return _plan_from_chapters(doc, outline, title, course_id)
        except ProjectGroundingError:
            pass

    # Prefer explicit coding steps in a transcript over coarse description phrases
    # ("build a word frequency counter") so we don't skip import/def milestones.
    prose_concepts = _concepts_from_prose(text, title or doc.title)
    if len(prose_concepts) >= 2 and _count_sentence_targets(text) < 2:
        try:
            return _plan_from_chapters(doc, prose_concepts, title, course_id)
        except ProjectGroundingError:
            pass

    if not text or len(text.strip()) < 40:
        raise ProjectGroundingError(
            "Not enough material to ground a course in this source. "
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
        if _looks_meta_heading(ch):
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
