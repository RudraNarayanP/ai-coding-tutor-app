"""Composition ground truth, measured from code rather than inferred from titles.

Two questions this answers, both about real repository material:

1. Do the lessons of a curriculum unit actually depend on each other? Computed from
   the AST of every module's `starter_code`/`solution_code`: a lesson *depends* on an
   earlier one when it calls it, passes it, or imports it — never on shared words or
   similar names, which is what makes `foo` appearing twice meaningless as evidence.

2. When a source really does compose artifacts, does the planned project express it?
   A guided project is one persistent file, so composition is cheap to state and
   impossible to see from a plan that only lists names.

Dev-only. Imported by `measure_project_quality` and by its tests; it asserts nothing
about policy, because a dependency that no source demonstrates cannot be required, and
one every source demonstrates is already satisfied.
"""

from __future__ import annotations

import ast
import io
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# ─── AST facts about a body of code ──────────────────────────────────────────

def top_level_names(source: str) -> list[str]:
    """Names a body of code makes available: defs, classes, module-level assignments."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            names.extend(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.append(alias.asname or alias.name.split(".")[0])
    return names


def referenced_names(source: str) -> set[str]:
    """Every name the code *uses*: called, loaded, used as an attribute base, or
    bound by an import. Deliberately excludes names bound only inside a string/comment.

    An import counts as a use, not as a local binding: `from micrograd.engine import
    Value` followed by `Value()` is the composition a learner is being taught, and
    treating the imported name as locally bound hides exactly the dependency that
    matters. A name *rebound* in the same body (`predict = 3`) is still excluded by
    `local_bindings`, so a shared word is not mistaken for a shared artifact.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
            base = node
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                used.add(base.id)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                used.add(func.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                used.add(alias.asname or alias.name.split(".")[0])
    return used


def local_bindings(source: str) -> set[str]:
    """Names the code binds itself — parameters, locals, its own defs and assignments.

    A dependency on these is not composition. Import aliases are *not* included; see
    `referenced_names`.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                bound.update(a.arg for a in node.args.args + node.args.posonlyargs
                             + node.args.kwonlyargs)
                if node.args.vararg:
                    bound.add(node.args.vararg.arg)
                if node.args.kwarg:
                    bound.add(node.args.kwarg.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.comprehension) and isinstance(node.target, ast.Name):
            bound.add(node.target.id)
    return bound


def call_sites(source: str) -> list[tuple[str, list[str]]]:
    """(callee, argument names) for every call written as bare identifiers."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out: list[tuple[str, list[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                callee = node.func.id
            elif isinstance(node.func, ast.Attribute):
                callee = node.func.attr
            else:
                continue
            args = [a.id for a in node.args if isinstance(a, ast.Name)]
            args += [k.value.id for k in node.keywords
                     if isinstance(k.value, ast.Name)]
            out.append((callee, args))
    return out


# ─── 1. does a curriculum unit compose? ──────────────────────────────────────

@dataclass
class UnitGraph:
    module: str
    course: str
    lessons: list[str] = field(default_factory=list)
    #: lesson id -> names that lesson defines
    defines: dict[str, list[str]] = field(default_factory=dict)
    #: (earlier lesson, later lesson, name) for each real cross-lesson use
    edges: list[tuple[str, str, str]] = field(default_factory=list)
    #: lesson ids that only ever exercise their own artifact
    isolated: list[str] = field(default_factory=list)

    @property
    def links(self) -> int:
        return len({(a, b) for a, b, _name in self.edges})

    @property
    def referenced_ratio(self) -> float:
        """Share of lessons after the first that consume an earlier lesson's artifact."""
        if len(self.lessons) < 2:
            return 0.0
        consumers = {b for _a, b, _n in self.edges}
        later = self.lessons[1:]
        return round(len([l for l in later if l in consumers]) / len(later), 2)


def curriculum_graphs() -> list[UnitGraph]:
    graphs: list[UnitGraph] = []
    for path in sorted((ROOT / "curriculum").glob("*/modules/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        graph = UnitGraph(module=data.get("id") or path.stem,
                         course=path.parents[1].name)
        bodies: list[tuple[str, str]] = []
        for lesson in data.get("lessons") or []:
            lesson_id = lesson.get("id") or ""
            code = "\n".join(
                part for part in (
                    lesson.get("starter_code") or "",
                    lesson.get("solution_code") or "",
                    "\n".join(t.get("unittest_code") or "" for t in lesson.get("tests") or []),
                ) if part
            )
            graph.lessons.append(lesson_id)
            graph.defines[lesson_id] = top_level_names(code)
            bodies.append((lesson_id, code))
        for index, (lesson_id, code) in enumerate(bodies):
            used = referenced_names(code) - local_bindings(code)
            used -= set(graph.defines[lesson_id])
            earlier: dict[str, str] = {}
            for previous, _prev_code in bodies[:index]:
                for name in graph.defines[previous]:
                    earlier[name] = previous
            hits = sorted(used & set(earlier))
            for name in hits:
                graph.edges.append((earlier[name], lesson_id, name))
            if not hits:
                graph.isolated.append(lesson_id)
        graphs.append(graph)
    return graphs


# ─── 2. when a source composes, does the plan say so? ────────────────────────

FENCED = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.S)
_DUMP_MARKER = re.compile(r"^(STARTER|SOLUTION):\s*(.+)$")
_TEST_MARKER = re.compile(r"^TEST\s+[\w.]+\s*:\s*(.+)$")


def code_blocks(text: str) -> tuple[list[str], int]:
    """Parsable code fragments inside a piece of source material, and how many were lost.

    Three formats appear in this repository's own material, and reading them wrongly is
    the difference between "the source shows no dependency" and "I could not read the
    source": fenced blocks in a pasted README or transcript; `STARTER:`/`SOLUTION:`
    lines holding a *Python repr* of the file, so `\n` is two characters; and
    `TEST name :` lines that mark newlines with `⏎`.

    Each fragment is kept separate on purpose. Joining them and parsing once means one
    malformed fragment silently destroys every dependency in the document, which is
    exactly the bug this function replaced — 9.8 KB of real dump code measured as zero
    edges. The second return value is the count of fragments that will not parse, so a
    reader can tell "no composition" from "could not look".
    """
    fragments: list[str] = [b for b in FENCED.findall(text or "") if b.strip()]
    for line in (text or "").splitlines():
        stripped = line.strip()
        marker = _DUMP_MARKER.match(stripped)
        if marker:
            payload = marker.group(2).strip()
            try:
                payload = ast.literal_eval(payload)
            except (ValueError, SyntaxError):
                payload = payload.replace("\\n", "\n")
            fragments.append(str(payload))
            continue
        test = _TEST_MARKER.match(stripped)
        if test:
            fragments.append(test.group(1).replace("⏎", "\n"))
    kept = [f for f in fragments if f.strip()]
    unparsable = sum(1 for f in kept if not _parses(f))
    return kept, unparsable


def _parses(text: str) -> bool:
    try:
        ast.parse(text)
        return True
    except SyntaxError:
        return False


def definition_bodies(blocks: list[str]) -> dict[str, str]:
    """The source of each top-level def/class, so a reference inside it can be
    attributed to the artifact that made it."""
    bodies: dict[str, str] = {}
    for block in blocks:
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                try:
                    bodies[node.name] = ast.unparse(node)
                except Exception:  # noqa: BLE001 - one odd node is not worth losing the rest
                    continue
    return bodies


def all_call_sites(blocks: list[str]) -> list[tuple[str, list[str]]]:
    out: list[tuple[str, list[str]]] = []
    for block in blocks:
        out.extend(call_sites(block))
    return out


@dataclass
class CompositionFinding:
    project_key: str
    label: str
    milestones: int
    #: artifacts the plan demands, in order
    artifacts: list[str] = field(default_factory=list)
    #: (earlier, later) where the later artifact's own body references the earlier one
    body_edges: list[tuple[str, str]] = field(default_factory=list)
    #: (earlier, later) where the source *passes* the earlier artifact into a call of
    #: the later one — the strongest form, and the one a name list cannot express
    arg_edges: list[tuple[str, str]] = field(default_factory=list)
    #: rendered composed calls found in the source, e.g. `count_words(sample)`
    composed_calls_in_source: list[str] = field(default_factory=list)
    #: checks in the plan that name a relationship rather than a thing
    expressing_checks: list[str] = field(default_factory=list)
    #: how much of the source's code could not be read — 0 means the edges below are a
    #: measurement, not an artefact of a failed parse
    unparsable_blocks: int = 0

    @property
    def edges(self) -> set[tuple[str, str]]:
        return set(self.body_edges) | set(self.arg_edges)


def project_composition(
    key: str, label: str, milestones: list, blocks: list[str], unparsable: int = 0
) -> CompositionFinding:
    """Compare what the plan asks for with what the source's code actually does.

    Order matters: a dependency only counts as composition for a guided project when
    the *later* milestone consumes the *earlier* one, because that is the sequence the
    learner walks. A reference in the other direction is still a real relationship —
    it is reported, but not as a chain.
    """
    artifacts: list[str] = []
    for milestone in milestones:
        check = milestone.checks[0] if milestone.checks else None
        if check and check.kind in {"import", "symbol", "function_call"} and check.target:
            artifacts.append(check.target)
    position = {name: i for i, name in enumerate(artifacts)}
    bodies = definition_bodies(blocks)

    body_edges: list[tuple[str, str]] = []
    for name, body in bodies.items():
        if name not in position:
            continue
        used = referenced_names(body) - local_bindings(body) - {name}
        for other in sorted(used & set(position)):
            if position[other] < position[name]:
                body_edges.append((other, name))

    arg_edges: list[tuple[str, str]] = []
    composed: list[str] = []
    for callee, args in all_call_sites(blocks):
        if callee not in position:
            continue
        for arg in args:
            if arg in position and position[arg] < position[callee]:
                arg_edges.append((arg, callee))
                composed.append(f"{callee}({arg})")

    expressing = [
        f"{check.kind}:{check.target}"
        for milestone in milestones
        for check in milestone.checks or []
        if re.search(r"\w+\s*\(\s*\w", check.target or "")
    ]
    return CompositionFinding(
        project_key=key, label=label, milestones=len(milestones), artifacts=artifacts,
        body_edges=sorted(set(body_edges)), arg_edges=sorted(set(arg_edges)),
        composed_calls_in_source=sorted(set(composed)), expressing_checks=expressing,
        unparsable_blocks=unparsable,
    )
