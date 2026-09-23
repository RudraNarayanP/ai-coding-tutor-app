"""Fetch a public GitHub repository as a course source, or refuse it for a named reason.

Create Course's other sources arrive as prose a human wrote for a camera; a repository
arrives as the finished artifact. So this module answers a narrower question than
``youtube_fetch`` does: *can this repo ground a course at all* — public, permissively
licensed, small enough to read, Python modules that import one another — and leaves the
ordering to ``repo_planner``.

Commit messages are deliberately not read as a syllabus. Measured on four real
repositories (``audit/ghbench_spike.py``), the earliest commits of karpathy/micrograd
are ``haha``, ``explain bit more`` and ``actually include the output``, 25 of nanoGPT's
first 100 are merge commits, and the subjects that survive the chapter route's matcher
are things like ``fix typo in neuron call from back when i was debugging``. The
repository's *dependency structure* is the ordered outline; its history is not.

No file's contents are ever copied into a course. The workspace a learner is handed
contains the repository's paths and nothing else, so a course asks them to write the
program rather than to read someone else's. That is also why a missing license is a
refusal while a copyleft one is not: a course carries no derived code, but it cannot be
made at all from a repository that granted nothing.
"""
from __future__ import annotations

import io
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx

API = "https://api.github.com"
ARCHIVE_HOST = "https://codeload.github.com"
_TIMEOUT = float(os.getenv("GITHUB_FETCH_TIMEOUT", "60"))

#: An archive larger than this is not something to read into a course, and pulling it
#: would be the most expensive thing the request path does.
MAX_ARCHIVE_BYTES = 25_000_000
MAX_SOURCE_BYTES = 400_000
MAX_SOURCE_FILES = 80

#: A course built from a repository contains no lines of that repository: only paths,
#: name spellings and declaration headers. That is why copyleft is not a refusal — the
#: app distributes nothing derived from the source. A repository with *no* license is,
#: because it grants nothing at all, not even to read it into memory and describe it.
UNKNOWN_LICENSES = {"", "NOASSERTION", "OTHER", "NONE"}

_URL = re.compile(
    r"^(?:https?://(?:www\.)?github\.com/|git@github\.com:)"
    r"(?P<owner>[A-Za-z0-9._-]+)/(?P<repo>[A-Za-z0-9._-]+)"
    r"(?:\.git)?(?:/(?P<kind>tree|blob|releases)/(?P<ref>[^/?#]+)(?P<tail>[^?#]*))?"
    r"(?:[?#].*)?$"
)
_SHORT = re.compile(r"^(?P<owner>[A-Za-z0-9._-]+)/(?P<repo>[A-Za-z0-9._-]+)$")
#: Directories that hold no lesson: tests, packaging, generated output, docs.
NON_CURRICULUM = re.compile(
    r"(^|/)(tests?|docs?|doc|examples?|benchmarks?|scripts?|tools?|ci|\.github|"
    r"node_modules|venv|\.venv|site-packages|build|dist)(/|$)"
)
NON_CURRICULUM_FILES = re.compile(
    r"(^|/)(setup\.py|conftest\.py|_version\.py|versioneer\.py|conf\.py|wsgi\.py|"
    r"django\.wsgi|manage\.py|noxfile\.py|setup\.cfg|tasks\.py)$|"
    r"(^|/)test_[^/]*\.py$|(^|/)[^/]*_test\.py$"
)


class RepoFetchError(ValueError):
    """User-facing: this URL is not a course source. Same role as IngestionError."""


@dataclass
class RepoFile:
    path: str
    content: str


@dataclass
class RepoSnapshot:
    """A repository reduced to what a course can be built from."""

    owner: str
    repo: str
    ref: str
    license: str = ""
    description: str = ""
    default_branch: str = ""
    stars: int = 0
    files: list[RepoFile] = field(default_factory=list)
    readme: str = ""
    skipped: list[str] = field(default_factory=list)

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_repo_url(text: str) -> tuple[str, str, str]:
    """(owner, repo, ref-or-empty) from a watch-style repo URL, a clone URL or `o/r`.

    A ref is only honoured for `tree/<branch>`; `blob/<sha>/file.py` and
    `pull/123` are not repositories.
    """
    raw = (text or "").strip().rstrip("/")
    match = _URL.match(raw) or _SHORT.match(raw)
    if not match:
        raise RepoFetchError(
            "That is not a repository URL. Paste the address of the project itself, "
            "like https://github.com/owner/repo"
        )
    kind = match.groupdict().get("kind") or ""
    if kind == "blob" or "/pull/" in raw or "/issues/" in raw:
        raise RepoFetchError("Paste the repository itself, not a file, pull request or issue.")
    return match.group("owner"), match.group("repo").removesuffix(".git"), (
        match.group("ref") if kind == "tree" else ""
    )


def license_problem(spdx: str) -> str:
    """Why this license cannot carry a course, or "" when it can."""
    if (spdx or "").strip().upper() in UNKNOWN_LICENSES:
        return (
            "it publishes no license, so nothing about its source is granted to us — not "
            "even having the app read its structure and describe it"
        )
    return ""


def is_curriculum_file(path: str) -> bool:
    """A Python module that could plausibly be a lesson, not a test or a build script."""
    if not path.endswith(".py"):
        return False
    return not (NON_CURRICULUM.search(path) or NON_CURRICULUM_FILES.search(path))


def snapshot_from_files(root: str | Path, files: list[tuple[str, bytes]], *,
                        owner: str, repo: str, ref: str = "", license: str = "",
                        description: str = "", stars: int = 0) -> RepoSnapshot:
    """Build a snapshot from (relpath, bytes) pairs. Shared by the HTTP and local paths."""
    snapshot = RepoSnapshot(owner=owner, repo=repo, ref=ref, license=license,
                            description=description, stars=stars)
    for rel, data in files:
        path = rel.replace("\\", "/")
        if path.endswith("README.md") and not snapshot.readme:
            try:
                snapshot.readme = data.decode("utf-8", "replace")[:20_000]
            except Exception:  # noqa: BLE001 - a README we cannot read is not fatal
                pass
        if not is_curriculum_file(path):
            continue
        if len(data) > MAX_SOURCE_BYTES:
            snapshot.skipped.append(f"{path} (too large)")
            continue
        if len(snapshot.files) >= MAX_SOURCE_FILES:
            snapshot.skipped.append(f"{path} (file cap)")
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            snapshot.skipped.append(f"{path} (not utf-8)")
            continue
        snapshot.files.append(RepoFile(path=path, content=text))
    return snapshot


def _zip_entries(payload: bytes) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            # The archive nests everything under "owner-repo-sha/"; drop that level.
            parts = info.filename.split("/", 1)
            rel = parts[1] if len(parts) == 2 else info.filename
            if rel:
                out.append((rel, archive.read(info)))
    return out


async def fetch_repo(url: str, client: httpx.AsyncClient | None = None) -> RepoSnapshot:
    """Download a public repository and reduce it to a snapshot, or refuse it."""
    owner, repo, ref = parse_repo_url(url)
    owns = client is None
    client = client or httpx.AsyncClient(follow_redirects=True, timeout=_TIMEOUT)
    try:
        meta = await client.get(f"{API}/repos/{owner}/{repo}")
        if meta.status_code == 404:
            raise RepoFetchError(
                f"github.com/{owner}/{repo} is not public (or does not exist). "
                "Paste the URL of a public repository."
            )
        if meta.status_code != 200:
            raise RepoFetchError(f"GitHub returned {meta.status_code} for that repository.")
        body = meta.json()
        license_id = (body.get("license") or {}).get("spdx_id") or ""
        problem = license_problem(license_id)
        if problem:
            raise RepoFetchError(f"Can't build a course from {owner}/{repo}: {problem}.")
        branch = ref or body.get("default_branch") or "HEAD"
        if int(body.get("size") or 0) * 1024 > MAX_ARCHIVE_BYTES:
            raise RepoFetchError(
                f"{owner}/{repo} is too large to read through in one sitting "
                f"({int(body.get('size') or 0) // 1024} MB). Try a smaller project."
            )
        archive = await client.get(f"{ARCHIVE_HOST}/{owner}/{repo}/zip/{branch}")
        if archive.status_code != 200:
            raise RepoFetchError(f"Could not download {owner}/{repo} (HTTP {archive.status_code}).")
        if len(archive.content) > MAX_ARCHIVE_BYTES:
            raise RepoFetchError(f"{owner}/{repo} is too large to read through in one sitting.")
        return snapshot_from_files(
            root=f"{owner}/{repo}", files=_zip_entries(archive.content),
            owner=owner, repo=repo, ref=branch, license=license_id,
            description=body.get("description") or "",
            stars=int(body.get("stargazers_count") or 0),
        )
    finally:
        if owns:
            await client.aclose()


def open_local_repo(path: str | Path) -> RepoSnapshot:
    """Snapshot a directory on disk. Used to measure the planner on real code.

    The GitHub path is a network dependency; `backend/` of this repository is real
    multi-file Python with a real import graph, and it is what the ordering tests
    assert against so no test needs the internet or somebody else's source.
    """
    root = Path(path).resolve()
    if not root.is_dir():
        raise RepoFetchError(f"{path} is not a directory.")
    license_id = ""
    for candidate in sorted(root.glob("LICENSE*")):
        match = re.search(r"MIT|Apache-2\.0|BSD[- ]3[- ]Clause|ISC", candidate.read_text(
            encoding="utf-8", errors="replace")[:4000])
        license_id = match.group(0).replace("BSD 3 Clause", "BSD-3-Clause") if match else "MIT"
        break
    files = [
        (str(p.relative_to(root)), p.read_bytes())
        for p in sorted(root.rglob("*.py"))
        if p.is_file() and ".git" not in p.parts
    ]
    readme = ""
    for name in ("README.md", "README.rst", "README"):
        if (root / name).exists():
            readme = (root / name).read_text(encoding="utf-8", errors="replace")[:20_000]
            break
    snapshot = snapshot_from_files(root, files, owner=root.name, repo="",
                                  license=license_id, description="")
    snapshot.repo = root.name
    snapshot.readme = readme
    return snapshot
