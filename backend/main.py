from . import env as _env  # noqa: F401 — load .env before other backend imports

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from . import learning_service
from .hearts import HeartStore
from .materials import (
    Material,
    MaterialCompletionRequest,
    MaterialCompletionResponse,
    PublicMaterial,
    to_public,
)
from .materials_data import MATERIALS
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .ai_models import OllamaHealth, ProvidersOverview, ProviderStatus, TutorRequest, TutorResponse
from .ai_provider import AIProvider, ALL_PROVIDERS, OllamaProvider, get_ai_provider, close_shared_client
from .api_settings import (
    ApiKeyValidationResult,
    ProviderInfo,
    get_all_providers_info,
    get_provider_info,
    remove_provider_key,
    update_provider_key,
    validate_provider_key,
)
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
from .source_ingestion import IngestionError, SourceIngestionService
from .sandbox import SandboxError, sandbox
from .feedback_store import FeedbackStore
from .tutor_service import TutorService
from .project_models import ProjectView, WorkspaceFile
from .project_planner import ProjectGroundingError
from .source_quality import SourceQualityError
from .project_store import ProjectStore
from . import project_service

logger = logging.getLogger("patchwork-tutor")

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_shared_client()

app = FastAPI(title="Patchwork AI Tutor", lifespan=lifespan)
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


class ExerciseFeedbackRequest(BaseModel):
    exercise_id: str = Field(min_length=1, max_length=120)
    lesson_id: str | None = Field(default=None, max_length=120)
    rating: str = Field(min_length=1, max_length=20)
    comment: str | None = Field(default=None, max_length=2000)


base_path = Path(__file__).resolve().parent
curriculum_root = base_path.parent / "curriculum"


def _env_path(var: str, default: Path) -> Path:
    """A writable-state directory that ops (and pytest) can redirect via env."""
    raw = os.getenv(var, "").strip()
    return Path(raw) if raw else default


# All authoritative runtime state lives here. Overridable so an automated run
# can never mutate a real learner's progression, hearts or saved projects.
state_root = _env_path("PATCHWORK_STATE_DIR", base_path)
project_store_root = _env_path(
    "PATCHWORK_PROJECT_DIR", curriculum_root / "generated" / "projects"
)

ingestion_service = SourceIngestionService()


loaded_curriculums = load_all_curriculums()
loaded_stores = {}
for lang, curr in loaded_curriculums.items():
    if lang.startswith("custom-"):
        loaded_stores[lang] = ProgressionStore(curr, storage_path=state_root / f"progression_state_generated_{lang}.json")
    else:
        loaded_stores[lang] = ProgressionStore(curr, storage_path=state_root / f"progression_state_{lang}.json")

user_store = UserStore(storage_path=state_root / "users_state.json")
# Hearts live on the server so the constraint cannot be edited away in devtools.
heart_store = HeartStore(storage_path=state_root / "hearts_state.json")
feedback_store = FeedbackStore(storage_path=state_root / "feedback_state.json")

# Create Course guided-project state (isolated from lessons/curriculum). Stored
# under curriculum/generated/projects/ which is already gitignored.
project_store = ProjectStore(storage_dir=project_store_root)

lesson_engine = LessonEngine(
    executor=sandbox,
    curriculums=loaded_curriculums,
    stores=loaded_stores,
)

# Global active provider setting and lock for thread/async safety
provider_lock = asyncio.Lock()
current_provider_id = os.getenv("AI_PROVIDER", "ollama").lower().strip()

def get_current_provider() -> AIProvider:
    return get_ai_provider(current_provider_id)


def _lesson_for_reference(lesson_id: str):
    """Server-side lookup of a lesson's canonical code for spoiler detection.

    The reference solution is never sent to the provider — it is only used to
    recognise when a "hint" has actually handed over the answer.
    """
    try:
        return lesson_engine.get_lesson(lesson_id)
    except KeyError:
        return None


tutor_service = TutorService(
    provider=get_current_provider(),
    lesson_lookup=_lesson_for_reference,
)

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
        "description": "HTTP/APIs, JSON, model APIs, tokenization, embeddings, prompt patterns, tool calling, RAG chunking/retrieval, and storing AI data in SQL.",
    },
    "dsa": {
        "is_primary": True,
        "tagline": "Algorithms, complexity & core data structures",
        "description": "Big O, stacks, queues, linked lists, recursion, binary search, hash maps, trees, BSTs, and graph traversals in pure Python.",
    },
    "ml-math": {
        "is_primary": True,
        "tagline": "Vectors, probability, stats & data prep for ML",
        "description": "Pure-Python vectors/matrices, probability, summary stats, data wrangling, train/test splits, and feature scaling.",
    },
    "ml": {
        "is_primary": True,
        "tagline": "Machine learning foundations from scratch",
        "description": "Linear regression, classification, loss/metrics, overfitting/regularization, and decision trees/ensembles in pure Python.",
    },
    "fullstack": {
        "is_primary": True,
        "tagline": "HTTP clients, REST, state & auth tokens",
        "description": "Full-stack client patterns: HTTP requests, REST consumption, immutable UI state, and auth token handling — coding exercises that pair with the Python backend track.",
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
    async with provider_lock:
        curr_id = current_provider_id
    statuses: list[ProviderStatus] = []
    for pid in ALL_PROVIDERS:
        prov = get_ai_provider(pid)
        st = await prov.health()
        st.is_current = (pid == curr_id)
        statuses.append(st)

    return ProvidersOverview(
        current_provider=curr_id,
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
    target_pid = req.provider.lower().strip()
    if target_pid not in ALL_PROVIDERS:
        raise HTTPException(status_code=400, detail={"error": "unknown_provider"})

    async with provider_lock:
        current_provider_id = target_pid
        new_provider = get_current_provider()
        tutor_service.provider = new_provider

    st = await new_provider.health()
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



@app.get("/api/mistakes")
async def list_mistakes(language: str | None = None, limit: int = 10):
    """Exercises the learner got wrong, re-served until they stick.

    A missed step is queued immediately; it leaves after two consecutive
    correct re-solves with a gap between them.
    """
    return {"due": lesson_engine.due_mistakes(language=language, limit=max(1, min(limit, 50)))}


@app.get("/api/materials", response_model=list[PublicMaterial])
async def list_materials(language: str | None = None, stage: str | None = None, concept: str | None = None):
    results = MATERIALS
    if language:
        results = [m for m in results if m.language.lower().strip() == language.lower().strip()]
    if stage:
        results = [m for m in results if m.recommended_stage.lower().strip() == stage.lower().strip()]
    if concept:
        results = [m for m in results if concept in m.concept_tags]
    return [to_public(m) for m in results]


@app.post("/api/materials/{material_id}/complete", response_model=MaterialCompletionResponse)
async def complete_material(material_id: str, payload: MaterialCompletionRequest):
    mat = next((m for m in MATERIALS if m.id == material_id), None)
    if not mat:
        raise HTTPException(status_code=404, detail={"error": "material_not_found"})

    lang = mat.language.lower().strip()
    store = lesson_engine.stores.get(lang, lesson_engine.store)

    passed = True
    feedback = "Material completed!"
    if mat.companion_question:
        user_ans = (payload.user_answer or "").strip()
        exp_ans = mat.companion_question.correct_answer.strip()
        passed = (user_ans.lower() == exp_ans.lower())
        feedback = "Correct! Material completed." if passed else "Incorrect answer. Try again!"

    xp_awarded = 0
    if passed:
        already_done = material_id in store.state().completed_material_ids
        store.mark_material_completed(material_id)
        if not already_done:
            xp_awarded = store.add_xp(mat.xp_reward)

    return MaterialCompletionResponse(
        material_id=material_id,
        passed=passed,
        feedback=feedback,
        xp_awarded=xp_awarded,
        total_xp=store.state().xp
    )

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


@app.get("/api/lessons/{lesson_id}/exercises/{exercise_id}/solution")
async def get_exercise_solution(lesson_id: str, exercise_id: str):
    """The canonical answer for one exercise step.

    Exercise steps render the same "Show full answer" affordance as lesson
    code, so they need the same capability; without this the button would
    silently paste the wrong thing on a step.
    """
    try:
        exercise = lesson_engine.get_exercise(lesson_id, exercise_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "exercise_not_found"}) from exc

    answer = exercise.correct_answer
    return {
        "exercise_id": exercise.id,
        "type": exercise.type,
        "solution_code": exercise.solution_code,
        "answer": answer if isinstance(answer, str) else None,
        "answers": [str(a) for a in answer] if isinstance(answer, list) else None,
        "starter_code": exercise.starter_code,
        "blanks": exercise.blanks,
        "question": exercise.question,
    }


async def submit_lesson(lesson_id: str, request: CodeSubmission) -> ProgressionResult:
    if not heart_store.can_attempt():
        raise HTTPException(
            status_code=403,
            detail={
                "error": "out_of_hearts",
                "hearts": heart_store.status().as_dict(),
                "message": "Out of hearts. Review your missed steps to earn one back.",
            },
        )
    try:
        result = await lesson_engine.run_lesson(lesson_id, request.code)
    except SandboxError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": "sandbox_unavailable", "message": str(exc)},
        ) from exc
    # The server owns the pool, so a failed assessment is charged here rather
    # than in the browser where it could be edited away.
    if not result.passed:
        result.hearts = heart_store.consume().as_dict()
    elif result.graduated:
        # Clearing the lesson's own task out of the review queue is rewarded
        # exactly like clearing a step is.
        result.hearts = heart_store.refund().as_dict()
    else:
        result.hearts = heart_store.status().as_dict()
    return result


@app.post("/api/lessons/{lesson_id}/run", response_model=ProgressionResult)
async def run_lesson(lesson_id: str, request: CodeSubmission):
    try:
        lesson_engine.get_lesson(lesson_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "lesson_not_found"}) from exc
    return await submit_lesson(lesson_id, request)


@app.post("/api/lessons/{lesson_id}/exercises/{exercise_id}/run", response_model=ProgressionResult)
async def run_exercise_code(lesson_id: str, exercise_id: str, request: CodeSubmission):
    try:
        return await lesson_engine.run_exercise_code(lesson_id, exercise_id, request.code)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "exercise_not_found", "message": str(exc)}) from exc
    except SandboxError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": "sandbox_unavailable", "message": str(exc)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "invalid_code", "message": str(exc)},
        ) from exc


@app.get("/api/hearts")
async def get_hearts():
    """Current heart pool, with time-based regen already applied."""
    return heart_store.status().as_dict()


class HeartSettingsRequest(BaseModel):
    unlimited: bool | None = None
    max_hearts: int | None = Field(default=None, ge=1, le=10)


@app.post("/api/hearts/settings")
async def set_hearts_settings(request: HeartSettingsRequest):
    if request.max_hearts is not None:
        heart_store.set_max(request.max_hearts)
    if request.unlimited is not None:
        heart_store.set_unlimited(request.unlimited)
    return heart_store.status().as_dict()


@app.post("/api/hearts/refill")
async def refill_hearts():
    return heart_store.refill().as_dict()


@app.post("/api/lessons/{lesson_id}/submit-exercise")
async def submit_exercise(lesson_id: str, request: ExerciseSubmissionRequest, user_id: str = "default_user"):
    try:
        lesson_engine.get_lesson(lesson_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "lesson_not_found"}) from exc

    # Replaying a missed step is always allowed: it is the way back into the
    # lesson path when the pool is empty, and graduating it refunds a heart.
    is_replay = lesson_engine.is_queued(request.exercise_id)
    if not is_replay and not heart_store.can_attempt():
        raise HTTPException(
            status_code=403,
            detail={
                "error": "out_of_hearts",
                "hearts": heart_store.status().as_dict(),
                "message": "Out of hearts. Review your missed steps to earn one back, "
                           "or wait for a refill.",
            },
        )
    try:
        res = await lesson_engine.submit_exercise(
            lesson_id=lesson_id,
            sublesson_id=request.sublesson_id,
            exercise_id=request.exercise_id,
            payload=request.payload,
        )
    except SandboxError as exc:
        # Backstop: grading itself falls back to static checks, but if the
        # sandbox ever still blows up, return a retryable grading response
        # instead of a 500 so the learner is never hard-blocked.
        progress = lesson_engine.lesson_progress(lesson_id)
        return {
            "exercise_id": request.exercise_id,
            "passed": False,
            "state": "incorrect",
            "attempt_count": 0,
            "feedback": f"Code runner unavailable ({exc}). Your answer was not graded — try again.",
            "xp_awarded": 0,
            "total_xp": 0,
            "level": 1,
            "explanation": None,
            "next_action": progress["next_action"],
            "lesson_completed": progress["lesson_completed"],
            "next_lesson_id": progress["next_lesson_id"],
            "progress": progress["progress"],
        }
    if res.get("xp_awarded", 0) > 0:
        user_store.update_user_xp(user_id, res["xp_awarded"])
    if not res.get("passed"):
        res["hearts"] = heart_store.consume().as_dict()
    elif res.get("graduated"):
        # Clearing a miss is rewarded, not just permitted.
        res["hearts"] = heart_store.refund().as_dict()
    else:
        res["hearts"] = heart_store.status().as_dict()
    return res


# ─── Learning sessions: the teaching ladder ──────────────────────────────────
# A lesson with an authored step pool serves a generated session; every other
# lesson keeps its existing exercise flow untouched. Failing a teaching rung never
# consumes a heart and never blocks an attempt -- that is the difference between a
# lesson that teaches and a lesson that bills you for reading it.

class StepAttemptRequest(BaseModel):
    payload: dict = Field(default_factory=dict)
    hints_used: int = Field(default=0, ge=0, le=8)


def _session_language(lesson_id: str, language: str | None) -> str:
    try:
        lesson_engine.get_lesson(lesson_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "lesson_not_found"}) from exc
    return (language or lesson_engine.get_lesson_language(lesson_id)).lower().strip()


@app.get("/api/lessons/{lesson_id}/session")
async def get_learning_session(lesson_id: str, language: str | None = None):
    lang = _session_language(lesson_id, language)
    session = learning_service.session_for(lesson_engine, lesson_id, lang)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "no_step_pool", "lesson_id": lesson_id,
                    "message": "This lesson has no authored teaching steps yet."},
        )
    return session


@app.post("/api/lessons/{lesson_id}/steps/{step_id}/seen")
async def mark_step_seen(lesson_id: str, step_id: str, language: str | None = None):
    """Acknowledge a presentation rung so the session resumes past it.

    Awards nothing on purpose: reading a worked example is not evidence, and paying
    for it turns the reward channel into an attendance counter.
    """
    lang = _session_language(lesson_id, language)
    pool = learning_service.pool_for(lang, lesson_id)
    if pool is None:
        raise HTTPException(status_code=404, detail={"error": "no_step_pool", "lesson_id": lesson_id})
    step = pool.by_id(step_id)
    if step is None:
        raise HTTPException(status_code=404, detail={"error": "step_not_found", "step_id": step_id})
    if learning_service.presentation_step(lang, lesson_id, step_id) is None:
        raise HTTPException(
            status_code=400,
            detail={"error": "not_a_presentation_step", "step_id": step_id,
                    "message": "Graded steps must be attempted, not acknowledged."},
        )
    store = lesson_engine.stores.get(lang, lesson_engine.store)
    return learning_service.mark_step_seen(store, pool, step)


@app.post("/api/lessons/{lesson_id}/steps/{step_id}/attempt")
async def attempt_learning_step(lesson_id: str, step_id: str, request: StepAttemptRequest,
                                user_id: str = "default_user"):
    lang = _session_language(lesson_id, None)
    if learning_service.pool_for(lang, lesson_id) is None:
        raise HTTPException(status_code=404, detail={"error": "no_step_pool", "lesson_id": lesson_id})

    charging = learning_service.charge_for(lang, lesson_id, step_id)
    replay = lesson_engine.is_queued(step_id)
    # Free-to-fail rungs stay available with an empty pool: a learner who has run
    # out of hearts must still be able to read and practise, which is the way back.
    if charging and not replay and not heart_store.can_attempt():
        raise HTTPException(
            status_code=403,
            detail={
                "error": "out_of_hearts",
                "hearts": heart_store.status().as_dict(),
                "message": "Out of hearts. Review a missed step or read ahead for free "
                           "to earn one back.",
            },
        )

    try:
        res = await learning_service.attempt_step(
            lesson_engine, lesson_id, lang, step_id, request.payload,
            hints_used=request.hints_used,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "step_not_gradable",
                                                     "message": str(exc)}) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": "step_not_found",
                                                     "message": str(exc)}) from exc

    if res.get("xp_awarded", 0) > 0:
        user_store.update_user_xp(user_id, res["xp_awarded"])
    if not res["passed"] and charging:
        res["hearts"] = heart_store.consume().as_dict()
    elif res.get("graduated"):
        res["hearts"] = heart_store.refund().as_dict()
    else:
        res["hearts"] = heart_store.status().as_dict()
    return res


@app.get("/api/concepts")
async def get_concepts(language: str | None = None):
    """The headline learning number: concepts demonstrated, not minutes spent."""
    lang = (language or lesson_engine.active_language).lower().strip()
    return learning_service.concepts_summary(lesson_engine, lang)


@app.post("/api/feedback")
async def submit_exercise_feedback(request: ExerciseFeedbackRequest, user_id: str = "default_user"):
    """Record a too_easy / too_difficult / report rating for an exercise.

    The aggregated signal immediately steers subsequent AI tutor responses
    for this learner (see adaptation_hint in the tutor prompt).
    """
    try:
        record = feedback_store.record(
            user_id=user_id,
            exercise_id=request.exercise_id,
            rating=request.rating,
            lesson_id=request.lesson_id,
            comment=request.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": "invalid_rating", "message": str(exc)}) from exc
    return {
        "status": "ok",
        "rating": record["rating"],
        "exercise_id": record["exercise_id"],
        "adaptation": feedback_store.adaptation_ack(user_id, record["rating"]),
        "summary": feedback_store.summary(user_id),
    }


@app.get("/api/feedback/summary")
async def get_feedback_summary(user_id: str = "default_user"):
    """Aggregated feedback counts + difficulty bias for a learner."""
    return feedback_store.summary(user_id)


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



# ─── Create Course: Guided Project Workspace ─────────────────────────────────
# These endpoints power the Create Course project experience ONLY. They are
# isolated from lessons/curriculum/progression and do not affect any other
# section of Patchwork.


class ProjectCreateRequest(BaseModel):
    material_type: str = Field(default="transcript", max_length=40)
    content: str = Field(default="", max_length=200_000)
    title: str = Field(default="", max_length=200)
    filename: str | None = Field(default=None, max_length=200)


class WorkspaceFilePayload(BaseModel):
    path: str = Field(min_length=1, max_length=200)
    content: str = Field(default="", max_length=200_000)


class WorkspaceUpdateRequest(BaseModel):
    files: list[WorkspaceFilePayload] = Field(default_factory=list, max_length=100)


class ProjectRunRequest(BaseModel):
    files: list[WorkspaceFilePayload] | None = None
    stdin: str = Field(default="", max_length=64 * 1024)


class ProjectTerminalRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=4000)
    files: list[WorkspaceFilePayload] | None = None
    stdin: str = Field(default="", max_length=64 * 1024)


class ProjectNextRequest(BaseModel):
    files: list[WorkspaceFilePayload] | None = None


class ProjectGuidanceRequest(BaseModel):
    question: str = Field(default="", max_length=1000)
    files: list[WorkspaceFilePayload] | None = None


def _to_workspace_files(payload: list[WorkspaceFilePayload] | None) -> list[WorkspaceFile] | None:
    if payload is None:
        return None
    return [WorkspaceFile(path=f.path, content=f.content) for f in payload]


@app.post("/api/create-course/projects")
async def create_project(req: ProjectCreateRequest):
    course_id = f"project-{uuid.uuid4().hex[:8]}"
    try:
        project = await project_service.build_project(
            ingestion_service,
            project_store,
            material_type=req.material_type,
            content=req.content,
            title=req.title,
            filename=req.filename,
            course_id=course_id,
            provider=get_current_provider(),
        )
    except IngestionError as exc:
        raise HTTPException(status_code=400, detail={"error": "ingestion_failed", "message": str(exc)})
    except SourceQualityError as exc:
        error_code = "source_rejected" if exc.decision == "reject" else "source_insufficient"
        payload = {
            "error": error_code,
            "decision": exc.decision,
            "message": str(exc),
            **exc.quality.to_public_dict(),
        }
        raise HTTPException(status_code=422, detail=payload)
    except ProjectGroundingError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "ungroundable_source",
                "decision": "insufficient",
                "message": str(exc),
            },
        )
    return project_service.to_learner_view(project)


@app.get("/api/create-course/projects")
async def list_projects():
    return project_store.list_summaries()


@app.get("/api/create-course/projects/{course_id}")
async def get_project(course_id: str):
    project = project_store.get(course_id)
    if not project:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})
    try:
        project_service.require_usable_project(project)
    except ProjectGroundingError as exc:
        raise HTTPException(status_code=422, detail={"error": "ungroundable_source", "message": str(exc)})
    return project_service.to_learner_view(project)


@app.delete("/api/create-course/projects/{course_id}")
async def delete_project(course_id: str):
    await project_service.destroy_terminal(course_id)
    if not project_store.delete(course_id):
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})
    return {"status": "deleted", "course_id": course_id}


@app.put("/api/create-course/projects/{course_id}/workspace")
async def save_project_workspace(course_id: str, req: WorkspaceUpdateRequest):
    files = _to_workspace_files(req.files) or []
    project = project_store.save_workspace(course_id, files)
    if not project:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})
    return project_service.to_learner_view(project)


@app.post("/api/create-course/projects/{course_id}/run")
async def run_project_workspace(course_id: str, req: ProjectRunRequest):
    project = project_store.get(course_id)
    if not project:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})
    files = _to_workspace_files(req.files)
    if files is not None:
        project = project_store.save_workspace(course_id, files) or project
    try:
        return await project_service.run_project(project_store, sandbox, project, stdin=req.stdin)
    except SandboxError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"error": "sandbox_error", "message": str(exc)})


@app.post("/api/create-course/projects/{course_id}/terminal")
async def project_terminal(course_id: str, req: ProjectTerminalRequest):
    project = project_store.get(course_id)
    if not project:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})
    files = _to_workspace_files(req.files)
    if files is not None:
        project = project_store.save_workspace(course_id, files) or project
    try:
        return await project_service.exec_terminal(project, command=req.command, stdin=req.stdin)
    except SandboxError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"error": "sandbox_error", "message": str(exc)})


@app.post("/api/create-course/projects/{course_id}/next")
async def project_next(course_id: str, req: ProjectNextRequest):
    project = project_store.get(course_id)
    if not project:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})
    files = _to_workspace_files(req.files)
    if files is not None:
        project = project_store.save_workspace(course_id, files) or project
    try:
        result = await project_service.evaluate_next(project_store, sandbox, project)
    except SandboxError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"error": "sandbox_error", "message": str(exc)})
    result["project"] = project_service.to_learner_view(project).model_dump()
    return result


@app.post("/api/create-course/projects/{course_id}/guidance")
async def project_guidance(course_id: str, req: ProjectGuidanceRequest):
    project = project_store.get(course_id)
    if not project:
        raise HTTPException(status_code=404, detail={"error": "project_not_found"})
    files = _to_workspace_files(req.files)
    if files is not None:
        project = project_store.save_workspace(course_id, files) or project
    return await project_service.guidance(sandbox, get_current_provider(), project, question=req.question)


@app.post("/api/tutor", response_model=TutorResponse)
async def tutor(request: TutorRequest):
    # Inject live learner-feedback adaptation so the AI adjusts on the go.
    hint = feedback_store.adaptation_hint(request.user_id or "default_user")
    if hint:
        request = request.model_copy(update={"adaptation_hint": hint})
    return await tutor_service.tutor(request, active_provider=get_current_provider())


# ─── API Settings Endpoints ─────────────────────────────────────────────────

class SettingsSaveRequest(BaseModel):
    api_key: str = Field(..., min_length=1, max_length=500)
    model: str | None = None


class SettingsResponse(BaseModel):
    providers: list[ProviderInfo]
    current_provider: str


@app.get("/api/settings", response_model=SettingsResponse)
async def get_settings():
    """Get all provider settings and current configuration."""
    try:
        async with asyncio.timeout(15):
            providers = await get_all_providers_info()
            async with provider_lock:
                curr_id = current_provider_id
            return SettingsResponse(
                providers=providers,
                current_provider=curr_id,
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
        async with provider_lock:
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
            async with provider_lock:
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
    generic_file = state_root / "progression_state.json"
    if generic_file.exists():
        try:
            generic_file.write_text("[]", encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Failed to reset generic progression file: {exc}")

    return {
        "success": True,
        "reset_languages": reset_langs,
        "message": "Progression reset successfully.",
    }
