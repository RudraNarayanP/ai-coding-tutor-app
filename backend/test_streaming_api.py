"""Integration tests for the streaming tutor endpoint and stored-key settings API."""

import json

import httpx
import pytest
from fastapi.middleware.gzip import GZipMiddleware

import backend.main as main
from backend.ai_models import TutorRequest
from backend.ai_provider import AIProviderError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def request(**overrides) -> TutorRequest:
    values = {
        "lesson_id": "loops-01",
        "lesson_title": "Loops that repeat",
        "instructions": "Add each number to total.",
        "code": "total = 0\nprint(total)",
        "test_results": [{"name": "prints total", "passed": False, "required": True, "error": "Expected 20"}],
        "previous_hints": [],
        "hint_level": 2,
        "session_id": "stream-test",
    }
    values.update(overrides)
    return TutorRequest.model_validate(values)


class FakeStreamingProvider:
    """Provider that implements tutor_stream by yielding tokens."""

    provider_id = "fake-stream"
    name = "Fake Streaming Provider"
    model = "fake-model"

    def __init__(self, tokens=None, error=None) -> None:
        self.tokens = tokens if tokens is not None else ["Try ", "tracing ", "the loop."]
        self.error = error

    async def tutor(self, request: TutorRequest) -> str:
        return "".join(self.tokens)

    async def tutor_stream(self, request: TutorRequest):
        if self.error:
            raise self.error
        for token in self.tokens:
            yield token

    async def health(self):
        from backend.ai_models import ProviderStatus

        return ProviderStatus(provider=self.provider_id, name=self.name, available=True, model=self.model)


class FakePlainProvider:
    """Provider without streaming support (no tutor_stream attribute)."""

    provider_id = "fake-plain"
    name = "Fake Plain Provider"
    model = "fake-model"

    def __init__(self, message="Think about the accumulator.") -> None:
        self.message = message

    async def tutor(self, request: TutorRequest) -> str:
        return self.message

    async def health(self):
        from backend.ai_models import ProviderStatus

        return ProviderStatus(provider=self.provider_id, name=self.name, available=True, model=self.model)


def parse_sse(raw: str) -> list[dict]:
    events = []
    for block in raw.split("\n\n"):
        if block.startswith("data: "):
            events.append(json.loads(block[len("data: "):]))
    return events


async def collect_stream(client: httpx.AsyncClient, payload: dict):
    async with client.stream("POST", "/api/tutor/stream", json=payload) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = ""
        async for chunk in response.aiter_text():
            raw += chunk
        return response, raw


# ---------------------------------------------------------------------------
# Streaming tutor endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_endpoint_emits_tokens_then_complete(monkeypatch):
    provider = FakeStreamingProvider()
    monkeypatch.setattr(main, "get_current_provider", lambda: provider)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        _, raw = await collect_stream(client, request().model_dump())

    events = parse_sse(raw)
    types = [event["type"] for event in events]
    assert types[0] == "token"
    assert types[-1] == "complete"
    assert types.count("complete") == 1
    token_content = "".join(event["content"] for event in events if event["type"] == "token")
    complete_event = events[-1]
    assert complete_event["content"] == token_content == "Try tracing the loop."


@pytest.mark.asyncio
async def test_stream_endpoint_falls_back_for_non_streaming_provider(monkeypatch):
    provider = FakePlainProvider()
    monkeypatch.setattr(main, "get_current_provider", lambda: provider)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        _, raw = await collect_stream(client, request().model_dump())

    events = parse_sse(raw)
    assert [event["type"] for event in events] == ["complete"]
    assert events[0]["content"] == provider.message


@pytest.mark.asyncio
async def test_stream_endpoint_emits_error_event_on_provider_failure(monkeypatch):
    provider = FakeStreamingProvider(error=AIProviderError("Ollama is down", provider="fake-stream", code="network_error"))
    monkeypatch.setattr(main, "get_current_provider", lambda: provider)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        _, raw = await collect_stream(client, request().model_dump())

    events = parse_sse(raw)
    assert events[-1]["type"] == "error"
    assert "Ollama is down" in events[-1]["message"]


@pytest.mark.asyncio
async def test_stream_endpoint_sanitises_code_leaking_responses(monkeypatch):
    provider = FakeStreamingProvider(tokens=["```python\n", "for i in range(3):\n", "    print(i)\n", "```"])
    monkeypatch.setattr(main, "get_current_provider", lambda: provider)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        _, raw = await collect_stream(client, request().model_dump())

    events = parse_sse(raw)
    complete = [event for event in events if event["type"] == "complete"][-1]
    assert "```" not in complete["content"]
    assert complete["content"]  # replaced by a safe hint-level fallback


# ---------------------------------------------------------------------------
# Stored-key settings endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settings_keys_metadata_endpoint():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get("/api/settings/keys")
    assert response.status_code == 200
    data = response.json()
    for field in ("keys_file", "master_key_file", "config_dir", "providers_with_keys"):
        assert field in data


@pytest.mark.asyncio
async def test_stored_provider_key_masking(monkeypatch):
    monkeypatch.setattr(main, "get_api_key", lambda pid: "sk-1234567890abcdefghij1234")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        masked = await client.get("/api/settings/providers/openai/key")
        revealed = await client.get("/api/settings/providers/openai/key", params={"reveal": "true"})

    assert masked.status_code == 200
    assert masked.json()["has_key"] is True
    assert masked.json()["key_masked"] == "sk-1...1234"
    assert "sk-1234567890abcdefghij1234" not in masked.text
    assert revealed.status_code == 200
    assert revealed.json()["key"] == "sk-1234567890abcdefghij1234"


@pytest.mark.asyncio
async def test_stored_provider_key_missing_returns_404(monkeypatch):
    monkeypatch.setattr(main, "get_api_key", lambda pid: None)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get("/api/settings/providers/openai/key")

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "key_not_found"


@pytest.mark.asyncio
async def test_stored_provider_key_unknown_provider_returns_400():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.get("/api/settings/providers/not-a-provider/key")

    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_provider"


# ---------------------------------------------------------------------------
# Middleware / backward compatibility
# ---------------------------------------------------------------------------


def test_gzip_middleware_is_enabled():
    assert any(mw.cls is GZipMiddleware for mw in main.app.user_middleware)


@pytest.mark.asyncio
async def test_non_streaming_tutor_endpoint_still_works(monkeypatch):
    provider = FakePlainProvider()
    monkeypatch.setattr(main, "get_current_provider", lambda: provider)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
        response = await client.post("/api/tutor", json=request().model_dump())

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["message"] == provider.message
