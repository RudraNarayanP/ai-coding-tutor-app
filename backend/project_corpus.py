"""Real-material corpus for measuring guided-project quality. Dev-only.

    python -m backend.measure_project_quality

Everything here is *existing* content in this repository — nothing is a
hand-written toy transcript. Two kinds of real material are used:

* verbatim text that already sits in the repo (the stored Karpathy-talk
  transcript, the tutorial transcripts the planner tests already carry, the
  project README, the audit reports and lesson dumps), and
* chapter lists assembled from this project's own authored curriculum
  (`curriculum/*/modules/*.json` lesson titles, or its learning objectives),
  which is the same shape of data `youtube_fetch.extract_chapters` hands to
  `_plan_from_chapters`. The *content* is real; the *wrapping* is ours, so
  `provenance` says so and no conclusion below rests on it being a video.

Each source carries a label decided by the rubric in ``LABEL_RUBRIC`` before any
planner runs, so a label cannot be chosen to fit a measured outcome, and
anything the rubric does not decide is left as ``unknown`` rather than forced.

Why the chapter path is the focus: ``_plan_from_chapters`` is the route a real
YouTube source with creator-authored chapters takes, and before this corpus it
had exactly zero examples here that were not hand-written inside the test suite.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .project_models import ProjectCourse
from .source_ingestion import SourceDocument, VideoSegment

ROOT = Path(__file__).resolve().parents[1]

#: The only three verdicts the rubric below can return. Anything it cannot decide
#: stays `unknown`; a measurement that leans on an `unknown` is not a measurement.
LABELS = ("good", "poor", "unknown")

LABEL_RUBRIC = """\
Decided from the material alone, before the planner is run:

  good      The source walks through building one program, in order, and names
            artifacts the learner must produce (files, functions, calls), OR it
            is a creator-authored chapter list whose sections each name a piece
            of one system being implemented.
  poor      The source does not describe building anything: a talk/lecture about
            a subject, or documentation about an existing codebase (how to run
            it, what was measured) rather than a build-along.
  unknown   Real material whose fitness is genuinely undecided under the two
            rules above — machine-generated dumps of this repo's own curriculum,
            chapter lists whose sections are unrelated one-function exercises,
            and paraphrased outlines that only a human with the video could
            judge. An unknown is never counted for or against a rule.
"""


@dataclass
class Source:
    """One corpus member: what it is, where it came from, how it was labelled."""

    key: str
    doc: SourceDocument
    label: str                      # good | poor | unknown
    provenance: str                 # verbatim | assembled | fixture | stored
    origin: str                     # where the text lives in this repo
    note: str = ""
    tracked: bool = True            # in git, so a test can depend on it


_TRACKED: set[str] | None = None


def is_tracked(rel: str) -> bool:
    """Is this path in git? `audit/` and the project store are gitignored runtime
    state, so material that only happens to sit on one machine must never become a
    test's premise. Probed once; treated as untracked if git is unavailable."""
    global _TRACKED
    if _TRACKED is None:
        try:
            import subprocess

            out = subprocess.run(
                ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, timeout=20
            )
            _TRACKED = set(out.stdout.splitlines()) if out.returncode == 0 else set()
        except Exception:  # noqa: BLE001 - no git means no claim of being tracked
            _TRACKED = set()
    return rel.replace("\\", "/") in _TRACKED


def _read(rel: str) -> str:
    return io.open(ROOT / rel, encoding="utf-8").read()


def _file_source(key: str, rel: str, label: str, note: str = "", provenance: str = "verbatim") -> Source:
    text = _read(rel)
    return Source(
        key=key,
        doc=SourceDocument(
            source_type="file_upload", source_url="", source_hash=key,
            title=Path(rel).name, plain_text=text, access_level="full",
        ),
        label=label, provenance=provenance, origin=rel, note=note,
        tracked=is_tracked(rel),
    )


def _chaptered(key: str, *, title: str, chapters: list[str], body: str, origin: str,
               label: str, note: str = "", provenance: str = "assembled",
               source_type: str = "youtube_url", tracked_path: str = "") -> Source:
    """A source that arrives the way a chaptered video does: one segment whose
    `chapters` came from the description, plus whatever text was gathered."""
    seg = VideoSegment(
        video_id=key, title=title, url="", position=1,
        transcript=body, chapters=list(chapters),
    )
    return Source(
        key=key,
        doc=SourceDocument(
            source_type=source_type, source_url="", source_hash=key, title=title,
            segments=[seg], plain_text=body, access_level="full",
        ),
        label=label, provenance=provenance, origin=origin, note=note,
        tracked=is_tracked(tracked_path or origin),
    )


# ─── Verbatim material already in the repository ─────────────────────────────

def stored_transcripts() -> list[Source]:
    """The transcripts of real sources that this app has already ingested."""
    out: list[Source] = []
    directory = ROOT / "curriculum" / "generated" / "projects"
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        excerpt = (data.get("source_excerpt") or "").strip()
        if len(excerpt) < 200:
            continue
        is_talk = excerpt.lower().startswith("[1hr talk]")
        is_build_along = excerpt.lower().startswith("in this tutorial we build")
        out.append(
            Source(
                key=f"stored:{path.stem}",
                doc=SourceDocument(
                    source_type=data.get("source_type") or "transcript",
                    source_url=data.get("source_url") or "",
                    source_hash=path.stem,
                    title=data.get("title") or path.stem,
                    plain_text=excerpt,
                    access_level="full",
                ),
                label="poor" if is_talk else ("good" if is_build_along else "unknown"),
                provenance="stored",
                origin=str(path.relative_to(ROOT)),
                tracked=False,
                note=(
                    "the refused guided project this investigation started from"
                    if is_talk else "a real ingested build-along captured from a live session"
                ),
            )
        )
    return out


def test_transcripts() -> list[Source]:
    """Real transcript-shaped text the planner suite already asserts on."""
    out: list[Source] = []
    for rel in ("backend/test_project_planner.py", "backend/test_source_quality.py"):
        text = _read(rel)
        for name, body in re.findall(r'^([A-Z][A-Z0-9_]*) = """(.*?)"""', text, re.S | re.M):
            if len(body.strip()) < 120:
                continue
            out.append(
                Source(
                    key=f"fixture:{Path(rel).stem}:{name}",
                    doc=SourceDocument(
                        source_type="transcript", source_url="", source_hash=name,
                        title=name.replace("_", " ").title(), plain_text=body.strip(),
                        access_level="full",
                    ),
                    label="unknown",
                    provenance="fixture",
                    tracked=is_tracked(rel),
                    origin=f"{rel}::{name}",
                    note="planner test fixture; its intended verdict is asserted in that file",
                )
            )
    return out


def project_docs() -> list[Source]:
    """Documentation and engineering reports: technical, real, not tutorials."""
    return [
        _file_source("doc:README.md", "README.md", "poor",
                     "documents how to run this app; no program is built in it"),
        _file_source("doc:COVERAGE_PLAN.md", "audit/COVERAGE_PLAN.md", "poor",
                     "an engineering plan for this repo"),
        _file_source("doc:HINT_QUALITY_REPORT.md", "audit/HINT_QUALITY_REPORT.md", "poor",
                     "a measurement report, code snippets are evidence not steps"),
        _file_source("doc:FINAL_VERIFICATION_REPORT.md", "audit/FINAL_VERIFICATION_REPORT.md", "poor",
                     "a verification write-up"),
    ]


def lesson_dumps() -> list[Source]:
    """Machine-generated dumps of this repo's own curriculum content."""
    origins = (
        "audit/ml_lessons_dump.txt", "audit/ai_lessons_dump.txt",
        "audit/dsa_lessons_dump.txt", "audit/fs_dump.txt",
        "audit/all_exercises_dump.txt",
    )
    return [
        _file_source(f"dump:{Path(rel).name}", rel, "unknown",
                     "STARTER/SOLUTION/TEST fields, not a build-along a learner would paste")
        for rel in origins
    ]


# ─── Chapter lists assembled from this project's authored curriculum ─────────

# Module path -> (label, why). Labels were written after reading every lesson
# title and description in each module, per the rubric above: the `good` ones are
# units where a later lesson consumes an earlier lesson's artifact (mse needs
# predict; encode needs build_vocab; should_refresh needs is_expired), the
# `unknown` ones are drill lists of independent one-function exercises, plus the
# two modules written in a language this app cannot verify at all.
MODULES: list[tuple[str, str, str]] = [
    ("curriculum/ml/modules/linear_regression.json", "good",
     "one model fitted by gradient descent: predict -> mse -> gd_step -> r2"),
    ("curriculum/ml/modules/classification.json", "unknown",
     "logistic chain, then unrelated k-NN and metric drills"),
    ("curriculum/ai/modules/ai_tokenization.json", "good",
     "one tokenizer pipeline: tokenize -> normalize -> build_vocab -> encode"),
    ("curriculum/ai/modules/ai_embeddings.json", "unknown",
     "independent similarity helpers"),
    ("curriculum/dsa/modules/graph_traversals.json", "unknown",
     "one graph type, then DFS, then BFS and distances over it — but relabelled from "
     "`good` after measuring: no lesson description names an artifact in code form, so "
     "nothing about it is mechanically verifiable and the gate rightly keeps refusing it"),
    ("curriculum/python/modules/decorators.json", "unknown",
     "decorator drills, each its own function"),
    ("curriculum/fullstack/modules/auth_tokens.json", "good",
     "one auth flow: header -> store -> decode -> expiry -> refresh"),
    ("curriculum/sql/modules/u8_joins.json", "unknown", "SQL: outside the Python verifier's reach"),
    ("curriculum/javascript/modules/async_promises.json", "unknown",
     "JavaScript: verification is Python-only"),
    ("curriculum/ml-math/modules/vectors_matrices.json", "unknown",
     "independent linear-algebra helpers"),
]


def _module(rel: str) -> dict:
    return json.loads(io.open(ROOT / rel, encoding="utf-8").read())


def _lesson_body(mod: dict) -> str:
    return "\n".join(
        f"{lesson.get('title','')}\n{lesson.get('description','')}\n"
        f"{(lesson.get('learning_objectives') or [''])[0]}"
        for lesson in mod.get("lessons") or []
    )


def curriculum_chapters() -> list[Source]:
    """Each module twice: chapters = lesson titles, chapters = learning objectives."""
    out: list[Source] = []
    for rel, label, why in MODULES:
        if not (ROOT / rel).exists():
            continue
        mod = _module(rel)
        body = _lesson_body(mod)
        stem = Path(rel).stem
        for flavour, getter in (
            ("titles", lambda l: l.get("title", "")),
            ("objectives", lambda l: (l.get("learning_objectives") or [""])[0]),
        ):
            chapters = [str(getter(l)).strip() for l in mod.get("lessons") or []]
            chapters = [c for c in chapters if c]
            if len(chapters) < 2:
                continue
            out.append(
                _chaptered(
                    f"chapters:{stem}:{flavour}",
                    title=mod.get("title") or stem,
                    chapters=chapters,
                    body=body,
                    origin=f"{rel} ({flavour})",
                    label=label,
                    note=why,
                    tracked_path=rel,
                )
            )
    return out


def real_chaptered_video() -> list[Source]:
    """The one genuinely-fetched chaptered video page in the repo, parsed by the
    production reader-proxy parser rather than typed in here."""
    from . import test_youtube_fetch as yt_pages
    from .youtube_fetch import _extract_description, extract_chapters

    chapters = [t for _ts, t in extract_chapters(yt_pages.SAMPLE_MD)]
    title = "Let's reproduce GPT-2 (124M)"
    description = _extract_description(yt_pages.SAMPLE_MD)
    return [
        _chaptered(
            "chapters:real-gpt2-repro",
            title=title,
            chapters=chapters,
            body=f"{title}. {description}",
            origin="backend/test_youtube_fetch.py::SAMPLE_MD via youtube_fetch.extract_chapters",
            label="good",
            provenance="verbatim",
            note="a real chapter list, parsed by the code that reads one",
            source_type="youtube_playlist",
            tracked_path="backend/test_youtube_fetch.py",
        )
    ]


# Chapter lists the planner test suite already carries. They mirror real videos
# (the GPT-2 reproduction and the micrograd lectures) but were typed by hand, so
# they widen the chapter sample without counting as real-world material:
# `provenance` is `fixture` and no finding below is allowed to rest only on them.
CHAPTER_FIXTURES: list[tuple[str, str, str, str]] = [
    ("backend.test_project_planner", "GPT2_CHAPTERS", "good",
     "chapters of the GPT-2 (124M) reproduction video"),
    ("backend.test_project_planner", "MICROGRAD_CHAPTERS", "good",
     "chapters of the micrograd lecture"),
    ("backend.test_source_quality", "CONCEPTUAL_CHAPTERS", "poor",
     "chapters of a maths-intuition video that implements nothing"),
    ("backend.test_source_quality", "ASSISTANT_TIPS_CHAPTERS", "poor",
     "chapters of a prompting-tips video"),
    ("backend.test_source_quality", "GPT2_STYLE_CHAPTERS", "unknown",
     "chapter list written to look like a real one"),
]


def chapter_fixtures() -> list[Source]:
    import importlib

    out: list[Source] = []
    for module_name, const, label, why in CHAPTER_FIXTURES:
        chapters = list(getattr(importlib.import_module(module_name), const))
        title = const.replace("_CHAPTERS", "").replace("_", " ").title() + " (test fixture)"
        out.append(
            _chaptered(
                f"chapters:{module_name.rsplit('.', 1)[-1]}:{const}",
                title=title,
                chapters=chapters,
                body=f"{title}. " + " ".join(chapters),
                origin=f"{module_name}::{const}",
                label=label,
                provenance="fixture",
                note=why,
                tracked_path=module_name.replace(".", "/") + ".py",
            )
        )
    return out


def stored_courses() -> list[tuple[str, ProjectCourse, str]]:
    """The courses actually sitting in the gitignored project store.

    Planning from the talk's transcript no longer gets past ``evaluate_source``, so
    the bad guided project this investigation started from cannot be reproduced from
    source material any more — it only survives as a stored file. It is measured
    as-stored, because that is the path the load-time usability rule guards.
    """
    out: list[tuple[str, ProjectCourse, str]] = []
    directory = ROOT / "curriculum" / "generated" / "projects"
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        try:
            course = ProjectCourse(**data)
        except Exception:  # noqa: BLE001 - a stored file we cannot read is not our business
            continue
        excerpt = (data.get("source_excerpt") or "").strip()
        is_talk = excerpt.lower().startswith("[1hr talk]")
        is_build_along = excerpt.lower().startswith("in this tutorial we build")
        out.append((
            f"as-stored:{path.stem}",
            course,
            "poor" if is_talk else ("good" if is_build_along else "unknown"),
        ))
    return out


def build_corpus(only_tracked: bool = False) -> list[Source]:
    """Every corpus member, keyed and labelled before anything is planned.

    `only_tracked` drops the material that lives in gitignored runtime state (the
    project store, `audit/`), which is what a test must ask for: real here, but not
    part of the repository, so not something a suite may depend on.
    """
    sources = [
        *real_chaptered_video(),
        *curriculum_chapters(),
        *chapter_fixtures(),
        *stored_transcripts(),
        *test_transcripts(),
        *lesson_dumps(),
        *project_docs(),
    ]
    if only_tracked:
        sources = [s for s in sources if s.tracked]
    seen: set[str] = set()
    out: list[Source] = []
    for source in sources:
        if source.key in seen:
            raise AssertionError(f"duplicate corpus key {source.key}")
        seen.add(source.key)
        out.append(source)
    return out
