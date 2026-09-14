"""Per-learner exercise feedback store (Duolingo-style tutoring adaptation).

Learners can rate any graded exercise as ``too_easy`` / ``too_difficult`` or
file a ``report``. The aggregated signal steers the AI tutor on the go: when
a learner keeps saying exercises are too hard, hints become more explicit and
broken into smaller steps; when everything feels too easy, the tutor gets more
concise and offers stretch goals.

Persisted as JSON next to the other progression stores so the adaptation
survives restarts.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger("patchwork.feedback")

VALID_RATINGS = ("too_easy", "too_difficult", "report")

# Recent feedback weighs more than stale feedback.
RECENT_WINDOW = 10


class FeedbackStore:
    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path
        self._lock = threading.Lock()
        # user_id -> list of feedback records (chronological)
        self._records: dict[str, list[dict]] = {}
        self._load()

    # ─── Persistence ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if self.storage_path and self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for user_id, records in data.items():
                        if isinstance(records, list):
                            self._records[str(user_id)] = [r for r in records if isinstance(r, dict)]
            except Exception as exc:
                logger.warning("FeedbackStore load error: %s", exc)

    def _save(self) -> None:
        if self.storage_path:
            try:
                with self._lock:
                    payload = {user_id: records[-200:] for user_id, records in self._records.items()}
                self.storage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            except Exception as exc:
                logger.warning("FeedbackStore save error: %s", exc)

    # ─── Recording ────────────────────────────────────────────────────────

    def record(
        self,
        user_id: str,
        exercise_id: str,
        rating: str,
        lesson_id: str | None = None,
        comment: str | None = None,
    ) -> dict:
        """Store one feedback event. Latest rating per exercise wins."""
        rating = (rating or "").strip().lower()
        if rating not in VALID_RATINGS:
            raise ValueError(f"Invalid rating: {rating!r}. Expected one of {VALID_RATINGS}.")

        user_id = (user_id or "default_user").strip() or "default_user"
        record = {
            "exercise_id": (exercise_id or "").strip(),
            "lesson_id": (lesson_id or "").strip() or None,
            "rating": rating,
            "comment": (comment or "").strip()[:2000] or None,
            "ts": time.time(),
        }
        with self._lock:
            records = self._records.setdefault(user_id, [])
            # One active rating per exercise: drop older entries for the same exercise+rating kind.
            records[:] = [r for r in records if not (r.get("exercise_id") == record["exercise_id"] and r.get("rating") == rating)]
            records.append(record)
            del records[:-200]
        self._save()
        return record

    # ─── Adaptation signal ────────────────────────────────────────────────

    def summary(self, user_id: str) -> dict:
        """Aggregate counts + derived difficulty bias for a learner."""
        user_id = (user_id or "default_user").strip() or "default_user"
        with self._lock:
            records = list(self._records.get(user_id, []))
        recent = records[-RECENT_WINDOW:]
        easy = sum(1 for r in recent if r.get("rating") == "too_easy")
        hard = sum(1 for r in recent if r.get("rating") == "too_difficult")
        reports = sum(1 for r in records if r.get("rating") == "report")

        if hard - easy >= 2:
            bias = "harder"
        elif easy - hard >= 2:
            bias = "easier"
        else:
            bias = "balanced"
        return {
            "user_id": user_id,
            "bias": bias,
            "too_easy": easy,
            "too_difficult": hard,
            "reports": reports,
            "total": len(records),
        }

    def adaptation_hint(self, user_id: str) -> str:
        """Prompt-ready instruction steering the tutor from live feedback."""
        data = self.summary(user_id)
        bias = data["bias"]
        reports = data["reports"]
        parts: list[str] = []
        if bias == "harder":
            parts.append(
                "Learner feedback signal: recent exercises feel TOO DIFFICULT. "
                "Slow down: use smaller steps, define any jargon before using it, "
                "and check understanding of one idea before introducing the next."
            )
        elif bias == "easier":
            parts.append(
                "Learner feedback signal: recent exercises feel TOO EASY. "
                "Be concise, skip elementary explanations, and offer a stretch "
                "challenge or edge case when natural."
            )
        if reports > 0:
            parts.append(
                f"Note: the learner has reported {reports} exercise(s) as problematic. "
                "Be extra careful: acknowledge the material itself might be confusing "
                "and clarify it rather than assuming learner error."
            )
        return " ".join(parts)

    def adaptation_ack(self, user_id: str, rating: str) -> str:
        """Human-facing confirmation returned right after a rating is saved."""
        data = self.summary(user_id)
        if rating == "report":
            return "Thanks — your report was saved and the tutor will be extra careful with this material."
        if data["bias"] == "harder":
            return "Noted! I'll slow down with smaller steps and clearer explanations."
        if data["bias"] == "easier":
            return "Noted! I'll keep things snappy and throw in stretch challenges."
        if rating == "too_easy":
            return "Noted — glad this felt easy! I'll keep the pace up."
        return "Noted — I'll adjust and give you more support on the next ones."
