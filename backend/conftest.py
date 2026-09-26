"""Keep automated runs off the learner's real runtime state.

`backend.main` builds its stores at import time, so any test that does
`import backend.main` gets the production progression files, the heart pool,
the leaderboard, the feedback log and the guided-project store. Before this
fixture those runs wrote straight into the working copy: a single pytest pass
left ~190 throwaway "Word Frequency Counter" projects in
``curriculum/generated/projects/`` (which the UI lists as resumable courses)
and bumped XP/hearts in the real state files.

Setting the env vars *here* — before any test module is imported — makes
``backend.main`` resolve every writable path into a throwaway directory
instead. Tests that want to assert on persistence still get it; they just get
it in isolation (see ``test_leaderboard.py`` for the explicit-constructors
variant).
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_RUN_DIR = Path(tempfile.mkdtemp(prefix="patchwork_test_state_"))

os.environ.setdefault("PATCHWORK_STATE_DIR", str(_RUN_DIR))
os.environ.setdefault("PATCHWORK_PROJECT_DIR", str(_RUN_DIR / "projects"))


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001
    shutil.rmtree(_RUN_DIR, ignore_errors=True)


# ─── Never let tests write the real .env or the real encrypted key store ────────
# Settings endpoints persist models via backend.env.upsert_env_var (project .env)
# and keys via backend.api_key_manager (~/.config/patchwork-tutor). Earlier runs of
# test_api_settings.py rewrote the learner's OPENROUTER_MODEL, appended OPENAI_MODEL
# and could delete a real saved OpenAI key. Redirect both, per test, and restore
# os.environ afterwards.
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_env_file_and_key_store(tmp_path, monkeypatch):
    saved_environ = dict(os.environ)
    fake_env = tmp_path / ".env"
    fake_env.write_text("", encoding="utf-8")
    try:
        from backend import env as env_mod

        monkeypatch.setattr(env_mod, "_env_path", lambda: fake_env)
    except Exception:  # noqa: BLE001 — module may not exist in trimmed checkouts
        pass
    try:
        from backend import api_key_manager as akm

        key_dir = tmp_path / "patchwork-tutor"
        monkeypatch.setattr(akm, "_CONFIG_DIR", key_dir)
        monkeypatch.setattr(akm, "_ENC_KEYS_FILE", key_dir / "keys.enc")
        monkeypatch.setattr(akm, "_KEY_FILE", key_dir / ".master.key")
    except Exception:  # noqa: BLE001
        pass
    yield
    os.environ.clear()
    os.environ.update(saved_environ)
