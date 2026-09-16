"""Data models for the Create Course "guided project" experience.

These models are used ONLY by the Create Course project-workspace feature. They
are intentionally separate from the lesson/curriculum models so that the rest of
Patchwork (Learn, Practice, Quests, native + standard generated courses) is not
affected in any way.

A guided project turns a source tutorial (YouTube video/playlist transcript, a
pasted transcript, or an uploaded tutorial) into ONE persistent project that the
learner builds across a sequence of source-grounded milestones. The learner owns
the code; the backend only inspects the workspace and verifies milestones.
"""
from __future__ import annotations

import time

from pydantic import BaseModel, Field


# ─── Verification ────────────────────────────────────────────────────────────

# Behaviour/outcome based checks. They deliberately verify RESULTS (a symbol is
# defined, a module is imported, the program runs, expected output appears) so
# that a learner's valid alternative implementation is still accepted.
VERIFICATION_KINDS = (
    "import",           # source imports a module (AST)
    "symbol",           # a top-level function/class/variable is defined (AST)
    "function_call",    # a given function/method is called anywhere (AST)
    "code_contains",    # the workspace code references a token/pattern (grounded, concept-level)
    "run_ok",           # the entry file runs without raising (sandbox)
    "stdout_contains",  # running the entry file prints a substring (sandbox)
    "file_exists",      # a file path exists in the workspace
)


class VerificationCheck(BaseModel):
    kind: str = Field(pattern=r"^(import|symbol|function_call|code_contains|run_ok|stdout_contains|file_exists)$")
    # For code_contains, target may be a "|"-separated list of acceptable tokens.
    target: str = Field(default="", max_length=400)
    description: str = Field(default="", max_length=280)


class Microstep(BaseModel):
    """A concise, Duolingo-style instruction: one observation, one action, one hint."""

    observation: str = Field(default="", max_length=400)
    action: str = Field(default="", max_length=400)
    hint: str = Field(default="", max_length=400)


class WorkspaceFile(BaseModel):
    path: str = Field(min_length=1, max_length=200)
    content: str = Field(default="", max_length=200_000)


class Milestone(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    order: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=160)
    # What the SOURCE actually does at this step (source-grounded, not invented).
    source_grounded_description: str = Field(default="", max_length=2000)
    source_quote: str = Field(default="", max_length=2000)
    microstep: Microstep = Field(default_factory=Microstep)
    why: str = Field(default="", max_length=2000)
    # Rich, engaging teaching content (LLM-enriched, source-grounded; falls back
    # to concise deterministic copy).
    hook: str = Field(default="", max_length=200)
    teach: str = Field(default="", max_length=1200)
    example: str = Field(default="", max_length=1200)
    celebrate: str = Field(default="", max_length=200)
    checks: list[VerificationCheck] = Field(default_factory=list)
    xp_reward: int = Field(default=20, ge=0, le=200)


class MilestoneProgress(BaseModel):
    milestone_id: str
    status: str = Field(default="pending", pattern=r"^(pending|current|completed)$")
    attempts: int = 0
    passed_check_descriptions: list[str] = Field(default_factory=list)
    last_feedback: str = Field(default="", max_length=2000)


class ProjectCourse(BaseModel):
    """The full persistent state of one guided project."""

    course_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    language: str = Field(default="python", max_length=40)

    # Source provenance (grounding).
    source_type: str = Field(default="transcript", max_length=40)
    source_url: str = Field(default="", max_length=500)
    source_hash: str = Field(default="", max_length=64)
    source_summary: str = Field(default="", max_length=4000)
    source_excerpt: str = Field(default="", max_length=20_000)

    project_goal: str = Field(default="", max_length=2000)
    # Polished learner-facing overview (not raw transcript).
    course_intro: str = Field(default="", max_length=2000)
    tech_stack: list[str] = Field(default_factory=list)
    entry_file: str = Field(default="main.py", max_length=200)

    milestones: list[Milestone] = Field(default_factory=list)

    # Runtime / learner-owned state.
    workspace_files: list[WorkspaceFile] = Field(default_factory=list)
    current_milestone_index: int = Field(default=0, ge=0)
    completed_milestone_ids: list[str] = Field(default_factory=list)
    milestone_progress: dict[str, MilestoneProgress] = Field(default_factory=dict)
    xp: int = Field(default=0, ge=0)
    completed: bool = False

    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    # ── Derived helpers ──────────────────────────────────────────────────────

    def milestone_by_id(self, milestone_id: str) -> Milestone | None:
        for m in self.milestones:
            if m.id == milestone_id:
                return m
        return None

    def completion_percent(self) -> int:
        if not self.milestones:
            return 0
        return round(100 * len(self.completed_milestone_ids) / len(self.milestones))

    def files_changed_count(self) -> int:
        return sum(1 for f in self.workspace_files if f.content.strip())


# ─── API request/response projections ────────────────────────────────────────


class ProjectMilestoneView(BaseModel):
    id: str
    order: int
    title: str
    status: str
    source_grounded_description: str
    source_quote: str = ""
    microstep: Microstep
    why: str = ""
    hook: str = ""
    teach: str = ""
    example: str = ""
    celebrate: str = ""
    xp_reward: int


class ProjectCheckResult(BaseModel):
    description: str
    passed: bool
    detail: str = ""


class ProjectView(BaseModel):
    """Public projection returned to the frontend (never leaks solution code)."""

    course_id: str
    title: str
    language: str
    source_type: str
    source_url: str = ""
    source_summary: str = ""
    project_goal: str
    course_intro: str = ""
    tech_stack: list[str]
    entry_file: str
    milestones: list[ProjectMilestoneView]
    workspace_files: list[WorkspaceFile]
    current_milestone_index: int
    completed_milestone_ids: list[str]
    xp: int
    completed: bool
    completion_percent: int
    files_changed: int

    @classmethod
    def from_project(cls, project: ProjectCourse) -> "ProjectView":
        # Sanitize learner-facing strings at the API boundary so already-persisted
        # courses with caption dumps still render as concise tutorial copy.
        from .project_copy import learner_facing_fields

        views: list[ProjectMilestoneView] = []
        for m in project.milestones:
            prog = project.milestone_progress.get(m.id)
            status = prog.status if prog else "pending"
            fields = learner_facing_fields(
                m,
                entry_file=project.entry_file or "main.py",
                project_title=project.title,
                project_goal=project.project_goal,
            )
            views.append(
                ProjectMilestoneView(
                    id=m.id,
                    order=m.order,
                    title=m.title,
                    status=status,
                    source_grounded_description=fields["source_grounded_description"],
                    source_quote=fields["source_quote"],
                    microstep=Microstep(
                        observation=fields["observation"],
                        action=fields["action"],
                        hint=fields["hint"],
                    ),
                    why=fields["why"],
                    hook=fields["hook"],
                    teach=fields["teach"],
                    example=fields["example"],
                    celebrate=fields["celebrate"],
                    xp_reward=m.xp_reward,
                )
            )
        return cls(
            course_id=project.course_id,
            title=project.title,
            language=project.language,
            source_type=project.source_type,
            source_url=project.source_url,
            source_summary=project.source_summary,
            project_goal=project.project_goal,
            course_intro=project.course_intro,
            tech_stack=project.tech_stack,
            entry_file=project.entry_file,
            milestones=views,
            workspace_files=project.workspace_files,
            current_milestone_index=project.current_milestone_index,
            completed_milestone_ids=project.completed_milestone_ids,
            xp=project.xp,
            completed=project.completed,
            completion_percent=project.completion_percent(),
            files_changed=project.files_changed_count(),
        )
