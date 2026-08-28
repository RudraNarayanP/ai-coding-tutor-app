import re
from dataclasses import dataclass, field

from .ai_models import TutorRequest, TutorResponse
from .ai_provider import AIProvider, AIProviderError


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
    def __init__(self, provider: AIProvider, sessions: TutorSessionStore | None = None) -> None:
        self.provider = provider
        self.sessions = sessions or TutorSessionStore()

    @staticmethod
    def _sanitize(message: str, request: TutorRequest) -> str:
        message = message.strip()
        if not message or len(message) > 6000:
            raise AIProviderError("Tutor returned an invalid response.")
        if not request.solution_requested and ("```" in message or len(re.findall(r"(?m)^\s*(def |class |for |while |import |from |[A-Za-z_][A-Za-z0-9_]*\s*=)", message)) >= 3):
            return LEVEL_FALLBACKS[request.hint_level]
        return message

    async def tutor(self, request: TutorRequest) -> TutorResponse:
        stored = self.sessions.hints_for(request.session_id, request.lesson_id)
        previous = list(dict.fromkeys(stored + request.previous_hints))[-8:]
        effective_request = request.model_copy(update={"previous_hints": previous})
        try:
            message = self._sanitize(await self.provider.tutor(effective_request), effective_request)
        except AIProviderError:
            return TutorResponse(hint_level=request.hint_level, message="AI tutoring is unavailable right now. Deterministic tests and lessons are still available.", available=False, error="tutor_unavailable")
        self.sessions.add_hint(request.session_id, request.lesson_id, message)
        return TutorResponse(hint_level=request.hint_level, message=message, is_solution=request.solution_requested, available=True)
