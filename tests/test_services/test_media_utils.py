"""Unit tests for media_utils module.

Tests the resolve_filename_conflict function with specific examples.
"""

from __future__ import annotations

from slaktbusken.services.media_utils import resolve_filename_conflict


class TestResolveFilenameConflict:
    """Unit tests for resolve_filename_conflict."""

    def test_no_conflict_returns_unchanged(self) -> None:
        """When target_name is not in existing_names, return it unchanged."""
        result = resolve_filename_conflict("photo.jpg", set())
        assert result == "photo.jpg"

    def test_no_conflict_with_other_files(self) -> None:
        """When other files exist but not the target, return unchanged."""
        result = resolve_filename_conflict("photo.jpg", {"other.jpg", "image.png"})
        assert result == "photo.jpg"

    def test_single_conflict_appends_1(self) -> None:
        """When target exists, append _1 before extension."""
        result = resolve_filename_conflict("photo.jpg", {"photo.jpg"})
        assert result == "photo_1.jpg"

    def test_multiple_conflicts_finds_next_available(self) -> None:
        """When _1 is also taken, use _2."""
        result = resolve_filename_conflict(
            "photo.jpg", {"photo.jpg", "photo_1.jpg"}
        )
        assert result == "photo_2.jpg"

    def test_gap_in_sequence_fills_gap(self) -> None:
        """When _1 is taken but _2 is not (even if _3 exists), use _2."""
        result = resolve_filename_conflict(
            "photo.jpg", {"photo.jpg", "photo_1.jpg", "photo_3.jpg"}
        )
        assert result == "photo_2.jpg"

    def test_no_extension_appends_suffix(self) -> None:
        """When file has no extension, append _n directly."""
        result = resolve_filename_conflict("file", {"file"})
        assert result == "file_1"

    def test_no_extension_multiple_conflicts(self) -> None:
        """When file has no extension and _1 is taken, use _2."""
        result = resolve_filename_conflict("file", {"file", "file_1"})
        assert result == "file_2"

    def test_double_extension_preserves_full_extension(self) -> None:
        """os.path.splitext splits on last dot, so .tar.gz → stem=file.tar, ext=.gz."""
        result = resolve_filename_conflict("archive.tar.gz", {"archive.tar.gz"})
        assert result == "archive.tar_1.gz"

    def test_dotfile_no_extension(self) -> None:
        """A dotfile like .gitignore has no extension per os.path.splitext."""
        result = resolve_filename_conflict(".gitignore", {".gitignore"})
        assert result == ".gitignore_1"

    def test_preserves_original_extension(self) -> None:
        """Extension is preserved exactly as given."""
        result = resolve_filename_conflict("scan.TIFF", {"scan.TIFF"})
        assert result == "scan_1.TIFF"

    def test_empty_existing_names_returns_unchanged(self) -> None:
        """Empty set means no conflicts possible."""
        result = resolve_filename_conflict("anything.png", set())
        assert result == "anything.png"
