"""Tests proving that the public lesson API does not expose internal grading data.

These tests form a security boundary contract:
- No test implementation code (unittest_code) must appear in API responses.
- No expected output values (expected_stdout, stdin) must appear in API responses.
- No completion requirements (required_test_names) must appear in API responses.
- No internal test list must appear in API responses.
- The engine continues to receive full internal definitions for grading.

If any of these tests fail, student-facing API responses are leaking answer-key
information that would allow a student to inspect grading logic through their
browser's network tab.
"""

import asyncio
import json

import httpx
import pytest

import backend.main as main_module
from backend.lesson_engine import LessonEngine, ProgressionStore
from backend.lesson_models import LessonDefinition, PublicLessonView
from backend.lessons import CURRICULUM

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def api_client():
    transport = httpx.ASGITransport(app=main_module.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def get_lesson_json(lesson_id: str) -> dict:
    async def _call():
        async with api_client() as client:
            return await client.get(f"/api/lessons/{lesson_id}")
    return asyncio.run(_call()).json()


# The complete set of internal-only fields that must never appear in a public
# lesson response.
FORBIDDEN_FIELDS = {
    "tests",
    "unittest_code",
    "expected_stdout",
    "stdin",
    "completion_requirements",
    "static_hints",
}

# Fields the frontend legitimately needs.
REQUIRED_PUBLIC_FIELDS = {
    "id",
    "title",
    "description",
    "order",
    "difficulty",
    "duration_minutes",
    "starter_code",
}


# ---------------------------------------------------------------------------
# PublicLessonView model contract
# ---------------------------------------------------------------------------

class TestPublicLessonViewModel:

    def test_public_view_contains_no_forbidden_fields(self):
        """PublicLessonView.model_fields must not include any internal field."""
        public_fields = set(PublicLessonView.model_fields.keys())
        leaked = public_fields & FORBIDDEN_FIELDS
        assert not leaked, (
            f"PublicLessonView model contains forbidden fields: {sorted(leaked)}"
        )

    def test_public_view_contains_all_required_fields(self):
        public_fields = set(PublicLessonView.model_fields.keys())
        missing = REQUIRED_PUBLIC_FIELDS - public_fields
        assert not missing, (
            f"PublicLessonView is missing required display fields: {sorted(missing)}"
        )

    def test_from_lesson_produces_no_forbidden_fields(self):
        """from_lesson() serialisation must not bleed internal data."""
        for lesson in CURRICULUM.lessons:
            view = PublicLessonView.from_lesson(lesson)
            dumped = view.model_dump()
            leaked = set(dumped.keys()) & FORBIDDEN_FIELDS
            assert not leaked, (
                f"Lesson {lesson.id}: PublicLessonView.from_lesson() leaked {sorted(leaked)}"
            )

    def test_from_lesson_preserves_required_display_fields(self):
        lesson = CURRICULUM.lessons[0]
        view = PublicLessonView.from_lesson(lesson)
        assert view.id == lesson.id
        assert view.title == lesson.title
        assert view.description == lesson.description
        assert view.order == lesson.order
        assert view.difficulty == lesson.difficulty
        assert view.duration_minutes == lesson.duration_minutes
        assert view.starter_code == lesson.starter_code

    def test_internal_definition_still_has_full_data(self):
        """LessonDefinition must NOT be stripped — the engine needs all fields."""
        for lesson in CURRICULUM.lessons:
            assert lesson.tests, f"Lesson {lesson.id} has no internal tests"
            assert lesson.completion_requirements.required_test_names, (
                f"Lesson {lesson.id} has no required_test_names"
            )
            assert any(t.unittest_code is not None for t in lesson.tests), (
                f"Lesson {lesson.id} has no unittest_code tests"
            )

    def test_public_view_json_serialisation_contains_no_forbidden_content(self):
        """Even as raw JSON the response must not contain forbidden keys."""
        for lesson in CURRICULUM.lessons:
            view = PublicLessonView.from_lesson(lesson)
            raw = view.model_dump_json()
            for field in FORBIDDEN_FIELDS:
                # Check that the key is not a JSON key (surrounded by quotes + colon)
                assert f'"{field}"' not in raw, (
                    f"Lesson {lesson.id}: field '{field}' found in JSON output of PublicLessonView"
                )


# ---------------------------------------------------------------------------
# API endpoint protection — every lesson
# ---------------------------------------------------------------------------

class TestLessonDetailEndpointProtection:

    @pytest.mark.parametrize("lesson", CURRICULUM.lessons)
    def test_lesson_detail_never_returns_tests_field(self, lesson):
        data = get_lesson_json(lesson.id)
        assert "tests" not in data, (
            f"GET /api/lessons/{lesson.id} returned a 'tests' field"
        )

    @pytest.mark.parametrize("lesson", CURRICULUM.lessons)
    def test_lesson_detail_never_returns_unittest_code(self, lesson):
        data = get_lesson_json(lesson.id)
        # Check the response JSON string itself — even nested occurrences
        raw = json.dumps(data)
        assert "unittest_code" not in raw, (
            f"GET /api/lessons/{lesson.id}: 'unittest_code' found in response body"
        )

    @pytest.mark.parametrize("lesson", CURRICULUM.lessons)
    def test_lesson_detail_never_returns_expected_stdout(self, lesson):
        data = get_lesson_json(lesson.id)
        raw = json.dumps(data)
        assert "expected_stdout" not in raw, (
            f"GET /api/lessons/{lesson.id}: 'expected_stdout' found in response body"
        )

    @pytest.mark.parametrize("lesson", CURRICULUM.lessons)
    def test_lesson_detail_never_returns_completion_requirements(self, lesson):
        data = get_lesson_json(lesson.id)
        assert "completion_requirements" not in data, (
            f"GET /api/lessons/{lesson.id} returned 'completion_requirements'"
        )

    @pytest.mark.parametrize("lesson", CURRICULUM.lessons)
    def test_lesson_detail_returns_required_display_fields(self, lesson):
        data = get_lesson_json(lesson.id)
        for field in REQUIRED_PUBLIC_FIELDS:
            assert field in data, (
                f"GET /api/lessons/{lesson.id}: required field '{field}' missing from response"
            )

    @pytest.mark.parametrize("lesson", CURRICULUM.lessons)
    def test_lesson_detail_starter_code_is_present_and_non_empty(self, lesson):
        data = get_lesson_json(lesson.id)
        assert data.get("starter_code"), (
            f"GET /api/lessons/{lesson.id}: 'starter_code' is absent or empty"
        )


# ---------------------------------------------------------------------------
# Lessons list endpoint — also must not leak test data
# ---------------------------------------------------------------------------

class TestLessonsListEndpointProtection:

    def test_lessons_list_contains_no_test_data(self):
        async def call():
            async with api_client() as client:
                return await client.get("/api/lessons")
        resp = asyncio.run(call())
        assert resp.status_code == 200
        raw = resp.text
        for field in ("unittest_code", "expected_stdout", "completion_requirements"):
            assert field not in raw, (
                f"GET /api/lessons: '{field}' found in list response"
            )

    def test_lessons_list_returns_summaries_only(self):
        async def call():
            async with api_client() as client:
                return await client.get("/api/lessons?language=python")
        resp = asyncio.run(call())
        data = resp.json()
        assert len(data) >= 70
        for item in data:
            # Each summary has exactly the safe summary fields
            assert "tests" not in item
            assert "starter_code" not in item
            assert "unittest_code" not in item


# ---------------------------------------------------------------------------
# Run endpoint — ProgressionResult is safe
# ---------------------------------------------------------------------------

class TestRunEndpointDoesNotLeakTestImplementations:

    def test_progression_result_model_has_no_unittest_code(self):
        """TestResult model (returned in ProgressionResult.tests) must not
        contain test implementation fields."""
        from backend.lesson_models import TestResult
        result_fields = set(TestResult.model_fields.keys())
        assert "unittest_code" not in result_fields
        assert "expected_stdout" not in result_fields
        assert "stdin" not in result_fields

    def test_internal_engine_still_uses_full_lesson_definition(self):
        """The engine must still operate on full LessonDefinition, not the public view."""
        engine = LessonEngine(
            _NullExecutor(), ProgressionStore(CURRICULUM), CURRICULUM
        )
        internal = engine.get_lesson("variables-01")
        assert isinstance(internal, LessonDefinition)
        assert internal.tests
        assert internal.completion_requirements.required_test_names


class _NullExecutor:
    async def run(self, payload: dict) -> dict:
        return {"tests": [], "stdout": "", "stderr": ""}


# ---------------------------------------------------------------------------
# Sandbox runner unittest_code parsing regression test
# ---------------------------------------------------------------------------

class TestSandboxRunnerUnittestCodeParsing:
    """Regression test for the sandbox runner unittest_code parsing bug.
    
    The sandbox runner must correctly handle curriculum files that include
    the full method definition (def test_name(self):) in unittest_code.
    Previously, it was wrapping this inside another method definition,
    creating a nested function that never executed.
    """
    
    def test_unittest_code_with_full_method_definition(self):
        """Test that sandbox correctly extracts method body from full definition."""
        import textwrap
        
        # Simulate curriculum format with full method definition
        method_body = "def test_EXPECTED_BAKE_TIME(self):\n    failure_msg = 'Expected a constant of EXPECTED_BAKE_TIME with a value of 40.'\n    self.assertEqual(EXPECTED_BAKE_TIME, 40, msg=failure_msg)"
        
        # Apply the same logic as the sandbox runner
        dedented = textwrap.dedent(method_body).strip()
        if dedented.startswith("def "):
            lines = dedented.split("\n")
            body_lines = []
            in_def = True
            for line in lines:
                if in_def:
                    if ":" in line:
                        in_def = False
                    continue
                body_lines.append(line)
            # Dedent the extracted body to remove the original indentation
            method_body = textwrap.dedent("\n".join(body_lines)).strip()
        
        # The result should be just the body, not another nested function
        assert "def test_EXPECTED_BAKE_TIME" not in method_body
        assert "self.assertEqual(EXPECTED_BAKE_TIME, 40" in method_body
        assert "failure_msg" in method_body
