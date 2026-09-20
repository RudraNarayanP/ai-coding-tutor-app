"""Tests for the per-exercise canonical answer endpoint.

Exercise steps show the same "Show full answer" affordance as lesson code, so
the endpoint behind it must return the answer for *that step*, not the lesson.
"""

from fastapi.testclient import TestClient

import backend.main as main
from backend.curriculum_loader import load_all_curriculums

client = TestClient(main.app)


def _first_code_exercise():
    for curriculum in load_all_curriculums().values():
        for lesson in curriculum.lessons:
            for exercise in [
                *(e for sub in lesson.sublessons for e in sub.exercises),
                *lesson.mastery_exam,
            ]:
                if (exercise.solution_code or "").strip():
                    return lesson.id, exercise.id, exercise.solution_code
    raise AssertionError("no exercise with a canonical solution in the curriculum")


def test_exercise_solution_returns_that_exercises_code():
    lesson_id, exercise_id, solution = _first_code_exercise()
    response = client.get(f"/api/lessons/{lesson_id}/exercises/{exercise_id}/solution")
    assert response.status_code == 200
    data = response.json()
    assert data["exercise_id"] == exercise_id
    assert data["solution_code"].strip() == solution.strip()


def test_exercise_solution_exposes_choice_answers_for_the_step():
    """Fill-blank / MCQ steps need `answers`/`answer`, not code."""
    found = False
    for curriculum in load_all_curriculums().values():
        for lesson in curriculum.lessons:
            for exercise in [
                *(e for sub in lesson.sublessons for e in sub.exercises),
                *lesson.mastery_exam,
            ]:
                if exercise.type in ("fill_blank", "mcq") and exercise.correct_answer:
                    response = client.get(
                        f"/api/lessons/{lesson.id}/exercises/{exercise.id}/solution"
                    )
                    assert response.status_code == 200
                    data = response.json()
                    assert data["answer"] or data["answers"]
                    found = True
                    break
            if found:
                break
        if found:
            break
    assert found, "no choice exercise with a correct answer in the curriculum"


def test_unknown_exercise_is_a_404_not_a_lesson_answer():
    lesson_id, _, _ = _first_code_exercise()
    response = client.get(f"/api/lessons/{lesson_id}/exercises/does-not-exist/solution")
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "exercise_not_found"


def test_unknown_lesson_is_a_404():
    response = client.get("/api/lessons/nope-999/exercises/nope/solution")
    assert response.status_code == 404
