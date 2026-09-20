"""Classify lessons by which interactive item their concept actually supports.

Purpose: decide where exercises are genuinely warranted before generating any,
rather than padding 334 lessons to make a count look good. Each lesson is
scored against the item types it can support with material that already exists
in the lesson, and the dominant concept shape is recorded.
"""

from __future__ import annotations

import collections
import re
from pathlib import Path

from backend.curriculum_loader import load_all_curriculums

# Concept families, keyed by signals in the lesson's own text.
FAMILY_RULES = [
    ("syntax-api recall", re.compile(r"\bmethod|operator|keyword|syntax|function\b", re.I)),
    ("code reading / output", re.compile(r"\boutput|prints|returns|evaluate|result of\b", re.I)),
    ("control flow", re.compile(r"\bif\b|else|elif|loop|for |while|branch|condition", re.I)),
    ("data structure", re.compile(r"\blist|dict|tuple|set|stack|queue|tree|hash|array|class\b", re.I)),
    ("transformation pipeline", re.compile(r"\bmap|filter|sort|join|split|convert|parse|encode|decode\b", re.I)),
    ("math / algorithm", re.compile(r"\bsum|average|formula|complexity|big o|recursive|binary|prime|modulo\b", re.I)),
    ("query language", re.compile(r"\bselect|where|join|group by|table|column|query|null\b", re.I)),
    ("async / state", re.compile(r"\bpromise|async|await|callback|state|render|event\b", re.I)),
]


def supports(lesson) -> set[str]:
    """Item types this lesson can back with material it already contains."""
    kinds: set[str] = set()
    solution = lesson.solution_code or ""
    starter = lesson.starter_code or ""
    objectives = " ".join(lesson.learning_objectives or [])
    tests = " ".join((t.unittest_code or "") + (t.expected_stdout or "") for t in lesson.tests)
    blob = " ".join([lesson.description or "", objectives, solution, tests])

    statements = [l for l in solution.split("\n") if l.strip() and not re.match(r"^\s*(#|import|from|//)", l)]
    if len([l for l in statements if re.match(r"^\s*\S", l)]) >= 3:
        kinds.add("ordering")
    if re.search(r"print\s*\(", solution) or lesson.type == "output_prediction":
        kinds.add("output_prediction")
    if re.search(r"\bdef\s+\w+\s*\(", solution) or "return" in solution:
        kinds.add("tiny_coding")
        kinds.add("code_completion")
        kinds.add("full_coding")
    if objectives:
        # Declarative objectives are factual claims: usable for recall items,
        # but only if the claim is short enough to be a proposition.
        short = [o for o in (lesson.learning_objectives or []) if 15 <= len(o) <= 110]
        if len(short) >= 2:
            kinds.add("mcq")
            kinds.add("true_false")
    if re.search(r"\b(and|or|not|both|either|only if|unless)\b", blob, re.I):
        kinds.add("select_multiple")
    if len(re.findall(r"\b\w+\s*=\s*\w+", starter)) >= 2 or re.search(r"key-value|mapping|pairs?", blob, re.I):
        kinds.add("matching")
    if re.search(r"\bwhat does|which (?:line|statement|value)|shortly|in words\b", blob, re.I):
        kinds.add("short_answer")
    if re.search(r"\bbug|error|fix|wrong|incorrect|traceback|exception", blob, re.I):
        kinds.add("debugging")
    return kinds


def family(lesson) -> str:
    blob = " ".join([lesson.title or "", lesson.description or "", " ".join(lesson.learning_objectives or [])])
    for name, pattern in FAMILY_RULES:
        if pattern.search(blob):
            return name
    return "other"


def main() -> None:
    curriculums = load_all_curriculums()
    per_type = collections.Counter()
    per_family = collections.Counter()
    coverage = collections.Counter()
    by_course_type = collections.defaultdict(collections.Counter)
    unsupported: list[str] = []

    for language, curriculum in sorted(curriculums.items()):
        for lesson in curriculum.lessons:
            kinds = supports(lesson)
            fam = family(lesson)
            per_family[fam] += 1
            if not kinds:
                unsupported.append(f"{language}/{lesson.id}")
                continue
            coverage["lessons with >=1 supported type"] += 1
            for kind in kinds:
                per_type[kind] += 1
                by_course_type[fam][kind] += 1

    total = sum(per_family.values())
    print(f"lessons: {total}\n")
    print("CONCEPT FAMILIES (what the lesson teaches)")
    for name, count in per_family.most_common():
        print(f"  {name:24s} {count:4d}  {count/total:5.1%}")
    print("\nITEM TYPES EACH LESSON COULD SUPPORT (a lesson counts in several)")
    for name, count in per_type.most_common():
        print(f"  {name:20s} {count:4d}  {count/total:5.1%}")
    print(f"\nlessons with no supportable item type: {len(unsupported)}")
    print(f"  {', '.join(unsupported[:12])}{' ...' if len(unsupported) > 12 else ''}")
    print("\nBEST FIT BY CONCEPT FAMILY (top 3 types per family)")
    for fam, counts in sorted(by_course_type.items(), key=lambda kv: -per_family[kv[0]]):
        top = ", ".join(f"{k}:{v}" for k, v in counts.most_common(3))
        print(f"  {fam:24s} n={per_family[fam]:4d}  {top}")


if __name__ == "__main__":
    main()
