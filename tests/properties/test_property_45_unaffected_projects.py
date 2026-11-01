"""Property 45: Projects without merge data are unaffected.

A project without merge candidates and history serialises exactly as the frozen
0.3 serialiser would, except for the top-level ``version`` and
``format_version`` values. The comparison goes through
``assert_equal_except_version_fields`` only.

**Validates: Requirements 7.14, 32.1**
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from hypothesis import given, settings

from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence import file_io
from slaktbusken.persistence.file_io import FilePersistence
from slaktbusken.persistence.migration import MigrationManager
from slaktbusken.persistence.serialization import deserialize, serialize
from slaktbusken.services.project_service import ProjectService
from tests.conftest import project_data_strategy
from tests.helpers.compat import assert_equal_except_version_fields
from tests.helpers.frozen_serialiser_v0_3 import serialize_v0_3


def _compare_with_frozen(data: ProjectData) -> str:
    """Serialise with production code and compare with the frozen 0.3 output."""
    after = serialize(data)
    old = dataclasses.replace(data, version="0.3")
    before = serialize_v0_3(old)
    assert_equal_except_version_fields(before, after)
    return after


@settings(settings.get_profile("sbk"))
@given(project_data_strategy())
def test_property_45_generated_projects_match_frozen_0_3(data: ProjectData) -> None:
    assert not data.merge_candidates and not data.merge_history
    after = _compare_with_frozen(data)

    doc = json.loads(after)
    assert "merge_candidates" not in doc
    assert "merge_history" not in doc
    assert "id_high_water_marks" not in doc
    assert data.id_high_water_marks == {}

    # Save/reload keeps the output identical.
    assert serialize(deserialize(after)) == after


def test_empty_project_matches_frozen_0_3() -> None:
    data = ProjectData(project=ProjectMetadata(title="Tom"))
    _compare_with_frozen(data)


def test_created_project_matches_frozen_0_3_after_save_and_load(tmp_path: Path) -> None:
    created = ProjectService().create_project("Nytt", tmp_path)
    path = tmp_path / "Nytt" / "Nytt.json.gz"
    raw = path.read_bytes()
    loaded = FilePersistence.load(path)
    assert loaded.version == "0.4"
    assert not loaded.merge_candidates and not loaded.merge_history
    assert loaded.id_high_water_marks == {}
    before = serialize_v0_3(dataclasses.replace(created, version="0.3"))
    assert_equal_except_version_fields(before, raw)


def test_four_version_constants_are_equal(tmp_path: Path) -> None:
    created = ProjectService().create_project("Version", tmp_path)
    values = {
        file_io.CURRENT_VERSION,
        MigrationManager.CURRENT_VERSION,
        ProjectData().version,
        created.version,
    }
    assert values == {"0.4"}


def test_migration_path_from_0_1_to_0_4() -> None:
    version = "0.1"
    seen = []
    while version != MigrationManager.CURRENT_VERSION:
        assert version in MigrationManager._migrations
        version, _ = MigrationManager._migrations[version]
        seen.append(version)
    assert seen[-1] == "0.4"

    migrated = MigrationManager.migrate(
        {"format": "släktbuske-file", "version": "0.1", "format_version": "0.1"}, "0.1"
    )
    assert migrated["version"] == migrated["format_version"] == "0.4"
