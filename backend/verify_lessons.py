"""Exhaustive per-lesson verification harness for the Patchwork curriculum.

Unlike validate_curriculum.py (structural integrity), this harness EXECUTES
every lesson and code exercise through the sandbox runner and proves:

1. The canonical solution passes every required test for its lesson.
2. Starter code is syntactically valid for its language.
3. Starter code is not pre-solved (must fail >= 1 required test when it
   differs from the solution; flagged when it equals the solution on
   practice/challenge/checkpoint lessons).
4. Every code exercise's solution passes its own tests.
5. Metadata quality: source attribution, learning objectives, vague-title
   heuristics, duplicate titles/descriptions inside a course.

Output: JSON findings written to audit/lesson_findings.json plus a readable
summary per course on stdout.

Run from the repository root:
    .venv/Scripts/python.exe -m backend.verify_lessons [--courses python,sql]
"""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from .curriculum_loader import load_all_curriculums

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "sandbox" / "runner.py"
PY = sys.executable

# Languages the host can execute directly via runner.py (needs python + node).
# dsa, ml, ai, and fullstack lessons are Python programs. The runner already
# executes them with the Python sandbox, so the audit must too.
LOCAL_LANGS = {
    "python", "py", "sql", "javascript", "typescript",
    "dsa", "ml", "ml-math", "ai", "fullstack",
    # javac and g++ on the host are the real compilers. Docker is optional.
    # A missing compiler is still a failed parse or a failed run, never a pass.
    "java", "cpp", "c++",
}
DOCKER_IMAGE = "patchwork-sandbox:local"

VAGUE_PATTERNS = [
    r"^(explore|understand|learn|discover)\s+(how|modern|advanced|the world)",
    r"\b(build something cool)\b",
    r"^(write a draft|implement them yourself|practice exercises)\b",
    r"^\d+\.\s*(misc|other|various|extra|more)\b",
]

MATERIAL_TYPES = {"practice", "challenge", "checkpoint"}

GENERIC_HINTS = {
    "read the one-line idea.",
    "compare each choice with the example.",
    "pick the choice that matches the example exactly.",
}

MICRO_EDITOR_TYPES = {"code", "tiny_coding"}


def replay_sample(lesson_ids: list[str]) -> list[str]:
    """Stable 10% of a course, at least one lesson when the course is non-empty.

    The pilot plays every rewritten lesson. A finished course replays this sample
    in the browser, plus any lesson a script flags.
    """
    ordered = list(lesson_ids)
    if not ordered:
        return []
    count = max(1, math.ceil(len(ordered) * 0.10))
    if count >= len(ordered):
        return ordered
    step = len(ordered) / count
    picked: list[str] = []
    for index in range(count):
        choice = ordered[min(len(ordered) - 1, int(index * step))]
        if choice not in picked:
            picked.append(choice)
    return picked


def _snippet(question: str, starter: str) -> str:
    match = re.search(r"```[a-zA-Z]*\n?([\s\S]*?)```", question or "")
    if match and match.group(1).strip():
        return match.group(1).strip()
    return (starter or "").strip()


def _joined_key(answer) -> str:
    if isinstance(answer, list):
        return " ".join(str(part) for part in answer)
    if answer is None:
        return ""
    return str(answer)


def _strip_types(code: str) -> tuple[bool, str]:
    """Strip TypeScript types with Node, then leave JavaScript for ``node --check``.

    ``node --check --experimental-strip-types`` does not strip. The runner loads
    ``.ts`` files with the same stripper, so the gate has to strip first or every
    real TypeScript snippet is reported as a syntax error.
    """
    proc = subprocess.run(
        [
            "node", "--input-type=module", "-e",
            "import { stripTypeScriptTypes } from 'node:module';"
            "import fs from 'node:fs';"
            "process.stdout.write(stripTypeScriptTypes(fs.readFileSync(0, 'utf8')));",
        ],
        input=code, capture_output=True, text=True, timeout=20,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "type strip failed").strip().splitlines()
        return False, detail[-1][:240] if detail else "type strip failed"
    return True, proc.stdout


def _node_parses(code: str, language: str) -> tuple[bool, str]:
    """Parse a JS or TS snippet with node --check.

    TypeScript is stripped with Node's type stripper first. ``node --check``
    then parses the JavaScript the runtime will actually execute.
    """
    import tempfile

    source = code if code.endswith("\n") else code + "\n"
    suffix = ".js"
    if language in {"typescript", "ts"}:
        ok, stripped = _strip_types(source)
        if not ok:
            return False, stripped
        source = stripped if stripped.endswith("\n") else stripped + "\n"
    try:
        with tempfile.TemporaryDirectory(prefix="pw_parse_") as folder:
            path = Path(folder) / f"snippet{suffix}"
            path.write_text(source, encoding="utf-8")
            proc = subprocess.run(
                ["node", "--check", str(path)],
                capture_output=True, text=True, timeout=20,
            )
    except FileNotFoundError:
        return False, "node is not installed"
    except subprocess.TimeoutExpired:
        return False, "node --check timed out"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "syntax error").strip().splitlines()
        return False, detail[-1][:240] if detail else "syntax error"
    return True, ""


def _sql_parses(code: str) -> tuple[bool, str]:
    """Prepare SQL in memory. Missing tables are fine; bad syntax is not."""
    import sqlite3

    try:
        conn = sqlite3.connect(":memory:")
        conn.executescript(code)
        conn.close()
    except sqlite3.Error as exc:
        text = str(exc).lower()
        if "syntax" in text or "incomplete" in text:
            return False, str(exc)[:240]
    return True, ""


def _compile_native(code: str, language: str) -> tuple[bool, str]:
    """Syntax-check Java or C++ with the host compiler.

    A fragment is wrapped in a main that already declares a few names, so an
    ordering line such as ``int total = left + right;`` is checked for real.
    A complete program is compiled as written. Compiler failure is a failure.
    """
    lang = language.lower()
    try:
        with tempfile.TemporaryDirectory(prefix="pw_parse_") as folder:
            root = Path(folder)
            if lang == "java":
                if re.search(r"\bclass\s+\w+", code):
                    src = code if code.endswith("\n") else code + "\n"
                else:
                    src = (
                        "import java.util.*;\n"
                        "public class Snippet {\n"
                        "  public static void main(String[] args) {\n"
                        "    int left = 2;\n"
                        "    int right = 3;\n"
                        "    int count = 4;\n"
                        "    String name = \"ada\";\n"
                        "    String word = \"ada\";\n"
                        f"    {code}\n"
                        "  }\n"
                        "}\n"
                    )
                match = re.search(r"(?:public\s+)?class\s+(\w+)", src)
                name = match.group(1) if match else "Snippet"
                path = root / f"{name}.java"
                path.write_text(src, encoding="utf-8")
                proc = subprocess.run(
                    ["javac", str(path)], capture_output=True, text=True, timeout=20,
                )
            else:
                if re.search(r"\bmain\s*\(", code):
                    src = code if code.endswith("\n") else code + "\n"
                else:
                    src = (
                        "#include <iostream>\n#include <string>\n#include <vector>\n"
                        "#include <algorithm>\n#include <memory>\n"
                        "int main() {\n"
                        "  int left = 2;\n  int right = 3;\n  int count = 4;\n"
                        "  std::string name = \"ada\";\n  std::string word = \"ada\";\n"
                        f"  {code}\n"
                        "  return 0;\n}\n"
                    )
                path = root / "snippet.cpp"
                path.write_text(src, encoding="utf-8")
                proc = subprocess.run(
                    ["g++", "-std=c++20", "-fsyntax-only", str(path)],
                    capture_output=True, text=True, timeout=20,
                )
    except FileNotFoundError:
        return False, "compiler is not installed"
    except subprocess.TimeoutExpired:
        return False, "compiler timed out"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "syntax error").strip().splitlines()
        return False, detail[-1][:240] if detail else "syntax error"
    return True, ""


def program_parses(language: str, code: str) -> tuple[bool, str]:
    lang = (language or "").lower()
    if lang in {"python", "py", "dsa", "ml", "ml-math", "ai", "fullstack"}:
        try:
            ast.parse(code)
        except SyntaxError as exc:
            return False, f"{exc.msg} (line {exc.lineno})"
        return True, ""
    if lang in {"javascript", "js", "typescript", "ts"}:
        return _node_parses(code, lang)
    if lang in {"sql", "sqlite"}:
        return _sql_parses(code)
    if lang == "java":
        return _compile_native(code, "java")
    if lang in {"cpp", "c++"}:
        return _compile_native(code, "cpp")
    return False, f"no parser wired for {language}"


def hint_gives_answer(hint: str, answer) -> bool:
    key = normalize(_joined_key(answer))
    if len(key) < 1:
        return False
    return key in normalize(hint or "")


def cross_lesson_duplicates(records: list[dict]) -> list[dict]:
    """Exact and near-duplicate prompts and teach lines across lessons in one course."""
    findings: list[dict] = []
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["course"]].append(record)
    for course, items in grouped.items():
        for index, left in enumerate(items):
            for right in items[index + 1:]:
                if left["lesson_id"] == right["lesson_id"]:
                    continue
                if not left["norm"] or not right["norm"]:
                    continue
                if left["norm"] == right["norm"]:
                    code = "duplicate_prompt"
                    detail = f"same text as {right['lesson_id']} ({right['kind']})"
                elif SequenceMatcher(None, left["norm"], right["norm"]).ratio() >= 0.9:
                    code = "near_duplicate_prompt"
                    detail = f"too close to {right['lesson_id']} ({right['kind']})"
                else:
                    continue
                findings.append({
                    "course": course,
                    "lesson_id": left["lesson_id"],
                    "lesson_title": left.get("lesson_title", ""),
                    "severity": "ERROR",
                    "code": code,
                    "detail": f"{left['kind']}: {detail}",
                })
    return findings


def run_sandbox(language: str, code: str, tests: list[dict], use_docker: bool) -> dict:
    payload = json.dumps({"language": language, "code": code, "tests": tests})
    if use_docker:
        # Mirror the exact learner-path restrictions from backend.sandbox so
        # the audit cannot pass on a looser sandbox than the app actually uses.
        from .sandbox import SandboxLimits

        lim = SandboxLimits()
        cmd = [
            "docker", "run", "--rm", "-i",
            "--network=none", "--read-only",
            "--tmpfs", "/tmp:exec,size=64m", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--user", "10001:10001",
            "--memory", lim.memory, "--cpus", lim.cpus,
            "--pids-limit", lim.pids,
            "--ulimit", "nofile=256:256",
            "--ulimit", f"fsize={lim.max_file_bytes}:{lim.max_file_bytes}",
            DOCKER_IMAGE,
        ]
    else:
        cmd = [PY, "-I", str(RUNNER)]
    try:
        proc = subprocess.run(
            cmd, input=payload, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=90,
        )
    except FileNotFoundError:
        return {"error": "docker unavailable for compiled languages", "tests": []}
    except subprocess.TimeoutExpired:
        return {"error": "harness timeout", "tests": []}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "error": f"runner produced no JSON (rc={proc.returncode}): "
                     f"{(proc.stderr or proc.stdout)[:300]}",
            "tests": [],
        }


def required_names(tests: list[dict]) -> set[str]:
    names = {t["name"] for t in tests if t.get("required", True)}
    return names or {t["name"] for t in tests}


def eval_code(language: str, code: str, tests: list[dict], use_docker: bool) -> dict:
    """Returns {'all_pass': bool, 'failed': [names], 'syntax_error': bool, 'error': str|None}"""
    res = run_sandbox(language, code, tests, use_docker)
    if res.get("error") and not res.get("tests"):
        return {"all_pass": False, "failed": [t["name"] for t in tests],
                "syntax_error": False, "error": res["error"]}
    req = required_names(tests)
    failed = [t["name"] for t in res.get("tests", [])
              if t["name"] in req and not t.get("passed")]
    missing = req - {t["name"] for t in res.get("tests", [])}
    failed += sorted(missing)
    syntax = any("SyntaxError" in (t.get("error") or "") for t in res.get("tests", []))
    return {"all_pass": not failed, "failed": failed, "syntax_error": syntax,
            "error": None}


def exercise_iter(lesson):
    for s in lesson.sublessons:
        for e in s.exercises:
            yield s.id, e
    for e in lesson.mastery_exam:
        yield "mastery-exam", e


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def audit_lesson(curriculum_key: str, language: str, lesson, seen: dict,
                 force_docker: bool = False, prompt_records: list | None = None) -> list[dict]:
    findings: list[dict] = []

    def add(severity: str, code: str, detail: str = "") -> None:
        findings.append({
            "course": curriculum_key, "lesson_id": lesson.id,
            "lesson_title": lesson.title, "severity": severity,
            "code": code, "detail": detail,
        })

    # --- metadata ---------------------------------------------------------
    if not (lesson.source and lesson.source.url):
        add("SOURCE", "missing_source", lesson.source.name if lesson.source else "")
    if not lesson.learning_objectives:
        add("WARN", "no_learning_objectives")
    blob = f"{lesson.title} {lesson.description}"
    for pat in VAGUE_PATTERNS:
        if re.search(pat, blob, re.IGNORECASE):
            add("WARN", "vague_wording", pat)
    if len(lesson.description) < 40:
        add("WARN", "thin_description", lesson.description)
    dupe_key = ("title", curriculum_key, normalize(lesson.title))
    if dupe_key in seen:
        add("WARN", "duplicate_title", f"also {seen[dupe_key]}")
    else:
        seen[dupe_key] = lesson.id
    dkey = ("desc", curriculum_key, normalize(lesson.description))
    if dkey in seen:
        add("ERROR", "duplicate_description", f"also {seen[dkey]}")
    else:
        seen[dkey] = lesson.id

    # --- lesson-level code -------------------------------------------------
    tests = [t.model_dump() for t in lesson.tests]
    starter = lesson.starter_code or ""
    solution = lesson.solution_code
    use_docker = force_docker or language not in LOCAL_LANGS

    if tests:
        if not solution:
            add("ERROR", "no_solution_authored",
                "tests exist but no canonical solution was ever verified")
        else:
            verdict = eval_code(language, solution, tests, use_docker)
            if verdict["syntax_error"]:
                add("ERROR", "solution_syntax_error", ", ".join(verdict["failed"]))
            elif not verdict["all_pass"]:
                add("ERROR", "solution_fails_tests",
                    f"{', '.join(verdict['failed'])} :: "
                    f"{verdict['error'] or 'see failed test names'}")
        # starter checks (only when a solution exists to compare against)
        if starter.strip() and solution:
            if normalize(starter) == normalize(solution):
                # Every lesson type — including learn demos — must present a
                # TODO skeleton the learner edits, never the finished answer.
                add("ERROR", "presolved_starter_equals_solution", lesson.type)
            else:
                sverdict = eval_code(language, starter, tests, use_docker)
                if sverdict["syntax_error"]:
                    add("ERROR", "starter_syntax_error")
                elif sverdict["all_pass"]:
                    add("ERROR", "starter_pre_solved")
                elif not sverdict["failed"] and sverdict["error"]:
                    add("WARN", "starter_exec_error", sverdict["error"])
    else:
        if lesson.type in MATERIAL_TYPES or solution:
            add("WARN", "lesson_without_tests")

    # --- exercises ---------------------------------------------------------
    for sub_id, ex in exercise_iter(lesson):
        etests = [t.model_dump() for t in ex.tests]

        def add_ex(severity, code, detail=""):
            add(severity, code, f"exercise {sub_id}/{ex.id}: {detail}")

        q = normalize(ex.question)
        if not q and ex.type not in ("fill_blank",):
            add_ex("WARN", "exercise_no_question")
        if len(q) < 15 and ex.type not in ("fill_blank", "ordering", "matching"):
            add_ex("WARN", "exercise_thin_question", ex.question[:80])
        for pat in VAGUE_PATTERNS:
            if re.search(pat, q, re.IGNORECASE):
                add_ex("WARN", "exercise_vague", pat)
        if ex.type in ("mcq", "true_false"):
            if not ex.options:
                add_ex("ERROR", "mcq_no_options")
            elif ex.correct_answer not in ex.options:
                add_ex("ERROR", "mcq_answer_not_in_options", str(ex.correct_answer))
            if ex.type == "mcq" and len(ex.options) < 2:
                add_ex("ERROR", "mcq_single_option")
        if ex.type == "select_multiple" and (
            not isinstance(ex.correct_answer, list)
            or not set(ex.correct_answer) <= set(ex.options)
        ):
            add_ex("ERROR", "select_multiple_answer_invalid")
        if ex.type == "fill_blank" and getattr(lesson, "player_mode", "") != "micro":
            if not ex.blanks:
                add_ex("ERROR", "fill_blank_no_blanks")
            if ex.correct_answer is not None and not isinstance(ex.correct_answer, list):
                add_ex("ERROR", "fill_blank_answer_not_list")
            if isinstance(ex.correct_answer, list) and ex.blanks and \
               len(ex.correct_answer) != len(ex.blanks):
                add_ex("ERROR", "fill_blank_answer_length_mismatch",
                       f"{len(ex.correct_answer)} answers vs {len(ex.blanks)} blanks")
        if ex.type == "matching" and not ex.pairs:
            add_ex("ERROR", "matching_no_pairs")
        if ex.type == "ordering" and not isinstance(ex.correct_answer, list):
            add_ex("ERROR", "ordering_answer_not_list")
        # Every course, every lesson. Hint 1 is a nudge. Hint 2 may name the answer.
        if ex.type != "teach" and ex.hints and hint_gives_answer(ex.hints[0], ex.correct_answer):
            add_ex("ERROR", "hint1_gives_answer", ex.id)
        if ex.options:
            seen_options: set[str] = set()
            for option in ex.options:
                token = option.strip()
                if token in seen_options:
                    add_ex("ERROR", "duplicate_option", token)
                seen_options.add(token)
        if ex.type in ("code", "tiny_coding") and ex.tests:
            if not ex.solution_code or not ex.solution_code.strip():
                add_ex("ERROR", "code_exercise_no_solution")
            else:
                v = eval_code(language, ex.solution_code, etests, use_docker)
                if not v["all_pass"]:
                    add_ex("ERROR", "exercise_solution_fails",
                           ", ".join(v["failed"]) or v["error"] or "")
                if ex.starter_code.strip() and "___" not in ex.starter_code and normalize(ex.starter_code) != \
                   normalize(ex.solution_code):
                    sv = eval_code(language, ex.starter_code, etests, use_docker)
                    if sv["syntax_error"]:
                        add_ex("ERROR", "exercise_starter_syntax_error")
                    elif sv["all_pass"]:
                        add_ex("ERROR", "exercise_starter_pre_solved")

    if getattr(lesson, "player_mode", "") == "micro":
        _audit_micro(curriculum_key, language, lesson, add, use_docker, prompt_records)
    return findings


def _audit_micro(curriculum_key, language, lesson, add, use_docker, prompt_records) -> None:
    """Execution and junk checks for one opted-in micro lesson.

    Counts are recorded here too, but a green count is not treated as proof.
    The proof is the sandbox run, the parse, and the cross-lesson prompt scan.
    """
    exercises = [ex for sub in lesson.sublessons for ex in sub.exercises]

    def add_ex(code: str, detail: str = "") -> None:
        add("ERROR", code, detail)

    if not 8 <= len(exercises) <= 10:
        add_ex("micro_screen_count", f"{len(exercises)} exercises")
    if not exercises or exercises[0].type != "teach":
        add_ex("micro_must_start_with_teach")
    editors = [ex for ex in exercises if ex.type in MICRO_EDITOR_TYPES]
    if len(editors) > 2:
        add_ex("micro_too_many_editors", str(len(editors)))
    if not editors:
        add_ex("micro_no_write")
    for index, ex in enumerate(exercises[:5]):
        if ex.type in MICRO_EDITOR_TYPES:
            add_ex("micro_editor_too_early", ex.id)

    speech = ""
    if exercises and exercises[0].type == "teach":
        speech = exercises[0].question or ""
    objective = (lesson.learning_objectives or [""])[0]
    for kind, text in (("teach", speech), ("objective", objective)):
        if prompt_records is not None and text.strip():
            prompt_records.append({
                "course": curriculum_key,
                "lesson_id": lesson.id,
                "lesson_title": lesson.title,
                "kind": kind,
                "norm": normalize(text),
            })

    for ex in exercises:
        if len(ex.hints) < 3 or any(not (hint or "").strip() for hint in ex.hints[:3]):
            add_ex("micro_hint_count", ex.id)
        for hint in ex.hints:
            if normalize(hint) in GENERIC_HINTS:
                add_ex("micro_generic_hint", ex.id)
        blob = " ".join([
            ex.question or "",
            ex.explanation or "",
            ex.worked_example or "",
            " ".join(ex.hints),
            " ".join(ex.options),
        ])
        if "`" in blob:
            add_ex("micro_backtick", ex.id)
        if ex.type != "teach" and ex.hints and hint_gives_answer(ex.hints[0], ex.correct_answer):
            add_ex("hint1_gives_answer", ex.id)
        if ex.options:
            seen_opts: set[str] = set()
            for option in ex.options:
                key = option.strip()
                if key in seen_opts:
                    add_ex("duplicate_option", f"{ex.id}: {key}")
                seen_opts.add(key)
        if ex.type != "teach" and prompt_records is not None and (ex.question or "").strip():
            prompt_records.append({
                "course": curriculum_key,
                "lesson_id": lesson.id,
                "lesson_title": lesson.title,
                "kind": ex.id,
                "norm": normalize(ex.question),
            })

        if ex.type == "output_prediction":
            snippet = _snippet(ex.question, ex.starter_code)
            if not snippet:
                add_ex("predict_missing_code", ex.id)
            else:
                res = run_sandbox(
                    language, snippet, [{"name": "predict", "required": True}], use_docker,
                )
                if res.get("error") and not res.get("tests"):
                    add_ex("predict_run_error", f"{ex.id}: {res.get('error')}")
                else:
                    stdout = ""
                    if res.get("tests"):
                        stdout = res["tests"][0].get("stdout") or ""
                    if stdout.strip() != str(ex.correct_answer).strip():
                        add_ex(
                            "predict_mismatch",
                            f"{ex.id}: key {ex.correct_answer!r} stdout {stdout!r}",
                        )
        if ex.type == "ordering":
            statement = _joined_key(ex.correct_answer)
            ok, err = program_parses(language, statement)
            if not ok:
                add_ex("ordering_does_not_parse", f"{ex.id}: {err}")
        if ex.type == "fill_blank":
            template = ex.starter_code or ""
            pieces = ex.correct_answer if isinstance(ex.correct_answer, list) else [ex.correct_answer]
            filled = template
            for piece in pieces:
                filled = filled.replace("___", "" if piece is None else str(piece), 1)
            if "___" in filled or not filled.strip():
                add_ex("fill_blank_unfilled", ex.id)
            else:
                ok, err = program_parses(language, filled)
                if not ok:
                    add_ex("fill_blank_does_not_parse", f"{ex.id}: {err}")
        if ex.type in MICRO_EDITOR_TYPES:
            if not ex.solution_code or not str(ex.solution_code).strip() or not ex.tests:
                add_ex("micro_write_unverified", ex.id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--courses", default="", help="comma list, default all")
    parser.add_argument("--docker", action="store_true",
                        help="route ALL execution through the Docker sandbox")
    args = parser.parse_args(argv)

    currs = load_all_curriculums()
    wanted = {c.strip().lower() for c in args.courses.split(",") if c.strip()}
    seen: dict = {}
    all_findings: list[dict] = []
    micro_ids: set[str] = set()
    prompt_records: list[dict] = []
    replay: dict[str, list[str]] = {}
    for key in sorted(currs):
        if wanted and key not in wanted:
            continue
        curr = currs[key]
        language = curr.course.language.lower()
        print(f"auditing {key} ({len(curr.lessons)} lessons)...", flush=True)
        course_micro = [lesson.id for lesson in curr.lessons if getattr(lesson, "player_mode", "") == "micro"]
        micro_ids.update(course_micro)
        replay[key] = replay_sample(course_micro)
        for lesson in curr.lessons:
            all_findings.extend(
                audit_lesson(
                    key, language, lesson, seen,
                    force_docker=args.docker, prompt_records=prompt_records,
                )
            )
    all_findings.extend(cross_lesson_duplicates(prompt_records))

    out_dir = ROOT / "audit"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "lesson_findings.json").write_text(
        json.dumps(all_findings, indent=2), encoding="utf-8")
    (out_dir / "replay_sample.json").write_text(
        json.dumps(replay, indent=2), encoding="utf-8")

    counts = Counter(f["code"] for f in all_findings)
    per_course = Counter(f["course"] for f in all_findings if f["severity"] != "SOURCE")
    print("\n=== finding codes ===")
    for code, n in counts.most_common():
        print(f"{code:34s} {n}")
    print("\n=== non-source findings per course ===")
    for c, n in per_course.most_common():
        print(f"{c:12s} {n}")
    print(f"\nwrote audit/lesson_findings.json ({len(all_findings)} findings)")
    # Hint leaks and duplicate choices fail the gate on every lesson, legacy or micro.
    # Screen-count rules stay on micro lessons until that lesson is opted in.
    GLOBAL_GATE = {"hint1_gives_answer", "duplicate_option"}
    gate = [
        f for f in all_findings
        if f["severity"] == "ERROR"
        and (f["lesson_id"] in micro_ids or f["code"] in GLOBAL_GATE)
    ]
    if gate:
        print(f"\nquality gate failed: {len(gate)} error(s)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
