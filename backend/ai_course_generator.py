"""OpenRouter-owned Create Course generation.

The configured AI provider (OpenRouter when AI_PROVIDER=openrouter) decides
discard vs create AND authors the guided course from the full transcript.
After create, the same provider self-reviews the full course JSON and revises
on FAIL until PASS or CREATE_COURSE_QUALITY_MAX_TRIES (default 8).
Heuristic planners are fallback-only when CREATE_COURSE_HEURISTIC_FALLBACK=1.

Watch quality retries in logs: logger ``patchwork.ai_course_generator`` emits
``quality_review attempt=N verdict=PASS|FAIL reason=...`` (no secrets).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

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
    SourceQualityDecision,
    SourceQualityError,
    _collect_chapters,
    gather_source_text,
)

logger = logging.getLogger("patchwork.ai_course_generator")

_VALID_CHECK_KINDS = {
    "import",
    "symbol",
    "function_call",
    "code_contains",
    "run_ok",
    "stdout_contains",
    "file_exists",
}

_TRANSCRIPT_BUDGET = 28_000
_CREATE_MAX_TOKENS = int(os.getenv("CREATE_COURSE_MAX_TOKENS", "12000") or 12000)

_SYSTEM = """You are Patchwork Create Course — the sole author of guided coding projects.

You receive a YouTube/tutorial source: title, URL, chapter markers (if any), and transcript text.
You alone decide discard vs create. Do NOT invent a project the source does not teach.

DISCARD when the source is primarily:
- a podcast, interview, Q&A, fireside chat, or conversation
- news, politics, motivational talk, TEDx, or product pitch
- a concept/math/intuition/visual lecture that EXPLAINS ideas but does NOT walk the viewer
  through writing code step-by-step in an editor (e.g. "But what is a neural network?",
  slide talks, "Intro to LLMs" talks without live coding)
- tips about *using* an AI chatbot rather than implementing software
- too thin/garbled to plan real milestones from
CRITICAL: If you would have to INVENT a coding project that the narrator never builds on
camera / in the transcript, you MUST discard. Do not turn explainers into fake tutorials.

CREATE only when the source itself shows BUILDING: the narrator writes/imports/defines/
trains/runs code the learner can mirror. Novel languages (Mojo, Zig, Rust, Elixir, …) and
topics not in a fixed curriculum are fine — ground milestones in THIS transcript and chapters.

LANGUAGE + STACK (critical — beginners follow your file names):
- Set "language" to the language ACTUALLY taught. Mojo tutorials → language "mojo" and entry_file "main.mojo". NEVER set language "python" for a Mojo course even if Mojo looks like Python.
- Rust→rust/main.rs, JS→javascript/main.js, TS→typescript/main.ts, Zig→zig/main.zig.
- tech_stack: only tools/libs named in the source (for Mojo: ["Mojo"] or ["Mojo","Modular"] — never invent numpy/torch/tensorflow).
- example and action MUST use that language real syntax (Mojo: fn / var / let / struct / print; NOT Python-only def/class advice unless the video is explicitly comparing).

GROUNDING — no invented apps:
- If chapter markers exist, milestones MUST follow those chapters in order (merge tiny adjacent chapters; skip pure outro/Q&A).
- project_goal must describe what the video actually builds or practices. Do NOT invent a calculator, todo app, or other product unless the narrator builds that exact app on camera.
- Language-tour courses (Hello World → variables → input → if/else → …) are valid: goal = code along with each demo in the source language.

LEARNER ASSUMPTION (critical):
- The learner NEVER watched the video. Transcript (+ chapter markers) is the ONLY source of truth.
- Write as if teaching someone who has only this app workspace — no video player, no instructor to copy.

BAN these phrases anywhere in course JSON (auto-fail quality):
- Video/instructor: "as in the video", "in the video", "follow the instructor", "as shown",
  "from the video", "watch the video", "like the tutorial", "as demonstrated", "refer to the video"
- Source/transcript crutches (learner has NO YouTube): "follow the source", "follow the transcript",
  "as in the source", "according to the video/source/transcript/instructor", "refer to the source",
  "matching the source", "see the transcript"

LEARNER GUIDE QUALITY (Duolingo-style — structured, not essays):
- Clear project_goal + short course_intro (why it matters) — each ≤2 sentences
- 5–12 milestones in source order (prefer 6–8 for long videos; merge tiny steps)
- Every milestone MUST stand alone without opening YouTube: concrete do-this steps, not "follow along".
- Each milestone (prose fields single-line; teach ≤40 words). Code inside action/example may span
  lines: write "\n" between code lines with real indentation. NEVER join block statements
  (if/while/for/fn/def/struct/class bodies) with ';' — that is invalid code in most languages:
  - title: short chapter-style name
  - hook: ≤12 words, curiosity spark
  - teach: 1–2 plain sentences that TEACH the concept (what it is / why it exists) — never empty meta
  - observation: what they will see/have after this step
  - action: numbered EXACT typing steps. Name the file. Quote the key token/snippet. Concrete do-this only.
  - hint: a REAL nudge (what to type / common mistake) — NEVER "follow the source/transcript/video"
  - example: ONE short, VALID code snippet in the correct language (no fences; "\n" between lines)
  - celebrate: short praise
  - why: one concrete motivation sentence that teaches what this unlocks — never empty
  - source_quote: short phrase copied from transcript/chapters
- Checks ONLY: import | symbol | function_call | code_contains | run_ok | stdout_contains | file_exists
- Checks must verify REAL learning outcomes (structured code artifacts). FORBIDDEN keyword-only targets:
  bare tokens like class / def / import / return / True / print alone, or any single common keyword ≤6 chars.
  Prefer distinctive symbols (Value, __init__, backward, tanh) or multi-token snippets / imports / run_ok.
- Non-Python: prefer code_contains / file_exists / run_ok (not Python AST import/symbol unless truly Python)
- NEVER paste raw transcript speech (no uh/um/you know)
- NEVER invent libraries or steps absent from the source (no numpy/react/express/torch unless named in transcript)
- First milestone may create the entry file; last may be run_ok smoke check
- Mojo function examples must use `fn`, not `def`.

Each milestone source_quote MUST be a short phrase copied from the transcript or chapter list. If you cannot find real implementation quotes (import/def/fn/class/train/write code), DISCARD.
Return STRICT JSON only (no markdown fences, no prose outside JSON):
{"decision":"discard","reason":"one short learner-facing sentence"}
OR
{"decision":"create","course":{
  "title":"...",
  "language":"python|mojo|javascript|typescript|rust|other",
  "entry_file":"main.py|main.mojo|...",
  "project_goal":"...",
  "course_intro":"...",
  "tech_stack":["..."],
  "milestones":[
    {"title":"...","hook":"...","teach":"...","observation":"...","action":"...",
     "hint":"real nudge: what to type / common mistake","example":"...","celebrate":"...","why":"...","source_quote":"short grounded phrase",
     "checks":[{"kind":"code_contains","target":"token","description":"..."}],
     "xp_reward":20}
  ]
}}
"""


def heuristic_fallback_enabled() -> bool:
    return os.getenv("CREATE_COURSE_HEURISTIC_FALLBACK", "").strip() in {"1", "true", "yes", "on"}



def _strip_code_fences(text: str) -> str:
    raw = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if m:
        return m.group(1).strip()
    return raw


def _close_truncated_json(raw: str) -> str:
    """Best-effort close of truncated JSON objects/arrays/strings."""
    s = raw.rstrip()
    # If we ended mid-string, close the quote.
    in_str = False
    esc = False
    for ch in s:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
    if in_str:
        s += '"'
    # Drop a trailing dangling comma.
    s = re.sub(r",\s*$", "", s)
    open_curly = s.count("{") - s.count("}")
    open_square = s.count("[") - s.count("]")
    s += "]" * max(0, open_square)
    s += "}" * max(0, open_curly)
    return s


def _extract_decision(raw: str) -> str:
    m = re.search(r'"decision"\s*:\s*"(create|discard|reject|insufficient)"', raw, re.I)
    return (m.group(1).lower() if m else "")


def _extract_milestones_loose(raw: str) -> list[dict[str, Any]]:
    """Pull milestone objects even when the outer JSON is truncated/invalid."""
    out: list[dict[str, Any]] = []
    for m in re.finditer(r'\{\s*"title"\s*:\s*"(.*?)"', raw, re.DOTALL):
        start = m.start()
        # Take a bounded window and try to parse one object.
        window = raw[start : start + 6000]
        obj = None
        # raw_decode parses ONE object and ignores the following milestones; plain
        # json.loads failed with "Extra data" on every non-last milestone, which
        # silently replaced real milestones with title-only stubs (no why/teach).
        try:
            obj, _end = json.JSONDecoder().raw_decode(window)
        except Exception:  # noqa: BLE001
            obj = None
        if obj is None:
            try:
                obj = json.loads(_close_truncated_json(window))
            except Exception:  # noqa: BLE001
                obj = None
        if obj is None and re.search(r'"milestones"\s*:', window[:600]):
            continue  # truncated course-level object, not a milestone
        if obj is None:
            # Minimal milestone from title alone.
            title = m.group(1).encode("utf-8").decode("unicode_escape", errors="ignore")
            title = re.sub(r"\s+", " ", title).strip()
            if not title:
                continue
            obj = {
                "title": title[:160],
                "action": f"Implement: {title[:120]}",
                "observation": title[:160],
                "teach": title[:200],
                "checks": [{"kind": "code_contains", "target": title.split()[0][:40], "description": f"Work on {title[:80]}"}],
            }
        if isinstance(obj, dict) and "milestones" in obj:
            continue  # course-level object, not a milestone
        if isinstance(obj, dict) and obj.get("title"):
            out.append(obj)
        if len(out) >= 14:
            break
    return out


def _debug_dump(stage: str, raw: str) -> None:
    """Opt-in: CREATE_COURSE_DEBUG_DIR=<dir> writes each raw model response for diagnosis."""
    d = os.getenv("CREATE_COURSE_DEBUG_DIR", "").strip()
    if not d:
        return
    try:
        from pathlib import Path

        path = Path(d)
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{time.strftime('%H%M%S')}_{stage}_{int(time.time() * 1000) % 100000}.txt").write_text(
            raw or "", encoding="utf-8"
        )
    except Exception:  # noqa: BLE001
        logger.exception("debug dump failed")


def _parse_json_object(text: str) -> dict[str, Any]:
    raw = _strip_code_fences(text)
    if not raw:
        return {}
    if not raw.startswith("{"):
        brace = raw.find("{")
        if brace != -1:
            raw = raw[brace:]

    # A complete object followed by trailing prose ("For the above text, give me a
    # summary...") must parse whole — the cut-at-last-milestone fallback below would
    # silently drop the final milestone.
    try:
        first, _end = json.JSONDecoder().raw_decode(raw)
        if isinstance(first, dict):
            return first
    except Exception:  # noqa: BLE001
        pass
    candidates = [raw, _close_truncated_json(raw)]
    # Also try cutting at last complete-looking milestone boundary.
    last_ms = raw.rfind('{"title"')
    if last_ms > 0:
        candidates.append(_close_truncated_json(raw[:last_ms].rstrip().rstrip(",")))

    for cand in candidates:
        try:
            data = json.loads(cand)
            if isinstance(data, dict):
                return data
        except Exception:  # noqa: BLE001
            continue

    # Brace-scan for a complete top-level object.
    depth = 0
    end = -1
    in_str = False
    esc = False
    for i, ch in enumerate(raw):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end != -1:
        try:
            data = json.loads(raw[: end + 1])
            if isinstance(data, dict):
                return data
        except Exception:  # noqa: BLE001
            pass

    # Last resort: synthesize a dict from decision + loose milestones.
    decision = _extract_decision(raw)
    if decision:
        reason_m = re.search(r'"reason"\s*:\s*"(.*?)"', raw, re.DOTALL)
        reason = reason_m.group(1) if reason_m else ""
        if decision == "create":
            milestones = _extract_milestones_loose(raw)
            title_m = re.search(r'"title"\s*:\s*"(.*?)"', raw)
            goal_m = re.search(r'"project_goal"\s*:\s*"(.*?)"', raw, re.DOTALL)
            lang_m = re.search(r'"language"\s*:\s*"(.*?)"', raw)
            entry_m = re.search(r'"entry_file"\s*:\s*"(.*?)"', raw)
            course: dict[str, Any] = {
                "title": (title_m.group(1) if title_m else "Guided Project")[:200],
                "language": (lang_m.group(1) if lang_m else "python")[:40],
                "entry_file": (entry_m.group(1) if entry_m else "main.py")[:200],
                "project_goal": re.sub(r"\s+", " ", (goal_m.group(1) if goal_m else ""))[:2000],
                "course_intro": "",
                "tech_stack": [],
                "milestones": milestones,
            }
            return {"decision": "create", "course": course}
        return {"decision": decision, "reason": re.sub(r"\s+", " ", reason)[:400]}
    return {}


# ---------------------------------------------------------------------------
# Library evidence (speech-aware). Auto-captions never contain code like
# ``import torch`` / ``torch.tensor``; narrators SAY "PyTorch" instead. We ground a
# library when the FULL transcript shows code-form usage OR the canonical name is
# spoken repeatedly (>= _SPOKEN_LIB_MIN, negations like "no numpy" excluded).
# A passing mention (micrograd says "numpy" twice) stays ungrounded.
# ---------------------------------------------------------------------------
_SPOKEN_LIB_MIN = 3
_LIB_ALIASES: dict[str, list[str]] = {
    "numpy": ["numpy", "np"],
    "pandas": ["pandas", "pd"],
    "sklearn": ["sklearn"],
    "scikit-learn": ["sklearn", "scikit-learn", "scikit learn"],
    "tensorflow": ["tensorflow", "tf"],
    "torch": ["torch"],
    "pytorch": ["pytorch", "torch"],
    "keras": ["keras"],
    "jax": ["jax"],
    "express": ["express"],
    "react": ["react"],
    "react-dom": ["react-dom", "reactdom"],
    "next.js": ["next.js", "next/"],
    "django": ["django"],
    "flask": ["flask"],
    "fastapi": ["fastapi"],
    "vue": ["vue"],
    "angular": ["@angular", "angular"],
    "svelte": ["svelte"],
}
# Canonical spoken names. Common English words (react, express, vue, angular, next)
# are deliberately absent: they only ground via code-form evidence.
_LIB_SPOKEN: dict[str, list[str]] = {
    "numpy": ["numpy", "num py"],
    "pandas": ["pandas"],
    "sklearn": ["scikit-learn", "scikit learn", "sklearn"],
    "scikit-learn": ["scikit-learn", "scikit learn", "sklearn"],
    "tensorflow": ["tensorflow", "tensor flow"],
    "torch": ["pytorch", "torch"],
    "pytorch": ["pytorch", "torch"],
    "keras": ["keras"],
    "jax": ["jax"],
    "django": ["django"],
    "flask": ["flask"],
    "fastapi": ["fastapi", "fast api"],
    "svelte": ["svelte"],
}
_NEGATION_RE = re.compile(
    r"(?:\bno|\bnot|\bwithout|\bdon'?t use|\bdo not use|\binstead of|\bavoid(?:ing)?|\bnever)\W+(?:\w+\W+){0,2}$"
)


def _spoken_lib_mentions(lib: str, low: str) -> int:
    names = _LIB_SPOKEN.get((lib or "").lower().strip(), [])
    count = 0
    for name in names:
        for m in re.finditer(r"(?<![a-z0-9_])" + re.escape(name) + r"(?![a-z0-9_])", low):
            before = low[max(0, m.start() - 30): m.start()]
            if _NEGATION_RE.search(before):
                continue
            count += 1
    return count


def lib_code_evidence(lib: str, src: str) -> bool:
    """True when the source shows import/from/attr-usage of the library."""
    lib_l = (lib or "").lower().strip()
    low = (src or "").lower()
    for name in _LIB_ALIASES.get(lib_l, [lib_l]):
        if ("import " + name) in low or ("from " + name) in low:
            return True
        if re.search(r"\b" + re.escape(name) + r"\.[A-Za-z_]", low):
            return True
    if lib_l in {"react", "react-dom"} and ("react-dom" in low or "reactdom" in low):
        return True
    if lib_l == "express" and "require(" in low and "express" in low:
        return True
    return False


def lib_grounded_in_source(lib: str, src: str) -> bool:
    """Code-form usage OR repeated (non-negated) spoken canonical name."""
    if lib_code_evidence(lib, src):
        return True
    return _spoken_lib_mentions(lib, (src or "").lower()) >= _SPOKEN_LIB_MIN


_EVIDENCE_LIBS = ("torch", "numpy", "pandas", "tensorflow", "keras", "jax", "sklearn", "django", "flask", "fastapi")
_EVIDENCE_LABEL = {"torch": "PyTorch (torch)", "sklearn": "scikit-learn"}


def library_evidence_line(doc: "SourceDocument") -> str:
    """Deterministic scan of the FULL transcript so review/revise (which only see a
    short sample) cannot hallucinate which libraries the tutorial uses."""
    try:
        full = f"{doc.title or ''}\n{gather_source_text(doc)}\n{' '.join(_collect_chapters(doc))}"
    except Exception:  # noqa: BLE001
        return ""
    low = full.lower()
    used, passing, absent = [], [], []
    for lib in _EVIDENCE_LIBS:
        n = _spoken_lib_mentions(lib, low)
        code = lib_code_evidence(lib, full)
        label = _EVIDENCE_LABEL.get(lib, lib)
        if code or n >= _SPOKEN_LIB_MIN:
            used.append(f"{label} ({n} mentions{', code-form' if code else ''})")
        elif n > 0:
            passing.append(f"{label} ({n} passing mention{'s' if n != 1 else ''})")
        elif lib in ("torch", "numpy"):
            absent.append(label)
    parts = []
    if used:
        parts.append("USED by the tutorial: " + ", ".join(used))
    if passing:
        parts.append("only mentioned in passing (NOT the stack): " + ", ".join(passing))
    if absent:
        parts.append("NOT in the transcript: " + ", ".join(absent))
    if not parts:
        return ""
    return (
        f"Library evidence (deterministic scan of the FULL {len(full)}-char transcript; "
        "ground truth, overrides the short sample below): " + "; ".join(parts) + "."
    )


def _sample_transcript(text: str, budget: int = _TRANSCRIPT_BUDGET) -> str:
    text = (text or "").strip()
    if len(text) <= budget:
        return text
    # Head / two middles / tail so long lectures still show implementation body.
    window = max(1500, budget // 5)
    if len(text) <= window * 4:
        return text[:budget]
    step = max(1, (len(text) - window) // 3)
    spans = [text[i : i + window] for i in range(0, len(text) - window + 1, step)][:4]
    joined = "\n\n…[transcript continues]…\n\n".join(spans)
    header = f"[Transcript sampled across {len(text)} characters — head, mid, mid, tail]\n\n"
    return (header + joined)[:budget]


def build_create_user_prompt(doc: SourceDocument, title: str) -> str:
    text = gather_source_text(doc)
    chapters = _collect_chapters(doc)
    heading = (title or doc.title or "").strip()
    parts = [
        f"Title: {heading}",
        f"Source URL: {doc.source_url or '(none)'}",
        f"Source type: {doc.source_type}",
    ]
    if chapters:
        outline = "\n".join(f"  {i}. {c}" for i, c in enumerate(chapters[:60], start=1))
        parts.append(f"Creator chapter markers (authoritative outline):\n{outline}")
    evidence = library_evidence_line(doc)
    if evidence:
        parts.append(evidence)
    sampled = _sample_transcript(text)
    if sampled:
        parts.append(f"Full/sampled transcript:\n{sampled}")
    else:
        parts.append("Transcript: (empty — decide discard/insufficient unless chapters alone are enough)")
    parts.append(
        "Decide discard or create. If create: learner never watched the video — transcript/chapters only; "
        "ban phrases like 'as in the video' / 'follow the instructor'; "
        "ground every milestone here; set language/entry_file to the language actually taught "
        "(Mojo→mojo/main.mojo, not python); do not invent a calculator/app unless the narrator builds it; "
        "each action = concrete numbered typing steps + why; checks must verify real code artifacts "
        "(not keyword-only topic words)."
    )
    return "\n\n".join(parts)


def _sanitize(text: str, max_len: int) -> str:
    cleaned = re.sub(r"\b(uh|um|er|ah|you know|i mean)\b", "", (text or "").strip(), flags=re.I)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned[:max_len]


def _sanitize_code(text: str, max_len: int) -> str:
    """Like _sanitize but keeps line breaks and indentation (action/example carry code).
    Models often double-escape newlines, so literal "\\n" becomes a real newline."""
    t = (text or "").replace("\r\n", "\n").strip()
    t = re.sub(r"\\n", "\n", t)
    t = re.sub(r"\b(uh|um|you know|i mean)\b(?=[ ,.])", "", t, flags=re.I)
    lines = [ln.rstrip() for ln in t.split("\n")]
    t = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return t[:max_len]


def _entry_for_language(language: str, entry_file: str) -> str:
    ef = (entry_file or "").strip()
    if ef:
        return ef[:200]
    lang = (language or "python").lower()
    mapping = {
        "python": "main.py",
        "mojo": "main.mojo",
        "javascript": "main.js",
        "typescript": "main.ts",
        "rust": "main.rs",
        "go": "main.go",
        "java": "Main.java",
        "cpp": "main.cpp",
        "c++": "main.cpp",
        "ruby": "main.rb",
        "zig": "main.zig",
    }
    return mapping.get(lang, "main.py")


def _normalize_checks(raw_checks: Any) -> list[VerificationCheck]:
    out: list[VerificationCheck] = []
    if not isinstance(raw_checks, list):
        return out
    for item in raw_checks[:3]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).strip().lower()
        if kind not in _VALID_CHECK_KINDS:
            # Soft remap common mistakes
            if kind in {"contains", "token", "keyword"}:
                kind = "code_contains"
            elif kind in {"def", "function", "class", "var"}:
                kind = "symbol"
            else:
                continue
        target = _sanitize(str(item.get("target", "")), 400)
        desc = _sanitize(str(item.get("description", "")), 280)
        if kind in {"import", "symbol", "function_call", "code_contains", "stdout_contains", "file_exists"} and not target:
            continue
        if not desc:
            desc = f"Verify {kind}: {target}"[:280]
        try:
            out.append(VerificationCheck(kind=kind, target=target, description=desc))
        except Exception:  # noqa: BLE001
            continue
    return out



def _infer_source_language(doc: SourceDocument, title: str) -> str | None:
    """Detect taught language from title/chapters/url when the model mislabels it."""
    heading = f"{title} {doc.title} {doc.source_url or ''}".lower()
    chapters = " ".join(_collect_chapters(doc)).lower()
    blob = f"{heading}\n{chapters}"
    rules = [
        ("mojo", r"\bmojo\b"),
        ("zig", r"\bzig\b"),
        ("rust", r"\brust\b"),
        ("go", r"\bgolang\b|\bgo programming\b"),
        ("typescript", r"\btypescript\b|\btsx\b"),
        ("javascript", r"\bjavascript\b|\bnode\.js\b"),
        ("java", r"\bjava\b(?!script)"),
        ("cpp", r"\bc\+\+|\bcpp\b"),
        ("ruby", r"\bruby\b"),
        ("python", r"\bpython\b|\bpytorch\b|\bmicrograd\b"),
    ]
    for lang, pat in rules:
        if re.search(pat, blob, re.I):
            return lang
    return None


def _normalize_language_and_stack(
    course: dict[str, Any],
    doc: SourceDocument,
    title: str,
) -> dict[str, Any]:
    """Correct common model mistakes: Mojo labeled python, junk tech_stack, wrong entry."""
    inferred = _infer_source_language(doc, title)
    language = _sanitize(str(course.get("language") or ""), 40).lower() or "python"
    if inferred and inferred != language:
        if inferred in {"mojo", "zig", "rust", "go", "java", "cpp", "ruby"} or language == "python":
            language = inferred
    course["language"] = language
    entry = _sanitize(str(course.get("entry_file") or ""), 200)
    course["entry_file"] = _entry_for_language(language, entry)

    tech = course.get("tech_stack") or []
    tech_stack = [_sanitize(str(t), 60) for t in tech if str(t).strip()][:12] if isinstance(tech, list) else []
    try:
        src_text = gather_source_text(doc)[:12000]
    except Exception:
        src_text = (doc.plain_text or "")[:12000]
    source_blob = " ".join(
        [
            (title or ""),
            (doc.title or ""),
            src_text,
            " ".join(_collect_chapters(doc)[:40]),
        ]
    ).lower()
    junk_unless_grounded = {
        "express", "react", "react-dom", "reactdom", "next.js", "nextjs",
        "django", "flask", "fastapi", "vue", "angular", "svelte",
        "numpy", "np", "pandas", "sklearn", "scikit-learn", "tensorflow",
        "torch", "pytorch", "keras", "jax",
    }
    try:
        full_src = gather_source_text(doc)
    except Exception:
        full_src = doc.plain_text or ""
    full_blob = " ".join([(title or ""), (doc.title or ""), full_src, " ".join(_collect_chapters(doc)[:40])])
    cleaned_stack = []
    for t in tech_stack:
        tl = (t or "").lower().strip()
        if tl in junk_unless_grounded:
            # Same speech-aware rule as local_precheck (whole transcript, code form
            # or >=3 spoken non-negated mentions); the old 12k-char substring scan
            # dropped PyTorch from build-GPT and kept numpy for micrograd.
            canon = {"np": "numpy", "reactdom": "react-dom", "nextjs": "next.js"}.get(tl, tl)
            if not lib_grounded_in_source(canon, full_blob):
                continue
        cleaned_stack.append(t)
    tech_stack = cleaned_stack

    if language == "mojo":
        banned = {
            "numpy", "torch", "pytorch", "tensorflow", "sklearn", "pandas",
            "accelerate", "express", "react",
        }
        tech_stack = [t for t in tech_stack if t.lower() not in banned and "torch" not in t.lower()]
        if not tech_stack or not any("mojo" in t.lower() for t in tech_stack):
            tech_stack = ["Mojo"]
    course["tech_stack"] = tech_stack

    chapters = [c.lower() for c in _collect_chapters(doc)[:30]]
    syllabus_hits = sum(
        1
        for c in chapters
        if re.search(
            r"hello\s*world|variable|datatype|user\s*input|if/?else|loop|function|oop|struct|simd",
            c,
        )
    )
    goal = str(course.get("project_goal") or "").lower()
    if syllabus_hits >= 4 and re.search(r"\bcalculator\b|\btodo\b|\bweather\s*app\b", goal):
        course["project_goal"] = (
            f"Code along with the {language} tutorial: practice each demo "
            f"(setup, syntax, and features from this transcript) in order."
        )
        raw_ms = course.get("milestones") if isinstance(course.get("milestones"), list) else []
        calc_only = sum(
            1 for m in raw_ms if isinstance(m, dict) and re.search(r"calculator", str(m.get("title") or ""), re.I)
        )
        if calc_only >= 3 and chapters:
            rebuilt = []
            for ch in _collect_chapters(doc)[:12]:
                if re.search(r"outro|final comments|ask questions|how to ask", ch, re.I):
                    continue
                token = ch.split()[0][:40] if ch.split() else ("fn" if language == "mojo" else "def")
                rebuilt.append(
                    {
                        "title": ch[:120],
                        "hook": f"Next: {ch[:60]}",
                        "teach": f"In this section you practice “{ch[:80]}” in {language}, following the transcript.",
                        "observation": f"You completed “{ch[:60]}”.",
                        "action": (
                            f"Open `{course['entry_file']}` and write the {language} code shown for “{ch[:50]}”. "
                            f"Include the key token from this section, then save."
                        ),
                        "example": "",
                        "celebrate": "Nice — onto the next section!",
                        "why": "Each section builds the next skill in the source tutorial.",
                        "source_quote": ch[:80],
                        "checks": [
                            {
                                "kind": "code_contains",
                                "target": token,
                                "description": f"Work on {ch[:60]}",
                            }
                        ],
                        "xp_reward": 20,
                    }
                )
            if len(rebuilt) >= 5:
                course["milestones"] = rebuilt
    return course



_WEAK_CHECK_TARGETS = {
    "setup", "basic", "user", "import", "loops", "functions", "variables", "implement",
    "create", "build", "write", "add", "the", "and", "for", "with", "this", "that",
    "from", "your", "step", "work", "next", "code", "mojo", "python", "cli", "package",
    "error", "handling", "basics", "statements", "hello", "world", "full", "course",
    # Trivial language keywords — passing these proves almost nothing.
    "class", "def", "return", "true", "false", "none", "pass", "self", "print",
    "var", "let", "fn", "if", "else", "elif", "while", "try", "except", "raise",
    "new", "const", "null", "void", "int", "str", "bool", "type", "main",
}

# Single common keywords (≤6 chars) that must not be the SOLE code_contains target.
_WEAK_SHORT_KEYWORDS = {
    "class", "def", "import", "return", "true", "false", "none", "pass", "self",
    "print", "var", "let", "fn", "if", "else", "elif", "while", "try", "new",
    "const", "null", "void", "int", "str", "bool", "type", "main", "for", "with",
    "from", "code", "step", "work", "next", "user", "basic", "setup",
}


def is_weak_keyword_check(kind: str, target: str) -> bool:
    """True for hollow code_contains targets (trivial token / denylist / empty)."""
    k = (kind or "").lower().strip()
    if k != "code_contains":
        return False
    # Allow alternates: only judge the first token for keyword-only weakness when alone.
    raw = (target or "").strip()
    if not raw:
        return True
    first = raw.split("|")[0].strip()
    # Multi-token / dotted / attribute / call-ish targets are usually concrete enough.
    if any(ch in first for ch in (".", "(", "=", " ", "_")) and len(first) > 6:
        # Still weak if the whole thing is ONLY a denylist word with punctuation stripped.
        compact = first.lower().rstrip(",:.")
        if compact in _WEAK_CHECK_TARGETS and len(compact) <= 8:
            return True
        return False
    tgt = first.lower().rstrip(",:.")
    if tgt in _WEAK_CHECK_TARGETS:
        return True
    if len(tgt) <= 6 and tgt in _WEAK_SHORT_KEYWORDS:
        return True
    if len(tgt) <= 3 and tgt.isalpha():
        return True
    return False


def _polish_milestone_dict(item: dict[str, Any], *, language: str, entry_file: str) -> dict[str, Any]:
    """Make learner-facing fields concrete when the model is vague but recoverable."""
    if not isinstance(item, dict):
        return item
    action = str(item.get("action") or "").strip()
    example = str(item.get("example") or "").strip()
    title = str(item.get("title") or "").strip()
    teach = str(item.get("teach") or "").strip()

    # Mojo: rewrite accidental Python def examples toward fn when not a comparison step.
    if language == "mojo" and example:
        if re.search(r"\bdef\b", example) and not re.search(r"\bfn\b", example):
            if not re.search(r"(?i)python\s*vs|vs\s*mojo|compar", title):
                example = re.sub(r"\bdef\b", "fn", example)
        item["example"] = example.strip()

    # Strengthen hollow checks using example/action tokens BEFORE rewriting action.
    checks = item.get("checks") if isinstance(item.get("checks"), list) else []
    improved = []
    for c in checks[:3]:
        if not isinstance(c, dict):
            continue
        kind = str(c.get("kind") or "code_contains").lower()
        target = str(c.get("target") or "").strip()
        tgt_l = target.lower().rstrip(",:.")
        title_word = (
            target[:1].isupper()
            and " " not in target
            and len(target) <= 16
            and tgt_l in title.lower()
        )
        weak = is_weak_keyword_check(kind, target) or title_word or target.endswith(":")
        if kind == "code_contains" and weak:
            src = f"{example} {action}"
            token = ""
            m2 = re.search(
                r"\b(__init__|backward|_backward|Value|tanh|SIMD|Neuron|Layer|MLP|Embedding|attention|parameters|grad|loss)\b",
                src,
            )
            if m2:
                token = m2.group(1)
            if not token:
                # Prefer tokens inside backticks or code-looking fragments in example.
                m = re.search(r"`([^`]+)`", src)
                if m:
                    frag = m.group(1)
                    m3 = re.search(r"\b([A-Za-z_][A-Za-z0-9_]{1,})\b", frag)
                    token = (m3.group(1) if m3 else frag.split("(")[0].strip())[:40]
            if not token and example:
                m3 = re.search(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\b", example)
                token = m3.group(1) if m3 else ""
            if token.endswith((".mojo", ".py", ".js", ".ts", ".rs")) or "/" in token:
                token = ""
            if token and not is_weak_keyword_check("code_contains", token):
                c = {**c, "target": token, "kind": "code_contains"}
            elif re.search(r"(?i)\b(cli|build|run|package|verify|smoke|final)\b", title):
                c = {
                    "kind": "run_ok",
                    "target": "",
                    "description": "Project runs without errors.",
                }
        improved.append(c)
    if improved:
        item["checks"] = improved

    # Always name the entry file so beginners know where to type.
    if entry_file and entry_file not in action:
        if action:
            rest = action[0].lower() + action[1:] if action and action[0].isupper() else action
            # Avoid "In `main.mojo`, in `main.mojo`..."
            if not re.match(r"(?i)in\s+`", rest):
                action = f"In `{entry_file}`, {rest}"
        else:
            action = f"In `{entry_file}`, implement: {title}"
        item["action"] = action

    # Do NOT paper over an empty teach/why with canned copy here: the canned text read
    # as a source reference to the reviewer and was re-injected every revise round, so
    # the loop could never PASS. Leave it empty so local precheck names the defect and
    # the model writes real copy.
    if not str(item.get("hook") or "").strip() and title:
        item["hook"] = title[:80]
    # CLI / run / package milestones: prefer runnable checks over hollow title tokens.
    if re.search(r"(?i)\b(cli|build|run|package|verify|smoke)\b", title):
        checks = item.get("checks") if isinstance(item.get("checks"), list) else []
        if not checks or all(
            is_weak_keyword_check(str(c.get("kind") or "code_contains"), str(c.get("target") or ""))
            for c in checks if isinstance(c, dict)
        ):
            item["checks"] = [
                {
                    "kind": "file_exists",
                    "target": entry_file,
                    "description": f"`{entry_file}` exists for this build step.",
                },
                {
                    "kind": "run_ok",
                    "target": "",
                    "description": "Project runs without errors.",
                },
            ]
    return item



def _default_milestone_hint(checks: list[VerificationCheck]) -> str:
    """Concrete nudge when the model omits hint — never 'follow the source'."""
    if checks:
        c = checks[0]
        kind = (c.kind or "").lower()
        target = (c.target or "").split("|")[0].strip()
        if kind == "import" and target:
            return f"Add `import {target}` (or `from {target} import ...`) near the top of the file."
        if kind == "symbol" and target:
            return f"Define `{target}` at the top level — keep the name exact."
        if kind == "function_call" and target:
            return f"Call `{target}(...)` somewhere so this step actually runs."
        if kind == "code_contains" and target and not is_weak_keyword_check(kind, target):
            return f"Include `{target}` in your implementation for this section."
        if kind == "file_exists":
            return "Create the named file in the workspace, then click NEXT."
        if kind == "run_ok":
            return "Run the entry file and fix errors until it finishes cleanly."
        if kind == "stdout_contains":
            return "Use `print(...)` so you can see a result in the terminal."
    return "Type the code for this section in the entry file, then click NEXT."


def course_dict_to_project(
    course: dict[str, Any],
    *,
    doc: SourceDocument,
    title: str,
    course_id: str,
) -> ProjectCourse:
    language = _sanitize(str(course.get("language") or "python"), 40) or "python"
    entry_file = _entry_for_language(language, str(course.get("entry_file") or ""))
    project_title = _sanitize(str(course.get("title") or title or doc.title or "Guided Project"), 200)
    goal = _sanitize(str(course.get("project_goal") or ""), 2000)
    intro = _sanitize(str(course.get("course_intro") or ""), 2000)
    tech = course.get("tech_stack") or []
    tech_stack = [_sanitize(str(t), 60) for t in tech if str(t).strip()][:12] if isinstance(tech, list) else []

    raw_ms = course.get("milestones") or []
    if not isinstance(raw_ms, list) or len(raw_ms) < 3:
        raise ProjectGroundingError(
            "The AI did not return enough milestones for a guided course. "
            "Try a hands-on coding tutorial with clearer implementation steps."
        )

    milestones: list[Milestone] = []
    for i, item in enumerate(raw_ms[:14], start=1):
        if not isinstance(item, dict):
            continue
        item = _polish_milestone_dict(item, language=language, entry_file=entry_file)
        m_title = _sanitize(str(item.get("title") or f"Step {i}"), 160)
        # Skip hollow overview slides that just repeat the course title.
        if i == 1 and project_title and m_title.lower().startswith(project_title.lower()[:18]):
            if not re.search(r"(?i)hello|setup|install|create|value|import", m_title):
                continue
        if not m_title:
            continue
        checks = _normalize_checks(item.get("checks"))
        coding_kinds = {"import", "symbol", "function_call", "code_contains"}
        if not any(c.kind in coding_kinds for c in checks):
            # Prefer a grounded code_contains token from the title/action.
            # Take the token from the model's own code (example first, then action) —
            # a capitalised title word ("Train") is a hollow keyword check.
            code_src = f"{item.get('example') or ''} {item.get('action') or ''}".replace("`", " ")
            token_m = (
                re.search(r"\b([A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]{2,})\b", code_src)
                or re.search(r"\b([A-Za-z_][A-Za-z0-9_]{3,})\(", code_src)
                or re.search(r"\b(?:def|class|fn|struct)\s+([A-Za-z_][A-Za-z0-9_]{2,})", code_src)
            )
            token = (token_m.group(1) if token_m else "")[:40]
            if token and token.lower() in m_title.lower().split():
                token = ""
            if is_weak_keyword_check("code_contains", token) or token.lower() in {"the", "and", "for", "with", "this", "that", "from", "your", "step"}:
                token = "fn" if language == "mojo" else ""
            if token and not is_weak_keyword_check("code_contains", token):
                checks = [
                    VerificationCheck(
                        kind="code_contains",
                        target=token,
                        description=f"Implement the work for: {m_title}",
                    )
                ] + checks
            elif language == "mojo" and token == "fn":
                # Mojo courses may legitimately check for fn when teaching functions.
                checks = [
                    VerificationCheck(
                        kind="code_contains",
                        target="fn ",
                        description=f"Implement the work for: {m_title}",
                    )
                ] + checks
        if not checks:
            if i == 1:
                checks = [
                    VerificationCheck(
                        kind="file_exists",
                        target=entry_file,
                        description=f"`{entry_file}` exists in your workspace.",
                    )
                ]
            else:
                # Prefer a distinctive title token; never fall back to bare "def"/"class".
                title_tok = re.sub(r"[^A-Za-z0-9_]+", "", (m_title or "").split()[-1] if (m_title or "").split() else "")[:40]
                if title_tok and not is_weak_keyword_check("code_contains", title_tok) and len(title_tok) >= 4:
                    checks = [
                        VerificationCheck(
                            kind="code_contains",
                            target=title_tok,
                            description=f"Implement the work for: {m_title}",
                        )
                    ]
                else:
                    checks = [
                        VerificationCheck(
                            kind="run_ok",
                            target="",
                            description=f"Run after implementing: {m_title}",
                        )
                    ]
        milestones.append(
            Milestone(
                id=f"m{i}",
                order=i,
                title=m_title,
                source_grounded_description=_sanitize(
                    str(item.get("teach") or item.get("observation") or m_title), 2000
                ),
                source_quote=_sanitize(str(item.get("source_quote") or ""), 2000),
                microstep=Microstep(
                    observation=_sanitize(str(item.get("observation") or m_title), 400),
                    # Models often double-escape newlines in numbered steps; the learner UI
                    # renders .pw-action with white-space: pre-line, so use real newlines.
                    action=_sanitize_code(str(item.get("action") or f"Implement: {m_title}"), 1000),
                    hint=_sanitize(str(item.get("hint") or "").strip(), 400),
                ),
                why=_sanitize(str(item.get("why") or ""), 2000),
                hook=_sanitize(str(item.get("hook") or m_title), 200),
                teach=_sanitize(str(item.get("teach") or ""), 1200),
                example=_sanitize_code(str(item.get("example") or ""), 1200),
                celebrate=_sanitize(str(item.get("celebrate") or "Nice work — keep going!"), 200),
                checks=checks,
                xp_reward=max(10, min(200, int(item.get("xp_reward") or 20))),
            )
        )

    if len(milestones) < 3:
        raise ProjectGroundingError(
            "The AI course had too few usable milestones. "
            "Try a build-along tutorial that actually implements a program."
        )

    text = gather_source_text(doc)
    now = time.time()
    starter = (
        f"# {project_title}\n"
        f"# Goal: {goal[:120]}\n"
        f"# Build this project step by step. Click NEXT when you finish a milestone.\n\n"
    )
    return ProjectCourse(
        course_id=course_id,
        title=project_title,
        language=language,
        source_type=doc.source_type,
        source_url=doc.source_url,
        source_hash=doc.source_hash,
        source_summary=text[:4000],
        source_excerpt=text[:20_000],
        project_goal=goal or f"Build along with: {project_title}",
        course_intro=intro,
        tech_stack=tech_stack,
        entry_file=entry_file,
        milestones=milestones,
        workspace_files=[WorkspaceFile(path=entry_file, content=starter)],
        created_at=now,
        updated_at=now,
    )


def _discard_error(reason: str) -> SourceQualityError:
    msg = _sanitize(reason, 400) or (
        "This source does not have enough hands-on coding material to build a good course. "
        "Try a build-along tutorial that actually implements a program."
    )
    decision = SourceQualityDecision(
        decision="reject",
        quality_score=0.15,
        source_type="ai_discard",
        rejection_reasons=[msg],
        confidence="high",
        user_message=msg,
        next_step="Try a hands-on coding tutorial that builds a specific application or system.",
        stage="ai_create",
    )
    return SourceQualityError.from_decision(decision)




def _transcript_blob(doc: SourceDocument) -> str:
    chapters = " ".join(_collect_chapters(doc))
    return f"{gather_source_text(doc)}\n{chapters}".lower()


def _grounding_hits(project: ProjectCourse, doc: SourceDocument, *, strict_quotes: bool = False) -> int:
    """How many milestones are grounded in the source.

    strict_quotes=True (explainers): only count real source_quote substring matches.
    Otherwise also accept titles whose distinctive tokens appear in the transcript.
    """
    blob = _transcript_blob(doc)
    hits = 0
    stop = {
        "setup", "implement", "create", "define", "build", "with", "from", "that", "this",
        "loop", "function", "class", "network", "neural", "model", "layer", "data",
        "train", "training", "simple", "basic", "intro", "introduction", "example",
    }
    for m in project.milestones:
        quote = (m.source_quote or "").strip().lower()
        if len(quote) >= 16 and quote[:100] in blob:
            hits += 1
            continue
        if strict_quotes:
            continue
        words = [w for w in re.findall(r"[a-zA-Z]{4,}", m.title.lower()) if w not in stop]
        # Require a rarer token (len>=6) present in source to avoid conceptual vocabulary matches.
        rare = [w for w in words if len(w) >= 6]
        if rare and sum(1 for w in rare[:3] if w in blob) >= 1:
            hits += 1
    return hits


def _looks_like_explainer(doc: SourceDocument, title: str) -> bool:
    heading = f"{title} {doc.title}".lower()
    chapters = " ".join(_collect_chapters(doc)).lower()
    if re.search(
        r"\bbut what is\b|\bexplained visually\b|\bthe intuition\b|\b1hr talk\b|\btedx\b|"
        r"\bhow to learn anything\b|\bmotivational\b|\bfireside\b|\bkeynote\b",
        heading,
    ):
        return True
    conceptual = 0
    for ch in _collect_chapters(doc)[:20]:
        if re.search(r"^(what|why|how .+ relates|introducing|intuition|notation)\b", ch.strip(), re.I):
            conceptual += 1
    return conceptual >= 3 and not re.search(
        r"\b(implement|coding|from scratch|def |import |train(?:ing)? loop)\b",
        chapters,
        re.I,
    )



_REVIEW_MAX_TOKENS = 1800
_DEFAULT_QUALITY_MAX_TRIES = 8

# Shared with project_copy / scrub / enrich — do not diverge.
from .project_copy import BANNED_VIDEO_PHRASES as _BANNED_VIDEO_PHRASES  # noqa: E402

_REVIEW_SYSTEM = """You are Patchwork Create Course Quality Reviewer.

You receive the FULL generated guided-course JSON plus a short transcript/chapter
summary. The learner NEVER watched the video — transcript-only teaching.

Return STRICT JSON only:
{"verdict":"PASS","reason":"one short sentence"}
OR
{"verdict":"FAIL","reason":"one short sentence","defects":["concrete defect 1","..."]}

FAIL when ANY of these are true:
- Guidance vague / essay-like / not actionable typing steps that stand alone without YouTube
- Banned video/source refs: "as in the video", "follow the instructor", "as shown",
  "from the video", "watch the video", "like the tutorial", "as demonstrated",
  "refer to the video", "follow the source", "follow the transcript",
  "as in the source", "according to the video/source/transcript"
- Hints that say follow the source/transcript/video instead of a real coding nudge
- Weak/keyword-only checks: majority (or all) code_contains targets that are a single
  common keyword ≤6 chars or denylist tokens (class, def, import, return, True, print alone)
- Checks that do not verify a real learning outcome / distinctive code artifact
- Wrong language/stack vs transcript (e.g. Mojo labeled python; invented libs like
  numpy/react/express/torch when NOT named in the transcript). Use the "Library
  evidence" line as ground truth for which libraries the FULL transcript uses — the
  sample you see is short; never claim a library is absent/present against it
- Empty or missing why / action / teach on milestones; why that does not teach the concept
- Invented app not grounded in transcript/chapters
- Too few milestones (<5) or checks that do not verify real code artifacts
  (Do NOT fail a course for not covering every chapter: 5–12 milestones that follow
  the main build arc of a long video is the intended size. If there are MORE than 12,
  the fix is to MERGE steps — never ask for additional milestones in the same review.)
- Examples use wrong language syntax (Mojo with def instead of fn, etc.)

NOT defects: "source_quote" is internal grounding metadata (chapter/transcript phrase),
not learner copy; naming a topic that is also a chapter title (e.g. "positional
encoding", "multi-head attention") in teach is NOT a video reference. Also NOT defects:
first-person plural narration ("We build...", "We fetch...") without naming a video/
instructor; a hint that pairs a concrete nudge with one clause of concept reminder;
a dataset/file URL used in code; distinctive API calls with arguments or dotted names
(e.g. "torch.zeros((1, 1)", "nn.Embedding(", "self.data = float(data)") as
code_contains targets — only bare single keywords are weak checks.

PASS only for top-class, transcript-grounded, beginner-safe courses that a learner can
complete WITHOUT opening the video, with non-keyword progress checks.
Be strict. Prefer FAIL with concrete, fixable defects over a soft PASS.
Do not invent secrets. Do not include API keys or credentials in the response.
"""

_REVISE_SYSTEM = """You are Patchwork Create Course reviser.

You previously authored a guided coding course. A quality review FAILED with concrete
defects. Revise the course JSON to fix EVERY defect. Prefer revise-in-place over
throwing away structure unless the course is fatally ungounded — then return discard.

Learner NEVER watched the video. Ban video/source/transcript-reference phrases
("follow the source", "as in the video", etc.). Every action/hint must stand alone
with concrete do-this steps and a real nudge — never "follow the source".
Why/teach must teach the concept. Checks must verify real learning outcomes — forbid
keyword-only targets (class/def/import/return/True alone). Do NOT invent libs
(numpy/react/express/torch) unless named in the transcript.
Keep language/entry_file/tech_stack aligned with the transcript. The "Library evidence"
line is a deterministic scan of the FULL transcript — trust it over the short sample.
Stack/library, check, copy and structure defects are ALWAYS fixable in place: never
return discard for them. Discard only when the source has no step-by-step code
implementation at all (talk, lecture, motivational video).
Examples must be short VALID code ("\n" between lines, never ';'-joined blocks). Include 5–12 solid milestones.

Return STRICT JSON only:
{"decision":"discard","reason":"..."}
OR
{"decision":"create","course":{ ... same schema as Create Course ... }}
"""


def _tolerate_reviser_discard(exc: Exception, already: int) -> bool:
    """CREATE already accepted the source; a single reviser discard is usually a
    hallucination about a fixable defect (e.g. stack). Keep the draft once."""
    return bool(getattr(exc, "from_reviser", False)) and already < 1


_DEFAULT_CREATE_MAX_SECONDS = 2400


def create_max_seconds() -> int:
    raw = os.getenv("CREATE_COURSE_MAX_SECONDS", "").strip()
    try:
        n = int(raw) if raw else _DEFAULT_CREATE_MAX_SECONDS
    except ValueError:
        n = _DEFAULT_CREATE_MAX_SECONDS
    return max(60, min(n, 7200))


def quality_max_tries() -> int:
    raw = os.getenv("CREATE_COURSE_QUALITY_MAX_TRIES", "").strip()
    if not raw:
        return _DEFAULT_QUALITY_MAX_TRIES
    try:
        n = int(raw)
    except ValueError:
        return _DEFAULT_QUALITY_MAX_TRIES
    return max(1, min(n, 30))


def project_to_course_dict(project: ProjectCourse) -> dict[str, Any]:
    """Serialize a ProjectCourse into create/review course JSON (no workspace/progress)."""
    milestones: list[dict[str, Any]] = []
    for m in project.milestones:
        milestones.append(
            {
                "title": m.title,
                "hook": m.hook or "",
                "teach": m.teach or m.source_grounded_description or "",
                "observation": (m.microstep.observation if m.microstep else "") or "",
                "action": (m.microstep.action if m.microstep else "") or "",
                "example": m.example or "",
                "celebrate": m.celebrate or "",
                "why": m.why or "",
                "source_quote": m.source_quote or "",
                "hint": (m.microstep.hint if m.microstep else "") or "",
                "checks": [
                    {"kind": c.kind, "target": c.target, "description": c.description}
                    for c in (m.checks or [])
                ],
                "xp_reward": m.xp_reward,
            }
        )
    return {
        "title": project.title,
        "language": project.language,
        "entry_file": project.entry_file,
        "project_goal": project.project_goal,
        "course_intro": project.course_intro,
        "tech_stack": list(project.tech_stack or []),
        "milestones": milestones,
    }

def local_precheck_course(
    project: ProjectCourse,
    doc: SourceDocument | None = None,
) -> list[str]:
    """Cheap local defects before spending a model review call.

    Model review remains authoritative for ship/no-ship; local findings only
    force an early revise when present.
    """
    from .project_copy import is_follow_source_template  # local import avoids cycles

    defects: list[str] = []
    blob_parts: list[str] = [
        project.title or "",
        project.project_goal or "",
        project.course_intro or "",
        " ".join(project.tech_stack or []),
    ]
    _file_like = re.compile(r"^[\w./-]+\.(py|mojo|🔥|js|jsx|ts|tsx|rs|go|java|cpp|cc|c|h|rb|toml|json|txt)$", re.I)
    for m in project.milestones:
        for c in m.checks or []:
            if c.kind == "code_contains" and _file_like.match((c.target or "").strip()):
                defects.append(
                    f"{m.id}: code_contains target `{c.target}` is a file name, not code — "
                    "use a file_exists check or a distinctive code token instead."
                )
    if len(project.milestones) > 12:
        defects.append(
            f"Too many milestones ({len(project.milestones)}): MERGE adjacent small steps into at most 12 "
            "(e.g. combine setup/hello-world, or related syntax topics). Keep core build topics; do not add more."
        )
    follow_source_hits = 0
    for m in project.milestones:
        hint = (m.microstep.hint if m.microstep else "") or ""
        action = (m.microstep.action if m.microstep else "") or ""
        obs = (m.microstep.observation if m.microstep else "") or ""
        blob_parts.extend(
            [
                m.title or "",
                m.hook or "",
                m.teach or "",
                m.example or "",
                m.celebrate or "",
                m.why or "",
                m.source_quote or "",
                m.source_grounded_description or "",
                obs,
                action,
                hint,
            ]
        )
        if is_follow_source_template(hint) or is_follow_source_template(action):
            follow_source_hits += 1
        for c in m.checks or []:
            blob_parts.append(f"{c.kind} {c.target} {c.description}")
    blob = "\n".join(blob_parts).lower()
    for phrase in _BANNED_VIDEO_PHRASES:
        if phrase in blob:
            defects.append(f"Banned learner-facing phrase present: '{phrase}'")
            break

    if follow_source_hits:
        defects.append(
            f"{follow_source_hits} milestone(s) use follow-the-source/transcript template "
            f"hints or actions; give concrete coding nudges instead."
        )

    if len(project.milestones) < 5:
        defects.append(f"Too few milestones ({len(project.milestones)}); need at least 5.")

    empty_action = [
        m.title for m in project.milestones
        if not ((m.microstep.action if m.microstep else "") or "").strip()
    ]
    if empty_action:
        defects.append(
            "Empty action on milestone(s): " + ", ".join(empty_action[:5])
        )

    empty_why = [m.title for m in project.milestones if not (m.why or "").strip()]
    if empty_why:
        defects.append("Empty why on milestone(s): " + ", ".join(empty_why[:5]))

    empty_hint = [
        m.title for m in project.milestones
        if not ((m.microstep.hint if m.microstep else "") or "").strip()
    ]
    if empty_hint:
        defects.append(
            "Missing hint on milestone(s): " + ", ".join(empty_hint[:5])
            + " — add a real nudge (what to type / a common mistake)."
        )

    empty_teach = [m.title for m in project.milestones if not (m.teach or "").strip()]
    if empty_teach:
        defects.append(
            "Empty teach on milestone(s): " + ", ".join(empty_teach[:5])
            + " — write 1-3 sentences explaining the concept in your own words."
        )

    weak = 0
    coding_checks = 0
    for m in project.milestones:
        for c in m.checks or []:
            kind = (c.kind or "").lower()
            if kind in {"import", "symbol", "function_call", "code_contains"}:
                coding_checks += 1
            if is_weak_keyword_check(kind, c.target or ""):
                weak += 1
    majority_weak = coding_checks > 0 and weak >= max(3, (coding_checks + 1) // 2)
    all_weak = coding_checks >= 3 and weak >= coding_checks
    if weak >= 3 or majority_weak or all_weak:
        defects.append(
            f"{weak}/{coding_checks or weak} weak/keyword-only code_contains checks; "
            f"verify real learning-outcome tokens (not class/def/import alone)."
        )

    # Ungrounded libs: tech_stack or early milestone copy invents libs absent from source.
    # Mere mention ("no numpy") is NOT grounding — require import/from/usage-like evidence.
    inventable = {
        "numpy", "pandas", "sklearn", "scikit-learn", "tensorflow", "torch", "pytorch",
        "keras", "jax", "express", "react", "react-dom", "next.js", "django", "flask",
        "fastapi", "vue", "angular", "svelte",
    }

    def _lib_grounded(lib: str, src: str) -> bool:
        return lib_grounded_in_source(lib, src)

    source_blob = ""
    if doc is not None:
        try:
            source_blob = (
                f"{project.title or ''} {doc.title or ''} {gather_source_text(doc)} "
                f"{' '.join(_collect_chapters(doc)[:40])}"
            )
        except Exception:
            source_blob = f"{project.title or ''} {getattr(doc, 'plain_text', '') or ''}"
    if source_blob:
        ungrounded: list[str] = []
        for t in project.tech_stack or []:
            tl = (t or "").lower().strip()
            if tl in inventable and not _lib_grounded(tl, source_blob):
                ungrounded.append(t)
        for m in project.milestones[:3]:
            fields = " ".join(
                [
                    m.teach or "",
                    m.example or "",
                    (m.microstep.action if m.microstep else "") or "",
                    " ".join(f"{c.kind} {c.target}" for c in (m.checks or [])),
                ]
            ).lower()
            for lib in inventable:
                if re.search(rf"\b{re.escape(lib)}\b", fields) and not _lib_grounded(lib, source_blob):
                    ungrounded.append(lib)
        if ungrounded:
            uniq = sorted(set(ungrounded))[:8]
            defects.append(
                "Ungrounded library/tech invented (not in transcript): " + ", ".join(uniq)
                + " — remove it or switch to the stack the transcript actually uses "
                "(see Library evidence). This is fixable; do not discard."
            )

    return defects


def _short_transcript_summary(doc: SourceDocument, title: str, *, limit: int = 2500) -> str:
    heading = (title or doc.title or "").strip()
    chapters = _collect_chapters(doc)
    parts = [f"Title: {heading}", f"Source URL: {doc.source_url or '(none)'}"]
    if chapters:
        outline = "\n".join(f"  {i}. {c}" for i, c in enumerate(chapters[:40], start=1))
        parts.append(f"Chapters:\n{outline}")
    evidence = library_evidence_line(doc)
    if evidence:
        parts.append(evidence)
    sampled = _sample_transcript(gather_source_text(doc), budget=limit)
    if sampled:
        parts.append(f"Transcript summary/sample:\n{sampled}")
    return "\n\n".join(parts)[: limit + 2500]


def _parse_review_payload(raw: str) -> dict[str, Any]:
    data = _parse_json_object(raw)
    verdict = str(data.get("verdict") or data.get("decision") or "").strip().upper()
    if verdict in {"ACCEPT", "OK", "CREATE"}:
        verdict = "PASS"
    if verdict in {"REJECT", "DISCARD", "INSUFFICIENT"}:
        verdict = "FAIL"
    if verdict not in {"PASS", "FAIL"}:
        # Heuristic: presence of defects => FAIL
        if isinstance(data.get("defects"), list) and data["defects"]:
            verdict = "FAIL"
        elif re.search(r'"verdict"\s*:\s*"PASS"', raw or "", re.I):
            verdict = "PASS"
        elif re.search(r'"verdict"\s*:\s*"FAIL"', raw or "", re.I):
            verdict = "FAIL"
        else:
            verdict = "FAIL"
    reason = _sanitize(str(data.get("reason") or ""), 400)
    defects_raw = data.get("defects") if isinstance(data.get("defects"), list) else []
    defects = [_sanitize(str(d), 300) for d in defects_raw if str(d).strip()][:20]
    if verdict == "FAIL" and not defects and reason:
        defects = [reason]
    return {"verdict": verdict, "reason": reason or verdict, "defects": defects}


async def review_course_with_ai(
    provider,
    project: ProjectCourse,
    doc: SourceDocument,
    *,
    title: str,
    local_hints: list[str] | None = None,
) -> dict[str, Any]:
    """Model review of the full course. Authoritative for ship/no-ship."""
    course_json = json.dumps(project_to_course_dict(project), ensure_ascii=False)
    summary = _short_transcript_summary(doc, title)
    hints = ""
    if local_hints:
        hints = "\n\nLocal precheck hints (advisory):\n- " + "\n- ".join(local_hints[:12])
    user = (
        f"{summary}\n\nFULL COURSE JSON TO REVIEW:\n{course_json}"
        f"{hints}\n\nReturn PASS or FAIL JSON only."
    )
    raw = await provider.generate_structured(_REVIEW_SYSTEM, user, max_tokens=_REVIEW_MAX_TOKENS)
    _debug_dump("review", raw)
    return _parse_review_payload(raw)


async def revise_course_with_ai(
    provider,
    project: ProjectCourse,
    doc: SourceDocument,
    *,
    title: str,
    course_id: str,
    defects: list[str],
) -> ProjectCourse:
    """Ask the model to revise the course using concrete defect feedback."""
    course_json = json.dumps(project_to_course_dict(project), ensure_ascii=False)
    summary = _short_transcript_summary(doc, title)
    defect_block = "\n".join(f"- {d}" for d in (defects or ["Quality not strong enough"])[:20])
    user = (
        f"{summary}\n\nCURRENT COURSE JSON:\n{course_json}\n\n"
        f"QUALITY DEFECTS TO FIX:\n{defect_block}\n\n"
        "Return revised create JSON (or discard if fatally ungounded)."
    )
    raw = await provider.generate_structured(_REVISE_SYSTEM, user, max_tokens=_CREATE_MAX_TOKENS)
    _debug_dump("revise", raw)
    data = _parse_json_object(raw)
    decision = str(data.get("decision") or "").strip().lower()
    if decision in {"discard", "reject", "insufficient"}:
        err = _discard_error(str(data.get("reason") or "Revised course discarded after quality review."))
        err.from_reviser = True  # type: ignore[attr-defined]
        raise err
    course = data.get("course")
    if not isinstance(course, dict):
        if isinstance(data.get("milestones"), list):
            course = data
        else:
            raise ProjectGroundingError(
                "The AI reviser returned an incomplete course. Try again with a clearer coding tutorial."
            )
    course = _normalize_language_and_stack(course, doc, title)
    return course_dict_to_project(course, doc=doc, title=title, course_id=course_id)


async def _create_course_draft(
    provider,
    doc: SourceDocument,
    *,
    title: str,
    course_id: str,
) -> ProjectCourse:
    """Initial CREATE JSON → ProjectCourse (with light structural retries)."""
    user = build_create_user_prompt(doc, title)
    last_err: Exception | None = None
    raw = ""
    for attempt in range(3):
        try:
            prompt = user
            if attempt > 0:
                prompt = (
                    user
                    + "\n\nRETRY: Previous JSON was invalid/incomplete or not grounded. "
                    "Return compact STRICT JSON. Prefer discard over inventing a project. "
                    "Keep examples short, valid code. Include 6-8 milestones with code_contains/import/symbol checks. Name the entry_file in every action."
                )
            raw = await provider.generate_structured(_SYSTEM, prompt, max_tokens=_CREATE_MAX_TOKENS)
            _debug_dump("create", raw)
        except Exception as exc:  # noqa: BLE001
            logger.exception("AI course generation failed")
            detail = getattr(exc, "message", None) or str(exc)
            raise ProjectGroundingError(
                f"The AI provider could not generate a course from this source: {detail}. "
                "Check your OpenRouter model name and API key in Settings, then retry."
            ) from exc

        data = _parse_json_object(raw)
        decision = str(data.get("decision") or "").strip().lower()
        if not decision:
            if re.search(r'"decision"\s*:\s*"create"', raw or "", re.I) or (
                isinstance(data.get("course"), dict) and data["course"].get("milestones")
            ):
                decision = "create"
            elif re.search(r'"decision"\s*:\s*"(discard|reject|insufficient)"', raw or "", re.I):
                decision = "discard"

        if decision in {"discard", "reject", "insufficient"}:
            raise _discard_error(str(data.get("reason") or ""))

        if decision != "create":
            if isinstance(data.get("course"), dict) or isinstance(data.get("milestones"), list):
                decision = "create"
            else:
                last_err = _discard_error(
                    str(data.get("reason") or "Could not decide whether this source supports a coding course.")
                )
                continue

        course = data.get("course")
        if not isinstance(course, dict):
            if isinstance(data.get("milestones"), list):
                course = data
            else:
                last_err = ProjectGroundingError(
                    "The AI returned an incomplete course. Try again or pick a clearer coding tutorial."
                )
                continue

        try:
            course = _normalize_language_and_stack(course, doc, title)
            project = course_dict_to_project(course, doc=doc, title=title, course_id=course_id)
        except Exception as exc:  # noqa: BLE001
            last_err = exc if isinstance(exc, Exception) else ProjectGroundingError(str(exc))
            continue

        coding = [
            m for m in project.milestones
            if m.checks and m.checks[0].kind in ("import", "symbol", "function_call", "code_contains")
        ]
        if len(coding) < 2 or len(project.milestones) < 3:
            last_err = ProjectGroundingError(
                "The AI course had too little implementable structure. Retrying or discard."
            )
            continue
        if len(project.milestones) < 5 and attempt == 0:
            last_err = ProjectGroundingError(
                "AI returned too few milestones for a full guided build; retrying once."
            )
            continue
        if _looks_like_explainer(doc, title):
            raise _discard_error(
                "This source explains concepts but does not walk through implementing a program. "
                "Try a build-along coding tutorial instead."
            )
        if _grounding_hits(project, doc) < 1 and attempt == 0:
            last_err = ProjectGroundingError(
                "AI milestones were not grounded in the transcript; retrying once."
            )
            continue
        return project

    if isinstance(last_err, SourceQualityError):
        raise last_err
    if last_err is not None:
        raise last_err
    raise ProjectGroundingError(
        "The AI returned an incomplete course. Try again or pick a clearer coding tutorial."
    )


async def generate_course_with_ai(
    provider,
    doc: SourceDocument,
    *,
    title: str,
    course_id: str,
) -> ProjectCourse:
    """Ask the configured provider to discard or create a ProjectCourse.

    Flow: CREATE → optional local precheck → model self-review → revise on FAIL,
    looping until PASS or CREATE_COURSE_QUALITY_MAX_TRIES. The course is only
    returned (for store.create at the call site) after a model PASS.
    """
    if provider is None:
        raise ProjectGroundingError(
            "No AI provider is configured for Create Course. "
            "Set AI_PROVIDER=openrouter (or another provider) and its API key in Settings."
        )

    project = await _create_course_draft(provider, doc, title=title, course_id=course_id)
    max_tries = quality_max_tries()
    last_fail_reason = "Quality review did not pass."
    reviser_discards = 0
    deadline = time.monotonic() + create_max_seconds()

    for attempt in range(1, max_tries + 1):
        if time.monotonic() > deadline:
            last_fail_reason = (
                f"Create exceeded CREATE_COURSE_MAX_SECONDS={create_max_seconds()}s; "
                f"last reason: {last_fail_reason}"
            )
            break
        local_defects = local_precheck_course(project, doc)
        if local_defects:
            logger.info(
                "quality_precheck attempt=%s fail defects=%s",
                attempt,
                "; ".join(local_defects[:8]),
            )
            last_fail_reason = local_defects[0]
            if attempt >= max_tries:
                break
            try:
                project = await revise_course_with_ai(
                    provider,
                    project,
                    doc,
                    title=title,
                    course_id=course_id,
                    defects=local_defects,
                )
            except SourceQualityError as exc:
                if not _tolerate_reviser_discard(exc, reviser_discards):
                    raise
                reviser_discards += 1
                last_fail_reason = f"Reviser discarded an already-created course: {exc}"
                logger.warning("reviser discard tolerated once (create stage accepted source): %s", exc)
            except Exception as exc:  # noqa: BLE001
                logger.exception("AI course revise after local precheck failed")
                last_fail_reason = str(exc)
            continue

        try:
            review = await review_course_with_ai(
                provider, project, doc, title=title, local_hints=None
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("AI course quality review failed")
            last_fail_reason = f"Review call failed: {exc}"
            if attempt >= max_tries:
                break
            continue

        verdict = review.get("verdict") or "FAIL"
        reason = review.get("reason") or verdict
        defects = review.get("defects") or []
        logger.info(
            "quality_review attempt=%s verdict=%s reason=%s defects=%s",
            attempt,
            verdict,
            reason[:200],
            " | ".join(str(d)[:160] for d in defects[:8]),
        )
        if verdict == "PASS":
            logger.info("quality_review PASS on attempt=%s — shipping course once", attempt)
            return project

        last_fail_reason = reason or (defects[0] if defects else "Quality not strong enough")
        if attempt >= max_tries:
            break
        try:
            project = await revise_course_with_ai(
                provider,
                project,
                doc,
                title=title,
                course_id=course_id,
                defects=defects or [last_fail_reason],
            )
        except SourceQualityError as exc:
            if not _tolerate_reviser_discard(exc, reviser_discards):
                raise
            reviser_discards += 1
            last_fail_reason = f"Reviser discarded an already-created course: {exc}"
            logger.warning("reviser discard tolerated once (create stage accepted source): %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("AI course revise after FAIL review failed")
            last_fail_reason = str(exc)

    raise ProjectGroundingError(
        f"Create Course quality review did not PASS after {max_tries} tries. "
        f"Last reason: {_sanitize(last_fail_reason, 300)}. "
        "Try a clearer build-along tutorial, or raise CREATE_COURSE_QUALITY_MAX_TRIES."
    )
