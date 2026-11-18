"""Presence check for the round-trip fixtures. Fails (never skips)."""

from __future__ import annotations

import pytest

from slaktbusken.model.project import ProjectData
from tests.test_gedcom_roundtrip import fixtures

pytestmark = pytest.mark.mandatory_integrity


def test_all_fixture_files_present():
    missing = fixtures.missing_fixtures()
    if missing:
        pytest.fail(
            "Fixture files missing: " + ", ".join(str(p) for p in missing),
            pytrace=False,
        )


def test_mergetest_loads_into_project_data():
    project = fixtures.load_mergetest()
    assert isinstance(project, ProjectData)
    assert project.persons


def test_exporttest_paths_exist():
    assert fixtures.exporttest_ged_path().is_file()
    assert fixtures.exporttest_json_path().is_file()
