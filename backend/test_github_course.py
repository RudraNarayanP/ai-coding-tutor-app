"""Tests for building a guided course out of a GitHub repository.

All of it runs offline, and the material is real: `backend/` of this repository is a
package of ~76 modules with a genuine import graph, so the ordering and decidability
assertions measure a program nobody wrote for the test suite. That is the same choice
`composition_measurement` made, for the same reason — somebody else's source code does
not have to live in this repo to prove the planner can read one.

The rule under test, from `audit/ghbench_spike.py`: a repository's *history* is not an
outline (the earliest commits of karpathy/micrograd are "haha" and "explain bit more"),
its dependency graph is.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

from backend import github_fetch as gh, repo_planner as rp
from backend.project_models import (
    Milestone,
    MilestoneProgress,
    ProjectCourse,
    WorkspaceFile,
)
from backend.project_planner import ProjectGroundingError, plan_project, validate_project
from backend.project_service import require_usable_project
from backend.project_verifier import evaluate_milestone
from backend.source_ingestion import IngestionError, SourceDocument, SourceIngestionService

BACKEND = Path(__file__).resolve().parent


def local_snapshot() -> gh.RepoSnapshot:
    """This repository's own backend package, read as if it had been fetched."""
    snapshot = gh.open_local_repo(BACKEND)
    snapshot.license = "MIT"        # a local directory has no SPDX id; not what is tested
    return snapshot


def repo_doc(snapshot: gh.RepoSnapshot) -> SourceDocument:
    return SourceDocument(
        source_type="github_repo", source_url=f"https://github.com/{snapshot.full_name}",
        source_hash=snapshot.full_name, title=snapshot.full_name,
        plain_text=snapshot.readme[:4000], access_level="full", repo=snapshot,
    )


def course_of(snapshot: gh.RepoSnapshot):
    return plan_project(repo_doc(snapshot), title="", course_id="test-repo")


def plan(files: list[tuple[str, str]]) -> list[rp.ModuleFacts]:
    return rp.dependency_order([f for f in rp.analyze(files) if not f.unparsable and f.public_names])


# ─── what counts as a source at all ──────────────────────────────────────────

@pytest.mark.parametrize("url,expected", [
    ("https://github.com/karpathy/micrograd", ("karpathy", "micrograd", "")),
    ("http://www.github.com/a/b/", ("a", "b", "")),
    ("git@github.com:owner/repo.git", ("owner", "repo", "")),
    ("karpathy/nanoGPT", ("karpathy", "nanoGPT", "")),
    ("https://github.com/pallets/flask/tree/stable", ("pallets", "flask", "stable")),
])
def test_a_repository_is_addressable_several_ways(url: str, expected: tuple) -> None:
    assert gh.parse_repo_url(url) == expected


@pytest.mark.parametrize("url", [
    "https://github.com/karpathy/micrograd/blob/master/micrograd/engine.py",
    "https://github.com/pallets/flask/pull/1",
    "https://gitlab.com/owner/repo",
    "https://www.youtube.com/watch?v=kCc8FmEb1nY",
    "",
])
def test_a_file_a_pr_or_a_different_site_is_not_a_repository(url: str) -> None:
    with pytest.raises(gh.RepoFetchError):
        gh.parse_repo_url(url)


@pytest.mark.parametrize("spdx", ["MIT", "Apache-2.0", "BSD-3-Clause", "GPL-3.0", "AGPL-3.0"])
def test_a_named_license_is_enough(spdx: str) -> None:
    """Copyleft is not a refusal, because a course carries no code from the repository."""
    assert gh.license_problem(spdx) == ""


@pytest.mark.parametrize("spdx", ["", "NOASSERTION", "other", None])
def test_a_repository_that_granted_nothing_is_refused(spdx: str | None) -> None:
    problem = gh.license_problem(spdx or "")
    assert problem and "no license" in problem


@pytest.mark.parametrize("path,ok", [
    ("micrograd/engine.py", True),
    ("src/flask/sansio/app.py", True),
    ("tests/test_engine.py", False),

    ("docs/conf.py", False),
    ("setup.py", False),
    ("conftest.py", False),
    ("notebook.ipynb", False),
    ("demo.py", True),
])
def test_which_files_are_lessons(path: str, ok: bool) -> None:
    """The round-6 lesson, applied to a file list: a test of somebody else's code is not
    something to build, and neither is packaging."""
    assert gh.is_curriculum_file(path) is ok


def test_an_unlicensed_repo_never_reaches_the_planner() -> None:
    snapshot = local_snapshot()
    snapshot.license = ""
    with pytest.raises(ProjectGroundingError, match="no license"):
        course_of(snapshot)


# ─── the graph ───────────────────────────────────────────────────────────────

def test_the_same_module_spelled_three_ways_is_one_module() -> None:
    modules = {"micrograd.engine", "micrograd.nn"}
    assert rp.resolves("micrograd.engine", modules) == {"micrograd.engine"}
    assert rp.resolves("micrograd.engine.Value", modules) == {"micrograd.engine"}
    assert rp.resolves("engine", modules) == {"micrograd.engine"}


def test_an_import_that_could_mean_two_files_means_neither() -> None:
    """A wrong edge orders the course wrongly; a missing one only costs a tie-break."""
    ordered = plan([
        ("app/utils.py", "def helper():\n    return 1\n"),
        ("lib/utils.py", "def helper():\n    return 2\n"),
        ("app/main.py", "from utils import helper\ndef run():\n    return helper()\n"),
    ])
    by_path = {f.path: f for f in ordered}
    assert by_path["app/main.py"].depends == set()
    assert "utils" in by_path["app/main.py"].external


def test_a_chain_is_ordered_and_its_entry_is_the_tip() -> None:
    ordered = plan([
        ("pkg/value.py", "class Value:\n    pass\n"),
        ("pkg/net.py", "from pkg.value import Value\nclass Neuron:\n    pass\n"),
        ("pkg/train.py", "from pkg.net import Neuron\ndef fit():\n    return Neuron()\n"),
        ("pkg/notes.txt", "not python"),
    ])
    assert [f.path for f in ordered] == ["pkg/value.py", "pkg/net.py", "pkg/train.py"]
    chain = rp.build_chain(ordered)
    assert rp.entry_point(ordered).path == "pkg/train.py"
    assert [f.path for f in chain] == ["pkg/value.py", "pkg/net.py", "pkg/train.py"]


def test_a_cycle_does_not_stop_the_order_and_says_so() -> None:
    ordered = plan([
        ("p/a.py", "from p.b import B\nclass A:\n    pass\n"),
        ("p/b.py", "from p.a import A\nclass B:\n    pass\n"),
    ])
    assert [f.path for f in ordered] == ["p/a.py", "p/b.py"]      # both are released,
    assert ordered[0].depends                                     # the order is a judgement


# ─── what the course is allowed to say about the graph ───────────────────────
#
# `plan_repository` tells the learner why each file comes where it does, and until now
# those sentences were generated by a branch order nobody had checked against the graph.
# Measured with `audit/chain_coherence.py` over 13 real repositories, 15 of the 86 causal
# sentences contradicted the repository they described. Each rule below is the smallest
# thing that makes one of those sentences true.

def _course_files(course) -> dict[str, str]:
    """The path each step is about, from the check that scopes it."""
    return {m.id: next((c.target for c in m.checks if c.kind == "file_exists"), "")
            for m in course.milestones}


def _undisclosed_dependencies(course, snapshot) -> list[str]:
    """Steps that import a file this course never asks for and never mention it.

    A dependency the milestone budget could not fit is a real limit of an eight-step
    course, and saying so is enough to make the step honest. Saying nothing is not: the
    learner is left with an import that cannot resolve and no step that explains it. It
    cannot list all of them - past `project_copy.MAX_WHY` the whole sentence is replaced
    by generic copy - so the promise checked here is that the step says it and names one.
    """
    facts = {f.module: f for f in rp.analyze([(f.path, f.content) for f in snapshot.files])}
    planned = {rp.module_of(p) for p in _course_files(course).values() if p}
    bad: list[str] = []
    for milestone in course.milestones:
        path = _course_files(course)[milestone.id]
        here = facts.get(rp.module_of(path)) if path else None
        if here is None:
            continue
        unassigned = sorted(here.depends - planned)
        if not unassigned:
            continue
        if "no step here asks you to write" not in milestone.why:
            bad.append(f"{path} imports {len(unassigned)} unassigned module(s) and says "
                       f"nothing about it: {milestone.why[:80]}")
        elif not any(dep in milestone.why for dep in unassigned):
            bad.append(f"{path} mentions unassigned imports but names none of {unassigned}")
    return bad


def test_a_dependency_no_step_provides_is_named_by_the_step_that_needs_it() -> None:
    """`flask/config.py` imports `flask/typing.py`, which holds only aliases.

    Nothing in the course asks for that file, and the step said so in one of two wrong
    ways: it either named the file's place in the graph and stayed silent about the import
    that cannot resolve - this synthetic case, where the old sentence was about `app.py` -
    or it reached the cycle branch and called the pair mutual, which is what
    `pallets/flask`'s real `config.py` did with `typing`. Both told the learner something
    the repository contradicts or nothing at all. The true thing is the fourth: this file
    imports a module no step assigns.
    """
    snapshot = gh.RepoSnapshot(owner="p", repo="q", ref="main", license="MIT", files=[
        gh.RepoFile(path="pkg/typing.py", content="FromAnyImportSyntax = object\n"),
        gh.RepoFile(path="pkg/config.py",
                    content="from pkg.typing import FromAnyImportSyntax\n\n\n"
                            "class Config:\n    pass\n"),
        gh.RepoFile(path="pkg/app.py",
                    content="from pkg.config import Config\n\n\ndef run():\n    return Config()\n"),
    ])
    course = course_of(snapshot)
    step = next(m for m in course.milestones if m.title.endswith("pkg/config.py"))
    assert "import cycle" not in step.why, step.why        # typing imports nothing back
    assert "pkg.typing" in step.why, step.why              # ... and so it is named instead
    assert "no step here asks you to write" in step.why


def test_a_real_cycle_is_still_called_a_cycle() -> None:
    """The other direction, because a check that can only fail proves nothing.

    Twelve files in one ring, and a budget of eight milestones that cannot fit the ring:
    exactly the shape pallets/flask has (a 17-file core), produced by the truncation
    `build_chain` documents. The file the budget drops in front of the tip is a real cycle
    partner, so this is the case the sentence exists for.
    """
    ring = []
    for i in range(12):
        previous = (i - 1) % 12          # m0 imports m11, so the twelve are one cycle
        ring.append(gh.RepoFile(
            path=f"ring/m{i}.py",
            content=(f"from ring.m{previous} import M{previous}\n\n\n"
                     f"class M{i}:\n    pass\n")))
    course = course_of(gh.RepoSnapshot(owner="p", repo="q", ref="main", license="MIT",
                                      files=ring))
    assert any("import cycle" in m.why for m in course.milestones), [m.why for m in course.milestones]


def test_a_cycle_reaching_through_the_project_counts_as_a_cycle() -> None:
    """`a` and `c` never name each other, and are still one cycle through `b`.

    The sentence has to be true of the graph rather than of one edge: flask's core is 17
    files that import each other through each other, and no pair in it has a direct edge.
    """
    assert rp.reaches("p.c", "p.a", {
        "p.a": rp.ModuleFacts(path="a", module="p.a", package="p", depends={"p.b"}),
        "p.b": rp.ModuleFacts(path="b", module="p.b", package="p", depends={"p.c"}),
        "p.c": rp.ModuleFacts(path="c", module="p.c", package="p", depends={"p.a"}),
    })
    assert not rp.reaches("p.b", "p.z", {
        "p.b": rp.ModuleFacts(path="b", module="p.b", package="p", depends={"p.c"}),
        "p.c": rp.ModuleFacts(path="c", module="p.c", package="p", depends=set()),
    })


def test_a_consumer_built_earlier_is_not_cited_as_a_reason() -> None:
    """`consumers_of` decides a sentence reading "before they can be built".

    Inside a cycle the release order can put a consumer first, and then that sentence
    tells the learner to wait for a file they have already written - which 8 of the 59
    milestones that used it did.
    """
    ordered = plan([
        ("p/a.py", "from p.b import B\nclass A:\n    pass\n"),
        ("p/b.py", "from p.a import A\nimport p.a\nclass B:\n    pass\n"),
    ])
    for module in ("p.a", "p.b"):
        home = next(i for i, f in enumerate(ordered) if f.module == module)
        later = rp.consumers_of(ordered, module)
        assert all(ordered.index(next(f for f in ordered if f.path == path)) > home
                   for path in later), (module, later)


def test_the_run_step_asks_for_the_imports_that_make_it_a_test() -> None:
    """`run_ok` runs the entry file, and an entry file that imports nothing runs fine.

    Measured: a course of empty stubs at the demanded paths passed every milestone of all
    13 repositories, the closing one included. The grader cannot be made to see this
    without a new kind of check, so what changed is what the learner is told to do - the
    one spelling that survives the runner, since `runpy.run_path` has no package for a
    leading dot to resolve against.
    """
    course = course_of(local_snapshot())
    run = course.milestones[-1]
    assert run.checks[0].kind == "run_ok"
    assert "import" in run.microstep.action.lower(), run.microstep.action
    assert "from ." in run.microstep.hint or "relative" in run.microstep.hint.lower()
    assert "cannot be skipped" not in run.why          # the claim the measurement refuted


def test_a_real_backend_course_leaves_no_dependency_unmentioned() -> None:
    """The failure, asserted on 80 modules of code nobody wrote for this test."""
    snapshot = local_snapshot()
    course = course_of(snapshot)
    assert not _undisclosed_dependencies(course, snapshot)


def test_the_projection_still_carries_what_the_planner_wrote() -> None:
    """Copy that only exists in the stored document is copy nobody reads.

    `polish_project_copy` re-mints any field longer than `project_copy.MAX_*`, and it is
    what replaced the run step's import guidance with a generic line the first time. The
    repo route's grounded sentences are the fix, so the screen is where they have to be.
    """
    from backend.project_service import to_learner_view

    view = to_learner_view(course_of(local_snapshot()))
    assert any("no step here asks you to write" in m.why for m in view.milestones), \
        [m.why for m in view.milestones]
    run = next(m for m in view.milestones if m.title.startswith("Run "))
    assert "import" in run.microstep.action.lower()
    assert "`from ." in run.microstep.hint


def test_unparsable_and_test_shaped_files_never_become_milestones() -> None:
    facts = rp.analyze([
        ("t/legacy.py", "print 'python two'\n"),
        ("t/test_engine.py", "def test_value():\n    assert 1\n"),
        ("t/engine.py", "class Value:\n    pass\n"),
    ])
    assert [f for f in facts if f.unparsable][0].path == "t/legacy.py"
    assert rp.dependency_order([f for f in facts if not f.unparsable and f.public_names]) == \
        [f for f in facts if f.path == "t/engine.py"]
    assert [n for n in facts[1].public_names] == []               # test_value is scaffolding


def test_a_repository_of_independent_scripts_is_refused() -> None:
    """No chain, no course — this is the honest limit, not a threshold to tune."""
    snapshot = gh.RepoSnapshot(owner="a", repo="b", ref="main", license="MIT", files=[
        gh.RepoFile(path=f"s{i}.py", content=f"def f{i}():\n    return {i}\n") for i in range(6)
    ])
    with pytest.raises(ProjectGroundingError, match="chain"):
        course_of(snapshot)


# ─── the course, on real code ────────────────────────────────────────────────

@pytest.fixture(scope="module")
def real_course():
    return course_of(local_snapshot())


def test_the_real_package_plans_and_survives_load(real_course) -> None:
    assert 2 < len(real_course.milestones) <= 9
    assert real_course.source_type == "github_repo"
    require_usable_project(real_course)                  # the same rule the Resume list applies
    validate_project(real_course)                        # the rule only creation applies
    kinds = {check.kind for m in real_course.milestones for check in m.checks}
    assert kinds <= {"symbol_in_file", "file_exists", "import", "run_ok"}, kinds
    assert real_course.milestones[-1].checks[0].kind == "run_ok"


def test_a_step_that_says_what_it_imports_also_checks_it(real_course) -> None:
    """The sentence and the check have to be the same claim.

    Every repository milestone already told the learner "these files exist, so this one
    can import them" while nothing verified that it did - so a course of `class Value:
    pass` files satisfied all 86 structural steps across 13 real repositories, ran
    cleanly, and paid full XP. Any step whose own `why` names an already-built
    dependency now demands it as an import in that file.
    """
    wired = [m for m in real_course.milestones
             if "which you have already written" in m.why and m.checks]
    assert wired, "the real package has no step that imports an earlier one"
    for milestone in wired:
        demanded = {c.target for c in milestone.checks
                    if c.kind == "import" and c.path == milestone.checks[0].path}
        sentence = next(s for s in re.split(r"(?<=\.)\s+", milestone.why)
                        if "which you have already written" in s)
        named = {t for t in re.findall(r"`([^`]+)`", sentence)
                 if t != milestone.checks[0].path}
        assert demanded and named <= demanded, (milestone.title, named, demanded)
    first = wired[0]
    path = first.checks[0].path
    body = next(f.content for f in local_snapshot().files if f.path == path)
    bare = [WorkspaceFile(path=path, content="\n".join(
        f"class {c.target}:\n    pass" if c.target[:1].isupper()
        else f"def {c.target}(*a, **k):\n    return None"
        for c in first.checks if c.kind == "symbol_in_file") + "\n")]
    assert asyncio.run(evaluate_milestone(None, real_course, first, bare))[0] is False
    assert asyncio.run(evaluate_milestone(
        None, real_course, first, [WorkspaceFile(path=path, content=body)]))[0] is True


def test_a_repository_check_names_the_file_it_scopes_to(real_course) -> None:
    """Every scoped check must carry its path, or it silently stops being scoped."""
    for milestone in real_course.milestones:
        path = next((c.target for c in milestone.checks if c.kind == "file_exists"), "")
        for check in milestone.checks:
            if check.kind == "symbol_in_file":
                assert check.path == path, f"{milestone.title}: {check.path} != {path}"


def test_the_wrong_file_does_not_earn_a_milestone(real_course) -> None:
    """The whole point of scoping, on real code: `Value` in the wrong file is a miss.

    The wrong-file workspace still contains the *required file* (empty), so the only
    thing failing is the scoping itself — otherwise `file_exists` would fail alongside
    and the test would pass for the wrong reason. Asserted in both directions because
    a check that can only fail proves nothing.
    """
    milestone = next(m for m in real_course.milestones
                     if m.checks[0].kind == "symbol_in_file"
                     and m.checks[0].path != real_course.entry_file)
    scoped = [c for c in milestone.checks if c.kind == "symbol_in_file"]
    home = scoped[0].path
    body = "".join(f"class {c.target}:\n    pass\n" for c in scoped)
    elsewhere = [WorkspaceFile(path=home, content="# not written yet\n"),
                 WorkspaceFile(path=real_course.entry_file, content=body)]
    in_place = [WorkspaceFile(path=home, content=body)]
    assert asyncio.run(evaluate_milestone(None, real_course, milestone, elsewhere))[0] is False
    assert asyncio.run(evaluate_milestone(None, real_course, milestone, in_place))[0] is True


def test_every_milestone_is_decidable_on_the_real_file_and_not_on_the_starter(
        real_course) -> None:
    """A check that cannot tell the repository's own file from the empty workspace is
    not a check — the standard every derivation rule in this project is held to."""
    real = {f.path: f.content for f in local_snapshot().files}
    starter = list(real_course.workspace_files)
    decided = 0
    for milestone in real_course.milestones:
        path = next((c.target for c in milestone.checks if c.kind == "file_exists"), "")
        if not path or path not in real:
            continue
        passed, *_ = asyncio.run(evaluate_milestone(
            None, real_course, milestone, [WorkspaceFile(path=path, content=real[path])]))
        bare, *_ = asyncio.run(evaluate_milestone(None, real_course, milestone, starter))
        assert passed, f"{milestone.title}: the real {path} does not satisfy its own check"
        assert not bare, f"{milestone.title}: the starter already satisfies it"
        decided += 1
    assert decided >= 2, "nothing was decided; the test would pass on an empty course"


def test_the_workspace_holds_no_line_of_the_repository(real_course) -> None:
    """The licensing rule, enforced where it matters: what the learner is handed."""
    snapshot = local_snapshot()
    body_lines = {
        line.strip() for f in snapshot.files for line in f.content.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    for file in real_course.workspace_files:
        assert [line for line in file.content.splitlines()
                if line.strip() and not line.startswith("#")] == []
        assert not {line.strip() for line in file.content.splitlines()} & body_lines
    # The manifest the enricher reads names the files, and no milestone asks for a file
    # the course never told the learner about.
    for milestone in real_course.milestones:
        path = next((c.target for c in milestone.checks if c.kind == "file_exists"), "")
        if path:
            assert path in real_course.source_excerpt


def test_the_prose_gate_is_never_asked_about_a_repository(monkeypatch) -> None:
    """`plan_project` dispatches on the source kind; a repo is judged by repo rules.

    Not a convenience: `evaluate_source` refuses what lacks tutorial language, so every
    repository would be refused *correctly* by it. The dispatch is only safe because
    `plan_repository` gates the license and the chain itself, which the two refusal
    tests above cover.
    """
    def never(*_args, **_kwargs):
        raise AssertionError("the prose gate ran on a repository source")

    monkeypatch.setattr("backend.project_planner.evaluate_source", never)
    course_of(local_snapshot())


@pytest.fixture(autouse=True)
def _no_llm_in_the_http_tests(monkeypatch, request) -> None:
    """The create endpoint enriches through whatever provider `.env` names.

    A test suite that spends paid requests on every run is neither deterministic nor
    free, and enrichment is not what these tests are about - it is best-effort copy
    layered on a course whose checks are already decided. So the provider is removed for
    every test here, which is also the honest way to assert a payload contains nothing:
    no model has been handed the repository to paraphrase.
    """
    if "monkeypatch" not in request.fixturenames:
        return
    import backend.main as main_module

    monkeypatch.setattr(main_module, "get_current_provider", lambda: None)


def test_the_endpoint_builds_a_course_from_a_repo_url(monkeypatch) -> None:
    """POST the way the Create page will, and get a course back.

    The endpoint needs no change for this feature: `material_type` is a string it passes
    through, and the whole difference lives behind `SourceIngestionService.ingest`. That
    is worth pinning, because the alternative — a second endpoint — would have forked the
    four quality gates every other source has to pass.
    """
    from fastapi.testclient import TestClient

    import backend.main as main_module

    async def fake(url: str) -> gh.RepoSnapshot:
        return local_snapshot()

    monkeypatch.setattr("backend.source_ingestion.fetch_repo", fake)
    client = TestClient(main_module.app)
    res = client.post(
        "/api/create-course/projects",
        json={"material_type": "github_url",
              "content": "https://github.com/karpathy/micrograd", "title": ""},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["course_id"].startswith("project-")
    assert len(data["milestones"]) >= 3
    assert all(m["title"].startswith(("Build ", "Run ")) for m in data["milestones"])
    assert any("`" in m["microstep"]["action"] for m in data["milestones"])
    # The view carries no `checks`: the learner is told what to write in prose, never
    # what the grader matches on. A repo course makes that sharper than a tutorial does
    # — `symbol Value` printed in the milestone list would be the whole answer key.
    assert not any("checks" in m for m in data["milestones"])


def test_a_non_github_url_is_a_clear_400() -> None:
    from fastapi.testclient import TestClient

    import backend.main as main_module

    client = TestClient(main_module.app)
    res = client.post(
        "/api/create-course/projects",
        json={"material_type": "github_url", "content": "https://example.com/docs", "title": ""},
    )
    assert res.status_code == 400
    assert "repository" in res.json()["detail"]["message"]


def test_a_fetch_failure_becomes_an_ingestion_error(monkeypatch) -> None:
    """Patched on `source_ingestion`'s own name.

    Patching `github_fetch.fetch_repo` leaves this suite talking to GitHub: the module
    did `from ... import fetch_repo`, so it holds its own binding, and the first draft
    of this test "passed" on a real 404 for a repository that does not exist.
    """
    async def refuse(url: str) -> gh.RepoSnapshot:
        raise gh.RepoFetchError("github.com/a/b is not public (or does not exist).")

    monkeypatch.setattr("backend.source_ingestion.fetch_repo", refuse)
    with pytest.raises(IngestionError, match="not public"):
        asyncio.run(SourceIngestionService().ingest(
            material_type="github_url", content="https://github.com/a/b", title=""))


def test_a_repo_with_nothing_to_build_is_an_ingestion_error(monkeypatch) -> None:
    async def thin(url: str) -> gh.RepoSnapshot:
        return gh.RepoSnapshot(owner="a", repo="b", ref="main", license="MIT",
                              files=[gh.RepoFile(path="one.py", content="X = 1\n")])

    monkeypatch.setattr("backend.source_ingestion.fetch_repo", thin)
    with pytest.raises(IngestionError, match="Python module"):
        asyncio.run(SourceIngestionService().ingest(
            material_type="github_url", content="https://github.com/a/b", title=""))


# ─── where the python lives decides whether it is the project ────────────────
#
# Measured on 11 real repositories, the only repeatable wrong-centre was a tooling
# directory: karpathy/llm.c is a C project whose `dev/data/*.py` download scripts
# chained well enough to become a whole course. Language share and GitHub's own
# metadata cannot be used instead — llm.c is 13.5% Python by bytes and micrograd, the
# repository this feature was built around, is 9.7%, and GitHub calls micrograd's
# primary language "Jupyter Notebook". So the rule is about location, and these two
# tests hold it to that with identical code in two places.

_COMMON = "def load(name):\n    return {'name': name}\n"
_RUN = "from {pkg}.common import load\n\n\ndef main():\n    return load('gpt2')\n"


def _snapshot_with(prefix: str) -> gh.RepoSnapshot:
    """Run the real fetch-time filter over two modules placed at `prefix`."""
    return gh.snapshot_from_files(
        "root",
        [(f"{prefix}/common.py", _COMMON.encode()),
         (f"{prefix}/run.py", _RUN.format(pkg=prefix.replace("/", ".")).encode())],
        owner="karpathy", repo="llm.c", ref="master", license="MIT",
    )


def test_the_same_two_modules_are_a_course_outside_dev_and_nothing_inside_it() -> None:
    """Identical code, two locations, opposite outcomes.

    The filter is applied while the repository is being read, so this asserts on the
    snapshot the fetch produces — which is what the planner is then handed.
    """
    inside = _snapshot_with("dev/data")
    assert [f.path for f in inside.files] == []
    with pytest.raises(ProjectGroundingError, match="chain|module"):
        plan_project(repo_doc(inside), title="", course_id="dev-centre")

    outside = _snapshot_with("llmtrain")
    assert len(outside.files) == 2
    course = plan_project(repo_doc(outside), title="", course_id="pkg-centre")
    names = [c.target for m in course.milestones for c in m.checks if c.kind == "symbol_in_file"]
    assert "load" in names and "main" in names


def test_a_dev_directory_is_excluded_for_every_language_not_just_python() -> None:
    """The list this rule joins is about what a directory is for, not what it holds."""
    assert gh.is_curriculum_file("dev/data/fineweb.py") is False
    assert gh.is_curriculum_file("dev/cuda/benchmark_on_modal.py") is False
    assert gh.is_curriculum_file("dev/kernels.c") is False        # never a lesson anyway
    assert gh.is_curriculum_file("dev/tooling/run.rs") is False
    assert gh.is_curriculum_file("src/devstore/engine.py") is True  # a name, not a dir


# The 13 modules llm.c really offers, copied as paths (no source), so the regression
# that motivated the rule stays pinned without a network call.
LLM_C_MODULES = [
    "dev/cuda/benchmark_on_modal.py", "dev/data/data_common.py", "dev/data/fineweb.py",
    "dev/data/hellaswag.py", "dev/data/mmlu.py", "dev/data/tinyshakespeare.py",
    "dev/data/tinystories.py", "dev/eval/export_hf.py", "dev/eval/summarize_eval.py",
    "dev/loss_checker_ci.py", "profile_gpt2cu.py", "train_gpt2.py", "train_llama3.py",
]


def test_llm_c_offers_no_chainable_project_once_its_tooling_directory_is_excluded() -> None:
    kept = [p for p in LLM_C_MODULES if gh.is_curriculum_file(p)]
    assert kept == ["profile_gpt2cu.py", "train_gpt2.py", "train_llama3.py"]
    # Those three are standalone entry scripts: no module here imports another, so the
    # chain rule that already existed is what refuses the repository.
    ordered = rp.dependency_order([f for f in rp.analyze([(p, _RUN.format(pkg="x")) for p in kept])
                                   if not f.unparsable and f.public_names])
    assert len(rp.build_chain(ordered, limit=8)) < 2


def test_the_pipeline_is_python_only_because_that_is_what_the_grader_can_read() -> None:
    """Stated as a test so the boundary is never mistaken for a preference.

    `symbol_in_file` parses Python; there is no C, Rust or Go checker in this app, which
    is why a repository's non-Python core is not "rejected" but simply not analysable.
    Adding another ecosystem means adding a verifier for it, not editing this filter.
    """
    assert gh.is_curriculum_file("main.c") is False
    assert gh.is_curriculum_file("src/lib.rs") is False
    assert gh.is_curriculum_file("cmd/main.go") is False
    assert gh.is_curriculum_file("src/index.ts") is False
    assert rp.resolves("micrograd.engine", {"micrograd.engine"}) == {"micrograd.engine"}


# ─── what finishing a repository course is evidence of ───────────────────────
#
# The chain was ordered, every name was real, and none of it asked whether the files
# worked together or did anything. Measured over 13 real repositories: a workspace of
# `class Value: pass` files satisfied all 86 structural milestones, ran cleanly, and was
# awarded `project_complete` at full XP - and a micrograd re-implementation whose `__add__`
# subtracts instead of adds was indistinguishable from the correct one.

_VALUE = """class Value:
    def __init__(self, data):
        self.data = data

    def __add__(self, other):
        return Value(self.data + (other.data if isinstance(other, Value) else other))
"""

_NET = """from app.value import Value


class Doubler:
    def __call__(self, v):
        return v + v


print(Doubler()(Value(3)).data)
"""


def _mini_package() -> gh.RepoSnapshot:
    return gh.RepoSnapshot(owner="a", repo="b", ref="main", license="MIT", files=[
        gh.RepoFile(path="app/value.py", content=_VALUE),
        gh.RepoFile(path="app/net.py", content=_NET),
    ])


def _stubs(course) -> list[WorkspaceFile]:
    """Every demanded name declared at the demanded path; nothing wired together."""
    out: list[WorkspaceFile] = []
    for milestone in course.milestones:
        path = next((c.target for c in milestone.checks if c.kind == "file_exists"), "")
        if not path:
            continue
        lines = [f"# {path}"]
        for check in milestone.checks:
            if check.kind != "symbol_in_file":
                continue
            lines.append(f"class {check.target}:\n    pass" if check.target[:1].isupper()
                         else f"def {check.target}(*args, **kwargs):\n    return None")
        out.append(WorkspaceFile(path=path, content="\n".join(lines) + "\n"))
    return out


def _finish(course, files, tmp: Path):
    from backend.project_service import evaluate_next
    from backend.project_store import ProjectStore
    from backend.sandbox import DockerSandbox

    store = ProjectStore(storage_dir=tmp)
    project = store.create(course.model_copy(deep=True))
    project = store.save_workspace(project.course_id, files) or project
    return project, asyncio.run(
        evaluate_next(store, DockerSandbox(), project, helped=False))


def test_empty_classes_alone_cannot_finish_a_repository(tmp_path) -> None:
    """The headline false positive, pinned end to end through the real gate."""
    course = course_of(_mini_package())
    assert [c.kind for c in course.milestones[-1].checks] == ["run_ok"]
    project, result = _finish(course, _stubs(course), tmp_path / "stubs")
    assert result["status"] == "incomplete"
    assert not project.completed
    assert 0 < project.xp < sum(m.xp_reward for m in course.milestones)
    assert "doesn't import" in result["feedback"]   # the wiring step is the wall


def test_the_wired_and_working_version_of_the_same_course_does_finish(tmp_path) -> None:
    """The control a stricter grader needs, or the change only moves the goalposts.

    `runpy.run_path` gives the entry file no package to resolve a leading dot against,
    so the spelling that works is the one from the project root - which is what the
    milestone's hint now tells the learner.
    """
    course = course_of(_mini_package())
    files = [WorkspaceFile(path="app/value.py", content=_VALUE),
             WorkspaceFile(path="app/net.py", content=_NET)]
    project, result = _finish(course, files, tmp_path / "real")
    assert result["status"] == "project_complete", result["feedback"]
    assert project.completed and project.xp == sum(m.xp_reward for m in course.milestones)
    assert {a["evidence"] for a in result["advanced"]} == {"structural", "executed"}
    assert "the program ran" in result["feedback"]
    assert result["summary"]["evidence_executed"] == 1


def test_a_wrong_but_wired_program_finishes_and_says_only_that_it_ran(tmp_path) -> None:
    """The boundary this change stops at, recorded rather than papered over.

    Right file, right names, wired together, `__add__` subtracting. Nothing in this app
    decides what a function returns - the only behavioural evidence a repository could
    supply is its own test suite, and `github_fetch` excludes it, correctly, because a
    course may not carry somebody else's code. So the completion sentence names what was
    seen, which is that the program ran.
    """
    wrong = _NET.replace("print(Doubler()(Value(3)).data)",
                         "print('built')")
    wrong_value = _VALUE.replace("self.data + (other.data", "self.data - (other.data")
    course = course_of(gh.RepoSnapshot(owner="a", repo="b", ref="main", license="MIT", files=[
        gh.RepoFile(path="app/value.py", content=wrong_value),
        gh.RepoFile(path="app/net.py", content=wrong),
    ]))
    files = [WorkspaceFile(path="app/value.py", content=wrong_value),
             WorkspaceFile(path="app/net.py", content=wrong)]
    project, result = _finish(course, files, tmp_path / "wrong")
    assert result["status"] == "project_complete"
    assert "the program ran" in result["feedback"]
    assert "works" not in result["feedback"]


def test_a_repository_courses_wiring_checks_survive_the_single_file_guard() -> None:
    """`_drops_unimportable_local_modules` was quietly deleting every one of them.

    That rule exists because a transcript route is one persistent `main.py`, so an
    `import ratelimit` check can never pass there. It decided what the project *had* from
    `workspace_files`, which for a repository course is the one seeded entry file - so
    each of the 75 wiring checks the corpus now carries was stripped before the course was
    ever saved. The files the course asks the learner to write are part of the project.
    """
    course = course_of(_mini_package())
    wired = [c for m in course.milestones for c in m.checks
             if c.kind == "import" and c.path == "app/net.py"]
    assert [c.target for c in wired] == ["app.value"]


# ─── the private-evidence boundary ───────────────────────────────────────────
#
# Behavioural grading was investigated and rejected on the corpus: across 13 checkouts,
# 418 upstream test files (6,455 test functions, 272 naming a module a course selects)
# cannot execute in the grading image, which is python:3.12-slim with no network -
# `pytest`, `torch`, `anyio` and `markupsafe` are simply absent, and 10 of the 12 oracle
# payloads that could be assembled at all also blow the 64 KiB transport ceiling. So there
# is no private oracle to leak. These tests pin the boundary that makes it *structurally*
# impossible rather than a policy somebody has to remember: what the fetch keeps, what the
# course stores, and what the learner's own requests can retrieve.
#
# Only the last test below is new behaviour, and it fails at b695713. The three boundary
# tests pass before and after by design - they are controls, and their job is to fail the
# day somebody starts storing the snapshot, which is the precondition for any oracle.

def test_nothing_about_the_repository_survives_into_the_saved_course(tmp_path) -> None:
    """Tests are dropped while the repository is being read, and never come back.

    The boundary is not a policy about what the planner is allowed to quote: the test
    suite is gone before the planner runs, so there is no oracle to leak and no answer
    key to stumble into. Then, separately, the saved document is checked - because
    `ProjectCourse` has no repository field at all, the file bodies are dropped with the
    snapshot and grading never sees them.
    """
    from backend.project_store import ProjectStore

    on_disk = sorted(str(p.relative_to(BACKEND)).replace("\\", "/")
                     for p in BACKEND.rglob("*.py") if "test_" in p.name)
    assert len(on_disk) > 5, on_disk          # this repository really does ship tests
    snapshot = local_snapshot()
    assert not [f.path for f in snapshot.files if "test" in f.path.split("/")[-1]]

    course = course_of(snapshot)
    store = ProjectStore(storage_dir=tmp_path)
    store.create(course)
    persisted = (tmp_path / f"{course.course_id}.json").read_text(encoding="utf-8")
    for path in on_disk:
        assert path not in persisted, path
    for milestone in course.milestones:
        for text in (milestone.source_quote, milestone.source_grounded_description,
                     milestone.teach, milestone.example, milestone.why):
            assert not any(p in text for p in on_disk), (milestone.title, text[:80])


def test_a_saved_course_holds_no_implementation_line_of_the_repository() -> None:
    """The licensing rule, checked against the document rather than the workspace.

    Declaration headers are allowed and are quoted on purpose - `class Value:` is the
    contract, not the lesson. Everything below a `:` is the project's own code, and none
    of it may appear in what a learner is served or what the enricher is prompted with.
    """
    snapshot = local_snapshot()
    course = course_of(snapshot)
    blob = json.dumps(course.model_dump(), default=str)
    bodies = {
        line.strip() for f in snapshot.files for line in f.content.splitlines()
        if len(line.strip()) > 40 and not line.strip().endswith(":")
        and not line.strip().startswith(("#", '"', "'", ">>>"))
    }
    assert bodies, "nothing substantial was collected - the test is vacuous"
    leaked = sorted(bodies & {line.strip() for line in blob.splitlines()} |
                    b for b in bodies if b in blob)
    assert not leaked, f"{len(leaked)} repository implementation lines in the course: {leaked[:2]}"


def test_the_completion_sentence_never_calls_a_run_a_behavioural_result() -> None:
    """EXECUTED must not be described as BEHAVIORALLY_VERIFIED, in either language.

    There is no behavioural state to reach today, which is the point: the sentence that
    fires when a program was observed running says that is all that was checked, because
    a wrong-but-running implementation earns exactly this feedback.
    """
    from backend.project_service import completion_feedback

    project = ProjectCourse(course_id="c", title="t", source_type="github_repo",
                            milestones=[Milestone(id="m1", order=1, title="Run")])
    project.milestone_progress["m1"] = MilestoneProgress(
        milestone_id="m1", status="completed", evidence="executed")
    said = completion_feedback(project)
    assert "the program ran" in said
    assert "behaves the same way has not been verified" in said
    assert not re.search(r"\b(correct|works|proven|verified against)\b", said.lower()
                         .replace("has not been verified", ""))


def test_no_http_response_can_carry_repository_test_source(monkeypatch) -> None:
    """The learner's own requests are the leak that matters, so they are checked here.

    Every route a project exposes - create, read, save, next, guidance - is answered with
    the persisted document, and the document holds no repository body. A test file's own
    text is used as the needle: if the snapshot ever starts being stored, or a milestone
    starts quoting an upstream test as an oracle, this fails on the wire rather than in a
    planner unit test.
    """
    from fastapi.testclient import TestClient

    import backend.main as main_module

    bodies = [
        f.content for f in gh.open_local_repo(BACKEND).files
    ]
    assert bodies
    needle_lines = {line.strip() for b in bodies for line in b.splitlines()
                    if len(line.strip()) > 60 and not line.strip().startswith(("#", '"', "'"))}

    async def refuse(url: str) -> gh.RepoSnapshot:      # no network, no LLM
        snapshot = local_snapshot()
        snapshot.license = "MIT"
        return snapshot

    monkeypatch.setattr("backend.source_ingestion.fetch_repo", refuse)
    seen = []
    real_enrich = main_module.__dict__.get("enrich_project")

    async def spy(provider, project):
        seen.append(provider)
        return await real_enrich(provider, project)

    import backend.project_service as project_service
    monkeypatch.setattr(project_service, "enrich_project", spy)
    client = TestClient(main_module.app)
    created = client.post(
        "/api/create-course/projects",
        json={"material_type": "github_url", "content": "https://github.com/a/b", "title": ""})
    assert created.status_code == 200, created.text
    course_id = created.json()["course_id"]
    responses = [created,
                 client.get(f"/api/create-course/projects/{course_id}"),
                 client.put(f"/api/create-course/projects/{course_id}/workspace",
                            json={"files": [{"path": "main.py", "content": "x = 1\n"}]}),
                 client.post(f"/api/create-course/projects/{course_id}/next",
                             json={"files": [{"path": "main.py", "content": "x = 1\n"}]}),
                 client.get("/api/create-course/projects")]
    client.delete(f"/api/create-course/projects/{course_id}")
    for response in responses:
        assert response.status_code in (200, 400, 422), response.status_code
        text = response.text
        leaked = [line for line in needle_lines if line in text]
        assert not leaked, f"{response.request.method} {response.url} leaked {leaked[:1]}"
    assert seen == [None], seen          # the guard holds: no paid provider in a test run
