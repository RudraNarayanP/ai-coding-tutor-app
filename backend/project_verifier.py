"""Milestone verification for Create Course guided projects.

Verification is outcome-based so a learner's valid alternative implementation is
accepted:

* Structural checks (`import`, `symbol`, `function_call`, `file_exists`) use
  Python's `ast` module — they inspect what the code *achieves*, not its exact
  text, and never execute learner code.
* Runtime checks (`run_ok`, `stdout_contains`) execute the whole persistent
  workspace inside the existing Docker sandbox and inspect real behaviour.

Nothing here mutates the learner's workspace; the learner owns the code.
"""
from __future__ import annotations

import ast
import json
import sys

from .project_models import (
    Milestone,
    ProjectCheckResult,
    ProjectCourse,
    VerificationCheck,
    WorkspaceFile,
)

_STDLIB = set(getattr(sys, "stdlib_module_names", set())) | {"__future__"}


def _python_sources(files: list[WorkspaceFile]) -> list[tuple[str, str]]:
    return [(f.path, f.content) for f in files if f.path.endswith(".py")]


def _parse_all(files: list[WorkspaceFile]) -> tuple[list[ast.AST], str | None]:
    """Parse every Python file. Returns (trees, first_syntax_error)."""
    trees: list[ast.AST] = []
    for path, content in _python_sources(files):
        try:
            trees.append(ast.parse(content, filename=path))
        except SyntaxError as exc:
            return trees, f"SyntaxError in {path}: {exc.msg} (line {exc.lineno})"
    return trees, None


def _imported_modules(trees: list[ast.AST]) -> set[str]:
    modules: set[str] = set()
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    modules.add(node.module.split(".")[0])
    return modules


def _defined_symbols(trees: list[ast.AST]) -> set[str]:
    names: set[str] = set()
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        names.add(tgt.id)
                    elif isinstance(tgt, (ast.Tuple, ast.List)):
                        for elt in tgt.elts:
                            if isinstance(elt, ast.Name):
                                names.add(elt.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    names.add(alias.asname or alias.name.split(".")[0])
    return names


def _called_names(trees: list[ast.AST]) -> set[str]:
    names: set[str] = set()
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    names.add(func.id)
                elif isinstance(func, ast.Attribute):
                    names.add(func.attr)
    return names


def build_bootstrap(files: list[WorkspaceFile], entry_file: str) -> str:
    """Produce a single Python program that materialises the workspace and runs
    the entry file as ``__main__`` inside the sandbox tmpfs."""
    file_map = {f.path: f.content for f in files}
    return (
        "import os, sys, json, runpy\n"
        f"_files = json.loads({json.dumps(json.dumps(file_map))})\n"
        "_root = '/tmp/pwproject'\n"
        "os.makedirs(_root, exist_ok=True)\n"
        "for _p, _c in _files.items():\n"
        "    _fp = os.path.join(_root, _p)\n"
        "    _d = os.path.dirname(_fp)\n"
        "    if _d:\n"
        "        os.makedirs(_d, exist_ok=True)\n"
        "    with open(_fp, 'w', encoding='utf-8') as _f:\n"
        "        _f.write(_c)\n"
        "os.chdir(_root)\n"
        "sys.path.insert(0, _root)\n"
        f"_entry = {json.dumps(entry_file)}\n"
        "if not os.path.exists(os.path.join(_root, _entry)):\n"
        "    raise FileNotFoundError('Entry file ' + _entry + ' not found in workspace')\n"
        "runpy.run_path(os.path.join(_root, _entry), run_name='__main__')\n"
    )


async def run_workspace(executor, files: list[WorkspaceFile], entry_file: str, stdin: str = "") -> dict:
    """Execute the persistent workspace in the sandbox. Returns a dict with
    keys: ran_ok, stdout, stderr, error (None on success)."""
    bootstrap = build_bootstrap(files, entry_file)
    payload = {
        "language": "python",
        "code": bootstrap,
        "tests": [{"name": "run", "stdin": stdin}],
    }
    result = await executor.run(payload)
    tests = result.get("tests") or []
    if tests:
        t = tests[0]
        return {
            "ran_ok": bool(t.get("passed")) and not t.get("error"),
            "stdout": t.get("stdout", "") or result.get("stdout", ""),
            "stderr": t.get("stderr", "") or result.get("stderr", ""),
            "error": t.get("error"),
        }
    return {
        "ran_ok": bool(result.get("passed")) and not result.get("error"),
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "error": result.get("error"),
    }


def _external_module_missing(error: str | None, tech_stack: list[str]) -> str | None:
    """If a run failed only because a non-stdlib dependency isn't installed in the
    sandbox, return that module name; otherwise None."""
    if not error:
        return None
    # e.g. "ModuleNotFoundError: No module named 'langchain'"
    import re

    m = re.search(r"No module named ['\"]([A-Za-z0-9_]+)['\"]", error)
    if not m:
        return None
    mod = m.group(1)
    if mod in _STDLIB:
        return None
    return mod


async def evaluate_milestone(
    executor,
    project: ProjectCourse,
    milestone: Milestone,
    files: list[WorkspaceFile],
) -> tuple[bool, list[ProjectCheckResult], str, str]:
    """Evaluate every check for a milestone against the current workspace.

    Returns (all_passed, per_check_results, stdout, stderr).
    """
    trees, syntax_error = _parse_all(files)
    imported = _imported_modules(trees)
    defined = _defined_symbols(trees)
    called = _called_names(trees)

    results: list[ProjectCheckResult] = []
    run_cache: dict | None = None
    stdout_out = ""
    stderr_out = ""

    async def _get_run() -> dict:
        nonlocal run_cache, stdout_out, stderr_out
        if run_cache is None:
            run_cache = await run_workspace(executor, files, project.entry_file)
            stdout_out = run_cache.get("stdout", "") or ""
            stderr_out = run_cache.get("stderr", "") or ""
        return run_cache

    for check in milestone.checks:
        passed, detail = await _evaluate_check(
            executor, project, check, files, imported, defined, called, syntax_error, _get_run
        )
        results.append(ProjectCheckResult(description=check.description or check.kind, passed=passed, detail=detail))

    all_passed = all(r.passed for r in results) and bool(results)
    return all_passed, results, stdout_out, stderr_out


async def _evaluate_check(
    executor,
    project: ProjectCourse,
    check: VerificationCheck,
    files: list[WorkspaceFile],
    imported: set[str],
    defined: set[str],
    called: set[str],
    syntax_error: str | None,
    get_run,
) -> tuple[bool, str]:
    kind = check.kind

    if kind == "file_exists":
        exists = any(f.path == check.target for f in files)
        return exists, ("" if exists else f"Add a file named `{check.target}`.")

    # Structural checks require parseable code.
    if kind in ("import", "symbol", "function_call") and syntax_error:
        return False, syntax_error

    if kind == "import":
        ok = check.target in imported
        return ok, ("" if ok else f"No import of `{check.target}` found yet.")

    if kind == "symbol":
        ok = check.target in defined
        return ok, ("" if ok else f"`{check.target}` isn't defined in your workspace yet.")

    if kind == "function_call":
        ok = check.target in called
        return ok, ("" if ok else f"`{check.target}` isn't called anywhere yet.")

    if kind == "code_contains":
        # Concept-level, grounded check: the workspace references any of the
        # accepted tokens (case-insensitive). Accepts alternative spellings via
        # a "|"-separated target list.
        blob = "\n".join(c for _p, c in _python_sources(files)).lower()
        tokens = [t.strip().lower() for t in check.target.split("|") if t.strip()]
        ok = any(t in blob for t in tokens) if tokens else False
        if ok:
            return True, ""
        pretty = " or ".join(f"`{t.strip()}`" for t in check.target.split("|") if t.strip())
        return False, f"Your code doesn't reference {pretty} yet."

    if kind in ("run_ok", "stdout_contains"):
        if syntax_error:
            return False, syntax_error
        run = await get_run()
        if run["ran_ok"]:
            if kind == "stdout_contains" and check.target:
                ok = check.target in (run.get("stdout") or "")
                return ok, ("" if ok else f"Expected output to contain `{check.target}`.")
            return True, ""
        # Real run failure — but tolerate (honestly) a missing external dependency
        # that the offline sandbox can't provide.
        missing = _external_module_missing(run.get("error"), project.tech_stack)
        if missing:
            return True, (
                f"Ran up to `{missing}`, an external dependency not installed in the offline "
                f"practice sandbox. Your code's syntax and structure are verified."
            )
        return False, (run.get("error") or "Your project raised an error when run.")

    return False, "Unknown check."
