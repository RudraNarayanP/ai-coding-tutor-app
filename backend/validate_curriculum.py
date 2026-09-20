#!/usr/bin/env python3
import sys
from pathlib import Path

# The audit verdict is printed with non-ASCII marks. On a Windows console
# (cp1252) that raised UnicodeEncodeError *after* a passing audit, so the
# script exited non-zero on healthy curriculum data.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):  # pragma: no cover - redirected/closed
            pass

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.curriculum_loader import load_all_curriculums
from backend.exercise_types import (
    ALL_TYPES,
    CHOICE_TYPES,
    CODE_TYPES,
    FILL_TYPES,
    MATCHING_TYPES,
    MULTI_SELECT_TYPES,
    ORDERING_TYPES,
    is_known,
)
from backend.starter_leak_audit import audit as audit_starter_leaks


def validate_exercise(lang: str, lesson_id: str, ex, errors: list[str]) -> None:
    """Check one exercise, whether it lives in a sublesson or a mastery exam.

    The type dispatch is registry-driven and ends in an ``else``: an unknown
    type used to fall off the bottom of an if/elif chain unnoticed, and the
    grader then auto-passed it.
    """
    ref = f"[{lang}/{lesson_id}/{ex.id}]"
    ex_type = ex.type.lower().strip()
    exp = ex.correct_answer

    q_text = (ex.question or ex.title or "").strip()
    if not q_text or "placeholder" in q_text.lower() or q_text.lower() == "todo":
        errors.append(f"{ref} Question text is empty or placeholder.")

    starter = (ex.starter_code or getattr(ex, "code", "") or "").strip()
    solution = (ex.solution_code or "").strip()
    if starter and solution and starter == solution:
        errors.append(f"{ref} Pre-solved code detected: starter_code matches solution_code.")
    if starter and isinstance(exp, str) and exp.strip() and starter == exp.strip():
        errors.append(f"{ref} Pre-solved code detected: starter_code matches correct_answer.")

    def need_answer_key(why: str) -> None:
        if exp is None or exp == "" or (isinstance(exp, (list, tuple, dict)) and len(exp) == 0):
            errors.append(f"{ref} Type '{ex_type}' {why}.")

    if not is_known(ex_type):
        errors.append(
            f"{ref} Unknown exercise type '{ex_type}'. Known types: "
            f"{', '.join(sorted(ALL_TYPES))}."
        )
    elif ex_type in CHOICE_TYPES:
        need_answer_key("missing correct_answer")
        if ex_type == "mcq":
            if not ex.options or len(ex.options) < 2:
                errors.append(f"{ref} MCQ requires at least 2 options.")
            elif isinstance(exp, str) and exp not in [
                o for o in ex.options
            ] and not exp.isdigit() and exp.lower() not in [o.lower() for o in ex.options]:
                errors.append(f"{ref} MCQ answer '{exp}' not found in options {ex.options}.")
    elif ex_type in FILL_TYPES:
        need_answer_key("missing correct_answer")
    elif ex_type in MULTI_SELECT_TYPES:
        need_answer_key("missing correct_answer")
        if not ex.options or len(ex.options) < 2:
            errors.append(f"{ref} select_multiple requires options.")
    elif ex_type in ORDERING_TYPES:
        if not isinstance(exp, list) or len(exp) == 0:
            errors.append(f"{ref} Type ordering missing list correct_answer.")
    elif ex_type in MATCHING_TYPES:
        if not ex.pairs and not isinstance(exp, dict):
            errors.append(f"{ref} Type matching missing pairs definition.")
    elif ex_type in CODE_TYPES:
        if not ex.tests and not ex.starter_code and not ex.solution_code:
            errors.append(f"{ref} Code exercise missing starter_code, tests or solution.")


def validate_all_curriculums() -> bool:
    print("=== Patchwork Curriculum Integrity Audit ===")
    curriculums = load_all_curriculums()
    if not curriculums:
        print("ERROR: No curriculums found!")
        return False

    errors = []
    total_lessons = 0
    total_exercises = 0

    # Starters must not hand over the answer, otherwise the exercise cannot be
    # practised: see backend/starter_leak_audit.py for the leak patterns.
    for leak in audit_starter_leaks():
        errors.append(
            f"[{leak.file}/{leak.lesson_id}] Starter code leaks the answer "
            f"({leak.rule}): {leak.starter_line!r} reveals {leak.answer!r}."
        )

    for lang, curr in curriculums.items():
        print(f"\nAuditing [{lang.upper()}] curriculum: '{curr.course.title}'")

        seen_module_ids = set()
        seen_concept_ids = set()
        seen_lesson_ids = set()
        seen_sublesson_ids = set()
        seen_exercise_ids = set()

        for module in curr.modules:
            if module.id in seen_module_ids:
                errors.append(f"[{lang}] Duplicate module ID: {module.id}")
            seen_module_ids.add(module.id)

        for concept_id, concept in curr.concepts.items():
            if concept_id in seen_concept_ids:
                errors.append(f"[{lang}] Duplicate concept ID: {concept_id}")
            seen_concept_ids.add(concept_id)

        for lesson in curr.lessons:
            total_lessons += 1
            if lesson.id in seen_lesson_ids:
                errors.append(f"[{lang}] Duplicate lesson ID: {lesson.id}")
            seen_lesson_ids.add(lesson.id)

            # Validate lesson tests
            for test in lesson.tests:
                if not test.expected_stdout and not test.unittest_code and not test.test_code:
                    errors.append(f"[{lang}/{lesson.id}] Test '{test.name}' lacks execution assertion.")

            # Validate sublessons & exercises
            for sub in lesson.sublessons:
                if sub.id in seen_sublesson_ids:
                    errors.append(f"[{lang}/{lesson.id}] Duplicate sublesson ID: {sub.id}")
                seen_sublesson_ids.add(sub.id)

                for ex in sub.exercises:
                    total_exercises += 1
                    if ex.id in seen_exercise_ids:
                        errors.append(f"[{lang}/{lesson.id}] Duplicate exercise ID: {ex.id}")
                    seen_exercise_ids.add(ex.id)
                    validate_exercise(lang, lesson.id, ex, errors)

            # Validate mastery exam exercises
            for ex in lesson.mastery_exam:
                total_exercises += 1
                if ex.id in seen_exercise_ids:
                    errors.append(f"[{lang}/{lesson.id}] Duplicate exam exercise ID: {ex.id}")
                seen_exercise_ids.add(ex.id)
                validate_exercise(lang, lesson.id, ex, errors)

    print(f"\nTotal Lessons Audited: {total_lessons}")
    print(f"Total Exercises Audited: {total_exercises}")

    if errors:
        print(f"\n❌ AUDIT FAILED with {len(errors)} issues:")
        for err in errors:
            print(f"  - {err}")
        return False

    print("\n✅ ALL CURRICULUMS PASSED INTEGRITY AUDIT!")
    return True


if __name__ == "__main__":
    success = validate_all_curriculums()
    sys.exit(0 if success else 1)
