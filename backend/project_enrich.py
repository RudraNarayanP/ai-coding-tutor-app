"""LLM enrichment for guided-project milestones.

Transforms the grounded milestone skeleton into polished, learner-facing
micro-content. Source transcripts are NEVER shown verbatim — the LLM rewrites
them into concise coaching copy. Enrichment is best-effort: if the provider is
unavailable, the project keeps its improved deterministic copy.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

from .project_copy import looks_like_raw_transcript, polish_project_copy
from .project_models import ProjectCourse
from .project_planner import ProjectGroundingError
from .source_ingestion import SourceDocument

logger = logging.getLogger("patchwork.project_enrich")

_CHUNK = 4
_CALL_TIMEOUT = 25.0
_TOTAL_BUDGET = 90.0
_RETRIES = 1

_FILLER_RE = re.compile(
    r"\b(uh|um|er|ah|like|you know|sort of|kind of|i mean|basically)\b",
    re.IGNORECASE,
)

_ASSESS_TIMEOUT = 45.0
_ASSESS_SYSTEM = (
    "You are the admissions judge for Patchwork Create Course. "
    "Your only job is KEEP or REJECT. Be strict. "
    "KEEP only if a learner can follow the source to BUILD a real program, "
    "with multiple distinct implementation steps. "
    "REJECT lectures, talks, explainers, interviews, slide overviews, product pitches, "
    "and anything too vague or conceptual to become a high-quality guided coding project. "
    "Do not be generous. Do not invent a project to justify KEEP. "
    "Return STRICT JSON only: {\"keep\": true} or {\"keep\": false, \"reason\": \"one short sentence for the learner\"}."
)


def _parse_json_object(text: str) -> dict:
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    if not text.startswith("{"):
        b = text.find("{")
        if b != -1:
            text = text[b:]
    for attempt in (text, text + "}", text + '"}'):
        try:
            data = json.loads(attempt)
            if isinstance(data, dict):
                return data
        except Exception:  # noqa: BLE001
            continue
    return {}


def _explicit_keep(data: dict) -> bool:
    if not data:
        return False
    value = data.get("keep", data.get("buildable"))
    return value is True or str(value).strip().lower() in {"true", "keep", "yes"}


async def _llm_keep_or_reject(provider, user: str) -> None:
    """Fail closed: only KEEP when the user's LLM explicitly says keep."""
    try:
        raw = await asyncio.wait_for(
            provider.generate_structured(_ASSESS_SYSTEM, user, max_tokens=250),
            timeout=_ASSESS_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001
        raise ProjectGroundingError(
            "The AI could not judge whether this source has enough material for a good course. "
            "Check your provider, then try a hands-on coding tutorial."
        ) from exc
    data = _parse_json_object(raw)
    if _explicit_keep(data):
        return
    reason = _sanitize(str(data.get("reason", "")), 400)
    raise ProjectGroundingError(
        reason
        or "This source does not have enough hands-on coding material to build a good course. "
        "Try a build-along tutorial that actually implements a program."
    )


async def assess_source_for_course(provider, doc: SourceDocument, title: str) -> None:
    """The user's configured LLM decides KEEP or REJECT for any source."""
    if provider is None:
        return
    from .project_planner import _collect_chapters, _gather_source_text

    text = _gather_source_text(doc)
    chapters = _collect_chapters(doc)
    user = (
        f"Title: {title or doc.title}\n"
        f"Chapters: {', '.join(chapters[:24]) or '(none)'}\n\n"
        f"Source excerpt:\n{text[:8000]}\n\n"
        "Decide KEEP or REJECT for turning this into a guided coding project.\n"
        "KEEP only if the source walks through implementing a program.\n"
        "REJECT if a learner would mostly listen or watch rather than code along."
    )
    await _llm_keep_or_reject(provider, user)


async def assess_planned_course(provider, project: ProjectCourse) -> None:
    """The user's configured LLM reviews the planned outline and can still REJECT."""
    if provider is None:
        return
    titles = [f"{m.order}. {m.title}" for m in project.milestones]
    user = (
        f"Proposed course title: {project.title}\n"
        f"Goal: {project.project_goal}\n"
        f"Tech: {', '.join(project.tech_stack) or '(none detected)'}\n"
        f"Milestones:\n" + "\n".join(titles) + "\n\n"
        "This outline was extracted from a source. Decide KEEP or REJECT.\n"
        "KEEP only if this is a coherent hands-on coding project with distinct implementation steps.\n"
        "REJECT if the steps are vague, repetitive, not actually coding, or would make a bad course."
    )
    await _llm_keep_or_reject(provider, user)


_SYSTEM = (
    "You are a concise coding coach for a Duolingo-style app. "
    "You write SHORT, polished teaching copy grounded in the given project. "
    "NEVER paste or paraphrase raw YouTube transcript dialogue. "
    "NEVER use speech fillers (uh, um, like, you know). "
    "NEVER invent features not in the source. "
    "Return STRICT JSON only (no markdown, no prose outside JSON)."
)


def _sanitize(text: str, max_len: int) -> str:
    cleaned = _FILLER_RE.sub("", (text or "").strip())
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if looks_like_raw_transcript(cleaned):
        return ""
    return cleaned[:max_len]


def _build_intro_prompt(project: ProjectCourse) -> str:
    milestones = [
        m.title for m in project.milestones
        if m.checks and m.checks[0].kind not in ("file_exists", "run_ok")
    ][:8]
    return (
        f"Project title: {project.title}\n"
        f"Technologies: {', '.join(project.tech_stack) or 'general Python'}\n"
        f"Milestone outline: {', '.join(milestones)}\n\n"
        "Write a SHORT course introduction (3-5 sentences, <=120 words) that explains:\n"
        "1) What real project we are building\n"
        "2) Why it matters\n"
        "3) What the learner will accomplish across milestones\n"
        "Do NOT quote the transcript. Do NOT use filler words.\n"
        'Return JSON: {"intro": "..."}'
    )


def _build_user_prompt(project: ProjectCourse, items: list[tuple[int, str, str]]) -> str:
    listing = "\n".join(f'{idx}. {title} — verify: {check_desc}' for idx, title, check_desc in items)
    outline = "; ".join(m.title for m in project.milestones[:16])
    return (
        f"Project: {project.title}\n"
        f"What it builds: {project.project_goal}\n"
        f"Goal: {project.project_goal}\n"
        f"Tech: {', '.join(project.tech_stack) or 'general'}\n"
        f"Project steps: {outline}\n\n"
        "For EACH numbered milestone, write polished learner-facing content.\n"
        "The source material is for grounding only — do NOT echo transcript speech.\n\n"
        "Return JSON mapping step number (string) to:\n"
        '{"hook": <=10 words headline, '
        '"observation": 1 short sentence (what this step is about), '
        '"action": 1 imperative coding task (<=25 words), '
        '"teach": 2 sentences max (what it is + why it matters — no filler), '
        '"example": ONE tiny code line, '
        '"celebrate": short hype line with one emoji}\n'
        "Never paste or paraphrase a raw video transcript.\n\n"
        f"Milestones:\n{listing}"
    )


def _parse_items(text: str) -> dict[int, dict]:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()

    candidate = text
    if not candidate.startswith("{"):
        b = candidate.find("{")
        if b != -1:
            candidate = candidate[b:]
    for attempt in (candidate, candidate + "}", candidate + '"}}'):
        try:
            data = json.loads(attempt)
            if isinstance(data, dict):
                return {
                    int(k): v for k, v in data.items()
                    if str(k).strip().lstrip("-").isdigit() and isinstance(v, dict)
                }
        except Exception:  # noqa: BLE001
            pass

    out: dict[int, dict] = {}
    for km in re.finditer(r'"(\d+)"\s*:\s*\{', text):
        order = int(km.group(1))
        start = km.end() - 1
        depth = 0
        in_str = False
        esc = False
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
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
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
        if end != -1:
            try:
                obj = json.loads(text[start : end + 1])
                if isinstance(obj, dict):
                    out[order] = obj
            except Exception:  # noqa: BLE001
                continue
    return out


def _apply_items(project: ProjectCourse, data: dict[int, dict]) -> int:
    by_order = {m.order: m for m in project.milestones}
    applied = 0
    for order, val in data.items():
        m = by_order.get(order)
        if not m or not isinstance(val, dict):
            continue
        hook = _sanitize(str(val.get("hook", "")), 200)
        observation = _sanitize(str(val.get("observation", "")), 400)
        action = _sanitize(str(val.get("action", "")), 400)
        teach = _sanitize(str(val.get("teach", "")), 1200)
        example = _sanitize(str(val.get("example", "")), 1200)
        celebrate = _sanitize(str(val.get("celebrate", "")), 200)
        # Refuse caption dumps the model echoed from source text.
        if looks_like_raw_transcript(teach) or looks_like_raw_transcript(hook):
            continue
        if not (hook or observation or action or teach):
            continue
        if hook:
            m.hook = hook
        if teach and len(teach) > 20:
            m.teach = teach
        if example:
            m.example = example
        if celebrate:
            m.celebrate = celebrate
        if observation and not looks_like_raw_transcript(observation) and len(observation.split()) <= 28:
            m.microstep.observation = observation
        elif hook and not looks_like_raw_transcript(hook):
            m.microstep.observation = hook
        if (
            action
            and len(action) >= 8
            and len(action.split()) <= 25
            and not looks_like_raw_transcript(action)
        ):
            m.microstep.action = action
        applied += 1
    return applied


async def _enrich_intro(provider, project: ProjectCourse) -> None:
    try:
        raw = await asyncio.wait_for(
            provider.generate_structured(_SYSTEM, _build_intro_prompt(project), max_tokens=400),
            timeout=_CALL_TIMEOUT,
        )
        text = raw.strip()
        m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        if not text.startswith("{"):
            b = text.find("{")
            if b != -1:
                text = text[b:]
        data = json.loads(text)
        intro = _sanitize(str(data.get("intro", "")), 2000)
        if intro and len(intro) > 40:
            project.course_intro = intro
    except Exception as exc:  # noqa: BLE001
        logger.info(f"Course intro enrichment skipped ({exc.__class__.__name__}).")


async def _enrich_chunk(provider, project: ProjectCourse, items: list[tuple[int, str, str]]) -> int:
    pending = list(items)
    total_applied = 0
    for attempt in range(_RETRIES + 1):
        if not pending:
            break
        user = _build_user_prompt(project, pending)
        raw = await asyncio.wait_for(
            provider.generate_structured(_SYSTEM, user, max_tokens=1200), timeout=_CALL_TIMEOUT
        )
        data = _parse_items(raw)
        total_applied += _apply_items(project, data)
        by_order = {m.order: m for m in project.milestones}
        pending = [
            (o, t, c) for (o, t, c) in pending
            if not (by_order.get(o) and by_order[o].teach)
        ]
    return total_applied


async def enrich_project(provider, project: ProjectCourse) -> ProjectCourse:
    """Best-effort enrich milestones and course intro. Never raises."""
    if provider is None:
        polish_project_copy(project)
        return project

    await _enrich_intro(provider, project)

    targets = [
        (m.order, m.title, m.checks[0].description if m.checks else "")
        for m in project.milestones
        if m.checks and m.checks[0].kind not in ("file_exists", "run_ok")
    ]
    if not targets:
        polish_project_copy(project)
        return project

    loop = asyncio.get_event_loop()
    start = loop.time()
    for i in range(0, len(targets), _CHUNK):
        if loop.time() - start > _TOTAL_BUDGET:
            logger.info("Enrichment budget exhausted; keeping deterministic copy.")
            break
        chunk = targets[i : i + _CHUNK]
        try:
            await _enrich_chunk(provider, project, chunk)
        except Exception as exc:  # noqa: BLE001 — enrichment is best-effort.
            logger.info(f"Milestone enrichment chunk failed ({exc.__class__.__name__}); using deterministic copy.")
    polish_project_copy(project)
    return project
