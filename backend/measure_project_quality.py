"""Measure guided-project quality signals against the real corpus. Dev script, not a gate.

Run it before adding any rule to ``project_planner.usability_problem``.

    python -m backend.measure_project_quality

Why this exists
---------------
A quality floor was proposed on the theory that a project can pass validation with
"one import check and one run check". It cannot: the existing ``coding < 2`` rule
refuses it. Measuring the actual corpus then showed that the proposed *replacement*
signals do not survive contact with the data, and that the suite already pins the
floor it might otherwise be tempting to raise:

* **Depth does not separate the good from the bad.** The one genuinely poor project
  on disk — the Karpathy talk, planned into 14 milestones of which 9 are
  run/print/setup checkpoints — carries *five* substantive checks. Six of the nine
  accepted projects carry fewer. A rule demanding more steps would reject good
  content while keeping the bad content it was written for, because the talk is not
  thin, it is repetitive.
* **Generic dominance cannot replace the duplicated-title rule.** A course with four
  real steps and two identically-titled "Run and verify" milestones is refused today
  by the blocklist and sits at 0.33 generic. Any "more than half the milestones are
  generic" threshold accepts it, so the blocklist is currently load-bearing. Whether
  it should be replaced by "milestone titles must be distinct" cannot be tested
  here: zero accepted projects repeat a title, so there is no legitimate
  repeated-title project to price the false rejection against.
* **Instructional-copy signals are unusable at load.** ``teach``/``example`` are
  filled by ``enrich_project``, a best-effort LLM call that "must not block a valid
  course". Every project planned without a working provider has empty copy, so a
  rule keyed on it would refuse good projects according to whether an API was
  reachable when they were created.

What would let a rule be added
------------------------------
The corpus is 3 stored projects and 8 planner runs over the transcripts already in
the test suite, with exactly one poor-but-planned example between them. To justify a
threshold, the corpus needs, for each candidate shape, at least one accepted and one
rejected example that the signal separates:

1. a long build-along with several legitimate "run it and see" checkpoints — to
   price generic-dominance and ``run_ok >= 3`` against real content instead of
   against a count;
2. a tutorial whose chapters genuinely repeat a step name, so title-uniqueness can
   be tested for false rejection rather than assumed safe;
3. a second poor source of a *different* kind (a talk with one code mention, a
   course that only configures a tool) — one negative example cannot fit a
   threshold, and 0.5-versus-0.64 is not a margin, it is a coincidence with n=1;
4. several accepted projects with only two substantive steps — to confirm the floor
   the suite already asserts (``test_source_quality`` requires
   ``>= 2`` non-setup, non-run checks) is not accidentally raised by a new rule.

Until those exist, the honest rule set is the current one, and this script is the
evidence that it was checked rather than assumed.
"""

from __future__ import annotations

import importlib
import json
import os
import atexit
import shutil
import tempfile
from collections import Counter
from pathlib import Path

# Importing the test modules pulls in backend.main, which builds stores at import
# time. Redirect every writable path before that happens, exactly as conftest does,
# so running a measurement can never touch a learner's real state.
_ROOT = Path(__file__).resolve().parents[1]
_RUN = tempfile.mkdtemp(prefix="patchwork_measure_")
os.environ.setdefault("PATCHWORK_STATE_DIR", _RUN)
os.environ.setdefault("PATCHWORK_PROJECT_DIR", str(Path(_RUN) / "projects"))
# ...and clean it up on the way out, or every run leaves a directory behind.
atexit.register(shutil.rmtree, _RUN, ignore_errors=True)

from backend.project_models import ProjectCourse  # noqa: E402
from backend.project_planner import plan_project, usability_problem  # noqa: E402
from backend.source_ingestion import SourceDocument  # noqa: E402

SUBSTANTIVE = {"import", "symbol", "function_call", "code_contains"}
TRANSCRIPT_MODULES = ("backend.test_project_planner", "backend.test_source_quality")
MIN_LENGTH = 60


def stored_projects() -> dict[str, ProjectCourse]:
    out: dict[str, ProjectCourse] = {}
    directory = _ROOT / "curriculum" / "generated" / "projects"
    for path in sorted(directory.glob("*.json")):
        try:
            project = ProjectCourse(**json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, Exception):  # noqa: BLE001 - a bad file is not our business
            continue
        # Keyed by course_id, not title: the store legitimately holds two
        # "Word Frequency Counter" projects, and labelling by title silently drops
        # one of them from a corpus whose whole job is counting.
        out[f"stored:{project.course_id[8:]}:{project.title[:18]}"] = project
    return out


def planned_projects() -> dict[str, ProjectCourse]:
    """Plan every real transcript the test suite already carries."""
    out: dict[str, ProjectCourse] = {}
    for module_name in TRANSCRIPT_MODULES:
        module = importlib.import_module(module_name)
        for name in sorted(dir(module)):
            value = getattr(module, name)
            if not (name.isupper() and isinstance(value, str) and len(value) > MIN_LENGTH):
                continue
            title = name.replace("_", " ").title()
            doc = SourceDocument(
                source_type="transcript", source_url="", source_hash="h",
                title=title, plain_text=value,
            )
            try:
                out[f"{module_name.split('.')[-1]}:{name}"] = plan_project(
                    doc, title=title, course_id="measured"
                )
            except Exception:  # noqa: BLE001 - refused sources produce no project, which is the point
                continue
    return out


def signals(project: ProjectCourse) -> dict[str, float | int]:
    checks = [
        (m.checks[0].kind, (m.checks[0].target or "").strip().lower())
        for m in project.milestones if m.checks
    ]
    kinds = [k for k, _ in checks]
    naming = [t for k, t in checks if k in SUBSTANTIVE and t]
    generic = len(kinds) - len(naming)
    titles = Counter((m.title or "").strip().lower() for m in project.milestones)
    return {
        "milestones": len(project.milestones),
        "substantive": len(naming),
        "distinct_steps": len(set(naming)),
        "generic": generic,
        "generic_share": round(generic / max(len(kinds), 1), 2),
        "repeated_titles": sum(c - 1 for c in titles.values() if c > 1),
    }


def main() -> int:
    corpus = {**stored_projects(), **planned_projects()}
    if not corpus:
        print("no projects to measure (no stored files, planner produced none)")
        return 1

    accepted = {n: p for n, p in corpus.items() if usability_problem(p) is None}
    refused = {n: p for n, p in corpus.items() if usability_problem(p) is not None}

    print(f"corpus: {len(corpus)} projects  ({len(accepted)} accepted, {len(refused)} refused)\n")
    width = max(46, max(len(n) for n in corpus) + 2)
    header = f"{'project':<{width}} {'ms':>3} {'sub':>4} {'dist':>5} {'gen':>4} {'share':>6} {'dups':>5}  verdict"
    print(header)
    print("-" * len(header))
    for label, project in sorted(corpus.items()):
        s = signals(project)
        problem = usability_problem(project)
        print(f"{label:<{width}} {s['milestones']:>3} {s['substantive']:>4} {s['distinct_steps']:>5} "
              f"{s['generic']:>4} {s['generic_share']:>6} {s['repeated_titles']:>5}  "
              f"{'refused' if problem else 'accepted'}")

    def span(group: dict[str, ProjectCourse], key: str) -> str:
        if not group:
            return "n/a"
        values = [signals(p)[key] for p in group.values()]
        return f"{min(values)}-{max(values)}"

    print("\nseparation check (a signal is only usable if accepted and refused ranges do not overlap):")
    for key, note in (
        ("substantive", "depth: the poor talk scores 5, most accepted projects score fewer -> NOT a signal"),
        ("generic", "accepted is pinned at 2 because the planner always adds setup + run -> artifact, not signal"),
        ("generic_share", "one refused example only -> a threshold fitted here is fitted to n=1"),
        ("repeated_titles", "no accepted project repeats a title -> false-positive rate unmeasurable"),
    ):
        print(f"  {key:<14} accepted {span(accepted, key):<7} refused {span(refused, key):<7}  {note}")
    print("\nsee this module's docstring for what corpus would make a rule justified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
