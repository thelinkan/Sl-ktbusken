"""Unit tests for the project-data safety guards.

Covers :func:`is_safe_external_url` (URL scheme allow-listing) and
:func:`resolve_within` (path containment), the guards applied to URLs and file
paths that originate from a (possibly shared) project file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from slaktbusken.services.safe_io import (
    is_safe_external_url,
    is_safe_media_extension,
    resolve_within,
)


class TestIsSafeMediaExtension:
    """Only inert media types may open via the OS handler without a prompt."""

    @pytest.mark.parametrize(
        "name",
        [
            "photo.jpg",
            "scan.JPEG",  # case-insensitive
            "doc.pdf",
            "letter.docx",
            "notes.txt",
            "clip.mp4",
            "song.mp3",
            "media/photos/portrait.png",  # extension read from a path
            "C:/archive/record.PDF",
        ],
    )
    def test_allows_known_media_types(self, name: str) -> None:
        assert is_safe_media_extension(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "setup.exe",
            "run.bat",
            "script.cmd",
            "macro.js",
            "page.html",
            "page.htm",
            "shortcut.lnk",
            "lib.dll",
            "archive.zip",
            "installer.msi",
            "payload.ps1",
            "app",  # no extension
        ],
    )
    def test_rejects_executable_and_unknown_types(self, name: str) -> None:
        assert is_safe_media_extension(name) is False

    @pytest.mark.parametrize("name", [None, "", "   "])
    def test_rejects_empty_or_missing(self, name) -> None:
        assert is_safe_media_extension(name) is False


class TestIsSafeExternalUrl:
    """Only web/mail schemes may be handed to the OS default handler."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/record/1",
            "https://riksarkivet.se/bild/42",
            "HTTPS://EXAMPLE.COM",  # scheme comparison is case-insensitive
            "mailto:archivist@example.com",
            "  https://example.com/leading-space  ",  # trimmed before parsing
        ],
    )
    def test_allows_web_and_mail_schemes(self, url: str) -> None:
        assert is_safe_external_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "file:///C:/Windows/System32/calc.exe",
            "file://etc/passwd",
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "ftp://example.com/x",
            "vbscript:msgbox(1)",
            "custom-protocol://do-something",
            # Scheme-less values the OS may interpret as a local path/command.
            "C:\\Windows\\System32\\calc.exe",
            "//server/share/file",
            "example.com/no-scheme",
        ],
    )
    def test_rejects_non_web_schemes(self, url: str) -> None:
        assert is_safe_external_url(url) is False

    @pytest.mark.parametrize("url", [None, "", "   ", "\t\n"])
    def test_rejects_empty_or_missing(self, url) -> None:
        assert is_safe_external_url(url) is False


class TestResolveWithin:
    """A project-referenced path must stay inside the project root."""

    def test_returns_resolved_path_for_contained_relative_file(
        self, tmp_path: Path
    ) -> None:
        resolved = resolve_within(tmp_path, "media/photos/photo.jpg")
        assert resolved == (tmp_path / "media" / "photos" / "photo.jpg").resolve()

    def test_allows_nested_subfolders(self, tmp_path: Path) -> None:
        resolved = resolve_within(tmp_path, "a/b/c/d.pdf")
        assert resolved is not None
        assert tmp_path.resolve() in resolved.parents

    def test_rejects_parent_traversal(self, tmp_path: Path) -> None:
        assert resolve_within(tmp_path, "../../secret.txt") is None

    def test_rejects_traversal_that_climbs_then_descends(
        self, tmp_path: Path
    ) -> None:
        # Escapes the root even though it re-descends into a sibling.
        assert resolve_within(tmp_path, "../sibling/x.txt") is None

    def test_rejects_absolute_path_outside_root(self, tmp_path: Path) -> None:
        # An absolute candidate keeps its own root and is not contained.
        outside = Path("C:/Windows/System32/calc.exe")
        assert resolve_within(tmp_path, str(outside)) is None

    def test_rejects_empty_candidate(self, tmp_path: Path) -> None:
        assert resolve_within(tmp_path, "") is None
        assert resolve_within(tmp_path, "   ") is None

    def test_containment_is_existence_independent(self, tmp_path: Path) -> None:
        # A contained path is returned even when the file does not exist yet.
        resolved = resolve_within(tmp_path, "not/created/yet.txt")
        assert resolved is not None
        assert not resolved.exists()

    def test_prefix_sibling_is_not_contained(self, tmp_path: Path) -> None:
        # ``root`` is ".../proj"; a sibling ".../proj-evil" shares a name prefix
        # but must not count as contained.
        root = tmp_path / "proj"
        root.mkdir()
        (tmp_path / "proj-evil").mkdir()
        assert resolve_within(root, "../proj-evil/x.txt") is None
