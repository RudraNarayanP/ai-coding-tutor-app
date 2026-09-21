"""Whole-curriculum health checks that no other gate performs.

`validate_curriculum.py` covers structure and per-exercise shape, and
`starter_leak_audit.py` covers answer spoilers. This closes the remaining gaps
that were previously unchecked across the whole repository of courses:

  - every exercise type in the curriculum maps to a real frontend widget
  - no exercise is presented in its own answer order (ordering items)
  - no placeholder or template text reached a learner
  - exercise ids are unique per course, including across mastery exams
"""

import json
import re

import pytest

from backend.curriculum_loader import load_all_curriculums
from backend.exercise_types import ALL_TYPES, widget_for
from backend.starter_leak_audit import iter_exercises, iter_step_exercises

CURRICULUMS = load_all_curriculums()

PLACEHOLDER_PATTERNS = [
    r"\blorem ipsum\b",
    r"\bplaceholder\b",
    r"\bTBD\b",
    r"\bFIXME\b",
    r"\bXXX\b",
    r"\bsolution code for\b",
    r"\breview solution\b",
    r"\bwrite your code solution below\b",
    r"\bexample\.com\b",
    r"\byour (?:answer|code) here\b",
]


def all_exercises():
    for language, curriculum in sorted(CURRICULUMS.items()):
        for lesson in curriculum.lessons:
            for sub in lesson.sublessons:
                for exercise in sub.exercises:
                    yield language, lesson.id, exercise
            for exercise in lesson.mastery_exam:
                yield language, lesson.id, exercise


EXERCISES = list(all_exercises())
TYPES_PRESENT = sorted({str(ex.type).lower().strip() for _l, _i, ex in EXERCISES})


# ---------------------------------------------------------------------------
# Coverage sanity: the suite must actually be looking at the whole curriculum
# ---------------------------------------------------------------------------

def test_every_course_is_represented_in_the_loaded_curriculums():
    assert len(CURRICULUMS) >= 11, f"only {sorted(CURRICULUMS)} loaded"
    assert sum(len(c.lessons) for c in CURRICULUMS.values()) > 300


def test_there_are_exercises_to_check():
    assert len(EXERCISES) >= 40, f"only {len(EXERCISES)} exercises found"


# ---------------------------------------------------------------------------
# No dead widgets
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ex_type", TYPES_PRESENT)
def test_every_type_in_use_has_a_frontend_widget(ex_type):
    assert ex_type in ALL_TYPES, f"'{ex_type}' is not in the shared type registry"
    assert widget_for(ex_type) != "unknown", f"'{ex_type}' would render no input"


def test_no_exercise_type_is_declared_but_unrenderable():
    unknown = [
        f"{language}/{lesson_id}/{exercise.id}: {exercise.type}"
        for language, lesson_id, exercise in EXERCISES
        if widget_for(exercise.type) == "unknown"
    ]
    assert unknown == []


# ---------------------------------------------------------------------------
# Ordering items must not leak the order
# ---------------------------------------------------------------------------

def test_ordering_options_are_never_already_in_answer_order():
    offenders = []
    for language, lesson_id, exercise in EXERCISES:
        if str(exercise.type).lower() != "ordering":
            continue
        key = [str(x) for x in (exercise.correct_answer or [])]
        shown = [str(x) for x in exercise.options]
        if shown == key:
            offenders.append(f"{language}/{lesson_id}/{exercise.id}")
    assert offenders == [], f"ordering items presented in solution order: {offenders}"


def test_ordering_items_offer_the_same_blocks_as_the_answer():
    for language, lesson_id, exercise in EXERCISES:
        if str(exercise.type).lower() != "ordering":
            continue
        key = sorted(str(x) for x in (exercise.correct_answer or []))
        shown = sorted(str(x) for x in exercise.options)
        ref = f"{language}/{lesson_id}/{exercise.id}"
        assert key == shown, f"{ref} shows blocks that are not the answer's"
        assert len(key) >= 3, f"{ref} is too short to test sequencing"
        assert len(set(key)) == len(key), f"{ref} has duplicate blocks"


# ---------------------------------------------------------------------------
# No placeholder content
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("language,lesson_id,exercise", EXERCISES,
                         ids=[f"{l}:{e.id}" for l, _i, e in EXERCISES])
def test_no_placeholder_text_reaches_the_learner(language, lesson_id, exercise):
    haystack = " ".join(
        str(getattr(exercise, field, "") or "")
        for field in ("question", "title", "explanation", "micro_explanation",
                      "worked_example_takeaway", "starter_code")
    )
    for pattern in PLACEHOLDER_PATTERNS:
        assert not re.search(pattern, haystack, re.I), (
            f"{language}/{lesson_id}/{exercise.id} contains {pattern!r}"
        )


def test_no_lesson_starter_is_labelled_as_a_solution():
    offenders = []
    for language, curriculum in sorted(CURRICULUMS.items()):
        for lesson in curriculum.lessons:
            starter = lesson.starter_code or ""
            if re.search(r"#\s*solution code|review solution", starter, re.I):
                offenders.append(f"{language}/{lesson.id}")
    assert offenders == []


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def test_exercise_ids_are_unique_within_each_course():
    seen: dict[str, set[str]] = {}
    for language, curriculum in sorted(CURRICULUMS.items()):
        ids: set[str] = set()
        for lesson in curriculum.lessons:
            for sub in lesson.sublessons:
                for exercise in sub.exercises:
                    assert exercise.id not in ids, f"{language}: dup {exercise.id}"
                    ids.add(exercise.id)
            for exercise in lesson.mastery_exam:
                assert exercise.id not in ids, f"{language}: dup exam {exercise.id}"
                ids.add(exercise.id)
        seen[language] = ids
    assert sum(len(v) for v in seen.values()) == len(EXERCISES)


# ---------------------------------------------------------------------------
# Grading preconditions, checked without a sandbox
# ---------------------------------------------------------------------------

def test_every_answer_keyed_exercise_actually_has_a_key():
    from backend.exercise_types import requires_answer_key

    offenders = []
    for language, lesson_id, exercise in EXERCISES:
        if not requires_answer_key(exercise.type):
            continue
        answer = exercise.correct_answer
        empty = answer is None or answer == "" or (
            isinstance(answer, (list, dict)) and len(answer) == 0
        )
        if exercise.type.lower() == "matching" and exercise.pairs:
            empty = False
        if empty:
            offenders.append(f"{language}/{lesson_id}/{exercise.id} ({exercise.type})")
    assert offenders == [], f"ungradeable exercises: {offenders}"


def test_curriculum_json_is_readable_by_the_same_path_the_audit_uses():
    # The leak audit walks raw JSON; make sure that view agrees with the loader
    # so a file the loader skips cannot hide a leak.
    # iter_exercises yields (lesson, exercise, path) straight from the JSON files.
    raw = {(lesson.get("id"), exercise.get("id")) for lesson, exercise, _p in iter_exercises()}
    loaded = {(lesson_id, exercise.id) for _l, lesson_id, exercise in EXERCISES}
    # Ladder steps are content the audit must also see, and they are not in the
    # loader's lesson list because a step pool is not a lesson. Subtracting them
    # keeps the agreement assertion about the thing it was written for: a lesson
    # file the loader silently skips would still hide its leaks here.
    steps = {(lesson.get("id"), exercise.get("id")) for lesson, exercise, _p in iter_step_exercises()}
    assert loaded == raw - steps, "the loader and the raw-JSON audit disagree about what exists"
    assert steps <= raw
    assert len(steps) >= 20, f"only {len(steps)} step items reached the audit view"
