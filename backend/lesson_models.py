from pydantic import BaseModel, Field


class ConceptDefinition(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$", min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    prerequisites: list[str] = Field(default_factory=list, max_length=20)


class DeterministicTestSpec(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=240)
    # stdout-matching mode (legacy / simple exercises)
    stdin: str = Field(default="", max_length=64 * 1024)
    expected_stdout: str | None = Field(default=None, max_length=64 * 1024)
    # unittest method mode (Exercism-style exercises)
    # When set, the runner executes this method body inside a TestCase class
    # together with the student's code loaded into the test namespace.
    unittest_code: str | None = Field(default=None, max_length=64 * 1024)
    required: bool = True


class CompletionRequirements(BaseModel):
    required_test_names: list[str] = Field(default_factory=list, max_length=20)


class LessonSource(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    url: str = Field(default="", max_length=500)
    license: str = Field(default="", max_length=80)


class LessonDefinition(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$", min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    order: int = Field(ge=1)
    difficulty: str = Field(min_length=1, max_length=40)
    duration_minutes: int = Field(ge=1, le=240)
    starter_code: str = Field(max_length=64 * 1024)
    solution_code: str | None = Field(default=None, max_length=64 * 1024)
    concepts: list[str] = Field(default_factory=list, max_length=20)
    prerequisites: list[str] = Field(default_factory=list, max_length=20)
    learning_objectives: list[str] = Field(default_factory=list, max_length=20)
    tests: list[DeterministicTestSpec] = Field(min_length=1, max_length=40)
    completion_requirements: CompletionRequirements = Field(default_factory=CompletionRequirements)
    static_hints: list[str] = Field(default_factory=list, max_length=4)
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


class PublicLessonView(BaseModel):
    """Safe public projection of a lesson returned by the lesson detail API.

    Contains only information the student UI needs to display the lesson and
    allow code submission.  All internal grading implementation — test code,
    expected outputs, completion requirements — is deliberately excluded so
    that students cannot inspect the answer key through the API.
    """

    id: str
    title: str
    description: str
    order: int
    difficulty: str
    duration_minutes: int
    starter_code: str
    concepts: list[str] = []
    prerequisites: list[str] = []
    learning_objectives: list[str] = []
    source: LessonSource | None = None

    @classmethod
    def from_lesson(cls, lesson: "LessonDefinition") -> "PublicLessonView":
        return cls(
            id=lesson.id,
            title=lesson.title,
            description=lesson.description,
            order=lesson.order,
            difficulty=lesson.difficulty,
            duration_minutes=lesson.duration_minutes,
            starter_code=lesson.starter_code,
            concepts=list(lesson.concepts),
            prerequisites=list(lesson.prerequisites),
            learning_objectives=list(lesson.learning_objectives),
            source=lesson.source,
        )


class LessonSummary(BaseModel):
    id: str
    title: str
    order: int
    difficulty: str
    duration_minutes: int
    status: str


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
    current_lesson_id: str | None = None
