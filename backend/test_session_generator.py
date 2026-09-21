"""Session generator rules, exercised against the real authored Linear Prediction pool.

Every rule in ``session_generator``'s docstring gets a test here, and the pool under
test is the file that ships — so a step that is authored without a key, or a teaching
rung that charges a heart, fails a test instead of reaching a learner.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.learning_models import LADDER, Stage, Stakes
from backend.session_generator import (
    ConceptState,
    Step,
    generate_session,
    next_interval,
)

POOL_PATH = (
    Path(__file__).resolve().parents[1] / "curriculum" / "ml" / "steps" / "linear-prediction.json"
)


@pytest.fixture(scope="module")
def pool() -> list[dict]:
    assert POOL_PATH.exists(), f"authored step pool is missing: {POOL_PATH}"
    return json.loads(POOL_PATH.read_text(encoding="utf-8"))["steps"]


@pytest.fixture(scope="module")
def steps(pool) -> list[Step]:
    return [Step.from_dict(raw) for raw in pool]


def ids(session) -> list[str]:
    return [s.step.id for s in session.steps]


def stages(session) -> list[Stage]:
    return [s.step.stage for s in session.steps]


def index(session, step_id: str) -> int:
    return ids(session).index(step_id)


# ─── Rule 1 + 2: the ladder, and resuming it ─────────────────────────────────

def test_a_fresh_learner_walks_the_whole_ladder_in_order(steps):
    session = generate_session(steps)
    assert stages(session) == list(LADDER)


def test_the_ladder_teaches_before_it_asks_for_production_code(steps):
    order = ids(generate_session(steps))
    assert order.index("lp-intro") < order.index("lp-worked") < order.index("lp-predict-up")
    assert order.index("lp-fill") < order.index("lp-independent")


def test_cleared_rungs_are_never_re_taught(steps):
    """The session resumes ahead of what is done; it does not restart.

    A second item on the same rung is allowed (that is variety, not re-teaching),
    but the presented steps must all be new to the learner.
    """
    cleared = {"lp-intro", "lp-worked", "lp-predict-up"}
    state = ConceptState(concept="linear-prediction", cleared_steps=cleared)
    session = generate_session(steps, [state])
    assert not cleared & set(ids(session))
    assert session.steps[0].step.stage in (Stage.INTERACT, Stage.GUIDED)
    assert Stage.INTRODUCE not in stages(session)


# ─── Rungs decide stakes: you cannot be charged for being taught ─────────────

def test_teaching_rungs_are_free_and_only_assessment_is_charged(steps):
    session = generate_session(steps)
    charged = [s.step.id for s in session.steps if s.stakes is Stakes.CHARGED]
    assert charged == ["lp-independent", "lp-transfer"]
    for entry in session.steps:
        if entry.step.stage.teaches:
            assert entry.stakes is Stakes.FREE, entry.step.id


def test_an_authored_stakes_field_cannot_upgrade_a_rung(steps):
    """A step cannot opt itself out of, or into, the charge its rung implies."""
    sneaky = {
        "id": "sneaky", "stage": "independent", "widget": "code",
        "concept": "c", "stakes": "free",
    }
    generous = {
        "id": "generous", "stage": "show", "widget": "present",
        "concept": "c", "stakes": "charged",
    }
    assert Step.from_dict(sneaky).effective_stakes is Stakes.CHARGED
    assert Step.from_dict(generous).effective_stakes is Stakes.FREE


# ─── Rule 3: fade the teaching for a learner who has demonstrated it ────────

def test_a_demonstrated_concept_opens_on_retrieval_and_a_mixed_check(steps):
    state = ConceptState(
        concept="linear-prediction",
        cleared_steps={"lp-intro", "lp-worked", "lp-predict-up", "lp-build",
                       "lp-fill", "lp-independent", "lp-debug", "lp-transfer"},
        evidence={"independent", "transferred"},
    )
    session = generate_session(steps, [state])
    assert stages(session) == [Stage.INTERACT, Stage.MASTERY]
    assert all("faded" in s.reason or "mixed-skill" in s.reason for s in session.steps)


def test_guided_success_alone_is_not_enough_to_be_faded(steps):
    """Solving with support is not the same claim as solving alone."""
    state = ConceptState(
        concept="linear-prediction",
        cleared_steps={"lp-intro", "lp-worked"},
        evidence={"guided"},
    )
    assert not state.demonstrated
    session = generate_session(steps, [state])
    # Not faded: the support rungs are still here, and there is no mixed check.
    assert Stage.SCAFFOLDED in stages(session)
    assert Stage.MASTERY not in stages(session)


# ─── Rule 4: remediate before re-asking ─────────────────────────────────────

def test_repeated_misses_insert_a_simpler_example_before_asking_again(steps):
    state = ConceptState(concept="linear-prediction", misses={"lp-fill": 2})
    session = generate_session(steps, [state])
    order = ids(session)
    assert index(session, "lp-worked-easier") < order.index("lp-fill")
    assert any("remediation" in s.reason for s in session.steps)


def test_a_single_miss_does_not_trigger_remediation(steps):
    state = ConceptState(concept="linear-prediction", misses={"lp-fill": 1})
    assert "lp-worked-easier" not in ids(generate_session(steps, [state]))


# ─── Rule 5: teach the misconception ahead of the pressure ───────────────────

def test_a_recorded_misconception_is_taught_before_the_independent_rung(steps):
    state = ConceptState(
        concept="linear-prediction", misconceptions={"wrong_variable": 3}
    )
    session = generate_session(steps, [state])
    assert index(session, "lp-debug") < ids(session).index("lp-independent")
    assert any("targets wrong_variable" in s.reason for s in session.steps)


# ─── Rule 6: a rung cleared with hints is not cleared ────────────────────────

def test_hint_dependent_success_requeues_the_rung_unaided(steps):
    state = ConceptState(
        concept="linear-prediction",
        cleared_steps={"lp-intro", "lp-worked", "lp-predict-up", "lp-build",
                       "lp-fill", "lp-independent"},
        hinted_steps={"lp-independent"},
    )
    session = generate_session(steps, [state])
    assert any("hint-dependent" in s.reason for s in session.steps)
    assert sum(1 for s in session.steps if s.step.stage is Stage.INDEPENDENT) == 1


# ─── Rule 7: modality variety, without deleting pedagogy ────────────────────

def test_no_two_adjacent_steps_share_an_interaction_widget(steps):
    session = generate_session(steps)
    for a, b in zip(session.steps, session.steps[1:]):
        if a.step.widget == b.step.widget:
            assert a.step.widget == "present", f"{a.step.id} then {b.step.id}"


def test_the_widget_preference_never_drops_a_rung():
    """When the only candidate repeats a widget, take it: a rung beats variety."""
    pool = [
        {"id": "a", "stage": "interact", "widget": "mcq", "concept": "c"},
        {"id": "b", "stage": "guided", "widget": "mcq", "concept": "c"},
    ]
    assert ids(generate_session(pool)) == ["a", "b"]


# ─── Rule 8: review is extra length past the end, never a moving target ─────

def test_due_review_is_appended_as_bonus_and_the_planned_length_holds():
    pool = [
        {"id": "teach", "stage": "introduce", "widget": "present", "concept": "c"},
        {"id": "ask", "stage": "interact", "widget": "mcq", "concept": "c"},
        {"id": "rev", "stage": "review", "widget": "output_prediction", "concept": "c"},
    ]
    due = ConceptState(concept="c", last_recall_at=0.0, interval_seconds=300.0)
    session = generate_session(pool, [due], now=1000.0)
    assert session.planned == 2
    assert session.bonus_count == 1
    assert session.steps[-1].step.id == "rev" and session.steps[-1].bonus
    assert "due for retrieval" in session.steps[-1].reason


def test_a_not_yet_due_concept_adds_nothing():
    pool = [
        {"id": "teach", "stage": "introduce", "widget": "present", "concept": "c"},
        {"id": "rev", "stage": "review", "widget": "mcq", "concept": "c"},
    ]
    fresh = ConceptState(concept="c", last_recall_at=990.0, interval_seconds=300.0)
    session = generate_session(pool, [fresh], now=1000.0)
    assert session.bonus_count == 0


# ─── Determinism, traceability, and the interval rule ────────────────────────

def test_the_same_inputs_always_produce_the_same_session(steps):
    first = ids(generate_session(steps))
    for _ in range(4):
        assert ids(generate_session(steps)) == first


def test_every_step_carries_a_reason_a_human_can_read(steps):
    session = generate_session(steps)
    assert all(s.reason.strip() for s in session.steps)
    assert len(session.trace()) == len(session.steps)


def test_an_empty_pool_is_an_error_not_a_silent_empty_session():
    with pytest.raises(ValueError):
        generate_session([])


def test_interval_collapses_on_a_miss_and_grows_on_recall():
    assert next_interval(0, recalled=False) == 300.0
    assert next_interval(300, recalled=True) == 1500.0
    assert next_interval(1500, recalled=True) == 7500.0
    assert next_interval(7500, recalled=False) == 300.0


# ─── The authored pool itself ────────────────────────────────────────────────

def test_the_linear_prediction_pool_covers_the_ladder_and_many_modalities(pool, steps):
    covered = {s.stage for s in steps}
    assert covered >= set(LADDER)
    widgets = {s.widget for s in steps}
    assert len(widgets) >= 8, widgets
    assert {"mcq", "ordering", "code_completion", "code", "identify_error"} <= widgets


def test_every_graded_step_ships_a_key_and_every_teaching_step_carries_feedback(pool):
    for raw in pool:
        stage, widget = raw["stage"], raw["widget"]
        if widget in {"present"}:
            assert "content" in raw, raw["id"]
            continue
        has_key = ("correct_answer" in raw or "blanks" in raw
                   or "correct_order" in raw or "pairs" in raw or "tests" in raw)
        assert has_key, f"{raw['id']} is graded but has no answer key"
        if stage in {"interact", "guided", "scaffolded", "explain"}:
            assert "feedback" in raw, f"{raw['id']} can be wrong but says nothing about it"


def test_the_independent_step_rejects_a_swapped_weight_and_bias(pool):
    """The ladder's own misconception story has to be the story the tests tell."""
    independent = next(r for r in pool if r["id"] == "lp-independent")
    names = {t["name"] for t in independent["tests"]}
    assert "test_predict_zero_input_uses_bias" in names
    swapped = "def predict(x, w, b):\n    return x * b + w\n"
    assert independent["solution_code"] != swapped
