"""Wave 2: twelve authored items across the courses that had the least.

Weighted by what wave 1 measurement actually said:

* matching (~4% blind-guess) and select_multiple (~2%) are the best signal per
  authoring hour, so they get eight of the twelve.
* ``code`` items are the only type the audit proves end to end - the canonical
  solution must pass the item's own tests and the starter must fail them - so
  four are included, each practising a *different* skill from the one its
  lesson already asks for, never a duplicate of the lesson task.
* zero mcq, zero true_false, zero fill_blank. mcq is already a third of the
  catalogue and true_false has a 50% guess floor with unshuffled options.

Targets: typescript (was 7 lessons / 0 items), dsa (35 / 1), ml (25 / 1 after
wave 1), ml-math (25 / 1), fullstack (20 / 3).

Every stem is written from the lesson's own stated content - the descriptions,
objectives and code in the module files - so nothing asks the learner for
something the lesson never taught. This script is the source of truth for these
items; ``--replace`` re-applies a corrected version instead of hand-editing JSON.

    python -m backend.patch_wave2_items            # write them
    python -m backend.patch_wave2_items --replace   # re-apply corrections
    python -m backend.verify_wave2_execution        # prove the code items run
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from backend import console

console.configure()

CURRICULUM_ROOT = Path(__file__).resolve().parent.parent / "curriculum"

CODE_XP = 15
RECALL_XP = 10


def code_item(item_id: str, question: str, starter: str, solution: str,
              tests: list[dict]) -> dict:
    return {
        "id": item_id,
        "type": "code",
        "question": question,
        "starter_code": starter,
        "solution_code": solution,
        "tests": tests,
        "xp_reward": CODE_XP,
    }


def match_item(item_id: str, question: str, pairs: list[tuple[str, str]],
               explanation: str) -> dict:
    return {
        "id": item_id,
        "type": "matching",
        "question": question,
        "pairs": [{"left": left, "right": right} for left, right in pairs],
        "correct_answer": {left: right for left, right in pairs},
        "explanation": explanation,
        "xp_reward": RECALL_XP,
    }


def multi_item(item_id: str, question: str, options: list[str],
               answers: list[str], explanation: str) -> dict:
    return {
        "id": item_id,
        "type": "select_multiple",
        "question": question,
        "options": options,
        "correct_answer": answers,
        "explanation": explanation,
        "xp_reward": RECALL_XP,
    }


def sub(sublesson_id: str, title: str, exercises: list[dict]) -> dict:
    return {"id": sublesson_id, "title": title, "order": 1, "exercises": exercises}


# (course, lesson_id) -> sublesson
ITEMS: dict[tuple[str, str], dict] = {
    # ─────────────────────────── dsa: three items ───────────────────────────
    ("dsa", "linked-lists-step-2"): sub("ll-traverse-sub", "Write a traversal", [
        # The lesson builds prepend/len (head-side work). This asks for the
        # other half of list skill: walking next pointers until the end.
        code_item(
            "ll-sum-code-1",
            "Implement `sum_values(head)` that walks the list from `head` and "
            "returns the total of every `value`, or 0 for an empty list.",
            "class ListNode:\n"
            "    def __init__(self, value, next=None):\n"
            "        self.value = value\n"
            "        self.next = next\n"
            "\n"
            "def sum_values(head):\n"
            "    # TODO: walk the list, adding each value\n"
            "    return 0\n",
            "class ListNode:\n"
            "    def __init__(self, value, next=None):\n"
            "        self.value = value\n"
            "        self.next = next\n"
            "\n"
            "def sum_values(head):\n"
            "    total = 0\n"
            "    node = head\n"
            "    while node is not None:\n"
            "        total += node.value\n"
            "        node = node.next\n"
            "    return total\n",
            [
                {"name": "test_sum_values",
                 "unittest_code":
                     "def test_sum_values(self):\n"
                     "    head = ListNode(1, ListNode(2, ListNode(3)))\n"
                     "    self.assertEqual(sum_values(head), 6)\n"},
                {"name": "test_sum_empty",
                 "unittest_code":
                     "def test_sum_empty(self):\n"
                     "    self.assertEqual(sum_values(None), 0)\n"},
                {"name": "test_sum_single",
                 "unittest_code":
                     "def test_sum_single(self):\n"
                     "    self.assertEqual(sum_values(ListNode(7)), 7)\n"},
            ],
        ),
    ]),
    ("dsa", "graph-traversals-step-1"): sub("graph-repr-sub", "Match the operation", [
        match_item(
            "graph-repr-match-1",
            "This graph keeps an adjacency list and treats every edge as "
            "undirected. Match each call to what it does to `self.adj`.",
            [
                ("add_edge('a', 'b')", "'b' is listed under 'a' and 'a' under 'b'"),
                ("neighbors('a')", "a list of the nodes directly joined to 'a'"),
                ("neighbors('zzz')", "an empty list, because the node is absent"),
                ("add_edge('a', 'b') twice", "'b' appears under 'a' two times"),
            ],
            "Edges are stored in both directions, a missing node falls back to "
            "an empty list, and appending never de-duplicates.",
        ),
    ]),
    ("dsa", "hash-maps-step-2"): sub("twosum-hashmap-sub", "Select every true statement", [
        multi_item(
            "twosum-hashmap-multi-1",
            "The lesson's `two_sum` makes one pass with a dict called `seen`. "
            "Select every statement that is true of that approach.",
            [
                "`seen` maps each value it has passed to that value's index",
                "for each number it looks up `target - number` before storing it",
                "the returned pair is ordered as the earlier index then the later one",
                "it sorts the numbers before searching",
                "it compares every pair of numbers with two nested loops",
            ],
            ["`seen` maps each value it has passed to that value's index",
             "for each number it looks up `target - number` before storing it",
             "the returned pair is ordered as the earlier index then the later one"],
            "One pass, keyed by complement lookup: `seen[need]` is necessarily an "
            "earlier index than the current `i`. Sorting or nested loops are the "
            "slower approaches this lesson replaces.",
        ),
    ]),

    # ─────────────────────────── ml: two items ──────────────────────────────
    ("ml", "metrics-confusion"): sub("confusion-match-sub", "Match each count", [
        match_item(
            "confusion-match-1",
            "`confusion(y_true, y_pred)` counts four cases with positive = 1. "
            "Match each case to the branch that produces it.",
            [
                ("true positive", "actual 1 and predicted 1"),
                ("false positive", "actual 0 but predicted 1"),
                ("true negative", "actual 0 and predicted 0"),
                ("false negative", "actual 1 but predicted 0"),
            ],
            "The first word says whether the prediction was right; the second "
            "says which class was predicted.",
        ),
    ]),
    ("ml", "clf-knn"): sub("knn-rule-sub", "Select what the rule guarantees", [
        multi_item(
            "knn-rule-multi-1",
            "The lesson's classifier takes the majority vote of the `k` nearest "
            "labels in 1D and breaks a tie toward the smaller label. Select every "
            "statement that follows from that rule.",
            [
                "with k = 1 the nearest label alone decides",
                "a 1-1 tie between two labels returns the smaller label",
                "distance is measured as the absolute difference from `x`",
                "increasing `k` can change the predicted label",
                "the prediction is always the label of the farthest point",
            ],
            ["with k = 1 the nearest label alone decides",
             "a 1-1 tie between two labels returns the smaller label",
             "distance is measured as the absolute difference from `x`",
             "increasing `k` can change the predicted label"],
            "Voting is over the k nearest by absolute distance, and ties resolve "
            "downward; a larger k pulls more neighbours into the vote, so the "
            "winner can flip.",
        ),
    ]),

    # ────────────────────────── ml-math: three items ────────────────────────
    ("ml-math", "matrix-multiply"): sub("dot-code-sub", "Write the inner product", [
        code_item(
            "dot-code-1",
            "Implement `dot(a, b)` returning the sum of the elementwise products "
            "of two equal-length sequences - the inner operation `matvec` repeats "
            "for every row.",
            "def dot(a, b):\n"
            "    # TODO: multiply matching elements together and add them up\n"
            "    return 0\n",
            "def dot(a, b):\n"
            "    return sum(x * y for x, y in zip(a, b))\n",
            [
                {"name": "test_dot_basic",
                 "unittest_code":
                     "def test_dot_basic(self):\n"
                     "    self.assertEqual(dot([1, 2, 3], [4, 5, 6]), 32)\n"},
                {"name": "test_dot_zeros",
                 "unittest_code":
                     "def test_dot_zeros(self):\n"
                     "    self.assertEqual(dot([9, 8], [0, 0]), 0)\n"},
                {"name": "test_dot_negatives",
                 "unittest_code":
                     "def test_dot_negatives(self):\n"
                     "    self.assertEqual(dot([1, -2], [3, 4]), -5)\n"},
            ],
        ),
    ]),
    ("ml-math", "stats-median"): sub("median-cases-sub", "Match case to behaviour", [
        match_item(
            "median-cases-match-1",
            "`median(xs)` sorts a copy of a non-empty list. Match each input case "
            "to what the function must do.",
            [
                ("odd length", "the single middle value of the sorted copy"),
                ("even length", "the mean of the two middle values"),
                ("input in random order", "sort a copy, leaving the caller's list alone"),
                ("repeated values", "count each repeat, because length decides the middle"),
            ],
            "The middle is chosen after sorting and depends only on length, so "
            "duplicates are ordinary members of the list.",
        ),
    ]),
    ("ml-math", "scale-standardize"): sub("standardize-zero-sub", "Select the all-zero results", [
        multi_item(
            "standardize-zero-multi-1",
            "`standardize(xs)` returns all zeros exactly when the population "
            "variance is 0. Select every input that produces an all-zero result.",
            ["[5, 5, 5]", "[0, 0]", "[7]", "[1, 2, 3]", "[1, 0]"],
            ["[5, 5, 5]", "[0, 0]", "[7]"],
            "Variance is 0 only when no value differs from the mean: identical "
            "values, and any single-element list. [1, 2, 3] and [1, 0] both "
            "spread around their mean.",
        ),
    ]),

    # ─────────────────────── typescript: three items ────────────────────────
    ("typescript", "ts-01"): sub("ts-annotations-sub", "Match annotation to values", [
        match_item(
            "ts-annotations-match-1",
            "TypeScript annotates JavaScript's primitives with lowercase type "
            "names. Match each annotation to the values it accepts.",
            [
                (": string", "text such as 'Alice'"),
                (": number", "42 and 3.5 alike"),
                (": boolean", "true or false only"),
                (") : string", "the type of the value the function hands back"),
            ],
            "Parameter annotations sit before the parameter, the return "
            "annotation after the parentheses, and `number` covers integers and "
            "decimals.",
        ),
    ]),
    ("typescript", "ts-02"): sub("ts-narrow-code-sub", "Write the type guard", [
        code_item(
            "ts-narrow-code-1",
            "Implement the exported `describe(input: number | string): string` so "
            "it returns 'number' for a number and 'string' for a string, using a "
            "`typeof` check to narrow the union.",
            "export function describe(input: number | string): string {\n"
            "    // TODO: narrow the union before choosing a label\n"
            "    return '';\n"
            "}\n",
            "export function describe(input: number | string): string {\n"
            "    return typeof input === 'number' ? 'number' : 'string';\n"
            "}\n",
            [
                {"name": "test_describe_number",
                 "test_code": "if (solution.describe(7) !== 'number') throw new Error('number case failed');"},
                {"name": "test_describe_string",
                 "test_code": "if (solution.describe('seven') !== 'string') throw new Error('string case failed');"},
                {"name": "test_describe_zero",
                 "test_code": "if (solution.describe(0) !== 'number') throw new Error('zero case failed');"},
            ],
        ),
    ]),
    ("typescript", "ts-03"): sub("ts-generics-sub", "Select the valid declarations", [
        multi_item(
            "ts-generics-multi-1",
            "This lesson's `Box<T>` must stay in plain erasable TypeScript: the "
            "field is declared on the class and assigned in the constructor. "
            "Select every declaration the lesson allows.",
            [
                "private value: T; declared on the class",
                "this.value = value inside the constructor",
                "getValue(): T returning the stored value",
                "constructor(private value: T) parameter-property shorthand",
            ],
            ["private value: T; declared on the class",
             "this.value = value inside the constructor",
             "getValue(): T returning the stored value"],
            "Parameter-property shorthand is TypeScript-only syntax that no "
            "erasable-syntax runtime understands, so the field has to be declared "
            "and assigned explicitly.",
        ),
    ]),

    # ───────────────────────── fullstack: one item ──────────────────────────
    ("fullstack", "fs-state-reducer"): sub("reducer-dec-sub", "Extend the reducer", [
        code_item(
            "reducer-dec-code-1",
            "Extend the reducer: implement `reduce(state, action)` for a "
            "`{'count': int}` state so `{'type': 'dec'}` lowers the count by one "
            "and an unknown type returns the state unchanged. Never mutate the "
            "old state object.",
            "def reduce(state, action):\n"
            "    t = action.get('type')\n"
            "    if t == 'inc':\n"
            "        return {'count': state['count'] + 1}\n"
            "    # TODO: handle 'dec', and leave the state alone for anything else\n"
            "    return state\n",
            "def reduce(state, action):\n"
            "    t = action.get('type')\n"
            "    if t == 'inc':\n"
            "        return {'count': state['count'] + 1}\n"
            "    if t == 'dec':\n"
            "        return {'count': state['count'] - 1}\n"
            "    return state\n",
            [
                {"name": "test_dec",
                 "unittest_code":
                     "def test_dec(self):\n"
                     "    self.assertEqual(reduce({'count': 3}, {'type': 'dec'}), {'count': 2})\n"},
                {"name": "test_unknown_action_keeps_state",
                 "unittest_code":
                     "def test_unknown_action_keeps_state(self):\n"
                     "    self.assertEqual(reduce({'count': 5}, {'type': 'nope'}), {'count': 5})\n"},
                {"name": "test_inc_still_works",
                 "unittest_code":
                     "def test_inc_still_works(self):\n"
                     "    self.assertEqual(reduce({'count': 0}, {'type': 'inc'}), {'count': 1})\n"},
                {"name": "test_returns_a_new_object",
                 "unittest_code":
                     "def test_returns_a_new_object(self):\n"
                     "    original = {'count': 1}\n"
                     "    result = reduce(original, {'type': 'dec'})\n"
                     "    self.assertEqual(original, {'count': 1})\n"
                     "    self.assertIsNot(original, result)\n"},
            ],
        ),
    ]),
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
            sublesson = ITEMS.get((course, str(lesson.get("id")).lower()))
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
                existing["exercises"] = sublesson["exercises"]
                existing["title"] = sublesson["title"]
                touched = True
                written.append(f"{course}/{lesson['id']} (replaced)")
            else:
                print(f"  already present: {course}/{lesson['id']} (pass --replace)")
        if touched:
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    matched = {w.split(" ")[0] for w in written}
    missing = {f"{c}/{l}" for (c, l) in ITEMS} - matched
    if missing:
        print(f"  !! no lesson matched for: {', '.join(sorted(missing))}")
    return written


def prove_code_items() -> list[str]:
    """Execution-prove every code item before anything is written.

    The same bar ``verify_lessons`` applies afterwards, applied here so an
    unprovable item never reaches a curriculum file: the canonical solution must
    pass the item's own tests, and the starter must fail them. A code item whose
    starter already passes is a solved exercise, and one whose solution fails is
    a broken answer key - both are worse than no item.
    """
    from backend.verify_lessons import LOCAL_LANGS, eval_code

    problems: list[str] = []
    for (course, lesson_id), sublesson in ITEMS.items():
        for exercise in sublesson["exercises"]:
            if exercise["type"] != "code":
                continue
            label = f"{course}/{lesson_id}/{exercise['id']}"
            tests = exercise["tests"]
            use_docker = course not in LOCAL_LANGS
            passed = eval_code(course, exercise["solution_code"], tests, use_docker)
            if not passed["all_pass"]:
                problems.append(
                    f"{label}: solution does not pass its own tests "
                    f"({', '.join(passed['failed']) or passed['error']})")
                continue
            started = eval_code(course, exercise["starter_code"], tests, use_docker)
            if started["syntax_error"]:
                problems.append(f"{label}: starter does not even compile/run")
            elif started["all_pass"]:
                problems.append(f"{label}: starter already passes - the item ships solved")
            else:
                print(f"  proven: {label} (solution passes, starter fails)")
    return problems


def main() -> int:
    code_items = sum(1 for s in ITEMS.values() for e in s["exercises"]
                     if e["type"] == "code")
    print(f"execution-proving {code_items} code items...")
    problems = prove_code_items()
    if problems:
        print("\nrefusing to write: code items failed the execution proof")
        for problem in problems:
            print("  -", problem)
        return 1

    written = apply_items(replace="--replace" in sys.argv)
    print(f"\nwave 2 items written: {len(written)} of {len(ITEMS)}")
    for item in written:
        print(f"  + {item}")
    return 0 if len(written) == len(ITEMS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
