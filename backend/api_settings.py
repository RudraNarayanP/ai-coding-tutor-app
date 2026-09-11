"""
API Settings Manager - Handles API configuration, key validation, and provider management.
This module provides the service functions for the frontend settings UI.
"""
import asyncio
import logging
import os
from typing import Any

import httpx
from pydantic import BaseModel, Field

from .ai_models import ProviderStatus
from .ai_provider import (
    ALL_PROVIDERS,
    get_ai_provider,
)
from .api_key_manager import (
    delete_api_key,
    get_api_key,
    has_api_key,
    mask_api_key,
    store_api_key,
    validate_api_key_format,
)
from .provider_cache import ProviderCache

logger = logging.getLogger("patchwork-tutor")

# Module-level TTL cache so repeated settings lookups / health checks do not
# hammer the provider APIs on every UI poll.
_provider_cache = ProviderCache(default_ttl=30.0)

# Provider-friendly names for UI
PROVIDER_DISPLAY_NAMES: dict[str, str] = {
    "ollama": "Ollama (Local)",
    "openai": "OpenAI",
    "anthropic": "Anthropic Claude",
    "openrouter": "OpenRouter",
    "gemini": "Google Gemini",
}

# Provider setup instructions for UI
PROVIDER_SETUP_INSTRUCTIONS: dict[str, str] = {
    "ollama": "Install Ollama from ollama.com, then run: ollama pull llama3.1:8b",
    "openai": "Get your API key from platform.openai.com/api-keys",
    "anthropic": "Get your API key from console.anthropic.com/settings/keys",
    "openrouter": "Get your API key from openrouter.ai/keys",
    "gemini": "Get your API key from aistudio.google.com/app/apikey",
}


class ProviderInfo(BaseModel):
    """Full provider information for the frontend."""
    id: str
    name: str
    has_key: bool
    key_masked: str | None
    model: str
    configured: bool
    available: bool
    health_status: ProviderStatus | None = None
    setup_instructions: str | None = None
    error: str | None = None


class ApiKeyValidationResult(BaseModel):
    """Result of API key validation."""
    valid: bool
    error: str | None = None
    provider: str
    key_masked: str | None = None


class ProviderKeyUpdate(BaseModel):
    """Request to update provider API key."""
    provider: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)
    model: str | None = None


class ProviderKeyDelete(BaseModel):
    """Request to delete provider API key."""
    provider: str = Field(..., min_length=1)


async def validate_provider_key(provider: str, api_key: str) -> ApiKeyValidationResult:
    """
    Validate an API key by testing it against the provider's API.
    Returns validation result with masked key on success.
    """
    is_valid, format_error = validate_api_key_format(provider, api_key)
    if not is_valid:
        return ApiKeyValidationResult(
            valid=False,
            error=format_error,
            provider=provider,
        )

    try:
        if provider == "openai":
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"}
                )
                if response.status_code == 401:
                    return ApiKeyValidationResult(
                        valid=False,
                        error="Invalid API key - please check and try again",
                        provider=provider,
                    )
                elif response.status_code != 200:
                    return ApiKeyValidationResult(
                        valid=False,
                        error=f"API returned error {response.status_code}",
                        provider=provider,
                    )

        elif provider == "anthropic":
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-3-5-sonnet-20241022",
                        "max_tokens": 10,
                        "messages": [{"role": "user", "content": "test"}]
                    }
                )
                if response.status_code == 401:
                    return ApiKeyValidationResult(
                        valid=False,
                        error="Invalid API key - please check and try again",
                        provider=provider,
                    )
                elif response.status_code not in (200, 201):
                    return ApiKeyValidationResult(
                        valid=False,
                        error=f"API returned error {response.status_code}",
                        provider=provider,
                    )

        elif provider == "openrouter":
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"}
                )
                if response.status_code == 401:
                    return ApiKeyValidationResult(
                        valid=False,
                        error="Invalid API key - please check and try again",
                        provider=provider,
                    )
                elif response.status_code != 200:
                    return ApiKeyValidationResult(
                        valid=False,
                        error=f"API returned error {response.status_code}",
                        provider=provider,
                    )

        elif provider == "gemini":
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                )
                if response.status_code in (400, 401, 403):
                    return ApiKeyValidationResult(
                        valid=False,
                        error="Invalid API key - please check and try again",
                        provider=provider,
                    )
                elif response.status_code != 200:
                    return ApiKeyValidationResult(
                        valid=False,
                        error=f"API returned error {response.status_code}",
                        provider=provider,
                    )

        elif provider == "ollama":
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get("http://localhost:11434/api/tags")
                if response.status_code != 200:
                    return ApiKeyValidationResult(
                        valid=False,
                        error="Ollama is not running. Please start Ollama first.",
                        provider=provider,
                    )

        return ApiKeyValidationResult(
            valid=True,
            provider=provider,
            key_masked=mask_api_key(api_key),
        )

    except httpx.TimeoutException:
        return ApiKeyValidationResult(
            valid=False,
            error=f"Connection timeout - check your internet or {provider} service status",
            provider=provider,
        )
    except httpx.ConnectError:
        return ApiKeyValidationResult(
            valid=False,
            error=f"Cannot connect to {provider} - check your internet connection",
            provider=provider,
        )
    except Exception as exc:
        logger.exception(f"Key validation error for {provider}")
        return ApiKeyValidationResult(
            valid=False,
            error=f"Validation failed: {type(exc).__name__}",
            provider=provider,
        )


async def get_provider_info(provider_id: str) -> ProviderInfo:
    """Get comprehensive provider information for the frontend."""
    cached = _provider_cache.get_provider_info(provider_id)
    if cached is not None:
        return cached

    display_name = PROVIDER_DISPLAY_NAMES.get(provider_id, provider_id.title())
    setup_instructions = PROVIDER_SETUP_INSTRUCTIONS.get(provider_id)

    # Check if we have a stored or env key
    stored_key = get_api_key(provider_id)
    env_key = os.getenv(f"{provider_id.upper()}_API_KEY")
    active_key = stored_key or env_key
    has_stored_key = bool(active_key)
    key_masked = mask_api_key(active_key) if active_key else None

    # Get the provider instance
    prov = get_ai_provider(provider_id)
    model = getattr(prov, "model", "")

    # Check configuration status
    if provider_id == "ollama":
        configured = True
    else:
        configured = has_stored_key

    # Health status
    available = False
    error: str | None = None
    health: ProviderStatus | None = None

    try:
        health = await prov.health()
        available = health.available
        error = health.error or health.reason
    except Exception as exc:
        logger.exception(f"Health check failed for {provider_id}")
        error = str(exc)

    info = ProviderInfo(
        id=provider_id,
        name=display_name,
        has_key=has_stored_key,
        key_masked=key_masked,
        model=model,
        configured=configured,
        available=available,
        health_status=health,
        setup_instructions=setup_instructions,
        error=error,
    )
    _provider_cache.set_provider_info(provider_id, info)
    return info


async def get_all_providers_info() -> list[ProviderInfo]:
    """Get information for all providers."""
    cached_overview = _provider_cache.get_providers_overview()
    if cached_overview is not None:
        return cached_overview

    results = [await get_provider_info(p) for p in ALL_PROVIDERS]
    _provider_cache.set_providers_overview(results)
    return results


def update_provider_key(provider: str, api_key: str, model: str | None = None) -> None:
    """Update API key for a provider (stores encrypted, updates env)."""
    store_api_key(provider, api_key)
    key_env = f"{provider.upper()}_API_KEY"
    os.environ[key_env] = api_key

    if model:
        model_env = f"{provider.upper()}_MODEL"
        os.environ[model_env] = model

    # Cached provider info (has_key, key_masked) and the overview list are
    # now stale.
    _provider_cache.delete(provider, "info")
    _provider_cache.delete("providers_overview")


def remove_provider_key(provider: str) -> bool:
    """Remove API key for a provider."""
    key_env = f"{provider.upper()}_API_KEY"
    os.environ.pop(key_env, None)
    deleted = delete_api_key(provider)
    _provider_cache.delete(provider, "info")
    _provider_cache.delete("providers_overview")
    return deleted
