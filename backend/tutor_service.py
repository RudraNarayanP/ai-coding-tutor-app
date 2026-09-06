import re
from dataclasses import dataclass, field

from .ai_models import TutorRequest, TutorResponse
from .ai_provider import AIProvider, AIProviderError, get_ai_provider, ALL_PROVIDERS


LEVEL_FALLBACKS = {
    1: "Think about the programming concept this exercise is practicing. What should happen for each value?",
    2: "Look at the part of your approach that handles each value. Trace one pass through it by hand.",
    3: "Compare the failing test with the relevant line in your code. That line does not produce the value the test expects.",
    4: "Trace the expected result from the inputs, then make the smallest change that produces that result for every case.",
}


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
    def __init__(
        self,
        provider: AIProvider | None = None,
        fallback_provider: AIProvider | None = None,
        sessions: TutorSessionStore | None = None,
    ) -> None:
        self.provider = provider or get_ai_provider()
        self.fallback_provider = fallback_provider
        self.sessions = sessions or TutorSessionStore()

    @staticmethod
    def _sanitize(message: str, request: TutorRequest) -> str:
        message = message.strip()
        if not message or len(message) > 6000:
            raise AIProviderError("Tutor returned an invalid response.")
        if not request.solution_requested and ("```" in message or len(re.findall(r"(?m)^\s*(def |class |for |while |import |from |[A-Za-z_][A-Za-z0-9_]*\s*=)", message)) >= 3):
            return LEVEL_FALLBACKS[request.hint_level]
        return message

    async def tutor(self, request: TutorRequest, active_provider: AIProvider | None = None) -> TutorResponse:
        primary = active_provider or self.provider
        stored = self.sessions.hints_for(request.session_id, request.lesson_id)
        previous = list(dict.fromkeys(stored + request.previous_hints))[-8:]
        effective_request = request.model_copy(update={"previous_hints": previous})

        used_fallback = False
        target_provider = primary
        raw_message = None

        try:
            raw_message = await target_provider.tutor(effective_request)
        except AIProviderError as primary_err:
            if self.fallback_provider and self.fallback_provider.provider_id != target_provider.provider_id:
                try:
                    target_provider = self.fallback_provider
                    raw_message = await target_provider.tutor(effective_request)
                    used_fallback = True
                except AIProviderError as fallback_err:
                    return TutorResponse(
                        hint_level=request.hint_level,
                        message=f"{primary_err.message} Fallback ({self.fallback_provider.name}) also failed: {fallback_err.message}",
                        available=False,
                        provider=primary.provider_id,
                        error=primary_err.code or "tutor_unavailable",
                    )
            else:
                return TutorResponse(
                    hint_level=request.hint_level,
                    message=primary_err.message,
                    available=False,
                    provider=primary.provider_id,
                    error=primary_err.code or "tutor_unavailable",
                )

        try:
            message = self._sanitize(raw_message, effective_request)
        except AIProviderError as sanitize_err:
            return TutorResponse(
                hint_level=request.hint_level,
                message=sanitize_err.message,
                available=False,
                provider=target_provider.provider_id,
                error="invalid_response",
            )

        self.sessions.add_hint(request.session_id, request.lesson_id, message)
        return TutorResponse(
            hint_level=request.hint_level,
            message=message,
            is_solution=request.solution_requested,
            available=True,
            provider=target_provider.provider_id,
            model=getattr(target_provider, "model", None),
            used_fallback=used_fallback,
        )
