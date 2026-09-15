"""Learner-facing copy for Create Course guided-project milestones.

The planner must stay source-grounded, but the *learner* should never see a raw
YouTube caption dump as a description, Why explanation, or instruction. This
module turns a milestone's structured check (import / symbol / …) into concise
tutorial-grounded copy, and sanitizes already-persisted courses on read.

Used only by Create Course (planner, enrichment, ProjectView, guidance).
"""
from __future__ import annotations

import re
from typing import Any

from .project_models import Microstep, Milestone

# Learner-facing caps. These are content limits, not CSS truncation: a caption
# dump is replaced with generated copy rather than sliced mid-sentence.
MAX_DESCRIPTION = 280
MAX_WHY = 420
MAX_QUOTE = 160
MAX_ACTION = 220
MAX_HINT = 220
MAX_TEACH = 420
MAX_HOOK = 120

_FILLERS = re.compile(
    r"\b(um+|uh+|you know|kind of|sort of|and so(?: it's)?|going to|gonna|"
    r"right so|basically|yeah|welcome back)\b",
    re.IGNORECASE,
)
_AWKWARD_IMPORT = re.compile(
    r"Add an\s+[`'\"]?import\s+",
    re.IGNORECASE,
)


def looks_like_raw_transcript(text: str | None, *, max_len: int = MAX_DESCRIPTION) -> bool:
    """True when text is a caption dump rather than a concise learner sentence."""
    if not text:
        return False
    stripped = re.sub(r"\s+", " ", text).strip()
    if not stripped:
        return False
    if len(stripped) > max_len:
        return True
    fillers = len(_FILLERS.findall(stripped))
    stops = stripped.count(".") + stripped.count("!") + stripped.count("?")
    # Spoken captions: long, almost no sentence enders, lots of filler.
    if len(stripped) > 160 and stops <= 1 and fillers >= 2:
        return True
    return False


def looks_like_awkward_instruction(text: str | None) -> bool:
    if not text:
        return False
    if _AWKWARD_IMPORT.search(text):
        return True
    return looks_like_raw_transcript(text, max_len=MAX_ACTION)


def code_ident_for_import(name: str) -> str:
    """Python import names are almost always lowercase; spoken captions Title-Case them.

    CamelCase (BeautifulSoup) and ALLCAPS (PIL, GPT2) are preserved. Unknown
    Title-Case tokens become pep-8 lowercase so instructions stay technically accurate.
    """
    if not name:
        return name
    if name[:1].isupper() and name[1:].islower():
        return name.lower()
    return name


def display_ident(name: str) -> str:
    """Human-readable identifier for titles (transformers → Transformers)."""
    if not name:
        return name
    if name.islower():
        return name[0].upper() + name[1:]
    return name


def short_source_excerpt(text: str | None, *, needle: str = "", max_len: int = MAX_QUOTE) -> str:
    """Keep a tight, local source snippet. Return '' rather than a caption dump."""
    raw = re.sub(r"\s+", " ", (text or "")).strip()
    if not raw:
        return ""
    if len(raw) <= 90 and not looks_like_raw_transcript(raw, max_len=max_len):
        return raw
    snippet = raw
    if needle:
        idx = raw.lower().find(needle.lower())
        if idx != -1:
            start = max(0, idx - 16)
            rest = raw[idx:]
            brk = re.search(r"\s+(?:and then|and so|, and|so we|then we)\b", rest, re.I)
            if brk and brk.start() >= len(needle):
                end = idx + brk.start()
            else:
                end = min(len(raw), start + max_len)
            snippet = raw[start:end].strip(" ,;:-")
            if start > 0:
                snippet = "…" + snippet
            if end < len(raw):
                snippet = snippet.rstrip(" .,;:") + "…"
    elif len(raw) > max_len:
        snippet = raw[: max_len - 1].rstrip() + "…"
    snippet = snippet.strip()
    if not snippet or looks_like_raw_transcript(snippet, max_len=max_len) or len(snippet) > max_len:
        return ""
    return snippet


def _first_sentences(text: str, n: int = 2, max_len: int = MAX_TEACH) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = " ".join(p.strip() for p in parts[:n] if p.strip())
    if len(kept) > max_len:
        kept = kept[: max_len - 1].rstrip() + "…"
    return kept


def learner_description(
    kind: str,
    target: str,
    *,
    title: str,
    entry_file: str,
    project_title: str,
) -> str:
    entry = entry_file or "main.py"
    if kind == "import":
        pkg = code_ident_for_import(target)
        shown = display_ident(pkg)
        return (
            f"Load the {shown} library so you can use it in this project. "
            f"Add the required import to `{entry}`."
        )
    if kind == "symbol":
        return (
            f"Define `{target}` so later steps in this project can use it. "
            f"Add it in `{entry}`."
        )
    if kind == "function_call":
        return f"Call `{target}` so this tutorial step actually runs. Put the call in `{entry}`."
    if kind == "code_contains":
        pretty = (target or "").split("|")[0].strip() or title
        label = title.strip() or pretty
        return f"Implement {label} in `{entry}`. Your code should use `{pretty}`."
    if kind == "file_exists":
        goal = project_title.strip() or "this project"
        return f"Create `{target or entry}` and start building {goal}."
    if kind == "stdout_contains":
        return f"Print a result from this step so you can see it work. Use `{entry}`."
    if kind == "run_ok":
        return "Run your complete project and confirm it works end-to-end."
    return f"Complete this step: {title}." if title else "Complete this tutorial step."


def learner_why(
    kind: str,
    target: str,
    *,
    title: str,
    project_title: str,
) -> str:
    project = project_title.strip() or "this project"
    if kind == "import":
        pkg = code_ident_for_import(target)
        return (
            f"This step matters because later work in “{project}” depends on `{pkg}` "
            f"being available. Importing it first is how the tutorial starts building."
        )
    if kind == "symbol":
        return (
            f"“{project}” needs `{target}` in place before you can use it. "
            f"Defining it now matches the tutorial's build order."
        )
    if kind == "function_call":
        return (
            f"Calling `{target}` is how this tutorial step produces a result. "
            f"Without it, the rest of “{project}” has nothing to run."
        )
    if kind == "code_contains":
        pretty = (target or "").split("|")[0].strip() or title
        return (
            f"This is a real section of the tutorial for “{project}”. "
            f"Building it (using `{pretty}`) moves your project toward the source's result."
        )
    if kind == "file_exists":
        return (
            "A guided project keeps one persistent workspace — this is the file "
            "you will grow across every milestone."
        )
    if kind == "run_ok" or kind == "stdout_contains":
        return (
            "The final check is that the whole project runs — the source's intended outcome, "
            f"not just that individual pieces exist."
        )
    return (
        f"This step, “{title}”, is part of building “{project}” from the tutorial. "
        f"Doing it now keeps your workspace aligned with the source."
    )


def learner_action(kind: str, target: str, *, entry_file: str, title: str) -> str:
    entry = entry_file or "main.py"
    if kind == "import":
        pkg = code_ident_for_import(target)
        return f"Add `import {pkg}` at the top of `{entry}` (or `from {pkg} import ...`)."
    if kind == "symbol":
        return f"Define `{target}` in `{entry}` (function, class, or assignment)."
    if kind == "function_call":
        return f"Call `{target}(...)` somewhere in `{entry}`."
    if kind == "code_contains":
        pretty = (target or "").split("|")[0].strip()
        return f"Implement {title} in `{entry}` — your code should reference `{pretty}`."
    if kind == "file_exists":
        return f"Create `{target or entry}` and add a comment describing the project goal."
    if kind == "stdout_contains":
        return f"Use `print(...)` in `{entry}` so this step produces visible output."
    if kind == "run_ok":
        return "Run your project and make sure it executes without errors."
    return f"Implement “{title}” in `{entry}`."


def learner_hint(kind: str, target: str) -> str:
    if kind == "import":
        pkg = code_ident_for_import(target)
        return f"Use `import {pkg}` or `from {pkg} import ...` — package names are lowercase."
    if kind == "symbol":
        return f"Make sure something named `{target}` is defined at the top level."
    if kind == "function_call":
        return f"Call `{target}(...)` somewhere in your code."
    if kind == "code_contains":
        first = (target or "").split("|")[0].strip()
        return f"Your implementation should use `{first}`."
    if kind == "stdout_contains":
        return "Use `print(...)` to show a result."
    if kind == "file_exists":
        return "Every file you create here persists across the whole course."
    return "Make sure the file runs top-to-bottom without raising an error."


def _check_of(milestone: Milestone) -> tuple[str, str]:
    if not milestone.checks:
        return "", ""
    c = milestone.checks[0]
    return c.kind or "", c.target or ""


def _keep(text: str | None, *, max_len: int = MAX_DESCRIPTION) -> bool:
    if not (text or "").strip():
        return False
    if looks_like_raw_transcript(text, max_len=max_len):
        return False
    if len(text.strip()) > max_len:
        return False
    return True


def learner_facing_fields(
    milestone: Milestone,
    *,
    entry_file: str = "main.py",
    project_title: str = "",
    project_goal: str = "",
) -> dict[str, Any]:
    """Pure projection: concise learner-facing strings. Does not mutate `milestone`."""
    kind, target = _check_of(milestone)
    title = milestone.title or ""
    project = project_title or project_goal or ""

    description = milestone.source_grounded_description or ""
    if not _keep(description, max_len=MAX_DESCRIPTION):
        description = learner_description(
            kind, target, title=title, entry_file=entry_file, project_title=project
        )

    why = milestone.why or ""
    if not _keep(why, max_len=MAX_WHY):
        why = learner_why(kind, target, title=title, project_title=project)

    action = milestone.microstep.action if milestone.microstep else ""
    if not _keep(action, max_len=MAX_ACTION) or looks_like_awkward_instruction(action):
        action = learner_action(kind, target, entry_file=entry_file, title=title)

    hint = milestone.microstep.hint if milestone.microstep else ""
    if (
        not _keep(hint, max_len=MAX_HINT)
        or looks_like_awkward_instruction(hint)
        or (kind == "import" and _AWKWARD_IMPORT.search(hint or ""))
    ):
        hint = learner_hint(kind, target)

    observation = milestone.microstep.observation if milestone.microstep else ""
    if looks_like_raw_transcript(observation):
        observation = milestone.hook or "Next step from the tutorial:"

    quote = short_source_excerpt(
        milestone.source_quote or "",
        needle=code_ident_for_import(target) or target or title.split(" ")[-1],
    )
    # Never repeat the huge description as the quote.
    if quote and (looks_like_raw_transcript(quote) or quote.strip() == description.strip()):
        quote = ""
    if quote and why and quote.strip() == why.strip():
        quote = ""

    teach = milestone.teach or ""
    if teach:
        if looks_like_raw_transcript(teach) or len(teach) > MAX_TEACH:
            teach = _first_sentences(teach, 2, MAX_TEACH)
        if looks_like_raw_transcript(teach):
            teach = ""

    hook = milestone.hook or ""
    if looks_like_raw_transcript(hook) or len(hook) > MAX_HOOK:
        hook = ""

    example = milestone.example or ""
    if looks_like_raw_transcript(example):
        example = ""

    return {
        "title": title,
        "source_grounded_description": description[:MAX_DESCRIPTION],
        "source_quote": quote[:MAX_QUOTE],
        "why": why[:MAX_WHY],
        "teach": teach[:MAX_TEACH],
        "hook": hook[:MAX_HOOK],
        "example": example[:1200],
        "celebrate": milestone.celebrate or "",
        "observation": (observation or "")[:400],
        "action": action[:MAX_ACTION],
        "hint": hint[:MAX_HINT],
    }


def apply_learner_facing_copy(
    milestone: Milestone,
    *,
    entry_file: str = "main.py",
    project_title: str = "",
    project_goal: str = "",
) -> Milestone:
    """Mutate a milestone in place with concise learner-facing copy."""
    fields = learner_facing_fields(
        milestone,
        entry_file=entry_file,
        project_title=project_title,
        project_goal=project_goal,
    )
    milestone.source_grounded_description = fields["source_grounded_description"]
    milestone.source_quote = fields["source_quote"]
    milestone.why = fields["why"]
    milestone.teach = fields["teach"]
    milestone.hook = fields["hook"]
    milestone.example = fields["example"]
    milestone.microstep = Microstep(
        observation=fields["observation"] or milestone.microstep.observation,
        action=fields["action"],
        hint=fields["hint"],
    )
    return milestone


def polish_project_copy(project) -> None:
    """Apply learner-facing copy to every milestone (generation + post-enrichment)."""
    for m in getattr(project, "milestones", []) or []:
        apply_learner_facing_copy(
            m,
            entry_file=getattr(project, "entry_file", "main.py") or "main.py",
            project_title=getattr(project, "title", "") or "",
            project_goal=getattr(project, "project_goal", "") or "",
        )
