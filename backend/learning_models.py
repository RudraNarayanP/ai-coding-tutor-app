"""The teaching ladder: step kinds, rungs and stakes.

This is the vocabulary the session generator and the step runner share. It is
deliberately separate from ``exercise_types.py``: that module says *how a response
is collected and graded* (a widget), this one says *why the step exists in a
lesson* (a rung of the ladder). One widget can serve several rungs — a multiple
choice card is `interact` when it introduces a quantity and `mastery` when it is
part of a mixed-skill check — and conflating the two is what turns a lesson into a
quiz.

Nothing here imports the curriculum, the store, or a clock, so the generator can be
exercised as a pure function in tests.
"""

from __future__ import annotations

from enum import Enum

SCHEMA_VERSION = "2026-09-21.1"


class Stage(str, Enum):
    """A rung of the teaching ladder, in the order a novice walks it.

    Order is the pedagogical claim: read and predict before you write, write with
    support before you write alone, then break it and use it somewhere new.
    """

    INTRODUCE = "introduce"        # state the idea, no response required
    SHOW = "show"                  # worked example, arithmetic on screen
    INTERACT = "interact"          # tiny prediction/recognition question, free
    GUIDED = "guided"              # assemble/fill, heavily supported, free
    SCAFFOLDED = "scaffolded"      # near-complete code to finish, free
    INDEPENDENT = "independent"    # write it from a signature, charged
    EXPLAIN = "explain"            # debug or describe someone else's code
    TRANSFER = "transfer"          # same idea, new surface, charged
    MASTERY = "mastery"            # mixed-skill check, no hints, charged
    REVIEW = "review"              # retrieval of something already demonstrated

    @property
    def teaches(self) -> bool:
        """Rungs whose whole job is instruction, so failing one costs nothing.

        A learner must not be charged for a first encounter: penalties on teaching
        steps suppress the attempt volume beginners need (see the research doc, and
        Duolingo's own 2025 reversal of hearts).
        """
        return self in _TEACHING_STAGES


_TEACHING_STAGES = frozenset(
    {
        Stage.INTRODUCE,
        Stage.SHOW,
        Stage.INTERACT,
        Stage.GUIDED,
        Stage.SCAFFOLDED,
        Stage.EXPLAIN,
        Stage.REVIEW,
    }
)

#: The ladder a brand-new concept walks, in order.
LADDER: tuple[Stage, ...] = (
    Stage.INTRODUCE,
    Stage.SHOW,
    Stage.INTERACT,
    Stage.GUIDED,
    Stage.SCAFFOLDED,
    Stage.INDEPENDENT,
    Stage.EXPLAIN,
    Stage.TRANSFER,
)

#: Rungs that require the learner to produce code in the editor. Two of these must
#: never be adjacent: an all-editor session is the thing the brief calls "LeetCode
#: with a dark theme".
EDITOR_STAGES = frozenset({Stage.GUIDED, Stage.SCAFFOLDED, Stage.INDEPENDENT, Stage.TRANSFER, Stage.MASTERY})

#: Evidence types that together justify calling a concept demonstrated. Guided
#: success is intentionally absent: solving with support is not the same claim as
#: solving alone (research doc §2.5, Part 29).
DEMONSTRATION_EVIDENCE = ("independent", "debugged", "transferred", "delayed_recall")

#: The evidence a passing step of each rung contributes, if any. Guided and
#: scaffolded success contribute nothing: supported solving is not a claim.
#: Lives here rather than in ``learning_service`` because the guided-project
#: ladder needs the same mapping and must not import the curriculum engine to get
#: it — two definitions of "what counts as demonstrated" is how the two surfaces
#: would drift.
EVIDENCE_FOR_STAGE: dict[Stage, str | None] = {
    Stage.INDEPENDENT: "independent",
    Stage.TRANSFER: "transferred",
    Stage.EXPLAIN: "debugged",
    Stage.MASTERY: "applied",
    Stage.REVIEW: "delayed_recall",
}

#: XP for clearing a rung by production rather than by being shown. Steps may
#: override with ``xp_reward``; teaching rungs award nothing, because reading a
#: worked example is not an accomplishment to buy.
STAGE_XP: dict[Stage, int] = {
    Stage.INDEPENDENT: 10,
    Stage.TRANSFER: 15,
    Stage.MASTERY: 20,
    Stage.EXPLAIN: 5,
    Stage.REVIEW: 5,
}


class Stakes(str, Enum):
    FREE = "free"
    CHARGED = "charged"


def default_stakes(stage: Stage) -> Stakes:
    return Stakes.FREE if stage.teaches else Stakes.CHARGED
