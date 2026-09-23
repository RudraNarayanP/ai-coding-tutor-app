"""Milestone verification for Create Course guided projects.

Verification is outcome-based so a learner's valid alternative implementation is
accepted:

* Structural checks (`import`, `symbol`, `symbol_in_file`, `function_call`,
  `code_contains`, `file_exists`) use Python's `ast` module — they inspect what
  the code says, not its exact text, and never execute learner code. They can
  prove a file, a name or a wiring line exists. They cannot prove any behaviour,
  and `evidence_of` is what keeps that claim in the record instead of letting a
  green tick imply more than it says.
* Runtime checks (`run_ok`, `stdout_contains`) execute the whole persistent
  workspace inside the existing Docker sandbox and inspect real behaviour. A run
  that stopped at a package the offline sandbox does not have is reported as
  *unverified* rather than passed: the learner may continue, because the gap is
  the environment's, but nothing was observed.

Nothing here mutates the learner's workspace; the learner owns the code.
"""
from __future__ import annotations

import ast
import io
import json
import re
import sys
import tokenize

from .project_models import (
    Milestone,
    ProjectCheckResult,
    ProjectCourse,
    VerificationCheck,
    WorkspaceFile,
)
# The exception type only, for the one branch that has to tell "the learner's program
# failed" apart from "this app could not run their program at all".
from .sandbox import SandboxError

_STDLIB = set(getattr(sys, "stdlib_module_names", set())) | {"__future__"}

#: The only checks that observe the learner's program doing anything.
RUNTIME_CHECK_KINDS = frozenset({"run_ok", "stdout_contains"})


def evidence_of(milestone: Milestone, results: list[ProjectCheckResult]) -> str:
    """What a set of passed checks actually established, for the completion record.

    The states are deliberately not collapsed into the boolean. `passed` answers "may this
    learner continue"; this answers "what did we just learn", and a project's ending is
    derived from the answer rather than asserted. Six are meaningful for a graded program;
    what this function produces today is marked, and `FAILED` belongs to the caller:

      STRUCTURAL (produced)   a name exists where it was required to exist - a file, a
                              declaration in that file, an import line between two of
                              them. Decided from syntax; learner code never runs.
      WIRED      (produced as STRUCTURAL) an `import` scoped to a named file can only pass
                              if that file asks for the module the course assigned it.
                              Wiring, not use: importing a name and ignoring it passes.
      EXECUTED   (produced)   the whole persistent workspace was run in the sandbox and
                              completed the execution contract: started, did not raise,
                              exited 0. This says the program runs. It says nothing about
                              what it computes.
      UNVERIFIED (produced)   the claim could not be tested here at all - a dependency the
                              offline image lacks, a payload over the transport ceiling.
                              The learner advances, because the gap is the environment's,
                              and the record refuses to say anything about behaviour.
      BEHAVIOURALLY_VERIFIED  not produced, and nothing may claim it. It would mean an
                              authoritative test of the real project passed against the
                              learner's code. No such test is available offline: across 13
                              checkouts, 418 upstream test files and 6,455 test functions
                              yield 0 behavioural verdicts in this image - see
                              `backend/oracle_feasibility.py`. Until that changes,
                              EXECUTED must never be worded as correctness, here or in
                              `project_service.completion_feedback`.
    """
    runtime = [result for check, result in zip(milestone.checks, results)
               if check.kind in RUNTIME_CHECK_KINDS]
    if runtime:
        return "executed" if all(r.verified for r in runtime) else "unverified"
    return "structural"


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


def _names_in_tree(tree: ast.AST) -> set[str]:
    names: set[str] = set()
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


def _defined_symbols(trees: list[ast.AST]) -> set[str]:
    return {name for tree in trees for name in _names_in_tree(tree)}


def _declared_in_file(files: list[WorkspaceFile], path: str) -> tuple[set[str], str | None]:
    """Names this file declares at module level, as a class or a def.

    `symbol_in_file` used to accept *any* binding, so `Value = None` satisfied the step
    about a class - and a course of such one-liners passed every structural milestone in
    all 13 repositories measured. This asks for the kind of thing the source file
    actually contains: `repo_planner` only ever demands a name it read off the module's
    top-level `class`/`def` list, so requiring one is exactly congruent with what the
    milestone names, and it is still decided from syntax rather than from text.
    """
    for file in files:
        if file.path != path:
            continue
        try:
            tree = ast.parse(file.content, filename=path)
        except SyntaxError as exc:
            return set(), f"SyntaxError in {path}: {exc.msg} (line {exc.lineno})"
        return {
            node.name for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }, None
    return set(), None


def _imported_in_file(files: list[WorkspaceFile], path: str) -> tuple[set[str], str | None]:
    """Every dotted part of every import in one file, plus the reason there are none.

    A path-scoped `import` check has to accept the three spellings of the same module,
    because which one is right depends on where the file sits: `import micrograd.engine`,
    `from micrograd.engine import Value`, and — inside the package, which is what the real
    project writes — `from .engine import Value`. The one thing all three contain is the
    leaf, so the leaf is what is matched. Matching the whole dotted name would reject the
    relative spelling, and the milestone would demand a line the repository itself does
    not write.
    """
    for file in files:
        if file.path != path:
            continue
        try:
            tree = ast.parse(file.content, filename=path)
        except SyntaxError as exc:
            return set(), f"SyntaxError in {path}: {exc.msg} (line {exc.lineno})"
        parts: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    parts.update(alias.name.split("."))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    parts.update(node.module.split("."))
                parts.update(alias.name for alias in node.names)
        return {p.lower() for p in parts if p}, None
    return set(), None


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


def _all_identifiers(trees: list[ast.AST]) -> set[str]:
    """Every identifier the code *references* — defined names, called names,
    attribute accesses, arguments, keyword args, and imports. Lowercased.

    This lets a concept-level `code_contains` check recognise a token whether it
    is defined (``def from_pretrained``), called (``obj.from_pretrained()``), or
    imported — instead of naive substring matching that also trips on comments.
    """
    ids: set[str] = set()
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                ids.add(node.name)
            elif isinstance(node, ast.Name):
                ids.add(node.id)
            elif isinstance(node, ast.Attribute):
                ids.add(node.attr)
            elif isinstance(node, ast.arg):
                ids.add(node.arg)
            elif isinstance(node, ast.keyword) and node.arg:
                ids.add(node.arg)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    ids.add(alias.asname or alias.name.split(".")[0])
                    ids.add(alias.name.split(".")[-1])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    ids.add(node.module.split(".")[0])
                    ids.add(node.module.split(".")[-1])
                for alias in node.names:
                    ids.add(alias.asname or alias.name)
    return {i.lower() for i in ids}


def _code_without_comments_strings(source: str) -> str:
    """Return source with comments removed and string *contents* blanked, so a
    token that only appears inside a comment or string literal is NOT counted."""
    try:
        pieces: list[str] = []
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            if tok.type in (tokenize.FSTRING_MIDDLE,) if hasattr(tokenize, "FSTRING_MIDDLE") else ():
                continue
            pieces.append(tok.string)
        return " ".join(pieces)
    except Exception:  # noqa: BLE001 — partial/edited code may not tokenize.
        return re.sub(r"#.*", "", source)


def _code_contains_match(
    token: str, identifiers: set[str], stripped_lower: str, raw_lower: str, syntax_ok: bool
) -> bool:
    """Semantic match for one accepted token.

    - dotted (``nn.Module``): attribute chain in real code, or last attr referenced
    - phrase (``def forward``): the salient identifier is actually defined/referenced
    - simple identifier: referenced in the AST, or present in comment/string-free code
    Falls back to lenient substring on unparseable code to avoid false negatives.
    """
    low = token.lower().strip()
    if not low:
        return False
    idents_in_token = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", low)

    if "." in token:
        if low in stripped_lower:
            return True
        if idents_in_token and syntax_ok and idents_in_token[-1] in identifiers:
            return True
        return low in raw_lower if not syntax_ok else False

    if " " in token:  # e.g. "def forward", "from x import y"
        if idents_in_token and syntax_ok and idents_in_token[-1] in identifiers:
            return True
        return low in stripped_lower

    # Simple identifier.
    if syntax_ok:
        if low in identifiers:
            return True
        # A bare identifier can still be valid even if AST didn't classify it
        # (e.g. inside an f-string expression); accept a comment/string-free hit.
        return bool(re.search(rf"\b{re.escape(low)}\b", stripped_lower))
    # Unparseable (mid-edit) code: be lenient — substring on comment-free source.
    return bool(re.search(rf"\b{re.escape(low)}\b", stripped_lower))


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
    identifiers = _all_identifiers(trees)
    source = "\n".join(c for _p, c in _python_sources(files))
    stripped_lower = _code_without_comments_strings(source).lower()
    raw_lower = source.lower()
    code_index = {
        "identifiers": identifiers,
        "stripped_lower": stripped_lower,
        "raw_lower": raw_lower,
        "syntax_ok": syntax_error is None,
    }

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
        passed, detail, verified = await _evaluate_check(
            executor, project, check, files, imported, defined, called, syntax_error, code_index, _get_run
        )
        results.append(ProjectCheckResult(
            description=check.description or check.kind, passed=passed, detail=detail,
            verified=verified))

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
    code_index: dict,
    get_run,
) -> tuple[bool, str, bool]:
    """(may the learner continue, what to tell them, was the claim actually tested).

    The third answer is the one that was missing. A run that stopped at a package the
    offline sandbox does not have let the learner through, and the record said the
    program had been shown to work. Advancing is still right - that gap is the
    environment's, not theirs - but advancing and demonstrating are different claims,
    and this is the only place that knows which one just happened.
    """
    kind = check.kind

    if kind == "file_exists":
        exists = any(f.path == check.target for f in files)
        return exists, ("" if exists else f"Add a file named `{check.target}`."), exists

    if kind == "symbol_in_file":
        # Path-scoped on purpose. `symbol` asks "did the learner write this anywhere",
        # which is right for a transcript that says "define count_words" and wrong for a
        # repository, where the whole lesson is *which file* a name belongs in: without
        # this, dropping `Value` into the entry file passes the `nn.py` milestone.
        path = check.path or ""
        if not path:
            return False, "This milestone names no file to check — that is a bug, not a step.", False
        if not any(f.path == path for f in files):
            return False, f"Add a file named `{path}`.", False
        names, error = _declared_in_file(files, path)
        if error:
            return False, error, False
        ok = check.target in names
        return ok, ("" if ok else f"`{check.target}` isn't declared in `{path}` yet - the "
                                  f"project has it as a class or a function there."), ok

    # Structural checks require parseable code.
    if kind in ("import", "symbol", "function_call") and syntax_error:
        return False, syntax_error, False

    if kind == "import":
        if check.path:
            # Scoped to one file the way `symbol_in_file` is. The claim is that *this*
            # file is wired into the one above it - which is the only part of
            # "rebuild it module by module" that can be decided without running it.
            parts, error = _imported_in_file(files, check.path)
            if error:
                return False, error, False
            leaf = (check.target or "").rstrip(".").split(".")[-1].lower()
            ok = bool(leaf) and leaf in parts
            return ok, ("" if ok else
                        f"`{check.path}` doesn't import `{check.target}` yet, and that is "
                        f"the file above it that this one stands on."), ok
        ok = check.target.lower() in {name.lower() for name in imported}
        return ok, ("" if ok else f"No import of `{check.target}` found yet."), ok

    if kind == "symbol":
        ok = check.target in defined
        return ok, ("" if ok else f"`{check.target}` isn't defined in your workspace yet."), ok

    if kind == "function_call":
        ok = check.target in called
        return ok, ("" if ok else f"`{check.target}` isn't called anywhere yet."), ok

    if kind == "code_contains":
        # Concept-level, grounded check. Semantic (AST-aware): a token counts
        # whether it is defined, called, imported, or accessed as an attribute —
        # and NOT when it only appears in a comment or string. Any of the
        # "|"-separated tokens satisfies the milestone (alternative impls).
        tokens = [t.strip() for t in check.target.split("|") if t.strip()]
        ok = any(
            _code_contains_match(
                t,
                code_index["identifiers"],
                code_index["stripped_lower"],
                code_index["raw_lower"],
                code_index["syntax_ok"],
            )
            for t in tokens
        )
        if ok:
            return True, "", True
        pretty = " or ".join(f"`{t}`" for t in tokens)
        return False, f"Your code doesn't reference {pretty} yet.", False

    if kind in ("run_ok", "stdout_contains"):
        if syntax_error:
            return False, syntax_error, False
        try:
            run = await get_run()
        except SandboxError as exc:
            # The grader could not carry the run out at all: the workspace does not fit
            # the sandbox payload ceiling, or Docker is not answering. That is this app's
            # limitation rather than the learner's error, and it used to surface as an
            # HTTP 503 on the very step that advances them - seven files re-implementing
            # part of a real framework is over the 64 KiB bootstrap ceiling on its own.
            # Same rule as an absent dependency: let them through, and say plainly that
            # nothing was observed.
            return True, (
                f"Unverified: this app could not run your project here ({exc}). Nothing "
                f"has been checked about whether it works."
            ), False
        if run["ran_ok"]:
            if kind == "stdout_contains" and check.target:
                ok = check.target in (run.get("stdout") or "")
                return ok, ("" if ok else f"Expected output to contain `{check.target}`."), ok
            return True, "", True
        # Real run failure — but tolerate (honestly) a missing external dependency
        # that the offline sandbox can't provide.
        missing = _external_module_missing(run.get("error"), project.tech_stack)
        if missing:
            # passed=True keeps the learner moving; verified=False says what did not
            # happen. The program was not seen to finish, so nothing about whether it
            # works was observed - and the old wording ("Your code's syntax and
            # structure are verified") claimed the opposite in the same breath as
            # admitting the run stopped early.
            return True, (
                f"Unverified: your code reached `{missing}`, a dependency the offline "
                f"practice sandbox does not have, so the program was never seen to "
                f"finish. Nothing about whether it works has been checked."
            ), False
        return False, (run.get("error") or "Your project raised an error when run."), False

    return False, "Unknown check.", False
