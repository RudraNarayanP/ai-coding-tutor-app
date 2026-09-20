"""Per-lesson exercise coverage plan for every shipped course.

Answers one question for each of the 334 lessons: does a *graded micro-item* here
teach something the lesson cannot already teach, what type would fit, can the
answer be verified mechanically, or does it need a human to author meaningful
wrong answers?

This is a planner, not a generator. It writes reports under ``audit/``
(gitignored) and never touches curriculum files or learner state. Classification
is rule-based so it is reproducible, and every row carries the signals that
produced its verdict so a specific lesson can be disagreed with instead of the
aggregate.

Why the framing had to change from "307 lessons have no exercises"
-----------------------------------------------------------------
`src/App.tsx` treats *every* lesson as interactive: a lesson with no sublesson
exercises still opens the fullscreen workspace and is presented as one
open-ended `code` item over the shared buffer (`lessonWorkspaceExercise`). So an
empty exercise list is not a dead screen - it is unstructured free play. The
thing those lessons lack is a *graded micro-item*: per-type feedback, a mistake
queue entry, spaced recall and a type-appropriate widget. That is the gap this
plan measures.

Consequences baked into the policy
----------------------------------
* A lesson whose own task is already "write code and pass the tests" (practice,
  challenge) does not need another coding item - that is the filler trap. It
  needs interleaved recall/reading items, so coding types are suppressed there.
* Multiple-choice, true/false, select-multiple and matching are routed to
  `authored`: a generator can make a correct stem cheaply, but a *plausible*
  distractor is the whole pedagogical value and cannot be proven by machine.
* `output_prediction`, `ordering` and `code_completion` can be mechanical
  because the sandbox proves them: canonical answer passes, every single-step
  alternative fails. Same bar `backend/generate_ordering_exercises.py` holds.
* `target_exercises` is a ceiling, not a to-do list. The near-term plan is
  expressed as waves, and wave 1 is deliberately small.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.analyse_exercise_fit import family as concept_family
from backend.console import configure as configure_console
from backend.curriculum_loader import load_all_curriculums
from backend.generate_ordering_exercises import (
    MAX_STATEMENTS,
    MIN_STATEMENTS,
    statement_units,
)

configure_console()

# ── verdicts ─────────────────────────────────────────────────────────────────

FIT_EXERCISE = "exercise"          # a graded micro-item adds real practice
FIT_DEMO_READER = "demo_reader"    # reading/recall only; nothing to author
FIT_THIN_MATERIAL = "thin_material"  # lesson states too little to build a good item yet
FIT_EXPLANATION_ONLY = "explanation_only"

ROUTE_MECHANICAL = "mechanical"    # derivable and provable by execution
ROUTE_AUTHORED = "authored"        # needs a human for meaningful wrong answers
ROUTE_NONE = "none"

CODING_TYPES = {"code", "code_completion", "full_coding", "tiny_coding"}

# Only a *learn* lesson can be called explanation-only on its title: a practice,
# challenge or checkpoint lesson is a task by definition, whatever it is called
# ("3. Fixture-like Setup (Concept Challenge)" is not an explanation).
EXPLANATION_TITLE_MARKERS = re.compile(
    r"\b(install|installation|set ?up|configure|environment|overview|roadmap|why\b"
    r"|history|introduction to|what (is|are)|getting started|tour|orientation"
    r"|best practices|glossary|cheat ?sheet|faq|troubleshoot)",
    re.I,
)

# Types that need the lesson to have a student-editable surface.
def _has_authoring_surface(lesson) -> bool:
    body = (lesson.starter_code or "") + "\n" + (lesson.solution_code or "")
    if re.search(r"TODO|\.\.\.\s*$|raise NotImplementedError", body, re.M):
        return True
    if re.search(r"^\s*(def|fn|function|class)\s+\w+", body, re.M):
        return True
    if re.search(r"^\s*(public |private |void |int |str |auto |func )*\w[\w<>*&]*\s+\w+\s*\([^)]*\)\s*[{;]",
                 lesson.solution_code or "", re.M):
        return True
    return False


def _statement_count(lesson) -> int:
    """Executable, non-trivial solution lines - the raw material for ordering."""
    keep = 0
    for line in (lesson.solution_code or "").splitlines():
        s = line.strip()
        if not s:
            continue
        if re.match(r"^(#|//|/\*|\*|import |from |@|package |using |end\s*$|\})", s):
            continue
        keep += 1
    return keep


def current_exercises(lesson) -> list:
    return [e for s in lesson.sublessons for e in s.exercises] + list(lesson.mastery_exam or [])


def existing_interaction(lesson, items: int) -> str:
    """What the learner can actually do in this lesson today."""
    kinds = {e.type for e in items}
    graded = len(kinds - CODING_TYPES) > 0 or "code" in kinds
    if items and graded:
        return "graded micro-items"
    if _has_authoring_surface(lesson) or lesson.tests:
        return "free-run only"      # workspace + Run, but nothing graded per item
    return "read only"


# ── recommendation ───────────────────────────────────────────────────────────

# Preferred item per lesson genre, given that the lesson body already provides
# its own interaction. Coding types are absent from practice/challenge on
# purpose: those lessons end in "write code, pass tests", so another code item
# is duplication, not variety.
GENRE_PREFERENCE = {
    "practice": ["debugging", "output_prediction", "select_multiple", "true_false", "ordering"],
    "challenge": ["output_prediction", "debugging", "matching", "select_multiple", "ordering"],
    "checkpoint": ["ordering", "matching", "select_multiple", "output_prediction", "true_false"],
    "learn": ["code_completion", "output_prediction", "ordering", "mcq", "matching", "true_false"],
}

# What the *concept* is actually good for. The recommendation is the intersection
# of genre preference and concept affinity: an item type that a lesson could
# technically back but that does not match what it teaches is filler with extra
# steps. Without this, the scarcity weighting below collapses the whole plan into
# "add another ordering exercise everywhere" - 170 identical recommendations.
FAMILY_AFFINITY = {
    "syntax-api recall": ["fill_blank", "code_completion", "matching", "true_false", "mcq"],
    "code reading / output": ["output_prediction", "debugging", "true_false", "code_completion"],
    "control flow": ["ordering", "output_prediction", "debugging", "code_completion"],
    "data structure": ["ordering", "output_prediction", "matching", "select_multiple", "debugging"],
    "transformation pipeline": ["ordering", "code_completion", "output_prediction", "matching"],
    "math / algorithm": ["output_prediction", "ordering", "code_completion", "debugging"],
    "query language": ["fill_blank", "code_completion", "output_prediction", "ordering", "matching"],
    "async / state": ["ordering", "output_prediction", "select_multiple", "debugging"],
    "other": ["mcq", "true_false", "matching", "output_prediction", "ordering"],
}

# Ceiling per genre - deliberately below "every lesson has items".
GENRE_TARGET = {"practice": 1, "challenge": 1, "checkpoint": 2, "learn": 2}

# The end-state mix we want, used only to rank within the types the concept
# already supports: mcq (12) and fill_blank (12) are plentiful, thin types get a
# nudge. It is a tie-breaker, never a licence to recommend an unfit type.
TYPE_SCARCITY_BONUS = {
    "ordering": 0.35, "matching": 0.35, "select_multiple": 0.30,
    "output_prediction": 0.30, "debugging": 0.30, "tiny_coding": 0.20,
    "true_false": 0.15, "code_completion": 0.10, "full_coding": 0.10,
    "mcq": 0.0, "fill_blank": 0.0, "code": 0.0,
}


PROCEDURE_SIGNAL = re.compile(
    r"\b(step|order|sequence|flow|process|stage|phase|then|pipeline|lifecycle|"
    r"algorithm|traversal|parse|render|bootstraps|protocol|checks?)\b", re.I)


def _is_procedural(lesson) -> bool:
    """Ordering is only honest when the generator could actually prove it.

    The first draft counted non-comment lines anywhere in the solution, which is
    true of nearly every lesson and produced 170 ordering recommendations -
    including for lessons that ``generate_ordering_exercises`` then rejected.
    The authority is the generator's own structural pre-filter: a solution must
    expose 3-5 *reorderable* top-level statements (imports, headers and
    docstrings are scaffolding, not steps) with no duplicates. Anything outside
    that window can never clear the execution proof, so it must never be
    recommended. Typescript, cpp and javascript have zero such lessons, which is
    why the earlier wave-1 pick of an ordering item in typescript was impossible.
    """
    units = statement_units(lesson.solution_code or "")
    if not MIN_STATEMENTS <= len(units) <= MAX_STATEMENTS:
        return False
    return len({unit.lower() for unit in units}) == len(units)


def _can_back(lesson, kind: str) -> bool:
    """Does this lesson contain real material for that item type?"""
    solution = lesson.solution_code or ""
    starter = lesson.starter_code or ""
    objectives = lesson.learning_objectives or []
    blob = " ".join([lesson.title or "", lesson.description or "", " ".join(objectives)])

    if kind == "output_prediction":
        return bool(re.search(r"print\s*\(|console\.log|std::cout|System\.out|\bSELECT\b",
                              solution, re.I))
    if kind == "ordering":
        return _is_procedural(lesson)
    if kind in ("code_completion", "tiny_coding", "full_coding"):
        return _has_authoring_surface(lesson)
    if kind == "debugging":
        return _has_authoring_surface(lesson) and _statement_count(lesson) >= 3
    if kind == "select_multiple":
        return bool(re.search(r"\b(and|or|not|both|either|only if|unless|all of)\b", blob, re.I)) \
            or len(objectives) >= 3
    if kind == "matching":
        return len(re.findall(r"`[^`]{2,}`|\b[a-z_]+\s*\(\)", blob)) >= 4 or len(objectives) >= 3
    if kind in ("mcq", "true_false"):
        # A recall item needs a claim to ask about: usable objectives, or a
        # description with real content next to a code body worth reading.
        if len([o for o in objectives if 15 <= len(o) <= 120]) >= 2:
            return True
        return len(blob.split()) >= 12 and _statement_count(lesson) >= 2
    if kind == "fill_blank":
        return bool(re.search(r"^\s*\S.*[=:(].*$", starter, re.M)) and _has_authoring_surface(lesson)
    return False


STRONG_KINDS = {"ordering", "output_prediction", "code_completion", "debugging",
                "matching", "select_multiple", "fill_blank", "tiny_coding", "full_coding"}


def tier_of(kinds: list[str]) -> str:
    """Fit strength, which is what the no-filler rule actually needs.

    There is no prose-only lesson in this curriculum to excuse (verified: the
    only title carrying a context word is a pytest challenge), so "should this
    stay explanation-only" cannot be the brake. The brake is fit strength: an
    item that can only ever be "true or false about a sentence" is cheap to
    generate and weak to learn from, and must not crowd out the types that make
    a learner do something.
    """
    if not kinds:
        return "none"
    return "strong" if set(kinds) & STRONG_KINDS else "recall_only"


def material_confidence(lesson, kind: str) -> str:
    """How much the lesson actually states - 'low' means the item must be
    authored from the code and prose, not lifted from the objectives."""
    objectives = lesson.learning_objectives or []
    usable = [o for o in objectives if 15 <= len(o) <= 120]
    if kind in ("output_prediction", "ordering", "code_completion", "fill_blank"):
        return "high"                       # the artifact itself is the material
    if len(usable) >= 2:
        return "high"
    if len(" ".join([lesson.description or ""] + objectives).split()) >= 20:
        return "medium"
    return "low"


MECHANICAL_KINDS = {"output_prediction", "ordering", "code_completion", "fill_blank"}


def _route_for(kind: str) -> str:
    return ROUTE_MECHANICAL if kind in MECHANICAL_KINDS else ROUTE_AUTHORED


def recommend(lesson, existing_types: set[str]) -> tuple[list[str], str]:
    """Concept-and-genre driven, never scarcity-driven.

    A type is only recommended when the genre wants that kind of item *and* the
    concept family suits it *and* the lesson really contains material for it. The
    scarcity weighting then only orders what survived all three filters.
    """
    genre = (lesson.type or "learn").lower()
    wanted = set(GENRE_PREFERENCE.get(genre, GENRE_PREFERENCE["learn"]))
    suits = set(FAMILY_AFFINITY.get(concept_family(lesson), FAMILY_AFFINITY["other"]))
    order = GENRE_PREFERENCE.get(genre, GENRE_PREFERENCE["learn"])

    fits = [k for k in order if k in wanted and k in suits and k not in existing_types
            and _can_back(lesson, k)]
    if not fits:
        # Nothing in the genre's preferred list fits this concept: fall back to
        # the concept's own ranking, still requiring real material for it.
        fits = [k for k in FAMILY_AFFINITY.get(concept_family(lesson), [])
                if k not in existing_types and _can_back(lesson, k)]
    if not fits:
        return [], ROUTE_NONE
    fits.sort(key=lambda k: -TYPE_SCARCITY_BONUS.get(k, 0.0))
    return fits[:3], _route_for(fits[0])


def fit_verdict(lesson, kinds: list[str], route: str) -> tuple[str, str]:
    """(verdict, why) - 'no fit found' is never the same thing as
    'no exercise belongs here', and conflating them hid 45 lessons that
    absolutely should carry items."""
    if (lesson.type or "").lower() == "learn" and EXPLANATION_TITLE_MARKERS.search(
            lesson.title or ""):
        return FIT_EXPLANATION_ONLY, "title is context/setup, not a checkable skill"
    if not kinds:
        return FIT_THIN_MATERIAL, "lesson states too little to build an honest item yet"
    if route == ROUTE_NONE:
        return FIT_THIN_MATERIAL, "no verifiable material in the lesson"
    if not _has_authoring_surface(lesson) and set(kinds) <= {"output_prediction", "mcq",
                                                            "true_false", "matching",
                                                            "ordering"}:
        return FIT_DEMO_READER, "demo has no authoring surface; reading/recall only"
    return FIT_EXERCISE, "concept maps onto a graded micro-item"


def value_score(row: dict, course_stats: dict, lesson) -> float:
    """Deterministic priority: biggest learning hole per unit of authoring work."""
    if row["target"] <= 0 or not row["kinds"]:
        return 0.0
    gap = max(0, row["target"] - row["current"])
    if gap == 0:
        return 0.0
    score = float(gap)

    # A lesson with literally no graded item counts against its course's density:
    # dsa / ml / ml-math / typescript have zero exercises across 92 lessons.
    density = course_stats["exercises"] / max(1, course_stats["lessons"])
    score += (1.0 - min(1.0, density * 4.0)) * 1.6

    # Free-run-only lessons gain more from a graded item than lessons that
    # already have one.
    score += {"free-run only": 1.0, "read only": 0.6, "graded micro-items": 0.0}[
        row["existing_interaction"]]

    # Genre: a checkpoint is a natural mixed-recall moment; a learn lesson is
    # where comprehension is currently invisible.
    score += {"learn": 0.8, "checkpoint": 0.7, "practice": 0.4, "challenge": 0.4}.get(
        row["lesson_type"], 0.3)

    score += max(TYPE_SCARCITY_BONUS.get(k, 0.0) for k in row["kinds"])

    # Cheaper to ship than the score implies when the sandbox can prove it.
    if row["mechanically_verifiable"] == "yes":
        score += 0.4
    if not _has_authoring_surface(lesson):
        score -= 0.2
    # A tap-two-buttons recall item is the least valuable thing this system can
    # spend a lesson on. It stays in the plan, but never above a doing-item.
    if row["tier"] == "recall_only":
        score -= 1.5
    return round(score, 3)


def build_rows() -> list[dict]:
    currs = load_all_curriculums()
    course_stats = {
        key: {"lessons": len(c.lessons),
              "exercises": sum(len(current_exercises(l)) for l in c.lessons)}
        for key, c in currs.items()
    }

    rows: list[dict] = []
    for course_key, curriculum in sorted(currs.items()):
        for lesson in curriculum.lessons:
            items = current_exercises(lesson)
            kinds, route = recommend(lesson, {e.type for e in items})
            verdict, why = fit_verdict(lesson, kinds, route)
            genre = (lesson.type or "learn").lower()
            if verdict == FIT_EXPLANATION_ONLY:
                target = 0
            elif verdict == FIT_THIN_MATERIAL:
                target = 0        # not a rejection: revisit once the lesson states more
            elif verdict == FIT_DEMO_READER:
                target = 1
            else:
                target = GENRE_TARGET.get(genre, 1)
            row = {
                "course": course_key,
                "lesson_id": lesson.id,
                "lesson_title": lesson.title,
                "lesson_type": lesson.type,
                "section": lesson.section_title,
                "difficulty": lesson.difficulty,
                "concept": ", ".join(lesson.concepts or []) or concept_family(lesson),
                "family": concept_family(lesson),
                "interactive_appropriate": {"exercise": "yes", "demo_reader": "reading-only",
                                            "thin_material": "not-yet",
                                            "explanation_only": "no"}[verdict],
                "recommended_types": "|".join(kinds),
                "kinds": kinds,
                "mechanically_verifiable": ("yes" if route == ROUTE_MECHANICAL
                                            else "partial" if kinds else "no"),
                "needs_authored_content": ("no" if route == ROUTE_MECHANICAL
                                           else "yes" if kinds else "n/a"),
                "explanation_only": "yes" if verdict == FIT_EXPLANATION_ONLY else "no",
                "current": len(items),
                "current_types": "|".join(sorted({e.type for e in items})),
                "existing_interaction": existing_interaction(lesson, items),
                "target": target,
                "verdict": verdict,
                "tier": tier_of(kinds),
                "why": why,
                "material_confidence": (material_confidence(lesson, kinds[0])
                                        if kinds else "n/a"),
            }
            row["gap"] = max(0, target - len(items))
            row["value_score"] = value_score(row, course_stats[course_key], lesson)
            rows.append(row)

    _assign_waves(rows)
    return rows


# ── waves ────────────────────────────────────────────────────────────────────

WAVE1_ITEMS_PER_COURSE = 1        # pilot-sized: one item per course, varied types
WAVE1_MAX_PER_TYPE = 3            # stop the wave collapsing into one cheap type


def _assign_waves(rows: list[dict]) -> None:
    """Mark which lessons the *next* small batch should cover.

    Constraints, in order: one item per lesson, at most one per course for the
    pilot wave, and a spread of item types rather than 12 more multiple-choice
    questions. Waves are assigned by value score so the ordering is
    reproducible, not hand-picked.
    """
    type_used: collections.Counter = collections.Counter()
    for row in rows:
        row["wave"] = ""
        row["wave_type"] = ""
        row["wave_route"] = ""
    ranked = sorted(rows, key=lambda r: (-r["value_score"], r["course"], r["lesson_id"]))
    per_course = collections.Counter()
    for row in ranked:
        if row["gap"] <= 0 or not row["kinds"]:
            continue
        if row["tier"] != "strong":
            continue            # wave 1 is proof-of-quality, not count-chasing
        if per_course[row["course"]] >= WAVE1_ITEMS_PER_COURSE:
            continue
        # pick the highest-scarcity type this lesson can actually back that the
        # wave is not already drowning in
        choice = next((k for k in sorted(row["kinds"],
                                         key=lambda x: -TYPE_SCARCITY_BONUS.get(x, 0.0))
                       if type_used[k] < WAVE1_MAX_PER_TYPE), None)
        if not choice:
            continue
        type_used[choice] += 1
        per_course[row["course"]] += 1
        row["wave"] = "1"
        row["wave_type"] = choice
        row["wave_route"] = _route_for(choice)


# ── reporting ────────────────────────────────────────────────────────────────

def write_csv(rows: list[dict], path: Path) -> None:
    cols = [c for c in rows[0].keys() if c != "kinds"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def summarise(rows: list[dict], top: int) -> str:
    out: list[str] = []
    by_course = collections.defaultdict(list)
    for r in rows:
        by_course[r["course"]].append(r)

    out.append(f"Lessons analysed: {len(rows)} across {len(by_course)} courses\n")
    out.append("## Current coverage vs ceiling vs next wave\n")
    out.append("| course | lessons | graded items | lessons with a graded item | "
               "free-run only | fit for items | explanation-only | ceiling | ceiling gap | wave 1 |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for course, rs in sorted(by_course.items()):
        out.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            course, len(rs),
            sum(r["current"] for r in rs),
            sum(1 for r in rs if r["current"]),
            sum(1 for r in rs if r["existing_interaction"] == "free-run only"),
            sum(1 for r in rs if r["interactive_appropriate"] == "yes"),
            sum(1 for r in rs if r["explanation_only"] == "yes"),
            sum(r["target"] for r in rs),
            sum(r["gap"] for r in rs),
            sum(1 for r in rs if r["wave"] == "1"),
        ))
    out.append("| **all** | **{}** | **{}** | **{}** | **{}** | **{}** | **{}** | **{}** | **{}** | **{}** |".format(
        len(rows),
        sum(r["current"] for r in rows),
        sum(1 for r in rows if r["current"]),
        sum(1 for r in rows if r["existing_interaction"] == "free-run only"),
        sum(1 for r in rows if r["interactive_appropriate"] == "yes"),
        sum(1 for r in rows if r["explanation_only"] == "yes"),
        sum(r["target"] for r in rows),
        sum(r["gap"] for r in rows),
        sum(1 for r in rows if r["wave"] == "1"),
    ))
    out.append("\nThe ceiling column is NOT a to-do list. It is what the genres allow "
               "if every fitting lesson eventually carries items; waves decide the order.")

    out.append("\n## Interaction today (what a learner can actually do)\n")
    for kind, n in collections.Counter(r["existing_interaction"] for r in rows).most_common():
        out.append(f"  {kind:22s} {n:4d} lessons")

    out.append("\n## Verdict per lesson\n")
    for kind, n in collections.Counter(r["verdict"] for r in rows).most_common():
        out.append(f"  {kind:20s} {n:4d}")
    out.append("\n## Fit strength (the no-filler brake)\n")
    for kind, n in collections.Counter(r["tier"] for r in rows).most_common():
        out.append(f"  {kind:12s} {n:4d}  " + {
            "strong": "concept supports an item where the learner does something",
            "recall_only": "only a sentence can be tested - lowest priority, ship sparingly",
            "none": "no fit found from the lesson's own material",
        }[kind])

    eo = [r for r in rows if r["explanation_only"] == "yes"]
    out.append(f"\n## The {len(eo)} lessons judged explanation-only (every one listed, "
               "because this is the only place items are refused)\n")
    for r in eo:
        out.append(f"  {r['course']:<10} {r['lesson_id']:<26} {r['lesson_type']:<10} "
                   f"{r['lesson_title'][:52]}")

    out.append("\n## Composition of the remaining ceiling\n")
    prim = collections.Counter()
    routes = collections.Counter()
    for r in rows:
        if r["gap"] > 0 and r["kinds"]:
            prim[r["kinds"][0]] += 1
            routes[r["mechanically_verifiable"]] += 1
    for kind, n in prim.most_common():
        out.append(f"  primary type {kind:20s} {n:4d}")
    out.append("")
    for kind, n in routes.most_common():
        out.append(f"  verifiable={kind:9s} {n:4d} lessons")
    out.append("\n  'partial' = authored content, mechanically checked once written. No item is")
    out.append("  ever accepted without execution or an explicit answer key.")

    out.append("\n## Type mix now vs after wave 1\n")
    now = collections.Counter(k for r in rows for k in r["current_types"].split("|") if k)
    after = collections.Counter(now)
    for r in rows:
        if r["wave"] == "1":
            after[r["wave_type"]] += 1
    for kind in sorted(set(now) | set(after)):
        out.append(f"  {kind:20s} now {now[kind]:3d}  -> after wave 1 {after[kind]:3d}")

    out.append("\n## Wave 1 - the proposed next batch\n")
    for r in [x for x in rows if x["wave"] == "1"]:
        route = {"mechanical": "provable by execution",
                 "authored": "needs authored content"}[r["wave_route"]]
        out.append(f"  {r['course']:<10} {r['lesson_id']:<26} {r['lesson_type']:<10} "
                   f"{r['wave_type']:<17} {route:<22} {r['lesson_title'][:40]}")

    out.append("\n## Highest-value gaps, interleaved by course (top %d)\n" % top)
    out.append(f"{'course':<11} {'lesson':<26} {'type':<10} {'fit':<13} {'route':<7} "
               f"{'now':>3} {'ceil':>4} {'score':>6}  recommended")
    by_course: dict[str, list[dict]] = collections.defaultdict(list)
    for r in sorted(rows, key=lambda x: (-x["value_score"], x["lesson_id"])):
        if r["gap"] > 0 and r["kinds"]:
            by_course[r["course"]].append(r)
    # Round-robin so one starved course cannot bury the readout with 20 ties.
    listed = 0
    rank = 0
    while listed < top:
        took = False
        rank += 1
        for course in sorted(by_course):
            if rank > len(by_course[course]):
                continue
            r = by_course[course][rank - 1]
            route = {"yes": "mech", "partial": "author", "no": "none"}[
                r["mechanically_verifiable"]]
            out.append(f"{r['course']:<11} {r['lesson_id']:<26} {r['lesson_type']:<10} "
                       f"{r['interactive_appropriate']:<13} {route:<7} {r['current']:>3} "
                       f"{r['target']:>4} {r['value_score']:>6}  {', '.join(r['kinds'])}")
            listed += 1
            took = True
            if listed >= top:
                break
        if not took:
            break
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    rows = build_rows()
    out_dir = ROOT / "audit"
    out_dir.mkdir(exist_ok=True)
    write_csv(rows, out_dir / "coverage_plan.csv")
    if args.json:
        (out_dir / "coverage_plan.json").write_text(
            json.dumps([{k: v for k, v in r.items() if k != "kinds"} for r in rows], indent=2),
            encoding="utf-8")
    print(summarise(rows, args.top))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
