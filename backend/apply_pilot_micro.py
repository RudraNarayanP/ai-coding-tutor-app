"""Install the three pilot micro lessons. Run once; safe to re-run."""

from __future__ import annotations

import json
from itertools import permutations
from pathlib import Path

from backend.answer_order import key_shown_first

ROOT = Path(__file__).resolve().parent.parent / "curriculum" / "python" / "modules"

HINTS = {
    "store": [
        "A name can hold text for later.",
        "The store happens between the name and the text.",
        'language = "Python"',
    ],
    "symbol": [
        "It is not the comparison symbol.",
        "It sits between the name and the text.",
        "=",
    ],
    "print-language": [
        "The print line uses the name, not a second copy of the text.",
        "Whatever was stored is what shows up.",
        "Python",
    ],
    "build-store": [
        "Start with the name.",
        "Then the store symbol, then the quoted text.",
        'language = "Python"',
    ],
    "fill-symbol": [
        "The blank is the store symbol.",
        "A comparison uses two of that symbol.",
        "=",
    ],
    "bug-store": [
        "The print is fine once the name exists.",
        "The first line compares two values.",
        "Line 1 should store with one equals sign.",
    ],
    "print-snack": [
        "Look at the text that was stored in the name.",
        "Print shows that text without quote marks.",
        "taco",
    ],
    "write-store": [
        "The blank is the text value.",
        "Quotes go around the letters.",
        'language = "Python"',
    ],
    "range-teach": [
        "The end number is a stop, not a visit.",
        "Count 1, then 2, then stop before 4.",
        "1, 2, 3",
    ],
    "range-walk": [
        "The stop value is not visited.",
        "Start at 1 and stop before 4.",
        "1, 2, 3",
    ],
    "range-sum": [
        "Add each number the loop actually visits.",
        "That is 1, then 2, then 3.",
        "6",
    ],
    "range-build": [
        "The line starts with for.",
        "in range comes after the name.",
        "for i in range(1, 4): print(i)",
    ],
    "range-fill": [
        "The stop is one past the last number you want.",
        "You want 1, 2, and 3.",
        "4",
    ],
    "range-bug": [
        "The body line is a normal print.",
        "A for header ends with a colon.",
        "Line 1 needs a colon.",
    ],
    "range-count": [
        "Subtract the start from the stop.",
        "5 minus 2 is how many steps you get.",
        "3",
    ],
    "range-write": [
        "The walk starts at 1.",
        "It must include n and exclude n + 1.",
        "1, n + 1",
    ],
    "return-teach": [
        "Showing a value is not the same as handing it back.",
        "The caller receives whatever comes after this keyword.",
        "return x * 2",
    ],
    "return-word": [
        "It is not the keyword that only displays text.",
        "The caller needs a value, not a display.",
        "return",
    ],
    "return-print": [
        "double is called with 5.",
        "The function hands back twice that number.",
        "10",
    ],
    "return-build": [
        "The header names the function and its input.",
        "The next chip hands back twice the input.",
        "def double(x): return x * 2",
    ],
    "return-fill": [
        "The blank is the keyword that hands a value back.",
        "Displaying the product would leave the caller with nothing.",
        "return",
    ],
    "return-bug": [
        "The last line prints whatever the function gives back.",
        "The second line displays the product and gives nothing back.",
        "Line 2 should hand the product back.",
    ],
    "return-greet": [
        "greet hands a short word back.",
        "Print shows that word, without quote marks.",
        "hi",
    ],
    "return-write": [
        "The blank is the whole hand-back line.",
        "Twice x is x times 2.",
        "return x * 2",
    ],
}


def safe_options(exercise_id: str, options: list[str], answer: str) -> list[str]:
    """Stored order is what the lesson player shows, and the old widget shuffles.

    The key must not be the first stored choice or the first shuffled button.
    """
    for perm in permutations(options):
        seq = list(perm)
        if seq[0] != answer and not key_shown_first(exercise_id, seq, answer):
            return seq
    raise SystemExit(f"no safe option order for {exercise_id}")


def ex(eid, etype, question, **kwargs):
    options = kwargs.get("options")
    answer = kwargs.get("correct_answer")
    if isinstance(options, list) and isinstance(answer, str) and answer in options and len(options) >= 3:
        kwargs["options"] = safe_options(eid, options, answer)
    item = {
        "id": eid,
        "type": etype,
        "question": question,
        "hints": kwargs.pop("hints"),
        "explanation": kwargs.pop("explanation"),
        "xp_reward": 0 if etype == "teach" else 10,
    }
    item.update(kwargs)
    return item


def pack(sub_id, title, exercises):
    return [{
        "id": sub_id,
        "title": title,
        "description": "",
        "order": 1,
        "exercises": exercises,
    }]


PILOTS = {
    "basics.json": {
        "variables-step-1": {
            "title": "Store text in a name",
            "player_mode": "micro",
            "learning_objectives": ["One equals sign stores a value in a name."],
            "sublessons": pack("py-var-micro", "Store text", [
                ex("var-teach", "teach", "One equals sign stores a value in a name.",
                   worked_example='language = "Python"', hints=HINTS["store"],
                   explanation="One equals sign stores a value in a name."),
                ex("var-mcq", "mcq", "Which symbol stores a value in a name?",
                   options=["->", "=", ":=", "=="], correct_answer="=",
                   hints=HINTS["symbol"], explanation="One equals sign stores a value, while two equals signs compare."),
                ex("var-predict", "output_prediction", "language holds text. What does the print line show?",
                   starter_code='language = "Python"\nprint(language)\n',
                   options=["language", "Python", '"Python"', "None"], correct_answer="Python",
                   hints=HINTS["print-language"], explanation="Print shows the text that was stored, without quotes."),
                ex("var-order", "ordering", "Build the line that stores the text Python in the name language.",
                   options=["language", "=", '"Python"', "=="],
                   correct_answer=["language", "=", '"Python"'],
                   hints=HINTS["build-store"], explanation="The name, one equals sign, then the quoted text."),
                ex("var-fill", "fill_blank", "Fill the symbol that stores the text in the name.",
                   starter_code='language ___ "Python"\n',
                   options=["=", "==", ":=", "->"], correct_answer="=",
                   hints=HINTS["fill-symbol"], explanation="One equals sign stores the text in the name."),
                ex("var-bug", "debugging", "The name is never created, so printing it crashes. Which line is wrong?",
                   starter_code='language == "Python"\nprint(language)\n',
                   correct_answer="1", hints=HINTS["bug-store"],
                   explanation="Line 1 compares instead of storing, so the name is never created."),
                ex("var-predict-2", "output_prediction", "A snack name was stored. What does print show?",
                   starter_code='snack = "taco"\nprint(snack)\n',
                   options=["taco", "snack", '"taco"', "None"], correct_answer="taco",
                   hints=HINTS["print-snack"], explanation="Print shows taco, the text that was stored."),
                ex("var-write", "code", "Store the text Python in language, then print it.",
                   starter_code="language = ___\nprint(language)\n",
                   solution_code='language = "Python"\nprint(language)\n',
                   tests=[{
                       "name": "prints_the_stored_text",
                       "description": "prints Python",
                       "expected_stdout": "Python\n",
                       "required": True,
                   }],
                   hints=HINTS["write-store"], explanation="One equals sign stores the text, and print shows it."),
            ]),
        },
    },
    "loops.json": {
        "loops-step-1": {
            "title": "Loop with range",
            "player_mode": "micro",
            "learning_objectives": ["range stops before its end, so range(1, 4) visits 1, 2, and 3."],
            "sublessons": pack("loops-micro", "Loop with range", [
                ex("loop-teach", "teach", "range stops before its end, so range(1, 4) visits 1, 2, and 3.",
                   worked_example="for i in range(1, 4):\n    print(i)",
                   hints=HINTS["range-teach"],
                   explanation="The end value is a stop, not a number the loop visits."),
                ex("loop-mcq", "mcq", "Which numbers does range(1, 4) visit?",
                   options=["1, 2, 3, 4", "0, 1, 2, 3", "1, 2, 3", "4, 3, 2, 1"],
                   correct_answer="1, 2, 3", hints=HINTS["range-walk"],
                   explanation="range starts at 1 and stops before 4."),
                ex("loop-predict", "output_prediction", "The loop adds each number it visits. What is printed?",
                   starter_code="total = 0\nfor i in range(1, 4):\n    total = total + i\nprint(total)\n",
                   options=["10", "4", "6", "0"], correct_answer="6",
                   hints=HINTS["range-sum"], explanation="The loop visits 1, 2, and 3, and those add up to 6."),
                ex("loop-order", "ordering", "Build a loop that prints 1, then 2, then 3.",
                   options=["for", "i", "in", "range(1, 4):", "print(i)", "while"],
                   correct_answer=["for", "i", "in", "range(1, 4):", "print(i)"],
                   hints=HINTS["range-build"], explanation="for walks the range, and the colon starts the body."),
                ex("loop-fill", "fill_blank", "Fill the stop so the loop prints 1, then 2, then 3.",
                   starter_code="for i in range(1, ___):\n    print(i)\n",
                   options=["4", "3", "5", "1"], correct_answer="4",
                   hints=HINTS["range-fill"], explanation="Stop at 4 so the last visit is 3."),
                ex("loop-bug", "debugging", "The loop header is missing the mark that starts its body. Which line?",
                   starter_code="for i in range(1, 4)\n    print(i)\n",
                   correct_answer="1", hints=HINTS["range-bug"],
                   explanation="Line 1 is missing the colon that starts the loop body."),
                ex("loop-mcq-2", "mcq", "How many numbers does range(2, 5) visit?",
                   options=["2", "4", "5", "3"], correct_answer="3",
                   hints=HINTS["range-count"], explanation="2, 3, and 4 are three visits. 5 is the stop."),
                ex("loop-write", "code", "Add the squares from 1 through n. Use range.",
                   starter_code="def sum_squares(n):\n    total = 0\n    for i in range(___):\n        total += i * i\n    return total\n",
                   solution_code="def sum_squares(n):\n    total = 0\n    for i in range(1, n + 1):\n        total += i * i\n    return total\n",
                   tests=[{
                       "name": "test_sum_squares",
                       "description": "sum of squares up to 3 is 14",
                       "unittest_code": "def test_sum_squares(self):\n    self.assertEqual(sum_squares(3), 1 + 4 + 9)",
                       "required": True,
                   }],
                   hints=HINTS["range-write"], explanation="range(1, n + 1) visits 1 through n, and n is included."),
            ]),
        },
    },
    "functions.json": {
        "functions-step-1": {
            "title": "Send a value back",
            "player_mode": "micro",
            "learning_objectives": ["return sends a value back to the caller. print only displays it."],
            "sublessons": pack("fn-micro", "Send a value back", [
                ex("fn-teach", "teach", "return sends a value back to the caller. print only displays it.",
                   worked_example="def double(x):\n    return x * 2",
                   hints=HINTS["return-teach"],
                   explanation="return hands the value back. print only shows it."),
                ex("fn-mcq", "mcq", "Which keyword sends a value back from a function?",
                   options=["print", "send", "return", "yield"], correct_answer="return",
                   hints=HINTS["return-word"], explanation="return hands the value back. print only shows it."),
                ex("fn-predict", "output_prediction", "double is called with 5. What does print show?",
                   starter_code="def double(x):\n    return x * 2\nprint(double(5))\n",
                   options=["5", "25", "None", "10"], correct_answer="10",
                   hints=HINTS["return-print"], explanation="return hands back 10, and print shows that 10."),
                ex("fn-order", "ordering", "Build a function that hands back twice its input.",
                   options=["def double(x):", "return x * 2", "print(x * 2)", "pass"],
                   correct_answer=["def double(x):", "return x * 2"],
                   hints=HINTS["return-build"], explanation="The header names double, and return hands back twice x."),
                ex("fn-fill", "fill_blank", "Fill the keyword that hands the product back to the caller.",
                   starter_code="def double(x):\n    ___ x * 2\n",
                   options=["return", "print", "yield", "pass"], correct_answer="return",
                   hints=HINTS["return-fill"], explanation="return hands the product back. print would not."),
                ex("fn-bug", "debugging", "double(5) gives back nothing, so the last line shows None. Which line?",
                   starter_code="def double(x):\n    print(x * 2)\nprint(double(5))\n",
                   correct_answer="2", hints=HINTS["return-bug"],
                   explanation="Line 2 displays the product, so the function gives back None."),
                ex("fn-predict-2", "output_prediction", "greet hands a word back. What does print show?",
                   starter_code='def greet():\n    return "hi"\nprint(greet())\n',
                   options=["greet", "hi", "None", '"hi"'], correct_answer="hi",
                   hints=HINTS["return-greet"], explanation="return hands back hi, and print shows that word."),
                ex("fn-write", "code", "Finish double so it hands back twice its input.",
                   starter_code="def double(x):\n    ___\n",
                   solution_code="def double(x):\n    return x * 2\n",
                   tests=[{
                       "name": "test_double",
                       "description": "double 5 is 10",
                       "unittest_code": "def test_double(self):\n    self.assertEqual(double(5), 10)",
                       "required": True,
                   }],
                   hints=HINTS["return-write"], explanation="return x * 2 hands twice the input back to the caller."),
            ]),
        },
    },
}


def main() -> None:
    for filename, lessons in PILOTS.items():
        path = ROOT / filename
        data = json.loads(path.read_text(encoding="utf-8"))
        for lesson in data["lessons"]:
            patch = lessons.get(lesson["id"])
            if not patch:
                continue
            lesson.update(patch)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("updated", filename)


if __name__ == "__main__":
    main()
