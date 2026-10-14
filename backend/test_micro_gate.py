"""Micro lessons are proved by execution, not by screen counts."""

from backend.curriculum_loader import load_all_curriculums
from backend.verify_lessons import (
    audit_lesson,
    cross_lesson_duplicates,
    hint_gives_answer,
    program_parses,
    replay_sample,
)

PILOT = ("variables-step-1", "loops-step-1", "functions-step-1")


def test_replay_sample_is_ten_percent_and_stable():
    assert replay_sample([]) == []
    assert replay_sample(["only"]) == ["only"]
    assert len(replay_sample(["a", "b", "c"])) == 1
    sample = replay_sample([f"l{i}" for i in range(20)])
    assert len(sample) == 2
    assert sample == replay_sample([f"l{i}" for i in range(20)])
    assert len(replay_sample([f"l{i}" for i in range(108)])) == 11


def test_hint_1_may_not_contain_the_key_and_a_parse_must_be_real_code():
    assert hint_gives_answer("pick =", "=")
    assert not hint_gives_answer("The blank is the store symbol.", "=")
    assert program_parses("python", 'language = "Python"')[0]
    assert not program_parses("python", "language ___")[0]
    assert program_parses("java", "int total = left + right;")[0]
    assert not program_parses("java", "int total = ;")[0]
    assert program_parses("cpp", "int total = left + right;")[0]
    assert not program_parses("cpp", "int total = ;")[0]
    assert program_parses("javascript", "const total = left + right")[0]
    assert program_parses("sql", "SELECT city FROM stops")[0]


def test_pilot_lessons_execute_and_are_not_copies():
    lessons = {lesson.id: lesson for lesson in load_all_curriculums()["python"].lessons}
    records = []
    errors = []
    for lesson_id in PILOT:
        lesson = lessons[lesson_id]
        assert lesson.player_mode == "micro"
        assert lesson.sublessons[0].exercises[0].type == "teach"
        findings = audit_lesson("python", "python", lesson, {}, prompt_records=records)
        errors.extend(item for item in findings if item["severity"] == "ERROR")
    errors.extend(cross_lesson_duplicates(records))
    assert errors == []


def test_every_python_micro_lesson_executes():
    """Every opted-in Python lesson, including the pilot, has to clear the gate."""
    records = []
    errors = []
    seen: dict = {}
    count = 0
    for lesson in load_all_curriculums()["python"].lessons:
        if lesson.player_mode != "micro":
            continue
        count += 1
        assert lesson.sublessons[0].exercises[0].type == "teach"
        findings = audit_lesson("python", "python", lesson, seen, prompt_records=records)
        errors.extend(item for item in findings if item["severity"] == "ERROR")
    errors.extend(cross_lesson_duplicates(records))
    assert count >= 3
    assert errors == []
