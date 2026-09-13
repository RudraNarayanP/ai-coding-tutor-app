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
    assert lesson.sublessons[0].exercises[0].starter_code.startswith("# Write")


@pytest.mark.asyncio
async def test_curriculum_generator_with_source_context_and_difficulty():
    from backend.custom_course_generator import CurriculumGenerator, SourceDocument, VideoSegment
    from backend.ai_provider import get_ai_provider

    provider = get_ai_provider("ollama")
    generator = CurriculumGenerator(provider)

    doc = SourceDocument(
        source_type="transcript",
        source_url="",
        source_hash="test1234",
        title="Deep Learning and Neural Networks",
        segments=[
            VideoSegment(
                video_id="vid1",
                title="Gradient Descent",
                url="https://youtube.com/watch?v=vid1",
                position=1,
                transcript="Backpropagation computes gradients of the loss function using chain rule.",
            )
        ],
        plain_text="Backpropagation computes gradients of the loss function using chain rule.",
    )

    graph = ConceptGraph(
        nodes=[ConceptNode("backpropagation", "Backpropagation", "Gradient calculation", [1], "core", ["ml"], ["Calculate gradients"])],
        edges=[],
        detected_domain="data_science",
        detected_difficulty="expert",
        source_summary="Deep Learning overview",
    )

    blueprint = UnitBlueprint(
        title="Unit 1: Backpropagation",
        concept_ids=["backpropagation"],
        lesson_slots=[
            LessonSlot("learn", ["backpropagation"], ["Calculate gradients"], "expert", 10, False, ["mcq"])
        ],
        pedagogical_rationale="Core unit",
    )

    module_def = await generator.generate_unit(blueprint, graph, doc, "course-123", 1)
    assert len(module_def.lessons) == 1
    lesson = module_def.lessons[0]
    assert len(lesson.sublessons) > 0
    exercise = lesson.sublessons[0].exercises[0]

    # Verify fallback or generated question incorporates source context and expert difficulty
    assert exercise.question is not None
    assert "backpropagation" in exercise.question.lower() or "Backpropagation" in exercise.question
    assert exercise.options is not None and len(exercise.options) > 0


def test_quality_validator_rejects_generic_template():
    from backend.custom_course_generator import CourseQualityValidator, ExerciseDefinition

    ex_generic = ExerciseDefinition(
        id="ex-generic",
        title="Generic Ex",
        type="mcq",
        question="What is the key principle of Python presented in the lesson material?",
        options=[
            "The core mechanism and definition of Python",
            "An alternative configuration unrelated to Python",
            "A deprecated legacy behavior superseded by Python",
        ],
        correct_answer="The core mechanism and definition of Python",
        explanation="The lesson material defines Python by its core fundamental principles.",
    )

    res = CourseQualityValidator.evaluate_exercise(
        ex_generic, source_context="Python list comprehensions allow concise syntax.", domain="programming"
    )
    assert res.passed is False
    assert res.score.overall_score < 70.0
    assert len(res.feedback) > 0


def test_quality_validator_passes_specific_content_bound_exercise():
    from backend.custom_course_generator import CourseQualityValidator, ExerciseDefinition

    ex_specific = ExerciseDefinition(
        id="ex-specific",
        title="Specific Ex",
        type="mcq",
        question="According to the Python lesson, which syntax demonstrates list comprehension to square numbers?",
        options=[
            "[x**2 for x in numbers]",
            "map(lambda x: x**2, numbers)",
            "for x in numbers: square(x)",
            "list.square(numbers)",
        ],
        correct_answer="[x**2 for x in numbers]",
        explanation="Python list comprehensions use brackets [expr for item in iterable] to construct new lists from existing iterables.",
    )

    res = CourseQualityValidator.evaluate_exercise(
        ex_specific, source_context="Python list comprehensions allow concise syntax.", domain="programming"
    )
    assert res.passed is True
    assert res.score.overall_score >= 70.0


def test_source_content_extracted_fallback():
    from backend.custom_course_generator import CurriculumGenerator, LessonSlot

    generator = CurriculumGenerator(provider=object())
    slot = LessonSlot("practice", ["list-comprehensions"], ["Filtering"], "intermediate", 5, False, ["mcq"])

    ex = generator._generate_content_extracted_exercise(
        lesson_id="test-lesson-1",
        c_title="List Comprehensions",
        slot=slot,
        domain="programming",
        source_context="Python list comprehensions allow concise syntax to filter and transform iterables using brackets.",
    )

    assert ex.question is not None
    assert "List Comprehensions" in ex.question or "list comprehensions" in ex.question or "source material" in ex.question
    assert len(ex.options) == 4
    assert ex.correct_answer in ex.options


def test_system_prompt_builder_domain_specialization_and_few_shot():
    from backend.custom_course_generator import CurriculumGenerator

    generator = CurriculumGenerator(provider=object())
    prompt = generator._build_system_prompt("programming")

    assert "DOMAIN SPECIALIZATION (PROGRAMMING)" in prompt
    assert "FEW-SHOT EXAMPLES OF QUESTION QUALITY" in prompt
    assert "EXCELLENT QUESTION EXAMPLE" in prompt
    assert "TERRIBLE QUESTION EXAMPLE" in prompt
