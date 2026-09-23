"""Sessions for Create Course guided projects, built by the shared generator.

This is the project half of the teaching ladder. It owns three things the
checklist flow did not have:

* a **session** per milestone — the teaching rungs the learner walks before the
  task, plus retrieval of earlier milestones when it comes due, ordered by
  :func:`backend.session_generator.generate_session` rather than by a second
  scheduler;
* **evidence** rather than completion — a milestone the learner was shown and then
  built unaided is a different claim from one the workspace happened to satisfy
  already, or one they finished after applying an AI suggestion. Both still
  complete the milestone and still pay its XP; only the first counts as
  demonstrated, and only the first stops the retrieval rung coming back.
* an honest **progress denominator** (``ladder_steps``), because the generator
  returns only what is still owed.

State lives on the project document itself (``ProjectCourse.concept_state``), so a
project keeps its ladder across restarts and deleting the project deletes its
history. Nothing here imports the curriculum engine: projects verify by running
the learner's workspace, which is a stronger check than any exercise grader and
already existed.
"""

from __future__ import annotations

import time
from typing import Any

from backend import project_ladder
from backend.learning_models import Stage
from backend.learning_service import _persist, concept_view
from backend.project_copy import learner_facing_fields
from backend.project_models import MilestoneProgress
from backend.session_generator import ConceptState, generate_session


def _now() -> float:
    return time.time()


def _milestone_at(project: Any, index: int | None = None) -> Any | None:
    milestones = list(getattr(project, "milestones", None) or [])
    if not milestones:
        return None
    idx = project.current_milestone_index if index is None else index
    return milestones[min(max(idx, 0), len(milestones) - 1)]


def _fields(project: Any, milestone: Any) -> dict[str, Any]:
    return learner_facing_fields(
        milestone,
        entry_file=getattr(project, "entry_file", "") or "main.py",
        project_title=getattr(project, "title", "") or "",
        project_goal=getattr(project, "project_goal", "") or "",
    )


def _state(project: Any, concept: str) -> ConceptState:
    return concept_view((project.concept_state or {}).get(concept), concept)


def _save(project: Any, concept: str, state: ConceptState) -> None:
    if not hasattr(project, "concept_state") or project.concept_state is None:
        project.concept_state = {}
    project.concept_state[concept] = _persist(state)


def _reason(entry: Any, rung: dict[str, Any]) -> str:
    """The generator's reason names a concept id; the authored one reads like a person."""
    return str(rung.get("reason_copy") or entry.reason or "")


def _public_step(entry: Any, rung: dict[str, Any], state: ConceptState) -> dict[str, Any]:
    return {
        **entry.as_public(),
        "reason": _reason(entry, rung),
        "title": rung.get("title", ""),
        "question": rung.get("question", ""),
        # No answer keys here. The curriculum ladder learned that rule the hard
        # way: a payload field that *is* the answer is a leak with no consumer.
        "options": rung.get("options", []),
        "content": rung.get("content", {}),
        "action": rung.get("action", ""),
        "hints": rung.get("hints", []),
        "checks": rung.get("checks", []),
        "cleared": entry.step.id in state.cleared_steps,
    }


def session_for_project(project: Any, *, now: float | None = None) -> dict[str, Any] | None:
    """The ladder session for the project's current milestone, or None if there is none."""
    milestone = _milestone_at(project)
    if milestone is None:
        return None
    moment = _now() if now is None else now
    fields = _fields(project, milestone)
    pool = project_ladder.session_pool(project, milestone, fields)

    by_id = {rung["id"]: rung for rung in pool}
    states = {}
    for rung in pool:
        concept = rung["concept"]
        states.setdefault(concept, _state(project, concept))
    session = generate_session(pool, list(states.values()), now=moment)

    steps: list[dict[str, Any]] = []
    build: dict[str, Any] | None = None
    for entry in session.steps:
        rung = by_id.get(entry.step.id, {})
        own = states.get(entry.step.concept) or _state(project, entry.step.concept)
        if entry.step.widget == project_ladder.BUILD_WIDGET:
            build = _public_step(entry, rung, own)
            continue
        steps.append(_public_step(entry, rung, own))

    own_state = states.get(project_ladder.milestone_concept(project.course_id, milestone.id))
    own_state = own_state or _state(project, project_ladder.milestone_concept(project.course_id, milestone.id))
    upcoming = _milestone_at(project, project.current_milestone_index + 1)
    return {
        "lesson_id": project.course_id,
        "skill": milestone.title or "",
        "concept": project_ladder.milestone_concept(project.course_id, milestone.id),
        "objective": project.project_goal or milestone.source_grounded_description or "",
        "story": {
            "why_this": fields.get("why") or "",
            "why_next": f"Next: {upcoming.title}" if upcoming else "That is the last step — the project is yours.",
        },
        "milestone_id": milestone.id,
        "milestone_title": milestone.title or "",
        "milestone_order": milestone.order,
        "milestone_total": len(project.milestones),
        "planned_steps": session.planned,
        "bonus_steps": session.bonus_count,
        "ladder_steps": project_ladder.ladder_steps(project, milestone, fields),
        "steps": steps,
        "build": build,
        "trace": [
            f"{e.step.stage.value:<11} {e.step.id:<24} {'(bonus) ' if e.bonus else ''}{_reason(e, by_id.get(e.step.id, {}))}"
            for e in session.steps
        ],
        "demonstrated": own_state.demonstrated,
        "evidence": sorted(own_state.evidence),
        "completion_percent": project.completion_percent(),
        "completed": bool(project.completed),
        "summary": project_summary(project) if project.completed else None,
    }


def mark_rung_seen(project: Any, step_id: str, *, now: float | None = None) -> dict[str, Any]:
    """Acknowledge a teaching card. Awards nothing: reading is not an accomplishment."""
    milestone = _milestone_at(project)
    if milestone is None:
        raise KeyError("this project has no milestones")
    fields = _fields(project, milestone)
    rung = next((r for r in project_ladder.session_pool(project, milestone, fields) if r["id"] == step_id), None)
    if rung is None:
        raise KeyError(f"rung {step_id!r} is not part of milestone {milestone.id}")
    if rung["widget"] != project_ladder.PRESENTATION_WIDGET:
        raise ValueError("only teaching cards are acknowledged; this rung is answered")
    state = _state(project, rung["concept"])
    state.cleared_steps.add(step_id)
    _save(project, rung["concept"], state)
    return {"step_id": step_id, "cleared": sorted(state.cleared_steps), "xp_awarded": 0}


def milestone_review_flags(project: Any, *, now: float | None = None) -> dict[str, bool]:
    """Which finished steps are older than their recall gap.

    The honest half of spacing for a project. A lesson can quiz an old concept
    fairly; a guided project cannot (see ``project_ladder.recall_rung``), so
    rather than invent a review card whose answer is sitting in the milestone list
    beside it, the list marks the steps a learner is overdue to prove again — and
    the check that proves them is the one this surface already has: running the
    program.
    """
    moment = _now() if now is None else now
    completed = set(getattr(project, "completed_milestone_ids", None) or [])
    flags: dict[str, bool] = {}
    for milestone in getattr(project, "milestones", None) or []:
        concept = project_ladder.milestone_concept(project.course_id, milestone.id)
        raw = (getattr(project, "concept_state", None) or {}).get(concept) or {}
        flags[milestone.id] = milestone.id in completed \
            and concept_view(raw, concept).due_for_review(moment)
    return flags


def record_production(project: Any, milestone: Any, *, passed: bool, helped: bool = False,
                      now: float | None = None) -> dict[str, Any]:
    """Record the outcome of the workspace's NEXT gate against the milestone's concept.

    ``helped`` covers both ways a learner can be carried: an applied AI suggestion,
    and a workspace that already satisfied the checks before they were taught the
    step (the old auto-skip cascade, which used to award XP for milestones nobody
    had met). Completion and XP are unchanged — the learner did build it — but
    evidence is only earned by producing it unaided after meeting the idea.
    """
    moment = _now() if now is None else now
    concept = project_ladder.milestone_concept(project.course_id, milestone.id)
    build_id = project_ladder.rung_id(milestone.id, Stage.INDEPENDENT)
    introduce_id = project_ladder.rung_id(milestone.id, Stage.INTRODUCE)
    state = _state(project, concept)

    if passed:
        state.cleared_steps.add(build_id)
        taught = introduce_id in state.cleared_steps
        if helped or not taught:
            state.hinted_steps.add(build_id)
        else:
            state.evidence.add("independent")
        # Seed the clock either way: a milestone built with help is exactly the one
        # that should come back for retrieval.
        if state.last_recall_at is None:
            state.last_recall_at = moment
            state.interval_seconds = project_ladder.BASE_INTERVAL_SECONDS
    else:
        state.misses[build_id] = state.misses.get(build_id, 0) + 1
    _save(project, concept, state)
    return {
        "concept": concept,
        "evidence": sorted(state.evidence),
        "demonstrated": concept_view(_persist(state), concept).demonstrated,
        "helped": bool(helped) or introduce_id not in state.cleared_steps,
    }


def project_summary(project: Any) -> dict[str, Any]:
    """What the learner actually did, for the end-of-project screen.

    Completion percentages say a project finished; this says what was learned and
    where the help came from, which is the part worth showing someone who just
    spent an hour on it.
    """
    built: list[str] = []
    unaided: list[str] = []
    helped: list[str] = []
    for milestone in project.milestones:
        concept = project_ladder.milestone_concept(project.course_id, milestone.id)
        state = _state(project, concept)
        if milestone.id in (project.completed_milestone_ids or []):
            built.append(milestone.title or milestone.id)
        if "independent" in state.evidence:
            unaided.append(milestone.title or milestone.id)
        elif milestone.id in (project.completed_milestone_ids or []):
            helped.append(milestone.title or milestone.id)
    due = sum(1 for is_due in milestone_review_flags(project).values() if is_due)
    # What the checks proved, kept beside what the learner did. A step can be finished,
    # built unaided, and still say nothing about whether the program works - which is
    # exactly the state a directory of empty classes leaves a project in.
    kinds = [(project.milestone_progress.get(m.id) or MilestoneProgress(milestone_id=m.id)).evidence
             for m in project.milestones]
    return {
        "evidence_executed": sum(1 for k in kinds if k == "executed"),
        "evidence_structural": sum(1 for k in kinds if k == "structural"),
        "evidence_unverified": sum(1 for k in kinds if k == "unverified"),
        "title": project.title,
        "milestones_built": built,
        "built_unaided": unaided,
        "completed_with_help": helped,
        "xp": int(getattr(project, "xp", 0) or 0),
        "files_changed": project.files_changed_count(),
        "tech_stack": list(getattr(project, "tech_stack", None) or []),
        "steps_overdue_for_review": due,
    }
