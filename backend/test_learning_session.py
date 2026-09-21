"""The teaching ladder, end to end, from a fresh learner's state.

This is the acceptance test from the transformation brief: a learner who knows
nothing about linear prediction must not be met with "Implement predict()". They
meet the idea, compute it by hand, predict with it, assemble it, finish it, and
only then write it — and nothing they do on the way costs them a heart.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend import step_pool
from backend.main import app, heart_store, lesson_engine

LESSON = "linreg-predict"


CONCEPT = "linear-prediction"


def _fresh_learner() -> None:
    """Wipe the ladder state, so each test really starts from a new learner.

    The store is a process-wide singleton pointed at one throwaway directory for
    the whole run, so without this the second test inherits the first learner's
    progress — and the brief's acceptance question is specifically about a learner
    who has never seen the concept.
    """
    store = lesson_engine.stores.get("ml", lesson_engine.store)
    store.set_concept_state(CONCEPT, {})


@pytest.fixture(autouse=True)
def isolated_ladder():
    """Pools are cached per language, hearts and concepts are process-global."""
    step_pool.clear_pool_cache()
    _fresh_learner()
    heart_store.refill()
    heart_store.set_unlimited(False)
    yield
    _fresh_learner()
    step_pool.clear_pool_cache()
    # Hearts are process-global on a module that is imported once per run, so a
    # test that empties the pool would otherwise starve the modules after it.
    heart_store.set_unlimited(False)
    heart_store.refill()


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def session_of(client) -> dict:
    response = client.get(f"/api/lessons/{LESSON}/session")
    assert response.status_code == 200, response.text
    return response.json()


def stages(steps: list[dict]) -> list[str]:
    return [s["stage"] for s in steps]


# ─── Part 39: teach before you test ──────────────────────────────────────────

def test_a_fresh_learner_is_taught_before_being_asked_for_code(client):
    session = session_of(client)
    order = stages(session["steps"])

    assert order[:3] == ["introduce", "show", "interact"], order
    first_editor = order.index("scaffolded")
    independent = order.index("independent")
    assert first_editor > 1, "an editor step arrived before any worked example"
    assert independent > order.index("guided"), "asked to produce code before assembling it"

    # The very first thing on screen is an idea, not a task.
    opening = session["steps"][0]
    assert opening["stage"] == "introduce"
    assert opening["content"]["formula"]
    assert "Implement" not in (opening.get("question") or "")
    assert opening["stakes"] == "free"


def test_the_ladder_asks_for_production_only_after_four_rungs_of_support(client):
    session = session_of(client)
    charged = [s["id"] for s in session["steps"] if s["stakes"] == "charged"]
    assert charged == ["lp-independent", "lp-transfer"]
    assert session["planned_steps"] == 8


def test_the_lesson_story_says_why_the_next_concept_exists(client):
    session = session_of(client)
    assert "wrong" in session["story"]["why_next"].lower() or session["story"]["why_next"]
    assert session["objective"]


# ─── Presentation steps are acknowledged, not graded ─────────────────────────

def test_a_presentation_step_cannot_be_attempted(client):
    response = client.post(
        f"/api/lessons/{LESSON}/steps/lp-intro/attempt",
        json={"payload": {"answer": "whatever"}},
    )
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["error"] == "step_not_gradable"


def test_marking_a_rung_seen_resumes_the_session_ahead_of_it(client):
    assert client.post(f"/api/lessons/{LESSON}/steps/lp-intro/seen").status_code == 200
    session = session_of(client)
    assert "lp-intro" not in [s["id"] for s in session["steps"]]
    assert session["steps"][0]["stage"] == "show"


def test_acknowledging_a_rung_awards_no_xp(client):
    body = client.post(f"/api/lessons/{LESSON}/steps/lp-intro/seen").json()
    assert body["xp_awarded"] == 0


# ─── Failing while learning is free ─────────────────────────────────────────

def test_a_wrong_answer_on_a_teaching_rung_costs_nothing_and_explains_itself(client):
    before = heart_store.status().hearts
    response = client.post(
        f"/api/lessons/{LESSON}/steps/lp-predict-up/attempt",
        json={"payload": {"answer": "9"}},
    )
    body = response.json()
    assert body["passed"] is False
    assert body["charging"] is False
    assert heart_store.status().hearts == before
    # The authored repair for that specific wrong turn, not "Not quite".
    assert "Multiply first" in body["feedback"]


def test_a_wrong_answer_on_a_teaching_rung_still_offers_the_retry(client):
    body = client.post(
        f"/api/lessons/{LESSON}/steps/lp-fill/attempt",
        json={"payload": {"answers": ["b"], "code": "def predict(x, w, b):\n    return w * b + b\n"}},
    ).json()
    assert body["passed"] is False
    assert body["feedback"], "a graded step answered wrongly with nothing to say about it"


def test_an_empty_heart_pool_still_lets_a_learner_read_and_practise(client):
    status = heart_store.status()
    while status.hearts > 0:
        status = heart_store.consume()

    free = client.post(
        f"/api/lessons/{LESSON}/steps/lp-predict-up/attempt",
        json={"payload": {"answer": "14"}},
    )
    assert free.status_code == 200, free.text
    assert free.json()["passed"] is True

    charged = client.post(
        f"/api/lessons/{LESSON}/steps/lp-independent/attempt",
        json={"payload": {"code": "def predict(x, w, b):\n    return w * x + b\n"}},
    )
    assert charged.status_code == 403
    assert charged.json()["detail"]["error"] == "out_of_hearts"
    heart_store.refill()


# ─── Evidence, not percentages ───────────────────────────────────────────────

def _clear(client, step_id, payload, hints=0):
    response = client.post(
        f"/api/lessons/{LESSON}/steps/{step_id}/attempt",
        json={"payload": payload, "hints_used": hints},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_supported_success_is_not_evidence_and_keeps_the_teaching(client):
    for rung, payload in (
        ("lp-predict-up", {"answer": "14"}),
        ("lp-build", {"order": ["w = 2", "x = 3", "prediction = w * x + b", "print(prediction)"]}),
        ("lp-fill", {"answers": ["x"], "code": "def predict(x, w, b):\n    return w * x + b\n"}),
    ):
        body = _clear(client, rung, payload)
        assert body["passed"] is True

    # Guided/scaffolded success contributes no evidence kind at all.
    session = session_of(client)
    assert session["evidence"] == []
    assert not session["demonstrated"]


def test_clearing_the_independent_rung_with_hints_does_not_count(client):
    body = _clear(
        client, "lp-independent",
        {"code": "def predict(x, w, b):\n    return w * x + b\n"}, hints=2,
    )
    assert body["passed"] is True
    assert "independent" not in body["evidence"], body["evidence"]
    # ...and the ladder re-queues the rung unaided rather than fading onward.
    assert any(s["stage"] == "independent" for s in body["session"]["steps"])


def test_independent_then_transfer_demonstrates_the_concept(client):
    client.post(f"/api/lessons/{LESSON}/steps/lp-intro/seen")
    client.post(f"/api/lessons/{LESSON}/steps/lp-worked/seen")
    _clear(client, "lp-predict-up", {"answer": "14"})
    _clear(client, "lp-match-symbols", {"pairs": {}})  # graded on keys; may be wrong
    _clear(client, "lp-build", {"order": ["w = 2", "x = 3", "prediction = w * x + b", "print(prediction)"]})
    _clear(client, "lp-fill", {"answers": ["x"], "code": "def predict(x, w, b):\n    return w * x + b\n"})
    independent = _clear(client, "lp-independent", {"code": "def predict(x, w, b):\n    return w * x + b\n"})
    assert "independent" in independent["evidence"]
    assert independent["xp_awarded"] > 0

    debug = _clear(
        client, "lp-debug",
        {"answer": "x and b are multiplied, so the input is scaled by the bias"},
    )
    assert debug["passed"] is True

    transfer = _clear(client, "lp-transfer", {"code": "def total(items, price, fee):\n    return price * items + fee\n"})
    assert transfer["lesson_completed"] is True
    assert "transferred" in transfer["evidence"]
    assert transfer["demonstrated"] is True

    concepts = client.get("/api/concepts", params={"language": "ml"}).json()
    row = next(c for c in concepts["concepts"] if c["concept"] == "linear-prediction")
    assert row["demonstrated"] is True
    assert concepts["demonstrated"] >= 1


# ─── Unknown ids stay graceful ───────────────────────────────────────────────

def test_a_lesson_without_authored_steps_says_so_rather_than_500(client):
    response = client.get("/api/lessons/no-such-lesson/session")
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "lesson_not_found"


def test_an_unknown_step_is_a_404(client):
    assert client.post(f"/api/lessons/{LESSON}/steps/nope/seen").status_code == 404
    response = client.post(f"/api/lessons/{LESSON}/steps/nope/attempt", json={"payload": {}})
    assert response.status_code == 404


# ─── The generator's decisions are readable, not hidden ──────────────────────

def test_every_step_reports_why_the_generator_included_it(client):
    session = session_of(client)
    assert all(s["reason"].strip() for s in session["steps"])
    assert len(session["trace"]) == session["planned_steps"] + session["bonus_steps"]


def test_sessions_are_identical_for_the_same_learner_state(client):
    first = [s["id"] for s in session_of(client)["steps"]]
    second = [s["id"] for s in session_of(client)["steps"]]
    assert first == second


def test_a_rung_cleared_with_hints_can_still_be_demonstrated_later(client):
    """Regression: being helped once must not lock a learner out of proving it.

    The first unaided pass owes the learner evidence even though the rung was
    already cleared with hints — XP is once-only, evidence is owed to the real
    accomplishment.
    """
    code = {"code": "def predict(x, w, b):\n    return w * x + b\n"}
    helped = _clear(client, "lp-independent", code, hints=3)
    assert helped["passed"] is True
    assert "independent" not in helped["evidence"]

    again = _clear(client, "lp-independent", code)
    assert "independent" in again["evidence"]
    assert again["xp_awarded"] == 0, "the same rung must not pay out twice"
