"""Concept-specific micro packs for every legacy lesson outside Python.

Each pack is original code for that lesson's concept. Predictions are real
programs, ordering and fill fragments parse, and the write screen leaves one
blank. ``pack_for`` is what the shipper installs.
"""

from __future__ import annotations

WORDS = (
    "amber birch cedar delta ember flint grove hazel ivory juniper kelp linen maple "
    "nectar olive pebble quartz ridge sage thyme umber violet willow yarrow zircon"
).split()

CATALOG: dict[str, dict] = {}


def _sub(value, number: int, word: str, other: str):
    if isinstance(value, str):
        return (
            value.replace("{m}", str(number + 1))
            .replace("{p}", str(number + 3))
            .replace("{n}", str(number))
            .replace("{w}", word)
            .replace("{o}", other)
        )
    if isinstance(value, list):
        return [_sub(item, number, word, other) for item in value]
    return value


def wrap(lang: str, lines: list[str]) -> str:
    if lang == "java":
        body = "".join(f"        {line}\n" for line in lines)
        return (
            "public class Solution {\n"
            "    public static void main(String[] args) {\n"
            f"{body}"
            "    }\n"
            "}\n"
        )
    body = "".join(f"    {line}\n" for line in lines)
    return (
        "#include <iostream>\n"
        "#include <string>\n"
        "#include <vector>\n"
        "#include <algorithm>\n"
        "#include <memory>\n"
        "int main() {\n"
        f"{body}"
        "    return 0;\n"
        "}\n"
    )


def _line_of(code: str, needle: str) -> str:
    for index, line in enumerate(code.splitlines(), 1):
        if needle in line:
            return str(index)
    raise SystemExit(f"needle {needle!r} missing from bug code")


def _add(record: dict) -> None:
    lid = record["id"]
    if lid in CATALOG:
        raise SystemExit(f"duplicate pack {lid}")
    CATALOG[lid] = record


def py(
    lid, action, setup, expr, setup2, expr2, order, distractor, fill, fans, fopts,
    bug, needle, bug_why, mcq, why, example, reveal=None,
):
    reveal = expr if reveal is None else reveal
    _add({
        "id": lid, "lang": "py", "action": action, "why": why, "example": example,
        "mcq": mcq, "predict": f"{setup}print({expr})\n", "predict2": f"{setup2}print({expr2})\n",
        "order": order, "distractor": distractor, "order_why": why,
        "fill_code": fill, "fill_answer": fans, "fill_options": fopts, "fill_why": why,
        "bug": bug, "needle": needle, "bug_why": bug_why,
        "starter": f"{setup}label = ___\nprint(label)\n",
        "solution": f"{setup}label = {reveal}\nprint(label)\n",
        "reveal": f"label = {reveal}",
        "write_why": f"The printed value is the result after this step {action}.",
    })


def js(
    lid, action, setup, expr, setup2, expr2, order, distractor, fill, fans, fopts,
    bug, needle, bug_why, mcq, why, example, reveal=None, lang="js", logged=True,
    starter_code=None, solution_code=None,
):
    reveal = expr if reveal is None else reveal
    if logged:
        predict = f"{setup}console.log({expr});\n"
        predict2 = f"{setup2}console.log({expr2});\n"
        starter = f"{setup}const label = ___;\nconsole.log(label);\n"
        solution = f"{setup}const label = {reveal};\nconsole.log(label);\n"
    else:
        predict, predict2 = setup, setup2
        starter = starter_code or f"{setup}const label = ___;\nconsole.log(label);\n"
        solution = solution_code or f"{setup}const label = {reveal};\nconsole.log(label);\n"
    _add({
        "id": lid, "lang": lang, "action": action, "why": why, "example": example,
        "mcq": mcq,
        "predict": predict, "predict2": predict2,
        "order": order, "distractor": distractor, "order_why": why,
        "fill_code": fill, "fill_answer": fans, "fill_options": fopts, "fill_why": why,
        "bug": bug, "needle": needle, "bug_why": bug_why,
        "starter": starter, "solution": solution,
        "reveal": f"const label = {reveal};",
        "write_why": f"The printed value is the result after this step {action}.",
    })


def sql(
    lid, action, q1, q2, order, distractor, fill, fans, fopts, bug, needle,
    bug_why, starter, solution, reveal, mcq, why, example,
):
    _add({
        "id": lid, "lang": "sql", "action": action, "why": why, "example": example,
        "mcq": mcq, "predict": q1 if q1.endswith("\n") else q1 + "\n",
        "predict2": q2 if q2.endswith("\n") else q2 + "\n",
        "order": order, "distractor": distractor, "order_why": why,
        "fill_code": fill, "fill_answer": fans, "fill_options": fopts, "fill_why": why,
        "bug": bug, "needle": needle, "bug_why": bug_why,
        "starter": starter if starter.endswith("\n") else starter + "\n",
        "solution": solution if solution.endswith("\n") else solution + "\n",
        "reveal": reveal, "write_why": f"The query result is what this step {action}.",
    })


def native(
    lid, lang, action, lines1, lines2, order, distractor, fill, fans, fopts,
    bug_lines, needle, bug_why, setup, result_type, expr, mcq, why, example,
):
    printer = "System.out.println(label);" if lang == "java" else "std::cout << label << std::endl;"
    _add({
        "id": lid, "lang": lang, "action": action, "why": why, "example": example,
        "mcq": mcq, "predict": lines1, "predict2": lines2,
        "order": order, "distractor": distractor, "order_why": why,
        "fill_code": fill, "fill_answer": fans, "fill_options": fopts, "fill_why": why,
        "bug": bug_lines, "needle": needle, "bug_why": bug_why,
        "starter": [*setup, f"{result_type} label = ___;", printer],
        "solution": [*setup, f"{result_type} label = {expr};", printer],
        "reveal": f"{result_type} label = {expr};",
        "write_why": f"The printed value is the result after this step {action}.",
    })


def render(record: dict, number: int, word: str) -> dict:
    other = WORDS[(WORDS.index(word) + 4) % len(WORDS)]
    lang = record["lang"]

    def code(key: str) -> str:
        raw = _sub(record[key], number, word, other)
        if lang in {"java", "cpp"} and isinstance(record[key], list):
            return wrap(lang, raw)
        if not isinstance(raw, str):
            raise SystemExit(f"{record['id']} {key} is not text")
        return raw

    order = _sub(record["order"], number, word, other)
    mcq = _sub(record["mcq"], number, word, other)
    fill_options = _sub(record["fill_options"], number, word, other)
    fill_answer = _sub(record["fill_answer"], number, word, other)
    distractor = _sub(record["distractor"], number, word, other)
    if len(set(order)) != len(order):
        raise SystemExit(f"{record['id']} duplicate order chips: {order}")
    if distractor in order:
        raise SystemExit(f"{record['id']} distractor collides with order")
    if len(set(mcq)) != 4 or len(mcq) != 4:
        raise SystemExit(f"{record['id']} mcq needs 4 distinct options")
    if len(set(fill_options)) != 4 or fill_answer not in fill_options:
        raise SystemExit(f"{record['id']} fill options do not contain the answer")
    starter = code("starter")
    solution = code("solution")
    fill_code = code("fill_code")
    if starter.count("___") != 1 or "___" in solution or fill_code.count("___") != 1:
        raise SystemExit(f"{record['id']} blank count is wrong")
    blob = " ".join([
        starter, solution, fill_code, code("predict"), code("bug"),
        record["why"], record["action"], *mcq, *order,
    ])
    if "`" in blob:
        raise SystemExit(f"{record['id']} contains a backtick")
    bug = code("bug")
    needle = _sub(record["needle"], number, word, other)
    return {
        "action": _sub(record["action"], number, word, other),
        "mcq": mcq,
        "why": _sub(record["why"], number, word, other),
        "predict": code("predict"),
        "predict2": code("predict2"),
        "order": order,
        "distractor": distractor,
        "order_why": _sub(record["order_why"], number, word, other),
        "fill_code": fill_code,
        "fill_answer": fill_answer,
        "fill_options": fill_options,
        "fill_why": _sub(record["fill_why"], number, word, other),
        "bug": bug,
        "bug_line": _line_of(bug, needle),
        "bug_why": _sub(record["bug_why"], number, word, other),
        "starter": starter,
        "solution": solution,
        "reveal": _sub(record["reveal"], number, word, other),
        "write_why": _sub(record["write_why"], number, word, other),
        "example": _sub(record["example"], number, word, other),
    }


def pack_for(lesson_id: str, word: str, number: int) -> dict:
    record = CATALOG.get(lesson_id)
    if record is None:
        raise SystemExit(f"no concept pack for {lesson_id}")
    return render(record, number, word)


def _load() -> None:
    from backend.catalog_web import load as load_web
    from backend.catalog_native import load as load_native
    from backend.catalog_sql import load as load_sql
    from backend.catalog_py import load as load_py

    load_web()
    load_native()
    load_sql()
    load_py()


_load()
