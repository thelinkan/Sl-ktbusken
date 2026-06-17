"""Property tests for gzip persistence round-trip (Property 2).

**Validates: Requirements 27.1, 27.2, 27.3, 27.4, 27.5, 27.6, 27.7**
"""

from __future__ import annotations

import gzip
import tempfile
from pathlib import Path

from hypothesis import given, settings

from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.file_io import FilePersistence
from slaktbusken.persistence.serialization import serialize
from tests.conftest import project_data_strategy


class TestPropertyGzipRoundTrip:
    """Property 2: write to .json.gz then read back produces equal data."""

    @given(data=project_data_strategy())
    @settings(max_examples=50)
    def test_save_then_load_produces_equal_data(self, data: ProjectData) -> None:
        """For any valid ProjectData, saving to .json.gz and loading back produces equal data."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "test_project.json.gz"
            FilePersistence.save(data, file_path)
            result = FilePersistence.load(file_path)
            assert result == data

    @given(data=project_data_strategy())
    @settings(max_examples=50)
    def test_intermediate_json_bytes_are_identical(self, data: ProjectData) -> None:
        """The intermediate JSON bytes in the .json.gz are identical to serialize() output."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "test_project.json.gz"
            FilePersistence.save(data, file_path)

            # Read and decompress to get the stored JSON bytes
            with open(file_path, "rb") as f:
                stored_json_bytes = gzip.decompress(f.read())

            # Compare with direct serialization
            expected_json_bytes = serialize(data).encode("utf-8")
            assert stored_json_bytes == expected_json_bytes


import json

import pytest

from slaktbusken.persistence.file_io import (
    CorruptedFileError,
    CURRENT_VERSION,
    UnsupportedVersionError,
)


class TestCorruptedFileHandling:
    """Unit tests for error handling when loading corrupted project files.

    **Validates: Requirements 3.4**
    """

    def test_invalid_gzip_header_raises_corrupted_file_error(
        self, tmp_path: Path
    ) -> None:
        """A file with invalid gzip data raises CorruptedFileError."""
        bad_file = tmp_path / "bad.json.gz"
        bad_file.write_bytes(b"this is not gzip data at all")

        with pytest.raises(CorruptedFileError, match="ogiltigt gzip-format"):
            FilePersistence.load(bad_file)

    def test_invalid_json_raises_corrupted_file_error(self, tmp_path: Path) -> None:
        """A valid gzip file with non-JSON content raises CorruptedFileError."""
        bad_file = tmp_path / "bad_json.json.gz"
        bad_file.write_bytes(gzip.compress(b"not valid json {{{"))

        with pytest.raises(CorruptedFileError, match="ogiltig JSON"):
            FilePersistence.load(bad_file)

    def test_missing_required_sections_raises_corrupted_file_error(
        self, tmp_path: Path
    ) -> None:
        """A valid gzip JSON file missing required sections raises CorruptedFileError."""
        incomplete_data = {"format_version": CURRENT_VERSION, "some_key": "some_value"}
        json_bytes = json.dumps(incomplete_data).encode("utf-8")
        bad_file = tmp_path / "incomplete.json.gz"
        bad_file.write_bytes(gzip.compress(json_bytes))

        with pytest.raises(CorruptedFileError, match="saknar obligatoriska avsnitt"):
            FilePersistence.load(bad_file)

    def test_unsupported_version_raises_unsupported_version_error(
        self, tmp_path: Path
    ) -> None:
        """A file with a newer version than CURRENT_VERSION raises UnsupportedVersionError."""
        # Create a version that is guaranteed to be newer.
        major, minor = CURRENT_VERSION.split(".")
        newer_version = f"{int(major) + 1}.0"
        future_data = {
            "format_version": newer_version,
            "format": {},
            "version": newer_version,
            "project": {},
        }
        json_bytes = json.dumps(future_data).encode("utf-8")
        future_file = tmp_path / "future.json.gz"
        future_file.write_bytes(gzip.compress(json_bytes))

        with pytest.raises(UnsupportedVersionError):
            FilePersistence.load(future_file)

    def test_file_not_found_raises_file_not_found_error(self, tmp_path: Path) -> None:
        """Loading a non-existent file raises FileNotFoundError."""
        missing_file = tmp_path / "does_not_exist.json.gz"

        with pytest.raises(FileNotFoundError):
            FilePersistence.load(missing_file)
