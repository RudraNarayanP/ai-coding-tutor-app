"""Speech-aware library grounding, reviser-discard tolerance, polish templates, provider diagnostics.

Regression for the build-GPT false discard (kCc8FmEb1nY): captions say "PyTorch" ~27x but
never contain ``import torch``; the old precheck flagged torch as invented and the reviser
(seeing only a 2.5k sample) discarded the course. The micrograd anti-numpy guard must hold.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from backend.ai_course_generator import (
    _short_transcript_summary,
    generate_course_with_ai,
    lib_grounded_in_source,
    library_evidence_line,
    local_precheck_course,
)
from backend.ai_provider import _finish_and_reasoning, _upstream_error_in_body
from backend.project_copy import (
    BANNED_VIDEO_PHRASES,
    beginner_teach,
    contains_banned_video_phrase,
    learner_facing_fields,
    learner_why,
)
from backend.project_models import Microstep, Milestone, ProjectCourse, VerificationCheck, WorkspaceFile
from backend.source_ingestion import SourceDocument, VideoSegment
from backend.source_quality import SourceQualityError

from backend.test_ai_course_generator_quality import ScriptedProvider, _doc, _good_course_json

_GPT_TRANSCRIPT = (
    "hi everyone. today we build a generatively pretrained transformer on tiny shakespeare. "
    + "we read the text and encode characters into integers. " * 40
    + "now we're going to use pytorch for this. pytorch gives us tensors. "
    + "let's wrap the data in a tensor and look at the dtype. " * 30
    + "in pytorch the embedding table is an nn module. we compute the loss with cross entropy in pytorch. "
    + "self attention: queries keys values, masked softmax. " * 30
)
_MICROGRAD_TRANSCRIPT = (
    "we build micrograd in pure python, a tiny autograd engine. define class value with data and grad. "
    + "implement add mul and backward with a topological sort. " * 40
    + "i'm plotting this with numpy here just to get a curve. we don't need numpy for the engine. "
    + "later we compare against pytorch. pytorch would give the same gradient. in pytorch you'd write torch tensor. "
)


def _yt_doc(title: str, transcript: str) -> SourceDocument:
    return SourceDocument(
        source_type="youtube_url",
        source_url="https://www.youtube.com/watch?v=x",
        source_hash="h",
        title=title,
        plain_text=transcript,
        segments=[VideoSegment(video_id="x", title=title, url="u", position=1, transcript=transcript)],
    )


def _project(stack: list[str], first_teach: str, first_check: str) -> ProjectCourse:
    ms = []
    for i in range(1, 7):
        teach = first_teach if i == 1 else f"Step {i} extends the model with a distinct piece."
        target = first_check if i == 1 else f"step_{i}_token"
        ms.append(
            Milestone(
                id=f"m{i}", order=i, title=f"Build part {i}", why=f"Part {i} is needed next.", teach=teach,
                microstep=Microstep(action=f"In `main.py`, write `{target}`.", observation="ok", hint=f"Name it `{target}`."),
                checks=[VerificationCheck(kind="code_contains", target=target, description="d")],
            )
        )
    return ProjectCourse(
        course_id="c", title="T", project_goal="g", entry_file="main.py", tech_stack=stack,
        milestones=ms, workspace_files=[WorkspaceFile(path="main.py", content="#")],
    )


def test_spoken_pytorch_grounds_torch_without_import_lines():
    assert lib_grounded_in_source("torch", _GPT_TRANSCRIPT)
    assert lib_grounded_in_source("pytorch", _GPT_TRANSCRIPT)
    assert not lib_grounded_in_source("numpy", _GPT_TRANSCRIPT)


def test_precheck_does_not_flag_torch_for_real_pytorch_tutorial():
    doc = _yt_doc("Let's build GPT: from scratch, in code, spelled out.", _GPT_TRANSCRIPT)
    project = _project(["Python", "PyTorch"], "Load the text into a torch tensor.", "torch.tensor(data")
    defects = local_precheck_course(project, doc)
    assert not any("Ungrounded" in d for d in defects), defects


def test_precheck_still_flags_numpy_for_micrograd_passing_mentions():
    doc = _yt_doc("building micrograd", _MICROGRAD_TRANSCRIPT)
    project = _project(["Python", "numpy"], "Use numpy arrays for Value.", "import numpy as np")
    defects = local_precheck_course(project, doc)
    assert any("Ungrounded" in d and "numpy" in d for d in defects), defects


def test_negated_mentions_do_not_ground():
    src = "no numpy here. without numpy we are fine. don't use numpy. " * 3
    assert not lib_grounded_in_source("numpy", src)


def test_library_evidence_line_and_summary_carry_full_transcript_truth():
    doc = _yt_doc("Let's build GPT", _GPT_TRANSCRIPT)
    line = library_evidence_line(doc)
    assert "USED by the tutorial: PyTorch (torch)" in line
    assert "NOT in the transcript: numpy" in line
    # The 2.5k sample alone would not show torch; the evidence line must be in the summary.
    summary = _short_transcript_summary(doc, "Let's build GPT")
    assert "PyTorch (torch)" in summary
    mg = library_evidence_line(_yt_doc("micrograd", _MICROGRAD_TRANSCRIPT))
    assert "numpy (2 passing mentions)" in mg or "numpy (1 passing mention)" in mg, mg


def test_reviser_discard_tolerated_once_then_pass(monkeypatch):
    monkeypatch.setenv("CREATE_COURSE_QUALITY_MAX_TRIES", "5")
    create = json.dumps(_good_course_json())
    fail = json.dumps({"verdict": "FAIL", "reason": "stack", "defects": ["uses torch"]})
    discard = json.dumps({"decision": "discard", "reason": "transcript is pure numpy (hallucinated)"})
    passed = json.dumps({"verdict": "PASS", "reason": "good"})
    provider = ScriptedProvider([create, fail, discard, passed])
    project = asyncio.run(generate_course_with_ai(provider, _doc(), title="Word Counter", course_id="c-tol"))
    assert project.course_id == "c-tol"
    assert not provider.responses


def test_reviser_discard_twice_is_honoured(monkeypatch):
    monkeypatch.setenv("CREATE_COURSE_QUALITY_MAX_TRIES", "6")
    create = json.dumps(_good_course_json())
    fail = json.dumps({"verdict": "FAIL", "reason": "x", "defects": ["x"]})
    discard = json.dumps({"decision": "discard", "reason": "not a coding tutorial"})
    provider = ScriptedProvider([create, fail, discard, fail, discard])
    with pytest.raises(SourceQualityError):
        asyncio.run(generate_course_with_ai(provider, _doc(), title="Word Counter", course_id="c-disc"))


def test_create_stage_discard_still_immediate(monkeypatch):
    provider = ScriptedProvider([json.dumps({"decision": "discard", "reason": "TEDx talk, no code"})])
    with pytest.raises(SourceQualityError):
        asyncio.run(generate_course_with_ai(provider, _doc(), title="talk", course_id="c-ted"))


def test_polish_templates_banned_and_never_generated():
    for phrase in ("real section of the tutorial", "real chapter of the tutorial", "moves your project toward the"):
        assert phrase in BANNED_VIDEO_PHRASES
    teach = beginner_teach("code_contains", "out._backward", title="Local Gradients: _backward for Each Op")
    why = learner_why("code_contains", "def tanh", title="More Ops", project_title="micrograd")
    assert not contains_banned_video_phrase(teach), teach
    assert not contains_banned_video_phrase(why), why


def test_empty_teach_reuses_ai_description_before_template():
    m = Milestone(
        id="m3", order=3, title="More Ops: Power, ReLU, tanh",
        source_grounded_description="Add __pow__, relu and tanh so the network can model non-linear functions.",
        why="Neural nets need non-linearities.", teach="",
        microstep=Microstep(action="In `micrograd.py`, implement __pow__, relu, tanh.", observation="ok", hint="Use math.tanh."),
        checks=[VerificationCheck(kind="code_contains", target="def tanh", description="d")],
    )
    fields = learner_facing_fields(m, entry_file="micrograd.py", project_title="micrograd")
    assert fields["teach"].startswith("Add __pow__, relu and tanh"), fields["teach"]


def test_provider_detects_200_error_body_and_finish_reason():
    assert _upstream_error_in_body({"error": {"code": 429, "message": "Rate limit exceeded: free-models-per-day"}}) == (
        429, "Rate limit exceeded: free-models-per-day",
    )
    assert _upstream_error_in_body({"choices": [{"message": {"content": "x"}}]}) is None
    assert _finish_and_reasoning(
        {"choices": [{"finish_reason": "length", "message": {"content": "", "reasoning": "abc"}}]}
    ) == ("length", 3)


def test_template_description_is_not_recycled_as_teach():
    m = Milestone(
        id="m5", order=5, title="Local Gradients: _backward for Each Op",
        source_grounded_description="Build “Local Gradients” in `micrograd.py` using the tutorial steps. Include `out._backward` as you implement this section.",
        why="Local derivatives are the lego bricks.", teach="",
        microstep=Microstep(action="In `micrograd.py`, implement _backward closures.", observation="ok", hint="Use out.grad."),
        checks=[VerificationCheck(kind="code_contains", target="out._backward", description="d")],
    )
    fields = learner_facing_fields(m, entry_file="micrograd.py", project_title="micrograd")
    assert "using the tutorial steps" not in fields["teach"]
    assert not contains_banned_video_phrase(fields["teach"]), fields["teach"]


def test_polish_does_not_inject_template_teach_or_why():
    from backend.ai_course_generator import _polish_milestone_dict
    item = _polish_milestone_dict(
        {"title": "Self-attention head", "action": "Write the Head class.", "teach": "", "why": "",
         "example": "class Head(nn.Module):", "checks": [{"kind": "code_contains", "target": "class Head"}]},
        language="python", entry_file="gpt.py",
    )
    assert not (item.get("teach") or "").strip()
    assert not (item.get("why") or "").strip()


def test_precheck_flags_empty_teach():
    project = _project(["Python"], "", "distinct_token_1")
    defects = local_precheck_course(project)
    assert any("Empty teach" in d for d in defects), defects


def test_loose_milestone_salvage_keeps_all_fields_of_non_last_milestones():
    from backend.ai_course_generator import _extract_milestones_loose
    ms = [
        {"title": f"Step {i}", "teach": f"teach {i}", "why": f"why {i}", "action": f"act {i}",
         "checks": [{"kind": "code_contains", "target": f"tok_{i}"}]}
        for i in range(1, 5)
    ]
    body = json.dumps({"decision": "create", "course": {"title": "T", "milestones": ms}})
    truncated = body[: body.rfind("why 4") ]  # cut inside the last milestone
    out = _extract_milestones_loose(truncated)
    assert [m.get("why") for m in out[:3]] == ["why 1", "why 2", "why 3"], out


def test_parse_keeps_last_milestone_when_model_adds_trailing_prose():
    from backend.ai_course_generator import _parse_json_object
    ms = [{"title": f"Step {i}", "why": f"w{i}"} for i in range(1, 14)]
    raw = json.dumps({"decision": "create", "course": {"title": "GPT", "milestones": ms}})
    raw += "\n\nFor the above text, give me a concise summary of the course. This course builds a GPT."
    data = _parse_json_object(raw)
    assert len(data["course"]["milestones"]) == 13


def test_fallback_check_token_comes_from_model_code_not_title():
    from backend.ai_course_generator import course_dict_to_project
    ms = []
    for i in range(1, 6):
        ms.append({
            "title": "Train bigram and generate" if i == 5 else f"Part {i}",
            "teach": "t", "why": "w", "hint": "h", "action": "Add the optimizer and loop.",
            "example": "optimizer=torch.optim.AdamW(model.parameters(),lr=1e-3); loss.backward()" if i == 5 else f"x_{i} = {i}",
            "checks": [{"kind": "run_ok", "target": ""}, {"kind": "stdout_contains", "target": "loss"}] if i == 5
            else [{"kind": "code_contains", "target": f"x_{i} = {i}"}],
        })
    doc = _yt_doc("Let's build GPT", _GPT_TRANSCRIPT)
    project = course_dict_to_project({"title": "GPT", "language": "python", "entry_file": "gpt.py", "milestones": ms},
                                     doc=doc, title="GPT", course_id="c")
    m5 = project.milestones[4]
    targets = [c.target for c in m5.checks]
    assert "Train" not in targets, targets
    assert any(t.startswith("torch.optim") or t.startswith("model.parameters") or t == "torch.optim.AdamW" for t in targets), targets


def test_missing_hint_is_not_replaced_by_template_and_is_flagged():
    from backend.ai_course_generator import course_dict_to_project
    ms = [{"title": f"Part {i}", "teach": "t", "why": "w", "action": "a", "example": f"val_{i} = {i}",
           "checks": [{"kind": "code_contains", "target": f"val_{i} = {i}"}]} for i in range(1, 6)]
    doc = _yt_doc("demo", "we write val code " * 10)
    project = course_dict_to_project({"title": "D", "language": "python", "entry_file": "main.py", "milestones": ms},
                                     doc=doc, title="D", course_id="c")
    assert all(not (m.microstep.hint or "") for m in project.milestones)
    assert any("Missing hint" in d for d in local_precheck_course(project))


# --- stack normalizer uses full transcript + speech-aware grounding -------------
def test_normalizer_keeps_pytorch_mentioned_after_12k_chars():
    from backend.ai_course_generator import _normalize_language_and_stack

    transcript = ("we write a bigram language model step by step in python. " * 260) + (
        "now we switch to pytorch. pytorch gives us nn modules. in pytorch the embedding is a table. "
    )
    assert transcript.index("pytorch") > 12000
    course = _normalize_language_and_stack(
        {"language": "python", "entry_file": "main.py", "tech_stack": ["PyTorch"]},
        _yt_doc("Let's build GPT", transcript),
        "Let's build GPT",
    )
    assert course["tech_stack"] == ["PyTorch"]


def test_normalizer_drops_numpy_mentioned_in_passing():
    from backend.ai_course_generator import _normalize_language_and_stack

    course = _normalize_language_and_stack(
        {"language": "python", "entry_file": "main.py", "tech_stack": ["Python", "numpy", "np"]},
        _yt_doc("micrograd", _MICROGRAD_TRANSCRIPT),
        "micrograd",
    )
    assert course["tech_stack"] == ["Python"]


def test_long_ai_action_not_truncated_or_templated():
    from backend.project_copy import MAX_ACTION

    assert MAX_ACTION >= 900


def test_course_dict_to_project_accepts_long_code_action():
    """Regression: a 900-char AI action (numbered steps + code) must neither be cut
    mid-token nor crash Microstep validation (was HTTP 500 string_too_long)."""
    from backend.ai_course_generator import course_dict_to_project

    data = _good_course_json()
    long_action = "1. In `main.py`, write `" + ("x = torch.zeros((1, 1), dtype=torch.long); " * 20) + "`. 2. Run it."
    assert 800 < len(long_action) <= 1000
    data["course"]["milestones"][0]["action"] = long_action
    proj = course_dict_to_project(data["course"], doc=_doc(), title="T", course_id="c-long")
    assert proj.milestones[0].microstep.action.endswith("2. Run it.")


# --- verifier: expression-style code_contains targets ----------------------------
def _cc(tok: str, code: str) -> bool:
    from backend import project_verifier as pv

    files = [WorkspaceFile(path="main.py", content=code)]
    trees, err = pv._parse_all(files)
    return pv._code_contains_match(
        tok, pv._all_identifiers(trees), pv._code_without_comments_strings(code).lower(), code.lower(), err is None
    )


_GPT_CODE = """import torch
optimizer = torch.optim.AdamW([])
optimizer.zero_grad(set_to_none=True)
class Block:
    def f(self, x):
        x = x + self.sa(self.ln1(x))
        return x
"""


def test_expression_target_matches_exact_code_regardless_of_spacing():
    assert _cc("optimizer.zero_grad(set_to_none=True)", _GPT_CODE)  # was unsatisfiable
    assert _cc("x+self.sa(self.ln1(x))", _GPT_CODE)


def test_expression_target_does_not_pass_on_unrelated_code():
    unrelated = "x = 1\\nprint(x)\\n"
    assert not _cc("x+self.sa(self.ln1(x))", unrelated)  # used to pass via last ident `x`
    assert not _cc("x[:,:t+1].mean", unrelated)


def test_expression_target_on_unparseable_code_uses_squeezed_substring():
    mojo = "fn main():\\n    var x: Int = 1\\n"
    assert _cc("fn main()", mojo)
    assert not _cc("fn add(", mojo)


# --- goal / intro scrub must keep normal prose with lists -----------------------
def test_scrub_keeps_ai_goal_and_intro_with_topic_lists():
    from backend.project_planner import scrub_project_learner_copy

    goal = ("Learn Mojo fundamentals by writing and running scripts that cover variables, control flow, "
            "functions, structs, memory ownership, SIMD, metaprogramming, packaging, and CLI build/run workflows.")
    intro = ("Mojo combines Python-like syntax with systems-level performance. This course walks through the "
             "language features so you can write, build, and run Mojo code on your own machine.")
    p = _project(["Mojo"], "Structs group data and methods together in Mojo.", "struct Point")
    p.project_goal, p.course_intro = goal, intro
    scrub_project_learner_copy(p)
    assert p.project_goal == goal
    assert p.course_intro == intro


def test_scrub_still_wipes_caption_dump_goal_and_template_has_no_banned_phrase():
    from backend.project_copy import contains_banned_video_phrase
    from backend.project_planner import _synthesize_project_goal, scrub_project_learner_copy

    p = _project(["Mojo"], "Structs group data and methods together in Mojo.", "struct Point")
    p.project_goal = "so um basically we we are gonna like build the the thing you know"
    p.course_intro = "uh so yeah um today we we go"
    scrub_project_learner_copy(p)
    assert "um" not in p.project_goal.split()
    assert p.course_intro == ""
    for g in (_synthesize_project_goal("Mojo course", ["Mojo", "Modular"]), _synthesize_project_goal("X", [])):
        assert not contains_banned_video_phrase(g), g
        assert "source" not in g.lower()


# --- post-PASS enrichment must not rewrite reviewed content ---------------------
class _EnrichProvider:
    def __init__(self):
        self.calls = 0

    async def generate_structured(self, system, user, max_tokens=0):
        self.calls += 1
        if '"intro"' in user:
            return json.dumps({"intro": "A brand new intro that replaces the reviewed one entirely here."})
        return json.dumps({str(i): {"hook": "New hook", "action": "Print Hello, Mojo! instead",
                                    "teach": "A much longer rewritten teach that contradicts the reviewed checks entirely.",
                                    "example": 'print("Hello, Mojo!")', "celebrate": "Yay 🎉",
                                    "observation": "New obs"} for i in range(1, 10)})


def test_fill_only_enrich_keeps_reviewed_fields_and_fills_empty_ones():
    from backend.project_enrich import enrich_project

    p = _project(["Mojo"], "Structs group data and methods.", "struct Point")
    p.course_intro = "Reviewed intro stays."
    for m in p.milestones:
        m.example, m.hook, m.celebrate = "print(1)", "", ""
    before = [(m.teach, m.microstep.action, m.example) for m in p.milestones]
    asyncio.run(enrich_project(_EnrichProvider(), p, fill_only=True))
    assert [(m.teach, m.microstep.action, m.example) for m in p.milestones] == before
    assert p.course_intro == "Reviewed intro stays."
    assert all(m.hook == "New hook" for m in p.milestones if m.checks[0].kind not in ("file_exists", "run_ok"))


def test_fill_only_enrich_makes_no_call_when_nothing_is_empty():
    from backend.project_enrich import enrich_project

    p = _project(["Mojo"], "Structs group data and methods.", "struct Point")
    p.course_intro = "Reviewed intro."
    for m in p.milestones:
        m.example, m.hook, m.celebrate, m.microstep.observation = "x", "h", "c", "o"
    prov = _EnrichProvider()
    asyncio.run(enrich_project(prov, p, fill_only=True))
    assert prov.calls == 0


def test_enrich_filler_strip_keeps_hyphenated_like():
    from backend.project_enrich import _sanitize

    assert "Python-like" in _sanitize("Mojo uses Python-like syntax.", 200)
    assert " like " not in _sanitize("so like we build it", 200)


def test_literal_backslash_n_in_action_becomes_real_newline():
    from backend.ai_course_generator import course_dict_to_project

    data = _good_course_json()
    data["course"]["milestones"][0]["action"] = "1. Edit `main.py`.\\n2. Add `x = 1`.\\n   3. Run it."
    proj = course_dict_to_project(data["course"], doc=_doc(), title="T", course_id="c-nl")
    act = proj.milestones[0].microstep.action
    assert "\\n" not in act
    assert [ln.strip() for ln in act.split("\n")] == ["1. Edit `main.py`.", "2. Add `x = 1`.", "3. Run it."]


def test_precheck_flags_more_than_12_milestones_as_merge():
    from backend.ai_course_generator import local_precheck_course

    p = _project(["Python"], "Values hold data and gradients for autograd.", "class Value")
    base = p.milestones[1]
    p.milestones = p.milestones + [
        base.model_copy(update={"id": f"x{i}", "order": 10 + i, "title": f"Extra {i}"}) for i in range(8)
    ]
    defects = local_precheck_course(p)
    assert any("Too many milestones (14)" in d and "MERGE" in d for d in defects)
    p.milestones = p.milestones[:12]
    assert not any("Too many milestones" in d for d in local_precheck_course(p))


# --- multi-line code in action/example survives; filename-as-code flagged -------
_MOJO_BLOCK = "struct Point:\n    var x: Int\n    var y: Int\n\n    fn __init__(inout self, x: Int, y: Int):\n        self.x = x\n        self.y = y"


def test_example_and_action_keep_multiline_code():
    from backend.ai_course_generator import course_dict_to_project

    data = _good_course_json()
    data["course"]["milestones"][0]["example"] = _MOJO_BLOCK.replace("\n", "\\n")
    data["course"]["milestones"][0]["action"] = "1. In `main.py`, add:\\nx = 1\\nif x:\\n    print(x)"
    proj = course_dict_to_project(data["course"], doc=_doc(), title="T", course_id="c-ml")
    assert proj.milestones[0].example == _MOJO_BLOCK
    assert "\n    print(x)" in proj.milestones[0].microstep.action


def test_raw_detectors_do_not_wipe_multiline_code():
    from backend.project_copy import looks_like_raw_transcript as copy_raw
    from backend.project_planner import looks_like_raw_transcript as plan_raw

    assert not copy_raw(_MOJO_BLOCK, max_len=1200)
    assert not plan_raw(_MOJO_BLOCK)
    assert plan_raw("so um basically we we go\nand uh like yeah")


def test_precheck_flags_filename_as_code_contains():
    from backend.ai_course_generator import local_precheck_course

    p = _project(["Mojo"], "Structs group data and methods together.", "main.mojo")
    assert any("is a file name" in d for d in local_precheck_course(p))
    p2 = _project(["Mojo"], "Structs group data and methods together.", "struct Point")
    assert not any("is a file name" in d for d in local_precheck_course(p2))


def test_validate_project_accepts_list_goal_comma_teach_and_long_action():
    """Regression (makemore 02:15): review PASSed, then validate_project rejected the
    course because the goal listed topics (>=3 commas) and re-capped actions at 400."""
    from backend.project_planner import validate_project

    p = _project(["PyTorch"], "Bigrams count, normalize, sample, and score character pairs, so we learn the basics.",
                 "torch.multinomial")
    p.project_goal = ("Build a character-level bigram language model in PyTorch: count pairs, normalize rows, "
                      "sample names, compute the negative log likelihood, and train a one-layer network.")
    long_action = "1. In `main.py`, add:\n" + "\n".join(f"W{i} = torch.randn((27, 27))" for i in range(35))
    assert 800 < len(long_action) <= 1000
    p.milestones[0].microstep.action = long_action
    validate_project(p)
    assert p.milestones[0].microstep.action == long_action


def test_validate_project_still_rejects_caption_dump_goal():
    import pytest as _pytest

    from backend.project_planner import validate_project

    p = _project(["PyTorch"], "Bigrams model pairs of characters.", "torch.multinomial")
    p.project_goal = "so um basically we we are gonna like build the the thing you know"
    with _pytest.raises(Exception):
        validate_project(p)
