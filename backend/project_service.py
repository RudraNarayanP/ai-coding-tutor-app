"""Orchestration for the Create Course guided-project experience.

This ties together ingestion → source-grounded planning → persistent workspace →
milestone verification (the NEXT gate) → read-only AI guidance. It is used only
by the Create Course project endpoints and does not touch any other subsystem.
"""
from __future__ import annotations

from .project_models import (
    MilestoneProgress,
    ProjectCheckResult,
    ProjectCourse,
    ProjectView,
    WorkspaceFile,
)
from .project_enrich import enrich_project
from . import project_planner
from .project_planner import (
    plan_project,
    scrub_project_learner_copy,
    validate_project,
)
from .project_sandbox import project_terminal_sandbox
from . import project_session
from .project_store import ProjectStore
from .project_verifier import evaluate_milestone, evidence_of, run_workspace
from .source_ingestion import IngestionError, SourceIngestionService
from .source_quality import (
    LlmSourceAnalyzer,
    ProjectGroundingError,
    evaluate_ingestion,
    evaluate_project,
    evaluate_source_with_analyzer,
    require_accept,
)


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

    Quality gate stages (all run before ``store.create``):
      1. ingestion — extraction produced usable material
      2. analysis — source can support a coherent coding project
      3. planning — ``plan_project`` (goal + milestone sequence)
      4. pre-workspace — final check; rejected sources are never persisted

    Raises IngestionError (bad/unavailable source) or ProjectGroundingError /
    SourceQualityError (source can't be turned into a real project).
    """
    doc = await ingestion_service.ingest(
        material_type=material_type,
        content=content,
        title=title,
        filename=filename,
    )
    # Stage 1 — ingestion quality (empty / failed extraction → insufficient).
    require_accept(evaluate_ingestion(doc))

    # Stage 2 — source analysis (optional AI refine on borderline cases only).
    #
    # A repository skips it. `evaluate_source` looks for prose that teaches — a build
    # verb, a step list, an instructional heading — and a finished program has no
    # reason to contain any of that, so the prose gate would refuse every repository on
    # absence of a tutorial. `plan_repository` judges the same four questions about the
    # object it has instead (licensed, readable, ordered, gradable) and cannot be
    # bypassed, because it runs on every path that has a `doc.repo`.
    analyzer = LlmSourceAnalyzer(provider) if provider is not None else None
    if doc.repo is None:
        require_accept(await evaluate_source_with_analyzer(doc, title=title, analyzer=analyzer))

    # Stage 3 — curriculum planning (also re-checks source + milestone quality).
    project = plan_project(doc, title=title, course_id=course_id)

    # Stage 4 — final quality check; never persist a rejected/insufficient course.
    require_accept(evaluate_project(project, stage="pre_workspace"))
    require_accept(evaluate_project(project, stage="pre_display"))
    # Loading applies this same gate in require_usable_project(). Without it a
    # project could be saved, listed under "Resume", and then refuse to open.
    require_usable_project(project)

    # Best-effort: make the course rich/engaging via the LLM. Never blocks creation.
    try:
        await enrich_project(provider, project)
    except Exception:  # noqa: BLE001 — copy enrichment must not block a valid course
        pass
    validate_project(project)
    # Re-check after enrichment so LLM copy cannot smuggle a rejected course through.
    require_accept(evaluate_project(project, stage="pre_display"))
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


async def exec_terminal(
    project: ProjectCourse,
    command: str,
    stdin: str = "",
) -> dict:
    """Run one shell command inside the project's isolated Docker terminal."""
    files = [{"path": f.path, "content": f.content} for f in project.workspace_files]
    result = await project_terminal_sandbox.exec_command(
        project.course_id,
        command,
        files=files,
        stdin=stdin,
    )
    return {
        "command": result.command,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "exit_code": result.exit_code,
        "cwd": result.cwd,
        "error": result.error,
        "ran_ok": result.exit_code == 0,
    }


async def destroy_terminal(course_id: str) -> None:
    await project_terminal_sandbox.destroy(course_id)


async def evaluate_next(store: ProjectStore, executor, project: ProjectCourse, *, helped: bool = False) -> dict:
    """The NEXT progression gate.

    Inspects the *current* workspace, verifies the current source-defined
    milestone, auto-skips any already-satisfied milestones (so a learner who
    worked ahead is credited), and stops at the first incomplete milestone with
    concise guidance. Idempotent: re-running never double-awards XP.

    Completion and evidence are separate claims. A milestone the workspace already
    satisfied, or one finished after applying an AI suggestion, still completes and
    still pays its XP — the learner does have the code — but it earns no evidence,
    so the ladder keeps its retrieval rung and the summary says it was helped.
    ``helped`` is the client's own account of applying a suggestion; being carried
    by an already-complete workspace needs no report, because no teaching rung was
    ever acknowledged.
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
            evidence = evidence_of(milestone, results)
            xp = store.complete_milestone(
                project,
                milestone,
                feedback=step_feedback(evidence),
                passed_check_descriptions=[r.description for r in results if r.passed],
                evidence=evidence,
            )
            record = project_session.record_production(
                project, milestone, passed=True, helped=helped
            )
            advanced.append(
                {
                    "milestone_id": milestone.id,
                    "title": milestone.title,
                    "xp_awarded": xp,
                    "already_completed": xp == 0,
                    # What this step's checks proved: a name in a file, or the program
                    # running. Kept separate from `unaided`, which answers who produced
                    # it - the two are independent, and merging them is how "the learner
                    # typed `class Value: pass`" comes to read as an accomplishment.
                    "evidence": evidence,
                    # `unaided`, not `demonstrated`: a project step earns one kind
                    # of evidence, and the ladder's bar for demonstrated is two.
                    # Shipping the stricter word would invite a UI to light up a
                    # badge that can never light.
                    "unaided": not record["helped"],
                }
            )
            store.set_current(project, idx + 1)
            continue

        # First incomplete milestone — stop and guide.
        feedback = _first_failure_feedback(results)
        store.record_attempt(project, milestone, feedback)
        project_session.record_production(project, milestone, passed=False, helped=helped)
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
            "summary": None,
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
        "feedback": completion_feedback(project),
        "stdout": last_stdout,
        "stderr": last_stderr,
        "xp": project.xp,
        "completion_percent": 100,
        "completed": True,
        "summary": project_session.project_summary(project),
    }


def completion_feedback(project: ProjectCourse) -> str:
    """What finishing this project is evidence *of*, stated honestly.

    "You built the whole thing" was once the only answer, and a workspace of
    `class Value: pass` files earned it: passing every check the grader can run is not
    the same claim as the program working, and the two come apart completely when the
    offline sandbox cannot install the dependency the program needs. So the sentence is
    derived from the evidence each step recorded rather than asserted.
    """
    kinds = [(project.milestone_progress.get(m.id) or MilestoneProgress(milestone_id=m.id)).evidence
             for m in project.milestones]
    ran = sum(1 for k in kinds if k == "executed")
    unproven = sum(1 for k in kinds if k == "unverified")
    if unproven:
        return ("Steps finished - but the program was never seen to run, because the "
                "practice sandbox is missing a dependency it needs. Nothing here has "
                "checked that your project works.")
    if ran:
        return ("Project complete, and the program ran: the last step executed the files "
                "you wrote.")
    return ("Project complete. Every step was checked against your code's shape - that "
            "the files, names and imports are there. Nothing here ran the program, so "
            "that it works is not something this app has verified.")


def step_feedback(evidence: str) -> str:
    """The line recorded against a completed step, worded to what it proved."""
    if evidence == "executed":
        return "Verified: your program ran."
    return "Step met: the checks on your code passed."


def _first_failure_feedback(results: list[ProjectCheckResult]) -> str:
    for r in results:
        if not r.passed:
            return r.detail or f"Not done yet: {r.description}"
    return "Keep going."


def list_learner_projects(store: ProjectStore) -> list[dict]:
    """The resume list, marked with whether each entry can actually be opened.

    Listing and opening must use the same predicate. They did not: a course saved
    before the usability rules existed was offered as resumable, and clicking it
    answered 422. Filtering the row out instead would hide data the learner can
    only delete from this screen, so the row stays and carries its reason.
    """
    rows: list[dict] = []
    for summary in store.list_summaries():
        row = dict(summary)
        project = store.get(summary["course_id"])
        problem = project_planner.usability_problem(project) if project else None
        row["usable"] = problem is None
        row["unusable_reason"] = problem or ""
        rows.append(row)
    return rows


def require_usable_project(project: ProjectCourse) -> None:
    """Block saved courses that lack enough implementation structure to be a real project."""
    problem = project_planner.usability_problem(project)
    if problem:
        raise ProjectGroundingError(
            f"This saved course is not a guided project: {problem} "
            "Try a build-along tutorial that actually implements a program."
        )


def to_learner_view(project: ProjectCourse) -> ProjectView:
    """Public Create Course view: never send raw transcript as lesson copy."""
    cleaned = project.model_copy(deep=True)
    scrub_project_learner_copy(cleaned)
    cleaned.source_summary = ""
    # `set(dict)` would yield every milestone id, not the due ones — the flags are
    # a mapping, so the values have to be filtered. Found in the browser: every
    # step, including untouched ones, wore the ↻ badge.
    flags = project_session.milestone_review_flags(project)
    return ProjectView.from_project(
        cleaned, review_due={mid for mid, due in flags.items() if due}
    )


def _milestone_payload(project: ProjectCourse, idx: int) -> dict:
    view = to_learner_view(project)
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
    from .project_copy import learner_facing_fields

    fields = (
        learner_facing_fields(
            milestone,
            entry_file=project.entry_file or "main.py",
            project_title=project.title,
            project_goal=project.project_goal,
        )
        if milestone
        else {}
    )
    base = {
        "milestone_id": milestone.id if milestone else None,
        "observation": fields.get("observation", ""),
        "action": fields.get("action", ""),
        "hint": fields.get("hint", ""),
        "why": fields.get("why", ""),
        "source_quote": fields.get("source_quote", ""),
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
            f"Source step: {fields.get('source_quote') or fields.get('source_grounded_description') or milestone.title}\n"
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
