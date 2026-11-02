"""Convention and scope-limit tests for the person comparison and merge feature.

Covers the Qt-free service rule (Requirement 34.5, 34.6) with a subprocess
import test that blocks ``PySide6``, and static scope limits (Requirement 33.2,
33.8, 33.9): no scoring, proposing or automatic assessment functions.

**Validates: Requirements 33.2, 33.8, 33.9, 34.5, 34.6**
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "slaktbusken"
SERVICES = PACKAGE / "services"

# New service modules and commit modules of this feature.
NEW_SERVICE_MODULES = (
    "candidate_index",
    "candidate_register",
    "comparison_session",
    "id_registry",
    "merge_candidate_redirect",
    "merge_candidate_service",
    "merge_engine",
    "merge_planner",
    "merge_planner_candidates",
    "merge_planner_families",
    "merge_planner_person",
    "merge_planner_refs",
    "merge_rules",
    "person_reference_index",
    "redirect_resolution",
)
COMMIT_MODULES = ("fs_ops", "journal", "preflight", "recovery", "transaction")

QT_FREE_MODULES = (
    "slaktbusken.model.merge_candidate",
    *(f"slaktbusken.services.{name}" for name in NEW_SERVICE_MODULES),
    "slaktbusken.services.commit",
    *(f"slaktbusken.services.commit.{name}" for name in COMMIT_MODULES),
)

_BLOCKER = textwrap.dedent(
    """
    import importlib.abc, importlib, sys

    class _Block(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in ("PySide6", "shiboken6"):
                raise ImportError("blocked: " + name)
            return None

    sys.meta_path.insert(0, _Block())
    # The planner step modules register themselves from merge_planner, which
    # must therefore be the entry point (importing a step module first hits a
    # known circular import unrelated to Qt).
    importlib.import_module("slaktbusken.services.merge_planner")
    importlib.import_module(sys.argv[1])
    assert not [m for m in sys.modules if m.split(".")[0] in ("PySide6", "shiboken6")]
    """
)


@pytest.mark.parametrize("module", QT_FREE_MODULES)
def test_module_imports_without_pyside6(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _BLOCKER, module],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"{module} needs PySide6:\n{result.stderr}"


def _module_paths() -> list[Path]:
    paths = [PACKAGE / "model" / "merge_candidate.py"]
    paths += [SERVICES / f"{name}.py" for name in NEW_SERVICE_MODULES]
    paths += [SERVICES / "commit" / f"{name}.py" for name in COMMIT_MODULES]
    paths.append(SERVICES / "commit" / "__init__.py")
    return paths


def test_module_files_exist() -> None:
    missing = [str(p) for p in _module_paths() if not p.is_file()]
    assert missing == []


def test_no_qt_imports_in_source() -> None:
    offenders: list[str] = []
    for path in _module_paths():
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(n.split(".")[0] in ("PySide6", "PyQt5", "PyQt6", "shiboken6") for n in names):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []


# ---------------------------------------------------------------------------
# Scope limits: no scoring, proposing or automatic assessment functions
# ---------------------------------------------------------------------------

_FORBIDDEN_NAME = re.compile(
    r"score|scoring|propos|suggest|recommend|rank|likelihood|probab|confidence"
    r"|percent|auto_?assess|auto_?merge|auto_?set|bulk|batch_merge|merge_all"
    r"|find_duplicate|detect_duplicate|guess|llm|generate_text",
    re.IGNORECASE,
)

# Event similarity inside one person merge pairs events of the two persons
# chosen by the user. It does not rate whether two persons are the same.
_ALLOWED_NAMES = {"is_similar_event_pair", "find_similar_event_pairs"}


def _defined_names(path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.append((node.name, node.lineno))
    return found


def test_no_scoring_proposing_or_auto_assessment_names() -> None:
    offenders = [
        f"{path.name}:{line} {name}"
        for path in _module_paths()
        for name, line in _defined_names(path)
        if name not in _ALLOWED_NAMES and _FORBIDDEN_NAME.search(name)
    ]
    assert offenders == []


def test_forbidden_name_detection_works() -> None:
    for bad in ("similarity_score", "propose_merge", "auto_assess", "rank_candidates", "merge_all"):
        assert _FORBIDDEN_NAME.search(bad), bad
    for good in ("set_assessment", "build_plan", "candidate_for_pair", "plan_candidates"):
        assert not _FORBIDDEN_NAME.search(good), good


def test_assessment_is_set_only_by_explicit_service_call() -> None:
    """Requirement 33.9: ``assessment`` is only written in the candidate service,
    the redirect planner (user-triggered merge) and the model constructors."""
    allowed = {
        PACKAGE / "model" / "merge_candidate.py",
        SERVICES / "merge_candidate_service.py",
        SERVICES / "merge_candidate_redirect.py",
        SERVICES / "merge_planner_candidates.py",
        SERVICES / "merge_engine.py",
        SERVICES / "merge_planner.py",
    }
    offenders: list[str] = []
    for path in PACKAGE.rglob("*.py"):
        if path in allowed or "ui" in path.relative_to(PACKAGE).parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and target.attr == "assessment":
                        offenders.append(f"{path.relative_to(PACKAGE)}:{node.lineno}")
    assert offenders == []


def test_services_start_no_timers_or_background_work() -> None:
    """Requirement 33.1: no automatic start from services (timers, threads)."""
    pattern = re.compile(r"QTimer|threading|Thread\(|sched|asyncio")
    offenders = [
        path.name
        for path in _module_paths()
        if pattern.search(path.read_text(encoding="utf-8-sig"))
    ]
    assert offenders == []
