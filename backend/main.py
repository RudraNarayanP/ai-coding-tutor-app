from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .ai_models import OllamaHealth, TutorRequest, TutorResponse
from .ai_provider import AIProvider, OllamaProvider
from .lesson_engine import LessonEngine, ProgressionStore
from .lesson_models import LessonSummary, ProgressionResult, ProgressionState, PublicLessonView
from .lessons import CURRICULUM
from .sandbox import SandboxError, sandbox
from .tutor_service import TutorService

app = FastAPI(title="Patchwork Local Tutor")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class CodeSubmission(BaseModel):
    code: str = Field(max_length=64 * 1024)


lesson_engine = LessonEngine(sandbox, ProgressionStore(CURRICULUM), CURRICULUM)

provider: AIProvider = OllamaProvider()
tutor_service = TutorService(provider)


@app.get("/api/health")
async def health():
    return {"status": "ok", "ollama": await provider.health()}


@app.get("/api/health/ollama", response_model=OllamaHealth)
async def ollama_health():
    return await provider.health()


@app.get("/api/progression", response_model=ProgressionState)
async def get_progression():
    return lesson_engine.store.state()


@app.get("/api/lessons", response_model=list[LessonSummary])
async def get_lessons():
    return lesson_engine.summaries()


@app.get("/api/lessons/{lesson_id}", response_model=PublicLessonView)
async def get_lesson(lesson_id: str):
    try:
        lesson = lesson_engine.get_lesson(lesson_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "lesson_not_found"}) from exc
    return PublicLessonView.from_lesson(lesson)


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
    return await tutor_service.tutor(request)
