"""Install micro lessons for every legacy lesson that is not already shipped.

Already-micro lessons and the five hand-authored boolean scripts are left
alone. Re-running this module will not overwrite them.

Questions are original. Official docs are linked only when a lesson has no
source URL. Each screen is executed or parsed before it is written.
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from itertools import combinations

from backend.micro_factory import _dedupe_descriptions, install, safe_options
from backend.micro_recipes import python_recipe
from backend.verify_lessons import hint_gives_answer, normalize, program_parses, run_sandbox

ROOT = Path(__file__).resolve().parent.parent / "curriculum"
SKIP = {
    "booleans",
    "booleans-step-1",
    "booleans-step-2",
    "booleans-step-3",
    "booleans-01",
}
# Hand-authored micro lessons. Their prompts already match the code.
KEEP_HAND = {
    "variables-step-1",
    "variables-step-2",
    "variables-01",
    "variables-practice-1",
    "variables-checkpoint",
    "numbers-step-1",
    "numbers-step-2",
    "numbers-01",
    "numbers-practice-1",
    "numbers-checkpoint",
    "loops-step-1",
    "conditionals-step-1",
    "conditionals-step-2",
    "functions-step-1",
}
PY = {"python", "py", "dsa", "ml", "ml-math", "ai", "fullstack"}
JS = {"javascript", "js", "typescript", "ts"}
SOURCES = {
    "python": ("Python official documentation", "https://docs.python.org/3/tutorial/", "PSF"),
    "dsa": ("Python official documentation", "https://docs.python.org/3/tutorial/datastructures.html", "PSF"),
    "ml": ("Python official documentation", "https://docs.python.org/3/tutorial/", "PSF"),
    "ml-math": ("Python official documentation", "https://docs.python.org/3/tutorial/", "PSF"),
    "ai": ("Python official documentation", "https://docs.python.org/3/tutorial/", "PSF"),
    "fullstack": ("Python official documentation", "https://docs.python.org/3/tutorial/", "PSF"),
    "javascript": ("MDN JavaScript reference", "https://developer.mozilla.org/en-US/docs/Web/JavaScript", "CC-BY-SA"),
    "typescript": ("TypeScript handbook", "https://www.typescriptlang.org/docs/handbook/intro.html", "Apache-2.0"),
    "java": ("The Java tutorials", "https://docs.oracle.com/javase/tutorial/", "Oracle"),
    "cpp": ("C++ reference", "https://en.cppreference.com/w/cpp/language", "CC-BY-SA"),
    "sql": ("SQLite language reference", "https://www.sqlite.org/lang.html", "Public domain"),
}
WORDS = (
    "amber birch cedar delta ember flint grove hazel ivory juniper kelp linen maple "
    "nectar olive pebble quartz ridge sage thyme umber violet willow yarrow zircon"
).split()
VERBS = {
    "add", "ask", "await", "bind", "build", "call", "cast", "check", "classify",
    "compare", "compute", "convert", "copy", "count", "create", "decode", "define",
    "delete", "encode", "filter", "find", "format", "group", "handle", "insert",
    "join", "limit", "make", "map", "meet", "merge", "open", "parse", "practice",
    "predict", "print", "query", "rank", "read", "return", "round", "scale",
    "score", "select", "sort", "store", "sum", "test", "train", "update", "use",
    "walk", "write",
}
GERUNDS = {
    "adding": "Add", "aggregating": "Aggregate", "assigning": "Assign",
    "awaiting": "Await", "balancing": "Balance", "binding": "Bind",
    "building": "Build", "calculating": "Calculate", "calling": "Call",
    "casting": "Cast", "catching": "Catch", "chaining": "Chain",
    "checking": "Check", "classifying": "Classify", "comparing": "Compare",
    "computing": "Compute", "converting": "Convert", "copying": "Copy",
    "counting": "Count", "creating": "Create", "decoding": "Decode",
    "defining": "Define", "deleting": "Delete", "dividing": "Divide",
    "drawing": "Draw", "encoding": "Encode", "extending": "Extend",
    "fetching": "Fetch", "filtering": "Filter", "finding": "Find",
    "formatting": "Format", "grouping": "Group", "handling": "Handle",
    "hashing": "Hash", "implementing": "Implement", "importing": "Import",
    "indexing": "Index", "inheriting": "Inherit", "initializing": "Initialize",
    "inserting": "Insert", "joining": "Join", "limiting": "Limit",
    "looping": "Loop", "making": "Make", "mapping": "Map", "measuring": "Measure",
    "merging": "Merge", "multiplying": "Multiply", "nesting": "Nest",
    "normalizing": "Normalize", "opening": "Open", "overloading": "Overload",
    "parsing": "Parse", "plotting": "Plot", "predicting": "Predict",
    "printing": "Print", "querying": "Query", "ranking": "Rank",
    "reading": "Read", "recursing": "Recurse", "reducing": "Reduce",
    "rendering": "Render", "replacing": "Replace", "returning": "Return",
    "rounding": "Round", "scaling": "Scale", "scoring": "Score",
    "searching": "Search", "selecting": "Select", "slicing": "Slice",
    "sorting": "Sort", "splitting": "Split", "storing": "Store",
    "subtracting": "Subtract", "summing": "Sum", "testing": "Test",
    "throwing": "Throw", "training": "Train", "traversing": "Traverse",
    "updating": "Update", "using": "Use", "validating": "Validate",
    "walking": "Walk", "writing": "Write",
}


def _scenes(count: int) -> list[str]:
    places = "harbor mesa orchard quarry attic depot ridge cove plaza marsh".split()
    roles = "clerks potters pickers crews archivists runners scouts bakers wardens smiths".split()
    verbs = "recount log weigh tag stamp hang sell roll paint stack".split()
    objs = "crates glazes apples slabs spools badges lanterns tickets wagons pixels".split()
    whens = [
        "before dawn", "at noon", "after rain", "at dusk", "tonight", "on monday",
        "after lunch", "near closing",
    ]
    out = []
    for when in whens:
        for obj in objs:
            for verb in verbs:
                for role in roles:
                    for place in places:
                        out.append(f"{place.capitalize()} {role} {verb} {obj} {when}")
                        if len(out) >= count:
                            return out
    raise SystemExit(f"only {len(out)} scenes for {count}")


def _plain(text: str) -> str:
    text = re.sub(r"^\d+\.\s*", "", text or "")
    text = text.replace("`", "")
    text = re.sub(r"\s*\([^)]*\)", "", text)
    text = re.sub(r"[^A-Za-z0-9 ,'-]", " ", text)
    return re.sub(r"\s+", " ", text).strip(" ,")


def verb_title(raw: str) -> str:
    words = _plain(raw).split()
    if not words:
        return "Practice this step"
    first = words[0].lower()
    if first in GERUNDS:
        words[0] = GERUNDS[first]
    elif first in VERBS:
        words[0] = words[0][0].upper() + words[0][1:]
    else:
        words.insert(0, "Practice")
    return " ".join(words[:6])[:52]


def _concept(lesson: dict) -> str:
    raw = ""
    objectives = lesson.get("learning_objectives") or []
    if objectives:
        raw = str(objectives[0])
    raw = raw or lesson.get("description") or lesson.get("title") or "this step"
    phrase = _plain(raw.split(".")[0])
    if len(phrase) > 88:
        phrase = phrase[:88].rsplit(" ", 1)[0]
    if phrase and phrase[0].isupper() and phrase[1:2].islower():
        phrase = phrase[0].lower() + phrase[1:]
    return phrase or "this step does one job"


def _family(language: str, blob: str) -> str:
    if language == "sql":
        for name, keys in (
            ("where", ("where", "filter")),
            ("distinct", ("distinct", "unique")),
            ("join", ("join",)),
            ("group", ("group", "aggregate", "count", "sum")),
            ("order", ("order", "sort", "limit")),
            ("insert", ("insert", "update", "delete", "transaction")),
        ):
            if any(key in blob for key in keys):
                return name
        return "select"
    for name, keys in (
        ("class", ("class", "__init__", "constructor", "object")),
        ("loop", ("loop", "for ", "while", "iterate")),
        ("cond", ("if ", "else", "conditional", "boolean")),
        ("fn", ("function", "return", "method", "def ", "lambda")),
        ("list", ("list", "array", "index", "slice")),
        ("dict", ("dict", "map", "record", "key")),
        ("text", ("string", "text", "concat")),
    ):
        if any(key in blob for key in keys):
            return name
    return "store"


def _word(seed: str, banned: str) -> str:
    banned_l = banned.lower()
    start = sum(seed.encode("utf-8")) % len(WORDS)
    for offset in range(len(WORDS)):
        word = WORDS[(start + offset) % len(WORDS)]
        if word not in banned_l:
            return word
    return "amber"


def _number(seed: str, banned: str) -> int:
    start = 20 + (sum(seed.encode("utf-8")) % 40)
    for offset in range(40):
        value = start + offset
        if str(value) not in banned:
            return value
    return 87


def _run(language: str, code: str) -> str:
    result = run_sandbox(language, code, [{"name": "probe", "required": True}], False)
    if result.get("error") and not result.get("tests"):
        raise SystemExit(f"{language} run failed: {result.get('error')} :: {code[:160]}")
    test = (result.get("tests") or [{}])[0]
    stdout = test.get("stdout") or ""
    if test.get("error") and not stdout.strip():
        raise SystemExit(f"{language} exec failed: {test.get('error')} :: {code[:160]}")
    return stdout


def _hide(text: str, answer: str) -> str:
    """Return a nudge that does not contain the answer."""
    from backend.prompt_align import render_nudge

    if not hint_gives_answer(text, answer) and "example" not in text.lower():
        return text
    return render_nudge(text or "this step", ["the snippet"], 0, answer)


def _pack(language: str, family: str, word: str, number: int) -> dict:
    """Code for one family. Questions are attached by the caller."""
    if language in PY or language in {"python"}:
        return _py_pack(family, word, number)
    if language in JS:
        return _js_pack(language, family, word, number)
    if language == "java":
        return _java_pack(family, word, number)
    if language in {"cpp", "c++"}:
        return _cpp_pack(family, word, number)
    if language == "sql":
        return _sql_pack(family, word, number)
    raise SystemExit(f"no pack for {language}")


def _py_pack(family: str, word: str, number: int) -> dict:
    other = WORDS[(WORDS.index(word) + 3) % len(WORDS)]
    if family == "class":
        return dict(
            action="stores the item on the new object",
            mcq=["self.item = item", "item == self", "print(item)", "return item"],
            why="self.item = item keeps the item on the object.",
            predict=f'class Bag:\n    def __init__(self, item):\n        self.item = item\nprint(Bag("{word}").item)\n',
            predict2=f'class Bag:\n    def __init__(self, item):\n        self.item = item\nprint(Bag("{other}").item)\n',
            order=["self.item", "=", "item"], distractor="==",
            order_why="self.item = item stores the item.",
            fill_code="self.item ___ item\n", fill_answer="=",
            fill_options=["=", "==", "!=", "+"],
            fill_why="One equals sign stores the item.",
            bug='class Bag:\n    def __init__(self, item):\n        self.item == item\nprint("nope")\n',
            bug_line="3", bug_why="Line 3 compares, so the item is never stored.",
            starter='class Bag:\n    def __init__(self, item):\n        self.item = item\nbag = Bag("marker")\nlabel = ___\nprint(label)\n'.replace("marker", word),
            solution='class Bag:\n    def __init__(self, item):\n        self.item = item\nbag = Bag("marker")\nlabel = bag.item\nprint(label)\n'.replace("marker", word),
            reveal="label = bag.item",
            write_why="The bag item is what gets printed.",
            example=f'bag = Bag("{word}")',
        )
    if family == "loop":
        return dict(
            action="walks every step and counts it",
            mcq=["for step in steps", "if step == steps", "step = steps", "return steps"],
            why="for step in steps visits each step.",
            predict=f"total = 0\nfor step in range({number}):\n    total = total + 1\nprint(total)\n",
            predict2=f"total = 0\nfor step in range({number + 3}):\n    total = total + 1\nprint(total)\n",
            order=["for", "step", "in", "steps:", "pass"], distractor="if",
            order_why="for step in steps: walks the steps.",
            fill_code="total = total ___ 1\n", fill_answer="+",
            fill_options=["+", "-", "*", "=="],
            fill_why="Plus counts one more step.",
            bug=f"total = 0\nfor step of range({number}):\n    total = total + 1\nprint(total)\n",
            bug_line="2", bug_why="Line 2 uses of, so the walk is not valid.",
            starter=f"total = 0\nfor step in range({number}):\n    total = total + 1\nlabel = ___\nprint(label)\n",
            solution=f"total = 0\nfor step in range({number}):\n    total = total + 1\nlabel = total\nprint(label)\n",
            reveal="label = total",
            write_why="The walk count is what gets printed.",
            example=f"for step in range({number}):\n    total = total + 1",
        )
    if family == "cond":
        return dict(
            action="keeps the matching branch",
            mcq=["if score >= limit", "score = limit", "for score in limit", "return limit"],
            why="if score >= limit chooses the matching branch.",
            predict=f'score = {number}\nprint("yes" if score >= {number - 5} else "no")\n',
            predict2=f'score = {number - 10}\nprint("yes" if score >= {number} else "no")\n',
            order=["if", "score", ">=", "limit:", "pass"], distractor="==",
            order_why="if score >= limit: is the branch.",
            fill_code="if score ___ limit:\n    label = 1\n", fill_answer=">=",
            fill_options=[">=", "==", "<=", "!="],
            fill_why=">= keeps the boundary and everything above it.",
            bug=f"score = {number}\nif score == 0:\n    label = 1\nprint(score)\n",
            bug_line="2", bug_why="Line 2 compares with zero instead of the limit.",
            starter=f'score = {number}\nlabel = "yes" if score >= {number - 5} else "no"\nshown = ___\nprint(shown)\n',
            solution=f'score = {number}\nlabel = "yes" if score >= {number - 5} else "no"\nshown = label\nprint(shown)\n',
            reveal="shown = label",
            write_why="The branch result is what gets printed.",
            example=f'score = {number}',
        )
    if family == "fn":
        return dict(
            action="hands the result back to the caller",
            mcq=["return value", "print(value)", "value == value", "pass"],
            why="return hands the value back.",
            predict=f"def double(value):\n    return value * 2\nprint(double({number}))\n",
            predict2=f"def double(value):\n    return value * 2\nprint(double({number + 2}))\n",
            order=["return", "value", "*", "2"], distractor="print",
            order_why="return value * 2 hands back twice the input.",
            fill_code="def double(value):\n    return value ___ 2\n", fill_answer="*",
            fill_options=["*", "+", "-", "=="],
            fill_why="The star doubles the value.",
            bug=f"def double(value):\n    print(value * 2)\nprint(double({number}))\n",
            bug_line="2", bug_why="Line 2 displays the product, so the caller receives nothing.",
            starter=f"def double(value):\n    return value * 2\nlabel = ___\nprint(label)\n",
            solution=f"def double(value):\n    return value * 2\nlabel = double({number})\nprint(label)\n",
            reveal=f"label = double({number})",
            write_why="The handed-back number is what gets printed.",
            example=f"return value * 2",
        )
    if family == "list":
        return dict(
            action="reads how many items are stored",
            mcq=["len(items)", "items[0]", "items + 1", "sum(items)"],
            why="len(items) is the stored count.",
            predict=f'items = ["{word}", "other"]\nprint(len(items))\n',
            predict2=f'items = ["{word}"]\nprint(len(items))\n',
            order=["len", "(", "items", ")"], distractor="sum",
            order_why="len(items) counts the items.",
            fill_code="shown = count ___ 1\n", fill_answer="+",
            fill_options=["+", "-", "*", "=="],
            fill_why="Plus adds one to the count.",
            bug=f'items = ["{word}", "other"]\nprint(items[9])\n',
            bug_line="2", bug_why="Line 2 reads a slot that is not there.",
            starter=f'items = ["{word}", "other"]\nlabel = ___\nprint(label)\n',
            solution=f'items = ["{word}", "other"]\nlabel = len(items)\nprint(label)\n',
            reveal="label = len(items)",
            write_why="The item count is what gets printed.",
            example=f'items = ["{word}", "other"]',
        )
    if family == "dict":
        return dict(
            action="reads the value stored under the name",
            mcq=['pairs["key"]', "pairs[0]", "len(pairs)", "pairs + 1"],
            why='pairs["key"] reads the stored value.',
            predict=f'pairs = {{"key": "{word}"}}\nprint(pairs["key"])\n',
            predict2=f'pairs = {{"key": "{WORDS[(WORDS.index(word) + 5) % len(WORDS)]}"}}\nprint(pairs["key"])\n',
            order=["pairs", "[", '"key"', "]"], distractor="len",
            order_why='pairs["key"] reads that entry.',
            fill_code='print(pairs[___])\n', fill_answer='"key"',
            fill_options=['"key"', '"missing"', "0", "None"],
            fill_why="The quoted name selects the entry.",
            bug='pairs = {"key": 1}\nprint(pairs["missing"])\n',
            bug_line="2", bug_why="Line 2 asks for a name that was never stored.",
            starter=f'pairs = {{"key": "{word}"}}\nlabel = ___\nprint(label)\n',
            solution=f'pairs = {{"key": "{word}"}}\nlabel = pairs["key"]\nprint(label)\n',
            reveal='label = pairs["key"]',
            write_why="The stored entry is what gets printed.",
            example=f'pairs["key"]',
        )
    if family == "text":
        return dict(
            action="builds one longer piece of text",
            mcq=['left + right', "left - right", "len(left)", "left == right"],
            why="left + right joins the two pieces.",
            predict=f'left = "{word}"\nright = "!"\nprint(left + right)\n',
            predict2=f'left = "{word}"\nright = "?"\nprint(left + right)\n',
            order=["left", "+", "right"], distractor="-",
            order_why="left + right joins the text.",
            fill_code="joined = left ___ right\n", fill_answer="+",
            fill_options=["+", "-", "*", "=="],
            fill_why="Plus joins the two pieces.",
            bug=f'left = "{word}"\nright = "!"\nprint(left - right)\n',
            bug_line="3", bug_why="Line 3 subtracts text instead of joining it.",
            starter=f'left = "{word}"\nright = "!"\nlabel = ___\nprint(label)\n',
            solution=f'left = "{word}"\nright = "!"\nlabel = left + right\nprint(label)\n',
            reveal="label = left + right",
            write_why="The joined text is what gets printed.",
            example=f'"{word}" + "!"',
        )
    other_n = number + 5
    return dict(
        action="stores the new number under the name",
        mcq=["total = left + right", "total == left", "print(left)", "return left"],
        why="total = left + right stores the sum.",
        predict=f"left = {number}\nright = 5\nprint(left + right)\n",
        predict2=f"left = {other_n}\nright = 5\nprint(left + right)\n",
        order=["total", "=", "left", "+", "right"], distractor="==",
        order_why="total = left + right stores the sum.",
        fill_code="total = left ___ right\n", fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds the two numbers.",
        bug=f"left = {number}\nright = 5\nprint(left - right)\n",
        bug_line="3", bug_why="Line 3 subtracts instead of adding.",
        starter=f"left = {number}\nright = 5\nlabel = ___\nprint(label)\n",
        solution=f"left = {number}\nright = 5\nlabel = left + right\nprint(label)\n",
        reveal="label = left + right",
        write_why="The stored sum is what gets printed.",
        example=f"left = {number}",
    )


def _js_pack(language: str, family: str, word: str, number: int) -> dict:
    typed = language in {"typescript", "ts"}
    decl = f'const label: string = "{word}";' if typed else f'const label = "{word}";'
    decl2 = f'const label: string = "{WORDS[(WORDS.index(word) + 4) % len(WORDS)]}";' if typed else f'const label = "{WORDS[(WORDS.index(word) + 4) % len(WORDS)]}";'
    num_decl = "const total: number = left + right;" if typed else "const total = left + right;"
    base = _py_pack("store", word, number)
    base.update(
        action="stores the sum under the name",
        mcq=[num_decl, "left == right", "console.log(left)", "return left"],
        why=f"{num_decl} stores the sum.",
        predict=f"const left = {number};\nconst right = 5;\nconsole.log(left + right);\n",
        predict2=f"const left = {number + 4};\nconst right = 5;\nconsole.log(left + right);\n",
        order=["const", "total", "=", "left", "+", "right"],
        distractor="==",
        order_why="const total = left + right stores the sum.",
        fill_code="const total = left ___ right;\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds the two numbers.",
        bug=f"const left = {number};\nconst right = 5;\nconsole.log(left - right);\n",
        bug_line="3",
        bug_why="Line 3 subtracts instead of adding.",
        starter=f"const left = {number};\nconst right = 5;\nconst label = ___;\nconsole.log(label);\n",
        solution=f"const left = {number};\nconst right = 5;\nconst label = left + right;\nconsole.log(label);\n",
        reveal="const label = left + right",
        write_why="The stored sum is what gets printed.",
        example=decl,
    )
    return base


def _java_pack(family: str, word: str, number: int) -> dict:
    def program(body: str) -> str:
        return (
            "public class Solution {\n"
            "    public static void main(String[] args) {\n"
            f"{body}"
            "    }\n"
            "}\n"
        )
    return dict(
        action="stores the sum and shows it",
        mcq=["int total = left + right;", "left == right;", "return left;", "total == left;"],
        why="int total = left + right; stores the sum.",
        predict=program(f"        int left = {number};\n        int right = 5;\n        System.out.println(left + right);\n"),
        predict2=program(f"        int left = {number + 4};\n        int right = 5;\n        System.out.println(left + right);\n"),
        order=["int", "total", "=", "left", "+", "right;"],
        distractor="==",
        order_why="int total = left + right; stores the sum.",
        fill_code="int total = left ___ right;\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds the two numbers.",
        bug=program(f"        int left = {number};\n        int right = 5;\n        System.out.println(left - right);\n"),
        bug_line="5",
        bug_why="The print line subtracts instead of adding.",
        starter=program(f'        int left = {number};\n        int right = 5;\n        int label = ___;\n        System.out.println(label);\n'),
        solution=program(f"        int left = {number};\n        int right = 5;\n        int label = left + right;\n        System.out.println(label);\n"),
        reveal="int label = left + right;",
        write_why="The stored sum is what gets printed.",
        example=f"int left = {number};",
    )


def _cpp_pack(family: str, word: str, number: int) -> dict:
    def program(body: str) -> str:
        return (
            "#include <iostream>\n#include <string>\n"
            "int main() {\n"
            f"{body}"
            "    return 0;\n}\n"
        )
    return dict(
        action="stores the sum and shows it",
        mcq=["int total = left + right;", "left == right;", "return left;", "total == left;"],
        why="int total = left + right; stores the sum.",
        predict=program(f"    int left = {number};\n    int right = 5;\n    std::cout << (left + right) << std::endl;\n"),
        predict2=program(f"    int left = {number + 4};\n    int right = 5;\n    std::cout << (left + right) << std::endl;\n"),
        order=["int", "total", "=", "left", "+", "right;"],
        distractor="==",
        order_why="int total = left + right; stores the sum.",
        fill_code="int total = left ___ right;\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds the two numbers.",
        bug=program(f"    int left = {number};\n    int right = 5;\n    std::cout << (left - right) << std::endl;\n"),
        bug_line="6",
        bug_why="The print line subtracts instead of adding.",
        starter=program(f"    int left = {number};\n    int right = 5;\n    int label = ___;\n    std::cout << label << std::endl;\n"),
        solution=program(f"    int left = {number};\n    int right = 5;\n    int label = left + right;\n    std::cout << label << std::endl;\n"),
        reveal="int label = left + right;",
        write_why="The stored sum is what gets printed.",
        example=f"int left = {number};",
    )


def _sql_pack(family: str, word: str, number: int) -> dict:
    queries = {
        "select": (f"SELECT {number} AS total;", f"SELECT {number + 4} AS total;"),
        "where": (
            f"SELECT {number} AS total WHERE {number} > 0;",
            f"SELECT {number + 4} AS total WHERE {number + 4} > 0;",
        ),
        "distinct": (
            f"SELECT DISTINCT '{word}' AS label;",
            f"SELECT DISTINCT '{WORDS[(WORDS.index(word) + 2) % len(WORDS)]}' AS label;",
        ),
        "group": (
            f"SELECT {number} AS total;",
            f"SELECT {number + 6} AS total;",
        ),
        "order": (
            f"SELECT {number} AS total ORDER BY total;",
            f"SELECT {number + 3} AS total ORDER BY total;",
        ),
        "join": (
            f"SELECT {number} AS total;",
            f"SELECT {number + 7} AS total;",
        ),
        "insert": (
            f"SELECT {number} AS total;",
            f"SELECT {number + 8} AS total;",
        ),
    }
    first, second = queries.get(family, queries["select"])
    return dict(
        action="shows the selected value",
        mcq=[f"SELECT {number} AS total", "INSERT INTO total", "total == total", "DROP TABLE total"],
        why=f"SELECT {number} AS total shows the value.",
        predict=first + "\n",
        predict2=second + "\n",
        order=["SELECT", str(number), "AS", "total"],
        distractor="DROP",
        order_why=f"SELECT {number} AS total shows the value.",
        fill_code="SELECT ___ AS total;\n",
        fill_answer=str(number),
        fill_options=[str(number), "0", "1", "NULL"],
        fill_why="The selected number is the value to show.",
        bug=f"SELECT 0 AS total;\n",
        bug_line="1",
        bug_why="The only line selects zero instead of the lesson value.",
        starter="SELECT ___ AS total;\n",
        solution=first + "\n",
        reveal=first,
        write_why="The selected value is what the table shows.",
        example=first,
    )


def _spec(lesson: dict, language: str) -> dict:
    from backend.prompt_align import KEYS, _details, apply_prompts

    blob = " ".join([
        lesson.get("title") or "",
        lesson.get("description") or "",
        (lesson.get("solution_code") or "")[:240],
    ]).lower()
    phrase = _concept(lesson)
    title = verb_title(lesson.get("title") or lesson["id"])
    topic = _plain(lesson.get("title") or lesson["id"]) or lesson["id"]
    word = _word(lesson["id"], f"{phrase} {topic}")
    number = _number(lesson["id"] + "n", f"{phrase} {topic}")
    if language == "python":
        pack = python_recipe(lesson["id"], word, number)
    else:
        from backend.concept_packs import pack_for
        pack = pack_for(lesson["id"], word, number)
    mcq_answer = pack["mcq"][0]
    spec = {
        "id": lesson["id"],
        "title": title,
        "example": pack["example"],
        "teach_bridge": pack["why"],
        "mcq_options": pack["mcq"],
        "mcq_answer": mcq_answer,
        "mcq_bridge": pack["why"],
        "mcq_why": pack["why"],
        "predict_code": pack["predict"],
        "predict_options": ["pending", "other", "none", "zero"],
        "predict_bridge": pack["why"],
        "predict_why": pack["why"],
        "chips": pack["order"] + ([pack["distractor"]] if pack["distractor"] not in pack["order"] else ["#"]),
        "order": pack["order"],
        "order_bridge": pack["order_why"],
        "order_why": pack["order_why"],
        "fill_code": pack["fill_code"],
        "fill_options": pack["fill_options"],
        "fill_answer": pack["fill_answer"],
        "fill_bridge": pack["fill_why"],
        "fill_why": pack["fill_why"],
        "bug_code": pack["bug"],
        "bug_line": pack["bug_line"],
        "bug_bridge": pack["bug_why"],
        "bug_why": pack["bug_why"],
        "second_kind": "predict",
        "predict2_code": pack["predict2"],
        "predict2_options": ["pending", "other", "none", "zero"],
        "second_bridge": pack["why"],
        "second_why": pack["why"],
        "starter": pack["starter"],
        "solution": pack["solution"],
        "write_bridge": pack["write_why"],
        "write_reveal": pack["reveal"],
        "write_why": pack["write_why"],
        "source_name": (lesson.get("source") or {}).get("name"),
        "source_url": (lesson.get("source") or {}).get("url"),
        "_action": pack["action"],
        "_details": _details(pack, lesson["id"]),
        "_frame": {
            key: 0 if key == "teach" else sum(lesson["id"].encode("utf-8")) % 8
            for key in KEYS
        },
        "_answers": {},
    }
    apply_prompts(spec)
    return spec


def _ensure_options(exercise_id: str, answer: str, seeds: list[str]) -> list[str]:
    """Pick four choices that have at least one order the client will not reveal.

    The factory reorders again. This only has to prove a safe permutation exists
    for this exercise id and this answer.
    """
    extras: list[str] = []
    for item in [
        *seeds, "none", "0", "1", "blank", "other", "no-match", "gap", "skip",
        "2", "3", "4", "5", "6", "7", "8", "9", "miss", "empty", "zero", "false", "true",
    ]:
        if item != answer and item not in extras:
            extras.append(item)
    for combo in combinations(extras, 3):
        options = [answer, *combo]
        if len(set(options)) != 4:
            continue
        try:
            safe_options(exercise_id, options, answer)
        except SystemExit:
            continue
        return options
    raise SystemExit(f"no safe option set for {exercise_id}")


def _choices(answer: str, seeds: list[str]) -> list[str]:
    return _ensure_options("unused-choices", answer, seeds)


def _without(text: str, answer: str, scene: str = "") -> str:
    """Drop any prompt that contains its answer, without a shared scene line."""
    del scene
    if not hint_gives_answer(text, answer):
        return text
    from backend.prompt_align import _drop, _sentence

    cleaned = _sentence(_drop(text, answer))
    if not hint_gives_answer(cleaned, answer):
        return cleaned
    fallback = _hide("Stay with the step this screen is about", answer)
    if hint_gives_answer(fallback, answer):
        raise SystemExit(f"cannot hide {answer!r}")
    return fallback


def _with_outputs(spec: dict, language: str) -> dict:
    first = _run(language, spec["predict_code"]).strip()
    second = _run(language, spec["predict2_code"]).strip()
    if not first or not second:
        raise SystemExit(f"{spec['id']} blank stdout")
    if first == second:
        raise SystemExit(f"{spec['id']} predictions match: {first!r}")
    spec["predict_options"] = _ensure_options(f"{spec['id']}-predict", first, [second, "none", "0"])
    spec["predict2_options"] = _ensure_options(f"{spec['id']}-predict-2", second, [first, "none", "0"])
    spec["mcq_options"] = _ensure_options(f"{spec['id']}-mcq", spec["mcq_answer"], spec["mcq_options"])
    spec["fill_options"] = _ensure_options(f"{spec['id']}-fill", spec["fill_answer"], spec["fill_options"])
    guards = {
        "predict_q": first,
        "predict_nudge": first,
        "second_q": second,
        "second_nudge": second,
        "fill_q": spec["fill_answer"],
        "fill_nudge": spec["fill_answer"],
        "mcq_q": spec["mcq_answer"],
        "mcq_nudge": spec["mcq_answer"],
        "bug_q": spec["bug_line"],
        "bug_nudge": spec["bug_line"],
        "order_q": spec["order"],
        "order_nudge": spec["order"],
        "write_q": first,
        "write_nudge": spec["fill_answer"],
    }
    for key, answer in guards.items():
        if key.endswith("_nudge"):
            spec[key] = _hide(spec[key], answer)
        else:
            spec[key] = _without(spec[key], answer)
    spec["_guard"] = [first, second, spec["fill_answer"], spec["mcq_answer"], spec["bug_line"], " ".join(spec["order"])]
    spec["_answers"] = {
        "teach": spec["teach"],
        "mcq_q": spec["mcq_answer"],
        "predict_q": first,
        "order_q": spec["order"],
        "fill_q": spec["fill_answer"],
        "bug_q": spec["bug_line"],
        "second_q": second,
        "write_q": spec["write_reveal"],
    }
    return spec


def _existing_prompts(course: str) -> list[tuple[str, str]]:
    folder = ROOT / course / "modules"
    found = []
    for path in folder.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for lesson in data.get("lessons", []):
            if lesson.get("player_mode") != "micro":
                continue
            objectives = lesson.get("learning_objectives") or [""]
            found.append((lesson["id"], objectives[0]))
            for sub in lesson.get("sublessons") or []:
                for exercise in sub.get("exercises") or []:
                    if exercise.get("question"):
                        found.append((lesson["id"], exercise["question"]))
    return found


def _separate(course: str, specs: list[dict]) -> None:
    from backend.prompt_align import separate

    rewriting = {spec["id"] for spec in specs}
    frozen = [item for item in _existing_prompts(course) if item[0] not in rewriting]
    separate(course, specs, frozen)


def _parse_for(language: str):
    def checker(code: str) -> tuple[bool, str]:
        return program_parses(language, code)
    return checker


def _runner_for(language: str):
    def runner(code: str) -> str:
        return _run(language, code)
    return runner


def _strip_ticks(value):
    if isinstance(value, str):
        return value.replace("`", "")
    if isinstance(value, list):
        return [_strip_ticks(item) for item in value]
    return value


def _sanitize(lesson: dict) -> None:
    lesson["description"] = _strip_ticks(lesson.get("description") or "")
    groups = [lesson.get("mastery_exam") or []]
    for sub in lesson.get("sublessons") or []:
        groups.append(sub.get("exercises") or [])
    for exercises in groups:
        for exercise in exercises:
            for field in ("question", "explanation", "worked_example", "hints", "options"):
                if field in exercise:
                    exercise[field] = _strip_ticks(exercise[field])
            options = exercise.get("options")
            if isinstance(options, list):
                seen: list[str] = []
                for option in options:
                    if option not in seen:
                        seen.append(option)
                exercise["options"] = seen
            hints = list(exercise.get("hints") or [])
            answer = exercise.get("correct_answer")
            if hints and exercise.get("type") != "teach" and hint_gives_answer(hints[0], answer):
                hints[0] = _hide("Stay with the step this screen is about.", answer)
                exercise["hints"] = hints


def ship(courses: list[str]) -> None:
    for course in courses:
        folder = ROOT / course / "modules"
        lessons = []
        for path in sorted(folder.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for lesson in data.get("lessons", []):
                if lesson["id"] in SKIP or lesson["id"] in KEEP_HAND:
                    continue
                lessons.append(lesson)
        if not lessons:
            print(f"{course}: nothing to install")
            continue
        language = course
        specs = []
        for lesson in lessons:
            spec = _with_outputs(_spec(lesson, language), language)
            if not (lesson.get("source") or {}).get("url"):
                name, url, _license = SOURCES.get(course, SOURCES["python"])
                spec["source_name"] = name
                spec["source_url"] = url
            specs.append(spec)
            print(f"built {course}/{lesson['id']}", flush=True)
        _separate(course, specs)
        install(course, specs, run=_runner_for(language), parse=_parse_for(language), replace=True)
        wanted = {spec["id"] for spec in specs}
        for path in sorted(folder.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            dirty = False
            for lesson in data.get("lessons", []):
                if lesson["id"] not in wanted:
                    continue
                _sanitize(lesson)
                dirty = True
            if dirty:
                path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _dedupe_descriptions(folder)
        print(f"{course}: installed {len(specs)}")


if __name__ == "__main__":
    import sys
    requested = [part.strip() for part in (sys.argv[1] if len(sys.argv) > 1 else "").split(",") if part.strip()]
    order = requested or [
        "python", "javascript", "typescript", "java", "cpp", "sql",
        "dsa", "ml-math", "ml", "ai", "fullstack",
    ]
    ship(order)
