"""Unit tests for OpenRouter-owned create → review → revise quality loop."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field

import pytest

from backend.ai_course_generator import (
    generate_course_with_ai,
    is_weak_keyword_check,
    local_precheck_course,
    project_to_course_dict,
    quality_max_tries,
    _parse_review_payload,
)
from backend.project_models import (
    Microstep,
    Milestone,
    ProjectCourse,
    VerificationCheck,
    WorkspaceFile,
)
from backend.source_ingestion import SourceDocument, VideoSegment
from backend.source_quality import ProjectGroundingError, SourceQualityError


def _doc(title: str = "Build a Word Counter in Python") -> SourceDocument:
    transcript = (
        "Welcome. Today we build a word frequency counter in Python. "
        "First create main.py. Import collections. Define count_words. "
        "Use Counter on the split text. Print the most common words. "
        "Run the program and verify stdout."
    )
    return SourceDocument(
        source_type="transcript",
        source_url="https://example.com/word-counter",
        source_hash="abc123",
        title=title,
        plain_text=transcript,
        segments=[
            VideoSegment(
                video_id="v1",
                title=title,
                url="https://example.com/word-counter",
                position=1,
                transcript=transcript,
                chapters=[
                    "Create main.py",
                    "Import collections",
                    "Define count_words",
                    "Use Counter",
                    "Print results",
                    "Run and verify",
                ],
            )
        ],
    )


def _good_course_json() -> dict:
    ms = []
    steps = [
        ("Create main.py", "main.py", "file_exists"),
        ("Import collections", "collections", "import"),
        ("Define count_words", "count_words", "symbol"),
        ("Use Counter", "Counter", "code_contains"),
        ("Print results", "print", "code_contains"),
        ("Run and verify", "", "run_ok"),
    ]
    for title, target, kind in steps:
        checks = [{"kind": kind, "target": target, "description": f"Check {title}"}]
        ms.append(
            {
                "title": title,
                "hook": title,
                "teach": f"In this step you {title.lower()} using the transcript.",
                "observation": f"You finished {title}.",
                "action": f"In `main.py`, implement: {title}. Quote key token `{target or 'print'}`.",
                "hint": f"Type `{target or 'print'}` exactly; check spelling and indentation.",
                "example": "from collections import Counter" if target == "collections" else f"# {title}",
                "celebrate": "Nice!",
                "why": f"This unlocks the next skill after {title}.",
                "source_quote": title,
                "checks": checks,
                "xp_reward": 20,
            }
        )
    return {
        "decision": "create",
        "course": {
            "title": "Word Frequency Counter",
            "language": "python",
            "entry_file": "main.py",
            "project_goal": "Build a word frequency counter from the transcript.",
            "course_intro": "Learn collections.Counter by building a small CLI.",
            "tech_stack": ["collections"],
            "milestones": ms,
        },
    }


def _weak_course_json() -> dict:
    data = _good_course_json()
    # Inject banned phrase + empty why + weak check
    data["course"]["milestones"][1]["action"] = "Do it as in the video"
    data["course"]["milestones"][1]["why"] = ""
    data["course"]["milestones"][2]["checks"] = [
        {"kind": "code_contains", "target": "setup", "description": "keyword only"}
    ]
    return data


class ScriptedProvider:
    """Returns scripted generate_structured responses in order."""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []
        self.provider_id = "scripted"

    async def generate_structured(self, system: str, user: str, max_tokens: int = 4000) -> str:
        self.calls.append((system[:80], user[:120]))
        if not self.responses:
            raise AssertionError("ScriptedProvider exhausted responses")
        return self.responses.pop(0)


def test_quality_max_tries_default_and_env(monkeypatch):
    monkeypatch.delenv("CREATE_COURSE_QUALITY_MAX_TRIES", raising=False)
    assert quality_max_tries() == 8
    monkeypatch.setenv("CREATE_COURSE_QUALITY_MAX_TRIES", "12")
    assert quality_max_tries() == 12
    monkeypatch.setenv("CREATE_COURSE_QUALITY_MAX_TRIES", "0")
    assert quality_max_tries() == 1


def test_parse_review_payload_pass_and_fail():
    assert _parse_review_payload('{"verdict":"PASS","reason":"solid"}')["verdict"] == "PASS"
    fail = _parse_review_payload(
        '{"verdict":"FAIL","reason":"vague","defects":["empty why","video phrase"]}'
    )
    assert fail["verdict"] == "FAIL"
    assert len(fail["defects"]) == 2


def test_local_precheck_flags_video_phrase_and_empty_why():
    project = ProjectCourse(
        course_id="c1",
        title="Demo",
        project_goal="goal",
        entry_file="main.py",
        milestones=[
            Milestone(
                id="m1",
                order=1,
                title="Step 1",
                why="",
                microstep=Microstep(action="as in the video do this", observation="x"),
                checks=[VerificationCheck(kind="code_contains", target="def", description="d")],
            ),
            Milestone(
                id="m2",
                order=2,
                title="Step 2",
                why="ok",
                microstep=Microstep(action="write code", observation="x"),
                checks=[VerificationCheck(kind="code_contains", target="setup", description="d")],
            ),
            Milestone(
                id="m3",
                order=3,
                title="Step 3",
                why="ok",
                microstep=Microstep(action="write more", observation="x"),
                checks=[VerificationCheck(kind="code_contains", target="basic", description="d")],
            ),
            Milestone(
                id="m4",
                order=4,
                title="Step 4",
                why="ok",
                microstep=Microstep(action="again", observation="x"),
                checks=[VerificationCheck(kind="code_contains", target="code", description="d")],
            ),
            Milestone(
                id="m5",
                order=5,
                title="Step 5",
                why="ok",
                microstep=Microstep(action="final", observation="x"),
                checks=[VerificationCheck(kind="run_ok", target="", description="d")],
            ),
        ],
        workspace_files=[WorkspaceFile(path="main.py", content="#")],
    )
    defects = local_precheck_course(project)
    assert any("Banned" in d or "as in the video" in d for d in defects)
    assert any("Empty why" in d for d in defects)


def test_review_loop_fail_then_pass_stores_once(monkeypatch):
    monkeypatch.setenv("CREATE_COURSE_QUALITY_MAX_TRIES", "5")
    create = json.dumps(_good_course_json())
    fail = json.dumps(
        {"verdict": "FAIL", "reason": "weak checks", "defects": ["Strengthen code_contains targets"]}
    )
    revise = json.dumps(_good_course_json())
    passed = json.dumps({"verdict": "PASS", "reason": "top-class"})
    provider = ScriptedProvider([create, fail, revise, passed])

    project = asyncio.run(
        generate_course_with_ai(provider, _doc(), title="Word Counter", course_id="course-loop")
    )
    assert project.course_id == "course-loop"
    assert len(project.milestones) >= 5
    # create + review FAIL + revise + review PASS
    assert len(provider.calls) == 4
    assert not provider.responses


def test_review_loop_pass_first_try(monkeypatch):
    monkeypatch.setenv("CREATE_COURSE_QUALITY_MAX_TRIES", "8")
    create = json.dumps(_good_course_json())
    passed = json.dumps({"verdict": "PASS", "reason": "good"})
    provider = ScriptedProvider([create, passed])
    project = asyncio.run(
        generate_course_with_ai(provider, _doc(), title="Word Counter", course_id="course-pass")
    )
    assert project.title
    assert len(provider.calls) == 2


def test_review_loop_max_tries_raises(monkeypatch):
    monkeypatch.setenv("CREATE_COURSE_QUALITY_MAX_TRIES", "2")
    # Local precheck will fail on banned phrase → revise each attempt, no PASS
    weak = json.dumps(_weak_course_json())
    # After revise still weak (script always returns weak create-shaped JSON)
    provider = ScriptedProvider([weak, weak, weak, weak])
    with pytest.raises(ProjectGroundingError) as ei:
        asyncio.run(
            generate_course_with_ai(provider, _doc(), title="Word Counter", course_id="course-max")
        )
    assert "quality review" in str(ei.value).lower() or "PASS" in str(ei.value)


def test_project_to_course_dict_roundtrip_shape():
    data = _good_course_json()["course"]
    # Build via generate path pieces
    from backend.ai_course_generator import course_dict_to_project

    project = course_dict_to_project(data, doc=_doc(), title="T", course_id="c")
    d = project_to_course_dict(project)
    assert d["entry_file"] == "main.py"
    assert len(d["milestones"]) >= 5
    assert "action" in d["milestones"][0]


def test_is_weak_keyword_check_denylist_and_short():
    assert is_weak_keyword_check("code_contains", "class")
    assert is_weak_keyword_check("code_contains", "def")
    assert is_weak_keyword_check("code_contains", "import")
    assert is_weak_keyword_check("code_contains", "return")
    assert is_weak_keyword_check("code_contains", "True")
    assert is_weak_keyword_check("code_contains", "print")
    assert is_weak_keyword_check("code_contains", "")
    assert not is_weak_keyword_check("code_contains", "Value")
    assert not is_weak_keyword_check("code_contains", "__init__")
    assert not is_weak_keyword_check("code_contains", "def __add__")
    assert not is_weak_keyword_check("import", "collections")
    assert not is_weak_keyword_check("symbol", "count_words")


def test_local_precheck_flags_follow_source_and_weak_class():
    project = ProjectCourse(
        course_id="c-follow",
        title="Micrograd",
        project_goal="Build Value autograd",
        entry_file="main.py",
        tech_stack=["Python"],
        milestones=[
            Milestone(
                id="m1",
                order=1,
                title="Import numpy",
                why="Start with arrays",
                teach="Use numpy",
                microstep=Microstep(
                    action="In main.py, import numpy as np",
                    observation="numpy ready",
                    hint="Follow the source for this step, then click NEXT.",
                ),
                checks=[VerificationCheck(kind="code_contains", target="import numpy as np", description="d")],
            ),
            Milestone(
                id="m2",
                order=2,
                title="Define Value",
                why="Need Value",
                teach="Value wraps scalars",
                microstep=Microstep(
                    action="Define class Value",
                    observation="class exists",
                    hint="Follow the source for this step, then click NEXT.",
                ),
                checks=[VerificationCheck(kind="code_contains", target="class", description="d")],
            ),
            Milestone(
                id="m3",
                order=3,
                title="Add",
                why="ops",
                teach="add",
                microstep=Microstep(action="add", observation="x", hint="Follow the transcript carefully."),
                checks=[VerificationCheck(kind="code_contains", target="def", description="d")],
            ),
            Milestone(
                id="m4",
                order=4,
                title="Mul",
                why="ops",
                teach="mul",
                microstep=Microstep(action="mul", observation="x", hint="ok nudge: use __mul__"),
                checks=[VerificationCheck(kind="code_contains", target="import", description="d")],
            ),
            Milestone(
                id="m5",
                order=5,
                title="Run",
                why="verify",
                teach="run",
                microstep=Microstep(action="run", observation="x", hint="Run the file."),
                checks=[VerificationCheck(kind="run_ok", target="", description="d")],
            ),
        ],
        workspace_files=[WorkspaceFile(path="main.py", content="#")],
    )
    # Without source doc: still flags follow-source + weak keyword checks
    defects = local_precheck_course(project)
    assert any("follow-the-source" in d.lower() or "Banned" in d for d in defects), defects
    assert any("weak" in d.lower() or "keyword" in d.lower() for d in defects), defects

    # With a micrograd-like source (no numpy): also flags ungrounded numpy
    doc = SourceDocument(
        source_type="transcript",
        source_url="https://www.youtube.com/watch?v=VMj-3S1tku0",
        source_hash="mg",
        title="The spelled-out intro to neural networks and backpropagation: building micrograd",
        plain_text=(
            "We build micrograd in pure Python. Define class Value with data and grad. "
            "Implement __add__ __mul__ backward topological sort. No numpy. "
            "Build a neuron and MLP and train."
        ),
    )
    defects2 = local_precheck_course(project, doc)
    assert any("Ungrounded" in d or "numpy" in d.lower() for d in defects2), defects2


def test_local_precheck_passes_solid_micrograd_shaped_course():
    steps = [
        ("Create main.py", "main.py", "file_exists"),
        ("Define Value", "Value", "symbol"),
        ("Add __add__", "__add__", "code_contains"),
        ("Add backward", "backward", "code_contains"),
        ("Build Neuron", "Neuron", "symbol"),
        ("Run smoke", "", "run_ok"),
    ]
    milestones = []
    for i, (title, target, kind) in enumerate(steps, start=1):
        milestones.append(
            Milestone(
                id=f"m{i}",
                order=i,
                title=title,
                why=f"This unlocks the next part after {title}.",
                teach=f"Teach: {title} matters for the autograd graph.",
                microstep=Microstep(
                    action=f"In `main.py`, implement {title} using `{target or 'print'}`.",
                    observation=f"Finished {title}.",
                    hint=f"Keep the name `{target}` exact." if target else "Run until clean.",
                ),
                checks=[VerificationCheck(kind=kind, target=target, description=f"Check {title}")],
            )
        )
    project = ProjectCourse(
        course_id="c-solid",
        title="Micrograd",
        project_goal="Build micrograd Value engine",
        entry_file="main.py",
        tech_stack=["Python"],
        milestones=milestones,
        workspace_files=[WorkspaceFile(path="main.py", content="#")],
    )
    defects = local_precheck_course(project)
    assert defects == [], defects

