import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from .ai_models import TutorRequest, TutorResponse
from .ai_provider import AIProvider, AIProviderError, get_ai_provider, ALL_PROVIDERS  # noqa: F401
from .hint_contract import (
    HINT_CONTRACT_VERSION,
    leak_reasons,
    offline_hint,
    repair_hint,
    strict_retry_request,
)

logger = logging.getLogger("patchwork.tutor")

# Errors worth one quick second chance: free-tier routers throttle constantly,
# and a 429 that clears in a heartbeat should not cost the learner a real hint.
TRANSIENT_PROVIDER_ERRORS = frozenset({"rate_limit", "network_error", "malformed_response"})


@dataclass
class TutorSessionStore:
    _hints: dict[tuple[str, str], list[str]] = field(default_factory=dict)

    def hints_for(self, session_id: str, lesson_id: str) -> list[str]:
        return list(self._hints.get((session_id, lesson_id), []))

    def add_hint(self, session_id: str, lesson_id: str, hint: str) -> None:
        key = (session_id, lesson_id)
        hints = self._hints.setdefault(key, [])
        if hint not in hints:
            hints.append(hint)
        del hints[:-8]


class TutorService:
    """Turns provider output into something a learner can actually use.

    Hints follow a strict flow-state contract: short, plain, spoiler-free, and
    ALWAYS available. When a model breaks the contract we repair the reply,
    retry once under stricter instructions, and finally fall back to a
    deterministic nudge built from the learner's own code and failing checks.
    Learners never see a provider error where a hint should be.
    """

    def __init__(
        self,
        provider: AIProvider | None = None,
        sessions: TutorSessionStore | None = None,
        lesson_lookup: Callable[[str], object | None] | None = None,
        backoff_seconds: float = 1.5,
    ) -> None:
        self.provider = provider or get_ai_provider()
        self.sessions = sessions or TutorSessionStore()
        # lesson_id -> lesson with .solution_code/.starter_code, used only to
        # detect spoilers. Never sent to the provider.
        self.lesson_lookup = lesson_lookup
        self.backoff_seconds = backoff_seconds

    # ─── helpers ──────────────────────────────────────────────────────────────

    def _reference(self, lesson_id: str) -> tuple[str, str]:
        if not self.lesson_lookup:
            return "", ""
        try:
            lesson = self.lesson_lookup(lesson_id)
        except Exception:  # a broken lookup must never break tutoring
            return "", ""
        if lesson is None:
            return "", ""
        return (
            getattr(lesson, "solution_code", "") or "",
            getattr(lesson, "starter_code", "") or "",
        )

    @staticmethod
    def _sanitize(message: str, request: TutorRequest) -> str:
        """Legacy entry point kept for existing tests and callers."""
        message = (message or "").strip()
        if not message or len(message) > 6000:
            raise AIProviderError("Tutor returned an invalid response.")
        if request.solution_requested:
            return message
        hint = repair_hint(message)
        if not hint:
            raise AIProviderError("Tutor revealed full code in hint.")
        return hint

    async def _ask(
        self, primary: AIProvider, attempt: TutorRequest, *, retry_transient: bool
    ) -> tuple[str | None, str | None]:
        """One provider call, with a single quick retry on throttling."""
        try:
            return await primary.tutor(attempt), None
        except AIProviderError as exc:
            code = exc.code or "tutor_unavailable"
            logger.info("hint request failed (%s): %s", code, exc.message)
            if not (retry_transient and code in TRANSIENT_PROVIDER_ERRORS):
                return None, code
            await asyncio.sleep(self.backoff_seconds)
            try:
                return await primary.tutor(attempt), None
            except AIProviderError as again:
                return None, again.code or "tutor_unavailable"

    async def _hint_with_repair(
        self, primary: AIProvider, request: TutorRequest
    ) -> tuple[str, str, str | None]:
        """Return (hint, source, diagnostic_error). Never raises."""
        solution, starter = self._reference(request.lesson_id)
        max_sentences = 3 if request.hint_level >= 4 else 2
        diagnostic: str | None = None

        for attempt_index, attempt in enumerate((request, strict_retry_request(request))):
            raw, error_code = await self._ask(
                primary, attempt, retry_transient=attempt_index == 0
            )
            if error_code:
                diagnostic = error_code
                break  # the provider is down; do not hammer it
            hint = repair_hint(
                raw,
                solution=solution,
                starter=starter,
                instructions=request.instructions,
                max_sentences=max_sentences,
            )
            if hint:
                source = "ai" if attempt_index == 0 else "ai_repaired"
                return hint, source, None
            diagnostic = "contract_violation"
            reasons = leak_reasons(
                raw or "",
                solution=solution,
                starter=starter,
                instructions=request.instructions,
            )
            logger.info(
                "hint contract violated (attempt %s): %s | reply=%r",
                attempt_index + 1,
                reasons or ["too_long_or_empty"],
                (raw or "")[:200],
            )

        return (
            offline_hint(
                code=request.code,
                test_results=request.test_results,
                hint_level=request.hint_level,
                previous_hints=request.previous_hints,
                learning_objective=getattr(request, "learning_objective", "") or "",
            ),
            "offline",
            diagnostic,
        )

    # ─── API ──────────────────────────────────────────────────────────────────

    async def tutor(
        self, request: TutorRequest, active_provider: AIProvider | None = None
    ) -> TutorResponse:
        primary = active_provider or self.provider
        stored = self.sessions.hints_for(request.session_id, request.lesson_id)
        previous = list(dict.fromkeys(stored + request.previous_hints))[-8:]
        effective_request = request.model_copy(update={"previous_hints": previous})

        if request.solution_requested:
            return await self._solution(primary, effective_request)
        return await self._hint(primary, effective_request)

    async def _solution(self, primary: AIProvider, request: TutorRequest) -> TutorResponse:
        try:
            raw = await primary.tutor(request)
        except AIProviderError as err:
            return TutorResponse(
                hint_level=request.hint_level,
                message=err.message,
                available=False,
                provider=primary.provider_id,
                error=err.code or "tutor_unavailable",
                source="unavailable",
            )
        message = (raw or "").strip()
        if not message or len(message) > 6000:
            return TutorResponse(
                hint_level=request.hint_level,
                message="Tutor returned an invalid response.",
                available=False,
                provider=primary.provider_id,
                error="invalid_response",
                source="unavailable",
            )
        return TutorResponse(
            hint_level=request.hint_level,
            message=message,
            is_solution=True,
            available=True,
            provider=primary.provider_id,
            model=getattr(primary, "model", None),
            source="ai",
            contract_version=HINT_CONTRACT_VERSION,
        )

    async def _hint(self, primary: AIProvider, request: TutorRequest) -> TutorResponse:
        message, source, diagnostic = await self._hint_with_repair(primary, request)
        self.sessions.add_hint(request.session_id, request.lesson_id, message)
        return TutorResponse(
            hint_level=request.hint_level,
            message=message,
            is_solution=False,
            available=True,
            provider=primary.provider_id if source != "offline" else None,
            model=getattr(primary, "model", None) if source != "offline" else None,
            error=diagnostic,
            source=source,
            contract_version=HINT_CONTRACT_VERSION,
        )
