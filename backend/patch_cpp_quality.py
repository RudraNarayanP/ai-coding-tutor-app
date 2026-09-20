"""C++ course quality patch: verified cppreference sources for all 33
lessons, enriched thin descriptions, added learning objectives to the three
Section-2 lessons, de-presolved cpp-perf-01, and fixed 3 fill_blank exercises.

Every cppreference URL was fetched and inspected this session.

Run from repo root:  .venv/Scripts/python.exe backend/patch_cpp_quality.py
"""
import json
from pathlib import Path

MOD = Path("curriculum/cpp/modules")
LIC = "CC BY-SA 4.0 (cppreference.com)"

def cpp(name: str, url: str) -> dict:
    return {"name": f"cppreference.com — {name}", "url": url, "license": LIC}

BASE = "https://en.cppreference.com/w/cpp"

SOURCES: dict[str, dict] = {
    "cpp-variables-step-1": cpp("std::cout — global object controlling output to stdout",
                                f"{BASE}/io/cout"),
    "cpp-variables-step-2": cpp("Fundamental types — int, basic integer type",
                                f"{BASE}/language/types"),
    "cpp-variables-01": cpp("Built-in multiplicative operators * / %",
                            f"{BASE}/language/operator_arithmetic"),
    "cpp-variables-practice-1": cpp("Built-in arithmetic operators",
                                    f"{BASE}/language/operator_arithmetic"),
    "cpp-variables-checkpoint": cpp("Built-in arithmetic operators",
                                    f"{BASE}/language/operator_arithmetic"),
    "cpp-conditionals-step-1": cpp("if statement (with else branch)", f"{BASE}/language/if"),
    "cpp-conditionals-step-2": cpp("Conditional AND (&&) / OR (||) operators",
                                   f"{BASE}/language/operator_logical"),
    "cpp-conditionals-01": cpp("if-else statements", f"{BASE}/language/if"),
    "cpp-conditionals-practice-1": cpp("if statement", f"{BASE}/language/if"),
    "cpp-conditionals-checkpoint": cpp("if statement", f"{BASE}/language/if"),
    "cpp-loops-step-1": cpp("for loop statement", f"{BASE}/language/for"),
    "cpp-loops-step-2": cpp("while loop statement", f"{BASE}/language/while"),
    "cpp-loops-01": cpp("for loop statement", f"{BASE}/language/for"),
    "cpp-loops-practice-1": cpp("for loop statement", f"{BASE}/language/for"),
    "cpp-loops-checkpoint": cpp("for loop statement", f"{BASE}/language/for"),
    "cpp-functions-step-1": cpp("References — 'Declares a named variable as a reference'",
                                f"{BASE}/language/reference"),
    "cpp-functions-step-2": cpp("References — const reference function parameters",
                                f"{BASE}/language/reference"),
    "cpp-functions-01": cpp("References — modifying the referred object",
                            f"{BASE}/language/reference"),
    "cpp-functions-practice-1": cpp("References — pass-by-reference mutation",
                                    f"{BASE}/language/reference"),
    "cpp-functions-checkpoint": cpp("References — function parameters",
                                    f"{BASE}/language/reference"),
    "cpp-vectors-step-1": cpp("std::vector — 'a sequence container that encapsulates dynamic size arrays'",
                              f"{BASE}/container/vector"),
    "cpp-vectors-step-2": cpp("std::vector", f"{BASE}/container/vector"),
    "cpp-vectors-01": cpp("std::vector", f"{BASE}/container/vector"),
    "cpp-vectors-practice-1": cpp("std::reverse — 'Reverses the order of the elements in the target range'",
                                  f"{BASE}/algorithm/reverse"),
    "cpp-vectors-checkpoint": cpp("std::vector", f"{BASE}/container/vector"),
    "cpp-classes-step-1": cpp("Member initializer lists in constructor definitions",
                              f"{BASE}/language/initializer_list"),
    "cpp-classes-step-2": cpp("Class specifier — data members and member functions",
                              f"{BASE}/language/class"),
    "cpp-classes-01": cpp("Class specifier — access specifiers and members",
                          f"{BASE}/language/class"),
    "cpp-classes-practice-1": cpp("Class specifier", f"{BASE}/language/class"),
    "cpp-classes-checkpoint": cpp("Class specifier", f"{BASE}/language/class"),
    "cpp-ptr-01": cpp("Pointer and member pointer types — address-of and indirection",
                      f"{BASE}/language/pointer"),
    "cpp-mem-01": cpp("std::unique_ptr — smart pointer that owns and disposes its object",
                      f"{BASE}/memory/unique_ptr"),
    "cpp-perf-01": cpp("std::sort — 'Sorts the elements in the target range [first, last)'",
                       f"{BASE}/algorithm/sort"),
}

DESCRIPTIONS: dict[str, str] = {
    "cpp-variables-checkpoint": (
        "Checkpoint for variables and arithmetic: implement square(int x) returning "
        "x * x. The test asserts square(6) == 36."
    ),
    "cpp-conditionals-checkpoint": (
        "Checkpoint for control flow: implement max_of_three(int a, int b, int c) "
        "returning the largest of the three values — nested if/else comparisons or "
        "std::max(a, std::max(b, c)). The test asserts max_of_three(10, 42, 25) == 42."
    ),
    "cpp-loops-practice-1": (
        "Practice: implement power(int base, int exp) returning base^exp as a "
        "long long, multiplying base into an accumulator exp times. "
        "The test asserts power(2, 5) == 32."
    ),
    "cpp-loops-checkpoint": (
        "Checkpoint for loops: implement count_multiples(int start, int end, int k) "
        "counting every integer i in [start, end] where i % k == 0. "
        "The test asserts count_multiples(1, 15, 3) == 5."
    ),
    "cpp-functions-practice-1": (
        "Practice with pass-by-reference: implement increment(int& value, "
        "int amount = 1) so it adds amount to value in-place; the caller's variable "
        "must change. The test runs increment(val, 5) on val == 10 and asserts "
        "val == 15."
    ),
    "cpp-vectors-practice-1": (
        "Practice: implement reverse_vector(std::vector<int>& numbers) reversing "
        "the vector in place — std::reverse(numbers.begin(), numbers.end()) or "
        "manual two-end swapping. The test asserts {1, 2, 3} becomes {3, 2, 1}."
    ),
    "cpp-vectors-checkpoint": (
        "Checkpoint for vectors: implement contains_value(const std::vector<int>& "
        "vec, int target) returning true when target appears in vec — a range-based "
        "for loop fits well. The test checks contains_value({10,20,30}, 20) is true "
        "and contains_value({10,20,30}, 99) is false."
    ),
    "cpp-perf-01": (
        "Modern C++ checkpoint: implement sortVector(std::vector<int>& vec) so it "
        "sorts the vector in place with std::sort over the [vec.begin(), "
        "vec.end()) iterator range. The test sorts {3, 1, 2} and checks the result."
    ),
}

OBJECTIVES: dict[str, list[str]] = {
    "cpp-ptr-01": [
        "Obtain an object's address with the built-in & operator",
        "Read and write the pointed-to object with the unary * indirection operator",
        "Bind int& references to existing objects so functions mutate callers",
    ],
    "cpp-mem-01": [
        "Explain RAII: std::unique_ptr disposes its object when it goes out of scope",
        "Allocate a managed heap object with std::make_unique<T>(value)",
        "Dereference a std::unique_ptr with * like a raw pointer",
    ],
    "cpp-perf-01": [
        "Sort a std::vector in place with std::sort",
        "Pass iterator ranges [first, last) to STL algorithms",
        "Include <algorithm> for std::sort and <vector> for the container",
    ],
}

# de-presolved checkpoint starter (must compile but fail the test)
CPP_PERF_STARTER = (
    "#include <vector>\n#include <algorithm>\n\n"
    "inline void sortVector(std::vector<int>& vec) {\n"
    "    // TODO: sort the range [vec.begin(), vec.end()) with std::sort\n}\n"
)

EXERCISE_FIXES = {
    "cpp-ex-2a": {"correct_answer": ["\"C++\""]},
    "cpp-exam-2": {
        "question": "Fill in the symbol that ends a C++ statement: int x = 5___",
        "blanks": [";"],
        "correct_answer": [";"],
    },
    "cpp-chk-2": {
        "question": "Complete the C++ main function return: return ___;",
        "blanks": ["0"],
        "correct_answer": ["0"],
        "explanation": "main returns 0 to signal success to the operating system.",
    },
}


def main() -> int:
    touched = 0
    ex_fixed = []
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
            if lid == "cpp-perf-01":
                lesson["starter_code"] = CPP_PERF_STARTER
                changed = True
            if lid in OBJECTIVES and not lesson.get("learning_objectives"):
                lesson["learning_objectives"] = OBJECTIVES[lid]
                changed = True
            def handle(ex):
                nonlocal changed
                if ex["id"] in EXERCISE_FIXES:
                    ex.update(EXERCISE_FIXES[ex["id"]])
                    ex_fixed.append(ex["id"])
                    changed = True
            for sub in lesson.get("sublessons", []):
                for ex in sub.get("exercises", []):
                    handle(ex)
            for ex in lesson.get("mastery_exam", []) or []:
                handle(ex)
        if changed:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
            touched += 1
    print(f"patched {touched} cpp modules; exercises fixed: {sorted(set(ex_fixed))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
