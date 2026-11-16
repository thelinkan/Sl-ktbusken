"""Migration of format 0.4 to 0.5.

**Validates: Requirements 21.1 to 21.6, 22.1**
"""

from __future__ import annotations

import copy
import gzip
import json
import shutil
from pathlib import Path

import pytest
from hypothesis import given, settings

from slaktbusken.persistence.file_io import FilePersistence, UnsupportedVersionError
from slaktbusken.persistence.migration import MigrationManager
from slaktbusken.persistence.serialization import deserialize, serialize
from tests.helpers.compat import assert_equal_except_version_fields
from tests.test_dataskydd.strategies import documents_0_4

pytestmark = pytest.mark.mandatory_integrity

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "project_v0_4.json.gz"
_VERSION_KEYS = {"version", "format_version"}


def _fixture_dict() -> dict:
    return json.loads(gzip.decompress(FIXTURE.read_bytes()).decode("utf-8"))


def _copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "projekt.json.gz"
    shutil.copy2(FIXTURE, target)
    return target


# Feature: data-integrity-0-3-0, Property 21: Migration to 0.5 is additive
# and idempotent
@settings(settings.get_profile("sbk"))
@given(documents_0_4())
def test_dp_property_21_migration_additive_and_idempotent(doc) -> None:
    """**Validates: Requirements 21.2, 21.3, 21.4**"""
    original = copy.deepcopy(doc)
    once = MigrationManager.migrate(copy.deepcopy(doc), "0.4")
    assert once["version"] == once["format_version"] == "0.5"
    assert {k: v for k, v in once.items() if k not in _VERSION_KEYS} == {
        k: v for k, v in original.items() if k not in _VERSION_KEYS
    }
    _, step = MigrationManager._migrations["0.4"]
    assert step(copy.deepcopy(once)) == once


def test_migration_0_4_to_0_5_only_changes_version() -> None:
    original = _fixture_dict()
    migrated = MigrationManager.migrate(copy.deepcopy(original), "0.4")
    assert migrated["version"] == migrated["format_version"] == "0.5"
    assert {k: v for k, v in migrated.items() if k not in _VERSION_KEYS} == {
        k: v for k, v in original.items() if k not in _VERSION_KEYS
    }


def test_migration_creates_backup(tmp_path: Path) -> None:
    path = _copy_fixture(tmp_path)
    FilePersistence.load(path)
    backup = tmp_path / "projekt_v0.4.json.gz"
    assert backup.is_file()
    assert backup.read_bytes() == FIXTURE.read_bytes()


def test_migration_is_idempotent(tmp_path: Path) -> None:
    path = _copy_fixture(tmp_path)
    first = FilePersistence.load(path)
    FilePersistence.save(first, path)
    reloaded = FilePersistence.load(path)
    # The saved file is already 0.5: no second backup and the same content.
    assert not (tmp_path / "projekt_v0.5.json.gz").exists()
    assert serialize(reloaded) == serialize(first)
    assert reloaded.version == "0.5"


def test_v0_4_fixture_opens_and_round_trips(tmp_path: Path) -> None:
    path = _copy_fixture(tmp_path)
    data = FilePersistence.load(path)
    assert data.version == "0.5"
    assert len(data.events) == 6 and len(data.residences) == 6
    FilePersistence.save(data, path)
    assert_equal_except_version_fields(
        FIXTURE.read_bytes(), path.read_bytes(),
        old_versions=("0.4",), new_version="0.5",
    )


def test_v0_4_residences_round_trip_without_origins(tmp_path: Path) -> None:
    data = FilePersistence.load(_copy_fixture(tmp_path))
    assert all(r.origins == [] for r in data.residences)
    assert all(e.origin is None and e.source_refs == [] for e in data.events)
    raw = json.loads(serialize(data))
    assert all("origins" not in r for r in raw["residences"])
    assert [r["id"] for r in raw["residences"]] == [
        r["id"] for r in _fixture_dict()["residences"]
    ]


def test_newer_version_refused(tmp_path: Path) -> None:
    doc = _fixture_dict()
    doc["version"] = doc["format_version"] = "0.6"
    path = tmp_path / "ny.json.gz"
    path.write_bytes(gzip.compress(json.dumps(doc).encode("utf-8")))
    before = path.read_bytes()
    with pytest.raises(UnsupportedVersionError):
        FilePersistence.load(path)
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_old_precision_approximate_not_rewritten_on_open(tmp_path: Path) -> None:
    data = FilePersistence.load(_copy_fixture(tmp_path))
    event = next(e for e in data.events if e.id == "event_1")
    assert event.date.precision == "approximate"
    assert event.date.qualifier == "exact"
    raw = json.loads(serialize(data))
    raw_date = next(e for e in raw["events"] if e["id"] == "event_1")["date"]
    assert raw_date["precision"] == "approximate"
    assert "qualifier" not in raw_date
    assert deserialize(json.dumps(raw)).events == data.events
