import pytest

from backend.curriculum_loader import load_default_curriculum
from backend.lesson_engine import LessonEngine, ProgressionStore
from backend.sandbox import sandbox


@pytest.mark.asyncio
async def test_fill_blank_exercise_preview_run():
    curr = load_default_curriculum()
    engine = LessonEngine(sandbox, ProgressionStore(curr), curr)
    lesson_id = "variables-practice-1"
    exercise_id = "cinema-ex-1a"
    code = "ticket_price = 12\nnum_tickets = 3\nticket_total = ticket_price * num_tickets"

    result = await engine.run_exercise_code(lesson_id, exercise_id, code)

    assert result.passed is True
    assert "ticket_total = 36" in (result.stdout or "")
    assert result.error is None


def test_public_exercise_view_includes_task_copy():
    from backend.curriculum_loader import load_default_curriculum
    from backend.lesson_models import PublicLessonView

    curr = load_default_curriculum()
    lesson = next(item for item in curr.lessons if item.id == "variables-practice-1")
    view = PublicLessonView.from_lesson(lesson)
    exercise = view.sublessons[0].exercises[0]
    assert exercise.id == "cinema-ex-1a"
    assert exercise.micro_explanation
    assert exercise.worked_example_takeaway
    dumped = exercise.model_dump()
    assert "solution_code" not in dumped
    assert "tests" not in dumped
