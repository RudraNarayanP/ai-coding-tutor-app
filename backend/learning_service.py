"""The learning session: ladder state, attempts, and what a step is worth.

Design constraint that shapes this whole module: **do not build a second engine.**
A graded step is converted to an ``ExerciseDefinition`` and handed to the existing
``grade_exercise``, and its misses go into the existing mistake queue via
``record_attempt`` — so recall timing, graduation and heart refunds behave identically
to a lesson exercise, and a step cannot drift into being marked wrong in review after
passing in the lesson.

What is new here is only what the ladder needs and the exercise model cannot
express: which *rung* a step is, what evidence a step produces, and whether failing
it costs anything.
"""

from __future__ import annotations

import time
from typing import Any

from backend import step_pool
from backend.learning_models import (
    EVIDENCE_FOR_STAGE,
    STAGE_XP,
    Stage,
    Stakes,
)
from backend.session_generator import (
    BASE_INTERVAL_SECONDS,
    ConceptState,
    Step,
    generate_session,
    next_interval,
)

# EVIDENCE_FOR_STAGE and STAGE_XP are re-exported from ``learning_models`` so the
# guided-project ladder and the curriculum ladder share one definition of what a
# rung is worth and what it proves. Importing them from here still works.


def _now() -> float:
    return time.time()


def concept_view(raw: dict[str, Any] | None, concept: str) -> ConceptState:
    """The persisted dict, as the generator's own state object.

    One definition of "demonstrated" for both sides, so a session cannot be
    faded in by the store and then re-taught by the generator.
    """
    raw = raw or {}
    return ConceptState(
        concept=concept,
        cleared_steps=set(raw.get("cleared_steps") or []),
        evidence=set(raw.get("evidence") or []),
        misses={k: int(v) for k, v in (raw.get("misses") or {}).items()},
        hinted_steps=set(raw.get("hinted_steps") or []),
        misconceptions={k: int(v) for k, v in (raw.get("misconceptions") or {}).items()},
        last_recall_at=raw.get("last_recall_at"),
        interval_seconds=float(raw.get("interval_seconds") or 0.0),
        strong_recalls=int(raw.get("strong_recalls") or 0),
    )


def _persist(state: ConceptState) -> dict[str, Any]:
    return {
        "cleared_steps": sorted(state.cleared_steps),
        "evidence": sorted(state.evidence),
        "misses": dict(state.misses),
        "hinted_steps": sorted(state.hinted_steps),
        "misconceptions": dict(state.misconceptions),
        "last_recall_at": state.last_recall_at,
        "interval_seconds": state.interval_seconds,
        "strong_recalls": state.strong_recalls,
    }


def concepts_in_pool(pool) -> list[str]:
    """Every concept the pool's steps name, this pool's own concept first.

    A pool may author *retrieval hooks* for a concept another lesson taught —
    "Mean Squared Error" opens by asking for a prediction, because error is only
    interesting once you have a prediction to be wrong about. Those hooks belong
    to a different concept, and the learner's history with *that* concept is what
    decides whether the hook can be served at all.
    """
    named = [str(s.get("concept") or pool.concept) for s in pool.steps]
    return sorted({pool.concept, *named})


def states_for(store, pool) -> dict[str, ConceptState]:
    """Learner state for every concept in the pool, keyed by concept."""
    return {c: concept_view(store.concept_state(c), c) for c in concepts_in_pool(pool)}


def _submitted_label(widget: str, payload: dict) -> str | None:
    """The answer as the learner saw it, for authored per-answer feedback."""
    if widget in ("mcq", "true_false", "output_prediction", "identify_error", "identify_mistake", "short_answer"):
        value = payload.get("answer")
        return str(value) if value is not None else None
    if widget == "select_multiple":
        answers = payload.get("answers") or []
        return str(answers[0]) if answers else None
    if widget == "ordering":
        order = payload.get("order") or payload.get("answers") or []
        return " | ".join(str(o) for o in order) if order else None
    if widget in ("fill_blank", "code_completion"):
        # What was typed into the blank, so a step that authored a repair for the
        # common wrong fill ("d" instead of "d ** 2") can actually say it. Without
        # this the answer text falls through to generic feedback and the authored
        # misconception repair is dead data in the pool.
        answers = payload.get("answers") or []
        if isinstance(answers, str):
            return answers
        return str(answers[0]) if answers else None
    return None


def authored_feedback(step: dict, widget: str, payload: dict, fallback: str) -> tuple[str, str | None]:
    """Interpreted feedback first, generic text only when nothing was authored.

    A wrong tap is usually a specific, known misconception, and the pool already
    names the repair for it — showing "Not quite" instead throws that away.
    """
    feedback = step.get("feedback") or {}
    label = _submitted_label(widget, payload)
    if isinstance(feedback, dict) and label and label in feedback:
        return str(feedback[label]), label
    return fallback, label


def _is_due(state: ConceptState, now: float) -> bool:
    return bool(state.interval_seconds) and state.last_recall_at is not None \
        and (now - state.last_recall_at) >= state.interval_seconds


def session_for(lesson_engine, lesson_id: str, language: str) -> dict[str, Any] | None:
    """The generated session for a ladder lesson, or None if it has no pool."""
    pool = step_pool.pool_for_lesson(language, lesson_id)
    if pool is None:
        return None
    store = lesson_engine.stores.get(language, lesson_engine.store)
    now = _now()
    # Every concept the pool names, not just its own: a retrieval hook for an old
    # concept can only be served if the generator can see what the learner showed
    # about *that* concept.
    states = states_for(store, pool)
    state = states[pool.concept]
    session = generate_session(pool.as_generator_pool(), list(states.values()), now=now)
    steps = []
    for entry in session.steps:
        raw = pool.by_id(entry.step.id) or {}
        own = states.get(entry.step.concept) or state
        steps.append(
            {
                **entry.as_public(),
                "title": raw.get("title", ""),
                "question": raw.get("question", ""),
                "options": raw.get("options", []),
                "pairs": raw.get("pairs", []),
                # `blanks` and `correct_order` are deliberately NOT sent. For a
                # fill rung `blanks` *is* the answer key, and for an ordering rung
                # `correct_order` is the answer — the learner's own editor renders
                # the task, so the payload needs neither. The exercise path has
                # stripped `blanks` for the same reason all along
                # (see ExerciseWorkspace.test.tsx); the ladder was violating it.
                "starter_code": raw.get("starter_code", "") or raw.get("code", ""),
                "content": raw.get("content", {}),
                "action": raw.get("action", ""),
                "hints": raw.get("hints", []),
                "cleared": entry.step.id in own.cleared_steps,
                "due": _is_due(own, now),
            }
        )
    return {
        "lesson_id": lesson_id,
        "skill": pool.skill,
        "concept": pool.concept,
        "objective": pool.objective,
        "story": pool.story,
        "planned_steps": session.planned,
        "bonus_steps": session.bonus_count,
        # How far through the lesson a learner starting from zero would get. The
        # session list only holds what is still owed, so without this the client
        # cannot tell "3 of 8" from "1 of 3" and the progress bar restarts every
        # time a rung is answered. Derived from the generator rather than counted
        # off the pool, because the pool also carries remediation and mixed-skill
        # rungs that a first visit never reaches.
        "ladder_steps": generate_session(pool.as_generator_pool(), [], now=0.0).planned,
        "steps": steps,
        "trace": session.trace(),
        "demonstrated": state.demonstrated,
        "evidence": sorted(state.evidence),
    }


def mark_step_seen(store, pool, step: dict, *, now: float | None = None) -> dict[str, Any]:
    """Record that a presentation rung was viewed, so the session resumes past it.

    Presentation steps award nothing on purpose: acknowledging you read something
    is not evidence, and paying for it is exactly the attendance metric that
    displaces learning.
    """
    moment = _now() if now is None else now
    concept = str(step.get("concept") or pool.concept)
    state = concept_view(store.concept_state(concept), concept)
    state.cleared_steps.add(step["id"])
    store.set_concept_state(concept, _persist(state))
    return {"step_id": step["id"], "cleared": sorted(state.cleared_steps), "xp_awarded": 0}


def _complete_rungs(pool, state: ConceptState) -> list[str]:
    """Charged rungs that carry real weight, in ladder order."""
    return [
        s["id"]
        for s in pool.steps
        if Stage(s["stage"]) in (Stage.INDEPENDENT, Stage.TRANSFER)
    ]


async def attempt_step(lesson_engine, lesson_id: str, language: str, step_id: str, payload: dict,                   *, hints_used: int = 0) -> dict[str, Any]:
    """Grade one authored step and update everything that follows from it."""
    pool = step_pool.pool_for_lesson(language, lesson_id)
    if pool is None:
        raise KeyError(f"lesson {lesson_id!r} has no authored step pool")
    step = pool.by_id(step_id)
    if step is None:
        raise KeyError(f"step {step_id!r} is not part of {pool.skill}")
    stage = Stage(step["stage"])
    widget = step["widget"]
    # A step belongs to the concept it names, which for a retrieval hook is the
    # concept an earlier lesson taught — not the one this lesson is about.
    step_concept = str(step.get("concept") or pool.concept)
    if widget == step_pool.PRESENTATION_WIDGET:
        raise ValueError("presentation steps are marked seen, never attempted")

    store = lesson_engine.stores.get(language, lesson_engine.store)
    lesson = lesson_engine.get_lesson(lesson_id)
    moment = _now()

    exercise = step_pool.step_as_exercise(pool, step)
    passed, graded_feedback = await lesson_engine.grade_exercise(exercise, payload, language)

    # Misses go through the existing queue so a missed step returns on a recall
    # gap and refunds a heart when it is finally cleared, exactly like a lesson
    # exercise does.
    queued_before = store.queued_exercise_ids()
    attempt_count = store.record_attempt(step_id, passed, lesson_id=lesson_id)
    graduated = step_id in queued_before and step_id not in store.queued_exercise_ids()

    state = concept_view(store.concept_state(step_concept), step_concept)
    hinted = hints_used > 0
    xp_awarded = 0

    if passed:
        # A rung cleared with hints is recorded as seen but not as evidence:
        # otherwise the ladder would fade teaching for a learner who has never
        # produced the thing unaided.
        first_clear = step_id not in state.cleared_steps
        state.cleared_steps.add(step_id)
        # XP is paid once; evidence is a set, and it is owed to the first
        # *unaided* pass rather than the first pass. Conflating the two stranded
        # any rung a learner had once cleared with hints: the step was already
        # "cleared", so solving it properly later earned them nothing at all.
        if not hinted:
            evidence = EVIDENCE_FOR_STAGE.get(stage)
            if evidence:
                state.evidence.add(evidence)
            if stage is Stage.REVIEW:
                state.strong_recalls += 1
                state.last_recall_at = moment
                state.interval_seconds = next_interval(state.interval_seconds, True)
            elif state.last_recall_at is None:
                # Seed the clock. Without this a concept whose pool authors no
                # review step could never become due, and spaced retrieval would
                # silently apply only to the concepts someone happened to write a
                # card for.
                state.last_recall_at = moment
                state.interval_seconds = BASE_INTERVAL_SECONDS
        if first_clear:
            xp_awarded += store.add_xp(int(step.get("xp_reward", STAGE_XP.get(stage, 0)) or 0))
    else:
        state.misses[step_id] = state.misses.get(step_id, 0) + 1
        state.strong_recalls = 0
        if stage is Stage.REVIEW:
            state.last_recall_at = moment
            state.interval_seconds = next_interval(0.0, False)
        elif state.last_recall_at is None:
            state.last_recall_at = moment
            state.interval_seconds = BASE_INTERVAL_SECONDS
        target = step.get("targets_misconception") or payload.get("misconception")
        if target:
            state.misconceptions[str(target)] = state.misconceptions.get(str(target), 0) + 1
    if hinted:
        state.hinted_steps.add(step_id)
    store.set_concept_state(step_concept, _persist(state))

    lesson_completed = False
    next_lesson_id = None
    # Completing a lesson is a claim about the lesson's own concept, so it reads
    # that concept's state even when the step just attempted was a hook for
    # another one.
    owned = state if step_concept == pool.concept else \
        concept_view(store.concept_state(pool.concept), pool.concept)
    rungs = _complete_rungs(pool, owned)
    if rungs and all(rid in owned.cleared_steps for rid in rungs):
        if lesson_id not in store.state().completed_lesson_ids:
            store.mark_completed(lesson_id)
            xp_awarded += store.add_xp(lesson.xp_reward or 10)
        lesson_completed = True
        progress = lesson_engine.lesson_progress(lesson_id)
        next_lesson_id = progress.get("next_lesson_id")

    feedback, _ = authored_feedback(step, widget, payload, graded_feedback)

    return {
        "step_id": step_id,
        "stage": stage.value,
        # What the *attempted step* proved, which for a retrieval hook is a
        # concept from an earlier lesson. The completion screen reads the lesson's
        # own state from ``session`` instead, so the two cannot be confused.
        "concept": step_concept,
        "passed": passed,
        "state": "correct" if passed else "incorrect",
        "attempt_count": attempt_count,
        "feedback": feedback,
        "explanation": step.get("explanation") or exercise.explanation or None,
        "misconception": step.get("targets_misconception"),
        "hints_used": hints_used,
        "xp_awarded": xp_awarded,
        "total_xp": store.state().xp,
        "level": store.state().level,
        "evidence": sorted(state.evidence),
        "demonstrated": concept_view(_persist(state), step_concept).demonstrated,
        "graduated": graduated,
        "still_queued": step_id in store.queued_exercise_ids(),
        "lesson_completed": lesson_completed,
        "next_lesson_id": next_lesson_id,
        "charging": step_charges(step),
        "session": session_for(lesson_engine, lesson_id, language),
    }


def step_charges(step: dict) -> bool:
    """Whether failing this step may cost a heart — the rung decides.

    Mirrors ``Step.effective_stakes`` so the endpoint gate and the model cannot
    disagree about what "free to fail" covers.
    """
    return Step.from_dict({**step, "concept": step.get("concept") or "_"}).effective_stakes is Stakes.CHARGED


def concepts_summary(lesson_engine, language: str) -> dict[str, Any]:
    """The headline number: concepts demonstrated independently, not minutes spent."""
    store = lesson_engine.stores.get(language, lesson_engine.store)
    items = []
    for pool in step_pool.pools_for_language(language):
        raw = store.concept_state(pool.concept)
        state = concept_view(raw, pool.concept)
        items.append(
            {
                "skill": pool.skill,
                "concept": pool.concept,
                "lesson_id": pool.lesson_id,
                "language": language,
                "objective": pool.objective,
                "evidence": sorted(state.evidence),
                "demonstrated": state.demonstrated,
                "in_progress": bool(state.cleared_steps) and not state.demonstrated,
                "misconceptions": state.misconceptions,
                "interval_seconds": state.interval_seconds,
                "due_for_review": bool(state.interval_seconds)
                and state.last_recall_at is not None
                and (_now() - state.last_recall_at) >= state.interval_seconds,
            }
        )
    return {
        "language": language,
        "demonstrated": sum(1 for i in items if i["demonstrated"]),
        "in_progress": sum(1 for i in items if i["in_progress"]),
        "total": len(items),
        "concepts": items,
    }


def charge_for(language: str, lesson_id: str, step_id: str) -> bool:
    """Whether this step may cost a heart, resolved before grading.

    The endpoint needs the answer before it can decide whether an empty heart pool
    should block the attempt, and that decision must come from the same rung rule
    as everything else rather than a second copy in the route.
    """
    pool = step_pool.pool_for_lesson(language, lesson_id)
    if pool is None:
        return False
    step = pool.by_id(step_id)
    return bool(step) and step_charges(step)


def presentation_step(language: str, lesson_id: str, step_id: str) -> dict | None:
    pool = step_pool.pool_for_lesson(language, lesson_id)
    if pool is None:
        return None
    step = pool.by_id(step_id)
    if step and step["widget"] == step_pool.PRESENTATION_WIDGET:
        return step
    return None


def pool_for(language: str, lesson_id: str):
    return step_pool.pool_for_lesson(language, lesson_id)
