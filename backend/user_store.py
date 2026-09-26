import logging
import json
import os
import threading
import time
from pathlib import Path
from pydantic import BaseModel, Field
from .xp_curve import level_from_xp

logger = logging.getLogger("patchwork.user_store")


class UserProfile(BaseModel):
    user_id: str
    username: str
    xp: int = 0
    level: int = 1
    streak: int = 1
    is_demo: bool = False
    created_at: float = Field(default_factory=time.time)
    last_active: float = Field(default_factory=time.time)


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    username: str
    xp: int
    level: int
    streak: int
    is_demo: bool = False
    is_current_user: bool = False


class UserStore:
    """Persistent shared store of real learner profiles for the live leaderboard.

    Empty is intentional: ranks appear only when real learners earn XP or set a
    display name. Demo / seeded fake names are never created and are purged if
    found in an older state file.
    """

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path
        self._users: dict[str, UserProfile] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if self.storage_path and self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                for item in data:
                    u = UserProfile(**item)
                    self._users[u.user_id] = u
            except Exception as exc:
                logger.warning("UserStore error: %s", exc)

        # Drop any leftover demo / fake seed rows from older builds.
        demos = [uid for uid, u in self._users.items() if u.is_demo or uid.startswith("demo_")]
        if demos:
            for uid in demos:
                del self._users[uid]
            self._save()

    def _save(self) -> None:
        if not self.storage_path:
            return
        with self._lock:
            payload = [u.model_dump() for u in self._users.values()]
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            # Compact JSON + atomic replace: smaller/faster than indent=2 rewrite.
            raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
            tmp = self.storage_path.with_suffix(".tmp_" + str(os.getpid()) + "_" + str(id(self)))
            tmp.write_text(raw, encoding="utf-8")
            tmp.replace(self.storage_path)
        except Exception as exc:
            logger.warning("UserStore error: %s", exc)

    def get_or_create_user(self, user_id: str, username: str | None = None) -> UserProfile:
        if user_id in self._users:
            user = self._users[user_id]
            if username and user.username != username:
                user.username = username
                user.last_active = time.time()
                self._save()
            return user

        new_user = UserProfile(
            user_id=user_id,
            username=username or f"Learner_{user_id[:8]}",
            xp=0,
            level=1,
            streak=1,
            is_demo=False,
        )
        self._users[user_id] = new_user
        self._save()
        return new_user

    def update_user_xp(self, user_id: str, xp_amount: int) -> UserProfile:
        user = self.get_or_create_user(user_id)
        if xp_amount > 0:
            user.xp += xp_amount
            user.level = level_from_xp(user.xp)
            user.last_active = time.time()
            self._save()
        return user

    def set_user_xp(self, user_id: str, total_xp: int) -> UserProfile:
        user = self.get_or_create_user(user_id)
        user.xp = max(0, total_xp)
        user.level = level_from_xp(user.xp)
        user.last_active = time.time()
        self._save()
        return user

    def update_profile(self, user_id: str, username: str | None = None, streak: int | None = None) -> UserProfile:
        user = self.get_or_create_user(user_id)
        if username:
            user.username = username.strip() or user.username
        if streak is not None:
            user.streak = max(1, streak)
        user.last_active = time.time()
        self._save()
        return user

    def get_leaderboard(self, current_user_id: str = "default_user") -> list[LeaderboardEntry]:
        """Rank real learners only (highest XP first). Empty list when nobody has joined."""
        real_users = [u for u in self._users.values() if not u.is_demo and not u.user_id.startswith("demo_")]
        sorted_users = sorted(
            real_users,
            key=lambda u: (-u.xp, u.username.lower(), u.user_id),
        )
        entries: list[LeaderboardEntry] = []
        for idx, u in enumerate(sorted_users, start=1):
            entries.append(
                LeaderboardEntry(
                    rank=idx,
                    user_id=u.user_id,
                    username=u.username,
                    xp=u.xp,
                    level=u.level,
                    streak=u.streak,
                    is_demo=False,
                    is_current_user=(u.user_id == current_user_id),
                )
            )
        return entries
