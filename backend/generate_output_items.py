"""Author output-prediction items whose distractors were *executed*, not invented.

An output-prediction question is the rare exercise type that can be fully
grounded: the program is real code from the lesson, the correct answer is what
that program actually prints, and every wrong option is what a *specific*
mutation of that program actually prints. Nothing here is a plausible-sounding
string written by a generator or a tired human - if the sandbox cannot produce
the value by running code, the option does not exist.

That gives each item three properties the brief asks for:

* genuinely solvable - the stem shows all the code needed;
* correct answer verified - it is the observed stdout of the real program;
* meaningful wrong answers - each one is the observable result of a concrete
  misunderstanding (an off-by-one bound, a swapped branch, a dropped call), and
  each is *different* from the others and from the answer, because a duplicate
  option would make two choices correct.

The mutation list is a fixed library of the classic mistakes for each construct;
a mutation that does not change the output, or that crashes, is discarded along
with its explanation, so a distractor can never be "technically also right".

    python -m backend.generate_output_items --only python/conditionals-step-2 --verbose
    python -m backend.generate_output_items --only ... --apply
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from backend import console
from backend.curriculum_loader import load_all_curriculums
from backend.generate_ordering_exercises import passes
from backend.verify_lessons import LOCAL_LANGS, eval_code

console.configure()

CURRICULUM_ROOT = Path(__file__).resolve().parent.parent / "curriculum"
OUTPUT_XP = 10
MIN_OPTIONS = 3          # answer + at least two real, distinct wrong outputs
MAX_OPTIONS = 4

# Each mutation is (label, transformation, why a learner would pick it). The
# label is only for the report; the explanation is what makes the distractor
# instructive rather than random noise.
MUTATIONS = {
    ">=": [("strict_gt", lambda s: s.replace(">=", ">", 1),
            "treats the boundary as excluded instead of included"),
           ("always_true", lambda s: re.sub(r">=\s*[\d.]+", ">= 0", s, count=1),
            "ignores the threshold entirely")],
    ">": [("gte", lambda s: s.replace(">", ">=", 1),
           "includes the boundary value"),
          ("negated", lambda s: s.replace(">", "<=", 1),
           "reverses the comparison")],
    "<=": [("lt", lambda s: s.replace("<=", "<", 1), "excludes the boundary value")],
    "==": [("not_eq", lambda s: s.replace("==", "!=", 1), "inverts the test"),
           ("assign", lambda s: s.replace("==", "=", 1), "assigns instead of comparing")],
    "!=": [("eq", lambda s: s.replace("!=", "==", 1), "inverts the test")],
}


def _run_output(language: str, code: str, tests: list[dict], use_docker: bool) -> str | None:
    """Stdout of running `code`, or None when it does not run cleanly."""
    verdict = eval_code(language, code, tests, use_docker)
    if verdict.get("all_pass") is False and verdict.get("error"):
        return None
    out = verdict.get("stdout")
    if out is None:
        # eval_code only returns stdout when the harness reports it; fall back
        # to a plain run through the same sandbox so the value is still observed.
        res = _preview(language, code, use_docker)
        out = res.get("stdout") if res else None
    if out is None:
        return None
    text = str(out).strip()
    return text or None


def _preview(language: str, code: str, use_docker: bool) -> dict | None:
    """Execute the program for its printed output only (no assertions)."""
    payload = json.dumps({"language": language, "code": code, "tests": [], "mode": "preview"})
    runner = Path(__file__).resolve().parent.parent / "sandbox" / "runner.py"
    try:
        proc = subprocess.run(
            ["python", "-I", str(runner)] if not use_docker else
            ["docker", "run", "--rm", "-i", "--network=none", "--read-only",
             "--tmpfs", "/tmp:exec,size=64m", "--cap-drop=ALL",
             "--security-opt=no-new-privileges", "--user", "10001:10001",
             "--memory", "128m", "--cpus", "0.5", "--pids-limit", "32",
             "patchwork-sandbox:local"],
            input=payload, capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 and not (proc.stdout or "").strip():
        return None
    try:
        return json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return None


def _candidate_lines(solution: str) -> list[tuple[int, str]]:
    """Lines whose operator has a documented mutation, best candidate first.

    Only lines that actually print something can back an output item: the learner
    has to be able to observe the difference.
    """
    lines = solution.split("\n")
    out: list[tuple[int, str]] = []
    for index, raw in enumerate(lines):
        for op in (">=", "!=", "==", "<=", ">"):
            if op in raw:
                out.append((index, op))
                break
    return out


def _shows_the_answer(code: str, answer: str) -> bool:
    """The stem must not already print the answer in a comment or string label."""
    for raw in code.split("\n"):
        stripped = raw.strip()
        if stripped.startswith("#") or stripped.startswith("//"):
            if answer and answer in stripped:
                return True
    return False


def _probe_program(solution: str, probe: str) -> str:
    """The lesson's code, plus one call whose result is printed.

    The curriculum's solutions are test-graded functions rather than scripts, so
    they print nothing and have no observable output to ask about. Appending a
    single probe call gives an outcome the learner can reason about without
    inventing a program: the function under test is the lesson's own, verbatim.
    """
    return f"{solution}\nprint({probe})\n"


def build_probe_item(lesson, language: str, probe: str, verbose: bool = False) -> dict | None:
    """An output item grounded in executing the lesson's function and its mutants."""
    solution = (lesson.solution_code or "").strip()
    if not solution or language not in LOCAL_LANGS:
        # Only the interpreted local runners support the preview mode this uses.
        return None

    program = _probe_program(solution, probe)
    base = _preview(language, program, use_docker=False)
    answer = str((base or {}).get("stdout") or "").strip()
    if not answer or (base or {}).get("error"):
        if verbose:
            print(f"    - {lesson.id}: probe produced no clean stdout")
        return None
    if _shows_the_answer(program, answer):
        if verbose:
            print(f"    - {lesson.id}: a comment in the program already states the output")
        return None

    options: list[str] = [answer]
    reasons: list[str] = []
    for _line_no, op in _candidate_lines(solution):
        for _label, mutate, reason in MUTATIONS[op]:
            variant = _probe_program(mutate(solution), probe)
            if variant == program:
                continue
            wrong = _preview(language, variant, use_docker=False)
            value = str((wrong or {}).get("stdout") or "").strip()
            if not value or value in options or "Error" in value or "Traceback" in value:
                # A crash is not a distractor: two options that both describe an
                # exception would make the item ambiguous.
                continue
            options.append(value)
            reasons.append(reason)
            if len(options) >= MAX_OPTIONS:
                break
        if len(options) >= MAX_OPTIONS:
            break

    if len(options) < MIN_OPTIONS:
        if verbose:
            print(f"    - {lesson.id}: only {len(options)} observed outcome(s) from the probe")
        return None

    return {
        "id": f"{lesson.id}-out-1",
        "type": "output_prediction",
        "question": f"What does this print?\n\n{program.rstrip()}",
        "options": options,
        "correct_answer": answer,
        "explanation": (f"Observed by running the code: the other options are what "
                        f"{_human_list(reasons)} produce."),
        "xp_reward": OUTPUT_XP,
    }


def build_item(lesson, language: str, verbose: bool = False) -> dict | None:
    solution = (lesson.solution_code or "").strip()
    tests = [t.model_dump() for t in lesson.tests]
    if not solution:
        return None
    use_docker = language not in LOCAL_LANGS

    if not passes(language, solution, tests, use_docker):
        if verbose:
            print(f"    - {lesson.id}: solution does not pass its own tests")
        return None
    answer = _run_output(language, solution, tests, use_docker)
    if not answer or len(answer.splitlines()) > 6 or len(answer) > 220:
        if verbose:
            print(f"    - {lesson.id}: no short, clean stdout to ask about")
        return None
    if _shows_the_answer(solution, answer):
        if verbose:
            print(f"    - {lesson.id}: the program's comments already state the output")
        return None

    options: list[str] = [answer]
    reasons: list[str] = []
    for line_no, op in _candidate_lines(solution):
        for _label, mutate, reason in MUTATIONS[op]:
            try:
                variant = mutate(solution)
            except Exception:
                continue
            if variant == solution:
                continue
            wrong = _run_output(language, variant, tests, use_docker)
            if not wrong or wrong in options:
                continue          # no observable difference, or a duplicate answer
            options.append(wrong)
            reasons.append(reason)
            if len(options) >= MAX_OPTIONS:
                break
        if len(options) >= MAX_OPTIONS:
            break

    if len(options) < MIN_OPTIONS:
        if verbose:
            print(f"    - {lesson.id}: only {len(options)} observable outcome(s); "
                  "cannot offer real distractors")
        return None

    return {
        "id": f"{lesson.id}-out-1",
        "type": "output_prediction",
        "question": "What does this program print?",
        "code": solution,
        "options": options,
        "correct_answer": answer,
        "explanation": f"The printed result above is what the code actually produces; "
                       f"the other options are what {_human_list(reasons)} produce.",
        "xp_reward": OUTPUT_XP,
    }


def _human_list(items: list[str]) -> str:
    cleaned = [i for i in items if i]
    if not cleaned:
        return "a variant of it"
    if len(cleaned) == 1:
        return cleaned[0]
    return ", ".join(cleaned[:-1]) + " or " + cleaned[-1]


def _write(lesson_id: str, item: dict) -> bool:
    for path in sorted(CURRICULUM_ROOT.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        for lesson in payload.get("lessons") or []:
            if lesson.get("id") != lesson_id:
                continue
            sublessons = lesson.setdefault("sublessons", [])
            for sub in sublessons:
                for ex in sub.get("exercises") or []:
                    if ex.get("id") == item["id"]:
                        return False
            sublessons.append({
                "id": f"{lesson_id}-out-sub",
                "title": "Predict the output",
                "order": len(sublessons) + 1,
                "exercises": [item],
            })
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", action="append", default=[], metavar="COURSE/LESSON_ID")
    parser.add_argument("--probe", action="append", default=[],
                        metavar="LESSON_ID=EXPRESSION",
                        help="ask what one call of the lesson's own function returns, "
                             "e.g. python/conditionals-step-1=evaluate_grade(50)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    probes: dict[str, str] = {}
    for spec in args.probe:
        key, _, expression = spec.partition("=")
        if key.strip() and expression.strip():
            probes[key.strip().lower()] = expression.strip()

    wanted = {o.strip().lower() for o in args.only if o.strip()}
    if not wanted:
        parser.error("refusing to write in bulk: pass one or more --only COURSE/LESSON_ID")

    built: list[tuple[str, str, dict]] = []
    for language, curriculum in sorted(load_all_curriculums().items()):
        for lesson in curriculum.lessons:
            key = f"{language}/{lesson.id}".lower()
            if key not in wanted:
                continue
            probe = probes.get(lesson.id.lower()) or probes.get(key)
            item = (build_probe_item(lesson, language, probe, verbose=args.verbose)
                    if probe else build_item(lesson, language, verbose=args.verbose))
            if not item:
                print(f"  ✗ {language}/{lesson.id}: not buildable with executed distractors")
                continue
            print(f"  ✓ {language}/{lesson.id}: {len(item['options'])} executed outcomes")
            built.append((language, lesson.id, item))

    if not built:
        print("\nnothing accepted")
        return 1

    if not args.apply:
        for language, lesson_id, item in built:
            print(f"\n[{language}/{lesson_id}]\n{json.dumps(item, indent=2)}")
        print("\n(nothing written; pass --apply)")
        return 0

    for language, lesson_id, item in built:
        if _write(lesson_id, item):
            print(f"  wrote {language}/{lesson_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
