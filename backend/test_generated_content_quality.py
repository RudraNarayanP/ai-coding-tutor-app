"""Guards on the custom-course generator's own content.

Generated courses bypass the hand-authored curriculum, so the leak audit never
sees them until a learner builds one. These checks pin the generator's
hard-coded fallbacks and its prompt instead.

The fallbacks used to be actively bad: one starter was literally
`# Solution code for {topic}` followed by a `print`, another was
`def process_content(): return 'success'` (a pre-solved body), and a third was
`# Review solution` with `result = True`. The prompt never asked for an
unsolved skeleton at all.
"""

import re
from pathlib import Path

import pytest

from backend.exercise_types import requires_answer_key

GENERATOR = Path(__file__).resolve().parent / "custom_course_generator.py"
SOURCE = GENERATOR.read_text(encoding="utf-8")

SOLUTION_LABELS = re.compile(
    r"#\s*solution code|#\s*review solution|#\s*check .*solution", re.IGNORECASE
)
PRESOLVED_BODIES = re.compile(
    r"return '(?:success|done|ok|True)'|result = True|return \{\s*'role'.*\}"
)


def starter_literals() -> list[str]:
    """Every starter-code string the generator can hand to a lesson."""
    return re.findall(r'starter_code\s*=\s*(f?"(?:[^"\\]|\\.)*")', SOURCE)


def rendered(literal: str) -> str:
    """Best-effort view of a (possibly f-)string literal's content."""
    body = literal[2:-1] if literal.startswith('f"') else literal[1:-1]
    body = re.sub(r"\{[^{}]*\}", "Topic", body)
    return body.encode().decode("unicode_escape")


# ---------------------------------------------------------------------------
# Fallback starters
# ---------------------------------------------------------------------------

def test_the_generator_has_starter_fallbacks_to_check():
    assert len(starter_literals()) >= 4, "expected the generator's fallback starters"


@pytest.mark.parametrize("literal", starter_literals(), ids=lambda lit: rendered(lit)[:40])
def test_no_fallback_starter_is_labelled_as_a_solution(literal):
    text = rendered(literal)
    assert not SOLUTION_LABELS.search(text), f"starter announces itself as a solution: {text!r}"


@pytest.mark.parametrize("literal", starter_literals(), ids=lambda lit: rendered(lit)[:40])
def test_no_fallback_starter_is_pre_solved(literal):
    text = rendered(literal)
    assert not PRESOLVED_BODIES.search(text), f"starter already contains the answer: {text!r}"


@pytest.mark.parametrize("literal", starter_literals(), ids=lambda lit: rendered(lit)[:40])
def test_every_fallback_starter_invites_work(literal):
    text = rendered(literal)
    if not text.strip():
        # An intentionally empty starter is right for choice-type items, which
        # have no editor at all.
        return
    assert re.search(r"# TODO|write your|implement|below", text, re.IGNORECASE), (
        f"starter neither asks for work nor leaves a slot: {text!r}"
    )


# ---------------------------------------------------------------------------
# The prompt itself
# ---------------------------------------------------------------------------

def test_prompt_asks_for_an_unsolved_skeleton():
    assert re.search(r"UNSOLVED skeleton", SOURCE), (
        "the generator prompt must tell the model not to pre-solve starters"
    )


def test_prompt_does_not_ask_for_answers_inside_prompts():
    # The schema legitimately asks for correct_answer/explanation fields; it
    # must not ask for them to be embedded in the learner-facing prompt.
    assert "starter_code" in SOURCE


# ---------------------------------------------------------------------------
# Generated exercise objects
# ---------------------------------------------------------------------------

def test_synthetic_mcq_fallback_does_not_default_to_the_first_option():
    """`correct_answer or options[0]` would make option 1 correct by default."""
    line = next((l for l in SOURCE.splitlines() if "correct_answer=ans" in l), "")
    assert line, "expected the synthetic MCQ fallback to remain visible to this test"
    assert "clean_opts[0]" not in line, (
        "synthetic MCQs must not silently mark the first option correct: " + line.strip()
    )


def test_answer_keyed_types_are_the_ones_the_generator_emits():
    emitted = set(re.findall(r'"type":\s*"(\w+)"', SOURCE)) | set(
        re.findall(r"type=[\"\'](\w+)[\"\']", SOURCE)
    )
    for ex_type in emitted:
        if requires_answer_key(ex_type):
            assert "correct_answer" in SOURCE
