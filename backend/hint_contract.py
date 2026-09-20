"""The AI-hint quality contract: prompt, repair, leak guard, offline fallback.

A learner in a flow state needs ONE short nudge — not an essay, not the
answer, and never a model error message. Every rule here is pure and
unit-testable so the guarantee holds for *any* provider, including small or
reasoning models that ignore instructions.

Pipeline (see backend/tutor_service.py):

    raw model reply -> repair_hint()  -> ok? -> ship it        (source="ai")
                                       |
                                       no -> one strict retry
                                       no -> offline_hint()    (source="offline")

Learners therefore always receive a usable, short, spoiler-free nudge.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

HINT_CONTRACT_VERSION = "2026-09-18.1"

# Flow-state budget: a hint must be readable in under three seconds.
MAX_HINT_WORDS = 45
MAX_HINT_CHARS = 260
SOFT_CHAR_LIMIT = 200
MIN_HINT_CHARS = 12
# Consecutive reference-solution tokens echoed back = the answer, not a nudge.
LEAK_TOKEN_RUN = 6
# Consecutive task-instruction tokens copied verbatim = a lazy restatement that
# tells the learner nothing they could not already read on the task card.
RESTATEMENT_TOKEN_RUN = 10

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_FENCE = re.compile(r"```.*?```|~~~.*?~~~|<pre>.*?</pre>", re.S | re.I)
_MD_HEADING = re.compile(r"(?m)^\s*#{1,6}\s+")
_MD_BULLET = re.compile(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+")
_MD_EMPH = re.compile(
    r"\*\*(.+?)\*\*|\*([^*\n]+)\*|__(.+?)__|(?<![A-Za-z0-9_])_([^_\n]+)_(?![A-Za-z0-9_])"
)
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_INLINE_CODE = re.compile(r"`([^`\n]*)`")
_CODE_KEYWORDS = re.compile(
    r"(?i)^\s*(?:def|class|for|while|import|from|return|const|let|var|function|public|private|"
    r"protected|struct|enum|template|namespace|new|delete|print|echo|pass|raise|yield|await|"
    r"async|if|elif|else|switch|case|try|except|catch|finally|do|SELECT|INSERT|UPDATE|DELETE|"
    r"FROM|WHERE|GROUP BY|ORDER BY|CREATE|ALTER|DROP)\b"
)
_CODE_MARKERS = re.compile(r"=>|::|<<|->|#include|\{\{|\}\}|self\.|console\.|System\.out|std::|printf\(|cout\s*<<")
_CODE_COMMENT = re.compile(r"^(?://|#(?!#)|/\*|\*/|<!--|\*/)")
_KEY_VALUE = re.compile(r"^[A-Za-z_$][\w.$\[\]']*\s*:\s*\S")
_CODE_EVIDENCE = re.compile(r"[(){}\[\];]|->|=>|\s[-+*/%=<>]\s|[-+*/%]$")
_SYMBOLS = re.compile(r"[{};\[\]()=<>|&%*/\\]")
_THINKING_TRACE = re.compile(
    r"(?i)^(?:let me analyze|i need to (?:provide|act|first|figure)|the user wants me|"
    r"as a (?:patient|coding|helpful)|let.?s break (?:this|it) down|i should (?:start|note|first|answer)|"
    r"here.?s my (?:thinking|plan|approach)|okay,? let|first,? i (?:will|need to)|i will (?:start|first))"
)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_PRAISE = re.compile(
    r"(?i)^(?:great|awesome|amazing|nice|good|well done|excellent|fantastic)\b[,!.]?\s*"
    r"(?:work|job|effort|track)?[,!.]?\s*"
)


def looks_like_code(line: str) -> bool:
    """Is this line code rather than prose?

    Deliberately conservative, and case-insensitive keyword matches need real
    evidence: "Let me analyze the situation." is prose while
    "return price + price * tax" is code.
    """
    text = (line or "").strip()
    if not text:
        return False
    if _CODE_COMMENT.match(text) or _CODE_MARKERS.search(text):
        return True
    evidence = bool(_CODE_EVIDENCE.search(text))
    if _CODE_KEYWORDS.match(text) and (evidence or len(text.split()) <= 4):
        return True
    if text.endswith((".", "!", "?")):
        return False
    if text.endswith(("{", "}", ";", ",", ":")):
        return True
    if _KEY_VALUE.match(text):
        return True
    letters = re.findall(r"[A-Za-z]", text)
    symbols = _SYMBOLS.findall(text)
    return bool(letters) and len(symbols) / max(1, len(text)) > 0.10


# ─── PROMPTS ───────────────────────────────────────────────────────────────────

_LEVEL_TEXT = {
    1: "Level 1 (concept): remind the idea the exercise tests. Do NOT mention their code, "
       "the field names, or any expected value.",
    2: "Level 2 (direction): say which part of their code decides the failing value and what to "
       "notice there. Never name the correct value, literal or field contents.",
    3: "Level 3 (diagnosis): name in words what is wrong or missing in their code. Still never "
       "write the corrected expression.",
    4: "Level 4 (approach): describe the fix as two spoken steps (work the value out, then hand "
       "it back). Words only — the learner types it themselves.",
}

HINT_SYSTEM_PROMPT = (
    "You are Patchwork's coding coach. A learner is mid-exercise and in a flow state. "
    "Your entire job is ONE nudge: short, plain, and never the answer.\n"
    "\n"
    "OUTPUT CONTRACT (obey exactly):\n"
    "- 1-2 sentences, at most 35 words. No exceptions.\n"
    "- Plain prose only: no markdown, no bold, no headings, no bullets, no numbered lists.\n"
    "- Never write code: no code blocks, no code lines, no complete statements, no signature. "
    "You may name at most one identifier (a function or variable name) in backticks.\n"
    "- Never hand over a value, literal, expression or line that makes a test pass. Say where to "
    "look and what to decide, not what to type.\n"
    "- Never copy a phrase from the Instructions block: the learner can already read it. A hint "
    "must add something the instructions do not.\n"
    "- Do not praise, do not teach theory, do not restate the task. No preamble and no thinking "
    "out loud: your first word is already the hint.\n"
    "- End with the single next action, in the imperative.\n"
    "\n"
    "HINT LEVELS (disclosure is capped per level):\n"
    + "\n".join(_LEVEL_TEXT[k] for k in sorted(_LEVEL_TEXT))
    + "\n"
    "GOOD examples (copy the style, never the content):\n"
    '- "Two checks are still red and both look at the label you return. Find the line that '
    'picks that value and ask what it should be reading from."'
    "\n"
    '- "Before typing, say out loud what the failing check expects back. Then change only the '
    'line that produces it."'
    "\n"
    'BAD (never answer like this): a function body, a code block, a numbered plan, the expected '
    'values spelled out, "Let me analyze...", or anything longer than two sentences.\n'
    "\n"
    "Deterministic test results are authoritative and cannot be changed. A hint is never a "
    "pass result."
)


def hint_system_prompt(level: int) -> str:
    """Level-aware contract; level 4 gets one more sentence but stays code-free."""
    if level >= 4:
        return HINT_SYSTEM_PROMPT.replace(
            "- 1-2 sentences, at most 35 words. No exceptions.",
            "- 2-3 sentences, at most 50 words. No exceptions.",
        )
    return HINT_SYSTEM_PROMPT


SOLUTION_SYSTEM_PROMPT = (
    "You are Patchwork's coding coach. The learner explicitly asked for the full solution. "
    "Reply with the complete corrected code in one fenced block, then at most one short "
    "sentence naming the change. Deterministic test results are authoritative."
)


def system_prompt_for(request: Any) -> str:
    if getattr(request, "solution_requested", False):
        return SOLUTION_SYSTEM_PROMPT
    return hint_system_prompt(int(getattr(request, "hint_level", 1) or 1))


# ─── DISCLOSURE GRADIENT ───────────────────────────────────────────────────────

_BRACED = re.compile(r"\{[^{}]*\}")
_CALL_SHAPE = re.compile(r"^([A-Za-z_]\w*)\s*\(.*\)$", re.S)


def _redact_span(match: re.Match[str]) -> str:
    inner = (match.group(1) or "").strip()
    if not inner:
        return ""
    if re.fullmatch(r"[A-Za-z_]\w{0,40}", inner):
        return inner  # a bare name is not a spoiler; it is already on screen
    call = _CALL_SHAPE.match(inner)
    if call:
        return call.group(1)  # keep the function name, drop the argument list
    if re.search(r"[=+\-*/<>!&|,;{}()\[\]]", inner):
        return "the required value"
    return inner


def redact_spec(text: str) -> str:
    """Strip literal answers from task prose for the early hint levels.

    Levels 1-2 must not be able to read the expected values straight off the
    prompt, so the model receives the task in prose without its literals. This
    enforces the disclosure gradient structurally instead of hoping the model
    behaves — the cheapest way to keep a hint a hint.
    """
    out = _BRACED.sub("the required shape", text or "")
    out = _INLINE_CODE.sub(_redact_span, out)
    out = re.sub(r"(?m)\s*[:,]\s*$", ".", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip()


def instructions_for_level(request: Any) -> str:
    """Task text at the disclosure level the learner is entitled to."""
    text = getattr(request, "instructions", "") or ""
    if getattr(request, "solution_requested", False):
        return text
    if int(getattr(request, "hint_level", 1) or 1) <= 2:
        redacted = redact_spec(text)
        return redacted or text
    return text


def strict_retry_request(request: Any) -> Any:
    """Second attempt after a broken contract: impossible-to-miss instructions."""
    note = (
        "CONTRACT VIOLATION on the previous attempt. Answer again with EXACTLY ONE plain "
        "sentence of at most 25 words telling the learner where to look. Zero code, zero "
        "identifiers, no preamble, no thinking out loud."
    )
    existing = (getattr(request, "adaptation_hint", "") or "").strip()
    merged = f"{existing}\n{note}".strip()[:2000]
    return request.model_copy(update={"adaptation_hint": merged})


# ─── REPAIR + LEAK GUARD ───────────────────────────────────────────────────────

def _tokens(text: str) -> list[str]:
    return _IDENT.findall(text or "")


# Stopwords are dropped from overlap runs so the guard measures copied code,
# not shared English ("the value of the" is not a spoiler).
_STOPWORDS = frozenset("""
a an the and or but if then else when while for to of in on at by with from into that this
these those it its is are was were be been being do does did doing have has had not no so as
than too very you your yours they them their we our i me my mine he she his her us let us
can could should would will shall may might must make made get got give take use used using
try to just now here there what which who whom how why again once about above below up down
out over under between both each other same please remember note look check first next
""".split())


def _sig_tokens(text: str) -> list[str]:
    return [t for t in _IDENT.findall(text or "") if t.lower() not in _STOPWORDS and len(t) > 1]


def _longest_common_run(a: list[str], b: list[str]) -> tuple[int, list[str]]:
    """Length and content of the longest token run shared contiguously."""
    if not a or not b:
        return 0, []
    best_len, best_end = 0, 0
    prev = [0] * (len(b) + 1)
    for index, token in enumerate(a, 1):
        cur = [0] * (len(b) + 1)
        for j, other in enumerate(b, 1):
            if token == other:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best_len:
                    best_len, best_end = cur[j], index
        prev = cur
    return best_len, a[best_end - best_len:best_end]


def _contains_sequence(hay: list[str], needle: list[str]) -> bool:
    if not needle:
        return True
    return any(hay[i:i + len(needle)] == needle for i in range(len(hay) - len(needle) + 1))


def token_run(text: str, source: str, ignore: str = "") -> int:
    """Longest run of tokens the reply copies verbatim from `source`.

    Runs that are also present in `ignore` (typically the learner's own
    starter) are not counted: repeating what is already on their screen is
    not a spoiler.
    """
    length, sequence = _longest_common_run(_sig_tokens(text), _sig_tokens(source))
    if not length:
        return 0
    if ignore and _contains_sequence(_sig_tokens(ignore), sequence):
        return 0
    return length


def solution_overlap(text: str, solution: str, starter: str = "") -> int:
    """Consecutive reference-solution tokens echoed back = the answer itself."""
    return token_run(text, solution, starter)


def leak_reasons(
    text: str,
    *,
    solution: str = "",
    starter: str = "",
    instructions: str = "",
) -> list[str]:
    reasons: list[str] = []
    raw = text or ""
    if "```" in raw or "~~~" in raw:
        reasons.append("fenced_code")
    code_lines = [line for line in raw.splitlines() if looks_like_code(line)]
    if code_lines:
        reasons.append(f"code_lines={len(code_lines)}")
    # Overlap is measured on the whole reply: a dumped solution is a spoiler
    # whether or not the code lines would survive stripping.
    whole = re.sub(r"\s+", " ", _INLINE_CODE.sub(lambda m: m.group(1), raw))
    run = solution_overlap(whole, solution, starter)
    if run >= LEAK_TOKEN_RUN:
        reasons.append(f"solution_run={run}")
    if instructions:
        copied = token_run(whole, instructions, starter)
        if copied >= RESTATEMENT_TOKEN_RUN:
            reasons.append(f"restates_instructions={copied}")
    if _THINKING_TRACE.match(plain_prose(raw)):
        reasons.append("model_self_talk")
    return reasons


def _inline_code_repl(match: re.Match[str]) -> str:
    inner = match.group(1).strip()
    if not inner:
        return ""
    # Keep short API-ish names as plain words; flatten statement-shaped spans.
    if len(_tokens(inner)) <= 3 and not re.search(r"[{};=()]", inner):
        return inner
    words = _tokens(inner)
    return " ".join(words[:3]) if words else ""


def strip_code(text: str) -> str:
    """Remove anything code-shaped, keep the prose.

    Inline code is flattened first so a sentence that merely mentions
    ``createButton(text)`` is not mistaken for a dumped line of code.
    """
    out = _FENCE.sub(" ", text or "")
    out = _INLINE_CODE.sub(_inline_code_repl, out)
    return "\n".join(line for line in out.splitlines() if not looks_like_code(line))


def plain_prose(text: str) -> str:
    """Markdown -> plain sentences, whitespace collapsed."""
    out = _MD_HEADING.sub("", text or "")
    out = _MD_BULLET.sub("", out)
    out = _MD_EMPH.sub(lambda m: m.group(1) or m.group(2) or m.group(3) or m.group(4) or "", out)
    out = _MD_LINK.sub(r"\1", out)
    out = _INLINE_CODE.sub(_inline_code_repl, out)
    return re.sub(r"\s+", " ", out).strip()


def tidy(text: str) -> str:
    """Drop model self-talk and opening praise; keep the nudge itself."""
    out = (text or "").strip()
    changed = True
    while changed:
        changed = False
        if _THINKING_TRACE.match(out):
            parts = _SENTENCE_END.split(out, maxsplit=1)
            out = parts[1].strip() if len(parts) > 1 else ""
            changed = True
        praise = _PRAISE.match(out)
        if praise and out[praise.end():].strip():
            out = out[praise.end():].strip()
            out = out[0].upper() + out[1:] if out else out
            changed = True
    return out


def condense(text: str, *, max_sentences: int = 2) -> str:
    """Keep at most two sentences inside the flow-state budget."""
    out = (text or "").strip()
    sentences = _SENTENCE_END.split(out)
    if len(sentences) > max_sentences:
        out = " ".join(sentences[:max_sentences]).strip()
    if len(out) <= SOFT_CHAR_LIMIT:
        return out
    kept: list[str] = []
    used = 0
    for sentence in _SENTENCE_END.split(out):
        if kept and used + len(sentence) > SOFT_CHAR_LIMIT:
            break
        kept.append(sentence)
        used += len(sentence) + 1
        if len(kept) >= max_sentences:
            break
    out = " ".join(kept).strip()
    if len(out) > MAX_HINT_CHARS or not re.search(r"[.!?]$", out):
        out = out[:MAX_HINT_CHARS].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return out


def repair_hint(
    raw: str | None,
    *,
    solution: str = "",
    starter: str = "",
    instructions: str = "",
    max_sentences: int = 2,
) -> str | None:
    """Turn any provider reply into a contract-clean hint, or None if hopeless.

    Compliant prose is passed through untouched, so a good model is never
    rewritten by this layer — only rule-breaking replies get operated on.
    """
    if not raw or not raw.strip() or len(raw) > 6000:
        return None
    body = tidy(plain_prose(strip_code(raw)))
    if not body:
        return None
    body = condense(tidy(body), max_sentences=max_sentences)
    if len(body) < MIN_HINT_CHARS or not re.search(r"[A-Za-z]", body):
        return None
    if len(body.split()) > MAX_HINT_WORDS:
        return None
    if leak_reasons(body, solution=solution, starter=starter, instructions=instructions):
        return None
    return body


# ─── OFFLINE FALLBACK ──────────────────────────────────────────────────────────

_FN_PATTERNS = (
    re.compile(r"\bdef\s+([A-Za-z_]\w*)\s*\("),
    re.compile(r"\bfunction\s+([A-Za-z_]\w*)\s*\("),
    re.compile(r"\b(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?(?:\(|function)"),
    re.compile(r"\bclass\s+([A-Za-z_]\w*)\b"),
)
# Words that follow `function`/`class` in prose or are keywords, not names.
_NAME_STOPWORDS = {
    "if", "for", "while", "switch", "catch", "return", "that", "this", "the", "a", "an",
    "to", "of", "and", "or", "in", "is", "it", "you", "your", "new", "try", "else",
}


def failing_check_names(test_results: Iterable[Any], limit: int = 5) -> list[str]:
    """Names of the checks that are red — names only, never their messages."""
    return _failing_tests(test_results)[:limit]


def _subject(code: str) -> str:
    for pattern in _FN_PATTERNS:
        match = pattern.search(code or "")
        if match and match.group(1) not in _NAME_STOPWORDS:
            return match.group(1)
    return ""


def _clip(text: Any, limit: int) -> str:
    out = re.sub(r"\s+", " ", str(text or "")).strip().rstrip(".")
    if len(out) <= limit:
        return out
    return out[:limit].rsplit(" ", 1)[0].rstrip(",;:")


def _failing_tests(test_results: Iterable[Any]) -> list[str]:
    names: list[str] = []
    for result in test_results or []:
        if isinstance(result, dict):
            passed, name = result.get("passed"), result.get("name")
        else:
            passed, name = getattr(result, "passed", None), getattr(result, "name", None)
        if not passed and name:
            names.append(str(name))
    return names


def offline_hint(
    *,
    code: str = "",
    test_results: Iterable[Any] = (),
    hint_level: int = 1,
    previous_hints: Iterable[str] = (),
    learning_objective: str = "",
) -> str:
    """A deterministic, curriculum-grounded nudge when the AI cannot help.

    Built only from what the learner already has — their own code, the failing
    check names, the lesson objective — so it can never spoil the answer.
    """
    subject = _subject(code)
    where = subject if subject else "your code"
    opening = f"The code in {subject}" if subject else "Your code"
    failing = _failing_tests(test_results)
    first_check = failing[0] if failing else "the first red check"
    turn = max(0, len(list(previous_hints or ())))
    level = min(4, max(1, int(hint_level or 1)))

    if level == 1:
        objective = _clip(learning_objective, 90)
        variants = [
            f"Before you type, say out loud what {first_check} expects back. "
            f"Then point at the line in {where} that decides it.",
            f"Read {first_check} once more and name the value it wants. "
            f"Find the one line in {where} that produces that value.",
            f"Start from the idea: {objective or 'work out what ' + first_check + ' wants'}. "
            f"Then change only the line in {where} that controls it.",
        ]
    elif level == 2:
        variants = [
            f"{len(failing) or 1} check is still red: {first_check}. "
            f"Start where {where} still has a TODO and make just that line real.",
            f"{first_check} is aimed at one decision inside {where}. "
            f"Find it, ignore everything else, fix that.",
        ]
    elif level == 3:
        variants = [
            f"{opening} hands back a placeholder instead of a computed value. "
            f"Decide the value {first_check} wants, then return it.",
            f"The mistake is inside {where}: what comes back never depends on what went in, "
            f"which is exactly what {first_check} catches. Make it depend on the inputs.",
        ]
    else:
        variants = [
            f"Two moves inside {where}: first work out the value {first_check} wants, "
            f"then hand that back. Change one line, run, read the next red check.",
            f"Build it in order: compute the value in {where}, return it, re-run. "
            f"Let each red check tell you which line is next.",
        ]
    return variants[(turn + level) % len(variants)]
