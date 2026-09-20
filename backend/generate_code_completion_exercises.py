"""Author *provable* code-completion items from a lesson's own solution.

A code-completion item is a line of real code with one load-bearing token
removed. The temptation is to generate these in bulk, because writing the stem
is cheap. The trap is that most blanks are guessable in several ways: if both
``>=`` and ``>`` satisfy the lesson's tests for that program, then a learner who
writes the other one is marked wrong by a text comparison, and a generator that
did not check has produced an unfair item at scale.

So this module refuses to emit anything it cannot prove, using the same
execution bar ``generate_ordering_exercises`` holds ordering to:

1. the solution with the true token restored must pass the lesson's own tests;
2. every plausible alternative token must *fail* those tests - same identifiers
   used in the lesson, and the whole comparison/boolean operator family when the
   blank is an operator;
3. at least three alternatives must have been tested, otherwise the proof is
   vacuous and the item is rejected;
4. the shipped stem and starter never contain the answer token, and the result
   is run through the real leak audit before it is written.

Only the blanked statement ships. The full program stays here as the proof
fixture, so the exercise cannot hand over the solution.

    python -m backend.generate_code_completion_exercises --only python/conditionals-step-1
    python -m backend.generate_code_completion_exercises --only ... --apply
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from backend import console
from backend.blank_template import BLANK_TOKEN
from backend.curriculum_loader import load_all_curriculums
from backend.generate_ordering_exercises import _body_indent, _is_scaffolding, passes
from backend.verify_lessons import LOCAL_LANGS

console.configure()

CURRICULUM_ROOT = Path(__file__).resolve().parent.parent / "curriculum"
COMPLETION_XP = 12
MIN_ALTERNATIVES_TESTED = 3

OPERATOR_FAMILY = ["==", "!=", ">=", "<=", ">", "<", "+", "-", "*", "/"]
BOOLEAN_FAMILY = ["and", "or", "not", "in", "is", "True", "False"]

TOKEN = re.compile(r"(<=|>=|==|!=|\+\+|--|[-+*/%<>=!&|^]|\b[A-Za-z_][A-Za-z0-9_]*\b)")

# Kinds of token worth asking for. Language keywords are excluded entirely:
# blanking ``return`` in ``def evaluate_grade(score): return "Fail"`` is provably
# unique and completely worthless, because the keyword is not what any of these
# lessons teach. The concept lives in the operator that decides a branch and the
# name that gets called.
PREFERRED_KINDS = ("operator", "call")


LANGUAGE_KEYWORDS = {"if", "else", "elif", "for", "while", "return", "def", "class",
                     "print", "range", "len", "True", "False", "None", "self", "func",
                     "function", "var", "let", "const", "end", "then", "do", "in", "is"}


def _kinds_of(token: str) -> tuple[str, ...]:
    if token in OPERATOR_FAMILY:
        return ("operator",)
    if token in BOOLEAN_FAMILY or token in LANGUAGE_KEYWORDS:
        return ()  # never the concept - see PREFERRED_KINDS
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token or ""):
        return ("call",)
    return ()


def _is_locally_bound(solution: str, token: str) -> bool:
    """Was this name invented by the lesson's author rather than fixed by the language?

    Uniqueness is not fairness. Blanking ``parts`` in
    ``return '&'.join(parts)`` is provably unique - every other identifier in
    that file breaks the tests - but the only reason the answer is ``parts`` is
    that the author chose that word. A learner who writes ``pieces`` and renames
    consistently has written equally correct code and would be marked wrong. A
    blank is only fair when the token is *not* a name this file invented, i.e. a
    stdlib/member name the language or the lesson's own interface fixes.
    """
    if not re.fullmatch(r"[A-Za-z_]\w*", token or ""):
        return False
    patterns = (
        rf"^\s*{re.escape(token)}\s*=",                       # parts = []
        rf"\b(def|function|fn|class|struct|interface|enum)\s+{re.escape(token)}\b",
        rf"\b(for|as|with)\s+{re.escape(token)}\b",
        rf"\b{re.escape(token)}\s*(=|:=)\s*",                 # any assignment target
    )
    return any(re.search(p, solution, re.M) for p in patterns)


def candidate_sites(solution: str) -> list[tuple[int, int, str, str]]:
    """(line index, token index, token, kind) worth blanking, best first.

    Skips scaffolding, blanks inside string literals (the answer would be
    quoted text the learner cannot infer), tokens that repeat on the same line
    (positionally ambiguous), and names the lesson invented itself (see
    ``_is_locally_bound``).
    """
    lines = solution.split("\n")
    body_indent = _body_indent(lines)
    scored: list[tuple[int, int, str, str]] = []
    for line_no, raw in enumerate(lines):
        text = raw.strip()
        if not text or _is_scaffolding(text, body_indent, raw):
            continue
        # Blank only outside string literals.
        masked = re.sub(r"'[^']*'|\"[^\"]*\"", lambda m: " " * len(m.group(0)), raw)
        matches = list(TOKEN.finditer(masked))
        for match in match_positions(matches):
            token = match.group(0)
            kinds = _kinds_of(token)
            if not kinds:
                continue
            occurrences = sum(1 for m in matches if m.group(0) == token)
            if occurrences != 1:
                continue
            if _is_locally_bound(solution, token):
                continue
            for kind in kinds:
                scored.append((line_no, match.start(), token, kind))
    order = {kind: index for index, kind in enumerate(PREFERRED_KINDS)}
    scored.sort(key=lambda entry: (order.get(entry[3], 99), -entry[0]))
    return scored


def match_positions(matches):
    """Tokens that are meaningful to blank, in right-to-left order.

    The rightmost interesting token is usually the one that decides behaviour
    (the operator in a condition, the name of the function called), while the
    leftmost is often an assignment target the learner can read off the tests.
    """
    return list(reversed(list(matches)))


def _template_line(raw: str, start: int, token: str) -> str:
    return raw[:start] + BLANK_TOKEN + raw[start + len(token):]


def _starter(solution: str, line_no: int, start: int, token: str) -> str:
    """The blanked statement, prefixed by its enclosing header if there is one.

    A bare ``if total ___ 100:`` is ambiguous without the surrounding signature,
    and the header carries no answer, so including it removes a guess at no cost.
    Only this fragment ships - the rest of the program stays here as the proof
    fixture, so the item cannot hand over the solution.
    """
    lines = solution.split("\n")
    head: list[str] = []
    indent = len(lines[line_no]) - len(lines[line_no].lstrip())
    for prior in reversed(lines[:line_no]):
        stripped = prior.strip()
        if not stripped:
            continue
        prior_indent = len(prior) - len(prior.lstrip())
        if prior_indent < indent and re.match(
                r"^(def|function|class|public|private|fn)\b", stripped):
            head.insert(0, prior)
            break
    return "\n".join(head + [_template_line(lines[line_no], start, token)])


def alternatives_for(solution: str, token: str) -> list[str]:
    """Other tokens a learner could plausibly have written here."""
    if token in OPERATOR_FAMILY:
        pool = [t for t in OPERATOR_FAMILY if t != token]
    elif token in BOOLEAN_FAMILY:
        pool = [t for t in BOOLEAN_FAMILY if t != token]
    else:
        identifiers = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b", solution))
        pool = sorted(i for i in identifiers if i != token and i.lower() not in {
            "true", "false", "none", "self", "print", "return", "import", "class"})
    return pool


def _fill(template_solution: str, line_no: int, start: int, token: str, value: str) -> str:
    lines = template_solution.split("\n")
    raw = lines[line_no]
    lines[line_no] = raw[:start] + value + raw[start + len(token):]
    return "\n".join(lines)


def _prompt(lesson, token_kind: str) -> str:
    objective = (lesson.learning_objectives or [""])[0]
    lead = {
        "operator": "Fill the blank with the operator that makes this code behave as the lesson describes.",
        "boolean": "Fill the blank with the boolean keyword or value this line needs.",
        "call": "Fill the blank with the name this line needs to work.",
        "keyword": "Fill the blank with the keyword this line needs.",
    }[token_kind]
    context = f" {objective.strip()}" if objective and len(objective) <= 160 else ""
    return f"{lead}{context}"


def candidate_for(lesson, language: str, verbose: bool = False) -> dict | None:
    solution = (lesson.solution_code or "").strip()
    tests = [t.model_dump() for t in lesson.tests]
    if not solution or not tests:
        return None

    use_docker = language not in LOCAL_LANGS
    lines = solution.split("\n")

    # The proof is only as good as the fixture: if the lesson's own solution
    # does not pass its own tests, no uniqueness claim about a blank means
    # anything. Checked once, not per candidate site.
    if not passes(language, solution, tests, use_docker):
        if verbose:
            print(f"    - {lesson.id}: the lesson's own solution does not pass its tests")
        return None

    for line_no, start, token, kind in candidate_sites(solution):
        alternatives = alternatives_for(solution, token)
        if len(alternatives) < MIN_ALTERNATIVES_TESTED:
            continue
        failures = 0
        ambiguous = False
        for alt in alternatives:
            variant = _fill(solution, line_no, start, token, alt)
            if variant == solution:
                continue
            try:
                if passes(language, variant, tests, use_docker):
                    ambiguous = True
                    break
            except Exception:
                ambiguous = True
                break
            failures += 1
        if ambiguous or failures < MIN_ALTERNATIVES_TESTED:
            if verbose:
                reason = "is guessable another way" if ambiguous else "had too few alternatives"
                print(f"    - {lesson.id}: line {line_no + 1} blank '{token}' {reason}")
            continue

        item = {
            "id": f"{lesson.id}-fill-1",
            "type": "code_completion",
            "question": _prompt(lesson, kind),
            "starter_code": _starter(solution, line_no, start, token),
            "correct_answer": [token],
            "blanks": [token],
            "explanation": f"`{token}` is what the lesson's own code uses here.",
            "xp_reward": COMPLETION_XP,
        }
        # A stem that quotes the answer is worse than no stem at all, and the
        # objective text is not under our control - so try the next position
        # instead of giving up on the lesson.
        problems = self_check(item)
        if problems:
            if verbose:
                print(f"    - {lesson.id}: line {line_no + 1} blank '{token}' "
                      f"is spoiled by its own stem -> {problems}")
            continue
        item["_proof"] = {"line": line_no + 1, "token": token, "kind": kind,
                          "alternatives_rejected": failures}
        return item
    return None


def _mentions_token(text: str, token: str) -> bool:
    """Token-aware containment.

    A plain substring test is wrong for short answers: blanking the keyword
    ``in`` made every pre-answer field look like a leak because "in" occurs
    inside "Fill", "line" and "behavior". Word characters get a word boundary;
    operators like ``>=`` cannot, so they are matched literally.
    """
    if not token:
        return False
    if re.fullmatch(r"\w+", token):
        return re.search(rf"(?<![\w]){re.escape(token)}(?![\w])", text or "") is not None
    return token in (text or "")


def self_check(item: dict) -> list[str]:
    """The answer must appear nowhere a learner can read it *before* answering.

    ``explanation`` is deliberately not checked: it is post-attempt feedback, and
    naming the token there is the point of it. The full ``starter_leak_audit``
    still runs over the written file afterwards; this is the cheap pre-flight.
    """
    token = item["correct_answer"][0]
    problems: list[str] = []
    for field in ("question", "starter_code"):
        text = item.get(field) or ""
        if _mentions_token(text, token):
            problems.append(f"{field} contains the answer token {token!r}")
    if BLANK_TOKEN not in item["starter_code"]:
        problems.append("starter_code has no blank to fill")
    return problems


def _write(path: Path, lesson_id: str, sublesson: dict) -> bool:
    payload = json.loads(path.read_text(encoding="utf-8"))
    touched = False
    for lesson in payload.get("lessons") or []:
        if lesson.get("id") != lesson_id:
            continue
        existing = {sub.get("id") for sub in lesson.get("sublessons") or []}
        if sublesson["id"] in existing:
            return False
        lesson.setdefault("sublessons", []).append(sublesson)
        lesson["sublessons"].sort(key=lambda s: s.get("order", 1))
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        touched = True
    return touched


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", action="append", default=[], metavar="COURSE/LESSON_ID")
    parser.add_argument("--apply", action="store_true", help="write the accepted items")
    parser.add_argument("--verbose", action="store_true", help="explain every rejection")
    args = parser.parse_args(argv)

    wanted = {o.strip().lower() for o in args.only if o.strip()}
    if not wanted:
        parser.error("refusing to write in bulk: pass one or more --only COURSE/LESSON_ID")

    accepted: list[tuple[str, str, dict]] = []
    for language, curriculum in sorted(load_all_curriculums().items()):
        for lesson in curriculum.lessons:
            if f"{language}/{lesson.id}".lower() not in wanted:
                continue
            if lesson.sublessons:
                print(f"  skip {language}/{lesson.id}: already has graded items")
                continue
            item = candidate_for(lesson, language, verbose=args.verbose)
            if not item:
                print(f"  ✗ {language}/{lesson.id}: no blank survived the uniqueness proof")
                continue
            problems = self_check(item)
            if problems:
                print(f"  ✗ {language}/{lesson.id}: draft rejected -> {problems}")
                continue
            proof = item.pop("_proof")
            print(f"  ✓ {language}/{lesson.id}: line {proof['line']} blank "
                  f"'{proof['token']}' ({proof['kind']}), "
                  f"{proof['alternatives_rejected']} alternatives all fail")
            accepted.append((language, lesson.id, item))

    if not accepted:
        print("\nnothing accepted")
        return 1

    if not args.apply:
        for language, lesson_id, item in accepted:
            print(f"\n[{language}/{lesson_id}] draft\n{json.dumps(item, indent=2)}")
        print("\n(nothing written; pass --apply)")
        return 0

    for path in sorted(CURRICULUM_ROOT.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        ids = {l.get("id") for l in payload.get("lessons") or []}
        for language, lesson_id, item in accepted:
            if lesson_id not in ids:
                continue
            exercise = {k: v for k, v in item.items()}
            sublesson = {
                "id": f"{lesson_id}-fill-sub",
                "title": "Complete the code",
                "order": 1,
                "exercises": [exercise],
            }
            if _write(path, lesson_id, sublesson):
                print(f"  wrote {language}/{lesson_id} -> {path.relative_to(CURRICULUM_ROOT.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
