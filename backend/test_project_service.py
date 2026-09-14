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
