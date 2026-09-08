import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch

from backend.main import app
from backend.api_settings import ApiKeyValidationResult


@pytest.mark.asyncio
async def test_get_settings_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/settings")
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert "current_provider" in data
        providers = {p["id"]: p for p in data["providers"]}
        assert "ollama" in providers
        assert "openai" in providers
        assert "anthropic" in providers
        assert "openrouter" in providers
        assert "gemini" in providers


@pytest.mark.asyncio
async def test_validate_key_invalid_format():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/settings/providers/openai/validate",
            json={"api_key": "invalid-no-sk-prefix-key-that-is-short"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "error" in data


@pytest.mark.asyncio
async def test_save_and_delete_key():
    mock_val = ApiKeyValidationResult(valid=True, provider="openai", key_masked="sk-1...9012")

    with patch("backend.main.validate_provider_key", return_value=mock_val):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            valid_key = "sk-123456789012345678901234567890123456789012"
            save_res = await client.post(
                "/api/settings/providers/openai/save",
                json={"api_key": valid_key, "model": "gpt-4o-mini"}
            )
            assert save_res.status_code == 200
            save_data = save_res.json()
            assert save_data["success"] is True

            # Check settings reports key exists
            settings_res = await client.get("/api/settings/providers/openai")
            assert settings_res.status_code == 200
            assert settings_res.json()["has_key"] is True

            # Delete key
            del_res = await client.delete("/api/settings/providers/openai/key")
            assert del_res.status_code == 200
            assert del_res.json()["success"] is True

            # Check key is deleted
            settings_after = await client.get("/api/settings/providers/openai")
            assert settings_after.status_code == 200
            assert settings_after.json()["has_key"] is False
