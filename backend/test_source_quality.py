"""Regression tests for the Create Course source quality gate.

Covers the brief's items 1–11 with deterministic fixtures. Decisions must be
accept | reject | insufficient. Nonsense milestone phrases are used as examples
of a *class* of failure, not as a hardcoded denylist — generalized variants
must also fail.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.main as main_module
from backend.project_models import Microstep, Milestone, VerificationCheck
from backend.project_planner import ProjectGroundingError, plan_project
from backend.project_service import build_project
from backend.project_store import ProjectStore
from backend.source_ingestion import IngestionError, SourceDocument, SourceIngestionService, VideoSegment
from backend.source_quality import (
    LlmSourceAnalyzer,
    SourceQualityError,
    evaluate_ingestion,
    evaluate_milestones,
    evaluate_source,
    evaluate_source_with_analyzer,
    filter_invalid_milestones,
    is_implementable_step,
)

client = TestClient(main_module.app)


# ─── Fixtures ────────────────────────────────────────────────────────────────

NONSENSE_TRANSCRIPT = """
Hey guys so today we're talking about ChatGPT tips.
You can just write him a draft for sure.
Write ChatGPT a draft.
Then write a memo on the nuclear conflict in North Korea.
Create our memo after that.
If you want to implement an algorithm, implement them yourself.
You can build like, you know, whatever you want.
Python is great and AI is the future. Coding is important.
"""

# Same failure class, different wording — must not depend on the screenshot strings.
GENERALIZED_NONSENSE = """
Welcome back to my productivity chat.
Compose her a briefing about the latest headlines.
Assemble like, you know, whatever the assistant suggests.
Ship them yourself after the chatbot replies.
Ask ChatGPT to draft an email for your boss.
Using AI and Python buzzwords does not make this a coding tutorial.
"""

UNRELATED_NEWS = """
Breaking news tonight. Headlines from the press conference dominate foreign policy.
Pundits debate the ceasefire. There is no code, no function, and no application to build.
This is commentary on current events, not a programming walkthrough.
"""

WORD_COUNT_TRANSCRIPT = """
In this tutorial we build a word frequency counter in Python.
First, import the collections module.
Next, define a function called count_words that takes a text string.
Then create a variable called sample containing some text.
Call count_words on the sample.
Finally, print the result so you can see the counts.
"""

FLASK_TODO_TRANSCRIPT = """
In this tutorial we build a Flask REST API for a todo list from scratch.
First, import flask.
Next, define a function called create_app that returns the application.
Then create a variable called app.
Add a route handler called list_todos.
Call create_app.
Finally, print the result so you can verify the server boots.
"""

NOISY_VALID = """
um so uh today we're gonna like build a word frequency counter in python you know
first we import the collections module then we define a function called count_words
that takes a text string then create a variable called sample containing some text
and then we call count_words on the sample and print the result yeah
"""

AMBIGUOUS_TECH = """
Today we'll talk about Python. Python is a great language. Algorithms are important.
You should learn to code. AI is the future. Programming will change the world.
ChatGPT is popular. That's all for this discussion.
"""

MIXED_TRANSCRIPT = """
In this tutorial we build a word frequency counter in Python.
First, import the collections module.
Next, define a function called count_words that takes a text string.
Also write a memo on the nuclear conflict.
Implement them yourself and build like.
Then create a variable called sample containing some text.
Call count_words on the sample.
Finally, print the result so you can see the counts.
"""


def _doc(text: str, title: str = "Source") -> SourceDocument:
    return SourceDocument(
        source_type="transcript",
        source_url="",
        source_hash="hash123",
        title=title,
        plain_text=text,
        access_level="text_only",
    )


def _chaptered(chapters: list[str], title: str, transcript: str = "") -> SourceDocument:
    seg = VideoSegment(
        video_id="vid1",
        title=title,
        url="https://youtu.be/vid1",
        position=1,
        transcript=transcript or f"{title}. " + " ".join(chapters),
        chapters=list(chapters),
    )
    return SourceDocument(
        source_type="youtube_url",
        source_url="https://youtu.be/vid1",
        source_hash="h",
        title=title,
        segments=[seg],
        access_level="full",
    )


def _store() -> ProjectStore:
    return ProjectStore(storage_dir=Path(tempfile.mkdtemp(prefix="pwqg_")))


# ─── 1. Nonsense source → reject / insufficient ───────────────────────────────

def test_nonsense_source_is_rejected_or_insufficient():
    decision = evaluate_source(_doc(NONSENSE_TRANSCRIPT, "ChatGPT Tips"), title="ChatGPT Tips")
    assert decision.decision == "reject"
    assert decision.source_type == "assistant_usage"
    with pytest.raises(SourceQualityError) as exc:
        plan_project(_doc(NONSENSE_TRANSCRIPT, "ChatGPT Tips"), title="ChatGPT Tips", course_id="bad")
    assert exc.value.decision == "reject"


def test_nonsense_is_generalized_not_hardcoded_phrases():
    """Variants of dangling / document-writing tasks fail even without the screenshot strings."""
    assert not is_implementable_step("compose her a briefing")
    assert not is_implementable_step("assemble like")
    assert not is_implementable_step("ship them yourself")
    decision = evaluate_source(_doc(GENERALIZED_NONSENSE, "Productivity chat"), title="Productivity chat")
    assert decision.decision in {"reject", "insufficient"}
    with pytest.raises(ProjectGroundingError):
        plan_project(_doc(GENERALIZED_NONSENSE, "Productivity chat"), title="Productivity chat", course_id="gen")


def test_nonsense_chapters_are_not_accepted_as_a_course():
    chapters = [
        "write him a draft",
        "write ChatGPT a draft for sure",
        "write a memo on the nuclear conflict in North Korea",
        "create our memo",
        "implement an algorithm",
        "implement them yourself",
        "build like",
    ]
    with pytest.raises(ProjectGroundingError):
        plan_project(
            _chaptered(chapters, "ChatGPT productivity tips", NONSENSE_TRANSCRIPT),
            title="ChatGPT productivity tips",
            course_id="ch-bad",
        )


# ─── 2. Unrelated source → reject ─────────────────────────────────────────────

def test_unrelated_news_source_is_rejected():
    decision = evaluate_source(_doc(UNRELATED_NEWS, "Nightly News"), title="Nightly News")
    assert decision.decision == "reject"
    assert decision.source_type == "news_commentary"
    assert "may be related to programming" not in decision.user_message.lower()
    with pytest.raises(SourceQualityError) as exc:
        plan_project(_doc(UNRELATED_NEWS, "Nightly News"), title="Nightly News", course_id="news")
    assert exc.value.decision == "reject"


# ─── 3. Empty transcript → reject / insufficient ──────────────────────────────

def test_empty_transcript_is_insufficient():
    decision = evaluate_ingestion(_doc("   ", "Empty"))
    assert decision.decision in {"reject", "insufficient"}
    with pytest.raises(ProjectGroundingError):
        plan_project(_doc("   ", "Empty"), title="Empty", course_id="empty")


def test_nearly_empty_transcript_is_insufficient():
    decision = evaluate_source(_doc("hi there", "Tiny"), title="Tiny")
    assert decision.decision in {"reject", "insufficient"}


# ─── 4. Failed extraction → clear failure ─────────────────────────────────────

class _FailedExtractIngestion(SourceIngestionService):
    async def ingest(self, material_type, content, title="", filename=None):  # noqa: ARG002
        seg = VideoSegment(video_id="abc", title="Video 1", url=content, position=1, transcript="", transcript_source="none")
        return SourceDocument(
            source_type="youtube_url",
            source_url=content,
            source_hash="dead",
            title="Video 1",
            segments=[seg],
            access_level="titles_only",
            access_notes=["Transcript unavailable."],
        )


def test_failed_extraction_is_clear_insufficient_failure():
    doc = asyncio.run(
        _FailedExtractIngestion().ingest("youtube_url", "https://www.youtube.com/watch?v=dQw4w9wg", title="")
    )
    decision = evaluate_ingestion(doc)
    assert decision.decision == "insufficient"
    assert "transcript" in decision.user_message.lower()
    store = _store()
    with pytest.raises(SourceQualityError) as exc:
        asyncio.run(
            build_project(
                _FailedExtractIngestion(),
                store,
                material_type="youtube_url",
                content="https://www.youtube.com/watch?v=dQw4w9wg",
                title="",
                filename=None,
                course_id="project-fail-extract",
            )
        )
    assert exc.value.decision == "insufficient"
    assert store.list_summaries() == []


def test_invalid_youtube_url_is_ingestion_failure():
    with pytest.raises(IngestionError, match="Invalid YouTube URL"):
        asyncio.run(SourceIngestionService().ingest("youtube_url", "https://notyoutube.com/watch?v=123"))


# ─── 5. Valid technical tutorial → accept ─────────────────────────────────────

def test_valid_word_frequency_tutorial_is_accepted():
    decision = evaluate_source(_doc(WORD_COUNT_TRANSCRIPT, "Word Frequency Counter"), title="Word Frequency Counter")
    assert decision.decision == "accept"
    project = plan_project(_doc(WORD_COUNT_TRANSCRIPT), title="Word Frequency Counter", course_id="wc")
    titles = " ".join(m.title.lower() for m in project.milestones)
    assert "count_words" in titles or "collections" in titles
    assert not any("memo" in m.title.lower() for m in project.milestones)


def test_valid_non_gpt2_flask_tutorial_is_accepted():
    """Acceptance is not hardcoded to GPT-2."""
    decision = evaluate_source(_doc(FLASK_TODO_TRANSCRIPT, "Flask Todo API"), title="Flask Todo API")
    assert decision.decision == "accept"
    project = plan_project(_doc(FLASK_TODO_TRANSCRIPT), title="Flask Todo API", course_id="flask")
    kinds = [m.checks[0].kind for m in project.milestones if m.checks]
    assert "import" in kinds
    assert any(m.checks and m.checks[0].target in {"flask", "create_app", "app", "list_todos"} for m in project.milestones)


# ─── 6. Ambiguous technical source → insufficient ─────────────────────────────

def test_ambiguous_technical_source_is_insufficient():
    decision = evaluate_source(_doc(AMBIGUOUS_TECH, "Why Python is Great"), title="Why Python is Great")
    assert decision.decision == "insufficient"
    assert decision.missing_information
    with pytest.raises(SourceQualityError) as exc:
        plan_project(_doc(AMBIGUOUS_TECH, "Why Python is Great"), title="Why Python is Great", course_id="amb")
    assert exc.value.decision == "insufficient"


# ─── 7. Valid source with noisy speech → not auto-rejected ────────────────────

def test_noisy_speech_valid_tutorial_is_accepted():
    decision = evaluate_source(_doc(NOISY_VALID, "Word Frequency Counter"), title="Word Frequency Counter")
    assert decision.decision == "accept"
    project = plan_project(_doc(NOISY_VALID), title="Word Frequency Counter", course_id="noisy")
    assert len([m for m in project.milestones if m.checks and m.checks[0].kind not in {"file_exists", "run_ok"}]) >= 2


# ─── 8. Curriculum with unrelated milestones → reject or regenerate ───────────

def test_unrelated_milestones_are_dropped_or_plan_rejected():
    project = plan_project(_doc(MIXED_TRANSCRIPT), title="Word Frequency Counter", course_id="mixed")
    blob = " ".join((m.title + " " + m.microstep.action).lower() for m in project.milestones)
    assert "memo" not in blob
    assert "nuclear" not in blob
    assert "implement them" not in blob
    assert "build like" not in blob
    assert any("count_words" in m.title or (m.checks and m.checks[0].target == "count_words") for m in project.milestones)


def test_filter_invalid_milestones_drops_dangling_fragments():
    milestones = [
        Milestone(
            id="m1", order=1, title="Set up the project",
            checks=[VerificationCheck(kind="file_exists", target="main.py")],
        ),
        Milestone(
            id="m2", order=2, title="write him a draft",
            microstep=Microstep(action="Build this part: write him a draft."),
            checks=[VerificationCheck(kind="code_contains", target="draft")],
        ),
        Milestone(
            id="m3", order=3, title="Import collections",
            microstep=Microstep(action="import the collections module"),
            checks=[VerificationCheck(kind="import", target="collections")],
        ),
        Milestone(
            id="m4", order=4, title="Define count_words",
            microstep=Microstep(action="define a function called count_words"),
            checks=[VerificationCheck(kind="symbol", target="count_words")],
        ),
        Milestone(
            id="m5", order=5, title="Run and verify the project",
            checks=[VerificationCheck(kind="run_ok", target="")],
        ),
    ]
    kept = filter_invalid_milestones(milestones)
    titles = [m.title.lower() for m in kept]
    assert "write him a draft" not in titles
    assert any("collections" in t or "count_words" in t for t in titles)
    decision = evaluate_milestones(kept, "Build a word frequency counter")
    assert decision.decision == "accept"


# ─── 9. Rejected → no workspace creation ──────────────────────────────────────

def test_rejected_source_does_not_create_workspace():
    store = _store()
    with pytest.raises(ProjectGroundingError):
        asyncio.run(
            build_project(
                SourceIngestionService(),
                store,
                material_type="transcript",
                content=NONSENSE_TRANSCRIPT,
                title="ChatGPT Tips",
                filename=None,
                course_id="project-no-ws",
            )
        )
    assert store.list_summaries() == []
    assert store.get("project-no-ws") is None


# ─── 10. Rejected → no false success / progress ───────────────────────────────

def test_rejected_api_has_no_false_success_or_progress():
    before = {p["course_id"] for p in client.get("/api/create-course/projects").json()}
    res = client.post(
        "/api/create-course/projects",
        json={"material_type": "transcript", "content": NONSENSE_TRANSCRIPT, "title": "ChatGPT Tips"},
    )
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["decision"] in {"reject", "insufficient"}
    assert detail["error"] in {"source_rejected", "source_insufficient", "ungroundable_source"}
    assert "message" in detail
    after = client.get("/api/create-course/projects").json()
    assert {p["course_id"] for p in after} == before
    assert all(p.get("completion_percent", 0) != 0 or p["course_id"] in before for p in after)


def test_rejected_response_is_not_a_zero_percent_course():
    res = client.post(
        "/api/create-course/projects",
        json={"material_type": "transcript", "content": UNRELATED_NEWS, "title": "Nightly News"},
    )
    assert res.status_code == 422
    body = res.json()
    assert "course_id" not in body
    assert "milestones" not in body.get("detail", {})


# ─── 11. Existing valid Create Course behavior intact ─────────────────────────

def test_existing_valid_create_course_api_still_works():
    res = client.post(
        "/api/create-course/projects",
        json={"material_type": "transcript", "content": WORD_COUNT_TRANSCRIPT, "title": "Word Frequency Counter"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["course_id"].startswith("project-")
    assert data["completion_percent"] == 0
    assert data["xp"] == 0
    assert data["completed"] is False
    titles = [m["title"] for m in data["milestones"]]
    assert any("collections" in t or "count_words" in t for t in titles)


def test_native_courses_untouched_by_quality_gate():
    res = client.get("/api/courses")
    assert res.status_code == 200
    ids = [c["id"] for c in res.json()]
    assert any(not i.startswith("project-") for i in ids)


# ─── Analyzer merge (deterministic fake provider) ─────────────────────────────

class _FakeProvider:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    async def generate_structured(self, system, user, max_tokens=400):  # noqa: ARG002
        return self.payload


def test_llm_analyzer_cannot_override_high_confidence_reject():
    prior = evaluate_source(_doc(UNRELATED_NEWS, "Nightly News"), title="Nightly News")
    assert prior.decision == "reject" and prior.confidence == "high"
    analyzer = LlmSourceAnalyzer(_FakeProvider('{"decision":"accept","project_goal":"invented","technical_evidence":["python"],"rejection_reasons":[],"missing_information":[],"confidence":"high","source_type":"coding_tutorial"}'))
    merged = asyncio.run(evaluate_source_with_analyzer(_doc(UNRELATED_NEWS, "Nightly News"), "Nightly News", analyzer))
    assert merged.decision == "reject"


def test_quality_decision_schema_fields_present():
    decision = evaluate_source(_doc(WORD_COUNT_TRANSCRIPT), title="Word Frequency Counter")
    payload = decision.to_public_dict()
    for key in (
        "decision",
        "quality_score",
        "project_goal",
        "source_type",
        "technical_evidence",
        "rejection_reasons",
        "missing_information",
        "confidence",
    ):
        assert key in payload
    assert payload["decision"] == "accept"
    assert payload["quality_score"] >= 0.5


# ─── Live-failure classes (generalized; not hardcoded video IDs) ──────────────

ASSISTANT_TIPS_TITLE = "36 Assistant Tips for Beginners (Become a PRO!)"
ASSISTANT_TIPS_CHAPTERS = [
    "Prompt follow-up questions",
    "Assign roles to ChatGPT",
    "Use natural language",
    "Set your context",
    "Rename your chat logs",
    "Utilize prompt sequences",
    "Archive your chats",
    "Use custom instructions",
    "Speak with ChatGPT",
    "Utilize output formatting",
]
ASSISTANT_TIPS_DESC = """
36 ChatGPT Tips for Beginners. Master prompting and custom instructions.
Write a birthday letter, then ask ChatGPT to act as a pirate.
Generate product descriptions for an e-commerce store.
Rename your chat logs and archive chats you want to keep.
"""

CLAUDE_PRODUCTIVITY = """
Welcome to Claude prompts to 10x your writing.
Ask Claude to draft an email for your boss.
Use custom instructions so the assistant always writes in your voice.
Speak with the chatbot and save the chat logs for later.
"""

NEWS_COMMENTARY_TITLE = "Governor reacts to critics saying the CEO is in charge"
NEWS_COMMENTARY_DESC = """
President-elect Jane Doe praised a donor at the rally and responded to criticism
that a private CEO is actually running the administration.
Republican strategist Alex Chen and Democratic strategist Morgan Lee join to discuss.
"""

CONCEPTUAL_TITLE = "But what is a neural network? | Deep learning chapter 1"
CONCEPTUAL_CHAPTERS = [
    "Introduction example",
    "Series preview",
    "What are neurons?",
    "Introducing layers",
    "Why layers?",
    "Edge detection example",
    "Counting weights and biases",
    "How learning relates",
    "Notation and linear algebra",
    "Recap",
    "Some final words",
]
CONCEPTUAL_DESC = """
But what is a neural network? What are the neurons, why are there layers,
and what is the math underlying it? We discuss backpropagation and gradient
descent at a high level so the intuition clicks. Help fund future lessons.
"""

GPT2_STYLE_CHAPTERS = [
    "intro: reproduce GPT-2",
    "exploring the GPT-2 (124M) OpenAI checkpoint",
    "SECTION 1: implementing the GPT-2 nn.Module",
    "implementing the forward pass to get logits",
    "sampling loop",
    "cross entropy loss",
    "data loader lite",
    "parameter sharing wte and lm_head",
    "float16, gradient scalers, bfloat16",
]

PASSING_ASSISTANT_MENTION = """
In this tutorial we build a word frequency counter in Python.
First, import the collections module.
Next, define a function called count_words that takes a text string.
Then create a variable called sample containing some text.
Call count_words on the sample.
Finally, print the result so you can see the counts.
If you get stuck you can ask ChatGPT to explain a traceback, but you still write the code.
"""


def test_assistant_tips_source_is_analysis_reject():
    doc = _chaptered(
        ASSISTANT_TIPS_CHAPTERS,
        ASSISTANT_TIPS_TITLE,
        ASSISTANT_TIPS_DESC,
    )
    decision = evaluate_source(doc, title=ASSISTANT_TIPS_TITLE)
    assert decision.decision == "reject"
    assert decision.source_type == "assistant_usage"
    assert decision.stage == "analysis"
    assert "assistant" in decision.user_message.lower() or "prompt" in decision.user_message.lower()
    assert "may be related to programming" not in decision.user_message.lower()
    with pytest.raises(SourceQualityError) as exc:
        plan_project(doc, title=ASSISTANT_TIPS_TITLE, course_id="tips-bad")
    assert exc.value.decision == "reject"
    assert exc.value.quality.stage == "analysis"


def test_assistant_tips_class_is_generalized_not_one_product():
    decision = evaluate_source(_doc(CLAUDE_PRODUCTIVITY, "Claude prompts to 10x your writing"))
    assert decision.decision == "reject"
    assert decision.source_type == "assistant_usage"


def test_news_commentary_is_rejected_not_ambiguous_technical():
    decision = evaluate_source(_doc(NEWS_COMMENTARY_DESC, NEWS_COMMENTARY_TITLE), title=NEWS_COMMENTARY_TITLE)
    assert decision.decision == "reject"
    assert decision.source_type == "news_commentary"
    assert "may be related to programming" not in decision.user_message.lower()
    assert "news" in decision.user_message.lower() or "comment" in decision.user_message.lower()


def test_conceptual_explainer_is_not_turned_into_a_build_along():
    doc = _chaptered(CONCEPTUAL_CHAPTERS, CONCEPTUAL_TITLE, CONCEPTUAL_DESC)
    decision = evaluate_source(doc, title=CONCEPTUAL_TITLE)
    assert decision.decision in {"reject", "insufficient"}
    assert decision.decision != "accept"
    assert decision.source_type == "conceptual_explainer"
    assert "implement a project" in decision.user_message.lower() or "intuition" in decision.user_message.lower()
    with pytest.raises(ProjectGroundingError):
        plan_project(doc, title=CONCEPTUAL_TITLE, course_id="nn-explainer")


def test_conceptual_explainer_api_does_not_create_invented_milestones():
    before = {p["course_id"] for p in client.get("/api/create-course/projects").json()}
    res = client.post(
        "/api/create-course/projects",
        json={
            "material_type": "transcript",
            "content": CONCEPTUAL_TITLE + "\n" + CONCEPTUAL_DESC + "\n" + "\n".join(CONCEPTUAL_CHAPTERS),
            "title": CONCEPTUAL_TITLE,
        },
    )
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["decision"] in {"reject", "insufficient"}
    blob = json.dumps(detail).lower()
    assert "implement backpropagation" not in blob
    assert "build a neural net" not in blob
    assert "train with gradient descent" not in blob
    after = {p["course_id"] for p in client.get("/api/create-course/projects").json()}
    assert after == before


def test_assistant_tips_api_is_source_rejected_not_ungroundable():
    before = {p["course_id"] for p in client.get("/api/create-course/projects").json()}
    res = client.post(
        "/api/create-course/projects",
        json={
            "material_type": "transcript",
            "content": ASSISTANT_TIPS_DESC + "\n" + "\n".join(ASSISTANT_TIPS_CHAPTERS),
            "title": ASSISTANT_TIPS_TITLE,
        },
    )
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["decision"] == "reject"
    assert detail["error"] == "source_rejected"
    assert detail.get("source_type") == "assistant_usage"
    assert {p["course_id"] for p in client.get("/api/create-course/projects").json()} == before


def test_news_commentary_api_is_source_rejected():
    res = client.post(
        "/api/create-course/projects",
        json={"material_type": "transcript", "content": NEWS_COMMENTARY_DESC, "title": NEWS_COMMENTARY_TITLE},
    )
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["decision"] == "reject"
    assert detail["error"] == "source_rejected"
    assert detail.get("source_type") == "news_commentary"
    assert "may be related to programming" not in detail.get("message", "").lower()


def test_karpathy_style_chapter_tutorial_is_still_accepted():
    doc = _chaptered(
        GPT2_STYLE_CHAPTERS,
        "Let's reproduce GPT-2 (124M)",
        "Let's reproduce GPT-2 (124M) from scratch in PyTorch. GitHub https://github.com/karpathy/build-nanogpt",
    )
    decision = evaluate_source(doc, title="Let's reproduce GPT-2 (124M)")
    assert decision.decision == "accept"
    project = plan_project(doc, title="Let's reproduce GPT-2 (124M)", course_id="gpt2-live-style")
    titles = " ".join(m.title.lower() for m in project.milestones)
    assert "nn.module" in titles
    assert "forward pass" in titles
    assert "implement backpropagation" not in titles


def test_assistant_tips_marketing_follow_along_does_not_count_as_a_build():
    """Live ChatGPT-tips pages say 'follow along' and mention OpenAI/GPT-4 without code."""
    desc = (
        "This video offers a comprehensive guide on mastering ChatGPT, the cutting-edge "
        "product of OpenAI's GPT-4 technology. We unravel 36 invaluable tips. "
        "Follow along and be amazed by the sheer power of ChatGPT! "
        "From prompt engineering to custom instructions, I cover it all. "
        "Assign roles to ChatGPT and speak with ChatGPT. Write a birthday letter."
    )
    doc = _chaptered(ASSISTANT_TIPS_CHAPTERS, "36 ChatGPT Tips for Beginners in 2024!", desc)
    decision = evaluate_source(doc, title="36 ChatGPT Tips for Beginners in 2024!")
    assert decision.decision == "reject"
    assert decision.source_type == "assistant_usage"


def test_conceptual_explainer_without_extracted_chapters_is_still_blocked():
    """Reader-proxy pages sometimes drop chapters; title+description must still fail."""
    desc = (
        "But what is a neural network? What are the neurons, why are there layers, "
        "and what is the math underlying it? Help fund future projects. "
        "We discuss backpropagation and gradient descent at a high level. "
        "Written/interactive form of this series: https://www.3blue1brown.com/topics/neural-networks"
    )
    doc = _chaptered([], CONCEPTUAL_TITLE, desc)
    decision = evaluate_source(doc, title=CONCEPTUAL_TITLE)
    assert decision.decision in {"reject", "insufficient"}
    assert decision.source_type == "conceptual_explainer"
    with pytest.raises(ProjectGroundingError):
        plan_project(doc, title=CONCEPTUAL_TITLE, course_id="nn-nochapters")
    decision = evaluate_source(_doc(PASSING_ASSISTANT_MENTION, "Word Frequency Counter"))
    assert decision.decision == "accept"
    project = plan_project(_doc(PASSING_ASSISTANT_MENTION), title="Word Frequency Counter", course_id="ask-aside")
    assert any(m.checks and m.checks[0].target == "count_words" for m in project.milestones)
