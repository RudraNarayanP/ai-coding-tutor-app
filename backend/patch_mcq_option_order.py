"""Rebalance stored option order so no single position holds the answer.

History: every hand-authored MCQ used to store its correct choice at index 0,
and the client rendered ``options`` in stored order - so always tapping the
first button answered the whole catalogue. ``ExerciseAnswerInput.orderedOptions``
now shuffles *display* order deterministically per exercise id, which is why a
lopsided store is no longer directly exploitable in the app.

It is still worth fixing, and this pass generalises the rebalancer beyond mcq to
every single-choice type with a string key (mcq, output_prediction, debugging):

* anything that reads the JSON directly - generated courses, exports, tests,
  a future screen that renders stored order - inherits the bias;
* the audit that measures items cannot tell "the author always writes the key
  first" from a coincidence unless the store is balanced;
* ``true_false`` is deliberately excluded because two options are *not* shuffled
  by the client, and that case is policed by the stricter
  ``starter_leak_audit.true_false_polarity`` rule instead.

Option text and ``correct_answer`` are untouched; only their order changes, and
grading matches by value, so this cannot change any item's difficulty.

    python -m backend.patch_mcq_option_order            # report + rewrite
    python -m backend.patch_mcq_option_order --dry-run
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from backend.answer_order import reorder_so_key_is_not_first

CURRICULUM = Path(__file__).resolve().parent.parent / "curriculum"

SINGLE_CHOICE_TYPES = ("mcq", "output_prediction", "debugging")


def exercises_of(lesson):
    for sub in lesson.get("sublessons") or []:
        yield from sub.get("exercises") or []
    yield from lesson.get("mastery_exam") or []


def rotate(options: list[str], answer: str, target: int) -> list[str]:
    rest = [opt for opt in options if opt != answer]
    target = max(0, min(target, len(rest)))
    return rest[:target] + [answer] + rest[target:]


def collect():
    found: list[tuple[Path, dict, dict, list[str], str]] = []
    for path in sorted(CURRICULUM.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        for lesson in payload.get("lessons") or []:
            if not isinstance(lesson, dict):
                continue
            for exercise in exercises_of(lesson):
                if str(exercise.get("type", "")).lower() not in SINGLE_CHOICE_TYPES:
                    continue
                options = exercise.get("options") or []
                answer = exercise.get("correct_answer")
                if (isinstance(options, list) and isinstance(answer, str)
                        and answer in options and len(options) > 1):
                    found.append((path, payload, exercise, options, answer))
    return found


def histogram(items) -> dict[tuple[str, int], int]:
    """Answer-position distribution read from the *current* exercise data.

    Reading the option list captured at collect() time instead would report the
    same histogram before and after, which is exactly how a first draft of this
    script hid whether the rotation had done anything at all.
    """
    out: collections.Counter = collections.Counter()
    for _path, _payload, exercise, _options, answer in items:
        current = exercise.get("options") or []
        if answer not in current:
            continue
        out[(str(exercise.get("type")).lower(), current.index(answer))] += 1
    return dict(sorted(out.items()))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    items = collect()
    print(f"{len(items)} single-choice items "
          f"({', '.join(SINGLE_CHOICE_TYPES)}); answer positions before:")
    for (kind, position), count in histogram(items).items():
        print(f"  {kind:18s} index {position}: {count}")

    # Spread each type's answers across positions in proportion to how many
    # slots that item has, so a 4-option item can place its key in 0..3 and the
    # counts stay roughly even.
    changed_files: set[Path] = set()
    per_type: collections.Counter = collections.Counter()
    for path, payload, exercise, options, answer in items:
        kind = str(exercise.get("type")).lower()
        index = per_type[kind]
        per_type[kind] += 1
        target = (index * 7 + 3) % len(options)
        new_options = rotate(options, answer, target)
        if new_options != options:
            exercise["options"] = new_options
            changed_files.add(path)

    if not args.dry_run:
        for path in sorted(changed_files):
            payload = next(p for f, p, *_rest in items if f == path)
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")

    # Spreading the store is only half the job. The client reshuffles per
    # exercise id, so a balanced store can still paint the key in the first
    # rendered slot - which is a learner-passable item. Rotate those few until
    # the displayed first option is not the answer.
    hidden = 0
    dirty_files: set[Path] = set()
    for path, payload, exercise, _options, answer in items:
        current = exercise.get("options") or []
        fixed = reorder_so_key_is_not_first(str(exercise.get("id")), current, answer)
        if fixed != current:
            exercise["options"] = fixed
            hidden += 1
            dirty_files.add(path)
    if not args.dry_run:
        for path in sorted(dirty_files):
            payload = next(p for f, p, *_rest in items if f == path)
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")

    print(f"\n{len(items)} items considered, {len(changed_files)} files "
          f"{'to rewrite' if args.dry_run else 'rewritten'}, "
          f"{hidden} items whose key sat in the first rendered slot "
          f"({'would be' if args.dry_run else 'were'}) moved")
    print("answer positions after:")
    for (kind, position), count in histogram(items).items():
        print(f"  {kind:18s} index {position}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
