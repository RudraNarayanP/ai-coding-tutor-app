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
)

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
