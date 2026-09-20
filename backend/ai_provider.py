from . import env as _env  # noqa: F401 — load .env before reading provider config

import os
import json
import logging
from dataclasses import dataclass, field
from typing import Protocol, Any
from urllib.parse import urlparse

import httpx

from .ai_models import OllamaHealth, ProviderStatus, TutorRequest
from .hint_contract import failing_check_names, redact_spec, system_prompt_for

logger = logging.getLogger("patchwork.ai_provider")


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
    async def generate_structured(self, system: str, user: str, max_tokens: int = 4000) -> str: ...
    async def health(self) -> ProviderStatus: ...


# Solutions need room for a full file plus one sentence.
TUTOR_MAX_TOKENS = 512
# Hints are 1-2 sentence nudges; a tight budget stops essays before they start.
HINT_MAX_TOKENS = 110
HINT_MAX_TOKENS_LEVEL4 = 150


def tutor_max_tokens(request: "TutorRequest") -> int:
    if getattr(request, "solution_requested", False):
        return TUTOR_MAX_TOKENS
    return HINT_MAX_TOKENS_LEVEL4 if int(getattr(request, "hint_level", 1) or 1) >= 4 else HINT_MAX_TOKENS


def _extract_openai_compatible_message(data: dict[str, Any]) -> str | None:
    """Return the model's SPEAKING text only.

    Reasoning models stream their private chain of thought into `reasoning`
    and it routinely contains the complete answer. Surfacing it as a hint is
    exactly what broke the learner flow, so it is never returned here; an
    empty `content` is treated as a provider failure and the tutor service
    repairs or falls back instead.
    """
    try:
        message_obj = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(message_obj, dict):
        return None
    candidate = message_obj.get("content")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    return None


def build_user_prompt(request: TutorRequest) -> str:
    unit_title = getattr(request, 'unit_title', '')
    concept_title = getattr(request, 'concept_title', '')
    prerequisites = getattr(request, 'prerequisites', [])
    lesson_id = getattr(request, 'lesson_id', '')
    source_summary = getattr(request, 'source_summary', '')
    generated_course_id = getattr(request, 'generated_course_id', None)

    lang_context = ""
    if generated_course_id or source_summary:
        lang_context = f"Custom Generated Course Context ({generated_course_id or 'active'}):\nSummary: {source_summary}\n"
    if "sql" in lesson_id.lower():
        lang_context = (
            "SQL Context:\n"
            "Database engine: SQLite (in-memory isolated).\n"
            "Available Seed Tables: customers(id, name, email, country), "
            "users(id, username, email, created_at, role), "
            "products(id, name, category, price, stock), "
            "orders(id, customer_id, product_id, quantity, order_date, total_amount), "
            "employees(id, first_name, last_name, department, salary), "
            "courses(id, title, category, price), "
            "transactions(id, user_id, amount, status, timestamp).\n"
        )
    elif "ts" in lesson_id.lower() or "typescript" in lesson_id.lower():
        lang_context = "Language Context: TypeScript (Static typing over JavaScript runtime).\n"
    elif "js" in lesson_id.lower() or "javascript" in lesson_id.lower():
        lang_context = "Language Context: JavaScript (Browser DOM / Node.js runtime).\n"

    unit_part = f"Unit: {unit_title}\n" if unit_title else ""
    concept_part = f"Concept: {concept_title}\n" if concept_title else ""
    prereq_part = f"Prerequisite concepts: {', '.join(prerequisites)}\n" if prerequisites else ""
    adaptation_hint = getattr(request, 'adaptation_hint', '') or ''
    adaptation_part = f"Live learner-feedback adaptation: {adaptation_hint}\n" if adaptation_hint.strip() else ""

    # ─── Disclosure ladder ────────────────────────────────────────────────────
    # Each level is handed strictly more information, so an early nudge cannot
    # be built out of the very values the learner is meant to work out. Test
    # output is withheld until level 3 because assertion messages routinely
    # contain the expected value verbatim.
    level = int(getattr(request, "hint_level", 1) or 1)
    wants_solution = bool(getattr(request, "solution_requested", False))
    full = wants_solution or level >= 3
    mid = wants_solution or level >= 2

    if full:
        instructions_label, instructions = "Instructions", request.instructions
    else:
        instructions_label = (
            "Instructions (expected values hidden at this level — never guess them aloud)"
        )
        instructions = redact_spec(request.instructions) or request.instructions

    if full:
        results_label = "Deterministic test results (authoritative)"
        results_part = f"{results_label}: {request.test_results}\n"
    elif mid:
        results_part = (
            "Failing check names only (details withheld at this level): "
            f"{failing_check_names(request.test_results)}\n"
        )
    else:
        results_part = (
            "Test details withheld at this level: the learner needs a concept nudge, "
            "not a diagnosis.\n"
        )

    code_part = (
        f"Student code:\n{request.code}\n"
        if mid
        else "Student code withheld at this level: do not describe their specific mistake.\n"
    )

    if wants_solution:
        reminder = "Now reply with the corrected code in one fenced block plus one short sentence."
    else:
        reminder = (
            "Now reply with the hint only: 1-2 plain sentences, at most 35 words, no code, "
            "no markdown, no preamble, ending in the learner's next action."
        )

    return (
        f"{lang_context}"
        f"{unit_part}{concept_part}{prereq_part}"
        f"Lesson: {request.lesson_title} ({request.lesson_id})\n"
        f"{instructions_label}: {instructions}\n"
        f"{code_part}"
        f"{results_part}"
        f"Previous hints in this session: {request.previous_hints}\n"
        f"Requested hint level: {request.hint_level}\n"
        f"solution_requested: {request.solution_requested}\n"
        f"{reminder}\n"
        f"{adaptation_part}"
    )


# ─── SHARED HTTP CLIENT FOR LATENCY OPTIMIZATION ──────────────────────────────
_shared_client: httpx.AsyncClient | None = None

def get_shared_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=20, max_connections=100))
    return _shared_client

async def close_shared_client() -> None:
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
        _shared_client = None


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
        payload: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "options": {"num_predict": tutor_max_tokens(request)},
            "messages": [
                {"role": "system", "content": system_prompt_for(request)},
                {"role": "user", "content": prompt},
            ],
        }
        if not getattr(request, "solution_requested", False):
            # Ollama runs thinking models too; a hint must never be a
            # chain-of-thought dump, so ask for a direct answer when supported.
            payload["think"] = False
        try:
            client = get_shared_client()
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout_seconds,
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

    async def generate_structured(self, system: str, user: str, max_tokens: int = 4000) -> str:
        try:
            client = get_shared_client()
            response = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "options": {"num_predict": max_tokens, "temperature": 0.0},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=self.timeout_seconds,
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
    # OpenRouter understands a `reasoning` control object; other OpenAI-compatible
    # servers may reject unknown fields, so it is opt-in per provider.
    supports_reasoning_param: bool = False

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
            "max_tokens": tutor_max_tokens(request),
            "messages": [
                {"role": "system", "content": system_prompt_for(request)},
                {"role": "user", "content": build_user_prompt(request)},
            ],
        }
        if self.supports_reasoning_param and not request.solution_requested:
            # Hints must arrive as speaking text. Reasoning models otherwise
            # spend the whole budget on a private chain of thought that
            # contains the answer, and the learner sees nothing usable.
            payload["reasoning"] = {"effort": "none"}

        try:
            client = get_shared_client()
            res = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=30.0)
            if res.status_code == 400 and "reasoning" in payload:
                # Some OpenAI-compatible servers reject the reasoning control
                # object; drop it and ask once more rather than lose the hint.
                payload.pop("reasoning", None)
                res = await client.post(
                    f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=30.0
                )
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

        message = _extract_openai_compatible_message(data)
        if message:
            return message
        raise AIProviderError(f"{self.name} returned an unexpected response format.", provider=self.provider_id, code="malformed_response")

    async def generate_structured(self, system: str, user: str, max_tokens: int = 4000) -> str:
        if not self.api_key:
            raise AIProviderError(f"{self.name} API key is not configured.", provider=self.provider_id, code="missing_api_key")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.headers_extra,
        }

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

        try:
            client = get_shared_client()
            res = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=60.0)
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

        message = _extract_openai_compatible_message(data)
        if message:
            return message
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

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.headers_extra,
        }
        try:
            client = get_shared_client()
            res = await client.get(f"{self.base_url}/models", headers=headers, timeout=10.0)
            if res.status_code == 401:
                return ProviderStatus(
                    provider=self.provider_id,
                    name=self.name,
                    available=False,
                    model=self.model,
                    configured=True,
                    reason=f"{self.name} API key is invalid or unauthorized.",
                    error="invalid_api_key",
                )
            if res.status_code != 200:
                return ProviderStatus(
                    provider=self.provider_id,
                    name=self.name,
                    available=False,
                    model=self.model,
                    configured=True,
                    reason=f"{self.name} health check failed with status {res.status_code}.",
                    error="health_check_failed",
                )
        except Exception as exc:
            logger.warning("%s health check failed: %s", self.name, exc)
            return ProviderStatus(
                provider=self.provider_id,
                name=self.name,
                available=False,
                model=self.model,
                configured=True,
                reason=f"{self.name} request failed or timed out.",
                error="network_error",
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
            "max_tokens": tutor_max_tokens(request),
            "system": system_prompt_for(request),
            "messages": [
                {"role": "user", "content": build_user_prompt(request)},
            ],
        }
        # Anthropic's extended thinking is off unless requested, so hints
        # already arrive as speaking text and need no extra control object.

        try:
            client = get_shared_client()
            res = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=30.0)
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

    async def generate_structured(self, system: str, user: str, max_tokens: int = 4000) -> str:
        if not self.api_key:
            raise AIProviderError("Anthropic API key is not configured.", provider=self.provider_id, code="missing_api_key")

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": 0.0,
            "system": system,
            "messages": [
                {"role": "user", "content": user},
            ],
        }

        try:
            client = get_shared_client()
            res = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=60.0)
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
                "parts": [{"text": system_prompt_for(request)}]
            },
            "contents": [{
                "parts": [{"text": build_user_prompt(request)}]
            }],
            "generationConfig": {
                "maxOutputTokens": tutor_max_tokens(request),
            }
        }

        try:
            client = get_shared_client()
            res = await client.post(url, json=payload, timeout=30.0)
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

    async def generate_structured(self, system: str, user: str, max_tokens: int = 4000) -> str:
        if not self.api_key:
            raise AIProviderError("Gemini API key is not configured.", provider=self.provider_id, code="missing_api_key")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "system_instruction": {
                "parts": [{"text": system}]
            },
            "contents": [{
                "parts": [{"text": user}]
            }],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.0,
            }
        }

        try:
            client = get_shared_client()
            res = await client.post(url, json=payload, timeout=60.0)
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
        default_model="meta-llama/llama-3.1-8b-instruct",
        base_url_env="OPENROUTER_BASE_URL",
        default_base_url="https://openrouter.ai/api/v1",
        headers_extra={"HTTP-Referer": "https://github.com/patchwork", "X-Title": "Patchwork AI Tutor"},
        supports_reasoning_param=True,
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
