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
        self._mastered: set[str] = set()
        self._skipped: set[str] = set()
        self._completed_sublessons: set[str] = set()
        self._completed_exercises: set[str] = set()
        self._xp: int = 0
        self._level: int = 1
        self._load()

    def _load(self) -> None:
        if self.storage_path and self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    valid_ids = {lid for lid in data if lid in self._lessons_by_id}
                    self._completed.update(valid_ids)
                elif isinstance(data, dict):
                    self._completed.update(data.get("completed_lesson_ids", []))
                    self._mastered.update(data.get("mastered_lesson_ids", []))
                    self._skipped.update(data.get("skipped_lesson_ids", []))
                    self._completed_sublessons.update(data.get("completed_sublesson_ids", []))
                    self._completed_exercises.update(data.get("completed_exercise_ids", []))
                    self._xp = int(data.get("xp", 0))
                    self._level = int(data.get("level", 1))
            except Exception:
                pass

    def _save(self) -> None:
        if self.storage_path:
            try:
                payload = {
                    "completed_lesson_ids": sorted(self._completed),
                    "mastered_lesson_ids": sorted(self._mastered),
                    "skipped_lesson_ids": sorted(self._skipped),
                    "completed_sublesson_ids": sorted(self._completed_sublessons),
                    "completed_exercise_ids": sorted(self._completed_exercises),
                    "xp": self._xp,
                    "level": self._level,
                }
                self.storage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            except Exception:
                pass

    def state(self) -> ProgressionState:
        done_set = self._completed | self._mastered | self._skipped
        current = next(
            (lesson.id for lesson in self._lessons if lesson.id not in done_set),
            None,
        )
        return ProgressionState(
            completed_lesson_ids=sorted(
                [lid for lid in self._completed if lid in self._lessons_by_id],
                key=lambda lesson_id: self._lessons_by_id[lesson_id].order,
            ),
            mastered_lesson_ids=sorted(self._mastered),
            skipped_lesson_ids=sorted(self._skipped),
            completed_sublesson_ids=sorted(self._completed_sublessons),
            completed_exercise_ids=sorted(self._completed_exercises),
            current_lesson_id=current,
            xp=self._xp,
            level=max(1, self._xp // 100 + 1),
        )

    def add_xp(self, amount: int) -> int:
        if amount > 0:
            self._xp += amount
            self._level = max(1, self._xp // 100 + 1)
            self._save()
        return amount

    def mark_exercise_completed(self, exercise_id: str) -> None:
        self._completed_exercises.add(exercise_id)
        self._save()

    def mark_sublesson_completed(self, sublesson_id: str) -> None:
        self._completed_sublessons.add(sublesson_id)
        self._save()

    def mark_completed(self, lesson_id: str) -> None:
        if lesson_id in self._lessons_by_id:
            self._completed.add(lesson_id)
            self._save()

    def mark_mastered(self, lesson_id: str) -> None:
        if lesson_id in self._lessons_by_id:
            self._mastered.add(lesson_id)
            self._completed.add(lesson_id)
            lesson = self._lessons_by_id[lesson_id]
            for sub in lesson.sublessons:
                self._completed_sublessons.add(sub.id)
                self._skipped.add(sub.id)
                for ex in sub.exercises:
                    self._completed_exercises.add(ex.id)
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
            comments = "\n".join(f"# Hint: {hint}" for hint in lesson.static_hints)
            return f"{comments}\n"
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
        xp_awarded = 0
        if passed:
            already_done = lesson_id in store.state().completed_lesson_ids
            store.mark_completed(lesson_id)
            if not already_done:
                xp_awarded = store.add_xp(lesson.xp_reward or 25)

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

    async def grade_exercise(self, exercise, user_input: dict, language: str) -> tuple[bool, str]:
        ex_type = exercise.type.lower().strip()
        expected = exercise.correct_answer

        if ex_type in ("mcq", "true_false", "output_prediction", "debugging"):
            ans = str(user_input.get("answer", "")).strip().lower()
            exp = str(expected or "").strip().lower()
            passed = (ans == exp) if exp else True
            feedback = "Correct!" if passed else exercise.explanation or f"Expected: {exercise.correct_answer}"
            return passed, feedback

        elif ex_type in ("fill_blank", "code_completion"):
            answers = user_input.get("answers", []) or user_input.get("answer", [])
            if isinstance(answers, str):
                answers = [answers]
            answers_norm = [str(a).strip().lower() for a in answers]

            if isinstance(expected, list):
                exp_norm = [str(e).strip().lower() for e in expected]
                passed = (answers_norm == exp_norm)
            elif isinstance(expected, str):
                passed = (len(answers_norm) == 1 and answers_norm[0] == expected.strip().lower())
            else:
                passed = True
            feedback = "Correct!" if passed else exercise.explanation or "Check your inputs and try again."
            return passed, feedback

        elif ex_type == "select_multiple":
            selected = set(str(s).strip().lower() for s in user_input.get("answers", []))
            exp_set = set(str(e).strip().lower() for e in (expected if isinstance(expected, list) else []))
            passed = (selected == exp_set)
            feedback = "Correct!" if passed else exercise.explanation or "Some choices were incorrect."
            return passed, feedback

        elif ex_type == "ordering":
            order = user_input.get("order", [])
            order_norm = [str(o).strip() for o in order]
            exp_norm = [str(e).strip() for e in (expected if isinstance(expected, list) else [])]
            passed = (order_norm == exp_norm)
            feedback = "Correct sequence!" if passed else exercise.explanation or "Order is incorrect."
            return passed, feedback

        elif ex_type == "matching":
            user_pairs = user_input.get("pairs", [])
            target = {p.left.strip().lower(): p.right.strip().lower() for p in exercise.pairs}
            got = {str(p.get("left", "")).strip().lower(): str(p.get("right", "")).strip().lower() for p in user_pairs}
            passed = (got == target)
            feedback = "All pairs matched!" if passed else exercise.explanation or "Some pairs do not match."
            return passed, feedback

        elif ex_type == "code":
            code = user_input.get("code", "")
            if exercise.tests:
                res = await self.executor.run({"language": language, "code": code, "tests": [t.model_dump() for t in exercise.tests]})
                passed = bool(res.get("passed", False))
                feedback = "All tests passed!" if passed else "Some tests failed."
                return passed, feedback
            else:
                passed = bool(code.strip())
                feedback = "Code submitted!" if passed else "Please enter code."
                return passed, feedback

        return True, "Exercise completed!"

    async def submit_exercise(self, lesson_id: str, sublesson_id: str | None, exercise_id: str, payload: dict) -> dict:
        lesson = self.get_lesson(lesson_id)
        lang = self.get_lesson_language(lesson_id)
        store = self.stores.get(lang, self.store)

        # Find target exercise in sublessons or mastery exam or direct
        target_ex = None
        target_sub = None
        for sub in lesson.sublessons:
            for ex in sub.exercises:
                if ex.id == exercise_id:
                    target_ex = ex
                    target_sub = sub
                    break
        if not target_ex:
            for ex in lesson.mastery_exam:
                if ex.id == exercise_id:
                    target_ex = ex
                    break

        if not target_ex:
            # Fallback mock exercise if not found
            from .lesson_models import ExerciseDefinition
            target_ex = ExerciseDefinition(id=exercise_id, type="code", tests=lesson.tests)

        passed, feedback = await self.grade_exercise(target_ex, payload, lang)
        xp_awarded = 0

        if passed:
            already_done = exercise_id in store.state().completed_exercise_ids
            store.mark_exercise_completed(exercise_id)
            if not already_done:
                xp_awarded = store.add_xp(target_ex.xp_reward or 10)

            # Check if all exercises in sublesson are completed
            if target_sub:
                sub_ex_ids = {ex.id for ex in target_sub.exercises}
                if sub_ex_ids.issubset(set(store.state().completed_exercise_ids)):
                    if target_sub.id not in store.state().completed_sublesson_ids:
                        store.mark_sublesson_completed(target_sub.id)
                        xp_awarded += store.add_xp(10)

        state = store.state()
        return {
            "exercise_id": exercise_id,
            "passed": passed,
            "feedback": feedback,
            "xp_awarded": xp_awarded,
            "total_xp": state.xp,
            "level": state.level,
            "explanation": target_ex.explanation,
        }

    async def run_test_out(self, lesson_id: str, submissions: dict) -> dict:
        """Run mastery exam for a mega lesson to test out / jump ahead."""
        lesson = self.get_lesson(lesson_id)
        lang = self.get_lesson_language(lesson_id)
        store = self.stores.get(lang, self.store)

        if not self._is_unlocked(lesson_id):
            return {"passed": False, "error": "Prerequisite lessons must be completed before testing out.", "score_pct": 0}

        # Gather exam exercises (mastery_exam or all sublesson exercises)
        exam_exercises = lesson.mastery_exam or [ex for sub in lesson.sublessons for ex in sub.exercises]
        if not exam_exercises:
            # Fallback if no sublesson exercises exist
            store.mark_mastered(lesson_id)
            xp_bonus = store.add_xp(100)
            return {"passed": True, "score_pct": 100, "xp_awarded": xp_bonus, "total_xp": store.state().xp}

        passed_count = 0
        weak_areas = []

        for ex in exam_exercises:
            sub_payload = submissions.get(ex.id, {})
            passed, _ = await self.grade_exercise(ex, sub_payload, lang)
            if passed:
                passed_count += 1
            else:
                weak_areas.append(ex.title or ex.question or ex.id)

        score_pct = round((passed_count / len(exam_exercises)) * 100)
        passed_exam = score_pct >= 80

        xp_awarded = 0
        if passed_exam:
            already_mastered = lesson_id in store.state().mastered_lesson_ids
            store.mark_mastered(lesson_id)
            if not already_mastered:
                xp_awarded = store.add_xp(100)

        state = store.state()
        return {
            "lesson_id": lesson_id,
            "passed": passed_exam,
            "score_pct": score_pct,
            "passed_count": passed_count,
            "total_questions": len(exam_exercises),
            "xp_awarded": xp_awarded,
            "total_xp": state.xp,
            "level": state.level,
            "weak_areas": weak_areas if not passed_exam else [],
        }
