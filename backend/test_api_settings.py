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


@pytest.mark.asyncio
async def test_save_provider_model_persists(tmp_path, monkeypatch):
    """Model-only save updates os.environ and is returned by settings."""
    import os
    from backend import env as env_mod
    from backend.api_settings import update_provider_model

    fake_env = tmp_path / ".env"
    fake_env.write_text("OPENROUTER_MODEL=cohere/north-mini-code:free\n", encoding="utf-8")
    monkeypatch.setattr(env_mod, "_env_path", lambda: fake_env)

    model_id = update_provider_model("openrouter", "nvidia/nemotron-3-super-120b-a12b:free")
    assert model_id == "nvidia/nemotron-3-super-120b-a12b:free"
    assert os.environ.get("OPENROUTER_MODEL") == "nvidia/nemotron-3-super-120b-a12b:free"
    assert "nvidia/nemotron-3-super-120b-a12b:free" in fake_env.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_save_provider_model_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/settings/providers/openrouter/model",
            json={"model": "nvidia/nemotron-3-super-120b-a12b:free"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["model"] == "nvidia/nemotron-3-super-120b-a12b:free"
        assert data["paid"] is False

        settings = await client.get("/api/settings")
        assert settings.status_code == 200
        body = settings.json()
        assert body.get("openrouter_model_presets")
        assert any(p["id"].startswith("nvidia/nemotron") for p in body["openrouter_model_presets"])
        openrouter = next(p for p in body["providers"] if p["id"] == "openrouter")
        assert openrouter["model"] == "nvidia/nemotron-3-super-120b-a12b:free"


def test_create_course_system_prompt_bans_video_phrases():
    from backend.ai_course_generator import _SYSTEM

    assert "NEVER watched the video" in _SYSTEM or "never watched" in _SYSTEM.lower()
    assert "as in the video" in _SYSTEM
    assert "keyword-only" in _SYSTEM.lower() or "keyword-only" in _SYSTEM or "FORBID keyword" in _SYSTEM
