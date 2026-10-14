"""Questions that name the same job as the code.

Scene openings and “compare with the example” hints are not produced here.
Each prompt says what to do and what a correct answer looks like, using the
pack’s action and a line from that lesson’s program.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from backend.verify_lessons import hint_gives_answer, normalize

SCENE_RE = re.compile(
    r"\b(?:Harbor|Mesa|Orchard|Quarry|Attic|Depot|Ridge|Cove|Plaza|Marsh) "
    r"(?:clerks|potters|pickers|crews|archivists|runners|scouts|bakers|wardens|smiths)\b"
)
KEYS = ("teach", "mcq_q", "predict_q", "order_q", "fill_q", "bug_q", "second_q", "write_q")
NUDGE_KEYS = {
    "teach": "teach_nudge",
    "mcq_q": "mcq_nudge",
    "predict_q": "predict_nudge",
    "order_q": "order_nudge",
    "fill_q": "fill_nudge",
    "bug_q": "bug_nudge",
    "second_q": "second_nudge",
    "write_q": "write_nudge",
}
SKIP_LINE = (
    "public class", "public static", "#include", "int main", "using namespace",
    "import ", "package ",
)


def scene_lesson(lesson: dict) -> bool:
    parts = list(lesson.get("learning_objectives") or [])
    for sub in lesson.get("sublessons") or []:
        for exercise in sub.get("exercises") or []:
            question = exercise.get("question") or ""
            if question:
                parts.append(question)
    return SCENE_RE.search(" ".join(parts)) is not None


def _joined(answer) -> str:
    if isinstance(answer, list):
        return " ".join(str(part) for part in answer)
    return str(answer)


def _sentence(text: str) -> str:
    text = text.replace("`", " ").replace("?", " ").replace("!", " ")
    text = text.replace(".", ",")
    text = " ".join(text.split()).strip(" ,")
    if not text:
        text = "Follow the step on this screen"
    return text[0].upper() + text[1:] + "."


def _drop(text: str, answer) -> str:
    key = normalize(_joined(answer))
    if not key:
        return text
    kept = [word for word in text.split() if key not in normalize(word)]
    return " ".join(kept)


def _fit(text: str, answer) -> str | None:
    if not hint_gives_answer(text, answer):
        done = _sentence(text)
        if not hint_gives_answer(done, answer):
            return done
    cleaned = _drop(text, answer)
    if len(cleaned.split()) < 6:
        return None
    done = _sentence(cleaned)
    if hint_gives_answer(done, answer):
        return None
    return done


_STOP = {
    "and", "as", "assert", "async", "await", "break", "class", "const", "continue",
    "cout", "def", "else", "endl", "false", "for", "from", "function", "if", "import",
    "in", "int", "let", "log", "main", "new", "none", "not", "null", "or", "out",
    "print", "println", "public", "return", "static", "std", "string", "system",
    "then", "true", "var", "void", "while", "with",
    "select", "from", "where", "distinct", "order", "by", "limit", "group", "join",
    "insert", "into", "update", "set", "delete", "values", "count", "as", "on",
    "inner", "left", "right", "having", "case", "when", "end", "null", "is",
}


def _anchors(code: str) -> list[str]:
    names: list[str] = []
    for name in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", code):
        if name.lower() in _STOP or name in names:
            continue
        names.append(name)
    nums: list[str] = []
    for num in re.findall(r"\b\d+\b", code):
        if num not in nums:
            nums.append(num)
    quotes = []
    for quote in re.findall(r"['\"]([A-Za-z][^'\"]{0,24})['\"]", code):
        if quote not in quotes:
            quotes.append(quote)
    found: list[str] = []

    def add(item: str) -> None:
        item = " ".join(item.split())
        if item and item not in found:
            found.append(item)

    useful = [num for num in nums if num != "0"] or nums
    if quotes and names:
        add(f"{names[0]} holding {quotes[0]}")
    elif quotes:
        add(f"the text {quotes[0]}")
    if names and useful:
        add(f"{names[0]} and {useful[-1]}")
    if len(names) >= 2:
        add(f"{names[0]} and {names[1]}")
    if names:
        add(f"the name {names[0]}")
    if useful:
        add(f"the value {useful[-1]}")
    return found


def _code_body(code: str) -> str:
    kept = []
    for raw in code.splitlines():
        line = raw.strip()
        if not line or line in {"{", "}", "};"} or line.startswith(SKIP_LINE):
            continue
        if line.startswith(("#include", "using ", "public class", "public static", "int main")):
            continue
        kept.append(line)
    return "\n".join(kept)


def _details(pack: dict, lesson_id: str) -> list[str]:
    del lesson_id
    found = _anchors(_code_body(pack.get("predict", "")))
    for item in _anchors(_code_body(pack.get("predict2", ""))):
        if item not in found:
            found.append(item)
    return found[:6] or ["the worked value"]


def _safe_detail(detail: str, answer) -> str:
    if hint_gives_answer(detail, answer):
        return "the snippet"
    return detail


def _frames(kind: str, action: str, detail: str) -> list[str]:
    job = action.strip().rstrip(".")
    setup = detail.strip()
    if kind == "teach":
        return [
            f"This step {job}, using {setup}",
            f"Using {setup}, this step {job}",
            f"The job in this step {job}, and the code uses {setup}",
            f"{setup} is where you can see that this step {job}",
            f"Watch this step, which {job}, with {setup}",
            f"Here the code {job}, and it uses {setup}",
            f"You are practicing the step that {job}, shown with {setup}",
            f"The one job to learn {job}, starting from {setup}",
        ]
    if kind == "mcq_q":
        return [
            f"Choose the line that {job}, which is the line that fits {setup}",
            f"The correct line {job}, and it is the line tied to {setup}",
            f"Keep the choice that {job} for {setup}",
            f"Select the line that {job}, the one that belongs with {setup}",
            f"Mark the choice that {job} when the code mentions {setup}",
            f"The match is the line that {job} for {setup}",
            f"Pick the line that {job}, not a line about something else, for {setup}",
            f"A correct choice {job} and goes with {setup}",
        ]
    if kind == "predict_q":
        return [
            f"Read the code that {job} for {setup}, and choose the value it prints",
            f"The program {job} with {setup}, so choose the printed value",
            f"Trace the code that {job} using {setup}, and select what it displays",
            f"Follow the code that {job} for {setup}, then choose the displayed value",
            f"After {setup}, the code {job}, and the correct choice is the printed value",
            f"Work out what is printed when the code {job} for {setup}",
            f"The displayed value is what the code prints when it {job} for {setup}",
            f"Select the output after the code {job}, using {setup}",
        ]
    if kind == "order_q":
        return [
            f"Arrange the pieces of the line that {job}, left to right, for {setup}",
            f"Build the line that {job} for {setup}, from the first piece to the last",
            f"Tap the pieces, in order, of the line that {job} for {setup}",
            f"Order the pieces so the line {job} for {setup}",
            f"The finished line {job}, so place its pieces in order for {setup}",
            f"Rebuild, from the left, the line that {job} for {setup}",
            f"Place every piece so the result {job} for {setup}",
            f"Make the line that {job} by ordering the pieces for {setup}",
        ]
    if kind == "fill_q":
        return [
            f"Fill the blank so the line {job} for {setup}",
            f"Replace the blank with the piece that makes the line {job} for {setup}",
            f"The blank is the missing piece of the line that {job} for {setup}",
            f"Supply the missing piece so the line {job} for {setup}",
            f"Finish the line that {job} by filling the blank for {setup}",
            f"The completed line {job} once you fill the blank for {setup}",
            f"Drop in the piece that lets the line {job} for {setup}",
            f"Complete the line for {setup} so that it {job}",
        ]
    if kind == "bug_q":
        return [
            f"Find the line that misses the job, which {job}, for {setup}",
            f"Spot the line that fails the job, which {job}, around {setup}",
            f"Choose the line that does another job than the one that {job} for {setup}",
            f"The wrong line is the one that misses the job, which {job}, for {setup}",
            f"Mark the line that breaks the job, which {job}, for {setup}",
            f"One line does another job than the one that {job} for {setup}",
            f"The mismatch misses the job, which {job}, for {setup}",
            f"Select the line that gets in the way of the job, which {job}, for {setup}",
        ]
    if kind == "second_q":
        return [
            f"On the new input, the code still {job} for {setup}, so choose what it prints",
            f"The second program {job} for {setup}, so choose the new printed value",
            f"Trace the second run, which {job} for {setup}, and select what it displays",
            f"A new input still has code that {job} for {setup}, and the correct choice is what it prints",
            f"Follow the second program, which {job} for {setup}, and choose its output",
            f"The second display is what prints after the code {job} for {setup}",
            f"Choose the printed result of the second run that {job} for {setup}",
            f"With the new data around {setup}, the code {job}, so select the new output",
        ]
    return [
        f"Fill the blank so the program {job}, and the print shows that result for {setup}",
        f"Complete the blank so this program {job} and prints the result for {setup}",
        f"Type the missing piece so the program {job} for {setup} and prints it",
        f"The blank is the missing piece of the program that {job} for {setup}",
        f"Finish the program that {job} by filling the blank for {setup}",
        f"Supply the blank so the run {job} and prints the result for {setup}",
        f"Make the program {job} by filling the blank for {setup}",
        f"The printed result shows up after you fill the blank so the code {job} for {setup}",
    ]


def _nudge_frames(action: str, detail: str) -> list[str]:
    job = action.strip().rstrip(".")
    setup = detail.strip()
    return [
        f"Follow the job, which {job}.",
        f"Ignore a line that does another job, and follow the one that {job}.",
        f"The piece you want is the one for the job, which {job}.",
        f"Check {setup}, then follow the job, which {job}.",
        f"The right result is whatever the job produces, and the job {job}.",
        f"Start from {setup} and keep the job, which {job}.",
    ]


def render_key(kind: str, action: str, details: list[str], frame: int, answer) -> str | None:
    safe_details = []
    for detail in details:
        safe = _safe_detail(detail, answer)
        if safe not in safe_details:
            safe_details.append(safe)
    styles = [frame % 8] + [style for style in range(8) if style != frame % 8]
    for style in styles:
        detail = safe_details[(frame // 8) % len(safe_details)]
        fitted = _fit(_frames(kind, action, detail)[style], answer)
        if fitted:
            return fitted
        for other in safe_details:
            if other == detail:
                continue
            fitted = _fit(_frames(kind, action, other)[style], answer)
            if fitted:
                return fitted
    return _fit(f"Follow the step that {action}", answer)


def render_nudge(action: str, details: list[str], frame: int, answer) -> str:
    for shift in range(16):
        detail = _safe_detail(details[(frame + shift) % len(details)], answer)
        for text in _nudge_frames(action, detail):
            if "example" in text.lower():
                continue
            fitted = _fit(text, answer)
            if fitted and not hint_gives_answer(fitted, answer):
                return fitted
    for fallback in (
        "Stay with the step this screen is about.",
        "Skip a choice aimed at a different job.",
        "Keep the piece that completes the step.",
        "The odd part is the one that does another job.",
    ):
        if not hint_gives_answer(fallback, answer):
            return fallback
    return "Stay with the step."


def apply_prompts(spec: dict) -> None:
    action = spec["_action"]
    details = spec["_details"]
    frames = spec["_frame"]
    guards = spec.get("_answers") or {}
    for kind in KEYS:
        answer = guards.get(kind, "")
        text = render_key(kind, action, details, frames[kind], answer)
        if text is None:
            raise SystemExit(f"{spec['id']} cannot phrase {kind}")
        spec[kind] = text
        spec[NUDGE_KEYS[kind]] = render_nudge(action, details, frames[kind], answer)


def separate(course: str, specs: list[dict], existing: list[tuple[str, str]]) -> None:
    """Rotate a prompt frame until no two lessons in the course share a near copy.

    Frozen lessons are the reference. Two frozen prompts are not rewritten here.
    """
    from collections import defaultdict

    groups: dict[str, list[dict]] = defaultdict(list)
    for spec in specs:
        groups[spec["_action"]].append(spec)
    for group in groups.values():
        if len(group) < 2:
            continue
        teach_styles = (0, 1, 2, 5, 6, 7)
        for index, spec in enumerate(group):
            spec["_frame"]["teach"] = teach_styles[index % len(teach_styles)]
            for key in KEYS:
                if key == "teach":
                    continue
                spec["_frame"][key] = spec["_frame"].get(key, 0) + index * 3
            apply_prompts(spec)

    for _round in range(80):
        records: list[tuple] = [(lid, None, "", normalize(text)) for lid, text in existing]
        for spec in specs:
            for key in KEYS:
                records.append((spec["id"], spec, key, normalize(spec[key])))
        buckets: dict[int, list[int]] = defaultdict(list)
        for index, record in enumerate(records):
            buckets[len(record[3]) // 16].append(index)
        found = None
        for index, (left_id, left_spec, left_key, left) in enumerate(records):
            if not left:
                continue
            length = len(left)
            for bucket in range(max(0, length // 16 - 2), length // 16 + 3):
                for other in buckets.get(bucket, ()):
                    if other <= index:
                        continue
                    right_id, right_spec, right_key, right = records[other]
                    if left_id == right_id or not right or (left_spec is None and right_spec is None):
                        continue
                    shorter, longer = sorted((length, len(right)))
                    if shorter / longer < 0.81:
                        continue
                    if left != right:
                        matcher = SequenceMatcher(None, left, right)
                        if matcher.quick_ratio() < 0.9:
                            continue
                        if matcher.ratio() < 0.9:
                            continue
                    target = right_spec if right_spec is not None else left_spec
                    key = right_key if right_spec is not None else left_key
                    if target is not None and key:
                        found = (target, key)
                        break
                if found:
                    break
            if found:
                break
        if not found:
            return
        spec, key = found
        spec["_frame"][key] = spec["_frame"].get(key, 0) + 1
        if spec["_frame"][key] > 48:
            raise SystemExit(f"cannot separate {course} {spec['id']} {key}")
        apply_prompts(spec)
    raise SystemExit(f"{course} still has near-duplicate prompts")
