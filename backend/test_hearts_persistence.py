"""Reading the heart pool must not dirty the learner's state file.

`GET /api/hearts` is polled on mount, on tab change and after every submit, so
``status()`` used to rewrite ``hearts_state.json`` on each poll just to move
``last_regen_at``. That made a read look like a write in git status and in any
"did this run touch real state?" check. These tests pin the read-only property
without weakening the regeneration math it must not break.
"""
from __future__ import annotations

import json

import pytest

from backend.hearts import HeartStore


class FakeClock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture()
def clock():
    return FakeClock()


@pytest.fixture()
def path(tmp_path):
    return tmp_path / "hearts.json"


def _poll_until_quiet(store: HeartStore, rounds: int = 3) -> None:
    for _ in range(rounds):
        store.status()


def test_status_on_a_full_pool_never_touches_the_file(path, clock):
    store = HeartStore(storage_path=path, clock=clock)
    store.refill()
    _poll_until_quiet(store)
    before = path.read_bytes()

    clock.advance(3600)          # plenty of elapsed time, but nothing to credit
    for _ in range(20):
        assert store.status().hearts == 5

    assert path.read_bytes() == before, "a poll rewrote state that had no change to make"


def _hearts_on_disk(path):
    return json.loads(path.read_text(encoding="utf-8"))["hearts"]


def test_status_still_persists_a_real_regeneration(path, clock):
    store = HeartStore(storage_path=path, clock=clock)
    store.consume()
    assert _hearts_on_disk(path) == 4

    clock.advance(300)
    assert store.status().hearts == 5
    assert _hearts_on_disk(path) == 5, "crediting a heart must be durable, not in-memory only"


def test_partial_progress_survives_polling_and_is_only_written_when_it_earns(path, clock):
    store = HeartStore(storage_path=path, clock=clock)
    store.consume()
    clock.advance(180)
    store.status()                       # poll mid-interval
    before = path.read_bytes()

    for step in (10, 10, 10):
        clock.advance(step)
        store.status()
    assert path.read_bytes() == before, "polling below the interval dirtied the file"

    clock.advance(300 - 180 - 30)        # crosses the interval: now a write is right
    assert store.status().hearts == 5
    assert path.read_bytes() != before


def test_a_stale_full_pool_starts_a_clean_countdown_when_a_heart_is_lost(path, clock):
    """The removed "refresh the clock while full" line must not be missed."""
    store = HeartStore(storage_path=path, clock=clock)
    store.refill()
    clock.advance(86_400)                # last_regen_at is now a day old
    assert store.status().seconds_to_next_heart == 0

    status = store.consume()
    assert status.hearts == 4
    assert status.seconds_to_next_heart == 300, (
        "losing a heart from a full pool must start a fresh interval, not inherit a stale clock"
    )


def test_restart_after_polling_only_restores_what_was_earned(path, clock):
    store = HeartStore(storage_path=path, clock=clock)
    store.consume()
    clock.advance(120)
    for _ in range(5):
        store.status()

    reloaded = HeartStore(storage_path=path, clock=clock)
    assert reloaded.status().hearts == 4
    assert 0 < reloaded.status().seconds_to_next_heart <= 180
