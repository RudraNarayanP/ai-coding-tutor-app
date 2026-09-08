import pytest
from backend.lesson_models import ExerciseDefinition, MatchingPair
from backend.lesson_engine import LessonEngine, ProgressionStore
from backend.curriculum_loader import load_all_curriculums

class DummyExecutor:
    async def run(self, payload):
        return {"passed": True, "tests": [{"name": "t1", "passed": True}]}

@pytest.fixture
def engine():
    curriculums = load_all_curriculums()
    curr = curriculums["python"]
    return LessonEngine(DummyExecutor(), ProgressionStore(curr), curriculums=curriculums)

@pytest.mark.asyncio
async def test_mcq_contract(engine):
    ex = ExerciseDefinition(id="ex-mcq", type="mcq", options=["=", "==", "->"], correct_answer="=")

    # Correct option
    passed, fb = await engine.grade_exercise(ex, {"answer": "="}, "python")
    assert passed is True
    assert fb == "Correct!"

    # Correct option case insensitive/trimmed
    passed_case, _ = await engine.grade_exercise(ex, {"answer": " = "}, "python")
    assert passed_case is True

    # Incorrect option
    failed, fb_fail = await engine.grade_exercise(ex, {"answer": "=="}, "python")
    assert failed is False

@pytest.mark.asyncio
async def test_true_false_contract(engine):
    ex = ExerciseDefinition(id="ex-tf", type="true_false", options=["True", "False"], correct_answer="True")

    passed, _ = await engine.grade_exercise(ex, {"answer": "True"}, "python")
    assert passed is True

    failed, _ = await engine.grade_exercise(ex, {"answer": "False"}, "python")
    assert failed is False

@pytest.mark.asyncio
async def test_fill_blank_contract(engine):
    ex = ExerciseDefinition(id="ex-fb", type="fill_blank", correct_answer=["\"Python\""])

    # Exact answer
    passed, _ = await engine.grade_exercise(ex, {"answers": ["\"Python\""]}, "python")
    assert passed is True

    # Normalized answer
    passed_norm, _ = await engine.grade_exercise(ex, {"answers": [" \"python\" "]}, "python")
    assert passed_norm is True

    # Invalid answer
    failed, _ = await engine.grade_exercise(ex, {"answers": ["\"Java\""]}, "python")
    assert failed is False

@pytest.mark.asyncio
async def test_ordering_contract(engine):
    ex = ExerciseDefinition(id="ex-ord", type="ordering", correct_answer=["step1", "step2", "step3"])

    passed, _ = await engine.grade_exercise(ex, {"order": ["step1", "step2", "step3"]}, "python")
    assert passed is True

    failed, _ = await engine.grade_exercise(ex, {"order": ["step2", "step1", "step3"]}, "python")
    assert failed is False

@pytest.mark.asyncio
async def test_matching_contract(engine):
    pairs = [MatchingPair(left="var", right="variable"), MatchingPair(left="fn", right="function")]
    ex = ExerciseDefinition(id="ex-match", type="matching", pairs=pairs)

    user_correct = [{"left": "var", "right": "variable"}, {"left": "fn", "right": "function"}]
    passed, _ = await engine.grade_exercise(ex, {"pairs": user_correct}, "python")
    assert passed is True

    user_incorrect = [{"left": "var", "right": "function"}, {"left": "fn", "right": "variable"}]
    failed, _ = await engine.grade_exercise(ex, {"pairs": user_incorrect}, "python")
    assert failed is False

@pytest.mark.asyncio
async def test_all_curriculums_integrity():
    curriculums = load_all_curriculums()
    for lang, curr in curriculums.items():
        for module in curr.modules:
            for lesson in module.lessons:
                for sub in lesson.sublessons:
                    for ex in sub.exercises:
                        if ex.type in ("mcq", "true_false") and isinstance(ex.correct_answer, str):
                            assert ex.correct_answer in ex.options
