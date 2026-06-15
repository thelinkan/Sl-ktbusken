"""Property tests for migration correctness and unit tests for version handling.

Property 15: For any valid ProjectData at version N, migrating to version N+1
then deserializing produces valid ProjectData with no data loss; backup file
is created with correct version suffix.

Also tests version handling edge cases:
- File with current version loads without migration
- File with older version triggers migration chain
- File with newer version raises UnsupportedVersionError with Swedish message

**Validates: Requirements 25.2, 27.1, 27.2, 27.3, 27.4, 27.5, 27.6, 27.7**
"""

from __future__ import annotations

import gzip
import json
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings

from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.file_io import (
    CURRENT_VERSION,
    FilePersistence,
    UnsupportedVersionError,
)
from slaktbusken.persistence.migration import MigrationError, MigrationManager
from slaktbusken.persistence.serialization import serialize
from tests.conftest import project_data_strategy


@pytest.fixture(autouse=True)
def _clean_migrations():
    """Remove any test-registered migrations after each test."""
    original = dict(MigrationManager._migrations)
    yield
    MigrationManager._migrations = original


def _register_test_migration_0_0_to_0_1():
    """Register a test migration from version 0.0 to 0.1."""

    @MigrationManager.register("0.0", "0.1")
    def _migrate(data: dict) -> dict:
        data["version"] = "0.1"
        data["format_version"] = "0.1"
        return data


def _save_raw_json_gz(data_dict: dict, path: Path) -> None:
    """Save a raw dict as gzipped JSON (bypassing FilePersistence)."""
    json_bytes = json.dumps(data_dict, ensure_ascii=False).encode("utf-8")
    with open(path, "wb") as f:
        f.write(gzip.compress(json_bytes))


# ---------------------------------------------------------------------------
# Task 5.6: Property test for migration correctness (Property 15)
# ---------------------------------------------------------------------------


class TestPropertyMigrationCorrectness:
    """Property 15: Migration produces valid ProjectData with backup."""

    @given(data=project_data_strategy())
    @settings(max_examples=30)
    def test_migration_preserves_data_and_creates_backup(
        self, data: ProjectData
    ) -> None:
        """Migrating from 0.0→0.1 produces equal data and creates backup file.

        **Validates: Requirements 25.2, 27.5, 27.6**
        """
        _register_test_migration_0_0_to_0_1()

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "test_project.json.gz"

            # Serialize the data normally, then patch version to "0.0"
            json_str = serialize(data)
            raw_dict = json.loads(json_str)
            raw_dict["version"] = "0.0"
            raw_dict["format_version"] = "0.0"
            _save_raw_json_gz(raw_dict, file_path)

            # Load should trigger migration from 0.0 → 0.1
            result = FilePersistence.load(file_path)

            # Verify data integrity: version should now be current
            assert result.version == CURRENT_VERSION

            # All entity collections should be preserved
            assert result.format == data.format
            assert result.project == data.project
            assert result.persons == data.persons
            assert result.families == data.families
            assert result.events == data.events
            assert result.places == data.places
            assert result.sources == data.sources
            assert result.media == data.media
            assert result.repositories == data.repositories
            assert result.dna_companies == data.dna_companies
            assert result.dna_profiles == data.dna_profiles
            assert result.dna_matches == data.dna_matches
            assert result.dna_segments == data.dna_segments
            assert result.dna_clusters == data.dna_clusters
            assert result.dna_triangulations == data.dna_triangulations
            assert result.research_notes == data.research_notes

            # Verify backup file was created with version suffix
            backup_path = Path(tmp_dir) / "test_project_v0.0.json.gz"
            assert backup_path.exists(), f"Expected backup at {backup_path}"


# ---------------------------------------------------------------------------
# Task 5.7: Unit tests for version handling edge cases
# ---------------------------------------------------------------------------


class TestVersionHandlingEdgeCases:
    """Unit tests for version handling: current, older, newer versions."""

    def test_current_version_loads_without_migration(self) -> None:
        """A file with the current version loads directly without migration.

        **Validates: Requirements 27.1, 27.2**
        """
        data = ProjectData(version=CURRENT_VERSION)

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "current.json.gz"
            FilePersistence.save(data, file_path)

            # Should load without issues (no migration triggered)
            result = FilePersistence.load(file_path)
            assert result.version == CURRENT_VERSION
            assert result == data

    def test_older_version_triggers_migration_chain(self) -> None:
        """A file with an older version triggers the migration chain.

        **Validates: Requirements 27.5, 27.6**
        """
        _register_test_migration_0_0_to_0_1()

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "old.json.gz"

            # Create a file at version 0.0
            raw_dict = {
                "format": "släktbuske-file",
                "version": "0.0",
                "format_version": "0.0",
                "project": {"title": "Old Project"},
            }
            _save_raw_json_gz(raw_dict, file_path)

            # Loading should succeed via migration
            result = FilePersistence.load(file_path)
            assert result.version == CURRENT_VERSION
            assert result.project.title == "Old Project"

            # Backup should exist with correct version suffix
            backup_path = Path(tmp_dir) / "old_v0.0.json.gz"
            assert backup_path.exists()

    def test_newer_version_raises_unsupported_version_error(self) -> None:
        """A file with a newer version raises UnsupportedVersionError with Swedish message.

        **Validates: Requirements 27.3, 27.4**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "future.json.gz"

            # Create a file at a future version
            raw_dict = {
                "format": "släktbuske-file",
                "version": "9.9",
                "format_version": "9.9",
                "project": {"title": "Future Project"},
            }
            _save_raw_json_gz(raw_dict, file_path)

            with pytest.raises(UnsupportedVersionError) as exc_info:
                FilePersistence.load(file_path)

            # Verify Swedish error message content
            msg = str(exc_info.value)
            assert "nyare version" in msg
            assert "9.9" in msg
            assert "Uppdatera" in msg

    def test_needs_migration_for_older_version(self) -> None:
        """MigrationManager.needs_migration returns True for older versions."""
        assert MigrationManager.needs_migration("0.0") is True

    def test_needs_migration_false_for_current_version(self) -> None:
        """MigrationManager.needs_migration returns False for current version."""
        assert MigrationManager.needs_migration(CURRENT_VERSION) is False

    def test_is_too_new_for_newer_version(self) -> None:
        """MigrationManager.is_too_new returns True for versions > current."""
        assert MigrationManager.is_too_new("1.0") is True
        assert MigrationManager.is_too_new("9.9") is True

    def test_is_too_new_false_for_current_or_older(self) -> None:
        """MigrationManager.is_too_new returns False for current or older."""
        assert MigrationManager.is_too_new(CURRENT_VERSION) is False
        assert MigrationManager.is_too_new("0.0") is False

    def test_migration_error_when_no_path_exists(self) -> None:
        """MigrationManager.migrate raises MigrationError when no path exists."""
        with pytest.raises(MigrationError):
            MigrationManager.migrate({"version": "0.0"}, "0.0")

    def test_create_backup_correct_suffix(self) -> None:
        """create_backup creates a file with the correct version suffix.

        **Validates: Requirements 27.6**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "project.json.gz"
            file_path.write_bytes(b"dummy content")

            backup = MigrationManager.create_backup(file_path, "0.0")
            expected = Path(tmp_dir) / "project_v0.0.json.gz"
            assert backup == expected
            assert backup.exists()
            assert backup.read_bytes() == b"dummy content"
