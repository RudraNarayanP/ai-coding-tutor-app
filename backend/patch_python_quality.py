"""Second-pass quality patch for the Python course:

1. Attach verified documentation sources to the 53 lessons that had none.
   Every URL/section below was actually fetched and inspected this session
   (docs.python.org 3.14, docs.pytest.org, d2l.ai).
2. De-presolve the 6 challenge/practice/checkpoint lessons whose starter code
   already contained the full solution; state each rule explicitly in the
   description and strengthen single-case tests to cover all branches.
3. Rewrite the 6 thin checkpoint descriptions into concrete task statements.
4. Add learning_objectives to py-automation-01 / py-backend-01 / py-aiml-01.

Run from repo root:
  .venv/Scripts/python.exe backend/patch_python_quality.py
"""
import json
from pathlib import Path

MOD = Path("curriculum/python/modules")

PSF = "Python documentation license (PSF)"
PYTEST_LIC = "MIT license (pytest documentation)"
D2L_LIC = "Apache 2.0 (Dive into Deep Learning book)"

DOC = "Python official documentation (docs.python.org)"

def doc(section: str) -> dict:
    name, url = section
    return {"name": f"{DOC} — {name}", "url": url, "license": PSF}

# ---------------------------------------------------------------------------
# 1. Verified sources for the 53 lessons that shipped without attribution.
#    (name, url) pairs were each confirmed present on the fetched page.
# ---------------------------------------------------------------------------
SOURCES: dict[str, dict] = {
    # variables — tutorial 3.1 (verified: "The equal sign (=) is used to assign
    # a value to a variable."; 3.1.1 Numbers arithmetic)
    "variables-step-1": doc(("3.1.2 Text — assignment with = (Tutorial: An Informal Introduction)",
                             "https://docs.python.org/3/tutorial/introduction.html#strings")),
    "variables-step-2": doc(("3.1.1 Numbers — arithmetic on numeric variables (Tutorial: An Informal Introduction)",
                             "https://docs.python.org/3/tutorial/introduction.html#numbers")),
    "variables-01": doc(("3.2 First Steps Towards Programming — variables and arithmetic",
                         "https://docs.python.org/3/tutorial/introduction.html#first-steps-towards-programming")),
    "variables-practice-1": doc(("3.2 First Steps Towards Programming — variables and arithmetic",
                                 "https://docs.python.org/3/tutorial/introduction.html#first-steps-towards-programming")),
    "variables-checkpoint": doc(("3.2 First Steps Towards Programming — variables and arithmetic",
                                 "https://docs.python.org/3/tutorial/introduction.html#first-steps-towards-programming")),
    # booleans — Language Reference §6.11 (verified quote on and/or semantics)
    "booleans-step-1": doc(("6.11 Boolean Operations — and, or, not (Language Reference)",
                            "https://docs.python.org/3/reference/expressions.html#boolean-operations")),
    "booleans-step-2": doc(("6.11 Boolean Operations — and, or, not (Language Reference)",
                            "https://docs.python.org/3/reference/expressions.html#boolean-operations")),
    "booleans-01": doc(("6.11 Boolean Operations — and (Language Reference)",
                        "https://docs.python.org/3/reference/expressions.html#boolean-operations")),
    "booleans-practice-1": doc(("6.11 Boolean Operations — or / and (Language Reference)",
                                "https://docs.python.org/3/reference/expressions.html#boolean-operations")),
    "booleans-checkpoint": doc(("6.11 Boolean Operations — not / and (Language Reference)",
                                "https://docs.python.org/3/reference/expressions.html#boolean-operations")),
    # classes — tutorial (verified __init__ and self quotes)
    "classes-step-1": doc(("Classes — __init__ constructor (Python Tutorial)",
                           "https://docs.python.org/3/tutorial/classes.html#instantiation")),
    "classes-step-2": doc(("Classes — methods and the self first argument (Python Tutorial)",
                           "https://docs.python.org/3/tutorial/classes.html#user-defined-objects")),
    "classes-01": doc(("Classes — object attributes and methods (Python Tutorial)",
                       "https://docs.python.org/3/tutorial/classes.html")),
    "classes-practice-1": doc(("Classes — mutating instance state in methods (Python Tutorial)",
                               "https://docs.python.org/3/tutorial/classes.html#user-defined-objects")),
    "classes-checkpoint": doc(("Classes — instantiation and attribute access (Python Tutorial)",
                               "https://docs.python.org/3/tutorial/classes.html#instantiation")),
    # comprehensions
    "comprehensions-step-1": doc(("5.1.3. List Comprehensions (Tutorial: Data Structures)",
                                  "https://docs.python.org/3/tutorial/datastructures.html#list-comprehensions")),
    "comprehensions-step-2": doc(("Displays for Lists, Sets, and Dictionaries — dict comprehensions (Language Reference)",
                                  "https://docs.python.org/3/reference/expressions.html#displays-for-lists-sets-and-dictionaries")),
    "comprehensions-01": doc(("5.1.4. Nested List Comprehensions (Tutorial: Data Structures)",
                              "https://docs.python.org/3/tutorial/datastructures.html#nested-list-comprehensions")),
    "comprehensions-practice-1": doc(("5.1.3. List Comprehensions — if clauses (Tutorial: Data Structures)",
                                      "https://docs.python.org/3/tutorial/datastructures.html#list-comprehensions")),
    "comprehensions-checkpoint": doc(("Displays for Lists, Sets, and Dictionaries — set comprehensions (Language Reference)",
                                      "https://docs.python.org/3/reference/expressions.html#displays-for-lists-sets-and-dictionaries")),
    # context managers
    "context-managers-step-1": doc(("With Statement Context Managers — __enter__/__exit__ (Language Reference)",
                                    "https://docs.python.org/3/reference/datamodel.html#with-statement-context-managers")),
    "context-managers-step-2": doc(("contextlib.contextmanager — decorator for generator-based context managers",
                                    "https://docs.python.org/3/library/contextlib.html#contextlib.contextmanager")),
    "context-managers-01": doc(("With Statement Context Managers — __enter__/__exit__ (Language Reference)",
                                "https://docs.python.org/3/reference/datamodel.html#with-statement-context-managers")),
    "context-managers-practice-1": doc(("contextlib.suppress — swallows specified exceptions in a with block",
                                        "https://docs.python.org/3/library/contextlib.html#contextlib.suppress")),
    "context-managers-checkpoint": doc(("With Statement Context Managers — __enter__/__exit__ (Language Reference)",
                                        "https://docs.python.org/3/reference/datamodel.html#with-statement-context-managers")),
    # decorators — verified @ f1(arg)(f2(func)) equivalence sentence
    "decorators-step-1": doc(("Function definitions — @decorator shorthand equivalence (Language Reference)",
                              "https://docs.python.org/3/reference/compound_stmts.html#function-definitions")),
    "decorators-step-2": doc(("Function definitions — @decorator shorthand equivalence (Language Reference)",
                              "https://docs.python.org/3/reference/compound_stmts.html#function-definitions")),
    "decorators-01": doc(("functools.cache — unbounded memoizing decorator",
                          "https://docs.python.org/3/library/functools.html#functools.cache")),
    "decorators-practice-1": doc(("Function definitions — @decorator shorthand equivalence (Language Reference)",
                                  "https://docs.python.org/3/reference/compound_stmts.html#function-definitions")),
    "decorators-checkpoint": doc(("Function definitions — @decorator shorthand equivalence (Language Reference)",
                                  "https://docs.python.org/3/reference/compound_stmts.html#function-definitions")),
    # exceptions — verified 8.3 try/except, 8.4 raise, 8.6 user exceptions derive Exception
    "exceptions-step-1": doc(("Handling Exceptions — try/except clauses (Tutorial: Errors and Exceptions)",
                              "https://docs.python.org/3/tutorial/errors.html#handling-exceptions")),
    "exceptions-step-2": doc(("Defining and Naming Exceptions — derive exceptions from Exception (Tutorial)",
                              "https://docs.python.org/3/tutorial/errors.html#defining-and-naming-exceptions")),
    "exceptions-01": doc(("Handling Exceptions — re-raising with bare raise (Tutorial)",
                          "https://docs.python.org/3/tutorial/errors.html#raising-exceptions")),
    "exceptions-practice-1": doc(("Handling Exceptions — except ValueError handlers (Tutorial)",
                                  "https://docs.python.org/3/tutorial/errors.html#handling-exceptions")),
    "exceptions-checkpoint": doc(("Raising Exceptions — raise ValueError(...) (Tutorial)",
                                  "https://docs.python.org/3/tutorial/errors.html#raising-exceptions")),
    # generators — verified "Using yield in a function definition is sufficient to cause that
    # definition to create a generator function"; islice quote + take recipe
    "generators-step-1": doc(("The yield statement — generator functions (Language Reference)",
                              "https://docs.python.org/3/reference/simple_stmts.html#yield")),
    "generators-step-2": doc(("itertools.islice — 'Make an iterator that returns selected elements from the iterable'",
                              "https://docs.python.org/3/library/itertools.html#itertools.islice")),
    "generators-01": doc(("The yield statement — incremental results from generators (Language Reference)",
                          "https://docs.python.org/3/reference/simple_stmts.html#yield")),
    "generators-practice-1": doc(("itertools Recipes — chunking with islice",
                                  "https://docs.python.org/3/library/itertools.html#itertools-recipes")),
    "generators-checkpoint": doc(("The yield statement — conditional yield in generators (Language Reference)",
                                  "https://docs.python.org/3/reference/simple_stmts.html#yield")),
    # pytest module — docs.pytest.org getting-started (assert introspection + approx quotes verified)
    "pytest-testing-step-1": {"name": "pytest documentation — Write your first test (plain asserts)",
                              "url": "https://docs.pytest.org/en/stable/getting-started.html",
                              "license": PYTEST_LIC},
    "pytest-testing-step-2": {"name": "pytest documentation — Write your first test (parametrize-style case running)",
                              "url": "https://docs.pytest.org/en/stable/getting-started.html",
                              "license": PYTEST_LIC},
    "pytest-testing-01": doc(("The yield statement — setup/teardown around a yielded value (Language Reference)",
                              "https://docs.python.org/3/reference/simple_stmts.html#yield")),
    "pytest-testing-practice-1": {"name": "pytest documentation — use pytest.approx() to compare floating-point values",
                                  "url": "https://docs.pytest.org/en/stable/getting-started.html",
                                  "license": PYTEST_LIC},
    "pytest-testing-checkpoint": {"name": "pytest reference — pytest.raises context behavior",
                                  "url": "https://docs.pytest.org/en/stable/reference/reference.html#pytest.raises",
                                  "license": PYTEST_LIC},
    # type hints & dataclasses — verified PEP 604 change note, PEP 585 container subscription,
    # dataclasses frozen + replace quotes
    "type-hints-dataclasses-step-1": doc(("typing — annotating parameters and return types",
                                          "https://docs.python.org/3/library/typing.html")),
    "type-hints-dataclasses-step-2": doc(("dataclasses — @dataclass generates __init__ for annotated fields",
                                          "https://docs.python.org/3/library/dataclasses.html")),
    "type-hints-dataclasses-01": doc(("dataclasses — frozen=True and dataclasses.replace()",
                                      "https://docs.python.org/3/library/dataclasses.html")),
    "type-hints-dataclasses-practice-1": doc(("typing — 'Unions can now be written as X | Y' (PEP 604 change note)",
                                              "https://docs.python.org/3/library/typing.html")),
    "type-hints-dataclasses-checkpoint": doc(("dataclasses — generated __init__ and methods on dataclasses",
                                              "https://docs.python.org/3/library/dataclasses.html")),
    # applied tracks
    "py-automation-01": doc(("Reading and Writing Files — with keyword and line iteration (Tutorial)",
                             "https://docs.python.org/3/tutorial/inputoutput.html#reading-and-writing-files")),
    "py-backend-01": doc(("More on Defining Functions — 'specify a default value for one or more arguments' (Tutorial)",
                          "https://docs.python.org/3/tutorial/controlflow.html#more-on-defining-functions")),
    "py-aiml-01": {"name": "Dive into Deep Learning §2.3 Linear Algebra — dot product is 'a sum over the products of the elements at the same position'",
                   "url": "https://d2l.ai/chapter_preliminaries/linear-algebra.html",
                   "license": D2L_LIC},
}

# ---------------------------------------------------------------------------
# 2/3. De-presolved lessons + rewritten descriptions.
# ---------------------------------------------------------------------------
REWRITES: dict[str, dict] = {
    "variables-01": {
        "description": (
            'Italian lasagna takes prep_time = 10 minutes of preparation and '
            'bake_time = 40 minutes in the oven. Keeping the given setup lines, '
            'compute total_time as the sum of prep_time and bake_time (the tests '
            'expect country == "Italy" and total_time == 50).'
        ),
        "starter_code": (
            'country = "Italy"\nprep_time = 10\nbake_time = 40\n\n'
            "# TODO: set total_time to the sum of prep_time and bake_time\ntotal_time = 0\n"
        ),
        "solution_code": (
            'country = "Italy"\nprep_time = 10\nbake_time = 40\n\n'
            'total_time = prep_time + bake_time\n'
        ),
    },
    "variables-practice-1": {
        "description": (
            "You are buying 3 movie tickets at ticket_price = 12 each plus one "
            "popcorn_price = 8 snack. Compute ticket_total = ticket_price * "
            "num_tickets, then grand_total = ticket_total + popcorn_price "
            "(the test expects grand_total == 44)."
        ),
        "starter_code": (
            "ticket_price = 12\npopcorn_price = 8\nnum_tickets = 3\n\n"
            "# TODO: compute ticket_total = ticket_price * num_tickets\n"
            "# TODO: compute grand_total = ticket_total + popcorn_price\n"
        ),
        "solution_code": (
            "ticket_price = 12\npopcorn_price = 8\nnum_tickets = 3\n\n"
            "ticket_total = ticket_price * num_tickets\n"
            "grand_total = ticket_total + popcorn_price\n"
        ),
    },
    "variables-checkpoint": {
        "description": (
            "For a triangle with base = 10 and height = 5, set area to the "
            "triangle formula (base * height) / 2. The test checks "
            "area == 25 — using / (true division) is expected."
        ),
        "starter_code": (
            "base = 10\nheight = 5\n\n"
            "# TODO: set area to (base * height) / 2\narea = 0\n"
        ),
        "solution_code": "base = 10\nheight = 5\n\narea = (base * height) / 2\n",
    },
    "booleans-01": {
        "description": (
            "Pac-Man may eat a ghost only while the power pellet is active AND "
            "he is touching a ghost. Implement eat_ghost(power_pellet_active, "
            "touching_ghost) so it returns True exactly when both inputs are "
            "True (all four combinations are tested)."
        ),
        "starter_code": (
            "def eat_ghost(power_pellet_active, touching_ghost):\n"
            "    # TODO: return True only when the pellet is active AND a ghost is touched\n"
            "    return False\n"
        ),
        "solution_code": (
            "def eat_ghost(power_pellet_active, touching_ghost):\n"
            "    return power_pellet_active and touching_ghost\n"
        ),
        "tests": [{
            "name": "test_ghost_gets_eaten",
            "required": True,
            "description": "eat_ghost is True only when both inputs are True.",
            "unittest_code": (
                "def test_ghost_gets_eaten(self):\n"
                "    self.assertEqual(eat_ghost(True, True), True)\n"
                "    self.assertEqual(eat_ghost(True, False), False)\n"
                "    self.assertEqual(eat_ghost(False, True), False)\n"
                "    self.assertEqual(eat_ghost(False, False), False)\n"
            ),
        }],
    },
    "booleans-practice-1": {
        "description": (
            "Implement unlock_door(has_keycard, passcode_correct, is_emergency): "
            "the door opens when the emergency override is active, OR when the "
            "keycard is held AND the passcode is correct. Every combination "
            "listed in the tests must hold."
        ),
        "starter_code": (
            "def unlock_door(has_keycard, passcode_correct, is_emergency):\n"
            "    # TODO: return True when is_emergency OR (has_keycard AND passcode_correct)\n"
            "    return False\n"
        ),
        "solution_code": (
            "def unlock_door(has_keycard, passcode_correct, is_emergency):\n"
            "    return is_emergency or (has_keycard and passcode_correct)\n"
        ),
        "tests": [{
            "name": "test_unlock_door",
            "required": True,
            "description": "Emergency override or keycard+passcode opens the door.",
            "unittest_code": (
                "def test_unlock_door(self):\n"
                "    self.assertTrue(unlock_door(False, False, True))\n"
                "    self.assertTrue(unlock_door(True, True, False))\n"
                "    self.assertFalse(unlock_door(True, False, False))\n"
                "    self.assertFalse(unlock_door(False, True, False))\n"
                "    self.assertFalse(unlock_door(False, False, False))\n"
            ),
        }],
    },
    "booleans-checkpoint": {
        "description": (
            "A camera device can take a photo only when it has a working camera "
            "module AND its memory is not full. Implement can_take_photo("
            "has_camera, memory_full) — all four input combinations are tested."
        ),
        "starter_code": (
            "def can_take_photo(has_camera, memory_full):\n"
            "    # TODO: return True only when has_camera is True AND memory_full is False\n"
            "    return False\n"
        ),
        "solution_code": (
            "def can_take_photo(has_camera, memory_full):\n"
            "    return has_camera and not memory_full\n"
        ),
        "tests": [{
            "name": "test_can_take_photo",
            "required": True,
            "description": "Photo allowed only with a camera and free memory.",
            "unittest_code": (
                "def test_can_take_photo(self):\n"
                "    self.assertTrue(can_take_photo(True, False))\n"
                "    self.assertFalse(can_take_photo(True, True))\n"
                "    self.assertFalse(can_take_photo(False, False))\n"
                "    self.assertFalse(can_take_photo(False, True))\n"
            ),
        }],
    },
    "comparisons-checkpoint": {
        "description": (
            "compare_scores(score_a, score_b) must return \"A\" when score_a is "
            "greater, \"B\" when score_b is greater, and \"Tie\" when both are "
            "equal — practicing comparison operators and if/elif/else."
        ),
    },
    "strings-checkpoint": {
        "description": (
            "wrap_string(s, char) must surround s with char on both sides, "
            "returning char + s + char using string concatenation."
        ),
    },
    "string-methods-checkpoint": {
        "description": (
            "hashtagify(word) must turn any raw word into a hashtag: strip "
            "surrounding whitespace, lowercase it, and prefix it with \"#\" "
            "(e.g. ' Python ' -> '#python')."
        ),
    },
    "lists-checkpoint": {
        "description": (
            "middle_element(lst) must return the middle item of an odd-length "
            "list using len(lst) // 2 for the integer middle index."
        ),
    },
    "list-methods-checkpoint": {
        "description": (
            "reverse_and_sort(lst) must return a NEW list with the numbers "
            "sorted from largest to smallest — use sorted(lst, reverse=True) "
            "so the original list stays unchanged."
        ),
    },
    "loops-checkpoint": {
        "description": (
            "filter_long_words(words, min_len) must return, via a list "
            "comprehension, only the words whose length is at least min_len."
        ),
    },
}

OBJECTIVES: dict[str, list[str]] = {
    "py-automation-01": [
        "Filter text lines with membership tests and list comprehensions",
        "Process file-like line data without manual accumulator loops",
        "Return a new list containing exactly the lines that match a keyword",
    ],
    "py-backend-01": [
        "Build API response payloads as dictionaries with fixed keys",
        "Use a default parameter value for optional arguments",
        "Compose status codes and bodies into a single response object",
    ],
    "py-aiml-01": [
        "Compute the dot product of two equal-length vectors",
        "Pair elements positionally with zip()",
        "Accumulate element-wise products with a generator expression and sum()",
    ],
}


def main() -> int:
    files = sorted(MOD.glob("*.json"))
    touched = set()
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for lesson in data["lessons"]:
            lid = lesson["id"]
            if lid in SOURCES and not (lesson.get("source") or {}).get("url"):
                lesson["source"] = SOURCES[lid]
                changed = True
            if lid in REWRITES:
                for key, value in REWRITES[lid].items():
                    lesson[key] = value
                    changed = True
            if lid in OBJECTIVES and not lesson.get("learning_objectives"):
                lesson["learning_objectives"] = OBJECTIVES[lid]
                changed = True
        if changed:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
            touched.add(path.name)
    print(f"patched {len(touched)} module files: {sorted(touched)}")
    print(f"entries applied: {len(SOURCES)} sources, {len(REWRITES)} rewrites, "
          f"{len(OBJECTIVES)} objective sets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
