"""Audit curriculum lessons for starter code that gives the answer away.

Learners practise by writing the body of an exercise. When ``starter_code``
already contains the answer -- either as a ``# TODO:`` comment that quotes the
solution verbatim, or as a body that only needs a literal swapped -- the
exercise is unsolvable-as-designed and the practice is worthless.

Three leak patterns are detected:

``todo_quotes_answer``
    A starter comment whose text is the solution line it replaces, e.g.
    ``# TODO: return replace(cfg, port=port)`` above ``return replace(...)``.

``presolved_body``
    A starter code line that reproduces the answer's structure, differing only
    in literals or identifier names, e.g. ``return { id: 0, active: false }``
    for the answer ``return { id: userId, active: true }``.

``answer_in_prompt``
    The lesson ``description`` quotes the exact answer expression, so the task
    statement hands over the code to type.

Run ``python -m backend.starter_leak_audit`` to print a report, or
``--json`` for machine-readable output. ``--strict`` exits non-zero when any
lesson leaks, which is how ``validate_curriculum.py`` gates it.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

CURRICULUM_ROOT = Path(__file__).resolve().parent.parent / "curriculum"

COMMENT_PREFIX = re.compile(r"^\s*(?://|#|/\*|\*|<!--)")
CODEISH = re.compile(r"[(){},=<>!+\-*/%]|\bself\b|\breturn\b")
TODO_LABEL = re.compile(r"\b(?:TODO|HINT|FIXME|TASK|STEP|NOTE|XXX)\b[:.\-]?\s*", re.IGNORECASE)
LEAD_VERB = re.compile(
    r"^\s*(?:return|resolve|write|create|make|compute|set|define|implement|build|add|set\s+up)\b[:\-]?\s*",
    re.IGNORECASE,
)
LITERAL = re.compile(
    r"'[^']*'|\"[^\"]*\"|\b\d+(?:\.\d+)?\b|\b(?:True|False|None|true|false|null|nil|undefined)\b"
)
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# A body like ``return 0.0;`` or ``pass`` is an honest placeholder, not an answer.
PLACEHOLDER_BODY = re.compile(
    r"^(?:pass|\.\.\.|\{ *\}|return (?:0(?:\.0+)?|None|null|nil|true|false|True|False|\"\"|'')?)\s*;?\s*$"
)

# Signatures and declarations are scaffolding the lesson deliberately hands over.
DECLARATION = re.compile(
    r"^\s*(?:@?(?:public|private|protected|static|async|export|default)\s+)*"
    r"(?:def|function|class|struct|interface|enum|type|import|from|namespace|constructor|new)\b",
    re.IGNORECASE,
)
# Only composite values (objects, arrays, calls with arguments) can spoil a result.
COMPOSITE = re.compile(r"[\[{(]\s*[^\s\]}]")

# Words that describe a requirement rather than spelling out code.
PROSE_HINTS = re.compile(
    r"\b(?:if|when|otherwise|else|only|must|should|both|either|neither|unless|because|so that)\b",
    re.IGNORECASE,
)

TODO_SIMILARITY_FLOOR = 0.90
MIN_SIGNAL_CHARS = 8


@dataclass
class Leak:
    """One starter-code leak found in a lesson or exercise."""

    rule: str
    lesson_id: str
    file: str
    starter_line: str
    answer: str
    similarity: float = 0.0
    scope: str = "lesson"

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "scope": self.scope,
            "lesson_id": self.lesson_id,
            "file": self.file,
            "starter_line": self.starter_line,
            "answer": self.answer,
            "similarity": round(self.similarity, 3),
        }


@dataclass
class LessonView:
    """The starter/solution pair for one lesson, split into lines once."""

    lesson: dict[str, Any]
    path: Path
    starter_lines: list[str] = field(default_factory=list)
    solution_lines: list[str] = field(default_factory=list)
    scope: str = "lesson"

    @property
    def lesson_id(self) -> str:
        return str(self.lesson.get("id", "?"))

    @property
    def has_pair(self) -> bool:
        return bool(self.starter_lines) and bool(self.solution_lines)


def normalise(text: str) -> str:
    """Strip comment markers, TODO labels and punctuation for comparison."""
    text = COMMENT_PREFIX.sub("", text)
    text = TODO_LABEL.sub("", text)
    text = LEAD_VERB.sub("", text)
    return re.sub(r"[^A-Za-z0-9_]+", "", text).lower()


def structure(text: str) -> str:
    """Reduce a line to its shape: literals and names both collapse to ``@``."""
    collapsed = LITERAL.sub("@", text)
    return IDENTIFIER.sub("@", collapsed).strip()


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def iter_raw_lessons(root: Path = CURRICULUM_ROOT) -> Iterable[tuple[Path, dict]]:
    """Yield ``(path, lesson)`` for every lesson object in the curriculum."""
    for path in sorted(root.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        for lesson in payload.get("lessons") or []:
            if isinstance(lesson, dict):
                yield path, lesson


def iter_lessons(root: Path = CURRICULUM_ROOT) -> Iterable[LessonView]:
    """Yield every lesson that carries both starter and solution code."""
    for path, lesson in iter_raw_lessons(root):
        starter = lesson.get("starter_code") or ""
        solution = lesson.get("solution_code") or ""
        if not (starter.strip() and solution.strip()):
            continue
        yield LessonView(
            lesson=lesson,
            path=path,
            starter_lines=starter.splitlines(),
            solution_lines=solution.splitlines(),
        )


# Prose an exercise shows while the learner is still composing. Anything here
# that reproduces the answer key makes the item unsolvable-as-designed.
EXERCISE_PROSE_FIELDS = (
    "question",
    "micro_explanation",
    "worked_example_takeaway",
    "deep_dive",
    "instructions",
    "hints",
    "static_hints",
)


def iter_exercises(root: Path = CURRICULUM_ROOT) -> Iterable[tuple[dict, dict, Path]]:
    """Yield ``(lesson, exercise, path)`` for sublesson and mastery-exam items."""
    for path, lesson in iter_raw_lessons(root):
        groups: list[list] = []
        for sub in lesson.get("sublessons") or []:
            if isinstance(sub, dict):
                groups.append(sub.get("exercises") or [])
        groups.append(lesson.get("mastery_exam") or [])
        for exercises in groups:
            for exercise in exercises:
                if isinstance(exercise, dict):
                    yield lesson, exercise, path


def exercise_code_view(lesson: dict, exercise: dict, path: Path) -> LessonView | None:
    """Wrap an exercise's starter/solution pair in a LessonView for reuse."""
    starter = exercise.get("starter_code") or ""
    solution = exercise.get("solution_code") or ""
    if not (starter.strip() and solution.strip()):
        return None
    merged = dict(exercise)
    merged["id"] = f"{lesson.get('id')}/{exercise.get('id')}"
    return LessonView(
        lesson=merged,
        path=path,
        starter_lines=starter.splitlines(),
        solution_lines=solution.splitlines(),
        scope="exercise",
    )


def answer_tokens(exercise: dict) -> list[str]:
    """The exact strings the learner is expected to produce."""
    tokens: list[str] = []
    for key in ("correct_answer", "blanks"):
        value = exercise.get(key)
        raw = value if isinstance(value, list) else ([value] if isinstance(value, str) else [])
        for item in raw:
            text = str(item).strip()
            if text:
                tokens.append(text)
    return sorted(set(tokens))


def prose_fields(exercise: dict) -> list[tuple[str, str]]:
    """Flatten the pre-submission prose of an exercise to ``(field, text)``."""
    out: list[tuple[str, str]] = []
    for field in EXERCISE_PROSE_FIELDS:
        value = exercise.get(field)
        raw = value if isinstance(value, list) else ([value] if isinstance(value, str) else [])
        for item in raw:
            text = str(item).strip()
            if text:
                out.append((field, text))
    return out


def check_answer_in_exercise_prompt(
    lesson: dict, exercise: dict, path: Path
) -> list[Leak]:
    """Flag fill-blank items whose prompt already contains the answer token."""
    if str(exercise.get("type", "")).lower() not in ("fill_blank", "code_completion"):
        return []
    leaks: list[Leak] = []
    item_id = f"{lesson.get('id')}/{exercise.get('id')}"
    for token in answer_tokens(exercise):
        # Short numeric tokens need word boundaries; identifiers and quoted
        # literals are matched exactly so quote-style lessons still count.
        pattern = re.escape(token)
        if re.fullmatch(r"[A-Za-z0-9_]+", token) and len(token) <= 3:
            pattern = rf"(?<![A-Za-z0-9_]){pattern}(?![A-Za-z0-9_])"
        probe = re.compile(pattern)
        for field, text in prose_fields(exercise):
            if probe.search(text):
                leaks.append(
                    Leak(
                        rule="answer_in_exercise_prompt",
                        lesson_id=item_id,
                        file=str(path),
                        starter_line=f"{field}: {text}",
                        answer=token,
                        similarity=1.0,
                        scope="exercise",
                    )
                )
                break
    return leaks


def check_mcq_answer_in_stem(lesson: dict, exercise: dict, path: Path) -> list[Leak]:
    """Flag multiple choice whose question text names the correct option."""
    if str(exercise.get("type", "")).lower() != "mcq":
        return []
    options = exercise.get("options") or []
    answer = exercise.get("correct_answer")
    if not isinstance(options, list) or not isinstance(answer, str):
        return []
    stem = " ".join(text for _, text in prose_fields(exercise))
    if answer not in options:
        return []
    probe = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(answer)}(?![A-Za-z0-9_])")
    if probe.search(stem):
        return [
            Leak(
                rule="mcq_answer_in_stem",
                lesson_id=f"{lesson.get('id')}/{exercise.get('id')}",
                file=str(path),
                starter_line=stem[:120],
                answer=answer,
                similarity=1.0,
                scope="exercise",
            )
        ]
    return []


def check_worked_example_is_answer(
    lesson: dict, exercise: dict, path: Path, solution: str
) -> list[Leak]:
    """Flag a worked example that is byte-for-byte the answer to type."""
    worked = str(exercise.get("worked_example") or "").strip()
    if not worked or not solution.strip():
        return []
    if normalise(worked) and normalise(worked) == normalise(solution):
        return [
            Leak(
                rule="worked_example_is_answer",
                lesson_id=f"{lesson.get('id')}/{exercise.get('id')}",
                file=str(path),
                starter_line=worked,
                answer=solution.strip(),
                similarity=1.0,
                scope="exercise",
            )
        ]
    return []


def audit_exercises(root: Path = CURRICULUM_ROOT) -> list[Leak]:
    """Audit every sublesson and mastery-exam item for answer leaks."""
    leaks: list[Leak] = []
    for lesson, exercise, path in iter_exercises(root):
        view = exercise_code_view(lesson, exercise, path)
        if view is not None:
            answers = answer_lines(view)
            for leak in (
                *check_todo_quotes_answer(view, answers),
                *check_presolved_body(view, answers),
            ):
                leaks.append(
                    Leak(
                        rule=f"exercise_{leak.rule}",
                        lesson_id=leak.lesson_id,
                        file=leak.file,
                        starter_line=leak.starter_line,
                        answer=leak.answer,
                        similarity=leak.similarity,
                        scope="exercise",
                    )
                )
            leaks.extend(
                check_worked_example_is_answer(lesson, exercise, path, view.lesson["solution_code"])
            )
        leaks.extend(check_answer_in_exercise_prompt(lesson, exercise, path))
        leaks.extend(check_mcq_answer_in_stem(lesson, exercise, path))
    return leaks


def has_answer_literal(text: str) -> bool:
    """True when a line carries a quoted literal worth comparing verbatim."""
    return bool(re.search(r'"[^"]{2,}"|\'[^\']{2,}\'', text))


def answer_lines(view: LessonView) -> list[str]:
    """Solution code lines the learner is expected to write themselves.

    A solution line counts as "answer" when no starter code line normalises to
    it. Comments never count as scaffolding, so a ``# TODO: <answer>`` cannot
    mask the very line it spoils. Lines carrying a quoted literal are kept even
    when they normalise to almost nothing, so ``return "C++";`` still counts.
    """
    starter_code_norms = {
        normalise(line)
        for line in view.starter_lines
        if not COMMENT_PREFIX.match(line) and normalise(line)
    }
    return [
        line.strip()
        for line in view.solution_lines
        if not COMMENT_PREFIX.match(line)
        and normalise(line) not in starter_code_norms
        and (len(normalise(line)) >= MIN_SIGNAL_CHARS or has_answer_literal(line))
    ]


def check_todo_quotes_answer(view: LessonView, answers: list[str]) -> list[Leak]:
    """Flag starter comments that are the answer code in a different font."""
    leaks: list[Leak] = []
    for line in view.starter_lines:
        if not COMMENT_PREFIX.match(line) or not CODEISH.search(line):
            continue
        if PROSE_HINTS.search(line):
            continue
        text = normalise(line)
        best = max(
            ((similarity(text, normalise(answer)), answer) for answer in answers),
            key=lambda pair: pair[0],
            default=(0.0, ""),
        )
        if len(text) >= MIN_SIGNAL_CHARS and best[0] >= TODO_SIMILARITY_FLOOR:
            leaks.append(
                Leak(
                    rule="todo_quotes_answer",
                    lesson_id=view.lesson_id,
                    file=str(view.path),
                    starter_line=line.strip(),
                    answer=best[1],
                    similarity=best[0],
                    scope=view.scope,
                )
            )
            continue
        # Short answers such as ``"C++"`` collapse to almost nothing once
        # punctuation is stripped, so compare the quoted literal verbatim.
        for answer in answers:
            literal = re.search(r'"[^"]{2,}"|\'[^\']{2,}\'', answer)
            if literal and literal.group() in line:
                leaks.append(
                    Leak(
                        rule="todo_quotes_answer",
                        lesson_id=view.lesson_id,
                        file=str(view.path),
                        starter_line=line.strip(),
                        answer=answer.strip(),
                        similarity=1.0,
                        scope=view.scope,
                    )
                )
                break
        else:
            # An expression answer with no string literal (`numbers.map(n => n * 2)`)
            # still spoils when the comment reproduces it: after normalisation the
            # comment body appears verbatim inside the answer line. Restricted to
            # comments that look like an expression (an operator or a call) so a
            # pointer like "set self.elapsed" — which names a field, not a formula
            # — is not treated as a spoiler.
            expression_like = bool(re.search(r"[\(\[\*+/=<>-]", TODO_LABEL.sub("", line)))
            if expression_like:
                for answer in answers:
                    if len(text) >= MIN_SIGNAL_CHARS and text in normalise(answer):
                        leaks.append(
                            Leak(
                                rule="todo_quotes_answer",
                                lesson_id=view.lesson_id,
                                file=str(view.path),
                                starter_line=line.strip(),
                                answer=answer.strip(),
                                similarity=1.0,
                                scope=view.scope,
                            )
                        )
                        break
    return leaks


def check_presolved_body(view: LessonView, answers: list[str]) -> list[Leak]:
    """Flag starter code that already has the answer's shape filled in."""
    leaks: list[Leak] = []
    for line in view.starter_lines:
        if COMMENT_PREFIX.match(line) or DECLARATION.match(line):
            continue
        body = line.strip()
        if PLACEHOLDER_BODY.match(body) or len(normalise(body)) < MIN_SIGNAL_CHARS:
            continue
        if not COMPOSITE.search(body):
            continue
        shape = structure(body)
        for answer in answers:
            if DECLARATION.match(answer) or normalise(body) == normalise(answer):
                continue
            if shape == structure(answer) and shape.count("@") >= 3:
                leaks.append(
                    Leak(
                        rule="presolved_body",
                        lesson_id=view.lesson_id,
                        file=str(view.path),
                        starter_line=body,
                        answer=answer.strip(),
                        similarity=similarity(normalise(body), normalise(answer)),
                        scope=view.scope,
                    )
                )
                break
    return leaks


def audit_lesson(view: LessonView) -> list[Leak]:
    """Run every leak rule against one lesson.

    The lesson ``description`` is deliberately not inspected: a task statement
    has to say what the finished function returns, so quoting an expected
    format there is a spec rather than a spoiler.
    """
    if not view.has_pair:
        return []
    answers = answer_lines(view)
    if not answers:
        return []
    return [
        *check_todo_quotes_answer(view, answers),
        *check_presolved_body(view, answers),
    ]


def mcq_position_bias(root: Path = CURRICULUM_ROOT) -> list[Leak]:
    """Flag a curriculum whose MCQ answers all sit in the same slot.

    The client used to render ``options`` in stored order, so a curriculum that
    keeps the correct choice at index 0 hands every answer to a learner who
    always taps the first button. ``orderedOptions`` now shuffles display order,
    but a lopsided authoring distribution still means generated and hand-authored
    courses share one degenerate answer key.
    """
    positions: dict[int, int] = {}
    total = 0
    sample = ""
    for _, exercise, path in iter_exercises(root):
        if str(exercise.get("type", "")).lower() != "mcq":
            continue
        options = exercise.get("options") or []
        answer = exercise.get("correct_answer")
        if not isinstance(options, list) or not isinstance(answer, str) or answer not in options:
            continue
        index = options.index(answer)
        positions[index] = positions.get(index, 0) + 1
        total += 1
        if index == 0 and not sample:
            sample = str(exercise.get("id"))
    if total < 5:
        return []
    dominant_index, dominant_count = max(positions.items(), key=lambda item: item[1])
    if dominant_count / total < 0.6:
        return []
    return [
        Leak(
            rule="mcq_answer_position_bias",
            lesson_id=f"{dominant_count}/{total} MCQs answer option {dominant_index + 1}",
            file=str(root),
            starter_line=f"example: {sample}",
            answer=f"correct option index {dominant_index}",
            similarity=dominant_count / total,
            scope="curriculum",
        )
    ]


def true_false_polarity(root: Path = CURRICULUM_ROOT) -> list[Leak]:
    """Flag a curriculum whose true/false items all answer the same way.

    Unlike MCQ options, `True`/`False` are deliberately rendered in fixed order
    (``orderedOptions`` skips lists shorter than three), so stored polarity *is*
    display position. Measured on wave 1: both true/false items answered "True"
    and the always-tap-the-first-option learner passed 2 of 2. A balanced set is
    fine; a curriculum where the answer is always the first button asks nothing.
    """
    tally: dict[str, int] = {}
    total = 0
    for _lesson, exercise, _path in iter_exercises(root):
        if str(exercise.get("type", "")).lower() != "true_false":
            continue
        answer = str(exercise.get("correct_answer", "")).strip().lower()
        if answer not in ("true", "false"):
            continue
        tally[answer] = tally.get(answer, 0) + 1
        total += 1
    if total < 2 or len(tally) > 1:
        return []
    (polarity, count), = tally.items()
    return [
        Leak(
            rule="true_false_polarity",
            lesson_id=f"{count}/{total} true_false items answer '{polarity.title()}'",
            file=str(root),
            starter_line="true/false options are shown in fixed order",
            answer=polarity,
            similarity=count / total,
            scope="curriculum",
        )
    ]


def answer_position_bias(root: Path = CURRICULUM_ROOT) -> list[Leak]:
    """Flag a single-choice type whose answers pile up in one slot.

    Same hazard as ``mcq_answer_position_bias``, applied to the other types that
    carry a string key and a list of options - `output_prediction` and
    `debugging`. Wave 3 measurement found all three debugging items stored their
    key first: harmless while the client shuffles display order, but the store is
    then one edit, one export or one non-shuffling renderer away from being free,
    and a lopsided store makes the position impossible to reason about in review.
    Small samples are skipped except when every item agrees: 3 of 3 in one slot
    is not a coincidence, it is the authoring habit this rule exists to catch.
    """
    buckets: dict[str, dict[int, int]] = {}
    for _lesson, exercise, _path in iter_exercises(root):
        kind = str(exercise.get("type", "")).lower()
        if kind not in ("output_prediction", "debugging"):
            continue
        options = exercise.get("options") or []
        answer = exercise.get("correct_answer")
        if not isinstance(options, list) or not isinstance(answer, str) \
                or answer not in options:
            continue
        positions = buckets.setdefault(kind, {})
        index = options.index(answer)
        positions[index] = positions.get(index, 0) + 1

    leaks: list[Leak] = []
    for kind, positions in sorted(buckets.items()):
        total = sum(positions.values())
        if total < 3:
            continue
        dominant_index, dominant_count = max(positions.items(), key=lambda item: item[1])
        lopsided = dominant_count / total >= 0.6 and total >= 5
        unanimous = dominant_count == total
        if not (lopsided or unanimous):
            continue
        leaks.append(Leak(
            rule="answer_position_bias",
            lesson_id=f"{dominant_count}/{total} {kind} items answer option "
                      f"{dominant_index + 1}",
            file=str(root),
            starter_line="store is lopsided even though the client shuffles display order",
            answer=f"correct option index {dominant_index}",
            similarity=dominant_count / total,
            scope="curriculum",
        ))
    return leaks


def displayed_answer_first(root: Path = CURRICULUM_ROOT) -> list[Leak]:
    """Flag items whose correct choice is the *first button the client renders*.

    The client hides stored order with a deterministic per-exercise hash, so a
    balanced store is not enough on its own: for a given item id the shuffle can
    still paint the key first. Wave 3 measurement found exactly one such item
    (`big-o-step-1-out-1`), winnable by always tapping the leftmost option.
    The browser never sees `correct_answer`, so only the store can fix this -
    hence a gate rather than a renderer change.
    """
    from .answer_order import key_shown_first

    leaks: list[Leak] = []
    for _lesson, exercise, path in iter_exercises(root):
        options = exercise.get("options") or []
        answer = exercise.get("correct_answer")
        if not isinstance(options, list) or not isinstance(answer, str):
            continue
        if len(options) < 3 or answer not in options:
            continue
        if str(exercise.get("type", "")).lower() not in ("mcq", "output_prediction",
                                                        "debugging"):
            # select_multiple is excluded on purpose: its key is a set, and the
            # first-tap behaviour (one option selected) can never equal a
            # multi-answer key, so there is nothing to hide here.
            continue
        if key_shown_first(str(exercise.get("id")), options, answer):
            leaks.append(Leak(
                rule="displayed_answer_first",
                lesson_id=str(exercise.get("id")),
                file=str(path),
                starter_line="the shuffled display puts the correct choice in the first slot",
                answer=answer[:60],
                similarity=1.0,
                scope="exercise",
            ))
    return leaks


def audit(root: Path = CURRICULUM_ROOT) -> list[Leak]:
    """Audit every curriculum lesson and exercise; return all leaks found."""
    leaks: list[Leak] = []
    for view in iter_lessons(root):
        leaks.extend(audit_lesson(view))
    leaks.extend(audit_exercises(root))
    leaks.extend(mcq_position_bias(root))
    leaks.extend(answer_position_bias(root))
    leaks.extend(true_false_polarity(root))
    leaks.extend(displayed_answer_first(root))
    return leaks


def leaked_lessons(leaks: list[Leak]) -> set[tuple[str, str]]:
    """Return the ``(file, lesson_id)`` pairs that leak their answer."""
    return {(leak.file, leak.lesson_id) for leak in leaks}


def summarise(leaks: list[Leak]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for leak in leaks:
        counts[leak.rule] = counts.get(leak.rule, 0) + 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--curriculum", type=Path, default=CURRICULUM_ROOT)
    parser.add_argument("--json", action="store_true", help="emit machine-readable findings")
    parser.add_argument("--strict", action="store_true", help="exit non-zero on any leak")
    args = parser.parse_args(argv)

    leaks = audit(args.curriculum)

    if args.json:
        print(json.dumps([leak.as_dict() for leak in leaks], indent=2))
    else:
        for leak in sorted(leaks, key=lambda item: (item.rule, item.file, item.lesson_id)):
            print(f"{leak.rule}  {leak.file} :: {leak.lesson_id}")
            print(f"    starter: {leak.starter_line[:120]}")
            print(f"    answer : {leak.answer[:120]}")
        print(
            f"\n{len(leaks)} leaks in {len(leaked_lessons(leaks))} lessons"
            if leaks
            else "\nno starter-code leaks found"
        )
        for rule, count in sorted(summarise(leaks).items()):
            print(f"  {rule}: {count}")

    return 1 if (args.strict and leaks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
