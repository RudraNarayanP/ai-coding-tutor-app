"""Tests for CurriculumLoader and the default loaded curriculum.

Covers:
  - Complete curriculum loads successfully
  - Every lesson has valid required fields
  - Every prerequisite resolves
  - No prerequisite cycles exist
  - Lesson ordering is deterministic
  - No duplicate IDs exist
  - Test spec validation (expected_stdout xor unittest_code)
  - Error paths: missing files, invalid schema, bad prereqs, cycles
"""

import json

import pytest

from backend.curriculum_loader import CurriculumLoadError, CurriculumLoader, load_default_curriculum
from backend.lesson_engine import LessonEngine, ProgressionStore


# ---------------------------------------------------------------------------
# Helpers for building isolated curriculum fixtures
# ---------------------------------------------------------------------------

def write_curriculum(tmp_path, course, modules):
    root = tmp_path / "curriculum"
    (root / "modules").mkdir(parents=True)
    (root / "course.json").write_text(json.dumps(course), encoding="utf-8")
    for filename, module in modules.items():
        (root / "modules" / filename).write_text(json.dumps(module), encoding="utf-8")
    return root


def base_course(path="modules/one.json"):
    return {
        "id": "test-course",
        "title": "Test",
        "language": "python",
        "modules": [{"id": "one", "path": path}],
    }


def base_lesson(lesson_id="variables-01", order=1, concepts=None, prereqs=None):
    return {
        "id": lesson_id,
        "title": "Test lesson",
        "description": "Practice something.",
        "order": order,
        "difficulty": "beginner",
        "duration_minutes": 10,
        "concepts": concepts or ["variables"],
        "prerequisites": prereqs or [],
        "starter_code": "pass",
        "tests": [{"name": "test_something", "unittest_code": "def test_something(self):\n    self.assertEqual(1, 1)"}],
        "completion_requirements": {"required_test_names": ["test_something"]},
    }


def base_module(concepts=None, lessons=None, module_id="one"):
    return {
        "id": module_id,
        "title": "Unit",
        "order": 1,
        "concepts": concepts or [{"id": "variables", "title": "Variables"}],
        "lessons": lessons or [base_lesson()],
    }


# ---------------------------------------------------------------------------
# Default curriculum structural tests
# ---------------------------------------------------------------------------

class TestDefaultCurriculumLoads:
    """The prepared curriculum loads and is internally consistent."""

    def test_curriculum_loads_without_error(self):
        curriculum = load_default_curriculum()
        assert curriculum is not None

    def test_correct_module_count(self):
        curriculum = load_default_curriculum()
        assert len(curriculum.modules) == 13

    def test_correct_concept_count(self):
        curriculum = load_default_curriculum()
        assert len(curriculum.concepts) == 13

    def test_correct_lesson_count(self):
        curriculum = load_default_curriculum()
        assert len(curriculum.lessons) == 13

    def test_lessons_are_ordered_by_order_field(self):
        curriculum = load_default_curriculum()
        orders = [l.order for l in curriculum.lessons]
        assert orders == sorted(orders)

    def test_first_lesson_is_variables(self):
        curriculum = load_default_curriculum()
        assert curriculum.lessons[0].id == "variables-01"

    def test_functions_lesson_is_functions_01(self):
        curriculum = load_default_curriculum()
        assert curriculum.lessons[-1].id == "functions-01"

    def test_no_duplicate_lesson_ids(self):
        curriculum = load_default_curriculum()
        ids = [l.id for l in curriculum.lessons]
        assert len(ids) == len(set(ids))

    def test_no_duplicate_lesson_orders(self):
        curriculum = load_default_curriculum()
        orders = [l.order for l in curriculum.lessons]
        assert len(orders) == len(set(orders))

    def test_no_duplicate_concept_ids(self):
        curriculum = load_default_curriculum()
        assert len(curriculum.concepts) == len(set(curriculum.concepts))

    def test_every_lesson_has_required_fields(self):
        curriculum = load_default_curriculum()
        for lesson in curriculum.lessons:
            assert lesson.id, f"Missing id on lesson {lesson}"
            assert lesson.title, f"Missing title on lesson {lesson.id}"
            assert lesson.description, f"Missing description on lesson {lesson.id}"
            assert lesson.starter_code is not None, f"Missing starter_code on {lesson.id}"
            assert lesson.tests, f"No tests on lesson {lesson.id}"

    def test_every_test_has_a_name(self):
        curriculum = load_default_curriculum()
        for lesson in curriculum.lessons:
            for test in lesson.tests:
                assert test.name, f"Test missing name in lesson {lesson.id}"

    def test_every_test_has_exactly_one_execution_strategy(self):
        """Each test must have either expected_stdout or unittest_code, not both, not neither."""
        curriculum = load_default_curriculum()
        for lesson in curriculum.lessons:
            for test in lesson.tests:
                has_stdout = test.expected_stdout is not None
                has_unittest = test.unittest_code is not None
                assert has_stdout ^ has_unittest, (
                    f"Lesson {lesson.id}, test '{test.name}': "
                    f"expected_stdout={has_stdout}, unittest_code={has_unittest}"
                )

    def test_every_lesson_completion_requirements_reference_existing_tests(self):
        curriculum = load_default_curriculum()
        for lesson in curriculum.lessons:
            test_names = {t.name for t in lesson.tests}
            for req in lesson.completion_requirements.required_test_names:
                assert req in test_names, (
                    f"Lesson {lesson.id}: required test '{req}' not in tests"
                )

    def test_all_lesson_concept_references_resolve(self):
        curriculum = load_default_curriculum()
        for lesson in curriculum.lessons:
            for concept_id in lesson.concepts + lesson.prerequisites:
                assert concept_id in curriculum.concepts, (
                    f"Lesson {lesson.id} references unknown concept '{concept_id}'"
                )

    def test_all_concept_prerequisite_references_resolve(self):
        curriculum = load_default_curriculum()
        for concept_id, concept in curriculum.concepts.items():
            for prereq in concept.prerequisites:
                assert prereq in curriculum.concepts, (
                    f"Concept '{concept_id}' has unknown prerequisite '{prereq}'"
                )

    def test_no_circular_concept_prerequisites(self):
        """load_default_curriculum() itself would raise CurriculumLoadError on a cycle."""
        curriculum = load_default_curriculum()
        # If we got here without an exception, there are no cycles.
        assert curriculum is not None

    def test_minimum_total_tests(self):
        """The imported curriculum has at least 80 deterministic tests."""
        curriculum = load_default_curriculum()
        total = sum(len(l.tests) for l in curriculum.lessons)
        assert total >= 80, f"Only {total} tests found"


# ---------------------------------------------------------------------------
# Loader error-path tests
# ---------------------------------------------------------------------------

class TestCurriculumLoaderErrors:

    def test_missing_module_file_raises(self, tmp_path):
        with pytest.raises(CurriculumLoadError, match="Curriculum file not found"):
            CurriculumLoader(
                write_curriculum(tmp_path, base_course("modules/missing.json"), {"one.json": base_module()})
            ).load()

    def test_invalid_module_schema_raises(self, tmp_path):
        module = base_module()
        del module["lessons"]
        with pytest.raises(CurriculumLoadError, match="Invalid module schema"):
            CurriculumLoader(write_curriculum(tmp_path, base_course(), {"one.json": module})).load()

    def test_duplicate_module_id_raises(self, tmp_path):
        course = {
            "id": "test-course",
            "title": "Test",
            "language": "python",
            "modules": [
                {"id": "one", "path": "modules/one.json"},
                {"id": "one", "path": "modules/one.json"},
            ],
        }
        with pytest.raises(CurriculumLoadError, match="Duplicate module reference"):
            CurriculumLoader(write_curriculum(tmp_path, course, {"one.json": base_module()})).load()

    def test_invalid_concept_prerequisite_raises(self, tmp_path):
        module = base_module(concepts=[{"id": "loops", "title": "Loops", "prerequisites": ["missing"]}])
        module["lessons"][0]["concepts"] = ["loops"]
        with pytest.raises(CurriculumLoadError, match="unknown prerequisites"):
            CurriculumLoader(write_curriculum(tmp_path, base_course(), {"one.json": module})).load()

    def test_circular_prerequisites_raises(self, tmp_path):
        concepts = [
            {"id": "variables", "title": "Variables", "prerequisites": ["loops"]},
            {"id": "loops", "title": "Loops", "prerequisites": ["variables"]},
        ]
        with pytest.raises(CurriculumLoadError, match="Circular concept prerequisite"):
            CurriculumLoader(write_curriculum(tmp_path, base_course(), {"one.json": base_module(concepts=concepts)})).load()

    def test_duplicate_lesson_id_raises(self, tmp_path):
        lessons = [base_lesson("dup-01", 1), base_lesson("dup-01", 2)]
        module = base_module(lessons=lessons)
        with pytest.raises(CurriculumLoadError, match="Duplicate lesson id"):
            CurriculumLoader(write_curriculum(tmp_path, base_course(), {"one.json": module})).load()

    def test_duplicate_lesson_order_raises(self, tmp_path):
        lessons = [base_lesson("lesson-a", 1), base_lesson("lesson-b", 1)]
        module = base_module(lessons=lessons)
        with pytest.raises(CurriculumLoadError, match="Duplicate lesson order"):
            CurriculumLoader(write_curriculum(tmp_path, base_course(), {"one.json": module})).load()

    def test_test_with_no_execution_strategy_raises(self, tmp_path):
        lesson = base_lesson()
        lesson["tests"] = [{"name": "bad_test", "required": True}]
        module = base_module(lessons=[lesson])
        with pytest.raises(CurriculumLoadError, match="must have either expected_stdout or unittest_code"):
            CurriculumLoader(write_curriculum(tmp_path, base_course(), {"one.json": module})).load()

    def test_test_with_both_execution_strategies_raises(self, tmp_path):
        lesson = base_lesson()
        lesson["tests"] = [{
            "name": "both_test",
            "expected_stdout": "hi\n",
            "unittest_code": "def both_test(self): pass",
            "required": True,
        }]
        module = base_module(lessons=[lesson])
        with pytest.raises(CurriculumLoadError, match="cannot have both"):
            CurriculumLoader(write_curriculum(tmp_path, base_course(), {"one.json": module})).load()

    def test_unknown_required_test_name_raises(self, tmp_path):
        lesson = base_lesson()
        lesson["completion_requirements"] = {"required_test_names": ["nonexistent_test"]}
        module = base_module(lessons=[lesson])
        with pytest.raises(CurriculumLoadError, match="unknown required tests"):
            CurriculumLoader(write_curriculum(tmp_path, base_course(), {"one.json": module})).load()


# ---------------------------------------------------------------------------
# Engine uses loaded curriculum
# ---------------------------------------------------------------------------

class TestEngineWithLoadedCurriculum:

    def test_engine_uses_injected_loaded_curriculum(self):
        curriculum = load_default_curriculum()

        class Executor:
            async def run(self, payload):
                return {
                    "tests": [{"name": t["name"], "passed": True} for t in payload["tests"]]
                }

        engine = LessonEngine(Executor(), ProgressionStore(curriculum), curriculum)
        result = __import__("asyncio").run(engine.run_lesson("variables-01", "pass"))
        assert result.completed is True
        assert engine.store.state().current_lesson_id == "booleans-01"

    def test_curriculum_loading_works_without_ollama(self):
        """Curriculum must load even when no AI provider is available."""
        # Simply importing and loading proves independence from Ollama
        curriculum = load_default_curriculum()
        assert len(curriculum.lessons) == 13

    def test_lesson_engine_works_without_ollama(self):
        curriculum = load_default_curriculum()

        class Executor:
            async def run(self, payload):
                return {
                    "tests": [{"name": t["name"], "passed": True} for t in payload["tests"]]
                }

        engine = LessonEngine(Executor(), ProgressionStore(curriculum), curriculum)
        result = __import__("asyncio").run(engine.run_lesson("variables-01", "pass"))
        assert result.completed is True

    def test_grading_works_without_ollama(self):
        """Passing required tests marks lesson completed regardless of AI."""
        curriculum = load_default_curriculum()

        class AlwaysPassExecutor:
            async def run(self, payload):
                return {
                    "tests": [{"name": t["name"], "passed": True} for t in payload["tests"]]
                }

        engine = LessonEngine(AlwaysPassExecutor(), ProgressionStore(curriculum), curriculum)
        result = __import__("asyncio").run(engine.run_lesson("variables-01", "pass"))
        assert result.passed is True
        assert result.completed is True

    def test_progression_works_without_ollama(self):
        curriculum = load_default_curriculum()

        class AlwaysPassExecutor:
            async def run(self, payload):
                return {
                    "tests": [{"name": t["name"], "passed": True} for t in payload["tests"]]
                }

        import asyncio
        engine = LessonEngine(AlwaysPassExecutor(), ProgressionStore(curriculum), curriculum)
        # Complete first two lessons
        asyncio.run(engine.run_lesson("variables-01", "pass"))
        asyncio.run(engine.run_lesson("booleans-01", "pass"))
        state = engine.store.state()
        assert "variables-01" in state.completed_lesson_ids
        assert "booleans-01" in state.completed_lesson_ids
        assert state.current_lesson_id == "numbers-01"
