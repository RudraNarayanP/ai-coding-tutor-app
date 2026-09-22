"""The teaching ladder for Create Course guided projects.

A guided project used to be a checklist: a paragraph of copy behind three
collapsed toggles, an editor, and a NEXT button that ran behavioural checks. The
learner met the task before the idea — the same "tester, not teacher" shape the
curriculum ladder was built to replace — and a milestone was *completed* whether
or not anything was learned: paste a working file, press NEXT, collect the XP for
every milestone the workspace happened to satisfy.

This module gives projects the framework the curriculum ladder proved out, by
reusing its vocabulary and its generator rather than copying them:

* rungs and stakes from :mod:`backend.learning_models` — teaching rungs are free
  and award nothing, the production rung is the one that earns evidence;
* ordering, resumption, fading, hint-dependence and review-as-bonus from
  :func:`backend.session_generator.generate_session`;
* one definition of "demonstrated", so a project and a lesson cannot disagree
  about what a learner has shown.

What is deliberately NOT derived, and why
-----------------------------------------
Every rung below is keyed on something that cannot be wrong by construction: the
source's own copy, or the learner's own running program. Two tempting additions
were built, measured against the projects on disk, and cut:

* **Recognition questions.** A quiz needs a key and distractors, and the only
  candidates are identifiers lifted out of a transcript — where ``Define fine``
  and ``Call hallucination`` (both real rows in a stored project) are
  mechanically indistinguishable from ``Define sample`` and ``Call count_words``
  (both real code). No source-text signal separated them: the "appears in a code
  context" test came back false for every identifier in every project, good and
  bad alike. Quizzing a learner on a name that was never code is worse than no
  rung, so the rung is absent instead of invented.
* **A retrieval card over the step list.** The workspace renders every milestone
  title, in order, beside the editor — so "put the steps back in the order you did
  them" and "which check belonged to this step" are both winnable by reading the
  sidebar. A review card you can pass by looking at the answer key is not
  retrieval, and it falsifies the evidence it claims.

Absent rungs are fine: the generator walks whatever a pool actually contains.
Spacing is therefore surfaced rather than quizzed, via
``project_session.milestone_review_flags``, and the closing ``run_ok`` milestone
already retrieves every earlier step at once — by making the learner's own program
work again.
"""

from __future__ import annotations

import re
from typing import Any

from backend.learning_models import Stage, Stakes, default_stakes

#: The widget the curriculum ladder uses for a card with no answer to give, so
#: one runner can render both surfaces.
PRESENTATION_WIDGET = "present"

#: Widget for the rung the learner answers by running their own program. It is
#: never rendered as a question; the workspace's NEXT gate is its answer sheet.
BUILD_WIDGET = "project_build"

#: First retrieval gap for a project milestone, and the growth factor. The same
#: numbers as the curriculum ladder: spacing is the effect, the schedule is not.
BASE_INTERVAL_SECONDS = 300.0

#: Milestones whose checks are about the learner's program rather than a name.
_BUILD_ONLY_KINDS = frozenset({"run_ok", "stdout_contains", "file_exists"})

_CODE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")

#: Enough to tell a line of source code from a sentence about it.
_CODEISH = re.compile(r"[(){}\[\]=]|\bdef\b|\bimport\b|\breturn\b|\bprint\b|^\s*\w+\.\w+", re.MULTILINE)


def milestone_concept(course_id: str, milestone_id: str) -> str:
    """One concept per milestone: the unit a project's ladder teaches and reviews."""
    return f"{course_id}:{milestone_id}"


def rung_id(milestone_id: str, stage: Stage | str) -> str:
    name = stage.value if isinstance(stage, Stage) else str(stage)
    return f"{milestone_id}-{name}"


def check_of(milestone: Any) -> tuple[str, str]:
    checks = getattr(milestone, "checks", None) or []
    if not checks:
        return "", ""
    first = checks[0]
    return str(getattr(first, "kind", "") or ""), str(getattr(first, "target", "") or "")


def is_code_step(milestone: Any) -> bool:
    """True when the milestone is about writing code rather than setting up or running.

    Setup and run milestones still get an introduce rung — the learner should know
    why the entry file exists — but they carry no name to teach and no example to
    show, so pretending otherwise produces an empty card.
    """
    kind, target = check_of(milestone)
    if kind in _BUILD_ONLY_KINDS:
        return False
    return bool(kind) and bool(target) and bool(_CODE_IDENTIFIER.match(target))


def _clip(text: str, limit: int) -> str:
    return (text or "").strip()[:limit]


def teaching_rungs(project: Any, milestone: Any, fields: dict[str, Any]) -> list[dict[str, Any]]:
    """The rungs that teach one milestone, in ladder order.

    These are the same strings the workspace already had — ``hook``, ``why``,
    ``teach``, ``example``, the source quote — but as rungs the learner passes
    through rather than drawers they may never open. A card with nothing to say is
    omitted: an empty "worked example" teaches nothing and costs a tap.
    """
    concept = milestone_concept(project.course_id, milestone.id)
    rungs: list[dict[str, Any]] = []

    lead = _clip(fields.get("hook") or "", 200) or _clip(milestone.title or "", 160)
    say = _clip(fields.get("source_grounded_description") or "", 600)
    why = _clip(fields.get("why") or "", 600)
    quote = _clip(fields.get("source_quote") or "", 600)
    if lead or say or why or quote:
        rungs.append(
            {
                "id": rung_id(milestone.id, Stage.INTRODUCE),
                "concept": concept,
                "stage": Stage.INTRODUCE.value,
                "widget": PRESENTATION_WIDGET,
                "order": 1,
                "stakes": Stakes.FREE.value,
                "title": milestone.title or "",
                "action": "Show me how" if is_code_step(milestone) else "Got it",
                "content": {
                    "lead": lead,
                    "say": say,
                    "takeaway": why,
                    "quote": quote,
                },
                "reason_copy": "first contact with this step: the idea before the task",
            }
        )

    teach = _clip(fields.get("teach") or "", 1200)
    example = _clip(fields.get("example") or "", 1200)
    action = _clip(fields.get("action") or "", 400)
    if teach or example:
        # The enriched `example` is usually the source's code line, but enrichment
        # is best-effort LLM copy and sometimes returns a sentence. Code goes in
        # the monospace block; prose goes in the paragraph, so neither is rendered
        # in the wrong shape.
        as_code = bool(example) and ("\n" in example or bool(_CODEISH.search(example)))
        rungs.append(
            {
                "id": rung_id(milestone.id, Stage.SHOW),
                "concept": concept,
                "stage": Stage.SHOW.value,
                "widget": PRESENTATION_WIDGET,
                "order": 2,
                "stakes": Stakes.FREE.value,
                "title": "What this step looks like",
                "action": "Let's build it",
                "content": {
                    "lead": teach or "Here is the shape of this step.",
                    "lines": [line for line in example.splitlines() if line.strip()] if as_code else [],
                    "say": "" if as_code else example,
                    "takeaway": action,
                },
                "reason_copy": "worked example from the source, before you write it",
            }
        )

    return rungs


def build_rung(project: Any, milestone: Any, fields: dict[str, Any]) -> dict[str, Any]:
    """The production rung: the learner's own program, verified by the NEXT gate.

    It is part of the session so the ladder can reason about it — stakes, evidence,
    hint-dependence, resumption — but it is never rendered as a question, because
    the answer sheet is the workspace and the grader is the existing verifier.
    """
    kind, target = check_of(milestone)
    hints = [_clip(fields.get("hint") or "", 400)] if fields.get("hint") else []
    return {
        "id": rung_id(milestone.id, Stage.INDEPENDENT),
        "concept": milestone_concept(project.course_id, milestone.id),
        "stage": Stage.INDEPENDENT.value,
        "widget": BUILD_WIDGET,
        "order": 10,
        "stakes": default_stakes(Stage.INDEPENDENT).value,
        "title": milestone.title or "",
        "question": _clip(fields.get("action") or milestone.title or "", 400),
        "checks": [c.description for c in (getattr(milestone, "checks", None) or [])],
        "hints": [h for h in hints if h],
        "xp_reward": int(getattr(milestone, "xp_reward", 0) or 0),
        "reason_copy": "production: your code, verified by running it",
    }


def recall_rung(project: Any, milestone: Any) -> dict[str, Any] | None:
    """Retrieval for a finished step. Returns None, and should keep doing so.

    Two shapes were built and measured against the projects on disk before this
    was cut, and both failed the same way: the workspace renders the whole
    milestone list, in order, with titles, beside the editor — so "put the steps
    back in the order you did them" and "which check belonged to this step" are
    both tasks whose answer is on screen while you answer. A review card winnable
    by reading the sidebar is not retrieval, and it falsifies the evidence it
    claims.

    What a project does have, and a lesson does not, is a stronger delayed check
    built in: the closing ``run_ok`` milestone makes the learner's whole program
    work again at the end, which is every step retrieved at once and graded by
    running it. Spacing is therefore surfaced rather than quizzed — see
    ``project_session.milestone_review_flags``.
    """
    return None


def session_pool(project: Any, milestone: Any, fields: dict[str, Any]) -> list[dict[str, Any]]:
    """Every rung the current milestone's session may serve.

    Teaching rungs belong to this milestone's concept; the build rung is the
    milestone's own verification. Retrieval rungs for earlier milestones would
    keep their own concept, which is what lets the shared generator decide whether
    they are due — and what stops a milestone the learner never met from quizzing
    them (rule 9). ``recall_rung`` explains why that path is currently empty.
    """
    pool = teaching_rungs(project, milestone, fields)
    pool.append(build_rung(project, milestone, fields))

    for earlier in project.milestones:
        if earlier.id in (project.completed_milestone_ids or []) and earlier.id != milestone.id:
            recall = recall_rung(project, earlier)
            if recall is not None:
                pool.append(recall)
    return pool


def ladder_steps(project: Any, milestone: Any, fields: dict[str, Any]) -> int:
    """The denominator the progress bar is allowed to promise.

    Counted here rather than from the returned session, because the generator only
    ever returns what is still owed — a bar built from that restarts at 1 of 2 the
    moment a rung is answered.
    """
    return len(teaching_rungs(project, milestone, fields)) + 1
