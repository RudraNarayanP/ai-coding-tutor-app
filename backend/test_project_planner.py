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


def test_milestones_have_strictly_increasing_order():
    project = plan_project(_doc(WORD_COUNT_TRANSCRIPT), title="Word Frequency Counter", course_id="project-test")
    orders = [m.order for m in project.milestones]
    assert orders == sorted(orders)
    assert orders[0] == 1
    assert len(set(orders)) == len(orders)
