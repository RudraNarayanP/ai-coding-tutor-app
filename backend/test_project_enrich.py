"""Tests for best-effort LLM enrichment of guided-project milestones."""
import asyncio
import json

from backend.project_enrich import enrich_project
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
        return json.dumps({
            "2": {"hook": "Build GPT-2 as one module.", "teach": "You wire embeddings and blocks into one class. It is the skeleton of the whole model.", "example": "class GPT(nn.Module): ...", "celebrate": "Skeleton assembled! 🦴"},
            "3": {"hook": "Teach the model with loss.", "teach": "Cross entropy measures prediction error. It is the signal that trains the network.", "example": "F.cross_entropy(logits, targets)", "celebrate": "Loss wired! ⚡"},
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
    # Hook is promoted to the learner-facing observation.
    assert m2.microstep.observation == "Build GPT-2 as one module."


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
