#!/usr/bin/env python3
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.curriculum_loader import load_all_curriculums


def validate_all_curriculums() -> bool:
    print("=== Patchwork Curriculum Integrity Audit ===")
    curriculums = load_all_curriculums()
    if not curriculums:
        print("ERROR: No curriculums found!")
        return False

    errors = []
    total_lessons = 0
    total_exercises = 0

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

                    ex_type = ex.type.lower().strip()
                    exp = ex.correct_answer

                    # Check placeholder or empty question
                    q_text = (ex.question or ex.title or "").strip()
                    if not q_text or "placeholder" in q_text.lower() or q_text.lower() == "todo":
                        errors.append(f"[{lang}/{lesson.id}/{ex.id}] Question text is empty or placeholder.")

                    # Check pre-solved starter code
                    starter = (ex.starter_code or getattr(ex, "code", "") or "").strip()
                    solution = (ex.solution_code or "").strip()
                    if starter and solution and starter == solution:
                        errors.append(f"[{lang}/{lesson.id}/{ex.id}] Pre-solved code detected: starter_code matches solution_code.")
                    if starter and isinstance(exp, str) and exp.strip() and starter == exp.strip():
                        errors.append(f"[{lang}/{lesson.id}/{ex.id}] Pre-solved code detected: starter_code matches correct_answer.")

                    if ex_type in ("mcq", "true_false", "output_prediction", "debugging", "identify_error"):
                        if exp is None or exp == "":
                            errors.append(f"[{lang}/{lesson.id}/{ex.id}] Type '{ex_type}' missing correct_answer.")
                        if ex_type == "mcq":
                            if not ex.options or len(ex.options) < 2:
                                errors.append(f"[{lang}/{lesson.id}/{ex.id}] MCQ requires at least 2 options.")
                            elif isinstance(exp, str):
                                if exp not in ex.options and not exp.isdigit() and exp.lower() not in [o.lower() for o in ex.options]:
                                    errors.append(f"[{lang}/{lesson.id}/{ex.id}] MCQ answer '{exp}' not found in options {ex.options}.")

                    elif ex_type in ("fill_blank", "code_completion"):
                        if exp is None or (isinstance(exp, list) and len(exp) == 0):
                            errors.append(f"[{lang}/{lesson.id}/{ex.id}] Type '{ex_type}' missing correct_answer.")

                    elif ex_type == "select_multiple":
                        if exp is None or (isinstance(exp, list) and len(exp) == 0):
                            errors.append(f"[{lang}/{lesson.id}/{ex.id}] Type select_multiple missing correct_answer.")
                        if not ex.options or len(ex.options) < 2:
                            errors.append(f"[{lang}/{lesson.id}/{ex.id}] Select_multiple requires options.")

                    elif ex_type == "ordering":
                        if not isinstance(exp, list) or len(exp) == 0:
                            errors.append(f"[{lang}/{lesson.id}/{ex.id}] Type ordering missing list correct_answer.")

                    elif ex_type == "matching":
                        if not ex.pairs and not isinstance(exp, dict):
                            errors.append(f"[{lang}/{lesson.id}/{ex.id}] Type matching missing pairs definition.")

                    elif ex_type == "code":
                        if not ex.tests and not ex.starter_code:
                            errors.append(f"[{lang}/{lesson.id}/{ex.id}] Code exercise missing starter_code or tests.")

            # Validate mastery exam exercises
            for ex in lesson.mastery_exam:
                total_exercises += 1
                if ex.id in seen_exercise_ids:
                    errors.append(f"[{lang}/{lesson.id}] Duplicate exam exercise ID: {ex.id}")
                seen_exercise_ids.add(ex.id)

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
