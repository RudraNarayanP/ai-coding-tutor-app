"""Tests for the NEXT progression gate and idempotent project progress."""
import asyncio
import tempfile
from pathlib import Path

from backend.project_models import (
    Microstep,
    Milestone,
    ProjectCourse,
    VerificationCheck,
    WorkspaceFile,
)
from backend.project_service import evaluate_next
from backend.project_store import ProjectStore


class FakeExecutor:
    """Executor that never needs Docker (used for structural-only milestones)."""

    async def run(self, payload):  # pragma: no cover - not hit by structural checks
        return {"passed": True, "tests": [{"name": "run", "passed": True, "error": None, "stdout": "", "stderr": ""}]}


def _store() -> ProjectStore:
    tmp = tempfile.mkdtemp(prefix="pwproj_")
    return ProjectStore(storage_dir=Path(tmp))


def _structural_project(course_id="project-svc") -> ProjectCourse:
    return ProjectCourse(
        course_id=course_id,
        title="Struct Project",
        source_hash="h",
        project_goal="goal",
        entry_file="main.py",
        milestones=[
            Milestone(id="m1", order=1, title="Setup",
                      checks=[VerificationCheck(kind="file_exists", target="main.py")], xp_reward=10),
            Milestone(id="m2", order=2, title="Import collections",
                      checks=[VerificationCheck(kind="import", target="collections")], xp_reward=20),
            Milestone(id="m3", order=3, title="Define count_words",
                      checks=[VerificationCheck(kind="symbol", target="count_words")], xp_reward=20),
        ],
        workspace_files=[WorkspaceFile(path="main.py", content="")],
    )


def test_next_blocks_until_milestone_complete():
    store = _store()
    project = store.create(_structural_project())
    executor = FakeExecutor()

    # m1 (file_exists main.py) passes; m2 (import collections) not yet done → stop at m2.
    result = asyncio.run(evaluate_next(store, executor, project))
    assert result["status"] == "incomplete"
    assert result["current_milestone"]["title"] == "Import collections"
    # m1 was auto-credited.
    assert any(a["milestone_id"] == "m1" for a in result["advanced"])
    assert project.xp == 10
    assert project.current_milestone_index == 1


def test_next_skips_ahead_when_learner_worked_ahead():
    store = _store()
    project = store.create(_structural_project())
    executor = FakeExecutor()
    # Learner implements BOTH remaining milestones before clicking NEXT once.
    project.workspace_files = [
        WorkspaceFile(path="main.py", content="import collections\ndef count_words(t):\n    return len(t.split())\n")
    ]
    result = asyncio.run(evaluate_next(store, executor, project))
    assert result["status"] == "project_complete"
    # All three milestones credited in a single NEXT.
    credited = {a["milestone_id"] for a in result["advanced"]}
    assert credited == {"m1", "m2", "m3"}
    assert project.completed is True
    assert project.xp == 50


def test_next_is_idempotent_no_duplicate_xp():
    store = _store()
    project = store.create(_structural_project())
    executor = FakeExecutor()
    project.workspace_files = [
        WorkspaceFile(path="main.py", content="import collections\ndef count_words(t):\n    return len(t.split())\n")
    ]
    asyncio.run(evaluate_next(store, executor, project))
    xp_after_first = project.xp
    # Clicking NEXT again (e.g. double submit / refresh) must not re-award XP.
    result2 = asyncio.run(evaluate_next(store, executor, project))
    assert project.xp == xp_after_first == 50
    assert result2["status"] == "project_complete"


def test_incomplete_returns_actionable_feedback():
    store = _store()
    project = store.create(_structural_project())
    executor = FakeExecutor()
    result = asyncio.run(evaluate_next(store, executor, project))
    assert result["feedback"]
    assert any(not c["passed"] for c in result["checks"])


def test_progress_persists_across_store_reload():
    tmp = tempfile.mkdtemp(prefix="pwproj_")
    store = ProjectStore(storage_dir=Path(tmp))
    project = store.create(_structural_project("project-persist"))
    executor = FakeExecutor()
    project.workspace_files = [WorkspaceFile(path="main.py", content="import collections\n")]
    asyncio.run(evaluate_next(store, executor, project))
    # m1 + m2 credited, stop at m3.
    assert project.xp == 30

    # Reload from disk — progress is authoritative and persisted.
    reloaded = ProjectStore(storage_dir=Path(tmp)).get("project-persist")
    assert reloaded is not None
    assert reloaded.xp == 30
    assert set(reloaded.completed_milestone_ids) == {"m1", "m2"}
    assert reloaded.current_milestone_index == 2


# ─── what a completion is evidence of ────────────────────────────────────────
#
# One sentence closes a project, and until now there was one sentence for all three
# things it can mean: the program was watched running, only the shape of the code was
# read, or the run never happened. Measured, the second of those was being sold as the
# first - a repository course was completable by `class Value: pass` files at full XP.

class _MissingDependencyExecutor:
    """The offline sandbox refusing to have a package, which is not the learner's bug."""

    async def run(self, payload):
        return {"passed": False, "tests": [{
            "name": "run", "passed": False, "stdout": "", "stderr": "",
            "error": "ModuleNotFoundError: No module named 'numpy'"}]}


def _run_project(course_id: str) -> ProjectCourse:
    return ProjectCourse(
        course_id=course_id, title="Run Project", source_hash="h", project_goal="goal",
        entry_file="main.py",
        milestones=[Milestone(
            id="m1", order=1, title="Run it", microstep=Microstep(),
            checks=[VerificationCheck(kind="run_ok", target="",
                                       description="Your project runs without errors.")],
            xp_reward=40)],
        workspace_files=[WorkspaceFile(path="main.py", content="print('ok')\n")],
    )


def test_a_project_checked_only_against_code_shape_says_so():
    store = _store()
    project = store.create(_structural_project("project-shape-only"))
    project.workspace_files = [
        WorkspaceFile(path="main.py",
                      content="import collections\ndef count_words(t):\n    return len(t)\n")]
    result = asyncio.run(evaluate_next(store, FakeExecutor(), project))
    assert result["status"] == "project_complete"
    assert {a["evidence"] for a in result["advanced"]} == {"structural"}
    assert "never ran" not in result["feedback"]
    assert "shape" in result["feedback"]
    # The claim reaches the end-of-project screen, not just the log.
    assert result["summary"]["evidence_executed"] == 0
    assert result["summary"]["evidence_structural"] == 3


def test_a_program_observed_running_is_reported_as_executed():
    store = _store()
    project = store.create(_run_project("project-ran"))
    result = asyncio.run(evaluate_next(store, FakeExecutor(), project))
    assert result["advanced"][0]["evidence"] == "executed"
    assert "the program ran" in result["feedback"]


def test_a_run_the_sandbox_could_not_carry_out_is_never_called_a_pass():
    store = _store()
    project = store.create(_run_project("project-unverified"))
    result = asyncio.run(evaluate_next(store, _MissingDependencyExecutor(), project))
    # The learner still finishes the checklist - the gap is the environment's -
    assert result["status"] == "project_complete"
    assert result["advanced"][0]["evidence"] == "unverified"
    # ... but the sentence now refuses to claim the program was shown to work.
    assert "never seen to run" in result["feedback"]
    assert result["summary"]["evidence_unverified"] == 1


def test_the_record_keeps_what_a_step_proved_across_a_reload():
    """The weaker claim has to survive, because the gate never revisits a finished step.

    `evaluate_next` moves the pointer forward and does not re-read a completed milestone,
    so whatever a step proved when it passed is what the project will report forever -
    including after a restart. That is the honest consequence of not re-testing steps
    nobody asked to re-test, and it is why the label has to be right the first time.
    """
    tmp = tempfile.mkdtemp(prefix="pwproj_ev_")
    store = ProjectStore(storage_dir=Path(tmp))
    project = store.create(_run_project("project-evidence-reload"))
    asyncio.run(evaluate_next(store, _MissingDependencyExecutor(), project))
    assert project.milestone_progress["m1"].evidence == "unverified"
    reloaded = ProjectStore(storage_dir=Path(tmp)).get("project-evidence-reload")
    assert reloaded.milestone_progress["m1"].evidence == "unverified"
    assert reloaded.completed is True
