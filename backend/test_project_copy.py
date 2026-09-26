"""Regression tests for Create Course learner-facing copy (description / Why / instructions).

Covers the GPT-2 caption-dump bugs without hardcoding that tutorial as the only path:
A) milestone description is not a giant raw transcript
B) Why is a concise explanation, not a full caption
C) explanation stays relevant to the milestone and source
D) other Create Course tutorials still plan correctly
E) persisted dump payloads are sanitized at the API projection (existing courses)
"""
from backend.project_copy import (
    apply_learner_facing_copy,
    beginner_action,
    beginner_observation,
    beginner_teach,
    code_ident_for_import,
    contains_banned_learner_phrase,
    is_follow_source_template,
    needs_learner_fallback,
    learner_description,
    learner_facing_fields,
    learner_hint,
    learner_why,
    looks_like_raw_transcript,
    polish_project_copy,
)
from backend.project_models import (
    Microstep,
    Milestone,
    ProjectCourse,
    ProjectView,
    VerificationCheck,
)
from backend.project_planner import plan_project, scrub_project_learner_copy
from backend.source_ingestion import SourceDocument


def _doc(text: str, title: str) -> SourceDocument:
    return SourceDocument(
        source_type="transcript",
        source_url="",
        source_hash="hash-copy",
        title=title,
        plain_text=text,
    )


# Spoken-caption style: almost no punctuation, fillers, the reported phrase.
GPT2_RAW_CAPTION = (
    "hello everybody welcome back today we are going to reproduce gpt-2 from scratch "
    "going from tensor flow to pytorch Friendly and so it's much easier to load and work with "
    "huggingface transformers so import Transformers and then we can load the gpt-2 model "
    "with from_pretrained and so we start by writing the neural net so define a class called GPT "
    "and then implement the forward method so that it returns the logits and then we import tiktoken "
    "to tokenize the text and then we can sample from the model and print the result"
)

FLASK_TRANSCRIPT = """
In this tutorial we build a small Flask API.
First, import flask.
Next, define a function called hello.
Then call hello.
Finally, print the result so you can see the response.
"""

WORD_COUNT = """
In this tutorial we build a word frequency counter in Python.
First, import the collections module.
Next, define a function called count_words that takes a text string.
Then create a variable called sample containing some text.
Call count_words on the sample.
Finally, print the result so you can see the counts.
"""

DUMP_PHRASE = "tensor flow to pytorch"


def test_looks_like_raw_transcript_detects_caption_dumps():
    assert looks_like_raw_transcript(GPT2_RAW_CAPTION) is True
    assert looks_like_raw_transcript("Load the collections library so you can count words.") is False


def test_title_case_import_becomes_pep8_package_name():
    # Spoken captions say "Transformers"; the package is transformers.
    assert code_ident_for_import("Transformers") == "transformers"
    assert code_ident_for_import("Flask") == "flask"
    assert code_ident_for_import("GPT2LMHeadModel") == "GPT2LMHeadModel"
    assert code_ident_for_import("PIL") == "PIL"


def test_a_generated_milestone_does_not_expose_giant_raw_transcript():
    project = plan_project(_doc(GPT2_RAW_CAPTION, "Reproduce GPT-2"), "Reproduce GPT-2", "project-cap")
    dump_hits = []
    for m in project.milestones:
        for field in (
            m.source_grounded_description,
            m.why,
            m.microstep.action,
            m.microstep.hint,
            m.teach,
            m.source_quote,
        ):
            assert len(field or "") <= 420, f"{m.title} field too long: {field[:80]!r}"
            assert DUMP_PHRASE not in (field or "").lower()
            if looks_like_raw_transcript(field):
                dump_hits.append((m.title, field[:80]))
    assert dump_hits == []


def test_b_why_is_concise_explanation_not_full_transcript():
    project = plan_project(_doc(GPT2_RAW_CAPTION, "Reproduce GPT-2"), "Reproduce GPT-2", "project-cap")
    import_ms = next(m for m in project.milestones if m.checks and m.checks[0].kind == "import")
    assert import_ms.why
    assert len(import_ms.why) <= 420
    assert DUMP_PHRASE not in import_ms.why.lower()
    assert "from the source:" not in import_ms.why.lower()
    # Why explains the step; it is not a caption paste.
    assert looks_like_raw_transcript(import_ms.why) is False
    # Source excerpt, if any, is a tight phrase — not the rest of the caption.
    if import_ms.source_quote:
        assert len(import_ms.source_quote) <= 160
        assert "from_pretrained" not in import_ms.source_quote.lower()
        assert DUMP_PHRASE not in import_ms.source_quote.lower()


def test_c_explanation_stays_relevant_to_milestone_and_source():
    project = plan_project(_doc(GPT2_RAW_CAPTION, "Reproduce GPT-2"), "Reproduce GPT-2", "project-cap")
    imports = [m for m in project.milestones if m.checks and m.checks[0].kind == "import"]
    assert imports, "caption mentioning import Transformers must yield an import milestone"
    # Canonical package name (not the spoken Title-Case token) is what we verify.
    targets = {m.checks[0].target.lower() for m in imports}
    assert "transformers" in targets or "tiktoken" in targets or "torch" in targets
    for m in imports:
        pkg = m.checks[0].target.lower()
        blob = f"{m.source_grounded_description} {m.why} {m.microstep.action} {m.microstep.hint}".lower()
        assert pkg in blob
        assert "import" in blob
        assert DUMP_PHRASE not in blob
        # Instructions must not use the awkward "Add an 'import X'" wording.
        assert "add an" not in m.microstep.action.lower()
        assert "add an" not in m.microstep.hint.lower()


def test_d_other_create_course_tutorials_still_plan():
    words = plan_project(_doc(WORD_COUNT, "Word Frequency Counter"), "Word Frequency Counter", "project-wc")
    kinds = [(m.checks[0].kind, m.checks[0].target) for m in words.milestones if m.checks]
    assert ("import", "collections") in kinds
    assert ("symbol", "count_words") in kinds
    for m in words.milestones:
        assert not looks_like_raw_transcript(m.source_grounded_description)
        assert not looks_like_raw_transcript(m.why)
        assert len(m.source_grounded_description) <= 280

    flask = plan_project(_doc(FLASK_TRANSCRIPT, "Flask API"), "Flask API", "project-flask")
    kinds = [(m.checks[0].kind, m.checks[0].target) for m in flask.milestones if m.checks]
    assert ("import", "flask") in kinds
    assert ("symbol", "hello") in kinds
    import_ms = next(m for m in flask.milestones if m.checks[0].kind == "import")
    assert "flask" in import_ms.microstep.action.lower()
    assert "transformers" not in import_ms.microstep.action.lower()


def test_e_persisted_dump_is_sanitized_on_read_without_mutating_store():
    dump = GPT2_RAW_CAPTION
    milestone = Milestone(
        id="m2",
        order=2,
        title="Import Transformers",
        source_grounded_description=dump[:2000],
        source_quote=dump[:2000],
        why=dump[:2000],
        teach=dump[:1200],
        microstep=Microstep(
            observation=dump[:400],
            action=f"Add an 'import Transformers' (or 'from Transformers import ...') statement. {dump[:200]}",
            hint="Add an 'import Transformers' (or 'from Transformers import ...') statement.",
        ),
        checks=[VerificationCheck(kind="import", target="Transformers", description="Your code imports `Transformers`.")],
        xp_reward=20,
    )
    project = ProjectCourse(
        course_id="project-old",
        title="Reproduce GPT-2",
        source_hash="h",
        project_goal="Reproduce GPT-2 from the video",
        entry_file="main.py",
        milestones=[milestone],
        workspace_files=[],
    )
    stored_desc = project.milestones[0].source_grounded_description
    view = ProjectView.from_project(project)
    # Stored course is unchanged (no silent rewrite of learner progress files).
    assert project.milestones[0].source_grounded_description == stored_desc
    mv = view.milestones[0]
    assert DUMP_PHRASE not in mv.source_grounded_description.lower()
    assert DUMP_PHRASE not in mv.why.lower()
    assert DUMP_PHRASE not in mv.microstep.action.lower()
    assert DUMP_PHRASE not in (mv.source_quote or "").lower()
    assert looks_like_raw_transcript(mv.source_grounded_description) is False
    assert looks_like_raw_transcript(mv.why) is False
    assert "transformers" in mv.microstep.action.lower()
    assert "add an" not in mv.microstep.action.lower()
    assert "import" in mv.source_grounded_description.lower()


def test_apply_copy_is_generic_not_hardcoded_to_gpt2():
    m = Milestone(
        id="m2",
        order=2,
        title="Import requests",
        source_grounded_description=GPT2_RAW_CAPTION[:2000],
        source_quote=GPT2_RAW_CAPTION[:2000],
        microstep=Microstep(action="", hint=""),
        checks=[VerificationCheck(kind="import", target="requests")],
        xp_reward=20,
    )
    apply_learner_facing_copy(m, entry_file="app.py", project_title="HTTP client", project_goal="Fetch JSON")
    assert "requests" in m.source_grounded_description.lower()
    assert "app.py" in m.microstep.action
    assert "gpt-2" not in m.source_grounded_description.lower()
    assert "transformers" not in m.source_grounded_description.lower()
    fields = learner_facing_fields(m, entry_file="app.py", project_title="HTTP client")
    assert fields["why"]
    assert "requests" in fields["why"].lower()


def _learner_blob(project: ProjectCourse) -> str:
    parts: list[str] = [project.project_goal or "", project.course_intro or ""]
    for m in project.milestones:
        parts.extend(
            [
                m.source_grounded_description or "",
                m.why or "",
                m.teach or "",
                m.hook or "",
                m.example or "",
                m.celebrate or "",
                (m.microstep.action if m.microstep else "") or "",
                (m.microstep.hint if m.microstep else "") or "",
                (m.microstep.observation if m.microstep else "") or "",
            ]
        )
    return "\n".join(parts)


def test_templates_have_zero_video_or_instructor_words():
    """Deterministic fallbacks must never mention video/instructor/watch-the-video."""
    kinds = [
        ("import", "collections"),
        ("symbol", "Value"),
        ("function_call", "backward"),
        ("code_contains", "tanh|grad"),
        ("file_exists", "main.py"),
        ("stdout_contains", ""),
        ("run_ok", ""),
    ]
    blobs = []
    for kind, target in kinds:
        blobs.append(learner_description(kind, target, title="Build Value", entry_file="main.py", project_title="Micrograd"))
        blobs.append(learner_why(kind, target, title="Build Value", project_title="Micrograd"))
        blobs.append(beginner_action(kind, target, entry_file="main.py", title="Build Value"))
        blobs.append(beginner_observation(kind, target, title="Build Value"))
        blobs.append(beginner_teach(kind, target, title="Build Value"))
        blobs.append(learner_hint(kind, target))
    joined = "\n".join(blobs)
    assert not contains_banned_learner_phrase(joined), joined
    assert "video" not in joined.lower()
    assert "instructor" not in joined.lower()


def test_scrub_enrich_preserve_good_ai_actions_strip_video_phrases():
    """Good AI action/teach/why/hint survive polish; banned video templates do not reappear."""
    good_action = (
        "1. In `main.py`, define class `Value` with `__init__` storing data and grad.\n"
        "2. Implement `__add__` and `__mul__` so expressions build a graph.\n"
        "3. Save, then click NEXT."
    )
    good_teach = (
        "Value is the scalar wrapper that tracks data and grad for backprop. "
        "Defining it first lets later ops attach to the same graph."
    )
    good_why = "Micrograd needs Value before you can build expression graphs."
    dirty_obs = "Build this the way the video does — copy the instructor."

    milestones = [
        Milestone(
            id="m1",
            order=1,
            title="Set up the project",
            source_grounded_description="Create main.py for the micrograd build.",
            why="One persistent workspace for the whole project.",
            teach="",
            microstep=Microstep(
                observation="Workspace ready.",
                action="Create `main.py` and add a project goal comment.",
                hint="Files persist across milestones.",
            ),
            checks=[VerificationCheck(kind="file_exists", target="main.py")],
            xp_reward=10,
        ),
        Milestone(
            id="m2",
            order=2,
            title="Define Value",
            source_grounded_description="Define the Value class for autograd scalars.",
            why=good_why,
            teach=good_teach,
            microstep=Microstep(
                observation=dirty_obs,
                action=good_action,
                hint="Keep the class name exactly Value.",
            ),
            checks=[VerificationCheck(kind="symbol", target="Value", description="Defines Value")],
            xp_reward=25,
        ),
        Milestone(
            id="m3",
            order=3,
            title="Implement tanh",
            source_grounded_description="Add tanh on Value for neuron activations.",
            why="Follow the video for this section in main.py",
            teach="Type the instructor snippet for tanh.",
            microstep=Microstep(
                observation="Next up from the video:",
                action="Write the code the instructor builds for tanh.",
                hint="Follow the video for this section in main.py",
            ),
            checks=[VerificationCheck(kind="code_contains", target="tanh")],
            xp_reward=25,
        ),
    ]
    project = ProjectCourse(
        course_id="project-ai-keep",
        title="Micrograd",
        project_goal="Build a tiny autograd engine",
        entry_file="main.py",
        milestones=milestones,
        workspace_files=[],
        tech_stack=["Python"],
    )

    # Simulate post-AI polish path
    polish_project_copy(project)
    scrub_project_learner_copy(project)

    # Good AI fields preserved
    m2 = project.milestones[1]
    assert m2.microstep.action == good_action
    assert m2.teach == good_teach
    assert m2.why == good_why

    blob = _learner_blob(project)
    assert not contains_banned_learner_phrase(blob), blob
    assert "video" not in blob.lower(), blob
    assert "instructor" not in blob.lower(), blob

    # Dirty milestone was rewritten to concrete, non-video copy
    m3 = project.milestones[2]
    assert "video" not in (m3.microstep.action or "").lower()
    assert "instructor" not in (m3.microstep.action or "").lower()
    assert m3.microstep.action
    assert "tanh" in (m3.microstep.action + m3.microstep.hint + m3.teach).lower()


def test_follow_source_phrases_are_banned_and_need_fallback():
    samples = [
        "Follow the source for this step, then click NEXT.",
        "Please follow the transcript carefully.",
        "Do it as in the source.",
        "According to the instructor, write Value.",
    ]
    for s in samples:
        assert contains_banned_learner_phrase(s) or is_follow_source_template(s), s
        assert needs_learner_fallback(s), s

