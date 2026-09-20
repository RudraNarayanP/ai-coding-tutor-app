"""Tests for the AI-hint quality contract (backend/hint_contract.py).

These are the guarantees a learner in a flow state depends on: a hint is
short, plain, actionable, never the answer, and always arrives.
"""

import asyncio

from backend.ai_models import TutorRequest
from backend.ai_provider import AIProviderError, build_user_prompt
from backend.hint_contract import (
    MAX_HINT_CHARS,
    condense,
    hint_system_prompt,
    leak_reasons,
    looks_like_code,
    offline_hint,
    redact_spec,
    repair_hint,
    solution_overlap,
    tidy,
    token_run,
)
from backend.tutor_service import TutorService, TutorSessionStore

SOLUTION = (
    "const createButton = (text) => ({\n"
    "    tag: 'button',\n"
    "    textContent: text,\n"
    "    disabled: false\n"
    "});\n"
    "module.exports = { createButton };\n"
)
STARTER = (
    "// TODO: return the button object\n"
    "const createButton = (text) => ({\n"
    "    tag: '', textContent: '', disabled: true\n"
    "});\n"
    "module.exports = { createButton };\n"
)
GOOD_HINT = (
    "Two checks are still red and both look at the label you return. "
    "Find the line that picks that value and ask what it should be reading from."
)


def run(coroutine):
    return asyncio.run(coroutine)


# ─── code-shape detection ──────────────────────────────────────────────────────

def test_prose_that_mentions_a_call_is_not_treated_as_code():
    assert looks_like_code("Look at createButton(text) before you change anything") is False
    assert looks_like_code("const createButton = (text) => ({") is True
    assert looks_like_code("    return total + 1") is True
    assert looks_like_code("total = 0") is True


# ─── disclosure gradient ───────────────────────────────────────────────────────

def test_redact_spec_hides_literal_values_but_keeps_names():
    out = redact_spec(
        "Implement `createButton(text)` returning `price + price * tax` "
        "as the object { tag: 'button', disabled: false }."
    )
    assert "createButton" in out
    assert "price * tax" not in out
    assert "'button'" not in out
    assert "disabled: false" not in out


def _request(**overrides) -> TutorRequest:
    values = {
        "lesson_id": "js-02",
        "lesson_title": "DOM & Event Fundamentals",
        "instructions": "Implement `createButton(text)` returning { tag: 'button', textContent: text }.",
        "code": STARTER,
        "test_results": [
            {"name": "test_button_text", "passed": False, "required": True, "error": "Expected 'Click Me'"}
        ],
        "hint_level": 1,
        "session_id": "t",
    }
    values.update(overrides)
    return TutorRequest.model_validate(values)


def test_level_one_prompt_withholds_code_test_output_and_literals():
    prompt = build_user_prompt(_request(hint_level=1))
    assert "Student code withheld" in prompt
    assert "Expected 'Click Me'" not in prompt
    assert "tag: 'button'" not in prompt


def test_level_two_prompt_shows_code_but_only_check_names():
    prompt = build_user_prompt(_request(hint_level=2))
    assert "test_button_text" in prompt
    assert "Expected 'Click Me'" not in prompt
    assert STARTER.splitlines()[1] in prompt


def test_level_four_prompt_shows_everything_except_the_solution():
    prompt = build_user_prompt(_request(hint_level=4))
    assert "Deterministic test results" in prompt
    assert "Expected 'Click Me'" in prompt
    assert SOLUTION not in prompt


def test_hint_level_saturates_instead_of_rejecting_the_request():
    assert _request(hint_level=9).hint_level == 4
    assert _request(hint_level=0).hint_level == 1
    assert _request(hint_level="junk").hint_level == 1


def test_level_four_contract_allows_one_more_sentence():
    assert "2-3 sentences" in hint_system_prompt(4)
    assert "2-3 sentences" not in hint_system_prompt(2)


# ─── repair ───────────────────────────────────────────────────────────────────

def test_compliant_hint_passes_through_untouched():
    assert repair_hint(GOOD_HINT) == GOOD_HINT


def test_essay_is_condensed_to_two_plain_sentences():
    essay = (
        "Great work! You are on the right track. The key concept here is that **arrow functions** "
        "let you write concise function expressions. When the function body is a single expression, "
        "you can omit the curly braces and the return keyword, which many learners find surprising.\n\n"
        "- **module.exports** is the standard way to expose your function to the test runner.\n"
        "- Operator precedence matters when combining operations."
    )
    hint = repair_hint(essay)
    assert hint
    assert len(hint) <= MAX_HINT_CHARS
    assert "**" not in hint
    assert "\n- " not in hint
    assert not hint.lower().startswith("great work")


def test_model_self_talk_is_cut_but_the_real_hint_survives():
    hint = repair_hint(
        "Let me analyze the situation. The failing check looks at the label, so find the line "
        "that builds it and ask what that value should depend on."
    )
    assert hint
    assert "Let me analyze" not in hint
    assert hint.startswith("The failing check")


def test_pure_code_dump_is_rejected_not_shipped():
    assert repair_hint("```js\n" + SOLUTION + "```") is None
    assert repair_hint(SOLUTION) is None


def test_code_dump_with_prose_keeps_only_the_prose():
    hint = repair_hint(
        "Your object is built from fixed values, so the label never follows the argument.\n"
        "```\n" + SOLUTION + "```"
    )
    assert hint == "Your object is built from fixed values, so the label never follows the argument."


def test_reference_solution_dump_is_flagged_as_a_leak():
    reasons = leak_reasons(SOLUTION, solution=SOLUTION, starter=STARTER)
    assert any(r.startswith("solution_run") for r in reasons)
    assert repair_hint(SOLUTION, solution=SOLUTION, starter=STARTER) is None


def test_tokens_already_visible_in_the_starter_are_not_a_leak():
    assert solution_overlap("Fix the createButton export line", SOLUTION, STARTER) < 6
    assert solution_overlap(
        "your createButton still returns tag as an empty string", SOLUTION, STARTER
    ) < 6


def test_copied_token_runs_ignore_stopwords():
    source = "return total_price plus tax_amount multiplied twelve_months"
    reply = "you can return total_price plus tax_amount multiplied twelve_months here"
    assert token_run(reply, source) == 6


def test_condense_respects_the_sentence_cap():
    out = condense("One. Two. Three. Four.", max_sentences=2)
    assert out == "One. Two."


def test_tidy_strips_opening_praise_only():
    assert tidy("Nice work! Read the first red check.") == "Read the first red check."


def test_empty_and_oversized_replies_are_unusable():
    assert repair_hint("") is None
    assert repair_hint("   ") is None
    assert repair_hint("x" * 7000) is None


# ─── offline fallback ──────────────────────────────────────────────────────────

def test_offline_hint_is_short_plain_and_points_at_the_failing_check():
    for level in (1, 2, 3, 4):
        hint = offline_hint(
            code=STARTER,
            test_results=[{"name": "test_button_text", "passed": False, "required": True}],
            hint_level=level,
            learning_objective="Model DOM element state as plain objects",
        )
        assert hint, level
        assert len(hint.split()) <= 45, (level, hint)
        assert "```" not in hint and "\n" not in hint
        assert "test_button_text" in hint or "red" in hint
        assert SOLUTION not in hint


def test_offline_hint_escalates_and_does_not_repeat_itself():
    args = dict(code=STARTER, test_results=[{"name": "t1", "passed": False, "required": True}])
    first = offline_hint(hint_level=1, previous_hints=[], **args)
    second = offline_hint(hint_level=1, previous_hints=[first], **args)
    assert first != second


def test_offline_hint_survives_missing_metadata():
    assert offline_hint(code="", test_results=[], hint_level=3)


# ─── the service pipeline: a learner always gets a usable hint ─────────────────

class ScriptedProvider:
    provider_id = "scripted"
    name = "Scripted"
    model = "scripted-1"

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    async def tutor(self, request):
        self.requests.append(request)
        reply = self.replies.pop(0) if self.replies else self.replies_default
        if isinstance(reply, Exception):
            raise reply
        return reply

    replies_default = "Read the first red check and change only the line that produces it."


class DownProvider(ScriptedProvider):
    """Stays down: every call raises, as a missing or blocked provider does."""

    def __init__(self, error):
        super().__init__([])
        self.error = error
        self.calls = 0

    async def tutor(self, request):
        self.requests.append(request)
        self.calls += 1
        raise self.error


def _service(replies):
    service = TutorService(provider=ScriptedProvider(replies), sessions=TutorSessionStore())
    service.backoff_seconds = 0
    return service


def test_clean_model_reply_is_shipped_verbatim():
    service = _service([GOOD_HINT])
    response = run(service.tutor(_request(hint_level=2)))
    assert response.available is True
    assert response.source == "ai"
    assert response.message == GOOD_HINT


def test_code_dump_triggers_a_strict_retry_then_the_clean_second_reply():
    service = _service([SOLUTION, "Look at the fields you return and ask which one follows the argument."])
    response = run(service.tutor(_request(hint_level=3)))
    assert response.source == "ai_repaired"
    assert "```" not in response.message
    assert len(service.provider.requests) == 2
    assert "CONTRACT VIOLATION" in service.provider.requests[1].adaptation_hint


def test_two_bad_replies_fall_back_to_a_deterministic_hint_instead_of_an_error():
    service = _service([SOLUTION, SOLUTION])
    response = run(service.tutor(_request(hint_level=2)))
    assert response.available is True
    assert response.source == "offline"
    assert response.error == "contract_violation"
    assert "```" not in response.message
    assert len(response.message.split()) <= 45


def test_provider_failure_still_delivers_a_hint_and_keeps_the_diagnostic():
    provider = DownProvider(
        AIProviderError("OpenRouter rate limit or quota exceeded.", provider="scripted", code="rate_limit")
    )
    service = TutorService(provider=provider, sessions=TutorSessionStore(), backoff_seconds=0)
    response = run(service.tutor(_request(hint_level=1)))
    assert response.available is True
    assert response.source == "offline"
    assert response.error == "rate_limit"
    assert response.provider is None
    assert provider.calls == 2  # one quick retry, then the fallback


def test_a_throttle_that_clears_immediately_still_produces_an_ai_hint():
    provider = ScriptedProvider(
        [AIProviderError("busy", provider="scripted", code="rate_limit"), GOOD_HINT]
    )
    service = TutorService(provider=provider, sessions=TutorSessionStore(), backoff_seconds=0)
    response = run(service.tutor(_request(hint_level=2)))
    assert response.source == "ai"
    assert response.message == GOOD_HINT
    assert response.error is None


def test_missing_provider_never_leaks_an_error_string_as_a_hint():
    provider = DownProvider(AIProviderError("no key", provider="scripted", code="missing_api_key"))
    service = TutorService(provider=provider, sessions=TutorSessionStore(), backoff_seconds=0)
    response = run(service.tutor(_request(hint_level=3)))
    assert response.available is True
    assert "no key" not in response.message
    assert "rate limit" not in response.message.lower()


def test_lesson_lookup_gives_the_guard_its_reference_solution():
    class Lesson:
        solution_code = SOLUTION
        starter_code = STARTER

    service = _service([SOLUTION, SOLUTION])
    service.lesson_lookup = lambda lesson_id: Lesson()
    response = run(service.tutor(_request(hint_level=4)))
    assert response.source == "offline"
    assert SOLUTION not in response.message


def test_solution_requests_are_never_repaired_or_shortened():
    service = _service(["```js\n" + SOLUTION + "```\nDone."] * 3)
    response = run(service.tutor(_request(hint_level=4, solution_requested=True)))
    assert response.is_solution is True
    assert response.available is True
    assert "```" in response.message
    assert len(service.provider.requests) == 1


def test_every_hint_is_stored_for_the_session_so_levels_build_on_each_other():
    service = _service([GOOD_HINT, "Next, check the export line."])
    run(service.tutor(_request(hint_level=1)))
    run(service.tutor(_request(hint_level=2)))
    assert service.provider.requests[1].previous_hints == [GOOD_HINT]


def test_empty_model_reply_never_reaches_the_learner_as_blank():
    service = _service(["", "   "])
    response = run(service.tutor(_request(hint_level=2)))
    assert response.available is True
    assert response.message.strip()
    assert response.source == "offline"
