"""Server-side fill-blank template construction.

Fill-blank curriculum stores the *solved* program in ``starter_code`` and lists
the tokens the learner must type in ``blanks`` — which is byte-identical to
``correct_answer``. Shipping ``blanks`` to the browser therefore hands over the
answer key, even though the UI only ever needs the blanked template.

This module performs the blanking on the server so the public exercise view can
drop ``blanks`` entirely. The rules mirror ``src/utils/assembleFillBlankCode.ts``
one-for-one; ``backend/test_blank_template.py`` pins that equivalence against
every fill-blank exercise in the curriculum.
"""

from __future__ import annotations

import re

BLANK_TOKEN = "___"


def _strip_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def template_from_question(question: str) -> str:
    """Recover an inline template from a prompt that already carries ``___``."""
    for line in (question or "").splitlines():
        text = line.strip()
        if BLANK_TOKEN in text:
            stripped = re.sub(r"^[^:]+:\s*", "", text).strip()
            return re.sub(r"\s*\([^)]*\)\s*$", "", stripped).strip()
    inline = re.search(r"[`']([^`']*___[^`']*)[`']", question or "")
    if inline:
        return inline.group(1)
    return ""


def build_blank_template(starter_code: str, blanks: list[str], question: str = "") -> str:
    """Return ``starter_code`` with every answer token replaced by ``___``."""
    code = (starter_code or "").strip()

    if BLANK_TOKEN in code:
        return code

    values = [str(blank) for blank in (blanks or []) if str(blank).strip()]

    if not code:
        if values:
            return "\n".join(BLANK_TOKEN for _ in values)
        return BLANK_TOKEN

    template = code
    for blank in values:
        candidates = list(
            dict.fromkeys(
                candidate
                for candidate in (
                    blank,
                    _strip_quotes(blank),
                    f'"{_strip_quotes(blank)}"',
                    f"'{_strip_quotes(blank)}'",
                )
                if candidate
            )
        )
        for candidate in candidates:
            index = template.rfind(candidate)
            if index >= 0:
                template = template[:index] + BLANK_TOKEN + template[index + len(candidate):]
                break
        else:
            template += f"\n{BLANK_TOKEN}"

    if BLANK_TOKEN not in template:
        template += f"\n{BLANK_TOKEN}"

    return template


def public_starter_code(exercise_type: str, starter_code: str, blanks: list[str], question: str) -> str:
    """The starter text a learner may see, with any answer key already removed."""
    if str(exercise_type).lower() not in ("fill_blank", "code_completion"):
        return starter_code
    if not (starter_code or "").strip():
        # The prompt itself carries ``___``; nothing to blank and no key to ship.
        return starter_code
    return build_blank_template(starter_code, blanks, question)
