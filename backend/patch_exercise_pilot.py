"""Hand-authored pilot: one recall item per lesson, across 7 types and 6 courses.

Every item is derived from a stated learning objective of the lesson it sits in,
and each is placed as a warm-up *before* the lesson's own write-from-scratch
task. Nothing here is machine-generated filler: the distractors are the mistakes
the concept actually invites.
"""

import json
import pathlib
import re

ROOT = pathlib.Path('curriculum')

# lesson id -> (sublesson title, exercise)
PILOT: dict[str, dict] = {
    # ---- true/false: the role/content contract of a chat payload ----------
    "ai-01": {
        "title": "Reading a request payload",
        "exercise": {
            "id": "ai-01-tf-1",
            "type": "true_false",
            "question": (
                "In a chat-completion request, every entry in the `messages` array "
                "carries both a `role` and a `content`."
            ),
            "micro_explanation": (
                "The API needs to know who said each line, not just the text."
            ),
            # Spelled out rather than relying on the widget's True/False
            # fallback, so the answer set travels with the data.
            "options": ["True", "False"],
            "correct_answer": "True",
            "explanation": (
                "Each message names its author through `role` (system, user or "
                "assistant) and carries the text for that turn in `content`."
            ),
            "xp_reward": 10,
        },
    },
    # ---- multiple choice: pointer indirection -----------------------------
    "cpp-ptr-01": {
        "title": "Reading through a pointer",
        "exercise": {
            "id": "cpp-ptr-01-mcq-1",
            "type": "mcq",
            "question": (
                "Given `int value = 7;` and `int* ptr = &value;`, which expression "
                "reaches the number `value` holds *through the pointer*?"
            ),
            "options": ["*ptr", "ptr", "&value", "ptr->value"],
            "correct_answer": "*ptr",
            "explanation": (
                "`*ptr` dereferences the address and yields the pointed-to object. "
                "`ptr` alone is the address, and `&value` just recomputes it."
            ),
            "xp_reward": 10,
        },
    },
    # ---- select multiple: which headers are genuinely required ------------
    "cpp-perf-01": {
        "title": "Headers for std::sort",
        "exercise": {
            "id": "cpp-perf-01-multi-1",
            "type": "select_multiple",
            "question": (
                "A file calls `std::sort` on a `std::vector<int>`. Which headers must "
                "it include? Select all that apply."
            ),
            "options": ["<algorithm>", "<vector>", "<string>", "<cstring>"],
            "correct_answer": ["<algorithm>", "<vector>"],
            "explanation": (
                "`std::sort` is declared in <algorithm> and the container itself "
                "needs <vector>; the other two are unrelated."
            ),
            "xp_reward": 15,
        },
    },
    # ---- multiple choice: map's return contract ---------------------------
    "js-05": {
        "title": "What map gives back",
        "exercise": {
            "id": "js-05-mcq-1",
            "type": "mcq",
            "question": "What does `numbers.map(double)` return?",
            "options": [
                "a brand new array holding each transformed value",
                "the original array, changed in place",
                "a single accumulated total",
                "undefined, because the callback has no return value",
            ],
            "correct_answer": "a brand new array holding each transformed value",
            "explanation": (
                "`map` never mutates its receiver: it builds and returns a new array "
                "of the callback's results."
            ),
            "xp_reward": 10,
        },
    },
    # ---- output prediction: floor division ---------------------------------
    "numbers-01": {
        "title": "Predict the value",
        "exercise": {
            "id": "numbers-01-out-1",
            "type": "output_prediction",
            "question": "What does `17 // 5` evaluate to in Python?",
            "options": ["3", "3.4", "2", "4"],
            "correct_answer": "3",
            "explanation": (
                "`//` is floor division: 17 divided by 5 is 3.4, and flooring gives "
                "3. `/` would have produced 3.4."
            ),
            "xp_reward": 10,
        },
    },
    # ---- debugging: branch order, the classic threshold trap --------------
    "conditionals-01": {
        "title": "Find the bug",
        "exercise": {
            "id": "conditionals-01-dbg-1",
            "type": "debugging",
            "question": (
                "This grader should return \"A\" for a score of 95 but returns "
                "\"B\" instead. Why?\n\n"
                "if score >= 80:\n    return \"B\"\nelif score >= 90:\n    return \"A\""
            ),
            "options": [
                "The 80 test matches first, so the 90 branch is never reached",
                "`elif` cannot follow a plain `if`",
                "90 is not greater than 80",
                "Python compares the strings \"A\" and \"B\", not the numbers",
            ],
            "correct_answer": "The 80 test matches first, so the 90 branch is never reached",
            "explanation": (
                "`if`/`elif` stops at the first true test, so the narrowest threshold "
                "must be checked first (90 before 80)."
            ),
            "xp_reward": 15,
        },
    },
    # ---- matching: clause to purpose --------------------------------------
    "sql-03": {
        "title": "Match clause to purpose",
        "exercise": {
            "id": "sql-03-match-1",
            "type": "matching",
            "question": "Match each SQL clause to the job it does in a query.",
            "pairs": [
                {"left": "WHERE", "right": "keeps only the rows that pass a test"},
                {"left": "LIKE", "right": "matches a text pattern with % and _"},
                {"left": "IN", "right": "matches any value from a listed set"},
                {"left": "BETWEEN", "right": "matches values inside a range"},
            ],
            "correct_answer": {
                "WHERE": "keeps only the rows that pass a test",
                "LIKE": "matches a text pattern with % and _",
                "IN": "matches any value from a listed set",
                "BETWEEN": "matches values inside a range",
            },
            "explanation": (
                "All four filter rows; they differ in *how* a row is matched — a test, "
                "a pattern, a set, or a range."
            ),
            "xp_reward": 15,
        },
    },
}

# js-05's starter still recites the solution; replace it with a real skeleton.
STARTER_FIXES = {
    "js-05": (
        "// TODO: build a new array with every value doubled\n"
        "function doubleAll(numbers) {\n"
        "    return [];\n"
        "}\n"
        "module.exports = { doubleAll };\n"
    ),
}


def main(dry_run: bool = False) -> int:
    changed: list[str] = []
    for path in sorted(ROOT.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        touched = False
        for lesson in payload.get("lessons") or []:
            if not isinstance(lesson, dict):
                continue
            lesson_id = lesson.get("id")
            if lesson_id in STARTER_FIXES and lesson.get("starter_code") != STARTER_FIXES[lesson_id]:
                lesson["starter_code"] = STARTER_FIXES[lesson_id]
                touched = True
                changed.append(f"{lesson_id} (starter)")
            spec = PILOT.get(lesson_id)
            if not spec:
                continue
            if lesson.get("sublessons"):
                print(f"  skip {lesson_id}: already has sublessons")
                continue
            exercise = dict(spec["exercise"])
            lesson["sublessons"] = [
                {
                    "id": f"{exercise['id']}-sub",
                    "title": spec["title"],
                    "order": 1,
                    "exercises": [exercise],
                }
            ]
            touched = True
            changed.append(f"{lesson_id}/{exercise['id']}")
        if touched and not dry_run:
            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
    print(f"{'would write' if dry_run else 'wrote'} {len(changed)} items:")
    for c in changed:
        print("   ", c)
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(dry_run="--dry-run" in sys.argv))
