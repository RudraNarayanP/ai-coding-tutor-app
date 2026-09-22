"""Tests for the rule that turns a source instruction into a verifiable check.

`_extract_target` reads a backticked call after a construction verb —
"Implement `mse(y_true, y_pred)` returning the mean of the squared residuals" —
as the artifact the learner must define. It is checked *before* the older prose
pattern, which read "returning the logistic function" as a symbol named `logistic`
and produced a milestone the source itself could not satisfy.

Every positive case is also run through the real grader: a derived check must pass
for the code the source asks for and fail for the empty starter file. A check that
cannot tell those apart is not a check.
"""

from __future__ import annotations

import asyncio

import pytest

from backend import project_corpus as corpus
from backend.project_models import Milestone, ProjectCourse, WorkspaceFile
from backend.project_planner import (
    _check_for,
    _extract_target,
    plan_project,
    usability_problem,
)
from backend.project_verifier import evaluate_milestone
from backend.source_ingestion import SourceDocument, VideoSegment

# Real lesson descriptions, copied from curriculum/ml/modules/{linear_regression,
# classification}.json. The chapter title is what a creator would have written; the
# sentence is what sits under it in the source.
SOURCES = {
    "1. Linear Prediction": "Implement `predict(x, w, b)` = w*x + b for scalars.",
    "2. Mean Squared Error": (
        "Implement `mse(y_true, y_pred)` returning the mean of the squared residuals."
    ),
    "3. Gradient Descent Step": (
        "Implement `gd_step(xs, ys, w, b, lr)` one step for y≈w*x+b. Return (w_new, b_new)."
    ),
    "1. Sigmoid": (
        "Implement `sigmoid(z)` returning the logistic function 1 / (1 + e^-z) using math.exp."
    ),
    "2. Logistic Predict": "Implement `logistic_predict(x, w, b, threshold=0.5)` returning 0/1.",
}


def graded(check_kind: str, target: str, code: str) -> bool:
    """Run one check through the real verifier against `code`."""
    course = ProjectCourse(
        course_id="graded", title="T", source_hash="h", project_goal="g", entry_file="main.py",
        milestones=[
            Milestone(id="m1", order=1, title="step",
                      checks=[_check_for(check_kind, target)]),
        ],
    )
    files = [WorkspaceFile(path="main.py", content=code)]
    passed, _results, _stdout, _stderr = asyncio.run(
        evaluate_milestone(None, course, course.milestones[0], files)
    )
    return passed


# ─── rule 1: a construction verb plus a backticked call names the artifact ───

@pytest.mark.parametrize(
    "sentence,expected",
    [
        (SOURCES["2. Mean Squared Error"], ("symbol", "mse")),
        (SOURCES["1. Linear Prediction"], ("symbol", "predict")),
        (SOURCES["2. Logistic Predict"], ("symbol", "logistic_predict")),
        (SOURCES["3. Gradient Descent Step"], ("symbol", "gd_step")),
        ("Define `tokenize(text)` splitting on whitespace.", ("symbol", "tokenize")),
    ],
)
def test_a_code_formatted_call_after_a_build_verb_is_the_artifact(sentence, expected) -> None:
    assert _extract_target(sentence) == expected


def test_describing_a_function_no_longer_invents_a_symbol_the_source_never_named() -> None:
    """The regression this fix is about.

    "…returning the logistic function…" is English about *what kind* of thing
    `sigmoid` is. The old order matched it first and the milestone demanded
    `define logistic`, which a learner following the tutorial could never satisfy —
    the source's own name was sitting in backticks one word earlier.
    """
    sentence = SOURCES["1. Sigmoid"]
    assert _extract_target(sentence) == ("symbol", "sigmoid")
    assert _extract_target(sentence) != ("symbol", "logistic")


def test_the_prose_pattern_still_works_when_the_source_gives_no_code_form() -> None:
    """The older branch is not deleted: a transcript that says "the forward method"
    with no code span still names `forward`, because that is a real instruction."""
    assert _extract_target("Next call the forward method to get logits.") == ("symbol", "forward")


@pytest.mark.parametrize(
    "sentence",
    [
        "Import the modules we need",
        "At the top, import the standard library modules we use",
        "We will need some packages later",
        "This section explains the idea behind the model",
    ],
)
def test_prose_without_a_named_artifact_still_yields_nothing(sentence: str) -> None:
    assert _extract_target(sentence) is None


def test_derived_symbol_checks_are_gradable_in_both_directions() -> None:
    """Satisfiable by the code the source asks for; refused by the starter file."""
    for heading, sentence in SOURCES.items():
        kind, target = _extract_target(sentence)
        assert kind == "symbol", heading
        learner = f"def {target}(*args, **kwargs):\n    return None\n"
        assert graded(kind, target, learner) is True, f"{heading}: {target} unverifiable"
        assert graded(kind, target, "# starter\n") is False, f"{heading}: {target} passes on nothing"


# ─── rule 2: a heading inherits the check from the sentence it summarises ────

def _body() -> str:
    return "\n".join(f"{heading}\n{sentence}" for heading, sentence in SOURCES.items())


# ─── end to end over real curriculum material ────────────────────────────────

def _chapter_source(rel: str, flavour: str = "titles") -> SourceDocument:
    return next(
        s.doc for s in corpus.curriculum_chapters() if s.key == f"chapters:{rel}:{flavour}"
    )


def test_a_real_curriculum_unit_now_plans_as_a_build_sequence() -> None:
    doc = _chapter_source("linear_regression")
    project = plan_project(doc, title="Unit 1: Linear Regression", course_id="linreg")
    symbols = [
        m.checks[0].target for m in project.milestones
        if m.checks and m.checks[0].kind == "symbol"
    ]
    assert symbols == ["predict", "mse", "gd_step", "fit_slope", "r2"], symbols
    assert usability_problem(project) is None
    assert project.milestones[0].checks[0].kind == "file_exists"
    assert project.milestones[-1].checks[0].kind == "run_ok"


def test_every_anchored_milestone_is_satisfiable_by_the_source_own_code() -> None:
    """The whole planned sequence, graded."""
    doc = _chapter_source("classification")
    project = plan_project(doc, title="Unit 2: Classification", course_id="clf")
    code = "\n".join(
        f"def {m.checks[0].target}(*args, **kwargs):\n    return None"
        for m in project.milestones
        if m.checks and m.checks[0].kind == "symbol"
    )
    assert code, "expected symbol milestones"
    for milestone in project.milestones:
        if not milestone.checks or milestone.checks[0].kind not in {"symbol", "import", "function_call"}:
            continue
        files = [WorkspaceFile(path="main.py", content=code + "\n")]
        passed, _r, _o, _e = asyncio.run(evaluate_milestone(None, project, milestone, files))
        assert passed, f"{milestone.title}: {milestone.checks[0].target}"


def test_the_new_derivations_do_not_rescue_lecture_material() -> None:
    """Coverage widened; the refusals did not move.

    A maths-intuition video and a prompting-tips video are still not build-alongs,
    and the stored talk course is still refused at load. If any of these flips, the
    anchor is matching prose it should not.
    """
    for name in ("CONCEPTUAL_CHAPTERS", "ASSISTANT_TIPS_CHAPTERS"):
        source = next(
            s for s in corpus.chapter_fixtures()
            if s.key.endswith(name)
        )
        with pytest.raises(Exception):
            plan_project(source.doc, title=source.doc.title, course_id=f"no-{name}")

    _key, talk, _label = next(row for row in corpus.stored_courses() if row[2] == "poor")
    assert usability_problem(talk), "the stored talk course must stay refused"


def test_a_chaptered_source_with_no_body_text_still_yields_nothing() -> None:
    """Chapters alone, with nothing quoted from the video, cannot support a check.

    Accepting this would mean inventing a milestone, which is what the anchor
    exists to avoid.
    """
    seg = VideoSegment(
        video_id="bare", title="Some Course", url="", position=1,
        transcript="", chapters=["1. Linear Prediction", "2. Mean Squared Error"],
    )
    doc = SourceDocument(
        source_type="youtube_playlist", source_url="", source_hash="bare",
        title="Some Course", segments=[seg], access_level="full",
    )
    with pytest.raises(Exception):
        plan_project(doc, title="Some Course", course_id="bare")
