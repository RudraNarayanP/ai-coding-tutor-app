"""Does a repository's import chain make a coherent course, or only a sorted file list?

Dev script and regression measurement, not a gate:

    python -m backend.chain_coherence                     # this repository's own backend/
    python -m backend.chain_coherence /path/to/clone ...   # any local checkouts
    python -m backend.chain_coherence --sandbox            # also run the stub program

`measure_project_quality.py` measures milestone quality for the prose routes, where a
guided project is one persistent `main.py`. The repository route is a different object -
several files at nested paths, an entry point chosen by fan-in, and a closing `run_ok`
that is offered as the composition test - and nothing measured its coherence. This does,
on real code: it reads local checkouts through the same `snapshot_from_files` the GitHub
fetch uses, so no test or measurement needs the network or anybody else's repository.

Five questions, reported apart and never averaged, because a zero in one means one thing
and not three. Four of them are invariants, and the script exits non-zero if one breaks:

  claims      is every causal sentence a milestone tells the learner true of the graph?
  gaps        is every import with no milestone behind it disclosed to the learner?
  workspace   what does the learner inherit already satisfied?
  artifact    is the name a step demands the name the next step actually references?
  stubs       (not an invariant) can a program of empty stubs pass the whole course?

The recorded run, 13 real permissively-licensed repositories - karpathy/micrograd,
minbpe, nanoGPT, pallets/flask, click, jinja, werkzeug, encode/httpx, uvicorn,
psf/requests, pypa/packaging, Textualize/rich and this app's own `backend/`, 13 courses,
99 milestones, 240 checks, 86 of them at nested paths:

  claims      15 of 86 sentences contradicted the repository before the fix; 0 after.
              All 8 cycle sentences are now true of the graph, and none names a direct
              mutual edge, because flask's 17-file core has none.
  gaps        126 imports have no milestone behind them - 96 because the eight-milestone
              budget cannot fit the closure, 30 because the module holds nothing
              gradeable. All 40 affected steps say so and name at least one of them;
              `_brief` counts the rest rather than listing them, because past
              `project_copy.MAX_WHY` the sentence is replaced by generic copy entirely.
              See `repo_planner.build_chain`.
  workspace   exactly 1 check of 240 is satisfied before any work, everywhere: the seeded
              entry file's `file_exists`, on the penultimate step. No first step is free.
  artifact    31 of 86 dependency edges demand a name the consumer never references,
              because a step asks for `ranked_defines()[:2]` and the file has more.
  stubs       what a workspace of empty definitions gets: **86 of 86** structural
              milestones passed, in all 13 repositories, and the closing `run_ok` passed
              with them in 13 of 13 - which is the finding that put the wiring checks in
              `plan_repository`. Measured again after them: 48 of 86, and
              `project_complete` 0 of 13 where it had been 13 of 13, while each
              repository's own source still finishes. The 48 that still pass are the
              steps that import nothing this course assigned, and for those a name in a
              file is genuinely all the milestone claims. See
              `audit/grading_audit.py` and `audit/corpus_integrity.py` for the
              adversarial suite and the before/after table; forcing a step to prove
              behaviour rather than wiring needs the repository's own tests, which
              `github_fetch` correctly keeps out of a course.
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import os
import re
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
# Same contract as conftest: importing the planner can build stores, and a measurement
# must never write into a learner's real state.
_RUN = tempfile.mkdtemp(prefix="patchwork_coherence_")
os.environ.setdefault("PATCHWORK_STATE_DIR", _RUN)
os.environ.setdefault("PATCHWORK_PROJECT_DIR", str(Path(_RUN) / "projects"))

from . import github_fetch as gh, repo_planner as rp  # noqa: E402
from .project_models import WorkspaceFile  # noqa: E402
from .project_planner import REPO_MILESTONE_MAX, plan_repository  # noqa: E402
from .project_verifier import evaluate_milestone  # noqa: E402
from .source_ingestion import SourceDocument  # noqa: E402

#: Each sentence `plan_repository` can emit, with the pattern that identifies it. Read
#: back out of the text the learner actually sees, so a change to the wording that drops
#: the claim is a change this script notices.
CLAIMS = [
    ("consumers", re.compile(r"stand on its own before they can be built")),
    ("cycle", re.compile(r"is in one import cycle with")),
    ("already", re.compile(r"which you have already written")),
    ("unassigned", re.compile(r"which no step here asks you to write")),
    ("root", re.compile(r"Nothing in the project is underneath this file")),
]
BACKTICK = re.compile(r"`([^`]+)`")


def reachable(start: str, target: str, by_module: dict) -> bool:
    """Is `target` reachable from `start` through imports? Computed here rather than
    borrowed from `repo_planner.reaches`: the checker and the checked must not agree by
    construction, or a passing measurement only proves the code equals itself."""
    seen, stack = set(), [start]
    while stack:
        module = stack.pop()
        if module == target:
            return True
        for dep in (by_module[module].depends if module in by_module else ()):
            if dep not in seen:
                seen.add(dep)
                stack.append(dep)
    return False


def milestone_path(milestone) -> str:
    return next((c.target for c in milestone.checks if c.kind == "file_exists"), "")


def code_names(tree_source: str) -> set[str]:
    """Names one file's code reads, so an edge can be checked against a real use."""
    try:
        tree = ast.parse(tree_source)
    except SyntaxError:
        return set()
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}


@dataclass
class Result:
    name: str
    refusal: str = ""
    course: object = None
    claims: Counter = field(default_factory=Counter)
    bad_claims: list = field(default_factory=list)
    gaps: list = field(default_factory=list)
    undisclosed: list = field(default_factory=list)
    workspace: Counter = field(default_factory=Counter)
    artifact: Counter = field(default_factory=Counter)
    stubs: Counter = field(default_factory=Counter)


def snapshot_of(path: Path) -> gh.RepoSnapshot:
    files = [(str(p.relative_to(path)).replace("\\", "/"), p.read_bytes())
             for p in sorted(path.rglob("*.py")) if p.is_file() and ".git" not in p.parts]
    return gh.snapshot_from_files(str(path), files, owner=path.parent.name,
                                  repo=path.name, ref="HEAD", license="MIT")


def measure_one(path: Path, executor=None) -> Result:
    result = Result(name=f"{path.parent.name}/{path.name}" if path.name != "backend"
                    else "patchwork/backend")
    snapshot = snapshot_of(path)
    if len(snapshot.files) < 2:
        result.refusal = f"only {len(snapshot.files)} curriculum modules in the snapshot"
        return result
    analyzed = rp.analyze([(f.path, f.content) for f in snapshot.files])
    ordered = rp.dependency_order([f for f in analyzed
                                   if not f.unparsable and f.public_names])
    chosen = rp.build_chain(ordered, limit=REPO_MILESTONE_MAX)
    try:
        course = plan_repository(
            SourceDocument(source_type="github_repo", source_url="u", source_hash="h",
                           title="t", plain_text="", access_level="full", repo=snapshot),
            title="", course_id="coherence")
    except Exception as exc:  # noqa: BLE001 - refusing a source is a result, not a crash
        result.refusal = f"{type(exc).__name__}: {str(exc)[:110]}"
        return result
    result.course = course
    by_path = {f.path: f for f in analyzed}
    by_module = {f.module: f for f in analyzed}
    planned = {f.module for f in chosen}
    position = {f.module: i for i, f in enumerate(chosen)}
    source = {f.path: f.content for f in snapshot.files}

    # -- claims: is every causal sentence true of the graph? --
    for milestone in course.milestones:
        path_here = milestone_path(milestone)
        facts = by_path.get(path_here)
        if facts is None:
            continue
        mine = facts.module
        here = {path_here, mine, facts.path[:-3]}
        for sentence in re.split(r"(?<=\.)\s+", milestone.why or ""):
            for branch, pattern in CLAIMS:
                if not pattern.search(sentence):
                    continue
                result.claims[branch] += 1
                named = [t.strip() for t in BACKTICK.findall(sentence)]
                modules = [t for t in named if t in by_module and t not in here]
                files = [t for t in named if t.endswith(".py") and t != path_here]
                if branch == "cycle":
                    wrong = [m for m in modules if not reachable(m, mine, by_module)]
                elif branch == "already":
                    wrong = ([m for m in modules if m not in facts.depends]
                             + [m for m in modules if position.get(m, 99) >= position[mine]])
                elif branch == "consumers":
                    wrong = ([f for f in files if f in by_path and mine not in by_path[f].depends]
                             + [f for f in files
                                if f in by_path and position.get(by_path[f].module, 99)
                                < position[mine]])
                elif branch == "unassigned":
                    wrong = [m for m in modules
                             if m in planned or m not in facts.depends]
                else:
                    wrong = [] if not facts.depends else sorted(facts.depends)
                result.claims[f"{branch}-true"] += not wrong
                if wrong:
                    result.bad_claims.append(f"{path_here}: {branch} says {wrong}")

    # -- gaps: does every step with an import behind it say so? --
    #
    # Naming every one is not achievable: `_brief` keeps a milestone a card rather than a
    # paragraph, and past `project_copy.MAX_WHY` the whole sentence is replaced by generic
    # copy, so a longer disclosure is a disclosure lost. So the promise checked here is the
    # one the text can keep - the step says it depends on files the course never assigns,
    # and names at least one - and the count of the rest is reported, not verified.
    for facts in chosen:
        unassigned = sorted(facts.depends - planned)
        if not unassigned:
            continue
        step = next((m for m in course.milestones if milestone_path(m) == facts.path), None)
        why = step.why if step else ""
        for dep in unassigned:
            provider = by_module.get(dep)
            why_missing = ("not in the snapshot" if provider is None else "unparsable"
                           if provider.unparsable else "nothing gradeable"
                           if not provider.public_names else "dropped by the budget")
            result.gaps.append(f"{facts.path} -> {dep} ({why_missing})")
        if "no step here asks you to write" not in why:
            result.undisclosed.append(f"{facts.path} -> {len(unassigned)} unassigned "
                                      f"imports, none mentioned: {why[:70]}")
        elif not any(dep in why for dep in unassigned):
            result.undisclosed.append(f"{facts.path} says it has unassigned imports but "
                                      f"names none of {unassigned}")

    # -- workspace: what is already satisfied before the learner types anything? --
    seeded = {f.path for f in course.workspace_files}
    passed_at_start = 0
    for milestone in course.milestones:
        path_here = milestone_path(milestone)
        if not path_here:
            continue
        result.workspace["steps"] += 1
        result.workspace["nested"] += "/" in path_here
        result.workspace["preseeded"] += path_here in seeded
        ok, results, *_ = asyncio.run(
            evaluate_milestone(None, course, milestone, list(course.workspace_files)))
        result.workspace["free steps"] += ok
        passed_at_start += sum(1 for r in results if r.passed)
        result.workspace["checks"] += len(results)
    result.workspace["checks free at the start"] = passed_at_start
    result.workspace["entry seeded"] = course.entry_file in seeded

    # -- artifact: does the demanded name get used by the file that depends on it? --
    for facts in chosen:
        used = code_names(source.get(facts.path, ""))
        for dep in sorted(facts.depends & planned):
            producer = next(f for f in chosen if f.module == dep)
            step = next((m for m in course.milestones
                         if milestone_path(m) == producer.path), None)
            if step is None:
                continue
            demanded = {c.target for c in step.checks if c.kind == "symbol_in_file"}
            result.artifact["edges"] += 1
            result.artifact["edges whose demanded name is used"] += bool(demanded & used)

    # -- stubs: can empty definitions carry the whole course? --
    stubs = []
    for milestone in course.milestones:
        path_here = milestone_path(milestone)
        if not path_here:
            continue
        body = [f"# stub for {path_here}"]
        for check in milestone.checks:
            if check.kind != "symbol_in_file" or check.path != path_here:
                continue
            if check.target[:1].isupper():
                body.append(f"class {check.target}:\n    pass")
            else:
                body.append(f"def {check.target}(*args, **kwargs):\n    return None")
        stubs.append(WorkspaceFile(path=path_here, content="\n".join(body) + "\n"))
    for milestone in course.milestones:
        kinds = {c.kind for c in milestone.checks}
        if "run_ok" in kinds:
            if executor is None:
                result.stubs["run_ok untested (needs --sandbox)"] += 1
                continue
            ok, *_ = asyncio.run(evaluate_milestone(executor, course, milestone, stubs))
            result.stubs["run_ok passed on stubs" if ok else "run_ok rejected stubs"] += 1
            continue
        ok, *_ = asyncio.run(evaluate_milestone(None, course, milestone, stubs))
        result.stubs["stub-total"] += 1
        result.stubs["stub-pass"] += ok
    result.stubs["bytes of stubs"] = sum(len(f.content) for f in stubs)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repos", nargs="*", type=Path,
                        help="local checkouts to measure (default: this repository's backend/)")
    parser.add_argument("--sandbox", action="store_true",
                        help="run the stub program through the Docker grader")
    args = parser.parse_args(argv)
    repos = args.repos or [_ROOT / "backend"]

    executor = None
    if args.sandbox:
        from .sandbox import sandbox as executor  # noqa: N813

    results = []
    for repo in repos:
        try:
            results.append(measure_one(repo, executor))
        except Exception as exc:  # noqa: BLE001 - one repository must not stop the sweep
            failure = Result(name=str(repo), refusal=f"MEASUREMENT CRASH "
                                                     f"{type(exc).__name__}: {exc}")
            results.append(failure)
            raise

    print(f"{'repository':<26} {'steps':>5} {'checks':>6} {'free@0':>6} {'gaps':>5} "
          f"{'undisc':>6} {'stubs':>7} {'run on stubs':>12} {'edges':>5} {'name used':>9}  "
          f"claims (true/total)")
    print("-" * 134)
    for r in results:
        if r.course is None:
            print(f"{r.name:<26} NOT PLANNED: {r.refusal}")
            continue
        claim = " ".join(f"{b}={r.claims[f'{b}-true']}/{r.claims[b]}"
                         for b, _ in CLAIMS if r.claims[b])
        run_on_stubs = (r.stubs["run_ok passed on stubs"]
                        or r.stubs["run_ok rejected stubs"] or "-")
        print(f"{r.name:<26} {r.workspace['steps']:>5} {r.workspace['checks']:>6} "
              f"{r.workspace['checks free at the start']:>6} {len(r.gaps):>5} "
              f"{len(r.undisclosed):>6} {r.stubs['stub-pass']:>3}/{r.stubs['stub-total']:<3} "
              f"{run_on_stubs:>12} {r.artifact['edges']:>5} "
              f"{r.artifact['edges whose demanded name is used']:>9}  {claim}")
        for line in r.gaps[:4]:
            print(f"{'':<26}   gap: {line}")
        if len(r.gaps) > 4:
            print(f"{'':<26}   ... and {len(r.gaps) - 4} more")
        for line in r.bad_claims[:4]:
            print(f"{'':<26}   FALSE CLAIM: {line}")
        for line in r.undisclosed[:4]:
            print(f"{'':<26}   UNDISCLOSED: {line}")

    broken = [f"{r.name}: {line}" for r in results for line in r.bad_claims]
    broken += [f"{r.name}: {line}" for r in results for line in r.undisclosed]
    print("\ninvariants:")
    print("  every causal sentence true of the graph, every unassigned import disclosed")
    if broken:
        for line in broken:
            print(f"  BROKEN  {line}")
    else:
        print("  OK")
    ran = sum(r.stubs["run_ok passed on stubs"] for r in results)
    blocked = sum(r.stubs["run_ok rejected stubs"] for r in results)
    untested = sum(r.stubs["run_ok untested (needs --sandbox)"] for r in results)
    print("\nnot an invariant, and the reason this file exists: the closing `run_ok` is")
    print(f"evaluated here on its own, so it accepted the stub workspace {ran} times")
    print(f"(rejected {blocked}, untested {untested} - rerun with --sandbox to include the")
    print("grader). That step still proves only that the entry file ran; what a stub no")
    print("longer gets past is the wiring each earlier step now demands, which is the")
    print("column above it. See `audit/corpus_integrity.py` for the completion verdict.")
    shutil.rmtree(_RUN, ignore_errors=True)
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
