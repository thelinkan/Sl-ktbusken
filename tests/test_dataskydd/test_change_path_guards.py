"""Static guards for the change paths (Requirements 18.4 to 18.6).

* The dirty guard reports ``X._dirty = ...`` outside ``ProjectService``
  where ``X`` is not the name ``self``.
* The collection mutation guard reports raw mutations of a ``ProjectData``
  collection in the UI layer, the app, the GEDCOM importer and the services
  unless the ``(module, function)`` pair is in ``change_path_allowlist.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.test_dataskydd.change_path_allowlist import CHANGE_PATH_ALLOWLIST

pytestmark = pytest.mark.mandatory_integrity

_PACKAGE = Path(__file__).resolve().parents[2] / "slaktbusken"

# Scopes of the guards (posix paths relative to slaktbusken/).
_DIRTY_SCOPE = ("app.py", "ui/", "services/")
#
# The services are the mutation implementations (ProjectService, delete,
# research, merge, translation services) and are reviewed through the
# change-path registry in test_change_paths.py. The guard covers the callers
# (app and UI), the GEDCOM importer and the one service that rebinds a
# ProjectData collection while a project is loaded.
_MUTATION_SCOPE = (
    "app.py",
    "ui/",
    "gedcom/importer.py",
    "services/place_dedupe.py",
)
_MUTATION_EXCLUDED: tuple[str, ...] = ()

PROJECT_DATA_COLLECTIONS = frozenset(
    {
        "persons",
        "families",
        "events",
        "residences",
        "places",
        "sources",
        "media",
        "repositories",
        "dna_companies",
        "dna_profiles",
        "dna_matches",
        "dna_segments",
        "dna_clusters",
        "dna_triangulations",
        "research_notes",
        "leverantorer",
        "kalltyper",
        "research_cases",
        "research_hypotheses",
        "research_actions",
        "merge_candidates",
        "merge_history",
    }
)

_MUTATING_METHODS = frozenset(
    {"append", "extend", "insert", "remove", "pop", "clear"}
)


def _python_files(scope: tuple[str, ...]) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for path in sorted(_PACKAGE.rglob("*.py")):
        rel = path.relative_to(_PACKAGE).as_posix()
        if rel.startswith(scope):
            files.append((rel, path))
    return files


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


# ----------------------------------------------------------------------
# Dirty guard
# ----------------------------------------------------------------------


def find_external_dirty_assignments(tree: ast.AST) -> list[int]:
    """Line numbers of ``X._dirty = ...`` where ``X`` is not the name ``self``."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        else:
            continue
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr == "_dirty"
                and not (
                    isinstance(target.value, ast.Name) and target.value.id == "self"
                )
            ):
                lines.append(node.lineno)
    return lines


def _external_dirty_violations(
    files: list[tuple[str, Path]],
) -> list[str]:
    violations: list[str] = []
    for rel, path in files:
        for line in find_external_dirty_assignments(_parse(path)):
            violations.append(f"{rel}:{line}")
    return violations


def test_guard_no_external_dirty_assignment() -> None:
    """The guard itself detects ``x._dirty = ...`` and passes ``self._dirty``."""
    bad = ast.parse("project_service._dirty = True\nself.svc._dirty = True\n")
    good = ast.parse("self._dirty = True\nclass A:\n    def f(self):\n        self._dirty = False\n")
    assert find_external_dirty_assignments(bad) == [1, 2]
    assert find_external_dirty_assignments(good) == []


def test_no_external_dirty_assignment() -> None:
    violations = _external_dirty_violations(_python_files(_DIRTY_SCOPE))
    assert violations == [], (
        "Direct '_dirty' assignment on another object; use "
        f"ProjectService.mark_changed: {violations}"
    )


# ----------------------------------------------------------------------
# Collection mutation guard
# ----------------------------------------------------------------------


def _collection_name(node: ast.AST) -> str | None:
    """The collection name if *node* is an attribute chain ending in one."""
    if isinstance(node, ast.Attribute) and node.attr in PROJECT_DATA_COLLECTIONS:
        return node.attr
    return None


class _MutationVisitor(ast.NodeVisitor):
    """Collects ``(function, line, description)`` of raw collection mutations."""

    def __init__(self) -> None:
        self._stack: list[str] = []
        self.found: list[tuple[str, int, str]] = []

    def _function(self) -> str:
        return self._stack[-1] if self._stack else "<module>"

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _MUTATING_METHODS:
            name = _collection_name(func.value)
            if name is not None:
                self.found.append(
                    (self._function(), node.lineno, f".{name}.{func.attr}()")
                )
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            if isinstance(target, ast.Subscript):
                name = _collection_name(target.value)
                if name is not None:
                    self.found.append((self._function(), node.lineno, f"del .{name}[...]"))
        self.generic_visit(node)

    def _check_target(self, target: ast.AST, line: int) -> None:
        if isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Slice):
            name = _collection_name(target.value)
            if name is not None:
                self.found.append((self._function(), line, f".{name}[a:b] = ..."))
        elif isinstance(target, ast.Attribute):
            name = _collection_name(target)
            if name is not None:
                self.found.append((self._function(), line, f".{name} = ..."))
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._check_target(element, line)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._check_target(target, node.lineno)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._check_target(node.target, node.lineno)
        self.generic_visit(node)


def find_collection_mutations(tree: ast.AST) -> list[tuple[str, int, str]]:
    visitor = _MutationVisitor()
    visitor.visit(tree)
    return visitor.found


def _allowed_pairs() -> set[tuple[str, str]]:
    return {(module, function) for module, function, _reason in CHANGE_PATH_ALLOWLIST}


def _unlisted_mutations() -> list[str]:
    allowed = _allowed_pairs()
    files = [
        (rel, path)
        for rel, path in _python_files(_MUTATION_SCOPE)
        if rel not in _MUTATION_EXCLUDED
    ]
    violations: list[str] = []
    for rel, path in files:
        for function, line, description in find_collection_mutations(_parse(path)):
            if (rel, function) not in allowed:
                violations.append(f"{rel}:{line} in {function}: {description}")
    return violations


def test_guard_no_unlisted_collection_mutation() -> None:
    violations = _unlisted_mutations()
    assert violations == [], (
        "Raw ProjectData collection mutation outside the allow-list. Route it "
        "through ProjectService or add a reviewed entry to "
        "change_path_allowlist.py:\n" + "\n".join(violations)
    )


def test_collection_guard_detects_each_mutation_form() -> None:
    source = (
        "def f(d, x):\n"
        "    d.places.append(x)\n"
        "    d.persons.extend([x])\n"
        "    d.events.insert(0, x)\n"
        "    d.families.remove(x)\n"
        "    d.sources.pop()\n"
        "    d.media.clear()\n"
        "    del d.places[0]\n"
        "    d.places[0:1] = []\n"
        "    d.events = []\n"
        "    local = [].append(1)\n"
    )
    kinds = [item[2] for item in find_collection_mutations(ast.parse(source))]
    assert len(kinds) == 9


def test_allowlist_entries_have_reasons_and_existing_modules() -> None:
    seen: set[tuple[str, str]] = set()
    for module, function, reason in CHANGE_PATH_ALLOWLIST:
        assert reason.strip(), f"Allow-list entry {module}::{function} has no reason"
        assert (_PACKAGE / module).is_file(), f"{module} does not exist"
        assert (module, function) not in seen, f"duplicate {module}::{function}"
        seen.add((module, function))


def test_allowlist_has_no_stale_entries() -> None:
    """Every allow-listed pair still contains a mutation (keeps the list honest)."""
    live: set[tuple[str, str]] = set()
    for rel, path in _python_files(_MUTATION_SCOPE):
        for function, _line, _desc in find_collection_mutations(_parse(path)):
            live.add((rel, function))
    stale = sorted(_allowed_pairs() - live)
    assert stale == [], f"Stale allow-list entries: {stale}"
