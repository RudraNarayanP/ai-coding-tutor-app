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

#: The second authored concept. It exists to prove the ladder is an architecture
#: and not a wrapper around one lesson.
MSE_LESSON = "linreg-mse"
MSE_CONCEPT = "measuring-error"

LADDER_LESSONS = (LESSON, MSE_LESSON)
LADDER_CONCEPTS = (CONCEPT, MSE_CONCEPT)


def _fresh_learner() -> None:
    """Wipe the ladder state, so each test really starts from a new learner.

    The store is a process-wide singleton pointed at one throwaway directory for
    the whole run, so without this the second test inherits the first learner's
    progress — and the brief's acceptance question is specifically about a learner
    who has never seen the concept. Both concepts are wiped because a session for
    one now reads the other's history.
    """
    store = lesson_engine.stores.get("ml", lesson_engine.store)
    for concept in LADDER_CONCEPTS:
        store.set_concept_state(concept, {})
    # Reaching a lesson twice in one run must not be punished for it: completion
    # is one-way in the store, and the throwaway directory is shared by the run.
    store._completed.difference_update(LADDER_LESSONS)


def seed_concept(concept: str, **state) -> None:
    """Write a learner's history directly, as a test's way of standing in time."""
    store = lesson_engine.stores.get("ml", lesson_engine.store)
    store.set_concept_state(concept, state)


def _state_of(concept: str) -> dict:
    store = lesson_engine.stores.get("ml", lesson_engine.store)
    return store.concept_state(concept)


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


def session_of(client, lesson: str = LESSON) -> dict:
    response = client.get(f"/api/lessons/{lesson}/session")
    assert response.status_code == 200, response.text
    return response.json()


def step_ids(session: dict) -> list[str]:
    return [s["id"] for s in session["steps"]]


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
    # The denominator the progress bar is allowed to promise, from a cold start.
    assert session["ladder_steps"] == 8


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
    # The bar's promise does not shrink as the owed list does: 8 rungs were
    # authored for this visit, 7 remain, and the client draws 1 of 8.
    assert session["planned_steps"] == len(session["steps"]) == 7
    assert session["ladder_steps"] == 8


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

def _clear(client, step_id, payload, hints=0, lesson=LESSON):
    response = client.post(
        f"/api/lessons/{lesson}/steps/{step_id}/attempt",
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


# ─── Phase 3: the second concept goes through the same architecture ──────────

def test_mean_squared_error_is_taught_the_same_way_as_prediction(client):
    """A new concept is authored, not taught twice by two code paths."""
    session = session_of(client, MSE_LESSON)
    order = stages(session["steps"])
    assert order == ["introduce", "show", "interact", "guided", "scaffolded",
                     "independent", "explain", "transfer"], order
    assert [s["id"] for s in session["steps"] if s["stakes"] == "charged"] == [
        "me-independent", "me-transfer"]
    assert session["ladder_steps"] == 8
    assert session["demonstrated"] is False
    assert "prediction" in session["story"]["why_this"].lower()


def test_a_learner_who_never_saw_prediction_is_not_quizzed_on_it(client):
    """The pool's opening step retrieves linear prediction; a novice never met it.

    This is the one place the shipped order of a lesson is the whole test: the file
    literally starts with a retrieval hook, and rule 9 is what keeps it off the
    screen of someone who has not had the previous lesson.
    """
    assert "me-retrieve-predict" not in step_ids(session_of(client, MSE_LESSON))
    assert session_of(client, MSE_LESSON)["bonus_steps"] == 0


def test_a_demonstrated_concept_is_retrieved_inside_the_next_lesson(client):
    seed_concept(
        CONCEPT,
        cleared_steps=["lp-intro", "lp-independent", "lp-transfer"],
        evidence=["independent", "transferred"],
        misses={}, hinted_steps={}, misconceptions={},
        last_recall_at=0.0, interval_seconds=300.0, strong_recalls=0,
    )
    session = session_of(client, MSE_LESSON)
    hook = next(s for s in session["steps"] if s["id"] == "me-retrieve-predict")
    assert hook["bonus"] is True
    assert hook["concept"] == CONCEPT
    assert hook["stakes"] == "free", "remembering must not be able to cost a heart"
    assert session["planned_steps"] == 8, "the progress bar promised 8 and got 8"
    assert "linear-prediction due for retrieval" in hook["reason"]


def test_recalled_evidence_is_filed_under_the_concept_it_belongs_to(client):
    """A hook proves something about last week's concept, not today's."""
    seed_concept(
        CONCEPT,
        cleared_steps=["lp-independent", "lp-transfer"],
        evidence=["independent", "transferred"],
        misses={}, hinted_steps={}, misconceptions={},
        last_recall_at=0.0, interval_seconds=300.0, strong_recalls=0,
    )
    body = _clear(client, "me-retrieve-predict", {"answer": "7"}, lesson=MSE_LESSON)
    assert body["passed"] is True
    assert body["concept"] == CONCEPT
    assert "delayed_recall" in body["evidence"]
    assert body["lesson_completed"] is False

    assert "delayed_recall" in _state_of(CONCEPT)["evidence"]
    filed = _state_of(MSE_CONCEPT)
    assert filed.get("evidence") in (None, []), "today's concept gained free evidence"


def test_a_wrong_recall_shortens_the_gap_instead_of_punishing(client):
    seed_concept(
        CONCEPT,
        cleared_steps=["lp-independent"], evidence=["independent"],
        misses={}, hinted_steps={}, misconceptions={},
        last_recall_at=0.0, interval_seconds=1500.0, strong_recalls=1,
    )
    body = _clear(client, "me-retrieve-predict", {"answer": "6"}, lesson=MSE_LESSON)
    assert body["passed"] is False
    assert body["charging"] is False
    state = _state_of(CONCEPT)
    assert state["interval_seconds"] == 300.0, "the gap must collapse, not grow"
    assert state["strong_recalls"] == 0


def test_a_first_unaided_pass_starts_the_review_clock(client):
    """Spacing cannot apply to a concept whose clock was never set.

    measuring-error ships no review rung of its own — its retrieval lives in the
    next lesson's pool — so without seeding on first contact it would never be
    scheduled and never come back.
    """
    _clear(client, "me-independent",
           {"code": "def mse(y_true, y_pred):\n    n = len(y_true)\n"
                    "    return sum((p - t) ** 2 for t, p in zip(y_true, y_pred)) / n\n"},
           lesson=MSE_LESSON)
    row = next(c for c in client.get("/api/concepts", params={"language": "ml"}).json()["concepts"]
               if c["concept"] == MSE_CONCEPT)
    assert row["interval_seconds"] == 300.0
    assert row["due_for_review"] is False, "five minutes have not passed yet"
    assert _state_of(MSE_CONCEPT)["last_recall_at"] is not None
    assert row["demonstrated"] is False, "one rung is not a demonstrated concept"


def test_the_whole_mse_ladder_can_be_walked_end_to_end(client):
    solution = ("def mse(y_true, y_pred):\n    n = len(y_true)\n"
                "    return sum((p - t) ** 2 for t, p in zip(y_true, y_pred)) / n\n")
    transfer = ("def mean_squared_error(forecast, actual):\n    n = len(actual)\n"
                "    return sum((f - a) ** 2 for f, a in zip(forecast, actual)) / n\n")
    client.post(f"/api/lessons/{MSE_LESSON}/steps/me-intro/seen")
    client.post(f"/api/lessons/{MSE_LESSON}/steps/me-worked/seen")
    order = ["diff = y_pred - y_true", "sq = diff * diff", "total = sum(sq)", "mse = total / n"]
    for rung, payload in (
        ("me-why-squared", {"answer": "square each error before averaging"}),
        ("me-match-steps", {"order": order}),
        ("me-fill", {"answers": ["d ** 2"]}),
        ("me-independent", {"code": solution}),
        ("me-debug", {"answer": "the differences are averaged without being squared"}),
    ):
        assert _clear(client, rung, payload, lesson=MSE_LESSON)["passed"] is True, rung

    final = _clear(client, "me-transfer", {"code": transfer}, lesson=MSE_LESSON)
    assert final["passed"] is True
    assert final["lesson_completed"] is True
    assert final["next_lesson_id"] and final["next_lesson_id"] != MSE_LESSON
    # The engine recommends the next *incomplete* lesson in path order, so a
    # learner who skipped lesson 1 is sent back to it — the ladder reports the
    # engine's answer rather than assuming lessons were done in order.
    assert sorted(final["evidence"]) == ["debugged", "independent", "transferred"]

    concepts = client.get("/api/concepts", params={"language": "ml"}).json()
    row = next(c for c in concepts["concepts"] if c["concept"] == MSE_CONCEPT)
    assert row["demonstrated"] is True


def test_a_demonstrated_concept_test_out_of_its_own_lesson(client):
    """The advanced learner's path: no re-teaching, one mixed-skill check."""
    seed_concept(
        MSE_CONCEPT,
        cleared_steps=["me-intro", "me-worked", "me-why-squared", "me-match-steps",
                       "me-fill", "me-independent", "me-debug", "me-transfer"],
        evidence=["independent", "transferred"],
        misses={}, hinted_steps={}, misconceptions={},
        last_recall_at=0.0, interval_seconds=300.0, strong_recalls=0,
    )
    session = session_of(client, MSE_LESSON)
    assert step_ids(session) == ["me-mixed-check", "me-why-squared"], session["trace"]
    assert session["planned_steps"] == 1, "one check, not eight rungs again"
    assert session["demonstrated"] is True
    assert all("faded" in line or "mixed-skill" in line or "due for retrieval" in line
               for line in session["trace"])


def test_a_wrong_fill_says_why_that_fill_is_wrong(client):
    """The scaffolded rung authored a repair for the sign-preserving mistake.

    Dead data in a content file is the failure mode this catches: the grader and
    the feedback lookup disagree about which field the learner answered in, and
    the learner is told nothing.
    """
    body = _clear(client, "me-fill", {"answers": ["d"]}, lesson=MSE_LESSON)
    assert body["passed"] is False
    assert "cancel" in body["feedback"].lower(), body["feedback"]


# ─── the payload is not an answer sheet ──────────────────────────────────────

def test_the_session_ships_no_field_that_is_also_the_answer():
    """`blanks` and `correct_order` are the key for their widgets, so they stay home.

    The exercise path has stripped `blanks` from the public payload for this reason
    all along (ExerciseWorkspace.test.tsx asserts it); the ladder reintroduced the
    same leak through a different endpoint, which is how a second render path
    defeats a rule like this one.
    """
    banned = {"correct_answer", "solution_code", "blanks", "correct_order", "answer"}
    from fastapi.testclient import TestClient
    from backend.main import app

    http = TestClient(app)
    body = http.get(f"/api/lessons/{LESSON}/session").json()
    for step in body["steps"]:
        assert banned.isdisjoint(step.keys()), (step["id"], sorted(set(step) & banned))
    # The learner still gets everything needed to answer.
    fill = next(s for s in body["steps"] if s["id"] == "lp-fill")
    assert fill["starter_code"] and "___" in fill["starter_code"]


def test_the_answer_key_still_reaches_the_grader():
    """Stripping the payload must not break grading — the key lives server-side."""
    from fastapi.testclient import TestClient
    from backend.main import app

    http = TestClient(app)
    body = http.post(
        f"/api/lessons/{LESSON}/steps/lp-fill/attempt",
        json={"payload": {"answers": ["x"], "code": "def predict(x, w, b):\n    return w * x + b\n"}},
    ).json()
    assert body["passed"] is True
