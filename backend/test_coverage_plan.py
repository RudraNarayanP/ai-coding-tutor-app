"""Invariants for the coverage planner.

The planner decides where new exercises are allowed to be created, so a bad
classification becomes bad curriculum. These tests pin the properties that make
its output trustworthy enough to plan from:

* one row per lesson, always, for every shipped course
* no recommendation outside the shared exercise-type registry
* "no item here" is only ever a *learn* lesson with a context title, and it
  always zeroes the target
* a lesson never gets recommended a type it already carries
* wave 1 stays small, one lesson per course, strong-tier only, and type-capped
* the whole analysis is deterministic across calls in one process
"""
from __future__ import annotations

import collections

import pytest

from backend.coverage_plan import (
    EXPLANATION_TITLE_MARKERS,
    FIT_EXPLANATION_ONLY,
    WAVE1_ITEMS_PER_COURSE,
    WAVE1_MAX_PER_TYPE,
    build_rows,
)
from backend.exercise_types import ALL_TYPES
from backend.curriculum_loader import load_all_curriculums


@pytest.fixture(scope="module")
def rows():
    return build_rows()


def _lesson_ids():
    for curriculum in load_all_curriculums().values():
        for lesson in curriculum.lessons:
            yield lesson.id


def test_every_lesson_is_planned_exactly_once(rows):
    ids = [r["lesson_id"] for r in rows]
    assert len(ids) == len(set(ids)) == len(list(_lesson_ids()))


def test_recommendations_come_from_the_shared_registry(rows):
    for r in rows:
        for kind in r["recommended_types"].split("|"):
            if kind:
                assert kind in ALL_TYPES, f"{r['lesson_id']} recommends unknown type {kind}"


def test_explanation_only_is_reserved_for_contextual_learn_lessons(rows):
    for r in rows:
        if r["explanation_only"] != "yes":
            continue
        assert r["lesson_type"] == "learn", f"{r['lesson_id']}: a task lesson is never explanation-only"
        assert EXPLANATION_TITLE_MARKERS.search(r["lesson_title"])
        assert r["target"] == 0


def test_a_lesson_is_never_recommended_a_type_it_already_has(rows):
    for r in rows:
        have = set(filter(None, r["current_types"].split("|")))
        want = set(filter(None, r["recommended_types"].split("|")))
        assert not (have & want), f"{r['lesson_id']}: {have & want} would duplicate a pattern"


def test_gap_and_target_stay_coherent(rows):
    for r in rows:
        assert r["gap"] == max(0, r["target"] - r["current"])
        if r["gap"]:
            assert r["kinds"], f"{r['lesson_id']} has a gap but nothing recommended"
            assert r["tier"] in {"strong", "recall_only"}


def test_tiers_partition_every_lesson(rows):
    counts = collections.Counter(r["tier"] for r in rows)
    assert set(counts) <= {"strong", "recall_only", "none"}
    assert sum(counts.values()) == len(rows)
    # sanity: the planner must not collapse everything into the cheap bucket
    assert counts["strong"] > counts["recall_only"]


def test_wave_one_is_one_lesson_per_course_and_type_capped(rows):
    wave = [r for r in rows if r["wave"] == "1"]
    per_course = collections.Counter(r["course"] for r in wave)
    per_type = collections.Counter(r["wave_type"] for r in wave)
    assert per_course and max(per_course.values()) <= WAVE1_ITEMS_PER_COURSE
    assert per_type and max(per_type.values()) <= WAVE1_MAX_PER_TYPE
    for r in wave:
        assert r["tier"] == "strong"
        assert r["wave_type"] in r["recommended_types"]
        assert r["wave_route"] in {"mechanical", "authored"}


def test_wave_one_covers_every_course_with_a_strong_gap(rows):
    starved = {r["course"] for r in rows if r["tier"] == "strong" and r["gap"] > 0}
    assert {r["course"] for r in rows if r["wave"] == "1"} == starved


def test_analysis_is_deterministic():
    a = [(r["lesson_id"], r["verdict"], r["recommended_types"], r["wave"], r["value_score"])
         for r in build_rows()]
    b = [(r["lesson_id"], r["verdict"], r["recommended_types"], r["wave"], r["value_score"])
         for r in build_rows()]
    assert a == b, "wave assignment leaked state between calls"
