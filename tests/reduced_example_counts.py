"""Hypothesis example-count policy of the Dataskydd group (Requirement 23.8 to 23.14).

Every property-based test under ``tests/test_dataskydd/`` uses at least
``DEFAULT_FLOOR`` examples. A test may use fewer only when it is listed in
``REDUCED_COUNT_ALLOWLIST`` with a minimum count (never below ``ABSOLUTE_FLOOR``),
its measured seconds per example and a reason, and when the test module documents
the same measurement in a ``MEASURED...`` constant or comment next to ``@settings``.

The guard test (``tests/test_meta/test_mandatory_groups_guard.py``) enforces the
rules and ``scripts/run_mandatory_tests.py`` prints the list after a run.

Reduction threshold (decided by the user, measured by task 16.3): a count is
reduced only when 100 examples would take more than ``REDUCTION_THRESHOLD_S``
seconds for one test function.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_FLOOR = 100
ABSOLUTE_FLOOR = 20
REDUCTION_THRESHOLD_S = 60.0
PROFILE_NAME = "sbk"


@dataclass(frozen=True)
class ReducedCount:
    min_examples: int  # ABSOLUTE_FLOOR <= min_examples < DEFAULT_FLOOR
    measured_s_per_example: float
    reason: str  # expensive integration, filesystem fault injection or full GEDCOM import


# Test id ("module::function") -> reviewed reduced count. Filled in by task 16.3.
REDUCED_COUNT_ALLOWLIST: dict[str, ReducedCount] = {
    # Measured 2026-11-16: 204.8 s for 28 parametrised cases x 100 examples
    # (0.073 s per example and case, 2.05 s per example across the function).
    # 25 examples take about 51 s.
    "tests/test_dataskydd/test_reimport.py::test_dp_property_16_repeated_import_is_stable": ReducedCount(
        25,
        0.073,
        "full GEDCOM import twice per example (plus save and reopen), "
        "28 parametrised cases; 100 examples take about 205 s",
    ),
}


# ---------------------------------------------------------------------------
# Hypothesis profile and override checks (shared by the guard and the runner)
# ---------------------------------------------------------------------------


def _call_name(node: ast.Call) -> str:
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def conftest_profile_problems(source: str, rel: str, *, root_conftest: bool) -> list[str]:
    """Problems with Hypothesis profiles registered or loaded in one conftest.py.

    Only the root ``tests/conftest.py`` may register and load the profile ``sbk`` and
    it must set ``max_examples`` to at least ``DEFAULT_FLOOR`` as a literal.
    """
    problems: list[str] = []
    registered = loaded = False
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if name == "register_profile":
            first = node.args[0] if node.args else None
            profile = first.value if isinstance(first, ast.Constant) else None
            if not root_conftest or profile != PROFILE_NAME:
                problems.append(f"{rel}: register_profile({profile!r}) är inte tillåten (rad {node.lineno})")
                continue
            registered = True
            count = None
            for kw in node.keywords:
                if kw.arg == "max_examples":
                    count = kw.value.value if isinstance(kw.value, ast.Constant) else "?"
                if kw.arg == "derandomize":
                    problems.append(f"{rel}: profilen {PROFILE_NAME} sätter derandomize (rad {node.lineno})")
            if count is not None and (not isinstance(count, int) or count < DEFAULT_FLOOR):
                problems.append(
                    f"{rel}: profilen {PROFILE_NAME} har max_examples={count!r}, minst {DEFAULT_FLOOR} krävs"
                )
        elif name == "load_profile":
            first = node.args[0] if node.args else None
            profile = first.value if isinstance(first, ast.Constant) else None
            if not root_conftest or profile != PROFILE_NAME:
                problems.append(f"{rel}: load_profile({profile!r}) är inte tillåten (rad {node.lineno})")
            else:
                loaded = True
    if root_conftest and not (registered and loaded):
        problems.append(f"{rel}: profilen {PROFILE_NAME} registreras eller laddas inte")
    return problems


def profile_max_examples(source: str) -> int:
    """The literal ``max_examples`` of the registered ``sbk`` profile (Hypothesis default 100)."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and _call_name(node) == "register_profile":
            for kw in node.keywords:
                if kw.arg == "max_examples" and isinstance(kw.value, ast.Constant):
                    return int(kw.value.value)
    return DEFAULT_FLOOR


def hypothesis_override_problems(
    argv: list[str], env: dict[str, str], root: Path
) -> list[str]:
    """Hypothesis overrides that could lower ``max_examples`` (Requirement 23.12).

    Looks at the command line, ``HYPOTHESIS_*`` and ``PYTEST_ADDOPTS`` in the
    environment, ``addopts`` in the pytest configuration files and every conftest.py.
    """
    problems: list[str] = []
    for arg in argv:
        if arg.startswith("--hypothesis"):
            problems.append(f"kommandoraden innehåller {arg}")
    for key, value in env.items():
        upper = key.upper()
        if upper == "HYPOTHESIS_PROFILE":
            problems.append(f"miljövariabeln {key}={value} är satt")
        elif upper.startswith("HYPOTHESIS_") and upper != "HYPOTHESIS_STORAGE_DIRECTORY":
            problems.append(f"miljövariabeln {key} är satt")
        elif upper in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS") and "hypothesis" in value.lower():
            problems.append(f"miljövariabeln {key} nämner hypothesis: {value}")
    for name in ("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini"):
        path = root / name
        if path.exists() and re.search(
            r"--hypothesis[-\w]*|hypothesis[-_]profile", path.read_text(encoding="utf-8-sig")
        ):
            problems.append(f"{name} nämner en Hypothesis-profil eller ett --hypothesis-alternativ")
    skip = {"venv", ".venv", ".git", ".hypothesis", "node_modules", "__pycache__", "build", "dist"}
    import os

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.endswith(".egg-info")]
        if "conftest.py" in filenames:
            path = Path(dirpath) / "conftest.py"
            rel = path.relative_to(root).as_posix()
            problems += conftest_profile_problems(
                path.read_text(encoding="utf-8-sig"), rel, root_conftest=rel == "tests/conftest.py"
            )
    return problems
