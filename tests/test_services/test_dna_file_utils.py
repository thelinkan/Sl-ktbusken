"""Unit tests for dna_file_utils module.

Tests the DNA subfolder file management utilities using tmp_path for isolation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slaktbusken.services.dna_file_utils import (
    delete_dna_file,
    ensure_dna_folder_exists,
    get_dna_folder,
    read_dna_file,
    write_dna_file,
)


@pytest.fixture
def project_path(tmp_path: Path) -> Path:
    """Create a fake project file path for testing."""
    return tmp_path / "myproject.json.gz"


class TestGetDnaFolder:
    """Tests for get_dna_folder."""

    def test_returns_dna_subfolder_relative_to_project_parent(
        self, project_path: Path
    ) -> None:
        """The dna folder is a sibling of the project file."""
        result = get_dna_folder(project_path)
        assert result == project_path.parent / "dna"

    def test_path_does_not_need_to_exist(self, project_path: Path) -> None:
        """get_dna_folder returns a path even if it doesn't exist on disk."""
        result = get_dna_folder(project_path)
        assert not result.exists()


class TestEnsureDnaFolderExists:
    """Tests for ensure_dna_folder_exists."""

    def test_creates_directory_when_missing(self, project_path: Path) -> None:
        """The dna/ folder is created if it doesn't exist."""
        dna_folder = ensure_dna_folder_exists(project_path)
        assert dna_folder.exists()
        assert dna_folder.is_dir()

    def test_returns_dna_folder_path(self, project_path: Path) -> None:
        """Returns the path to the dna/ folder."""
        dna_folder = ensure_dna_folder_exists(project_path)
        assert dna_folder == project_path.parent / "dna"

    def test_idempotent_when_folder_exists(self, project_path: Path) -> None:
        """Calling twice doesn't raise or change behavior."""
        ensure_dna_folder_exists(project_path)
        dna_folder = ensure_dna_folder_exists(project_path)
        assert dna_folder.exists()


class TestWriteDnaFile:
    """Tests for write_dna_file."""

    def test_creates_file_with_correct_json_content(
        self, project_path: Path
    ) -> None:
        """Written file contains the expected JSON data."""
        data = {"rsid": "rs12345", "chromosome": "1", "position": 100}
        write_dna_file(project_path, "test_data.json", data)

        file_path = project_path.parent / "dna" / "test_data.json"
        assert file_path.exists()

        content = json.loads(file_path.read_text(encoding="utf-8"))
        assert content == data

    def test_creates_dna_folder_if_missing(self, project_path: Path) -> None:
        """The dna/ folder is created automatically."""
        write_dna_file(project_path, "auto.json", [1, 2, 3])
        assert (project_path.parent / "dna").is_dir()

    def test_preserves_unicode_characters(self, project_path: Path) -> None:
        """Swedish and other unicode chars are preserved."""
        data = {"name": "Björk Ångström", "note": "Hälsning"}
        write_dna_file(project_path, "unicode.json", data)

        content = json.loads(
            (project_path.parent / "dna" / "unicode.json").read_text(
                encoding="utf-8"
            )
        )
        assert content == data


class TestReadDnaFile:
    """Tests for read_dna_file."""

    def test_reads_back_written_data(self, project_path: Path) -> None:
        """Round-trip: write then read returns same data."""
        data = {"segments": [{"chr": "1", "start": 100, "end": 200}]}
        write_dna_file(project_path, "segments.json", data)

        result = read_dna_file(project_path, "segments.json")
        assert result == data

    def test_raises_file_not_found_for_missing_file(
        self, project_path: Path
    ) -> None:
        """FileNotFoundError when file doesn't exist."""
        ensure_dna_folder_exists(project_path)
        with pytest.raises(FileNotFoundError):
            read_dna_file(project_path, "nonexistent.json")

    def test_raises_json_decode_error_for_invalid_json(
        self, project_path: Path
    ) -> None:
        """json.JSONDecodeError when file has invalid JSON."""
        dna_folder = ensure_dna_folder_exists(project_path)
        bad_file = dna_folder / "bad.json"
        bad_file.write_text("not valid json {{{", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            read_dna_file(project_path, "bad.json")


class TestDeleteDnaFile:
    """Tests for delete_dna_file."""

    def test_removes_existing_file(self, project_path: Path) -> None:
        """Deletes the file from the dna/ folder."""
        write_dna_file(project_path, "to_delete.json", {"temp": True})
        file_path = project_path.parent / "dna" / "to_delete.json"
        assert file_path.exists()

        delete_dna_file(project_path, "to_delete.json")
        assert not file_path.exists()

    def test_handles_missing_file_gracefully(self, project_path: Path) -> None:
        """No exception raised when deleting a file that doesn't exist."""
        ensure_dna_folder_exists(project_path)
        # Should not raise
        delete_dna_file(project_path, "already_gone.json")
