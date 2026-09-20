"""``verify_lessons --docker`` must really route execution through Docker.

The flag used to be parsed and silently ignored: ``audit_lesson`` decided the
executor from the language alone, so python/sql/javascript/typescript always ran
in the loose in-process runner while the app (``backend/sandbox.py``) uses the
hardened container whenever Docker is reachable. An audit that passes on a
different sandbox than learners hit is not evidence - which is the exact failure
mode this guard exists for.
"""
from __future__ import annotations

import backend.verify_lessons as vl


def _route_for(monkeypatch, language: str, force_docker: bool) -> list[bool]:
    seen: list[bool] = []

    def fake_run_sandbox(lang, code, tests, use_docker):
        seen.append(use_docker)
        return {"tests": [{"name": "t", "passed": True, "stdout": "", "stderr": "", "error": None}],
                "stdout": "", "stderr": "", "error": None}

    monkeypatch.setattr(vl, "run_sandbox", fake_run_sandbox)
    vl.audit_lesson("demo", language, _stub_lesson(), {}, force_docker=force_docker)
    assert seen, "audit_lesson never executed anything"
    return seen


def _stub_lesson():
    from backend.lesson_models import LessonDefinition

    return LessonDefinition(
        id="demo-01",
        title="Demo lesson",
        description="Adds two numbers and returns the sum.",
        order=1,
        difficulty="beginner",
        duration_minutes=5,
        type="practice",
        starter_code="def add(a, b):\n    # TODO: return the sum\n    pass\n",
        solution_code="def add(a, b):\n    return a + b\n",
        tests=[{
            "name": "adds",
            "unittest_code": "class T(unittest.TestCase):\n    def test_adds(self):\n        self.assertEqual(add(2, 3), 5)\n",
        }],
    )


def test_local_languages_default_to_the_in_process_runner(monkeypatch):
    assert set(_route_for(monkeypatch, "python", force_docker=False)) == {False}


def test_force_docker_overrides_the_language_shortcut(monkeypatch):
    assert set(_route_for(monkeypatch, "python", force_docker=True)) == {True}


def test_compiled_languages_already_required_docker(monkeypatch):
    assert set(_route_for(monkeypatch, "cpp", force_docker=False)) == {True}
