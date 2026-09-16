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
import os
import threading
from pathlib import Path

from .sandbox import SandboxError

class ProgressionStore:
    def __init__(self, curriculum: Curriculum, storage_path: Path | None = None) -> None:
        self._lock = threading.Lock()
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
        self._completed_materials: set[str] = set()
        self._attempts: dict[str, int] = {}
        self._last_results: dict[str, str] = {}
        self._xp: int = 0
        self._level: int = 1
        self._load()

    def _load(self) -> None:
        if self.storage_path and self.storage_path.exists():
            with self._lock:
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
                        self._completed_materials.update(data.get("completed_material_ids", []))
                        self._attempts.update(
                            {k: int(v) for k, v in (data.get("attempt_counts") or {}).items()}
                        )
                        self._last_results.update(data.get("last_results") or {})
                        self._xp = int(data.get("xp", 0))
                        self._level = int(data.get("level", 1))
                except Exception:
                    pass

    def _save(self) -> None:
        if self.storage_path:
            with self._lock:
                try:
                    payload = {
                        "completed_lesson_ids": sorted(self._completed),
                        "mastered_lesson_ids": sorted(self._mastered),
                        "skipped_lesson_ids": sorted(self._skipped),
                        "completed_sublesson_ids": sorted(self._completed_sublessons),
                        "completed_exercise_ids": sorted(self._completed_exercises),
                        "completed_material_ids": sorted(self._completed_materials),
                        "attempt_counts": dict(self._attempts),
                        "last_results": dict(self._last_results),
                        "xp": self._xp,
                        "level": self._level,
                    }
                    tmp_path = self.storage_path.with_suffix(f".tmp_{os.getpid()}_{id(self)}")
                    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                    tmp_path.replace(self.storage_path)
                except Exception:
                    pass

    def state(self) -> ProgressionState:
        with self._lock:
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
                completed_material_ids=sorted(self._completed_materials),
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

    def mark_material_completed(self, material_id: str) -> None:
        self._completed_materials.add(material_id)
        self._save()

    def mark_exercise_completed(self, exercise_id: str) -> None:
        self._completed_exercises.add(exercise_id)
        self._save()

    def mark_sublesson_completed(self, sublesson_id: str) -> None:
        self._completed_sublessons.add(sublesson_id)
        self._save()

    def record_attempt(self, exercise_id: str, passed: bool) -> int:
        """Record a grading attempt for an exercise and persist it. Returns the attempt count."""
        self._attempts[exercise_id] = self._attempts.get(exercise_id, 0) + 1
        self._last_results[exercise_id] = "correct" if passed else "incorrect"
        self._save()
        return self._attempts[exercise_id]

    def attempt_count(self, exercise_id: str) -> int:
        return self._attempts.get(exercise_id, 0)

    def last_result(self, exercise_id: str) -> str | None:
        return self._last_results.get(exercise_id)

    def reset(self) -> None:
        self._completed.clear()
        self._mastered.clear()
        self._skipped.clear()
        self._completed_sublessons.clear()
        self._completed_exercises.clear()
        self._attempts.clear()
        self._last_results.clear()
        self._xp = 0
        self._level = 1
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
            sec_id = getattr(lesson, "section_id", "section-1")
            sec_title = getattr(lesson, "section_title", "Section 1")
            test_out = getattr(lesson, "test_out_eligible", False)
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
                    section_id=sec_id,
                    section_title=sec_title,
                    unit_id=uid,
                    unit_title=utitle,
                    type=ltype,
                    test_out_eligible=test_out,
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

    def _static_execution(self, lesson, language: str, code: str) -> dict:
        """Simulate a sandbox result for non-Python code via solution comparison."""
        solution = getattr(lesson, "solution_code", None)
        if solution and solution.strip():
            ok = self._normalize_code(code) == self._normalize_code(solution)
            return {
                "tests": [
                    {
                        "name": test.name,
                        "passed": ok,
                        "error": None if ok else "Static check: your code does not match the expected solution yet.",
                        "stdout": "",
                        "stderr": "",
                        "execution_time_ms": 0,
                    }
                    for test in lesson.tests
                ],
                "stdout": "",
                "stderr": "",
                "execution_time_ms": 0,
                "error": None,
            }
        return {
            "tests": [],
            "stdout": "",
            "stderr": "",
            "execution_time_ms": 0,
            "error": f"{language} code execution needs the Docker runner, which is unavailable.",
        }

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
        if lang.lower().strip() != "python":
            # No multi-language runner exists: grade statically against the
            # canonical solution so RUN CODE stays useful without Docker.
            execution = self._static_execution(lesson, lang, code)
        else:
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

    def _find_exercise(self, lesson: LessonDefinition, exercise_id: str):
        for sub in lesson.sublessons:
            for ex in sub.exercises:
                if ex.id == exercise_id:
                    return ex
        for ex in lesson.mastery_exam:
            if ex.id == exercise_id:
                return ex
        return None

    async def _execute_tests(self, lang: str, code: str, tests: list) -> dict:
        if lang.lower().strip() != "python":
            fake_lesson = type("L", (), {"tests": tests, "solution_code": ""})()
            return self._static_execution(fake_lesson, lang, code)
        return await self.executor.run(
            {
                "language": lang,
                "code": code,
                "tests": [test.model_dump() for test in tests],
            }
        )

    def _tests_from_execution(self, tests_spec: list, execution: dict) -> tuple[list[TestResult], bool]:
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
            for test in tests_spec
        ]
        required_names = {test.name for test in tests_spec if test.required}
        passed = bool(tests) and all(
            test.passed for test in tests if test.name in required_names
        )
        return tests, passed

    async def run_exercise_code(
        self, lesson_id: str, exercise_id: str, code: str
    ) -> ProgressionResult:
        """Run tests for a single exercise without persisting completion."""
        lesson = self.get_lesson(lesson_id)
        lang = self.get_lesson_language(lesson_id)
        exercise = self._find_exercise(lesson, exercise_id)
        if exercise is None:
            raise KeyError(f"Exercise '{exercise_id}' not found in lesson '{lesson_id}'.")
        if not exercise.tests:
            raise KeyError(f"Exercise '{exercise_id}' has no runnable tests.")

        execution = await self._execute_tests(lang, code, exercise.tests)
        tests, passed = self._tests_from_execution(exercise.tests, execution)
        return ProgressionResult(
            lesson_id=lesson_id,
            passed=passed,
            completed=False,
            next_lesson_id=None,
            tests=tests,
            stdout=execution.get("stdout", ""),
            stderr=execution.get("stderr", ""),
            execution_time_ms=execution.get("execution_time_ms", 0),
            error=execution.get("error"),
        )

    @staticmethod
    def _normalize_code(code: str) -> str:
        """Whitespace-insensitive, case-sensitive normalization for code comparison."""
        return "".join(str(code or "").split())

    def _grade_code_static(self, exercise, code: str) -> tuple[bool, str]:
        """Grade a code submission without executing it.

        Used for non-Python languages (no multi-language runner exists). Compares against the
        canonical solution or expected answer instead of running tests.
        """
        submitted = self._normalize_code(code)
        if not submitted:
            return False, "Your answer is empty — write some code first, then check again."

        expected = exercise.correct_answer
        if isinstance(expected, str) and expected.strip():
            passed = self._normalize_code(expected) in submitted
            feedback = "Correct!" if passed else (exercise.explanation or "Your code doesn't contain the expected answer yet.")
            return passed, feedback
        if isinstance(expected, list) and expected:
            missing = [e for e in expected if self._normalize_code(e) not in submitted]
            passed = not missing
            feedback = "Correct!" if passed else (exercise.explanation or "Your code is missing an expected part — try again.")
            return passed, feedback

        solution = getattr(exercise, "solution_code", None)
        if solution and solution.strip():
            passed = submitted == self._normalize_code(solution)
            if passed:
                return True, "Correct! Your code matches the expected solution."
            return False, exercise.explanation or "Not quite — compare your code with what the question asks for and try again."

        return True, "Submitted successfully!"

    async def grade_exercise(self, exercise, user_input: dict, language: str) -> tuple[bool, str]:
        ex_type = exercise.type.lower().strip()
        expected = exercise.correct_answer

        if ex_type in ("mcq", "true_false", "output_prediction", "debugging", "identify_error", "short_answer"):
            ans_raw = user_input.get("answer")
            ans = str(ans_raw).strip() if ans_raw is not None else ""
            exp = str(expected).strip() if expected is not None else ""

            passed = (ans.lower() == exp.lower()) if exp else True

            # Index match support: if user sent option index (0-based)
            if not passed and exercise.options and ans.isdigit():
                idx = int(ans)
                if 0 <= idx < len(exercise.options):
                    opt_val = exercise.options[idx].strip()
                    passed = (opt_val.lower() == exp.lower())

            feedback = "Correct!" if passed else (exercise.explanation or f"Expected: {exercise.correct_answer}")
            return passed, feedback

        elif ex_type in ("fill_blank", "code_completion"):
            raw_ans = user_input.get("answers", user_input.get("answer", []))
            if isinstance(raw_ans, str):
                answers = [raw_ans]
            elif isinstance(raw_ans, list):
                answers = raw_ans
            else:
                answers = [str(raw_ans)]

            def norm_exp(v):
                s = str(v).strip()
                if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
                    s = s[1:-1].strip()
                return s.lower()

            def norm_ans(ans_v, exp_v):
                s = str(ans_v).strip()
                e_str = str(exp_v).strip() if exp_v is not None else ""
                if "=" in s and "=" not in e_str:
                    s = s.split("=", 1)[1].strip()
                if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
                    s = s[1:-1].strip()
                return s.lower()

            if isinstance(expected, list):
                exp_norm = [norm_exp(e) for e in expected]
                ans_norm = [
                    norm_ans(answers[i], expected[i]) if i < len(expected) else norm_ans(answers[i], "")
                    for i in range(len(answers))
                ]
                raw_ans_norm = [str(a).strip().lower() for a in answers]
                raw_exp_norm = [str(e).strip().lower() for e in expected]
                passed = (raw_ans_norm == raw_exp_norm) or (ans_norm == exp_norm)
            elif isinstance(expected, (str, int, float, bool)):
                exp_norm = norm_exp(expected)
                ans_norm = norm_ans(answers[0], expected) if answers else ""
                raw_ans0 = str(answers[0]).strip().lower() if answers else ""
                raw_exp = str(expected).strip().lower()
                passed = (raw_ans0 == raw_exp) or (ans_norm == exp_norm)
            else:
                passed = True

            feedback = "Correct!" if passed else (exercise.explanation or "Check your inputs and try again.")
            return passed, feedback

        elif ex_type == "select_multiple":
            raw_sel = user_input.get("answers", user_input.get("answer", user_input.get("selected", [])))
            if isinstance(raw_sel, (str, int, float, bool)):
                raw_sel = [raw_sel]

            selected_norm = set(str(s).strip().lower() for s in raw_sel)

            if isinstance(expected, list):
                exp_norm = set(str(e).strip().lower() for e in expected)
            elif isinstance(expected, str):
                exp_norm = {expected.strip().lower()}
            else:
                exp_norm = set()

            passed = (selected_norm == exp_norm)
            feedback = "Correct!" if passed else (exercise.explanation or "Some choices were incorrect.")
            return passed, feedback

        elif ex_type == "ordering":
            raw_order = user_input.get("order", user_input.get("answers", []))
            if isinstance(raw_order, str):
                raw_order = [raw_order]

            order_norm = [str(o).strip().lower() for o in raw_order]
            if isinstance(expected, list):
                exp_norm = [str(e).strip().lower() for e in expected]
            elif expected is not None:
                exp_norm = [str(expected).strip().lower()]
            else:
                exp_norm = []

            passed = (order_norm == exp_norm)
            feedback = "Correct sequence!" if passed else (exercise.explanation or "Order is incorrect.")
            return passed, feedback

        elif ex_type == "matching":
            user_pairs = user_input.get("pairs", user_input.get("answers", []))
            target = {}
            if exercise.pairs:
                target = {p.left.strip().lower(): p.right.strip().lower() for p in exercise.pairs}
            elif isinstance(expected, dict):
                target = {str(k).strip().lower(): str(v).strip().lower() for k, v in expected.items()}

            got = {}
            if isinstance(user_pairs, list):
                for p in user_pairs:
                    if isinstance(p, dict):
                        got[str(p.get("left", "")).strip().lower()] = str(p.get("right", "")).strip().lower()
            elif isinstance(user_pairs, dict):
                got = {str(k).strip().lower(): str(v).strip().lower() for k, v in user_pairs.items()}

            passed = (got == target) if target else True
            feedback = "All pairs matched!" if passed else (exercise.explanation or "Some pairs do not match.")
            return passed, feedback

        elif ex_type in ("code", "tiny_coding", "identify_mistake"):
            code = str(user_input.get("code") or user_input.get("answer") or "")
            if exercise.tests and language.lower().strip() == "python":
                res = await self.executor.run({"language": language, "code": code, "tests": [t.model_dump() for t in exercise.tests]})
                passed = bool(res.get("passed", False))
                feedback = "All tests passed!" if passed else "Some tests failed."
                return passed, feedback
            elif exercise.tests or exercise.solution_code or exercise.correct_answer:
                return self._grade_code_static(exercise, code)
            else:
                passed = bool(code.strip())
                feedback = "Submitted successfully!" if passed else "Please provide an answer."
                return passed, feedback

        if expected is not None:
            ans = str(user_input.get("answer", user_input.get("code", ""))).strip().lower()
            exp = str(expected).strip().lower()
            passed = (ans == exp)
            return passed, "Correct!" if passed else (exercise.explanation or "Try again.")

        return True, "Exercise completed!"

    async def submit_exercise(self, lesson_id: str, sublesson_id: str | None, exercise_id: str, payload: dict) -> dict:
        lesson = self.get_lesson(lesson_id)
        lang = self.get_lesson_language(lesson_id)
        store = self.stores.get(lang, self.store)

        # Find target exercise in sublessons or mastery exam
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
            raise KeyError(f"Exercise '{exercise_id}' not found in lesson '{lesson_id}'.")

        passed, feedback = await self.grade_exercise(target_ex, payload, lang)
        xp_awarded = 0
        attempt_count = store.record_attempt(exercise_id, passed)

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

            # Check if all sublessons in lesson are completed
            if lesson.sublessons:
                all_sub_ids = {sub.id for sub in lesson.sublessons}
                if all_sub_ids.issubset(set(store.state().completed_sublesson_ids)):
                    if lesson.id not in store.state().completed_lesson_ids:
                        store.mark_completed(lesson.id)
                        xp_awarded += store.add_xp(lesson.xp_reward or 25)

        state = store.state()
        progress = self.lesson_progress(lesson_id)
        return {
            "exercise_id": exercise_id,
            "passed": passed,
            "state": "correct" if passed else "incorrect",
            "attempt_count": attempt_count,
            "feedback": feedback,
            "xp_awarded": xp_awarded,
            "total_xp": state.xp,
            "level": state.level,
            "explanation": target_ex.explanation,
            "next_action": progress["next_action"],
            "lesson_completed": progress["lesson_completed"],
            "next_lesson_id": progress["next_lesson_id"],
            "progress": progress["progress"],
        }

    def lesson_progress(self, lesson_id: str) -> dict:
        """Authoritative lesson progress derived from the progression store.

        The current exercise is the first exercise (in canonical flattened order)
        that is not yet completed. If every exercise is completed the lesson is
        complete. `next_action` tells the client what the learner should do next.
        """
        lesson = self.get_lesson(lesson_id)
        lang = self.get_lesson_language(lesson_id)
        store = self.stores.get(lang, self.store)
        state = store.state()

        all_exercises = [ex for sub in lesson.sublessons for ex in sub.exercises]
        completed = set(state.completed_exercise_ids)
        remaining = [ex for ex in all_exercises if ex.id not in completed]

        lesson_completed = bool(all_exercises) and not remaining
        # Lessons without sublesson exercises (pure code lessons) complete via run_lesson.
        if not all_exercises:
            lesson_completed = lesson_id in state.completed_lesson_ids

        next_lesson_id = state.current_lesson_id if lesson_completed else None

        return {
            "lesson_id": lesson_id,
            "total_exercises": len(all_exercises),
            "completed_exercise_ids": sorted(completed & {ex.id for ex in all_exercises}),
            "attempt_counts": {k: v for k, v in store._attempts.items() if k in {ex.id for ex in all_exercises}},
            "last_results": {k: v for k, v in store._last_results.items() if k in {ex.id for ex in all_exercises}},
            "lesson_completed": lesson_completed,
            "next_action": "lesson_complete" if lesson_completed else "answer",
            "next_lesson_id": next_lesson_id,
            "progress": {
                "completed": len(all_exercises) - len(remaining),
                "total": len(all_exercises),
            },
        }

    async def run_test_out(self, lesson_id: str, submissions: dict) -> dict:
        """Run mastery exam for a mega lesson to test out / jump ahead."""
        lesson = self.get_lesson(lesson_id)
        lang = self.get_lesson_language(lesson_id)
        store = self.stores.get(lang, self.store)

        if not getattr(lesson, "test_out_eligible", False):
            return {"passed": False, "error": "This lesson does not support test-out.", "score_pct": 0}

        if not self._is_unlocked(lesson_id):
            return {"passed": False, "error": "Prerequisite lessons must be completed before testing out.", "score_pct": 0}

        # Gather exam exercises (mastery_exam or all sublesson exercises)
        exam_exercises = lesson.mastery_exam or [ex for sub in lesson.sublessons for ex in sub.exercises]
        if not exam_exercises:
            raise ValueError(f"No exam exercises available for test-out in lesson '{lesson_id}'.")

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
