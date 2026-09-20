"""Apply step: write verified ordering candidates into the curriculum JSON.

Kept separate from the search so a candidate can never be persisted without
having passed the execution proof in `generate_ordering_exercises`.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

CURRICULUM_ROOT = Path(__file__).resolve().parent.parent / "curriculum"

# Balanced spread beats a pile-up in whichever language happens to have the
# most multi-statement solutions.
MAX_PER_COURSE = 8
ORDERING_XP = 10


def signature(units: list[str]) -> str:
    """A shape fingerprint: identifiers and literals removed.

    Two lessons whose solutions differ only in variable names would produce
    the same exercise twice, so they collapse to one signature.
    """
    normalised = []
    for unit in units:
        text = re.sub(r"'[^']*'|\"[^\"]*\"", "@", unit)
        text = re.sub(r"\b\d+(?:\.\d+)?\b", "#", text)
        text = re.sub(r"[A-Za-z_][A-Za-z0-9_]*", "v", text)
        normalised.append(re.sub(r"\s+", " ", text).strip())
    return hashlib.sha256("||".join(normalised).encode()).hexdigest()[:16]


def presentation_order(units: list[str], lesson_id: str) -> list[str]:
    """A deterministic order that is never the solution order.

    The options list is what the learner sees before they answer, so leaving it
    in canonical order would hand them the answer. Rotating by a hash keeps it
    stable across renders without ever matching the key.
    """
    if len(units) < 2:
        return list(units)
    seed = int(hashlib.sha256(lesson_id.encode()).hexdigest(), 16)
    for offset in range(1, len(units) + 1):
        shift = (seed + offset) % len(units)
        candidate = units[shift:] + units[:shift]
        if candidate != units:
            return candidate
    return list(reversed(units))


def build_exercise(lesson: dict[str, Any], units: list[str], prompt: str, explanation: str) -> dict:
    lesson_id = str(lesson.get("id"))
    return {
        "id": f"{lesson_id}-order-1",
        "type": "ordering",
        "question": prompt,
        "options": presentation_order(units, lesson_id),
        "correct_answer": list(units),
        "explanation": explanation,
        "xp_reward": ORDERING_XP,
    }


def build_sublesson(exercise: dict, position: int) -> dict:
    return {
        "id": f"{exercise['id']}-sub",
        "title": "Order the steps",
        "order": position,
        "exercises": [exercise],
    }


def insert_sublesson(path: Path, lesson_id: str, sublesson: dict) -> bool:
    """Attach one sublesson to a lesson, preserving all other content."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    for lesson in payload.get("lessons") or []:
        if lesson.get("id") != lesson_id:
            continue
        existing = lesson.get("sublessons") or []
        if any(sub.get("id") == sublesson["id"] for sub in existing):
            return False
        lesson["sublessons"] = [*existing, sublesson]
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return True
    return False
