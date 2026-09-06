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
        store: ProgressionStore | None = None,
        curriculum: Curriculum | None = None,
        curriculums: dict[str, Curriculum] | None = None,
        stores: dict[str, ProgressionStore] | None = None,
    ) -> None:
        self.executor = executor
        self.curriculums: dict[str, Curriculum] = curriculums or {}
        if curriculum:
            self.curriculums[curriculum.course.language] = curriculum
        self.stores: dict[str, ProgressionStore] = stores or {}
        if store and curriculum:
            self.stores[curriculum.course.language] = store
        self.active_language = "python"

    @property
    def curriculum(self) -> Curriculum:
        return self.curriculums.get(self.active_language) or next(iter(self.curriculums.values()))

    @property
    def store(self) -> ProgressionStore:
        return self.stores.get(self.active_language) or next(iter(self.stores.values()))

    def get_lesson(self, lesson_id: str, language: str | None = None) -> LessonDefinition:
        target_lang = (language or self.active_language).lower().strip()
        if target_lang in self.curriculums:
            curr = self.curriculums[target_lang]
            try:
                return next(l for l in curr.lessons if l.id == lesson_id)
            except StopIteration:
                pass
        for curr in self.curriculums.values():
            try:
                return next(l for l in curr.lessons if l.id == lesson_id)
            except StopIteration:
                continue
        raise KeyError(lesson_id)

    def get_lesson_language(self, lesson_id: str) -> str:
        for lang, curr in self.curriculums.items():
            if any(l.id == lesson_id for l in curr.lessons):
                return lang
        return self.active_language

    def get_solution_code(self, lesson: LessonDefinition) -> str:
        if lesson.solution_code:
            return lesson.solution_code
        if lesson.static_hints:
            return "\n".join(lesson.static_hints) + "\n"
        return "# Solution not available.\n"

    def summaries(self, language: str | None = None) -> list[LessonSummary]:
        lang = (language or self.active_language).lower().strip()
        curr = self.curriculums.get(lang, self.curriculum)
        store = self.stores.get(lang, self.store)
        state = store.state()

        lesson_unit_map = {}
        for module in curr.modules:
            for lesson in module.lessons:
                lesson_unit_map[lesson.id] = (module.id, module.title)

        result = []
        for lesson in curr.lessons:
            uid, utitle = lesson_unit_map.get(lesson.id, ("unit-1", "Unit 1"))
            ltype = getattr(lesson, "type", "learn") or "learn"
            status = (
                "completed"
                if lesson.id in state.completed_lesson_ids
                else "current"
                if lesson.id == state.current_lesson_id
                else "locked"
            )
            result.append(
                LessonSummary(
                    id=lesson.id,
                    title=lesson.title,
                    order=lesson.order,
                    difficulty=lesson.difficulty,
                    duration_minutes=lesson.duration_minutes,
                    status=status,
                    unit_id=uid,
                    unit_title=utitle,
                    type=ltype,
                )
            )
        return result

    def _is_unlocked(self, lesson_id: str) -> bool:
        lang = self.get_lesson_language(lesson_id)
        store = self.stores.get(lang, self.store)
        curr = self.curriculums.get(lang, self.curriculum)
        lesson = self.get_lesson(lesson_id, language=lang)
        current_id = store.state().current_lesson_id
        if current_id is None:
            return True
        current_lesson = next((l for l in curr.lessons if l.id == current_id), None)
        if not current_lesson:
            return True
        return lesson.order <= current_lesson.order

    async def run_lesson(self, lesson_id: str, code: str) -> ProgressionResult:
        lesson = self.get_lesson(lesson_id)
        lang = self.get_lesson_language(lesson_id)
        store = self.stores.get(lang, self.store)

        if not self._is_unlocked(lesson_id):
            return ProgressionResult(
                lesson_id=lesson_id,
                passed=False,
                completed=False,
                tests=[],
                error="lesson_locked",
            )
        execution = await self.executor.run(
            {
                "language": lang,
                "code": code,
                "tests": [test.model_dump() for test in lesson.tests],
            }
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
            store.mark_completed(lesson_id)
        state = store.state()
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
