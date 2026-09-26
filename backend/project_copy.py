"""Learner-facing copy for Create Course guided-project milestones.

The planner must stay source-grounded, but the *learner* should never see a raw
YouTube caption dump as a description, Why explanation, or instruction. This
module turns a milestone's structured check (import / symbol / …) into concise
tutorial-grounded copy, and sanitizes already-persisted courses on read.

Used only by Create Course (planner, enrichment, ProjectView, guidance).
"""
from __future__ import annotations

import re
from .speech_fillers import HEDGE_SORT_KIND
from typing import Any

from .project_models import Microstep, Milestone

# Learner-facing caps. These are content limits, not CSS truncation: a caption
# dump is replaced with generated copy rather than sliced mid-sentence.
MAX_DESCRIPTION = 280
MAX_WHY = 420
MAX_QUOTE = 160
MAX_ACTION = 1000  # AI actions often carry short code steps; 400 cut them mid-token
MAX_HINT = 280
MAX_TEACH = 900
MAX_HOOK = 160
# Worked examples carry whole functions/classes (ultra micrograd m4 was cut mid-token
# at 1200 chars, 03:41 IST). Cap generously and only ever at a line boundary.
MAX_EXAMPLE = 2400


def cap_code(text: str | None, max_len: int = MAX_EXAMPLE) -> str:
    t = text or ""
    if len(t) <= max_len:
        return t
    cut = t[:max_len]
    nl = cut.rfind("\n")
    return (cut[:nl] if nl > max_len // 2 else cut).rstrip()

_FILLERS = re.compile(
    r"\b(um+|uh+|you know|" + HEDGE_SORT_KIND + r"|and so(?: it's)?|going to|gonna|"
    r"right so|basically|yeah|welcome back)\b",
    re.IGNORECASE,
)
_AWKWARD_IMPORT = re.compile(
    r"Add an\s+[`'\"]?import\s+",
    re.IGNORECASE,
)



# Learner-facing copy must NEVER assume a video player or instructor to copy.
# Shared with planner scrub, enrich sanitize, and AI local_precheck.
BANNED_VIDEO_PHRASES: tuple[str, ...] = (
    "as in the video",
    "in the video",
    "from the video",
    "watch the video",
    "follow the video",
    "follow the instructor",
    "the way the video",
    "as shown in the video",
    "shown in the video",
    "matching the video",
    "like the tutorial",
    "as demonstrated",
    "refer to the video",
    "type the instructor",
    "the instructor snippet",
    "the instructor builds",
    "the instructor's",
    "as shown",
    "from this video section",
    "video section",
    "chapter of the video",
    "chapters of the video",
    "the video's",
    "the video does",
    "the video shows",
    "rest of the video",
    "built from the video",
    "next up from the video",
    "you've built the video",
    # Source / transcript dependency — learner has no external player.
    "follow the source",
    "follow the transcript",
    "follow this source",
    "follow the tutorial source",
    "as in the source",
    "as in the transcript",
    "according to the video",
    "according to the source",
    "according to the transcript",
    "according to the instructor",
    "from the source for this",
    "copied from the transcript",
    "paste from the transcript",
    "see the source",
    "see the transcript",
    "refer to the source",
    "refer to the transcript",
    "matching the source",
    "matching the transcript",
    "like the source",
    "copy the source",
    "open the youtube",
    "watch on youtube",
    # Hollow polish templates (used to be injected over cleared AI teach/why).
    "real section of the tutorial",
    "real chapter of the tutorial",
    "moves your project toward the",
)

# Alias: same list; tests and precheck use the learner-facing name.
BANNED_LEARNER_PHRASES: tuple[str, ...] = BANNED_VIDEO_PHRASES


def contains_banned_video_phrase(text: str | None) -> bool:
    """True when learner-facing text references a video/instructor to copy."""
    if not (text or "").strip():
        return False
    low = text.lower()
    return any(p in low for p in BANNED_VIDEO_PHRASES)


def first_banned_video_phrase(text: str | None) -> str | None:
    if not (text or "").strip():
        return None
    low = text.lower()
    for p in BANNED_VIDEO_PHRASES:
        if p in low:
            return p
    return None


def contains_banned_learner_phrase(text: str | None) -> bool:
    """True when learner copy depends on video/source/transcript/instructor."""
    return contains_banned_video_phrase(text)


def first_banned_learner_phrase(text: str | None) -> str | None:
    return first_banned_video_phrase(text)


_FOLLOW_SOURCE_HINT = re.compile(
    r"follow\s+the\s+(?:source|transcript|video|tutorial|instructor)"
    r"|as\s+in\s+the\s+(?:source|transcript|video)"
    r"|according\s+to\s+the\s+(?:source|transcript|video|instructor)",
    re.IGNORECASE,
)


def is_follow_source_template(text: str | None) -> bool:
    """True for hollow hints/actions that tell the learner to follow external source."""
    if not (text or "").strip():
        return False
    return bool(_FOLLOW_SOURCE_HINT.search(text))


def _is_multiline_code(text: str) -> bool:
    """Multi-line code (e.g. a Mojo/Python block in action/example) is not a caption dump."""
    lines = [ln for ln in (text or "").split("\n") if ln.strip()]
    if len(lines) < 2:
        return False
    codey = sum(1 for ln in lines if re.search(r"[(){}\[\]=:]|^\s{2,}\S", ln))
    return codey >= max(2, len(lines) // 2)


def looks_like_raw_transcript(text: str | None, *, max_len: int = MAX_DESCRIPTION) -> bool:
    """True when text is a caption dump rather than learner-facing tutorial copy.

    Structured beginner instructions (numbered steps, backticks) may be 30–50
    words and must survive. Only wipe clear STT/filler dumps.
    """
    if not text:
        return False
    raw = text.strip()
    if not raw:
        return False
    stripped = re.sub(r"\s+", " ", raw)
    fillers = len(_FILLERS.findall(stripped))
    if _is_multiline_code(raw):
        return fillers >= 2
    if fillers >= 2:
        return True
    if fillers >= 1 and len(stripped.split()) > 40:
        return True
    structured = bool(
        re.search(r"(?m)^\s*\d+[.)]\s", raw)
        or "`" in raw
        or re.search(r"(?i)\b(import|from .+ import|def |class |print\()", raw)
    )
    words = stripped.split()
    if len(stripped) > max_len and not structured:
        return True
    if len(words) > 70 and not structured:
        return True
    stops = stripped.count(".") + stripped.count("!") + stripped.count("?")
    if len(stripped) > 160 and stops <= 1 and fillers >= 1 and not structured:
        return True
    # Multi-word STT doubles (case-insensitive).
    if re.search(r"\b((?:\w+\s+){1,3}\w+)\s+\1\b", stripped, re.IGNORECASE):
        return True
    # Single-word doubles only when same-case (avoids "up Up" title glitches).
    if re.search(r"\b(\w+)\s+\1\b", stripped):
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
        return (
            f"Build “{label}” in `{entry}` using the tutorial steps. "
            f"Include `{pretty}` as you implement this section."
        )
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
            f"`{pretty}` is the piece of “{project}” this step adds; the next "
            f"milestones build directly on it."
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


_WEAK_ACTION = re.compile(
    r"(?:so your code references|your code should reference|code references|doesn.t reference)\s*`[^`]+`"
    r"|Implement this step so your code references"
    r"|Complete this step:\s*",
    re.IGNORECASE,
)


def is_weak_learner_action(text: str | None) -> bool:
    """True for empty or pass/fail jargon that should become beginner steps."""
    if not (text or "").strip():
        return True
    return bool(_WEAK_ACTION.search(text))


def needs_learner_fallback(text: str | None, *, max_len: int = MAX_ACTION) -> bool:
    """True when text is empty, STT-like, weak, awkward, or banned learner language.

    Non-empty clean AI copy must survive polish — only replace when this is True.
    """
    if not (text or "").strip():
        return True
    if contains_banned_learner_phrase(text) or is_follow_source_template(text):
        return True
    if looks_like_awkward_instruction(text):
        return True
    if is_weak_learner_action(text):
        return True
    if looks_like_raw_transcript(text, max_len=max_len):
        return True
    if len(text.strip()) > max_len:
        return True
    return False


def beginner_action(
    kind: str,
    target: str,
    *,
    entry_file: str = "main.py",
    title: str = "",
    source_label: str = "",
) -> str:
    """Concrete beginner steps grounded in the section title — what to type/import/check."""
    entry = entry_file or "main.py"
    # Long chapter titles blow past the UI action budget; keep the label short.
    raw_label = (title or "").strip() or "this step"
    label = raw_label if len(raw_label) <= 48 else (raw_label[:45].rstrip() + "…")
    context = f"{label} {source_label} {target}".lower()
    token = (target or "").split("|")[0].strip()
    alts = [t.strip() for t in (target or "").split("|") if t.strip()]

    if kind == "import":
        pkg = code_ident_for_import(target)
        return (
            f"1. Open `{entry}` and add `import {pkg}` at the top "
            f"(or `from {pkg} import ...`).\n"
            f"2. Save the file — NEXT checks that `{pkg}` is imported."
        )
    if kind == "symbol":
        return (
            f"1. In `{entry}`, create `{target}` (a function, class, or assignment).\n"
            f"2. Keep the name exactly `{target}` — e.g. `fn {target}(...):` / `def {target}(...):` or `{target} = ...`.\n"
            f"3. Save, then click NEXT."
        )
    if kind == "function_call":
        return (
            f"1. In `{entry}`, add a line that calls `{target}(...)`.\n"
            f"2. Pass the arguments this section of the tutorial uses.\n"
            f"3. Optionally `print(...)` the result so you can see it."
        )
    if kind == "file_exists":
        return (
            f"1. Create `{target or entry}` in the workspace.\n"
            f"2. Add a short comment describing the project goal.\n"
            f"3. Click NEXT when the file exists."
        )
    if kind == "stdout_contains":
        return (
            f"1. In `{entry}`, add a `print(...)` that shows what you just computed.\n"
            f"2. Run the file and confirm something appears in the terminal."
        )
    if kind == "run_ok":
        return (
            f"1. Run `{entry}` with the Run button.\n"
            f"2. Fix any errors until it finishes cleanly, then click NEXT."
        )
    if kind == "code_contains":
        how = f"`{token}`" if token else label
        alt_note = ""
        if len(alts) > 1:
            alt_note = " (or " + " / ".join(f"`{a}`" for a in alts[1:3]) + ")"
        # Language-intro / syllabus chapters (Mojo, Python basics) must not get
        # ML-library copy. Also use word boundaries so "datatypes" ≠ "data".
        lang_intro = bool(re.search(
            r"\b(variable|datatype|data\s*types?|hello\s+world|if/?else|conditional|"
            r"loops?|functions?|oop|struct|mojo|simd|declaration|user\s+input|"
            r"setting\s+up|setup|print|cli|metaprogramming|decorator|ownership|"
            r"borrow)\b",
            context,
        ))
        if (not lang_intro) and re.search(
            r"\b(pandas|sklearn|csv|dataset|looking at data|"
            r"load(?:ing)?(?:\s+the)?\s+data|inspect(?:ing)?|"
            r"analy[sz](?:e|ing|is)|explor(?:e|ing|atory))\b",
            context,
        ):
            return (
                f"1. In `{entry}`, import the libraries this section uses "
                f"(often `pandas` and `sklearn`).\n"
                f"2. Load the dataset (e.g. `pd.read_csv(...)`) and inspect it with "
                f"`.head()`, `.shape`, or `.describe()`.\n"
                f"3. Keep {how}{alt_note} in mind — you'll use it as the model after the data is ready."
            )
        if (not lang_intro) and re.search(r"k-?nearest|\bknn\b", context):
            return (
                f"1. Import `{token or 'KNeighborsClassifier'}` from sklearn.\n"
                f"2. Create the classifier and call `.fit` on your training data.\n"
                f"3. Predict on a sample and print the result."
            )
        if (not lang_intro) and re.search(
            r"\b(linear\s+regression|support\s+vector|\bsvm\b|k-?means|"
            r"train(?:ing)?\s+(?:the\s+)?model|fit(?:ting)?\s+(?:the\s+)?model)\b",
            context,
        ):
            return (
                f"1. Import `{token or 'LinearRegression'}` (from `sklearn.linear_model` if needed).\n"
                f"2. Create the model, e.g. `model = {token or 'LinearRegression'}()`.\n"
                f"3. Fit it with `model.fit(X, y)`, then print a score or a prediction."
            )
        if (not lang_intro) and re.search(r"\b(plot|matplotlib|visuali[sz])\b", context):
            return (
                f"1. Import `matplotlib.pyplot as plt` (and any data libs you need).\n"
                f"2. Plot the data or results this section shows.\n"
                f"3. Call `plt.show()` or print a confirmation."
            )
        lang_hint = ""
        if entry.endswith(".mojo"):
            lang_hint = (
                f" If `{entry}` ends with .mojo, use Mojo "
                f"(`fn`/`var`/`let`/`struct`), not Python-only `def`."
            )
        return (
            f"1. Open `{entry}` and implement “{label}” from this tutorial section.\n"
            f"2. Type the code for this step — include {how}{alt_note}.{lang_hint}\n"
            f"3. Run a quick check (`print` or a call) so you can see it working."
        )
    return (
        f"1. Implement “{label}” in `{entry}`.\n"
        f"2. Finish this tutorial section, then click NEXT."
    )


def learner_action(kind: str, target: str, *, entry_file: str, title: str) -> str:
    return beginner_action(kind, target, entry_file=entry_file, title=title)


def beginner_observation(kind: str, target: str, *, title: str = "") -> str:
    label = (title or "").strip() or "this section"
    if kind == "import":
        pkg = code_ident_for_import(target)
        return f"First tools: import `{pkg}` so later steps can use it."
    if kind == "symbol":
        return f"Next, define `{target}` — a building block for “{label}”."
    if kind == "function_call":
        return f"Now run `{target}` so this part of the project actually executes."
    if kind == "code_contains":
        return f"Build “{label}” step by step in your file, following this tutorial section."
    if kind == "stdout_contains":
        return "Time to see output — a print confirms your code works."
    if kind == "run_ok":
        return "Run the whole project and confirm it works end-to-end."
    if kind == "file_exists":
        return "Your project workspace is ready — start with the entry file."
    return f"Next up: {label}."


def beginner_teach(kind: str, target: str, *, title: str = "", source_label: str = "") -> str:
    """Short teach blurb for chapter milestones when the LLM is not used."""
    label = (title or "").strip() or "this step"
    token = (target or "").split("|")[0].strip()
    context = f"{label} {source_label}".lower()
    if kind == "import":
        pkg = code_ident_for_import(target)
        return (
            f"Libraries are tools you borrow. Importing `{pkg}` makes its functions "
            f"available in your file so you can follow the tutorial without rewriting them."
        )
    if kind == "symbol":
        return (
            f"`{target}` is a name you create so later lines can reuse this logic. "
            f"Matching the tutorial's name keeps later steps easy to follow."
        )
    if kind == "function_call":
        return (
            f"Defining code isn't enough — calling `{target}(...)` is what makes it run. "
            f"This is how the tutorial produces a visible result."
        )
    if kind == "code_contains":
        lang_intro = bool(re.search(
            r"\b(variable|datatype|data\s*types?|hello\s+world|if/?else|conditional|"
            r"loops?|functions?|oop|struct|mojo|simd|declaration|user\s+input|"
            r"setting\s+up|setup|print|cli|metaprogramming|decorator|ownership|"
            r"borrow)\b",
            context,
        ))
        if (not lang_intro) and re.search(
            r"\b(pandas|sklearn|csv|dataset|looking at data|"
            r"load(?:ing)?(?:\s+the)?\s+data|inspect(?:ing)?|"
            r"analy[sz](?:e|ing|is)|explor(?:e|ing|atory))\b",
            context,
        ):
            return (
                f"Before fitting a model, load and inspect the dataset so its shape "
                f"and columns are clear. `{token or 'the model class'}` comes after the data is trusted."
            )
        return (
            f"This step adds `{token or 'the key idea'}` for “{label}”. Once it is in "
            f"your file, later milestones can call and extend it."
        )
    if kind in ("run_ok", "stdout_contains"):
        return "Running end-to-end proves the pieces work together — the tutorial's intended outcome."
    return f"This step, “{label}”, keeps your workspace aligned with the source tutorial."


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
        return (
            f"Type the code from this section in your file. "
            f"When it works, you should see `{first}` appear in the code."
        )
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


# Signatures of canned polish/planner copy — never recycle these as "AI" teach.
_TEMPLATE_COPY = re.compile(
    r"using the tutorial steps|as you implement this section|the source covers this as|"
    r"so later steps in this project can use it|so this tutorial step actually runs|"
    r"is the piece of .{1,80} this step adds|later milestones can call and extend it",
    re.IGNORECASE,
)


def _ai_teach_fallback(milestone) -> str:
    """Reuse the model's own description as teach before any canned template."""
    desc = (getattr(milestone, "source_grounded_description", "") or "").strip()
    if not desc or contains_banned_learner_phrase(desc) or looks_like_raw_transcript(desc):
        return ""
    if _TEMPLATE_COPY.search(desc):
        return ""
    if desc == (getattr(milestone, "why", "") or "").strip():
        return ""
    return _first_sentences(desc, 2, MAX_TEACH)


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
    if not _keep(description, max_len=MAX_DESCRIPTION) or contains_banned_learner_phrase(description):
        description = learner_description(
            kind, target, title=title, entry_file=entry_file, project_title=project
        )

    why = milestone.why or ""
    if not _keep(why, max_len=MAX_WHY) or contains_banned_learner_phrase(why):
        why = learner_why(kind, target, title=title, project_title=project)

    action = milestone.microstep.action if milestone.microstep else ""
    if needs_learner_fallback(action, max_len=MAX_ACTION):
        action = learner_action(kind, target, entry_file=entry_file, title=title)

    hint = milestone.microstep.hint if milestone.microstep else ""
    if (
        needs_learner_fallback(hint, max_len=MAX_HINT)
        or (kind == "import" and _AWKWARD_IMPORT.search(hint or ""))
    ):
        hint = learner_hint(kind, target)

    observation = milestone.microstep.observation if milestone.microstep else ""
    if needs_learner_fallback(observation, max_len=400):
        observation = (
            milestone.hook
            if (milestone.hook and not contains_banned_learner_phrase(milestone.hook))
            else beginner_observation(kind, target, title=title)
        )

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
        if contains_banned_learner_phrase(teach):
            teach = ""
        elif looks_like_raw_transcript(teach) or len(teach) > MAX_TEACH:
            teach = _first_sentences(teach, 2, MAX_TEACH)
        if teach and (looks_like_raw_transcript(teach) or contains_banned_learner_phrase(teach)):
            teach = ""
    if not teach:
        teach = _ai_teach_fallback(milestone)
    if not teach and kind in {"import", "symbol", "function_call", "code_contains"}:
        teach = beginner_teach(kind, target, title=title)

    hook = milestone.hook or ""
    if looks_like_raw_transcript(hook) or len(hook) > MAX_HOOK or contains_banned_learner_phrase(hook):
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
        "example": cap_code(example),
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
