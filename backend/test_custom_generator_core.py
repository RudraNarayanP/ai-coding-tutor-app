import pytest
from backend.custom_course_generator import (
    CourseGenerationRequest,
    InputValidator,
    LearningDomainClassifier,
    LearningDomain,
    StructureValidator,
    ConceptGraph,
    ConceptNode,
    CurriculumBlueprint,
    UnitBlueprint,
    LessonSlot,
    CurriculumGenerator,
)
from backend.lesson_models import ExerciseDefinition, LessonDefinition

def test_input_validator_valid():
    req = CourseGenerationRequest(
        material_type="youtube_url",
        content="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    )
    InputValidator.validate(req)


def test_input_validator_invalid_host():
    req = CourseGenerationRequest(
        material_type="youtube_url",
        content="https://malicious.com/watch?v=123",
    )
    with pytest.raises(ValueError, match="domain 'malicious.com' is not allowed"):
        InputValidator.validate(req)


def test_learning_domain_classifier():
    classifier = LearningDomainClassifier()
    graph = ConceptGraph(
        nodes=[
            ConceptNode(
                id="derivative",
                label="Derivatives and Integrals",
                description="Calculus fundamentals",
                source_segments=[1],
                difficulty="foundational",
                domain_tags=["calculus", "math"],
                learning_objectives=["Calculate derivatives"],
            )
        ],
        edges=[],
        detected_domain="mathematics",
        detected_difficulty="beginner",
        source_summary="Math summary",
    )
    domain = classifier.classify(graph)
    assert domain == LearningDomain.MATHEMATICS

    exercises = classifier.select_exercise_types(
        domain=LearningDomain.MATHEMATICS,
        lesson_type="checkpoint",
        learning_objectives=["calculate derivatives"],
    )
    assert "calculation" in exercises


def test_exercise_definition_none_coercion():
    from backend.lesson_models import ExerciseDefinition
    ex = ExerciseDefinition(
        id="ex-none-test",
        title=None,
        type="mcq",
        question="Test Question",
        starter_code=None,
        explanation=None,
        options=None,
    )
    assert ex.starter_code == ""
    assert ex.title == ""
    assert ex.explanation == ""
    assert ex.options == []


def test_structure_validator():
    validator = StructureValidator()
    graph = ConceptGraph(
        nodes=[
            ConceptNode("c1", "Concept 1", "desc", [1], "core", [], ["obj"])
        ],
        edges=[],
        detected_domain="general",
        detected_difficulty="beginner",
        source_summary="",
    )
    slots = [
        LessonSlot("learn", ["c1"], ["obj"], "beginner", 5, False, ["mcq"]),
        LessonSlot("checkpoint", ["c1"], ["obj"], "intermediate", 10, True, ["short_answer"]),
    ]
    blueprint = CurriculumBlueprint(
        units=[UnitBlueprint("Unit 1", ["c1"], slots, "Rationale")],
        total_lessons=2,
        domain="general",
        sequencing_rationale="Rationale",
    )
    res = validator.validate(blueprint, graph)
    assert res.valid is True


def _make_slot(slot_type: str = "practice") -> LessonSlot:
    return LessonSlot(
        type=slot_type,
        concept_ids=["c1"],
        learning_objectives=["obj"],
        difficulty="beginner",
        duration_minutes=5,
        test_out_eligible=False,
        suggested_exercise_types=["mcq"],
    )


def test_exercise_definition_accepts_null_starter_code():
    ex = ExerciseDefinition(id="ex-1", title="T", type="tiny_coding", starter_code=None)
    assert ex.starter_code == ""


def test_exercise_definition_default_starter_code_empty():
    ex = ExerciseDefinition(id="ex-2", title="T", type="mcq")
    assert ex.starter_code == ""


def test_lesson_definition_accepts_null_starter_code():
    lesson = LessonDefinition.model_validate(
        {
            "id": "lesson-1",
            "title": "Lesson 1",
            "description": "desc",
            "order": 1,
            "difficulty": "beginner",
            "duration_minutes": 5,
            "starter_code": None,
        }
    )
    assert lesson.starter_code == ""


@pytest.mark.asyncio
async def test_build_lesson_definition_mcq_null_starter_code():
    """Regression: mcq exercises previously passed starter_code=None, which failed
    ExerciseDefinition validation (starter_code is a non-optional str)."""
    generator = CurriculumGenerator(provider=object())  # provider unused by this method
    lesson = generator._build_lesson_definition(
        lesson_id="course-lesson-1",
        course_id="course",
        unit_id="course-mod-1",
        unit_title="Unit 1",
        order=1,
        slot=_make_slot(),
        domain="general",
    )
    assert lesson.sublessons[0].exercises[0].starter_code == ""


@pytest.mark.asyncio
async def test_build_lesson_definition_tiny_coding_keeps_starter_code():
    generator = CurriculumGenerator(provider=object())
    lesson = generator._build_lesson_definition(
        lesson_id="course-lesson-2",
        course_id="course",
        unit_id="course-mod-1",
        unit_title="Unit 1",
        order=1,
        slot=_make_slot("checkpoint"),
        domain="programming",
    )
    assert lesson.sublessons[0].exercises[0].starter_code.startswith("# Write your solution")
