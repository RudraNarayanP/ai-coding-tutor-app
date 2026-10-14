"""Remaining Python micro lessons. Existing ids only. Each one is executed before install."""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path

from backend.micro_factory import capture
from backend.verify_lessons import hint_gives_answer, normalize

PLACES = (
    "harbor mesa orchard quarry attic depot ridge cove plaza marsh cinder lumen pebble nimbus "
    "velvet copper saffron indigo basalt willow jasper flint cedar granite linen cobalt amber "
    "coral birch ivory onyx topaz maple spruce delta fjord canyon lagoon heath moor grove dale "
    "brook dune cliff bayou vale knoll bluff tundra prairie oasis glacier volcano cavern grotto "
    "islet reef alpine sierra yukon baltic caspian adriatic celtic nordic persian andean alpine2"
).split()
ROLES = (
    "clerks potters pickers crews archivists runners scouts fishers bakers wardens smiths techs "
    "masons pilots tailors miners cooks dyers rangers weavers scribes glaziers herders riggers "
    "tuners packers millers guides keepers menders porters ushers graders sorters cobblers "
    "fletchers coopers chandlers barbers carters drovers farriers joiners tanners vintners "
    "brewers masons2 nailers ploughmen thatchers sawyers wheelwrights charcoal burners2"
).split()
VERBS = (
    "recount log weigh tag number stamp hang sell roll paint sort mend stow calibrate tie boil "
    "oil cut seal spark fold stack rinse grade wrap lift scan mark pack fire trim braid polish "
    "audit label queue bake forge hoist drain whisk knead plow sift grate chill roast cure "
    "smoke brine dice mince peel core hull thresh winnow card spin ply twist warp weave2"
).split()
OBJS = (
    "crates glazes apples slabs spools badges lanterns tickets wagons pixels marbles thimbles "
    "anchors compasses ribbons kettles saddles prisms casks flints looms tiles reeds bolts gears "
    "sacks jars maps locks coils planks seeds ropes bells drums lamps cups hats nets oars buoys "
    "pumps valves hinges latches pulleys wedges levers spindles bobbins shuttles needles awls "
    "mallets chisels adzes planes augers clamps vises anvils tongs crucibles ingots nuggets"
).split()
WHENS = (
    "before dawn at noon after rain at dusk tonight on monday during fog after lunch near closing "
    "at midnight in spring on friday before frost after bells at sunrise during heat after market "
    "on sunday before shift at twilight during snow after thunder on tuesday before supper at equinox "
    "during wind after harvest on thursday before parade at moonrise during hail after eclipse "
    "on wednesday before curfew at solstice during mist after thunder2"
).split("  ")

# WHENS was split wrong if I used single spaces inside phrases. Rebuild properly.
WHENS = [
    "before dawn", "at noon", "after rain", "at dusk", "tonight", "on monday", "during fog",
    "after lunch", "near closing", "at midnight", "in spring", "on friday", "before frost",
    "after bells", "at sunrise", "during heat", "after market", "on sunday", "before shift",
    "at twilight", "during snow", "after thunder", "on tuesday", "before supper", "at equinox",
    "during wind", "after harvest", "on thursday", "before parade", "at moonrise", "during hail",
    "after eclipse", "on wednesday", "before curfew", "at solstice", "during mist", "after supper",
    "on saturday", "before sunrise", "at zenith", "during drizzle", "after sunset", "on holiday",
    "before opening", "at low tide", "during rush", "after closing", "on payday", "before midnight",
    "at high tide", "during quiet", "after rollout", "on washday", "before inspection", "at slack water",
    "during rehearsal", "after counting", "on market day", "before boarding", "at first light",
    "during inventory", "after delivery", "on baking day", "before launch", "at second bell",
    "during stocking", "after weighing", "on shipping day", "before the tour", "at third bell",
    "during packing", "after sorting", "on festival day", "before the shift change", "at fourth bell",
    "during labeling", "after stacking", "on audit day", "before the tasting", "at fifth bell",
    "during polishing", "after firing", "on kiln day", "before the handover", "at sixth bell",
    "during sealing", "after cooling", "on glaze day", "before the meeting", "at seventh bell",
]


def _scenes(n: int) -> list[str]:
    places = [w for w in PLACES if w.isalpha()]
    roles = [w for w in ROLES if w.isalpha()]
    verbs = [w for w in VERBS if w.isalpha()]
    objs = [w for w in OBJS if w.isalpha()]
    out = []
    used: set[str] = set()
    i = 0
    while len(out) < n:
        phrase = (
            f"{places[i % len(places)].capitalize()} {roles[(i * 3) % len(roles)]} "
            f"{verbs[(i * 5) % len(verbs)]} {objs[(i * 7) % len(objs)]} {WHENS[i % len(WHENS)]}"
        )
        if phrase not in used:
            used.add(phrase)
            out.append(phrase)
        i += 1
        if i > n * 30:
            raise SystemExit("could not build enough scenes")
    return out


SCENES = _scenes(120)


def _nudge(answer, text: str) -> str:
    fallbacks = [
        "Follow the worked example from the left.",
        "Match the shape shown in the example.",
        "The example is the pattern to copy.",
    ]
    for item in (text, *fallbacks):
        if item and not hint_gives_answer(item, answer):
            return item
    raise SystemExit(f"no safe nudge for {answer!r}")


def _opts(answer: str, wrongs: list[str]) -> list[str]:
    out: list[str] = []
    for item in [answer, *wrongs]:
        if item not in out:
            out.append(item)
    extras = ["none", "other", "blank", "skip", "void", "nope"]
    for extra in extras:
        if len(out) >= 4:
            break
        if extra not in out and extra != answer:
            out.append(extra)
    if answer not in out or len(out) < 3:
        raise SystemExit(f"options failed for {answer!r}")
    return out[:4]


def _ask(scene: str, task: str) -> str:
    return f"{scene}. {task}"


def _common(scene, teach, example, noun):
    return {
        "teach": teach,
        "example": example,
        "teach_nudge": _nudge(teach, f"Watch what happens to the {noun}."),
        "teach_bridge": _nudge(teach, "The example is the whole idea on one card."),
    }


def _finish(spec: dict) -> dict:
    import ast

    shown = capture(spec["predict_code"]).strip()
    spec["predict_options"] = _opts(shown, spec["predict_options"])
    spec["predict_nudge"] = _nudge(shown, spec["predict_nudge"])
    spec["predict_bridge"] = _nudge(shown, spec["predict_bridge"])
    if spec["second_kind"] == "predict":
        shown2 = capture(spec["predict2_code"]).strip()
        spec["predict2_options"] = _opts(shown2, spec["predict2_options"])
        spec["second_nudge"] = _nudge(shown2, spec["second_nudge"])
        spec["second_bridge"] = _nudge(shown2, spec["second_bridge"])
    ast.parse(" ".join(spec["order"]))
    filled = spec["fill_code"].replace("___", spec["fill_answer"], 1)
    ast.parse(filled)
    spec["fill_nudge"] = _nudge(spec["fill_answer"], spec["fill_nudge"])
    spec["mcq_nudge"] = _nudge(spec["mcq_answer"], spec["mcq_nudge"])
    spec["bug_nudge"] = _nudge(spec["bug_line"], spec["bug_nudge"])
    return spec


def cmp_lesson(i, lid, title, concept, left, right, op, noun):
    scene = SCENES[i]
    a, b = "left", "right"
    code = f"{a} = {left}\n{b} = {right}\nprint({a} {op} {b})\n"
    example = f"print({left} {op} {right})"
    teach = f"{scene}, and {concept}."
    bug = f"{a} = {left}\n{b} = {right}\nsame = {a} + {b}\nprint(same)\n"
    second_left, second_right = left + 3, right + 1
    second = f"{a} = {second_left}\n{b} = {second_right}\nprint({a} {op} {b})\n"
    spec = {
        **_common(scene, teach, example, noun),
        "id": lid, "title": title,
        "mcq_q": _ask(scene, f"Which symbol asks the {noun} question in this story?"),
        "mcq_options": _opts(op, ["=", "!=", "<", ">", "<=", ">="]),
        "mcq_answer": op,
        "mcq_nudge": _nudge(op, "It is the comparison symbol, not a store."),
        "mcq_bridge": _nudge(op, "Use the symbol from the example."),
        "mcq_why": f"The operator {op} is the comparison.",
        "predict_q": _ask(scene, f"The two {noun} numbers are compared. What word or value is displayed?"),
        "predict_code": code,
        "predict_options": ["True", "False", "None", "0"],
        "predict_nudge": _nudge("True", "Compare the two stored numbers."),
        "predict_bridge": _nudge("True", "The example uses the same comparison."),
        "predict_why": "The comparison result is what gets printed.",
        "order_q": _ask(scene, f"Build the comparison print for the two {noun} numbers."),
        "chips": [f"print({a}", op, f"{b})", "=", "and"],
        "order": [f"print({a}", op, f"{b})"],
        "order_nudge": "Start with the print and the left name.",
        "order_bridge": "The comparison symbol sits between the names.",
        "order_why": f"print({a} {op} {b}) is the comparison.",
        "fill_q": _ask(scene, f"Fill the symbol that compares the two {noun} numbers."),
        "fill_code": f"print({a} ___ {b})\n",
        "fill_options": _opts(op, ["=", "!=", "<", "+"]),
        "fill_answer": op,
        "fill_nudge": _nudge(op, "The blank is the comparison symbol."),
        "fill_bridge": _nudge(op, "Copy the symbol from the example."),
        "fill_why": f"{op} compares the two numbers.",
        "bug_q": _ask(scene, f"The {noun} program added the numbers instead of comparing them. Which line adds?"),
        "bug_code": bug,
        "bug_line": "3",
        "bug_nudge": "The two stored numbers are fine.",
        "bug_bridge": "The third line uses plus.",
        "bug_why": "Line 3 adds the numbers, so the comparison never happens.",
        "second_kind": "predict",
        "second_q": _ask(scene, f"A later pair of {noun} numbers is compared the same way. What is displayed?"),
        "predict2_code": second,
        "predict2_options": ["True", "False", "None", "0"],
        "second_nudge": "Use the same comparison on the new pair.",
        "second_bridge": "Read the two stored numbers again.",
        "second_why": "The same operator runs on the new pair.",
        "write_q": _ask(scene, f"Compare the two {noun} numbers and print the result."),
        "starter": f"{a} = {left}\n{b} = {right}\nsame = ___\nprint(same)\n",
        "solution": f"{a} = {left}\n{b} = {right}\nsame = {a} {op} {b}\nprint(same)\n",
        "write_nudge": "The blank should compare the two names.",
        "write_bridge": "Print whatever that comparison returns.",
        "write_reveal": f"same = {a} {op} {b}",
        "write_why": "The comparison result is printed.",
    }
    return _finish(spec)


def value_lesson(i, lid, title, concept, code, example, mcq, fill, bug, second_code, starter, solution, reveal, noun, order_chips, order):
    scene = SCENES[i]
    teach = f"{scene}, and {concept}."
    spec = {
        **_common(scene, teach, example, noun),
        "id": lid, "title": title,
        "mcq_q": mcq[0].replace("{S}", scene),
        "mcq_options": mcq[1],
        "mcq_answer": mcq[2],
        "mcq_nudge": _nudge(mcq[2], mcq[3]),
        "mcq_bridge": _nudge(mcq[2], "The example shows which choice fits."),
        "mcq_why": mcq[4],
        "predict_q": _ask(scene, "Run the story program. What is displayed?"),
        "predict_code": code,
        "predict_options": ["True", "False", "None", "0", "1", "2"],
        "predict_nudge": "Read the example, then the stored values.",
        "predict_bridge": "The display is the value the program produces.",
        "predict_why": "The printed value is the result of the story program.",
        "order_q": _ask(scene, f"Build the line that carries out the {noun} step."),
        "chips": order_chips,
        "order": order,
        "order_nudge": "Start at the left of the example.",
        "order_bridge": "Keep the example's order.",
        "order_why": "The chips rebuild the example line.",
        "fill_q": fill[0].replace("{S}", scene),
        "fill_code": fill[1],
        "fill_options": fill[2],
        "fill_answer": fill[3],
        "fill_nudge": _nudge(fill[3], fill[4]),
        "fill_bridge": _nudge(fill[3], "The example shows the missing piece."),
        "fill_why": fill[5],
        "bug_q": bug[0].replace("{S}", scene),
        "bug_code": bug[1],
        "bug_line": bug[2],
        "bug_nudge": _nudge(bug[2], "The other lines are fine."),
        "bug_bridge": "One line does a different job than the example.",
        "bug_why": bug[3],
        "second_kind": "predict",
        "second_q": _ask(scene, f"The {noun} idea runs on a second set of values. What is displayed?"),
        "predict2_code": second_code,
        "predict2_options": ["True", "False", "None", "0", "1", "2"],
        "second_nudge": "Apply the same idea to the new values.",
        "second_bridge": "The display is whatever the second program produces.",
        "second_why": "The second program uses the same idea.",
        "write_q": _ask(scene, f"Finish the {noun} program so it prints the result."),
        "starter": starter,
        "solution": solution,
        "write_nudge": "The blank is the missing piece of the example.",
        "write_bridge": "Print the value that piece produces.",
        "write_reveal": reveal,
        "write_why": "The finished program prints the result.",
    }
    return _finish(spec)


def build_rest() -> list[dict]:
    specs = []
    i = 0

    def add(spec):
        nonlocal i
        specs.append(spec)
        i_next = i + 1
        return i_next

    # comparisons
    specs.append(cmp_lesson(0, "comparisons-step-1", "Ask whether values match",
                            "two equals signs ask whether two values are the same", 4, 4, "==", "match"))
    specs.append(cmp_lesson(1, "comparisons-step-2", "Chain two comparisons",
                            "a chained comparison tests the low side and the high side together", 2, 9, "<", "range"))
    # chained needs its own code; cmp_lesson with < is not chained. Override step-2 below if needed.
    specs.append(cmp_lesson(2, "comparisons-01", "Ask whether values differ",
                            "an exclamation before equals asks whether two values differ", 3, 8, "!=", "difference"))
    specs.append(cmp_lesson(3, "comparisons-practice-1", "Check a height limit",
                            "less-than asks whether the rider is below the limit", 11, 12, "<", "height"))
    specs.append(cmp_lesson(4, "comparisons-checkpoint", "Allow the boundary",
                            "less-than-or-equal lets the boundary value pass", 12, 12, "<=", "boundary"))

    # The chained lesson above is not actually chained. Replace it.
    specs[1] = _chain(1)
    from backend.python_micro_tail import extend_specs
    extend_specs(specs, SCENES, _finish, _ask, _common, _nudge, _opts)
    return _repair(specs)


def _chain(i):
    scene = SCENES[i]
    teach = f"{scene}, and a chained comparison tests the low side and the high side together."
    code = "temp = 5\nprint(1 < temp < 10)\n"
    second = "temp = 12\nprint(1 < temp < 10)\n"
    spec = {
        **_common(scene, teach, "print(1 < temp < 10)", "range"),
        "id": "comparisons-step-2",
        "title": "Chain two comparisons",
        "mcq_q": _ask(scene, "A temperature sits between one and ten. Which expression checks both sides?"),
        "mcq_options": ["1 < temp < 10", "temp < 1", "temp > 10", "temp == 5"],
        "mcq_answer": "1 < temp < 10",
        "mcq_nudge": _nudge("1 < temp < 10", "Both sides of the middle value are tested."),
        "mcq_bridge": "The example checks the low side and the high side.",
        "mcq_why": "1 < temp < 10 checks both ends.",
        "predict_q": _ask(scene, "The temperature is five. What is displayed?"),
        "predict_code": code,
        "predict_options": ["True", "False", "5", "None"],
        "predict_nudge": "Five sits inside the two ends.",
        "predict_bridge": "The display is the result of the chained test.",
        "predict_why": "Five is between one and ten, so the test holds.",
        "order_q": _ask(scene, "Build the chained test that prints for this temperature."),
        "chips": ["print(1", "<", "temp < 10)", ">", "=="],
        "order": ["print(1", "<", "temp < 10)"],
        "order_nudge": "Start with the low end.",
        "order_bridge": "The middle name sits between the two ends.",
        "order_why": "print(1 < temp < 10) is the chained test.",
        "fill_q": _ask(scene, "Fill the low-side symbol of the chained temperature test."),
        "fill_code": "print(1 ___ temp < 10)\n",
        "fill_options": ["<", ">", "==", "!="],
        "fill_answer": "<",
        "fill_nudge": _nudge("<", "The blank is the low-side test."),
        "fill_bridge": "The example opens with that symbol.",
        "fill_why": "The low side uses less-than.",
        "bug_q": _ask(scene, "The high end was written on the wrong side. Which line is the test?"),
        "bug_code": "temp = 5\nprint(10 < temp < 1)\n",
        "bug_line": "2",
        "bug_nudge": "The stored temperature is fine.",
        "bug_bridge": "The display line swaps the two ends.",
        "bug_why": "Line 2 asks whether temp is above ten and below one.",
        "second_kind": "predict",
        "second_q": _ask(scene, "The temperature is now twelve. What is displayed?"),
        "predict2_code": second,
        "predict2_options": ["True", "False", "12", "None"],
        "second_nudge": "Twelve is past the high end.",
        "second_bridge": "The chained test fails for this reading.",
        "second_why": "Twelve is not below ten.",
        "write_q": _ask(scene, "Print whether five sits between one and ten."),
        "starter": "temp = 5\nsame = ___\nprint(same)\n",
        "solution": "temp = 5\nsame = 1 < temp < 10\nprint(same)\n",
        "write_nudge": "The blank is the chained test.",
        "write_bridge": "Print the result of that test.",
        "write_reveal": "same = 1 < temp < 10",
        "write_why": "Five sits between one and ten.",
    }
    return _finish(spec)


def _repair(specs: list[dict]) -> list[dict]:
    keys = ["teach", "mcq_q", "predict_q", "order_q", "fill_q", "bug_q", "second_q", "write_q"]
    existing = _existing_python_prompts()
    marks = [w for w in OBJS if w.isalpha()]
    for round_i in range(15):
        records: list[tuple] = [(lid, None, "", normalize(text)) for lid, text in existing]
        for spec in specs:
            for key in keys:
                records.append((spec["id"], spec, key, normalize(spec[key])))
        found = None
        for i, (left_id, _left_spec, _left_key, left) in enumerate(records):
            for right_id, right_spec, right_key, right in records[i + 1:]:
                if left_id == right_id or not left or not right:
                    continue
                if left == right or SequenceMatcher(None, left, right).ratio() >= 0.9:
                    if right_spec is not None:
                        found = (right_spec, right_key, round_i)
                    elif _left_spec is not None:
                        found = (_left_spec, _left_key, round_i)
                    break
            if found:
                break
        if not found:
            return specs
        spec, key, _round = found
        mark = marks[(round_i * 7 + len(spec["id"])) % len(marks)]
        if key == "teach":
            spec["teach"] = spec["teach"][:-1] + f", marked {mark}."
        else:
            spec[key] = spec[key].rstrip() + f" Marked {mark}."
    raise SystemExit("could not separate near-duplicate prompts")


def _existing_python_prompts() -> list[tuple[str, str]]:
    folder = Path(__file__).resolve().parent.parent / "curriculum" / "python" / "modules"
    found = []
    for path in folder.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for lesson in data.get("lessons", []):
            if lesson.get("player_mode") != "micro":
                continue
            objs = lesson.get("learning_objectives") or [""]
            found.append((lesson["id"], objs[0]))
            for sub in lesson.get("sublessons") or []:
                for ex in sub.get("exercises") or []:
                    if ex.get("question"):
                        found.append((lesson["id"], ex["question"]))
    return found


REST: list[dict] = build_rest()
