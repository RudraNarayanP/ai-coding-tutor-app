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
