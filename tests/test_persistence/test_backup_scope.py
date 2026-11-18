"""Tests for the migration backup scope (Req 7.8, 7.9, 7.10)."""

from __future__ import annotations

import ast
import gzip
import json
from pathlib import Path

from slaktbusken.persistence.migration import MigrationManager

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "slaktbusken"
MIGRATION_MODULE = PACKAGE_ROOT / "persistence" / "migration.py"
COMMIT_DIR = PACKAGE_ROOT / "services" / "commit"


def _is_commit_module(path: Path) -> bool:
    """True for modules of the Merge_Transaction (services/commit/)."""
    return COMMIT_DIR in path.parents


def _make_project(tmp_path: Path, with_persons: bool) -> Path:
    project = tmp_path / "project.json.gz"
    with gzip.open(project, "wt", encoding="utf-8") as fh:
        json.dump({"version": "0.3"}, fh)
    if with_persons:
        translation = tmp_path / "translation"
        translation.mkdir()
        (translation / "persons.json").write_text('{"a": 1}', encoding="utf-8")
    return project


def test_backup_copies_persons_json_when_present(tmp_path: Path) -> None:
    project = _make_project(tmp_path, with_persons=True)

    backup = MigrationManager.create_backup(project, "0.3")

    assert backup == tmp_path / "project_v0.3.json.gz"
    assert backup.read_bytes() == project.read_bytes()
    persons_backup = tmp_path / "translation" / "persons_v0.3.json"
    assert persons_backup.read_text(encoding="utf-8") == '{"a": 1}'
    # The original is untouched.
    assert (tmp_path / "translation" / "persons.json").exists()


def test_backup_without_persons_json_completes(tmp_path: Path) -> None:
    project = _make_project(tmp_path, with_persons=False)

    backup = MigrationManager.create_backup(project, "0.3")

    assert backup == tmp_path / "project_v0.3.json.gz"
    assert backup.exists()
    assert not (tmp_path / "translation").exists()


def test_backup_with_translation_dir_but_no_persons_json(tmp_path: Path) -> None:
    project = _make_project(tmp_path, with_persons=False)
    (tmp_path / "translation").mkdir()

    backup = MigrationManager.create_backup(project, "0.2")

    assert backup == tmp_path / "project_v0.2.json.gz"
    assert list((tmp_path / "translation").iterdir()) == []


def test_backup_naming_and_location_unchanged(tmp_path: Path) -> None:
    project = tmp_path / "family.json"
    project.write_text("{}", encoding="utf-8")

    backup = MigrationManager.create_backup(project, "0.1")

    assert backup.parent == project.parent
    assert backup.name == "family_v0.1.json"


def _py_files() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def _references(tree: ast.AST, name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name:
            return True
        if isinstance(node, ast.Attribute) and node.attr == name:
            return True
        if isinstance(node, ast.alias) and node.name.split(".")[-1] == name:
            return True
    return False


def test_backup_project_files_referenced_only_by_permitted_callers() -> None:
    offenders = []
    for path in _py_files():
        if path == MIGRATION_MODULE or _is_commit_module(path):
            continue
        if _references(_parse(path), "backup_project_files"):
            offenders.append(path.relative_to(PACKAGE_ROOT).as_posix())
    assert offenders == []

    # Inside migration.py only the definition and MigrationManager.create_backup
    # may use it.
    tree = _parse(MIGRATION_MODULE)
    users = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "backup_project_files":
                continue
            if any(
                isinstance(n, ast.Name) and n.id == "backup_project_files"
                for n in ast.walk(node)
            ):
                users.append(node.name)
    assert users == ["create_backup"]


def test_no_other_backup_api_added() -> None:
    found = []
    for path in _py_files():
        if _is_commit_module(path):
            continue  # Merge_Transaction Recovery_Point (services/commit/)
        for node in ast.walk(_parse(path)):
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ) and "backup" in node.name.lower():
                found.append((path.relative_to(PACKAGE_ROOT).as_posix(), node.name))
    assert sorted(found) == [
        ("persistence/migration.py", "backup_project_files"),
        ("persistence/migration.py", "create_backup"),
    ]
