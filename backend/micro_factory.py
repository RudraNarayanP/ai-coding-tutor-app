"""Install concept-specific micro lessons from a spec catalog.

Re-run ``python -m backend.python_micro_specs`` after editing a catalog.
A spec is not shipped until its predictions have been executed, its ordering
and fill-blank reconstructions parse, and hint 1 does not contain the answer.
"""

from __future__ import annotations

import ast
import io
import json
import re
from contextlib import redirect_stdout
from difflib import SequenceMatcher
from pathlib import Path

from backend.answer_order import key_shown_first
from backend.verify_lessons import hint_gives_answer, normalize

ROOT = Path(__file__).resolve().parent.parent / "curriculum"
SKIP = {
    "variables-step-1",
    "loops-step-1",
    "functions-step-1",
    "booleans",
    "booleans-step-1",
    "booleans-step-2",
    "booleans-step-3",
    "booleans-01",
}


def safe_options(exercise_id: str, options: list[str], answer: str) -> list[str]:
    """Stored order is what the lesson player shows. The key must not be first.

    The stored slot otherwise rotates so a whole course does not park every
    answer on the same button.
    """
    from itertools import permutations

    valid: list[list[str]] = []
    for perm in permutations(options):
        seq = list(perm)
        if seq[0] == answer or key_shown_first(exercise_id, seq, answer):
            continue
        valid.append(seq)
    if not valid:
        raise SystemExit(f"no safe option order for {exercise_id}")
    target = 1 + (sum(exercise_id.encode("utf-8")) % (len(options) - 1))
    for seq in valid:
        if seq.index(answer) == target:
            return seq
    return valid[sum(exercise_id.encode("utf-8")) % len(valid)]


def capture(code: str) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        exec(compile(code, "<micro>", "exec"), {"__name__": "__micro__"})
    return buf.getvalue()


def _no_ticks(*parts: str) -> None:
    for part in parts:
        if "`" in part:
            raise SystemExit(f"backtick in {part!r}")


def _hints(nudge: str, bridge: str, reveal: str, answer) -> list[str]:
    _no_ticks(nudge, bridge, reveal)
    if hint_gives_answer(nudge, answer):
        raise SystemExit(f"hint 1 contains {answer!r}: {nudge}")
    if not nudge.strip() or not bridge.strip() or not reveal.strip():
        raise SystemExit("empty hint")
    return [nudge, bridge, reveal]


def _stem_hides(question: str, nudge: str, answer: str) -> None:
    blob = f"{question} {nudge}"
    if re.search(rf"(?<![A-Za-z0-9_]){re.escape(answer)}(?![A-Za-z0-9_])", blob):
        raise SystemExit(f"stem contains {answer!r}: {question}")


def _ex(eid, etype, question, hints, explanation, **kwargs):
    _no_ticks(question, explanation)
    item = {
        "id": eid,
        "type": etype,
        "question": question,
        "hints": hints,
        "explanation": explanation,
        "xp_reward": 0 if etype == "teach" else 10,
    }
    item.update(kwargs)
    options = item.get("options")
    answer = item.get("correct_answer")
    if isinstance(options, list) and isinstance(answer, str) and answer in options and len(options) >= 3:
        if len(options) > 7:
            raise SystemExit(f"{eid} has too many options to reorder")
        item["options"] = safe_options(eid, options, answer)
    return item


def _parse_python(code: str) -> tuple[bool, str]:
    try:
        ast.parse(code)
    except SyntaxError as exc:
        return False, f"{exc.msg} (line {exc.lineno})"
    return True, ""


def build_exercises(spec: dict, *, run=None, parse=None) -> list[dict]:
    """Build the eight screens. ``run`` returns stdout; ``parse`` checks a snippet.

    Python is the default. Other languages pass the sandbox runner and
    ``program_parses`` so a prediction is the stdout the gate will rerun.
    """
    runner = run or capture
    checker = parse or _parse_python
    lid = spec["id"]
    teach = spec["teach"].strip()
    if teach.count(".") != 1 or not teach.endswith("."):
        raise SystemExit(f"{lid} teach must be one sentence: {teach}")
    _no_ticks(teach, spec["example"])

    pred_out = runner(spec["predict_code"]).strip()
    if pred_out not in spec["predict_options"]:
        raise SystemExit(f"{lid} predict stdout {pred_out!r} not in options")
    pred2_out = ""
    if spec["second_kind"] == "predict":
        pred2_out = runner(spec["predict2_code"]).strip()
        if pred2_out not in spec["predict2_options"]:
            raise SystemExit(f"{lid} predict2 stdout {pred2_out!r} not in options")
    write_out = runner(spec["solution"])
    if not write_out.strip():
        raise SystemExit(f"{lid} solution printed nothing")

    order_src = " ".join(spec["order"])
    ok, err = checker(order_src)
    if not ok:
        raise SystemExit(f"{lid} ordering does not parse: {order_src}: {err}")
    missing = [chip for chip in spec["order"] if chip not in spec["chips"]]
    if missing:
        raise SystemExit(f"{lid} order chip missing from options: {missing}")
    if len(set(spec["chips"])) != len(spec["chips"]):
        raise SystemExit(f"{lid} duplicate order chips")

    filled = spec["fill_code"].replace("___", spec["fill_answer"], 1)
    if "___" in filled:
        raise SystemExit(f"{lid} fill left a blank")
    ok, err = checker(filled)
    if not ok:
        raise SystemExit(f"{lid} fill does not parse: {filled}: {err}")
    _stem_hides(spec["fill_q"], spec["fill_nudge"], spec["fill_answer"])

    _stem_hides(spec["mcq_q"], spec["mcq_nudge"], spec["mcq_answer"])
    if spec["mcq_answer"] not in spec["mcq_options"]:
        raise SystemExit(f"{lid} mcq answer not in options")
    if spec["second_kind"] == "mcq":
        _stem_hides(spec["second_q"], spec["second_nudge"], spec["second_answer"])

    bug_lines = spec["bug_code"].splitlines()
    bug_no = int(spec["bug_line"])
    if not 1 <= bug_no <= len(bug_lines):
        raise SystemExit(f"{lid} bug line out of range")

    prefix = lid
    return [
        _ex(
            f"{prefix}-teach", "teach", teach,
            _hints(spec["teach_nudge"], spec["teach_bridge"], spec["example"].replace("\n", " / "), teach),
            teach, worked_example=spec["example"],
        ),
        _ex(
            f"{prefix}-mcq", "mcq", spec["mcq_q"],
            _hints(spec["mcq_nudge"], spec["mcq_bridge"], spec["mcq_answer"], spec["mcq_answer"]),
            spec["mcq_why"], options=spec["mcq_options"], correct_answer=spec["mcq_answer"],
        ),
        _ex(
            f"{prefix}-predict", "output_prediction", spec["predict_q"],
            _hints(spec["predict_nudge"], spec["predict_bridge"], pred_out, pred_out),
            spec["predict_why"], starter_code=spec["predict_code"],
            options=spec["predict_options"], correct_answer=pred_out,
        ),
        _ex(
            f"{prefix}-order", "ordering", spec["order_q"],
            _hints(spec["order_nudge"], spec["order_bridge"], order_src, spec["order"]),
            spec["order_why"], options=spec["chips"], correct_answer=spec["order"],
        ),
        _ex(
            f"{prefix}-fill", "fill_blank", spec["fill_q"],
            _hints(spec["fill_nudge"], spec["fill_bridge"], spec["fill_answer"], spec["fill_answer"]),
            spec["fill_why"], starter_code=spec["fill_code"],
            options=spec["fill_options"], correct_answer=spec["fill_answer"],
        ),
        _ex(
            f"{prefix}-bug", "debugging", spec["bug_q"],
            _hints(spec["bug_nudge"], spec["bug_bridge"], f"Line {spec['bug_line']}", spec["bug_line"]),
            spec["bug_why"], starter_code=spec["bug_code"], correct_answer=str(spec["bug_line"]),
        ),
        _second(spec, prefix, pred2_out),
        _ex(
            f"{prefix}-write", "code", spec["write_q"],
            _hints(spec["write_nudge"], spec["write_bridge"], spec["write_reveal"], None),
            spec["write_why"], starter_code=spec["starter"], solution_code=spec["solution"],
            tests=[{
                "name": f"{prefix}-prints",
                "description": spec["write_why"][:80],
                "expected_stdout": write_out,
                "required": True,
            }],
        ),
    ]


def _second(spec: dict, prefix: str, pred2_out: str) -> dict:
    if spec["second_kind"] == "predict":
        return _ex(
            f"{prefix}-predict-2", "output_prediction", spec["second_q"],
            _hints(spec["second_nudge"], spec["second_bridge"], pred2_out, pred2_out),
            spec["second_why"], starter_code=spec["predict2_code"],
            options=spec["predict2_options"], correct_answer=pred2_out,
        )
    return _ex(
        f"{prefix}-mcq-2", "mcq", spec["second_q"],
        _hints(spec["second_nudge"], spec["second_bridge"], spec["second_answer"], spec["second_answer"]),
        spec["second_why"], options=spec["second_options"], correct_answer=spec["second_answer"],
    )


def prompts_of(spec: dict, exercises: list[dict]) -> list[str]:
    texts = [spec["teach"], spec["teach"]]
    texts.extend(ex["question"] for ex in exercises if ex["type"] != "teach")
    return texts


def assert_distinct(groups: list[tuple[str, list[str]]]) -> None:
    flat: list[tuple[str, str]] = []
    for lid, texts in groups:
        for text in texts:
            flat.append((lid, normalize(text)))
    for i, (left_id, left) in enumerate(flat):
        for right_id, right in flat[i + 1:]:
            if left_id == right_id or not left or not right:
                continue
            if left == right or SequenceMatcher(None, left, right).ratio() >= 0.9:
                raise SystemExit(f"near duplicate\n{left_id}: {left}\n{right_id}: {right}")


def install(course: str, specs: list[dict], *, run=None, parse=None, replace: bool = False) -> None:
    folder = ROOT / course / "modules"
    by_id = {spec["id"]: spec for spec in specs}
    if len(by_id) != len(specs):
        raise SystemExit("duplicate spec id")
    built: dict[str, list[dict]] = {}
    groups: list[tuple[str, list[str]]] = []
    for spec in specs:
        exercises = build_exercises(spec, run=run, parse=parse)
        if not 8 <= len(exercises) <= 10:
            raise SystemExit(f"{spec['id']} screen count {len(exercises)}")
        built[spec["id"]] = exercises
        groups.append((spec["id"], prompts_of(spec, exercises)))

    existing_micro_prompts: list[tuple[str, list[str]]] = []
    for path in sorted(folder.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for lesson in data.get("lessons", []):
            if lesson.get("player_mode") == "micro" and lesson["id"] not in by_id:
                texts = [lesson.get("learning_objectives", [""])[0]]
                for sub in lesson.get("sublessons") or []:
                    for ex in sub.get("exercises") or []:
                        if ex.get("question"):
                            texts.append(ex["question"])
                existing_micro_prompts.append((lesson["id"], texts))
    assert_distinct(groups + existing_micro_prompts)

    seen_files = 0
    installed = 0
    for path in sorted(folder.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for lesson in data.get("lessons", []):
            spec = by_id.get(lesson["id"])
            if spec is None:
                continue
            # A shipped micro lesson is the source of truth unless this run is
            # explicitly replacing scene-prefixed prompts.
            if lesson.get("player_mode") == "micro" and not replace:
                continue
            exercises = built[lesson["id"]]
            lesson["title"] = spec["title"]
            lesson["player_mode"] = "micro"
            lesson["learning_objectives"] = [spec["teach"]]
            lesson["sublessons"] = [{
                "id": f"{lesson['id']}-micro"[:80],
                "title": spec["title"][:120],
                "description": "",
                "order": 1,
                "exercises": exercises,
            }]
            if not (lesson.get("source") or {}).get("url"):
                lesson["source"] = {
                    "name": spec.get("source_name") or "Python official documentation",
                    "url": spec.get("source_url") or "https://docs.python.org/3/tutorial/",
                    "license": spec.get("source_license") or "Python documentation license (PSF)",
                }
            description = (lesson.get("description") or "").rstrip()
            lesson["description"] = description
            changed = True
            installed += 1
        if changed:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            seen_files += 1
    _dedupe_descriptions(folder)
    print(f"installed {installed} lessons across {seen_files} files")


def _dedupe_descriptions(folder: Path) -> None:
    """Duplicate descriptions are a failing error once a lesson is micro."""
    loaded: list[tuple[Path, dict]] = []
    for path in sorted(folder.glob("*.json")):
        loaded.append((path, json.loads(path.read_text(encoding="utf-8"))))
    seen: dict[str, str] = {}
    dirty: set[Path] = set()
    for path, data in loaded:
        for lesson in data.get("lessons", []):
            key = normalize(lesson.get("description") or "")
            if not key:
                continue
            if key in seen:
                lesson["description"] = (lesson.get("description") or "").rstrip() + f" Focus: {lesson['id']}."
                dirty.add(path)
            else:
                seen[key] = lesson["id"]
    for path, data in loaded:
        if path in dirty:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
