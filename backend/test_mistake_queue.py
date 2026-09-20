"""Tests for the mistake queue that re-serves missed exercises.

Covers:
  - a wrong answer queues the exercise and makes it due immediately
  - one correct re-solve is not enough; it leaves after two, with a gap
  - a second correct answer before the gap has elapsed does not graduate
  - lesson and sublesson ids survive a reload from disk
  - the /api/mistakes payload carries no answer key
"""

import json
import time

import pytest

from backend.curriculum_loader import load_all_curriculums
from backend.lesson_engine import (
    MISTAKES_GRADUATE_AFTER,
    MISTAKES_RECALL_SECONDS,
    ProgressionStore,
)

CURRICULUM = load_all_curriculums()["python"]
LESSON_ID = "variables-step-1"
EXERCISE_ID = "py-ex-1a"
SUBLESSON_ID = "py-var-sub-1"


@pytest.fixture()
def store(tmp_path):
    path = tmp_path / "progression.json"
    return ProgressionStore(CURRICULUM, storage_path=path)


def miss(store, exercise_id=EXERCISE_ID, now=None):
    return store.record_attempt(exercise_id, False, lesson_id=LESSON_ID, sublesson_id=SUBLESSON_ID, now=now)


def solve(store, exercise_id=EXERCISE_ID, now=None):
    return store.record_attempt(exercise_id, True, lesson_id=LESSON_ID, sublesson_id=None, now=now)


# ---------------------------------------------------------------------------
# Queueing
# ---------------------------------------------------------------------------

def test_wrong_answer_queues_the_exercise_as_due_now(store):
    miss(store)
    due = store.due_mistakes()
    assert [entry["exercise_id"] for entry in due] == [EXERCISE_ID]
    assert due[0]["streak"] == 0
    assert due[0]["wrong_count"] == 1


def test_correct_answer_on_a_fresh_exercise_does_not_queue_it(store):
    solve(store)
    assert store.due_mistakes() == []
    assert store.mistake_queue() == []


def test_repeat_mistakes_accumulate_but_stay_due_once(store):
    miss(store)
    miss(store)
    miss(store)
    due = store.due_mistakes()
    assert len(due) == 1
    assert due[0]["wrong_count"] == 3


def test_wrong_answer_resets_an_in_progress_streak(store):
    miss(store)
    solve(store)
    assert store.mistake_queue()[0]["streak"] == 1
    miss(store, now=time.time() + 400)
    assert store.mistake_queue()[0]["streak"] == 0


# ---------------------------------------------------------------------------
# Graduation and spacing
# ---------------------------------------------------------------------------

def test_one_correct_solve_is_not_enough(store):
    miss(store)
    solve(store)
    assert store.mistake_queue(), "exercise left the queue too early"
    assert MISTAKES_GRADUATE_AFTER >= 2


def test_second_correct_solve_after_the_gap_graduates_it(store):
    miss(store)
    solve(store)
    gap = MISTAKES_RECALL_SECONDS[0]
    solve(store, now=time.time() + gap + 1)
    assert store.mistake_queue() == []


def test_an_early_second_correct_solve_still_graduates(store):
    """Answering ahead of the gap is rare; when it happens, count it."""
    miss(store)
    solve(store)
    solve(store, now=time.time() - 1)
    assert store.due_mistakes() == []
    assert store.mistake_queue() == []


def test_exercise_is_not_due_immediately_after_a_miss_and_a_solve(store):
    miss(store)
    solve(store)
    assert store.due_mistakes() == [], "recall should wait for the gap to elapse"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_queue_survives_a_reload_with_its_lesson_ids(store):
    miss(store)
    reloaded = ProgressionStore(CURRICULUM, storage_path=store.storage_path)
    entry = reloaded.mistake_queue()[0]
    assert entry["lesson_id"] == LESSON_ID
    assert entry["sublesson_id"] == SUBLESSON_ID
    assert entry["wrong_count"] == 1


def test_reset_clears_the_queue(store):
    miss(store)
    store.reset()
    assert store.mistake_queue() == []


def test_attempt_counts_are_still_returned(store):
    assert miss(store) == 1
    assert solve(store) == 2


# ---------------------------------------------------------------------------
# API payload
# ---------------------------------------------------------------------------

def test_mistakes_endpoint_exposes_no_answer_key():
    from fastapi.testclient import TestClient

    from backend.main import app, lesson_engine

    language = "python"
    engine_store = lesson_engine.stores[language]
    target = next(
        (
            (lesson.id, sub.id, ex.id)
            for lesson in engine_store._lessons
            for sub in lesson.sublessons
            for ex in sub.exercises
        ),
        None,
    )
    assert target, "expected the python course to still carry sublesson exercises"
    lesson_id, sublesson_id, exercise_id = target

    engine_store.clear_mistakes()
    engine_store.record_attempt(exercise_id, False, lesson_id=lesson_id, sublesson_id=sublesson_id)
    try:
        body = TestClient(app).get("/api/mistakes").json()
        assert body["due"], "a missed exercise should be served back"
        for item in body["due"]:
            exercise = item["exercise"]
            for forbidden in ("correct_answer", "blanks", "solution_code", "explanation"):
                assert forbidden not in exercise, f"{forbidden} leaked into /api/mistakes"
            assert item["wrong_count"] >= 1
    finally:
        engine_store.clear_mistakes()


def test_mistakes_endpoint_respects_the_language_filter():
    from fastapi.testclient import TestClient

    from backend.main import app

    body = TestClient(app).get("/api/mistakes", params={"language": "python"}).json()
    assert all(item["language"] == "python" for item in body["due"])


def test_queue_is_json_serialisable(store):
    miss(store)
    json.dumps({"mistake_queue": store.mistake_queue()})
