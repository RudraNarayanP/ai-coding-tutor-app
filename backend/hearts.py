"""Server-authoritative hearts.

Hearts used to live only in ``localStorage``, which meant they were decorative:
nothing blocked a submission at zero, the out-of-hearts modal was unreachable
code, and clearing them was a one-line devtools edit. Moving the pool to the
server makes it a real constraint while keeping it forgiving:

* one heart per wrong exercise answer, never below zero;
* a heart regenerates every ``HEART_REGEN_SECONDS`` — computed lazily from a
  timestamp, so it works whether or not the app is open, and leftover partial
  progress is not thrown away;
* clearing an exercise from the mistake queue refunds a heart, so practising
  what you got wrong is the way *back* into the lesson path;
* reviewing queued mistakes is always allowed, even at zero hearts, so a
  learner is never locked out of the one activity that restores them;
* ``unlimited`` stays a Settings toggle, but is stored here rather than only
  in the browser.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_HEARTS = 5
HEART_REGEN_SECONDS = 300
GRADUATE_HEART_REFUND = 1

DEFAULT_PATH = Path(__file__).resolve().parent / "hearts_state.json"


@dataclass
class HeartStatus:
    hearts: int
    max_hearts: int
    unlimited: bool
    seconds_to_next_heart: int

    def as_dict(self) -> dict:
        return asdict(self)


class HeartStore:
    """A single global heart pool, persisted to disk and safe across threads."""

    def __init__(
        self,
        storage_path: Path | None = DEFAULT_PATH,
        clock=time.time,
        max_hearts: int = MAX_HEARTS,
        regen_seconds: int = HEART_REGEN_SECONDS,
    ) -> None:
        self._lock = threading.Lock()
        self.storage_path = storage_path
        self.clock = clock
        self.max_hearts = max_hearts
        self.regen_seconds = regen_seconds
        self._hearts = max_hearts
        self._unlimited = False
        self._last_regen_at = self.clock()
        self._load()

    # ------------------------------------------------------------------ state

    def _load(self) -> None:
        if not self.storage_path or not self.storage_path.exists():
            return
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        self.max_hearts = int(data.get("max_hearts", self.max_hearts))
        self._hearts = max(0, min(self.max_hearts, int(data.get("hearts", self.max_hearts))))
        self._unlimited = bool(data.get("unlimited", False))
        self._last_regen_at = float(data.get("last_regen_at", self.clock()))

    def _write_locked(self) -> None:
        if not self.storage_path:
            return
        payload = {
            "hearts": self._hearts,
            "max_hearts": self.max_hearts,
            "unlimited": self._unlimited,
            "last_regen_at": self._last_regen_at,
            "regen_seconds": self.regen_seconds,
        }
        try:
            tmp = self.storage_path.with_suffix(f".tmp_{os.getpid()}_{id(self)}")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(self.storage_path)
        except OSError:
            pass

    def _regen_locked(self, now: float) -> bool:
        """Credit whole elapsed regen intervals, keeping the remainder.

        Returns True only when persisted state actually changed, so a read can
        be proven not to dirty the file. A full pool has nothing to credit and
        no countdown to run, so its clock is deliberately left alone here:
        ``consume`` restarts it the moment a heart is lost.
        """
        if self._hearts >= self.max_hearts:
            return False
        elapsed = now - self._last_regen_at
        if elapsed < self.regen_seconds:
            return False
        earned = int(elapsed // self.regen_seconds)
        self._hearts = min(self.max_hearts, self._hearts + earned)
        # Only consume the intervals actually credited, so a partial interval
        # is not silently reset every time the client polls.
        self._last_regen_at += earned * self.regen_seconds
        if self._hearts >= self.max_hearts:
            self._last_regen_at = now
        return True

    def _status_locked(self, now: float) -> HeartStatus:
        if self._unlimited:
            return HeartStatus(self.max_hearts, self.max_hearts, True, 0)
        wait = self.regen_seconds - (now - self._last_regen_at)
        if self._hearts >= self.max_hearts:
            wait = 0
        return HeartStatus(
            hearts=self._hearts,
            max_hearts=self.max_hearts,
            unlimited=False,
            seconds_to_next_heart=max(0, int(wait)) if self._hearts < self.max_hearts else 0,
        )

    # ------------------------------------------------------------- public API

    def status(self) -> HeartStatus:
        """Read the pool. Credits any regen that has come due, and is the only
        path where a write is optional: nothing is persisted unless the credit
        changed something, so polling cannot dirty the learner's state file."""
        with self._lock:
            now = self.clock()
            if self._regen_locked(now):
                self._write_locked()
            return self._status_locked(self.clock())

    def consume(self, count: int = 1) -> HeartStatus:
        with self._lock:
            self._regen_locked(self.clock())
            if not self._unlimited:
                self._hearts = max(0, self._hearts - max(1, count))
                if self._hearts < self.max_hearts:
                    # Restart the clock only when a heart was actually lost from
                    # a full pool; otherwise the pending partial interval stays.
                    if self._hearts + count >= self.max_hearts:
                        self._last_regen_at = self.clock()
            self._write_locked()
            return self._status_locked(self.clock())

    def refund(self, count: int = GRADUATE_HEART_REFUND) -> HeartStatus:
        with self._lock:
            self._regen_locked(self.clock())
            was_full = self._hearts >= self.max_hearts
            self._hearts = min(self.max_hearts, self._hearts + max(1, count))
            if was_full and self._hearts < self.max_hearts:
                self._last_regen_at = self.clock()
            self._write_locked()
            return self._status_locked(self.clock())

    def refill(self) -> HeartStatus:
        with self._lock:
            self._hearts = self.max_hearts
            self._last_regen_at = self.clock()
            self._write_locked()
            return self._status_locked(self.clock())

    def set_unlimited(self, value: bool) -> HeartStatus:
        with self._lock:
            self._unlimited = bool(value)
            if self._unlimited:
                self._hearts = self.max_hearts
                self._last_regen_at = self.clock()
            self._write_locked()
            return self._status_locked(self.clock())

    def set_max(self, value: int) -> HeartStatus:
        with self._lock:
            self.max_hearts = max(1, min(10, int(value)))
            self._hearts = min(self._hearts, self.max_hearts)
            self._write_locked()
            return self._status_locked(self.clock())

    def can_attempt(self) -> bool:
        with self._lock:
            self._regen_locked(self.clock())
            return self._unlimited or self._hearts > 0
