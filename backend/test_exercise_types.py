"""Tests for the shared exercise-type registry and the auto-pass holes it closes.

Covers:
  - the Python frozensets and the TypeScript arrays cannot drift apart
  - unknown exercise types fail grading instead of passing
  - a known type with no answer key fails instead of passing
  - open-ended code exercises still accept a plain submission
"""

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.exercise_types import (
    ALL_TYPES,
    CHOICE_TYPES,
    CODE_TYPES,
    FILL_TYPES,
    MATCHING_TYPES,
    MULTI_SELECT_TYPES,
    ORDERING_TYPES,
    is_known,
    requires_answer_key,
    widget_for,
)
from backend.lesson_engine import LessonEngine

SRC = Path(__file__).resolve().parent.parent / "src" / "utils" / "exerciseTypes.ts"

PAIRS = {
    "CHOICE_TYPES": CHOICE_TYPES,
    "MULTI_SELECT_TYPES": MULTI_SELECT_TYPES,
    "ORDERING_TYPES": ORDERING_TYPES,
    "MATCHING_TYPES": MATCHING_TYPES,
    "FILL_TYPES": FILL_TYPES,
    "CODE_TYPES": CODE_TYPES,
}


def _ts_array(name: str) -> set[str]:
    match = re.search(rf"export const {name}: readonly string\[\] = \[(.*?)\]", SRC.read_text(encoding="utf-8"), re.S)
    assert match, f"{name} not found in exerciseTypes.ts"
    return set(re.findall(r"'([^']+)'", match.group(1)))


# ---------------------------------------------------------------------------
# Python / TypeScript parity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(PAIRS))
def test_frontend_and_backend_agree_on_each_type_list(name):
    assert _ts_array(name) == set(PAIRS[name]), f"{name} drifted between backend and frontend"


def test_no_type_is_listed_twice():
    sizes = {name: len(members) for name, members in PAIRS.items()}
    assert sum(sizes.values()) == len(ALL_TYPES), f"overlapping or duplicated types: {sizes}"


def test_all_types_is_the_union():
    union = set().union(*(set(members) for members in PAIRS.values()))
    assert union == set(ALL_TYPES)


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def test_short_answer_routes_to_the_choice_widget():
    # It used to be graded by the backend but absent from every frontend list.
    assert "short_answer" in CHOICE_TYPES
    assert widget_for("short_answer") == "choice"


def test_unknown_type_routes_to_unknown():
    assert widget_for("interpretive_dance") == "unknown"
    assert not is_known("interpretive_dance")


@pytest.mark.parametrize(
    "ex_type,widget",
    [
        ("mcq", "choice"),
        ("select_multiple", "multi_select"),
        ("ordering", "ordering"),
        ("matching", "matching"),
        ("fill_blank", "fill"),
        ("code_completion", "fill"),
        ("code", "code"),
        ("tiny_coding", "code"),
    ],
)
def test_every_known_type_has_a_widget(ex_type, widget):
    assert widget_for(ex_type) == widget


def test_every_choice_type_requires_an_answer_key():
    for ex_type in CHOICE_TYPES | FILL_TYPES | MULTI_SELECT_TYPES | ORDERING_TYPES | MATCHING_TYPES:
        assert requires_answer_key(ex_type), ex_type
    assert not requires_answer_key("code")


# ---------------------------------------------------------------------------
# Grading: no silent pass
# ---------------------------------------------------------------------------

def grade(exercise, payload):
    engine = LessonEngine.__new__(LessonEngine)
    return asyncio.run(engine.grade_exercise(exercise, payload, "python"))


def exercise_of(ex_type, correct_answer=None, **kwargs):
    return SimpleNamespace(
        type=ex_type,
        correct_answer=correct_answer,
        options=kwargs.get("options", []),
        pairs=kwargs.get("pairs", []),
        explanation=kwargs.get("explanation", ""),
        tests=kwargs.get("tests", []),
        solution_code=kwargs.get("solution_code", ""),
        starter_code=kwargs.get("starter_code", ""),
    )


def test_unknown_type_is_not_awarded_a_pass():
    passed, feedback = grade(exercise_of("mystery", "anything"), {"answer": "anything"})
    assert passed is False
    assert "unknown exercise type" in feedback


def test_mcq_without_an_answer_key_does_not_auto_pass():
    passed, feedback = grade(exercise_of("mcq", None, options=["a", "b"]), {"answer": "a"})
    assert passed is False
    assert "no answer key" in feedback


def test_matching_without_pairs_does_not_auto_pass():
    passed, _ = grade(exercise_of("matching", {"a": "b"}), {"pairs": []})
    assert passed is False


def test_select_multiple_requires_a_non_empty_key():
    passed, _ = grade(exercise_of("select_multiple", [], options=["a", "b"]), {"answers": []})
    assert passed is False


def test_ordering_does_not_pass_an_empty_sequence_against_no_key():
    passed, _ = grade(exercise_of("ordering", []), {"order": []})
    assert passed is False


def test_mcq_still_grades_correctly_when_keyed():
    ex = exercise_of("mcq", "gamma", options=["alpha", "gamma"])
    assert grade(ex, {"answer": "gamma"})[0] is True
    assert grade(ex, {"answer": "alpha"})[0] is False


def test_mcq_accepts_a_zero_based_option_index():
    ex = exercise_of("mcq", "gamma", options=["alpha", "gamma"])
    assert grade(ex, {"answer": "1"})[0] is True


def test_a_digit_that_is_a_visible_choice_is_the_value_not_the_position():
    """Regression: on a numeric choice list the index rule was an auto-pass.

    `lp-recall` asks what `predict(10, 0, 4)` prints with options 4/0/10/14. The
    authored wrong answer "0" is also index 0, which is the key — so the old rule
    graded a learner who had multiplied nothing as correct, and the ladder filed
    that as evidence.
    """
    ex = exercise_of("output_prediction", "4", options=["4", "0", "10", "14"])
    assert grade(ex, {"answer": "4"})[0] is True
    assert grade(ex, {"answer": "0"})[0] is False, "0 is a choice here, not a position"
    assert grade(ex, {"answer": "10"})[0] is False
    assert grade(ex, {"answer": "14"})[0] is False


def test_open_code_exercise_still_accepts_a_submission():
    ex = exercise_of("code", None, starter_code="print('hi')")
    passed, _ = grade(ex, {"code": "print('hi')"})
    assert passed is True


def test_empty_open_code_submission_is_not_a_pass():
    ex = exercise_of("code", None, starter_code="print('hi')")
    passed, _ = grade(ex, {"code": "   "})
    assert passed is False
