from backend.curriculum_loader import load_all_curriculums

def test_audit_all_curriculums():
    curriculums = load_all_curriculums()
    assert len(curriculums) >= 5

    for lang, curr in curriculums.items():
        for module in curr.modules:
            for lesson in module.lessons:
                # Audit sublesson exercises
                for sub in lesson.sublessons:
                    for ex in sub.exercises:
                        ex_type = ex.type.lower().strip()
                        if ex_type in ("mcq", "true_false", "output_prediction", "debugging"):
                            assert ex.options, f"{lang}/{lesson.id}/{ex.id} missing options"
                            assert ex.correct_answer is not None, f"{lang}/{lesson.id}/{ex.id} missing correct_answer"
                            if isinstance(ex.correct_answer, str):
                                assert ex.correct_answer in ex.options, f"{lang}/{lesson.id}/{ex.id} correct_answer '{ex.correct_answer}' not in options {ex.options}"

                # Audit mastery exam exercises
                for ex in lesson.mastery_exam:
                    ex_type = ex.type.lower().strip()
                    if ex_type in ("mcq", "true_false", "output_prediction", "debugging"):
                        assert ex.options, f"{lang}/{lesson.id}/{ex.id} (exam) missing options"
                        assert ex.correct_answer is not None, f"{lang}/{lesson.id}/{ex.id} (exam) missing correct_answer"
                        if isinstance(ex.correct_answer, str):
                            assert ex.correct_answer in ex.options, f"{lang}/{lesson.id}/{ex.id} (exam) correct_answer '{ex.correct_answer}' not in options {ex.options}"

if __name__ == "__main__":
    test_audit_all_curriculums()
    print("All curriculum exercise options and correct_answer values verified successfully!")
