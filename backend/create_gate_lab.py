"""Measure the Create Course source gate against real YouTube sources.

The gate refuses sources it cannot ground in a buildable project. When it is too
strict a learner with a genuine multi-hour course gets "not enough information"
and the feature is dead for them; when it is too loose it invents curricula from
a podcast blurb. Neither failure is visible from the unit tests, which feed the
gate hand-written text. This lab feeds it the real thing.

Every case declares the verdict a human would defend:

    accept  -- a tutorial/playlists that actually builds something
    reject  -- interviews, news, motivational, assistant-tips, pure-math lectures
    insufficient -- a source with too little recovered to plan from

Run ``python -m backend.create_gate_lab`` for a report, ``--strict`` to fail on
any mismatch, ``--refresh`` to re-download. Fetched sources are cached under
``audit/gate_lab/`` so the lab is free to re-run and stays reproducible.

The AI analyzer is exercised too (``--llm``) because it is the only component
that can read intent rather than patterns; without it the lab measures the
deterministic half of the gate only.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .project_planner import ProjectGroundingError, plan_project
from .project_service import require_usable_project
from .source_ingestion import SourceDocument, SourceIngestionService, VideoSegment
from .source_quality import (
    SourceQualityError,
    _classify_source_type,
    _collect_chapters,
    _conceptual_signal_count,
    _DANGLING_OBJECT,
    _has_strong_teach,
    _score,
    _WRITE_DOCUMENT,
    assess_transcript_quality,
    evaluate_ingestion,
    evaluate_project,
    evaluate_source,
    evaluate_source_with_analyzer,
    extract_project_goal,
    extract_technical_evidence,
    gather_source_text,
    has_code_artifact,
    has_implementation_cluster,
    is_implementable_step,
    LlmSourceAnalyzer,
)

CACHE_DIR = Path(__file__).resolve().parent.parent / "audit" / "gate_lab"


@dataclass
class Case:
    url: str
    expect: str  # accept | reject | insufficient; "|" separates defensible verdicts
    label: str
    note: str = ""


CORPUS: list[Case] = [
    # ── Real, buildable: must be accepted ─────────────────────────────────────
    Case(
        "https://www.youtube.com/watch?v=WFr2WgN9_xE",
        "accept",
        "Tech With Tim — 7h ML & AI mega course",
        "Captions disabled; 33 creator chapters across 4 series.",
    ),
    Case(
        "https://www.youtube.com/watch?v=kCc8FmEb1nY",
        "accept",
        "Karpathy — Let's build GPT from scratch",
    ),
    Case(
        "https://www.youtube.com/watch?v=VMj-3S1tku0",
        "accept",
        "Karpathy — building micrograd",
    ),
    Case(
        "https://www.youtube.com/watch?v=l8pRSuU81PU",
        "accept",
        "Karpathy — Let's reproduce GPT-2 (124M)",
    ),
    Case(
        "https://www.youtube.com/watch?v=z3YMz-Gocmw",
        "accept",
        "Dave Gray — build a Flask REST API",
    ),
    Case(
        "https://www.youtube.com/watch?v=oQ5UfJqW5Jo",
        "accept",
        "NeuralNine — full Flask course, basics to deploy",
    ),
    Case(
        "https://www.youtube.com/watch?v=x4rFhThSX04",
        "accept",
        "freeCodeCamp — Learn React JS with practice projects",
    ),
    Case(
        "https://www.youtube.com/watch?v=bMknfKXIFA8",
        "accept",
        "freeCodeCamp — React course, beginner tutorial",
    ),
    Case(
        "https://www.youtube.com/watch?v=SqcY0GlETPk",
        "accept",
        "Programming with Mosh — React tutorial for beginners",
    ),
    # ── Not a build-along: must not become a course ───────────────────────────
    Case(
        "https://www.youtube.com/watch?v=zjkBMFhNj_g",
        "reject|insufficient",
        "Karpathy — [1hr Talk] Intro to LLMs",
        "A talk. No implementation sequence.",
    ),
    Case(
        "https://www.youtube.com/watch?v=I2ZK3ngNvvI",
        "reject|insufficient",
        "Lex Clips — Advice for ML beginners",
        "Interview.",
    ),
    Case(
        "https://www.youtube.com/watch?v=KT7K3z4RfwQ",
        "reject|insufficient",
        "Lex Clips — How to hack the simulation",
        "Interview.",
    ),
    Case(
        "https://www.youtube.com/watch?v=Ilg3gGewQ5U",
        "reject|insufficient",
        "3Blue1Brown — Backpropagation, intuitively",
        "Math intuition, no code.",
    ),
    Case(
        "https://www.youtube.com/watch?v=kPGTx4wcm_w",
        "reject|insufficient",
        "Sebastian Raschka — Developing an LLM",
        "Slide talk: 'make it fit onto this slide', no code typed.",
    ),
    Case(
        "https://www.youtube.com/watch?v=qL4JY6Y5pmA",
        "reject|insufficient",
        "Vanishing Gradients — Raschka LLM book chat",
        "Two people discussing a book.",
    ),
    # ── Edge cases: short builds, tips, TED, motivational ─────────────────────
    Case(
        "https://www.youtube.com/watch?v=V9N3q1W9h0I",
        "accept|insufficient",
        "TutLinks — Flask Hello World (short)",
        "Buildable intent in title/desc; YouTube often returns no captions — analysis may accept, planning needs more steps.",
    ),
    Case(
        "https://www.youtube.com/watch?v=MwZwr5Tvyxo",
        "accept|insufficient",
        "Corey Schafer — Flask tutorial part 1 getting started",
        "Buildable Flask intro; without API captions the planner may still be insufficient — not a false reject of junk.",
    ),
    Case(
        "https://www.youtube.com/watch?v=O8hQStVHTO0",
        "reject|insufficient",
        "AI Foundations — 36 ChatGPT Tips for Beginners",
        "Assistant tips / prompting productivity, not a software build.",
    ),
    Case(
        "https://www.youtube.com/watch?v=lFZgr6ayX_U",
        "reject|insufficient",
        "AI Foundations — All ChatGPT Features Explained",
        "Product feature tour of an assistant, not a coding project.",
    ),
    Case(
        "https://www.youtube.com/watch?v=nv9WwHpOKEg",
        "reject|insufficient",
        "TED — With AI Anyone Can Be a Coder (Dohmke)",
        "TED stage talk / product demo, not a build-along tutorial.",
    ),
    Case(
        "https://www.youtube.com/watch?v=-jRREn6ifEQ",
        "reject|insufficient",
        "TEDx — The poetry of programming (Linda Liukas)",
        "Motivational / poetic talk about coding culture, no implementation.",
    ),
]


# ─── Source cache ─────────────────────────────────────────────────────────────


def _cache_key(url: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", url.split("://")[-1])[:120]


def _doc_to_json(doc: SourceDocument) -> dict[str, Any]:
    return {
        "source_type": doc.source_type,
        "source_url": doc.source_url,
        "source_hash": doc.source_hash,
        "title": doc.title,
        "plain_text": doc.plain_text,
        "total_duration_seconds": doc.total_duration_seconds,
        "access_level": doc.access_level,
        "access_notes": doc.access_notes,
        "segments": [asdict(s) for s in doc.segments],
    }


def _doc_from_json(data: dict[str, Any]) -> SourceDocument:
    return SourceDocument(
        source_type=data["source_type"],
        source_url=data["source_url"],
        source_hash=data["source_hash"],
        title=data["title"],
        plain_text=data.get("plain_text", ""),
        total_duration_seconds=data.get("total_duration_seconds", 0),
        access_level=data.get("access_level", "full"),
        access_notes=data.get("access_notes", []),
        segments=[VideoSegment(**s) for s in data.get("segments", [])],
    )


async def load_doc(url: str, refresh: bool = False) -> SourceDocument:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{_cache_key(url)}.json"
    if path.exists() and not refresh:
        return _doc_from_json(json.loads(path.read_text(encoding="utf-8")))
    svc = SourceIngestionService()
    material = "youtube_playlist" if "list=" in url and "/watch" not in url else "youtube_url"
    doc = await svc.ingest(material_type=material, content=url, title="", filename=None)
    path.write_text(json.dumps(_doc_to_json(doc), ensure_ascii=False), encoding="utf-8")
    return doc


# ─── One case ─────────────────────────────────────────────────────────────────


@dataclass
class Result:
    label: str
    expect: str
    got: str
    stage: str
    reason: str
    score: float
    chapters: int
    evidence: int
    milestones: int
    goal: str
    detail: list[str]


async def run_case(case: Case, refresh: bool = False, use_llm: bool = False) -> Result:
    doc = await load_doc(case.url, refresh)
    text = gather_source_text(doc)
    chapters = [ch for seg in doc.segments for ch in (seg.chapters or [])]
    detail = [
        f"recovered={len(text)} chars",
        f"transcript_source={','.join(sorted({s.transcript_source for s in doc.segments})) or '-'}",
        f"access={doc.access_level}",
    ]

    def make(got: str, stage: str, reason: str, *, score=0.0, evidence=0, milestones=0, goal=""):
        return Result(
            label=case.label,
            expect=case.expect,
            got=got,
            stage=stage,
            reason=reason,
            score=score,
            chapters=len(chapters),
            evidence=evidence,
            milestones=milestones,
            goal=goal,
            detail=detail,
        )

    ingest = evaluate_ingestion(doc)
    if ingest.decision != "accept":
        return make(ingest.decision, "ingestion", ingest.user_message[:160])

    # Production passes the *user's* title, which is empty for a pasted URL —
    # measuring with the case label would hand the gate text the learner never did.
    if use_llm:
        analysis = await _analyze_with_provider(doc)
        if analysis is None:
            analysis = evaluate_source(doc)
    else:
        analysis = evaluate_source(doc)
    if analysis.decision != "accept":
        return make(
            analysis.decision,
            "analysis",
            analysis.user_message[:160],
            score=analysis.quality_score,
            evidence=len(analysis.technical_evidence),
            goal=analysis.project_goal,
        )

    try:
        project = plan_project(doc, title="", course_id=f"lab-{_cache_key(case.url)[:24]}")
    except ProjectGroundingError as exc:
        return make(
            "insufficient",
            "planning",
            str(exc)[:160],
            score=analysis.quality_score,
            evidence=len(analysis.technical_evidence),
            goal=analysis.project_goal,
        )

    final = evaluate_project(project, stage="pre_workspace")
    try:
        require_usable_project(project)
    except ProjectGroundingError as exc:
        return make(
            "insufficient",
            "usability",
            str(exc)[:160],
            score=final.quality_score,
            evidence=len(analysis.technical_evidence),
            milestones=len(project.milestones),
            goal=analysis.project_goal,
        )
    return make(
        final.decision,
        final.stage,
        final.user_message[:160],
        score=final.quality_score,
        evidence=len(analysis.technical_evidence),
        milestones=len(project.milestones),
        goal=project.project_goal,
    )


async def _analyze_with_provider(doc: SourceDocument):
    from .ai_provider import get_current_provider

    provider = get_current_provider()
    if provider is None:
        return None
    prior = evaluate_source(doc)
    analyzer = LlmSourceAnalyzer(provider)
    return await evaluate_source_with_analyzer(doc, analyzer=analyzer)


# ─── Planner quality scoreboard ───────────────────────────────────────────────

#: Video-section vocabulary. A milestone title may name a topic, but it must not
#: read like a line in the creator's table of contents.
_SECTION_LABEL = re.compile(
    r"\b(?:explanation|introduction|overview|analysis|discussion|conclusion|recap|"
    r"theory|math|why|what is|getting started|installation|download|part \d+)\b",
    re.IGNORECASE,
)

#: Ordinary English words the extractor has been measured grabbing as identifiers.
#: Used only to score output — production code must not key on this list. It is
#: deliberately not every word in the corpus: "subtract" and "render" are names a
#: creator really does give a function, and flagging them would push the planner
#: toward dropping correct steps to please the scoreboard.
_MEASURED_NONNAMES = {
    "believe", "whatever", "entire", "additional", "used", "or", "and", "but",
    "let", "lets", "first", "object", "handle", "dot", "dasr", "variable",
    "instance", "everything", "all", "some", "main",
}


def plan_quality_problems(project, doc: SourceDocument) -> list[str]:
    """Name every learner-visible defect in a planned course.

    The gate decides whether a source becomes a course; this decides whether the
    course is worth opening. Each rule here traces to a defect measured on the
    real sources in this corpus.
    """
    from .project_copy import _FILLERS
    from .project_planner import _concept_stem, _stems_overlap

    problems: list[str] = []
    subs = [
        m for m in project.milestones
        if m.checks and m.checks[0].kind not in {"file_exists", "run_ok"}
    ]
    for m in subs:
        kind = m.checks[0].kind
        target = (m.checks[0].target or "").split("|")[0].strip()
        if _FILLERS.search(m.title):
            problems.append(f"filler in title: {m.title!r}")
        if m.title.endswith("…"):
            problems.append(f"truncated title: {m.title!r}")
        if _SECTION_LABEL.search(m.title) and kind == "code_contains":
            problems.append(f"section label as a coding step: {m.title!r}")
        if target.lower() in _MEASURED_NONNAMES:
            problems.append(f"{kind} target is an English word: {target!r} (title {m.title!r})")
    stems: list[set[str]] = []
    for m in subs:
        stem = _concept_stem(m.title)
        if not stem:
            continue
        if any(_stems_overlap(stem, prev) for prev in stems):
            problems.append(f"duplicate concept: {m.title!r}")
        stems.append(stem)

    chapters = [c for seg in doc.segments or [] for c in (seg.chapters or [])]
    if len(chapters) >= 8 and len(subs) < 0.4 * len(chapters):
        # Legitimately red for a multi-series source: a guided project is one
        # persistent file, so four unrelated builds cannot be one course. The
        # goal is required to name the series it planned instead — see
        # test_goal_names_the_steps_this_course_actually_builds.
        problems.append(
            f"outline coverage: {len(subs)} steps planned from {len(chapters)} chapters"
        )
    return problems


async def plan_report(case: Case) -> list[str]:
    doc = await load_doc(case.url)
    if evaluate_source(doc).decision != "accept":
        return []
    try:
        project = plan_project(doc, title="", course_id="lab-plan")
    except ProjectGroundingError as exc:
        return [f"{case.label}: refused at planning — {str(exc)[:70]}"]
    problems = plan_quality_problems(project, doc)
    print(f"\n### {case.label}")
    for m in project.milestones:
        c = m.checks[0] if m.checks else None
        print(f"    {m.order:>2}. {m.title[:70]:72} [{c.kind if c else '-'}:{(c.target if c else '')[:30]}]")
    for p in problems:
        print(f"    !! {p}")
    return problems


# ─── Report ───────────────────────────────────────────────────────────────────


async def trace_case(case: Case) -> None:
    """Print every signal the gate looked at, so a verdict can be argued with."""
    doc = await load_doc(case.url)
    text = gather_source_text(doc)
    chapters = _collect_chapters(doc)
    heading = (doc.title or "").strip()
    blob = f"{heading}\n{doc.title}\n{text}\n" + "\n".join(chapters)
    evidence = extract_technical_evidence(text + "\n" + "\n".join(chapters), heading)
    goal = extract_project_goal(text, heading)
    teach = _has_strong_teach(blob)
    status, notes = assess_transcript_quality(text, chapter_count=len(chapters))
    kind = _classify_source_type(blob, heading, evidence, chapters)
    score, conf = _score(
        evidence=evidence,
        teach=teach,
        goal=goal,
        transcript_status=status,
        source_kind=kind,
        dangling=len(_DANGLING_OBJECT.findall(blob)),
        doc_tasks=len(_WRITE_DOCUMENT.findall(blob)),
    )
    implementation = has_implementation_cluster(blob, chapters)
    impl_ch = [c for c in chapters if is_implementable_step(c)]
    print(f"\n=== {case.label}  (expect {case.expect})")
    print(f"    recovered={len(text)} chars  chapters={len(chapters)}  access={doc.access_level}")
    print(f"    transcript={status} {notes}")
    print(f"    source_kind={kind}  score={score:.2f}  confidence={conf}")
    print(f"    goal={goal[:90]!r}")
    print(f"    evidence({len(evidence)})={evidence}")
    print(
        f"    implementation={implementation}  teach={teach}  "
        f"implementable_chapters={len(impl_ch)}  conceptual={_conceptual_signal_count(blob, heading, chapters)}  "
        f"code_artifact={has_code_artifact(blob)}"
    )
    decision = evaluate_source(doc)
    print(f"    stage2={decision.decision} :: {decision.user_message[:150]}")
    try:
        project = plan_project(doc, title="", course_id="lab-trace")
        print(f"    planned={len(project.milestones)} milestones")
        for m in project.milestones[:10]:
            print(f"       - {m.title[:88]}")
        print(f"    stage4={evaluate_project(project, stage='pre_workspace').decision}")
    except ProjectGroundingError as exc:
        print(f"    planning RAISED :: {str(exc)[:170]}")


def _matches(r: Result) -> bool:
    return r.got in {v.strip() for v in r.expect.split("|")}


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure the Create Course source gate on real sources.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when a case disagrees with its expected verdict.")
    parser.add_argument("--refresh", action="store_true", help="Re-download sources instead of using the cache.")
    parser.add_argument("--llm", action="store_true", help="Also run the AI analyzer (spends provider requests).")
    parser.add_argument("--trace", action="store_true", help="Print every signal the gate read, per case.")
    parser.add_argument("--plan", action="store_true", help="Score the planned course: titles, checks, coverage.")
    parser.add_argument("--only", default="", help="Run only cases whose label or url contains this text.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print the gate's reason for every case, not just mismatches.")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    cases = [c for c in CORPUS if not args.only or args.only.lower() in (c.label + c.url).lower()]

    if args.plan:
        tally: list[str] = []
        for case in cases:
            tally += await plan_report(case)
        print(f"\n{len(tally)} planner-quality problems across {len(cases)} sources.")
        return 1 if (tally and args.strict) else 0

    if args.trace:
        for case in cases:
            await trace_case(case)
        return 0

    results: list[Result] = []
    for case in cases:
        try:
            results.append(await run_case(case, refresh=args.refresh, use_llm=args.llm))
        except Exception as exc:  # noqa: BLE001 — a fetch failure must not hide the other cases
            results.append(
                Result(
                    label=case.label,
                    expect=case.expect,
                    got="error",
                    stage="fetch",
                    reason=f"{type(exc).__name__}: {str(exc)[:140]}",
                    detail=[],
                )
            )

    bad = [r for r in results if not _matches(r)]
    if args.as_json:
        print(json.dumps([asdict(r) for r in results], indent=1, ensure_ascii=False))
    else:
        print(f"{'':2}{'verdict':>12} {'expected':>18} {'stage':>10} {'ch':>3} {'ev':>3} {'ms':>3}  case")
        for r in results:
            ok = _matches(r)
            print(
                f"{'ok ' if ok else 'BAD':2}{r.got:>12} {r.expect:>18} {r.stage:>10} "
                f"{r.chapters:>3} {r.evidence:>3} {r.milestones:>3}  {r.label}"
            )
            if not ok or args.verbose:
                print(f"   {'':10}-> {r.reason}")
                print(f"   {'':10}   {'; '.join(r.detail)}")
                if r.goal:
                    print(f"   {'':10}   goal: {r.goal[:110]}")
        print(f"\n{len(results) - len(bad)}/{len(results)} cases match their expected verdict.")
        for r in bad:
            print(f"  MISMATCH {r.label}: expected {r.expect}, got {r.got} at {r.stage}")
    return 1 if (bad and args.strict) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
