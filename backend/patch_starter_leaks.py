"""Rewrite curriculum starters that hand the learner the answer.

``backend.starter_leak_audit`` flags two leak patterns, both of which make an
exercise unfalsifiable practice:

* ``todo_quotes_answer`` -- ``# TODO: return width * height`` sitting directly
  above ``return width * height``. The learner deletes two lines and retypes
  them; nothing is recalled or constructed.
* ``presolved_body`` -- the body is already the answer with a literal swapped,
  e.g. ``return { id: 0, active: false };`` for ``return { id: userId, active:
  true };``.

The fix moves the *specification* into the task description (where a learner
can legitimately read it) and leaves the starter as an honest skeleton: a
placeholder body plus a TODO that names the goal in prose without containing
the expression that computes it.

Run with ``python -m backend.patch_starter_leaks`` (add ``--dry-run`` to preview).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CURRICULUM_ROOT = Path(__file__).resolve().parent.parent / "curriculum"

# lesson id -> the fields to overwrite. ``starter_code`` is required;
# ``description`` only changes where the old TODO carried the only spec.
FIXES: dict[str, dict[str, str]] = {
    # ---------------------------------------------------------------- AI
    "ai-tool-result-msg": {
        "starter_code": (
            "def tool_result_message(call_id, content):\n"
            "    # TODO: return the tool result message described in the task\n"
            "    return {}\n"
        ),
    },
    # ---------------------------------------------------------------- C++
    "cpp-variables-step-2": {
        "starter_code": (
            "int calculate_total(int price, int quantity) {\n"
            "    // TODO: return the cost of `quantity` items at `price` each\n"
            "    return 0;\n"
            "}\n"
        ),
    },
    "cpp-variables-01": {
        "description": (
            "Calculate required rocket fuel mass in C++: fuel equals "
            "`payload_mass * distance * 0.15`."
        ),
        "starter_code": (
            "double calculate_fuel(double payload_mass, double distance) {\n"
            "    // TODO: return the fuel mass for this payload and distance\n"
            "    return 0.0;\n"
            "}\n"
        ),
    },
    "cpp-variables-practice-1": {
        "starter_code": (
            "double circle_area(double radius) {\n"
            "    const double pi = 3.141592653589793;\n"
            "    // TODO: return the area of a circle with this radius\n"
            "    return 0.0;\n"
            "}\n"
        ),
    },
    "cpp-classes-practice-1": {
        "starter_code": (
            "class Rectangle {\n"
            "private:\n"
            "    double width_;\n"
            "    double height_;\n"
            "public:\n"
            "    Rectangle(double width, double height)\n"
            "        : width_(width), height_(height) {}\n"
            "\n"
            "    double area() const {\n"
            "        // TODO: return the area of this rectangle\n"
            "        return 0.0;\n"
            "    }\n"
            "};\n"
        ),
    },
    "cpp-conditionals-step-2": {
        "description": (
            "C++ uses `&&` for AND, `||` for OR, and `!` for NOT. Implement "
            "`can_drive(bool has_license, bool is_sober)`, which is true only "
            "when the driver holds a licence and is sober."
        ),
        "starter_code": (
            "bool can_drive(bool has_license, bool is_sober) {\n"
            "    // TODO: return true only when both conditions hold\n"
            "    return false;\n"
            "}\n"
        ),
    },
    "cpp-functions-step-2": {
        "description": (
            "Pass large objects by `const &` to avoid expensive copies while "
            "guaranteeing immutability. Implement `greeting(const std::string& "
            "name)` returning `\"Hello, \"` followed by the name and a `!`."
        ),
        "starter_code": (
            "#include <string>\n"
            "\n"
            "std::string greeting(const std::string& name) {\n"
            "    // TODO: return the greeting for this name\n"
            '    return "";\n'
            "}\n"
        ),
    },
    "cpp-mem-01": {
        "description": (
            "Use `std::unique_ptr` and RAII patterns for automated memory "
            "management. Implement `makeHeapInt(int value)` returning a "
            "`std::unique_ptr<int>` that owns a heap-allocated copy of "
            "`value`; prefer the `std::make_unique` factory."
        ),
        "starter_code": (
            "#include <memory>\n"
            "\n"
            "inline std::unique_ptr<int> makeHeapInt(int value) {\n"
            "    // TODO: return a unique_ptr owning a heap copy of value\n"
            "    return std::unique_ptr<int>();\n"
            "}\n"
        ),
    },
    # ---------------------------------------------------------------- Java
    "java-variables-step-2": {
        "starter_code": (
            "public class Solution {\n"
            "    public static int calculateTotal(int price, int quantity) {\n"
            "        // TODO: return the total cost\n"
            "        return 0;\n"
            "    }\n"
            "}\n"
        ),
    },
    "java-variables-01": {
        "description": (
            "Calculate total order cost including sales tax: multiply "
            "`itemPrice` by `count`, then apply `taxRate` as a fraction."
        ),
        "starter_code": (
            "public class Solution {\n"
            "    public static double calculateBill(double itemPrice, int count, "
            "double taxRate) {\n"
            "        // TODO: return the bill total including tax\n"
            "        return 0.0;\n"
            "    }\n"
            "}\n"
        ),
    },
    "java-variables-practice-1": {
        "description": (
            "Convert Fahrenheit temperature to Celsius using "
            "`(fahrenheit - 32) * 5 / 9`."
        ),
        "starter_code": (
            "public class Solution {\n"
            "    public static double fahrenheitToCelsius(double fahrenheit) {\n"
            "        // TODO: return the temperature in Celsius\n"
            "        return 0.0;\n"
            "    }\n"
            "}\n"
        ),
    },
    "java-methods-step-2": {
        "description": (
            "Break down problems into small private/public helper methods. "
            "Implement `formatName(String firstName, String lastName)` "
            'returning the last name, a comma and a space, then the first name.'
        ),
        "starter_code": (
            "public class Solution {\n"
            "    public static String formatName(String firstName, String lastName) {\n"
            '        // TODO: return "last, first"\n'
            '        return "";\n'
            "    }\n"
            "}\n"
        ),
    },
    "java-methods-01": {
        "description": (
            "Implement currency exchange conversion: the converted amount is "
            "`amount * exchangeRate`."
        ),
        "starter_code": (
            "public class Solution {\n"
            "    public static double convert(double amount, double exchangeRate) {\n"
            "        // TODO: return the converted amount\n"
            "        return 0.0;\n"
            "    }\n"
            "}\n"
        ),
    },
    # ---------------------------------------------------------------- JavaScript
    "js-03": {
        "starter_code": (
            "// TODO: return the user record described in the task\n"
            "async function fetchUserData(userId) {\n"
            "    return {};\n"
            "}\n"
            "module.exports = { fetchUserData };\n"
        ),
    },
    "js-06": {
        "starter_code": (
            "async function fetchUserData(userId) {\n"
            "    return { name: 'User' + userId };\n"
            "}\n"
            "\n"
            "function getUserLabel(userId) {\n"
            "    // TODO: resolve the user, then return just the name\n"
            "    return Promise.resolve('');\n"
            "}\n"
            "module.exports = { getUserLabel };\n"
        ),
    },
    "js-04": {
        "starter_code": (
            "// TODO: default the port and return the config object described above\n"
            "function createServerConfig(port) {\n"
            "    return {};\n"
            "}\n"
            "module.exports = { createServerConfig };\n"
        ),
    },
    # ---------------------------------------------------------------- Python
    "py-backend-01": {
        "description": (
            "Format backend REST API response dictionaries: "
            "`make_api_response(data, status)` returns a dict with the status "
            "code under `status_code` and the payload under `body`."
        ),
        "starter_code": (
            "def make_api_response(data: dict, status: int = 200) -> dict:\n"
            "    # TODO: return the response envelope described in the task\n"
            "    return {}\n"
        ),
    },
    "variables-step-2": {
        "description": (
            "Variables can hold numbers and participate in arithmetic. There "
            "are 3 more bananas than apples, so `total_fruit` counts the "
            "apples plus 3."
        ),
        "starter_code": (
            "apples = 5\n"
            "# TODO: set total_fruit to all the fruit\n"
            "total_fruit = 0\n"
        ),
    },
    "variables-practice-1": {
        "starter_code": (
            "ticket_price = 12\n"
            "popcorn_price = 8\n"
            "num_tickets = 3\n"
            "\n"
            "# TODO: work out the ticket subtotal, then the grand total\n"
        ),
    },
    "variables-checkpoint": {
        "starter_code": (
            "base = 10\n"
            "height = 5\n"
            "\n"
            "# TODO: set area to the area of this triangle\n"
            "area = 0\n"
        ),
    },
    "comprehensions-step-2": {
        "starter_code": (
            "def word_lengths(words):\n"
            "    # TODO: return a dict mapping each word to how long it is\n"
            "    pass\n"
        ),
    },
    "dictionaries-step-1": {
        "starter_code": (
            "def get_item_count(inventory, item):\n"
            "    # TODO: return the count for item, or 0 when it is missing\n"
            "    pass\n"
        ),
    },
    "functions-step-2": {
        "starter_code": (
            "def area_of_rectangle(width, height):\n"
            '    """Calculate rectangle area."""\n'
            "    # TODO: return the area\n"
            "    pass\n"
        ),
    },
    "functions-practice-1": {
        "description": (
            "Calculate scaled recipe quantities: multiply `base_amount` by the "
            "ratio of `target_servings` to `base_servings`."
        ),
        "starter_code": (
            "def scale_recipe(base_amount, base_servings, target_servings):\n"
            '    """Return scaled amount for target_servings."""\n'
            "    # TODO: return the scaled amount\n"
            "    pass\n"
        ),
    },
    "list-methods-step-2": {
        "starter_code": (
            "def count_and_sort(lst, target):\n"
            "    # TODO: return how often target appears, and the sorted list\n"
            "    pass\n"
        ),
    },
    "list-methods-checkpoint": {
        "starter_code": (
            "def reverse_and_sort(lst):\n"
            "    # TODO: return a new list ordered from largest to smallest\n"
            "    pass\n"
        ),
    },
    "lists-practice-1": {
        "starter_code": (
            "def total_weight(item_weights):\n"
            "    # TODO: return the weight of everything added together\n"
            "    pass\n"
        ),
    },
    "lists-checkpoint": {
        "starter_code": (
            "def middle_element(lst):\n"
            "    # TODO: return the middle item of this odd-length list\n"
            "    pass\n"
        ),
    },
    "loops-practice-1": {
        "description": (
            "Apply a percentage discount to all prices in a list using a "
            "comprehension: each price is reduced by `discount_pct` percent."
        ),
        "starter_code": (
            "def apply_discounts(prices, discount_pct):\n"
            "    # TODO: return a new list with every price discounted\n"
            "    pass\n"
        ),
    },
    "numbers-step-2": {
        "starter_code": (
            "def get_remainder(dividend, divisor):\n"
            "    # TODO: return what is left over after dividing evenly\n"
            "    pass\n"
        ),
    },
    "pytest-testing-practice-1": {
        "description": (
            "Implement `approx_equal(a, b, tol=1e-6)` for float comparisons in "
            "tests: two numbers count as equal when their distance is within "
            "`tol`."
        ),
        "starter_code": (
            "def approx_equal(a, b, tol=1e-6):\n"
            "    # TODO: return True when a and b are within tol of each other\n"
            "    pass\n"
        ),
    },
    "string-methods-step-1": {
        "starter_code": (
            "def make_loud(s):\n"
            "    # TODO: return s in capital letters\n"
            "    pass\n"
            "\n"
            "def is_question(s):\n"
            "    # TODO: return True when s ends with a question mark\n"
            "    pass\n"
        ),
    },
    "string-methods-step-2": {
        "starter_code": (
            "def clean_and_censor(s, word, mask):\n"
            "    # TODO: trim the ends, then swap word for mask\n"
            "    pass\n"
        ),
    },
    "string-methods-practice-1": {
        "starter_code": (
            "def sanitize_email(raw_email):\n"
            "    # TODO: return the address trimmed and in lower case\n"
            "    pass\n"
        ),
    },
    "string-methods-checkpoint": {
        "starter_code": (
            "def hashtagify(word):\n"
            "    # TODO: return the word dressed up as a hashtag\n"
            "    pass\n"
        ),
    },
    "strings-practice-1": {
        "starter_code": (
            "def format_badge(name, role):\n"
            "    # TODO: return the badge text for this name and role\n"
            "    pass\n"
        ),
    },
    "strings-checkpoint": {
        "starter_code": (
            "def wrap_string(s, char):\n"
            "    # TODO: return s with char on both sides\n"
            "    pass\n"
        ),
    },
    "type-hints-dataclasses-01": {
        "starter_code": (
            "from dataclasses import dataclass, replace\n"
            "\n"
            "@dataclass(frozen=True)\n"
            "class Config:\n"
            "    host: str\n"
            "    port: int = 80\n"
            "\n"
            "def with_port(cfg: Config, port: int) -> Config:\n"
            "    # TODO: return a new Config that uses the given port\n"
            "    pass\n"
        ),
    },
    "type-hints-dataclasses-checkpoint": {
        "starter_code": (
            "from dataclasses import dataclass\n"
            "\n"
            "@dataclass\n"
            "class Pair:\n"
            "    left: str\n"
            "    right: str\n"
            "\n"
            "    def swap(self) -> 'Pair':\n"
            "        # TODO: return a Pair with the two sides exchanged\n"
            "        pass\n"
        ),
    },
    # ---------------------------------------------------------------- TypeScript
    "ts-04": {
        "starter_code": (
            "export interface ApiResponse<T> {\n"
            "    data: T;\n"
            "    status: number;\n"
            "}\n"
            "\n"
            "export function wrapData<T>(data: T): ApiResponse<T> {\n"
            "    // TODO: return the data together with the OK status code\n"
            '    throw new Error("not implemented");\n'
            "}\n"
        ),
    },
    # -------------------------------------------- round 2: literal-bearing TODOs
    "java-variables-step-1": {
        "starter_code": (
            "public class Solution {\n"
            "    public static String getLanguage() {\n"
            "        // TODO: return the name of the language\n"
            "        return null;\n"
            "    }\n"
            "}\n"
        ),
    },
    "js-02": {
        "starter_code": (
            "// TODO: return the button object described in the task\n"
            "const createButton = (text) => ({\n"
            "    tag: '', textContent: '', disabled: true\n"
            "});\n"
            "module.exports = { createButton };\n"
        ),
    },
    "js-07": {
        "starter_code": (
            "// TODO: export the app name, then build the title from it\n"
            "export const appName = '';\n"
            "\n"
            "export function formatTitle(title) {\n"
            "    return title;\n"
            "}\n"
        ),
    },
    "exceptions-checkpoint": {
        "starter_code": (
            "def read_config(data):\n"
            "    # TODO: return the host from data, raising ValueError if absent\n"
            "    pass\n"
        ),
    },
    "tuples-practice-1": {
        "starter_code": (
            "def format_location(coord):\n"
            "    # TODO: unpack the coordinate and build the label from the task\n"
            "    pass\n"
        ),
    },
    "ts-02": {
        "starter_code": (
            "export interface User {\n"
            "    id: number;\n"
            "    name: string;\n"
            "}\n"
            "\n"
            "export function getId(input: number | User): number {\n"
            "    // TODO: narrow the union before reading the id\n"
            "    return 0;\n"
            "}\n"
        ),
    },
    "ts-05": {
        "starter_code": (
            "export function describeValue(value: string | number | boolean): string {\n"
            "    // TODO: return the name of the value's primitive type\n"
            "    return '';\n"
            "}\n"
        ),
    },
}

# Exercise-level fixes. ``question`` is the text the learner reads while
# composing, so an answer token repeated there is the same leak as a
# pre-filled editor; these reword the prompt to describe the goal instead.
EXERCISE_FIXES: dict[str, dict[str, object]] = {
    "cpp-ex-1b": {
        "question": (
            "In C++, `std::cout` prints the value of what follows it. "
            "What will `std::cout << 7 + 5;` display?"
        ),
        "options": ["12", "7 + 5", "75", "Nothing"],
        "correct_answer": "12",
        "explanation": "std::cout evaluates the expression and prints the result, so 7 + 5 shows 12.",
    },
    "cpp-ex-2b": {
        "starter_code": (
            "#include <string>\n"
            "\n"
            "std::string get_language() {\n"
            "    // TODO: return the language name as a string\n"
            '    return "";\n'
            "}\n"
        ),
    },
    "java-ex-1a": {
        "question": "Which keyword sends a value back to the caller of a Java method?",
    },
    "java-ex-1b": {
        "question": "Complete the return statement so the method gives back the language name:",
    },
    "java-exam-1": {
        "question": "Which Java type does a method declare when it produces a whole number?",
    },
    "py-ex-1a": {
        "worked_example_takeaway": "An assignment stores the text in a variable named language.",
    },
    "py-ex-2a": {
        "worked_example": 'greeting = "Hello"',
    },
    "py-exam-2": {
        "question": "Complete the assignment so that x holds ten:",
    },
    "py-num-ex-1a": {
        "question": "Store the number of apples in a variable, then total the fruit:",
    },
    "py-recipe-ex-1": {
        "question": "Calculate total_time by adding the two existing time variables:",
        "worked_example_takeaway": "Adding the two preparation times gives the total time.",
    },
    "py-chk-2": {
        "question": "Complete the concatenation so result reads Hello World:",
    },
    "py-bool-chk-1": {
        "question": "What does `not True` evaluate to in Python?",
    },
}


def apply_fixes(root: Path = CURRICULUM_ROOT, dry_run: bool = False) -> list[str]:
    """Patch every lesson and exercise in the fix tables; return changed ids."""
    remaining_lessons = dict(FIXES)
    remaining_exercises = dict(EXERCISE_FIXES)
    changed: list[str] = []
    for path in sorted(root.rglob("*.json")):
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        touched = False
        for lesson in payload.get("lessons") or []:
            if not isinstance(lesson, dict):
                continue
            lesson_id = lesson.get("id")
            patch = remaining_lessons.pop(lesson_id, None) if isinstance(lesson_id, str) else None
            if patch:
                for field, value in patch.items():
                    if lesson.get(field) != value:
                        lesson[field] = value
                        touched = True
                changed.append(str(lesson_id))
            for exercise in _exercises_of(lesson):
                ex_patch = remaining_exercises.pop(exercise.get("id"), None)
                if not ex_patch:
                    continue
                for field, value in ex_patch.items():
                    if exercise.get(field) != value:
                        exercise[field] = value
                        touched = True
                changed.append(f"{lesson_id}/{exercise.get('id')}")
        if touched and not dry_run:
            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
    missing = sorted(remaining_lessons) + sorted(remaining_exercises)
    if missing:
        raise SystemExit(f"FIXES references unknown items: {missing}")
    return changed


def _exercises_of(lesson: dict) -> list[dict]:
    """Every sublesson and mastery-exam exercise belonging to a lesson."""
    out: list[dict] = []
    for sub in lesson.get("sublessons") or []:
        if isinstance(sub, dict):
            out.extend(ex for ex in (sub.get("exercises") or []) if isinstance(ex, dict))
    out.extend(ex for ex in (lesson.get("mastery_exam") or []) if isinstance(ex, dict))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    changed = apply_fixes(dry_run=args.dry_run)
    verb = "would patch" if args.dry_run else "patched"
    print(f"{verb} {len(changed)} lessons")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
