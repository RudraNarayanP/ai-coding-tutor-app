import asyncio
import logging
import os
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
from .lesson_engine import LessonEngine, ProgressionStore
from .lesson_models import LessonSummary, ProgressionResult, ProgressionState, PublicLessonView
from .lessons import CURRICULUM
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


from pathlib import Path
progression_path = Path(__file__).resolve().parent / "progression_state.json"
lesson_engine = LessonEngine(sandbox, ProgressionStore(CURRICULUM, storage_path=progression_path), CURRICULUM)

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
