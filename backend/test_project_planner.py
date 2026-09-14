"""Tests for source-grounded guided-project planning (Create Course only)."""
import pytest

from backend.project_planner import ProjectGroundingError, plan_project
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
    assert import_ms.microstep.action  # concise action present


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
