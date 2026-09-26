"""Create Course source quality gate.

Evaluates an ingested source BEFORE expensive generation and BEFORE a persistent
workspace is created. Decisions are structured:

    accept | reject | insufficient

The gate is deterministic (no network). An optional LLM analyzer may refine
*borderline* (medium-confidence) cases, but it cannot override a high-confidence
deterministic accept or reject, and tests never require a live model.

This is not a keyword allow/deny list for "Python" / "AI" / "ChatGPT". It looks
for clustered implementation evidence (code artifacts, named techniques, APIs,
architecture) versus non-project shapes (dangling instructions, document-writing
tasks, conversations, news, empty/garbled transcripts).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Any, Literal, Protocol

from .project_models import Milestone, ProjectCourse
from .source_ingestion import SourceDocument

Decision = Literal["accept", "reject", "insufficient"]
Confidence = Literal["high", "medium", "low"]


class ProjectGroundingError(ValueError):
    """Raised when a source cannot be reliably turned into a guided project."""


class SourceQualityError(ProjectGroundingError):
    """Raised when a source must not become a guided project.

    Subclasses ``ProjectGroundingError`` so existing ``except`` clauses and tests
    still match. Extra fields drive the API's accept/reject/insufficient contract.
    """

    def __init__(self, message: str, decision: SourceQualityDecision) -> None:
        super().__init__(message)
        self.decision = decision.decision  # reject | insufficient
        self.quality = decision

    @classmethod
    def from_decision(cls, decision: "SourceQualityDecision") -> "SourceQualityError":
        return cls(decision.user_message, decision)


@dataclass
class SourceQualityDecision:
    decision: Decision
    quality_score: float = 0.0
    project_goal: str = ""
    source_type: str = "unknown"
    technical_evidence: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    confidence: Confidence = "low"
    user_message: str = ""
    next_step: str = ""
    stage: str = "analysis"

    def to_public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["quality_score"] = round(float(self.quality_score), 3)
        return data


# ─── Messages ────────────────────────────────────────────────────────────────

_REJECT_MSG = (
    "This video doesn't contain enough relevant technical content to create a "
    "meaningful coding project. Try a tutorial that builds a specific application, "
    "algorithm, or technical system."
)
_NEWS_MSG = (
    "This source is news or political commentary, not a coding tutorial. "
    "Create Course needs a hands-on tutorial that builds a specific application, "
    "algorithm, or technical system."
)
_ASSISTANT_MSG = (
    "This source is about using an AI assistant (prompting, tips, or productivity "
    "chats), not about implementing software. Create Course needs a coding or ML "
    "tutorial that builds a specific application, algorithm, or technical system."
)
_CONCEPTUAL_MSG = (
    "This source explains a concept but doesn't show how to implement a project. "
    "Create Course needs a tutorial that builds a specific application, algorithm, "
    "or technical system — not a math or intuition lecture alone."
)
_INSUFFICIENT_MSG = (
    "This source may be related to programming, but there isn't enough reliable "
    "material to create a meaningful coding project. Patchwork won't guess at "
    "goals, milestones, or requirements."
)
_INSUFFICIENT_NEXT = (
    "Paste a fuller transcript, or pick a hands-on tutorial that shows a specific "
    "application, algorithm, or technical system being built."
)
_REJECT_NEXT = (
    "Try a tutorial that builds a specific application, algorithm, or technical system."
)
_EXTRACT_MSG = (
    "YouTube didn't return a transcript for this video, so there's no source "
    "content to ground a project in. Open the video on YouTube, click the "
    '"…" menu → "Show transcript", copy the text, then use the '
    '"Paste Transcript / Notes" option here to build the guided project.'
)


# ─── Structural patterns (general, not screenshot-phrase denylists) ───────────

# Pronoun / filler objects after a construction verb: "implement them", "build like".
_DANGLING_OBJECT = re.compile(
    r"\b(?:write|create|implement|build|make|compose|draft|assemble|ship|code)\s+"
    r"(?:him|her|them|it|this|that|us|me|yourself|yourselves|like|stuff|things|whatever)\b",
    re.IGNORECASE,
)

# Document-production tasks (memos, emails, essays) — not software artifacts.
# Allow a short recipient/filler span so "write ChatGPT a draft" still matches.
_WRITE_DOCUMENT = re.compile(
    r"\b(?:write|draft|compose|create)\b.{0,48}\b"
    r"(?:memo|email|e-mails?|letter|essay|speech|briefing|press[ -]?release|"
    r"cover[ -]?letter|thank[- ]you(?: note)?|newsletter|draft)"
    r"(?!\s+(?:function|class|method|variable|module|component|parser))",
    re.IGNORECASE,
)

# Using an assistant as a writing/productivity tool, not implementing software.
# Product names only — not GPT-2 / model-architecture tutorials.
_ASSISTANT_PRODUCT = (
    r"(?:chat\s*gpt|chatgpt|google\s*bard|gemini(?:\s+(?:advanced|pro|app))?|"
    r"claude(?:\s+\d)?|copilot|the chatbot|the assistant)"
)
_ASSISTANT_USAGE = re.compile(
    r"\b(?:ask|tell|prompt|write)\s+" + _ASSISTANT_PRODUCT + r"\b|"
    r"\b" + _ASSISTANT_PRODUCT + r"\s+(?:to|will|can|for)\b|"
    r"\buse\s+" + _ASSISTANT_PRODUCT + r"\s+(?:to|for|and)\b|"
    r"\b(?:tips?|hacks?|prompts?|tricks?|features?)\s+(?:for|to use)\s+" + _ASSISTANT_PRODUCT + r"\b|"
    r"\bhow to use\s+" + _ASSISTANT_PRODUCT + r"\b|"
    r"\b" + _ASSISTANT_PRODUCT + r"\s+(?:tips?|hacks?|prompts?|tricks?|features?)\b",
    re.IGNORECASE,
)
_ASSISTANT_TIPS_TITLE = re.compile(
    r"\b(?:\d+\s+)?" + _ASSISTANT_PRODUCT + r"\s+(?:tips?|hacks?|prompts?|tricks?|features?)\b|"
    r"\b(?:tips?|hacks?|prompts?|tricks?)\s+(?:for|to use)\s+" + _ASSISTANT_PRODUCT + r"\b|"
    r"\bhow to use\s+" + _ASSISTANT_PRODUCT + r"\b",
    re.IGNORECASE,
)
_ASSISTANT_HABIT = re.compile(
    # Tip/productivity habits only. Bare "talk to" matches every LLM intro lecture
    # that says you can talk to ChatGPT — those are talks, not assistant-tips videos.
    r"\b(?:assign roles to|speak with|chat logs|custom instructions|"
    r"prompt sequences?|prompt follow-up|act as a|archive (?:your )?chats)\b",
    re.IGNORECASE,
)

_CONVERSATION = re.compile(
    r"\b(podcast|interview|today'?s guest|welcome to the (?:show|podcast)|"
    r"sit(?:ting)? down with|fireside chat|q\s*&\s*a episode|"
    r"thanks for (?:coming|joining|being) on|"
    r"my (?:guest|co-?host) (?:today|is|this)|"
    r"welcome back to)\b",
    re.IGNORECASE,
)

_NEWS = re.compile(
    r"\b(?:breaking news|geopolitic|foreign policy|headlines|pundit|"
    r"ceasefire|election night|press conference|nightly news|newsroom|"
    r"news central|president-elect|"
    r"(?:war|conflict) in [A-Z][a-z]+)\b",
    re.IGNORECASE,
)
_NEWS_PATTERNS = (
    re.compile(r"\b(?:breaking news|nightly news|news central|newsroom|headlines)\b", re.I),
    re.compile(r"\b(?:pundit|press conference|ceasefire|election night|foreign policy|geopolitic)\b", re.I),
    re.compile(r"\b(?:president-elect|white house|prime minister|campaign trail)\b", re.I),
    re.compile(r"\breacts? to (?:critics?|reports?|allegations|claims)\b", re.I),
    re.compile(r"\b(?:republican|democratic|labour|conservative) strategist\b", re.I),
    re.compile(r"\bresponded to criticism\b", re.I),
    re.compile(r"\bjoined (?:us |by ).{0,80}\b(?:discuss|debate|react)\b", re.I),
    re.compile(r"\b(?:war|conflict) in [A-Z][a-z]+\b"),
)

_MOTIVATIONAL = re.compile(
    r"\b(?:believe in yourself|hustle culture|morning routine|manifest(?:ing)?|"
    r"inspirational talk|motivational speech)\b",
    re.IGNORECASE,
)

_TEACH_BUILD = re.compile(
    r"\b(from scratch|step[- ]by[- ]step|follow along|"
    r"hands[- ]on|live coding|build along|coding along|"
    r"github\.com|jupyter|colab|starter code|"
    r"let'?s (?:build|write|code|implement|create)|"
    r"define (?:a |the )?(?:class|function|method|dataclass)|"
    r"reproduce)\b",
    re.IGNORECASE,
)
# Weaker instructional cues — only count when technical evidence already exists.
_TEACH_WEAK = re.compile(
    r"\b(tutorial|walkthrough|exercise|implement|lesson)\b",
    re.IGNORECASE,
)
_NEGATED_TEACH = re.compile(
    r"\b(?:not|no|never)\s+(?:a |an |the )?(?:tutorial|walkthrough|coding|programming)\b",
    re.IGNORECASE,
)

# Conceptual / intuition lectures — not build-alongs.
_CONCEPTUAL_TITLE = re.compile(
    r"\bbut what is\b|"
    r"\bwhat is(?: a| an)?\b.{0,60}\?|"
    r"\b(?:explained(?: visually)?|the intuition|intuitively|visuali[sz]ed|"
    r"the math (?:behind|of|underlying)|essence of|intuition behind)\b",
    re.IGNORECASE,
)
_CONCEPTUAL_HEADING = re.compile(
    r"^\s*(?:but\s+)?(?:what (?:is|are)\b|why (?:are|is|do|does)\b|"
    r"how \w+ relates\b|introducing\b|notation\b|series preview\b|"
    r"some final words\b|intuition\b)",
    re.IGNORECASE,
)
_BUILD_ACTION_HEADING = re.compile(
    r"\b(?:implement(?:ing)?|build(?:ing)?|code|coding|define|defined|"
    r"write|writing|create|creating|train(?:ing)? the|reproduc(?:e|ing)|"
    r"from scratch|follow along|load(?:ing)? the|sampling loop|"
    r"forward pass|backward (?:pass|function))\b",
    re.IGNORECASE,
)
_BUILD_INTENT = re.compile(
    r"\blet'?s (?:build|implement|write|code|create|reproduce)\b|"
    r"\bwe (?:will |are going to |gonna )?(?:build|implement|reproduce)\b|"
    r"\bhow to (?:build|implement)\b|"
    r"\bimplementing\b|"
    r"\bfrom scratch\b|"
    r"\bfollow(?:ing)? along\b|"
    r"\bhands[- ]on\b|"
    r"github\.com|"
    r"\bstarter code\b|"
    r"\bdefine (?:a |the )?(?:class|function|method)\b|"
    r"\breproduce\b",
    re.IGNORECASE,
)

# A narrator announcing the next thing they are about to write. Rare in a talk,
# dense in a build-along, and the only implementation cue a captioned lecture
# leaves behind when the page exposes no chapters, repo link or file names.
_SPOKEN_BUILD = re.compile(
    r"\b(?:we(?:'ll| will| are going to|'re going to)?|i(?:'ll| will| am going to)"
    r"|let'?s|you(?:'ll| will))\s+(?:now\s+|then\s+)?"
    r"(?:build|implement|write|create|code|define|train|reproduce)\b",
    re.IGNORECASE,
)

_CODE_IMPORT = re.compile(
    r"\bimport\s+[A-Za-z_][A-Za-z0-9_.]*\b|\bfrom\s+[A-Za-z_][A-Za-z0-9_.]*\s+import\b"
)
_CODE_DEF = re.compile(
    r"\bdef\s+[A-Za-z_]"
    r"|\bclass\s+(?:called\s+)?[A-Z][A-Za-z0-9_]*"
    r"|\bfunction\s+called\s+[A-Za-z_]"
    r"|\b(?:async )?function\s+[A-Za-z_][A-Za-z0-9_]*\s*\("
    r"|\b(?:const|let|var)\s+[A-Za-z_][A-Za-z0-9_]*\s*="
)
_CODE_FILE = re.compile(r"\b[\w.-]+\.(?:py|js|ts|tsx|jsx|java|cpp|cc|h|hpp|sql|ipynb|rs|go)\b")
_DOTTED_API = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_.]*")
# GPTConfig / HTTPServer — acronym then PascalCase. Does NOT match ChatGPT.
_ACRONYM_PASCAL = re.compile(r"\b[A-Z]{2,}[a-z][A-Za-z0-9]*\b")
_INNER_CAMEL = re.compile(r"\b[A-Z][a-z]+[A-Z][A-Za-z0-9]*\b")
_PRODUCT_CAMEL = {
    "chatgpt",
    "youtube",
    "linkedin",
    "facebook",
    "instagram",
    "whatsapp",
    "tiktok",
    "powerpoint",
}
_SNAKE_ID = re.compile(r"\b[a-z][a-z0-9]+_[a-z0-9_]+\b")
_GITHUB = re.compile(r"github\.com/[\w.-]+/[\w.-]+", re.IGNORECASE)
_DOTTED_URL_HEAD = {"www", "http", "https", "image", "mailto"}
_DOTTED_URL_TAIL = {
    "com", "org", "net", "io", "edu", "gov", "html", "htm", "php",
    "co", "uk", "us", "au", "jpg", "jpeg", "png", "gif", "webp", "svg",
}

# Bare category nouns with no specific technique/name.
_GENERIC_OBJECTS = {
    "algorithm",
    "app",
    "application",
    "program",
    "system",
    "project",
    "code",
    "script",
    "software",
    "thing",
    "stuff",
    "tool",
}

_GENERIC_BARE = re.compile(
    r"\b(?:implement|build|create|write|make)\s+(?:an?\s+|the\s+)?"
    r"(algorithm|app|application|program|system|project|code|script|software|thing|stuff|tool)\b"
    r"(?:\s*$|\s+(?:yourself|yourselves|like)\b)",
    re.IGNORECASE,
)

# Words that are too generic to count as technical evidence on their own.
_GENERIC_TECH_WORDS = {
    "python",
    "ai",
    "chatgpt",
    "gpt",
    "code",
    "coding",
    "program",
    "programming",
    "algorithm",
    "software",
    "computer",
    "data",
    "app",
    "application",
    "project",
    "tutorial",
    "course",
    "lesson",
    "video",
    "learn",
    "learning",
}

# Programming constructs / components that *do* count when they appear as objects.
_CONSTRUCTS = {
    "function",
    "class",
    "method",
    "module",
    "variable",
    "endpoint",
    "database",
    "schema",
    "parser",
    "tokenizer",
    "dataloader",
    "optimizer",
    "server",
    "client",
    "router",
    "handler",
    "pipeline",
    "dataset",
    "tensor",
    "scraper",
    "crawler",
    "counter",
    "websocket",
    "cache",
    "compiler",
    "interpreter",
    "decorator",
    "iterator",
    "generator",
    "middleware",
    "controller",
    "serializer",
    "migration",
    "query",
    "index",
    "thread",
    "process",
    "socket",
    "buffer",
    "encoder",
    "decoder",
    "attention",
    "gradient",
    "backprop",
    "backpropagation",
    "transformer",
    "perceptron",
    "regression",
    "logits",
    "micrograd",
    "derivative",
    "neuron",
    "embeddings",
    "checkpoint",
    "scheduler",
    "dataclass",
    "hyperparameter",
    "hyperparameters",
}

_SPECIFIC_PHRASES = (
    "linear regression",
    "logistic regression",
    "k-nearest",
    "k nearest",
    "k-means",
    "k means",
    "support vector",
    "neural net",
    "neural network",
    "from scratch",
    "word frequency",
    "flash attention",
    "self-attention",
    "cross entropy",
    "data loader",
    "gradient descent",
    "value object",
    "forward pass",
    "sampling loop",
    "from_pretrained",
    "rest api",
    "web scraper",
    "todo list",
    "frequency counter",
    "backpropagat",
    "micrograd",
    "multi-layer perceptron",
    "expression graph",
    "loss function",
    "nn.module",
)

# Short tokens that still name a real technique (not "ai" / "code").
_SPECIFIC_TOKENS = {
    "knn",
    "svm",
    "mlp",
    "rnn",
    "cnn",
    "lstm",
    "gan",
    "ddp",
    "api",
    "sql",
    "html",
    "css",
    "json",
    "http",
    "tcp",
}

# High-signal libraries/frameworks. Presence is evidence, never sufficient alone.
_LIBRARIES = {
    "pytorch",
    "torch",
    "tensorflow",
    "keras",
    "numpy",
    "pandas",
    "sklearn",
    "scikit-learn",
    "flask",
    "fastapi",
    "django",
    "requests",
    "httpx",
    "beautifulsoup",
    "bs4",
    "langchain",
    "transformers",
    "tiktoken",
    "sqlalchemy",
    "pytest",
    "matplotlib",
    "openai",
    "anthropic",
    "sqlite3",
    "pydantic",
    "asyncio",
    "collections",
    "beautifulsoup4",
    "express",
    "react",
    "vue",
    "nextjs",
    "spring",
    "junit",
}

_FILLER_WORDS = {
    "um",
    "uh",
    "like",
    "yeah",
    "gonna",
    "wanna",
    "kinda",
    "sorta",
    "okay",
    "ok",
    "right",
    "basically",
}


# ─── Evidence extraction ──────────────────────────────────────────────────────


def gather_source_text(doc: SourceDocument) -> str:
    if doc.plain_text and doc.plain_text.strip():
        return doc.plain_text
    parts: list[str] = []
    for seg in doc.segments or []:
        if seg.transcript and seg.transcript.strip():
            parts.append(f"{seg.title}. {seg.transcript}")
        elif seg.description_snippet:
            parts.append(f"{seg.title}. {seg.description_snippet}")
        elif seg.title:
            parts.append(seg.title)
    return "\n".join(parts)


def _collect_chapters(doc: SourceDocument) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for seg in doc.segments or []:
        for ch in seg.chapters or []:
            cleaned = ch.strip(" -–—:•\t")
            key = cleaned.lower()
            if cleaned and key not in seen:
                seen.add(key)
                out.append(cleaned)
    return out


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


def _real_dotted_tokens(text: str) -> list[str]:
    """Dotted identifiers that look like APIs (nn.Module), not www.example.com."""
    if not text:
        return []
    hits: list[str] = []
    for match in _DOTTED_API.finditer(text):
        token = match.group(0)
        head, _, rest = token.partition(".")
        if head.lower() in _DOTTED_URL_HEAD:
            continue
        first_tail = rest.split(".", 1)[0].lower()
        if first_tail in _DOTTED_URL_TAIL:
            continue
        hits.append(token)
    return hits


def has_code_artifact(text: str) -> bool:
    """True for real code/API artifacts — not product names like ChatGPT."""
    if not text:
        return False
    return bool(
        _CODE_IMPORT.search(text)
        or _CODE_DEF.search(text)
        or _CODE_FILE.search(text)
        or _real_dotted_tokens(text)
        or _GITHUB.search(text)
        or _ACRONYM_PASCAL.search(text)
    )


def _library_hits(text: str) -> list[str]:
    low = text.lower()
    found: list[str] = []
    for lib in _LIBRARIES:
        if re.search(rf"\b{re.escape(lib)}\b", low) and lib not in found:
            found.append(lib)
    return found


def _specific_phrase_hits(text: str) -> list[str]:
    low = text.lower()
    return [p for p in _SPECIFIC_PHRASES if p in low]


def _construct_hits(text: str) -> list[str]:
    words = set(_words(text))
    return sorted(w for w in words if w in _CONSTRUCTS)


def has_technical_substance(text: str) -> bool:
    """True when a span names something a learner could actually implement."""
    if not text or not text.strip():
        return False
    if is_dangling_or_document_task(text) and not has_code_artifact(text):
        return False
    if is_generic_bare_task(text):
        return False
    if has_code_artifact(text):
        return True
    if _SNAKE_ID.search(text) and not is_dangling_or_document_task(text):
        return True
    if _ACRONYM_PASCAL.search(text):
        return True
    for m in _INNER_CAMEL.finditer(text):
        if m.group(0).lower() not in _PRODUCT_CAMEL:
            return True
    if _library_hits(text):
        return True
    if _specific_phrase_hits(text):
        return True
    if _construct_hits(text):
        return True
    if any(w in _SPECIFIC_TOKENS for w in _words(text)):
        return True
    return False


def is_dangling_or_document_task(text: str) -> bool:
    return bool(_DANGLING_OBJECT.search(text) or _WRITE_DOCUMENT.search(text))


def is_generic_bare_task(text: str) -> bool:
    return bool(_GENERIC_BARE.search(text.strip()))


def is_conceptual_heading(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if _CONCEPTUAL_HEADING.search(cleaned):
        return True
    if cleaned.endswith("?") and not _BUILD_ACTION_HEADING.search(cleaned):
        return True
    return False


def is_implementable_step(text: str) -> bool:
    """A candidate milestone/heading must be a concrete, technical action."""
    cleaned = (text or "").strip()
    if len(cleaned) < 6:
        return False
    if is_dangling_or_document_task(cleaned):
        return False
    if is_generic_bare_task(cleaned):
        return False
    if is_conceptual_heading(cleaned):
        return False
    # Incomplete fragments: action verb plus a trailing filler ("build like").
    if re.search(r"\b(?:build|implement|create|write|make)\s+like\b", cleaned, re.I):
        return False
    return has_technical_substance(cleaned)


def _has_strong_teach(text: str) -> bool:
    if _NEGATED_TEACH.search(text):
        return False
    return bool(_TEACH_BUILD.search(text))


def extract_technical_evidence(text: str, title: str = "") -> list[str]:
    blob = f"{title}\n{text}"
    evidence: list[str] = []
    if _CODE_IMPORT.search(blob):
        evidence.append("source includes import/from statements")
    if _CODE_DEF.search(blob):
        evidence.append("source defines functions or classes")
    if _CODE_FILE.search(blob):
        evidence.append("source names source files")
    if _real_dotted_tokens(blob) or _ACRONYM_PASCAL.search(blob):
        evidence.append("source names APIs or code identifiers")
    if _GITHUB.search(blob):
        evidence.append("source links a code repository")
    libs = _library_hits(blob)
    if libs:
        evidence.append("libraries: " + ", ".join(libs[:8]))
    phrases = _specific_phrase_hits(blob)
    if phrases:
        evidence.append("techniques: " + ", ".join(phrases[:8]))
    constructs = _construct_hits(blob)
    if constructs:
        evidence.append("constructs: " + ", ".join(constructs[:8]))
    if _has_strong_teach(blob):
        evidence.append("instructional build-along language")
    return evidence


def extract_project_goal(text: str, title: str) -> str:
    blob = f"{title}. {text}"
    patterns = (
        r"\b(?:let'?s |we (?:will |are going to |gonna )?)?(?:build|implement|create|reproduce|write)\s+"
        r"(?:a |an |the |how to )?([A-Za-z][A-Za-z0-9 ._-]{3,80}?)(?:[.!,]|$)",
        r"\bin this (?:tutorial|video|lesson|course) we (?:will |are going to )?"
        r"(?:build|implement|create|reproduce|write)\s+(?:a |an |the )?([^.!?\n]{3,80})",
    )
    for pat in patterns:
        m = re.search(pat, blob, re.I)
        if m:
            goal = m.group(0).strip(" .")
            if is_implementable_step(goal) or has_technical_substance(goal):
                return goal[:200]
    if title and has_technical_substance(title):
        return title.strip()[:200]
    return ""


# ─── Transcript quality ───────────────────────────────────────────────────────

#: Words of recovered text a diversity statistic is meaningful over. Longer than
#: this and the statistic measures the source's length, not its quality.
_DIVERSITY_SAMPLE_WORDS = 3000


def _repeated_ngram_share(words: list[str], n: int = 5, min_repeats: int = 3) -> float:
    """Share of words sitting inside an n-word run that repeats ``min_repeats``+ times.

    A type-token ratio cannot be used to detect a stuck caption track: word
    diversity falls with length under Zipf's law, so a single ratio flags every
    genuine transcript past ~15k words as garbage — which is precisely the
    multi-hour courses this feature exists for. Measured on the real-source
    corpus in ``create_gate_lab``: 9 genuine build-alongs (12k-118k words) sit at
    0.000-0.068, while repeated-caption garbage sits at 1.0.
    """
    if len(words) < n + 1:
        return 0.0
    counts = Counter(tuple(words[i : i + n]) for i in range(len(words) - n + 1))
    total = sum(counts.values())
    stuck = sum(c for c in counts.values() if c >= min_repeats)
    return stuck / max(total, 1)


def assess_transcript_quality(text: str, chapter_count: int = 0) -> tuple[str, list[str]]:
    """Return (status, notes). status: ok | empty | garbage | repetitive | fragmented.

    Informal speech and filler ('um', 'uh', 'like') are NOT automatic failures.
    """
    stripped = (text or "").strip()
    if len(stripped) < 40 and chapter_count < 2:
        return "empty", ["Transcript is empty or nearly empty."]

    words = _words(stripped)
    if len(words) < 12 and chapter_count < 2:
        return "empty", ["Too little recovered text to ground a project."]

    if not words:
        return "empty", ["No words could be recovered from the source."]

    if len(words) > 40 and _repeated_ngram_share(words) > 0.35:
        return "repetitive", ["Extracted captions repeat the same phrases over and over."]

    # Low vocabulary diversity, measured on a bounded sample so the statistic does
    # not depend on how long the source is.
    sample = words[:_DIVERSITY_SAMPLE_WORDS]
    if len(sample) > 40 and len(set(sample)) / len(sample) < 0.05:
        return "repetitive", ["Extracted captions are almost entirely repeated text."]

    alpha = sum(ch.isalpha() or ch.isspace() for ch in stripped)
    if stripped and alpha / max(len(stripped), 1) < 0.35:
        return "garbage", ["Extracted text looks unusable (garbled or non-linguistic)."]

    # Extremely fragmented: almost no content words and no technical evidence.
    content = [w for w in words if w not in _FILLER_WORDS and len(w) > 2]
    if len(words) > 25 and len(content) / max(len(words), 1) < 0.15 and not has_technical_substance(stripped):
        return "fragmented", ["Speech is too fragmented to recover a project."]

    return "ok", []


_ASSISTANT_HABIT_NEAR_PRODUCT = re.compile(
    r"(?:" + _ASSISTANT_PRODUCT + r").{0,48}(?:assign roles|speak with|chat logs|custom instructions|"
    r"prompt sequences?|prompt follow-up|act as a|archive)|"
    r"(?:assign roles|speak with|chat logs|custom instructions|prompt sequences?|"
    r"prompt follow-up|act as a|archive).{0,48}(?:" + _ASSISTANT_PRODUCT + r")",
    re.IGNORECASE,
)


def _assistant_signal_count(blob: str, title: str) -> int:
    """Clustered assistant-usage evidence — not a single product-name hit."""
    heading = title or ""
    haystack = f"{heading}\n{blob}"
    hits = 0
    tips = bool(_ASSISTANT_TIPS_TITLE.search(heading) or _ASSISTANT_TIPS_TITLE.search(haystack))
    usage = bool(_ASSISTANT_USAGE.search(haystack))
    if tips:
        hits += 2  # a tips-shaped title is decisive on its own
    elif usage:
        hits += 1
    # Habit only counts when it sits next to a product name — otherwise an LLM
    # intro that says "talk to the model" and later names ChatGPT looks like tips.
    if _ASSISTANT_HABIT_NEAR_PRODUCT.search(haystack) or (
        _ASSISTANT_HABIT.search(haystack) and tips
    ):
        hits += 1
    if len(_WRITE_DOCUMENT.findall(haystack)) >= 1 and re.search(_ASSISTANT_PRODUCT, haystack, re.I):
        hits += 1
    return hits


def _news_signal_count(blob: str, title: str) -> int:
    haystack = f"{title}\n{blob}"
    return sum(1 for pat in _NEWS_PATTERNS if pat.search(haystack))


def _conceptual_signal_count(blob: str, title: str, chapters: list[str]) -> int:
    hits = 0
    if _CONCEPTUAL_TITLE.search(title or "") or _CONCEPTUAL_TITLE.search(blob or ""):
        hits += 1
    headings = list(chapters)
    for line in (blob or "").splitlines():
        stripped = line.strip(" -•\t")
        if is_conceptual_heading(stripped):
            headings.append(stripped)
    conceptual_chapters = [c for c in headings if is_conceptual_heading(c)]
    if len(conceptual_chapters) >= 2:
        hits += 1
    if len(conceptual_chapters) >= 4:
        hits += 1
    return hits



#: Chapter titles that read like a coding syllabus rather than a talk outline.
#: freeCodeCamp-style intros often ship a dense TOC (Hello World, Variables,
#: Functions, OOP…) with little prose in the description. Those chapters ARE
#: the implementation sequence — treat a cluster of them as build evidence.
_CURRICULUM_CHAPTER = re.compile(
    r"\b(?:hello\s+world|variables?|declarations?|datatypes?|data\s+types?|"
    r"user\s+input|if/?else|conditionals?|loops?|functions?|methods?|"
    r"classes?|objects?|oop|object[- ]oriented|imports?|libraries?|"
    r"exceptions?|error\s+handling|decorators?|metaprogramming|"
    r"jupyter|setting\s+up|setup|cli|compilers?|interpreters?|"
    r"structs?|ownership|borrow(?:ed|ing)?|simd)\b",
    re.IGNORECASE,
)


def _curriculum_chapters(chapters: list[str]) -> list[str]:
    out: list[str] = []
    for chapter in chapters:
        cleaned = (chapter or "").strip()
        if len(cleaned) < 3 or is_conceptual_heading(cleaned):
            continue
        if _CURRICULUM_CHAPTER.search(cleaned) or is_implementable_step(cleaned):
            out.append(cleaned)
    return out


def _action_chapters(chapters: list[str]) -> list[str]:
    out: list[str] = []
    for chapter in chapters:
        if is_conceptual_heading(chapter):
            continue
        if _BUILD_ACTION_HEADING.search(chapter) and (
            is_implementable_step(chapter) or has_code_artifact(chapter)
        ):
            out.append(chapter)
    return out


def _implementation_density(blob: str) -> bool:
    """True when a long spoken source keeps naming the code it is writing.

    Every other route in ``has_implementation_cluster`` reads structure the video
    *page* exposes — chapters, a repo link, file names. A captioned lecture
    exposes none of that, so its evidence is spread over tens of thousands of
    spoken words and only a count over a long span can see it.

    Topic vocabulary does not count: a two-hour conversation about LLMs names
    PyTorch and transformers constantly. What separates a build-along is someone
    saying the identifiers out the way you say them while typing them —
    ``nn.Module``, ``main.py``, ``import flask``. Measured on the real-source
    corpus (``create_gate_lab``): 9 build-alongs run 9-196 such mentions, and a
    talk, a slide lecture and two interviews all run exactly 0.
    """
    words = _words(blob)
    if len(words) < 2000:
        return False
    if len(_SPOKEN_BUILD.findall(blob)) < 4:
        return False
    named_code = (
        len(_real_dotted_tokens(blob))
        + len(_CODE_FILE.findall(blob))
        + len(_CODE_IMPORT.findall(blob))
    )
    return named_code >= 5


#: How often a long source must name code for one mention to mean anything:
#: roughly one code-naming per this many words.
_CODE_MENTION_FLOOR = 4000

#: Longest a line can still read as a step heading rather than a paragraph.
_STEP_HEADING_MAX = 160


def _names_code_persistently(blob: str) -> bool:
    """True when code is named often enough for its length to be the point.

    A single "function called back" in a two-hour conversation about a machine
    learning book is a figure of speech; the same phrase in a ninety-second
    transcript is the tutorial. Counting mentions once, as this used to, accepted
    the former and planned it into eleven milestones of transcript noise.
    """
    mentions = (
        len(_CODE_DEF.findall(blob))
        + len(_CODE_IMPORT.findall(blob))
        + len(_CODE_FILE.findall(blob))
        + len(_real_dotted_tokens(blob))
    )
    return mentions >= max(2, 1 + len(_words(blob)) // _CODE_MENTION_FLOOR)


def has_implementation_cluster(blob: str, chapters: list[str] | None = None) -> bool:
    """True when the source actually demonstrates building something.

    Vocabulary like "neural network", "OpenAI", or marketing "follow along"
    is not enough. Spoken English ("let me", "function of") is not code.
    """
    chapters = chapters or []
    defs = bool(_CODE_IMPORT.search(blob) or _CODE_DEF.search(blob))
    files = bool(_CODE_FILE.search(blob))
    github = bool(_GITHUB.search(blob))
    action = _action_chapters(chapters)
    strong_teach = _has_strong_teach(blob)
    build_intent = bool(_BUILD_INTENT.search(blob))
    libs = _library_hits(blob)

    if len(action) >= 2:
        return True
    # Dense coding syllabus TOC (language intro / freeCodeCamp-style course).
    if len(_curriculum_chapters(chapters)) >= 5:
        return True
    impl_lines: set[str] = set()
    for line in blob.splitlines():
        stripped = line.strip(" -•\t")
        if len(stripped) < 8:
            continue
        # This route reads a chapter list. Without a ceiling it also reads an
        # entire transcript as one implementable step, because a 20k-word blob
        # contains the words "build" and "implement" somewhere.
        if len(stripped) > _STEP_HEADING_MAX:
            continue
        if is_conceptual_heading(stripped):
            continue
        if not is_implementable_step(stripped):
            continue
        if _BUILD_ACTION_HEADING.search(stripped) or re.search(r"\bimplementation\b", stripped, re.I):
            # The blob repeats the title as its own heading; one line is one cue.
            impl_lines.add(stripped.lower())
    if len(impl_lines) >= 2:
        return True
    if (defs or files) and _names_code_persistently(blob):
        return True
    if github and (build_intent or strong_teach or libs or action):
        return True
    if (strong_teach or build_intent) and libs and action:
        return True
    if _implementation_density(blob):
        return True
    return False


def _classify_source_type(
    blob: str,
    title: str,
    evidence: list[str],
    chapters: list[str] | None = None,
) -> str:
    heading = f"{title}"
    chapters = chapters or []
    dangling = len(_DANGLING_OBJECT.findall(blob))
    doc_tasks = len(_WRITE_DOCUMENT.findall(blob))
    implementation = has_implementation_cluster(blob, chapters)
    real_code = bool(
        _CODE_IMPORT.search(blob)
        or _CODE_DEF.search(blob)
        or _CODE_FILE.search(blob)
        or _real_dotted_tokens(blob)
        or _GITHUB.search(blob)
    )
    strong_tech = bool(_library_hits(blob) or _specific_phrase_hits(blob) or _ACRONYM_PASCAL.search(blob))
    buildable = real_code or strong_tech

    # Interviews/podcasts often name "from scratch" when discussing a book title.
    # Without an implementation cluster that teach cue must not outrank conversation.
    if (_CONVERSATION.search(heading) or _CONVERSATION.search(blob)) and not implementation:
        return "conversation"
    # Assistant-usage wins over marketing "follow along" / product names like OpenAI
    # unless the source actually shows code, files, a repo, or build-along chapters.
    # A tips-shaped title is enough; otherwise demand a denser cluster so an LLM
    # intro that names ChatGPT once is not labeled as a prompting tips video.
    assistant_hits = _assistant_signal_count(blob, heading)
    tips_shaped = bool(
        _ASSISTANT_TIPS_TITLE.search(heading) or _ASSISTANT_TIPS_TITLE.search(blob)
    )
    if not implementation and (tips_shaped or assistant_hits >= 3):
        return "assistant_usage"
    if dangling + doc_tasks >= 2 and not real_code and not implementation:
        return "unrelated"
    news_hits = _news_signal_count(blob, heading)
    if news_hits >= 2 and not implementation:
        return "news_commentary"
    if news_hits >= 1 and not implementation and not buildable:
        return "news_commentary"
    if _NEWS.search(blob) and not implementation and not buildable:
        return "news_commentary"
    if _MOTIVATIONAL.search(blob) and not implementation and not buildable:
        return "motivational"
    conceptual_hits = _conceptual_signal_count(blob, heading, chapters)
    strong_conceptual_title = bool(
        _CONCEPTUAL_TITLE.search(heading)
        or re.search(r"\bbut what is\b", blob, re.I)
        or re.search(r"\bthe math underlying\b", blob, re.I)
    )
    if not implementation and (conceptual_hits >= 2 or strong_conceptual_title):
        return "conceptual_explainer"
    if implementation and (buildable or _has_strong_teach(blob) or real_code or _specific_phrase_hits(blob)):
        return "coding_tutorial"
    if buildable and (_has_strong_teach(blob) or real_code or _specific_phrase_hits(blob)) and implementation:
        return "coding_tutorial"
    if any(w in _GENERIC_TECH_WORDS for w in _words(blob)) and not implementation:
        return "ambiguous_technical"
    if not evidence:
        return "unrelated"
    return "ambiguous_technical"


# ─── Core evaluation ──────────────────────────────────────────────────────────


def _score(
    *,
    evidence: list[str],
    teach: bool,
    goal: str,
    transcript_status: str,
    source_kind: str,
    dangling: int,
    doc_tasks: int,
) -> tuple[float, Confidence]:
    score = 0.0
    score += min(0.45, 0.09 * len(evidence))
    if teach:
        score += 0.12
    if goal:
        score += 0.12
    if transcript_status == "ok":
        score += 0.08
    if source_kind in {
        "conversation",
        "news_commentary",
        "motivational",
        "assistant_usage",
        "unrelated",
        "conceptual_explainer",
    }:
        score -= 0.45
    if dangling + doc_tasks >= 2 and len(evidence) < 2:
        score -= 0.25
    score = max(0.0, min(1.0, score))
    if score >= 0.72 or (
        source_kind
        in {"conversation", "news_commentary", "assistant_usage", "conceptual_explainer"}
        and score < 0.55
    ):
        conf: Confidence = "high"
    elif score >= 0.45:
        conf = "medium"
    else:
        conf = "high" if source_kind != "coding_tutorial" else "medium"
    return score, conf


def evaluate_ingestion(doc: SourceDocument) -> SourceQualityDecision:
    """Stage 1 — did extraction produce usable material?"""
    text = gather_source_text(doc)
    chapters = _collect_chapters(doc)
    failed_extract = doc.source_type in ("youtube_url", "youtube_playlist") and doc.access_level == "titles_only"
    if failed_extract:
        return SourceQualityDecision(
            decision="insufficient",
            quality_score=0.05,
            source_type="empty_or_failed",
            missing_information=["usable transcript", "chapter outline or description of what is built"],
            confidence="high",
            user_message=_EXTRACT_MSG,
            next_step=_INSUFFICIENT_NEXT,
            stage="ingestion",
        )

    status, notes = assess_transcript_quality(text, chapter_count=len(chapters))
    if status in {"empty", "garbage", "repetitive", "fragmented"} and len(chapters) < 2:
        kind = "insufficient"
        msg = _INSUFFICIENT_MSG
        if status == "empty":
            missing = ["a usable transcript or outline"]
        else:
            missing = ["recoverable source text (captions are unusable)"]
        return SourceQualityDecision(
            decision=kind,  # type: ignore[arg-type]
            quality_score=0.08,
            source_type="empty_or_failed",
            rejection_reasons=notes,
            missing_information=missing,
            confidence="high",
            user_message=msg if status != "empty" else (
                "The transcript is empty or too short to create a meaningful coding project. "
                + _INSUFFICIENT_NEXT
            ),
            next_step=_INSUFFICIENT_NEXT,
            stage="ingestion",
        )

    return SourceQualityDecision(
        decision="accept",
        quality_score=0.5,
        source_type="ingested",
        confidence="medium",
        user_message="Source material was extracted.",
        stage="ingestion",
    )


def evaluate_source(doc: SourceDocument, title: str = "") -> SourceQualityDecision:
    """Stage 2 — can this source support a coherent, valuable coding project?"""
    text = gather_source_text(doc)
    chapters = _collect_chapters(doc)
    heading = (title or doc.title or "").strip()
    blob = f"{heading}\n{doc.title}\n{text}\n" + "\n".join(chapters)

    ingest = evaluate_ingestion(doc)
    if ingest.decision != "accept":
        ingest.stage = "analysis"
        return ingest

    evidence = extract_technical_evidence(text + "\n" + "\n".join(chapters), heading)
    goal = extract_project_goal(text, heading)
    teach = _has_strong_teach(blob)
    dangling = len(_DANGLING_OBJECT.findall(blob))
    doc_tasks = len(_WRITE_DOCUMENT.findall(blob))
    t_status, t_notes = assess_transcript_quality(text, chapter_count=len(chapters))
    title_for_class = "\n".join(part for part in (heading, doc.title) if part)
    source_kind = _classify_source_type(blob, title_for_class, evidence, chapters)
    score, conf = _score(
        evidence=evidence,
        teach=teach,
        goal=goal,
        transcript_status=t_status,
        source_kind=source_kind,
        dangling=dangling,
        doc_tasks=doc_tasks,
    )

    implementable_chapters = [c for c in chapters if is_implementable_step(c)]
    implementation = has_implementation_cluster(blob, chapters)
    has_enough_structure = implementation and (
        len(evidence) >= 2
        or (len(_action_chapters(chapters)) >= 2 and has_technical_substance(blob))
        or (len(_curriculum_chapters(chapters)) >= 5)
        or (bool(goal) and has_code_artifact(blob) and teach)
        or bool(_CODE_IMPORT.search(blob) or _CODE_DEF.search(blob))
    )

    if source_kind in {"conversation", "news_commentary", "motivational", "assistant_usage", "unrelated"}:
        reasons = {
            "conversation": "This source reads like a conversation or interview, not a teach-and-build lesson.",
            "news_commentary": "This source is news or commentary, not a technical implementation tutorial.",
            "motivational": "This source is motivational content, not a coding project.",
            "assistant_usage": "This source is about using an AI assistant to write things, not about implementing software.",
            "unrelated": "The source does not describe a coherent software or technical system to build.",
        }
        messages = {
            "conversation": (
                "This source reads like a podcast, interview, or conversation rather than a "
                "teach-and-build lesson. Create Course needs a coding or ML tutorial, walkthrough, "
                "or playlist with examples you can implement."
            ),
            "news_commentary": _NEWS_MSG,
            "motivational": _REJECT_MSG,
            "assistant_usage": _ASSISTANT_MSG,
            "unrelated": _REJECT_MSG,
        }
        return SourceQualityDecision(
            decision="reject",
            quality_score=score,
            project_goal=goal,
            source_type=source_kind,
            technical_evidence=evidence,
            rejection_reasons=[reasons[source_kind], *t_notes],
            confidence="high",
            user_message=messages[source_kind],
            next_step=_REJECT_NEXT,
            stage="analysis",
        )

    if source_kind == "conceptual_explainer" or (not implementation and _conceptual_signal_count(blob, heading, chapters) >= 2):
        return SourceQualityDecision(
            decision="insufficient",
            quality_score=min(score, 0.35),
            project_goal=goal,
            source_type="conceptual_explainer",
            technical_evidence=evidence,
            rejection_reasons=[
                "The source explains a concept but does not demonstrate implementing a project."
            ],
            missing_information=["a hands-on implementation sequence (code, files, or build-along steps)"],
            confidence="high",
            user_message=_CONCEPTUAL_MSG,
            next_step=_INSUFFICIENT_NEXT,
            stage="analysis",
        )

    if not has_enough_structure or source_kind == "ambiguous_technical":
        missing: list[str] = []
        if not goal:
            missing.append("a clear project goal (what the learner is building)")
        if len(evidence) < 2:
            missing.append("concrete technical material (libraries, APIs, functions, files, or architecture)")
        if len(implementable_chapters) < 2 and not has_code_artifact(blob):
            missing.append("an implementable sequence of steps")
        return SourceQualityDecision(
            decision="insufficient",
            quality_score=score,
            project_goal=goal,
            source_type=source_kind,
            technical_evidence=evidence,
            rejection_reasons=t_notes,
            missing_information=missing or ["enough implementable technical detail"],
            confidence=conf,
            user_message=_INSUFFICIENT_MSG + " Missing: " + "; ".join(missing or ["enough implementable technical detail"]) + ".",
            next_step=_INSUFFICIENT_NEXT,
            stage="analysis",
        )

    return SourceQualityDecision(
        decision="accept",
        quality_score=max(score, 0.7),
        project_goal=goal or heading,
        source_type="coding_tutorial",
        technical_evidence=evidence,
        confidence="high" if score >= 0.6 else "medium",
        user_message="Source is suitable for a guided coding project.",
        stage="analysis",
    )


def evaluate_milestones(
    milestones: list[Milestone],
    project_goal: str,
    stage: str = "planning",
) -> SourceQualityDecision:
    """Stage 3 — planned milestones must be a coherent technical sequence."""
    substantive = [
        m
        for m in milestones
        if m.checks and m.checks[0].kind not in {"file_exists", "run_ok"}
    ]
    bad: list[str] = []
    good = 0
    for m in substantive:
        blob = f"{m.title} {m.microstep.action} {m.source_quote} {m.source_grounded_description}"
        # Concrete verification targets already prove the step is implementable ?
        # important for novel languages (Mojo/Zig/?) whose titles the English
        # heuristic does not recognize.
        has_concrete = any(
            c.kind in {"import", "symbol", "function_call", "code_contains"}
            and (c.target or "").strip()
            for c in (m.checks or [])
        )
        if (
            not has_concrete
            and not is_implementable_step(m.title)
            and not is_implementable_step(blob)
        ):
            bad.append(m.title)
            continue
        good += 1

    if good < 2:
        return SourceQualityDecision(
            decision="reject" if bad and not good else "insufficient",
            quality_score=0.15,
            project_goal=project_goal,
            source_type="malformed_plan",
            rejection_reasons=[
                "Planned milestones are incoherent, unrelated, or not implementable."
            ],
            missing_information=["a coherent sequence of technical milestones"],
            confidence="high",
            user_message=_REJECT_MSG if bad else _INSUFFICIENT_MSG,
            next_step=_REJECT_NEXT if bad else _INSUFFICIENT_NEXT,
            stage=stage,
        )

    return SourceQualityDecision(
        decision="accept",
        quality_score=0.8,
        project_goal=project_goal,
        source_type="coding_tutorial",
        technical_evidence=[f"{good} implementable milestones"],
        confidence="high",
        user_message="Milestone sequence is coherent.",
        stage=stage,
    )


def filter_invalid_milestones(milestones: list[Milestone]) -> list[Milestone]:
    """Drop structurally invalid milestones; keep setup/run sentinels.

    A milestone with a concrete import/symbol/call check is kept even when the
    surrounding prose is informal — those checks already name a real artifact.
    """
    kept: list[Milestone] = []
    for m in milestones:
        kind = m.checks[0].kind if m.checks else ""
        target = m.checks[0].target if m.checks else ""
        if kind in {"file_exists", "run_ok"}:
            kept.append(m)
            continue
        if is_dangling_or_document_task(m.title) or is_generic_bare_task(m.title):
            continue
        if kind in {"import", "symbol", "function_call"} and target and len(target) >= 2:
            kept.append(m)
            continue
        blob = f"{m.title} {m.microstep.action} {m.source_quote}"
        if is_implementable_step(m.title) or is_implementable_step(blob):
            kept.append(m)
    for i, m in enumerate(kept, start=1):
        m.order = i
        m.id = f"m{i}"
    return kept


def evaluate_project(project: ProjectCourse, stage: str = "pre_workspace") -> SourceQualityDecision:
    """Stages 4–5 — final check before persistence / display."""
    if not project.milestones:
        return SourceQualityDecision(
            decision="reject",
            quality_score=0.0,
            source_type="malformed_plan",
            rejection_reasons=["Course has no milestones."],
            confidence="high",
            user_message=_REJECT_MSG,
            next_step=_REJECT_NEXT,
            stage=stage,
        )
    planned = evaluate_milestones(project.milestones, project.project_goal, stage=stage)
    if planned.decision != "accept":
        return planned
    # Learner-facing titles must not be dangling fragments.
    for m in project.milestones:
        kind = m.checks[0].kind if m.checks else ""
        if kind in {"file_exists", "run_ok"}:
            continue
        if is_dangling_or_document_task(m.title) or is_generic_bare_task(m.title):
            return SourceQualityDecision(
                decision="reject",
                quality_score=0.2,
                project_goal=project.project_goal,
                source_type="malformed_plan",
                rejection_reasons=[f"Milestone “{m.title}” is not an implementable technical step."],
                confidence="high",
                user_message=_REJECT_MSG,
                next_step=_REJECT_NEXT,
                stage=stage,
            )
    planned.stage = stage
    return planned


def require_accept(decision: SourceQualityDecision) -> None:
    if decision.decision != "accept":
        raise SourceQualityError.from_decision(decision)


# ─── Optional AI analyzer (existing provider architecture) ────────────────────


class SourceAnalyzer(Protocol):
    async def analyze(
        self, doc: SourceDocument, title: str, prior: SourceQualityDecision
    ) -> dict[str, Any]: ...


#: Refusals about *what kind* of source this is. No amount of transcript turns a
#: news broadcast into a tutorial, so these never go to the model.
_SHAPE_REJECTS = {"conversation", "news_commentary", "assistant_usage", "motivational"}

#: A refusal about how much material survived extraction does go to the model —
#: that is the class the pattern language has been proven wrong about.
_UPGRADE_MIN_ARTIFACTS = 3

_ANALYZER_SYSTEM = """You decide whether a learning source can become a source-grounded coding project. In the product, a learner builds one file milestone by milestone and each milestone is checked by running their code.

Judge what the source does, not how long it is. Ninety seconds of "import flask, define create_app" is buildable. Nine hours is buildable if it walks through writing something, and is not buildable if it only discusses the field.

ACCEPT when the source shows software or an ML system being made: it names the libraries, files, functions, classes, APIs or architecture it writes, and its steps could be carried out in an editor. A long course or playlist that covers one build across several parts counts. So does a video whose creator published an outline of what they implement.

REJECT a talk, interview, podcast, news or commentary, motivational content, a lecture read off slides, or an explanation of a concept or of mathematics that never reaches code. REJECT a video about *using* an AI assistant to write things rather than about implementing software.

INSUFFICIENT when it looks like it could be a tutorial but the recovered text is too thin to plan from: a title, a marketing blurb, or captions that never name what is being written.

Never invent a project the source does not describe. To accept, you must name the goal and at least three concrete artifacts the learner will implement, taken from this source — a file, a function, a class, a model, an endpoint. If you cannot list three, do not accept.

Return STRICT JSON only:
{"decision": "accept|reject|insufficient", "project_goal": string, "first_artifacts": [string], "source_type": "coding_tutorial|conceptual_explainer|conversation|news_commentary|assistant_usage|motivational|unrelated|ambiguous_technical", "technical_evidence": [string], "rejection_reasons": [string], "missing_information": [string], "confidence": "high|medium|low"}"""


def build_analyzer_view(doc: SourceDocument, title: str = "", budget: int = 9000) -> str:
    """What the model reads: the outline, plus spans from across the whole source.

    The head of a seven-hour transcript is someone saying hello. Reading only the
    first few thousand characters judged every long course on its introduction.
    """
    text = gather_source_text(doc)
    chapters = _collect_chapters(doc)
    parts = [f"Title: {(title or doc.title).strip()}"]
    if chapters:
        outline = "\n".join(f"  - {c}" for c in chapters[:80])
        parts.append(f"Creator's outline, in order:\n{outline}")
    if len(text) <= budget // 2:
        parts.append(f"Source text:\n{text}")
    else:
        window = budget // 8
        step = max(1, (len(text) - window) // 3)
        spans = [text[i : i + window] for i in range(0, len(text) - window + 1, step)][:4]
        joined = "\n … \n".join(spans)
        parts.append(
            f"Spans sampled from across {len(text)} characters of source "
            f"(head, two middles, tail):\n{joined}"
        )
    return "\n\n".join(parts)[:budget]


class LlmSourceAnalyzer:
    """Wraps AIProvider.generate_structured. Failures never loosen the gate."""

    def __init__(self, provider: Any) -> None:
        self.provider = provider

    async def analyze(
        self, doc: SourceDocument, title: str, prior: SourceQualityDecision
    ) -> dict[str, Any]:
        user = (
            f"{build_analyzer_view(doc, title)}\n\n"
            f"A pattern-matching pre-gate already decided: {json.dumps(prior.to_public_dict())}\n"
            "Decide from the source itself. The pre-gate is often wrong about long "
            "sources and right about what kind of source this is.\n"
        )
        raw = await self.provider.generate_structured(_ANALYZER_SYSTEM, user, max_tokens=700)
        raw = (raw or "").strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return {}
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else {}


def _committed_to_a_plan(extra: dict[str, Any]) -> bool:
    """True when the model put its agreement where its verdict is: a real plan."""
    if str(extra.get("confidence") or "").lower() == "low":
        return False
    if not str(extra.get("project_goal") or "").strip():
        return False
    artifacts = [a for a in (extra.get("first_artifacts") or []) if str(a).strip()]
    if len(artifacts) < _UPGRADE_MIN_ARTIFACTS:
        return False
    evidence = [e for e in (extra.get("technical_evidence") or []) if str(e).strip()]
    return len(evidence) >= 2


def _merge_analyzer(prior: SourceQualityDecision, extra: dict[str, Any]) -> SourceQualityDecision:
    """The model always adds rationale, and may overturn a refusal it can plan around."""
    if not extra:
        return prior
    extra_ev = extra.get("technical_evidence") or []
    extra_rs = extra.get("rejection_reasons") or []
    if isinstance(extra_ev, list):
        prior.technical_evidence = list(dict.fromkeys(prior.technical_evidence + [str(x) for x in extra_ev]))
    if isinstance(extra_rs, list):
        prior.rejection_reasons = list(dict.fromkeys(prior.rejection_reasons + [str(x) for x in extra_rs]))

    proposed = str(extra.get("decision") or prior.decision).lower()
    if proposed not in {"accept", "reject", "insufficient"}:
        proposed = prior.decision

    if prior.decision != "accept":
        shape_refusal = prior.source_type in _SHAPE_REJECTS or prior.source_type == "empty_or_failed"
        if proposed == "accept" and (shape_refusal or not _committed_to_a_plan(extra)):
            proposed = prior.decision
    elif prior.quality_score >= 0.65 and proposed == "reject":
        # Never talk down a source the patterns read as strongly buildable.
        proposed = prior.decision

    prior.decision = proposed  # type: ignore[assignment]
    if extra.get("project_goal") and not prior.project_goal:
        prior.project_goal = str(extra["project_goal"])[:200]
    return prior


async def evaluate_source_with_analyzer(
    doc: SourceDocument,
    title: str = "",
    analyzer: SourceAnalyzer | None = None,
) -> SourceQualityDecision:
    """Deterministic evaluation, with the model reviewing refusals it can be wrong about.

    An accept from the pattern language is cheap to keep and expensive to re-argue,
    so accepts are not re-litigated. A refusal is where patterns have been proven
    wrong — every long transcript in the real-source corpus was refused — so a
    refusal about how much material survived goes to the model. A refusal about the
    *kind* of source does not.
    """
    prior = evaluate_source(doc, title)
    if analyzer is None:
        return prior
    reviews = prior.confidence != "high" or (
        prior.decision != "accept" and prior.source_type not in _SHAPE_REJECTS
    )
    if not reviews:
        return prior
    try:
        extra = await analyzer.analyze(doc, title, prior)
    except Exception:  # noqa: BLE001 — analyzer is best-effort; never invent a course.
        return prior
    return _merge_analyzer(prior, extra)
