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
    code_ident_for_import,
    learner_facing_fields,
    looks_like_raw_transcript,
)
from backend.project_models import (
    Microstep,
    Milestone,
    ProjectCourse,
    ProjectView,
    VerificationCheck,
)
from backend.project_planner import plan_project
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
