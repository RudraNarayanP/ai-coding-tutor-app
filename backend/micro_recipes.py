"""Executable micro-lesson recipes.

This module only builds spec fragments. It does not write curriculum files.
``backend.ship_micro`` is the installer, and it skips lessons that already
shipped as micro.
"""

from __future__ import annotations

import ast
from pathlib import Path

import io
from contextlib import redirect_stdout

from backend.starter_leak_audit import LessonView, answer_lines, check_presolved_body


def _run(code: str) -> str:
    """Execute the way the Python sandbox does, with ``__name__ == '__main__'``.

    Dataclasses look up the class module, so ``__micro__`` is not a stand-in.
    """
    buf = io.StringIO()
    namespace = {"__name__": "__main__"}
    with redirect_stdout(buf):
        exec(compile(code, "<micro>", "exec"), namespace, namespace)
    return buf.getvalue()

# Lessons that stay on the hand-authored player scripts.
SKIP = {
    "booleans",
    "booleans-step-1",
    "booleans-step-2",
    "booleans-step-3",
    "booleans-01",
}


def _bug_line(code: str, needle: str) -> str:
    hits = [str(index) for index, line in enumerate(code.splitlines(), 1) if needle in line]
    if len(hits) != 1:
        raise SystemExit(f"bug needle {needle!r} hits {hits} in {code!r}")
    return hits[0]


def _check(label: str, pack: dict) -> dict:
    order_src = " ".join(pack["order"])
    try:
        ast.parse(order_src)
    except SyntaxError as exc:
        raise SystemExit(f"{label} order does not parse: {order_src}: {exc.msg}") from exc
    if len(set(pack["order"])) != len(pack["order"]):
        raise SystemExit(f"{label} duplicate order token")
    if pack["distractor"] in pack["order"]:
        raise SystemExit(f"{label} distractor collides")
    filled = pack["fill_code"].replace("___", pack["fill_answer"], 1)
    if "___" in filled or pack["fill_code"].count("___") != 1:
        raise SystemExit(f"{label} fill blank count")
    try:
        ast.parse(filled)
    except SyntaxError as exc:
        raise SystemExit(f"{label} fill does not parse: {filled}: {exc.msg}") from exc
    if pack["fill_answer"] not in pack["fill_options"] or len(set(pack["fill_options"])) != 4:
        raise SystemExit(f"{label} fill options")
    if len(set(pack["mcq"])) != 4 or pack["mcq"][0] == "":
        raise SystemExit(f"{label} mcq options")
    if pack["starter"].count("___") != 1 or "___" in pack["solution"]:
        raise SystemExit(f"{label} write blank")
    first = _run(pack["predict"]).strip()
    second = _run(pack["predict2"]).strip()
    written = _run(pack["solution"])
    if not first or not second or not written.strip():
        raise SystemExit(f"{label} blank output {first!r} {second!r}")
    if first == second:
        raise SystemExit(f"{label} predictions match {first!r}")
    view = LessonView(
        lesson={"id": label, "solution_code": pack["solution"]},
        path=Path("probe"),
        starter_lines=pack["starter"].splitlines(),
        solution_lines=pack["solution"].splitlines(),
        scope="exercise",
    )
    leaks = check_presolved_body(view, answer_lines(view))
    if leaks:
        raise SystemExit(f"{label} starter leaks: {leaks[0].starter_line} ~ {leaks[0].answer}")
    pack["bug_line"] = _bug_line(pack["bug"], pack.pop("_needle"))
    return pack


def _pack(
    action: str,
    why: str,
    mcq: list[str],
    predict: str,
    predict2: str,
    order: list[str],
    distractor: str,
    order_why: str,
    fill_code: str,
    fill_answer: str,
    fill_options: list[str],
    fill_why: str,
    bug: str,
    needle: str,
    bug_why: str,
    starter: str,
    solution: str,
    reveal: str,
    write_why: str,
    example: str,
) -> dict:
    return {
        "action": action,
        "mcq": mcq,
        "why": why,
        "predict": predict,
        "predict2": predict2,
        "order": order,
        "distractor": distractor,
        "order_why": order_why,
        "fill_code": fill_code,
        "fill_answer": fill_answer,
        "fill_options": fill_options,
        "fill_why": fill_why,
        "bug": bug,
        "bug_why": bug_why,
        "_needle": needle,
        "starter": starter,
        "solution": solution,
        "reveal": reveal,
        "write_why": write_why,
        "example": example,
    }


def _finish(label: str, **kwargs) -> dict:
    return _check(label, _pack(**kwargs))


def _n(number: int, twist: int) -> tuple[int, int]:
    left = number + twist * 3
    right = 4 + (twist % 3)
    return left, right


def dot(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    body = (
        f"width = {left}\nheight = {right}\n"
        "print(width * height + width)\n"
    )
    body2 = (
        f"width = {left + 2}\nheight = {right}\n"
        "print(width * height + width)\n"
    )
    return _finish(
        "dot",
        action="multiplies the pair and then adds the width",
        why="width * height + width is the combined product.",
        mcq=["width * height + width", "width + height", "width == height", "print(width)"],
        predict=body,
        predict2=body2,
        order=["part", "=", "width", "*", "height"],
        distractor="+",
        order_why="part = width * height multiplies the pair.",
        fill_code="part = width ___ height\n",
        fill_answer="*",
        fill_options=["*", "+", "-", "=="],
        fill_why="The star multiplies the pair.",
        bug=f"width = {left}\nheight = {right}\nprint(width + height + width)\n",
        needle="width + height",
        bug_why="The print adds the pair instead of multiplying.",
        starter=f"width = {left}\nheight = {right}\nlabel = ___\nprint(label)\n",
        solution=f"width = {left}\nheight = {right}\nlabel = width * height + width\nprint(label)\n",
        reveal="label = width * height + width",
        write_why="The combined product is what gets printed.",
        example=f"width = {left}",
    )


def filter_list(word: str, number: int, twist: int) -> dict:
    cut = 10 + twist
    body = (
        f"items = [1, {number}, {number + 2}]\n"
        f"kept = [item for item in items if item > {cut}]\n"
        "print(sum(kept))\n"
    )
    body2 = (
        f"items = [1, 2, {number}]\n"
        f"kept = [item for item in items if item > {cut}]\n"
        "print(sum(kept))\n"
    )
    return _finish(
        "filter_list",
        action="keeps the values above the cutoff and adds them",
        why="The comprehension drops values that are not above the cutoff.",
        mcq=[
            f"item > {cut}",
            f"item == {cut}",
            "item = items",
            "print(item)",
        ],
        predict=body,
        predict2=body2,
        order=["rows", "=", "[", "a", "for", "b", "in", "c", "if", "d", "]"],
        distractor="while",
        order_why="rows = [a for b in c if d] keeps the matches.",
        fill_code=f"kept = [item for item in items if item ___ {cut}]\n",
        fill_answer=">",
        fill_options=[">", "<", "==", "!="],
        fill_why="The cutoff keeps the greater values.",
        bug=(
            f"items = [1, {number}, {number + 2}]\n"
            f"kept = [item for item in items if item < {cut}]\n"
            "print(sum(kept))\n"
        ),
        needle=f"item < {cut}",
        bug_why="The filter keeps the small values instead of the large ones.",
        starter=(
            f"items = [1, {number}, {number + 2}]\n"
            f"kept = [item for item in items if item > {cut}]\n"
            "label = ___\nprint(label)\n"
        ),
        solution=(
            f"items = [1, {number}, {number + 2}]\n"
            f"kept = [item for item in items if item > {cut}]\n"
            "label = sum(kept)\nprint(label)\n"
        ),
        reveal="label = sum(kept)",
        write_why="The kept total is what gets printed.",
        example=f"item > {cut}",
    )


def dict_get(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    other = left + 5
    predict = f"payload = {{'status': {left}, 'ok': 1}}\nprint(payload['status'])\n"
    predict2 = f"payload = {{'status': {other}, 'ok': 1}}\nprint(payload['status'])\n"
    return _finish(
        "dict_get",
        action="reads the value stored under status",
        why="payload['status'] reads that entry.",
        mcq=["payload['status']", "payload[0]", "len(payload)", "payload + 1"],
        predict=predict,
        predict2=predict2,
        order=["payload", "[", "'status'", "]"],
        distractor="len",
        order_why="payload['status'] reads the stored status.",
        fill_code="print(payload[___])\n",
        fill_answer="'status'",
        fill_options=["'status'", "'missing'", "0", "None"],
        fill_why="The quoted name selects the status entry.",
        bug="payload = {'status': 1}\nprint(payload['missing'])\n",
        needle="missing",
        bug_why="The print asks for a name that was never stored.",
        starter=f"payload = {{'status': {left}, 'ok': 1}}\nlabel = ___\nprint(label)\n",
        solution=f"payload = {{'status': {left}, 'ok': 1}}\nlabel = payload['status']\nprint(label)\n",
        reveal="label = payload['status']",
        write_why="The stored status is what gets printed.",
        example="payload['status']",
    )


def dict_items(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    predict = (
        f"pairs = {{'a': {left}, 'b': 2}}\n"
        "total = 0\n"
        "for key, value in pairs.items():\n"
        "    total = total + value\n"
        "print(total)\n"
    )
    predict2 = (
        f"pairs = {{'a': {left + 3}, 'b': 2}}\n"
        "total = 0\n"
        "for key, value in pairs.items():\n"
        "    total = total + value\n"
        "print(total)\n"
    )
    return _finish(
        "dict_items",
        action="adds every stored value",
        why="pairs.items() walks each stored pair.",
        mcq=["pairs.items()", "pairs[0]", "len(pairs)", "pairs + 1"],
        predict=predict,
        predict2=predict2,
        order=["for", "key,", "value", "in", "pairs.items():", "pass"],
        distractor="if",
        order_why="for key, value in pairs.items(): walks the pairs.",
        fill_code="total = total ___ value\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds the stored value.",
        bug=(
            f"pairs = {{'a': {left}}}\n"
            "total = 0\n"
            "for key, value in pairs:\n"
            "    total = total + value\n"
            "print(total)\n"
        ),
        needle="in pairs:",
        bug_why="The walk reads names only, so the values are never added.",
        starter=(
            f"pairs = {{'a': {left}, 'b': 2}}\n"
            "total = 0\n"
            "for key, value in pairs.items():\n"
            "    total = total + value\n"
            "label = ___\nprint(label)\n"
        ),
        solution=(
            f"pairs = {{'a': {left}, 'b': 2}}\n"
            "total = 0\n"
            "for key, value in pairs.items():\n"
            "    total = total + value\n"
            "label = total\nprint(label)\n"
        ),
        reveal="label = total",
        write_why="The added values are what get printed.",
        example="for key, value in pairs.items():",
    )


def dict_count(word: str, number: int, twist: int) -> dict:
    extra = 2 + twist
    predict = (
        "counts = {}\n"
        f"for piece in ['{word}', '{word}', 'other']:\n"
        "    counts[piece] = counts.get(piece, 0) + 1\n"
        f"print(counts['{word}'] + {extra})\n"
    )
    predict2 = (
        "counts = {}\n"
        f"for piece in ['{word}', 'other']:\n"
        "    counts[piece] = counts.get(piece, 0) + 1\n"
        f"print(counts['{word}'] + {extra})\n"
    )
    return _finish(
        "dict_count",
        action="counts how often the word was seen",
        why="counts.get(piece, 0) + 1 stores one more sighting.",
        mcq=["counts.get(piece, 0) + 1", "counts[0]", "len(piece)", "piece == piece"],
        predict=predict,
        predict2=predict2,
        order=["counts", "[", "piece", "]", "=", "seen"],
        distractor="==",
        order_why="counts[piece] = seen stores the new tally.",
        fill_code="counts[piece] = counts.get(piece, 0) ___ 1\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus records one more sighting.",
        bug=(
            "counts = {}\n"
            f"for piece in ['{word}', '{word}']:\n"
            "    counts[piece] = counts.get(piece, 0)\n"
            f"print(counts['{word}'])\n"
        ),
        needle="counts.get(piece, 0)",
        bug_why="The tally is stored without adding the new sighting.",
        starter=(
            "counts = {}\n"
            f"for piece in ['{word}', '{word}', 'other']:\n"
            "    counts[piece] = counts.get(piece, 0) + 1\n"
            "label = ___\nprint(label)\n"
        ),
        solution=(
            "counts = {}\n"
            f"for piece in ['{word}', '{word}', 'other']:\n"
            "    counts[piece] = counts.get(piece, 0) + 1\n"
            f"label = counts['{word}']\nprint(label)\n"
        ),
        reveal=f"label = counts['{word}']",
        write_why="The word tally is what gets printed.",
        example="counts.get(piece, 0) + 1",
    )


def class_init(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    other = left + 4
    predict = (
        "class Bag:\n"
        "    def __init__(self, item):\n"
        "        self.item = item\n"
        f"print(Bag({left}).item)\n"
    )
    predict2 = (
        "class Bag:\n"
        "    def __init__(self, item):\n"
        "        self.item = item\n"
        f"print(Bag({other}).item)\n"
    )
    return _finish(
        "class_init",
        action="stores the reading on the new object",
        why="self.item = item keeps the reading on the object.",
        mcq=["self.item = item", "item == self", "print(item)", "return item"],
        predict=predict,
        predict2=predict2,
        order=["self.item", "=", "item"],
        distractor="==",
        order_why="self.item = item stores the reading.",
        fill_code="self.item ___ item\n",
        fill_answer="=",
        fill_options=["=", "==", "!=", "+"],
        fill_why="One equals sign stores the reading.",
        bug=(
            "class Bag:\n"
            "    def __init__(self, item):\n"
            "        self.item == item\n"
            "print(0)\n"
        ),
        needle="==",
        bug_why="The constructor compares, so the reading is never stored.",
        starter=(
            "class Bag:\n"
            "    def __init__(self, item):\n"
            "        self.item = item\n"
            f"bag = Bag({left})\n"
            "label = ___\nprint(label)\n"
        ),
        solution=(
            "class Bag:\n"
            "    def __init__(self, item):\n"
            "        self.item = item\n"
            f"bag = Bag({left})\n"
            "label = bag.item\nprint(label)\n"
        ),
        reveal="label = bag.item",
        write_why="The stored reading is what gets printed.",
        example="self.item = item",
    )


def class_method(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    predict = (
        "class Bag:\n"
        "    def __init__(self, item):\n"
        "        self.item = item\n"
        "    def doubled(self):\n"
        "        return self.item * 2\n"
        f"print(Bag({left}).doubled())\n"
    )
    predict2 = (
        "class Bag:\n"
        "    def __init__(self, item):\n"
        "        self.item = item\n"
        "    def doubled(self):\n"
        "        return self.item * 2\n"
        f"print(Bag({left + right}).doubled())\n"
    )
    return _finish(
        "class_method",
        action="hands back twice the stored reading",
        why="return self.item * 2 hands the doubled reading back.",
        mcq=["return self.item * 2", "self.item == item", "print(self)", "pass"],
        predict=predict,
        predict2=predict2,
        order=["return", "self.item", "*", "2"],
        distractor="print",
        order_why="return self.item * 2 hands back twice the reading.",
        fill_code="return self.item ___ 2\n",
        fill_answer="*",
        fill_options=["*", "+", "-", "=="],
        fill_why="The star doubles the stored reading.",
        bug=(
            "class Bag:\n"
            "    def __init__(self, item):\n"
            "        self.item = item\n"
            "    def doubled(self):\n"
            "        print(self.item * 2)\n"
            f"print(Bag({left}).doubled())\n"
        ),
        needle="print(self.item * 2)",
        bug_why="The method displays the product, so the caller receives nothing useful.",
        starter=(
            "class Bag:\n"
            "    def __init__(self, item):\n"
            "        self.item = item\n"
            "    def doubled(self):\n"
            "        return self.item * 2\n"
            f"bag = Bag({left})\n"
            "label = ___\nprint(label)\n"
        ),
        solution=(
            "class Bag:\n"
            "    def __init__(self, item):\n"
            "        self.item = item\n"
            "    def doubled(self):\n"
            "        return self.item * 2\n"
            f"bag = Bag({left})\n"
            "label = bag.doubled()\nprint(label)\n"
        ),
        reveal="label = bag.doubled()",
        write_why="The handed-back product is what gets printed.",
        example="return self.item * 2",
    )


def class_deposit(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    predict = (
        "class Account:\n"
        "    def __init__(self, balance):\n"
        "        self.balance = balance\n"
        "    def deposit(self, amount):\n"
        "        self.balance = self.balance + amount\n"
        "        return self.balance\n"
        f"print(Account({left}).deposit({right}))\n"
    )
    predict2 = (
        "class Account:\n"
        "    def __init__(self, balance):\n"
        "        self.balance = balance\n"
        "    def deposit(self, amount):\n"
        "        self.balance = self.balance + amount\n"
        "        return self.balance\n"
        f"print(Account({left}).deposit({right + 2}))\n"
    )
    return _finish(
        "class_deposit",
        action="adds the deposit and hands back the new balance",
        why="self.balance + amount is the updated balance.",
        mcq=["self.balance + amount", "self.balance == amount", "print(amount)", "pass"],
        predict=predict,
        predict2=predict2,
        order=["updated", "=", "balance", "+", "amount"],
        distractor="==",
        order_why="updated = balance + amount stores the deposit.",
        fill_code="self.balance = self.balance ___ amount\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds the deposit.",
        bug=(
            "class Account:\n"
            "    def __init__(self, balance):\n"
            "        self.balance = balance\n"
            "    def deposit(self, amount):\n"
            "        self.balance = self.balance - amount\n"
            "        return self.balance\n"
            f"print(Account({left}).deposit({right}))\n"
        ),
        needle="self.balance - amount",
        bug_why="The method subtracts the deposit.",
        starter=(
            "class Account:\n"
            "    def __init__(self, balance):\n"
            "        self.balance = balance\n"
            "    def deposit(self, amount):\n"
            "        self.balance = self.balance + amount\n"
            "        return self.balance\n"
            f"account = Account({left})\n"
            "label = ___\nprint(label)\n"
        ),
        solution=(
            "class Account:\n"
            "    def __init__(self, balance):\n"
            "        self.balance = balance\n"
            "    def deposit(self, amount):\n"
            "        self.balance = self.balance + amount\n"
            "        return self.balance\n"
            f"account = Account({left})\n"
            f"label = account.deposit({right})\nprint(label)\n"
        ),
        reveal=f"label = account.deposit({right})",
        write_why="The updated balance is what gets printed.",
        example="self.balance = self.balance + amount",
    )


def compare_ge(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    limit = 15
    predict = f"score = {left}\nprint(score * 2 if score >= {limit} else score)\n"
    predict2 = f"score = {limit - 1}\nprint(score * 2 if score >= {limit} else score)\n"
    return _finish(
        "compare_ge",
        action="keeps twice the score when it reaches the limit",
        why="score >= limit includes the boundary.",
        mcq=[f"score >= {limit}", "score = limit", "score == 0", "print(score)"],
        predict=predict,
        predict2=predict2,
        order=["if", "score", ">=", "limit:", "pass"],
        distractor="==",
        order_why="if score >= limit: is the boundary check.",
        fill_code="if score ___ limit:\n    label = 1\n",
        fill_answer=">=",
        fill_options=[">=", ">", "==", "<"],
        fill_why="The boundary check includes the limit itself.",
        bug=f"score = {left}\nif score == 0:\n    score = 1\nprint(score)\n",
        needle="score == 0",
        bug_why="The branch compares with zero instead of the limit.",
        starter=f"score = {left}\nlabel = ___\nprint(label)\n",
        solution=f"score = {left}\nlabel = score * 2 if score >= {limit} else score\nprint(label)\n",
        reveal=f"label = score * 2 if score >= {limit} else score",
        write_why="The boundary result is what gets printed.",
        example=f"score >= {limit}",
    )


def compare_chain(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    predict = f"score = {left}\nprint(score + 100 if 15 < score < 80 else 7)\n"
    predict2 = "score = 3\nprint(score + 100 if 15 < score < 80 else 7)\n"
    return _finish(
        "compare_chain",
        action="keeps the score only when it sits between the two bounds",
        why="15 < score < 80 is one chained comparison.",
        mcq=["15 < score < 80", "score = 15", "score == 80", "print(score)"],
        predict=predict,
        predict2=predict2,
        order=["if", "low", "<", "score:", "pass"],
        distractor="==",
        order_why="if low < score: opens the range check.",
        fill_code="if low < score ___ high:\n    label = 1\n",
        fill_answer="<",
        fill_options=["<", ">", "==", "="],
        fill_why="The second symbol finishes the chain.",
        bug=f"score = {left}\nif score == 15:\n    score = 1\nprint(score)\n",
        needle="score == 15",
        bug_why="The branch checks equality instead of the range.",
        starter=f"score = {left}\nlabel = ___\nprint(label)\n",
        solution=f"score = {left}\nlabel = score + 100 if 15 < score < 80 else 7\nprint(label)\n",
        reveal="label = score + 100 if 15 < score < 80 else 7",
        write_why="The range result is what gets printed.",
        example="15 < score < 80",
    )


def compare_eq(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    predict = f"card = {left}\ntarget = {left}\nprint(card * 2 if card == target else card)\n"
    predict2 = f"card = {left}\ntarget = {left + 1}\nprint(card * 2 if card == target else card)\n"
    return _finish(
        "compare_eq",
        action="doubles the card when it matches the target",
        why="card == target is the match.",
        mcq=["card == target", "card = target", "card != target", "print(card)"],
        predict=predict,
        predict2=predict2,
        order=["if", "card", "==", "target:", "pass"],
        distractor="=",
        order_why="if card == target: is the match.",
        fill_code="if card ___ target:\n    label = 1\n",
        fill_answer="==",
        fill_options=["==", "=", "!=", "<"],
        fill_why="Two equals signs ask whether the values match.",
        bug=f"card = {left}\ntarget = {left}\nprint(card * 2 if card != target else card)\n",
        needle="card != target",
        bug_why="The branch keeps the mismatch instead of the match.",
        starter=f"card = {left}\ntarget = {left}\nlabel = ___\nprint(label)\n",
        solution=f"card = {left}\ntarget = {left}\nlabel = card * 2 if card == target else card\nprint(label)\n",
        reveal="label = card * 2 if card == target else card",
        write_why="The match result is what gets printed.",
        example="card == target",
    )


def compare_ne(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    predict = f"left = {left}\nright = {left + 2}\nprint(left + right if left != right else left)\n"
    predict2 = f"left = {left}\nright = {left}\nprint(left + right if left != right else left)\n"
    return _finish(
        "compare_ne",
        action="adds the two readings when they differ",
        why="left != right is the difference check.",
        mcq=["left != right", "left = right", "left == right", "print(left)"],
        predict=predict,
        predict2=predict2,
        order=["if", "left", "!=", "right:", "pass"],
        distractor="==",
        order_why="if left != right: keeps the unequal case.",
        fill_code="if left ___ right:\n    label = 1\n",
        fill_answer="!=",
        fill_options=["!=", "==", "=", "<"],
        fill_why="The exclamation form asks whether the values differ.",
        bug=f"left = {left}\nright = {left + 2}\nprint(left + right if left == right else 0)\n",
        needle="left == right",
        bug_why="The branch keeps the equal case.",
        starter=f"left = {left}\nright = {left + 2}\nlabel = ___\nprint(label)\n",
        solution=f"left = {left}\nright = {left + 2}\nlabel = left + right if left != right else left\nprint(label)\n",
        reveal="label = left + right if left != right else left",
        write_why="The unequal sum is what gets printed.",
        example="left != right",
    )


def comp_list(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    predict = f"raw = [{left}, {right}]\ngrown = [step + 1 for step in raw]\nprint(sum(grown))\n"
    predict2 = f"raw = [{left + 3}, {right}]\ngrown = [step + 1 for step in raw]\nprint(sum(grown))\n"
    return _finish(
        "comp_list",
        action="builds a new list by adding one to each reading",
        why="step + 1 transforms each reading.",
        mcq=["[step + 1 for step in raw]", "step = raw", "raw + 1", "print(raw)"],
        predict=predict,
        predict2=predict2,
        order=["grown", "=", "[", "step", "+", "1", "for", "item", "in", "raw", "]"],
        distractor="while",
        order_why="The comprehension builds the new list.",
        fill_code="grown = [step ___ 1 for step in raw]\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds one to each reading.",
        bug=f"raw = [{left}, {right}]\ngrown = [step - 1 for step in raw]\nprint(sum(grown))\n",
        needle="step - 1",
        bug_why="The comprehension subtracts instead of adding.",
        starter=f"raw = [{left}, {right}]\ngrown = [step + 1 for step in raw]\nlabel = ___\nprint(label)\n",
        solution=f"raw = [{left}, {right}]\ngrown = [step + 1 for step in raw]\nlabel = sum(grown)\nprint(label)\n",
        reveal="label = sum(grown)",
        write_why="The transformed total is what gets printed.",
        example="[step + 1 for step in raw]",
    )


def comp_dict(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    predict = f"names = ['a', 'b']\npairs = {{name: {left} for name in names}}\nprint(sum(pairs.values()))\n"
    predict2 = f"names = ['a', 'b', 'c']\npairs = {{name: {left} for name in names}}\nprint(sum(pairs.values()))\n"
    return _finish(
        "comp_dict",
        action="builds a dictionary that stores the same reading for each name",
        why="The dict comprehension stores one entry per name.",
        mcq=["{name: reading for name in names}", "names[0]", "len(names)", "names + 1"],
        predict=predict,
        predict2=predict2,
        order=["pairs", "=", "{", "name:", "reading", "for", "name", "in", "names", "}"],
        distractor="while",
        order_why="The dict comprehension stores one entry per name.",
        fill_code="bonus = reading ___ 2\n",
        fill_answer="*",
        fill_options=["*", "+", "-", "=="],
        fill_why="The star scales the stored reading.",
        bug=f"names = ['a', 'b']\npairs = {{name: 0 for name in names}}\nprint(sum(pairs.values()))\n",
        needle="name: 0",
        bug_why="Every entry stores zero instead of the reading.",
        starter=f"names = ['a', 'b']\npairs = {{name: {left} for name in names}}\nlabel = ___\nprint(label)\n",
        solution=f"names = ['a', 'b']\npairs = {{name: {left} for name in names}}\nlabel = sum(pairs.values())\nprint(label)\n",
        reveal="label = sum(pairs.values())",
        write_why="The stored total is what gets printed.",
        example="{name: reading for name in names}",
    )


def comp_flat(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    predict = (
        f"nested = [[{left}], [{right}]]\n"
        "flat = [item for pair in nested for item in pair]\n"
        "print(sum(flat))\n"
    )
    predict2 = (
        f"nested = [[{left}], [{right}], [{left}]]\n"
        "flat = [item for pair in nested for item in pair]\n"
        "print(sum(flat))\n"
    )
    return _finish(
        "comp_flat",
        action="adds the readings after the nested rows are flattened",
        why="The double comprehension walks every inner row.",
        mcq=["[item for pair in nested for item in pair]", "nested[0]", "len(nested)", "nested + 1"],
        predict=predict,
        predict2=predict2,
        order=["total", "=", "left", "+", "right"],
        distractor="==",
        order_why="total = left + right adds the flattened readings.",
        fill_code="total = left ___ right\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds the flattened readings.",
        bug=(
            f"nested = [[{left}], [{right}]]\n"
            "flat = [pair for pair in nested]\n"
            "print(len(flat))\n"
        ),
        needle="pair for pair",
        bug_why="The comprehension keeps the rows instead of the inner readings.",
        starter=(
            f"nested = [[{left}], [{right}]]\n"
            "flat = [item for pair in nested for item in pair]\n"
            "label = ___\nprint(label)\n"
        ),
        solution=(
            f"nested = [[{left}], [{right}]]\n"
            "flat = [item for pair in nested for item in pair]\n"
            "label = sum(flat)\nprint(label)\n"
        ),
        reveal="label = sum(flat)",
        write_why="The flattened total is what gets printed.",
        example="[item for pair in nested for item in pair]",
    )


def comp_set(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    predict = f"nums = [{left}, {left}, {right}]\nprint(sum({{item for item in nums}}))\n"
    predict2 = f"nums = [{left}, {left}, {left}]\nprint(sum({{item for item in nums}}))\n"
    return _finish(
        "comp_set",
        action="adds each reading once",
        why="A set comprehension drops repeated readings.",
        mcq=["{item for item in nums}", "nums[0]", "nums + nums", "print(nums)"],
        predict=predict,
        predict2=predict2,
        order=["kept", "=", "len", "(", "seen", ")"],
        distractor="sum",
        order_why="kept = len(seen) counts the unique readings.",
        fill_code="total = left ___ right\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds the unique readings.",
        bug=f"nums = [{left}, {left}, {right}]\nprint(sum(nums))\n",
        needle="sum(nums)",
        bug_why="The print adds the repeats instead of the unique readings.",
        starter=f"nums = [{left}, {left}, {right}]\nunique = {{item for item in nums}}\nlabel = ___\nprint(label)\n",
        solution=f"nums = [{left}, {left}, {right}]\nunique = {{item for item in nums}}\nlabel = sum(unique)\nprint(label)\n",
        reveal="label = sum(unique)",
        write_why="The unique total is what gets printed.",
        example="{item for item in nums}",
    )


def branch(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    limit = 15 + twist
    predict = f"score = {left}\nprint(score if score >= {limit} else 90)\n"
    predict2 = f"score = 4\nprint(score if score >= {limit} else 90)\n"
    return _finish(
        "branch",
        action="keeps the score when it reaches the limit",
        why="The matching branch is the one that runs.",
        mcq=[f"score >= {limit}", "score = limit", "for score in limit", "print(limit)"],
        predict=predict,
        predict2=predict2,
        order=["if", "score", ">=", "limit:", "pass"],
        distractor="==",
        order_why="if score >= limit: chooses the matching branch.",
        fill_code="if score ___ limit:\n    label = 1\n",
        fill_answer=">=",
        fill_options=[">=", "==", "<=", "!="],
        fill_why="The boundary includes the limit.",
        bug=f"score = {left}\nif score == 0:\n    score = 1\nprint(score)\n",
        needle="score == 0",
        bug_why="The branch compares with zero instead of the limit.",
        starter=f"score = {left}\nlabel = ___\nprint(label)\n",
        solution=f"score = {left}\nlabel = score if score >= {limit} else 90\nprint(label)\n",
        reveal=f"label = score if score >= {limit} else 90",
        write_why="The branch result is what gets printed.",
        example=f"score >= {limit}",
    )


def context(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    predict = (
        "class Door:\n"
        "    def __enter__(self):\n"
        f"        return {left}\n"
        "    def __exit__(self, *args):\n"
        "        return False\n"
        "with Door() as state:\n"
        "    print(state + 1)\n"
    )
    predict2 = (
        "class Door:\n"
        "    def __enter__(self):\n"
        f"        return {left + 4}\n"
        "    def __exit__(self, *args):\n"
        "        return False\n"
        "with Door() as state:\n"
        "    print(state + 1)\n"
    )
    return _finish(
        "context",
        action="shows the value handed out of the managed block",
        why="__enter__ hands the value to the with line.",
        mcq=["return self", "with Door() as state", "state == Door", "print(Door)"],
        predict=predict,
        predict2=predict2,
        order=["with", "Door()", "as", "state:", "pass"],
        distractor="if",
        order_why="with Door() as state: opens the managed block.",
        fill_code="bonus = state ___ 1\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds one to the handed-out value.",
        bug=(
            "class Door:\n"
            "    def __enter__(self):\n"
            "        return 0\n"
            "    def __exit__(self, *args):\n"
            "        return False\n"
            "with Door() as state:\n"
            f"    print(state + {left})\n"
        ),
        needle="return 0",
        bug_why="__enter__ hands out zero instead of the reading.",
        starter=(
            "class Door:\n"
            "    def __enter__(self):\n"
            f"        return {left}\n"
            "    def __exit__(self, *args):\n"
            "        return False\n"
            "with Door() as state:\n"
            "    label = ___\nprint(label)\n"
        ),
        solution=(
            "class Door:\n"
            "    def __enter__(self):\n"
            f"        return {left}\n"
            "    def __exit__(self, *args):\n"
            "        return False\n"
            "with Door() as state:\n"
            "    label = state\nprint(label)\n"
        ),
        reveal="label = state",
        write_why="The handed-out value is what gets printed.",
        example="with Door() as state:",
    )


def context_cm(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    predict = (
        "from contextlib import contextmanager\n"
        "@contextmanager\n"
        "def door():\n"
        f"    yield {left}\n"
        "with door() as state:\n"
        "    print(state + 2)\n"
    )
    predict2 = (
        "from contextlib import contextmanager\n"
        "@contextmanager\n"
        "def door():\n"
        f"    yield {left + 3}\n"
        "with door() as state:\n"
        "    print(state + 2)\n"
    )
    return _finish(
        "context_cm",
        action="yields the reading into the managed block",
        why="yield hands the reading to the with line.",
        mcq=["yield reading", "return reading", "print(reading)", "pass"],
        predict=predict,
        predict2=predict2,
        order=["def", "door():", "yield", "value"],
        distractor="return",
        order_why="def door(): yield value hands the reading out.",
        fill_code="bonus = state ___ 2\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds two to the yielded reading.",
        bug=(
            "from contextlib import contextmanager\n"
            "@contextmanager\n"
            "def door():\n"
            "    return\n"
            "with door() as state:\n"
            "    print(state)\n"
        ),
        needle="return",
        bug_why="The generator returns instead of yielding a reading.",
        starter=(
            "from contextlib import contextmanager\n"
            "@contextmanager\n"
            "def door():\n"
            f"    yield {left}\n"
            "with door() as state:\n"
            "    label = ___\nprint(label)\n"
        ),
        solution=(
            "from contextlib import contextmanager\n"
            "@contextmanager\n"
            "def door():\n"
            f"    yield {left}\n"
            "with door() as state:\n"
            "    label = state\nprint(label)\n"
        ),
        reveal="label = state",
        write_why="The yielded reading is what gets printed.",
        example="yield reading",
    )


def context_time(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    predict = (
        "class Timer:\n"
        "    def __enter__(self):\n"
        "        self.mark = 10\n"
        "        return self\n"
        "    def __exit__(self, *args):\n"
        "        return False\n"
        "with Timer() as timer:\n"
        f"    print({left} - timer.mark)\n"
    )
    predict2 = (
        "class Timer:\n"
        "    def __enter__(self):\n"
        "        self.mark = 10\n"
        "        return self\n"
        "    def __exit__(self, *args):\n"
        "        return False\n"
        "with Timer() as timer:\n"
        f"    print({left + 5} - timer.mark)\n"
    )
    return _finish(
        "context_time",
        action="shows how far the end sits past the mark",
        why="end - mark is the elapsed gap.",
        mcq=["end - mark", "end + mark", "end == mark", "print(mark)"],
        predict=predict,
        predict2=predict2,
        order=["elapsed", "=", "end", "-", "start"],
        distractor="+",
        order_why="elapsed = end - start is the gap.",
        fill_code="elapsed = end ___ start\n",
        fill_answer="-",
        fill_options=["-", "+", "*", "=="],
        fill_why="Minus finds the gap.",
        bug=(
            "class Timer:\n"
            "    def __enter__(self):\n"
            "        self.mark = 10\n"
            "        return self\n"
            "    def __exit__(self, *args):\n"
            "        return False\n"
            "with Timer() as timer:\n"
            f"    print({left} + timer.mark)\n"
        ),
        needle=f"{left} + timer.mark",
        bug_why="The print adds the mark instead of subtracting it.",
        starter=(
            "class Timer:\n"
            "    def __enter__(self):\n"
            "        self.mark = 10\n"
            "        return self\n"
            "    def __exit__(self, *args):\n"
            "        return False\n"
            "with Timer() as timer:\n"
            "    label = ___\nprint(label)\n"
        ),
        solution=(
            "class Timer:\n"
            "    def __enter__(self):\n"
            "        self.mark = 10\n"
            "        return self\n"
            "    def __exit__(self, *args):\n"
            "        return False\n"
            "with Timer() as timer:\n"
            f"    label = {left} - timer.mark\nprint(label)\n"
        ),
        reveal=f"label = {left} - timer.mark",
        write_why="The elapsed gap is what gets printed.",
        example="end - mark",
    )


def context_suppress(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    predict = (
        "class Quiet:\n"
        "    def __enter__(self):\n"
        "        return self\n"
        "    def __exit__(self, exc_type, exc, tb):\n"
        "        return True\n"
        "try:\n"
        "    with Quiet():\n"
        "        raise RuntimeError('nope')\n"
        f"    print({left + 5})\n"
        "except RuntimeError:\n"
        f"    print({left})\n"
    )
    predict2 = (
        "class Quiet:\n"
        "    def __enter__(self):\n"
        "        return self\n"
        "    def __exit__(self, exc_type, exc, tb):\n"
        "        return False\n"
        "try:\n"
        "    with Quiet():\n"
        "        raise RuntimeError('nope')\n"
        f"    print({left + 5})\n"
        "except RuntimeError:\n"
        f"    print({left})\n"
    )
    return _finish(
        "context_suppress",
        action="lets the block finish when the exit asks to suppress",
        why="Returning True from __exit__ suppresses the error.",
        mcq=["return True", "return False", "raise RuntimeError", "print(error)"],
        predict=predict,
        predict2=predict2,
        order=["flag", "=", "True"],
        distractor="False",
        order_why="flag = True is the suppress signal.",
        fill_code="bonus = reading ___ 5\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds five after the block finishes.",
        bug=(
            "class Quiet:\n"
            "    def __enter__(self):\n"
            "        return self\n"
            "    def __exit__(self, exc_type, exc, tb):\n"
            "        return False\n"
            "print(1)\n"
        ),
        needle="return False",
        bug_why="__exit__ lets the error escape.",
        starter=(
            "class Quiet:\n"
            "    def __enter__(self):\n"
            "        return self\n"
            "    def __exit__(self, exc_type, exc, tb):\n"
            "        return True\n"
            "try:\n"
            "    with Quiet():\n"
            "        raise RuntimeError('nope')\n"
            "    label = ___\n"
            "except RuntimeError:\n"
            "    label = 0\n"
            "print(label)\n"
        ),
        solution=(
            "class Quiet:\n"
            "    def __enter__(self):\n"
            "        return self\n"
            "    def __exit__(self, exc_type, exc, tb):\n"
            "        return True\n"
            "try:\n"
            "    with Quiet():\n"
            "        raise RuntimeError('nope')\n"
            f"    label = {left}\n"
            "except RuntimeError:\n"
            "    label = 0\n"
            "print(label)\n"
        ),
        reveal=f"label = {left}",
        write_why="The finished-block reading is what gets printed.",
        example="return True",
    )


def context_lock(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    common = (
        "class Lock:\n"
        "    def __init__(self):\n"
        "        self.open = 0\n"
        "    def __enter__(self):\n"
        "        self.open = 1\n"
        "        return self\n"
        "    def __exit__(self, *args):\n"
        "        self.open = 0\n"
        "        return False\n"
    )
    predict = common + "lock = Lock()\nwith lock:\n    held = lock.open\nprint(held * " + str(left) + " + held)\n"
    predict2 = common + "lock = Lock()\nwith lock:\n    held = lock.open\nheld = lock.open\nprint(held * " + str(left) + " + " + str(left) + ")\n"
    return _finish(
        "context_lock",
        action="shows the flag while the lock is held",
        why="Inside the block the flag is on.",
        mcq=["self.open = 1", "self.open == 1", "print(self)", "return 0"],
        predict=predict,
        predict2=predict2,
        order=["self.open", "=", "1"],
        distractor="==",
        order_why="self.open = 1 turns the flag on.",
        fill_code="shown = held * reading ___ held\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds the flag after the scaled reading.",
        bug=(common + "lock = Lock()\nwith lock:\n    held = lock.open\nprint(held)\n").replace(
            "self.open = 1", "self.open = 5", 1
        ),
        needle="self.open = 5",
        bug_why="The flag is set to five instead of on.",
        starter=common + "lock = Lock()\nwith lock:\n    label = ___\nprint(label)\n",
        solution=common + "lock = Lock()\nwith lock:\n    label = lock.open\nprint(label)\n",
        reveal="label = lock.open",
        write_why="The held flag is what gets printed.",
        example="self.open = 1",
    )


def deco_wrap(word: str, number: int, twist: int) -> dict:
    extra = 3 + twist
    predict = (
        "def bonus(fn):\n"
        "    def wrapped(value):\n"
        f"        return fn(value) + {extra}\n"
        "    return wrapped\n"
        "@bonus\n"
        "def base(value):\n"
        "    return value\n"
        f"print(base({number}))\n"
    )
    predict2 = (
        "def bonus(fn):\n"
        "    def wrapped(value):\n"
        f"        return fn(value) + {extra + 4}\n"
        "    return wrapped\n"
        "@bonus\n"
        "def base(value):\n"
        "    return value\n"
        f"print(base({number}))\n"
    )
    return _finish(
        "deco_wrap",
        action="adds the bonus before handing the result back",
        why="The wrapper adds the bonus to the original result.",
        mcq=[f"fn(value) + {extra}", "fn(value) == value", "print(fn)", "pass"],
        predict=predict,
        predict2=predict2,
        order=["return", "fn", "(", "value", ")"],
        distractor="print",
        order_why="return fn(value) calls the wrapped function.",
        fill_code="return fn(value) ___ extra\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds the bonus.",
        bug=(
            "def bonus(fn):\n"
            "    def wrapped(value):\n"
            "        return fn(value) - extra\n"
            "    return wrapped\n"
            "extra = 3\n"
            "@bonus\n"
            "def base(value):\n"
            "    return value\n"
            f"print(base({number}))\n"
        ),
        needle="fn(value) - extra",
        bug_why="The wrapper subtracts the bonus.",
        starter=(
            "def bonus(fn):\n"
            "    def wrapped(value):\n"
            f"        return fn(value) + {extra}\n"
            "    return wrapped\n"
            "@bonus\n"
            "def base(value):\n"
            "    return value\n"
            "label = ___\nprint(label)\n"
        ),
        solution=(
            "def bonus(fn):\n"
            "    def wrapped(value):\n"
            f"        return fn(value) + {extra}\n"
            "    return wrapped\n"
            "@bonus\n"
            "def base(value):\n"
            "    return value\n"
            f"label = base({number})\nprint(label)\n"
        ),
        reveal=f"label = base({number})",
        write_why="The wrapped result is what gets printed.",
        example=f"fn(value) + {extra}",
    )


def deco_memo(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = (
        "def memo(fn):\n"
        "    cache = {}\n"
        "    def wrapped(value):\n"
        "        if value not in cache:\n"
        "            cache[value] = fn(value)\n"
        "        return cache[value]\n"
        "    return wrapped\n"
        "@memo\n"
        "def double(value):\n"
        "    return value * 2\n"
    )
    return _finish(
        "deco_memo",
        action="reuses the stored result for a repeated call",
        why="The cache returns the stored result on the second call.",
        mcq=["cache[value] = fn(value)", "cache == value", "print(cache)", "pass"],
        predict=body + f"print(double({left}) + double({left}))\n",
        predict2=body + f"print(double({left + 1}) + double({left + 1}))\n",
        order=["cache", "[", "value", "]", "=", "fn(value)"],
        distractor="==",
        order_why="cache[value] = fn(value) stores the result.",
        fill_code="return value ___ 2\n",
        fill_answer="*",
        fill_options=["*", "+", "-", "=="],
        fill_why="The star doubles the stored input.",
        bug=body.replace("cache[value] = fn(value)", "cache[value] = 0") + f"print(double({left}))\n",
        needle="cache[value] = 0",
        bug_why="The cache stores zero instead of the result.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + f"label = double({left})\nprint(label)\n",
        reveal=f"label = double({left})",
        write_why="The cached result is what gets printed.",
        example="cache[value] = fn(value)",
    )


def deco_count(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = (
        "def count_calls(fn):\n"
        "    def wrapped(value):\n"
        "        wrapped.calls = wrapped.calls + 1\n"
        "        return fn(value)\n"
        "    wrapped.calls = 0\n"
        "    return wrapped\n"
        "@count_calls\n"
        "def echo(value):\n"
        "    return value\n"
    )
    return _finish(
        "deco_count",
        action="counts how many times the wrapper runs",
        why="Each call adds one to the wrapper tally.",
        mcq=["wrapped.calls + 1", "wrapped.calls == 1", "print(calls)", "pass"],
        predict=body + f"echo({left})\necho({left})\nprint(echo.calls * {left})\n",
        predict2=body + f"echo({left})\nprint(echo.calls * {left})\n",
        order=["seen", "=", "calls", "+", "1"],
        distractor="==",
        order_why="seen = calls + 1 records one more call.",
        fill_code="wrapped.calls = wrapped.calls ___ 1\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus records one more call.",
        bug=body.replace("wrapped.calls + 1", "wrapped.calls + 0") + f"echo({left})\nprint(echo.calls)\n",
        needle="wrapped.calls + 0",
        bug_why="The tally adds zero, so the call is not recorded.",
        starter=body + f"echo({left})\necho({left})\nlabel = ___\nprint(label)\n",
        solution=body + f"echo({left})\necho({left})\nlabel = echo.calls\nprint(label)\n",
        reveal="label = echo.calls",
        write_why="The call tally is what gets printed.",
        example="wrapped.calls + 1",
    )


def deco_guard(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = (
        "def positive(fn):\n"
        "    def wrapped(value):\n"
        "        if value <= 0:\n"
        "            return 90\n"
        "        return fn(value)\n"
        "    return wrapped\n"
        "@positive\n"
        "def echo(value):\n"
        "    return value\n"
    )
    return _finish(
        "deco_guard",
        action="rejects a non-positive argument before the call",
        why="The guard returns early when the argument is not positive.",
        mcq=["value <= 0", "value == 0", "print(value)", "pass"],
        predict=body + f"print(echo({left}))\n",
        predict2=body + "print(echo(0))\n",
        order=["if", "value", "<=", "0:", "return", "90"],
        distractor="==",
        order_why="if value <= 0: return 90 rejects the bad argument.",
        fill_code="if value ___ 0:\n    label = 1\n",
        fill_answer="<=",
        fill_options=["<=", "<", "==", ">"],
        fill_why="The check includes zero.",
        bug=body.replace("value <= 0", "value > 0") + f"print(echo({left}))\n",
        needle="value > 0",
        bug_why="The guard rejects positive arguments.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + f"label = echo({left})\nprint(label)\n",
        reveal=f"label = echo({left})",
        write_why="The accepted argument is what gets printed.",
        example="if value <= 0: return 90",
    )


def exc_div(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = (
        "def safe(value):\n"
        "    try:\n"
        f"        return {left} // value\n"
        "    except ZeroDivisionError:\n"
        f"        return {left + 6}\n"
    )
    return _finish(
        "exc_div",
        action="returns a fallback when the divisor is zero",
        why="The except branch runs for ZeroDivisionError.",
        mcq=["except ZeroDivisionError", "except KeyError", "return value", "print(value)"],
        predict=body + "print(safe(0))\n",
        predict2=body + "print(safe(2))\n",
        order=["def", "safe(value):", "return", "left", "//", "value"],
        distractor="%",
        order_why="return left // value is the division.",
        fill_code=f"return {left} ___ value\n",
        fill_answer="//",
        fill_options=["//", "/", "%", "+"],
        fill_why="The double slash divides and drops the remainder.",
        bug=body.replace("ZeroDivisionError", "KeyError") + "print(safe(0))\n",
        needle="KeyError",
        bug_why="The except watches the wrong error.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + "label = safe(0)\nprint(label)\n",
        reveal="label = safe(0)",
        write_why="The fallback is what gets printed.",
        example="except ZeroDivisionError",
    )


def exc_custom(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    def program(extra: int) -> str:
        return (
            "class Boom(Exception):\n"
            "    pass\n"
            "try:\n"
            "    raise Boom('stop')\n"
            "except Boom:\n"
            f"    print({left + extra})\n"
        )
    return _finish(
        "exc_custom",
        action="handles the custom error and shows a reading",
        why="except Boom catches the raised Boom.",
        mcq=["raise Boom('stop')", "print(Boom)", "Boom == stop", "pass"],
        predict=program(3),
        predict2=program(8),
        order=["raise", "Boom", "(", "'stop'", ")"],
        distractor="return",
        order_why="raise Boom('stop') raises the custom error.",
        fill_code=f"shown = {left} ___ 3\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus builds the reading shown after the catch.",
        bug=(
            "class Boom(Exception):\n"
            "    pass\n"
            "try:\n"
            "    raise Boom('stop')\n"
            "except KeyError:\n"
            f"    print({left})\n"
        ),
        needle="KeyError",
        bug_why="The except watches the wrong error.",
        starter=(
            "class Boom(Exception):\n"
            "    pass\n"
            "try:\n"
            "    raise Boom('stop')\n"
            "except Boom:\n"
            "    label = ___\n"
            "print(label)\n"
        ),
        solution=(
            "class Boom(Exception):\n"
            "    pass\n"
            "try:\n"
            "    raise Boom('stop')\n"
            "except Boom:\n"
            f"    label = {left}\n"
            "print(label)\n"
        ),
        reveal=f"label = {left}",
        write_why="The caught-branch reading is what gets printed.",
        example="raise Boom('stop')",
    )


def exc_retry(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    def program(goal: int) -> str:
        return (
            "def attempt(goal):\n"
            "    left_tries = 3\n"
            "    while left_tries:\n"
            "        try:\n"
            "            if left_tries > 1:\n"
            "                raise RuntimeError('again')\n"
            "            return goal\n"
            "        except RuntimeError:\n"
            "            left_tries = left_tries - 1\n"
            "    return 0\n"
            f"print(attempt({goal}))\n"
        )
    return _finish(
        "exc_retry",
        action="tries again until the call can return the goal",
        why="Each RuntimeError spends one try.",
        mcq=["left_tries - 1", "left_tries == 1", "print(goal)", "pass"],
        predict=program(left),
        predict2=program(left + 4),
        order=["raise", "RuntimeError", "(", "'again'", ")"],
        distractor="return",
        order_why="raise RuntimeError('again') spends a try.",
        fill_code="left_tries = left_tries ___ 1\n",
        fill_answer="-",
        fill_options=["-", "+", "*", "=="],
        fill_why="Minus spends one try.",
        bug=program(left).replace("left_tries > 1", "left_tries > 5"),
        needle="left_tries > 5",
        bug_why="The threshold never matches, so no retry happens.",
        starter=program(left).replace(f"print(attempt({left}))\n", "label = ___\nprint(label)\n"),
        solution=program(left).replace(f"print(attempt({left}))\n", f"label = attempt({left})\nprint(label)\n"),
        reveal=f"label = attempt({left})",
        write_why="The goal reached after retries is what gets printed.",
        example="left_tries - 1",
    )


def exc_parse(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = (
        "def parse(text):\n"
        "    try:\n"
        "        return int(text)\n"
        "    except ValueError:\n"
        f"        return {left}\n"
    )
    return _finish(
        "exc_parse",
        action="returns the fallback when the text is not a whole number",
        why="ValueError means the text could not be converted.",
        mcq=["except ValueError", "except KeyError", "return text", "print(text)"],
        predict=body + "print(parse('nope'))\n",
        predict2=body + f"print(parse('{left + 4}'))\n",
        order=["return", "int", "(", "text", ")"],
        distractor="str",
        order_why="return int(text) converts the text.",
        fill_code="shown = parsed ___ 1\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds one after a successful conversion.",
        bug=body.replace("ValueError", "KeyError") + "print(parse('nope'))\n",
        needle="KeyError",
        bug_why="The except watches the wrong error.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + "label = parse('nope')\nprint(label)\n",
        reveal="label = parse('nope')",
        write_why="The fallback is what gets printed.",
        example="except ValueError",
    )


def exc_translate(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = (
        "def lookup(pairs, key):\n"
        "    try:\n"
        "        return pairs[key]\n"
        "    except KeyError:\n"
        f"        return {left + 4}\n"
    )
    return _finish(
        "exc_translate",
        action="returns a clear fallback when the name is missing",
        why="KeyError means that name was never stored.",
        mcq=["except KeyError", "except ValueError", "return pairs", "print(key)"],
        predict=body + f"print(lookup({{'a': {left}}}, 'missing'))\n",
        predict2=body + f"print(lookup({{'a': {left}}}, 'a'))\n",
        order=["raise", "ValueError", "(", "'missing'", ")"],
        distractor="return",
        order_why="raise ValueError('missing') replaces the lookup error.",
        fill_code=f"shown = {left} ___ 4\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus builds the fallback reading.",
        bug=body.replace("KeyError", "TypeError") + f"print(lookup({{'a': {left}}}, 'missing'))\n",
        needle="TypeError",
        bug_why="The except watches the wrong error.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + f"label = lookup({{'a': {left}}}, 'missing')\nprint(label)\n",
        reveal=f"label = lookup({{'a': {left}}}, 'missing')",
        write_why="The missing-name fallback is what gets printed.",
        example="except KeyError",
    )


def func_add(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    body = (
        "def total(left, right):\n"
        "    \"\"\"Add the two readings.\"\"\"\n"
        "    return left + right\n"
    )
    return _finish(
        "func_add",
        action="adds the two arguments and hands the sum back",
        why="return left + right hands the sum to the caller.",
        mcq=["return left + right", "left == right", "print(left)", "pass"],
        predict=body + f"print(total({left}, {right}))\n",
        predict2=body + f"print(total({left}, {right + 3}))\n",
        order=["return", "left", "+", "right"],
        distractor="print",
        order_why="return left + right hands back the sum.",
        fill_code="return left ___ right\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds the two arguments.",
        bug=body.replace("left + right", "left - right") + f"print(total({left}, {right}))\n",
        needle="left - right",
        bug_why="The function subtracts the arguments.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + f"label = total({left}, {right})\nprint(label)\n",
        reveal=f"label = total({left}, {right})",
        write_why="The handed-back sum is what gets printed.",
        example="return left + right",
    )


def func_const(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    bake = 7 + twist
    body = (
        f"PREP = {left}\n"
        f"BAKE = {bake}\n"
        "def total():\n"
        "    return PREP + BAKE\n"
    )
    return _finish(
        "func_const",
        action="adds the two fixed readings",
        why="PREP + BAKE is the combined reading.",
        mcq=["PREP + BAKE", "PREP == BAKE", "print(PREP)", "pass"],
        predict=body + "print(total())\n",
        predict2=body.replace(f"BAKE = {bake}", f"BAKE = {bake + 4}") + "print(total())\n",
        order=["TOTAL", "=", "PREP", "+", "BAKE"],
        distractor="==",
        order_why="TOTAL = PREP + BAKE stores the combined reading.",
        fill_code="return PREP ___ BAKE\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds the two fixed readings.",
        bug=body.replace("PREP + BAKE", "PREP - BAKE") + "print(total())\n",
        needle="PREP - BAKE",
        bug_why="The function subtracts the bake reading.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + "label = total()\nprint(label)\n",
        reveal="label = total()",
        write_why="The combined reading is what gets printed.",
        example="PREP + BAKE",
    )


def func_scale(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = (
        "def scale(value, portions):\n"
        "    return value * portions\n"
    )
    return _finish(
        "func_scale",
        action="multiplies the base reading by the portion count",
        why="value * portions scales the reading.",
        mcq=["value * portions", "value + portions", "value == portions", "print(value)"],
        predict=body + f"print(scale({left}, 2))\n",
        predict2=body + f"print(scale({left}, 3))\n",
        order=["return", "value", "*", "portions"],
        distractor="+",
        order_why="return value * portions scales the reading.",
        fill_code="return value ___ portions\n",
        fill_answer="*",
        fill_options=["*", "+", "-", "=="],
        fill_why="The star scales the reading.",
        bug=body.replace("value * portions", "value + portions") + f"print(scale({left}, 2))\n",
        needle="value + portions",
        bug_why="The function adds the portion count instead of scaling.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + f"label = scale({left}, 2)\nprint(label)\n",
        reveal=f"label = scale({left}, 2)",
        write_why="The scaled reading is what gets printed.",
        example="value * portions",
    )


def func_doc(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = (
        "def total(value):\n"
        "    \"\"\"Add one serving.\"\"\"\n"
        "    return value + 1\n"
    )
    return _finish(
        "func_doc",
        action="adds one serving and includes the note length",
        why="The docstring is stored on the function and the return adds one.",
        mcq=["return value + 1", "value == 1", "print(value)", "pass"],
        predict=body + f"print(total({left}) + len(total.__doc__))\n",
        predict2=body + f"print(total({left + 3}) + len(total.__doc__))\n",
        order=["return", "value", "+", "1"],
        distractor="print",
        order_why="return value + 1 adds one serving.",
        fill_code="return value ___ 1\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds one serving.",
        bug=body.replace("value + 1", "value - 1") + f"print(total({left}))\n",
        needle="value - 1",
        bug_why="The function subtracts one serving.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + f"label = total({left})\nprint(label)\n",
        reveal=f"label = total({left})",
        write_why="The serving total is what gets printed.",
        example="return value + 1",
    )


def gen_yield(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = (
        "def seq(limit):\n"
        "    step = 0\n"
        "    while step < limit:\n"
        "        yield step\n"
        "        step = step + 1\n"
    )
    return _finish(
        "gen_yield",
        action="adds the yielded steps",
        why="yield hands each step out one at a time.",
        mcq=["yield step", "return step", "print(step)", "pass"],
        predict=body + f"print(sum(seq(4)) + {left})\n",
        predict2=body + f"print(sum(seq(5)) + {left})\n",
        order=["def", "seq():", "yield", "step"],
        distractor="return",
        order_why="def seq(): yield step hands out one step.",
        fill_code="step = step ___ 1\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus moves to the next step.",
        bug=body.replace("yield step", "return step") + f"print(sum(seq(4)) + {left})\n",
        needle="return step",
        bug_why="The function returns one step and then stops.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + f"label = sum(seq(4)) + {left}\nprint(label)\n",
        reveal=f"label = sum(seq(4)) + {left}",
        write_why="The yielded total is what gets printed.",
        example="yield step",
    )


def gen_take(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    body = (
        "def take(limit, source):\n"
        "    count = 0\n"
        "    for item in source:\n"
        "        if count == limit:\n"
        "            break\n"
        "        yield item\n"
        "        count = count + 1\n"
    )
    return _finish(
        "gen_take",
        action="adds only the first readings from the source",
        why="The generator stops when the limit is reached.",
        mcq=["if count == limit: break", "count = limit", "print(item)", "pass"],
        predict=body + f"print(sum(take(2, [{left}, {left + 3}, {left + 9}])))\n",
        predict2=body + f"print(sum(take(1, [{left}, {left + 3}, {left + 9}])))\n",
        order=["if", "count", "==", "limit:", "break"],
        distractor="return",
        order_why="if count == limit: break stops the walk.",
        fill_code="count = count ___ 1\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus counts one more taken reading.",
        bug=body.replace("count == limit", "count == 0") + f"print(sum(take(2, [{left}, {right}])))\n",
        needle="count == 0",
        bug_why="The stop check matches immediately.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + f"label = sum(take(2, [{left}, {left + 3}, {left + 9}]))\nprint(label)\n",
        reveal=f"label = sum(take(2, [{left}, {left + 3}, {left + 9}]))",
        write_why="The taken total is what gets printed.",
        example="if count == limit: break",
    )


def gen_avg(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = (
        "def averages(values):\n"
        "    total = 0\n"
        "    seen = 0\n"
        "    for value in values:\n"
        "        total = total + value\n"
        "        seen = seen + 1\n"
        "        yield total // seen\n"
    )
    return _finish(
        "gen_avg",
        action="yields the running whole-number average",
        why="total // seen is the average so far.",
        mcq=["total // seen", "total * seen", "print(total)", "pass"],
        predict=body + f"print(list(averages([{left}, {left + 4}]))[-1])\n",
        predict2=body + f"print(list(averages([{left}, {left + 4}, {left + 6}]))[-1])\n",
        order=["def", "gen():", "yield", "total", "//", "seen"],
        distractor="return",
        order_why="yield total // seen hands out the average.",
        fill_code="total = total ___ value\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus adds the new reading into the running total.",
        bug=body.replace("total // seen", "total * seen") + f"print(list(averages([{left}]))[-1])\n",
        needle="total * seen",
        bug_why="The generator multiplies instead of dividing.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + f"label = list(averages([{left}, {left + 4}]))[-1]\nprint(label)\n",
        reveal=f"label = list(averages([{left}, {left + 4}]))[-1]",
        write_why="The latest average is what gets printed.",
        example="total // seen",
    )


def gen_chunk(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = (
        "def chunks(values, size):\n"
        "    start = 0\n"
        "    while start < len(values):\n"
        "        yield values[start:start + size]\n"
        "        start = start + size\n"
    )
    return _finish(
        "gen_chunk",
        action="adds the first chunk of readings",
        why="The slice takes size readings and then the start moves forward.",
        mcq=["start + size", "start == size", "print(values)", "pass"],
        predict=body + f"print(sum(list(chunks([{left}, 2, 3, 4], 2))[0]))\n",
        predict2=body + f"print(sum(list(chunks([{left}, 2, 3, 4], 3))[0]))\n",
        order=["step", "=", "start", "+", "size"],
        distractor="-",
        order_why="step = start + size is the next chunk boundary.",
        fill_code="start = start ___ size\n",
        fill_answer="+",
        fill_options=["+", "-", "*", "=="],
        fill_why="Plus moves the start by one chunk.",
        bug=body.replace("start = start + size", "start = start - size") + "print(0)\n",
        needle="start = start - size",
        bug_why="The chunk moves backward.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + f"label = sum(list(chunks([{left}, 2, 3, 4], 2))[0])\nprint(label)\n",
        reveal=f"label = sum(list(chunks([{left}, 2, 3, 4], 2))[0])",
        write_why="The first chunk total is what gets printed.",
        example="start + size",
    )


def gen_filter(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = (
        "def keep(values, cut):\n"
        "    for value in values:\n"
        "        if value > cut:\n"
        "            yield value\n"
    )
    return _finish(
        "gen_filter",
        action="adds only the readings above the cutoff",
        why="yield runs only when the reading is above the cutoff.",
        mcq=["value > cut", "value == cut", "print(value)", "pass"],
        predict=body + f"print(sum(keep([{left}, 3, {left + 5}], 10)))\n",
        predict2=body + f"print(sum(keep([{left}, 3, {left + 5}], {left})))\n",
        order=["flag", "=", "value", ">", "cut"],
        distractor="<",
        order_why="flag = value > cut is the keep test.",
        fill_code="if value ___ cut:\n    label = 1\n",
        fill_answer=">",
        fill_options=[">", "<", "==", "<="],
        fill_why="The cutoff keeps the greater readings.",
        bug=body.replace("value > cut", "value < cut") + f"print(sum(keep([{left}, 3], 10)))\n",
        needle="value < cut",
        bug_why="The generator keeps the small readings.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + f"label = sum(keep([{left}, 3, {left + 5}], 10))\nprint(label)\n",
        reveal=f"label = sum(keep([{left}, 3, {left + 5}], 10))",
        write_why="The kept total is what gets printed.",
        example="value > cut",
    )


def loop_filter(word: str, number: int, twist: int) -> dict:
    return gen_filter(word, number, twist)


def _opts(answer: str) -> list[str]:
    pool = [answer, "+", "-", "*", "==", ">", "<", "//"]
    opts: list[str] = []
    for item in pool:
        if item not in opts:
            opts.append(item)
        if len(opts) == 4:
            break
    return opts


def list_append(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    predict = f"items = [{left}]\nitems.append({right})\nprint(sum(items))\n"
    predict2 = f"items = [{left}]\nitems.append({right})\nitems.append({right})\nprint(sum(items))\n"
    return _finish(
        "list_append",
        action="adds the stored readings after one more is attached",
        why="append stores the new reading at the end.",
        mcq=["items.append(reading)", "items[0]", "len(items)", "items + 1"],
        predict=predict, predict2=predict2,
        order=["items", ".", "append", "(", "reading", ")"],
        distractor="pop",
        order_why="items.append(reading) stores the new reading.",
        fill_code="total = left ___ right\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus adds the stored readings.",
        bug=f"items = [{left}]\nitems.append(0)\nprint(sum(items))\n",
        needle="append(0)",
        bug_why="Zero is attached instead of the reading.",
        starter=f"items = [{left}]\nitems.append({right})\nlabel = ___\nprint(label)\n",
        solution=f"items = [{left}]\nitems.append({right})\nlabel = sum(items)\nprint(label)\n",
        reveal="label = sum(items)",
        write_why="The stored total is what gets printed.",
        example="items.append(reading)",
    )


def list_insert(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    predict = f"items = [{right}]\nitems.insert(0, {left})\nprint(sum(items))\n"
    predict2 = f"items = [{right}, {right}]\nitems.insert(0, {left})\nprint(sum(items))\n"
    return _finish(
        "list_insert",
        action="adds the readings after one is placed at the front",
        why="insert(0, reading) places the reading at the front.",
        mcq=["items.insert(0, reading)", "items.append(0)", "items[0] == reading", "print(items)"],
        predict=predict, predict2=predict2,
        order=["items", ".", "insert", "(", "0", ",", "reading", ")"],
        distractor="append",
        order_why="items.insert(0, reading) places the reading first.",
        fill_code="total = left ___ right\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus adds the stored readings.",
        bug=f"items = [{right}]\nitems.insert(1, {left})\nprint(items[0])\n",
        needle="insert(1,",
        bug_why="The reading is placed after the old front.",
        starter=f"items = [{right}]\nitems.insert(0, {left})\nlabel = ___\nprint(label)\n",
        solution=f"items = [{right}]\nitems.insert(0, {left})\nlabel = sum(items)\nprint(label)\n",
        reveal="label = sum(items)",
        write_why="The stored total is what gets printed.",
        example="items.insert(0, reading)",
    )


def list_sort(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = f"items = [{left + 5}, {left}, {left + 2}]\n"
    return _finish(
        "list_sort",
        action="shows a reading from the sorted order",
        why="sorted(items) orders the readings from small to large.",
        mcq=["sorted(items)", "items[0]", "items.append(0)", "print(items)"],
        predict=body + "print(sorted(items)[0])\n",
        predict2=body + "print(sorted(items)[-1])\n",
        order=["ordered", "=", "sorted", "(", "items", ")"],
        distractor="reversed",
        order_why="ordered = sorted(items) stores the ordered readings.",
        fill_code="if ordered[0] ___ ordered[1]:\n    label = 1\n",
        fill_answer="<", fill_options=_opts("<"),
        fill_why="The first sorted reading is smaller than the next.",
        bug=body + "print(sorted(items, reverse=True)[0])\n",
        needle="reverse=True",
        bug_why="The order is reversed, so the first reading is the large one.",
        starter=body + "ordered = sorted(items)\nlabel = ___\nprint(label)\n",
        solution=body + "ordered = sorted(items)\nlabel = ordered[0]\nprint(label)\n",
        reveal="label = ordered[0]",
        write_why="The smallest reading is what gets printed.",
        example="sorted(items)",
    )


def list_pop(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    predict = f"items = [{left}, {right}, {left + 6}]\nitems.pop()\nprint(items[-1] + {left})\n"
    predict2 = f"items = [{left}, {right}, {left + 6}]\nitems.pop()\nitems.pop()\nprint(items[-1] + {left})\n"
    return _finish(
        "list_pop",
        action="shows the new top after the last reading is removed",
        why="pop() removes the last reading.",
        mcq=["items.pop()", "items.append(0)", "items[0]", "len(items)"],
        predict=predict, predict2=predict2,
        order=["items", ".", "pop", "(", ")"],
        distractor="append",
        order_why="items.pop() removes the last reading.",
        fill_code="shown = top ___ left\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus adds the base reading to the new top.",
        bug=f"items = [{left}, {right}]\nitems.append({left})\nprint(items[-1])\n",
        needle="append",
        bug_why="A reading is attached instead of removed.",
        starter=f"items = [{left}, {right}, {left + 6}]\nitems.pop()\nlabel = ___\nprint(label)\n",
        solution=f"items = [{left}, {right}, {left + 6}]\nitems.pop()\nlabel = items[-1] + {left}\nprint(label)\n",
        reveal=f"label = items[-1] + {left}",
        write_why="The new top plus the base reading is what gets printed.",
        example="items.pop()",
    )


def list_count(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    return _finish(
        "list_count",
        action="scales the base reading by how often it appears",
        why="count(reading) is how many times that reading is stored.",
        mcq=["items.count(reading)", "items[0]", "len(items)", "items + 1"],
        predict=f"items = [{left}, {right}, {left}]\nprint(items.count({left}) * {left})\n",
        predict2=f"items = [{left}, {right}, {right}]\nprint(items.count({left}) * {left})\n",
        order=["seen", "=", "items.count", "(", "reading", ")"],
        distractor="len",
        order_why="seen = items.count(reading) stores the tally.",
        fill_code="shown = seen ___ left\n", fill_answer="*", fill_options=_opts("*"),
        fill_why="The star scales the base reading by the tally.",
        bug=f"items = [{left}, {right}, {left}]\nprint(items.count({right}) * {left})\n",
        needle=f"count({right})",
        bug_why="The tally counts the other reading.",
        starter=f"items = [{left}, {right}, {left}]\nlabel = ___\nprint(label)\n",
        solution=f"items = [{left}, {right}, {left}]\nlabel = items.count({left}) * {left}\nprint(label)\n",
        reveal=f"label = items.count({left}) * {left}",
        write_why="The scaled tally is what gets printed.",
        example="items.count(reading)",
    )


def list_len(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    return _finish(
        "list_len",
        action="scales the base reading by how many items are stored",
        why="len(items) is the stored count.",
        mcq=["len(items)", "items[0]", "items + 1", "sum(items)"],
        predict=f"items = [{left}, {right}, 8]\nprint(len(items) * {left})\n",
        predict2=f"items = [{left}, {right}]\nprint(len(items) * {left})\n",
        order=["seen", "=", "len", "(", "items", ")"],
        distractor="sum",
        order_why="seen = len(items) stores the count.",
        fill_code="shown = seen ___ left\n", fill_answer="*", fill_options=_opts("*"),
        fill_why="The star scales the base reading by the count.",
        bug=f"items = [{left}, {right}, 8]\nprint(items[0])\n",
        needle="items[0]",
        bug_why="The print reads the first slot instead of the count.",
        starter=f"items = [{left}, {right}, 8]\nlabel = ___\nprint(label)\n",
        solution=f"items = [{left}, {right}, 8]\nlabel = len(items) * {left}\nprint(label)\n",
        reveal=f"label = len(items) * {left}",
        write_why="The scaled count is what gets printed.",
        example="len(items)",
    )


def list_concat(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    return _finish(
        "list_concat",
        action="adds the readings from both lists",
        why="left_items + right_items joins the lists.",
        mcq=["left_items + right_items", "left_items - right_items", "len(left_items)", "left_items == right_items"],
        predict=f"print(sum([{left}] + [{right}]))\n",
        predict2=f"print(sum([{left}] + [{right}, {right}]))\n",
        order=["joined", "=", "left_items", "+", "right_items"],
        distractor="-",
        order_why="joined = left_items + right_items joins the lists.",
        fill_code="joined = left_items ___ right_items\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus joins the two lists.",
        bug=f"print(sum([{left}] + []))\n",
        needle="+ []",
        bug_why="The second list is empty, so its readings are missing.",
        starter=f"left_items = [{left}]\nright_items = [{right}]\nlabel = ___\nprint(label)\n",
        solution=f"left_items = [{left}]\nright_items = [{right}]\nlabel = sum(left_items + right_items)\nprint(label)\n",
        reveal="label = sum(left_items + right_items)",
        write_why="The joined total is what gets printed.",
        example="left_items + right_items",
    )


def list_slice(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    body = f"items = [{left}, {right}, {left + 6}, 9]\n"
    return _finish(
        "list_slice",
        action="adds the readings in the chosen slice",
        why="items[0:2] keeps the first two readings.",
        mcq=["items[0:2]", "items[0]", "len(items)", "items + 1"],
        predict=body + "print(sum(items[0:2]))\n",
        predict2=body + "print(sum(items[0:3]))\n",
        order=["chunk", "=", "items", "[", "0:2", "]"],
        distractor="len",
        order_why="chunk = items[0:2] keeps the first two readings.",
        fill_code="chunk = items[0 ___ 2]\n", fill_answer=":", fill_options=[":", ",", "+", "-"],
        fill_why="The colon separates the start from the stop.",
        bug=body + "print(sum(items[2:4]))\n",
        needle="items[2:4]",
        bug_why="The slice starts too late.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + "label = sum(items[0:2])\nprint(label)\n",
        reveal="label = sum(items[0:2])",
        write_why="The slice total is what gets printed.",
        example="items[0:2]",
    )


def list_sum(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    return _finish(
        "list_sum",
        action="adds every stored reading",
        why="sum(items) adds the stored readings.",
        mcq=["sum(items)", "len(items)", "items[0]", "items + 1"],
        predict=f"items = [{left}, {right}]\nprint(sum(items))\n",
        predict2=f"items = [{left}, {right}, 6]\nprint(sum(items))\n",
        order=["total", "=", "left", "+", "right"],
        distractor="-",
        order_why="total = left + right adds the two readings.",
        fill_code="total = left ___ right\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus adds the two readings.",
        bug=f"items = [{left}, {right}]\nprint(len(items))\n",
        needle="len(items)",
        bug_why="The print counts the slots instead of adding the readings.",
        starter=f"items = [{left}, {right}]\nlabel = ___\nprint(label)\n",
        solution=f"items = [{left}, {right}]\nlabel = sum(items)\nprint(label)\n",
        reveal="label = sum(items)",
        write_why="The stored total is what gets printed.",
        example="sum(items)",
    )


def list_index(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    body = f"items = [{right}, {left}, {left + 3}]\n"
    return _finish(
        "list_index",
        action="shows the reading in the chosen slot",
        why="items[1] is the second slot.",
        mcq=["items[1]", "len(items)", "items + 1", "sum(items)"],
        predict=body + "print(items[1])\n",
        predict2=body + "print(items[2])\n",
        order=["print", "(", "items", "[", "1", "]", ")"],
        distractor="len",
        order_why="print(items[1]) shows the second slot.",
        fill_code="shown = items[1] ___ 2\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus adds two to the chosen slot.",
        bug=body + "print(items[9])\n",
        needle="items[9]",
        bug_why="The slot is past the end of the list.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + "label = items[1]\nprint(label)\n",
        reveal="label = items[1]",
        write_why="The chosen slot is what gets printed.",
        example="items[1]",
    )


def loop_enum(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    def program(values: str) -> str:
        return (
            f"items = {values}\n"
            "total = 0\n"
            "for index, value in enumerate(items):\n"
            "    total = total + index + value\n"
            "print(total)\n"
        )
    return _finish(
        "loop_enum",
        action="adds each slot number and its reading",
        why="enumerate pairs the slot number with the reading.",
        mcq=["enumerate(items)", "items[0]", "len(items)", "items + 1"],
        predict=program(f"[{left}, {right}]"),
        predict2=program(f"[{left}, {right}, 5]"),
        order=["for", "index,", "value", "in", "enumerate(items):", "pass"],
        distractor="if",
        order_why="for index, value in enumerate(items): walks the pairs.",
        fill_code="total = total ___ value\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus adds the reading.",
        bug=(
            f"items = [{left}, {right}]\n"
            "total = 0\n"
            "for value in items:\n"
            "    total = total + value\n"
            "print(total)\n"
        ),
        needle="for value in items",
        bug_why="The walk drops the slot numbers.",
        starter=(
            f"items = [{left}, {right}]\n"
            "total = 0\n"
            "for index, value in enumerate(items):\n"
            "    total = total + index + value\n"
            "label = ___\nprint(label)\n"
        ),
        solution=(
            f"items = [{left}, {right}]\n"
            "total = 0\n"
            "for index, value in enumerate(items):\n"
            "    total = total + index + value\n"
            "label = total\nprint(label)\n"
        ),
        reveal="label = total",
        write_why="The paired total is what gets printed.",
        example="enumerate(items)",
    )


def loop_sum(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    def program(count: int) -> str:
        return (
            "total = 0\n"
            f"for step in range({count}):\n"
            f"    total = total + {left}\n"
            "print(total)\n"
        )
    return _finish(
        "loop_sum",
        action="adds the reading once for every step",
        why="The loop adds the reading on each step.",
        mcq=["for step in range(count)", "if step == count", "step = count", "print(step)"],
        predict=program(4), predict2=program(3),
        order=["for", "step", "in", "steps:", "pass"],
        distractor="if",
        order_why="for step in steps: walks the steps.",
        fill_code="total = total ___ left\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus adds the reading for this step.",
        bug=(
            "total = 0\n"
            "for step in range(4):\n"
            f"    total = total - {left}\n"
            "print(total)\n"
        ),
        needle=f"total - {left}",
        bug_why="The loop subtracts the reading.",
        starter=(
            "total = 0\n"
            "for step in range(4):\n"
            f"    total = total + {left}\n"
            "label = ___\nprint(label)\n"
        ),
        solution=(
            "total = 0\n"
            "for step in range(4):\n"
            f"    total = total + {left}\n"
            "label = total\nprint(label)\n"
        ),
        reveal="label = total",
        write_why="The step total is what gets printed.",
        example="for step in range(count)",
    )


def loop_comp(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    def program(extra: str) -> str:
        return (
            f"prices = [{left}, {left + 5}{extra}]\n"
            "discounted = [price - 2 for price in prices]\n"
            "print(sum(discounted))\n"
        )
    return _finish(
        "loop_comp",
        action="subtracts two from each price and adds the results",
        why="price - 2 is the discounted price.",
        mcq=["price - 2", "price + 2", "price == 2", "print(price)"],
        predict=program(""), predict2=program(f", {left + 9}"),
        order=["saved", "=", "price", "-", "2"],
        distractor="+",
        order_why="saved = price - 2 stores the discount.",
        fill_code="saved = price ___ 2\n", fill_answer="-", fill_options=_opts("-"),
        fill_why="Minus takes two off the price.",
        bug=(
            f"prices = [{left}, {left + 5}]\n"
            "discounted = [price + 2 for price in prices]\n"
            "print(sum(discounted))\n"
        ),
        needle="price + 2",
        bug_why="The comprehension adds two instead of subtracting.",
        starter=(
            f"prices = [{left}, {left + 5}]\n"
            "discounted = [price - 2 for price in prices]\n"
            "label = ___\nprint(label)\n"
        ),
        solution=(
            f"prices = [{left}, {left + 5}]\n"
            "discounted = [price - 2 for price in prices]\n"
            "label = sum(discounted)\nprint(label)\n"
        ),
        reveal="label = sum(discounted)",
        write_why="The discounted total is what gets printed.",
        example="price - 2",
    )


def str_case(word: str, number: int, twist: int) -> dict:
    predict = f"text = '{word}' + 'ing'\nprint(text.upper())\n"
    predict2 = f"text = '{word}' + 'ed'\nprint(text.upper())\n"
    return _finish(
        "str_case",
        action="shows the reading in uppercase",
        why="upper() changes every letter to uppercase.",
        mcq=["text.upper()", "text.lower()", "len(text)", "text == text"],
        predict=predict, predict2=predict2,
        order=["shouted", "=", "text.upper", "(", ")"],
        distractor="lower",
        order_why="shouted = text.upper() stores the uppercase reading.",
        fill_code="shown = size ___ 1\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus adds one to the size.",
        bug=f"text = '{word}' + 'ing'\nprint(text.lower())\n",
        needle=".lower()",
        bug_why="The print uses lowercase.",
        starter=f"text = '{word}' + 'ing'\nlabel = ___\nprint(label)\n",
        solution=f"text = '{word}' + 'ing'\nlabel = text.upper()\nprint(label)\n",
        reveal="label = text.upper()",
        write_why="The uppercase reading is what gets printed.",
        example="text.upper()",
    )


def str_replace(word: str, number: int, twist: int) -> dict:
    predict = f"text = '{word}' + '!'\nprint(text.replace('!', '?'))\n"
    predict2 = f"text = '{word}' + '!'\nprint(text.replace('!', '.'))\n"
    return _finish(
        "str_replace",
        action="swaps the mark at the end of the reading",
        why="replace swaps one mark for another.",
        mcq=["text.replace('!', '?')", "text.upper()", "len(text)", "text == '!'"],
        predict=predict, predict2=predict2,
        order=["clean", "=", "text.replace", "(", "'!'", ",", "'?'", ")"],
        distractor="upper",
        order_why="text.replace('!', '?') swaps the mark.",
        fill_code="clean = text.replace('!', ___)\n", fill_answer="'?'",
        fill_options=["'?'", "'!'", "''", "'x'"],
        fill_why="The question mark is the replacement.",
        bug=f"text = '{word}' + '!'\nprint(text.replace('x', '?'))\n",
        needle="replace('x'",
        bug_why="The search mark is not in the reading, so nothing changes.",
        starter=f"text = '{word}' + '!'\nlabel = ___\nprint(label)\n",
        solution=f"text = '{word}' + '!'\nlabel = text.replace('!', '?')\nprint(label)\n",
        reveal="label = text.replace('!', '?')",
        write_why="The swapped reading is what gets printed.",
        example="text.replace('!', '?')",
    )


def str_chain(word: str, number: int, twist: int) -> dict:
    predict = f"text = '  ' + '{word}' + '!'\nprint(text.strip().replace('!', '?').upper())\n"
    predict2 = f"text = '  ' + '{word}' + '!'\nprint(text.strip().replace('!', '.').upper())\n"
    return _finish(
        "str_chain",
        action="trims, swaps the mark, then shows uppercase",
        why="The methods run from left to right.",
        mcq=["text.strip().replace('!', '?').upper()", "text.upper().strip()", "len(text)", "text == text"],
        predict=predict, predict2=predict2,
        order=["clean", "=", "text.strip", "(", ")"],
        distractor="upper",
        order_why="text.strip() removes the outer spaces first.",
        fill_code="shown = size ___ 1\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus adds one to the size.",
        bug=f"text = '  ' + '{word}' + '!'\nprint(text.replace('!', '?').upper())\n",
        needle="text.replace",
        bug_why="The spaces are never trimmed.",
        starter=f"text = '  ' + '{word}' + '!'\nlabel = ___\nprint(label)\n",
        solution=f"text = '  ' + '{word}' + '!'\nlabel = text.strip().replace('!', '?').upper()\nprint(label)\n",
        reveal="label = text.strip().replace('!', '?').upper()",
        write_why="The cleaned reading is what gets printed.",
        example="text.strip().replace('!', '?').upper()",
    )


def str_strip(word: str, number: int, twist: int) -> dict:
    predict = f"text = '  ' + '{word}'\nprint(text.strip())\n"
    predict2 = f"text = '  ' + '{word}' + 's'\nprint(text.strip())\n"
    return _finish(
        "str_strip",
        action="shows the reading without the outer spaces",
        why="strip() removes spaces from both ends.",
        mcq=["text.strip()", "text.upper()", "len(text)", "text == text"],
        predict=predict, predict2=predict2,
        order=["clean", "=", "text.strip", "(", ")"],
        distractor="upper",
        order_why="clean = text.strip() stores the trimmed reading.",
        fill_code="shown = size ___ 1\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus adds one to the size.",
        bug=f"text = '  ' + '{word}'\nprint(text.upper())\n",
        needle=".upper()",
        bug_why="The print changes case and leaves the spaces.",
        starter=f"text = '  ' + '{word}'\nlabel = ___\nprint(label)\n",
        solution=f"text = '  ' + '{word}'\nlabel = text.strip()\nprint(label)\n",
        reveal="label = text.strip()",
        write_why="The trimmed reading is what gets printed.",
        example="text.strip()",
    )


def str_end(word: str, number: int, twist: int) -> dict:
    predict = f"text = '{word}' + 'ing'\nprint(text if text.endswith('ing') else text + '?')\n"
    predict2 = f"text = '{word}' + 'ing'\nprint(text if text.endswith('xyz') else text + '?')\n"
    return _finish(
        "str_end",
        action="keeps the reading when it ends with the mark",
        why="endswith asks whether the mark is at the end.",
        mcq=["text.endswith('ing')", "text.startswith('ing')", "len(text)", "text == text"],
        predict=predict, predict2=predict2,
        order=["flag", "=", "text.endswith", "(", "'ing'", ")"],
        distractor="upper",
        order_why="text.endswith('ing') checks the ending.",
        fill_code="shown = size ___ 1\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus adds one to the size.",
        bug=f"text = '{word}' + 'ing'\nprint(text if text.startswith('ing') else text + '?')\n",
        needle="startswith",
        bug_why="The check looks at the start instead of the end.",
        starter=f"text = '{word}' + 'ing'\nlabel = ___\nprint(label)\n",
        solution=f"text = '{word}' + 'ing'\nlabel = text if text.endswith('ing') else text + '?'\nprint(label)\n",
        reveal="label = text if text.endswith('ing') else text + '?'",
        write_why="The ending check is what gets printed.",
        example="text.endswith('ing')",
    )


def str_concat(word: str, number: int, twist: int) -> dict:
    mark = "!" if twist % 2 == 0 else "#"
    other = "?" if mark == "!" else "*"
    predict = f"left = '{word}'\nright = '{mark}'\nprint(left + right)\n"
    predict2 = f"left = '{word}'\nright = '{other}'\nprint(left + right)\n"
    return _finish(
        "str_concat",
        action="joins the reading and the mark",
        why="left + right joins the two pieces.",
        mcq=["left + right", "left - right", "len(left)", "left == right"],
        predict=predict, predict2=predict2,
        order=["joined", "=", "left", "+", "right"],
        distractor="-",
        order_why="joined = left + right joins the text.",
        fill_code="joined = left ___ right\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus joins the two pieces.",
        bug=f"left = '{word}'\nright = '{mark}'\nprint(left)\n",
        needle="print(left)",
        bug_why="The mark is never joined.",
        starter=f"left = '{word}'\nright = '{mark}'\nlabel = ___\nprint(label)\n",
        solution=f"left = '{word}'\nright = '{mark}'\nlabel = left + right\nprint(label)\n",
        reveal="label = left + right",
        write_why="The joined text is what gets printed.",
        example="left + right",
    )


def str_slice(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = f"text = '{word}' + 'stone'\n"
    return _finish(
        "str_slice",
        action="shows the opening letters of the reading",
        why="text[:3] keeps the first three letters.",
        mcq=["text[:3]", "text[0]", "len(text)", "text + text"],
        predict=body + "print(text[:3])\n",
        predict2=body + "print(text[:4])\n",
        order=["chunk", "=", "text", "[", ":3", "]"],
        distractor="len",
        order_why="chunk = text[:3] keeps the opening letters.",
        fill_code="chunk = text[___3]\n", fill_answer=":", fill_options=[":", ",", "+", "-"],
        fill_why="The colon starts the slice from the beginning.",
        bug=body + "print(text[3:])\n",
        needle="text[3:]",
        bug_why="The slice drops the opening letters.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + "label = text[:3]\nprint(label)\n",
        reveal="label = text[:3]",
        write_why="The opening letters are what get printed.",
        example="text[:3]",
    )


def str_join(word: str, number: int, twist: int) -> dict:
    predict = f"parts = ['{word}', 'id']\nprint('-'.join(parts))\n"
    predict2 = f"parts = ['{word}', 'id']\nprint('/'.join(parts))\n"
    return _finish(
        "str_join",
        action="joins the parts with the separator",
        why="join places the separator between the parts.",
        mcq=["'-'.join(parts)", "parts[0]", "len(parts)", "parts + parts"],
        predict=predict, predict2=predict2,
        order=["joined", "=", "'-'", ".", "join", "(", "parts", ")"],
        distractor="split",
        order_why="'-'.join(parts) places the dash between the parts.",
        fill_code="joined = left ___ right\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus is the other way to join two pieces.",
        bug=f"parts = ['{word}', 'id']\nprint(''.join(parts))\n",
        needle="''.join",
        bug_why="The separator is empty, so the parts are stuck together.",
        starter=f"parts = ['{word}', 'id']\nlabel = ___\nprint(label)\n",
        solution=f"parts = ['{word}', 'id']\nlabel = '-'.join(parts)\nprint(label)\n",
        reveal="label = '-'.join(parts)",
        write_why="The joined parts are what get printed.",
        example="'-'.join(parts)",
    )


def str_index(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = f"text = '{word}' + '!'\n"
    return _finish(
        "str_index",
        action="adds the base reading to the slot where the mark sits",
        why="index finds the slot of the mark.",
        mcq=["text.index('!')", "text[0]", "len(text)", "text + '!'"],
        predict=body + f"print(text.index('!') + {left})\n",
        predict2=body + f"print(text.index('{word[0]}') + {left})\n",
        order=["slot", "=", "text.index", "(", "'!'", ")"],
        distractor="len",
        order_why="text.index('!') finds the mark.",
        fill_code="shown = slot ___ left\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus adds the base reading to the slot.",
        bug=body + f"print(text.index('?') + {left})\n",
        needle="index('?')",
        bug_why="The mark being sought is not in the reading.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + f"label = text.index('!') + {left}\nprint(label)\n",
        reveal=f"label = text.index('!') + {left}",
        write_why="The slot plus the base reading is what gets printed.",
        example="text.index('!')",
    )


def tuple_index(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    body = f"pair = ({left}, {right})\n"
    return _finish(
        "tuple_index",
        action="shows the chosen slot of the pair",
        why="pair[0] is the first slot.",
        mcq=["pair[0]", "len(pair)", "pair + pair", "sum(pair)"],
        predict=body + "print(pair[0] + 3)\n",
        predict2=body + "print(pair[1] + 3)\n",
        order=["print", "(", "pair", "[", "0", "]", ")"],
        distractor="len",
        order_why="print(pair[0]) shows the first slot.",
        fill_code="shown = pair[0] ___ 3\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus adds three to the first slot.",
        bug=body + "print(pair[9])\n",
        needle="pair[9]",
        bug_why="The slot is past the end of the pair.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + "label = pair[0] + 3\nprint(label)\n",
        reveal="label = pair[0] + 3",
        write_why="The first slot plus three is what gets printed.",
        example="pair[0]",
    )


def tuple_unpack(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    predict = f"pair = ({left}, {right})\nfirst, second = pair\nprint(first + second)\n"
    predict2 = f"pair = ({left}, {right + 4})\nfirst, second = pair\nprint(first + second)\n"
    return _finish(
        "tuple_unpack",
        action="adds the two names unpacked from the pair",
        why="first, second = pair stores each slot in a name.",
        mcq=["first, second = pair", "pair[0]", "len(pair)", "pair + pair"],
        predict=predict, predict2=predict2,
        order=["first", ",", "second", "=", "pair"],
        distractor="==",
        order_why="first, second = pair unpacks the pair.",
        fill_code="print(first ___ second)\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus adds the unpacked readings.",
        bug=f"pair = ({left}, {right})\nfirst = pair\nprint(first)\n",
        needle="first = pair",
        bug_why="The whole pair is stored in one name.",
        starter=f"pair = ({left}, {right})\nfirst, second = pair\nlabel = ___\nprint(label)\n",
        solution=f"pair = ({left}, {right})\nfirst, second = pair\nlabel = first + second\nprint(label)\n",
        reveal="label = first + second",
        write_why="The unpacked sum is what gets printed.",
        example="first, second = pair",
    )


def tuple_slice(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    body = f"row = ({left}, {right}, {left + 4}, 9)\n"
    return _finish(
        "tuple_slice",
        action="adds the readings in the chosen slice of the row",
        why="row[:2] keeps the first two slots.",
        mcq=["row[:2]", "row[0]", "len(row)", "row + row"],
        predict=body + "print(sum(row[:2]))\n",
        predict2=body + "print(sum(row[:3]))\n",
        order=["chunk", "=", "row", "[", ":2", "]"],
        distractor="len",
        order_why="chunk = row[:2] keeps the first two slots.",
        fill_code="chunk = row[___2]\n", fill_answer=":", fill_options=[":", ",", "+", "-"],
        fill_why="The colon starts the slice from the beginning.",
        bug=body + "print(sum(row[2:4]))\n",
        needle="row[2:4]",
        bug_why="The slice starts too late.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + "label = sum(row[:2])\nprint(label)\n",
        reveal="label = sum(row[:2])",
        write_why="The slice total is what gets printed.",
        example="row[:2]",
    )


def assert_ok(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = (
        "def check(value):\n"
        "    assert value > 0\n"
        "    return value\n"
    )
    return _finish(
        "assert_ok",
        action="hands the reading back after the check passes",
        why="assert value > 0 stops the function when the reading is not positive.",
        mcq=["assert value > 0", "value == 0", "print(value)", "pass"],
        predict=body + f"print(check({left}) + 3)\n",
        predict2=body + f"print(check({left + 2}) + 3)\n",
        order=["assert", "value", ">", "0"],
        distractor="==",
        order_why="assert value > 0 is the check.",
        fill_code="assert value ___ 0\n", fill_answer=">", fill_options=_opts(">"),
        fill_why="The check requires a positive reading.",
        bug=body.replace("value > 0", "value < 0") + f"print(check({left}))\n",
        needle="value < 0",
        bug_why="The check rejects positive readings.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + f"label = check({left})\nprint(label)\n",
        reveal=f"label = check({left})",
        write_why="The checked reading is what gets printed.",
        example="assert value > 0",
    )


def assert_cases(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = (
        "def check(value, expected):\n"
        "    assert value == expected\n"
        "    return value\n"
    )
    return _finish(
        "assert_cases",
        action="hands the reading back when it matches the expected value",
        why="assert value == expected checks one case.",
        mcq=["assert value == expected", "value = expected", "print(value)", "pass"],
        predict=body + f"print(check({left}, {left}) + 2)\n",
        predict2=body + f"print(check({left}, {left}) + 5)\n",
        order=["assert", "value", "==", "expected"],
        distractor="=",
        order_why="assert value == expected checks the case.",
        fill_code="return value ___ 2\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus adds two after the check.",
        bug=body.replace("value == expected", "value != expected") + f"print(check({left}, {left}))\n",
        needle="value != expected",
        bug_why="The check rejects a match.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + f"label = check({left}, {left})\nprint(label)\n",
        reveal=f"label = check({left}, {left})",
        write_why="The matching reading is what gets printed.",
        example="assert value == expected",
    )


def fixture(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    def program(bump: int) -> str:
        return (
            "def setup():\n"
            f"    return {left}\n"
            "def teardown(value):\n"
            f"    return value + {bump}\n"
            "print(teardown(setup()))\n"
        )
    return _finish(
        "fixture",
        action="shows the setup reading after teardown adjusts it",
        why="setup provides the reading and teardown adjusts it.",
        mcq=["teardown(setup())", "setup == teardown", "print(setup)", "pass"],
        predict=program(1), predict2=program(4),
        order=["base", "=", "setup", "(", ")"],
        distractor="==",
        order_why="base = setup() stores the prepared reading.",
        fill_code="return value ___ 1\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus adjusts the prepared reading.",
        bug=program(1).replace("return value + 1", "return value - 1"),
        needle="value - 1",
        bug_why="Teardown subtracts instead of adjusting upward.",
        starter=program(1).replace("print(teardown(setup()))\n", "label = ___\nprint(label)\n"),
        solution=program(1).replace("print(teardown(setup()))\n", "label = teardown(setup())\nprint(label)\n"),
        reveal="label = teardown(setup())",
        write_why="The adjusted reading is what gets printed.",
        example="teardown(setup())",
    )


def approx(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = (
        "def close(value, target):\n"
        "    gap = value - target\n"
        "    if gap < 0:\n"
        "        gap = -gap\n"
        "    return value if gap < 3 else value + 15\n"
    )
    return _finish(
        "approx",
        action="keeps the reading when it sits close to the target",
        why="A small absolute gap counts as close.",
        mcq=["gap < 3", "gap == 3", "print(gap)", "pass"],
        predict=body + f"print(close({left}, {left + 1}))\n",
        predict2=body + f"print(close({left}, {left + 10}))\n",
        order=["gap", "=", "value", "-", "target"],
        distractor="+",
        order_why="gap = value - target is the distance.",
        fill_code="if gap ___ 3:\n    label = 1\n", fill_answer="<", fill_options=_opts("<"),
        fill_why="The tolerance keeps a gap below three.",
        bug=body.replace("gap < 3", "gap > 3") + f"print(close({left}, {left + 1}))\n",
        needle="gap > 3",
        bug_why="The tolerance is reversed.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + f"label = close({left}, {left + 1})\nprint(label)\n",
        reveal=f"label = close({left}, {left + 1})",
        write_why="The close reading is what gets printed.",
        example="gap < 3",
    )


def assert_raises(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    def program(raises: bool) -> str:
        body = "    raise RuntimeError('stop')\n" if raises else "    return None\n"
        return (
            "def fails():\n"
            f"{body}"
            "try:\n"
            "    fails()\n"
            f"    print({left + 6})\n"
            "except RuntimeError:\n"
            f"    print({left})\n"
        )
    return _finish(
        "assert_raises",
        action="shows the caught reading when the call fails",
        why="except RuntimeError runs when the call raises.",
        mcq=["raise RuntimeError('stop')", "return None", "print(stop)", "pass"],
        predict=program(True), predict2=program(False),
        order=["raise", "RuntimeError", "(", "'stop'", ")"],
        distractor="return",
        order_why="raise RuntimeError('stop') is the expected failure.",
        fill_code=f"shown = {left} ___ 6\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus builds the reading used when the call succeeds.",
        bug=program(True).replace("raise RuntimeError('stop')", "raise ValueError('stop')"),
        needle="ValueError",
        bug_why="The call raises a different error than the handler catches.",
        starter=(
            "def fails():\n"
            "    raise RuntimeError('stop')\n"
            "try:\n"
            "    fails()\n"
            "    label = 0\n"
            "except RuntimeError:\n"
            "    label = ___\n"
            "print(label)\n"
        ),
        solution=(
            "def fails():\n"
            "    raise RuntimeError('stop')\n"
            "try:\n"
            "    fails()\n"
            "    label = 0\n"
            "except RuntimeError:\n"
            f"    label = {left}\n"
            "print(label)\n"
        ),
        reveal=f"label = {left}",
        write_why="The caught reading is what gets printed.",
        example="raise RuntimeError('stop')",
    )


def typed_fn(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = (
        "def score(value: int) -> int:\n"
        "    return value + 2\n"
    )
    return _finish(
        "typed_fn",
        action="adds two and hands back an integer",
        why="The annotation says the argument and the result are integers.",
        mcq=["def score(value: int) -> int", "value == int", "print(value)", "pass"],
        predict=body + f"print(score({left}))\n",
        predict2=body + f"print(score({left + 3}))\n",
        order=["def", "score(value:", "int)", "->", "int:", "return", "value"],
        distractor="str",
        order_why="The annotation marks an integer argument and result.",
        fill_code="return value ___ 2\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus adds two.",
        bug=body.replace("value + 2", "value - 2") + f"print(score({left}))\n",
        needle="value - 2",
        bug_why="The function subtracts two.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + f"label = score({left})\nprint(label)\n",
        reveal=f"label = score({left})",
        write_why="The annotated result is what gets printed.",
        example="def score(value: int) -> int",
    )


def dataclass_basic(word: str, number: int, twist: int) -> dict:
    left, right = _n(number, twist)
    body = (
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class Point:\n"
        "    x: int\n"
        "    y: int\n"
    )
    return _finish(
        "dataclass_basic",
        action="shows one field of the new point",
        why="Point(x, y) stores both fields.",
        mcq=["Point(x, y).x", "Point == x", "print(Point)", "pass"],
        predict=body + f"print(Point({left}, {right}).x + 1)\n",
        predict2=body + f"print(Point({left}, {right}).y + 1)\n",
        order=["point", "=", "Point", "(", "left", ",", "right", ")"],
        distractor="==",
        order_why="point = Point(left, right) builds the point.",
        fill_code="shown = point.x ___ 1\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus adds one to the field.",
        bug=body + f"print(Point({left}, {right}).x - 1)\n",
        needle=".x - 1",
        bug_why="The print subtracts one from the field.",
        starter=body + f"point = Point({left}, {right})\nlabel = ___\nprint(label)\n",
        solution=body + f"point = Point({left}, {right})\nlabel = point.x + 1\nprint(label)\n",
        reveal="label = point.x + 1",
        write_why="The field plus one is what gets printed.",
        example="Point(x, y).x",
    )


def frozen(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = (
        "from dataclasses import dataclass, replace\n"
        "@dataclass(frozen=True)\n"
        "class Config:\n"
        "    port: int\n"
        "    def moved(self):\n"
        "        return replace(self, port=self.port + 1)\n"
    )
    return _finish(
        "frozen",
        action="shows the port on a new config",
        why="replace builds a new frozen config instead of editing the old one.",
        mcq=["replace(self, port=self.port + 1)", "self.port = 1", "print(self)", "pass"],
        predict=body + f"print(Config({left}).moved().port)\n",
        predict2=body + f"print(Config({left + 3}).moved().port)\n",
        order=["updated", "=", "replace", "(", "self", ",", "port=1", ")"],
        distractor="==",
        order_why="replace builds a new config.",
        fill_code="return replace(self, port=self.port ___ 1)\n",
        fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus moves the port up by one.",
        bug=body.replace("self.port + 1", "self.port - 1") + f"print(Config({left}).moved().port)\n",
        needle="self.port - 1",
        bug_why="The new config moves the port down.",
        starter=body + "label = ___\nprint(label)\n",
        solution=body + f"label = Config({left}).moved().port\nprint(label)\n",
        reveal=f"label = Config({left}).moved().port",
        write_why="The new port is what gets printed.",
        example="replace(self, port=self.port + 1)",
    )


def optional_fn(word: str, number: int, twist: int) -> dict:
    left, _right = _n(number, twist)
    body = (
        "def label(value: int | None = None) -> int:\n"
        "    if value is None:\n"
        f"        return {left}\n"
        "    return value\n"
    )
    return _finish(
        "optional_fn",
        action="uses the fallback when the argument is missing",
        why="None selects the fallback integer.",
        mcq=["value: int | None", "value == None", "print(value)", "value = None"],
        predict=body + "print(label(None))\n",
        predict2=body + f"print(label({left + 4}))\n",
        order=["def", "label(value:", "int)", "->", "int:", "return", "value"],
        distractor="str",
        order_why="The annotation allows an integer result.",
        fill_code=f"shown = {left} ___ 4\n", fill_answer="+", fill_options=_opts("+"),
        fill_why="Plus builds the other reading.",
        bug=body.replace("value is None", "value == 1") + "print(label(None))\n",
        needle="value == 1",
        bug_why="The fallback check does not recognize a missing argument.",
        starter=body + "label_out = ___\nprint(label_out)\n",
        solution=body + "label_out = label(None)\nprint(label_out)\n",
        reveal="label_out = label(None)",
        write_why="The fallback integer is what gets printed.",
        example="value: int | None",
    )


PYTHON_PLAN: dict[str, tuple[str, int]] = {
    "py-aiml-01": ("dot", 0),
    "py-automation-01": ("filter_list", 0),
    "py-backend-01": ("dict_get", 0),
    "classes-step-1": ("class_init", 0),
    "classes-step-2": ("class_method", 0),
    "classes-01": ("class_init", 1),
    "classes-practice-1": ("class_deposit", 0),
    "classes-checkpoint": ("class_init", 2),
    "comparisons-step-1": ("compare_ge", 0),
    "comparisons-step-2": ("compare_chain", 0),
    "comparisons-01": ("compare_eq", 0),
    "comparisons-practice-1": ("compare_ge", 1),
    "comparisons-checkpoint": ("compare_ne", 0),
    "comprehensions-step-1": ("comp_list", 0),
    "comprehensions-step-2": ("comp_dict", 0),
    "comprehensions-01": ("comp_flat", 0),
    "comprehensions-practice-1": ("filter_list", 1),
    "comprehensions-checkpoint": ("comp_set", 0),
    "conditionals-01": ("branch", 0),
    "conditionals-practice-1": ("branch", 1),
    "conditionals-checkpoint": ("branch", 2),
    "context-managers-step-1": ("context", 0),
    "context-managers-step-2": ("context_cm", 0),
    "context-managers-01": ("context_time", 0),
    "context-managers-practice-1": ("context_suppress", 0),
    "context-managers-checkpoint": ("context_lock", 0),
    "decorators-step-1": ("deco_wrap", 0),
    "decorators-step-2": ("deco_wrap", 1),
    "decorators-01": ("deco_memo", 0),
    "decorators-practice-1": ("deco_count", 0),
    "decorators-checkpoint": ("deco_guard", 0),
    "dictionaries-step-1": ("dict_get", 1),
    "dictionaries-step-2": ("dict_items", 0),
    "dictionaries-01": ("dict_get", 2),
    "dictionaries-practice-1": ("dict_count", 0),
    "dictionaries-checkpoint": ("dict_items", 1),
    "exceptions-step-1": ("exc_div", 0),
    "exceptions-step-2": ("exc_custom", 0),
    "exceptions-01": ("exc_retry", 0),
    "exceptions-practice-1": ("exc_parse", 0),
    "exceptions-checkpoint": ("exc_translate", 0),
    "functions-step-2": ("func_add", 0),
    "functions-01": ("func_const", 0),
    "functions-practice-1": ("func_scale", 0),
    "functions-checkpoint": ("func_doc", 0),
    "generators-step-1": ("gen_yield", 0),
    "generators-step-2": ("gen_take", 0),
    "generators-01": ("gen_avg", 0),
    "generators-practice-1": ("gen_chunk", 0),
    "generators-checkpoint": ("gen_filter", 0),
    "list-methods-step-1": ("list_append", 0),
    "list-methods-step-2": ("list_sort", 0),
    "list-methods-01": ("list_insert", 0),
    "list-methods-practice-1": ("list_pop", 0),
    "list-methods-checkpoint": ("list_count", 0),
    "lists-step-1": ("list_len", 0),
    "lists-step-2": ("list_concat", 0),
    "lists-01": ("list_slice", 0),
    "lists-practice-1": ("list_sum", 0),
    "lists-checkpoint": ("list_index", 0),
    "loops-step-2": ("loop_enum", 0),
    "loops-01": ("loop_sum", 0),
    "loops-practice-1": ("loop_comp", 0),
    "loops-checkpoint": ("loop_filter", 0),
    "pytest-testing-step-1": ("assert_ok", 0),
    "pytest-testing-step-2": ("assert_cases", 0),
    "pytest-testing-01": ("fixture", 0),
    "pytest-testing-practice-1": ("approx", 0),
    "pytest-testing-checkpoint": ("assert_raises", 0),
    "string-methods-step-1": ("str_case", 0),
    "string-methods-step-2": ("str_replace", 0),
    "string-methods-01": ("str_chain", 0),
    "string-methods-practice-1": ("str_strip", 0),
    "string-methods-checkpoint": ("str_end", 0),
    "strings-step-1": ("str_concat", 0),
    "strings-step-2": ("str_slice", 0),
    "strings-01": ("str_concat", 1),
    "strings-practice-1": ("str_join", 0),
    "strings-checkpoint": ("str_index", 0),
    "tuples-step-1": ("tuple_index", 0),
    "tuples-step-2": ("tuple_unpack", 0),
    "tuples-01": ("tuple_slice", 0),
    "tuples-practice-1": ("tuple_unpack", 1),
    "tuples-checkpoint": ("tuple_index", 1),
    "type-hints-dataclasses-step-1": ("typed_fn", 0),
    "type-hints-dataclasses-step-2": ("dataclass_basic", 0),
    "type-hints-dataclasses-01": ("frozen", 0),
    "type-hints-dataclasses-practice-1": ("optional_fn", 0),
    "type-hints-dataclasses-checkpoint": ("dataclass_basic", 1),
}


def python_recipe(lesson_id: str, word: str, number: int) -> dict:
    """Return the executable pack for one Python lesson id."""
    kind, twist = PYTHON_PLAN[lesson_id]
    return globals()[kind](word, number, twist)
