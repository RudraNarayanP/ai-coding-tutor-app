"""Authored step pools: the ladder content that sits beside the curriculum.

A *pool* is the ordered set of teaching steps for one skill, authored by hand in
``curriculum/<lang>/steps/*.json`` and attached to a lesson by id. Graded steps reuse
the existing exercise types and the existing grader, so this module adds a rung
layer without adding a second grading path — the thing that would let a step drift
into being graded one way on the map and another way in review.

Validation here is deliberately strict and runs at import/scan time rather than
during a learner's session: the whole point of the ladder is that a learner is never
handed an unloaded teaching step or a graded step with no key.

    pool file                          lesson
    curriculum/ml/steps/               linreg-predict   "lesson": "linreg-predict"
        linear-prediction.json  ────────┘               "skill": "linear-prediction"
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from backend.exercise_types import ALL_TYPES
from backend.lesson_models import ExerciseDefinition
from backend.learning_models import LADDER, Stage, Stakes

STEP_ID_PATTERN = re.compile(r"^[a-z0-9-]+$")

#: A presentation step asks for nothing but a tap, so it has no answer key.
PRESENTATION_WIDGET = "present"

#: Widgets that can be graded by the existing engine, unchanged.
GRADABLE_WIDGETS = set(ALL_TYPES)

#: The keys a step may answer to. ``present`` steps are skipped by the grader.
NON_CHARGED_STAGES = {stage for stage in Stage if stage.teaches}

_ROOT = Path(__file__).resolve().parent.parent / "curriculum"
_lock = threading.Lock()


@dataclass(frozen=True)
class StepPool:
    """One skill's authored steps, already validated."""

    skill: str
    lesson_id: str
    concept: str
    objective: str
    story: dict
    steps: tuple[dict, ...]
    source: Path

    def by_id(self, step_id: str) -> dict | None:
        return next((s for s in self.steps if s["id"] == step_id), None)

    def as_generator_pool(self) -> list[dict]:
        """The shape ``session_generator.Step.from_dict`` consumes."""
        return [
            {
                "id": s["id"],
                "stage": s["stage"],
                "widget": s["widget"],
                "concept": s.get("concept", self.concept),
                "order": s.get("order", 0),
                "difficulty": s.get("difficulty", 1),
                "stakes": s.get("stakes"),
                "remediation_of": s.get("remediation_of"),
                "targets_misconception": s.get("targets_misconception"),
                "requires_editor": s.get("requires_editor"),
            }
            for s in self.steps
        ]


def _missing_key_reason(widget: str, raw: dict) -> str | None:
    """The key the *grader* reads, per widget — not any field that looks like one.

    A step whose key the engine will not find is worse than a missing exercise: it
    reports "could not be scored" to a learner who answered correctly. The same
    widget-name mistake has already produced a silent auto-pass in this codebase
    once, so this check is intentionally the strict version.
    """
    from backend.exercise_types import (
        CHOICE_TYPES,
        FILL_TYPES,
        MATCHING_TYPES,
        MULTI_SELECT_TYPES,
        ORDERING_TYPES,
    )

    def present(field):
        return raw.get(field) not in (None, [], {}, "")

    if widget in FILL_TYPES:
        return None if present("correct_answer") else f"needs correct_answer (the {widget} key)"
    if widget in ORDERING_TYPES:
        return None if (present("correct_order") or present("correct_answer")) else "needs correct_order"
    if widget in MATCHING_TYPES:
        return None if present("pairs") else "needs pairs"
    if widget in MULTI_SELECT_TYPES or widget in CHOICE_TYPES:
        return None if present("correct_answer") else "needs correct_answer"
    # Code types are graded by running tests, or by a reference solution.
    if present("tests") or present("solution_code"):
        return None
    return "needs tests or a solution_code to be graded"


def _validate(raw: dict, source: Path, seen_ids: set[str]) -> None:
    def fail(message: str) -> None:
        raise ValueError(f"{source.name}: step {raw.get('id')!r} {message}")

    step_id = raw.get("id")
    if not isinstance(step_id, str) or not STEP_ID_PATTERN.match(step_id):
        fail("has an id that is missing or not [a-z0-9-]")
    if step_id in seen_ids:
        fail("is a duplicate id in this pool")

    try:
        stage = Stage(str(raw["stage"]))
    except (KeyError, ValueError):
        fail(f"has unknown stage {raw.get('stage')!r}; ladder is {[s.value for s in LADDER]}")

    widget = str(raw.get("widget") or raw.get("type") or "")
    if widget != PRESENTATION_WIDGET and widget not in GRADABLE_WIDGETS:
        fail(f"has widget {widget!r} which the exercise registry does not know")

    if widget == PRESENTATION_WIDGET:
        if "content" not in raw:
            fail("is a presentation step with no content")
    else:
        missing = _missing_key_reason(widget, raw)
        if missing:
            fail(f"uses gradable widget {widget!r} but {missing}")

    # A teaching rung that is authored as charged is an authoring mistake, not a
    # design choice: the rung decides stakes, and silently ignoring it would let
    # the file claim something the runtime will not do.
    stakes = raw.get("stakes")
    if stakes == Stakes.CHARGED.value and stage in NON_CHARGED_STAGES:
        fail(f"is a {stage.value} rung authored charged; teaching rungs are free to fail")

    if stage in (Stage.INTERACT, Stage.GUIDED, Stage.SCAFFOLDED, Stage.EXPLAIN):
        feedback = raw.get("feedback")
        if not isinstance(feedback, dict) or not feedback:
            fail("can be answered wrongly but ships no per-answer feedback")

    remediation = raw.get("remediation_of")
    if remediation is not None and not isinstance(remediation, str):
        fail("has a non-string remediation_of")

    solution = raw.get("solution_code")
    if solution is not None and solution == raw.get("starter_code"):
        fail("has a solution identical to its starter code")


def load_pool(path: Path) -> StepPool:
    raw = json.loads(path.read_text(encoding="utf-8"))
    for field in ("skill", "lesson", "steps"):
        if field not in raw:
            raise ValueError(f"{path.name}: missing required field {field!r}")
    steps = raw["steps"]
    if not isinstance(steps, list) or not steps:
        raise ValueError(f"{path.name}: steps must be a non-empty list")

    seen: set[str] = set()
    for step in steps:
        _validate(step, path, seen)
        seen.add(step["id"])

    # Remediation links are checked after every id is known, so a typo points at
    # the step that references it rather than failing on ordering.
    for step in steps:
        target = step.get("remediation_of")
        if target and target not in seen:
            raise ValueError(f"{path.name}: step {step['id']!r} remediates unknown step {target!r}")

    concepts = {step.get("concept") for step in steps if step.get("concept")}
    return StepPool(
        skill=raw["skill"],
        lesson_id=raw["lesson"],
        concept=raw.get("concept") or (concepts.pop() if len(concepts) == 1 else raw["skill"]),
        objective=raw.get("objective", ""),
        story=raw.get("story") or {},
        steps=tuple(steps),
        source=path,
    )


@lru_cache(maxsize=64)
def _pools_for_language(language: str) -> tuple[StepPool, ...]:
    directory = _ROOT / language / "steps"
    if not directory.is_dir():
        return ()
    return tuple(load_pool(path) for path in sorted(directory.glob("*.json")))


def pools_for_language(language: str) -> tuple[StepPool, ...]:
    with _lock:
        return _pools_for_language((language or "").lower().strip())


def pool_for_lesson(language: str, lesson_id: str) -> StepPool | None:
    return next((p for p in pools_for_language(language) if p.lesson_id == lesson_id), None)


def has_session(language: str, lesson_id: str) -> bool:
    """True when this lesson has authored teaching steps to run.

    Everything else in the curriculum keeps behaving exactly as it does today;
    the ladder is added where it exists rather than imposed everywhere at once.
    """
    return pool_for_lesson(language, lesson_id) is not None


def step_as_exercise(pool: StepPool, step: dict) -> ExerciseDefinition:
    """An authored step, in the shape the existing grader already understands.

    Field names are shared on purpose: a step that grades differently from an
    exercise of the same type is the kind of split that makes a review card and a
    lesson disagree about whether the learner has answered correctly.
    """
    payload = {
        "id": step["id"],
        "title": step.get("title", ""),
        "type": step["widget"],
        "question": step.get("question", ""),
        "options": step.get("options", []),
        "correct_answer": step.get("correct_answer") or step.get("correct_order") or step.get("answer"),
        "blanks": step.get("blanks", []),
        "pairs": step.get("pairs", []),
        "starter_code": step.get("starter_code", "") or step.get("code", ""),
        "solution_code": step.get("solution_code"),
        "tests": step.get("tests", []),
        "hints": step.get("hints", []),
        "explanation": step.get("explanation", ""),
        "micro_explanation": step.get("micro_explanation", ""),
        "worked_example": step.get("worked_example", ""),
        "worked_example_takeaway": step.get("worked_example_takeaway", ""),
        "deep_dive": step.get("deep_dive", ""),
        "xp_reward": step.get("xp_reward", 0),
    }
    if step["widget"] == "matching" and payload["pairs"]:
        payload["correct_answer"] = {p["left"]: p["right"] for p in payload["pairs"]}
    if step["widget"] == "ordering" and step.get("correct_order"):
        payload["correct_answer"] = step["correct_order"]
    return ExerciseDefinition(**payload)


def clear_pool_cache() -> None:
    """Test hook: pools are cached per language and the loader otherwise persists."""
    with _lock:
        _pools_for_language.cache_clear()
