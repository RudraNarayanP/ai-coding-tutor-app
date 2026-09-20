"""Measure a wave of exercises the way a learner would experience it.

Coverage numbers say how many items exist; this says whether an item actually
works as a learning step. Every policy below drives the real FastAPI app through
`TestClient` (in-process ASGI, real grader, real sandbox subprocesses) with all
writable state redirected to a temp directory, so nothing here can touch a real
learner's progression.

What each policy is for:

* ``competent``   - answers correctly first try: proves the key is accepted and
  the reward path pays exactly once.
* ``first_option``- always taps the first listed option: the chance-pass rate.
  An item a learner can pass by tapping the same position is not measuring
  anything, and this catches it (option display order is hashed per item in the
  UI, so a high rate here means the *stored* order leaks the answer).
* ``near_miss``   - the most plausible wrong answer per type (a rotated match, a
  partial multi-select, the boundary-off output): must always be rejected, or
  the grader is too loose.
* ``struggling``  - wrong, then correct twice: exercises the whole
  miss -> queue -> replay -> graduation loop and the heart charge/refund balance.

Reported per item: first-attempt accuracy by policy, attempts, XP paid, hearts
charged/refunded, whether the miss was queued, whether replay was served, and
whether it graduated. Run with ``--wallclock`` to additionally wait out the real
recall gap and heart-regen interval instead of asserting them from injected
clocks - that is the only honest way to close "wall-clock regeneration
unverified".

    python -m backend.wave_metrics
    python -m backend.wave_metrics --wallclock 6
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import pathlib
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Redirect every writable store before backend.main builds them at import time.
RUN_DIR = Path(tempfile.mkdtemp(prefix="patchwork_metrics_"))
os.environ["PATCHWORK_STATE_DIR"] = str(RUN_DIR)
os.environ["PATCHWORK_PROJECT_DIR"] = str(RUN_DIR / "projects")

from backend import console  # noqa: E402
from backend.answer_order import displayed_options as answer_order_displayed  # noqa: E402
from backend.curriculum_loader import load_all_curriculums  # noqa: E402
from backend.exercise_types import (  # noqa: E402
    CODE_TYPES,
    FILL_TYPES,
    MATCHING_TYPES,
    MULTI_SELECT_TYPES,
    ORDERING_TYPES,
)

console.configure()

WAVE1_IDS = {
    "big-o-step-1-out-1", "stats-zscore-out-1", "js-02-tf-1",
    "sql-11-match-1", "ai-02-multi-1",
}

WAVE2_IDS = {
    "ll-sum-code-1", "graph-repr-match-1", "twosum-hashmap-multi-1",
    "confusion-match-1", "knn-rule-multi-1",
    "dot-code-1", "median-cases-match-1", "standardize-zero-multi-1",
    "ts-annotations-match-1", "ts-narrow-code-1", "ts-generics-multi-1",
    "reducer-dec-code-1",
}

WAVE3_IDS = {
    "bool-or-not-out-1", "division-kinds-match-1", "compare-ops-match-1",
    "elif-boundary-dbg-1", "access-rule-multi-1", "last-digit-code-1",
    "cpp-factorial-code-1", "cpp-vowels-code-1", "cpp-half-value-multi-1",
    "cpp-const-ref-multi-1", "cpp-logic-ops-match-1", "cpp-power-loop-dbg-1",
}

SCOPES = {
    "wave1": WAVE1_IDS, "wave2": WAVE2_IDS, "wave3": WAVE3_IDS,
    "both": WAVE1_IDS | WAVE2_IDS,
    "all": WAVE1_IDS | WAVE2_IDS | WAVE3_IDS,
}

# Which ids the current run measures; set from --scope in main().
MEASURED_IDS = WAVE1_IDS | WAVE2_IDS | WAVE3_IDS


def displayed_options(exercise_id: str, options: list[str]) -> list[str]:
    """The order the learner actually sees.

    Lives in `backend/answer_order.py` with a fixture pinned by both test suites,
    because it mirrors `orderedOptions` in the client: measuring the *stored*
    first option overstates what a learner tapping the leftmost button gets, and
    the first run of this harness did exactly that and called it "first option".
    """
    return answer_order_displayed(exercise_id, options)


def right_payload(exercise) -> dict:
    answer = exercise.correct_answer
    ex_type = str(exercise.type).lower()
    if ex_type in MATCHING_TYPES and isinstance(answer, dict):
        return {"pairs": [{"left": k, "right": v} for k, v in answer.items()]}
    if ex_type in ORDERING_TYPES and isinstance(answer, list):
        return {"order": list(answer)}
    if isinstance(answer, list):
        return {"answers": list(answer)}
    return {"answer": str(answer)}


def near_miss_payload(exercise) -> dict | None:
    """The likeliest wrong answer for this item, by type."""
    ex_type = str(exercise.type).lower()
    answer = exercise.correct_answer
    options = [str(o) for o in (exercise.options or [])]
    if ex_type == "true_false":
        return {"answer": "False" if str(answer).lower() == "true" else "True"}
    if ex_type in ("mcq", "output_prediction", "debugging"):
        others = [o for o in options if o.strip().lower() != str(answer).strip().lower()]
        return {"answer": others[0]} if others else None
    if ex_type in MULTI_SELECT_TYPES and isinstance(answer, list):
        return {"answers": list(answer[:-1])}
    if ex_type in MATCHING_TYPES and isinstance(answer, dict) and len(answer) > 1:
        keys = list(answer)
        rotated = {k: answer[keys[(i + 1) % len(keys)]] for i, k in enumerate(keys)}
        return {"pairs": [{"left": k, "right": v} for k, v in rotated.items()]}
    if ex_type in ORDERING_TYPES and isinstance(answer, list):
        return {"order": list(reversed(answer))}
    if ex_type in FILL_TYPES:
        if isinstance(answer, list):
            return {"answers": ["__nope__" for _ in answer]}
        return {"answer": "__nope__"}
    return None


def first_option_payload(exercise, *, displayed: bool = True) -> dict | None:
    """The answer a learner gets by always choosing the first button.

    ``displayed=True`` is the real exploit - what the client actually renders.
    ``displayed=False`` is the authoring-bias signal: a curriculum that always
    stores its key first is one `rotate`-able edit away from being free, and it
    is what the position-distribution gate measures.
    """
    ex_type = str(exercise.type).lower()
    options = [str(o) for o in (exercise.options or [])]
    if not options:
        return None
    if displayed:
        options = displayed_options(exercise.id, options)
    if ex_type in MULTI_SELECT_TYPES:
        return {"answers": options[:max(1, len(options) // 2)]}
    if ex_type in MATCHING_TYPES:
        pairs = [p for p in (exercise.pairs or [])]
        if not pairs:
            return None
        rights = [str(p.right if hasattr(p, "right") else p["right"]) for p in pairs]
        return {"pairs": [{"left": (p.left if hasattr(p, "left") else p["left"]),
                           "right": rights[0]} for p in pairs]}
    if ex_type in ORDERING_TYPES:
        return {"order": options}          # stored display order
    return {"answer": options[0]}


def iter_wave_items():
    for language, curriculum in sorted(load_all_curriculums().items()):
        for lesson in curriculum.lessons:
            for sub in lesson.sublessons:
                for exercise in sub.exercises:
                    if exercise.id in MEASURED_IDS:
                        yield language, lesson, sub, exercise


def reset_learner(client) -> None:
    """Start each policy from the same clean slate.

    Without this the first pass drains the shared heart pool and later policies
    measure 403s instead of item quality - which is exactly what the first run
    of this harness did.
    """
    from backend.main import heart_store, lesson_engine

    for store in lesson_engine.stores.values():
        store.reset()
        store.clear_mistakes()
    heart_store.refill()


def measure(policy: str, client, items) -> list[dict]:
    rows: list[dict] = []
    for language, lesson, sub, exercise in items:
        ex_type = str(exercise.type).lower()
        if ex_type in CODE_TYPES:
            continue
        payload = {
            "competent": right_payload(exercise),
            "first_shown": first_option_payload(exercise, displayed=True),
            "stored_first": first_option_payload(exercise, displayed=False),
            "near_miss": near_miss_payload(exercise),
        }.get(policy)
        if payload is None:
            continue
        started = time.time()
        response = client.post(
            f"/api/lessons/{lesson.id}/submit-exercise",
            json={"exercise_id": exercise.id, "sublesson_id": sub.id, "payload": payload},
        )
        elapsed = time.time() - started
        if response.status_code != 200:
            rows.append({"item": exercise.id, "policy": policy, "http": response.status_code,
                         "error": json.dumps(response.json())[:160]})
            continue
        body = response.json()
        rows.append({
            "item": exercise.id,
            "course": language,
            "type": ex_type,
            "policy": policy,
            "passed": body.get("passed"),
            "attempt": body.get("attempt_count"),
            "xp": body.get("xp_awarded"),
            "hearts": (body.get("hearts") or {}).get("hearts"),
            "queued": body.get("still_queued"),
            "graduated": body.get("graduated"),
            "next_action": body.get("next_action"),
            "seconds": round(elapsed, 2),
        })
    return rows


def struggling_loop(client, items) -> list[dict]:
    """Wrong -> queued -> replay served -> correct -> correct -> graduated."""
    report = []
    for language, lesson, sub, exercise in items:
        ex_type = str(exercise.type).lower()
        if ex_type in CODE_TYPES:
            continue
        learner = f"m-{uuid.uuid4().hex[:8]}"
        entry: dict = {"item": exercise.id, "course": language, "type": ex_type,
                       "steps": []}
        wrong = near_miss_payload(exercise) or {"answer": "__nope__"}
        hearts_before = client.get("/api/hearts").json()["hearts"]
        first = client.post(f"/api/lessons/{lesson.id}/submit-exercise",
                            json={"exercise_id": exercise.id, "sublesson_id": sub.id,
                                  "payload": wrong, "user_id": learner}).json()
        entry["steps"].append(("miss", first.get("passed"),
                               (first.get("hearts") or {}).get("hearts")))
        served = client.get("/api/mistakes").json()["due"]
        entry["queued_immediately"] = any(s["exercise_id"] == exercise.id for s in served)

        right = right_payload(exercise)
        solves = []
        for _ in range(2):
            res = client.post(f"/api/lessons/{lesson.id}/submit-exercise",
                              json={"exercise_id": exercise.id, "sublesson_id": sub.id,
                                    "payload": right, "user_id": learner}).json()
            solves.append((res.get("passed"), res.get("graduated"),
                           (res.get("hearts") or {}).get("hearts")))
        entry["steps"] += [("solve", *s) for s in solves]
        entry["graduated"] = any(bool(s[1]) for s in solves)
        entry["hearts_before"] = hearts_before
        entry["hearts_after"] = client.get("/api/hearts").json()["hearts"]
        remaining = client.get("/api/mistakes").json()["due"]
        entry["still_due_after"] = any(s["exercise_id"] == exercise.id for s in remaining)
        report.append(entry)
    return report


ANSWER_HINT = re.compile(r'"(answer|correct|is_correct|correct_answer|solution|key)"\s*:')


def leak_probe(client, items) -> list[str]:
    """The wire must not carry the answer designation.

    What counts as a leak is narrower than "the key string appears somewhere":
    for select-multiple, matching and ordering the key *is* a subset of the
    options the learner is shown, so searching for it only ever proves the
    widget is working. The real test is structural - no field that says which
    choice is right (`correct_answer`, `blanks`, `solution_code`, or a bare
    `answer`/`correct` key) may reach the browser. Content-level spoilers are
    the leak audit's job at authoring time, not the transport's.
    """
    problems: list[str] = []
    seen_lessons: set[str] = set()
    for language, lesson, sub, exercise in items:
        if lesson.id in seen_lessons:
            continue
        seen_lessons.add(lesson.id)
        blob = json.dumps(client.get(f"/api/lessons/{lesson.id}").json())
        for needle in ('"correct_answer"', '"blanks"', '"solution_code"'):
            if needle in blob:
                problems.append(f"lesson view of {lesson.id} contains {needle}")
        hint = ANSWER_HINT.search(blob)
        if hint:
            problems.append(f"lesson view of {lesson.id} exposes {hint.group(0)}")
    return problems


# A near-correct implementation per authored code item: the submission a learner
# who half-understood the task would write. Each one passes at least one of the
# item's tests and must still be rejected overall, otherwise the item is only
# checking that something was typed.
# A near-correct implementation per authored code item: the submission a learner
# who half-understood the task would write. Each one passes at least one of the
# item's tests and must still be rejected overall, otherwise the item is only
# checking that something was typed.
NEAR_MISS_CODE = {
    # counts y as a vowel too - passes the empty and "AEIOU" cases, fails the words
    "cpp-vowels-code-1": (
        "#include <string>\n"
        "int count_vowels(std::string s) {\n"
        "    int count = 0;\n"
        "    for (char c : s) {\n"
        "        if (c == 'a' || c == 'e' || c == 'i' || c == 'o' || c == 'u'"
        " || c == 'y') { count++; }\n"
        "    }\n"
        "    return count;\n"
        "}\n"
    ),
    # multiplies n times but starts at 1*1 and stops early for 0! and 1!
    "cpp-factorial-code-1": (
        "long long factorial(int n) {\n"
        "    long long result = n;\n"
        "    for (int i = 2; i < n; ++i) { result *= i; }\n"
        "    return result;\n"
        "}\n"
    ),
    # integer-divides instead of taking the remainder: right idea, wrong operator
    "last-digit-code-1": (
        "def last_digit(n):\n    return n // 10\n"
    ),
    "ll-sum-code-1": (
        "class ListNode:\n"
        "    def __init__(self, value, next=None):\n"
        "        self.value = value\n"
        "        self.next = next\n"
        "\n"
        "def sum_values(head):\n"
        "    return head.value if head is not None else 0\n"
    ),
    "dot-code-1": (
        "def dot(a, b):\n"
        "    return sum(a) + sum(b)\n"
    ),
    "ts-narrow-code-1": (
        "export function describe(input: number | string): string {\n"
        "    return 'number';\n"
        "}\n"
    ),
    "reducer-dec-code-1": (
        "def reduce(state, action):\n"
        "    t = action.get('type')\n"
        "    if t == 'inc':\n"
        "        return {'count': state['count'] + 1}\n"
        "    if t == 'dec':\n"
        "        state['count'] -= 1\n"
        "        return state\n"
        "    return state\n"
    ),
}


def measure_code_items(client, items) -> list[dict]:
    """Drive the code items through the real submit endpoint, three ways."""
    rows: list[dict] = []
    for language, lesson, sub, exercise in items:
        if str(exercise.type).lower() not in CODE_TYPES:
            continue
        cases = [("solution", exercise.solution_code or ""),
                 ("starter", exercise.starter_code or ""),
                 ("near_miss", NEAR_MISS_CODE.get(exercise.id, ""))]
        for name, code in cases:
            if not code:
                continue
            body = client.post(f"/api/lessons/{lesson.id}/exercises/{exercise.id}/run",
                               json={"code": code}).json()
            tests = body.get("tests") or []
            rows.append({
                "item": exercise.id, "course": language, "type": exercise.type,
                "policy": f"code:{name}", "passed": bool(body.get("passed")),
                "tests_passed": f"{sum(1 for t in tests if t.get('passed'))}/{len(tests)}",
                "error": body.get("error"),
            })
    return rows


def wallclock_check(client, minutes: int) -> dict:
    """Measure the real recall timings on the wall clock, not an injected one.

    Two different gaps are easy to conflate, and the first version of this probe
    labelled them wrongly:

    * a **miss** is due *immediately* - ``record_attempt`` sets ``due_at`` to now,
      so "review your misses" has something in it the moment you look;
    * the **300 s recall gap** applies *after the first correct re-solve*, which
      is what makes the second look effortful instead of instant recall.

    This waits for both, plus the 300 s heart regeneration, on real time.
    """
    lesson = next((l for k, c in sorted(load_all_curriculums().items())
                   for l in c.lessons if l.sublessons), None)
    if lesson is None:
        return {"error": "no lesson with exercises"}
    sub = lesson.sublessons[0]
    exercise = sub.exercises[0]
    started = time.time()

    def due_now() -> bool:
        return any(m["exercise_id"] == exercise.id
                   for m in client.get("/api/mistakes").json()["due"])

    def submit(payload: dict) -> dict:
        return client.post(f"/api/lessons/{lesson.id}/submit-exercise",
                           json={"exercise_id": exercise.id, "sublesson_id": sub.id,
                                 "payload": payload}).json()

    result: dict = {"lesson": f"{lesson.id}/{exercise.id}", "budget_minutes": minutes}

    submit({"answer": "__definitely_wrong__"})
    hearts_after_miss = client.get("/api/hearts").json()["hearts"]
    # 1. how long until the miss is offered back? designed to be immediate.
    for _ in range(20):
        if due_now():
            break
        time.sleep(1)
    result["miss_became_due_after_seconds"] = round(time.time() - started)

    # 2. first correct re-solve parks it behind the recall gap. The heart that
    #    the miss cost regenerates over the same window, so one loop observes
    #    both on the same clock instead of measuring them after the fact.
    first = submit(right_payload(exercise))
    result["first_resolve_graduated"] = bool(first.get("graduated"))
    result["parked_immediately_after_resolve"] = not due_now()
    parked_at = time.time()
    deadline = parked_at + minutes * 60
    while time.time() < deadline:
        time.sleep(20)
        now = time.time() - parked_at
        if result.get("recall_gap_observed_seconds") is None and due_now():
            result["recall_gap_observed_seconds"] = round(now)
        status = client.get("/api/hearts").json()
        if status["hearts"] > hearts_after_miss and "heart_regen_observed_seconds" not in result:
            result["heart_regen_observed_seconds"] = round(now)
            result["hearts_after_regen"] = status["hearts"]
        if "recall_gap_observed_seconds" in result and "heart_regen_observed_seconds" in result:
            break
    result.setdefault("recall_gap_observed_seconds", None)

    second = submit(right_payload(exercise))
    result["second_resolve_graduated"] = bool(second.get("graduated"))
    result["queue_emptied"] = not due_now()
    result["total_seconds"] = round(time.time() - started)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wallclock", type=int, default=0,
                        help="minutes to wait for real recall/regen timings")
    parser.add_argument("--scope", default="both", choices=sorted(SCOPES),
                        help="which authored waves to measure")
    parser.add_argument("--json", default="audit/wave1_metrics.json")
    args = parser.parse_args(argv)

    global MEASURED_IDS
    MEASURED_IDS = SCOPES[args.scope]

    from fastapi.testclient import TestClient
    from backend.main import app

    items = list(iter_wave_items())
    print(f"scope: {args.scope} | wave items found: {len(items)} of {len(MEASURED_IDS)} expected")
    for language, lesson, _sub, exercise in items:
        print(f"  {language:10s} {lesson.id:16s} {exercise.id:22s} {exercise.type}")

    with TestClient(app) as client:
        rows: list[dict] = []
        for policy in ("competent", "first_shown", "stored_first", "near_miss"):
            reset_learner(client)
            rows += measure(policy, client, items)
        reset_learner(client)
        code_rows = measure_code_items(client, items)
        reset_learner(client)
        loop = struggling_loop(client, items)
        leaks = leak_probe(client, items)
        wall = wallclock_check(client, args.wallclock) if args.wallclock else None

    if code_rows:
        print("\n== code items through the real run endpoint ==")
        print(f"{'item':24s} {'case':18s} pass  tests")
        for r in code_rows:
            print(f"{r['item']:24s} {r['policy']:18s} {str(r['passed']):5s} {r['tests_passed']}"
                  + (f"  error={r['error']}" if r.get("error") else ""))
        bad = [r for r in code_rows
               if (r["policy"] == "code:solution") != bool(r["passed"])]
        for r in bad:
            leaks.append(f"{r['item']}: {r['policy']} passed={r['passed']} "
                         f"(solution must pass, starter and near-miss must fail)")

    print("\n== per-item behaviour by policy ==")
    print(f"{'item':24s} {'type':17s} {'policy':13s} pass attempt xp hearts queued")
    for r in rows:
        print(f"{r.get('item',''):24s} {r.get('type',''):17s} {r.get('policy',''):13s} "
              f"{str(r.get('passed')):5s} {str(r.get('attempt')):7s} {str(r.get('xp')):3s} "
              f"{str(r.get('hearts')):6s} {str(r.get('queued'))}")

    print("\n== miss -> queue -> replay -> graduation ==")
    for entry in loop:
        print(f"  {entry['item']:24s} queued_now={entry['queued_immediately']} "
              f"graduated={entry['graduated']} hearts {entry['hearts_before']}->"
              f"{entry['hearts_after']} still_due_after={entry['still_due_after']}")

    print("\n== summary ==")
    by_policy = collections.defaultdict(list)
    for r in rows:
        if "passed" in r:
            by_policy[r["policy"]].append(bool(r["passed"]))
    for policy, results in sorted(by_policy.items()):
        rate = sum(results) / len(results) if results else 0
        print(f"  {policy:13s} passed {sum(results)}/{len(results)}  ({rate:.0%})")
    xp_total = sum(r.get("xp") or 0 for r in rows)
    print(f"  xp awarded across all runs: {xp_total} "
          "(includes the lesson/sublesson bonuses each first completion unlocks)")
    print(f"  leak problems: {len(leaks)}")
    for problem in leaks:
        print("    -", problem)
    passable = [r for r in rows
                if r.get("policy") in ("first_shown", "stored_first", "near_miss")
                and r.get("passed")]
    print(f"  items passable by tapping first / authoring bias / near-miss: "
          f"{len(passable)}"
          + (f" -> {sorted({r['item'] + ':' + r['policy'] for r in passable})}" if passable else ""))
    if wall:
        print("\n== wall-clock replay timing (real clock) ==")
        print("  " + json.dumps(wall))

    payload = {"items": [f"{l}/{x.id}" for l, _le, _s, x in items],
               "rows": rows, "loop": loop, "leaks": leaks, "wallclock": wall}
    out = ROOT / args.json
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {out.relative_to(ROOT)}")
    shutil_rmtree(RUN_DIR)
    # A stored-first bias is an authoring-hygiene signal, not a learner
    # exploitable one, so it reports without failing the run; anything a learner
    # can win by tapping the same button, or with a plausible near-miss, fails.
    exploitable = [r for r in rows if r.get("policy") in ("first_shown", "near_miss")
                   and r.get("passed")]
    return 1 if leaks or exploitable else 0


def shutil_rmtree(path: Path) -> None:
    import shutil
    shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
