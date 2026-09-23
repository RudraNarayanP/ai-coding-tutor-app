"""Turn a repository's import structure into the order a learner should build it in.

The unit of a course here is a *module*, because that is the unit a repository is built
from: `micrograd/engine.py` defines the number that carries its own gradient, and
`trainer.py` cannot exist before it. Walking the import graph gives an ordered list of
files where every file's dependencies are already behind it, and reading each file's
syntax tree gives the names a milestone can honestly demand — so the checks are `symbol`
and `file_exists`, both decided by the existing verifier without executing anything.

Nothing in this module writes prose. A repository has no narration, and inventing one
would be a model guessing at somebody else's intent; the text a learner sees is built
from facts (this file defines X; that file imports it), and `enrich_project` stays the
only place a sentence may be added.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field


@dataclass
class ModuleFacts:
    """What one source file says about itself, read out of its syntax tree."""

    path: str
    module: str
    package: str
    defines: list[tuple[str, str, int]] = field(default_factory=list)  # (kind, name, lines)
    signatures: dict[str, str] = field(default_factory=dict)
    imports: set[str] = field(default_factory=set)      # every imported dotted name
    internal: set[str] = field(default_factory=set)     # ... of these, the repo's own files
    external: set[str] = field(default_factory=set)     # torch, flask, requests, ...
    depends: set[str] = field(default_factory=set)      # module names to build first
    unparsable: bool = False

    @property
    def public_names(self) -> list[str]:
        return [name for _kind, name, _size in self.defines]

    def ranked_defines(self) -> list[tuple[str, str, int]]:
        """Classes first, then the biggest: a file's centrepiece leads its milestone."""
        order = {"class": 0, "def": 1, "variable": 2}
        return sorted(self.defines, key=lambda item: (order.get(item[0], 3), -item[2], item[1]))


def module_of(path: str) -> str:
    parts = (path or "").replace("\\", "/").split("/")
    return ".".join(parts[:-1] + [parts[-1].rsplit(".", 1)[0]]).strip(".")


def package_of(path: str) -> str:
    return module_of(path).rsplit(".", 1)[0]


def _span(node: ast.AST) -> int:
    start = getattr(node, "lineno", 0) or 0
    end = getattr(node, "end_lineno", 0) or start
    return max(1, end - start + 1)


_TEST_NAME = re.compile(r"^(?:test|tests)_\w+$|^\w+_tests?$")


def _header(lines: list[str], node: ast.AST) -> str:
    """The declaration only: `class Value:` or `def backward(self, target=None):`.

    This is the API a learner has to provide, which is a different thing from the body
    that implements it — pasting the body into a milestone would turn a guided project
    into a typing test over somebody else's work, and a permissive license does not
    make it a lesson.
    """
    start = (getattr(node, "lineno", 0) or 1) - 1
    out: list[str] = []
    for text in lines[start:start + 8]:
        out.append(text.strip())
        if text.rstrip().endswith(":"):
            break
    return " ".join(out)[:160]


def _is_test_name(name: str) -> bool:
    return bool(_TEST_NAME.match(name or ""))


def _relative(node: ast.ImportFrom, facts: ModuleFacts) -> list[str]:
    """`from .engine import Value` inside `micrograd/` names `micrograd.engine`."""
    base = facts.package.split(".") if facts.package else []
    base = base[: len(base) - (node.level - 1)]
    names = [".".join([*base, node.module])] if node.module else [".".join(base)]
    names += [".".join([*base, alias.name]) for alias in node.names]
    return [n for n in names if n]


def read_module(path: str, source: str) -> ModuleFacts:
    """Parse one file for its top-level definitions and its imports.

    Unparsable files are flagged and excluded from the course rather than guessed at:
    Python 2 sources, notebooks exported oddly and a truncated download all look like
    this, and a milestone built on a file nothing can read would be unverifiable.
    """
    facts = ModuleFacts(path=path, module=module_of(path), package=package_of(path))
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError, RecursionError):
        facts.unparsable = True
        return facts
    lines = source.splitlines()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            # `_private` is not a deliverable, and a `test_*` function is the harness that
            # marks somebody else's work — the round-6 finding, applied to a file's
            # top level. A module-level constant is not something you implement either,
            # so `logger` and `ROOT` never become a milestone.
            if node.name.startswith("_") or _is_test_name(node.name):
                continue
            kind = "class" if isinstance(node, ast.ClassDef) else "def"
            facts.defines.append((kind, node.name, _span(node)))
            facts.signatures[node.name] = _header(lines, node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue                        # constants are context, never a milestone
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            facts.imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                facts.imports.update(_relative(node, facts))
                continue
            if node.module:
                facts.imports.add(node.module)
                facts.imports.update(f"{node.module}.{alias.name}" for alias in node.names)
    return facts


def resolves(import_name: str, modules: set[str]) -> set[str]:
    """Which of this repository's modules an import names.

    The same file is spelled three ways depending on where the reader stands:
    `from . import engine`, `from micrograd.engine import Value`, and — when the
    snapshot's root sits *inside* the package — `from backend.engine import X`. All
    three mean `micrograd/engine.py`.

    An ambiguous spelling links to nothing. Two `utils.py` in different packages both
    end with `utils`, and guessing between them would order the course wrong on
    purpose; an unresolved edge only costs a tie-break, exactly like a cycle.
    """
    exact = {m for m in modules if m == import_name or import_name.startswith(m + ".")}
    if exact:
        return exact
    relative = {m for m in modules if import_name.endswith("." + m) or m.endswith("." + import_name)}
    return relative if len(relative) == 1 else set()


def analyze(files: list[tuple[str, str]]) -> list[ModuleFacts]:
    """Read every file, then mark which of its imports point inside this repository."""
    facts_list = [read_module(path, source) for path, source in files]
    modules = {f.module for f in facts_list}
    for facts in facts_list:
        if facts.unparsable:
            continue
        for name in sorted(facts.imports):
            hits = {m for m in resolves(name, modules) if m != facts.module}
            if hits:
                facts.internal |= hits
            else:
                facts.external.add(name.split(".")[0])
        facts.depends = set(facts.internal)
    return facts_list


def dependency_order(facts_list: list[ModuleFacts]) -> list[ModuleFacts]:
    """Files in build order — every one after the files it imports. Leaves first.

    A cycle in a real package is not a reason to refuse the repository: flask's `app.py`
    and `ctx.py` import each other, and so do the cores of most frameworks. When nothing
    is ready, the file with the fewest unresolved dependencies goes next, which keeps a
    cyclic package starting at its leaves rather than at whatever sorts first — a course
    that opens with the biggest file in the project is reading the graph backwards.
    """
    by_module = _index(facts_list)
    depths = {f.module: depth(f, by_module) for f in facts_list}
    ordered: list[ModuleFacts] = []
    remaining = dict(by_module)
    done: set[str] = set()
    while remaining:
        ready = sorted((f for f in remaining.values() if f.depends <= done),
                       key=lambda f: (depths[f.module], f.path))
        if not ready:
            ready = [min(remaining.values(),
                         key=lambda f: (len(f.depends - done), depths[f.module], f.path))]
        for facts in ready:
            ordered.append(facts)
            done.add(facts.module)
            remaining.pop(facts.module, None)
    return ordered


def entry_point(ordered: list[ModuleFacts]) -> ModuleFacts | None:
    """The file worth running: the one that leans on the most of the others.

    Last-in-build-order is not good enough — a repository has dozens of independent
    leaves, and the last alphabetical one is arbitrary. Fan-out into the project is the
    honest reading of "the program": `train.py` before `model.py`, `app.py` before
    `json/tag.py`. Depth is the tie-break, and a cycle makes depth unreliable, which is
    exactly when counting what a file needs is the better signal anyway.
    """
    chain = [f for f in ordered if f.depends] or ordered
    return max(chain, key=lambda f: (len(f.depends), f.path == ordered[-1].path, f.path))


def _index(ordered: list[ModuleFacts]) -> dict[str, ModuleFacts]:
    return {f.module: f for f in ordered}


def depth(facts: ModuleFacts, by_module: dict[str, ModuleFacts], seen=None) -> int:
    """How many modules must exist before this one can run. Cycles count as 0 more."""
    seen = seen or set()
    if facts.module in seen:
        return 0
    seen = seen | {facts.module}
    beneath = [by_module[m] for m in facts.depends if m in by_module and m != facts.module]
    return 1 + max((depth(f, by_module, seen) for f in beneath), default=-1)


def _closure(tip: ModuleFacts, by_module: dict[str, ModuleFacts]) -> set[str]:
    """Every module the entry point needs, directly or through another one of them."""
    needed: set[str] = {tip.module}
    frontier = [tip]
    while frontier:
        current = frontier.pop()
        for dep in current.depends:
            module = next((m for m in by_module if m == dep or dep.startswith(m + ".")), None)
            if module and module not in needed:
                needed.add(module)
                frontier.append(by_module[module])
    return needed


def reaches(start: str, target: str, by_module: dict[str, ModuleFacts]) -> bool:
    """Can `start` get back to `target` by following imports?

    A cycle is a property of the whole graph, not of one edge: flask's `config.py` and
    `sansio/app.py` never import each other directly, and both sit in one 17-module cycle.
    Saying "these two files import each other" about a one-way edge is a sentence the
    repository contradicts, so the branch that says it has to ask this question first.
    """
    seen: set[str] = set()
    stack = [start]
    while stack:
        module = stack.pop()
        if module == target:
            return True
        for dep in (by_module[module].depends if module in by_module else ()):
            if dep not in seen:
                seen.add(dep)
                stack.append(dep)
    return False


def build_chain(ordered: list[ModuleFacts], limit: int = 8) -> list[ModuleFacts]:
    """The modules that have to exist for the entry point to run, in build order.

    A repository's first eight files by name are not a course — they are eight unrelated
    leaves. Walking down from the entry point keeps every selected file something the
    learner will actually need, which is what makes "build it from the start to the
    finish" more than a phrase.

    The budget and the graph do not always fit, and this function is where that shows. A
    chain that contains no gaps must contain the entry point's whole dependency closure,
    and a closure only fits if it is small enough: measured across 13 real repositories,
    the largest fitting closure is 1 module for pallets/flask at this limit and 18 at 20,
    because flask's core is one cycle of 17 files and every one of them needs the other 16.
    Choosing the largest fitting closure therefore refuses flask, click, jinja, httpx and
    requests outright and reduces Textualize/rich to two milestones, so the tip is kept and
    the truncation leaves prerequisites behind - 96 unsatisfied imports across the corpus.
    `plan_repository` names every one of them in the milestone that needs it, which is the
    honest form of a scope this budget cannot close. Making the course both full-sized and
    gap-free is a bigger milestone budget or a per-cycle milestone, not a filter here.
    """
    if not ordered:
        return []
    tip = entry_point(ordered)
    by_module = _index(ordered)
    needed = _closure(tip, by_module)
    selected = [f for f in ordered if f.module in needed]
    return selected[:limit] if len(selected) <= limit else selected[:limit - 1] + [tip]


def consumers_of(ordered: list[ModuleFacts], module: str) -> list[str]:
    """Which of the course's *later* files import this one — the reason it comes when it does.

    "Later" is load-bearing. The milestone text built from this tells the learner those
    files "can be built" after this one, and inside a cyclic package a consumer can be
    released before the file it imports: 8 of the 59 milestones that used this list named
    a file the learner had already written. An earlier consumer is not a reason to build
    this now, and the branches below this one say what is actually underneath the file.
    """
    home = next((i for i, f in enumerate(ordered) if f.module == module), len(ordered))
    return [f.path for i, f in enumerate(ordered) if i > home and module in f.depends]
