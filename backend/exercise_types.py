"""Single source of truth for exercise types.

Backend validation, backend grading and the frontend widget router all have to
agree on which exercise types exist. They used to keep three separate lists,
and the gaps between them were silent: ``short_answer`` was graded but had no
frontend list entry, ``validate_curriculum`` had no ``else`` branch so an
unknown type passed validation without complaint, and ``grade_exercise``
returned ``True`` for any type it did not recognise with no answer key.

Every set here is mirrored in ``src/utils/exerciseTypes.ts``;
``backend/test_exercise_types.py`` pins the two together.
"""

from __future__ import annotations

# Tap-a-choice types: graded by comparing a single submitted ``answer``.
CHOICE_TYPES = frozenset(
    {"mcq", "true_false", "output_prediction", "debugging", "identify_error", "short_answer"}
)
# Tap-several: submitted as ``answers`` and compared as a set.
MULTI_SELECT_TYPES = frozenset({"select_multiple"})
# Drag/tap into sequence: submitted as ``order``.
ORDERING_TYPES = frozenset({"ordering"})
# Pair matching: submitted as ``pairs``.
MATCHING_TYPES = frozenset({"matching"})
# Type-the-missing-token: submitted as ``answers`` aligned to the blank sites.
FILL_TYPES = frozenset({"fill_blank", "code_completion"})
# Write code in the editor and run it through the sandbox.
CODE_TYPES = frozenset({"code", "tiny_coding", "identify_mistake"})

ALL_TYPES = (
    CHOICE_TYPES
    | MULTI_SELECT_TYPES
    | ORDERING_TYPES
    | MATCHING_TYPES
    | FILL_TYPES
    | CODE_TYPES
)

# Types where an empty/absent ``correct_answer`` means the item cannot be
# graded, so it must fail loudly rather than wave the learner through.
ANSWER_REQUIRED_TYPES = CHOICE_TYPES | MULTI_SELECT_TYPES | ORDERING_TYPES | MATCHING_TYPES | FILL_TYPES

# Open-ended types that legitimately accept any non-empty submission when no
# tests or reference solution exist.
OPEN_ENDED_TYPES = CODE_TYPES


def normalise_type(raw: object) -> str:
    return str(raw or "").lower().strip()


def is_known(raw: object) -> bool:
    return normalise_type(raw) in ALL_TYPES


def widget_for(raw: object) -> str:
    """Which frontend widget renders the input for this type."""
    ex_type = normalise_type(raw)
    if ex_type in CHOICE_TYPES:
        return "choice"
    if ex_type in MULTI_SELECT_TYPES:
        return "multi_select"
    if ex_type in ORDERING_TYPES:
        return "ordering"
    if ex_type in MATCHING_TYPES:
        return "matching"
    if ex_type in FILL_TYPES:
        return "fill"
    if ex_type in CODE_TYPES:
        return "code"
    return "unknown"


def requires_answer_key(raw: object) -> bool:
    return normalise_type(raw) in ANSWER_REQUIRED_TYPES


def is_open_ended(raw: object) -> bool:
    return normalise_type(raw) in OPEN_ENDED_TYPES


def ungradeable_feedback(exercise_type: str, reason: str) -> str:
    """Feedback for an item the server cannot score.

    Grading an unknown or answer-less exercise as correct teaches the learner
    nothing and hides an authoring bug, so the message names the problem.
    """
    return (
        f"This step could not be scored ({reason}; type {exercise_type!r}). "
        "Please report it so the exercise can be fixed."
    )
