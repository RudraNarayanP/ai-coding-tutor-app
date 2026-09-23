"""Tests for best-effort LLM enrichment of guided-project milestones."""
import asyncio
import json

import pytest

from backend.project_enrich import assess_planned_course, assess_source_for_course, enrich_project
from backend.project_planner import ProjectGroundingError
from backend.source_ingestion import SourceDocument
from backend.project_models import (
    Microstep,
    Milestone,
    ProjectCourse,
    VerificationCheck,
)


def _project() -> ProjectCourse:
    return ProjectCourse(
        course_id="p", title="Reproduce GPT-2", source_hash="h", project_goal="build gpt-2",
        tech_stack=["torch"], entry_file="main.py",
        milestones=[
            Milestone(id="m1", order=1, title="Set up",
                      checks=[VerificationCheck(kind="file_exists", target="main.py")], xp_reward=10),
            Milestone(id="m2", order=2, title="implementing the GPT-2 nn.Module",
                      microstep=Microstep(observation="orig", action="Build this part", hint="h"),
                      checks=[VerificationCheck(kind="code_contains", target="nn.Module")], xp_reward=25),
            Milestone(id="m3", order=3, title="cross entropy loss",
                      checks=[VerificationCheck(kind="code_contains", target="cross_entropy")], xp_reward=25),
            Milestone(id="m4", order=4, title="Run and verify",
                      checks=[VerificationCheck(kind="run_ok", target="")], xp_reward=40),
        ],
    )


class GoodProvider:
    provider_id = "fake"

    async def generate_structured(self, system, user, max_tokens=900):
        if "keep or reject" in user.lower() or "buildable" in user.lower():
            return json.dumps({"keep": True, "reason": "Hands-on implementation steps are present."})
        if '"intro"' in user or "course introduction" in user.lower():
            return json.dumps({
                "intro": "We build a small GPT-style model from scratch. You will implement the tokenizer, model blocks, and training loop step by step.",
            })
        return json.dumps({
            "2": {
                "hook": "Build GPT-2 as one module.",
                "observation": "Wire embeddings and transformer blocks into one class.",
                "action": "Define a `GPT` class that subclasses `nn.Module`.",
                "teach": "You wire embeddings and blocks into one class. It is the skeleton of the whole model.",
                "example": "class GPT(nn.Module): ...",
                "celebrate": "Skeleton assembled! 🦴",
            },
            "3": {
                "hook": "Teach the model with loss.",
                "observation": "Cross entropy turns logits into a training signal.",
                "action": "Compute cross entropy loss from your model logits.",
                "teach": "Cross entropy measures prediction error. It is the signal that trains the network.",
                "example": "F.cross_entropy(logits, targets)",
                "celebrate": "Loss wired! ⚡",
            },
        })


class BrokenProvider:
    provider_id = "broken"

    async def generate_structured(self, system, user, max_tokens=900):
        raise RuntimeError("model unavailable")


def test_enrichment_populates_rich_content():
    project = _project()
    asyncio.run(enrich_project(GoodProvider(), project))
    m2 = project.milestone_by_id("m2")
    assert m2.teach and "skeleton" in m2.teach.lower()
    assert m2.example.startswith("class GPT")
    assert "🦴" in m2.celebrate
    assert m2.microstep.observation == "Wire embeddings and transformer blocks into one class."
    assert "nn.Module" in m2.microstep.action
    assert project.course_intro and "GPT" in project.course_intro


def test_enrichment_skips_setup_and_run_milestones():
    project = _project()
    asyncio.run(enrich_project(GoodProvider(), project))
    assert project.milestone_by_id("m1").teach == ""
    assert project.milestone_by_id("m4").teach == ""


def test_enrichment_failure_keeps_deterministic_copy():
    project = _project()
    # Must not raise, and must preserve original deterministic microstep.
    asyncio.run(enrich_project(BrokenProvider(), project))
    m2 = project.milestone_by_id("m2")
    assert m2.teach == ""
    assert m2.microstep.observation == "orig"


def test_enrichment_with_no_provider_is_noop():
    project = _project()
    asyncio.run(enrich_project(None, project))
    assert project.milestone_by_id("m2").teach == ""


def _source(text: str, title: str = "Source") -> SourceDocument:
    return SourceDocument(
        source_type="transcript", source_url="", source_hash="h", title=title, plain_text=text,
    )


class RejectProvider:
    async def generate_structured(self, system, user, max_tokens=220):
        return json.dumps({
            "keep": False,
            "reason": "This source is only an overview and does not show enough implementation steps to build a course.",
        })


class AcceptProvider:
    async def generate_structured(self, system, user, max_tokens=220):
        return json.dumps({"keep": True})


class SilentProvider:
    async def generate_structured(self, system, user, max_tokens=220):
        return "not sure, maybe?"


def test_llm_rejects_source_without_enough_course_material():
    with pytest.raises(ProjectGroundingError, match="enough implementation"):
        asyncio.run(assess_source_for_course(RejectProvider(), _source("import numpy\ndef foo():\n  pass\n"), "Talk"))


def test_llm_accepts_source_with_enough_course_material():
    tutorial = (
        "First, import the collections module.\n"
        "Next, define a function called count_words that takes a text string.\n"
        "Then create a variable called sample containing some text.\n"
    )
    asyncio.run(assess_source_for_course(AcceptProvider(), _source(tutorial), "Word Frequency"))


def test_llm_assess_noop_without_provider():
    asyncio.run(assess_source_for_course(None, _source("hello world this is a lecture only"), "Talk"))


def test_llm_rejects_unless_it_explicitly_keeps():
    with pytest.raises(ProjectGroundingError):
        asyncio.run(assess_source_for_course(SilentProvider(), _source("import numpy\ndef foo():\n  pass\n"), "Talk"))


def test_llm_fails_closed_when_provider_errors():
    with pytest.raises(ProjectGroundingError, match="could not judge"):
        asyncio.run(assess_source_for_course(BrokenProvider(), _source("import numpy\ndef foo():\n  pass\n"), "Talk"))


def test_llm_can_reject_a_planned_course_outline():
    with pytest.raises(ProjectGroundingError):
        asyncio.run(assess_planned_course(RejectProvider(), _project()))


def test_a_teach_that_fits_the_character_limit_is_still_refused():
    """Two rules share the name `looks_like_raw_transcript` and they do not agree.

    `project_copy`'s measures characters; the one `validate_project` applies counts words
    and flags anything over 28. So a 202-character teaching block of 31 words passed the
    enrichment guard, landed on the milestone, and then rejected the *whole course* at
    creation with "still contains raw transcript speech" — a message that blames the
    learner's source for a fault in the app's own copy. Measured on karpathy/micrograd
    before the fix: 2 of 8 real builds failed this way, on any source type.

    The refusal drops the whole item, which is the contract this function already had
    for the character rule; the deterministic copy stays.
    """
    from backend.project_enrich import _apply_items
    from backend.project_planner import validate_project

    long_teach = (
        "Value wraps a scalar with its gradient and a backward function, forming the "
        "building block of automatic differentiation. Every operation on it records a "
        "computation graph so gradients can flow backward."
    )
    assert len(long_teach.split()) > 28, "the point of this case is a short-but-wordy block"
    assert len(long_teach) < 280

    project = _project()
    applied = _apply_items(project, {2: {
        "hook": "How the module gets built",
        "observation": "You define the module class.",
        "action": "Define nn.Module in main.py.",
        "teach": long_teach,
    }})

    milestone = project.milestones[1]
    assert applied == 0
    assert milestone.teach == "" and milestone.hook == ""
    assert milestone.microstep.action == "Build this part"   # deterministic copy survives
    validate_project(project)                                # the build still goes through


def test_a_teach_within_both_rules_is_still_applied():
    """The guard must not simply turn enrichment off."""
    from backend.project_enrich import _apply_items

    project = _project()
    applied = _apply_items(project, {2: {
        "hook": "How the module gets built",
        "teach": "Value holds a number and its gradient, so every operation can be undone later.",
    }})
    assert applied == 1
    assert project.milestones[1].teach.startswith("Value holds")
