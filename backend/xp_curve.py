"""One XP/level curve for the whole app.

The frontend grew a progressive curve (``60 + 40 * (n - 1)`` per level) while
the backend kept a flat ``xp // 100 + 1``. Two learners with identical XP could
therefore be shown different levels depending on which endpoint answered, and
the level a learner saw could change when they refreshed.

``src/utils/gamification.ts`` keeps its own copy for optimistic rendering;
``backend/test_xp_curve.py`` pins the two together.
"""

from __future__ import annotations

XP_LEVEL_ONE = 0
BASE_LEVEL_STEP = 60
LEVEL_STEP_GROWTH = 40


def xp_for_level(level: int) -> int:
    """Total XP needed to reach `level`. Level 1 is always free."""
    if level <= 1:
        return XP_LEVEL_ONE
    total = 0
    for step in range(1, level):
        total += BASE_LEVEL_STEP + LEVEL_STEP_GROWTH * (step - 1)
    return total


def level_from_xp(xp: int) -> int:
    level = 1
    while xp >= xp_for_level(level + 1):
        level += 1
    return level


def xp_into_level(xp: int) -> dict[str, int]:
    """Progress within the current level, for the level ring in the UI."""
    level = level_from_xp(xp)
    base = xp_for_level(level)
    nxt = xp_for_level(level + 1)
    return {
        "level": level,
        "current": max(0, xp - base),
        "needed": max(1, nxt - base),
    }
