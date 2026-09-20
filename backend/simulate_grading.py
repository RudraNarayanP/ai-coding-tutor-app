"""Grading-contract simulation for every exercise in every course.

For each exercise we ask the REAL engine grader:
  - does the officially correct answer pass?  (must pass)
  - do plausible wrong answers fail?         (must fail)
  - for code exercises: solution_code must pass, starter_code must fail.

Any mismatch means learners can be marked wrong while correct (or correct
while wrong) — the mission's strictest rule. Run:
  .venv/Scripts/python.exe backend/simulate_grading.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.curriculum_loader import load_all_curriculums  # noqa: E402
from backend.lesson_engine import LessonEngine, ProgressionStore  # noqa: E402


def wrong_mcq_options(ex, correct: str) -> list[str]:
    return [o for o in (ex.options or []) if str(o).strip().lower() != str(correct).strip().lower()]


def payloads(ex, language: str):
    """Yield (label, payload, expected_passed)."""
    t = ex.type.lower().strip()
    ans = ex.correct_answer
    if t in ("mcq", "true_false", "output_prediction", "debugging", "identify_error", "short_answer"):
        yield "correct-option", {"answer": ans}, True
        for opt in wrong_mcq_options(ex, ans)[:2]:
            yield f"wrong-option({opt!r})", {"answer": opt}, False
        yield "wrong-gibberish", {"answer": "__definitely_wrong__"}, not bool(ans)
    elif t in ("fill_blank", "code_completion"):
        expected = ans if isinstance(ans, list) else [ans]
        yield "correct-blanks", {"answers": [str(e) for e in expected]}, True
        yield "wrong-blanks", {"answers": ["__zzz__"] * len(expected)}, False
    elif t == "select_multiple":
        correct = list(ans or [])
        yield "correct-set", {"answers": correct}, True
        yield "subset", {"answers": correct[:-1] or ["__zzz__"]}, False
        yield "superset", {"answers": correct + ["__extra__"]}, False
    elif t == "ordering":
        seq = list(ans or [])
        yield "correct-order", {"order": seq}, True
        yield "reversed", {"order": seq[::-1]}, len(seq) < 2
    elif t == "matching":
        pairs = [{"left": p.left, "right": p.right} for p in (ex.pairs or [])]
        yield "correct-pairs", {"pairs": pairs}, True
        swapped = [{"left": pairs[0]["left"], "right": pairs[-1]["right"]} for _ in pairs] if len(pairs) > 1 else pairs
        yield "swapped-pairs", {"pairs": swapped}, len(pairs) < 2
    elif t in ("code", "tiny_coding", "identify_mistake"):
        if ex.solution_code:
            yield "solution-code", {"code": ex.solution_code}, True
        if ex.starter_code and ex.starter_code.strip():
            yield "starter-code", {"code": ex.starter_code}, False
        yield "empty-code", {"code": ""}, False
    else:
        if ans is not None:
            yield "correct-answer", {"answer": ans}, True
        yield "gibberish", {"answer": "__wrong__"}, False


async def main() -> int:
    import tempfile

    from backend.sandbox import DockerSandbox

    curriculums = load_all_curriculums()
    tmp = Path(tempfile.mkdtemp(prefix="patchwork_simgrade_"))
    engine = LessonEngine(
        DockerSandbox(),
        curriculums=curriculums,
        stores={
            lang: ProgressionStore(curr, storage_path=tmp / f"sim_{lang}_state.json")
            for lang, curr in curriculums.items()
        },
    )

    failures = []
    checked = 0
    for lang, curriculum in curriculums.items():
        for lesson in curriculum.lessons:
            pools = [(sub.id, ex) for sub in lesson.sublessons for ex in sub.exercises]
            pools += [("mastery", ex) for ex in lesson.mastery_exam]
            for _, ex in pools:
                for label, payload, expected in payloads(ex, lang):
                    checked += 1
                    try:
                        passed, feedback = await engine.grade_exercise(ex, payload, lang)
                    except Exception as exc:  # noqa: BLE001
                        failures.append(f"{lang} {lesson.id} {ex.id} [{label}] RAISED {type(exc).__name__}: {exc}")
                        continue
                    if passed != expected:
                        failures.append(
                            f"{lang} {lesson.id} {ex.id} [{label}] expected "
                            f"{'pass' if expected else 'fail'} got {'pass' if passed else 'fail'} :: {feedback[:80]}"
                        )
    print(f"checked {checked} grading scenarios across {sum(len(c.lessons) for c in curriculums.values())} lessons")
    if failures:
        print("MISMATCHES:")
        for f in failures:
            print("  ", f)
        return 1
    print("ALL GRADING CONTRACTS OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
