import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Protocol, Any, AsyncGenerator
from urllib.parse import urlparse

import httpx

from .ai_models import OllamaHealth, ProviderStatus, TutorRequest

logger = logging.getLogger("patchwork-tutor")


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
    async def tutor_stream(self, request: TutorRequest) -> AsyncGenerator[str, None]: ...


SYSTEM_PROMPT = (
    "You are a patient coding teacher. Deterministic test results are authoritative and cannot be changed. "
    "Return tutoring prose only. Do not provide complete working code unless solution_requested is true.\n"
    "Follow the requested hint level exactly.\n"
    "Level 1: explain the concept without naming the exact mistake.\n"
    "Level 2: point toward the relevant part of the approach.\n"
    "Level 3: identify the student's mistake.\n"
    "Level 4: explain the correct approach in detail.\n"
)


def build_user_prompt(request: TutorRequest) -> str:
    unit_title = getattr(request, 'unit_title', '')
    concept_title = getattr(request, 'concept_title', '')
    prerequisites = getattr(request, 'prerequisites', [])
    unit_part = f"Unit: {unit_title}\n" if unit_title else ""
    concept_part = f"Concept: {concept_title}\n" if concept_title else ""
    prereq_part = f"Prerequisite concepts: {', '.join(prerequisites)}\n" if prerequisites else ""
    return (
        f"{unit_part}{concept_part}{prereq_part}"
        f"Lesson: {request.lesson_title} ({request.lesson_id})\n"
        f"Instructions: {request.instructions}\n"
        f"Student code:\n{request.code}\n"
        f"Deterministic test results (authoritative): {request.test_results}\n"
        f"Previous hints in this session: {request.previous_hints}\n"
        f"Requested hint level: {request.hint_level}\n"
        f"solution_requested: {request.solution_requested}"
    )


# ─── SHARED HTTP CLIENT FOR LATENCY OPTIMIZATION ──────────────────────────────
_shared_client: httpx.AsyncClient | None = None

def get_shared_client(timeout: float = 30.0) -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(timeout=timeout, limits=httpx.Limits(max_keepalive_connections=20, max_connections=100))
    return _shared_client


# ─── 1. OLLAMA PROVIDER ────────────────────────────────────────────────────────
@dataclass
class OllamaProvider:
    provider_id: str = "ollama"
    name: str = "Ollama (Local)"
    base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"))
    model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3.1:8b"))
    timeout_seconds: float = field(default_factory=lambda: float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "30")))

    async def tutor(self, request: TutorRequest) -> str:
        prompt = build_user_prompt(request)
        try:
            client = get_shared_client(self.timeout_seconds)
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "options": {"num_predict": 180},
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

    async def tutor_stream(self, request: TutorRequest) -> AsyncGenerator[str, None]:
        """Stream tutor response from Ollama."""
        prompt = build_user_prompt(request)
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "stream": True,
                        "options": {"num_predict": 300},
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                    },
                ) as response:
                    if response.status_code == 404:
                        raise AIProviderError("Configured Ollama model is unavailable.", provider="ollama", code="model_missing")
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line.strip():
                            try:
                                data = json.loads(line)
                                if "message" in data and "content" in data["message"]:
                                    content = data["message"]["content"]
                                    if content:
                                        yield content
                            except json.JSONDecodeError:
                                # Skip invalid JSON lines
                                continue
        except (httpx.HTTPError, ValueError) as exc:
            raise AIProviderError("Ollama returned an invalid or unreachable response.", provider="ollama", code="network_error") from exc

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


# ─── 2. OPENAI & OPENROUTER PROVIDER (OPENAI COMPATIBLE) ───────────────────────
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
            "max_tokens": 180,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(request)},
            ],
        }

        try:
            client = get_shared_client(30.0)
            res = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            if res.status_code == 401:
                raise AIProviderError(f"{self.name} API key is invalid or unauthorized.", provider=self.provider_id, code="invalid_api_key")
            elif res.status_code == 429:
                raise AIProviderError(f"{self.name} rate limit or quota exceeded.", provider=self.provider_id, code="rate_limit")
            elif res.status_code == 404:
                try:
                    body = res.json()
                    msg = None
                    if isinstance(body, dict):
                        # common OpenRouter error shape
                        msg = body.get('error', {}).get('message') or body.get('message') or str(body)
                    else:
                        msg = str(body)
                except Exception:
                    msg = 'Model unavailable or not accessible with this account'
                raise AIProviderError(f"{self.name} model unavailable: {msg}", provider=self.provider_id, code="model_unavailable")
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

    async def tutor_stream(self, request: TutorRequest) -> AsyncGenerator[str, None]:
        """Stream tutor response from OpenAI/OpenRouter compatible APIs."""
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
            "stream": True,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(request)},
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code == 401:
                        raise AIProviderError(f"{self.name} API key is invalid or unauthorized.", provider=self.provider_id, code="invalid_api_key")
                    elif response.status_code == 429:
                        raise AIProviderError(f"{self.name} rate limit or quota exceeded.", provider=self.provider_id, code="rate_limit")
                    elif response.status_code == 404:
                        try:
                            body = response.json()
                            msg = None
                            if isinstance(body, dict):
                                # common OpenRouter error shape
                                msg = body.get('error', {}).get('message') or body.get('message') or str(body)
                            else:
                                msg = str(body)
                        except Exception:
                            msg = 'Model unavailable or not accessible with this account'
                        raise AIProviderError(f"{self.name} model unavailable: {msg}", provider=self.provider_id, code="model_unavailable")
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            line = line[6:]  # Remove "data: " prefix
                        if line.strip() == "[DONE]":
                            break
                        if line.strip():
                            try:
                                data = json.loads(line)
                                if "choices" in data and len(data["choices"]) > 0:
                                    delta = data["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        content = delta["content"]
                                        if content:
                                            yield content
                            except json.JSONDecodeError:
                                # Skip invalid JSON lines
                                continue
        except (httpx.HTTPError, ValueError) as exc:
            raise AIProviderError(f"{self.name} request failed or timed out.", provider=self.provider_id, code="network_error") from exc

    async def health(self) -> ProviderStatus:
        # Check for a present API key (env or stored)
        key = self.api_key
        if not key:
            return ProviderStatus(
                provider=self.provider_id,
                name=self.name,
                available=False,
                model=self.model,
                configured=False,
                reason=f"{self.api_key_env} environment variable not set or key not stored",
                error="missing_api_key",
            )

        # Validate key format locally first
        try:
            from .api_key_manager import validate_api_key_format
            valid, vmsg = validate_api_key_format(self.provider_id, key)
            if not valid:
                return ProviderStatus(
                    provider=self.provider_id,
                    name=self.name,
                    available=False,
                    model=self.model,
                    configured=True,
                    reason=f"Invalid API key format: {vmsg}",
                    error="invalid_key_format",
                )
        except Exception:
            # If validation helper is missing or fails, fall back to conservative false
            return ProviderStatus(
                provider=self.provider_id,
                name=self.name,
                available=False,
                model=self.model,
                configured=True,
                reason="Key validation failed",
                error="validation_error",
            )

        # Perform a lightweight network check to ensure the key actually works.
        try:
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                **self.headers_extra,
            }
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json={
                        "model": self.model,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
                if resp.status_code == 401:
                    return ProviderStatus(
                        provider=self.provider_id,
                        name=self.name,
                        available=False,
                        model=self.model,
                        configured=True,
                        reason="API key unauthorized",
                        error="invalid_api_key",
                    )
                if resp.status_code not in (200, 201):
                    return ProviderStatus(
                        provider=self.provider_id,
                        name=self.name,
                        available=False,
                        model=self.model,
                        configured=True,
                        reason=f"API returned status {resp.status_code}",
                        error="api_error",
                    )
        except Exception:
            return ProviderStatus(
                provider=self.provider_id,
                name=self.name,
                available=False,
                model=self.model,
                configured=True,
                reason="Network error while checking provider",
                error="network_error",
            )

        return ProviderStatus(
            provider=self.provider_id,
            name=self.name,
            available=True,
            model=self.model,
            configured=True,
        )


# ─── 3. ANTHROPIC PROVIDER ─────────────────────────────────────────────────────
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
            "max_tokens": 180,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": build_user_prompt(request)},
            ],
        }

        try:
            client = get_shared_client(30.0)
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

    async def tutor_stream(self, request: TutorRequest) -> AsyncGenerator[str, None]:
        """Stream tutor response from Anthropic."""
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
            "stream": True,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": build_user_prompt(request)},
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                async with client.stream(
                    "POST",
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code == 401:
                        raise AIProviderError("Anthropic API key is invalid.", provider=self.provider_id, code="invalid_api_key")
                    elif response.status_code == 429:
                        raise AIProviderError("Anthropic rate limit reached.", provider=self.provider_id, code="rate_limit")
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            event_data = line[6:]  # Remove "data: " prefix
                            if event_data.strip() == "[DONE]":
                                break
                            if event_data.strip():
                                try:
                                    data = json.loads(event_data)
                                    if data.get("type") == "content_block_delta":
                                        delta = data.get("delta", {})
                                        if "text" in delta:
                                            text = delta["text"]
                                            if text:
                                                yield text
                                except json.JSONDecodeError:
                                    # Skip invalid JSON lines
                                    continue
        except (httpx.HTTPError, ValueError) as exc:
            raise AIProviderError("Anthropic API request failed.", provider=self.provider_id, code="network_error") from exc

    async def health(self) -> ProviderStatus:
        key = self.api_key
        if not key:
            return ProviderStatus(
                provider=self.provider_id,
                name=self.name,
                available=False,
                model=self.model,
                configured=False,
                reason="ANTHROPIC_API_KEY environment variable not set or key not stored",
                error="missing_api_key",
            )
        # Validate key format first
        try:
            from .api_key_manager import validate_api_key_format
            valid, vmsg = validate_api_key_format(self.provider_id, key)
            if not valid:
                return ProviderStatus(
                    provider=self.provider_id,
                    name=self.name,
                    available=False,
                    model=self.model,
                    configured=True,
                    reason=f"Invalid API key format: {vmsg}",
                    error="invalid_key_format",
                )
        except Exception:
            return ProviderStatus(
                provider=self.provider_id,
                name=self.name,
                available=False,
                model=self.model,
                configured=True,
                reason="Key validation failed",
                error="validation_error",
            )

        # Perform a lightweight API call to confirm the key works
        try:
            headers = {
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json={
                        "model": self.model,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
                if resp.status_code == 401:
                    return ProviderStatus(
                        provider=self.provider_id,
                        name=self.name,
                        available=False,
                        model=self.model,
                        configured=True,
                        reason="API key unauthorized",
                        error="invalid_api_key",
                    )
                if resp.status_code not in (200, 201):
                    return ProviderStatus(
                        provider=self.provider_id,
                        name=self.name,
                        available=False,
                        model=self.model,
                        configured=True,
                        reason=f"API returned status {resp.status_code}",
                        error="api_error",
                    )
        except Exception:
            return ProviderStatus(
                provider=self.provider_id,
                name=self.name,
                available=False,
                model=self.model,
                configured=True,
                reason="Network error while checking Anthropic",
                error="network_error",
            )

        return ProviderStatus(
            provider=self.provider_id,
            name=self.name,
            available=True,
            model=self.model,
            configured=True,
        )


# ─── 4. GEMINI PROVIDER ────────────────────────────────────────────────────────
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

        payload = {
            "contents": [{
                "parts": [{
                    "text": f"{SYSTEM_PROMPT}\n\n{build_user_prompt(request)}"
                }]
            }],
            "generationConfig": {
                "maxOutputTokens": 300,
                "temperature": 0.7
            }
        }

        try:
            client = get_shared_client(30.0)
            res = await client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}", json=payload)
            if res.status_code in (400, 401, 403):
                raise AIProviderError("Invalid API key - please check and try again", provider=self.provider_id, code="invalid_api_key")
            elif res.status_code == 429:
                raise AIProviderError("Gemini rate limit exceeded.", provider=self.provider_id, code="rate_limit")
            elif res.status_code != 200:
                raise AIProviderError(f"API returned error {res.status_code}", provider=self.provider_id, code="api_error")
            res.raise_for_status()
            data = res.json()
        except AIProviderError:
            raise
        except Exception as exc:
            raise AIProviderError("Gemini API request failed.", provider=self.provider_id, code="network_error") from exc

        try:
            candidates = data.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if parts:
                    text = parts[0].get("text", "")
                    if isinstance(text, str) and text.strip():
                        return text.strip()
            raise AIProviderError("Gemini returned an invalid response format.", provider=self.provider_id, code="malformed_response")
        except (KeyError, IndexError, TypeError):
            pass
        raise AIProviderError("Gemini returned an unexpected response format.", provider=self.provider_id, code="unexpected_response")

    async def tutor_stream(self, request: TutorRequest) -> AsyncGenerator[str, None]:
        """Stream tutor response from Gemini."""
        if not self.api_key:
            raise AIProviderError("Gemini API key is not configured.", provider=self.provider_id, code="missing_api_key")

        payload = {
            "contents": [{
                "parts": [{
                    "text": f"{SYSTEM_PROMPT}\n\n{build_user_prompt(request)}"
                }]
            }],
            "generationConfig": {
                "maxOutputTokens": 300,
                "temperature": 0.7
            }
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                async with client.stream(
                    "POST",
                    f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:streamGenerateContent?key={self.api_key}",
                    json=payload
                ) as response:
                    if response.status_code in (400, 401, 403):
                        raise AIProviderError("Invalid API key - please check and try again", provider=self.provider_id, code="invalid_api_key")
                    elif response.status_code != 200:
                        raise AIProviderError(f"API returned error {response.status_code}", provider=self.provider_id, code="api_error")
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if line.strip():
                            try:
                                data = json.loads(line)
                                if "candidates" in data and len(data["candidates"]) > 0:
                                    content = data["candidates"][0].get("content", {})
                                    parts = content.get("parts", [])
                                    if parts:
                                        text = parts[0].get("text", "")
                                        if text:
                                            yield text
                            except json.JSONDecodeError:
                                # Skip invalid JSON lines
                                continue
        except (httpx.HTTPError, ValueError) as exc:
            raise AIProviderError("Gemini API request failed.", provider=self.provider_id, code="network_error") from exc

    async def health(self) -> ProviderStatus:
        key = self.api_key
        if not key:
            return ProviderStatus(
                provider=self.provider_id,
                name=self.name,
                available=False,
                model=self.model,
                configured=False,
                reason="GEMINI_API_KEY environment variable not set or key not stored",
                error="missing_api_key",
            )
        # Gemini keys are usually alphanumeric with some special chars
        if len(key) < 30:
            return ProviderStatus(
                provider=self.provider_id,
                name=self.name,
                available=False,
                model=self.model,
                configured=True,
                reason="Gemini API key appears to be invalid",
                error="invalid_key_format",
            )
        if not key.replace("-", "").replace("_", "").isalnum():
            return ProviderStatus(
                provider=self.provider_id,
                name=self.name,
                available=False,
                model=self.model,
                configured=True,
                reason="Gemini API key contains invalid characters",
                error="invalid_key_format",
            )

        # Perform a lightweight API call to confirm the key works
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                )
                if resp.status_code in (400, 401, 403):
                    return ProviderStatus(
                        provider=self.provider_id,
                        name=self.name,
                        available=False,
                        model=self.model,
                        configured=True,
                        reason="Invalid API key - please check and try again",
                        error="invalid_api_key",
                    )
                if resp.status_code != 200:
                    return ProviderStatus(
                        provider=self.provider_id,
                        name=self.name,
                        available=False,
                        model=self.model,
                        configured=True,
                        reason=f"API returned error {resp.status_code}",
                        error="api_error",
                    )
        except Exception:
            return ProviderStatus(
                provider=self.provider_id,
                name=self.name,
                available=False,
                model=self.model,
                configured=True,
                reason="Network error while checking Gemini",
                error="network_error",
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
        default_model="meta-llama/llama-3.1-8b-instruct",
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