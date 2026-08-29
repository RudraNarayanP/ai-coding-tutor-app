import os
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlparse

import httpx

from .ai_models import OllamaHealth, TutorRequest


class AIProviderError(Exception):
    pass


class AIProvider(Protocol):
    async def tutor(self, request: TutorRequest) -> str: ...
    async def health(self) -> OllamaHealth: ...


@dataclass(frozen=True)
class OllamaConfig:
    base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"))
    model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3.1:8b"))
    timeout_seconds: float = field(default_factory=lambda: float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "45")))

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Ollama must use a localhost HTTP endpoint.")
        if not self.model or len(self.model) > 120:
            raise ValueError("OLLAMA_MODEL must be a non-empty model name.")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 300:
            raise ValueError("OLLAMA_TIMEOUT_SECONDS must be between 0 and 300.")


@dataclass
class OllamaProvider:
    config: OllamaConfig = field(default_factory=OllamaConfig)

    async def tutor(self, request: TutorRequest) -> str:
        system = (
            "You are a patient coding teacher. Deterministic test results are authoritative and cannot be changed. "
            "Return tutoring prose only. Follow the requested hint level exactly. "
            "Do not provide complete working code unless solution_requested is true.\n"
            "Level 1: explain the concept without naming the exact mistake.\n"
            "Level 2: point toward the relevant part of the approach.\n"
            "Level 3: identify the student's mistake.\n"
            "Level 4: explain the correct approach in detail."
        )
        prompt = (
            f"Lesson: {request.lesson_title} ({request.lesson_id})\n"
            f"Instructions: {request.instructions}\n"
            f"Student code:\n{request.code}\n"
            f"Deterministic test results (authoritative): {request.test_results}\n"
            f"Previous hints in this session: {request.previous_hints}\n"
            f"Requested hint level: {request.hint_level}\n"
            f"solution_requested: {request.solution_requested}"
        )
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                response = await client.post(
                    f"{self.config.base_url}/api/chat",
                    json={
                        "model": self.config.model,
                        "stream": False,
                        "options": {"num_predict": 300},
                        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                    },
                )
                if response.status_code == 404:
                    raise AIProviderError("Configured Ollama model is unavailable.")
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AIProviderError("Ollama returned an invalid or unreachable response.") from exc
        message = payload.get("message", {}).get("content") if isinstance(payload, dict) else None
        if not isinstance(message, str) or not message.strip():
            raise AIProviderError("Ollama returned an invalid response.")
        return message.strip()

    async def health(self) -> OllamaHealth:
        try:
            async with httpx.AsyncClient(timeout=min(self.config.timeout_seconds, 5)) as client:
                response = await client.get(f"{self.config.base_url}/api/tags")
                response.raise_for_status()
                payload = response.json()
            models = payload.get("models", []) if isinstance(payload, dict) else []
            names = {model.get("name") for model in models if isinstance(model, dict)}
            if self.config.model not in names:
                return OllamaHealth(available=False, model=self.config.model, base_url=self.config.base_url, error="configured_model_missing")
            return OllamaHealth(available=True, model=self.config.model, base_url=self.config.base_url)
        except (httpx.HTTPError, ValueError, TypeError):
            return OllamaHealth(available=False, model=self.config.model, base_url=self.config.base_url, error="ollama_unavailable")
