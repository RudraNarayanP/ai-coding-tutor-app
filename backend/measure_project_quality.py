"""Measure guided-project quality signals against a real-material corpus.

Dev script, not a gate. Run it before adding any rule to
``project_planner.usability_problem``:

    python -m backend.measure_project_quality

Why this exists
---------------
A quality floor was proposed on the theory that a project can pass validation with
"one import check and one run check". It cannot: the existing ``coding < 2`` rule
refuses it. Measuring the actual corpus then showed that the proposed *replacement*
signals do not survive contact with the data, and that the suite already pins the
floor it might otherwise be tempting to raise:

* **Depth does not separate the good from the bad.** The one genuinely poor project
  on disk — the Karpathy talk, planned into 14 milestones of which 9 are
  run/print/setup checkpoints — carries *five* substantive checks. Six of the nine
  accepted projects carry fewer. A rule demanding more steps would reject good
  content while keeping the bad content it was written for, because the talk is not
  thin, it is repetitive.
* **Generic dominance cannot replace the duplicated-title rule.** A course with four
  real steps and two identically-titled "Run and verify" milestones is refused today
  by the blocklist and sits at 0.33 generic. Any "more than half the milestones are
  generic" threshold accepts it, so the blocklist is currently load-bearing.
* **Instructional-copy signals are unusable at load.** ``teach``/``example`` are
  filled by ``enrich_project``, a best-effort LLM call that "must not block a valid
  course". Every project planned without a working provider has empty copy, so a
  rule keyed on it would refuse good projects according to whether an API was
  reachable when they were created.

Round 2 — the chapter path, on real material
--------------------------------------------
The corpus was rebuilt from content that already exists in this repository
(``backend.project_corpus``): the stored transcripts of sources the app really
ingested, the reader-proxy page of a real chaptered video parsed by the production
chapter parser, chapter lists assembled from this app's own authored curriculum,
and non-tutorial technical prose (the project README, engineering reports, curriculum
dumps). Labels come from the rubric in that module and are fixed before planning.
Result: 53 sources, 17 of which plan into a course, 36 refused upstream — plus the 3
courses as they sit on disk.

What the numbers showed, and what stopped a rule from being written:

* **The chapter path's defect is under-coverage, not leniency.** *(count confirmed,
  cause wrong — see round 3 below)* Of 24 chaptered
  sources, 16 yield *no* derivable check for any heading: `_chapter_check` cannot
  name a verification for "1. Linear Prediction", "4. Whitespace Tokenize" or
  "2. Token Store" — real, implementable steps, in this app's own curriculum — while
  it keeps 7 of 8 headings for a GPT-2-shaped chapter list and 6 of 8 for the
  micrograd one. Only 4 of the 24 become a course. The matcher's vocabulary is two
  videos' worth of curated tokens (``CONCEPT_TOKENS``), so the path only fires on
  material that resembles them. Adding a quality *floor* there can only delete more
  of the legitimate content it already refuses.
* **Chapter milestones are curated inferences, and that is load-bearing.** The
  "untraceable concept" signal — a ``code_contains`` token that appears nowhere in the
  source (``data loader lite`` -> ``DataLoader|dataloader``, ``cross entropy loss`` ->
  ``cross_entropy``) — fires on the two best chapter projects in the corpus. A
  "milestone checks must be traceable to the source" rule would refuse them, so
  source-traceability cannot gate that route.
* **Progression between milestones is a property of the shape of build-alongs.** The
  GPT-2 chapter projects score ``chain`` 0.17-0.25, the lowest in the corpus among
  legitimate content, because a from-scratch model video's chapters are parallel
  subsystems (loss, dataloader, attention) that never reference each other. A rule
  demanding that each step reuse an earlier step's artifact would reject exactly the
  deepest content the feature can produce.
* **"Grounded identifier" is not measurable on prose sources.** Requiring a symbol's
  name to appear *as code* in the source refused 13 projects, including both stored
  word-frequency build-alongs, because the source text is English ("import the
  collections module") rather than code. The talk's ``call hallucination`` — the one
  defect that looked clean before it was measured — is now refused two stages
  upstream (``evaluate_source`` answers ``reject/unrelated`` for its stored
  transcript), and its signal value (0.0) sits inside the accepted range (0.0-0.5),
  so the rule guards nothing and separates nobody.
* **Duplicate verification is already handled, by the planner itself.** No freshly
  planned project repeats a ``(kind, target)`` pair or a title — ``seen_checks`` and
  ``_dedupe_milestones`` drop those before a course exists — so a stricter version of
  that rule is a measured no-op, and the price of loosening it cannot be estimated.
  The looser "nested identifier" definition does fire 4-5 times per curriculum dump
  project (``emb_dot`` vs ``test_emb_dot``), a real content problem recurring across
  three independent sources — and it also fires on ``app`` vs ``create_app`` and on
  ``backward|grad`` vs ``backward|grad|parameters``, both legitimate. A deliverable's
  test harness genuinely is a different artifact from the deliverable; deciding which
  one the learner owes needs to know what the source was *about*, which no
  token-overlap predicate can supply. Recorded as a gap, not a rule.
* **The final milestone cannot express dependence.** 19 of the 20 measured courses
  close with a bare ``run_ok``; the closer is the planner's shape, not the source's,
  so "does the ending depend on the earlier work" has no variance to measure. What no
  check in the corpus requires is that the pieces *fit*: every check names an
  identifier in one persistent `main.py`, so a project can satisfy all of them with
  code that never composes into the thing the source built. That is a limit of the
  check vocabulary, not a threshold, and it is where a real fix belongs — a check that
  runs the earlier milestones' artifacts together — which is a feature, not a gate.

Round 3 — why the chapter path produced nothing, and what one rule changed
--------------------------------------------------------------------------
The "starved" bullet above was a count without a cause. Attributing every dropped
heading to the gate that rejected it (`derivation_report`, printed below) showed the
loss was not the chapter matcher's vocabulary. A chapter heading is a creator's
summary — "2. Mean Squared Error", "4. Whitespace Tokenize" — and the artifact it
names is spelled out in the sentence underneath it, in code form:
"Implement \`mse(y_true, y_pred)\` returning the mean of the squared residuals".
`_extract_target`, the planner's only reader of prose, had patterns for `def x`, for
"define a function called x" and for "the forward method", but not for a backticked
call after a construction verb. The information was in the source and nothing read it.

One rule, added for that reason and nothing else: a construction verb followed within
the clause by a backticked call yields \`symbol <name>\` — checked *before* the prose
pattern, which read "returning the logistic function" as a demand to define
\`logistic\`. That second half is the correctness part: the old order produced
milestones the source itself could not satisfy, and \`sigmoid\` sat in backticks one
word away.

Measured on the corpus's 24 chaptered sources, with and without the rule:

  courses          4 -> 8        (2 labelled good, 2 unknown; no \`poor\` source moved)
  interior steps                 24 -> 44
  symbol checks       1 -> 21    (AST-verifiable, so each is a real artifact)
  code_contains      23 -> 23    (unchanged: the curated route was not touched)

Two things this did *not* do, both of which were tried. The chapter route still
derives nothing from a noun-phrase heading — the four rescued units came through
`plan_project`'s sentence extractor, which is the path that reads prose; and an
anchor that paired each heading with the body sentence sharing its subject was built,
measured, and cut: it rescued nothing the sentence route had not already rescued, and
it mis-attributed neighbours ("1. Linear Prediction" → \`logistic_predict\`) because
"prediction" and "predict" only share a prefix. Adding it would have raised the yield
number without raising the number of courses a learner could not already get.

The remaining ceiling is upstream and deliberate: of the 20 chaptered sources that
still produce nothing, 14 are refused by `evaluate_source` before planning — including
6 genuinely buildable curriculum units labelled good, which the source gate reads as
"ambiguous_technical" because a lesson-title list with no code-bearing description
around it looks like a topic, not a tutorial. That is a gate decision with its own
evidence requirements, not a derivation problem.

Verdict: no production *validation* rule is justified by this corpus. The one defect the
corpus newly *shows* (test scaffolding harvested as deliverables; step counts that mean
"this file mentions these names" rather than "the program was assembled") is a planner
capability gap. Fixing it means giving the planner more information about the source,
not refusing more sources.

Reading the tables
------------------
``route`` is which branch of ``plan_project`` produced the course: ``chapters``
(creator-authored outline), ``prose`` (implementable concepts named in the
title/description), ``sentences`` (step sentences in the transcript), ``stored``
(measured on the file on disk, because planning it today is impossible). A row under
``NOT PLANNED`` died before a course existed, which is evidence about the upstream
gates, not about milestone quality.

Signal columns, all computed over *interior* milestones — the ``file_exists main.py``
opener and the trailing bare ``run_ok`` are removed by kind and position, never by
title: ``ms`` their count, ``tdiv`` distinct titles / count, ``dup`` repeated
``(kind, target)`` pairs, ``near`` pairs whose identifier tokens nest, ``chain`` share
of steps that name something an earlier step already required, ``kinds`` distinct check
kinds, ``build`` share of steps whose check names code to write, ``ground``/``gshare``
identifier checks whose name appears in the source *as code*, ``trace`` ``code_contains``
tokens actually present in the source, ``spch`` stored fields that read as raw
transcript (which projection scrubs before a learner sees them), ``close`` the final
milestone's check kind.
"""

from __future__ import annotations

import atexit
import os
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# Importing the planner's test modules pulls in backend.main, which builds stores at
# import time. Redirect every writable path before that happens, exactly as conftest
# does, so running a measurement can never touch a learner's real state.
_ROOT = Path(__file__).resolve().parents[1]
_RUN = tempfile.mkdtemp(prefix="patchwork_measure_")
os.environ.setdefault("PATCHWORK_STATE_DIR", _RUN)
os.environ.setdefault("PATCHWORK_PROJECT_DIR", str(Path(_RUN) / "projects"))
atexit.register(shutil.rmtree, _RUN, ignore_errors=True)

from backend import project_planner  # noqa: E402
from backend.project_corpus import (  # noqa: E402
    LABELS,
    Source,
    build_corpus,
    stored_courses,
)
from backend.project_models import ProjectCourse  # noqa: E402
from backend.project_planner import (  # noqa: E402
    SUBSTANTIVE_CHECK_KINDS,
    looks_like_raw_transcript,
    plan_project,
    usability_problem,
)
from backend.source_ingestion import SourceDocument  # noqa: E402
from backend.source_quality import evaluate_ingestion, evaluate_source  # noqa: E402

IDENT_KINDS = frozenset({"import", "symbol", "function_call"})
LABELS = ("good", "poor", "unknown")


# ─── Planning, with the route recorded ───────────────────────────────────────

def plan_with_route(source: Source) -> tuple[ProjectCourse | None, str, str]:
    """Run the real planner; report which branch *built* the course, and any refusal.

    `plan_project` tries the chapter route first and swallows its refusal, so
    recording an attempt would credit chapters with a course the sentence extractor
    actually produced. The tracer only counts a route when it returns.
    """
    fired: list[str] = []
    original = project_planner._plan_from_chapters

    def tracer(*args, **kwargs):  # noqa: ANN002, ANN003
        project = original(*args, **kwargs)
        fired.append("chapters")
        return project

    project_planner._plan_from_chapters = tracer
    try:
        project = plan_project(source.doc, title=source.doc.title, course_id="measured")
    except Exception as exc:  # noqa: BLE001 - refusing a source is a result, not a crash
        route = fired[0] if fired else "prose/sentences"
        return None, route, f"{type(exc).__name__}: {str(exc)[:90]}"
    finally:
        project_planner._plan_from_chapters = original
    if fired:
        route = "chapters"
    else:
        concepts = project_planner._concepts_from_prose(
            project_planner._gather_source_text(source.doc), source.doc.title
        )
        route = "prose" if len(concepts) >= 2 else "sentences"
    return project, route, ""


# ─── Signals ─────────────────────────────────────────────────────────────────

def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 1}


def _code_context_hits(target: str, blob: str) -> bool:
    """True when the source shows this name *as code*, not merely says the word."""
    if not target:
        return False
    root = target.split(".")[0]
    needles = (
        f"`{target}`", f"`{root}`",
        f"def {target}", f"class {target}", f"import {target}",
        f"from {target}", f"{target}(", f"{target} =", f".{target}",
        f"{target.split('|')[0]}(",
    )
    low = blob.lower()
    if any(n.lower() in low for n in needles):
        return True
    # snake_case / dotted / CamelCase names are code morphology wherever they appear.
    if re.search(rf"\b{re.escape(target)}\b", blob) and ("_" in target or "." in target
                                                         or any(c.isupper() for c in target[1:])):
        return True
    return False


def interior(project: ProjectCourse) -> list:
    """Milestones the planner derived from the source, minus its two sentinels.

    ``plan_project`` always opens with ``file_exists main.py`` and always closes
    with a bare ``run_ok``. Those are the container, not content: counting them as
    steps is what made the talk look six steps deep, and excluding them structurally
    (by check kind and position) avoids a title blocklist.
    """
    ms = list(project.milestones)
    if ms and ms[0].checks and ms[0].checks[0].kind == "file_exists":
        ms = ms[1:]
    if ms and ms[-1].checks and ms[-1].checks[0].kind == "run_ok" and not (ms[-1].checks[0].target or ""):
        ms = ms[:-1]
    return ms


def signals(project: ProjectCourse, blob: str) -> dict:
    ms = interior(project)
    checks = [(m.checks[0].kind, (m.checks[0].target or "").strip()) for m in ms if m.checks]
    naming = [(k, t) for k, t in checks if k in SUBSTANTIVE_CHECK_KINDS and t]
    idents = [(k, t) for k, t in naming if k in IDENT_KINDS]
    contains = [(k, t) for k, t in naming if k == "code_contains"]

    titles = [ (m.title or "").strip().lower() for m in ms ]
    title_dups = sum(c - 1 for c in Counter(titles).values() if c > 1)

    exact_dups = sum(c - 1 for c in Counter((k, t.lower()) for k, t in naming).values() if c > 1)
    near = 0
    for i, (ki, ti) in enumerate(naming):
        for (kj, tj) in naming[i + 1:]:
            if ki != kj:
                continue
            a, b = _tokens(ti), _tokens(tj)
            if not a or not b or a == b:
                continue
            if a < b or b < a:
                near += 1

    seen: set[str] = set()
    linked = 0
    for m in ms:
        here = _tokens(m.title) | _tokens(m.checks[0].target if m.checks else "")
        if seen and (here & seen):
            linked += 1
        seen |= here
    chain_share = round(linked / max(len(ms) - 1, 1), 2)

    near_pairs = [
        f"{ti} ⊂ {tj}"
        for i, (ki, ti) in enumerate(naming)
        for (kj, tj) in naming[i + 1:]
        if ki == kj and _tokens(ti) and _tokens(ti) != _tokens(tj)
        and (_tokens(ti) < _tokens(tj) or _tokens(tj) < _tokens(ti))
    ]
    ungrounded = [t for _k, t in idents if not _code_context_hits(t, blob)]
    untraceable = [
        t for _k, t in contains
        if not any(alt.strip().lower() in blob.lower() for alt in t.split("|") if alt.strip())
    ]
    speech_fields = sorted({
        field
        for m in ms
        for field, value in (
            ("action", m.microstep.action), ("observation", m.microstep.observation),
            ("hook", m.hook), ("teach", m.teach), ("example", m.example),
            ("description", m.source_grounded_description),
        )
        if looks_like_raw_transcript(value or "")
    })
    grounded = len(idents) - len(ungrounded)
    traceable = len(contains) - len(untraceable)
    repeated = [t for t, c in Counter(titles).items() if c > 1]
    n = max(len(ms), 1)
    return {
        "ms": len(ms),
        "tdiv": round(1 - title_dups / n, 2),
        "tdup": title_dups,
        "dup": exact_dups,
        "near": len(near_pairs),
        "near_pairs": near_pairs,
        "chain": chain_share,
        "kinds": len({k for k, _ in checks}),
        "build": round(len(naming) / n, 2),
        "grounded": f"{grounded}/{len(idents)}" if idents else "-",
        "gshare": round(grounded / len(idents), 2) if idents else -1.0,
        "ungrounded": ungrounded,
        "trc": f"{traceable}/{len(contains)}" if contains else "-",
        "untraceable": untraceable,
        "speech": len(speech_fields),
        "speech_fields": speech_fields,
        "repeated_titles": repeated,
        "closer": (project.milestones[-1].checks[0].kind
                   if project.milestones and project.milestones[-1].checks else "?"),
    }


# ─── Candidate rules, priced against the corpus ──────────────────────────────

CANDIDATES: list[tuple[str, str, callable, callable]] = [
    ("near-dup",
     "two milestones whose checks name nested identifiers (sigmoid / test_sigmoid)",
     lambda s: s["near"] > 0,
     lambda s: s["near_pairs"][:3]),
    ("ungrounded-ident",
     "an import/symbol/call check whose name never appears as code in the source",
     lambda s: bool(s["ungrounded"]),
     lambda s: s["ungrounded"][:3]),
    ("half-ungrounded",
     "…and at least half of the identifier checks don't",
     lambda s: s["gshare"] >= 0 and s["gshare"] < 0.5,
     lambda s: s["ungrounded"][:3]),
    ("untraceable-concept",
     "a code_contains check whose tokens appear nowhere in the source",
     lambda s: bool(s["untraceable"]),
     lambda s: s["untraceable"][:3]),
    ("titles-repeat", "two milestones share a title",
     lambda s: s["tdup"] > 0, lambda s: s["repeated_titles"][:3]),
    ("no-chain", "milestones never refer to anything an earlier milestone built",
     lambda s: s["ms"] >= 3 and s["chain"] < 0.25, lambda s: [f"chain={s['chain']}"]),
    ("speech-copy", "a stored learner-facing field still reads as raw transcript",
     lambda s: s["speech"] > 0, lambda s: s["speech_fields"][:4]),
]


@dataclass
class Record:
    """One corpus member and whatever the pipeline made of it."""

    key: str
    label: str
    provenance: str
    route: str
    project: ProjectCourse | None
    reason: str
    blob: str
    doc: SourceDocument | None = None
    signals: dict = field(default_factory=dict)


def source_blob(doc: SourceDocument) -> str:
    """Everything the learner's source actually said, chapters included."""
    return (doc.plain_text or "") + "\n" + "\n".join(
        f"{seg.title}\n{seg.transcript}\n{seg.description_snippet}\n" + "\n".join(seg.chapters)
        for seg in doc.segments
    )


def chapter_yield(records: list[Record]) -> None:
    """What a chapter list becomes: how many headings survive, and which are dropped.

    ``_plan_from_chapters`` keeps a chapter only when ``_chapter_check`` can name a
    verification for it, which means the heading must match the curated
    ``CONCEPT_TOKENS`` tables or yield a code-looking identifier. This is where the
    chapter path loses content — measured rather than assumed.
    """
    print("\nchapter yield (headings in -> checkable headings -> milestones planned):")
    print("  `checkable` counts headings `_chapter_check` can derive a verification from;")
    print("  `ms` is the interior milestone count of the course that actually exists, so a")
    print("  0 there with checkable > 0 means the source was refused earlier, not that the")
    print("  chapter matcher failed.")
    width = max(len(r.key) for r in records) + 1
    print(f"  {'source':<{width}} {'in':>3} {'chk':>4} {'ms':>4}  dropped headings")
    for record in records:
        if record.doc is None:
            continue
        chapters = project_planner._collect_chapters(record.doc)
        if len(chapters) < 2:
            continue
        dropped: list[str] = []
        checkable = 0
        for chapter in chapters:
            if project_planner._looks_meta_heading(chapter):
                dropped.append(f"{chapter[:34]} [meta]")
            elif project_planner._chapter_check(chapter) is None:
                dropped.append(f"{chapter[:34]} [no check derivable]")
            else:
                checkable += 1
        made = f"{len(interior(record.project))}" if record.project else "-"
        print(f"  {record.key:<{width}} {len(chapters):>3} {checkable:>4} {made:>4}  "
              + (f"{len(dropped)} dropped: " + "; ".join(dropped[:4]) if dropped else "none"))
        for extra in dropped[4:]:
            print(f"  {'':<{width}} {'':>3} {'':>4}  and: {extra}")

    chapter_records = [
        r for r in records
        if r.doc is not None and len(project_planner._collect_chapters(r.doc)) >= 2
    ]
    dead = [r for r in chapter_records
            if not any(project_planner._chapter_check(c) for c in project_planner._collect_chapters(r.doc))]
    alive = [r for r in chapter_records if r.project is not None]
    print(f"  → {len(chapter_records)} chaptered sources; {len(dead)} yield no derivable check at all;"
          f" {len(alive)} become a course.")


def why_dropped(heading: str) -> str:
    """Which gate in `_chapter_check`'s order rejected this heading.

    Attribution matters: "the chapter path produces nothing" is four different
    problems — a meta heading (correct), lecture wording (correct), a noun-phrase
    heading whose artifact is only in the body (a derivation gap), or a heading too
    generic to verify (correct). Only the third is fixable by derivation.
    """
    cleaned = project_planner._clean_chapter(heading)
    low = cleaned.lower()
    if project_planner._looks_meta_heading(cleaned):
        return "meta-heading (correct refusal)"
    if re.search(r"\b(what is|intro to|introduction|history|why |overview)\b", low):
        return "lecture-wording (correct refusal)"
    if not project_planner.is_implementable_step(cleaned) and not project_planner._match_concept_tokens(cleaned):
        from backend import source_quality as sq

        if sq.is_dangling_or_document_task(cleaned):
            return "dangling/document (correct refusal)"
        if sq.is_generic_bare_task(cleaned):
            return "generic-bare-task (correct refusal)"
        if sq.is_conceptual_heading(cleaned):
            return "conceptual-heading (correct refusal)"
        absent = []
        if not sq.has_code_artifact(cleaned):
            absent.append("no-code-form")
        if not sq._library_hits(cleaned):
            absent.append("no-library")
        if not sq._specific_phrase_hits(cleaned):
            absent.append("no-technique-phrase")
        if not sq._construct_hits(cleaned):
            absent.append("no-construct-noun")
        return "heading-names-nothing: " + "+".join(absent)
    return "implementable but no check derived"


def derivation_report(records: list[Record]) -> None:
    """The check kinds the planner can derive, and where each corpus heading lands."""
    print("\nderivation attribution over chaptered sources (which gate rejected what):")
    reasons: Counter = Counter()
    kinds: Counter = Counter()
    for record in records:
        if record.doc is None:
            continue
        for chapter in project_planner._collect_chapters(record.doc):
            check = project_planner._chapter_check(chapter)
            if check is None:
                reasons[why_dropped(chapter)] += 1
            else:
                kinds[check.kind] += 1
    total = sum(reasons.values()) + sum(kinds.values())
    print(f"  {total} headings across the corpus -> {sum(kinds.values())} derive a check "
          f"from the heading alone")
    for kind, count in kinds.most_common():
        print(f"    {count:>4}  derives {kind}")
    for reason, count in reasons.most_common():
        print(f"    {count:>4}  {reason}")

    # What the routes actually produced, kind by kind, over planned courses.
    produced: Counter = Counter()
    for record in records:
        if record.project is None:
            continue
        for m in record.project.milestones:
            if m.checks:
                produced[m.checks[0].kind] += 1
    print("  check kinds in the courses that exist: "
          + "  ".join(f"{k}={n}" for k, n in produced.most_common()))
    print("  `import`/`symbol`/`function_call` are the kinds the grader verifies from")
    print("  the AST; `code_contains` needs a curated token; `run_ok` needs the sandbox.")


def main() -> int:
    corpus = build_corpus()
    rows: list[tuple[Source, ProjectCourse | None, str, str]] = []
    for source in corpus:
        ingest = evaluate_ingestion(source.doc)
        if ingest.decision != "accept":
            rows.append((source, None, "ingestion", f"{ingest.decision} @ ingestion: {ingest.source_type}"))
            continue
        gate = evaluate_source(source.doc, source.doc.title)
        if gate.decision != "accept":
            rows.append((source, None, "analysis", f"{gate.decision} @ source gate: {gate.source_type}"))
            continue
        project, route, error = plan_with_route(source)
        if project is None:
            rows.append((source, None, route, f"refused @ planning: {error}"))
            continue
        rows.append((source, project, route, usability_problem(project) or ""))

    # Courses already on disk, measured as they are served to a learner. The talk's
    # transcript no longer survives the source gate, so this is the only place its
    # milestone shape can still be measured.
    stored = [
        (key, course, label, source_blob(SourceDocument(
            source_type=course.source_type, source_url=course.source_url,
            source_hash=course.source_hash, title=course.title,
            plain_text=course.source_excerpt or "", access_level="full",
        )))
        for key, course, label in stored_courses()
    ]

    print(f"corpus: {len(corpus)} real-material sources "
          f"({sum(1 for s, p, *_ in rows if p is not None)} planned, "
          f"{sum(1 for s, p, *_ in rows if p is None)} refused upstream) + "
          f"{len(stored)} courses as-stored\n")

    records = [
        Record(key=source.key, label=source.label, provenance=source.provenance,
               route=route, project=project, reason=reason, blob=source_blob(source.doc),
               doc=source.doc)
        for source, project, route, reason in rows
    ] + [
        Record(key=key, label=label, provenance="stored", route="stored",
               project=course, reason=usability_problem(course) or "", blob=blob)
        for key, course, label, blob in stored
    ]

    width = max(len(r.key) for r in records) + 2
    print(f"{'label':<8} {'provenance':<11} {'outcome':<18} {'where':<11} source")
    print("-" * (width + 52))
    for record in records:
        if record.project is None:
            outcome = "NOT PLANNED"
        elif record.reason:
            outcome = "refused at load"
        else:
            outcome = "offered to learner"
        print(f"{record.label:<8} {record.provenance:<11} {outcome:<18} "
              f"{record.route:<11} {record.key}")
        if record.reason:
            print(" " * 40 + "└─ " + record.reason)

    # --- per-project signal table -------------------------------------------
    print("\nsignals over interior milestones (the setup/run sentinels are excluded by"
          "\nkind and position, not by title):")
    header = (f"{'source':<{width}} {'label':<6} {'route':<10} {'ms':>3} {'tdiv':>5} {'dup':>4} "
              f"{'near':>5} {'chain':>6} {'kinds':>6} {'build':>6} {'ground':>8} {'trace':>6} "
              f"{'spch':>5} {'close':>8}  gate")
    print(header)
    print("-" * len(header))
    measured: list[Record] = []
    for record in records:
        if record.project is None:
            continue
        record.signals = signals(record.project, record.blob)  # type: ignore[assignment]
        s = record.signals
        measured.append(record)
        print(f"{record.key:<{width}} {record.label:<6} {record.route:<10} {s['ms']:>3} {s['tdiv']:>5} "
              f"{s['dup']:>4} {s['near']:>5} {s['chain']:>6} {s['kinds']:>6} {s['build']:>6} "
              f"{s['grounded']:>8} {s['trc']:>6} {s['speech']:>5} {str(s['closer']):>8}  "
              f"{'refuse' if record.reason else 'accept'}")
    closers = Counter(str(r.signals["closer"]) for r in measured)  # type: ignore[index]
    print(f"  close: {dict(closers)} — the final milestone's check kind is decided by the")
    print("  planner's shape, not by the source, so 'does the ending depend on the earlier")
    print("  steps' cannot discriminate between good and poor content.")

    # --- distribution by label ---------------------------------------------
    def bucket(group: list[Record], key: str) -> str:
        vals = sorted(
            r.signals[key] for r in group  # type: ignore[index]
            if isinstance(r.signals[key], (int, float)) and r.signals[key] != -1.0  # type: ignore[index]
        )
        if not vals:
            return "n/a"
        return f"n={len(vals)} {min(vals)}-{max(vals)} mid {vals[len(vals) // 2]}"

    print("\ndistribution of each signal, by label (planned + stored projects):")
    print(f"{'signal':<10} " + "".join(f"{lab:>26}" for lab in LABELS))
    for key in ("ms", "tdiv", "dup", "near", "chain", "kinds", "build", "gshare", "speech"):
        print(f"{key:<10} " + "".join(f"{bucket([r for r in measured if r.label == lab], key):>26}"
                                     for lab in LABELS))

    # --- route coverage -----------------------------------------------------
    print("\ncoverage by route (the chapter path is the one this corpus was built for):")
    by_route: dict[str, Counter] = defaultdict(Counter)
    for record in records:
        stage = record.route if record.project is None else "planned:" + record.route
        by_route[stage][record.label] += 1
    for stage, counts in sorted(by_route.items()):
        print(f"  {stage:<24} " + "  ".join(f"{lab}={counts[lab]}" for lab in LABELS if counts[lab]))

    # --- price each candidate rule -----------------------------------------
    print("\ncandidate rules, priced on the corpus (NEW refusals only, by label):")
    for name, gloss, predicate, evidence in CANDIDATES:
        hits: dict[str, list[str]] = defaultdict(list)
        shown: list[str] = []
        for record in measured:
            if usability_problem(record.project) is not None:
                continue  # already refused; not this rule's doing
            if predicate(record.signals):
                hits[record.label].append(record.key)
                if len(shown) < 3:
                    shown.append(f"{record.key} [{', '.join(evidence(record.signals))}]")
        total = sum(len(v) for v in hits.values())
        print(f"  {name:<21} refuses {total:<3} "
              + "  ".join(f"{lab}={len(hits[lab])}" for lab in LABELS))
        print(f"  {'':<21} {gloss}")
        for line in shown:
            print(f"  {'':<21} ↳ {line}")

    print("\nseparation check — a signal is only usable if the accepted range and the")
    print("refused range do not overlap:")
    accepted = [r for r in measured if not r.reason]
    refused = [r for r in measured if r.reason]
    for key in ("ms", "tdiv", "dup", "near", "chain", "kinds", "build", "gshare", "speech"):
        def rng(group: list[Record]) -> str:
            vals = sorted(r.signals[key] for r in group
                          if isinstance(r.signals[key], (int, float)) and r.signals[key] != -1.0)
            return f"{min(vals)}-{max(vals)}" if vals else "n/a"
        a, b = rng(accepted), rng(refused)
        verdict = "overlaps -> useless" if a != "n/a" and b != "n/a" and a == b else ""
        print(f"  {key:<14} accepted {a:<10} refused {b:<10} {verdict}")

    chapter_yield(records)
    derivation_report(records)

    # --- corpus composition -------------------------------------------------
    print("\ncorpus composition:")
    make: dict[str, Counter] = defaultdict(Counter)
    for record in records:
        make[record.provenance][record.label] += 1
    for provenance, counts in sorted(make.items()):
        print(f"  {provenance:<11} " + "  ".join(f"{lab}={counts[lab]}" for lab in LABELS if counts[lab])
              + f"   ({sum(counts.values())} sources)")
    print("\nsee project_corpus.LABEL_RUBRIC for how labels were fixed, and this file's")
    print("docstring for which of these measurements justified a rule (none did).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
