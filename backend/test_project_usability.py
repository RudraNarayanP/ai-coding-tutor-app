"""Which saved courses count as a buildable guided project, and which do not.

The gate is `usability_problem`, the single rule that both opening a project and
listing it consult. Two things went wrong before it was unified, and both are
asserted here:

* a course whose milestones re-verify the same step passed. One check *is* the
  definition of a step, so "Import collections" twice means the learner does one
  thing, the NEXT gate cascades through both, and the progress bar reports six
  steps for three. Nothing in the old rules looked at what was verified;
* the resume list did not apply the open-time rule at all, so a course that had
  been refused since the rules were tightened stayed on screen as resumable and
  answered 422 when clicked.

The positive fixtures are as important as the negatives. The first draft of the
duplicate rule compared check kinds alone, and it rejected a legitimate pandas
tutorial with two "run it and see" checkpoints — a `run_ok` check has no target,
so "the same check twice" says nothing about it, and a build-along that says
"run it after each function" is normal. That is why the rule is restricted to
checks that name something, and why these shapes are pinned here rather than left
to be discovered by a learner.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend import project_service
from backend.project_models import (
    Microstep,
    Milestone,
    ProjectCourse,
    VerificationCheck,
    WorkspaceFile,
)
from backend.project_planner import is_hollow_guided_project, usability_problem
from backend.project_store import ProjectStore

STORED_PROJECTS = (
    Path(__file__).resolve().parents[1] / "curriculum" / "generated" / "projects"
)


def milestone(order: int, title: str, kind: str, target: str = "") -> Milestone:
    return Milestone(
        id=f"m{order}",
        order=order,
        title=title,
        source_grounded_description=title,
        microstep=Microstep(observation="Next:", action=title, hint="Try it."),
        checks=[VerificationCheck(kind=kind, target=target, description=f"`{target or kind}`")],
        xp_reward=20,
    )


def course(milestones: list[Milestone], course_id: str = "project-under-test") -> ProjectCourse:
    return ProjectCourse(
        course_id=course_id,
        title="Under test",
        source_hash="h",
        project_goal="Build something real",
        entry_file="main.py",
        milestones=milestones,
        workspace_files=[WorkspaceFile(path="main.py", content="")],
    )


def refused(problem: str | None) -> bool:
    return problem is not None


# ─── the shape that shipped: a talk, not a tutorial ──────────────────────────

def LLM_TALK_COURSE(course_id: str = "project-83d16553") -> ProjectCourse:
    """The 14 milestones actually stored for the Karpathy talk.

    Reconstructed rather than read from disk because
    `curriculum/generated/projects/` is gitignored runtime state — a test that
    depends on it would pass on one machine and not another.
    """
    steps = [milestone(1, "Set up the project", "file_exists", "main.py")]
    steps += [milestone(i, "Run and verify", "run_ok") for i in range(2, 8)]
    steps.append(milestone(8, "Call hallucination", "function_call", "hallucination"))
    steps.append(milestone(9, "Call Transformer", "function_call", "Transformer"))
    steps.append(milestone(10, "Call reversal", "function_call", "reversal"))
    steps.append(milestone(11, "Define fine", "symbol", "fine"))
    steps.append(milestone(12, "Call alignment", "function_call", "alignment"))
    steps.append(milestone(13, "Run and verify", "run_ok"))
    steps.append(milestone(14, "Print the result", "stdout_contains"))
    return course(steps, course_id)


def test_a_talk_turned_into_run_checkpoints_is_refused():
    project = LLM_TALK_COURSE()
    assert refused(usability_problem(project))
    assert is_hollow_guided_project(project) is True


def test_the_refusal_names_the_actual_defect():
    """The reason reaches the resume list, so "invalid" is not the best we can say."""
    reason = usability_problem(LLM_TALK_COURSE())
    assert reason
    assert "run the program" in reason.lower() or "one step" in reason.lower()


# ─── the hole: two milestones verifying one step ─────────────────────────────

def test_a_step_verified_twice_is_refused():
    """The old rules counted milestones, never what they checked.

    Five milestones, four "substantive" ones, one run checkpoint: every previous
    predicate was satisfied. But three of them demand `counter` and the learner
    writes it once.
    """
    project = course([
        milestone(1, "Set up the project", "file_exists", "main.py"),
        milestone(2, "Use Counter", "code_contains", "counter"),
        milestone(3, "Counter again", "code_contains", "counter"),
        milestone(4, "Counter as a dict", "code_contains", "counter"),
        milestone(5, "Run and see", "run_ok"),
    ])
    reason = usability_problem(project)
    assert refused(reason)
    assert "Counter again" in reason and "Use Counter" in reason


def test_an_import_that_appears_twice_is_refused():
    project = course([
        milestone(1, "Import collections", "import", "collections"),
        milestone(2, "Import collections again", "import", "collections"),
        milestone(3, "Define count_words", "symbol", "count_words"),
        milestone(4, "Call count_words", "function_call", "count_words"),
        milestone(5, "Run it", "run_ok"),
    ])
    assert refused(usability_problem(project))


def test_case_does_not_make_two_checks_of_one_name():
    """`import Collections` and `import collections` verify the same requirement."""
    project = course([
        milestone(1, "Import collections", "import", "collections"),
        milestone(2, "Bring in Collections", "import", "Collections"),
        milestone(3, "Define parse", "symbol", "parse"),
        milestone(4, "Call parse", "function_call", "parse"),
    ])
    assert refused(usability_problem(project))


# ─── legitimate courses that must keep working ───────────────────────────────

def test_a_real_build_along_is_accepted():
    """The Word Frequency Counter transcript, as the planner actually lays it out."""
    project = course([
        milestone(1, "Set up the project", "file_exists", "main.py"),
        milestone(2, "Import collections", "import", "collections"),
        milestone(3, "Define count_words", "symbol", "count_words"),
        milestone(4, "Define sample", "symbol", "sample"),
        milestone(5, "Call count_words", "function_call", "count_words"),
        milestone(6, "Print the result", "run_ok"),
    ])
    assert usability_problem(project) is None


def test_a_name_defined_and_later_called_is_not_a_duplicate():
    """The same identifier under two different requirements is two real steps."""
    project = course([
        milestone(1, "Import collections", "import", "collections"),
        milestone(2, "Define count_words", "symbol", "count_words"),
        milestone(3, "Define sample", "symbol", "sample"),
        milestone(4, "Call count_words", "function_call", "count_words"),
        milestone(5, "Run it", "run_ok"),
    ])
    assert usability_problem(project) is None


def test_a_tutorial_with_several_run_checkpoints_is_not_called_hollow():
    """The false rejection the first draft of the duplicate rule produced.

    Six things to write and two "run it and see" checkpoints is a normal
    build-along. A `run_ok` check has no target, so two of them are two
    checkpoints at two points in the program, not one step listed twice.
    """
    project = course([
        milestone(1, "Import pandas", "import", "pandas"),
        milestone(2, "Define load_data", "symbol", "load_data"),
        milestone(3, "Define clean", "symbol", "clean"),
        milestone(4, "Call plot", "function_call", "plot"),
        milestone(5, "Define model", "symbol", "model"),
        milestone(6, "Call train", "function_call", "train"),
        milestone(7, "Run what you have", "run_ok"),
        milestone(8, "Run the finished script", "run_ok"),
    ])
    assert usability_problem(project) is None


def test_two_print_checkpoints_are_two_steps_not_one():
    """`code_contains` with different targets is different work, even if repetitive."""
    project = course([
        milestone(1, "Define greet", "symbol", "greet"),
        milestone(2, "Call greet", "function_call", "greet"),
        milestone(3, "Print the greeting", "code_contains", "greeting"),
        milestone(4, "Print the count too", "code_contains", "count"),
        milestone(5, "Run it", "run_ok"),
    ])
    assert usability_problem(project) is None


# ─── listing and opening must agree ──────────────────────────────────────────

@pytest.fixture()
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(storage_dir=tmp_path / "projects")


def test_the_resume_list_marks_a_course_that_cannot_be_opened(store: ProjectStore):
    store.create(course([milestone(1, "Import os", "import", "os"),
                          milestone(2, "Define main", "symbol", "main"),
                          milestone(3, "Call main", "function_call", "main")],
                         "project-good"))
    store.create(LLM_TALK_COURSE())

    rows = {r["course_id"]: r for r in project_service.list_learner_projects(store)}
    assert rows["project-good"]["usable"] is True
    assert rows["project-good"]["unusable_reason"] == ""
    assert rows["project-83d16553"]["usable"] is False
    assert rows["project-83d16553"]["unusable_reason"]
    # Nothing disappears: the only useful action left is Delete, and it lives on
    # this row, so hiding it would strand the file on disk.
    assert len(rows) == 2


def test_the_list_never_admits_something_the_open_path_refuses(store: ProjectStore):
    """One predicate, two call sites — the invariant that broke.

    A row offered as resumable must survive `require_usable_project`, and a row
    marked unusable must be the one that raises. Anything else is a click that
    fails for a reason the screen already knew.
    """
    store.create(course([milestone(1, "Import re", "import", "re"),
                         milestone(2, "Define slugify", "symbol", "slugify"),
                         milestone(3, "Call slugify", "function_call", "slugify")],
                        "project-a"))
    store.create(course([milestone(1, "Use Counter", "code_contains", "counter"),
                         milestone(2, "Counter again", "code_contains", "counter"),
                         milestone(3, "Define main", "symbol", "main")],
                        "project-b"))
    for row in project_service.list_learner_projects(store):
        project = store.get(row["course_id"])
        if row["usable"]:
            project_service.require_usable_project(project)  # must not raise
        else:
            with pytest.raises(Exception, match="not a guided project"):
                project_service.require_usable_project(project)


def test_a_refused_course_cannot_be_opened_but_says_why():
    """End to end: the row explains, and the open route answers 422 with the reason."""
    import uuid

    import backend.main as main_module
    from fastapi.testclient import TestClient

    client = TestClient(main_module.app)
    course_id = f"project-refused-{uuid.uuid4().hex[:6]}"
    main_module.project_store.create(LLM_TALK_COURSE(course_id=course_id))
    try:
        rows = {r["course_id"]: r for r in client.get("/api/create-course/projects").json()}
        assert rows[course_id]["usable"] is False
        assert "run" in rows[course_id]["unusable_reason"].lower()

        response = client.get(f"/api/create-course/projects/{course_id}")
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["error"] == "ungroundable_source"
        # The same words the list row showed, so the screen cannot promise a click
        # that the route then explains differently.
        assert rows[course_id]["unusable_reason"] in detail["message"]
    finally:
        main_module.project_store.delete(course_id)


# ─── against the content that actually exists on this machine ────────────────

@pytest.mark.skipif(not STORED_PROJECTS.is_dir(), reason="no stored projects here")
def test_the_rule_gets_the_real_stored_projects_right():
    """Pinned to the two cases inspected by hand, tolerant of what is on disk.

    The Karpathy-talk course and the Word Frequency Counter tutorials are the real
    content this rule was written against: the first is a talk with checkpoints,
    the others are genuine build-alongs. A change that flips either of those is the
    regression this catches, and it is checked against the actual files rather than
    a fixture that agrees with whatever the code already does.
    """
    paths = sorted(STORED_PROJECTS.glob("*.json"))
    if not paths:
        pytest.skip("no stored projects")
    talk = counter = 0
    for path in paths:
        project = ProjectCourse(**json.loads(path.read_text(encoding="utf-8")))
        if "Talk" in project.title:
            talk += 1
            assert refused(usability_problem(project)), project.title
        elif "Word Frequency" in project.title:
            counter += 1
            assert usability_problem(project) is None, f"{project.title}: {usability_problem(project)}"
    assert talk and counter, f"expected both shapes on disk, saw talk={talk} counter={counter}"
