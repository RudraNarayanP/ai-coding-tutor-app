"""A test run must never touch the learner's real runtime state.

Regression guard for the state-isolation fix. Before ``backend/conftest.py``
existed, importing ``backend.main`` inside pytest bound the production stores,
so a single suite pass wrote ~190 throwaway guided projects into
``curriculum/generated/projects/`` and mutated the real progression, heart pool
and leaderboard files.
"""
from __future__ import annotations

import json
from pathlib import Path

import backend.main as main_module

REPO_ROOT = Path(__file__).resolve().parent.parent


def _repo_state_is_untouched() -> bool:
    """The live project dir is the default when no override is configured."""
    default_dir = REPO_ROOT / "curriculum" / "generated" / "projects"
    return main_module.project_store.storage_dir.resolve() != default_dir


def test_env_path_helper_prefers_the_override(monkeypatch):
    monkeypatch.setenv("PW_TEST_DIR", "/custom/place")
    assert main_module._env_path("PW_TEST_DIR", Path("/fallback")) == Path("/custom/place")

    monkeypatch.setenv("PW_TEST_DIR", "   ")
    assert main_module._env_path("PW_TEST_DIR", Path("/fallback")) == Path("/fallback")

    monkeypatch.delenv("PW_TEST_DIR", raising=False)
    assert main_module._env_path("PW_TEST_DIR", Path("/fallback")) == Path("/fallback")


def test_project_store_is_redirected_away_from_the_repo():
    assert _repo_state_is_untouched(), (
        "Guided projects are being written into the live store during tests — "
        "backend/conftest.py stopped isolating PATCHWORK_PROJECT_DIR."
    )


def test_writable_state_files_all_live_outside_the_repo():
    paths = [
        main_module.user_store.storage_path,
        main_module.heart_store.storage_path,
        main_module.feedback_store.storage_path,
    ] + [store.storage_path for store in main_module.lesson_engine.stores.values()]
    for path in paths:
        assert path is not None
        resolved = Path(path).resolve()
        assert REPO_ROOT not in resolved.parents and resolved != REPO_ROOT, (
            f"{Path(path).name} still points inside the working tree ({resolved}); "
            "a test run would overwrite real learner state."
        )


def test_isolated_store_persists_within_a_run(tmp_path):
    """Isolation must not cost durability: the same dir still round-trips state."""
    from backend.hearts import HeartStore

    target = tmp_path / "hearts.json"
    store = HeartStore(storage_path=target)
    store.consume()
    assert store.status().hearts == 4
    assert json.loads(target.read_text(encoding="utf-8"))["hearts"] == 4
    assert HeartStore(storage_path=target).status().hearts == 4
