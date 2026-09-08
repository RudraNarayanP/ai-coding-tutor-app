from pydantic import BaseModel, Field


class ConceptDefinition(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$", min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    prerequisites: list[str] = Field(default_factory=list, max_length=20)


class DeterministicTestSpec(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=240)
    stdin: str = Field(default="", max_length=64 * 1024)
    expected_stdout: str | None = Field(default=None, max_length=64 * 1024)
    unittest_code: str | None = Field(default=None, max_length=64 * 1024)
    test_code: str | None = Field(default=None, max_length=64 * 1024)
    required: bool = True


class CompletionRequirements(BaseModel):
    required_test_names: list[str] = Field(default_factory=list, max_length=20)


class LessonSource(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    url: str = Field(default="", max_length=500)
    license: str = Field(default="", max_length=80)


class MatchingPair(BaseModel):
    left: str
    right: str


class ExerciseDefinition(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$", min_length=1, max_length=80)
    title: str = Field(default="", max_length=120)
    type: str = Field(default="code")
    question: str = Field(default="", max_length=2000)
    options: list[str] = Field(default_factory=list)
    correct_answer: str | list[str] | dict[str, str] | None = None
    blanks: list[str] = Field(default_factory=list)
    pairs: list[MatchingPair] = Field(default_factory=list)
    starter_code: str = Field(default="", max_length=64 * 1024)
    solution_code: str | None = Field(default=None, max_length=64 * 1024)
    tests: list[DeterministicTestSpec] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)
    xp_reward: int = Field(default=10, ge=0)
    explanation: str = Field(default="", max_length=2000)


class SubLessonDefinition(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$", min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    order: int = Field(default=1, ge=1)
    exercises: list[ExerciseDefinition] = Field(default_factory=list)


class LessonDefinition(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$", min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    order: int = Field(ge=1)
    difficulty: str = Field(min_length=1, max_length=40)
    duration_minutes: int = Field(ge=1, le=240)
    type: str = Field(default="learn", max_length=40)
    section_id: str = Field(default="section-1", max_length=80)
    section_title: str = Field(default="Section 1", max_length=120)
    test_out_eligible: bool = Field(default=False)
    starter_code: str = Field(default="", max_length=64 * 1024)
    solution_code: str | None = Field(default=None, max_length=64 * 1024)
    concepts: list[str] = Field(default_factory=list, max_length=20)
    prerequisites: list[str] = Field(default_factory=list, max_length=20)
    learning_objectives: list[str] = Field(default_factory=list, max_length=20)
    tests: list[DeterministicTestSpec] = Field(default_factory=list, max_length=40)
    completion_requirements: CompletionRequirements = Field(default_factory=CompletionRequirements)
    static_hints: list[str] = Field(default_factory=list, max_length=4)
    sublessons: list[SubLessonDefinition] = Field(default_factory=list)
    mastery_exam: list[ExerciseDefinition] = Field(default_factory=list)
    xp_reward: int = Field(default=25, ge=0)
    source: LessonSource | None = None


class ModuleDefinition(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$", min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    order: int = Field(ge=1)
    concepts: list[ConceptDefinition] = Field(default_factory=list, max_length=100)
    lessons: list[LessonDefinition] = Field(min_length=1, max_length=100)


class ModuleReference(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$", min_length=1, max_length=80)
    path: str = Field(min_length=1, max_length=240)


class CourseDefinition(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$", min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    language: str = Field(min_length=1, max_length=40)
    modules: list[ModuleReference] = Field(min_length=1, max_length=100)


class Curriculum(BaseModel):
    course: CourseDefinition
    modules: list[ModuleDefinition]
    concepts: dict[str, ConceptDefinition]
    lessons: tuple[LessonDefinition, ...]


class PublicExerciseView(BaseModel):
    id: str
    title: str = ""
    type: str = "code"
    question: str = ""
    options: list[str] = []
    blanks: list[str] = []
    pairs: list[MatchingPair] = []
    starter_code: str = ""
    hints: list[str] = []
    xp_reward: int = 10


class PublicSubLessonView(BaseModel):
    id: str
    title: str
    description: str = ""
    order: int = 1
    exercises: list[PublicExerciseView] = []


class PublicLessonView(BaseModel):
    """Safe public projection of a lesson returned by the lesson detail API."""

    id: str
    title: str
    description: str
    order: int
    difficulty: str
    duration_minutes: int
    starter_code: str
    type: str = "learn"
    section_id: str | None = None
    section_title: str | None = None
    unit_id: str | None = None
    unit_title: str | None = None
    concept_id: str | None = None
    concept_title: str | None = None
    test_out_eligible: bool = False
    concepts: list[str] = []
    prerequisites: list[str] = []
    learning_objectives: list[str] = []
    sublessons: list[PublicSubLessonView] = []
    mastery_exam: list[PublicExerciseView] = []
    xp_reward: int = 25
    source: LessonSource | None = None

    @classmethod
    def from_lesson(
        cls,
        lesson: "LessonDefinition",
        unit_id: str | None = None,
        unit_title: str | None = None,
        concept_id: str | None = None,
        concept_title: str | None = None,
    ) -> "PublicLessonView":
        sub_views = [
            PublicSubLessonView(
                id=s.id,
                title=s.title,
                description=s.description,
                order=s.order,
                exercises=[
                    PublicExerciseView(
                        id=e.id,
                        title=e.title,
                        type=e.type,
                        question=e.question,
                        options=e.options,
                        blanks=e.blanks,
                        pairs=e.pairs,
                        starter_code=e.starter_code,
                        hints=e.hints,
                        xp_reward=e.xp_reward,
                    )
                    for e in s.exercises
                ],
            )
            for s in lesson.sublessons
        ]
        exam_views = [
            PublicExerciseView(
                id=e.id,
                title=e.title,
                type=e.type,
                question=e.question,
                options=e.options,
                blanks=e.blanks,
                pairs=e.pairs,
                starter_code=e.starter_code,
                hints=e.hints,
                xp_reward=e.xp_reward,
            )
            for e in lesson.mastery_exam
        ]
        return cls(
            id=lesson.id,
            title=lesson.title,
            description=lesson.description,
            order=lesson.order,
            difficulty=lesson.difficulty,
            duration_minutes=lesson.duration_minutes,
            starter_code=lesson.starter_code,
            type=getattr(lesson, "type", "learn") or "learn",
            section_id=getattr(lesson, "section_id", "section-1"),
            section_title=getattr(lesson, "section_title", "Section 1"),
            unit_id=unit_id,
            unit_title=unit_title,
            concept_id=concept_id,
            concept_title=concept_title,
            test_out_eligible=getattr(lesson, "test_out_eligible", False),
            concepts=list(lesson.concepts),
            prerequisites=list(lesson.prerequisites),
            learning_objectives=list(lesson.learning_objectives),
            sublessons=sub_views,
            mastery_exam=exam_views,
            xp_reward=lesson.xp_reward,
            source=lesson.source,
        )


class CourseSummary(BaseModel):
    id: str
    title: str
    language: str
    lesson_count: int
    completed_count: int
    is_primary: bool = True
    tagline: str = ""
    description: str = ""


class LessonSummary(BaseModel):
    id: str
    title: str
    order: int
    difficulty: str
    duration_minutes: int
    status: str
    section_id: str | None = None
    section_title: str | None = None
    unit_id: str | None = None
    unit_title: str | None = None
    type: str | None = None
    test_out_eligible: bool = False


class TestResult(BaseModel):
    name: str
    passed: bool
    required: bool
    description: str = ""
    error: str | None = None
    stdout: str = ""
    stderr: str = ""
    execution_time_ms: int = 0


class ProgressionResult(BaseModel):
    lesson_id: str
    passed: bool
    completed: bool
    next_lesson_id: str | None = None
    tests: list[TestResult]
    stdout: str = ""
    stderr: str = ""
    execution_time_ms: int = 0
    error: str | None = None


class ProgressionState(BaseModel):
    completed_lesson_ids: list[str] = Field(default_factory=list)
    mastered_lesson_ids: list[str] = Field(default_factory=list)
    skipped_lesson_ids: list[str] = Field(default_factory=list)
    completed_sublesson_ids: list[str] = Field(default_factory=list)
    completed_exercise_ids: list[str] = Field(default_factory=list)
    current_lesson_id: str | None = None
    xp: int = 0
    level: int = 1


class LessonProgress(BaseModel):
    """Authoritative per-lesson progress derived from the progression store."""

    lesson_id: str
    total_exercises: int = 0
    completed_exercise_ids: list[str] = Field(default_factory=list)
    attempt_counts: dict[str, int] = Field(default_factory=dict)
    last_results: dict[str, str] = Field(default_factory=dict)
    lesson_completed: bool = False
    next_action: str = "answer"  # "answer" | "lesson_complete"
    next_lesson_id: str | None = None
    progress: dict = Field(default_factory=dict)  # {"completed": int, "total": int}
