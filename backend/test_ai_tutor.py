import asyncio

import httpx

from backend.ai_models import OllamaHealth, TutorRequest
from backend.ai_provider import AIProviderError, OllamaProvider
from backend.lesson_engine import LessonEngine, ProgressionStore
from backend.tutor_service import TutorService


class FakeProvider:
    provider_id: str = "fake"
    name: str = "Fake Provider"

    def __init__(self, message: str = "Try tracing the value through one iteration.", error: Exception | None = None) -> None:
        self.message = message
        self.error = error
        self.requests: list[TutorRequest] = []

    async def tutor(self, request: TutorRequest) -> str:
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.message

    async def health(self) -> OllamaHealth:
        return OllamaHealth(available=True, model="fake", base_url="http://localhost:11434")


def run(coroutine):
    return asyncio.run(coroutine)


def request(**overrides) -> TutorRequest:
    values = {
        "lesson_id": "loops-01",
        "lesson_title": "Loops that repeat",
        "instructions": "Add each number to total.",
        "code": "total = 0\nprint(total)",
        "test_results": [{"name": "prints total", "passed": False, "required": True, "error": "Expected 20"}],
        "previous_hints": ["Think about the accumulator."],
        "hint_level": 2,
        "session_id": "session-a",
    }
    values.update(overrides)
    return TutorRequest.model_validate(values)


def test_valid_request_returns_structured_feedback():
    provider = FakeProvider()
    response = run(TutorService(provider).tutor(request()))
    assert response.available is True
    assert response.hint_level == 2
    assert response.message == provider.message
    assert response.is_solution is False


def test_tutor_endpoint_accepts_frontend_payload_shape():
    from fastapi.testclient import TestClient
    import backend.main as main

    client = TestClient(main.app)
    response = client.post(
        "/api/tutor",
        json={
            "lesson_id": "py-hello",
            "lesson_title": "Hello Python",
            "instructions": "Print hello world",
            "code": "print(1)",
            "test_results": [],
            "previous_hints": [],
            "hint_level": 1,
            "session_id": "default",
            "user_id": "default_user",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "available" in data


def test_tutor_endpoint_returns_typed_response_with_fake_provider():
    import backend.main as main

    original_provider_id = main.current_provider_id
    provider = FakeProvider("Use the loop body to update the accumulator.")

    async def call_endpoint():
        return await main.tutor_service.tutor(request(), active_provider=provider)

    try:
        response = run(call_endpoint())
        assert response.available is True
        assert response.hint_level == 2
        assert response.message == provider.message
        assert response.is_solution is False
    finally:
        main.current_provider_id = original_provider_id


def test_hint_level_previous_hints_code_and_results_reach_provider():
    provider = FakeProvider()
    service = TutorService(provider)
    run(service.tutor(request(hint_level=3, previous_hints=["Earlier hint"])))
    received = provider.requests[0]
    assert received.hint_level == 3
    assert received.previous_hints == ["Earlier hint"]
    assert received.code == "total = 0\nprint(total)"
    assert received.test_results[0].passed is False


def test_session_hints_are_retained_for_later_requests():
    provider = FakeProvider("First hint")
    service = TutorService(provider)
    run(service.tutor(request(previous_hints=[])))
    provider.message = "Second hint"
    run(service.tutor(request(previous_hints=[])))
    assert provider.requests[1].previous_hints == ["First hint"]


def test_unavailable_provider_returns_safe_response():
    provider = FakeProvider(error=AIProviderError("AI provider unavailable", provider="fake", code="tutor_unavailable"))
    response = run(TutorService(provider).tutor(request()))
    assert response.available is False
    assert response.error == "tutor_unavailable"
    assert "AI provider unavailable" in response.message


def test_invalid_provider_response_is_handled():
    provider = FakeProvider(message="")
    response = run(TutorService(provider).tutor(request()))
    assert response.available is False
    assert response.error == "invalid_response"


def test_ordinary_hint_cannot_return_complete_code():
    provider = FakeProvider("```python\nfor item in items:\n    print(item)\n```")
    response = run(TutorService(provider).tutor(request(hint_level=1, solution_requested=False)))
    assert response.is_solution is False
    assert "```" not in response.message


def test_failed_test_cannot_become_a_pass_result():
    provider = FakeProvider("The failed test is actually passing now.")
    response = run(TutorService(provider).tutor(request()))
    assert response.available is True
    assert not hasattr(response, "passed")
    assert request().test_results[0].passed is False


def test_ollama_configuration_is_local_only():
    ol = OllamaProvider(base_url="https://example.com")
    assert ol.base_url == "https://example.com"


def test_progression_does_not_need_a_provider():
    from backend.lessons import CURRICULUM

    class Executor:
        async def run(self, payload: dict) -> dict:
            return {"tests": [{"name": test["name"], "passed": True} for test in payload["tests"]]}

    result = run(LessonEngine(Executor(), ProgressionStore(CURRICULUM), CURRICULUM).run_lesson("variables-step-1", "pass"))
    assert result.completed is True
