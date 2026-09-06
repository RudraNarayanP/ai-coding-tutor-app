from typing import Protocol

from .lesson_models import (
    Curriculum,
    LessonDefinition,
    LessonSummary,
    ProgressionResult,
    ProgressionState,
    TestResult,
)


class ExecutionService(Protocol):
    async def run(self, payload: dict) -> dict: ...


import json
from pathlib import Path

class ProgressionStore:
    def __init__(self, curriculum: Curriculum, storage_path: Path | None = None) -> None:
        self._lessons = curriculum.lessons
        self._lessons_by_id: dict[str, LessonDefinition] = {
            lesson.id: lesson for lesson in self._lessons
        }
        self.storage_path = storage_path
        self._completed: set[str] = set()
        self._load()

    def _load(self) -> None:
        if self.storage_path and self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    valid_ids = {lid for lid in data if lid in self._lessons_by_id}
                    self._completed.update(valid_ids)
            except Exception:
                pass

    def _save(self) -> None:
        if self.storage_path:
            try:
                self.storage_path.write_text(
                    json.dumps(sorted(self._completed)), encoding="utf-8"
                )
            except Exception:
                pass

    def state(self) -> ProgressionState:
        current = next(
            (lesson.id for lesson in self._lessons if lesson.id not in self._completed),
            None,
        )
        return ProgressionState(
            completed_lesson_ids=sorted(
                self._completed,
                key=lambda lesson_id: self._lessons_by_id[lesson_id].order,
            ),
            current_lesson_id=current,
        )

    def mark_completed(self, lesson_id: str) -> None:
        if lesson_id in self._lessons_by_id:
            self._completed.add(lesson_id)
            self._save()


class LessonEngine:
    def __init__(
        self,
        executor: ExecutionService,
        store: ProgressionStore,
        curriculum: Curriculum,
    ) -> None:
        self.executor = executor
        self.curriculum = curriculum
        self.store = store

    def get_lesson(self, lesson_id: str) -> LessonDefinition:
        try:
            return next(l for l in self.curriculum.lessons if l.id == lesson_id)
        except StopIteration:
            raise KeyError(lesson_id)

    def summaries(self) -> list[LessonSummary]:
        state = self.store.state()
        return [
            LessonSummary(
                id=lesson.id,
                title=lesson.title,
                order=lesson.order,
                difficulty=lesson.difficulty,
                duration_minutes=lesson.duration_minutes,
                status=(
                    "completed"
                    if lesson.id in state.completed_lesson_ids
                    else "current"
                    if lesson.id == state.current_lesson_id
                    else "locked"
                ),
            )
            for lesson in self.curriculum.lessons
        ]

    def _is_unlocked(self, lesson_id: str) -> bool:
        lesson = self.get_lesson(lesson_id)
        current_id = self.store.state().current_lesson_id
        if current_id is None:
            # All lessons completed — still allow re-running any
            return True
        current_order = self.get_lesson(current_id).order
        return lesson.order <= current_order

    async def run_lesson(self, lesson_id: str, code: str) -> ProgressionResult:
        lesson = self.get_lesson(lesson_id)
        if not self._is_unlocked(lesson_id):
            return ProgressionResult(
                lesson_id=lesson_id,
                passed=False,
                completed=False,
                tests=[],
                error="lesson_locked",
            )
        execution = await self.executor.run(
            {"code": code, "tests": [test.model_dump() for test in lesson.tests]}
        )
        result_by_name = {
            result.get("name"): result for result in execution.get("tests", [])
        }
        tests = [
            TestResult(
                name=test.name,
                required=test.required,
                description=test.description,
                passed=bool(result_by_name.get(test.name, {}).get("passed", False)),
                error=result_by_name.get(test.name, {}).get("error"),
                stdout=result_by_name.get(test.name, {}).get("stdout", ""),
                stderr=result_by_name.get(test.name, {}).get("stderr", ""),
                execution_time_ms=result_by_name.get(test.name, {}).get(
                    "execution_time_ms", 0
                ),
            )
            for test in lesson.tests
        ]
        required_names = set(
            lesson.completion_requirements.required_test_names
        ) or {test.name for test in lesson.tests if test.required}
        passed = bool(tests) and all(
            test.passed for test in tests if test.name in required_names
        )
        if passed:
            self.store.mark_completed(lesson_id)
        state = self.store.state()
        return ProgressionResult(
            lesson_id=lesson_id,
            passed=passed,
            completed=lesson_id in state.completed_lesson_ids,
            next_lesson_id=state.current_lesson_id,
            tests=tests,
            stdout=execution.get("stdout", ""),
            stderr=execution.get("stderr", ""),
            execution_time_ms=execution.get("execution_time_ms", 0),
            error=execution.get("error"),
        )
