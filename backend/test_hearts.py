"""Tests for the server-authoritative heart pool."""

import time

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
def hearts(tmp_path, clock):
    return HeartStore(storage_path=tmp_path / "hearts.json", clock=clock, max_hearts=5)


# ---------------------------------------------------------------------------
# Consume
# ---------------------------------------------------------------------------

def test_starts_full(hearts):
    status = hearts.status()
    assert status.hearts == 5
    assert status.max_hearts == 5
    assert status.unlimited is False


def test_consume_drops_one_heart(hearts):
    assert hearts.consume().hearts == 4


def test_consume_never_goes_below_zero(hearts):
    for _ in range(10):
        hearts.consume()
    assert hearts.status().hearts == 0
    assert hearts.can_attempt() is False


def test_full_pool_can_attempt(hearts):
    assert hearts.can_attempt() is True


# ---------------------------------------------------------------------------
# Refill
# ---------------------------------------------------------------------------

def test_no_heart_regenerates_before_the_interval(hearts, clock):
    hearts.consume()
    clock.advance(299)
    assert hearts.status().hearts == 4


def test_one_heart_regenerates_after_the_interval(hearts, clock):
    hearts.consume()
    clock.advance(300)
    assert hearts.status().hearts == 5


def test_several_hearts_regenerate_for_several_intervals(hearts, clock):
    for _ in range(3):
        hearts.consume()
    assert hearts.status().hearts == 2
    clock.advance(300 * 2 + 120)
    status = hearts.status()
    assert status.hearts == 4
    # the 120s already waited still counts toward the next heart
    assert 0 < status.seconds_to_next_heart <= 180


def test_partial_interval_is_not_reset_by_polling(hearts, clock):
    hearts.consume()
    # Poll repeatedly inside the first interval: none of these reads may
    # restart the countdown, or a learner who checks often never refills.
    for _ in range(10):
        clock.advance(20)
        assert hearts.status().hearts == 4
    assert hearts.status().seconds_to_next_heart > 0
    clock.advance(100)
    assert hearts.status().hearts == 5


def test_regeneration_stops_at_the_maximum(hearts, clock):
    hearts.consume()
    clock.advance(300 * 50)
    assert hearts.status().hearts == 5


def test_full_pool_reports_no_wait(hearts):
    assert hearts.status().seconds_to_next_heart == 0


def test_refill_restores_the_pool(hearts):
    for _ in range(4):
        hearts.consume()
    assert hearts.refill().hearts == 5


# ---------------------------------------------------------------------------
# Refund
# ---------------------------------------------------------------------------

def test_refund_returns_one_heart(hearts):
    hearts.consume()
    assert hearts.refund().hearts == 5


def test_refund_is_capped_at_the_maximum(hearts):
    assert hearts.refund(3).hearts == 5


def test_refund_when_full_does_not_steal_the_pending_interval(hearts, clock):
    hearts.refund()
    clock.advance(299)
    hearts.consume()
    assert hearts.status().hearts == 4


# ---------------------------------------------------------------------------
# Unlimited and max
# ---------------------------------------------------------------------------

def test_unlimited_never_consumes(hearts):
    hearts.set_unlimited(True)
    for _ in range(8):
        hearts.consume()
    assert hearts.status().hearts == 5
    assert hearts.can_attempt() is True


def test_turning_unlimited_off_keeps_the_pool_full(hearts):
    hearts.set_unlimited(True)
    status = hearts.set_unlimited(False)
    assert status.unlimited is False
    assert status.hearts == 5


def test_max_hearts_is_clamped_to_a_sane_range(hearts):
    assert hearts.set_max(99).max_hearts == 10
    assert hearts.set_max(0).max_hearts == 1


def test_lowering_the_maximum_caps_the_current_pool(hearts):
    hearts.set_max(2)
    assert hearts.status().hearts == 2


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_pool_survives_a_restart(tmp_path, clock):
    path = tmp_path / "hearts.json"
    first = HeartStore(storage_path=path, clock=clock, max_hearts=5)
    first.consume()
    first.consume()
    second = HeartStore(storage_path=path, clock=clock)
    assert second.status().hearts == 3


def test_regeneration_catches_up_on_time_spent_offline(tmp_path):
    clock = FakeClock()
    path = tmp_path / "hearts.json"
    first = HeartStore(storage_path=path, clock=clock, max_hearts=5)
    for _ in range(4):
        first.consume()
    clock.advance(300 * 4)
    restarted = HeartStore(storage_path=path, clock=clock)
    assert restarted.status().hearts == 5


def test_a_corrupt_file_falls_back_to_a_full_pool(tmp_path):
    path = tmp_path / "hearts.json"
    path.write_text("{not json", encoding="utf-8")
    store = HeartStore(storage_path=path, max_hearts=5)
    assert store.status().hearts == 5


def test_no_storage_path_still_works_in_memory():
    store = HeartStore(storage_path=None, max_hearts=3)
    assert store.consume().hearts == 2


def test_status_is_json_serialisable(hearts):
    import json

    json.dumps(hearts.status().as_dict())


def test_time_based_regen_uses_the_injected_clock_not_wall_clock(tmp_path):
    clock = FakeClock()
    store = HeartStore(storage_path=tmp_path / "h.json", clock=clock, max_hearts=5)
    store.consume()
    clock.advance(300)
    assert store.status().hearts == 5
    assert time.time() > 0
