"""Wave 3: twelve authored items for python and cpp, every claim executed first.

Two things make this wave different from a normal content dump.

1. **A content-verification gate.** Any item whose stem or options assert a
   number, a boolean or an output carries a ``_verify`` list of small programs.
   Each one is compiled/run in the real sandbox, and the item is *not written*
   unless every observed result matches what the item claims. So an option like
   "`double y = 5 / 2` gives 2.5" cannot survive on a guess - the compiler said
   2, and that is what the item says. The ``_verify`` channel is stripped before
   writing, because it is authoring evidence, not learner content.
2. **The code-item proof from wave 2 is kept**: a canonical solution must pass
   the item's own tests and the starter must fail them, so nothing ships solved
   and nothing ships with a broken key.

Type mix, per the measurement in wave 1/2: 2 ``code``, 3 ``matching``,
3 ``select_multiple``, 1 ``output_prediction``, 2 ``debugging``, plus 1 more
``code`` and 1 ``matching`` for cpp. Still zero mcq and zero true_false.

    python -m backend.patch_wave3_items             # verify + write
    python -m backend.patch_wave3_items --replace   # re-apply a corrected item
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

BOOLEANS_PROGRAM = (
    "def can_enter_club(has_vip_pass, is_on_guestlist):\n"
    "    return has_vip_pass or is_on_guestlist\n"
    "\n"
    "print(can_enter_club(False, True), can_enter_club(False, False),"
    " not can_enter_club(True, False))\n"
)

TEMP_BUGGY = (
    "def temperature_status(temp):\n"
    "    if temp < 15:\n"
    "        return \"Cold\"\n"
    "    elif temp < 28:\n"
    "        return \"Warm\"\n"
    "    return \"Hot\"\n"
    "\n"
    "print(temperature_status(28), temperature_status(15), temperature_status(29))\n"
)

TEMP_FIXED = TEMP_BUGGY.replace("elif temp < 28:", "elif temp <= 28:")

POWER_BUGGY = (
    "long long power(int base, int exp) {\n"
    "    long long result = 1;\n"
    "    for (int i = 0; i <= exp; ++i) { result *= base; }\n"
    "    return result;\n"
    "}\n"
    "#include <iostream>\n"
    "int main() { std::cout << power(2, 5) << std::endl; return 0; }\n"
)

POWER_FIXED = POWER_BUGGY.replace("i <= exp", "i < exp")

CPP_STORE_HALF = (
    "#include <iostream>\n"
    "int main() {\n"
    "    double x = 5.0 / 2.0; double y = 5 / 2; double z = 2.5;\n"
    "    int w = 5.0 / 2.0; float v = 2.5f;\n"
    "    std::cout << x << '|' << y << '|' << z << '|' << w << '|' << v << std::endl;\n"
    "    return 0;\n"
    "}\n"
)


def _code(item_id, question, starter, solution, tests, verify=None):
    return {"id": item_id, "type": "code", "question": question,
            "starter_code": starter, "solution_code": solution, "tests": tests,
            "xp_reward": CODE_XP, "_verify": verify or []}


def _match(item_id, question, pairs, explanation, verify=None):
    return {"id": item_id, "type": "matching", "question": question,
            "pairs": [{"left": l, "right": r} for l, r in pairs],
            "correct_answer": {l: r for l, r in pairs},
            "explanation": explanation, "xp_reward": RECALL_XP, "_verify": verify or []}


def _multi(item_id, question, options, answers, explanation, verify=None):
    return {"id": item_id, "type": "select_multiple", "question": question,
            "options": options, "correct_answer": answers,
            "explanation": explanation, "xp_reward": RECALL_XP, "_verify": verify or []}


def _out(item_id, question, options, answer, explanation, verify):
    return {"id": item_id, "type": "output_prediction", "question": question,
            "options": options, "correct_answer": answer,
            "explanation": explanation, "xp_reward": RECALL_XP, "_verify": verify}


def _dbg(item_id, question, options, answer, explanation, verify):
    return {"id": item_id, "type": "debugging", "question": question,
            "options": options, "correct_answer": answer,
            "explanation": explanation, "xp_reward": RECALL_XP, "_verify": verify}


def sub(sub_id, title, exercises):
    return {"id": sub_id, "title": title, "order": 1, "exercises": exercises}


ITEMS: dict[tuple[str, str], dict] = {
    # ══════════════════════════════ python ══════════════════════════════
    ("python", "booleans-step-2"): sub("bool-or-not-sub", "Predict the output", [
        _out(
            "bool-or-not-out-1",
            "What does this program print?\n\n```python\n" + BOOLEANS_PROGRAM + "```",
            # every option below is the observed stdout of a variant of this
            # program; a fourth variant (swapping the first call's arguments)
            # printed the same text as the answer and was therefore not offered.
            ["True False False", "False False True", "True False True"],
            "True False False",
            "`or` is True when at least one side is True, so (False, True) gives "
            "True and (False, False) gives False; `not` then flips the third call, "
            "which was True, to False. The other options are what `and` instead of "
            "`or`, or dropping the `not`, would print.",
            [
                {"language": "python", "code": BOOLEANS_PROGRAM, "expect": "True False False"},
                {"language": "python",
                 "code": BOOLEANS_PROGRAM.replace("has_vip_pass or is_on_guestlist",
                                                  "has_vip_pass and is_on_guestlist"),
                 "expect": "False False True"},
                {"language": "python",
                 "code": BOOLEANS_PROGRAM.replace(" not can_enter_club(True, False)",
                                                  " can_enter_club(True, False)"),
                 "expect": "True False True"},
            ],
        ),
    ]),
    ("python", "numbers-step-1"): sub("division-kinds-sub", "Match the operation", [
        _match(
            "division-kinds-match-1",
            "This lesson separates true division from floor division. Match each "
            "expression to the value it produces.",
            [
                ("7 / 2", "3.5"),
                ("7 // 2", "3"),
                ("7 % 2", "1"),
                ("-7 // 2", "-4"),
            ],
            "`/` keeps the fraction, `//` rounds *down*, and `%` is the remainder. "
            "Rounding down, not toward zero, is why -7 // 2 is -4.",
            [{"language": "python", "code": "print(7 / 2, 7 // 2, 7 % 2, -7 // 2)",
              "expect": "3.5 3 1 -4"}],
        ),
    ]),
    ("python", "comparisons-step-1"): sub("compare-ops-sub", "Match the operator", [
        _match(
            "compare-ops-match-1",
            "Match each comparison operator to the question it asks.",
            [("a == b", "do the two values hold the same content?"),
             ("a != b", "are the two values different?"),
             ("a > b", "is a strictly larger than b?"),
             ("a <= b", "is a no more than b?")],
            "`==` and `=` are not the same thing: one compares, the other assigns.",
        ),
    ]),
    ("python", "conditionals-step-2"): sub("elif-boundary-dbg-sub", "Find the defect", [
        _dbg(
            "elif-boundary-dbg-1",
            "The lesson defines Cold below 15, Warm from 15 through 28, and Hot "
            "above 28. This program prints `Hot Warm Hot` for "
            "`(28, 15, 29)`. What is wrong with it?\n\n```python\n"
            + TEMP_BUGGY.split("print(")[0] + "```",
            ["`elif temp < 28` should be `elif temp <= 28`, so 28 counts as Warm",
             "`if temp < 15` should be `if temp <= 15`, so 15 counts as Cold",
             "the final `return \"Hot\"` should be `return \"Warm\"`",
             "nothing is wrong - `Hot` is correct for 28 because it is the last branch"],
            "`elif temp < 28` should be `elif temp <= 28`, so 28 counts as Warm",
            "Only the upper boundary is off: 28 fails both `< 15` and `< 28`, so it "
            "falls through to Hot. The lower boundary already treats 15 as Warm, "
            "which is what the lesson asks for.",
            [{"language": "python", "code": TEMP_BUGGY, "expect": "Hot Warm Hot"},
             {"language": "python", "code": TEMP_FIXED, "expect": "Warm Warm Hot"}],
        ),
    ]),
    ("python", "booleans-practice-1"): sub("access-rule-sub", "Select the combinations that open the door", [
        _multi(
            "access-rule-multi-1",
            "The rule is: the door opens when the emergency override is active, OR "
            "when the keycard is held AND the passcode is correct. Select every "
            "combination that opens the door. (keycard, passcode, emergency)",
            ["keycard + correct passcode, no emergency",
             "no keycard, no passcode, emergency active",
             "no keycard, correct passcode, emergency active",
             "keycard, wrong passcode, no emergency",
             "no keycard, no passcode, no emergency"],
            ["keycard + correct passcode, no emergency",
             "no keycard, no passcode, emergency active",
             "no keycard, correct passcode, emergency active"],
            "Emergency alone opens the door whatever else is true; without it, both "
            "the keycard and the correct passcode are needed.",
            [{"language": "python",
              "code": "def unlock_door(k, p, e):\n    return e or (k and p)\n"
                      "combos = [(True, True, False), (False, False, True), "
                      "(False, True, True), (True, False, False), "
                      "(False, False, False)]\n"
                      "print(sum(1 for k, p, e in combos if unlock_door(k, p, e)))",
              "expect": "3"}],
        ),
    ]),
    ("python", "numbers-step-2"): sub("last-digit-code-sub", "Write it with modulo", [
        _code(
            "last-digit-code-1",
            "Implement `last_digit(n)` returning the ones digit of a non-negative "
            "integer - the same remainder idea this lesson uses, with 10.",
            "def last_digit(n):\n    # TODO: return the ones digit\n    return 0\n",
            "def last_digit(n):\n    return n % 10\n",
            [{"name": "test_last_digit_multi",
              "unittest_code": "def test_last_digit_multi(self):\n"
                               "    self.assertEqual(last_digit(123), 3)\n"},
             {"name": "test_last_digit_single",
              "unittest_code": "def test_last_digit_single(self):\n"
                               "    self.assertEqual(last_digit(7), 7)\n"},
             {"name": "test_last_digit_round",
              "unittest_code": "def test_last_digit_round(self):\n"
                               "    self.assertEqual(last_digit(40), 0)\n"}],
        ),
    ]),

    # ═══════════════════════════════ cpp ════════════════════════════════
    ("cpp", "cpp-loops-step-1"): sub("cpp-factorial-code-sub", "Write the loop", [
        _code(
            "cpp-factorial-code-1",
            "Implement `factorial(int n)` returning n! as a long long, with 0! "
            "defined as 1. Accumulate in a loop the way `sum_range` does.",
            "long long factorial(int n) {\n"
            "    long long result = 1;\n"
            "    // TODO: multiply result by each value from 2 up to n\n"
            "    return 0;\n"
            "}\n",
            "long long factorial(int n) {\n"
            "    long long result = 1;\n"
            "    for (int i = 2; i <= n; ++i) { result *= i; }\n"
            "    return result;\n"
            "}\n",
            [{"name": "test_factorial_five", "test_code": "if (factorial(5) != 120) throw std::runtime_error(\"5!\");"},
             {"name": "test_factorial_zero", "test_code": "if (factorial(0) != 1) throw std::runtime_error(\"0!\");"},
             {"name": "test_factorial_one", "test_code": "if (factorial(1) != 1) throw std::runtime_error(\"1!\");"},
             {"name": "test_factorial_ten", "test_code": "if (factorial(10) != 3628800) throw std::runtime_error(\"10!\");"}],
        ),
    ]),
    ("cpp", "cpp-loops-checkpoint"): sub("cpp-vowels-code-sub", "Write the counting loop", [
        _code(
            "cpp-vowels-code-1",
            "Implement `count_vowels(std::string s)` returning how many characters "
            "are a, e, i, o or u (lower case only). Count inside a loop, as "
            "`count_multiples` does.",
            "#include <string>\n"
            "int count_vowels(std::string s) {\n"
            "    int count = 0;\n"
            "    // TODO: scan the string and count aeiou\n"
            "    return count;\n"
            "}\n",
            "#include <string>\n"
            "int count_vowels(std::string s) {\n"
            "    int count = 0;\n"
            "    for (char c : s) {\n"
            "        if (c == 'a' || c == 'e' || c == 'i' || c == 'o' || c == 'u') {\n"
            "            count++;\n"
            "        }\n"
            "    }\n"
            "    return count;\n"
            "}\n",
            [{"name": "test_count_phrase", "test_code": "if (count_vowels(\"orchestra\") != 3) throw std::runtime_error(\"phrase\");"},
             {"name": "test_count_none", "test_code": "if (count_vowels(\"rhythm\") != 0) throw std::runtime_error(\"none\");"},
             {"name": "test_count_empty", "test_code": "if (count_vowels(\"\") != 0) throw std::runtime_error(\"empty\");"},
             {"name": "test_count_upper_ignored", "test_code": "if (count_vowels(\"AEIOU\") != 0) throw std::runtime_error(\"case\");"}],
        ),
    ]),
    ("cpp", "cpp-variables-01"): sub("cpp-half-value-sub", "Select the ones that keep 2.5", [
        _multi(
            "cpp-half-value-multi-1",
            "Each declaration below is meant to end up holding 2.5. Select every "
            "one that actually does.",
            ["double x = 5.0 / 2.0;",
             "double y = 5 / 2;",
             "double z = 2.5;",
             "int w = 5.0 / 2.0;",
             "float v = 2.5f;"],
            ["double x = 5.0 / 2.0;", "double z = 2.5;", "float v = 2.5f;"],
            "`5 / 2` is integer division and yields 2 before the double ever sees "
            "it, and `int w` truncates the 2.5 it is given. One operand written as "
            "a decimal is enough to make the division floating-point.",
            [{"language": "cpp", "code": CPP_STORE_HALF, "expect": "2.5|2|2.5|2|2.5"}],
        ),
    ]),
    ("cpp", "cpp-functions-step-2"): sub("cpp-const-ref-sub", "Select the const references", [
        _multi(
            "cpp-const-ref-multi-1",
            "This lesson passes large objects by `const &` to avoid a copy while "
            "guaranteeing the function cannot change them. Select every parameter "
            "declaration that does both.",
            ["const std::string& name", "std::string name", "const std::string& text",
             "std::string& ref"],
            ["const std::string& name", "const std::string& text"],
            "`const &` borrows without copying and forbids writes. Plain `std::string` "
            "copies, and a non-const reference can modify the caller's object.",
        ),
    ]),
    ("cpp", "cpp-conditionals-step-2"): sub("cpp-logic-ops-sub", "Match the operator to its rule", [
        _match(
            "cpp-logic-ops-match-1",
            "Match each C++ expression to when it is true.",
            [("a && b", "both a and b are true"),
             ("a || b", "at least one of a and b is true"),
             ("!flag", "flag is false"),
             ("n % 2 == 0", "n divides by 2 with no remainder")],
            "`&&` needs both, `||` needs one, `!` flips, and `%` gives the remainder "
            "that decides divisibility.",
        ),
    ]),
    ("cpp", "cpp-loops-practice-1"): sub("cpp-power-loop-dbg-sub", "Find the defect", [
        _dbg(
            "cpp-power-loop-dbg-1",
            "`power(base, exp)` should return base raised to exp, and the test "
            "expects `power(2, 5)` to be 32. It prints 64 instead. What is wrong?\n\n"
            "```cpp\n" + POWER_BUGGY.split("#include")[0].strip() + "\n```",
            ["`i <= exp` runs one multiplication too many; it should be `i < exp`",
             "the loop should start at `int i = 1` so the exponent is counted",
             "`result` should be initialised to 0 so the first multiply seeds it",
             "nothing is wrong; 2^5 is 64"],
            "`i <= exp` runs one multiplication too many; it should be `i < exp`",
            "Starting `result` at 1 and multiplying `exp` times is the whole "
            "algorithm; looping to `<= exp` performs exp + 1 multiplications. "
            "Initialising `result` to 0 would make every answer 0.",
            [{"language": "cpp", "code": POWER_BUGGY, "expect": "64"},
             {"language": "cpp", "code": POWER_FIXED, "expect": "32"}],
        ),
    ]),
}


# ── verification gates ───────────────────────────────────────────────────────

def verify_claims() -> list[str]:
    """Execute every ``_verify`` program and compare against the claim."""
    from backend.verify_lessons import LOCAL_LANGS, run_sandbox

    problems: list[str] = []
    for (course, lesson_id), sublesson in ITEMS.items():
        for exercise in sublesson["exercises"]:
            for check in exercise.get("_verify") or []:
                language = check.get("language", course)
                use_docker = language not in LOCAL_LANGS
                result = run_sandbox(language, check["code"],
                                     [{"name": "observe", "expected_stdout": "\x00",
                                       "required": False}], use_docker)
                observed = (result.get("stdout") or "").strip()
                if observed != check["expect"].strip():
                    problems.append(
                        f"{course}/{lesson_id}/{exercise['id']}: claim "
                        f"{check['expect']!r} but the sandbox printed {observed!r}")
                else:
                    print(f"  verified: {exercise['id']} -> {observed!r}")
    return problems


def prove_code_items() -> list[str]:
    """Canonical solution must pass the item's tests; starter must fail them."""
    from backend.verify_lessons import LOCAL_LANGS, eval_code

    problems: list[str] = []
    for (course, lesson_id), sublesson in ITEMS.items():
        for exercise in sublesson["exercises"]:
            if exercise["type"] != "code":
                continue
            label = f"{course}/{lesson_id}/{exercise['id']}"
            use_docker = course not in LOCAL_LANGS
            solution = eval_code(course, exercise["solution_code"], exercise["tests"], use_docker)
            if not solution["all_pass"]:
                problems.append(f"{label}: solution fails "
                                f"({', '.join(solution['failed']) or solution['error']})")
                continue
            starter = eval_code(course, exercise["starter_code"], exercise["tests"], use_docker)
            if starter["syntax_error"]:
                problems.append(f"{label}: starter does not compile")
            elif starter["all_pass"]:
                problems.append(f"{label}: starter already passes - ships solved")
            else:
                print(f"  proven: {label} (solution passes, starter fails)")
    return problems


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
            if key not in ITEMS:
                continue
            sublesson = json.loads(json.dumps(ITEMS[key]))
            for exercise in sublesson["exercises"]:
                exercise.pop("_verify", None)
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


def main() -> int:
    claims = sum(len(e.get("_verify") or []) for s in ITEMS.values() for e in s["exercises"])
    print(f"executing {claims} content claims...")
    problems = verify_claims()
    print("execution-proving code items...")
    problems += prove_code_items()
    if problems:
        print("\nrefusing to write:")
        for problem in problems:
            print("  -", problem)
        return 1

    written = apply_items(replace="--replace" in sys.argv)
    print(f"\nwave 3 items written: {len(written)} of {len(ITEMS)}")
    for item in written:
        print(f"  + {item}")
    return 0 if len(written) == len(ITEMS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
