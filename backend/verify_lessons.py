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
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from .curriculum_loader import load_all_curriculums

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "sandbox" / "runner.py"
PY = sys.executable

# Languages the host can execute directly via runner.py (needs python + node).
LOCAL_LANGS = {"python", "sql", "javascript", "typescript"}
DOCKER_IMAGE = "patchwork-sandbox:local"

VAGUE_PATTERNS = [
    r"^(explore|understand|learn|discover)\s+(how|modern|advanced|the world)",
    r"\b(build something cool)\b",
    r"^(write a draft|implement them yourself|practice exercises)\b",
    r"^\d+\.\s*(misc|other|various|extra|more)\b",
]

MATERIAL_TYPES = {"practice", "challenge", "checkpoint"}


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
                 force_docker: bool = False) -> list[dict]:
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
        if ex.type == "fill_blank":
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
        if ex.type in ("code", "tiny_coding") and ex.tests:
            if not ex.solution_code or not ex.solution_code.strip():
                add_ex("ERROR", "code_exercise_no_solution")
            else:
                v = eval_code(language, ex.solution_code, etests, use_docker)
                if not v["all_pass"]:
                    add_ex("ERROR", "exercise_solution_fails",
                           ", ".join(v["failed"]) or v["error"] or "")
                if ex.starter_code.strip() and normalize(ex.starter_code) != \
                   normalize(ex.solution_code):
                    sv = eval_code(language, ex.starter_code, etests, use_docker)
                    if sv["syntax_error"]:
                        add_ex("ERROR", "exercise_starter_syntax_error")
                    elif sv["all_pass"]:
                        add_ex("ERROR", "exercise_starter_pre_solved")
    return findings


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
    for key in sorted(currs):
        if wanted and key not in wanted:
            continue
        curr = currs[key]
        language = curr.course.language.lower()
        print(f"auditing {key} ({len(curr.lessons)} lessons)...", flush=True)
        for lesson in curr.lessons:
            all_findings.extend(
                audit_lesson(key, language, lesson, seen, force_docker=args.docker)
            )

    out_dir = ROOT / "audit"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "lesson_findings.json").write_text(
        json.dumps(all_findings, indent=2), encoding="utf-8")

    counts = Counter(f["code"] for f in all_findings)
    per_course = Counter(f["course"] for f in all_findings if f["severity"] != "SOURCE")
    print("\n=== finding codes ===")
    for code, n in counts.most_common():
        print(f"{code:34s} {n}")
    print("\n=== non-source findings per course ===")
    for c, n in per_course.most_common():
        print(f"{c:12s} {n}")
    print(f"\nwrote audit/lesson_findings.json ({len(all_findings)} findings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
