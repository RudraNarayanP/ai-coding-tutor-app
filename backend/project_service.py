"""Orchestration for the Create Course guided-project experience.

This ties together ingestion → source-grounded planning → persistent workspace →
milestone verification (the NEXT gate) → read-only AI guidance. It is used only
by the Create Course project endpoints and does not touch any other subsystem.
"""
from __future__ import annotations

from .project_models import (
    ProjectCheckResult,
    ProjectCourse,
    ProjectView,
    WorkspaceFile,
)
from .project_enrich import enrich_project
from .project_planner import ProjectGroundingError, plan_project
from .project_store import ProjectStore
from .project_verifier import evaluate_milestone, run_workspace
from .source_ingestion import IngestionError, SourceIngestionService


async def build_project(
    ingestion_service: SourceIngestionService,
    store: ProjectStore,
    *,
    material_type: str,
    content: str,
    title: str,
    filename: str | None,
    course_id: str,
    provider=None,
) -> ProjectCourse:
    """Ingest a source and build a persistent, source-grounded guided project.

    Raises IngestionError (bad/unavailable source) or ProjectGroundingError
    (source can't be turned into a real project) — both surfaced as clear errors.
    """
    doc = await ingestion_service.ingest(
        material_type=material_type,
        content=content,
        title=title,
        filename=filename,
    )
    # If a YouTube source came back without a transcript (a common case when
    # automated transcript access is blocked for the server's IP/region), tell the
    # learner exactly how to proceed instead of fabricating a project from a bare
    # title.
    if doc.source_type in ("youtube_url", "youtube_playlist") and doc.access_level == "titles_only":
        raise ProjectGroundingError(
            "YouTube didn't return a transcript for this video, so there's no source "
            "content to ground a project in. Open the video on YouTube, click the "
            "\"…\" menu → \"Show transcript\", copy the text, then use the "
            "\"Paste Transcript / Notes\" option here to build the guided project."
        )
    project = plan_project(doc, title=title, course_id=course_id)
    # Best-effort: make the course rich/engaging via the LLM. Never blocks creation.
    try:
        await enrich_project(provider, project)
    except Exception:  # noqa: BLE001
        pass
    return store.create(project)


async def run_project(store: ProjectStore, executor, project: ProjectCourse, stdin: str = "") -> dict:
    """Run the persistent workspace and return terminal output."""
    result = await run_workspace(executor, project.workspace_files, project.entry_file, stdin=stdin)
    return {
        "ran_ok": result["ran_ok"],
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "error": result.get("error"),
    }


async def evaluate_next(store: ProjectStore, executor, project: ProjectCourse) -> dict:
    """The NEXT progression gate.

    Inspects the *current* workspace, verifies the current source-defined
    milestone, auto-skips any already-satisfied milestones (so a learner who
    worked ahead is credited), and stops at the first incomplete milestone with
    concise guidance. Idempotent: re-running never double-awards XP.
    """
    advanced: list[dict] = []
    last_checks: list[ProjectCheckResult] = []
    last_stdout = ""
    last_stderr = ""

    # Guard against pathological loops; there are never more milestones than this.
    for _ in range(len(project.milestones) + 1):
        idx = project.current_milestone_index
        if idx >= len(project.milestones):
            break
        milestone = project.milestones[idx]
        passed, results, stdout, stderr = await evaluate_milestone(
            executor, project, milestone, project.workspace_files
        )
        last_checks = results
        last_stdout = stdout
        last_stderr = stderr

        if passed:
            xp = store.complete_milestone(
                project,
                milestone,
                feedback="Milestone verified.",
                passed_check_descriptions=[r.description for r in results if r.passed],
            )
            advanced.append(
                {
                    "milestone_id": milestone.id,
                    "title": milestone.title,
                    "xp_awarded": xp,
                    "already_completed": xp == 0,
                }
            )
            store.set_current(project, idx + 1)
            continue

        # First incomplete milestone — stop and guide.
        feedback = _first_failure_feedback(results)
        store.record_attempt(project, milestone, feedback)
        store.persist(project)
        return {
            "status": "incomplete",
            "advanced": advanced,
            "current_milestone": _milestone_payload(project, idx),
            "checks": [r.model_dump() for r in results],
            "feedback": feedback,
            "stdout": last_stdout,
            "stderr": last_stderr,
            "xp": project.xp,
            "completion_percent": project.completion_percent(),
            "completed": project.completed,
        }

    # All milestones complete.
    project.completed = True
    store.set_current(project, len(project.milestones))
    store.persist(project)
    return {
        "status": "project_complete",
        "advanced": advanced,
        "current_milestone": None,
        "checks": [r.model_dump() for r in last_checks],
        "feedback": "Project complete — you built the whole thing from the source!",
        "stdout": last_stdout,
        "stderr": last_stderr,
        "xp": project.xp,
        "completion_percent": 100,
        "completed": True,
    }


def _first_failure_feedback(results: list[ProjectCheckResult]) -> str:
    for r in results:
        if not r.passed:
            return r.detail or f"Not done yet: {r.description}"
    return "Keep going."


def _milestone_payload(project: ProjectCourse, idx: int) -> dict:
    view = ProjectView.from_project(project)
    for mv in view.milestones:
        if mv.order == idx + 1:
            return mv.model_dump()
    return view.milestones[idx].model_dump() if idx < len(view.milestones) else {}


async def guidance(executor, provider, project: ProjectCourse, question: str = "") -> dict:
    """Read-only AI guidance for the current milestone.

    Always returns a concise, deterministic microstep. If an AI provider is
    configured, it best-effort adds a short suggestion and an optional code
    snippet. The suggestion is NEVER applied automatically — the frontend offers
    an explicit "Apply suggestion" action owned by the learner.
    """
    idx = min(project.current_milestone_index, len(project.milestones) - 1)
    milestone = project.milestones[idx] if project.milestones else None
    base = {
        "milestone_id": milestone.id if milestone else None,
        "observation": milestone.microstep.observation if milestone else "",
        "action": milestone.microstep.action if milestone else "",
        "hint": milestone.microstep.hint if milestone else "",
        "why": milestone.why if milestone else "",
        "source_quote": milestone.source_quote if milestone else "",
        "suggestion": None,
        "suggestion_note": "",
        "provider_used": None,
    }
    if provider is None or milestone is None:
        return base

    try:
        current_code = "\n\n".join(
            f"# {f.path}\n{f.content}" for f in project.workspace_files if f.path.endswith(".py")
        )[:6000]
        system = (
            "You are a concise coding tutor for a guided project. You are READ-ONLY: "
            "never claim to edit the learner's files. Ground everything in the provided source. "
            "Reply in <=60 words with a single actionable hint. Optionally include ONE minimal code "
            "snippet fenced in ``` that the learner may choose to apply. Do not solve unrelated steps."
        )
        user = (
            f"Project goal: {project.project_goal}\n"
            f"Current milestone: {milestone.title}\n"
            f"Source step: {milestone.source_quote or milestone.source_grounded_description}\n"
            f"What must be true: {'; '.join(c.description for c in milestone.checks)}\n"
            f"Learner question: {question or '(none)'}\n"
            f"Learner's current code:\n{current_code}\n"
        )
        text = await provider.generate_structured(system, user, max_tokens=220)
        snippet = _extract_code_block(text)
        base["suggestion_note"] = _strip_code_block(text).strip()[:600]
        base["suggestion"] = snippet
        base["provider_used"] = getattr(provider, "provider_id", None) or getattr(provider, "name", None)
    except Exception:  # noqa: BLE001 — guidance is best-effort; never break the workspace.
        pass
    return base


def _extract_code_block(text: str) -> str | None:
    import re

    m = re.search(r"```(?:[a-zA-Z0-9_+-]*)\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip("\n")
    return None


def _strip_code_block(text: str) -> str:
    import re

    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)
