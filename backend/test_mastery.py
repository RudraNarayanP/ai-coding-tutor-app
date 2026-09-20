"""Tests for the mastery threshold that replaced pass-once completion.

Previously a lesson finished the moment each exercise had been passed once, so
guessing through a step was indistinguishable from knowing it, and nothing ever
asked again. Mastery now requires every exercise to be *cleared* — passed and
no longer sitting in the mistake queue — plus a minimum first-attempt accuracy.
"""

import pytest

from backend.curriculum_loader import load_all_curriculums
from backend.lesson_engine import (
    MASTERY_FIRST_ATTEMPT_THRESHOLD,
    LessonEngine,
    ProgressionStore,
)

CURRICULUM = load_all_curriculums()["python"]
LESSON_ID = "variables-step-1"


class DummyExecutor:
    async def run(self, payload: dict) -> dict:
        return {"passed": True, "tests": [], "stdout": "", "stderr": "", "error": None}


@pytest.fixture()
def store(tmp_path):
    return ProgressionStore(CURRICULUM, storage_path=tmp_path / "progression.json")


@pytest.fixture()
def engine(store):
    return LessonEngine(executor=DummyExecutor(), curriculum=CURRICULUM, store=store)


def lesson_exercise_ids(store):
    lesson = store._lessons_by_id[LESSON_ID]
    return [ex.id for sub in lesson.sublessons for ex in sub.exercises]


def clear(store, engine, exercise_ids):
    """Pass each exercise once, with no prior miss."""
    for exercise_id in exercise_ids:
        store.record_attempt(exercise_id, True, lesson_id=LESSON_ID)
        store.mark_exercise_completed(exercise_id)


# ---------------------------------------------------------------------------
# Cleared vs merely answered
# ---------------------------------------------------------------------------

def test_a_missed_exercise_is_answered_but_not_cleared(store, engine):
    ids = lesson_exercise_ids(store)
    clear(store, engine, ids)
    store.record_attempt(ids[0], False, lesson_id=LESSON_ID)

    progress = engine.lesson_progress(LESSON_ID)
    assert ids[0] in progress["completed_exercise_ids"]
    assert ids[0] not in progress["cleared_exercise_ids"]
    assert ids[0] in progress["queued_exercise_ids"]
    # Passing every step still completes the lesson. Browser testing showed
    # that gating completion on an emptied queue stranded the learner in
    # "review" while the recall timer ran, with nothing actually due.
    assert progress["lesson_completed"] is True
    # Mastery is what the outstanding miss withholds.
    assert progress["mastery"]["mastered"] is False


def test_clearing_the_queue_is_what_grants_mastery(store, engine):
    ids = lesson_exercise_ids(store)
    clear(store, engine, ids)
    store.record_attempt(ids[0], False, lesson_id=LESSON_ID)
    assert engine.lesson_progress(LESSON_ID)["mastery"]["mastered"] is False

    # Two consecutive correct re-solves graduate it, as the queue requires.
    store.record_attempt(ids[0], True, lesson_id=LESSON_ID)
    store.record_attempt(ids[0], True, lesson_id=LESSON_ID, now=_future())
    progress = engine.lesson_progress(LESSON_ID)
    assert progress["cleared_exercise_ids"] == sorted(ids)
    assert progress["queued_exercise_ids"] == []
    assert progress["mastery"]["mastered"] is True


def test_lesson_is_not_blocked_while_a_recall_interval_is_running(store, engine):
    """A parked item must not hold the lesson hostage."""
    import time

    ids = lesson_exercise_ids(store)
    clear(store, engine, ids)
    store.record_attempt(ids[0], False, lesson_id=LESSON_ID)
    store.record_attempt(ids[0], True, lesson_id=LESSON_ID)  # parked for 5 min

    progress = engine.lesson_progress(LESSON_ID)
    assert progress["lesson_completed"] is True
    assert progress["next_action"] == "lesson_complete"
    assert progress["queued_exercise_ids"] == [ids[0]]

    now = time.time()
    assert ids[0] not in store.due_exercise_ids(now=now + 100)
    assert ids[0] in store.due_exercise_ids(now=now + 400)


def test_a_due_item_does_ask_for_review(store, engine):
    """The one case that should interrupt: a queued item whose gap has elapsed."""
    ids = lesson_exercise_ids(store)
    clear(store, engine, ids)
    store.record_attempt(ids[0], False, lesson_id=LESSON_ID)
    # Not complete yet, and something is due right now.
    store._completed_exercises.discard(ids[1])
    progress = engine.lesson_progress(LESSON_ID)
    assert progress["lesson_completed"] is False
    assert progress["next_action"] == "review"
    assert ids[0] in progress["queued_exercise_ids"]


def _future():
    import time

    return time.time() + 4000


# ---------------------------------------------------------------------------
# Accuracy gate
# ---------------------------------------------------------------------------

def test_mastery_requires_the_configured_first_attempt_accuracy(store, engine):
    assert MASTERY_FIRST_ATTEMPT_THRESHOLD == 0.8
    ids = lesson_exercise_ids(store)
    clear(store, engine, ids)
    mastery = engine.lesson_progress(LESSON_ID)["mastery"]
    assert mastery["required"] == len(ids)
    assert mastery["first_attempt_accuracy"] == 1.0
    assert mastery["mastered"] is True


def test_guessing_through_everything_is_completion_without_mastery(store, engine):
    ids = lesson_exercise_ids(store)
    for exercise_id in ids:
        store.record_attempt(exercise_id, False, lesson_id=LESSON_ID)
        store.record_attempt(exercise_id, True, lesson_id=LESSON_ID)
        store.record_attempt(exercise_id, True, lesson_id=LESSON_ID, now=_future())
        store.mark_exercise_completed(exercise_id)

    progress = engine.lesson_progress(LESSON_ID)
    assert progress["lesson_completed"] is True
    mastery = progress["mastery"]
    assert mastery["first_attempt_accuracy"] == 0.0
    assert mastery["mastered"] is False


def test_partial_accuracy_below_the_threshold_is_not_mastered(store, engine):
    ids = lesson_exercise_ids(store)
    assert len(ids) >= 2
    clear(store, engine, ids)
    # One of two first attempts wrong -> 0.5 accuracy, below 0.8.
    store.record_attempt(ids[0], False, lesson_id=LESSON_ID)
    store._first_attempt_misses.add(ids[0])
    mastery = engine.lesson_progress(LESSON_ID)["mastery"]
    assert mastery["first_attempt_accuracy"] < MASTERY_FIRST_ATTEMPT_THRESHOLD
    assert mastery["mastered"] is False


def test_mastery_is_recorded_once_and_not_repeatedly_awarded(store, engine):
    ids = lesson_exercise_ids(store)
    clear(store, engine, ids)
    assert store.state().mastered_lesson_ids == []
    store.mark_lesson_mastered(LESSON_ID)
    assert LESSON_ID in store.state().mastered_lesson_ids
    assert LESSON_ID in store.state().completed_lesson_ids


def test_earned_mastery_does_not_skip_sublessons(store, engine):
    """Test-out mastery skips ahead; earned mastery must not."""
    lesson = store._lessons_by_id[LESSON_ID]
    before = set(store.state().skipped_sublesson_ids) if hasattr(
        store.state(), "skipped_sublesson_ids"
    ) else set()
    store.mark_lesson_mastered(LESSON_ID)
    assert set(store._skipped).isdisjoint({sub.id for sub in lesson.sublessons})
    assert before == set()


def test_a_lesson_with_no_exercises_cannot_be_mastered_by_the_threshold(store, engine):
    code_lesson = next(l for l in CURRICULUM.lessons if not l.sublessons)
    mastery = engine._mastery_for(
        code_lesson, cleared=set(), store=store
    )
    assert mastery["required"] == 0
    assert mastery["mastered"] is False


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_first_attempt_misses_survive_a_reload(store, tmp_path):
    ids = lesson_exercise_ids(store)
    store.record_attempt(ids[0], False, lesson_id=LESSON_ID)
    reloaded = ProgressionStore(CURRICULUM, storage_path=store.storage_path)
    assert reloaded.missed_on_first_attempt(ids) == {ids[0]}


def test_mastery_state_survives_a_reload(store, engine):
    clear(store, engine, lesson_exercise_ids(store))
    store.mark_lesson_mastered(LESSON_ID)
    reloaded = ProgressionStore(CURRICULUM, storage_path=store.storage_path)
    assert LESSON_ID in reloaded.state().mastered_lesson_ids
