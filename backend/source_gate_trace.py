"""Trace `evaluate_source`'s decision path, branch by branch. Dev-only.

`evaluate_source` answers one word — accept / reject / insufficient — and a word is
not evidence. This module replays its branches in the same order, using the same
predicates, and reports which clause bound plus every intermediate it weighed, so a
refusal can be attributed to a specific condition instead of argued about.

`trace_source_gate` is checked against the production decision for every corpus
member by `backend/test_source_gate_trace.py`: a trace that disagrees with the code
it describes is worse than no trace.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend import source_quality as sq
from backend.source_ingestion import SourceDocument


@dataclass
class GateTrace:
    """Every intermediate `evaluate_source` computes, and the branch that decided."""

    decision: str
    branch: str                       # which clause fired, in source order
    source_kind: str = ""
    stage: str = "analysis"
    reason: str = ""                  # human-readable: what the binding clause lacked
    evidence: list[str] = field(default_factory=list)
    goal: str = ""
    teach: bool = False
    transcript_status: str = ""
    chapters: list[str] = field(default_factory=list)
    implementable_chapters: int = 0
    action_chapters: int = 0
    implementation: bool = False
    has_code_artifact: bool = False
    structure_alternatives: dict[str, bool] = field(default_factory=dict)
    has_enough_structure: bool = False
    conceptual_signals: int = 0
    dangling_and_document: int = 0

    @property
    def condition(self) -> str:
        """The single predicate this decision came down to, stable enough to count."""
        return f"{self.branch}|{self.reason}"


# Branch names, in the order `evaluate_source` reaches them.
BRANCH_INGEST = "stage1-ingestion"
BRANCH_SHAPE = "stage2-source-shape"
BRANCH_CONCEPTUAL = "stage2-conceptual-explainer"
BRANCH_STRUCTURE = "stage2-structure"
BRANCH_ACCEPT = "accept"


#: A Markdown code span the author presents as code: `name`, `name(args)`, `Class`,
#: `pkg.mod`. Not a file name (`main.py`) and not prose inside the span.
CODE_SPAN = re.compile(r"`\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)(\s*\([^`]*\))?`")
_FILE_SUFFIX = re.compile(r"\.(py|js|ts|tsx|jsx|json|md|txt|sh|yml|yaml|toml|csv|html|css|rs|go|java|cpp)$")


def code_spans(text: str) -> list[str]:
    """Names the source itself marks as code, in order of appearance."""
    return [m.group(1) for m in CODE_SPAN.finditer(text or "")
            if not _FILE_SUFFIX.search(m.group(1))]


# ─── counterfactuals: price a candidate rule before writing it ───────────────
#
# Three of the gate's tests ask the same question in different words —
# `has_implementation_cluster`, `_classify_source_type`'s `real_code`, and the fourth
# structure alternative — and all three look for `def`/`class`/`import` written *as
# Python source text*. The candidate mirrors the derivation rule already shipped in
# `project_planner`: a tutorial that writes `mse(y_true, y_pred)` inside a code span is
# naming a definition, because that is the only form Markdown has for saying so.
# Extending `_CODE_DEF` reaches all three tests at once, which makes it one rule
# rather than three exceptions.

#: `` `predict(x, w, b)` `` (a call) or `` `TokenStore` `` (a class); never `main.py`.
SPAN_DEFINITION = re.compile(
    r"`\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*\([^`]*\)|[A-Z][A-Za-z0-9_]*[A-Z][A-Za-z0-9_]*)\s*`"
)


def _extended(pattern: "re.Pattern[str]") -> "re.Pattern[str]":
    return re.compile(pattern.pattern + r"|(?:" + SPAN_DEFINITION.pattern + r")", pattern.flags)


def _spans_count_as_definitions() -> dict:
    return {"_CODE_DEF": _extended(sq._CODE_DEF)}


def _spans_are_distinct_evidence() -> dict:
    """Naming several artifacts in code form must be its own evidence line.

    Needed alongside the candidate above because `extract_technical_evidence` adds one
    entry per *category*: folding code spans into the constructs line changes no count,
    which is how this candidate first hid behind a zero-flip measurement.
    """
    original = sq.extract_technical_evidence

    def patched(text: str, title: str = "") -> list[str]:
        evidence = list(original(text, title))
        named = {s for s in code_spans(title + "\n" + text) if not _FILE_SUFFIX.search(s)}
        if len(named) >= 2 and not any(e.startswith("artifacts named as code") for e in evidence):
            evidence.insert(0, "artifacts named as code: " + ", ".join(sorted(named)[:8]))
        return evidence

    return {"extract_technical_evidence": patched}


#: Named candidates, each a bundle of monkeypatches over `source_quality`.
COUNTERFACTUALS: dict[str, dict] = {
    "spans-count-as-definitions": _spans_count_as_definitions(),
    "spans-are-distinct-evidence": _spans_are_distinct_evidence(),
    "spans-count-everywhere": {
        **_spans_count_as_definitions(), **_spans_are_distinct_evidence(),
    },
}


def with_patch(name: str):
    """Context manager applying one named counterfactual to `source_quality`."""
    import contextlib

    @contextlib.contextmanager
    def apply():
        saved = {}
        for attribute, replacement in COUNTERFACTUALS[name].items():
            saved[attribute] = getattr(sq, attribute)
            setattr(sq, attribute, replacement)
        try:
            yield
        finally:
            for attribute, original in saved.items():
                setattr(sq, attribute, original)

    return apply()


def trace_source_gate(doc: SourceDocument, title: str = "") -> GateTrace:
    """Replay `evaluate_source`'s branch order and report what each one saw."""
    text = sq.gather_source_text(doc)
    chapters = sq._collect_chapters(doc)
    heading = (title or doc.title or "").strip()
    blob = f"{heading}\n{doc.title}\n{text}\n" + "\n".join(chapters)

    # B1 — stage 1 carried over verbatim.
    ingest = sq.evaluate_ingestion(doc)
    if ingest.decision != "accept":
        status, notes = sq.assess_transcript_quality(text, chapter_count=len(chapters))
        return GateTrace(
            decision=ingest.decision, branch=BRANCH_INGEST, stage=ingest.stage,
            source_kind=ingest.source_type, transcript_status=status,
            chapters=chapters,
            reason=("titles-only extraction" if ingest.source_type == "empty_or_failed"
                    and doc.access_level == "titles_only" else f"transcript:{status}"),
        )

    evidence = sq.extract_technical_evidence(text + "\n" + "\n".join(chapters), heading)
    goal = sq.extract_project_goal(text, heading)
    teach = sq._has_strong_teach(blob)
    dangling = len(sq._DANGLING_OBJECT.findall(blob))
    doc_tasks = len(sq._WRITE_DOCUMENT.findall(blob))
    t_status, _notes = sq.assess_transcript_quality(text, chapter_count=len(chapters))
    title_for_class = "\n".join(part for part in (heading, doc.title) if part)
    source_kind = sq._classify_source_type(blob, title_for_class, evidence, chapters)
    implementation = sq.has_implementation_cluster(blob, chapters)
    implementable_chapters = [c for c in chapters if sq.is_implementable_step(c)]
    action = sq._action_chapters(chapters)
    has_artifact = sq.has_code_artifact(blob)
    conceptual = sq._conceptual_signal_count(blob, heading, chapters)

    shared = dict(
        source_kind=source_kind, evidence=evidence, goal=goal, teach=teach,
        transcript_status=t_status, chapters=chapters,
        implementable_chapters=len(implementable_chapters), action_chapters=len(action),
        implementation=implementation, has_code_artifact=has_artifact,
        conceptual_signals=conceptual, dangling_and_document=dangling + doc_tasks,
    )

    # B2 — a shape that is never a coding tutorial, whatever else it contains.
    if source_kind in {"conversation", "news_commentary", "motivational",
                       "assistant_usage", "unrelated"}:
        return GateTrace(decision="reject", branch=BRANCH_SHAPE, reason=source_kind, **shared)

    # B3 — explains a concept, demonstrates nothing.
    if source_kind == "conceptual_explainer" or (not implementation and conceptual >= 2):
        return GateTrace(decision="insufficient", branch=BRANCH_CONCEPTUAL,
                         reason="conceptual_explainer" if source_kind == "conceptual_explainer"
                         else f"no-implementation+{conceptual}conceptual-signals", **shared)

    # B4 — the structure test, whose four alternatives are recorded separately so a
    # refusal names the missing evidence rather than "not enough structure".
    alternatives = {
        "evidence>=2": len(evidence) >= 2,
        "action-chapters>=2+substance": len(action) >= 2 and sq.has_technical_substance(blob),
        "goal+code-artifact+teach": bool(goal) and has_artifact and teach,
        "import-or-def-in-text": bool(sq._CODE_IMPORT.search(blob) or sq._CODE_DEF.search(blob)),
    }
    has_enough = implementation and any(alternatives.values())
    if not has_enough or source_kind == "ambiguous_technical":
        missing = [name for name, ok in alternatives.items() if not ok]
        if not implementation:
            reason = "no-implementation-cluster"
        elif source_kind == "ambiguous_technical":
            reason = "ambiguous_technical" + (":all-four-structure-tests-fail" if not any(alternatives.values()) else "")
        else:
            reason = "structure:" + "+".join(missing)
        return GateTrace(decision="insufficient", branch=BRANCH_STRUCTURE,
                         structure_alternatives=alternatives,
                         has_enough_structure=has_enough, reason=reason, **shared)

    return GateTrace(decision="accept", branch=BRANCH_ACCEPT,
                     structure_alternatives=alternatives, has_enough_structure=True, **shared)
