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
