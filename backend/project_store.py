"""Persistent, idempotent store for Create Course guided projects.

State is authoritative on the backend and persisted to disk so a learner can
resume a project across sessions. Progress mutations (milestone completion, XP)
are idempotent: completing an already-completed milestone never double-awards XP
or duplicates completion events.

State lives under ``curriculum/generated/projects/`` which is already gitignored,
so learner runtime state is never committed.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from .project_models import (
    Milestone,
    MilestoneProgress,
    ProjectCourse,
    WorkspaceFile,
)

logger = logging.getLogger("patchwork.project_store")


class ProjectStore:
    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._cache: dict[str, ProjectCourse] = {}
        self._load_all()

    # ── persistence ──────────────────────────────────────────────────────────

    def _path(self, course_id: str) -> Path:
        return self.storage_dir / f"{course_id}.json"

    def _load_all(self) -> None:
        for path in self.storage_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                project = ProjectCourse(**data)
                self._cache[project.course_id] = project
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"Failed to load project {path.name}: {exc}")

    def _persist(self, project: ProjectCourse) -> None:
        try:
            self._path(project.course_id).write_text(
                json.dumps(project.model_dump(), indent=2), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to persist project {project.course_id}: {exc}")

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def create(self, project: ProjectCourse) -> ProjectCourse:
        with self._lock:
            self._init_progress(project)
            self._cache[project.course_id] = project
            self._persist(project)
            return project

    def get(self, course_id: str) -> ProjectCourse | None:
        return self._cache.get(course_id)

    def list_summaries(self) -> list[dict]:
        out: list[dict] = []
        for p in sorted(self._cache.values(), key=lambda x: x.updated_at, reverse=True):
            out.append(
                {
                    "course_id": p.course_id,
                    "title": p.title,
                    "language": p.language,
                    "completion_percent": p.completion_percent(),
                    "completed": p.completed,
                    "milestone_count": len(p.milestones),
                    "updated_at": p.updated_at,
                }
            )
        return out

    def delete(self, course_id: str) -> bool:
        with self._lock:
            existed = self._cache.pop(course_id, None) is not None
            path = self._path(course_id)
            if path.exists():
                try:
                    path.unlink()
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"Failed to delete project {course_id}: {exc}")
            return existed

    # ── mutations ────────────────────────────────────────────────────────────

    def _init_progress(self, project: ProjectCourse) -> None:
        for idx, m in enumerate(project.milestones):
            if m.id not in project.milestone_progress:
                project.milestone_progress[m.id] = MilestoneProgress(
                    milestone_id=m.id,
                    status="current" if idx == project.current_milestone_index else "pending",
                )

    def save_workspace(self, course_id: str, files: list[WorkspaceFile]) -> ProjectCourse | None:
        with self._lock:
            project = self._cache.get(course_id)
            if not project:
                return None
            project.workspace_files = files
            project.updated_at = time.time()
            self._persist(project)
            return project

    def complete_milestone(
        self,
        project: ProjectCourse,
        milestone: Milestone,
        feedback: str,
        passed_check_descriptions: list[str],
    ) -> int:
        """Idempotently mark a milestone complete. Returns XP awarded (0 if it was
        already complete)."""
        prog = project.milestone_progress.setdefault(
            milestone.id, MilestoneProgress(milestone_id=milestone.id)
        )
        prog.passed_check_descriptions = passed_check_descriptions
        prog.last_feedback = feedback
        if milestone.id in project.completed_milestone_ids:
            prog.status = "completed"
            return 0
        project.completed_milestone_ids.append(milestone.id)
        prog.status = "completed"
        project.xp += milestone.xp_reward
        return milestone.xp_reward

    def record_attempt(self, project: ProjectCourse, milestone: Milestone, feedback: str) -> None:
        prog = project.milestone_progress.setdefault(
            milestone.id, MilestoneProgress(milestone_id=milestone.id)
        )
        prog.attempts += 1
        prog.last_feedback = feedback

    def set_current(self, project: ProjectCourse, index: int) -> None:
        index = max(0, min(index, len(project.milestones)))
        project.current_milestone_index = index
        for i, m in enumerate(project.milestones):
            prog = project.milestone_progress.setdefault(
                m.id, MilestoneProgress(milestone_id=m.id)
            )
            if m.id in project.completed_milestone_ids:
                prog.status = "completed"
            elif i == index:
                prog.status = "current"
            else:
                prog.status = "pending"

    def persist(self, project: ProjectCourse) -> None:
        with self._lock:
            project.updated_at = time.time()
            self._persist(project)
