import asyncio
import logging
import os
import time
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .ai_models import OllamaHealth, ProvidersOverview, ProviderStatus, TutorRequest, TutorResponse
from .ai_provider import AIProvider, ALL_PROVIDERS, OllamaProvider, get_ai_provider
from .api_settings import (
    ApiKeyValidationResult,
    ProviderInfo,
    get_all_providers_info,
    get_provider_info,
    remove_provider_key,
    update_provider_key,
    validate_provider_key,
)
from pathlib import Path
from .curriculum_loader import CurriculumLoader, load_all_curriculums
from .lesson_engine import LessonEngine, ProgressionStore
from .user_store import LeaderboardEntry, UserProfile, UserStore
from .lesson_models import (
    CourseDefinition,
    CourseSummary,
    Curriculum,
    LessonProgress,
    LessonSummary,
    ModuleReference,
    ProgressionResult,
    ProgressionState,
    PublicLessonView,
)
from .custom_course_generator import (
    ConceptGraph,
    ConceptGraphBuilder,
    CourseGenerationRequest,
    CourseSerializer,
    CurriculumGenerator,
    CurriculumSequencer,
    DuplicateDetector,
    GeneratedCourseMetadata,
    GeneratedCoursePreview,
    GeneratedCourseStore,
    GenerationError,
    GenerationJob,
    IngestionError,
    InputValidator,
    RegenerateLessonRequest,
    RegenerateUnitRequest,
    SourceDocument,
    SourceIngestionService,
    StructureValidator,
    QualityGate,
    UnitBlueprint,
    build_custom_curriculum_from_text,
)
from .sandbox import SandboxError, sandbox
from .tutor_service import TutorService

logger = logging.getLogger("patchwork-tutor")

app = FastAPI(title="Patchwork AI Tutor")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CodeSubmission(BaseModel):
    code: str = Field(max_length=64 * 1024)


class ProviderSelection(BaseModel):
    provider: str


class CourseSelection(BaseModel):
    language: str


class ExerciseSubmissionRequest(BaseModel):
    exercise_id: str
    sublesson_id: str | None = None
    payload: dict = Field(default_factory=dict)


class TestOutRequest(BaseModel):
    submissions: dict[str, dict] = Field(default_factory=dict)


class ProfileUpdateRequest(BaseModel):
    user_id: str = "default_user"
    username: str | None = None
    streak: int | None = None
    xp: int | None = None


base_path = Path(__file__).resolve().parent
curriculum_root = base_path.parent / "curriculum"
course_serializer = CourseSerializer(curriculum_root)
generated_store = GeneratedCourseStore()
duplicate_detector = DuplicateDetector(course_serializer)
ingestion_service = SourceIngestionService()

# Startup sweep of abandoned drafts
generated_store.sweep_abandoned_drafts(course_serializer)

loaded_curriculums = load_all_curriculums()
loaded_stores = {}
for lang, curr in loaded_curriculums.items():
    if lang.startswith("custom-"):
        loaded_stores[lang] = ProgressionStore(curr, storage_path=base_path / f"progression_state_generated_{lang}.json")
    else:
        loaded_stores[lang] = ProgressionStore(curr, storage_path=base_path / f"progression_state_{lang}.json")

user_store = UserStore(storage_path=base_path / "users_state.json")

lesson_engine = LessonEngine(
    executor=sandbox,
    curriculums=loaded_curriculums,
    stores=loaded_stores,
)

# Global active provider setting
current_provider_id = os.getenv("AI_PROVIDER", "ollama").lower().strip()
fallback_provider_id = os.getenv("AI_FALLBACK_PROVIDER", "").lower().strip() or None

def get_current_provider() -> AIProvider:
    return get_ai_provider(current_provider_id)

def get_fallback_provider() -> AIProvider | None:
    return get_ai_provider(fallback_provider_id) if fallback_provider_id else None

tutor_service = TutorService(provider=get_current_provider(), fallback_provider=get_fallback_provider())

COURSE_METADATA = {
    "python": {
        "is_primary": True,
        "tagline": "AI, automation & general programming",
        "description": "Python fundamentals, data structures, algorithms, automation, backend, and AI/ML foundations.",
    },
    "cpp": {
        "is_primary": True,
        "tagline": "Performance, systems & deep programming",
        "description": "C++ fundamentals, memory, pointers/references, performance, systems concepts, and modern C++.",
    },
    "javascript": {
        "is_primary": True,
        "tagline": "Web & application development",
        "description": "JavaScript fundamentals, browser/DOM, events, async programming, modules, APIs, Node.js, and web application foundations.",
    },
    "typescript": {
        "is_primary": True,
        "tagline": "Typed modern application development",
        "description": "JavaScript relationship, static typing, interfaces, unions, narrowing, generics, classes, modules, and application architecture.",
    },
    "sql": {
        "is_primary": True,
        "tagline": "Databases & data",
        "description": "Relational database fundamentals, tables, SELECT, JOINs, aggregation, subqueries, CTEs, transactions, views, indexes, and window functions.",
    },
    "java": {
        "is_primary": False,
        "tagline": "Enterprise & object-oriented development",
        "description": "Java fundamentals, object-oriented programming, methods, arrays, classes, and enterprise patterns.",
    },
    "ai": {
        "is_primary": False,
        "tagline": "AI application development & LLM patterns",
        "description": "HTTP/APIs, JSON, env vars, calling model APIs, structured outputs, prompt design, tool calling, embeddings, RAG, and storing AI data in SQL.",
    },
}


@app.get("/api/health")
async def health():
    active_prov = get_current_provider()
    st = await active_prov.health()
    return {
        "status": "ok",
        "provider": active_prov.provider_id,
        "available": st.available,
        "ollama": await OllamaProvider().health(),
    }


@app.get("/api/health/ollama", response_model=OllamaHealth)
async def ollama_health():
    ol = OllamaProvider()
    st = await ol.health()
    return OllamaHealth(
        available=st.available,
        model=st.model,
        base_url=ol.base_url,
        error=st.error,
    )


@app.get("/api/ai/providers", response_model=ProvidersOverview)
async def get_ai_providers():
    statuses: list[ProviderStatus] = []
    for pid in ALL_PROVIDERS:
        prov = get_ai_provider(pid)
        st = await prov.health()
        st.is_current = (pid == current_provider_id)
        statuses.append(st)

    return ProvidersOverview(
        current_provider=current_provider_id,
        fallback_provider=fallback_provider_id,
        providers=statuses,
    )


@app.get("/api/ai/health", response_model=ProviderStatus)
async def get_ai_health():
    prov = get_current_provider()
    st = await prov.health()
    st.is_current = True
    return st


@app.post("/api/ai/select", response_model=ProviderStatus)
async def select_ai_provider(req: ProviderSelection):
    global current_provider_id
    if req.provider.lower() not in ALL_PROVIDERS:
        raise HTTPException(status_code=400, detail={"error": "unknown_provider"})
    current_provider_id = req.provider.lower()
    tutor_service.provider = get_current_provider()
    st = await tutor_service.provider.health()
    st.is_current = True
    return st


@app.get("/api/courses", response_model=list[CourseSummary])
async def get_courses():
    courses = []
    for lang, curr in lesson_engine.curriculums.items():
        store = lesson_engine.stores.get(lang, lesson_engine.store)
        state = store.state()
        meta = COURSE_METADATA.get(lang, {
            "is_primary": False,
            "tagline": "Programming & Development",
            "description": f"{curr.course.title} course track.",
        })
        courses.append(
            CourseSummary(
                id=curr.course.id,
                title=curr.course.title,
                language=curr.course.language,
                lesson_count=len(curr.lessons),
                completed_count=len(state.completed_lesson_ids),
                is_primary=meta["is_primary"],
                tagline=meta["tagline"],
                description=meta["description"],
            )
        )
    return courses


@app.post("/api/courses/select")
async def select_course(req: CourseSelection):
    lang = req.language.lower().strip()
    if lang not in lesson_engine.curriculums:
        raise HTTPException(status_code=400, detail={"error": "unknown_course_language"})
    lesson_engine.active_language = lang
    return {"status": "ok", "active_language": lang}


@app.get("/api/progression", response_model=ProgressionState)
async def get_progression(language: str | None = None):
    lang = (language or lesson_engine.active_language).lower().strip()
    store = lesson_engine.stores.get(lang, lesson_engine.store)
    return store.state()


@app.get("/api/lessons", response_model=list[LessonSummary])
async def get_lessons(language: str | None = None):
    return lesson_engine.summaries(language=language)


@app.get("/api/lessons/{lesson_id}", response_model=PublicLessonView)
async def get_lesson(lesson_id: str):
    try:
        lesson = lesson_engine.get_lesson(lesson_id)
        lang = lesson_engine.get_lesson_language(lesson_id)
        curr = lesson_engine.curriculums[lang]
        unit_id = None
        unit_title = None
        for module in curr.modules:
            if any(l.id == lesson_id for l in module.lessons):
                unit_id = module.id
                unit_title = module.title
                break
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "lesson_not_found"}) from exc
    return PublicLessonView.from_lesson(lesson, unit_id=unit_id, unit_title=unit_title)


@app.get("/api/lessons/{lesson_id}/solution")
async def get_lesson_solution(lesson_id: str):
    try:
        lesson = lesson_engine.get_lesson(lesson_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "lesson_not_found"}) from exc
    return {"solution_code": lesson_engine.get_solution_code(lesson)}


async def submit_lesson(lesson_id: str, request: CodeSubmission) -> ProgressionResult:
    try:
        return await lesson_engine.run_lesson(lesson_id, request.code)
    except SandboxError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": "sandbox_unavailable", "message": str(exc)},
        ) from exc


@app.post("/api/lessons/{lesson_id}/run", response_model=ProgressionResult)
async def run_lesson(lesson_id: str, request: CodeSubmission):
    try:
        lesson_engine.get_lesson(lesson_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "lesson_not_found"}) from exc
    return await submit_lesson(lesson_id, request)


@app.post("/api/lessons/{lesson_id}/submit-exercise")
async def submit_exercise(lesson_id: str, request: ExerciseSubmissionRequest, user_id: str = "default_user"):
    try:
        lesson_engine.get_lesson(lesson_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "lesson_not_found"}) from exc
    res = await lesson_engine.submit_exercise(
        lesson_id=lesson_id,
        sublesson_id=request.sublesson_id,
        exercise_id=request.exercise_id,
        payload=request.payload,
    )
    if res.get("xp_awarded", 0) > 0:
        user_store.update_user_xp(user_id, res["xp_awarded"])
    return res


@app.post("/api/lessons/{lesson_id}/test-out")
async def test_out_lesson(lesson_id: str, request: TestOutRequest, user_id: str = "default_user"):
    try:
        lesson_engine.get_lesson(lesson_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "lesson_not_found"}) from exc
    res = await lesson_engine.run_test_out(lesson_id=lesson_id, submissions=request.submissions)
    if res.get("xp_awarded", 0) > 0:
        user_store.update_user_xp(user_id, res["xp_awarded"])
    return res


@app.get("/api/leaderboard", response_model=list[LeaderboardEntry])
async def get_leaderboard(user_id: str = "default_user"):
    active_xp = lesson_engine.store.state().xp
    user = user_store.get_or_create_user(user_id)
    if active_xp > user.xp:
        user_store.set_user_xp(user_id, active_xp)
    return user_store.get_leaderboard(current_user_id=user_id)


@app.get("/api/user/profile", response_model=UserProfile)
async def get_user_profile(user_id: str = "default_user"):
    active_xp = lesson_engine.store.state().xp
    user = user_store.get_or_create_user(user_id)
    if active_xp > user.xp:
        user = user_store.set_user_xp(user_id, active_xp)
    return user


@app.post("/api/user/profile", response_model=UserProfile)
async def update_user_profile(req: ProfileUpdateRequest):
    if req.xp is not None:
        user_store.set_user_xp(req.user_id, req.xp)
    return user_store.update_profile(
        user_id=req.user_id,
        username=req.username,
        streak=req.streak,
    )


@app.get("/api/lessons/{lesson_id}/progress", response_model=LessonProgress)
async def get_lesson_progress(lesson_id: str):
    """Authoritative lesson progress: completed exercises, attempts, and next action."""
    try:
        lesson_engine.get_lesson(lesson_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "lesson_not_found"}) from exc
    return lesson_engine.lesson_progress(lesson_id)


@app.post("/api/run", response_model=ProgressionResult)
async def run_current_lesson(request: CodeSubmission):
    current_lesson_id = lesson_engine.store.state().current_lesson_id
    if current_lesson_id is None:
        raise HTTPException(status_code=409, detail={"error": "course_complete"})
    return await submit_lesson(current_lesson_id, request)


async def run_generation_pipeline(job: GenerationJob) -> None:
    job.status = "generating"
    provider = get_current_provider()

    try:
        # Stage 1: Reading source
        s0 = job.stages[0]
        s0.state = "active"
        doc = await ingestion_service.ingest(
            material_type=job.request.material_type,
            content=job.request.content,
            title=job.request.title,
            filename=job.request.filename,
        )
        s0.state = "done"

        # Stage 2 & 3: Understanding topics & Building prerequisites
        s1, s2 = job.stages[1], job.stages[2]
        s1.state = "active"
        graph_builder = ConceptGraphBuilder(provider)
        graph = await graph_builder.build(doc)
        s1.state = "done"
        s2.state = "done"

        # Stage 4: Designing units
        s3 = job.stages[3]
        s3.state = "active"
        sequencer = CurriculumSequencer(provider)
        validator = StructureValidator()

        blueprint = await sequencer.sequence(graph)
        val_res = validator.validate(blueprint, graph)
        if not val_res.valid:
            blueprint = await sequencer.sequence(graph, retry_hint=val_res.retry_hint)
            val_res = validator.validate(blueprint, graph)

        blueprint = validator.enforce_schema_invariants(blueprint)
        s3.state = "done"

        # Stage 5 & 6: Creating exercises & Creating checkpoints
        s4, s5 = job.stages[4], job.stages[5]
        s4.state = "active"
        generator = CurriculumGenerator(provider)

        course_id = f"custom-{uuid.uuid4().hex[:8]}"
        modules = []
        for u_idx, u_bp in enumerate(blueprint.units, start=1):
            mod = await generator.generate_unit(
                unit_blueprint=u_bp,
                graph=graph,
                doc=doc,
                course_id=course_id,
                unit_index=u_idx,
            )
            modules.append(mod)
        s4.state = "done"
        s5.state = "done"

        # Stage 7: Finalizing course
        s6 = job.stages[6]
        s6.state = "active"

        all_lessons = [l for m in modules for l in m.lessons]
        all_concepts = {c.id: c for m in modules for c in m.concepts}
        course_def = CourseDefinition(
            id=course_id,
            title=doc.title or job.request.title or "Custom AI Course",
            language=course_id,
            modules=[ModuleReference(id=m.id, path=f"modules/{m.id}.json") for m in modules],
        )

        curriculum = Curriculum(
            course=course_def,
            modules=modules,
            concepts=all_concepts,
            lessons=tuple(all_lessons),
        )

        QualityGate.validate_or_raise(curriculum, doc)

        metadata = GeneratedCourseMetadata(
            course_id=course_id,
            source_type=job.request.material_type,
            source_url=job.request.content if job.request.material_type in ("youtube_url", "youtube_playlist") else "",
            source_hash=doc.source_hash,
            title=course_def.title,
            description=f"Generated from {job.request.material_type.replace('_', ' ')} source material.",
            language=course_id,
            generated_at=time.time(),
            status="draft",
            difficulty=job.request.difficulty or graph.detected_difficulty,
            practice_intensity=job.request.practice_intensity or "balanced",
            unit_count=len(modules),
            lesson_count=len(all_lessons),
            topics=[n.label for n in graph.nodes],
            source_summary=graph.source_summary,
            sequencing_rationale=blueprint.sequencing_rationale,
            domain=graph.detected_domain,
            access_level=doc.access_level,
            access_notes=doc.access_notes,
        )

        draft_path = course_serializer.write_draft(curriculum, metadata)
        job.draft_path = draft_path
        job.course_id = course_id

        total_exercises = sum(len(sub.exercises) for l in all_lessons for sub in (l.sublessons or []))
        checkpoint_count = sum(1 for l in all_lessons if l.type == "checkpoint")

        job.preview = GeneratedCoursePreview(
            course_id=course_id,
            title=metadata.title,
            source_name=doc.title,
            source_url=metadata.source_url,
            unit_count=metadata.unit_count,
            lesson_count=metadata.lesson_count,
            exercise_count=total_exercises,
            checkpoint_count=checkpoint_count,
            topics=metadata.topics,
            difficulty=metadata.difficulty,
            domain=metadata.domain,
            language=course_id,
            estimated_minutes=sum(l.duration_minutes for l in all_lessons),
            sequencing_rationale=metadata.sequencing_rationale,
            access_notes=doc.access_notes,
        )

        s6.state = "done"
        job.status = "draft"
    except Exception as exc:
        job.status = "error"
        job.error = str(exc)
        for s in job.stages:
            if s.state == "active":
                s.state = "error"


@app.post("/api/courses/generate")
async def generate_course_alias(req: CourseGenerationRequest):
    """Alias endpoint for course generation."""
    return await generate_course(req)

@app.post("/api/generate-course")
async def generate_course(req: CourseGenerationRequest):
    try:
        InputValidator.validate(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid_input", "message": str(exc)})

    # Duplicate detection check unless forced
    if not req.force_duplicate:
        s_hash = SourceIngestionService.compute_source_hash(req.material_type, req.content or req.title)
        existing = duplicate_detector.find_duplicate(s_hash)
        if existing:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "duplicate_source",
                    "existing_course_id": existing.course_id,
                    "existing_title": existing.title,
                },
            )

    job = generated_store.create_job(req)
    asyncio.create_task(run_generation_pipeline(job))
    return {"job_id": job.job_id, "status": job.status}


@app.get("/api/generate-course/{job_id}/status")
async def get_generation_status(job_id: str):
    job = generated_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"error": "job_not_found"})
    return {
        "job_id": job.job_id,
        "status": job.status,
        "stages": [
            {"name": s.name, "label": s.label, "state": s.state} for s in job.stages
        ],
        "course_id": job.course_id,
        "preview": job.preview.model_dump() if job.preview else None,
        "error": job.error,
    }


@app.post("/api/generate-course/{job_id}/confirm")
async def confirm_generation_course(job_id: str):
    job = generated_store.get_job(job_id)
    if not job or not job.course_id or job.status != "draft":
        raise HTTPException(status_code=404, detail={"error": "draft_not_found_or_invalid"})

    active_path = course_serializer.confirm_draft(job.course_id)
    loader = CurriculumLoader(active_path)
    curr = loader.load()

    cid = curr.course.id.lower().strip()
    lesson_engine.curriculums[cid] = curr
    lesson_engine.stores[cid] = ProgressionStore(
        curr,
        storage_path=base_path / f"progression_state_generated_{cid}.json"
    )
    lesson_engine.active_language = cid
    job.status = "active"

    meta = course_serializer.load_metadata(cid)
    return CourseSummary(
        id=curr.course.id,
        title=curr.course.title,
        language=curr.course.id,
        lesson_count=len(curr.lessons),
        completed_count=0,
        is_primary=False,
        tagline="My AI Courses",
        description=meta.description or f"AI Custom Course: {curr.course.title}",
    )


@app.get("/api/generated-courses")
async def get_generated_courses():
    active_metas = course_serializer.list_active()
    return active_metas


@app.get("/api/generated-courses/{course_id}")
async def get_generated_course_detail(course_id: str):
    try:
        meta = course_serializer.load_metadata(course_id)
        curr = lesson_engine.curriculums.get(course_id)
        summary = None
        if curr:
            summary = CourseSummary(
                id=curr.course.id,
                title=curr.course.title,
                language=curr.course.id,
                lesson_count=len(curr.lessons),
                completed_count=len(lesson_engine.stores[course_id].state().completed_lesson_ids) if course_id in lesson_engine.stores else 0,
                is_primary=False,
                tagline="My AI Courses",
                description=meta.description,
            )
        return {"metadata": meta, "summary": summary}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "course_not_found"})


@app.delete("/api/generated-courses/{course_id}")
async def delete_generated_course(course_id: str):
    course_serializer.delete(course_id)
    if course_id in lesson_engine.curriculums:
        del lesson_engine.curriculums[course_id]
    if course_id in lesson_engine.stores:
        del lesson_engine.stores[course_id]
    p_state = base_path / f"progression_state_generated_{course_id}.json"
    if p_state.exists():
        p_state.unlink()
    return {"status": "ok", "deleted_course_id": course_id}


@app.put("/api/generated-courses/{course_id}")
async def update_generated_course_metadata(course_id: str, updates: dict):
    try:
        meta = course_serializer.load_metadata(course_id)
        if "title" in updates and updates["title"]:
            meta.title = updates["title"]
        if "difficulty" in updates and updates["difficulty"]:
            meta.difficulty = updates["difficulty"]
        if "practice_intensity" in updates and updates["practice_intensity"]:
            meta.practice_intensity = updates["practice_intensity"]

        # Persist updated metadata
        meta_path = course_serializer.active_dir / course_id / "_metadata.json"
        if not meta_path.exists():
            meta_path = course_serializer.drafts_dir / course_id / "_metadata.json"
        if meta_path.exists():
            with meta_path.open("w", encoding="utf-8") as f:
                f.write(meta.model_dump_json(indent=2))

        return {"status": "ok", "metadata": meta}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"error": "course_not_found"})


@app.post("/api/generated-courses/{course_id}/regenerate-lesson")
async def regenerate_course_lesson(course_id: str, req: RegenerateLessonRequest):
    curr = lesson_engine.curriculums.get(course_id)
    if not curr:
        raise HTTPException(status_code=404, detail={"error": "generated_course_not_found"})

    generator = CurriculumGenerator(get_current_provider())
    dummy_doc = SourceDocument("transcript", "", "dummy_hash", curr.course.title)
    dummy_graph = ConceptGraph([], [], "general", "beginner", "")

    new_lesson = await generator.regenerate_lesson(
        lesson_id=req.lesson_id,
        concept_ids=["core-concept"],
        graph=dummy_graph,
        doc=dummy_doc,
        pedagogical_style=req.pedagogical_style,
        course_id=course_id,
    )

    # Persist updated lesson into module file
    active_path = course_serializer.active_dir / course_id
    if active_path.exists():
        for mod in curr.modules:
            for idx, l in enumerate(mod.lessons):
                if l.id == req.lesson_id:
                    mod.lessons[idx] = new_lesson
                    mod_file = active_path / "modules" / f"{mod.id}.json"
                    with mod_file.open("w", encoding="utf-8") as f:
                        f.write(mod.model_dump_json(indent=2))
                    break

        # Reload curriculum in lesson_engine
        loader = CurriculumLoader(active_path)
        lesson_engine.curriculums[course_id] = loader.load()

    return new_lesson


@app.post("/api/generated-courses/{course_id}/regenerate-unit")
async def regenerate_course_unit(course_id: str, req: RegenerateUnitRequest):
    curr = lesson_engine.curriculums.get(course_id)
    if not curr:
        raise HTTPException(status_code=404, detail={"error": "generated_course_not_found"})

    generator = CurriculumGenerator(get_current_provider())
    dummy_doc = SourceDocument("transcript", "", "dummy_hash", curr.course.title)
    dummy_graph = ConceptGraph([], [], "general", "beginner", "")
    unit_bp = UnitBlueprint(
        title=f"Unit {req.unit_id}",
        concept_ids=["core-concept"],
        lesson_slots=[],
        pedagogical_rationale="Regenerated unit.",
    )

    new_module = await generator.regenerate_unit(
        unit_blueprint=unit_bp,
        graph=dummy_graph,
        doc=dummy_doc,
        pedagogical_style=req.pedagogical_style,
        course_id=course_id,
        unit_index=1,
    )

    # Persist updated module to disk
    active_path = course_serializer.active_dir / course_id
    if active_path.exists():
        mod_file = active_path / "modules" / f"{req.unit_id}.json"
        if not mod_file.exists():
            mod_file = active_path / "modules" / f"{new_module.id}.json"
        with mod_file.open("w", encoding="utf-8") as f:
            f.write(new_module.model_dump_json(indent=2))

        # Reload curriculum in lesson_engine
        loader = CurriculumLoader(active_path)
        lesson_engine.curriculums[course_id] = loader.load()

    return new_module





@app.post("/api/tutor", response_model=TutorResponse)
async def tutor(request: TutorRequest):
    return await tutor_service.tutor(request, active_provider=get_current_provider())


# ─── API Settings Endpoints ─────────────────────────────────────────────────

class SettingsSaveRequest(BaseModel):
    api_key: str = Field(..., min_length=1, max_length=500)
    model: str | None = None


class SettingsResponse(BaseModel):
    providers: list[ProviderInfo]
    current_provider: str
    fallback_provider: str | None = None


@app.get("/api/settings", response_model=SettingsResponse)
async def get_settings():
    """Get all provider settings and current configuration."""
    try:
        async with asyncio.timeout(15):
            providers = await get_all_providers_info()
            return SettingsResponse(
                providers=providers,
                current_provider=current_provider_id,
                fallback_provider=fallback_provider_id,
            )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail={"error": "settings_timeout"}) from exc
    except Exception as exc:
        logger.exception("get_settings error")
        raise HTTPException(status_code=500, detail={"error": "settings_error", "message": type(exc).__name__}) from exc


@app.get("/api/settings/providers/{provider}", response_model=ProviderInfo)
async def get_provider_settings(provider: str):
    """Get settings for a specific provider."""
    normalized = provider.strip().lower()
    if normalized not in ALL_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_provider", "message": f"Unknown provider: {provider}"}
        )
    try:
        async with asyncio.timeout(10):
            return await get_provider_info(normalized)
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail={"error": "provider_timeout"}) from exc
    except Exception as exc:
        logger.exception(f"get_provider_settings error for {provider}")
        raise HTTPException(status_code=500, detail={"error": "provider_error", "message": type(exc).__name__}) from exc


@app.post("/api/settings/providers/{provider}/validate", response_model=ApiKeyValidationResult)
async def validate_key(provider: str, request: SettingsSaveRequest):
    """Validate an API key without saving it."""
    normalized = provider.strip().lower()
    if normalized not in ALL_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_provider", "message": f"Unknown provider: {provider}"}
        )

    try:
        async with asyncio.timeout(15):
            result = await validate_provider_key(normalized, request.api_key)
            return result
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail={"error": "validation_timeout"}) from exc
    except Exception as exc:
        logger.exception(f"validate_key error for {provider}")
        raise HTTPException(status_code=500, detail={"error": "validation_error", "message": type(exc).__name__}) from exc


@app.post("/api/settings/providers/{provider}/save")
async def save_provider_settings(provider: str, request: SettingsSaveRequest):
    """Save API key and model for a provider."""
    normalized = provider.strip().lower()
    if normalized not in ALL_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_provider", "message": f"Unknown provider: {provider}"}
        )

    try:
        # First validate the key
        async with asyncio.timeout(15):
            validation = await validate_provider_key(normalized, request.api_key)
            if not validation.valid:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "invalid_key", "message": validation.error}
                )

        # Save the key
        update_provider_key(normalized, request.api_key, request.model)

        # Refresh tutor_service provider
        global current_provider_id
        tutor_service.provider = get_current_provider()

        return {
            "success": True,
            "provider": normalized,
            "key_masked": validation.key_masked,
            "message": f"{normalized.title()} API key saved successfully"
        }
    except HTTPException:
        raise
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail={"error": "save_timeout"}) from exc
    except Exception as exc:
        logger.exception(f"save_provider_settings error for {provider}")
        raise HTTPException(status_code=500, detail={"error": "save_error", "message": type(exc).__name__}) from exc


@app.delete("/api/settings/providers/{provider}/key")
async def delete_provider_key(provider: str):
    """Delete API key for a provider."""
    normalized = provider.strip().lower()
    if normalized not in ALL_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_provider", "message": f"Unknown provider: {provider}"}
        )

    try:
        removed = remove_provider_key(normalized)
        if removed:
            tutor_service.provider = get_current_provider()

        return {
            "success": True,
            "provider": normalized,
            "message": f"{normalized.title()} API key removed"
        }
    except Exception as exc:
        logger.exception(f"delete_provider_key error for {provider}")
        raise HTTPException(status_code=500, detail={"error": "delete_error", "message": type(exc).__name__}) from exc


# ─── Progression Reset Endpoint ──────────────────────────────────────────────

@app.post("/api/progression/reset")
async def reset_progression(language: str | None = None):
    """Reset course progression. If language is specified, resets only that language; otherwise resets all."""
    targets = [language.lower().strip()] if language else list(lesson_engine.stores.keys())
    reset_langs = []
    for lang in targets:
        if lang in lesson_engine.stores:
            store = lesson_engine.stores[lang]
            store.reset()
            reset_langs.append(lang)

    # Also clean generic progression_state.json if it exists
    generic_file = base_path / "progression_state.json"
    if generic_file.exists():
        try:
            generic_file.write_text("[]", encoding="utf-8")
        except Exception:
            pass

    return {
        "success": True,
        "reset_languages": reset_langs,
        "message": "Progression reset successfully.",
    }
