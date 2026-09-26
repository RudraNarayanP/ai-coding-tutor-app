"""Tests for source-grounded guided-project planning (Create Course only)."""
import re
import pytest

from backend.project_planner import (
    ProjectGroundingError,
    _extract_target,
    looks_like_raw_transcript,
    plan_project,
    validate_project,
)
from backend.source_ingestion import SourceDocument


WORD_COUNT_TRANSCRIPT = """
In this tutorial we build a word frequency counter in Python.
First, import the collections module.
Next, define a function called count_words that takes a text string.
Then create a variable called sample containing some text.
Call count_words on the sample.
Finally, print the result so you can see the counts.
"""


def _doc(text: str, title: str = "Word Frequency Counter") -> SourceDocument:
    return SourceDocument(
        source_type="transcript",
        source_url="",
        source_hash="hash123",
        title=title,
        plain_text=text,
    )


def test_plan_is_grounded_in_source_steps():
    project = plan_project(_doc(WORD_COUNT_TRANSCRIPT), title="Word Frequency Counter", course_id="project-test")

    kinds = [(m.checks[0].kind, m.checks[0].target) for m in project.milestones if m.checks]
    # Setup milestone first.
    assert kinds[0] == ("file_exists", "main.py")
    # Source-grounded structural milestones appear in order.
    assert ("import", "collections") in kinds
    assert ("symbol", "count_words") in kinds
    assert ("symbol", "sample") in kinds
    assert ("function_call", "count_words") in kinds
    # A run milestone closes the project.
    assert any(k == "run_ok" for k, _ in kinds)


def test_milestones_keep_source_quotes():
    project = plan_project(_doc(WORD_COUNT_TRANSCRIPT), title="Word Frequency Counter", course_id="project-test")
    import_ms = next(m for m in project.milestones if m.checks and m.checks[0].kind == "import")
    # The milestone preserves the actual source sentence for transparency.
    assert "import" in import_ms.source_quote.lower()
    # Learner-facing action is synthesized — not the raw source sentence.
    assert import_ms.microstep.action
    assert "import" in import_ms.microstep.action.lower()
    assert not looks_like_raw_transcript(import_ms.microstep.action)


def test_long_transcript_chunks_do_not_break_milestone_validation():
    """Dense transcripts must be chunked/clipped so Pydantic field limits still hold."""
    from backend.project_planner import _chunk_long_step, _clip

    long_blob = "import torch " + ("and numpy " * 400) + "to build the model."
    chunks = _chunk_long_step(long_blob, max_len=800)
    assert chunks, "expected at least one chunk"
    assert all(len(chunk) <= 800 for chunk in chunks)
    assert len(_clip(long_blob, 2000)) <= 2000
    assert len(_clip(long_blob, 400)) <= 400

    # Accepted plans also stay within learner-facing field caps.
    project = plan_project(_doc(WORD_COUNT_TRANSCRIPT), title="Word Frequency Counter", course_id="project-long")
    for milestone in project.milestones:
        assert len(milestone.source_quote) <= 2000
        assert len(milestone.source_grounded_description) <= 2000
        assert len(milestone.microstep.action) <= 400

def test_tech_stack_detected_from_source():
    project = plan_project(_doc(WORD_COUNT_TRANSCRIPT), title="Word Frequency Counter", course_id="project-test")
    assert "collections" in project.tech_stack


def test_seed_workspace_has_entry_file():
    project = plan_project(_doc(WORD_COUNT_TRANSCRIPT), title="Word Frequency Counter", course_id="project-test")
    assert project.entry_file == "main.py"
    assert any(f.path == "main.py" for f in project.workspace_files)


def test_ungroundable_source_raises_clear_error():
    weak = "I really like turtles. The weather today is nice. Please subscribe and hit the bell."
    with pytest.raises(ProjectGroundingError):
        plan_project(_doc(weak, title="Random Vlog"), title="Random Vlog", course_id="project-x")


def test_empty_source_raises_clear_error():
    with pytest.raises(ProjectGroundingError):
        plan_project(_doc("   ", title="Empty"), title="Empty", course_id="project-x")


GPT2_TRANSCRIPT = """
In this video we reproduce GPT-2 from scratch in PyTorch.
First, import torch and import torch.nn as nn.
Let's load the reference weights, so from transformers import GPT2LMHeadModel.
Now define a dataclass called GPTConfig that holds the hyperparameters.
Next, define a class called CausalSelfAttention that implements attention.
Then define a class called MLP for the feed forward network.
Now define a class called Block that combines attention and MLP.
Define a class called GPT that inherits from nn dot Module.
Implement the forward method so that it returns the logits.
Add a method called from_pretrained that loads the GPT-2 weights.
Let's use tiktoken, so import tiktoken.
Finally, print the loss so you can watch it go down.
"""


def test_symbol_case_is_preserved_for_real_class_names():
    # Critical: checks must use the learner's real casing (GPT, not gpt), else a
    # correct implementation could never be verified.
    project = plan_project(_doc(GPT2_TRANSCRIPT), title="Reproduce GPT-2", course_id="project-gpt2")
    symbols = [m.checks[0].target for m in project.milestones if m.checks and m.checks[0].kind == "symbol"]
    assert "GPTConfig" in symbols
    assert "CausalSelfAttention" in symbols
    assert "GPT" in symbols
    assert "MLP" in symbols
    # No lowercased duplicates that would never match real code.
    assert "gpt" not in symbols and "gptconfig" not in symbols


def test_the_x_method_extracts_method_name_not_filler():
    project = plan_project(_doc(GPT2_TRANSCRIPT), title="Reproduce GPT-2", course_id="project-gpt2")
    symbols = [m.checks[0].target for m in project.milestones if m.checks and m.checks[0].kind == "symbol"]
    assert "forward" in symbols  # from "Implement the forward method"
    assert "so" not in symbols   # filler word must never become a symbol


def test_ml_tech_stack_detected():
    project = plan_project(_doc(GPT2_TRANSCRIPT), title="Reproduce GPT-2", course_id="project-gpt2")
    assert "torch" in project.tech_stack
    assert "transformers" in project.tech_stack
    assert "tiktoken" in project.tech_stack


def test_from_import_uses_package_root():
    project = plan_project(_doc(GPT2_TRANSCRIPT), title="Reproduce GPT-2", course_id="project-gpt2")
    imports = [m.checks[0].target for m in project.milestones if m.checks and m.checks[0].kind == "import"]
    assert "transformers" in imports
    assert "GPT2LMHeadModel" not in imports  # must be the module, not the symbol
    assert "Transformers" not in imports  # spoken Title-Case must be canonicalized


def test_unpunctuated_caption_does_not_collapse_to_one_transcript_milestone():
    caption = (
        "hello everybody welcome back going from tensor flow to pytorch Friendly and so it's "
        "much easier to load and work with huggingface transformers so import Transformers "
        "and then we import torch and then define a class called GPT and then implement the "
        "forward method so that it returns the logits and then print the result"
    )
    project = plan_project(_doc(caption, title="Reproduce GPT-2"), title="Reproduce GPT-2", course_id="project-raw")
    imports = [m.checks[0].target.lower() for m in project.milestones if m.checks and m.checks[0].kind == "import"]
    assert "transformers" in imports
    assert "torch" in imports
    for m in project.milestones:
        assert "tensor flow to pytorch" not in (m.source_grounded_description or "").lower()
        assert "tensor flow to pytorch" not in (m.why or "").lower()
        assert len(m.source_grounded_description or "") <= 280


def _chaptered_doc(chapters, title="Reproduce GPT-2 (124M)"):
    from backend.source_ingestion import VideoSegment
    seg = VideoSegment(
        video_id="vid1", title=title, url="", position=1,
        transcript=f"{title}. Chapters. " + " ".join(chapters), chapters=list(chapters),
    )
    return SourceDocument(
        source_type="youtube_url", source_url="https://youtu.be/vid1", source_hash="h",
        title=title, segments=[seg], access_level="full",
    )


GPT2_CHAPTERS = [
    "intro: reproduce GPT-2",
    "SECTION 1: implementing the GPT-2 nn.Module",
    "implementing the forward pass to get logits",
    "sampling loop",
    "cross entropy loss",
    "data loader lite",
    "flash attention",
    "SECTION 3: hyperparameters, AdamW, gradient clipping",
]


def test_chapter_based_plan_builds_grounded_milestones():
    project = plan_project(_chaptered_doc(GPT2_CHAPTERS), title="Reproduce GPT-2 (124M)", course_id="project-yt")
    titles = [m.title for m in project.milestones]
    # Real chapters become milestones (meta "intro" is skipped).
    assert any("nn.Module" in t for t in titles)
    assert any("cross entropy loss" in t for t in titles)
    assert any("flash attention" in t for t in titles)
    assert not any(t.lower().startswith("intro") for t in titles)
    # Concept-level checks are used so alternative implementations are accepted.
    kinds = {m.checks[0].kind for m in project.milestones if m.checks}
    assert "code_contains" in kinds
    assert project.milestones[0].checks[0].kind == "file_exists"
    assert project.milestones[-1].checks[0].kind == "run_ok"


def test_vague_video_with_few_buildable_chapters_is_rejected():
    vague = ["intro", "my story", "please subscribe", "thanks for watching", "outro", "sponsor message"]
    with pytest.raises(ProjectGroundingError):
        plan_project(_chaptered_doc(vague, title="Vlog"), title="Vlog", course_id="project-vague")


def test_milestones_have_strictly_increasing_order():
    project = plan_project(_doc(WORD_COUNT_TRANSCRIPT), title="Word Frequency Counter", course_id="project-test")
    orders = [m.order for m in project.milestones]
    assert orders == sorted(orders)
    assert orders[0] == 1
    assert len(set(orders)) == len(orders)


MICROGRAD_CHAPTERS = [
    "intro",
    "micrograd overview",
    "derivative of a simple function with one input",
    "starting the core Value object of micrograd and its visualization",
    "manual backpropagation example #1: simple expression",
    "implementing the backward function for each operation",
    "collecting all of the parameters of the neural net",
    "doing gradient descent optimization manually, training the network",
]


def test_livecoding_theory_chapters_are_kept_and_not_mapped_to_adamw():
    """Expert whiteboard / from-scratch lessons must not be declined or GPT-2-tokenized."""
    project = plan_project(
        _chaptered_doc(MICROGRAD_CHAPTERS, title="building micrograd"),
        title="building micrograd",
        course_id="project-micrograd",
    )
    titles = " ".join(m.title.lower() for m in project.milestones)
    assert "derivative" in titles
    assert "value object" in titles or "micrograd" in titles
    assert "backpropagation" in titles or "backward" in titles
    params = next(m for m in project.milestones if "parameters of the neural" in m.title.lower())
    assert "parameters" in (params.checks[0].target or "")
    assert "AdamW" not in (params.checks[0].target or "")
    for m in project.milestones:
        if m.checks:
            assert "AdamW" not in (m.checks[0].target or "")


def test_podcast_style_source_is_rejected():
    podcast = _chaptered_doc(
        ["Introduction", "Neural networks", "Biology", "Aliens", "Universe", "Transformers"],
        title="Tesla AI, Aliens, and AGI | Some Technical Podcast #333",
    )
    with pytest.raises(ProjectGroundingError, match="podcast|interview|conversation"):
        plan_project(podcast, title="Tesla AI, Aliens, and AGI | Some Technical Podcast #333", course_id="pod")


def test_follow_along_description_grounds_milestones_without_url_allowlist():
    from backend.source_ingestion import VideoSegment

    desc = (
        "Original lecture on neural networks. GitHub https://github.com/example/micrograd "
        "In this video I follow the lecture on how to build Micrograd, how to train Neural "
        "Networks and implementing Backpropagation."
    )
    seg = VideoSegment(
        video_id="abc123abc12",
        title="I completed the AI challenge (advanced)",
        url="https://youtu.be/abc123abc12",
        position=1,
        transcript=desc,
        chapters=[],
        description_snippet=desc[:500],
    )
    doc = SourceDocument(
        source_type="youtube_url",
        source_url="https://youtu.be/abc123abc12",
        source_hash="h",
        title=seg.title,
        segments=[seg],
        access_level="full",
    )
    project = plan_project(doc, title=seg.title, course_id="follow")
    blob = " ".join((m.title + " " + m.source_quote).lower() for m in project.milestones)
    assert "micrograd" in blob or "backprop" in blob or "neural" in blob
    assert len([m for m in project.milestones if m.checks and m.checks[0].kind != "file_exists"]) >= 2
    titles = [m.title.lower() for m in project.milestones]
    # Description phrases must not emit duplicate micrograd/neural-net milestones.
    assert sum("micrograd" in t for t in titles) == 1
    assert sum("neural" in t for t in titles) <= 1


def test_playlist_tutorial_titles_become_grounded_milestones():
    from backend.source_ingestion import VideoSegment

    titles = [
        "Python ML Tutorial #1 - Introduction",
        "Python ML Tutorial #2 - Linear Regression p.1",
        "Python ML Tutorial #3 - KNN Implementation",
        "Python ML Tutorial #4 - SVM Implementation",
        "Python ML Tutorial #5 - K Means Clustering",
    ]
    segs = [
        VideoSegment(video_id=f"vid{i}", title=t, url="", position=i, transcript=t, chapters=[])
        for i, t in enumerate(titles, 1)
    ]
    doc = SourceDocument(
        source_type="youtube_playlist",
        source_url="https://www.youtube.com/playlist?list=PLexample",
        source_hash="h",
        title="ML Fundamentals",
        segments=segs,
        access_level="full",
    )
    project = plan_project(doc, title="ML Fundamentals", course_id="playlist-ml")
    joined = " ".join(m.title.lower() for m in project.milestones)
    assert "linear regression" in joined
    assert "knn" in joined or "nearest" in joined
    assert "print the result" not in joined
    assert "aliens" not in joined


DENSE_STT_TRANSCRIPT = """
In this tutorial we build a tokenizer for a small language model.
what we want is we want to trade off uh this um symbol size of this vocabulary
as we call it and the resulting sequence length so we don't want just two symbols
when we print the key and the value we can see what is happening in the dictionary
print the tokens to verify the encoding works
define a variable called bite to hold the text chunks
when we run the model we should see output on the screen
import tiktoken to load the reference tokenizer
"""


def test_raw_transcript_not_used_as_learner_action():
    project = plan_project(_doc(DENSE_STT_TRANSCRIPT), title="Deep Dive into LLMs", course_id="project-llm")
    for m in project.milestones:
        assert not looks_like_raw_transcript(m.microstep.action)
        assert not looks_like_raw_transcript(m.microstep.observation)
        assert "uh" not in m.microstep.action.lower()
        assert "um" not in m.microstep.action.lower()


def test_narrative_print_sentences_do_not_spawn_duplicate_milestones():
    project = plan_project(_doc(DENSE_STT_TRANSCRIPT), title="Deep Dive into LLMs", course_id="project-llm")
    print_titles = [m.title for m in project.milestones if "print" in m.title.lower()]
    assert len(print_titles) <= 1


def test_duplicate_meaningless_titles_are_rejected_by_validation():
    from backend.project_models import Microstep, Milestone, ProjectCourse, VerificationCheck

    project = ProjectCourse(
        course_id="p", title="Bad", source_hash="h", project_goal="Build bad",
        entry_file="main.py",
        milestones=[
            Milestone(id="m1", order=1, title="Set up",
                      checks=[VerificationCheck(kind="file_exists", target="main.py")]),
            Milestone(id="m2", order=2, title="Define tokenizer",
                      microstep=Microstep(action="Define tokenizer.", observation="obs"),
                      checks=[VerificationCheck(kind="symbol", target="tokenizer")]),
            Milestone(id="m3", order=3, title="Define tokenizer",
                      microstep=Microstep(action="Define tokenizer again.", observation="obs"),
                      checks=[VerificationCheck(kind="symbol", target="encode")]),
            Milestone(id="m4", order=4, title="Run",
                      checks=[VerificationCheck(kind="run_ok", target="")]),
        ],
    )
    with pytest.raises(ProjectGroundingError, match="duplicate"):
        validate_project(project)


def test_validate_accepts_well_formed_project():
    project = plan_project(_doc(WORD_COUNT_TRANSCRIPT), title="Word Frequency Counter", course_id="project-test")
    validate_project(project)


LECTURE_TRANSCRIPT = """
every great LLM starts with a bite a bite is a small chunk of text that a model
can process at once what we want is we want to trade off uh this um symbol size
your LLM is a confident liar about this fish it's not going to exactly parrot
the documents that it saw in the training set but again it's some kind of a
lossy compression of the internet we call it hallucination when we run the
model we call Transformer attention and then we print the key and the value
"""


def test_lecture_talk_is_rejected_instead_of_fake_coding_course():
    with pytest.raises(
        ProjectGroundingError,
        match="enough hands-on coding material|lecture|implementation|enough reliable material|isn't enough",
    ):
        plan_project(_doc(LECTURE_TRANSCRIPT, title="Intro to Large Language Models"),
                     title="Intro to Large Language Models", course_id="project-talk")


def test_chaptered_lecture_is_rejected_not_turned_into_fake_milestones():
    lecture_chapters = [
        "Intro to Large Language Models",
        "Tokens and bites",
        "Hallucinations",
        "Transformers",
        "Attention",
        "Why this matters",
    ]
    with pytest.raises(
        ProjectGroundingError,
        match="enough hands-on coding material|enough reliable material|isn't enough",
    ):
        plan_project(
            _chaptered_doc(lecture_chapters, title="[1hr Talk] Intro to Large Language Models"),
            title="[1hr Talk] Intro to Large Language Models",
            course_id="project-talk-ch",
        )


def test_hollow_saved_course_is_detected():
    from backend.project_models import Milestone, ProjectCourse, VerificationCheck
    from backend.project_planner import is_hollow_guided_project

    project = ProjectCourse(
        course_id="p", title="Talk", source_hash="h", project_goal="goal",
        entry_file="main.py",
        milestones=[
            Milestone(id="m1", order=1, title="Set up the project",
                      checks=[VerificationCheck(kind="file_exists", target="main.py")]),
            Milestone(id="m2", order=2, title="Run and verify",
                      checks=[VerificationCheck(kind="run_ok", target="")]),
            Milestone(id="m3", order=3, title="Run and verify",
                      checks=[VerificationCheck(kind="run_ok", target="")]),
            Milestone(id="m4", order=4, title="Print output",
                      checks=[VerificationCheck(kind="stdout_contains", target="")]),
        ],
    )
    assert is_hollow_guided_project(project) is True


def test_spoken_call_it_is_not_a_function():
    from backend.project_planner import _extract_target
    assert _extract_target("we call it attention") is None
    assert _extract_target("we call this Tokenizer") is None
    assert _extract_target("Call count_words on the sample.") == ("function_call", "count_words")


def test_scrub_replaces_transcript_action_on_existing_milestones():
    from backend.project_models import Microstep, Milestone, VerificationCheck
    from backend.project_planner import scrub_learner_fields

    m = Milestone(
        id="m2", order=2, title="Define tokenizer",
        microstep=Microstep(
            observation="Next up from the video:",
            action="what we want is we want to trade off uh this um symbol size of this vocabulary as we call it and the resulting sequence length so we don't want just two symbols",
        ),
        checks=[VerificationCheck(kind="symbol", target="tokenizer")],
    )
    scrub_learner_fields(m)
    assert "what we want" not in m.microstep.action.lower()
    assert "uh" not in m.microstep.action.lower()
    assert "tokenizer" in m.microstep.action
    assert not looks_like_raw_transcript(m.microstep.action)


def test_project_goal_is_polished_not_raw_transcript():
    project = plan_project(_doc(WORD_COUNT_TRANSCRIPT), title="Word Frequency Counter", course_id="project-test")
    assert "step by step" in project.project_goal.lower()
    assert not looks_like_raw_transcript(project.project_goal)


def test_long_unpunctuated_transcript_does_not_exceed_field_limits():
    """Regression: dense YouTube transcripts without punctuation used to produce
    one giant 'sentence' that crashed Milestone validation (>2000 chars)."""
    from backend.project_planner import _cap_field, _split_steps

    giant = ("import torch and define GPTConfig and implement forward " * 200).strip()
    assert all(len(chunk) <= 800 for chunk in _split_steps(giant))
    assert len(_cap_field(giant)) == 2000

    blob = GPT2_TRANSCRIPT
    project = plan_project(_doc(blob, title="Reproduce GPT-2"), title="Reproduce GPT-2", course_id="project-long")
    for milestone in project.milestones:
        assert len(milestone.source_grounded_description) <= 2000
        assert len(milestone.source_quote) <= 2000


# ---------------------------------------------------------------------------
# Import targets must be real modules, never English nouns from the prose
# ---------------------------------------------------------------------------

GENERIC_PROSE = [
    "Import the modules we need",
    "At the top, import the standard library modules we use",
    "import several other libraries",
    "import the required packages",
    "import the following code",
]


@pytest.mark.parametrize("sentence", GENERIC_PROSE)
def test_generic_nouns_after_import_are_not_turned_into_checks(sentence):
    """Regression: this produced `Your code imports modules`, which nobody can pass."""
    assert _extract_target(sentence) is None


@pytest.mark.parametrize(
    "sentence,expected",
    [
        ("import time", ("import", "time")),
        ("from functools import wraps", ("import", "functools")),
        ("import the collections module", ("import", "collections")),
        ("Install the requests package", ("import", "requests")),
        ("import numpy as np", ("import", "numpy")),
    ],
)
def test_real_module_names_still_extract(sentence, expected):
    assert _extract_target(sentence) == expected


def test_planned_project_has_no_unimportable_import_check():
    """Every import check in a planned project must name a real module."""
    import sys as _sys

    doc = _doc(
        "# Build a Rate Limiter\n\n"
        "## Step 1: Import the modules we need\n\n"
        "At the top, import the standard library modules we use:\n\n"
        "```python\nimport time\nfrom functools import wraps\n```\n\n"
        "## Step 2: Define the counter\n\n"
        "```python\nclass FixedWindowCounter:\n    def allow(self):\n        return True\n```\n\n"
        "## Step 3: Run it\n\n"
        "```bash\npython main.py\n```\n",
        title="Build a Rate Limiter",
    )
    project = plan_project(doc, title="Build a Rate Limiter", course_id="project-ratelimit")
    stdlib = set(_sys.stdlib_module_names)
    for milestone in project.milestones:
        for check in milestone.checks:
            if check.kind != "import":
                continue
            root = (check.target or "").split(".")[0].lower()
            assert root in stdlib or root in {"ratelimit", "demo", "main"}, (
                f"{milestone.id}: unimportable check for `{check.target}`"
            )


def test_no_milestone_requires_importing_a_local_module_the_project_lacks():
    """Regression: `import ratelimit` in a single-file project is unpassable.

    A tutorial that authors `ratelimit.py` and then imports it describes two
    files. The generated project has only `main.py`, so that check could never
    pass and the learner stalled at 77% with no way forward.
    """
    doc = _doc(
        "# Build a Rate Limiter\n\n"
        "## Step 1: Create ratelimit.py\n\n"
        "```python\nimport time\nfrom functools import wraps\n\n"
        "class RateLimitExceeded(Exception):\n    pass\n\n"
        "class TokenBucket:\n    def __init__(self, capacity, rate):\n"
        "        self.capacity = capacity\n\n    def allow(self):\n        return True\n```\n\n"
        "## Step 2: Import ratelimit in demo.py\n\n"
        "```python\nfrom ratelimit import TokenBucket, RateLimitExceeded\n\n"
        "bucket = TokenBucket(10, 1)\nprint(bucket.allow())\n```\n\n"
        "## Step 3: Run it\n\n"
        "```bash\npython main.py\n```\n",
        title="Build a Rate Limiter",
    )
    project = plan_project(doc, title="Build a Rate Limiter", course_id="project-localmod")
    importable = {
        (f.path or "").split("/")[-1].rsplit(".", 1)[0].lower()
        for f in project.workspace_files
    }
    for milestone in project.milestones:
        for check in milestone.checks:
            if check.kind != "import":
                continue
            root = (check.target or "").split(".")[0].lower()
            authored_in_source = f"{root}.py" in (doc.plain_text or "")
            assert not authored_in_source or root in importable, (
                f"{milestone.id}: requires `import {root}`, a file this project has none of"
            )


# ─── Learner-facing step quality (measured against real YouTube courses) ───────
# Every case here is a string a real tutorial produced before these rules existed.

def test_chapter_label_becomes_an_action_not_a_table_of_contents_entry():
    from backend.project_planner import _chapter_title

    assert _chapter_title("K-Nearest Neighbors Part 2 – Algorithm Explanation") == (
        "Implement k-nearest neighbors"
    )
    assert _chapter_title("Support Vector Machines Part 1 - SkLearn Datasets and Analysis") == (
        "Implement a support vector machine"
    )
    # A gerund chapter reads as a task when the learner meets it.
    assert _chapter_title("Creating the Bird") == "Build the Bird"


def test_chapter_title_never_cuts_mid_word():
    from backend.project_planner import _chapter_title

    long_chapter = "implement a small self attention mechanism for a single individual head layer norm"
    title = _chapter_title(long_chapter)
    assert not title.endswith("…")
    assert title == title.strip()
    assert len(title) <= 60
    assert " he" != title[-3:]


def test_speech_debris_is_stripped_from_step_titles():
    from backend.project_planner import _strip_speech_debris

    assert _strip_speech_debris("train these Transformers um") == "train these Transformers"
    assert _strip_speech_debris("create a new a new endpoint") == "create a new endpoint"
    assert _strip_speech_debris(
        "train Transformers but this is a very simple implementation"
    ) == "train Transformers"
    assert _strip_speech_debris("build GPT from scratch so I covered that") == "build GPT from scratch"


@pytest.mark.parametrize(
    "sentence",
    [
        "import believe it or not a method called",
        "I'm going to import the entire react Library",
        "import whatever because I'm doing an export default",
        "install additional packages that we need",
        "import or any npm options it talks about",
    ],
)
def test_the_word_after_import_is_not_automatically_a_package(sentence):
    assert _extract_target(sentence) is None


@pytest.mark.parametrize(
    "sentence,expected",
    [
        ("import react", ("import", "react")),
        ("import time", ("import", "time")),
        ("from flask import jsonify", ("import", "flask")),
        # Unknown, but the source says it twice: corroborated.
        ("import neat and then import neat again", ("import", "neat")),
    ],
)
def test_real_and_corroborated_imports_still_extract(sentence, expected):
    assert _extract_target(sentence) == expected


def test_a_symbol_spoken_as_two_words_is_not_guessed_at():
    """`handleSubmit` arrives as "handle submit"; a check for `handle` never passes."""
    assert _extract_target("create a function called handle submit and up here") is None
    assert _extract_target("call the Dot Upper function or you") is None
    # A single-word name, and a name followed by a description, both survive.
    assert _extract_target("define a function called count_words that takes text") == (
        "symbol",
        "count_words",
    )
    assert _extract_target("create a new function called subtract of course") == ("symbol", "subtract")


def test_the_same_step_said_three_ways_is_one_milestone():
    from backend.project_planner import Milestone, VerificationCheck, _dedupe_milestones

    def ms(i, title, target):
        return Milestone(
            id=f"m{i}", order=i, title=title,
            checks=[VerificationCheck(kind="code_contains", target=target)],
        )

    kept = _dedupe_milestones([
        ms(1, "Train the Transformer", "train|Transformer"),
        ms(2, "Train these Transformers", "train|Transformers"),
        ms(3, "Train Transformers", "Transformers|simple"),
    ])
    assert [m.title for m in kept] == ["Train the Transformer"]


def test_defining_and_calling_one_symbol_are_two_milestones():
    from backend.project_planner import Milestone, VerificationCheck, _dedupe_milestones

    kept = _dedupe_milestones([
        Milestone(id="m1", order=1, title="Define count_words",
                  checks=[VerificationCheck(kind="symbol", target="count_words")]),
        Milestone(id="m2", order=2, title="Call count_words",
                  checks=[VerificationCheck(kind="function_call", target="count_words")]),
    ])
    assert len(kept) == 2


def test_goal_names_the_steps_this_course_actually_builds():
    """A four-series mega course plans one series; the goal must not promise four."""
    chapters = [
        "intro", "Linear Regression Part 1 – Data Loading and Analysis",
        "K-Nearest Neighbors Part 3 – Implementation",
        "Support Vector Machines Part 3 – Implementation",
        "K-Means Clustering - Implementation",
    ]
    doc = _chaptered_doc(chapters, title="Python Machine Learning & AI Mega Course - Learn 4 Areas")
    project = plan_project(doc, title="Python Machine Learning & AI Mega Course - Learn 4 Areas", course_id="goal")
    assert "linear regression" in project.project_goal.lower()
    assert "4 Areas" in project.project_goal
    assert len(project.project_goal) <= 280, "polish replaces an over-long goal with boilerplate"


# ─── Beginner milestone copy quality ──────────────────────────────────────────

def test_code_contains_action_is_beginner_not_references_jargon():
    """code_contains fallbacks must tell beginners what to type — not 'reference X'."""
    from backend.project_models import Microstep, Milestone, VerificationCheck
    from backend.project_planner import _action_for, scrub_learner_fields

    action = _action_for(
        "code_contains",
        "LinearRegression|sklearn",
        "Load and analyze data for linear regression",
        source_label="Linear Regression Part 1 – Data Loading and Analysis",
    )
    low = action.lower()
    assert "references" not in low
    assert "reference `" not in low
    assert "import" in low or "load" in low or "pandas" in low or "sklearn" in low
    assert "linearregression" in low.replace("`", "")

    m = Milestone(
        id="m2",
        order=2,
        title="Load and analyze data for linear regression",
        microstep=Microstep(
            observation="um so what we want is we want to load the data uh",
            action="Implement this step so your code references `LinearRegression`.",
            hint="hint",
        ),
        teach="okay so um we are going to look at the data kind of",
        checks=[VerificationCheck(kind="code_contains", target="LinearRegression|sklearn")],
        xp_reward=25,
    )
    scrub_learner_fields(m)
    assert "references" not in m.microstep.action.lower()
    assert "uh" not in m.microstep.action.lower()
    assert not re.search(r"\bum\b", (m.teach or "").lower())
    assert m.microstep.action
    assert m.teach


def test_scrub_keeps_beginner_multistep_strips_stt_filler():
    from backend.project_models import Microstep, Milestone, VerificationCheck
    from backend.project_planner import looks_like_raw_transcript, scrub_learner_fields

    good = (
        "1. In `main.py`, import pandas and sklearn.\n"
        "2. Load the dataset with `pd.read_csv(...)` and inspect it with `.head()`.\n"
        "3. Keep `LinearRegression` in mind for the next model step after the data looks right."
    )
    assert not looks_like_raw_transcript(good)
    assert len(good.split()) >= 28

    m = Milestone(
        id="m2",
        order=2,
        title="Load and analyze data for linear regression",
        microstep=Microstep(observation="Build this section.", action=good, hint="hint"),
        teach=(
            "Before fitting a model, load and inspect the data so you know its shape "
            "and columns. LinearRegression comes after you trust the dataset."
        ),
        checks=[VerificationCheck(kind="code_contains", target="LinearRegression|sklearn")],
        xp_reward=25,
    )
    scrub_learner_fields(m)
    assert m.microstep.action == good
    assert "LinearRegression" in m.teach

    stt = Milestone(
        id="m3",
        order=3,
        title="Implement linear regression",
        microstep=Microstep(
            observation="next",
            action="um so uh we kind of want to like load the data you know and stuff",
            hint="h",
        ),
        checks=[VerificationCheck(kind="code_contains", target="LinearRegression|sklearn")],
        xp_reward=25,
    )
    scrub_learner_fields(stt)
    assert not re.search(r"\bum\b", stt.microstep.action.lower())
    assert not re.search(r"\buh\b", stt.microstep.action.lower())
    assert "references" not in stt.microstep.action.lower()


def test_ml_mega_course_chapter_plan_has_actionable_microsteps():
    chapters = [
        "intro",
        "Linear Regression Part 1 – Data Loading and Analysis",
        "Linear Regression Part 2 – Model Fitting",
        "K-Nearest Neighbors Part 3 – Implementation",
        "Support Vector Machines Part 3 – Implementation",
        "K-Means Clustering - Implementation",
    ]
    doc = _chaptered_doc(
        chapters,
        title="Python Machine Learning & AI Mega Course - Learn 4 Areas",
    )
    project = plan_project(
        doc,
        title="Python Machine Learning & AI Mega Course - Learn 4 Areas",
        course_id="ml-mega-quality",
    )
    coding = [
        m for m in project.milestones
        if m.checks and m.checks[0].kind == "code_contains"
    ]
    assert len(coding) >= 2
    for m in coding:
        low = m.microstep.action.lower()
        assert "references" not in low
        assert "reference `" not in low
        assert any(
            verb in low
            for verb in ("import", "load", "create", "fit", "implement", "open", "write", "add")
        ), m.microstep.action
        assert m.teach, f"missing teach for {m.title}"
        assert not looks_like_raw_transcript(m.microstep.action)
