import os
import pytest
import httpx
from unittest.mock import AsyncMock, patch

from backend.ai_models import TutorRequest, ProviderStatus
from backend.ai_provider import (
    AIProviderError,
    OllamaProvider,
    OpenAICompatibleProvider,
    AnthropicProvider,
    GeminiProvider,
    get_ai_provider,
)
from backend.tutor_service import TutorService, TutorSessionStore


@pytest.fixture
def sample_request():
    return TutorRequest(
        lesson_id="variables-01",
        lesson_title="Variable Assignment",
        instructions="Create variable country = 'Italy'",
        code="country = None",
        test_results=[],
        previous_hints=[],
        hint_level=1,
    )


@pytest.mark.asyncio
async def test_provider_factory():
    with patch.dict(os.environ, {"AI_PROVIDER": "openai"}):
        p = get_ai_provider()
        assert p.provider_id == "openai"

    with patch.dict(os.environ, {"AI_PROVIDER": "anthropic"}):
        p = get_ai_provider()
        assert p.provider_id == "anthropic"

    with patch.dict(os.environ, {"AI_PROVIDER": "openrouter"}):
        p = get_ai_provider()
        assert p.provider_id == "openrouter"

    with patch.dict(os.environ, {"AI_PROVIDER": "gemini"}):
        p = get_ai_provider()
        assert p.provider_id == "gemini"

    with patch.dict(os.environ, {"AI_PROVIDER": "unknown"}):
        p = get_ai_provider()
        assert p.provider_id == "ollama"


@pytest.mark.asyncio
async def test_openai_missing_key_health():
    p = get_ai_provider("openai")
    with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=True):
        st = await p.health()
        assert st.available is False
        assert st.error == "missing_api_key"


@pytest.mark.asyncio
async def test_openai_provider_tutor_success(sample_request):
    p = OpenAICompatibleProvider(
        provider_id="openai",
        name="OpenAI",
        api_key_env="OPENAI_API_KEY",
        model_env="OPENAI_MODEL",
        default_model="gpt-4o-mini",
    )
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}):
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Focus on assigning string 'Italy' to country."}}]
        }
        mock_response.raise_for_status = lambda: None

        with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
            res = await p.tutor(sample_request)
            assert "Italy" in res


@pytest.mark.asyncio
async def test_anthropic_provider_tutor_success(sample_request):
    p = AnthropicProvider()
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [{"text": "Try setting country = 'Italy'."}]
        }
        mock_response.raise_for_status = lambda: None

        with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
            res = await p.tutor(sample_request)
            assert "Italy" in res


@pytest.mark.asyncio
async def test_gemini_provider_tutor_success(sample_request):
    p = GeminiProvider()
    with patch.dict(os.environ, {"GEMINI_API_KEY": "gemini-test-key"}):
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Set the country variable."}]}}]
        }
        mock_response.raise_for_status = lambda: None

        with patch.object(httpx.AsyncClient, "post", return_value=mock_response):
            res = await p.tutor(sample_request)
            assert "Set the country variable" in res
