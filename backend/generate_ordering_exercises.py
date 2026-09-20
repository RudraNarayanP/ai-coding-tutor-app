"""Derive ordering exercises from real lesson solutions, verified by execution.

The app is ~96% "write code in the editor and hit Run", because only 13 of 334
lessons contain any exercise at all. This adds a genuinely different item type
without inventing prose: take a lesson's own multi-statement solution, present
its statements shuffled, and ask the learner to restore the order.

Why execution rather than parsing: deciding whether an order is *unique* needs
to know data dependencies across six languages (python, js, ts, java, cpp, sql).
Instead of a fragile per-language analyser, every candidate is proven by
running it: the canonical order must pass the lesson's own tests, and **every
adjacent swap must fail**. If no neighbouring pair can be exchanged, the order
is the only one the grader will accept, so a learner reasoning correctly cannot
be marked wrong. Candidates that do not prove out are dropped, not guessed at.

Run:  python -m backend.generate_ordering_exercises [--dry-run] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from backend.curriculum_loader import load_all_curriculums
from backend import console
from backend.verify_lessons import LOCAL_LANGS, eval_code
from backend.ordering_content import (
    MAX_PER_COURSE,
    build_exercise,
    build_sublesson,
    signature,
)

console.configure()

CURRICULUM_ROOT = Path(__file__).resolve().parent.parent / "curriculum"

MIN_STATEMENTS = 3
MAX_STATEMENTS = 5
# A lesson whose solution is one expression teaches nothing about sequencing.
SKIP_IF_SINGLE_EXPRESSION = True


def statement_units(solution_code: str) -> list[str]:
    """The ordered executable statements of a solution, dedented and merged.

    Imports, decorators, function/class headers, docstrings and blank lines are
    scaffolding rather than steps, so they stay in the prompt and never become
    reorderable units.
    """
    lines = solution_code.split("\n")
    body_indent = _body_indent(lines)
    units: list[str] = []
    buffer: list[str] = []
    depth = 0

    for raw in lines:
        text = raw.strip()
        if not text:
            continue
        if _is_scaffolding(text, body_indent, raw):
            continue
        content = text
        depth += len(re.findall(r"[\({\[]", content)) - len(re.findall(r"[\)}\]]", content))
        buffer.append(content)
        if depth <= 0:
            units.append(" ".join(buffer))
            buffer = []
            depth = 0
    if buffer:
        units.append(" ".join(buffer))
    return [u for u in units if u and not _is_docstring(u)]


def _body_indent(lines: list[str]) -> int:
    """Indent of the first executable line after a def/class header."""
    for index, raw in enumerate(lines):
        if re.match(r"^\s*(def|function|class|public|private|fn)\b", raw):
            for follow in lines[index + 1:]:
                if follow.strip():
                    return len(follow) - len(follow.lstrip())
    return 0


def _is_scaffolding(text: str, body_indent: int, raw: str) -> bool:
    if re.match(r"^(import|from|#include|using|package|#\s*define)\b", text):
        return True
    if text.startswith(("@", "#[")):
        return True
    if re.match(r"^(def|function|fn|class|struct|interface|enum)\b", text):
        return True
    if re.match(r"^(public|private|protected)\s+(static\s+)?\w+", text) and text.endswith("{"):
        return True
    if re.match(r"^\}\s*;?\s*$", text):
        return True
    if text.startswith("return") and body_indent and (len(raw) - len(raw.lstrip())) < body_indent:
        return True
    return False


def _is_docstring(unit: str) -> bool:
    return bool(re.fullmatch(r'(""".*"""|\x27\x27\x27.*\x27\x27\x27)', unit, re.S))


def rotate_adjacent(units: list[str], index: int) -> list[str]:
    swapped = list(units)
    swapped[index], swapped[index + 1] = swapped[index + 1], swapped[index]
    return swapped


def passes(language: str, code: str, tests: list[dict], use_docker: bool) -> bool:
    """Whether `code` satisfies every required test, using the audit harness."""
    return eval_code(language, code, tests, use_docker)["all_pass"]


def build_prompt(units: list[str], lesson_title: str) -> str:
    return (
        f"Put the steps of `{lesson_title}` back in order. "
        "Each line depends on the one before it."
    )


def candidate_for(lesson, language: str) -> dict | None:
    """Return an ordering item for a lesson, or None when it does not qualify."""
    solution = (lesson.solution_code or "").strip()
    tests = [t.model_dump() for t in lesson.tests]
    if not solution or not tests:
        return None

    units = statement_units(solution)
    if not MIN_STATEMENTS <= len(units) <= MAX_STATEMENTS:
        return None
    if len({unit.lower() for unit in units}) != len(units):
        return None  # duplicate statements make the order ambiguous

    use_docker = language not in LOCAL_LANGS
    body_indent = _body_indent(solution.split("\n"))

    def render(order: list[str]) -> str:
        head = [l for l in solution.split("\n") if _is_scaffolding_keep(l, body_indent)]
        return "\n".join(head + [(" " * body_indent + u if body_indent else u) for u in order])

    # The canonical order must pass the lesson's own tests.
    if not passes(language, render(units), tests, use_docker):
        return None

    # ...and every neighbouring swap must fail, which is what makes the answer
    # unique. Anything else and a correct learner could be marked wrong.
    for index in range(len(units) - 1):
        swapped = rotate_adjacent(units, index)
        try:
            if passes(language, render(swapped), tests, use_docker):
                return None
        except Exception:
            return None

    return {
        "units": units,
        "prompt": build_prompt(units, lesson.title),
        "explanation": f"The order the solution in “{lesson.title}” actually runs in.",
    }


def _is_scaffolding_keep(raw: str, body_indent: int) -> bool:
    """Header lines that stay fixed above the reorderable body."""
    text = raw.strip()
    if not text:
        return False
    indent = len(raw) - len(raw.lstrip())
    if indent >= body_indent and body_indent > 0:
        return False
    return bool(
        re.match(r"^(import|from|#include|using|package)\b", text)
        or re.match(r"^(def|function|fn|class|struct|interface)\b", text)
        or re.match(r"^(public|private|protected)\b", text)
        or text.startswith("@")
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true", help="write the accepted items")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="COURSE/LESSON_ID",
        help="target specific lessons (repeatable), e.g. dsa/graph-traversals-step-2. "
             "Requested lessons bypass the per-course cap, since the choice is explicit; "
             "every execution proof and the dedupe still apply.",
    )
    args = parser.parse_args(argv)

    wanted = {o.strip().lower() for o in args.only if o.strip()}

    found: list[tuple[str, str, dict]] = []
    for language, curriculum in sorted(load_all_curriculums().items()):
        for lesson in curriculum.lessons:
            if wanted and f"{language}/{lesson.id}".lower() not in wanted:
                continue
            if lesson.sublessons and not wanted:
                continue  # already a multi-step lesson
            try:
                item = candidate_for(lesson, language)
            except Exception as exc:  # a sandbox hiccup must not abort the sweep
                print(f"  skip {language}/{lesson.id}: {exc}")
                continue
            if item:
                found.append((language, lesson.id, item))
                print(f"  ✓ {language}/{lesson.id} — {len(item['units'])} steps")
            elif wanted:
                print(f"  ✗ {language}/{lesson.id} — did not qualify")
            if args.limit and len(found) >= args.limit:
                break
        if args.limit and len(found) >= args.limit:
            break

    print(f"\nexecution-verified candidates: {len(found)}")

    # Drop near-duplicates and balance across courses before writing.
    seen_signatures: set[str] = set()
    per_course: dict[str, int] = {}
    accepted: list[tuple[str, str, dict]] = []
    for language, lesson_id, item in found:
        digest = signature(item["units"])
        if digest in seen_signatures:
            print(f"  dup  {language}/{lesson_id} — same shape as an accepted item")
            continue
        if per_course.get(language, 0) >= MAX_PER_COURSE:
            print(f"  cap  {language}/{lesson_id} — {language} already at {MAX_PER_COURSE}")
            continue
        seen_signatures.add(digest)
        per_course[language] = per_course.get(language, 0) + 1
        accepted.append((language, lesson_id, item))

    print(f"accepted after dedupe + per-course cap: {len(accepted)}")
    print(f"  spread: {dict(sorted(per_course.items()))}")

    if args.dry_run or not args.apply:
        for language, lesson_id, item in accepted:
            print(f"\n[{language}/{lesson_id}]")
            for unit in item["units"]:
                print(f"   • {unit[:100]}")
        if not args.apply:
            print("\n(nothing written; pass --apply)")
        return 0

    for path in sorted(CURRICULUM_ROOT.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        touched = False
        for lesson in payload.get("lessons") or []:
            match = next(
                (
                    (lid, item)
                    for _lang, lid, item in accepted
                    if lid == lesson.get("id")
                ),
                None,
            )
            if not match:
                continue
            lesson_id, item = match
            if lesson.get("sublessons"):
                continue
            exercise = build_exercise(lesson, item["units"], item["prompt"], item["explanation"])
            lesson["sublessons"] = [build_sublesson(exercise, len(lesson.get("sublessons") or []) + 1)]
            touched = True
        if touched:
            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
    print(f"wrote ordering items for {len(accepted)} lessons")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
