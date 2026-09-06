import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .ai_models import OllamaHealth, ProvidersOverview, ProviderStatus, TutorRequest, TutorResponse
from .ai_provider import AIProvider, ALL_PROVIDERS, OllamaProvider, get_ai_provider
from pathlib import Path
from .curriculum_loader import load_all_curriculums
from .lesson_engine import LessonEngine, ProgressionStore
from .lesson_models import CourseSummary, LessonSummary, ProgressionResult, ProgressionState, PublicLessonView
from .sandbox import SandboxError, sandbox
from .tutor_service import TutorService

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


base_path = Path(__file__).resolve().parent
loaded_curriculums = load_all_curriculums()
loaded_stores = {
    lang: ProgressionStore(curr, storage_path=base_path / f"progression_state_{lang}.json")
    for lang, curr in loaded_curriculums.items()
}

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
        courses.append(
            CourseSummary(
                id=curr.course.id,
                title=curr.course.title,
                language=curr.course.language,
                lesson_count=len(curr.lessons),
                completed_count=len(state.completed_lesson_ids),
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


@app.post("/api/run", response_model=ProgressionResult)
async def run_current_lesson(request: CodeSubmission):
    current_lesson_id = lesson_engine.store.state().current_lesson_id
    if current_lesson_id is None:
        raise HTTPException(status_code=409, detail={"error": "course_complete"})
    return await submit_lesson(current_lesson_id, request)


@app.post("/api/tutor", response_model=TutorResponse)
async def tutor(request: TutorRequest):
    return await tutor_service.tutor(request, active_provider=get_current_provider())
