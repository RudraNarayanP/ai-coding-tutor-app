# Design: AI Custom Course Generator (Revised)

## Overview

The AI Custom Course Generator transforms user-supplied learning material into fully interactive, mastery-based Patchwork courses. The generated courses are first-class citizens — they load through the existing `CurriculumLoader`, run through the existing `LessonEngine`, award XP via the same rules, and surface in the same course library as native content.

This revision addresses five architectural critiques of the original design:

1. **Curriculum sequencing is AI-driven**, not a hardcoded Python grouping function.
2. **Exercise selection is domain-aware**, not a binary `is_programming` flag.
3. **YouTube ingestion is structured and degrades gracefully**, not a raw-text pipeline that assumes transcript access.
4. **Draft/Active lifecycle is explicit** — a course does not exist as an active course until the user confirms it.
5. **Lesson and unit regeneration are first-class** — with pedagogical style control, not just MCQ reshuffling.

---

## Architecture

### Pipeline Overview

```
User Input (URL / text / file)
  │
  ▼
InputValidator
  │
  ▼
SourceIngestionService      ← produces structured SourceDocument (per-video segments, not flat text)
  │
  ▼
ConceptGraphBuilder         ← LLM call: builds ConceptGraph (nodes + prerequisite edges)
  │
  ▼
CurriculumSequencer         ← LLM call: sequences concept graph into pedagogical unit/lesson order
  │
  ▼
StructureValidator          ← deterministic: validates schema correctness, triggers retry on violation (never restructures)
  │
  ▼
CurriculumGenerator         ← LLM call per unit: generates full lesson + exercise definitions
  │
  ▼
CourseSerializer            ← writes DRAFT to curriculum/generated/.drafts/{course_id}/
  │
  ▼
[User reviews preview]
  │
  ▼
ConfirmHandler              ← moves DRAFT → curriculum/generated/{course_id}/ → ACTIVE
  │
  ▼
Existing CurriculumLoader / LessonEngine (unchanged)
```

All stages are orchestrated by `GenerationJob`. Stages map 1:1 to the UI progress indicator.

---

### GenerationJob

File: `backend/custom_course_generator.py`

```python
@dataclass
class StageStatus:
    name: str
    label: str
    state: Literal["pending", "active", "done", "error"] = "pending"
    started_at: float | None = None
    completed_at: float | None = None

@dataclass
class GenerationJob:
    job_id: str
    request: "CourseGenerationRequest"
    status: Literal["queued", "generating", "draft", "active", "error"] = "queued"
    stages: list[StageStatus] = field(default_factory=list)
    course_id: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    preview: "GeneratedCoursePreview | None" = None
    draft_path: Path | None = None   # set when draft is written to disk
```

**Key distinction from original design:** `status = "draft"` means files exist on disk under `.drafts/` but are NOT loaded into `LessonEngine`. Only after `POST /confirm` does the course become `"active"` and get registered with the engine.

---

### InputValidator

File: `backend/custom_course_generator.py`

```python
class InputValidator:
    ALLOWED_URL_HOSTS = {"www.youtube.com", "youtube.com", "youtu.be"}
    MAX_TRANSCRIPT_CHARS = 50_000
    MAX_FILE_BYTES = 5 * 1024 * 1024
    ALLOWED_MIME_TYPES = {"text/plain", "application/pdf", "text/markdown"}

    @staticmethod
    def validate(req: "CourseGenerationRequest") -> None:
        """Raise ValueError with a user-facing message on any violation."""
```

---

### SourceIngestionService — Structured, Graceful Degradation

File: `backend/source_ingestion.py` (new file)

The fundamental redesign here: `SourceDocument` is **not** a flat blob of `raw_text`. It is a structured list of `VideoSegment` objects, each preserving its identity, metadata, and what content was actually available. This is what lets the concept graph builder understand "Video 3 builds on Video 1" rather than treating the whole playlist as one undifferentiated corpus.

```python
@dataclass
class VideoSegment:
    video_id: str
    title: str
    url: str
    position: int                        # 1-indexed within playlist
    duration_seconds: int
    transcript: str                      # empty string if unavailable
    transcript_source: str               # "api" | "yt-dlp" | "none"
    chapters: list[str]                  # chapter titles if available
    description_snippet: str             # first 500 chars of video description

@dataclass
class SourceDocument:
    source_type: str                     # "youtube_url" | "youtube_playlist" | "transcript" | "file_upload"
    source_url: str
    source_hash: str                     # sha256 of normalised URL or content fingerprint
    title: str                           # playlist/video title or user-provided title
    segments: list[VideoSegment]         # one per video; single video = list of one
    plain_text: str                      # for transcript/file sources; empty for YouTube
    total_duration_seconds: int
    access_level: str                    # "full" | "titles_only" | "text_only"
    access_notes: list[str]              # human-readable notes about what was/wasn't available
```

#### Graceful Degradation Tree

The ingestion service does NOT assume transcript access. It tries each level and records what it got:

```
YouTube URL / Playlist
      │
      ▼
[Level 1] youtube-transcript-api
      │  success → transcript_source = "api"
      │  fail    ↓
      ▼
[Level 2] yt-dlp subtitle extraction
      │  success → transcript_source = "yt-dlp"
      │  fail    ↓
      ▼
[Level 3] Titles + descriptions + chapters only
      │  always succeeds if video is public
      │  → access_level = "titles_only"
      │  → access_notes includes: "Transcript unavailable. Course structure
      │    based on video titles and descriptions. Consider pasting a
      │    transcript manually for richer content."
      │
      ▼
[Level 4] Video private / deleted / age-restricted
           → raise IngestionError with user-facing message
           → suggest paste-transcript alternative
```

For `access_level = "titles_only"`, the pipeline continues — the concept graph builder and curriculum sequencer are explicitly told in their prompts that transcript depth is unavailable and should only reason from titles, descriptions, and chapter markers. A weaker course is better than a failed course.

```python
class SourceIngestionService:
    async def ingest(self, req: "CourseGenerationRequest") -> SourceDocument: ...
    async def _ingest_youtube_video(self, url: str) -> SourceDocument: ...
    async def _ingest_youtube_playlist(self, url: str) -> SourceDocument: ...
    async def _ingest_transcript(self, text: str, title: str) -> SourceDocument: ...
    async def _ingest_file(self, b64_content: str, filename: str) -> SourceDocument: ...
    async def _fetch_video_segment(self, video_id: str, position: int) -> VideoSegment: ...
    def _try_transcript_api(self, video_id: str) -> tuple[str, str]: ...  # (text, source)
    def _try_ytdlp(self, video_id: str) -> tuple[str, str]: ...
```

Playlist ingestion preserves all video boundaries. The concept graph builder receives the full `SourceDocument.segments` list, not a concatenated string, so it can reason about which concepts appear in which video and in what order.

---

### ConceptGraphBuilder — LLM-Driven

File: `backend/custom_course_generator.py`

**Replaces the original `ContentExtractor` + `CurriculumAnalyzer` combination entirely.**

This is the first major LLM call. It does not just extract a flat topic list — it builds a concept graph with prerequisite edges. The LLM is the right tool for this because prerequisite relationships are semantic, not syntactic.

```python
@dataclass
class ConceptNode:
    id: str                          # slug, e.g. "gradient-descent"
    label: str                       # human-readable, e.g. "Gradient Descent"
    description: str                 # 1-2 sentences
    source_segments: list[int]       # which VideoSegment positions cover this concept
    difficulty: str                  # "foundational" | "core" | "advanced"
    domain_tags: list[str]           # e.g. ["optimization", "calculus", "ml"]
    learning_objectives: list[str]   # e.g. ["explain the role of learning rate", ...]

@dataclass
class ConceptGraph:
    nodes: list[ConceptNode]
    edges: list[tuple[str, str]]     # (prerequisite_concept_id, dependent_concept_id)
    detected_domain: str             # see LearningDomainClassifier below
    detected_difficulty: str         # "beginner" | "intermediate" | "advanced"
    source_summary: str              # 2–3 sentence summary for AI tutor context

class ConceptGraphBuilder:
    def __init__(self, provider: "AIProvider") -> None:
        self.provider = provider

    async def build(self, doc: SourceDocument) -> ConceptGraph: ...
    def _build_prompt(self, doc: SourceDocument) -> str: ...
    def _parse_response(self, raw: str) -> ConceptGraph: ...
```

**Prompt design:** The prompt passes:
- For YouTube: the list of segments with titles, descriptions, chapters, and transcripts (truncated per segment to fit token budget)
- For text: the plain text (truncated to 12,000 tokens)
- The instruction to produce a JSON object matching `ConceptGraph`
- Explicit instruction: "Identify prerequisite relationships. If concept B cannot be understood without concept A, add an edge (A → B). Do not add edges that are not genuinely prerequisite — just being related is not enough."

The response is parsed with `json.loads`. On parse failure, retry once with a stricter prompt. On second failure, raise `GenerationError`.

---

### CurriculumSequencer — LLM-Driven

File: `backend/custom_course_generator.py`

**This is the second LLM call, and it replaces the original hardcoded `CurriculumAnalyzer`.**

The concept graph is a DAG. Topological sort gives a valid prerequisite order, but it doesn't produce a *good pedagogical sequence*. The LLM knows that you teach probability before maximum likelihood, that you introduce intuition before formalism, that you use worked examples before asking students to derive. A Python function doesn't.

```python
@dataclass
class LessonSlot:
    type: str                        # "learn" | "practice" | "review" | "challenge" | "checkpoint"
    concept_ids: list[str]           # which ConceptNodes this slot covers
    learning_objectives: list[str]   # from the concept nodes
    difficulty: str
    duration_minutes: int
    test_out_eligible: bool
    suggested_exercise_types: list[str]  # from LearningDomainClassifier (see below)

@dataclass
class UnitBlueprint:
    title: str
    concept_ids: list[str]           # which concepts this unit covers
    lesson_slots: list[LessonSlot]
    pedagogical_rationale: str       # LLM's one-sentence explanation of why this unit is sequenced here

@dataclass
class CurriculumBlueprint:
    units: list[UnitBlueprint]
    total_lessons: int
    domain: str
    sequencing_rationale: str        # LLM's explanation of the overall sequence

class CurriculumSequencer:
    def __init__(self, provider: "AIProvider") -> None:
        self.provider = provider

    async def sequence(self, graph: ConceptGraph) -> CurriculumBlueprint: ...
    def _build_prompt(self, graph: ConceptGraph) -> str: ...
    def _parse_response(self, raw: str, graph: ConceptGraph) -> CurriculumBlueprint: ...
```

**Prompt design:** The sequencer prompt passes the full concept graph (nodes + edges) and asks the LLM to:
1. Group concepts into units where each unit has a coherent theme
2. Sequence units such that prerequisites always appear in earlier units
3. Within each unit, order lessons using the mastery pattern: `learn → practice → review → checkpoint`
4. For each lesson slot, suggest the most appropriate exercise types given the concept's learning objectives and domain
5. Explain the pedagogical rationale for the unit sequence (stored in `pedagogical_rationale`, used in course preview)

The LLM output is validated by `StructureValidator` immediately after parsing.

---

### StructureValidator — Deterministic

File: `backend/custom_course_generator.py`

This is the **only** pure-Python logic in the curriculum analysis pipeline. Its contract is narrow and explicit: **validate schema correctness and detect out-of-bounds proposals — never restructure, merge, split, or resequence what the LLM decided**.

```python
@dataclass
class ValidationResult:
    valid: bool
    violations: list[str]       # human-readable descriptions of each violation
    retry_hint: str             # appended to the sequencer's retry prompt if valid=False

class StructureValidator:
    # Hard limits — anything outside these is a malformed response, not a pedagogical choice
    MAX_UNITS = 12
    MIN_UNITS = 1
    MAX_LESSONS_PER_UNIT = 10
    MIN_LESSONS_PER_UNIT = 2
    MAX_TOTAL_LESSONS = 80

    def validate(self, blueprint: CurriculumBlueprint, graph: ConceptGraph) -> ValidationResult:
        """
        Returns ValidationResult. Does NOT modify the blueprint.

        Checks (structural correctness only):
        1. Unit count within [MIN_UNITS, MAX_UNITS].
        2. Each unit's lesson count within [MIN_LESSONS_PER_UNIT, MAX_LESSONS_PER_UNIT].
        3. Total lesson count <= MAX_TOTAL_LESSONS.
        4. All concept_ids in slots exist in graph.nodes.
        5. Every unit ends with a checkpoint slot (schema requirement).
        6. No unit contains zero learn slots (schema requirement).
        7. No duplicate lesson slot types violate the learn→practice→review→checkpoint invariant.

        On violation: returns valid=False with a retry_hint that tells the
        CurriculumSequencer exactly what constraint was breached so its retry
        prompt can ask the LLM to correct it.

        Does NOT: merge units, split units, reorder units, remove concepts,
        add lessons, or make any structural change to the blueprint.
        """

    def enforce_schema_invariants(self, blueprint: CurriculumBlueprint) -> CurriculumBlueprint:
        """
        The ONLY mutations this method is allowed to make — both are schema
        requirements, not pedagogical decisions:

        1. If a unit's final slot is not a checkpoint: append a checkpoint slot.
           (The LLM omitted it — this is a schema fix, not a curriculum decision.)
        2. If a concept_id in a slot does not exist in graph.nodes: remove that
           specific ID from the slot's concept_ids list.
           (The LLM hallucinated a concept ID — purge the invalid reference.)

        Everything else that validate() flags as a violation must be sent back
        to CurriculumSequencer for a retry, not silently restructured here.
        """
```

**The retry loop:**

```python
async def _sequence_with_validation(
    sequencer: CurriculumSequencer,
    validator: StructureValidator,
    graph: ConceptGraph,
    max_retries: int = 2,
) -> CurriculumBlueprint:
    blueprint = await sequencer.sequence(graph)
    for attempt in range(max_retries):
        result = validator.validate(blueprint, graph)
        if result.valid:
            break
        # Tell the LLM exactly what was wrong and ask it to fix its own output
        blueprint = await sequencer.sequence(graph, retry_hint=result.retry_hint)
    # After retries: apply only the narrow schema invariants (checkpoint endings, bad IDs)
    # If still invalid after retries: raise GenerationError with the violations list
    result = validator.validate(blueprint, graph)
    if not result.valid:
        raise GenerationError(
            f"Curriculum sequencing produced an invalid structure after {max_retries} retries: "
            + "; ".join(result.violations)
        )
    return validator.enforce_schema_invariants(blueprint)
```

**The key principle:** The validator never merges units, never splits units, never trims lessons, never reorders anything. If the LLM proposes 15 units, it gets told "15 units exceeds the maximum of 12 — please consolidate" and retries. The LLM decides how to consolidate. If it still returns 13 after two retries, the pipeline raises `GenerationError` and the user sees a friendly "We couldn't structure this course — please try again." The alternative — silent Python-driven merging — would produce a course whose structure the AI never actually endorsed.

---

### LearningDomainClassifier — Domain-Aware Exercise Selection

File: `backend/custom_course_generator.py`

**Replaces the `is_programming` binary flag entirely.**

The original design mapped the entire course to one of two exercise type buckets. The revised design classifies the domain per concept and selects exercise types based on learning objectives.

```python
class LearningDomain:
    PROGRAMMING       = "programming"
    MATHEMATICS       = "mathematics"
    LANGUAGE_LEARNING = "language_learning"
    SYSTEMS           = "systems"          # OS, networking, hardware
    DATA_SCIENCE      = "data_science"
    SCIENCE           = "science"          # physics, chemistry, biology
    THEORY            = "theory"           # CS theory, logic, proofs
    GENERAL           = "general"

# Exercise type pools per domain
DOMAIN_EXERCISE_POOLS: dict[str, list[str]] = {
    LearningDomain.PROGRAMMING: [
        "code_completion", "debugging", "output_prediction", "fill_blank",
        "mcq", "identify_mistake", "trace_execution", "tiny_coding",
    ],
    LearningDomain.MATHEMATICS: [
        "calculation", "proof_step_ordering", "fill_blank", "mcq",
        "identify_mistake", "worked_example_completion", "true_false",
    ],
    LearningDomain.LANGUAGE_LEARNING: [
        "recognition", "recall", "sentence_construction", "matching",
        "ordering", "fill_blank", "select_multiple", "true_false",
    ],
    LearningDomain.SYSTEMS: [
        "trace_execution", "scheduling_simulation", "mcq", "ordering",
        "debugging", "code_completion", "short_answer", "scenario_question",
    ],
    LearningDomain.DATA_SCIENCE: [
        "output_prediction", "code_completion", "mcq", "fill_blank",
        "interpretation", "identify_mistake", "calculation",
    ],
    LearningDomain.SCIENCE: [
        "prediction", "classification", "interpretation", "mcq",
        "ordering", "true_false", "short_answer", "fill_blank",
    ],
    LearningDomain.THEORY: [
        "proof_step_ordering", "mcq", "true_false", "fill_blank",
        "counterexample", "short_answer", "identify_mistake",
    ],
    LearningDomain.GENERAL: [
        "mcq", "true_false", "fill_blank", "matching",
        "ordering", "select_multiple", "short_answer", "scenario_question",
    ],
}

class LearningDomainClassifier:
    def classify(self, graph: ConceptGraph) -> str:
        """
        Returns a LearningDomain constant.
        Uses graph.detected_domain (set by ConceptGraphBuilder).
        Falls back to keyword matching on concept labels/tags if domain is 'general'.
        """

    def select_exercise_types(
        self,
        domain: str,
        lesson_type: str,          # "learn" | "practice" | "review" | "checkpoint"
        learning_objectives: list[str],
        n: int = 3,
    ) -> list[str]:
        """
        Returns n exercise type strings appropriate for this domain + lesson type + objectives.

        Rules:
        - checkpoint: always include at least one evaluative type
          (tiny_coding for programming, calculation for math, short_answer for theory/general)
        - review: prefer recall/recognition types
        - practice: prefer active production types (coding, calculation, sentence_construction)
        - learn: prefer scaffolded types (fill_blank, mcq, trace_execution)
        - learning_objectives are used to break ties:
          if any objective contains "implement" → prefer coding types
          if any objective contains "explain" → prefer short_answer or scenario_question
          if any objective contains "identify" → prefer mcq or classification
          if any objective contains "calculate" → prefer calculation or fill_blank
        """
```

The `suggested_exercise_types` field on `LessonSlot` is populated by `LearningDomainClassifier.select_exercise_types()` during the `CurriculumSequencer` stage. The `CurriculumGenerator` then uses these suggestions as strong hints in its per-unit LLM prompt.

---

### CurriculumGenerator — LLM Call Per Unit

File: `backend/custom_course_generator.py`

One LLM call per unit (not per lesson). Receives the `UnitBlueprint` (including `suggested_exercise_types` per slot), the `ConceptGraph` (for the concepts covered by this unit), and the relevant `SourceDocument` segments.

```python
class CurriculumGenerator:
    def __init__(self, provider: "AIProvider") -> None:
        self.provider = provider

    async def generate_unit(
        self,
        unit_blueprint: UnitBlueprint,
        graph: ConceptGraph,
        doc: SourceDocument,
        course_id: str,
        unit_index: int,
    ) -> "ModuleDefinition": ...

    async def regenerate_lesson(
        self,
        lesson_id: str,
        concept_ids: list[str],
        graph: ConceptGraph,
        doc: SourceDocument,
        pedagogical_style: str,    # "conceptual" | "mathematical" | "practical" | "visual" | "socratic"
        course_id: str,
    ) -> "LessonDefinition": ...

    async def regenerate_unit(
        self,
        unit_blueprint: UnitBlueprint,
        graph: ConceptGraph,
        doc: SourceDocument,
        pedagogical_style: str,
        course_id: str,
        unit_index: int,
    ) -> "ModuleDefinition": ...

    def _build_unit_prompt(
        self,
        unit_blueprint: UnitBlueprint,
        graph: ConceptGraph,
        doc: SourceDocument,
        pedagogical_style: str | None = None,
    ) -> str: ...

    def _build_lesson_prompt(
        self,
        concept_ids: list[str],
        graph: ConceptGraph,
        doc: SourceDocument,
        lesson_type: str,
        suggested_exercise_types: list[str],
        pedagogical_style: str,
    ) -> str: ...
```

The `pedagogical_style` parameter is the key addition for regeneration. Each style injects specific instructions into the prompt:

```python
PEDAGOGICAL_STYLE_INSTRUCTIONS: dict[str, str] = {
    "conceptual": (
        "Focus on building deep intuition. Use analogies, comparisons to known concepts, "
        "and 'why does this work?' explanations. Minimize formalism. Maximize understanding."
    ),
    "mathematical": (
        "Be rigorous and precise. Include formal definitions, step-by-step derivations, "
        "and quantitative examples. Use calculation and proof-step exercises."
    ),
    "practical": (
        "Lead with working examples and real-world applications. Show before you explain. "
        "Maximize hands-on exercises and minimize abstract theory."
    ),
    "visual": (
        "Describe concepts in terms of visual models, diagrams, and spatial reasoning. "
        "Use ordering and classification exercises. Describe what a diagram would look like."
    ),
    "socratic": (
        "Teach through questions. Each lesson should guide the learner to discover the concept "
        "themselves by answering a sequence of increasingly specific questions."
    ),
}
```

The initial generation (non-regeneration) uses no `pedagogical_style` — the LLM chooses based on domain and difficulty.

---

### CourseSerializer — Draft/Active Separation

File: `backend/custom_course_generator.py`

**Replaces the original single-path write.** Drafts live in `.drafts/`, active courses live in the normal path.

```python
class CourseSerializer:
    def __init__(self, curriculum_root: Path) -> None:
        self.root = curriculum_root

    @property
    def drafts_dir(self) -> Path:
        return self.root / "generated" / ".drafts"

    @property
    def active_dir(self) -> Path:
        return self.root / "generated"

    def write_draft(self, curriculum: "Curriculum", metadata: "GeneratedCourseMetadata") -> Path:
        """
        Writes to curriculum/generated/.drafts/{course_id}/ using temp-then-rename.
        NOT visible to CurriculumLoader (which skips .drafts/).
        Returns the draft directory path.
        """

    def confirm_draft(self, course_id: str) -> Path:
        """
        Moves curriculum/generated/.drafts/{course_id}/
             → curriculum/generated/{course_id}/
        Updates _metadata.json: status = "active"
        Returns the active directory path.
        THIS is when the course becomes loadable by CurriculumLoader.
        """

    def delete(self, course_id: str) -> None:
        """Removes curriculum/generated/{course_id}/ (active) or .drafts/{course_id}/ (draft)."""

    def list_active(self) -> list["GeneratedCourseMetadata"]:
        """Reads _metadata.json from every curriculum/generated/*/ (skipping .drafts/)."""

    def list_drafts(self) -> list["GeneratedCourseMetadata"]:
        """Reads _metadata.json from every curriculum/generated/.drafts/*/."""

    def load_metadata(self, course_id: str) -> "GeneratedCourseMetadata": ...
    def save_metadata(self, course_id: str, meta: "GeneratedCourseMetadata") -> None: ...
```

**Why this matters:** Under the original design, `GET /api/generated-courses` could return a course the user had not accepted, and `LessonEngine` would try to load it. With the draft/active split:
- `CurriculumLoader` only scans `curriculum/generated/` and naturally skips `.drafts/` (dot-prefix directories are ignored by the existing glob pattern)
- The frontend never shows a course in "My AI Courses" until `POST /confirm` succeeds
- Abandoned drafts (user closed the browser mid-generation) are cleaned up by a startup sweep

---

### DuplicateDetector

File: `backend/custom_course_generator.py`

```python
class DuplicateDetector:
    def compute_hash(self, req: "CourseGenerationRequest") -> str:
        """
        youtube_url: sha256(normalised_url) — strips utm params, lowercases host, resolves youtu.be
        transcript/file: sha256(content[:4096] + str(len(content)))
        Returns 16-char hex prefix.
        """

    def find_duplicate(self, source_hash: str) -> "GeneratedCourseMetadata | None":
        """Checks active courses only (not drafts). Draft duplicates are allowed."""
```

---

### GeneratedCourseStore

File: `backend/custom_course_generator.py`

In-process registry of active `GenerationJob` objects. Completed jobs survive only as long as the process is running; finished courses survive on disk.

```python
class GeneratedCourseStore:
    MAX_JOBS_IN_MEMORY = 200

    def create_job(self, req: "CourseGenerationRequest") -> "GenerationJob": ...
    def get_job(self, job_id: str) -> "GenerationJob | None": ...
    def check_rate_limit(self, key: str, max_per_day: int = 5) -> bool: ...
    def record_generation(self, key: str) -> None: ...
    def evict_old_jobs(self) -> None: ...
    def sweep_abandoned_drafts(self, serializer: "CourseSerializer") -> int:
        """
        Called at app startup. Removes any .drafts/ directories that have no
        corresponding in-memory job (i.e., from a crashed/restarted process).
        Returns count of drafts removed.
        """
```

---

## Data Models

### CourseGenerationRequest

```python
class CourseGenerationRequest(BaseModel):
    material_type: str = Field(pattern=r"^(youtube_url|youtube_playlist|transcript|file_upload)$")
    content: str = Field(default="", max_length=50_000)
    title: str = Field(default="", max_length=120)
    filename: str | None = None
    difficulty: str | None = Field(default=None, pattern=r"^(beginner|intermediate|advanced)$")
    practice_intensity: str | None = Field(default=None, pattern=r"^(light|balanced|heavy)$")
    force_duplicate: bool = False     # skips duplicate detection when user chooses CREATE NEW VERSION
```

### GeneratedCourseMetadata

Persisted as `_metadata.json` in the course directory (draft or active).

```python
class GeneratedCourseMetadata(BaseModel):
    course_id: str
    source_type: str
    source_url: str = ""
    source_hash: str
    title: str
    description: str = ""
    language: str                     # detected domain key, e.g. "python", "general", "mathematics"
    generated_at: float
    status: str                       # "draft" | "active" | "error"
    difficulty: str
    practice_intensity: str = "balanced"
    unit_count: int
    lesson_count: int
    topics: list[str] = Field(default_factory=list)
    source_summary: str = ""          # 2–3 sentence summary passed to AI tutor context
    sequencing_rationale: str = ""    # LLM's explanation of the overall course sequence
    domain: str = "general"           # LearningDomain constant
    access_level: str = "full"        # from SourceDocument: "full" | "titles_only" | "text_only"
    access_notes: list[str] = Field(default_factory=list)  # forwarded to preview UI
```

### GeneratedCoursePreview

```python
class GeneratedCoursePreview(BaseModel):
    course_id: str
    title: str
    source_name: str
    source_url: str
    unit_count: int
    lesson_count: int
    exercise_count: int
    checkpoint_count: int
    topics: list[str]
    difficulty: str
    domain: str
    language: str
    estimated_minutes: int
    sequencing_rationale: str         # shown in preview UI as "How this course is structured"
    access_notes: list[str]           # e.g. "Transcript unavailable for 3 videos..."
```

### RegenerateLessonRequest / RegenerateUnitRequest

```python
class RegenerateLessonRequest(BaseModel):
    lesson_id: str
    pedagogical_style: str = Field(
        default="conceptual",
        pattern=r"^(conceptual|mathematical|practical|visual|socratic)$"
    )

class RegenerateUnitRequest(BaseModel):
    unit_id: str                      # module id
    pedagogical_style: str = Field(
        default="conceptual",
        pattern=r"^(conceptual|mathematical|practical|visual|socratic)$"
    )
```

---

## API Endpoints

### POST /api/generate-course

Starts async generation. Returns `job_id` immediately.

**Responses:**
- `202` — `{ "job_id": "...", "status": "queued" }`
- `400` — validation failure with user-facing `message`
- `409` — duplicate detected: `{ "error": "duplicate_source", "existing_course_id": "...", "existing_title": "..." }`
- `429` — rate limit: `{ "error": "rate_limit_exceeded" }`

### GET /api/generate-course/{job_id}/status

Returns `GenerationJobStatus`. When `status = "draft"`, `preview` is populated. Frontend transitions to preview step.

```json
{
  "job_id": "...",
  "status": "draft",
  "stages": [
    { "name": "reading_source",         "label": "Reading source",         "state": "done" },
    { "name": "understanding_topics",   "label": "Understanding topics",   "state": "done" },
    { "name": "building_prerequisites", "label": "Building prerequisites", "state": "done" },
    { "name": "designing_units",        "label": "Designing units",        "state": "done" },
    { "name": "creating_exercises",     "label": "Creating exercises",     "state": "done" },
    { "name": "creating_checkpoints",   "label": "Creating checkpoints",   "state": "done" },
    { "name": "finalizing_course",      "label": "Finalizing course",      "state": "done" }
  ],
  "course_id": "custom-a1b2c3d4",
  "preview": { ... GeneratedCoursePreview ... },
  "error": null
}
```

### POST /api/generate-course/{job_id}/confirm

**Transitions DRAFT → ACTIVE.** Moves files from `.drafts/` to active directory, registers curriculum and progression store in `LessonEngine`. This is the only moment the course enters the live system.

- `200` — `CourseSummary` (same shape as items in `GET /api/courses`)
- `404` — job not found or already confirmed/deleted
- `409` — draft files missing (generation may have been interrupted)

### GET /api/generated-courses

Lists all **active** generated courses (status = "active"). Does NOT include drafts.

### GET /api/generated-courses/{course_id}

Returns `{ "metadata": GeneratedCourseMetadata, "summary": CourseSummary }`.

### DELETE /api/generated-courses/{course_id}

Deletes active course: removes `curriculum/generated/{course_id}/`, removes progression state file, deregisters from `LessonEngine`.

### PUT /api/generated-courses/{course_id}

Updates course metadata and optionally reorders/removes units.

```json
{
  "title": "New Title",
  "difficulty": "advanced",
  "practice_intensity": "heavy",
  "remove_unit_ids": ["custom-a1b2c3d4-mod-2"],
  "unit_order": ["custom-a1b2c3d4-mod-1", "custom-a1b2c3d4-mod-3"]
}
```

Note: `PUT` can be called on a **draft** (before confirm) or an **active** course (after confirm). On active courses, the engine reloads the curriculum after writing.

### POST /api/generated-courses/{course_id}/regenerate-exercise

Regenerates a single exercise. Unchanged from original design.

### POST /api/generated-courses/{course_id}/regenerate-lesson

**New endpoint — not in original design.**

Regenerates an entire lesson with a specified pedagogical style. Does not change adjacent lessons.

```json
{ "lesson_id": "custom-a1b2c3d4-m1-l2", "pedagogical_style": "mathematical" }
```

Response: the new `LessonDefinition` JSON. Client updates its local state and the engine reloads the module.

Use case: "Unit 4 — Gradient Descent. Make this much more mathematical."

### POST /api/generated-courses/{course_id}/regenerate-unit

**New endpoint — not in original design.**

Regenerates an entire unit with a specified pedagogical style. All lessons within the unit are replaced. The unit's concept coverage and position in the course are preserved.

```json
{ "unit_id": "custom-a1b2c3d4-mod-4", "pedagogical_style": "practical" }
```

Response: the new `ModuleDefinition` JSON. Engine reloads the module after write.

This is the correct response to "I want this whole section to be more hands-on" — not just regenerating one MCQ.

---

## Frontend Components

### Tab Type Change

```typescript
// Before
type ActiveTab = 'learn' | 'characters' | 'leaderboards' | 'quests' | 'profile'

// After
type ActiveTab = 'learn' | 'create' | 'leaderboards' | 'quests' | 'profile'
```

Left sidebar nav: `🔤 CHARACTERS` → `✨ CREATE`. The `charSubTab` state, `duo-characters-view` JSX block, and the `🔤 Characters` header button are all removed. Character mascots (`PatchworkCharacter` component) remain unchanged as in-lesson companions.

### CreatePage

File: `src/components/CreatePage.tsx`

```typescript
type CreateStep = 'input' | 'generating' | 'preview' | 'editing'

interface CreatePageProps {
  onCourseReady: (courseId: string) => void
}
```

**Step 1 — input**

Three material type tabs: YouTube URL | Paste Transcript | Upload File.

On submit → `POST /api/generate-course` → 202: store `jobId`, advance to `generating`.

409 (duplicate) renders inline resolution card:
- **OPEN EXISTING** → `onCourseReady(existing_course_id)` directly
- **REGENERATE** → `DELETE /api/generated-courses/{id}` then retry
- **CREATE NEW VERSION** → retry with `force_duplicate: true`

**Step 2 — generating**

Polls `GET /api/generate-course/{jobId}/status` every 1.5s. Clears interval on `draft` or `error`.

Stage tracker UI:
- `done` → ✓ green
- `active` → pulsing dot (CSS keyframe animation)
- `pending` → ○ muted
- `error` → ✗ red + error message

If `access_notes` is non-empty on the resulting preview, show them as an informational banner (not an error): "ℹ️ Transcript was unavailable for 2 videos. Course content is based on titles and descriptions."

**Step 3 — preview**

Renders `GeneratedCoursePreview`. Shows `sequencing_rationale` as a "How this course is structured" section — this gives learners confidence that the AI actually reasoned about the content, not just listed topics.

**Step 4 — editing (optional)**

Controls:
- Course title (text input)
- Difficulty (Beginner / Intermediate / Advanced)
- Practice intensity (Light / Balanced / Heavy)
- Topic/unit list with remove buttons
- Unit drag-to-reorder (HTML5 drag API, no library)
- **Pedagogical style selector** — new, not in original design:
  ```
  Teaching style for this course:
  ○ Conceptual (intuition-first)
  ○ Mathematical (rigorous, formal)
  ● Practical (examples-first)
  ○ Visual (diagrams and models)
  ○ Socratic (guided discovery)
  ```
  Sets `pedagogical_style` sent to `PUT /api/generated-courses/{courseId}` and used if any unit is regenerated before confirming.

On SAVE & START → `PUT` with edits → `POST /confirm` → `onCourseReady`.

### GuidebookPanel

File: `src/components/GuidebookPanel.tsx`

Slide-out drawer (fixed right, `width: 340px`, `z-index: 200`) triggered by `📖 Guidebook` button in lesson workspace header. Does not navigate away from the lesson. Content is static `SYNTAX_REFERENCE` data keyed by language, extracted to `src/utils/syntaxReference.ts`.

For generated courses where `domain` is not a programming language, the panel shows "Concepts & Terminology" using the `ConceptGraph`'s node labels and descriptions instead of syntax tables.

### Lesson/Unit Regeneration UI

Inside the course map (when viewing a generated course), each unit card and each lesson node has a `⟳` regeneration button:

- **Lesson ⟳** → opens a small popover with pedagogical style selector → calls `POST /regenerate-lesson`
- **Unit ⟳** → opens a popover with pedagogical style selector + confirmation ("This will replace all X lessons in this unit") → calls `POST /regenerate-unit`

During regeneration: the unit/lesson shows a loading state. On completion: the course map re-fetches the module and updates in place without a full page reload.

---

## Implementation Notes

### Pipeline Stage → LLM Call Mapping

| Stage | LLM call? | Component |
|---|---|---|
| reading_source | No | SourceIngestionService |
| understanding_topics | **Yes** | ConceptGraphBuilder |
| building_prerequisites | **Yes** (same call as above) | ConceptGraphBuilder |
| designing_units | **Yes** (with retry loop) | CurriculumSequencer + StructureValidator |
| creating_exercises | **Yes** (per unit) | CurriculumGenerator |
| creating_checkpoints | No (schema enforcement only) | StructureValidator.enforce_schema_invariants |
| finalizing_course | No | CourseSerializer |

The `designing_units` stage covers the full `_sequence_with_validation` retry loop. If the sequencer returns an out-of-bounds structure, `StructureValidator` returns `valid=False` with a `retry_hint`, and the sequencer is called again with that hint appended to its prompt. The LLM fixes its own output. After `max_retries=2`, if still invalid, the job transitions to `error`.

The `creating_checkpoints` stage is intentionally narrow: `StructureValidator.enforce_schema_invariants` only appends a checkpoint slot if the LLM omitted the required final slot of a unit, and strips hallucinated concept IDs. It does not merge, split, or reorder anything.

### Token Budget Management

`ConceptGraphBuilder` receives the full `SourceDocument` but must fit within the LLM's context window. Strategy:
- For playlists: truncate each `VideoSegment.transcript` to `min(len(transcript), 3000 // len(segments))` chars, so total input scales with playlist size
- The concept graph prompt uses the segment structure (not flat text) so the LLM can reason about per-video concept boundaries even with truncated transcripts
- `CurriculumGenerator` receives only the concepts covered by the target unit + the relevant source segment transcripts, not the full document

### Draft Lifecycle Cleanup

At `app startup` in `main.py`:
```python
store.sweep_abandoned_drafts(serializer)
```
This removes `.drafts/` directories with no in-memory job. Drafts older than 24 hours are also eligible for cleanup.

### File Path Conventions

| Artefact | Path |
|---|---|
| Active course curriculum | `curriculum/generated/{course_id}/` |
| Draft course curriculum | `curriculum/generated/.drafts/{course_id}/` |
| Course definition | `.../course.json` |
| Module files | `.../modules/{module_id}.json` |
| Course metadata | `.../_metadata.json` |
| Progression state | `backend/progression_state_generated_{course_id}.json` |

`CurriculumLoader.load_all_curriculums()` scans `curriculum/generated/` but naturally skips `.drafts/` because the existing glob uses `iterdir()` and the dot-prefix convention means drafts are invisible to it. Add an explicit `if course_path.name.startswith('.')` guard to make this contract explicit.

### AI Provider Extension

Add `generate_structured` to the `AIProvider` protocol for deterministic JSON generation:

```python
class AIProvider(Protocol):
    name: str
    provider_id: str
    async def tutor(self, request: TutorRequest) -> str: ...
    async def generate_structured(self, system: str, user: str, max_tokens: int = 4000) -> str: ...
    async def health(self) -> ProviderStatus: ...
```

Each provider implementation calls with `temperature=0`. `generate_structured` is used by `ConceptGraphBuilder`, `CurriculumSequencer`, and `CurriculumGenerator`. `tutor` continues to be used only by `TutorService`.

### AI Tutor Context for Generated Courses

In `TutorRequest`, add:
```python
source_summary: str = ""
generated_course_id: str | None = None
```

When the active lesson belongs to a generated course, the frontend passes `source_summary` (fetched once from `GET /api/generated-courses/{course_id}` and cached in state) and `generated_course_id`. The tutor service prepends a brief context paragraph to the system prompt when these fields are present.

### Security Checklist

| Concern | Mitigation |
|---|---|
| SSRF | URL allowlist: only `youtube.com`, `youtu.be` |
| File abuse | MIME type + 5 MB size check on decoded bytes |
| LLM prompt injection | Source text in user role only, never concatenated into system prompt |
| Key exposure | All LLM calls through `ai_provider.py`; no keys in frontend |
| Runaway generation | 5/day/IP rate limit; input size caps; token budget per call |
| Verbatim reproduction | LLM prompt instructs originality; no wholesale transcript → lesson copy |
| Draft pollution | `CurriculumLoader` skips `.drafts/`; startup sweep removes orphaned drafts |

### Dependencies to Add

```
# backend/requirements.txt
youtube-transcript-api>=0.6.0
yt-dlp>=2024.1.0          # optional; guarded with try/except ImportError
python-multipart>=0.0.9   # for FastAPI UploadFile
```

### Testing Strategy

- `test_concept_graph_builder.py` — mocked provider, assert ConceptGraph structure and edge validity
- `test_curriculum_sequencer.py` — mocked provider, assert topological ordering respected in output
- `test_structure_validator.py` — pure Python, test clamping and invariant enforcement
- `test_learning_domain_classifier.py` — unit tests for domain detection and exercise type selection per domain
- `test_source_ingestion.py` — mocked httpx, test all four degradation levels
- `test_draft_lifecycle.py` — assert draft invisible to CurriculumLoader, confirm moves to active path
- `test_regenerate_lesson.py` — mocked provider, assert lesson replaced in module file
- `test_regenerate_unit.py` — mocked provider, assert all lessons in unit replaced
- `test_generation_pipeline.py` — full pipeline integration with fixture SourceDocument and mocked provider
