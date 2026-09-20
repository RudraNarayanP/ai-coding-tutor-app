"""A lesson's own code task must be replayable, not just chargeable.

Failing one of the 307 lessons that have no sublesson exercises used to cost a
heart and be forgotten: ``run_lesson`` graded the code but never called
``record_attempt``, so the miss entered no queue, was never re-served, and gave
mastery nothing to measure. These tests pin the wiring, and pin the boundaries
of the derived item - it must never pay out twice or distort progress.

These use a stub executor only to drive the engine's own bookkeeping. The real
end-to-end path (real sandbox, real HTTP, isolated state directory) is verified
separately; see ``audit/COVERAGE_PLAN.md`` section 8.
"""
from __future__ import annotations

import asyncio

import pytest

from backend.curriculum_loader import load_all_curriculums
from backend.lesson_engine import (
    LESSON_TASK_PREFIX,
    LessonEngine,
    ProgressionStore,
    is_lesson_task,
    lesson_task_id,
)

CURRICULUM = load_all_curriculums()["python"]


class StubExecutor:
    """Reports every test as passed or as failed, on demand."""

    def __init__(self, pass_tests: bool = True):
        self.pass_tests = pass_tests
        self.calls = 0

    async def run(self, payload: dict) -> dict:
        self.calls += 1
        return {
            "tests": [
                {"name": t["name"], "passed": self.pass_tests, "stdout": "", "stderr": ""}
                for t in payload["tests"]
            ],
            "stdout": "",
            "stderr": "",
            "execution_time_ms": 1,
        }


def _lesson_without_exercises():
    """First exercise-free lesson that the unlock chain can actually reach."""
    lessons = CURRICULUM.lessons
    for index, lesson in enumerate(lessons):
        if lesson.sublessons or lesson.mastery_exam:
            continue
        return lesson, index
    raise AssertionError("expected at least one exercise-free lesson in the python course")


LESSON, LESSON_INDEX = _lesson_without_exercises()
TASK_ID = lesson_task_id(LESSON.id)


@pytest.fixture()
def engine(tmp_path):
    store = ProgressionStore(CURRICULUM, storage_path=tmp_path / "progression.json")
    # The target lesson must be unlocked, so complete the lessons that precede
    # it - the same state a real learner would be in when they arrive here.
    for prior in CURRICULUM.lessons[:LESSON_INDEX]:
        store.mark_completed(prior.id)
    eng = LessonEngine(
        StubExecutor(),
        stores={CURRICULUM.course.language: store},
        curriculums={CURRICULUM.course.language: CURRICULUM},
    )
    return eng, store


def run_lesson(eng, code: str = "x = 1"):
    return asyncio.run(eng.run_lesson(LESSON.id, code))


# ── the wiring ───────────────────────────────────────────────────────────────

def test_the_derived_id_is_valid_and_unique(tmp_path):
    assert is_lesson_task(TASK_ID)
    assert TASK_ID == f"{LESSON_TASK_PREFIX}{LESSON.id}"
    # ExerciseDefinition enforces ^[a-z0-9-]+$; a ':' would have been rejected.
    assert LESSON_TASK_PREFIX == "lt-"
    shipped = {ex.id for l in CURRICULUM.lessons for ex
               in [e for s in l.sublessons for e in s.exercises] + list(l.mastery_exam)}
    assert not any(i.startswith(LESSON_TASK_PREFIX) for i in shipped), "prefix collides"


def test_a_failed_lesson_task_is_queued(engine):
    eng, store = engine
    eng.executor.pass_tests = False
    result = run_lesson(eng)
    assert result.passed is False
    queued = {entry["exercise_id"] for entry in store.mistake_queue()}
    assert queued == {TASK_ID}, "the lesson miss never reached the queue"


def test_the_queue_describes_the_lesson_task_as_a_code_item(engine):
    eng, store = engine
    eng.executor.pass_tests = False
    run_lesson(eng)
    due = eng.due_mistakes(CURRICULUM.course.language)
    assert len(due) == 1
    item = due[0]
    assert item["exercise_id"] == TASK_ID
    assert item["lesson_id"] == LESSON.id
    exercise = item["exercise"]
    assert exercise["type"] == "code"
    assert exercise["question"] == (LESSON.description or LESSON.title)
    assert exercise["starter_code"] == (LESSON.starter_code or "")
    for forbidden in ("correct_answer", "solution_code", "blanks", "tests", "explanation"):
        assert forbidden not in exercise, f"{forbidden} leaked into the review payload"


def test_re_solving_the_lesson_task_graduates_it_and_reports_it(engine):
    eng, store = engine
    eng.executor.pass_tests = False
    run_lesson(eng)
    assert store.queued_exercise_ids() == {TASK_ID}

    eng.executor.pass_tests = True
    first = run_lesson(eng)
    assert first.graduated is False, "one solve is not graduation"
    assert store.queued_exercise_ids() == {TASK_ID}

    second = run_lesson(eng, "ok")
    # The recall gap has not elapsed in wall-clock terms, but an early correct
    # answer still counts (see test_mistake_queue), so this one graduates.
    assert second.graduated is True
    assert store.mistake_queue() == []


def test_a_passed_lesson_task_awards_no_extra_xp_and_no_fake_completion(engine):
    eng, store = engine
    eng.executor.pass_tests = True
    result = run_lesson(eng)
    assert result.passed and result.xp_awarded == (LESSON.xp_reward or 25)
    assert TASK_ID not in store.state().completed_exercise_ids, (
        "the derived task must not masquerade as a completed exercise")


def test_a_replayed_lesson_task_awards_no_xp_at_all(engine):
    eng, store = engine
    eng.executor.pass_tests = False
    run_lesson(eng)
    assert store.queued_exercise_ids() == {TASK_ID}
    eng.executor.pass_tests = True
    res = asyncio.run(eng.submit_exercise(LESSON.id, None, TASK_ID, {"code": "x = 1"}))
    assert res["passed"] is True
    assert res["xp_awarded"] == 0
    assert TASK_ID not in store.state().completed_exercise_ids


def test_lesson_progress_never_surfaces_the_derived_id(engine):
    """A queued lesson task must not strand the learner in 'review'."""
    eng, store = engine
    eng.executor.pass_tests = False
    run_lesson(eng)
    progress = eng.lesson_progress(LESSON.id)
    assert TASK_ID not in progress["queued_exercise_ids"]
    assert TASK_ID not in progress["completed_exercise_ids"]
    assert progress["total_exercises"] == 0
    assert progress["next_action"] in {"answer", "lesson_complete"}


def test_a_locked_lesson_records_no_attempt(engine):
    eng, store = engine
    locked = CURRICULUM.lessons[-1].id
    result = asyncio.run(eng.run_lesson(locked, "x = 1"))
    assert result.error == "lesson_locked"
    assert store.mistake_queue() == [], "an ungraded attempt must not be recorded"
    assert store._attempts == {}
