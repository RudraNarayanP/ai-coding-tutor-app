"""Live AI-hint quality lab: what does the tutor ACTUALLY send learners?

The static pipeline tests use fake providers, which hides the real failure
mode learners hit: a small/hosted model that answers a hint request with a
code dump or an essay. This harness asks the REAL configured provider for
hints on REAL curriculum lessons at every hint level, then scores each raw
reply against the flow-state contract:

  leak      - fenced code, code-shaped lines, or a verbatim run copied from
              the lesson's reference solution (the answer, not a nudge)
  long      - more than 55 words / 320 characters
  markdown  - **bold**, headings, bullet lists
  vague     - no actionable next step
  filler    - pure praise / restated instructions

Run from the repository root:
    .venv/Scripts/python.exe -m backend.hint_lab --per-course 2 --levels 1,2,3,4
    .venv/Scripts/python.exe -m backend.hint_lab --lessons js-02,loops-03 --raw
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.ai_models import TestResult, TutorRequest  # noqa: E402
from backend.ai_provider import get_ai_provider  # noqa: E402
from backend.curriculum_loader import load_all_curriculums  # noqa: E402
from backend.hint_contract import looks_like_code  # noqa: E402

MAX_WORDS = 55
MAX_CHARS = 320
LEAK_TOKEN_RUN = 6  # consecutive identifier tokens copied from the solution

_FENCE = re.compile(r"```.*?```|~~~.*?~~~", re.S)
_MARKDOWN = re.compile(r"\*\*|^#{1,6}\s|^\s*[-*]\s|^\s*\d+\.\s|^\s*\|", re.M)
_FILLER = re.compile(
    r"^(great|awesome|nice|good|well)\b|keep it up|you.{0,6}got this|"
    r"don.{0,3}t worry|that.{0,4}s okay|restating|as (i )?mentioned",
    re.I,
)
_ACTION = re.compile(
    r"\b(add|change|try|use|start|check|return|replace|write|call|pass|make|set|"
    r"look|name|think|count|print|define|loop|index|remove|insert|swap|split|join|"
    r"focus|first|next|before|instead|remember|read|find|fix|decide|work|hand|"
    r"build|point|ignore|say|ask|notice|aim|run|trace|compare|sketch|outline)\b",
    re.I,
)
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _tokens(code: str) -> list[str]:
    return _IDENT.findall(code or "")


def solution_overlap(text: str, solution: str, starter: str) -> int:
    """Longest run of consecutive solution tokens echoed by the reply.

    Tokens already present in the starter are skipped: repeating what the
    learner can already see is not a spoiler.
    """
    if not solution:
        return 0
    sol = _tokens(solution)
    seen = set(_tokens(starter or ""))
    reply = _tokens(text)
    if not reply:
        return 0
    reply_set = set(reply)
    best = 0
    for i in range(len(sol)):
        if sol[i] in seen or sol[i] not in reply_set:
            continue
        run = 0
        j = i
        while j < len(sol) and sol[j] in reply_set and sol[j] not in seen:
            run += 1
            j += 1
        best = max(best, run)
    return best


def score(raw: str, *, solution: str = "", starter: str = "") -> dict:
    text = raw or ""
    body = _FENCE.sub(" ", text)
    words = len(re.findall(r"\S+", body))
    code_lines = [line for line in body.splitlines() if looks_like_code(line)]
    run = solution_overlap(body, solution, starter)
    leak_reasons = []
    if "```" in text or "~~~" in text:
        leak_reasons.append("fenced_code")
    if code_lines:
        leak_reasons.append(f"code_lines={len(code_lines)}")
    if run >= LEAK_TOKEN_RUN:
        leak_reasons.append(f"solution_run={run}")
    return {
        "chars": len(body.strip()),
        "words": words,
        "leak": bool(leak_reasons),
        "leak_reasons": leak_reasons,
        "long": words > MAX_WORDS or len(body.strip()) > MAX_CHARS,
        "markdown": bool(_MARKDOWN.search(text)),
        "filler": bool(_FILLER.search(body.strip())),
        "actionable": bool(_ACTION.search(body)),
    }


def broken_attempt(solution: str) -> str:
    """A realistic near-miss: solution with its most answer-like line gutted."""
    lines = solution.splitlines()
    if not lines:
        return ""
    idx = max(
        range(len(lines)),
        key=lambda i: (len(lines[i]), i) if ("=" in lines[i] or "return" in lines[i]) else (0, i),
    )
    out = list(lines)
    indent = re.match(r"\s*", out[idx]).group(0)
    out[idx] = f"{indent}# TODO: finish this part"
    return "\n".join(out)


def test_results_for(lesson, passed: bool = False) -> list[TestResult]:
    results = []
    for spec in (lesson.tests or [])[:3]:
        results.append(
            TestResult(
                name=spec.name,
                passed=passed,
                required=spec.required,
                description=spec.description,
                error=None if passed else f"AssertionError in {spec.name}: expected behaviour not met",
            )
        )
    return results or [
        TestResult(name="test_required_behaviour", passed=False, required=True,
                   error="AssertionError: expected behaviour not met")
    ]


def build_request(lesson, language: str, level: int, variant: str, *, code: str | None = None) -> TutorRequest:
    if code is None:
        if variant == "starter":
            code = lesson.starter_code or ""
        else:
            code = broken_attempt(lesson.solution_code or lesson.starter_code or "")
    return TutorRequest(
        lesson_id=lesson.id,
        lesson_title=lesson.title,
        unit_title=lesson.section_title or "",
        concept_title="",
        prerequisites=list(lesson.prerequisites or [])[:5],
        instructions=(lesson.description or lesson.title)[:2000],
        learning_objective=(lesson.learning_objectives or [""])[0][:500],
        code=code[:6000],
        test_results=test_results_for(lesson),
        previous_hints=[],
        hint_level=level,
        session_id="hint-lab",
        solution_requested=False,
        user_id="hint-lab",
    )


def pick_lessons(curriculums, per_course: int, ids: list[str] | None):
    chosen = []
    for course_id, curr in sorted(curriculums.items()):
        language = curr.course.language
        code_lessons = [
            l for l in curr.lessons
            if (l.starter_code or "").strip() and (l.solution_code or "").strip()
        ]
        if ids:
            code_lessons = [l for l in code_lessons if l.id in ids]
        # spread across lesson types
        picked, seen_types = [], {}
        for lesson in code_lessons:
            t = lesson.type or "learn"
            if seen_types.get(t, 0) >= max(1, per_course // 2):
                continue
            seen_types[t] = seen_types.get(t, 0) + 1
            picked.append((course_id, language, lesson))
            if len(picked) >= per_course:
                break
        chosen.extend(picked)
    if ids:
        chosen = [c for c in chosen if c[2].id in ids]
    return chosen


async def probe(provider, cases, levels, variants, *, mode="pipeline", raw=False, delay=0.0):
    """mode="raw" scores what the model says; mode="pipeline" scores what a learner sees."""
    service = None
    lessons_by_id = {}
    if mode == "pipeline":
        from backend.tutor_service import TutorService, TutorSessionStore

        for _course_id, _lang, lesson in cases:
            lessons_by_id[lesson.id] = lesson
        service = TutorService(
            provider=provider,
            sessions=TutorSessionStore(),
            lesson_lookup=lambda lid: lessons_by_id.get(lid),
        )

    rows = []
    for course_id, language, lesson in cases:
        for variant in variants:
            for level in levels:
                req = build_request(lesson, language, level, variant)
                entry = {
                    "course": course_id,
                    "language": language,
                    "lesson_id": lesson.id,
                    "lesson_title": lesson.title,
                    "level": level,
                    "variant": variant,
                }
                try:
                    if service is None:
                        text = await provider.tutor(req)
                        entry["source"] = "raw"
                    else:
                        response = await service.tutor(req)
                        text = response.message
                        entry["source"] = response.source
                        entry["diagnostic"] = response.error
                    entry["raw"] = (text or "") if raw else (text or "")[:1200]
                    entry.update(score(text, solution=lesson.solution_code or "",
                                        starter=lesson.starter_code or ""))
                except Exception as exc:  # provider-level failure is also a finding
                    entry["raw"] = f"<error: {type(exc).__name__}: {exc}>"
                    entry["source"] = "error"
                    entry.update({
                        "chars": 0, "words": 0, "leak": False, "leak_reasons": ["provider_error"],
                        "long": False, "markdown": False, "filler": False, "actionable": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                rows.append(entry)
                status = "LEAK" if entry.get("leak") else ("ERR" if entry.get("error") else "ok")
                print(f"[{status:>4}] {course_id:<10} {lesson.id:<18} L{level} {variant:<9} "
                      f"{entry['source']:<12} "
                      f"{entry['words']:>3}w {entry['chars']:>4}c "
                      f"{'md' if entry['markdown'] else '  '} "
                      f"{'act' if entry['actionable'] else '   '} "
                      f"| {entry['raw'].replace(chr(10), ' ⏎ ')[:150]}")
                if delay:
                    await asyncio.sleep(delay)
    return rows


def summarise(rows) -> dict:
    n = len(rows)
    def rate(pred):
        hits = [r for r in rows if pred(r)]
        return len(hits), (100.0 * len(hits) / n if n else 0.0)
    keys = ["leak", "long", "markdown", "filler"]
    summary = {"samples": n, "model": os.getenv("OPENROUTER_MODEL", "")}
    for k in keys:
        c, pct = rate(lambda r, k=k: r.get(k))
        summary[f"{k}_count"], summary[f"{k}_pct"] = c, round(pct, 1)
    c, pct = rate(lambda r: not r.get("actionable"))
    summary["no_action_count"], summary["no_action_pct"] = c, round(pct, 1)
    c, pct = rate(lambda r: bool(r.get("error")))
    summary["error_count"], summary["error_pct"] = c, round(pct, 1)
    sources: dict[str, int] = {}
    for row in rows:
        sources[row.get("source", "?")] = sources.get(row.get("source", "?"), 0) + 1
    summary["sources"] = sources
    words = [r["words"] for r in rows if not r.get("error")]
    summary["median_words"] = sorted(words)[len(words) // 2] if words else 0
    summary["max_words"] = max(words) if words else 0
    good = [r for r in rows if not r.get("error") and not r.get("leak") and not r.get("long")
            and not r.get("markdown") and r.get("actionable")]
    summary["pass_count"] = len(good)
    summary["pass_pct"] = round(100.0 * len(good) / n, 1) if n else 0.0
    return summary


async def main() -> int:
    ap = argparse.ArgumentParser(description="Live AI-hint quality lab")
    ap.add_argument("--per-course", type=int, default=2)
    ap.add_argument("--levels", default="1,2,3,4")
    ap.add_argument("--variants", default="starter,near-miss")
    ap.add_argument("--lessons", default="", help="comma-separated lesson ids (overrides --per-course)")
    ap.add_argument("--model", default="", help="override OPENROUTER_MODEL for this run")
    ap.add_argument("--provider", default="", help="override AI_PROVIDER for this run")
    ap.add_argument("--raw", action="store_true", help="print full raw replies")
    ap.add_argument("--mode", choices=("pipeline", "raw"), default="pipeline",
                    help="pipeline = what the learner sees; raw = what the model says")
    ap.add_argument("--delay", type=float, default=0.3)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    if args.model:
        os.environ["OPENROUTER_MODEL"] = args.model
    if args.provider:
        os.environ["AI_PROVIDER"] = args.provider

    curriculums = load_all_curriculums()
    ids = [i.strip() for i in args.lessons.split(",") if i.strip()] or None
    cases = pick_lessons(curriculums, args.per_course, ids)
    levels = [int(x) for x in args.levels.split(",") if x.strip()]
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]

    provider = get_ai_provider()
    print(f"provider={provider.provider_id} model={getattr(provider, 'model', '?')} "
          f"lessons={len(cases)} levels={levels} variants={variants}\n")

    rows = await probe(provider, cases, levels, variants, mode=args.mode, raw=args.raw, delay=args.delay)
    summary = summarise(rows)
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))

    if args.out:
        Path(args.out).write_text(
            json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8"
        )
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
