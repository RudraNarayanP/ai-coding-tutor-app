"""Tests for static code grading (Docker-free) + learner feedback adaptation."""

import pytest
from types import SimpleNamespace
from fastapi.testclient import TestClient

from backend.feedback_store import FeedbackStore
from backend.lesson_engine import LessonEngine
from backend.lesson_models import ExerciseDefinition
from backend.sandbox import SandboxError
from backend.ai_provider import build_user_prompt
from backend.ai_models import TutorRequest


# ─── Static code grading ──────────────────────────────────────────────────

JAVA_SOLUTION = (
    "public class Solution {\n"
    "    public static String getLanguage() {\n"
    '        return "Java";\n'
    "    }\n"
    "}\n"
)


def _java_exercise(**overrides):
    data = {
        "id": "java-ex-2a",
        "type": "code",
        "question": "Implement static method getLanguage() returning 'Java'.",
        "starter_code": "public class Solution {\n    public static String getLanguage() {\n        return \"\";\n    }\n}\n",
        "solution_code": JAVA_SOLUTION,
        "tests": [{"name": "test_get_language", "test_code": "if (!Solution.getLanguage().equals(\"Java\")) throw new AssertionError();", "required": True}],
    }
    data.update(overrides)
    return ExerciseDefinition(**data)


class _NullExecutor:
    async def run(self, payload):
        raise AssertionError("executor should not be used for non-python grading")


def _engine(executor=None):
    engine = LessonEngine.__new__(LessonEngine)
    engine.executor = executor or _NullExecutor()
    return engine


@pytest.mark.asyncio
async def test_java_code_exercise_passes_statically_without_docker():
    engine = _engine()
    passed, _ = await engine.grade_exercise(_java_exercise(), {"code": JAVA_SOLUTION}, "java")
    assert passed is True


@pytest.mark.asyncio
async def test_java_code_exercise_ignores_whitespace_differences():
    engine = _engine()
    squished = 'public class Solution{public static String getLanguage(){return "Java";}}'
    passed, _ = await engine.grade_exercise(_java_exercise(), {"code": squished}, "java")
    assert passed is True


@pytest.mark.asyncio
async def test_java_code_exercise_fails_on_wrong_return_value():
    engine = _engine()
    wrong = JAVA_SOLUTION.replace('"Java"', '""')
    passed, feedback = await engine.grade_exercise(_java_exercise(), {"code": wrong}, "java")
    assert passed is False
    assert feedback


@pytest.mark.asyncio
async def test_code_exercise_empty_submission_fails_with_guidance():
    engine = _engine()
    passed, feedback = await engine.grade_exercise(_java_exercise(), {"code": "   "}, "java")
    assert passed is False
    assert "empty" in feedback.lower()


@pytest.mark.asyncio
async def test_correct_answer_contains_check_for_code():
    engine = _engine()
    ex = _java_exercise(solution_code=None, tests=[], correct_answer='return "Java";')
    passed, _ = await engine.grade_exercise(ex, {"code": JAVA_SOLUTION}, "java")
    assert passed is True
    failed, _ = await engine.grade_exercise(ex, {"code": "return nothing;"}, "java")
    assert failed is False


def test_static_execution_result_shape_for_run_code():
    engine = _engine()
    lesson = SimpleNamespace(
        solution_code=JAVA_SOLUTION,
        tests=[SimpleNamespace(name="test_get_language")],
    )
    result = engine._static_execution(lesson, "java", JAVA_SOLUTION)
    assert result["tests"][0]["passed"] is True
    assert result["error"] is None

    bad = engine._static_execution(lesson, "java", "garbage")
    assert bad["tests"][0]["passed"] is False

    no_solution = engine._static_execution(SimpleNamespace(solution_code=None, tests=[]), "java", "x")
    assert "Docker" in no_solution["error"]


# ─── Feedback store + adaptation ───────────────────────────────────────────

def test_feedback_bias_and_hints():
    store = FeedbackStore()
    assert store.summary("u1")["bias"] == "balanced"
    assert store.adaptation_hint("u1") == ""

    store.record("u1", "ex-1", "too_difficult")
    store.record("u1", "ex-2", "too_difficult")
    assert store.summary("u1")["bias"] == "harder"
    assert "TOO DIFFICULT" in store.adaptation_hint("u1")

    store.record("u1", "ex-3", "too_easy")
    store.record("u1", "ex-4", "too_easy")
    store.record("u1", "ex-5", "too_easy")
    store.record("u1", "ex-6", "too_easy")
    assert store.summary("u1")["bias"] == "easier"
    assert "TOO EASY" in store.adaptation_hint("u1")

    ack = store.adaptation_ack("u1", "too_easy")
    assert ack


def test_feedback_report_ack_and_invalid_rating():
    store = FeedbackStore()
    store.record("u2", "ex-9", "report", comment="Typo in question")
    assert "report" in store.adaptation_ack("u2", "report").lower()
    assert "reported" in store.adaptation_hint("u2").lower()
    with pytest.raises(ValueError):
        store.record("u2", "ex-9", "meh")


def test_latest_rating_per_exercise_wins():
    store = FeedbackStore()
    store.record("u3", "ex-1", "too_easy")
    store.record("u3", "ex-1", "too_easy")
    assert store.summary("u3")["total"] == 1


def test_adaptation_hint_injected_into_ai_prompt():
    req = TutorRequest(
        lesson_id="l1",
        lesson_title="T",
        instructions="Do it",
        code="x",
        test_results=[],
        hint_level=1,
        adaptation_hint="Be concise.",
    )
    prompt = build_user_prompt(req)
    assert "Be concise." in prompt


# ─── Feedback API endpoints ────────────────────────────────────────────────

def test_feedback_endpoints_roundtrip():
    from backend.main import app, feedback_store

    client = TestClient(app)
    res = client.post(
        "/api/feedback?user_id=endpoint_user",
        json={"exercise_id": "ex-1", "lesson_id": "l1", "rating": "too_difficult"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "adaptation" in data

    summary = client.get("/api/feedback/summary?user_id=endpoint_user")
    assert summary.status_code == 200
    assert summary.json()["too_difficult"] >= 1

    bad = client.post(
        "/api/feedback?user_id=endpoint_user",
        json={"exercise_id": "ex-1", "rating": "nope"},
    )
    assert bad.status_code == 400
