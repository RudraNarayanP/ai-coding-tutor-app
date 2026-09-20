"""Tests for server-side blanking and answer-key removal from public payloads.

Covers:
  - build_blank_template replaces the answer token with the blank marker
  - every fill-blank exercise served by the API shows a blank, never the answer
  - the public exercise payload no longer carries ``blanks``
  - ``/api/materials`` does not ship the companion ``correct_answer``
"""

import json
import re

import pytest
from fastapi.testclient import TestClient

from backend.blank_template import build_blank_template, template_from_question
from backend.curriculum_loader import load_all_curriculums
from backend.main import app
from backend.materials_data import MATERIALS

client = TestClient(app)

BLANK = "___"
FILL_TYPES = ("fill_blank", "code_completion")


def all_exercises():
    """Every (lesson_id, exercise) pair in the loaded curriculum."""
    for language, curriculum in sorted(load_all_curriculums().items()):
        for lesson in curriculum.lessons:
            for sub in lesson.sublessons:
                for exercise in sub.exercises:
                    yield language, lesson.id, exercise
            for exercise in lesson.mastery_exam:
                yield language, lesson.id, exercise


FILL_BLANKS = [
    (lang, lid, ex) for lang, lid, ex in all_exercises() if ex.type.lower() in FILL_TYPES
]


# ---------------------------------------------------------------------------
# Unit behaviour
# ---------------------------------------------------------------------------

def test_replaces_the_last_occurrence_of_the_answer():
    template = build_blank_template(
        "num_tickets = 3\nticket_total = ticket_price * num_tickets", ["num_tickets"], ""
    )
    assert template == "num_tickets = 3\nticket_total = ticket_price * ___"


def test_code_that_already_has_a_blank_is_returned_unchanged():
    assert build_blank_template("return ___;", ['"Java"'], "") == "return ___;"


def test_quote_variants_are_matched():
    # The bare token is tried first, so the surrounding quotes survive.
    assert build_blank_template('lang = "Java"', ["Java"], "") == 'lang = "___"'


def test_missing_blank_appends_one_rather_than_leaking():
    template = build_blank_template("x = 1", ["never-appears"], "")
    assert BLANK in template


def test_question_supplies_the_template_when_there_is_no_code():
    assert template_from_question("Fill in: ___ * FROM customers;") == "___ * FROM customers;"


# ---------------------------------------------------------------------------
# Curriculum-wide invariant
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "language,lesson_id,exercise",
    FILL_BLANKS,
    ids=[f"{lang}:{ex.id}" for lang, _l, ex in FILL_BLANKS],
)
def test_public_starter_blanks_the_answer(language, lesson_id, exercise):
    payload = client.get(f"/api/lessons/{lesson_id}").json()
    served = _find_exercise(payload, exercise.id)
    assert served is not None, f"{lesson_id}/{exercise.id} missing from API"

    starter = served.get("starter_code") or ""
    answers = [str(a) for a in (exercise.correct_answer or [])]

    if starter.strip():
        assert BLANK in starter, f"starter was not blanked: {starter!r}"
        # An answer token may legitimately reappear as *given* scaffolding
        # (``popcorn_price = 8``), but never on the line the learner must fill.
        for line in starter.splitlines():
            if BLANK not in line:
                continue
            for answer in answers:
                bare = answer.strip("\"'")
                if len(bare) < 3:
                    continue
                assert bare not in line, f"answer {answer!r} left on the blank line: {line!r}"

    assert "blanks" not in served, "public exercise payload still ships the blanks answer key"


def _find_exercise(payload, exercise_id):
    for sub in payload.get("sublessons") or []:
        for exercise in sub.get("exercises") or []:
            if exercise.get("id") == exercise_id:
                return exercise
    for exercise in payload.get("mastery_exam") or []:
        if exercise.get("id") == exercise_id:
            return exercise
    return None


def test_no_fill_blank_exercise_is_left_unaudited():
    assert len(FILL_BLANKS) >= 10, "expected the curriculum to still carry fill-blank items"


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

def test_materials_endpoint_omits_companion_answers():
    body = client.get("/api/materials").json()
    with_question = [m for m in body if m.get("companion_question")]
    assert with_question, "expected materials with companion questions"
    for material in with_question:
        assert "correct_answer" not in material["companion_question"]
        assert "question" in material["companion_question"]


def test_materials_still_grade_server_side():
    assert MATERIALS, "materials data must remain available for grading"
    graded = [m for m in MATERIALS if m.companion_question]
    assert all(m.companion_question.correct_answer for m in graded)


def test_public_projection_keeps_the_key_out_of_the_payload():
    from backend.materials import to_public

    source = next(m for m in MATERIALS if m.companion_question)
    dumped = json.loads(to_public(source).model_dump_json())
    assert "correct_answer" not in dumped["companion_question"]
    # the source object itself is untouched, so grading still has the answer
    assert source.companion_question.correct_answer
