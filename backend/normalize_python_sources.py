"""Normalize section numbers in Python lesson source names to match the actual
docs.python.org (3.14) headings verified via direct page fetches.

Applies the same string replacements to the curriculum JSON files and to
backend/patch_python_solutions.py so both stay in sync.
"""
import json
from pathlib import Path

ROOT = Path(".")
REPLACEMENTS = [
    ("3.1.5. Lists", "3.1.3. Lists"),
    ("3.2.2. Strings", "3.1.2. Text (Strings)"),
    ("4.1.1. String Methods", "String Methods"),
    ("4. Sequence Types", "Common Sequence Operations"),
    ("4.7. Defining Functions", "4.8. Defining Functions"),
    ("5.1 Data Structures — List Comprehensions", "5.1.3. List Comprehensions — Data Structures"),
    ("8.7.4 List Comprehensions", "5.1.3. List Comprehensions"),
    ("5.1. Sorting Methods — list.count / sorted()",
     "5.1. More on Lists (count) + Sorting — Data Structures"),
    ("5.1. Sorting Methods", "Sorting — sorted() (Built-in Functions)"),
    ("5.1. Lists — reference (Methods of Lists)",
     "Mutable Sequence Types — Methods of Lists (Standard Types)"),
    ("5. Tuples", "Tuple Types"),
    ("3. Built-in Functions — min() and max()", "min() and max() — Built-in Functions"),
    ("6. Comparisons — chained comparisons",
     "Comparisons — chained comparisons (Language Reference)"),
    ("6. Comparisons", "Comparisons — Expressions (Language Reference)"),
    ("3.3. Logic values — Boolean operations",
     "Boolean Operations — Language Reference"),
    ("4.2. for Statements / 5.1.4 enumerate() — Control Flow",
     "4.2. for Statements + 5.6. Looping Techniques (enumerate)"),
    ("4.2. for Statements / 7.2 Dictionaries — Mapping .get()",
     "Mapping Types — dict.get() (Standard Types)"),
    ("7.2 Dictionaries", "5.5. Dictionaries"),
]


def fix_text(text: str) -> str:
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    return text


def main() -> int:
    touched = 0
    for path in sorted(ROOT.glob("curriculum/python/modules/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for lesson in data["lessons"]:
            src = lesson.get("source") or {}
            name = src.get("name", "")
            if name:
                fixed = fix_text(name)
                if fixed != name:
                    src["name"] = fixed
                    changed = True
        if changed:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
            touched += 1
    patcher = ROOT / "backend/patch_python_solutions.py"
    if patcher.exists():
        patcher.write_text(fix_text(patcher.read_text(encoding="utf-8")),
                           encoding="utf-8")
    print(f"normalized source names in {touched} module files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
