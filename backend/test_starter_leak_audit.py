"""Tests for backend.starter_leak_audit.

Covers:
  - ``todo_quotes_answer`` catches a TODO that is the solution line verbatim
  - ``presolved_body`` catches a body that only needs a literal swapped
  - honest skeletons (prose TODO over a placeholder body) stay clean
  - scaffolding and default declarations are not mistaken for answers
  - the shipped curriculum has zero leaks
"""

import json
from pathlib import Path

from backend.starter_leak_audit import (
    CURRICULUM_ROOT,
    LessonView,
    audit,
    audit_lesson,
    normalise,
    structure,
)


def lesson(starter, solution, description="", lesson_id="l1"):
    """Build a LessonView without touching disk."""
    payload = {
        "id": lesson_id,
        "starter_code": starter,
        "solution_code": solution,
        "description": description,
    }
    return LessonView(
        lesson=payload,
        path=Path("curriculum/test/modules/fake.json"),
        starter_lines=starter.splitlines(),
        solution_lines=solution.splitlines(),
    )


def rules(view):
    return {leak.rule for leak in audit_lesson(view)}


# ---------------------------------------------------------------------------
# Leak detection
# ---------------------------------------------------------------------------

def test_todo_comment_that_is_the_answer_is_flagged():
    view = lesson(
        "def area_of_rectangle(width, height):\n"
        '    """Calculate rectangle area."""\n'
        "    # TODO: Return width * height\n"
        "    pass\n",
        "def area_of_rectangle(width, height):\n"
        '    """Calculate rectangle area."""\n'
        "    return width * height\n",
    )
    assert "todo_quotes_answer" in rules(view)


def test_presolved_body_with_swapped_literals_is_flagged():
    view = lesson(
        "// TODO: resolve { id: userId, active: true }\n"
        "async function fetchUserData(userId) {\n"
        "    return { id: 0, active: false };\n"
        "}\n",
        "async function fetchUserData(userId) {\n"
        "    return { id: userId, active: true };\n"
        "}\n",
    )
    assert "presolved_body" in rules(view)


def test_every_leak_reports_the_lesson_and_line():
    view = lesson(
        "def get_remainder(dividend, divisor):\n"
        "    # TODO: Return dividend % divisor\n"
        "    pass\n",
        "def get_remainder(dividend, divisor):\n"
        "    return dividend % divisor\n",
    )
    leaks = [leak for leak in audit_lesson(view) if leak.rule == "todo_quotes_answer"]
    assert len(leaks) == 1
    assert leaks[0].lesson_id == "l1"
    assert leaks[0].answer == "return dividend % divisor"


# ---------------------------------------------------------------------------
# Known-good starters must stay clean
# ---------------------------------------------------------------------------

def test_prose_todo_over_placeholder_body_is_clean():
    view = lesson(
        "def get_remainder(dividend, divisor):\n"
        "    # TODO: return what is left over after dividing evenly\n"
        "    pass\n",
        "def get_remainder(dividend, divisor):\n"
        "    return dividend % divisor\n",
    )
    assert rules(view) == set()


def test_zero_placeholder_return_is_not_a_leak():
    view = lesson(
        "double circle_area(double radius) {\n"
        "    const double pi = 3.141592653589793;\n"
        "    // TODO: return the area of a circle with this radius\n"
        "    return 0.0;\n"
        "}\n",
        "double circle_area(double radius) {\n"
        "    const double pi = 3.141592653589793;\n"
        "    return pi * radius * radius;\n"
        "}\n",
    )
    assert rules(view) == set()


def test_shared_scaffolding_is_not_an_answer():
    view = lesson(
        "from dataclasses import dataclass, replace\n"
        "\n"
        "@dataclass(frozen=True)\n"
        "class Config:\n"
        "    host: str\n"
        "\n"
        "def with_port(cfg, port):\n"
        "    # TODO: return a new Config that uses the given port\n"
        "    pass\n",
        "from dataclasses import dataclass, replace\n"
        "\n"
        "@dataclass(frozen=True)\n"
        "class Config:\n"
        "    host: str\n"
        "\n"
        "def with_port(cfg, port):\n"
        "    return replace(cfg, port=port)\n",
    )
    assert rules(view) == set()


def test_prose_todo_worded_like_a_requirement_is_clean():
    """A TODO that reads as an English requirement should not trip Rule A."""
    view = lesson(
        "bool can_drive(bool has_license, bool is_sober) {\n"
        "    // TODO: return true only when both conditions hold\n"
        "    return false;\n"
        "}\n",
        "bool can_drive(bool has_license, bool is_sober) {\n"
        "    return has_license && is_sober;\n"
        "}\n",
    )
    assert rules(view) == set()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_normalise_strips_comment_markers_and_todo_label():
    assert normalise("# TODO: Return width * height") == normalise("return width * height")


def test_structure_collapses_literals_and_names():
    assert structure("return { id: 0, active: false };") == structure(
        "return { id: userId, active: true };"
    )


# ---------------------------------------------------------------------------
# Whole-curriculum regression gate
# ---------------------------------------------------------------------------

def test_shipped_curriculum_has_no_starter_leaks():
    leaks = audit(CURRICULUM_ROOT)
    assert leaks == [], "\n".join(
        f"{leak.rule} {leak.file}::{leak.lesson_id} {leak.starter_line!r}" for leak in leaks
    )


def test_audit_only_reads_curriculum_json():
    assert CURRICULUM_ROOT.name == "curriculum"
    assert (CURRICULUM_ROOT / "python" / "modules").is_dir()
    assert json.loads((CURRICULUM_ROOT / "python" / "course.json").read_text(encoding="utf-8"))


# ── answer-distribution rules ────────────────────────────────────────────────

def _curriculum(tmp_path: Path, exercises: list[dict]) -> Path:
    """Write a throwaway curriculum tree and return its root.

    The distribution rules look across the whole curriculum, so they need real
    files on disk - and they must never read the shipped one when under test.
    """
    root = tmp_path / "curriculum"
    module = root / "testcourse" / "modules"
    module.mkdir(parents=True)
    payload = {
        "course": {
            "id": "testcourse",
            "language": "testcourse",
            "title": "Test course",
            "tagline": "t",
            "description": "d",
            "difficulty": "beginner",
        },
        "lessons": [{
            "id": "l1",
            "title": "Lesson one",
            "description": "Write a function that adds two numbers and returns.",
            "order": 1,
            "difficulty": "beginner",
            "duration_minutes": 5,
            "type": "learn",
            "sublessons": [{"id": "s1", "title": "Step", "order": 1,
                            "exercises": exercises}],
        }],
    }
    (module / "m1.json").write_text(json.dumps(payload), encoding="utf-8")
    return root


def _tf(answer: str, index: int) -> dict:
    return {"id": f"tf-{index}", "type": "true_false",
            "question": f"Statement number {index} about adding two numbers.",
            "options": ["True", "False"], "correct_answer": answer}


def test_true_false_polarity_flags_a_one_sided_set(tmp_path):
    root = _curriculum(tmp_path, [_tf("True", 1), _tf("True", 2), _tf("True", 3)])
    hits = [leak for leak in audit(root) if leak.rule == "true_false_polarity"]
    assert hits, "three items all answering True must be flagged"
    assert "3/3" in hits[0].lesson_id


def test_true_false_polarity_passes_a_balanced_set(tmp_path):
    root = _curriculum(tmp_path, [_tf("True", 1), _tf("False", 2)])
    assert not [leak for leak in audit(root) if leak.rule == "true_false_polarity"]


def test_true_false_polarity_ignores_a_single_item(tmp_path):
    root = _curriculum(tmp_path, [_tf("True", 1)])
    assert not [leak for leak in audit(root) if leak.rule == "true_false_polarity"]


def test_mcq_position_bias_flags_every_answer_in_slot_one(tmp_path):
    exercises = [
        {"id": f"m{i}", "type": "mcq",
         "question": f"Which of these describes operation number {i}?",
         "options": ["alpha", "beta", "gamma"], "correct_answer": "alpha"}
        for i in range(6)
    ]
    root = _curriculum(tmp_path, exercises)
    hits = [leak for leak in audit(root) if leak.rule == "mcq_answer_position_bias"]
    assert hits, "an MCQ set that always answers option 1 must be flagged"


def test_mcq_position_bias_passes_a_spread_of_positions(tmp_path):
    options = ["alpha", "beta", "gamma"]
    exercises = [
        {"id": f"m{i}", "type": "mcq",
         "question": f"Which of these describes operation number {i}?",
         "options": options, "correct_answer": options[i % 3]}
        for i in range(6)
    ]
    root = _curriculum(tmp_path, exercises)
    assert not [leak for leak in audit(root) if leak.rule == "mcq_answer_position_bias"]


def test_shipped_curriculum_has_balanced_answer_distributions():
    """The shipped set must satisfy both distribution rules.

    Wave 1 measurement found every true/false item answering True, so this is
    the regression that keeps a future author from re-creating that pattern.
    """
    rules = {leak.rule for leak in audit(CURRICULUM_ROOT)}
    assert "true_false_polarity" not in rules
    assert "mcq_answer_position_bias" not in rules


def test_answer_position_bias_flags_a_unanimous_small_set(tmp_path):
    """3 of 3 in one slot is degenerate, not a small-sample coincidence."""
    exercises = [
        {"id": f"d{i}", "type": "debugging",
         "question": f"Which line is wrong in program number {i}?",
         "options": ["the first comparison", "the return", "the loop bound"],
         "correct_answer": "the first comparison"}
        for i in range(3)
    ]
    root = _curriculum(tmp_path, exercises)
    hits = [leak for leak in audit(root) if leak.rule == "answer_position_bias"]
    assert hits, "every debugging item answering option 1 must be flagged"


def test_answer_position_bias_ignores_a_spread_set(tmp_path):
    options = ["the first comparison", "the return", "the loop bound"]
    exercises = [
        {"id": f"d{i}", "type": "debugging",
         "question": f"Which line is wrong in program number {i}?",
         "options": options, "correct_answer": options[i % 3]}
        for i in range(6)
    ]
    root = _curriculum(tmp_path, exercises)
    assert not [leak for leak in audit(root) if leak.rule == "answer_position_bias"]


def test_shipped_curriculum_balances_answer_positions_per_type():
    rules = {leak.rule for leak in audit(CURRICULUM_ROOT)}
    assert "answer_position_bias" not in rules
