"""Grade every graded curriculum item both ways with the real grader.

For each item the answer key must be accepted and a wrong answer must be
rejected. The right-answer half proves the key is in the shape the grader
expects; the wrong-answer half is the one that catches silent auto-pass, a key
that matches anything, and a comparison loose enough to accept a near-miss.

Wrong answers are derived per type rather than hand-maintained, so a new item is
covered the moment it is written:

* true_false      -> the other boolean
* mcq / output    -> a different option
* select_multiple -> the key minus one correct entry (a partial answer must not
  pass, or "select all that apply" degrades into "select any")
* matching        -> right-hand sides rotated, so every pair is wrong
* ordering        -> the sequence reversed, or rotated if that is a palindrome
* fill / completion -> a token that is not the key
* code-like       -> skipped: those are graded by running tests, which
  ``backend/verify_lessons.py`` proves in the real sandbox

``WRONG`` keeps hand-picked near-misses for items where the generic derivation
would be trivially wrong rather than plausibly wrong.
"""
from __future__ import annotations

import asyncio

from backend.curriculum_loader import load_all_curriculums
from backend.exercise_types import (
    CODE_TYPES,
    FILL_TYPES,
    MATCHING_TYPES,
    MULTI_SELECT_TYPES,
    ORDERING_TYPES,
)
from backend.lesson_engine import LessonEngine

# Deliberate near-misses a learner would really pick, where "pick another option"
# would be too easy to reject.
WRONG = {
    "cpp-ptr-01-mcq-1": {"answer": "ptr"},
    "cpp-perf-01-multi-1": {"answers": ["<algorithm>"]},
    "js-05-mcq-1": {"answer": "the original array, changed in place"},
    "conditionals-01-dbg-1": {"answer": "`elif` cannot follow a plain `if`"},
    "sql-03-match-1": {"pairs": [
        {"left": "WHERE", "right": "matches values inside a range"},
        {"left": "LIKE", "right": "keeps only the rows that pass a test"},
        {"left": "IN", "right": "matches a text pattern with % and _"},
        {"left": "BETWEEN", "right": "matches any value from a listed set"},
    ]},
}


class DummyExecutor:
    async def run(self, payload):
        return {"passed": True, "tests": []}


def right_payload(exercise) -> dict:
    answer = exercise.correct_answer
    ex_type = str(exercise.type).lower()
    if ex_type in MATCHING_TYPES and isinstance(answer, dict):
        return {"pairs": [{"left": k, "right": v} for k, v in answer.items()]}
    if ex_type in ORDERING_TYPES and isinstance(answer, list):
        return {"order": list(answer)}
    if isinstance(answer, list):
        return {"answers": list(answer)}
    return {"answer": str(answer)}


def wrong_payload(exercise) -> dict | None:
    """A derived answer that must be rejected, or None when none can be derived."""
    ex_type = str(exercise.type).lower()
    answer = exercise.correct_answer
    options = [str(o) for o in (exercise.options or [])]

    if ex_type == "true_false":
        return {"answer": "False" if str(answer).lower() == "true" else "True"}
    if ex_type in ("mcq", "output_prediction", "debugging", "identify_error"):
        alternates = [o for o in options if o.strip().lower() != str(answer).strip().lower()]
        return {"answer": alternates[0]} if alternates else None
    if ex_type in MULTI_SELECT_TYPES and isinstance(answer, list) and len(answer) > 1:
        return {"answers": list(answer[:-1])}
    if ex_type in MATCHING_TYPES and isinstance(answer, dict) and len(answer) > 1:
        keys = list(answer)
        rotated = {k: answer[keys[(i + 1) % len(keys)]] for i, k in enumerate(keys)}
        return {"pairs": [{"left": k, "right": v} for k, v in rotated.items()]}
    if ex_type in ORDERING_TYPES and isinstance(answer, list) and len(answer) > 1:
        shuffled = list(reversed(answer))
        if shuffled == answer:
            shuffled = list(answer[1:] + answer[:1])
        return {"order": shuffled} if shuffled != answer else None
    if ex_type in FILL_TYPES:
        blanks = answer if isinstance(answer, list) else [answer]
        wrongs = ["__definitely_not_the_key__" for _ in blanks]
        return {"answers": wrongs} if isinstance(answer, list) else {"answer": wrongs[0]}
    return None


def iter_items():
    for language, curriculum in sorted(load_all_curriculums().items()):
        for lesson in curriculum.lessons:
            items = [ex for sub in lesson.sublessons for ex in sub.exercises]
            items += list(lesson.mastery_exam or [])
            for exercise in items:
                yield language, lesson, exercise


def main() -> int:
    engine = LessonEngine(executor=DummyExecutor(), curriculums=load_all_curriculums())
    rows, skipped = [], []
    for language, lesson, exercise in iter_items():
        ex_type = str(exercise.type).lower()
        if ex_type in CODE_TYPES:
            skipped.append(f"{exercise.id} ({ex_type}: graded by running its tests)")
            continue
        wrong = WRONG.get(exercise.id) or wrong_payload(exercise)
        if wrong is None:
            skipped.append(f"{exercise.id} ({ex_type}: no derivable wrong answer)")
            continue
        ok_right, msg_right = asyncio.run(
            engine.grade_exercise(exercise, right_payload(exercise), language))
        ok_wrong, _ = asyncio.run(engine.grade_exercise(exercise, wrong, language))
        rows.append((language, lesson.id, exercise.id, ex_type, ok_right, ok_wrong, msg_right))

    print(f"{'course':11s} {'item':26s} {'type':17s} right wrong")
    failures = []
    for lang, _lesson, ex_id, ex_type, ok_right, ok_wrong, msg in rows:
        flag = ""
        if not ok_right:
            flag = "  <-- correct answer REJECTED"
            failures.append(f"{ex_id}: right answer rejected ({msg})")
        if ok_wrong:
            flag = "  <-- wrong answer ACCEPTED"
            failures.append(f"{ex_id}: wrong answer accepted ({ex_type})")
        print(f"{lang:11s} {ex_id:26s} {ex_type:17s} {str(ok_right):5s} {str(ok_wrong):5s}{flag}")

    print(f"\ngraded both ways: {len(rows)} items | problems: {len(failures)}")
    for note in skipped:
        print(f"  skipped {note}")
    for failure in failures:
        print("  -", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
