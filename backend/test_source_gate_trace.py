"""Tests for the source gate's decision path and what may count as a tutorial.

`evaluate_source` is what stands between a pasted source and a guided project, and
until this corpus it had been exercised only against hand-written fixtures. Two
things are pinned here:

* the trace in `backend/source_gate_trace.py` must agree with the production decision
  for every real corpus source — a trace that drifts from the code it describes turns
  every measurement built on it into fiction;
* a Markdown code span naming an artifact counts as implementation evidence, because
  that is the only form the real sources this feature ingests (transcripts, video
  descriptions, pasted docs) use to say "define this" — while lecture, news,
  assistant-tips and documentation material must still be refused for the right reason.
"""

from __future__ import annotations

import pytest

from backend import source_quality as sq
from backend.project_corpus import build_corpus
from backend.project_planner import _extract_target
from backend.source_gate_trace import (
    BRANCH_ACCEPT,
    BRANCH_CONCEPTUAL,
    BRANCH_SHAPE,
    BRANCH_STRUCTURE,
    COUNTERFACTUALS,
    code_spans,
    trace_source_gate,
    with_patch,
)
from backend.source_ingestion import SourceDocument, VideoSegment


def _transcript(text: str, title: str = "Source") -> SourceDocument:
    return SourceDocument(
        source_type="transcript", source_url="", source_hash="t",
        title=title, plain_text=text, access_level="full",
    )


@pytest.fixture(scope="module")
def corpus():
    return build_corpus()


# ─── the trace describes the code ────────────────────────────────────────────

def test_the_trace_agrees_with_the_production_decision_on_every_source(corpus) -> None:
    mismatches = []
    for source in corpus:
        real = sq.evaluate_source(source.doc, source.doc.title).decision
        traced = trace_source_gate(source.doc, source.doc.title).decision
        if real != traced:
            mismatches.append((source.key, real, traced))
    assert not mismatches, f"trace drifted from the gate: {mismatches}"


def test_every_source_lands_in_a_named_branch(corpus) -> None:
    known = {BRANCH_ACCEPT, BRANCH_SHAPE, BRANCH_CONCEPTUAL, BRANCH_STRUCTURE,
             "stage1-ingestion"}
    for source in corpus:
        trace = trace_source_gate(source.doc, source.doc.title)
        assert trace.branch in known, source.key
        # A refusal must name the condition that bound, not just "not enough material".
        if trace.decision != "accept":
            assert trace.reason, f"{source.key} refused without a reason"


def test_the_shipped_candidate_is_the_measured_one(corpus) -> None:
    """A counterfactual already in production must change nothing.

    If a candidate starts flipping sources again, either the shipped rule was
    narrowed or someone re-priced it — either way the measurement in
    `measure_project_quality`'s docstring needs re-reading.
    """
    base = {s.key: trace_source_gate(s.doc, s.doc.title).decision for s in corpus}
    for name in COUNTERFACTUALS:
        with with_patch(name):
            after = {s.key: trace_source_gate(s.doc, s.doc.title).decision for s in corpus}
        assert after == base, f"{name} still changes decisions: " \
            f"{[k for k in base if base[k] != after[k]]}"


# ─── a code span is a source naming its own artifact ─────────────────────────

def test_a_tutorial_that_names_its_artifacts_in_code_is_a_build_along() -> None:
    """The real-shape case. No pasted transcript contains a literal `def` line."""
    doc = _transcript(
        "Unit 4: Tokenization\n"
        "Implement `tokenize(text)` splitting on whitespace and dropping empties.\n"
        "Implement `normalize_tokens(tokens)` lowercasing and stripping punctuation.\n"
        "Implement `build_vocab(token_lists)` mapping tokens to sorted ids.\n"
        "Implement `encode(tokens, vocab, unk_id)` mapping unknown tokens to unk.\n",
        title="Build a tokenizer",
    )
    assert sq.evaluate_source(doc, "Build a tokenizer").decision == "accept"
    trace = trace_source_gate(doc, "Build a tokenizer")
    assert trace.implementation is True
    assert {"tokenize", "normalize_tokens", "build_vocab", "encode"} <= set(code_spans(
        doc.plain_text))


def test_a_class_named_in_code_counts_too() -> None:
    doc = _transcript(
        "Implement `auth_header(token)` returning an Authorization bearer header.\n"
        "Implement `TokenStore` with set/get/clear methods.\n"
        "Implement `jwt_payload(token)` decoding the middle base64url segment.\n",
        title="Auth tokens",
    )
    assert sq.evaluate_source(doc, "Auth tokens").decision == "accept"


def test_naming_no_artifact_is_still_refused_for_the_right_reason() -> None:
    """Accepting code spans must not turn vague prose into a tutorial.

    This is the shape of the graph-traversal unit: real lessons, real chaining, and
    not one artifact name a verifier could look for.
    """
    doc = _transcript(
        "Represent an undirected graph and add edges.\n"
        "Return DFS visit order starting from a node, iterative or recursive.\n"
        "Return BFS visit order from a start node.\n"
        "Unweighted shortest path length via BFS, or -1 if unreachable.\n",
        title="Graph traversals",
    )
    decision = sq.evaluate_source(doc, "Graph traversals")
    assert decision.decision != "accept"
    trace = trace_source_gate(doc, "Graph traversals")
    assert not code_spans(doc.plain_text)
    # Which branch refuses depends on how much shape survives without artifact
    # names; what must hold is that it is refused and that the trace says where.
    assert trace.branch != BRANCH_ACCEPT, trace.branch


def test_the_gate_still_refuses_non_tutorials_after_the_change(corpus) -> None:
    """Every intentional refusal, kept under the shipped rule."""
    expected = {
        "assistant_usage": 0, "news_commentary": 0, "unrelated": 0,
        "conceptual_explainer": 0,
    }
    for source in corpus:
        decision = sq.evaluate_source(source.doc, source.doc.title)
        if decision.source_type in expected and decision.decision == "accept":
            pytest.fail(f"{source.key} ({decision.source_type}) is now accepted")
        if source.key.startswith("doc:") and decision.decision == "accept":
            # Documentation may pass analysis, but it must not reach a course.
            with pytest.raises(Exception):
                from backend.project_planner import plan_project

                plan_project(source.doc, title=source.doc.title, course_id="doc-gate")
    assert True


def test_lecture_material_without_code_spans_cannot_be_rescued_by_prose() -> None:
    """The Karpathy-talk shape: technical words, nothing to build."""
    doc = _transcript(
        "Hi everyone, so recently I gave a thirty minute talk about how these systems "
        "are trained. The model is really just two files on your file system, the "
        "parameters file and some kind of code that runs those parameters. We call "
        "this hallucination when the model makes things up. Transformers are a "
        "particular type of model and attention is the mechanism inside them.\n",
        title="[1hr Talk] Intro to Large Language Models",
    )
    decision = sq.evaluate_source(doc, "[1hr Talk] Intro to Large Language Models")
    assert decision.decision != "accept"
    assert trace_source_gate(doc, "x").branch != BRANCH_ACCEPT


# ─── the derivation side of the same concept ────────────────────────────────

@pytest.mark.parametrize(
    "sentence,expected",
    [
        ("Implement `mse(y_true, y_pred)` returning residuals.", ("symbol", "mse")),
        ("Implement `TokenStore` with set/get/clear methods.", ("symbol", "TokenStore")),
        ("Build `with_temp_dict(factory)` that yields a dict.", ("symbol", "with_temp_dict")),
    ],
)
def test_a_code_span_after_a_build_verb_names_the_artifact(sentence, expected) -> None:
    assert _extract_target(sentence) == expected


@pytest.mark.parametrize(
    "sentence",
    [
        # A bare lowercase word in backticks is not proof of a deliverable name.
        "Create `venv` and activate it.",
        "Add a `prompt` template here.",
        "Open `main.py` and edit it.",
        "Run `pytest` to check the suite.",
    ],
)
def test_a_bare_lowercase_span_is_not_promoted_into_a_required_symbol(sentence) -> None:
    assert _extract_target(sentence) is None


def test_the_prose_pattern_is_silenced_when_the_source_already_showed_its_name() -> None:
    """`symbol wrapped` was a milestone nobody could intend.

    The sentence names its deliverable in code (`shout`) and mentions "the wrapped
    function" only to describe a parameter. With a code span present, the loose prose
    pattern no longer gets a vote.
    """
    sentence = ("Implement `shout` that uppercases the string returned by "
                "the wrapped function.")
    result = _extract_target(sentence)
    assert result != ("symbol", "wrapped")
    assert result is None or result[1] == "shout"


def test_the_prose_pattern_still_works_when_no_code_form_appears() -> None:
    assert _extract_target("Next call the forward method to get logits.") == ("symbol", "forward")


def test_span_pattern_is_case_sensitive_on_purpose() -> None:
    """A global IGNORECASE made the PascalCase branch match every word.

    `venv` satisfied "[A-Z]...[A-Z]" when the flag lowercased the distinction, so the
    verb is matched with a scoped flag instead and case shape still means something.
    """
    assert _extract_target("Create `venv` and activate it.") is None
    assert _extract_target("Create `TokenStore` with set/get/clear.") == ("symbol", "TokenStore")
