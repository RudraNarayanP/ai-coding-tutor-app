"""Tests for telling a learner's deliverable from the harness that checks it.

A guided project is built in one file and graded by the checks it emits, so a milestone
demanding `test_emb_dot` asks the learner to write the test that marks their own work —
and takes the step from the function the tutorial actually named. The distinction is
made structurally (a definition bound to nothing but its instance, whose following code
calls the test framework's assertions) and never by the name, which is what the corpus
evidence supports and what a `test_` prefix rule could not claim.

Every test below is drawn from shapes that exist in this repository's own material: the
curriculum's `unittest_code` fields, its starter/solution skeletons, the audit dumps'
inline copies of them, and its testing unit whose deliverables *are* assertion helpers.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.project_models import Milestone, ProjectCourse, VerificationCheck, WorkspaceFile
from backend.project_planner import plan_project, scaffolding_names
from backend.project_verifier import evaluate_milestone
from backend.source_ingestion import SourceDocument

# The audit dumps carry the curriculum's unittest fields inline, verbatim in shape:
# a `TEST <name> :` label, the def, and the assertion joined by ⏎ markers.
DUMP_SHAPED_TEST = (
    "======== ml clf-sigmoid learn | 1. Sigmoid\n"
    "DESC: Implement `sigmoid(z)` = 1/(1+e^{-z}).\n"
    "STARTER: 'def sigmoid(z):\\n    # TODO\\n    pass\\n'\n"
    "SOLUTION: 'import math\\n\\ndef sigmoid(z):\\n    return 1 / (1 + math.exp(-z))\\n'\n"
    "TEST test_sigmoid : def test_sigmoid(self): ⏎     self.assertAlmostEqual(sigmoid(0), 0.5) ⏎"
    "     self.assertTrue(sigmoid(10) > 0.99) ⏎ \n"
)


def _names(text: str) -> set[str]:
    return scaffolding_names(text)


# ─── what the rule catches ───────────────────────────────────────────────────

def test_a_unittest_case_is_not_a_learner_deliverable() -> None:
    assert _names(DUMP_SHAPED_TEST) == {"test_sigmoid"}


def test_a_test_setup_method_is_caught_too() -> None:
    text = ("def setUp(self):\n    self.app = create_app()\n"
            "    self.assertTrue(self.app is not None)\n")
    assert _names(text) == {"setUp"}


def test_the_classification_ignores_the_name_entirely() -> None:
    """Same shape, different name: the rule is about the role, not the prefix.

    A project's `check_something(self)` that only asserts is the harness whatever it
    is called, and a `test_runner(self, cases)` with real parameters is not.
    """
    harness = "def verifies_the_output(self):\n    self.assertEqual(run(), 3)\n"
    deliverable = "def test_runner(self, cases):\n    return [run(c) for c in cases]\n"
    assert _names(harness) == {"verifies_the_output"}
    assert _names(deliverable) == set()


# ─── what must survive ──────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text",
    [
        # The app's own testing unit: the deliverables ARE assertion helpers.
        "Implement `assert_equal(actual, expected)` that raises AssertionError with a "
        "helpful message.\n",
        "Implement `run_cases(fn, cases)` where each case is (args_tuple, expected).\n",
        "Build `with_temp_dict(factory)` that creates a dict via factory, yields it.\n",
        "Implement `approx_equal(a, b, tol=1e-6)` for float comparisons in tests.\n",
        "Implement `raises(exc_type, fn)` that returns True if fn() raises exc_type.\n",
    ],
)
def test_the_repo_s_testing_curriculum_is_untouched(text: str) -> None:
    assert _names(text) == set()


def test_a_tutorial_that_asks_for_the_test_still_gets_it_as_a_deliverable() -> None:
    """An instruction wins over the shape, so TDD content is not silently dropped."""
    text = ("Next define a test_login function that checks the endpoint.\n"
            "def test_login(self):\n    self.assertEqual(status, 401)\n")
    assert _names(text) == set()


def test_a_class_method_the_learner_must_write_survives() -> None:
    """21 of this repo's real deliverables are self-methods; the old idea of
    matching on `self` alone flagged them. A parameter is the difference."""
    text = "def deposit(self, amount):\n    self.balance += amount\n"
    assert _names(text) == set()


def test_pytest_style_module_functions_are_deliberately_not_caught() -> None:
    """The documented limit, kept as a test so nobody 'fixes' it with a prefix.

    `def test_login():` with no bound instance is indistinguishable from a learner's
    own module function by structure alone; only the name separates them, and a name
    rule would also reject the testing curriculum above. So the rule misses these.
    """
    assert _names("def test_login():\n    assert client.get('/x').status_code == 401\n") == set()


# ─── end to end: the milestone is gone and the real one takes its place ──────

def _plan(text: str) -> ProjectCourse:
    doc = SourceDocument(
        source_type="transcript", source_url="", source_hash="t",
        title="Sigmoid", plain_text=text, access_level="full",
    )
    return plan_project(doc, title="Sigmoid", course_id="scaffold")


def test_a_planned_project_drops_the_harness_and_keeps_the_deliverable() -> None:
    project = _plan(DUMP_SHAPED_TEST + "\n" + DUMP_SHAPED_TEST.replace("sigmoid", "mse").replace(
        "1. Sigmoid", "2. MSE").replace("1/(1+e^{-z})", "mean squared error"))
    symbols = [m.checks[0].target for m in project.milestones
               if m.checks and m.checks[0].kind == "symbol"]
    assert "sigmoid" in symbols or "mse" in symbols, symbols
    assert not [s for s in symbols if s in _names(DUMP_SHAPED_TEST)], symbols


def test_the_remaining_checks_are_still_decidable_by_the_real_grader() -> None:
    """A check that cannot fail is not a check: each one must pass the code it asks
    for and refuse the starter file."""
    project = _plan(DUMP_SHAPED_TEST)
    for milestone in project.milestones:
        check = milestone.checks[0] if milestone.checks else None
        if not check or check.kind not in {"symbol", "import", "function_call"}:
            continue
        name = check.target
        code = (f"import {name}\n" if check.kind == "import"
                else f"def {name}(*a, **k):\n    return None\n\n{name}()\n"
                if check.kind == "function_call" else f"def {name}(*a, **k):\n    return None\n")
        solo = ProjectCourse(
            course_id="d", title="t", source_hash="h", project_goal="g", entry_file="main.py",
            milestones=[Milestone(id="m1", order=1, title=milestone.title, checks=[check])],
        )

        def grade(content: str) -> bool:
            return asyncio.run(evaluate_milestone(
                None, solo, solo.milestones[0], [WorkspaceFile(path="main.py", content=content)]
            ))[0]

        assert grade(code) is True, f"{milestone.title}: unverifiable"
        assert grade("# starter\n") is False, f"{milestone.title}: passes on nothing"
