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
