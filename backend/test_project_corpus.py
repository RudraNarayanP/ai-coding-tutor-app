"""Regression tests for the real-material project corpus and what it proved.

These pin *measurements*, not thresholds. Nothing here asserts a new production
rule — `python -m backend.measure_project_quality` concluded that the corpus does not
justify one — so the job of this file is to keep that conclusion re-checkable and to
make it loud if the planner's behaviour on real material changes underneath it.

Only material that is actually in git is used (see `project_corpus.is_tracked`):
`audit/` and the project store are gitignored runtime state, real on the machine that
made the measurements but not something a suite may depend on.
"""

from __future__ import annotations

import pytest

from backend import measure_project_quality as measure
from backend.project_corpus import LABELS, Source, build_corpus
from backend.project_planner import (
    SUBSTANTIVE_CHECK_KINDS,
    _chapter_check,
    plan_project,
    usability_problem,
)
from backend.source_quality import evaluate_source



@pytest.fixture(scope="module")
def corpus() -> list[Source]:
    return [source for source in build_corpus(only_tracked=True) if source.tracked]


# ─── the corpus itself ───────────────────────────────────────────────────────

def test_corpus_is_real_material_and_every_source_is_explained(corpus: list[Source]) -> None:
    assert len(corpus) >= 40, f"corpus shrank to {len(corpus)}; measurements here lose their base"
    assert len({source.key for source in corpus}) == len(corpus)
    for source in corpus:
        assert source.label in LABELS
        assert source.provenance in {"verbatim", "assembled", "fixture"}
        assert source.origin and source.note, f"{source.key} carries no reason for its label"
        assert source.doc.title
        assert source.tracked


def test_labels_are_decidable_from_the_material_alone(corpus: list[Source]) -> None:
    """Identical content must not carry two labels — a label is read off the source,
    never chosen after seeing what the planner did with it."""
    by_text: dict[str, set[str]] = {}
    for source in corpus:
        text = (source.doc.plain_text or "") + "|".join(
            seg.title + "".join(seg.chapters) for seg in source.doc.segments
        )
        by_text.setdefault(text[:4000], set()).add(source.label)
    forced = {key[:60] for key, labels in by_text.items() if len(labels) > 1}
    assert not forced, f"same material labelled two ways: {forced}"


def test_ambiguous_material_is_left_unknown(corpus: list[Source]) -> None:
    """The rubric's third answer has to be used, or it is a euphemism for guessing."""
    assert {s.label for s in corpus} <= set(LABELS)
    assert sum(1 for s in corpus if s.label == "unknown") >= 20
    assert any(s.label == "poor" and "README" in s.key for s in corpus), (
        "the README is the tracked `poor` example: technical, real, and building nothing"
    )


# ─── the chapter path, which is what this corpus was built to look at ────────

def test_a_real_chaptered_video_becomes_a_grounded_course(corpus: list[Source]) -> None:
    source = next(s for s in corpus if s.key == "chapters:real-gpt2-repro")
    project = plan_project(source.doc, title=source.doc.title, course_id="corpus-gpt2")
    steps = measure.interior(project)
    assert len(steps) >= 4
    assert {m.checks[0].kind for m in steps} == {"code_contains"}
    keys = {(m.checks[0].kind, m.checks[0].target.lower()) for m in steps}
    assert len(keys) == len(steps), "a chapter course must not verify one thing twice"
    assert usability_problem(project) is None


@pytest.mark.parametrize(
    "heading",
    [
        "1. Linear Prediction",
        "2. Mean Squared Error",
        "4. Whitespace Tokenize",
        "2. Token Store",
        "1. Adjacency List Graph",
        "9. Embedding Dot Product",
    ],
)
def test_a_chapter_heading_alone_still_names_no_artifact(heading: str) -> None:
    """The chapter route's limit, measured rather than wished away.

    `_chapter_check` sees only the heading, and a bare noun phrase carries no
    verifiable name: the artifact lives in the instruction beneath it. The route
    that rescues these units is the sentence extractor in `plan_project`, which now
    reads the code form in that instruction (see `test_chapter_derivation.py`) — so
    the unit becomes a course, but not through its chapter list. An earlier attempt
    to anchor each heading onto its own sentence was measured and cut: it rescued
    nothing that the sentence route did not already handle, and it matched
    neighbouring lessons' compound names ("1. Linear Prediction" → `logistic_predict`).
    """
    assert _chapter_check(heading) is None


def test_real_curriculum_units_now_plan_as_build_sequences(corpus: list[Source]) -> None:
    """The yield this file was written to make visible.

    Before `_extract_target` could read "`mse(y_true, y_pred)`", neither of these
    units produced a course at all: 0 of 24 chaptered sources became 4. They are
    measured here as the concrete content a learner would get.
    """
    for key, symbols in (
        ("chapters:linear_regression:titles", ["predict", "mse", "gd_step", "fit_slope", "r2"]),
        ("chapters:classification:titles", ["sigmoid", "logistic_predict", "knn_classify",
                                            "accuracy", "precision_recall"]),
    ):
        source = next(s for s in corpus if s.key == key)
        project = plan_project(source.doc, title=source.doc.title, course_id="corpus-yield")
        found = [m.checks[0].target for m in measure.interior(project)
                 if m.checks and m.checks[0].kind == "symbol"]
        assert found == symbols, f"{key}: {found}"
        assert usability_problem(project) is None
        # Every step quotes the sentence its check came from.
        for milestone in measure.interior(project):
            assert milestone.source_quote and "`" in milestone.source_quote, milestone.title


def test_most_chaptered_material_yields_nothing_at_all(corpus: list[Source]) -> None:
    chaptered = [
        s for s in corpus
        if len([c for seg in s.doc.segments for c in seg.chapters]) >= 2
    ]
    assert len(chaptered) >= 20
    dead = [
        s for s in chaptered
        if not any(_chapter_check(c) for seg in s.doc.segments for c in seg.chapters)
    ]
    assert len(dead) >= len(chaptered) // 2, (
        f"only {len(dead)} of {len(chaptered)} chaptered sources are unbuildable; the"
        " corpus's premise — that the chapter path is starved, not lenient — needs"
        " re-measuring before any gate on it is trusted"
    )


def test_no_planned_course_repeats_a_step_so_a_stricter_rule_is_a_noop(
    corpus: list[Source],
) -> None:
    """`seen_checks` and `_dedupe_milestones` already guarantee this.

    It is the reason the duplicate-verification idea cannot be *priced* on today's
    material: a rule tightening it refuses nothing new, and loosening it cannot be
    shown safe either.
    """
    checked = 0
    for source in corpus:
        if evaluate_source(source.doc, source.doc.title).decision != "accept":
            continue
        try:
            project = plan_project(source.doc, title=source.doc.title, course_id="corpus-dup")
        except Exception:  # noqa: BLE001 - a refusal is a result, not a failure
            continue
        steps = measure.interior(project)
        naming = [
            (m.checks[0].kind, m.checks[0].target.strip().lower())
            for m in steps
            if m.checks and m.checks[0].kind in SUBSTANTIVE_CHECK_KINDS and m.checks[0].target
        ]
        titles = [(m.title or "").strip().lower() for m in steps]
        assert len(set(naming)) == len(naming), f"{source.key} repeats a check: {naming}"
        assert len(set(titles)) == len(titles), f"{source.key} repeats a title: {titles}"
        checked += 1
    assert checked >= 8, f"only {checked} tracked sources plan into a course; corpus coverage lost"


# ─── the candidates that were measured and rejected ─────────────────────────

def test_code_context_is_the_wrong_test_for_prose_sources() -> None:
    """Why "ungrounded identifier" died.

    The predicate accepts a name as "shown as code" if it merely *looks* like code
    (`count_words`, `nn.Module`) or appears with code punctuation. A tutorial written
    in English names its packages and variables in prose — "import the collections
    module", "create a variable called sample" — so those two checks were scored
    ungrounded, and demanding grounding refused 13 of the 20 measured courses,
    including both stored word-frequency build-alongs. Kept as a test so the idea is
    not re-proposed from the same intuition.
    """
    prose = "First, import the collections module.\nNext, create a variable called sample."
    assert measure._code_context_hits("collections", prose) is False
    assert measure._code_context_hits("sample", prose) is False
    # A snake_case name passes on morphology alone, with no code context at all.
    assert measure._code_context_hits("count_words", prose + "\nThen call count_words once.") is True
    assert measure._code_context_hits("emb_dot", "Implement `emb_dot(a, b)` for lists.") is True


def test_traceability_to_the_source_cannot_gate_the_chapter_route(
    corpus: list[Source],
) -> None:
    """`data loader lite` -> `DataLoader|dataloader` is a *useful* inference, and the
    source never writes that token. A rule demanding it would refuse the best chapter
    courses in the corpus."""
    source = next(s for s in corpus if s.key == "chapters:real-gpt2-repro")
    project = plan_project(source.doc, title=source.doc.title, course_id="corpus-trace")
    blob = measure.source_blob(source.doc)
    targets = [m.checks[0].target for m in measure.interior(project)]
    untraceable = [
        t for t in targets
        if not any(alt.strip().lower() in blob.lower() for alt in t.split("|") if alt.strip())
    ]
    assert untraceable, "expected curated tokens the source does not spell out"
    assert usability_problem(project) is None


def test_parallel_subsystem_chapters_have_no_back_references(corpus: list[Source]) -> None:
    """`chain` is low on the *good* chapter courses, so a progression rule would
    reject the deepest content the feature produces."""
    source = next(s for s in corpus if s.key == "chapters:real-gpt2-repro")
    project = plan_project(source.doc, title=source.doc.title, course_id="corpus-chain")
    signals = measure.signals(project, measure.source_blob(source.doc))
    assert signals["chain"] <= 0.3, signals
    assert usability_problem(project) is None


def test_the_closer_is_shape_not_content(corpus: list[Source]) -> None:
    """Every planned course ends in a bare `run_ok`, so "does the final verification
    depend on the earlier work" has no variance to measure — and no check in the
    corpus requires the pieces to fit together, only that the names coexist."""
    closers = set()
    for source in corpus:
        if evaluate_source(source.doc, source.doc.title).decision != "accept":
            continue
        try:
            project = plan_project(source.doc, title=source.doc.title, course_id="corpus-close")
        except Exception:  # noqa: BLE001
            continue
        if project.milestones and project.milestones[-1].checks:
            closers.add(project.milestones[-1].checks[0].kind)
            assert project.entry_file == "main.py"
    assert closers and closers <= {"run_ok", "import", "symbol"}, closers


# ─── the harness ─────────────────────────────────────────────────────────────

def test_no_planned_course_asks_the_learner_to_build_the_harness(corpus: list[Source]) -> None:
    """Nothing a course demands of a learner may be the code that marks their work.

    Pinned across the whole corpus rather than on one fixture, because the harvest
    only ever appeared in material that inlines a curriculum lesson's `unittest_code`
    — and a future source shape should fail here, not silently re-add the step.
    """
    from backend.project_planner import scaffolding_names

    checked = 0
    for source in corpus:
        try:
            project = plan_project(source.doc, title=source.doc.title, course_id="corpus-roles")
        except Exception:  # noqa: BLE001 - a refusal is a result
            continue
        flagged = scaffolding_names(source.doc.plain_text or "")
        named = {m.checks[0].target for m in project.milestones
                 if m.checks and m.checks[0].kind in {"symbol", "function_call"} and m.checks[0].target}
        assert not (named & flagged), f"{source.key}: {sorted(named & flagged)}"
        checked += 1
    assert checked >= 25, f"only {checked} corpus sources plan a course; the check lost its base"


def test_measure_runs_and_reports_the_whole_corpus(capsys) -> None:
    """The script is the evidence behind the decision not to add a rule; if it
    silently loses sources, the evidence is wrong."""
    assert measure.main() == 0
    out = capsys.readouterr().out
    for section in ("corpus composition", "chapter yield", "candidate rules",
                      "separation check", "artifact roles", "source gate: which clause"):
        assert section in out, f"the report lost its {section!r} section"
    assert "speech-copy" in out and "untraceable-concept" in out


def test_interior_excludes_the_sentinels_by_shape_not_title() -> None:
    from backend.project_models import Milestone, ProjectCourse, VerificationCheck

    project = ProjectCourse(
        course_id="p", title="T", source_hash="h", project_goal="g", entry_file="main.py",
        milestones=[
            Milestone(id="m1", order=1, title="Set up the project",
                      checks=[VerificationCheck(kind="file_exists", target="main.py")]),
            Milestone(id="m2", order=2, title="Define w",
                      checks=[VerificationCheck(kind="symbol", target="w")]),
            Milestone(id="m3", order=3, title="Run and verify the project",
                      checks=[VerificationCheck(kind="run_ok", target="")]),
        ],
    )
    assert [m.id for m in measure.interior(project)] == ["m2"]
