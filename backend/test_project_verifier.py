"""Tests for milestone verification (structural AST + sandbox execution)."""
import asyncio

from backend.project_models import (
    Milestone,
    ProjectCourse,
    VerificationCheck,
    WorkspaceFile,
)
from backend.project_verifier import evaluate_milestone, run_workspace
from backend.sandbox import DockerSandbox

sandbox = DockerSandbox()


def _project(files: list[WorkspaceFile], tech: list[str] | None = None) -> ProjectCourse:
    return ProjectCourse(
        course_id="project-test",
        title="Test Project",
        source_hash="h",
        project_goal="test",
        tech_stack=tech or [],
        entry_file="main.py",
        workspace_files=files,
    )


def _eval(project, milestone):
    return asyncio.run(evaluate_milestone(sandbox, project, milestone, project.workspace_files))


def test_import_check_passes_for_any_valid_import():
    project = _project([WorkspaceFile(path="main.py", content="import collections\n")])
    ms = Milestone(id="m", order=1, title="Import", checks=[VerificationCheck(kind="import", target="collections")])
    passed, results, _, _ = _eval(project, ms)
    assert passed is True
    assert results[0].passed is True


def test_import_check_accepts_from_import_alias():
    project = _project([WorkspaceFile(path="main.py", content="from collections import Counter as C\n")])
    ms = Milestone(id="m", order=1, title="Import", checks=[VerificationCheck(kind="import", target="collections")])
    passed, _, _, _ = _eval(project, ms)
    assert passed is True


def test_import_check_is_case_insensitive_for_spoken_package_names():
    # Persisted courses may still have Title-Case targets from old caption parsing.
    project = _project([WorkspaceFile(path="main.py", content="from transformers import GPT2LMHeadModel\n")])
    ms = Milestone(id="m", order=1, title="Import", checks=[VerificationCheck(kind="import", target="Transformers")])
    passed, _, _, _ = _eval(project, ms)
    assert passed is True


def test_symbol_check_accepts_alternative_implementations():
    # Two very different valid implementations both define count_words.
    for body in (
        "def count_words(t):\n    return len(t.split())\n",
        "count_words = lambda t: len(t.split())\n",
    ):
        project = _project([WorkspaceFile(path="main.py", content=body)])
        ms = Milestone(id="m", order=1, title="Def", checks=[VerificationCheck(kind="symbol", target="count_words")])
        passed, _, _, _ = _eval(project, ms)
        assert passed is True, body


def test_symbol_check_fails_when_missing():
    project = _project([WorkspaceFile(path="main.py", content="x = 1\n")])
    ms = Milestone(id="m", order=1, title="Def", checks=[VerificationCheck(kind="symbol", target="count_words")])
    passed, results, _, _ = _eval(project, ms)
    assert passed is False
    assert "count_words" in results[0].detail


def test_code_contains_recognizes_defined_from_pretrained_regression():
    # Regression for the reported false negative: a classmethod named
    # from_pretrained that also calls .from_pretrained must satisfy the
    # "exploring the checkpoint" milestone check.
    code = (
        "import torch.nn as nn\n"
        "from transformers import GPT2LMHeadModel\n\n"
        "class GPT(nn.Module):\n"
        "    @classmethod\n"
        "    def from_pretrained(cls, m):\n"
        "        return GPT2LMHeadModel.from_pretrained(m)\n"
    )
    project = _project([WorkspaceFile(path="main.py", content=code)])
    ms = Milestone(id="m", order=1, title="Checkpoint",
                   checks=[VerificationCheck(kind="code_contains", target="from_pretrained|state_dict")])
    passed, results, _, _ = _eval(project, ms)
    assert passed is True, results[0].detail


def test_code_contains_accepts_async_def_and_alternatives():
    project = _project([WorkspaceFile(path="main.py", content="class M:\n    async def forward(self, x):\n        return x\n")])
    ms = Milestone(id="m", order=1, title="Forward",
                   checks=[VerificationCheck(kind="code_contains", target="def forward")])
    passed, _, _, _ = _eval(project, ms)
    assert passed is True


def test_code_contains_ignores_comment_only_mentions():
    # A token that appears ONLY in a comment/string must NOT satisfy the check
    # (naive substring matching would wrongly pass this).
    project = _project([WorkspaceFile(path="main.py", content="# TODO: add from_pretrained later\nx = 1\n")])
    ms = Milestone(id="m", order=1, title="Checkpoint",
                   checks=[VerificationCheck(kind="code_contains", target="from_pretrained|state_dict")])
    passed, _, _, _ = _eval(project, ms)
    assert passed is False


def test_code_contains_check_accepts_any_token():
    project = _project([WorkspaceFile(path="main.py", content="x = torch.nn.functional.cross_entropy(a, b)\n")])
    ms = Milestone(id="m", order=1, title="Loss",
                   checks=[VerificationCheck(kind="code_contains", target="cross_entropy|CrossEntropyLoss")])
    passed, _, _, _ = _eval(project, ms)
    assert passed is True


def test_code_contains_check_fails_when_absent():
    project = _project([WorkspaceFile(path="main.py", content="print('hi')\n")])
    ms = Milestone(id="m", order=1, title="Attn",
                   checks=[VerificationCheck(kind="code_contains", target="scaled_dot_product_attention|flash")])
    passed, results, _, _ = _eval(project, ms)
    assert passed is False
    assert "scaled_dot_product_attention" in results[0].detail


def test_function_call_check():
    project = _project([WorkspaceFile(path="main.py", content="def f():\n    return 1\nf()\n")])
    ms = Milestone(id="m", order=1, title="Call", checks=[VerificationCheck(kind="function_call", target="f")])
    passed, _, _, _ = _eval(project, ms)
    assert passed is True


def test_syntax_error_fails_structural_check_with_detail():
    project = _project([WorkspaceFile(path="main.py", content="def broken(:\n")])
    ms = Milestone(id="m", order=1, title="Def", checks=[VerificationCheck(kind="symbol", target="broken")])
    passed, results, _, _ = _eval(project, ms)
    assert passed is False
    assert "SyntaxError" in results[0].detail


def test_file_exists_check():
    project = _project([WorkspaceFile(path="main.py", content="")])
    ms = Milestone(id="m", order=1, title="Setup", checks=[VerificationCheck(kind="file_exists", target="main.py")])
    passed, _, _, _ = _eval(project, ms)
    assert passed is True


# ── Sandbox execution (real Docker) ──────────────────────────────────────────

def test_run_ok_executes_workspace():
    project = _project([WorkspaceFile(path="main.py", content="print('hello project')\n")])
    ms = Milestone(id="m", order=1, title="Run", checks=[VerificationCheck(kind="run_ok", target="")])
    passed, results, stdout, _ = _eval(project, ms)
    assert passed is True
    assert "hello project" in stdout


def test_run_ok_reports_real_error():
    project = _project([WorkspaceFile(path="main.py", content="raise ValueError('boom')\n")])
    ms = Milestone(id="m", order=1, title="Run", checks=[VerificationCheck(kind="run_ok", target="")])
    passed, results, _, _ = _eval(project, ms)
    assert passed is False
    assert "boom" in (results[0].detail or "") or "ValueError" in (results[0].detail or "")


def test_run_across_multiple_files():
    files = [
        WorkspaceFile(path="helper.py", content="def greet():\n    return 'hi from helper'\n"),
        WorkspaceFile(path="main.py", content="from helper import greet\nprint(greet())\n"),
    ]
    result = asyncio.run(run_workspace(sandbox, files, "main.py"))
    assert result["ran_ok"] is True
    assert "hi from helper" in result["stdout"]


def test_missing_external_dependency_is_tolerated_honestly():
    # An external package the offline sandbox can't provide is reported honestly,
    # not faked as a full run — but does not fail structural progress.
    project = _project(
        [WorkspaceFile(path="main.py", content="import langchain\nprint('x')\n")],
        tech=["langchain"],
    )
    ms = Milestone(id="m", order=1, title="Run", checks=[VerificationCheck(kind="run_ok", target="")])
    passed, results, _, _ = _eval(project, ms)
    assert passed is True
    assert "langchain" in results[0].detail


# ─── symbol_in_file: the same name, in the file the step asked for ───────────
#
# A repository course is organised by *where a name lives*, which is the lesson:
# micrograd's `Value` belongs in `engine.py` and its `Neuron` in `nn.py`. The plain
# `symbol` check asks "did you write this anywhere", so defining `Value` in the entry
# file satisfied the milestone about a different file. These tests pin the scoped
# behaviour in both directions, because a check that only ever fails tells nothing.

def _scoped(target: str, path: str) -> Milestone:
    return Milestone(
        id="m", order=1, title=f"Define {target}",
        checks=[VerificationCheck(kind="symbol_in_file", target=target, path=path)],
    )


def test_a_symbol_in_the_wrong_file_does_not_satisfy_the_check():
    project = _project([
        WorkspaceFile(path="engine.py", content="class Value:\n    pass\n"),
        WorkspaceFile(path="nn.py", content="x = 1\n"),
    ])
    passed, results, _, _ = _eval(project, _scoped("Value", "nn.py"))
    assert passed is False
    assert "nn.py" in results[0].detail


def test_the_same_symbol_in_the_named_file_does_satisfy_it():
    project = _project([
        WorkspaceFile(path="engine.py", content="class Value:\n    pass\n"),
        WorkspaceFile(path="nn.py", content="class Value:\n    pass\n"),
    ])
    passed, *_ = _eval(project, _scoped("Value", "nn.py"))
    assert passed is True


def test_a_missing_file_is_named_as_the_missing_thing():
    project = _project([WorkspaceFile(path="main.py", content="class Value:\n    pass\n")])
    passed, results, _, _ = _eval(project, _scoped("Value", "nn.py"))
    assert passed is False
    assert "nn.py" in results[0].detail


def test_mentioning_the_name_in_a_comment_or_string_is_not_defining_it():
    """AST, not text search — the difference between a check and a grep."""
    project = _project([
        WorkspaceFile(path="nn.py", content="# TODO: class Value goes here\n"
                                           "note = 'define Value in engine.py'\n"),
    ])
    passed, *_ = _eval(project, _scoped("Value", "nn.py"))
    assert passed is False


def test_a_broken_other_file_does_not_mask_this_one():
    """Scoping means the check answers its own question and no one else's.

    The workspace-wide `symbol` check fails outright when any file has a syntax error.
    That is right for a single-file project and wrong here: the step asks about
    `engine.py`, which is fine, and the milestone that *runs* the project is where a
    broken `nn.py` has to be caught.
    """
    project = _project([
        WorkspaceFile(path="engine.py", content="class Value:\n    pass\n"),
        WorkspaceFile(path="nn.py", content="def broken(:\n"),
    ])
    assert _eval(project, _scoped("Value", "engine.py"))[0] is True
    assert _eval(project, _scoped("Value", "nn.py"))[0] is False


def test_a_scoped_check_with_no_path_fails_rather_than_loosening():
    """Silently degrading to "defined anywhere" is the bug the kind exists to remove."""
    project = _project([WorkspaceFile(path="main.py", content="class Value:\n    pass\n")])
    milestone = Milestone(
        id="m", order=1, title="Define Value",
        checks=[VerificationCheck(kind="symbol_in_file", target="Value", path="")],
    )
    assert _eval(project, milestone)[0] is False


def test_an_unscoped_symbol_check_still_accepts_any_file():
    """Non-GitHub projects keep their old behaviour — the scoping is opt-in per check."""
    project = _project([WorkspaceFile(path="elsewhere.py", content="def count_words():\n    return 1\n")])
    milestone = Milestone(
        id="m", order=1, title="Define count_words",
        checks=[VerificationCheck(kind="symbol", target="count_words")],
    )
    assert _eval(project, milestone)[0] is True
