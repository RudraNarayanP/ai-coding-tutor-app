"""Could a repository's own tests be a private behavioural oracle? Measured: no.

    python -m backend.oracle_feasibility                       # this repo's own backend/
    python -m backend.oracle_feasibility /path/to/clone ...    # any local checkouts
    python -m backend.oracle_feasibility --ceiling 65536       # keep the real ceiling

Why this file exists
--------------------
A guided project built from a repository can prove three things about a learner's code -
that the required names are declared in the required files, that the files import each
other, and that the program ran - and it cannot prove a fourth: that the program *behaves*
the way the original does. `project_service.completion_feedback` says so out loud, and the
sentence is a claim about this app, so the evidence for it lives in the repository.

The obvious candidate is the repository's own upstream test suite, executed against the
learner's tree and never shown to the learner. That is exactly what this measures, by
building the mechanism rather than arguing about it: source-under-test plus only the test
modules that name a file the course selected are shipped into the real grading container
through the same `build_bootstrap` used by `run_ok`, behind a generated `unittest` entry
point that distinguishes "a test failed" from "no test could run".

The result, over 13 checkouts - 12 real permissively-licensed repositories (micrograd,
minbpe, nanoGPT, flask, click, jinja, werkzeug, httpx, uvicorn, requests, packaging,
rich) plus this app's own `backend/`:

  418 test files found; 272 of them name a module some course selected; 6,455 test
  functions between them. **Behavioural verdicts obtainable offline: 0.**
  12 of the 13 verdicts are `UNVERIFIED(no runnable test)` and the thirteenth - nanoGPT -
  has no covering test at all. Three independent reasons, each fatal alone:

  - dependencies. The grading image is `python:3.12-slim` with `--network=none`, and the
    suites import `pytest`, `pretend`, `hypothesis`, `anyio`, `trio`, `markupsafe`,
    `tiktoken`, `fastapi` - and micrograd, the teaching repository this feature was built
    around, imports `torch`. Nothing here can install them at grading time.
  - transport. The bootstrap embeds the workspace in its own source and the sandbox caps
    that at 64 KiB, and 10 of the 12 payloads that could be assembled at all are 259 KB -
    1.0 MB; only micrograd's 6 KB and minbpe's 27 KB fit. Measured again with the ceiling
    widened to 16 MB, which is what produced the numbers above: the ceiling is not the
    only wall, it is just a second one.
  - environment. 6 of the 13 suites carry markers for servers, sockets or open ports
    (`ephemeral_port_reserve`, `httpserver`, `responses`, `localhost:NNNN`), and the
    grading timeout is 10 seconds for Python against suites of up to 1,396 functions.

Also worth knowing before this is retried: there is no oracle to leak *structurally*.
`github_fetch.is_curriculum_file` drops test files while the repository is being read,
and `ProjectCourse` holds no repository field, so the snapshot - source and tests alike -
is gone before grading. Any real design would start by introducing a store that does not
exist today, and Phase 8's tests in `test_github_course.py` pin the boundary as it stands.

Threat model, because this script really did execute repository-authored test code
-----------------------------------------------------------------------------
Running an upstream suite is not running a learner's code. It is executing arbitrary
third-party source from a repository any user pasted a URL for, and it does so by import,
which means `conftest.py`, pytest plugins, `setup.py`/`pyproject` build hooks and any
module-level statement in the test tree all run too - measured here as
`tests/importer.circular_import_b` exploding at import time in uvicorn's suite. What
contains that is the existing grading container, unchanged: `--network=none`,
`--read-only`, `--tmpfs /tmp:exec,size=64m`, `--cap-drop=ALL`,
`--security-opt=no-new-privileges`, an unprivileged uid, 128 MB, 0.5 CPU, 32 pids, a
10-second wall, 64 KiB of output, and no secret in its environment because nothing is
passed to it but the payload. So the blast radius is a container that already runs
untrusted student code, with two real additions worth naming before anyone wires this in:

  - the learner's own files are in that workspace, so test code could read them; today a
    learner's code is only ever executed by the learner's own request.
  - the oracle payload is built by this app, not typed by the learner, so the 64 KiB
    ceiling that limits what a learner can submit would have to be raised for the grader
    - which is precisely the transport failure measured above, and exactly the kind of
    limit that should not be widened without a separate file channel instead.

Neither is disqualifying on its own. Both are why "just run the tests" is a design with a
security review in front of it, not a flag to flip.

What would change the answer
---------------------------- a pre-baked grading image carrying each ecosystem's test
runner and each repository's declared dependency set, a file channel that does not inline
the workspace into the code string, and a budget per run. All three are infrastructure
changes outside this module's remit, and none of them is a reason to claim behavioural
verification today.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_RUN = tempfile.mkdtemp(prefix="patchwork_oracle_")
os.environ.setdefault("PATCHWORK_STATE_DIR", _RUN)
os.environ.setdefault("PATCHWORK_PROJECT_DIR", str(Path(_RUN) / "projects"))

from . import github_fetch as gh, repo_planner as rp  # noqa: E402
from .project_models import WorkspaceFile  # noqa: E402
from .project_planner import REPO_MILESTONE_MAX, plan_repository  # noqa: E402
from .project_verifier import build_bootstrap  # noqa: E402
from .sandbox import DockerSandbox, SandboxLimits  # noqa: E402
from .source_ingestion import SourceDocument  # noqa: E402

#: What makes a file the repository's harness rather than its product. The same shapes
#: `github_fetch.NON_CURRICULUM_FILES` uses to keep them out of a course - here they are
#: the candidate oracle, so the two uses have to stay visibly in sync.
TEST_PATH = re.compile(r"(^|/)(tests?|testing)(/|$)|(^|/)test_[^/]*\.py$|(^|/)[^/]*_test\.py$")
STDLIB = set(getattr(sys, "stdlib_module_names", set()))
NEEDS_OUTSIDE = re.compile(
    r"pytest\.mark\.(network|slow|integration|live)|responses\.|vcr\b|httpserver|"
    r"localhost:\d|requests\.get\(['\"]http|urlopen\(['\"]http|socket\.socket\(", re.I)


@dataclass
class Suite:
    name: str
    test_files: list[str] = field(default_factory=list)
    frameworks: Counter = field(default_factory=Counter)
    test_functions: int = 0
    third_party: set[str] = field(default_factory=set)
    needs_outside: list[str] = field(default_factory=list)
    covering: list[str] = field(default_factory=list)
    verdict: str = ""
    detail: str = ""
    payload_kb: int = 0
    fits_real_ceiling: bool = False


def oracle_entry(modules: list[str]) -> str:
    """A runner that reports UNVERIFIED by dying differently from a failure.

    An `ImportError` is a missing package, a collection error is the repository's harness
    not standing up, and only an assertion failure is a statement about the code under
    test. Collapsing those three into "the tests failed" is how an environment problem
    turns into a learner's mark - the exact mistake this file exists to avoid repeating.
    """
    return (
        "import json, sys, unittest\n"
        f"_modules = {json.dumps(modules)}\n"
        "_loaded, _missing, _broken = [], [], []\n"
        "for _m in _modules:\n"
        "    try:\n"
        "        __import__(_m)\n"
        "        _loaded.append(_m)\n"
        "    except ModuleNotFoundError as _e:\n"
        "        _missing.append(str(_e))\n"
        "    except BaseException as _e:\n"
        "        _broken.append(f'{type(_e).__name__}: {_e}')\n"
        "if not _loaded:\n"
        "    print('UNVERIFIED: no oracle module could be imported', file=sys.stderr)\n"
        "    print(json.dumps({'missing': _missing, 'broken': _broken}), file=sys.stderr)\n"
        "    sys.exit(3)\n"
        "_suite = unittest.TestSuite()\n"
        "_loader = unittest.TestLoader()\n"
        "for _m in _loaded:\n"
        "    try:\n"
        "        _suite.addTests(_loader.loadTestsFromModule(sys.modules[_m]))\n"
        "    except BaseException as _e:\n"
        "        _broken.append(f'collection {type(_e).__name__}: {_e}')\n"
        "if _suite.countTestCases() == 0:\n"
        "    print('UNVERIFIED: the oracle collected no test', file=sys.stderr)\n"
        "    print(json.dumps({'broken': _broken, 'loaded': _loaded}), file=sys.stderr)\n"
        "    sys.exit(3)\n"
        "sys.argv = ['unittest']\n"
        "_result = unittest.TextTestRunner(verbosity=0).run(_suite)\n"
        + "print(f'COLLECTED={_suite.countTestCases()} PASSED={len(_result.successes)} "
          "FAILURES={len(_result.failures)} ERRORS={len(_result.errors)} "
          "SKIPPED={len(_result.skipped)} BROKEN={len(_broken)}')\n"
        + "sys.exit(0 if _result.wasSuccessful() and not _broken else 1)\n"
    )


def inspect(root: Path, planned: list[str]) -> Suite:
    suite = Suite(name=root.name)
    leaves = {Path(p).stem for p in planned} | {p[:-3].replace("/", ".") for p in planned}
    for path in sorted(root.rglob("*.py")):
        if ".git" in path.parts:
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if not TEST_PATH.search(rel):
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        suite.test_files.append(rel)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            suite.frameworks["unparsable"] += 1
            continue
        names, mods, is_unittest = [], set(), False
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                names.append(node.name)
            elif isinstance(node, ast.ClassDef) and any(
                    getattr(b, "id", getattr(getattr(b, "value", None), "id", "")) in
                    ("TestCase", "Testcase", "Test") for b in node.bases):
                is_unittest = True
            elif isinstance(node, ast.Import):
                mods.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                mods.add(node.module.split(".")[0])
        suite.test_functions += len(names)
        suite.third_party |= {m for m in mods if m not in STDLIB and m != "__future__"}
        suite.frameworks["pytest+unittest" if "pytest" in mods and is_unittest else
                         "pytest" if "pytest" in mods else
                         "unittest" if is_unittest or names else "none"] += 1
        if NEEDS_OUTSIDE.search(source):
            suite.needs_outside.append(rel)
        if any(len(leaf) > 2 and leaf in source for leaf in leaves):
            suite.covering.append(rel)
    return suite


def run_oracle(root: Path, suite: Suite, planned: list[str], ceiling: int) -> None:
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*.py")):
        if ".git" in path.parts:
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if TEST_PATH.search(rel) or rel in planned or path.name == "__init__.py":
            try:
                files[rel] = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    modules = sorted({p[:-3].replace("/", ".") for p in suite.covering})
    files["_patchwork_oracle.py"] = oracle_entry(modules)
    workspace = [WorkspaceFile(path=p, content=c) for p, c in files.items()]
    suite.payload_kb = sum(len(c) for c in files.values()) // 1024
    bootstrap = build_bootstrap(workspace, "_patchwork_oracle.py")
    suite.fits_real_ceiling = len(bootstrap) < 64 * 1024

    started = time.perf_counter()
    try:
        result = asyncio.run(DockerSandbox(SandboxLimits(max_code_bytes=ceiling)).run(
            {"language": "python", "code": bootstrap, "tests": [{"name": "oracle", "stdin": ""}]}))
    except Exception as exc:  # noqa: BLE001 - a transport refusal is a labelled result
        suite.verdict = "UNVERIFIED(transport)"
        suite.detail = f"{type(exc).__name__}: {str(exc)[:140]}"
        return
    seconds = round(time.perf_counter() - started, 1)
    test = (result.get("tests") or [{}])[0]
    out = (test.get("stdout") or "") + (test.get("stderr") or "")
    error = str(test.get("error") or "")
    if "UNVERIFIED" in out:
        suite.verdict = "UNVERIFIED(no runnable test)"
        suite.detail = " ".join(out.split()[-16:])
    elif "COLLECTED=" in out:
        summary = next((ln for ln in out.splitlines() if "COLLECTED=" in ln), "")
        counts = dict(kv.split("=") for kv in summary.split() if "=" in kv)
        bad = int(counts.get("FAILURES", 0)) + int(counts.get("ERRORS", 0))
        suite.verdict = ("FAIL(behaviour)" if bad else
                         "UNVERIFIED(harness error)" if int(counts.get("BROKEN", 0))
                         else "PASS(behaviour)")
        suite.detail = summary
    elif "timeout" in error.lower():
        suite.verdict, suite.detail = "UNVERIFIED(timeout)", f"{seconds}s budget"
    else:
        suite.verdict = "UNVERIFIED(container)"
        suite.detail = (error or out)[-160:]
    if seconds:
        suite.detail += f" [{seconds}s]"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repos", nargs="*", type=Path,
                        help="local checkouts (default: this repository's backend/)")
    parser.add_argument("--ceiling", type=int, default=16_000_000,
                        help="payload limit; 65536 keeps the production ceiling")
    args = parser.parse_args(argv)

    print(f"behavioural oracle feasibility, max_code_bytes={args.ceiling}\n")
    print(f"{'checkout':<22} {'tests':>5} {'cover':>5} {'fns':>6} {'payload':>9} "
          f"{'fits64k':>7}  frameworks / verdict")
    print("-" * 132)
    tally: Counter = Counter()
    totals = Counter()
    for root in (args.repos or [_ROOT / "backend"]):
        root = root.resolve()
        snapshot = gh.open_local_repo(root)
        snapshot.license = "MIT"
        try:
            course = plan_repository(
                SourceDocument(source_type="github_repo", source_url=root.name,
                               source_hash=root.name, title=root.name, plain_text="",
                               access_level="full", repo=snapshot),
                title="", course_id="oracle")
        except Exception as exc:  # noqa: BLE001 - a refusal is a result
            print(f"{root.name:<22} NOT PLANNED: {type(exc).__name__}: {str(exc)[:70]}")
            continue
        planned = [c.target for m in course.milestones for c in m.checks
                   if c.kind == "file_exists"]
        suite = inspect(root, planned)
        totals["test files"] += len(suite.test_files)
        totals["covering a planned module"] += len(suite.covering)
        totals["test functions"] += suite.test_functions
        if not suite.covering:
            suite.verdict = "no test names a planned module"
        else:
            run_oracle(root, suite, planned, args.ceiling)
        tally[suite.verdict.split("(")[0]] += 1
        print(f"{root.name:<22} {len(suite.test_files):>5} {len(suite.covering):>5} "
              f"{suite.test_functions:>6} {suite.payload_kb:>7}KB "
              f"{str(suite.fits_real_ceiling):>7}  {suite.verdict}")
        print(f"{'':<22} {'':>5} {'':>5} {'':>6} {'':>7}  "
              f"{', '.join(f'{k}={v}' for k, v in suite.frameworks.most_common(3))}"
              f"{'  needs-outside: ' + ', '.join(Path(p).name for p in suite.needs_outside[:4]) if suite.needs_outside else ''}")
        if suite.third_party:
            print(f"{'':<22} third-party imports in the suite: "
                  f"{', '.join(sorted(suite.third_party - set(suite.test_files))[:9])}")
        if suite.detail:
            print(f"{'':<22} {suite.detail[:120]}")

    print(f"\ntotals: " + "  ".join(f"{k}={v}" for k, v in totals.items()))
    print("verdicts: " + "  ".join(f"{k}={v}" for k, v in tally.most_common()))
    behavioural = tally["PASS"] + tally["FAIL"]
    print(f"\nbehavioural evidence obtainable offline: {behavioural} repositories. "
          "Until that number is not zero, `run_ok` remains execution, not correctness - "
          "see this module's docstring for the three reasons and what would have to "
          "change.")
    shutil.rmtree(_RUN, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
