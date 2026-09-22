"""Tests for composition measurement: what the repo's own code proves and refutes.

Nothing here asserts a production rule, because the measurement found none that is
justified. What these tests protect is the measurement itself: a dependency detector
that quietly misses `from x import y` (it did, once) or a stub program that does not
parse (it did, once) turns "composition is absent" into an artefact of the probe. So
the detector is tested against cases where a dependency undeniably exists and cases
where only the *word* exists, and the corpus-level conclusions are pinned as facts
that must fail loudly if the code or the curriculum changes.
"""

from __future__ import annotations

import asyncio

import pytest

from backend import composition_measurement as cm
from backend.project_models import Milestone, ProjectCourse, VerificationCheck, WorkspaceFile
from backend.project_verifier import evaluate_milestone

COMPOSED = "def mse(y_true, y_pred):\n    return 0\n\ndef report(t, p):\n    return mse(t, p)\n"
UNRELATED = "def mse(y_true, y_pred):\n    return 0\n\ndef report(t, p):\n    return t + p\n"
SWAPPED = "def mse(y_pred, y_true):\n    return 0\n\ndef report(t, p):\n    return mse(p, t)\n"


def _grade(needle: str, code: str) -> bool:
    course = ProjectCourse(
        course_id="g", title="t", source_hash="h", project_goal="g", entry_file="main.py",
        milestones=[Milestone(id="m1", order=1, title="s",
                              checks=[VerificationCheck(kind="code_contains", target=needle)])],
    )
    passed, _results, _out, _err = asyncio.run(
        evaluate_milestone(None, course, course.milestones[0],
                           [WorkspaceFile(path="main.py", content=code)])
    )
    return passed


def _blocks(code: str) -> list[str]:
    fragments, _unparsable = cm.code_blocks(code)
    return fragments or [code]


# ─── the detector: real dependencies only ────────────────────────────────────

def test_a_call_into_an_earlier_lesson_is_a_dependency() -> None:
    assert cm.top_level_names("def mse(y_true, y_pred):\n    return 0\n") == ["mse"]
    used = cm.referenced_names("def report(t, p):\n    return mse(t, p)\n")
    assert "mse" in used - cm.local_bindings("def report(t, p):\n    return mse(t, p)\n")


def test_an_import_is_a_dependency_not_a_local_binding() -> None:
    """Regression: import aliases were subtracted as local names, hiding the one
    dependency form a learner most often writes (`from micrograd.engine import Value`)."""
    earlier = "MICRO = 1\n"
    later = "from models import MICRO\n\ndef f():\n    return MICRO\n"
    used = cm.referenced_names(later) - cm.local_bindings(later)
    assert set(cm.top_level_names(earlier)) & used == {"MICRO"}


def test_a_rebound_word_is_not_a_dependency() -> None:
    """`predict` appearing twice is not composition: here the second one is a local."""
    earlier = "def predict(x, w, b):\n    return x\n"
    later = "def other():\n    predict = 3\n    return predict\n"
    used = cm.referenced_names(later) - cm.local_bindings(later)
    assert not set(cm.top_level_names(earlier)) & used


def test_a_similar_name_is_not_a_dependency() -> None:
    earlier = "def model(x):\n    return x\n"
    later = "def other():\n    return models\n"
    used = cm.referenced_names(later) - cm.local_bindings(later)
    assert not set(cm.top_level_names(earlier)) & used


def test_the_detector_finds_real_dependencies_in_the_backend_itself() -> None:
    """A positive control on code this repository knows is coupled."""
    import io
    from pathlib import Path

    here = Path(__file__).resolve().parent          # backend/
    models = io.open(here / "project_models.py", encoding="utf-8").read()
    planner = io.open(here / "project_planner.py", encoding="utf-8").read()
    used = cm.referenced_names(planner) - cm.local_bindings(planner)
    shared = set(cm.top_level_names(models)) & used
    assert {"Milestone", "ProjectCourse", "VerificationCheck"} <= shared


# ─── the corpus facts, pinned ────────────────────────────────────────────────

def test_no_curriculum_unit_in_this_repo_composes() -> None:
    """0 of 59: the shipped curriculum is independent-exercise content.

    This is the fact that refutes a chain requirement, so it is a test: if someone
    later writes a unit whose lessons really do build on each other, this fails and the
    question has to be re-asked with that evidence in hand.
    """
    graphs = [g for g in cm.curriculum_graphs() if len(g.lessons) >= 3]
    assert len(graphs) >= 50
    composing = [g for g in graphs if g.edges]
    assert not composing, f"curriculum now composes: {[(g.module, g.edges[:2]) for g in composing]}"


def test_dump_style_sources_show_only_scaffolding_composition() -> None:
    """The one place real material composes, it composes as `test_X` calling `X`.

    Uses the same inline `STARTER:`/`SOLUTION:`/`TEST` format the audit dumps use, so
    the reader formats are exercised too: `STARTER` payloads are Python *reprs* and
    `TEST` bodies mark newlines with `⏎`.
    """
    source = (
        "======== demo learn | 1. Demo\n"
        "DESC: Implement `emb_dot(a, b)` for equal-length float lists.\n"
        "STARTER: 'def emb_dot(a, b):\\n    # TODO\\n    pass\\n'\n"
        "SOLUTION: 'def emb_dot(a, b):\\n    return sum(x * y for x, y in zip(a, b))\\n'\n"
        "TEST test_emb_dot : def test_emb_dot(self): ⏎     self.assertEqual(emb_dot([1, 2], [3, 4]), 11) ⏎\n"
    )
    blocks, unparsable = cm.code_blocks(source)
    assert unparsable == 0, "every fragment should be readable, or the edges below are not a measurement"
    assert any("emb_dot" in body for body in cm.definition_bodies(blocks))

    milestones = [
        Milestone(id="m1", order=1, title="Define emb_dot",
                  checks=[VerificationCheck(kind="symbol", target="emb_dot")]),
        Milestone(id="m2", order=2, title="Define test_emb_dot",
                  checks=[VerificationCheck(kind="symbol", target="test_emb_dot")]),
    ]
    finding = cm.project_composition("demo", "unknown", milestones, blocks, unparsable)
    assert ("emb_dot", "test_emb_dot") in finding.body_edges
    assert not finding.arg_edges, "a harness that passes a literal is not data-flow composition"


def test_unparsable_fragments_are_reported_not_silently_dropped() -> None:
    """One malformed fragment must not erase a whole document's evidence."""
    good = "def alpha():\n    return 1\n"
    broken = "def beta(:\n    return 2\n"
    blocks, unparsable = cm.code_blocks(f"STARTER: {good!r}\nSOLUTION: {broken!r}\n")
    assert unparsable == 1
    assert list(cm.definition_bodies(blocks)) == ["alpha"]


# ─── the vocabulary limit: no check can express a relationship ───────────────

def test_code_contains_names_a_thing_and_cannot_tell_composition_from_coexistence() -> None:
    assert _grade("mse", COMPOSED) is True
    assert _grade("mse", UNRELATED) is True, "expected: identifier-only semantics"


def test_a_spaced_needle_degrades_to_its_last_identifier() -> None:
    """`mse(t, p)` looks like a relationship assertion and is not one."""
    assert _grade("mse(t, p)", UNRELATED) is True


def test_a_paren_needle_matches_nothing_at_all() -> None:
    """The one form that *would* express a call is unmatchable.

    The identifier branch wraps the needle in `\\b…\\b`, and no word boundary follows an
    escaped `(`, so the literal text can never hit. Writing it with a space instead
    silently changes the meaning to "last identifier referenced" — see the test above.
    Either way the planner has no way to require composition today.
    """
    assert _grade("mse(t,p)", COMPOSED) is False


def test_swapped_arguments_are_indistinguishable_to_every_available_needle() -> None:
    """No needle separates `mse(p, t)` from `mse(t, p)`, so no check can require the
    data to actually flow from the earlier milestone."""
    assert _grade("mse", SWAPPED) == _grade("mse", COMPOSED)
    assert _grade("mse(t, p)", SWAPPED) is True


# ─── milestones are independently satisfiable ────────────────────────────────

def test_a_project_of_unrelated_stubs_satisfies_every_structural_check() -> None:
    """The concrete version of "milestones coexist rather than compose".

    One stub per artifact, none referring to another, and the file parses — an
    unparseable stub would be graded by the verifier's lenient fallback rather than by
    its AST rules, which is how this measurement first reported a false 100%.
    """
    course = ProjectCourse(
        course_id="stub", title="t", source_hash="h", project_goal="g", entry_file="main.py",
        milestones=[
            Milestone(id="m1", order=1, title="Import",
                      checks=[VerificationCheck(kind="import", target="math")]),
            Milestone(id="m2", order=2, title="Define mse",
                      checks=[VerificationCheck(kind="symbol", target="mse")]),
            Milestone(id="m3", order=3, title="Call mse",
                      checks=[VerificationCheck(kind="function_call", target="mse")]),
            Milestone(id="m4", order=4, title="Define report",
                      checks=[VerificationCheck(kind="symbol", target="report")]),
        ],
    )
    code = ("import math\n\n"
            "def mse(*args, **kwargs):\n    return None\n\n"
            "mse()\n\n"
            "def report(*args, **kwargs):\n    return None\n")
    import ast

    ast.parse(code)  # the stub must be valid Python or the result below means nothing
    for milestone in course.milestones:
        passed, _r, _o, _e = asyncio.run(
            evaluate_milestone(None, course, milestone, [WorkspaceFile(path="main.py", content=code)])
        )
        assert passed, f"{milestone.title} was not satisfied by an uncomposed stub"
    # ...and the last artifact never had to touch the second: its body references
    # nothing but its own parameters.
    report_body = cm.definition_bodies([code])["report"]
    assert "mse" not in (cm.referenced_names(report_body) - cm.local_bindings(report_body))
