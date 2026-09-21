"""Deterministic, explainable session generation.

``generate_session(skill, pool, learner, recent)`` returns an ordered list of steps
plus a printable reason for every decision. It is a pure function over plain data:
no clock, no storage, no randomness, no model. That is a design requirement, not a
convenience — the research this build rests on found that adaptive-mechanic platforms
alone beat conventional instruction by about nothing (g = 0.05) and only pay off as a
supplement to authored content (g = 0.43). The ordering below is pedagogy made
inspectable, so a lesson can be explained, reproduced in a test, and debugged
without a dataset.

The rules, in the order they apply:

1. Ladder          — a new concept walks introduce → show → interact → guided →
                     scaffolded → independent → explain → transfer.
2. Resume          — rungs already cleared are not re-taught; the session starts at
                     the first uncleared rung.
3. Fading          — a concept already demonstrated *and* fully walked drops the
                     teaching rungs and opens with one retrieval prompt (expertise
                     reversal: guidance becomes redundant, then harmful, as prior
                     knowledge grows). It never fades a ladder the learner is
                     still inside.
4. Remediation     — repeated misses at a rung insert a simpler worked example
                     before asking again.
5. Misconception   — a recorded misconception inserts a step that targets it ahead
                     of the next charged rung, so the weakness is taught rather than
                     re-tested.
6. Hint dependence — clearing a rung with hints does not count as clearing it; the
                     rung is re-queued later in the session instead.
7. Modality        — never two of the same response widget in a row, and never two
                     editor rungs in row.
8. Review as bonus — due retrieval is appended *past* the known end, so the progress
                     indicator never shrinks or moves backwards mid-session.
9. First contact   — a step that names a concept this pool does not teach is a
                     retrieval hook for something an earlier lesson taught. It fires
                     for a learner who has met that concept (rules 3 and 8) and stays
                     silent for one who has not: nobody should be handed a quiz on
                     material they never saw.

9 is why the generator is handed the learner state for *every* concept a pool names,
not just the pool's own: a hook is only as good as the history it can read.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from backend.learning_models import (
    LADDER,
    EDITOR_STAGES,
    Stage,
    Stakes,
    default_stakes,
)

#: A miss run this long triggers a remediation step rather than another attempt.
REMEDIATE_AFTER_MISSES = 2
#: First recall gap for a concept, and the factor applied on each strong recall.
BASE_INTERVAL_SECONDS = 300.0
INTERVAL_GROWTH = 5.0
#: Consecutive strong recalls before a concept is treated as demonstrated without
#: an explicit transfer step.
DEMONSTRATED_AFTER = 1


@dataclass(frozen=True)
class Step:
    """One authored step from a skill's pool.

    ``stage`` is the rung it serves, ``widget`` the response mechanism (the shared
    exercise-type vocabulary), and the optional hooks drive rules 4 and 5.
    """

    id: str
    stage: Stage
    widget: str
    concept: str
    order: int = 0
    difficulty: int = 1
    remediation_of: str | None = None      # this step is the simpler fallback for that rung
    targets_misconception: str | None = None
    requires_editor: bool | None = None
    stakes: Stakes | None = None
    max_hints: int = 4

    @property
    def uses_editor(self) -> bool:
        if self.requires_editor is not None:
            return self.requires_editor
        return self.stage in EDITOR_STAGES

    @property
    def effective_stakes(self) -> Stakes:
        """The rung decides, not the author.

        Charging is a claim about the *learner's* relationship to the material —
        first contact is free to fail, production under pressure is not — so an
        authored ``stakes`` value is treated as a note, not a setting. Both
        overrides are ignored: a teaching step cannot be made costly, and an
        assessment step cannot be made free.
        """
        rung_default = default_stakes(self.stage)
        if self.stakes is None:
            return rung_default
        if self.stakes is Stakes.FREE and rung_default is Stakes.FREE:
            return Stakes.FREE
        return rung_default

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Step":
        stage = Stage(str(raw["stage"]))
        widget = str(raw.get("widget") or raw.get("type") or "")
        if not widget:
            raise ValueError(f"step {raw.get('id')!r} has no widget/type")
        stakes_raw = raw.get("stakes")
        return cls(
            id=str(raw["id"]),
            stage=stage,
            widget=widget,
            concept=str(raw.get("concept") or ""),
            order=int(raw.get("order", 0)),
            difficulty=int(raw.get("difficulty", 1)),
            remediation_of=raw.get("remediation_of"),
            targets_misconception=raw.get("targets_misconception"),
            requires_editor=raw.get("requires_editor"),
            stakes=Stakes(str(stakes_raw)) if stakes_raw else None,
            max_hints=int(raw.get("max_hints", 4)),
        )


@dataclass
class ConceptState:
    """What the learner has shown about one concept.

    Evidence is a set of *kinds*, not a percentage: the claim "demonstrated" has to
    rest on independent production, not on a completion count that hint use and
    retries can inflate.
    """

    concept: str
    cleared_steps: set[str] = field(default_factory=set)
    evidence: set[str] = field(default_factory=set)      # independent|debugged|transferred|delayed_recall
    misses: dict[str, int] = field(default_factory=dict)  # step id -> consecutive misses
    hinted_steps: set[str] = field(default_factory=set)
    misconceptions: dict[str, int] = field(default_factory=dict)
    last_recall_at: float | None = None
    interval_seconds: float = 0.0
    strong_recalls: int = 0

    @property
    def seen(self) -> bool:
        return bool(self.cleared_steps)

    @property
    def demonstrated(self) -> bool:
        """Independent production plus one further, different form of evidence."""
        return "independent" in self.evidence and (
            len(self.evidence - {"guided"}) >= 2
            or self.strong_recalls >= DEMONSTRATED_AFTER
        )

    def due_for_review(self, now: float) -> bool:
        if self.last_recall_at is None or not self.interval_seconds:
            return False
        return (now - self.last_recall_at) >= self.interval_seconds


@dataclass(frozen=True)
class SessionStep:
    step: Step
    reason: str
    bonus: bool = False

    @property
    def stakes(self) -> Stakes:
        return self.step.effective_stakes

    def as_public(self) -> dict[str, Any]:
        return {
            "id": self.step.id,
            "stage": self.step.stage.value,
            "widget": self.step.widget,
            "concept": self.step.concept,
            "stakes": self.stakes.value,
            "bonus": self.bonus,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class Session:
    steps: tuple[SessionStep, ...]
    concepts: tuple[str, ...]

    @property
    def planned(self) -> int:
        """Steps known up front — the length the progress bar may promise."""
        return sum(1 for s in self.steps if not s.bonus)

    @property
    def bonus_count(self) -> int:
        return sum(1 for s in self.steps if s.bonus)

    def trace(self) -> list[str]:
        return [
            f"{s.step.stage.value:<11} {s.step.id:<26} {'(bonus) ' if s.bonus else ''}{s.reason}"
            for s in self.steps
        ]

    def as_public(self) -> dict[str, Any]:
        return {
            "concepts": list(self.concepts),
            "planned_steps": self.planned,
            "bonus_steps": self.bonus_count,
            "steps": [s.as_public() for s in self.steps],
        }


_LADDER_INDEX = {stage: i for i, stage in enumerate(LADDER)}


def _rank(step: Step) -> tuple[int, int, str]:
    """Authored ladder position, then author order, then id: a total order."""
    return (_LADDER_INDEX.get(step.stage, len(LADDER)), step.order, step.id)


def _pick(pool: Sequence[Step], done: set[str], *, stage: Stage | None = None,
          avoid_widget: str | None = None, avoid_editor: bool = False,
          prefer: str | None = None, allow_remediation: bool = False) -> Step | None:
    """First unused step satisfying the constraints, easiest ladder position first.

    ``avoid_*`` are *preferences*, not filters. A rung is never dropped because
    picking it would repeat a widget or stack two editor steps: the fading sequence
    guided → scaffolded → independent is legitimately three editor rungs in a row,
    and losing a rung to a style rule would break the pedagogy the ladder exists to
    deliver. ``prefer`` pulls a matching misconception or remediation step forward.
    """
    candidates = [
        s for s in pool
        if s.id not in done
        and (stage is None or s.stage is stage)
        # A fallback example is not a default example: serving the easier worked
        # example as first contact tells the learner nothing and wastes the rung.
        and (allow_remediation or s.remediation_of is None)
    ]
    if not candidates:
        return None

    def key(step: Step) -> tuple[int, int, int, str]:
        repeatable = step.widget in NON_INTERACTIVE_WIDGETS
        return (
            0 if repeatable or not avoid_widget or step.widget != avoid_widget else 1,
            1 if (avoid_editor and step.uses_editor) else 0,
            step.order if prefer is None or not _matches_hint(step, prefer) else -1,
            step.id,
        )

    return min(candidates, key=key)


def _matches_hint(step: Step, hint: str) -> bool:
    return step.targets_misconception == hint or step.remediation_of == hint


def _strongest_misconception(state: ConceptState) -> str | None:
    if not state.misconceptions:
        return None
    return max(sorted(state.misconceptions), key=lambda k: state.misconceptions[k])


#: Widgets that ask for nothing but a tap to continue. Two in a row is reading a
#: lesson, and a preference that tried to avoid that would reorder the ladder.
NON_INTERACTIVE_WIDGETS = frozenset({"present"})


def _ladder_finished(pool_for: Sequence[Step], done: set[str]) -> bool:
    """Has the learner been through every rung this concept asks them to produce?

    Fading is a claim about a *finished* piece of work. Applied halfway through a
    lesson it deletes the rung the learner is standing in front of: clearing
    `independent` and then `explain` already counts as demonstrated, so without
    this check the transfer rung — the one where they use the idea on a problem
    they have not seen — vanished from the session mid-lesson.
    """
    charged = [s.id for s in pool_for if s.stage in (Stage.INDEPENDENT, Stage.TRANSFER)]
    return all(step_id in done for step_id in charged)


def generate_session(
    pool: Iterable[Step | dict[str, Any]],
    learner: Iterable[ConceptState] = (),
    *,
    now: float = 0.0,
    review_limit: int = 2,
) -> Session:
    steps = [s if isinstance(s, Step) else Step.from_dict(s) for s in pool]
    if not steps:
        raise ValueError("a session needs a non-empty step pool")
    states = {s.concept: s for s in learner}
    concepts = sorted({s.concept for s in steps if s.concept})
    if not concepts:
        raise ValueError("no step in the pool declares a concept")

    used: set[str] = set()
    out: list[SessionStep] = []
    prev: SessionStep | None = None

    def add(step: Step, reason: str, *, bonus: bool = False) -> SessionStep | None:
        nonlocal prev
        if step.id in used:
            return None
        entry = SessionStep(step=step, reason=reason, bonus=bonus)
        used.add(step.id)
        out.append(entry)
        if not bonus:
            prev = entry
        return entry

    for concept in concepts:
        state = states.get(concept) or ConceptState(concept=concept)
        pool_for = [s for s in steps if s.concept == concept]
        if not pool_for:
            continue
        done = set(state.cleared_steps)

        # Rule 9 — a group of steps that only retrieve is a hook for a concept an
        # earlier lesson taught, so it has nothing to say to a learner who never
        # met it. Their first contact with a concept must always be instruction.
        if not state.seen and not any(
            s.stage in (Stage.INTRODUCE, Stage.SHOW) for s in pool_for
        ):
            continue

        # Rule 3 — fade the teaching rungs once the concept is demonstrated *and*
        # every rung of this ladder has been walked. Fading is a between-sessions
        # decision; mid-lesson it would re-route the learner past their own work.
        if state.demonstrated and _ladder_finished(pool_for, done):
            retrieval = _pick(pool_for, done, stage=Stage.INTERACT)
            if retrieval is not None:
                add(retrieval, f"faded: {concept} already demonstrated, opening on retrieval "
                               "instead of re-teaching")
            # The gate that separates "did it once" from "demonstrated" is a
            # mixed-skill check, not a higher score on the same item. A check the
            # learner has already passed stays passed: re-serving it every visit
            # turns a demonstrated concept into a permanent exit ticket.
            check = _pick(pool_for, used | done, stage=Stage.MASTERY)
            if check is not None:
                add(
                    check,
                    f"mixed-skill check for {concept}: prior knowledge must survive a "
                    "different surface, not a repeat",
                )
            continue

        # Rules 1, 2, 4, 5, 7 — walk the ladder from the first uncleared rung.
        for stage in LADDER:
            wants_hint = _strongest_misconception(state) if stage in (
                Stage.INDEPENDENT, Stage.TRANSFER, Stage.MASTERY
            ) else None

            # Rule 5 — teach the misconception before asking for it under pressure.
            if wants_hint:
                targeted = _pick(
                    [
                        s for s in pool_for
                        if s.targets_misconception == wants_hint and s.stage is not stage
                    ],
                    used | done,
                )
                if targeted is not None:
                    add(
                        targeted,
                        f"targets {wants_hint} "
                        f"({state.misconceptions.get(wants_hint, 0)} recorded) before the "
                        f"charged {stage.value} rung",
                    )

            while True:
                step = _pick(
                    pool_for,
                    used | done,
                    stage=stage,
                    avoid_widget=prev.step.widget if prev else None,
                    avoid_editor=bool(prev and prev.step.uses_editor),
                    prefer=wants_hint,
                )
                if step is None:
                    break

                # Rule 4 — remediate before asking a twice-missed rung again.
                misses = state.misses.get(step.id, 0)
                if misses >= REMEDIATE_AFTER_MISSES:
                    backstep = _pick(
                        [s for s in pool_for if s.remediation_of == step.id],
                        used | done,
                        allow_remediation=True,
                    )
                    if backstep is not None and add(
                        backstep,
                        f"remediation: {misses} misses at {stage.value} → simpler "
                        "worked example before asking again",
                    ):
                        continue

                add(step, _placement_reason(step, state, wants_hint))
                break

        # Rule 6 — a rung cleared only with hints is not cleared.
        hinted = [sid for sid in sorted(done) if sid in state.hinted_steps]
        for sid in hinted[:1]:
            step = next((s for s in pool_for if s.id == sid), None)
            if step is None or step.stage not in (Stage.INDEPENDENT, Stage.TRANSFER):
                continue
            # Deliberately ignores `done`: the whole point is to re-ask it unaided.
            retry = _pick(pool_for, used, stage=step.stage)
            if retry is not None and add(
                retry,
                f"hint-dependent: {sid} was cleared using hints, so it is "
                "re-queued unaided before mastery",
            ):
                break

    # Rule 8 — due retrieval goes past the end, as bonus length.
    for concept in sorted(concepts):
        state = states.get(concept)
        if state is None or not state.due_for_review(now):
            continue
        if sum(1 for s in out if s.bonus) >= review_limit:
            break
        review = _pick([s for s in steps if s.concept == concept], used, stage=Stage.REVIEW)
        if review is None:
            review = _pick([s for s in steps if s.concept == concept], used, stage=Stage.INTERACT)
        if review is not None and add(
            review,
            f"review: {concept} due for retrieval "
            f"({int(now - (state.last_recall_at or 0))}s >= {int(state.interval_seconds)}s)",
            bonus=True,
        ):
            continue

    if not out:
        # Every rung is cleared, so the visit is review. Rank by how much each step
        # asks the learner to *retrieve*: a session that opened with the worked
        # example again (which is what plain ladder order gives) re-shows a concept
        # to someone who has already proved it, and acknowledges reading instead of
        # testing memory. `present` steps are last, and only if nothing else exists.
        retrievable = [s for s in steps if s.widget != PRESENTATION_WIDGET]
        pool = sorted(retrievable, key=_retrieval_rank) or list(steps)
        for step in pool[:3]:
            add(step, "retrieval-only: every rung of this skill is already cleared",
                bonus=True)

    return Session(steps=tuple(out), concepts=tuple(concepts))


#: Widgets that ask for no retrieval at all, so they never lead a review session.
PRESENTATION_WIDGET = "present"

#: Lower is more worth retrieving. Delayed recall and the mixed check are the two
#: that say something about the memory; a fill blank is the weakest.
_RETRIEVAL_ORDER = (
    Stage.REVIEW,
    Stage.MASTERY,
    Stage.INTERACT,
    Stage.EXPLAIN,
    Stage.TRANSFER,
    Stage.INDEPENDENT,
    Stage.GUIDED,
    Stage.SCAFFOLDED,
    Stage.SHOW,
    Stage.INTRODUCE,
)


def _retrieval_rank(step: Step) -> tuple[int, int, str]:
    try:
        return (_RETRIEVAL_ORDER.index(step.stage), step.order, step.id)
    except ValueError:
        return (len(_RETRIEVAL_ORDER), step.order, step.id)


def _placement_reason(step: Step, state: ConceptState, wants_hint: str | None) -> str:
    if step.targets_misconception and step.targets_misconception == wants_hint:
        return (
            f"targets {step.targets_misconception} "
            f"({state.misconceptions.get(step.targets_misconception, 0)} recorded) "
            f"before the next charged rung"
        )
    return f"ladder: {step.stage.value} rung for {step.concept}"


def next_interval(previous_seconds: float, recalled: bool) -> float:
    """Double-ish on strong recall, collapse on a miss. Explainable, not fitted.

    Deliberately a two-line rule rather than FSRS or SM-2: spacing itself is a
    strong effect, but no published study shows a fancier scheduler produces better
    *learning*, and a rule we can state in a test is worth more here than a margin
    we cannot verify.
    """
    if not recalled:
        return BASE_INTERVAL_SECONDS
    base = previous_seconds or BASE_INTERVAL_SECONDS
    return math.floor(base * INTERVAL_GROWTH)
