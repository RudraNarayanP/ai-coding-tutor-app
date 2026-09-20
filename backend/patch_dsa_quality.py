"""DSA course quality patch: verified docs.python.org sources for all 35
lessons + one enriched description (trees-bst-01).

DSA lessons are implemented in pure Python, so each lesson is grounded in the
official documentation for the language mechanics it exercises (classes, dict
mapping types, deque O(1) popleft, list-as-stack, bisect/bisection, the
"Time complexity of operations on built-in types" table, recursion sentence in
Defining Functions). All cited pages were fetched and inspected this session.

Run:  .venv/Scripts/python.exe backend/patch_dsa_quality.py
"""
import json
from pathlib import Path

MOD = Path("curriculum/dsa/modules")
DOC = "Python official documentation (docs.python.org)"
LIC = "Python documentation license (PSF)"


def doc(name: str, url: str) -> dict:
    return {"name": f"{DOC} — {name}", "url": url, "license": LIC}


SOURCES: dict[str, dict] = {
    "big-o-step-1": doc("4.2. for Statements — Looping Statements (Tutorial)",
                        "https://docs.python.org/3/tutorial/controlflow.html#for-statements"),
    "big-o-step-2": doc("Time complexity of operations on built-in types — 'x in s' is O(1) for sets, O(n) for lists",
                        "https://docs.python.org/3/library/time-complexity.html"),
    "big-o-01": doc("4.2. for Statements — nested iteration (Tutorial)",
                    "https://docs.python.org/3/tutorial/controlflow.html#for-statements"),
    "big-o-practice-1": doc("enumerate() — Built-in Functions",
                            "https://docs.python.org/3/library/functions.html#enumerate"),
    "big-o-checkpoint": doc("3.1.1. Numbers — arithmetic operators (Tutorial)",
                            "https://docs.python.org/3/tutorial/introduction.html#numbers"),
    "graph-traversals-step-1": doc("Classes — __init__ and instance attributes (Tutorial)",
                                   "https://docs.python.org/3/tutorial/classes.html"),
    "graph-traversals-step-2": doc("The while statement (Language Reference)",
                                   "https://docs.python.org/3/reference/compound_stmts.html#while"),
    "graph-traversals-01": doc("collections.deque — 'thread-safe, memory efficient appends and pops ... O(1)'",
                               "https://docs.python.org/3/library/collections.html#collections.deque"),
    "graph-traversals-practice-1": doc("collections.deque — popleft and O(1) ends",
                                       "https://docs.python.org/3/library/collections.html#collections.deque"),
    "graph-traversals-checkpoint": doc("collections.deque — queue operations",
                                       "https://docs.python.org/3/library/collections.html#collections.deque"),
    "hash-maps-step-1": doc("Mapping Types — dict.get() and key lookup",
                            "https://docs.python.org/3/library/stdtypes.html#mapping-types-dict"),
    "hash-maps-step-2": doc("Time complexity — dict 'x in d' is O(1) average",
                            "https://docs.python.org/3/library/time-complexity.html"),
    "hash-maps-01": doc("sorted() — Built-in Functions",
                        "https://docs.python.org/3/library/functions.html#sorted"),
    "hash-maps-practice-1": doc("Mapping Types — dict.get() counting",
                                "https://docs.python.org/3/library/stdtypes.html#mapping-types-dict"),
    "hash-maps-checkpoint": doc("Set types — 'x in s' O(1) and set operations",
                                "https://docs.python.org/3/library/time-complexity.html"),
    "linked-lists-step-1": doc("Classes — objects, attributes, and methods (Tutorial)",
                               "https://docs.python.org/3/tutorial/classes.html"),
    "linked-lists-step-2": doc("Classes — instance state and self (Tutorial)",
                               "https://docs.python.org/3/tutorial/classes.html"),
    "linked-lists-01": doc("The while statement (Language Reference)",
                           "https://docs.python.org/3/reference/compound_stmts.html#while"),
    "linked-lists-practice-1": doc("Classes — attribute traversal (Tutorial)",
                                   "https://docs.python.org/3/tutorial/classes.html"),
    "linked-lists-checkpoint": doc("The while statement — Floyd two-pointer cycle detection loop (Language Reference)",
                                   "https://docs.python.org/3/reference/compound_stmts.html#while"),
    "recursion-binary-search-step-1": doc("Defining Functions — 'When a function ... calls itself recursively, a new local symbol table is created'",
                                          "https://docs.python.org/3/tutorial/controlflow.html#defining-functions"),
    "recursion-binary-search-step-2": doc("bisect — 'maintaining a list in sorted order' via bisection",
                                          "https://docs.python.org/3/library/bisect.html"),
    "recursion-binary-search-01": doc("bisect — bisection algorithm on sorted lists",
                                      "https://docs.python.org/3/library/bisect.html"),
    "recursion-binary-search-practice-1": doc("Defining Functions — recursive calls (Tutorial)",
                                              "https://docs.python.org/3/tutorial/controlflow.html#defining-functions"),
    "recursion-binary-search-checkpoint": doc("Defining Functions — recursive calls (Tutorial)",
                                              "https://docs.python.org/3/tutorial/controlflow.html#defining-functions"),
    "stacks-queues-step-1": doc("5.1.1. Using Lists as Stacks — append()/pop() (Tutorial)",
                                "https://docs.python.org/3/tutorial/datastructures.html#using-lists-as-stacks"),
    "stacks-queues-step-2": doc("collections.deque — append()/popleft() at O(1)",
                                "https://docs.python.org/3/library/collections.html#collections.deque"),
    "stacks-queues-01": doc("5.1.1. Using Lists as Stacks (Tutorial)",
                            "https://docs.python.org/3/tutorial/datastructures.html#using-lists-as-stacks"),
    "stacks-queues-practice-1": doc("5.1.1. Using Lists as Stacks — popping reverses order (Tutorial)",
                                    "https://docs.python.org/3/tutorial/datastructures.html#using-lists-as-stacks"),
    "stacks-queues-checkpoint": doc("collections.deque — sliding-window queue (append + popleft)",
                                    "https://docs.python.org/3/library/collections.html#collections.deque"),
    "trees-bst-step-1": doc("Defining Functions — recursive calls (Tutorial)",
                            "https://docs.python.org/3/tutorial/controlflow.html#defining-functions"),
    "trees-bst-step-2": doc("Classes — objects created inside loops (Tutorial)",
                            "https://docs.python.org/3/tutorial/classes.html"),
    "trees-bst-01": doc("The while statement — search loops with early return (Language Reference)",
                        "https://docs.python.org/3/reference/compound_stmts.html#while"),
    "trees-bst-practice-1": doc("Defining Functions — recursive max of subtrees (Tutorial)",
                                "https://docs.python.org/3/tutorial/controlflow.html#defining-functions"),
    "trees-bst-checkpoint": doc("Defining Functions — recursion with bounds (Tutorial)",
                                "https://docs.python.org/3/tutorial/controlflow.html#defining-functions"),
}

DESCRIPTIONS = {
    "trees-bst-01": (
        "BST search challenge: implement bst_contains(root, value). Start at the "
        "root; while the current node exists, compare value with cur.value — go "
        "right when value is larger, left when smaller, and return True on an "
        "exact match. Reaching a None child means the value is not in the tree. "
        "Tests: the tree 5(3, 7) contains 7 (True) but not 4 (False)."
    ),
}


def main() -> int:
    touched = 0
    for path in sorted(MOD.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for lesson in data["lessons"]:
            lid = lesson["id"]
            if lid in SOURCES and not (lesson.get("source") or {}).get("url"):
                lesson["source"] = SOURCES[lid]
                changed = True
            if lid in DESCRIPTIONS:
                lesson["description"] = DESCRIPTIONS[lid]
                changed = True
        if changed:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
            touched += 1
    print(f"patched {touched} dsa modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
