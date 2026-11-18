"""Registration of the Dataskydd mandatory group (Requirement 23)."""

from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.mandatory_integrity

ROOT = pathlib.Path(__file__).resolve().parents[2]
_FORBIDDEN_MARKS = {"skip", "skipif", "xfail"}


def _test_names(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def _has_forbidden_mark(path: pathlib.Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_MARKS:
            return True
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_MARKS:
            return True
    return False


def test_dataskydd_group_registered_and_complete() -> None:
    from fnmatch import fnmatchcase

    from tests.mandatory_groups import MANDATORY_GROUPS

    groups = [g for g in MANDATORY_GROUPS if g.key == "data_protection"]
    assert len(groups) == 1
    group = groups[0]
    assert group.title_sv == "Dataskydd"

    package = ROOT / "tests" / "test_dataskydd"
    package_modules = {
        f"tests/test_dataskydd/{p.name}" for p in package.glob("test_*.py")
    }
    assert package_modules <= set(group.modules)

    for entry in group.required_tests:
        module, name = entry.split("::")
        path = ROOT / module
        assert path.exists(), entry
        names = _test_names(path)
        assert any(fnmatchcase(n, name) for n in names), entry

    required = {e.split("::")[1] for e in group.required_tests}
    assert "test_dataskydd_group_registered_and_complete" in required
    for number in range(1, 29):
        assert f"test_dp_property_{number}_*" in required, number

    for path in sorted(package.glob("*.py")):
        assert not _has_forbidden_mark(path), path.name
