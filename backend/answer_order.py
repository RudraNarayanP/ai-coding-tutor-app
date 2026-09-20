"""Mirror of the client's deterministic option order, for authoring gates.

``src/components/ExerciseAnswerInput.tsx`` reorders options with an FNV-1a hash
of the exercise id so the correct choice is not always the first button. The
browser never receives ``correct_answer``, so only the curriculum can guarantee
that the shuffled result does not put the key first - and for a given item id
the hash is fixed, which means some stored orderings *do* land the key in slot
one. Wave 3 measurement caught exactly that: ``big-o-step-1-out-1`` was passable
by tapping the leftmost option, purely by hash luck.

This module is the Python side of that contract. To keep the two sides from
drifting silently, ``audit/answer_order_fixture.json`` pins id/option lists to
their expected display order, and both test suites assert against it:
``backend/test_answer_order.py`` (this code) and
``src/components/ExerciseAnswerInput.test.tsx`` (the real function).

If the client's algorithm changes, the fixture test here fails on purpose.
"""
from __future__ import annotations

import json
from itertools import permutations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = ROOT / "fixtures" / "answer_order.json"

_OPTIONS = 3          # the client leaves lists shorter than this untouched


def _utf16_units(text: str) -> list[int]:
    """UTF-16 code units, matching JavaScript's `charCodeAt`."""
    raw = text.encode("utf-16-le")
    return [int.from_bytes(raw[i:i + 2], "little") for i in range(0, len(raw), 2)]


def _imul(left: int, right: int) -> int:
    """JavaScript's `Math.imul`: a 32-bit signed multiply."""
    result = (left * right) & 0xFFFFFFFF
    return result - (1 << 32) if result >= (1 << 31) else result


def hash_string(text: str) -> int:
    """`hashString` in ExerciseAnswerInput.tsx (FNV-1a, unsigned 32-bit)."""
    h = 2166136261
    for unit in _utf16_units(text):
        h = _imul(h ^ unit, 16777619)
    return h & 0xFFFFFFFF


def displayed_options(exercise_id: str, options: list[str]) -> list[str]:
    """The order a learner actually sees."""
    if len(options) < _OPTIONS:
        return list(options)
    seed = hash_string(str(exercise_id or ""))
    keyed = [(hash_string(f"{seed}:{index}:{option}"), index, option)
             for index, option in enumerate(options)]
    return [option for _, _, option in sorted(keyed, key=lambda entry: entry[0])]


def key_shown_first(exercise_id: str, options: list[str], answer: str) -> bool:
    """True when the leftmost button is the right answer."""
    shown = displayed_options(exercise_id, options)
    return bool(shown) and shown[0] == answer


def reorder_so_key_is_not_first(exercise_id: str, options: list[str],
                                answer: str) -> list[str]:
    """Reorder the stored options until the displayed first slot is not the key.

    Grading matches options by value, so changing the stored order cannot alter
    difficulty - only which button the client paints first.

    The search is every permutation of the list, tried in a stable order
    (closest to the original arrangement first). An earlier version only tried
    rotations of the non-answer items, which looked exhaustive and was not: it
    left one item with the key still in the first rendered slot, and the gate
    caught it. Small option counts make the full search cheap.
    """
    if answer not in options or not key_shown_first(exercise_id, options, answer):
        return list(options)

    original = list(options)
    for candidate in sorted(
        (list(permutation) for permutation in permutations(original)),
        key=lambda arrangement: ([original.index(o) for o in arrangement]),
    ):
        if not key_shown_first(exercise_id, candidate, answer):
            return candidate
    return original


def load_fixture() -> list[dict]:
    if not FIXTURE_PATH.exists():
        return []
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def write_fixture(cases: list[dict]) -> Path:
    FIXTURE_PATH.parent.mkdir(exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(cases, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    return FIXTURE_PATH
