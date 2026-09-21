"""Step pools are validated on load, because a bad step reaches a learner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend import step_pool
from backend.step_pool import load_pool

REAL_POOL = Path(__file__).resolve().parents[1] / "curriculum" / "ml" / "steps" / "linear-prediction.json"
MSE_POOL = Path(__file__).resolve().parents[1] / "curriculum" / "ml" / "steps" / "measuring-error.json"
SHIPPED_POOLS = pytest.mark.parametrize("path", [REAL_POOL, MSE_POOL], ids=["linear-prediction", "measuring-error"])


def pool_dict(**over) -> dict:
    base = {
        "skill": "test-skill",
        "lesson": "test-lesson",
        "concept": "test-concept",
        "steps": [
            {
                "id": "teach-me",
                "stage": "interact",
                "widget": "mcq",
                "question": "2 * 3 + 1?",
                "options": ["7", "6"],
                "correct_answer": "7",
                "feedback": {"6": "Multiply first, then add."},
            }
        ],
    }
    base.update(over)
    return base


def write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "pool.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@SHIPPED_POOLS
def test_a_shipped_pool_loads_and_validates(path):
    """Every pool that ships is one a learner can actually be handed.

    Both real pools run through the same gates: this is the check that a second
    authored concept did not slip past the rules the first one was written under.
    """
    pool = load_pool(path)
    assert len(pool.steps) >= 10
    assert {s["stage"] for s in pool.steps} >= {"introduce", "show", "interact", "guided",
                                                "scaffolded", "independent", "explain", "transfer"}
    # The ladder teaches exactly one concept; anything else is a retrieval hook.
    for step in pool.steps:
        foreign = (step.get("concept") or pool.concept) != pool.concept
        assert not foreign or step["stage"] == "review", (
            f"{step['id']} reaches outside {pool.concept} without being a review rung"
        )


def test_the_two_shipped_pools_teach_different_concepts():
    """Proves the architecture generalises rather than special-casing one lesson."""
    predict, mse = load_pool(REAL_POOL), load_pool(MSE_POOL)
    assert (predict.lesson_id, predict.concept) == ("linreg-predict", "linear-prediction")
    assert (mse.lesson_id, mse.concept) == ("linreg-mse", "measuring-error")
    assert mse.steps[0]["concept"] == predict.concept, "the causal link is authored, not implied"


def test_a_step_cannot_reach_another_concept_through_a_teaching_rung(tmp_path):
    """Foreign material may only be retrieved, never taught or charged against.

    Authoring `independent` under another concept would spend a learner's heart on
    a lesson that never undertook to teach them that thing.
    """
    with pytest.raises(ValueError, match="must be stage 'review'"):
        load_pool(write(tmp_path, pool_dict(steps=[{
            "id": "steal", "concept": "some-other-lesson", "stage": "interact",
            "widget": "mcq", "question": "q", "options": ["1", "2"],
            "correct_answer": "1", "feedback": {"2": "no"},
        }])))


def test_a_review_rung_must_explain_a_wrong_answer_too(tmp_path):
    with pytest.raises(ValueError, match="per-answer feedback"):
        load_pool(write(tmp_path, pool_dict(steps=[{
            "id": "bare-recall", "stage": "review", "widget": "mcq",
            "question": "q", "options": ["1", "2"], "correct_answer": "1",
        }])))


def test_a_gradable_step_without_the_key_its_widget_needs_is_refused(tmp_path):
    """'blanks' is not a key for code_completion; the grader reads correct_answer.

    The failure mode this guards is the worst one available: a learner answers
    correctly and the server reports it could not be scored.
    """
    payload = pool_dict(steps=[{
        "id": "sneaky-fill", "stage": "scaffolded", "widget": "code_completion",
        "question": "finish it", "blanks": ["x"], "starter_code": "x = ___\n",
        "feedback": {"hint": "try it"},
    }])
    with pytest.raises(ValueError, match="correct_answer"):
        load_pool(write(tmp_path, payload))

    fixed = pool_dict(steps=[dict(payload["steps"][0], correct_answer=["x"])])
    assert load_pool(write(tmp_path, fixed)).steps[0]["id"] == "sneaky-fill"


def test_an_ungradable_code_step_is_refused(tmp_path):
    payload = pool_dict(steps=[{
        "id": "bare-code", "stage": "independent", "widget": "code",
        "question": "write it", "starter_code": "def f():\n    pass\n",
    }])
    with pytest.raises(ValueError, match="tests or a solution_code"):
        load_pool(write(tmp_path, payload))


def test_a_teaching_rung_cannot_be_authored_as_charged(tmp_path):
    """The rung decides stakes, so an author claiming otherwise is a mistake."""
    payload = pool_dict(steps=[{
        "id": "mean-intro", "stage": "interact", "widget": "mcq", "stakes": "charged",
        "question": "2 * 3 + 1?", "options": ["7", "6"], "correct_answer": "7",
        "feedback": {"6": "Multiply first."},
    }])
    with pytest.raises(ValueError, match="free to fail"):
        load_pool(write(tmp_path, payload))


def test_a_wrongable_step_with_no_feedback_is_refused(tmp_path):
    payload = pool_dict(steps=[{
        "id": "silent-mcq", "stage": "interact", "widget": "mcq",
        "question": "2 * 3 + 1?", "options": ["7", "6"], "correct_answer": "7",
    }])
    with pytest.raises(ValueError, match="per-answer feedback"):
        load_pool(write(tmp_path, payload))


def test_dangling_remediation_and_duplicate_ids_are_caught(tmp_path):
    with pytest.raises(ValueError, match="unknown step"):
        load_pool(write(tmp_path, pool_dict(steps=[
            {"id": "a", "stage": "interact", "widget": "mcq", "question": "q",
             "options": ["1", "2"], "correct_answer": "1", "feedback": {"2": "no"},
             "remediation_of": "does-not-exist"},
        ])))
    with pytest.raises(ValueError, match="duplicate id"):
        dup = {"id": "a", "stage": "interact", "widget": "mcq", "question": "q",
               "options": ["1", "2"], "correct_answer": "1", "feedback": {"2": "no"}}
        load_pool(write(tmp_path, pool_dict(steps=[dup, dict(dup)])))


def test_an_unknown_stage_or_widget_is_refused(tmp_path):
    with pytest.raises(ValueError, match="unknown stage"):
        load_pool(write(tmp_path, pool_dict(steps=[{
            "id": "weird", "stage": "vibes", "widget": "mcq", "question": "q",
            "options": ["1"], "correct_answer": "1", "feedback": {"x": "y"},
        }])))
    with pytest.raises(ValueError, match="does not know"):
        load_pool(write(tmp_path, pool_dict(steps=[{
            "id": "weird", "stage": "interact", "widget": "telepathy", "question": "q",
            "correct_answer": "1",
        }])))


def test_a_lesson_without_a_pool_has_no_session(tmp_path):
    step_pool.clear_pool_cache()
    assert step_pool.pool_for_lesson("python", "variables-step-1") is None
    assert step_pool.has_session("ml", "linreg-predict") is True
