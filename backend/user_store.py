import json
import time
from pathlib import Path
from pydantic import BaseModel, Field


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
    is_demo: bool
    is_current_user: bool = False


class UserStore:
    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path
        self._users: dict[str, UserProfile] = {}
        self._load()

    def _load(self) -> None:
        if self.storage_path and self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                for item in data:
                    u = UserProfile(**item)
                    self._users[u.user_id] = u
            except Exception:
                pass

        if not self._users:
            self._seed_default_users()

    def _seed_default_users(self) -> None:
        default_user = UserProfile(
            user_id="default_user",
            username="Patchwork Learner",
            xp=0,
            level=1,
            streak=1,
            is_demo=False,
        )
        self._users[default_user.user_id] = default_user

        seed_demos = [
            ("demo_alex", "[Demo] Alex", 180, 2),
            ("demo_sam", "[Demo] Sam", 120, 2),
            ("demo_jordan", "[Demo] Jordan", 60, 1),
            ("demo_taylor", "[Demo] Taylor", 30, 1),
        ]
        for uid, name, xp, level in seed_demos:
            self._users[uid] = UserProfile(
                user_id=uid,
                username=name,
                xp=xp,
                level=level,
                streak=1,
                is_demo=True,
            )
        self._save()

    def _save(self) -> None:
        if self.storage_path:
            try:
                payload = [u.model_dump() for u in self._users.values()]
                self.storage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            except Exception:
                pass

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
            username=username or f"Learner_{user_id[:6]}",
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
            user.level = max(1, user.xp // 100 + 1)
            user.last_active = time.time()
            self._save()
        return user

    def set_user_xp(self, user_id: str, total_xp: int) -> UserProfile:
        user = self.get_or_create_user(user_id)
        user.xp = max(0, total_xp)
        user.level = max(1, user.xp // 100 + 1)
        user.last_active = time.time()
        self._save()
        return user

    def update_profile(self, user_id: str, username: str | None = None, streak: int | None = None) -> UserProfile:
        user = self.get_or_create_user(user_id)
        if username:
            user.username = username
        if streak is not None:
            user.streak = max(1, streak)
        user.last_active = time.time()
        self._save()
        return user

    def get_leaderboard(self, current_user_id: str = "default_user") -> list[LeaderboardEntry]:
        sorted_users = sorted(
            self._users.values(),
            key=lambda u: (-u.xp, u.username.lower())
        )
        entries = []
        for idx, u in enumerate(sorted_users, start=1):
            entries.append(
                LeaderboardEntry(
                    rank=idx,
                    user_id=u.user_id,
                    username=u.username,
                    xp=u.xp,
                    level=u.level,
                    streak=u.streak,
                    is_demo=u.is_demo,
                    is_current_user=(u.user_id == current_user_id),
                )
            )
        return entries
