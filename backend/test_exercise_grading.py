import pytest
import asyncio
from backend.lesson_models import ExerciseDefinition, MatchingPair
from backend.lesson_engine import LessonEngine, ProgressionStore
from backend.curriculum_loader import load_default_curriculum

class DummyExecutor:
    async def run(self, payload):
        return {"passed": True, "tests": [{"name": "t1", "passed": True}]}

@pytest.mark.asyncio
async def test_mcq_grading():
    curr = load_default_curriculum()
    engine = LessonEngine(DummyExecutor(), ProgressionStore(curr), curr)
    ex = ExerciseDefinition(id="test-mcq", type="mcq", correct_answer="int", explanation="int is integer")

    passed, feedback = await engine.grade_exercise(ex, {"answer": "int"}, "python")
    assert passed is True

    failed, feedback_fail = await engine.grade_exercise(ex, {"answer": "str"}, "python")
    assert failed is False

@pytest.mark.asyncio
async def test_fill_blank_grading():
    curr = load_default_curriculum()
    engine = LessonEngine(DummyExecutor(), ProgressionStore(curr), curr)
    ex = ExerciseDefinition(id="test-fill", type="fill_blank", correct_answer=["10"])

    passed, _ = await engine.grade_exercise(ex, {"answers": ["10"]}, "python")
    assert passed is True

    failed, _ = await engine.grade_exercise(ex, {"answers": ["20"]}, "python")
    assert failed is False

@pytest.mark.asyncio
async def test_submit_exercise_and_xp():
    curr = load_default_curriculum()
    store = ProgressionStore(curr)
    engine = LessonEngine(DummyExecutor(), store, curr)

    res = await engine.submit_exercise("variables-step-1", "py-var-sub-1", "py-ex-1a", {"answer": "="})
    assert res["passed"] is True
    assert res["xp_awarded"] == 10

    # Repeat submission -> anti-farming check (0 XP)
    res_repeat = await engine.submit_exercise("variables-step-1", "py-var-sub-1", "py-ex-1a", {"answer": "="})
    assert res_repeat["passed"] is True
    assert res_repeat["xp_awarded"] == 0

@pytest.mark.asyncio
async def test_test_out_exam():
    curr = load_default_curriculum()
    store = ProgressionStore(curr)
    engine = LessonEngine(DummyExecutor(), store, curr)

    submissions = {
        "py-exam-1": {"answer": "str"},
        "py-exam-2": {"answer": "10"}
    }

    result = await engine.run_test_out("variables-step-1", submissions)
    assert result["passed"] is True
    assert result["score_pct"] == 100
    assert result["xp_awarded"] == 100
