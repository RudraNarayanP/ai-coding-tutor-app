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
from pathlib import Path

import pytest

from backend import github_fetch as gh, repo_planner as rp
from backend.project_models import WorkspaceFile
from backend.project_planner import ProjectGroundingError, plan_project
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
    kinds = {check.kind for m in real_course.milestones for check in m.checks}
    assert kinds <= {"symbol", "file_exists", "run_ok"}, kinds
    assert real_course.milestones[-1].checks[0].kind == "run_ok"


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
