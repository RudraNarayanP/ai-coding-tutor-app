"""The teaching ladder for guided projects: what it teaches, and what it refuses.

These tests cover both halves. The first half is the obvious one — a milestone
must be taught before it is asked for. The second half matters more: several
plausible rung types were built, measured against the projects on disk, and cut
because their answer was already on the screen or their key could not be trusted.
Each of those refusals is asserted here, so re-adding one is a deliberate act
rather than a quiet regression.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from backend import project_ladder, project_session
from backend.project_models import (
    Microstep,
    Milestone,
    ProjectCourse,
    ProjectView,
    VerificationCheck,
    WorkspaceFile,
)

REPO = Path(__file__).resolve().parents[1]
REAL_PROJECT = REPO / "curriculum" / "generated" / "projects" / "project-b8e6f733.json"


def _milestone(mid: str, order: int, *, kind="symbol", target="count_words",
               teach="Counter turns a list into a tally.", example="counts = Counter(words)",
               hook="Tally the words", why="Counting is the whole point of the program.",
               hint=None) -> Milestone:
    return Milestone(
        id=mid,
        order=order,
        title=f"Define {target}",
        source_grounded_description="Count each word in the sample text.",
        source_quote="we will define count_words over the sample",
        microstep=Microstep(observation="Next step from the source:", action=f"Write `{target}`.",
                            hint=hint or f"`{target}` returns a tally."),
        why=why,
        hook=hook,
        teach=teach,
        example=example,
        checks=[VerificationCheck(kind=kind, target=target, description=f"Your code defines `{target}`.")],
        xp_reward=20,
    )


def _project(**over) -> ProjectCourse:
    base = dict(
        course_id="project-demo",
        title="Word Frequency Counter",
        source_hash="h",
        project_goal="Count how often each word appears.",
        entry_file="main.py",
        milestones=[
            Milestone(id="m1", order=1, title="Set up the project",
                      microstep=Microstep(action="Create main.py", hint="Every file persists."),
                      why="One persistent workspace.",
                      checks=[VerificationCheck(kind="file_exists", target="main.py",
                                                description="`main.py` exists.")],
                      xp_reward=10),
            _milestone("m2", 2, target="count_words"),
            _milestone("m3", 3, target="sample", teach="A sample string gives the function input.",
                       example="sample = 'the word the other word'"),
        ],
        workspace_files=[WorkspaceFile(path="main.py", content="")],
    )
    base.update(over)
    return ProjectCourse(**base)


def _walk(project: ProjectCourse) -> dict:
    """Acknowledge every teaching card of the current milestone and return the session."""
    session = project_session.session_for_project(project)
    for step in session["steps"]:
        project_session.mark_rung_seen(project, step["id"])
    return project_session.session_for_project(project)


# ─── teach before asking ─────────────────────────────────────────────────────

def test_a_code_step_is_taught_before_the_learner_is_asked_for_code():
    project = _project()
    project.current_milestone_index = 1
    session = project_session.session_for_project(project)
    stages = [step["stage"] for step in session["steps"]]
    assert stages == ["introduce", "show"], stages
    assert session["build"]["stage"] == "independent"
    # The task itself is the last thing they meet, not the first.
    assert session["steps"][0]["content"]["lead"] == "Tally the words"


def test_a_step_with_nothing_to_show_gets_no_empty_card():
    bare = _milestone("m2", 2, teach="", example="")
    project = _project(milestones=[bare])
    rungs = project_ladder.teaching_rungs(project, bare, project_session._fields(project, bare))
    assert [r["stage"] for r in rungs] == ["introduce"], rungs


def test_a_setup_step_is_still_introduced():
    """`Create main.py` is not a concept, but the learner should be told why it exists."""
    project = _project()
    session = project_session.session_for_project(project)
    assert [s["stage"] for s in session["steps"]] == ["introduce"]
    assert session["steps"][0]["content"]["takeaway"] == "One persistent workspace."


def test_reading_a_card_awards_nothing():
    project = _project()
    project.current_milestone_index = 1
    session = project_session.session_for_project(project)
    result = project_session.mark_rung_seen(project, session["steps"][0]["id"])
    assert result["xp_awarded"] == 0
    assert project.xp == 0


def test_acknowledging_a_card_resumes_the_session_past_it():
    project = _project()
    project.current_milestone_index = 1
    assert project_session.session_for_project(project)["steps"][0]["stage"] == "introduce"
    project_session.mark_rung_seen(project, "m2-introduce")
    assert [s["stage"] for s in project_session.session_for_project(project)["steps"]] == ["show"]


def test_the_bar_promises_the_whole_ladder_and_never_moves_backwards():
    """The generator returns only what is owed; a bar built from that shrinks."""
    project = _project()
    project.current_milestone_index = 1
    first = project_session.session_for_project(project)
    project_session.mark_rung_seen(project, "m2-introduce")
    second = project_session.session_for_project(project)
    assert first["ladder_steps"] == second["ladder_steps"] == 3
    assert first["planned_steps"] == 3 and second["planned_steps"] == 2


def test_only_a_teaching_card_can_be_acknowledged():
    project = _project()
    with pytest.raises(ValueError):
        project_session.mark_rung_seen(project, "m1-independent")
    with pytest.raises(KeyError):
        project_session.mark_rung_seen(project, "not-a-rung")


# ─── evidence, not attendance ────────────────────────────────────────────────

def test_building_it_yourself_after_being_taught_is_evidence():
    project = _project()
    project.current_milestone_index = 1
    _walk(project)
    record = project_session.record_production(project, project.milestones[1], passed=True, helped=False)
    assert record["evidence"] == ["independent"]
    assert record["helped"] is False


def test_an_applied_suggestion_completes_the_step_and_proves_nothing():
    """XP and completion are unchanged; the claim about the learner is."""
    project = _project()
    project.current_milestone_index = 1
    _walk(project)
    record = project_session.record_production(project, project.milestones[1], passed=True, helped=True)
    assert record["evidence"] == []
    assert record["demonstrated"] is False
    assert record["helped"] is True


def test_a_workspace_that_already_had_the_answer_did_not_learn_the_step():
    """The hole the old auto-skip cascade walked straight through.

    Paste a finished file, press NEXT, and every milestone the workspace happens to
    satisfy completed and paid out. Here it still completes — the code is real —
    but with no teaching acknowledged there is no evidence, so the step never
    reports as demonstrated.
    """
    project = _project()
    project.current_milestone_index = 1
    record = project_session.record_production(project, project.milestones[1], passed=True, helped=False)
    assert record["helped"] is True, "never taught is never unaided"
    assert record["evidence"] == []


def test_a_failed_build_records_a_miss_rather_than_evidence():
    project = _project()
    project.current_milestone_index = 1
    _walk(project)
    project_session.record_production(project, project.milestones[1], passed=False, helped=False)
    state = project.concept_state["project-demo:m2"]
    assert state["misses"] == {"m2-independent": 1}
    assert state["evidence"] == []


def test_one_step_being_built_alone_does_not_credit_the_next_one():
    project = _project()
    project.current_milestone_index = 1
    _walk(project)
    project_session.record_production(project, project.milestones[1], passed=True, helped=False)
    assert project.concept_state["project-demo:m2"]["evidence"] == ["independent"]

    project.current_milestone_index = 2
    assert project.concept_state.get("project-demo:m3", {}).get("evidence", []) == []
    session = project_session.session_for_project(project)
    assert session["evidence"] == []


def test_a_single_unaided_step_is_not_called_demonstrated():
    """`demonstrated` needs a second kind of evidence, and a project step has none.

    Naming this honestly is the point: the ladder's own bar is independent
    production *plus* something else, and no derived project rung can supply the
    something else. The view therefore says "built unaided", which is what happened.
    """
    project = _project()
    project.current_milestone_index = 1
    _walk(project)
    record = project_session.record_production(project, project.milestones[1], passed=True, helped=False)
    assert record["evidence"] == ["independent"]
    assert record["demonstrated"] is False
    view = ProjectView.from_project(project, review_due=set())
    row = next(m for m in view.milestones if m.id == "m2")
    assert row.built_unaided is True
    assert next(m for m in view.milestones if m.id == "m3").built_unaided is False


# ─── what the derivation refuses to invent ───────────────────────────────────

def test_no_derived_card_can_be_answered_by_reading_the_milestone_list():
    """Every served card is a teaching card, and nothing here carries an answer key.

    A rung with options and a key would be quizzable; in a project the milestone
    list, the source quote and the check text are all on screen, so any such key is
    also on screen. If someone adds a gradable derived rung, this test is the one
    that has to be argued with.
    """
    project = _project()
    project.current_milestone_index = 2
    project.completed_milestone_ids = ["m1", "m2"]
    session = project_session.session_for_project(project)
    for step in session["steps"]:
        assert step["widget"] == project_ladder.PRESENTATION_WIDGET, step
        assert not step.get("options"), step
        assert "correct_answer" not in step and "correct_order" not in step, step
    assert project_ladder.recall_rung(project, project.milestones[0]) is None


def test_the_build_rung_is_never_rendered_as_a_question():
    project = _project()
    project.current_milestone_index = 1
    session = project_session.session_for_project(project)
    assert all(s["widget"] != project_ladder.BUILD_WIDGET for s in session["steps"])
    assert session["build"]["widget"] == project_ladder.BUILD_WIDGET
    assert session["build"]["checks"] == ["Your code defines `count_words`."]


def test_a_build_rung_cannot_be_acknowledged():
    project = _project()
    project.current_milestone_index = 1
    with pytest.raises(ValueError):
        project_session.mark_rung_seen(project, "m2-independent")


# ─── spacing: flagged, not quizzed ───────────────────────────────────────────

def test_a_finished_step_becomes_due_rather_than_done_forever():
    project = _project()
    project.current_milestone_index = 1
    project.completed_milestone_ids = ["m2"]
    _walk(project)
    project_session.record_production(project, project.milestones[1], passed=True, helped=False)

    now = time.time()
    assert project_session.milestone_review_flags(project, now=now)["m2"] is False
    later = now + project_ladder.BASE_INTERVAL_SECONDS + 1
    assert project_session.milestone_review_flags(project, now=later)["m2"] is True


def test_a_step_never_built_is_never_flagged_for_review():
    project = _project()
    assert project_session.milestone_review_flags(project) == {"m1": False, "m2": False, "m3": False}


# ─── the summary at the end ──────────────────────────────────────────────────

def test_the_summary_says_which_steps_were_built_alone():
    project = _project()
    project.current_milestone_index = 1
    _walk(project)
    project_session.record_production(project, project.milestones[1], passed=True, helped=False)
    project.completed_milestone_ids.append("m2")
    project.current_milestone_index = 2
    _walk(project)
    project_session.record_production(project, project.milestones[2], passed=True, helped=True)
    project.completed_milestone_ids.append("m3")

    summary = project_session.project_summary(project)
    assert summary["built_unaided"] == ["Define count_words"]
    assert summary["completed_with_help"] == ["Define sample"]
    assert set(summary["milestones_built"]) == {"Define count_words", "Define sample"}


def test_the_summary_does_not_flatter_a_learner_who_never_built_anything():
    project = _project()
    project.completed_milestone_ids = ["m1", "m2", "m3"]
    summary = project_session.project_summary(project)
    assert summary["built_unaided"] == []
    assert len(summary["completed_with_help"]) == 3


# ─── against the content that actually ships ─────────────────────────────────

@pytest.mark.skipif(not REAL_PROJECT.exists(), reason="no stored project on this machine")
def test_a_real_stored_project_derives_a_sane_ladder():
    """The derivation must survive real generator output, not just fixtures."""
    project = ProjectCourse(**json.loads(REAL_PROJECT.read_text(encoding="utf-8")))
    seen_cards = 0
    for index, milestone in enumerate(project.milestones):
        project.current_milestone_index = index
        session = project_session.session_for_project(project)
        stages = [s["stage"] for s in session["steps"]]
        assert stages[0] == "introduce", (milestone.id, stages)
        assert set(stages) <= {"introduce", "show"}, (milestone.id, stages)
        assert session["ladder_steps"] == len(session["steps"]) + 1
        assert session["build"] is not None
        seen_cards += len(stages)
    assert seen_cards >= len(project.milestones), "every milestone must teach something"


@pytest.mark.skipif(not REAL_PROJECT.exists(), reason="no stored project on this machine")
def test_a_real_project_records_evidence_only_for_unaided_work():
    project = ProjectCourse(**json.loads(REAL_PROJECT.read_text(encoding="utf-8")))
    project.current_milestone_index = 1
    _walk(project)
    unaided = project_session.record_production(project, project.milestones[1], passed=True, helped=False)
    assert unaided["evidence"] == ["independent"]

    project.current_milestone_index = 2
    _walk(project)
    helped = project_session.record_production(project, project.milestones[2], passed=True, helped=True)
    assert helped["evidence"] == []


@pytest.mark.skipif(not REAL_PROJECT.exists(), reason="no stored project on this machine")
def test_a_learner_can_walk_a_real_project_to_the_end_without_getting_stuck():
    """Every milestone must be finishable from its own session, with no dead ends."""
    project = ProjectCourse(**json.loads(REAL_PROJECT.read_text(encoding="utf-8")))
    for index, milestone in enumerate(project.milestones):
        project.current_milestone_index = index
        session = project_session.session_for_project(project)
        assert session["build"], milestone.id
        for step in list(session["steps"]):
            project_session.mark_rung_seen(project, step["id"])
        after = project_session.session_for_project(project)
        assert after["steps"] == [], (milestone.id, [s["id"] for s in after["steps"]])
        # Teaching done, build still available: the way on is never removed.
        assert after["build"]["id"] == f"{milestone.id}-independent"


def test_only_the_overdue_step_is_flagged_in_the_learner_view():
    """The bug this catches was `set(dict)`: keys, not the true-valued ones.

    It made every milestone read "due for review", including steps nobody had
    touched, and no unit test noticed because the fixture marked one milestone and
    the component only asked about that one. A browser did.
    """
    import time

    from backend import project_service

    project = _project()
    project.current_milestone_index = 2
    project.completed_milestone_ids = ["m2", "m3"]
    now = time.time()
    for mid, age in (("m2", 9000.0), ("m3", 1.0)):
        _state = project.concept_state.setdefault(
            project_ladder.milestone_concept(project.course_id, mid), {}
        )
        _state.update({
            "cleared_steps": [f"{mid}-introduce", f"{mid}-independent"],
            "evidence": ["independent"],
            "last_recall_at": now - age,
            "interval_seconds": project_ladder.BASE_INTERVAL_SECONDS,
        })

    view = project_service.to_learner_view(project)
    flagged = {m.id for m in view.milestones if m.review_due}
    assert flagged == {"m2"}, sorted(flagged)
    unaided = {m.id for m in view.milestones if m.built_unaided}
    assert unaided == {"m2", "m3"}


def test_a_step_never_built_is_not_flagged_as_due_even_with_a_stale_clock():
    project = _project()
    project.concept_state[project_ladder.milestone_concept(project.course_id, "m3")] = {
        "cleared_steps": ["m3-introduce"],
        "evidence": [],
        "last_recall_at": 0.0,
        "interval_seconds": 300.0,
    }
    assert project_session.milestone_review_flags(project, now=time.time())["m3"] is False
