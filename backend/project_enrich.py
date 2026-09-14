"""LLM enrichment for guided-project milestones.

Turns the grounded milestone skeleton into rich, engaging, dopamine-heavy
micro-content: a punchy hook, a concise what-and-why explanation, a tiny worked
example, and a celebratory completion line — all grounded in the source's real
chapters. Enrichment is best-effort: if the provider is unavailable, slow, or
returns malformed output, the project keeps its (improved) deterministic copy,
so course creation never fails or hangs because of the LLM.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

from .project_models import ProjectCourse

logger = logging.getLogger("patchwork.project_enrich")

_CHUNK = 4             # milestones per LLM call (small = less truncation risk)
_CALL_TIMEOUT = 25.0   # seconds per call
_TOTAL_BUDGET = 90.0   # seconds total across all calls
_RETRIES = 1           # extra attempts per chunk on failure/empty


_SYSTEM = (
    "You are a witty, encouraging coding-course writer for a Duolingo-style app. "
    "You write tight, dopamine-heavy micro-content that keeps learners hooked. "
    "Everything must be GROUNDED in the given project/source — never invent unrelated topics. "
    "Return STRICT JSON only (no markdown, no prose outside JSON)."
)


def _build_user_prompt(project: ProjectCourse, items: list[tuple[int, str]]) -> str:
    listing = "\n".join(f'{idx}. {title}' for idx, title in items)
    return (
        f"Project: {project.title}\n"
        f"What it builds: {project.project_goal}\n"
        f"Tech: {', '.join(project.tech_stack) or 'general'}\n"
        f"Source summary: {project.source_summary[:1200]}\n\n"
        f"For EACH numbered step below, write engaging micro-content grounded in what this project "
        f"actually builds at that step. Return a JSON object mapping the step number (as a string) to "
        f'an object: {{"hook": punchy line <=12 words, "teach": 2 sentences (what it is + why it '
        f'matters), "example": ONE tiny code line or pattern, "celebrate": a short hype line with one '
        f"emoji}}.\n\nSteps:\n{listing}"
    )


def _parse_items(text: str) -> dict[int, dict]:
    """Parse the model's JSON mapping step-number -> content, tolerating markdown
    fences, surrounding prose, and truncation. Salvages individual step objects
    when the whole payload can't be parsed, so a partially-truncated response
    still enriches the steps it did return."""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()

    # 1) Try the whole object.
    candidate = text
    if not candidate.startswith("{"):
        b = candidate.find("{")
        if b != -1:
            candidate = candidate[b:]
    for attempt in (candidate, candidate + "}", candidate + '"}}'):
        try:
            data = json.loads(attempt)
            if isinstance(data, dict):
                return {int(k): v for k, v in data.items() if str(k).strip().lstrip("-").isdigit() and isinstance(v, dict)}
        except Exception:  # noqa: BLE001
            pass

    # 2) Salvage: brace-match each `"<num>": { ... }` object individually.
    out: dict[int, dict] = {}
    for km in re.finditer(r'"(\d+)"\s*:\s*\{', text):
        order = int(km.group(1))
        start = km.end() - 1  # index of "{"
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
        hook = str(val.get("hook", "")).strip()
        teach = str(val.get("teach", "")).strip()
        example = str(val.get("example", "")).strip()
        celebrate = str(val.get("celebrate", "")).strip()
        if teach and len(teach) > 20:
            m.hook = hook[:200]
            m.teach = teach[:1200]
            m.example = example[:1200]
            if celebrate:
                m.celebrate = celebrate[:200]
            if hook:
                m.microstep.observation = hook[:400]
            applied += 1
    return applied


async def _enrich_chunk(provider, project: ProjectCourse, items: list[tuple[int, str]]) -> int:
    """Enrich one chunk; retries once, and only re-requests the steps still
    missing. Returns how many milestones were newly enriched."""
    pending = list(items)
    total_applied = 0
    for attempt in range(_RETRIES + 1):
        if not pending:
            break
        user = _build_user_prompt(project, pending)
        raw = await asyncio.wait_for(
            provider.generate_structured(_SYSTEM, user, max_tokens=1000), timeout=_CALL_TIMEOUT
        )
        data = _parse_items(raw)
        total_applied += _apply_items(project, data)
        by_order = {m.order: m for m in project.milestones}
        pending = [(o, t) for (o, t) in pending if not (by_order.get(o) and by_order[o].teach)]
    return total_applied


async def enrich_project(provider, project: ProjectCourse) -> ProjectCourse:
    """Best-effort enrich all buildable milestones. Never raises."""
    if provider is None:
        return project
    # Skip trivial setup/run milestones; enrich the substantive ones.
    targets = [
        (m.order, m.title)
        for m in project.milestones
        if m.checks and m.checks[0].kind not in ("file_exists", "run_ok")
    ]
    if not targets:
        return project

    loop = asyncio.get_event_loop()
    start = loop.time()
    for i in range(0, len(targets), _CHUNK):
        if loop.time() - start > _TOTAL_BUDGET:
            logger.info("Enrichment budget exhausted; keeping deterministic copy for remaining milestones.")
            break
        chunk = targets[i : i + _CHUNK]
        try:
            await _enrich_chunk(provider, project, chunk)
        except Exception as exc:  # noqa: BLE001 — enrichment is best-effort.
            logger.info(f"Milestone enrichment chunk failed ({exc.__class__.__name__}); using deterministic copy.")
    return project
