"""Wave 1 of the coverage plan: five authored items, one per course, varied types.

Why authored and not generated: three mechanical routes were tried against these
lessons and all three came back empty at a fair bar -

* ordering: 0 of 334 lessons clear the existing execution proof (canonical order
  must pass *and* every adjacent swap must fail);
* code completion: the only blanks that survive the uniqueness proof ask the
  learner to guess a name the lesson author invented (`return '&'.join(parts)`),
  which is provable but not fair;
* output prediction from the lesson's own program: 0 lessons print anything,
  because the solutions are test-graded functions, and adding a probe call plus
  the operator-mutation library still did not reach three distinct outcomes.

So these five are hand-authored, and every quantitative option below was
*produced by running the variant that yields it* - see the `-- executed` notes
inline. Nothing here is a plausible-sounding number.

Idempotent: re-running reports "already present" and changes nothing.

    python -m backend.patch_wave1_items            # write the five items
    python -m backend.verify_pilot_grading         # grade each right and wrong
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from backend import console

console.configure()

CURRICULUM_ROOT = Path(__file__).resolve().parent.parent / "curriculum"

BIG_O_PROGRAM = (
    "def linear_sum(n):\n"
    "    total = 0\n"
    "    for i in range(1, n + 1):\n"
    "        total += i\n"
    "    return total\n"
    "\n"
    "print(linear_sum(5))\n"
)

ZSCORE_PROGRAM = (
    "def zscore(x, mu, sigma):\n"
    "    return (x - mu) / sigma\n"
    "\n"
    "print(zscore(10, 8, 2))\n"
)

# (course, lesson_id) -> sublesson. Written into that lesson's `sublessons`.
ITEMS: dict[tuple[str, str], dict] = {
    # ── dsa: loop bounds, all four values executed ──────────────────────────
    ("dsa", "big-o-step-1"): {
        "id": "big-o-step-1-out-sub",
        "title": "Predict the output",
        "order": 1,
        "exercises": [{
            "id": "big-o-step-1-out-1",
            "type": "output_prediction",
            "question": f"What does this program print?\n\n```python\n{BIG_O_PROGRAM}```",
            # executed: canonical -> 15, range(1, n) -> 10, range(1, n + 2) -> 21.
            # range(n + 1) was also executed and gave 15, so it is deliberately
            # not offered: a duplicate of the answer would make two options right.
            "options": ["10", "15", "21"],
            "correct_answer": "15",
            "explanation": (
                "range(1, 6) yields 1, 2, 3, 4 and 5, which add to 15. "
                "10 is what stopping one early (range(1, n)) gives; 21 is what "
                "one extra iteration (range(1, n + 2)) gives."
            ),
            "xp_reward": 10,
        }],
    },
    # ── ml-math: the z-score formula, all four values executed ──────────────
    ("ml-math", "stats-zscore"): {
        "id": "stats-zscore-out-sub",
        "title": "Predict the output",
        "order": 1,
        "exercises": [{
            "id": "stats-zscore-out-1",
            "type": "output_prediction",
            "question": f"What does this program print?\n\n```python\n{ZSCORE_PROGRAM}```",
            # executed: (x-mu)/sigma -> 1.0, (mu-x)/sigma -> -1.0,
            # (x-mu)*sigma -> 4, x - mu/sigma -> 6.0
            "options": ["4", "-1.0", "1.0", "6.0"],
            "correct_answer": "1.0",
            "explanation": (
                "(10 - 8) / 2 is 1.0. -1.0 is the subtracted the wrong way round, "
                "4 comes from multiplying by sigma instead of dividing, and 6.0 "
                "comes from dropping the brackets so only mu is divided."
            ),
            "xp_reward": 10,
        }],
    },
    # ── javascript: the arrow-function form the lesson asks for ─────────────
    ("javascript", "js-02"): {
        "id": "js-02-tf-sub",
        "title": "Check the idea",
        "order": 1,
        "exercises": [{
            "id": "js-02-tf-1",
            "type": "true_false",
            "options": ["True", "False"],
            # Deliberately False. Measurement showed both true_false items in the
            # catalogue answering "True", and the UI keeps True/False in fixed
            # order, so a learner who always taps the first option passed every
            # one. The false form is also the more instructive claim here: it
            # targets the exact mistake the lesson's own code avoids.
            "question": (
                "In `const createButton = (text) => { tag: 'button' }` the braces "
                "hand back that object, so an arrow function never needs "
                "parentheses around a returned object literal."
            ),
            "correct_answer": "False",
            "explanation": (
                "With braces, `{` opens the function body, so `tag: 'button'` is a "
                "labelled statement and the function returns undefined. Wrapping the "
                "object in parentheses - `=> ({ tag: 'button' })` - is what makes it "
                "the value handed back."
            ),
            "xp_reward": 10,
        }],
    },
    # ── sql: the three constraints this lesson's own table declares ─────────
    ("sql", "sql-11"): {
        "id": "sql-11-match-sub",
        "title": "Match each constraint to what it guarantees",
        "order": 1,
        "exercises": [{
            "id": "sql-11-match-1",
            "type": "matching",
            "question": (
                "The `projects` table in this lesson declares three constraints "
                "and a column type. Match each to what it guarantees."
            ),
            "pairs": [
                {"left": "PRIMARY KEY", "right": "one row per value, and it is never missing"},
                {"left": "NOT NULL", "right": "the column must be given a value"},
                {"left": "CHECK (budget >= 0)", "right": "rejects a value outside the allowed range"},
                {"left": "REAL", "right": "stores a decimal number, not a whole number"},
            ],
            "correct_answer": {
                "PRIMARY KEY": "one row per value, and it is never missing",
                "NOT NULL": "the column must be given a value",
                "CHECK (budget >= 0)": "rejects a value outside the allowed range",
                "REAL": "stores a decimal number, not a whole number",
            },
            "explanation": (
                "`id INTEGER PRIMARY KEY` both identifies the row and implies it is "
                "present; NOT NULL only requires a value; CHECK is the range test; "
                "REAL is the floating-point type."
            ),
            "xp_reward": 10,
        }],
    },
    # ── ai: exactly the keys this lesson's tool JSON contains ───────────────
    ("ai", "ai-02"): {
        "id": "ai-02-multi-sub",
        "title": "Select every part of a tool definition",
        "order": 1,
        "exercises": [{
            "id": "ai-02-multi-1",
            "type": "select_multiple",
            "question": (
                "A tool definition is JSON that lets a model trigger a local "
                "function. Select every key that belongs in the definition this "
                "lesson builds for `run_sql_query`."
            ),
            "options": [
                "type", "name", "description", "parameters", "temperature", "api_key",
            ],
            "correct_answer": ["type", "name", "description", "parameters"],
            "explanation": (
                "The definition carries the tool's `type` ('function'), its `name`, a "
                "`description` the model reads, and a JSON-schema `parameters` object. "
                "`temperature` is a generation setting and `api_key` is a credential - "
                "neither belongs in a tool declaration."
            ),
            "xp_reward": 10,
        }],
    },
}


def apply_items(replace: bool = False) -> list[str]:
    written: list[str] = []
    for path in sorted(CURRICULUM_ROOT.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or not payload.get("lessons"):
            continue
        course = path.relative_to(CURRICULUM_ROOT).parts[0].lower()
        touched = False
        for lesson in payload["lessons"]:
            key = (course, str(lesson.get("id")).lower())
            sublesson = ITEMS.get(key) or ITEMS.get((course, str(lesson.get("id"))))
            if not sublesson:
                continue
            sublessons = lesson.setdefault("sublessons", [])
            existing = next((s for s in sublessons if s.get("id") == sublesson["id"]), None)
            if existing is None:
                sublessons.append(sublesson)
                sublessons.sort(key=lambda s: s.get("order", 1))
                touched = True
                written.append(f"{course}/{lesson['id']}")
            elif replace:
                # Keep the authoring correction path honest: the script stays the
                # source of truth for these items, so a measured fix can be
                # re-applied instead of hand-editing JSON.
                existing["exercises"] = sublesson["exercises"]
                existing["title"] = sublesson["title"]
                touched = True
                written.append(f"{course}/{lesson['id']} (replaced)")
            else:
                print(f"  already present: {course}/{lesson['id']} (pass --replace to update)")
        if touched:
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    missing = {f"{c}/{l}" for (c, l) in ITEMS} - {w.split(' ')[0] for w in written}
    if missing:
        print(f"  !! no lesson matched for: {', '.join(sorted(missing))}")
    return written


def main() -> int:
    written = apply_items(replace="--replace" in sys.argv)
    print(f"\nwave 1 items written: {len(written)}")
    for item in written:
        print(f"  + {item}")
    return 0 if written or "--allow-empty" in sys.argv else 1


if __name__ == "__main__":
    raise SystemExit(main())
