import os
import json
from dataclasses import dataclass, field
from typing import Protocol, Any
from urllib.parse import urlparse

import httpx

from .ai_models import OllamaHealth, ProviderStatus, TutorRequest


class AIProviderError(Exception):
    def __init__(self, message: str, provider: str = "unknown", code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.code = code


class AIProvider(Protocol):
    name: str
    provider_id: str

    async def tutor(self, request: TutorRequest) -> str: ...
    async def health(self) -> ProviderStatus: ...


SYSTEM_PROMPT = (
    "You are a patient coding teacher. Deterministic test results are authoritative and cannot be changed. "
    "Return tutoring prose only. Follow the requested hint level exactly. "
    "Do not provide complete working code unless solution_requested is true.\n"
    "Level 1: explain the concept without naming the exact mistake.\n"
    "Level 2: point toward the relevant part of the approach.\n"
    "Level 3: identify the student's mistake.\n"
    "Level 4: explain the correct approach in detail."
)


def build_user_prompt(request: TutorRequest) -> str:
    return (
        f"Lesson: {request.lesson_title} ({request.lesson_id})\n"
        f"Instructions: {request.instructions}\n"
        f"Student code:\n{request.code}\n"
        f"Deterministic test results (authoritative): {request.test_results}\n"
        f"Previous hints in this session: {request.previous_hints}\n"
        f"Requested hint level: {request.hint_level}\n"
        f"solution_requested: {request.solution_requested}"
    )


# ─── 1. OLLAMA PROVIDER ────────────────────────────────────────────────────────

@dataclass
class OllamaProvider:
    provider_id: str = "ollama"
    name: str = "Ollama (Local)"
    base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"))
    model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3.1:8b"))
    timeout_seconds: float = field(default_factory=lambda: float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "45")))

    async def tutor(self, request: TutorRequest) -> str:
        prompt = build_user_prompt(request)
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "stream": False,
                        "options": {"num_predict": 300},
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                    },
                )
                if response.status_code == 404:
                    raise AIProviderError("Configured Ollama model is unavailable.", provider="ollama", code="model_missing")
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AIProviderError("Ollama returned an invalid or unreachable response.", provider="ollama", code="network_error") from exc

        message = payload.get("message", {}).get("content") if isinstance(payload, dict) else None
        if not isinstance(message, str) or not message.strip():
            raise AIProviderError("Ollama returned an invalid response.", provider="ollama", code="invalid_response")
        return message.strip()

    async def health(self) -> ProviderStatus:
        try:
            async with httpx.AsyncClient(timeout=min(self.timeout_seconds, 5)) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                payload = response.json()
            models = payload.get("models", []) if isinstance(payload, dict) else []
            names = {m.get("name") for m in models if isinstance(m, dict)}
            if self.model not in names:
                return ProviderStatus(
                    provider=self.provider_id,
                    name=self.name,
                    available=False,
                    model=self.model,
                    reason="Model missing in local Ollama instance",
                    error="configured_model_missing",
                )
            return ProviderStatus(
                provider=self.provider_id,
                name=self.name,
                available=True,
                model=self.model,
            )
        except Exception:
            return ProviderStatus(
                provider=self.provider_id,
                name=self.name,
                available=False,
                model=self.model,
                reason="Ollama service unreachable on localhost",
                error="ollama_unavailable",
            )


# ─── 2. OPENAI & OPENROUTER PROVIDER (OPENAI COMPATIBLE) ──────────────────────

@dataclass
class OpenAICompatibleProvider:
    provider_id: str
    name: str
    api_key_env: str
    model_env: str
    default_model: str
    base_url_env: str | None = None
    default_base_url: str = "https://api.openai.com/v1"
    headers_extra: dict[str, str] = field(default_factory=dict)

    @property
    def api_key(self) -> str:
        key = os.getenv(self.api_key_env, "").strip()
        if key:
            return key
        try:
            from .api_key_manager import get_api_key
            return (get_api_key(self.provider_id) or "").strip()
        except Exception:
            return ""

    @property
    def model(self) -> str:
        return os.getenv(self.model_env, "").strip() or self.default_model

    @property
    def base_url(self) -> str:
        if self.base_url_env and os.getenv(self.base_url_env):
            return os.getenv(self.base_url_env, "").rstrip("/")
        return self.default_base_url.rstrip("/")

    async def tutor(self, request: TutorRequest) -> str:
        if not self.api_key:
            raise AIProviderError(f"{self.name} API key is not configured.", provider=self.provider_id, code="missing_api_key")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.headers_extra,
        }

        payload = {
            "model": self.model,
            "max_tokens": 300,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(request)},
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                res = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                if res.status_code == 401:
                    raise AIProviderError(f"{self.name} API key is invalid or unauthorized.", provider=self.provider_id, code="invalid_api_key")
                elif res.status_code == 429:
                    raise AIProviderError(f"{self.name} rate limit or quota exceeded.", provider=self.provider_id, code="rate_limit")
                res.raise_for_status()
                data = res.json()
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError(f"{self.name} request failed or timed out.", provider=self.provider_id, code="network_error") from exc

        try:
            message = data["choices"][0]["message"]["content"]
            if isinstance(message, str) and message.strip():
                return message.strip()
        except (KeyError, IndexError, TypeError):
            pass
        raise AIProviderError(f"{self.name} returned an unexpected response format.", provider=self.provider_id, code="malformed_response")

    async def health(self) -> ProviderStatus:
        if not self.api_key:
            return ProviderStatus(
                provider=self.provider_id,
                name=self.name,
                available=False,
                model=self.model,
                configured=False,
                reason=f"{self.api_key_env} environment variable not set",
                error="missing_api_key",
            )
        return ProviderStatus(
            provider=self.provider_id,
            name=self.name,
            available=True,
            model=self.model,
            configured=True,
        )


# ─── 3. ANTHROPIC PROVIDER ───────────────────────────────────────────────────

@dataclass
class AnthropicProvider:
    provider_id: str = "anthropic"
    name: str = "Anthropic Claude"

    @property
    def api_key(self) -> str:
        key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if key:
            return key
        try:
            from .api_key_manager import get_api_key
            return (get_api_key("anthropic") or "").strip()
        except Exception:
            return ""

    @property
    def model(self) -> str:
        return os.getenv("ANTHROPIC_MODEL", "").strip() or "claude-3-5-sonnet-20241022"

    async def tutor(self, request: TutorRequest) -> str:
        if not self.api_key:
            raise AIProviderError("Anthropic API key is not configured.", provider=self.provider_id, code="missing_api_key")

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "max_tokens": 300,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": build_user_prompt(request)},
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                res = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
                if res.status_code == 401:
                    raise AIProviderError("Anthropic API key is invalid.", provider=self.provider_id, code="invalid_api_key")
                elif res.status_code == 429:
                    raise AIProviderError("Anthropic rate limit reached.", provider=self.provider_id, code="rate_limit")
                res.raise_for_status()
                data = res.json()
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError("Anthropic API request failed.", provider=self.provider_id, code="network_error") from exc

        try:
            content = data["content"][0]["text"]
            if isinstance(content, str) and content.strip():
                return content.strip()
        except (KeyError, IndexError, TypeError):
            pass
        raise AIProviderError("Anthropic returned an invalid response format.", provider=self.provider_id, code="malformed_response")

    async def health(self) -> ProviderStatus:
        if not self.api_key:
            return ProviderStatus(
                provider=self.provider_id,
                name=self.name,
                available=False,
                model=self.model,
                configured=False,
                reason="ANTHROPIC_API_KEY environment variable not set",
                error="missing_api_key",
            )
        return ProviderStatus(
            provider=self.provider_id,
            name=self.name,
            available=True,
            model=self.model,
            configured=True,
        )


# ─── 4. GEMINI PROVIDER ───────────────────────────────────────────────────────

@dataclass
class GeminiProvider:
    provider_id: str = "gemini"
    name: str = "Google Gemini"

    @property
    def api_key(self) -> str:
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if key:
            return key
        try:
            from .api_key_manager import get_api_key
            return (get_api_key("gemini") or "").strip()
        except Exception:
            return ""

    @property
    def model(self) -> str:
        return os.getenv("GEMINI_MODEL", "").strip() or "gemini-1.5-flash"

    async def tutor(self, request: TutorRequest) -> str:
        if not self.api_key:
            raise AIProviderError("Gemini API key is not configured.", provider=self.provider_id, code="missing_api_key")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "system_instruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": [{
                "parts": [{"text": build_user_prompt(request)}]
            }],
            "generationConfig": {
                "maxOutputTokens": 300,
            }
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                res = await client.post(url, json=payload)
                if res.status_code in (400, 401, 403):
                    raise AIProviderError("Gemini API key is invalid or request denied.", provider=self.provider_id, code="invalid_api_key")
                elif res.status_code == 429:
                    raise AIProviderError("Gemini rate limit exceeded.", provider=self.provider_id, code="rate_limit")
                res.raise_for_status()
                data = res.json()
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError("Gemini API request failed.", provider=self.provider_id, code="network_error") from exc

        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            if isinstance(text, str) and text.strip():
                return text.strip()
        except (KeyError, IndexError, TypeError):
            pass
        raise AIProviderError("Gemini returned an invalid response format.", provider=self.provider_id, code="malformed_response")

    async def health(self) -> ProviderStatus:
        if not self.api_key:
            return ProviderStatus(
                provider=self.provider_id,
                name=self.name,
                available=False,
                model=self.model,
                configured=False,
                reason="GEMINI_API_KEY environment variable not set",
                error="missing_api_key",
            )
        return ProviderStatus(
            provider=self.provider_id,
            name=self.name,
            available=True,
            model=self.model,
            configured=True,
        )


# ─── 5. PROVIDER FACTORY & REGISTRY ─────────────────────────────────────────

def create_openai_provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        provider_id="openai",
        name="OpenAI",
        api_key_env="OPENAI_API_KEY",
        model_env="OPENAI_MODEL",
        default_model="gpt-4o-mini",
        base_url_env="OPENAI_BASE_URL",
        default_base_url="https://api.openai.com/v1",
    )


def create_openrouter_provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        provider_id="openrouter",
        name="OpenRouter",
        api_key_env="OPENROUTER_API_KEY",
        model_env="OPENROUTER_MODEL",
        default_model="meta-llama/llama-3.1-8b-instruct:free",
        base_url_env="OPENROUTER_BASE_URL",
        default_base_url="https://openrouter.ai/api/v1",
        headers_extra={"HTTP-Referer": "https://github.com/patchwork", "X-Title": "Patchwork AI Tutor"},
    )


ALL_PROVIDERS: dict[str, Any] = {
    "ollama": OllamaProvider,
    "openai": create_openai_provider,
    "anthropic": AnthropicProvider,
    "openrouter": create_openrouter_provider,
    "gemini": GeminiProvider,
}


def get_ai_provider(provider_id: str | None = None) -> AIProvider:
    pid = (provider_id or os.getenv("AI_PROVIDER", "ollama")).lower().strip()
    factory = ALL_PROVIDERS.get(pid)
    if not factory:
        pid = "ollama"
        factory = ALL_PROVIDERS["ollama"]

    if isinstance(factory, type):
        return factory()
    elif callable(factory):
        return factory()
    return factory
