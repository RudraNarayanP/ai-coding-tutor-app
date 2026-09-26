"""Orchestration for the Create Course guided-project experience.

This ties together ingestion → OpenRouter-owned AI create/discard → persistent
workspace → milestone verification (the NEXT gate) → read-only AI guidance.
Heuristic ``plan_project`` is fallback-only when CREATE_COURSE_HEURISTIC_FALLBACK=1.
"""
from __future__ import annotations

from .ai_course_generator import (
    generate_course_with_ai,
    heuristic_fallback_enabled,
)
from .project_models import (
    ProjectCheckResult,
    ProjectCourse,
    ProjectView,
    WorkspaceFile,
)
from .project_enrich import enrich_project
from .project_planner import (
    is_hollow_guided_project,
    plan_project,
    scrub_project_learner_copy,
    validate_project,
)
from .project_sandbox import project_terminal_sandbox
from .project_store import ProjectStore
from .project_verifier import evaluate_milestone, run_workspace
from .source_ingestion import IngestionError, SourceIngestionService
from .source_quality import (
    LlmSourceAnalyzer,
    ProjectGroundingError,
    evaluate_ingestion,
    evaluate_project,
    evaluate_source,
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
      1. ingestion — extraction produced usable material (empty transcript blocks)
      2. ai_create — configured OpenRouter/provider owns discard vs create + structure
      3. ai_quality_review — same provider self-reviews full course; revise until PASS
         (CREATE_COURSE_QUALITY_MAX_TRIES); store.create runs only after PASS
      4. schema validation — post-model checks; hollow/leak rejection
      5. optional enrich polish (best-effort)

    Heuristic ``plan_project`` runs only if AI is unavailable AND
    CREATE_COURSE_HEURISTIC_FALLBACK=1.

    Raises IngestionError (bad/unavailable source) or ProjectGroundingError /
    SourceQualityError (source can't be turned into a real project).
    """
    doc = await ingestion_service.ingest(
        material_type=material_type,
        content=content,
        title=title,
        filename=filename,
    )
    # Stage 1 — thin preflight: empty / failed extraction must not reach the model.
    require_accept(evaluate_ingestion(doc))

    # Advisory heuristic only — must NOT replace AI ownership of accept/reject.
    # Kept for logging / future telemetry; never raises here.
    try:
        _advisory = evaluate_source(doc, title=title)
        if _advisory.decision != "accept":
            import logging

            logging.getLogger("patchwork.project_service").info(
                "Heuristic advisory=%s source_type=%s (AI still owns create/discard)",
                _advisory.decision,
                _advisory.source_type,
            )
    except Exception:  # noqa: BLE001
        pass

    # Stage 2 — OpenRouter / configured provider owns discard vs create + course.
    project: ProjectCourse | None = None
    if provider is not None:
        project = await generate_course_with_ai(
            provider, doc, title=title, course_id=course_id
        )
    elif heuristic_fallback_enabled():
        # Explicit opt-in safety net — never the default creator.
        analyzer = LlmSourceAnalyzer(provider) if provider is not None else None
        analysis = await evaluate_source_with_analyzer(doc, title=title, analyzer=analyzer)
        require_accept(analysis)
        project = plan_project(doc, title=title, course_id=course_id)
    else:
        raise ProjectGroundingError(
            "Create Course requires a configured AI provider (OpenRouter recommended). "
            "Set AI_PROVIDER and its API key in Settings, or set "
            "CREATE_COURSE_HEURISTIC_FALLBACK=1 to use local planning as a last resort."
        )

    # Stage 3 — schema / hollow / transcript-leak validation after model JSON.
    require_accept(evaluate_project(project, stage="pre_workspace"))
    require_usable_project(project)

    # Best-effort polish only — never the structure owner.
    try:
        # AI-created courses already PASSED the quality review: enrichment may only
        # fill empty fields, never rewrite reviewed teach/action/example.
        await enrich_project(provider, project, fill_only=True)
    except Exception:  # noqa: BLE001 — copy enrichment must not block a valid course
        pass
    scrub_project_learner_copy(project)
    # If banned video/instructor phrases remain after enrich+scrub, re-polish+re-scrub.
    try:
        from .ai_course_generator import local_precheck_course
        from .project_copy import polish_project_copy

        defects = local_precheck_course(project)
        banned_left = [d for d in defects if "Banned learner-facing phrase" in d]
        if banned_left:
            polish_project_copy(project)
            scrub_project_learner_copy(project)
    except Exception:  # noqa: BLE001 — never block create on precheck polish
        pass
    validate_project(project)
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


def require_usable_project(project: ProjectCourse) -> None:
    """Block saved courses that lack enough implementation structure to be a real project."""
    if is_hollow_guided_project(project):
        raise ProjectGroundingError(
            "This saved course does not have enough real coding material to be a guided project. "
            "Delete it from Create and try a build-along tutorial that actually implements a program."
        )


def to_learner_view(project: ProjectCourse) -> ProjectView:
    """Public Create Course view: never send raw transcript as lesson copy."""
    cleaned = project.model_copy(deep=True)
    scrub_project_learner_copy(cleaned)
    cleaned.source_summary = ""
    return ProjectView.from_project(cleaned)


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
