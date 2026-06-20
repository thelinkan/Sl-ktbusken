"""Unit tests for DNA company logo file copy logic.

Tests the _copy_to_logo_folder function which handles copying external
image files into the project's logo folder with conflict resolution.

Covers Requirements 3.1, 3.2, 3.3, 3.4, 3.7.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from slaktbusken.ui.editors.dna_editor import _copy_to_logo_folder


class TestCopyToLogoFolderSuccess:
    """Tests for successful file copy operations."""

    def test_copy_file_to_existing_folder(self, tmp_path: Path) -> None:
        """A file is copied successfully when the logo folder already exists.

        Validates: Requirement 3.1
        """
        # Arrange
        source = tmp_path / "external" / "company.png"
        source.parent.mkdir()
        source.write_bytes(b"fake png data")

        logo_folder = tmp_path / "media" / "logo"
        logo_folder.mkdir(parents=True)

        # Act
        result = _copy_to_logo_folder(source, logo_folder)

        # Assert
        assert result is not None
        assert result == logo_folder / "company.png"
        assert result.exists()
        assert result.read_bytes() == b"fake png data"

    def test_original_filename_preserved(self, tmp_path: Path) -> None:
        """The copied file retains the original filename.

        Validates: Requirement 3.3
        """
        source = tmp_path / "downloads" / "MyDNA_Logo.jpg"
        source.parent.mkdir()
        source.write_bytes(b"jpeg content")

        logo_folder = tmp_path / "media" / "logo"
        logo_folder.mkdir(parents=True)

        result = _copy_to_logo_folder(source, logo_folder)

        assert result is not None
        assert result.name == "MyDNA_Logo.jpg"


class TestCopyCreatesFolder:
    """Tests for automatic logo folder creation."""

    def test_creates_logo_folder_when_missing(self, tmp_path: Path) -> None:
        """The logo folder is created automatically if it does not exist.

        Validates: Requirement 3.2
        """
        source = tmp_path / "external" / "logo.png"
        source.parent.mkdir()
        source.write_bytes(b"image data")

        logo_folder = tmp_path / "media" / "logo"
        assert not logo_folder.exists()

        result = _copy_to_logo_folder(source, logo_folder)

        assert result is not None
        assert logo_folder.exists()
        assert result.exists()
        assert result.read_bytes() == b"image data"

    def test_creates_nested_logo_folder(self, tmp_path: Path) -> None:
        """Multiple levels of missing parent directories are created.

        Validates: Requirement 3.2
        """
        source = tmp_path / "src" / "icon.png"
        source.parent.mkdir()
        source.write_bytes(b"icon bytes")

        logo_folder = tmp_path / "deep" / "nested" / "media" / "logo"
        assert not logo_folder.exists()

        result = _copy_to_logo_folder(source, logo_folder)

        assert result is not None
        assert logo_folder.exists()
        assert result.exists()


class TestUniqueFilenameOnConflict:
    """Tests for unique filename generation when conflicts exist."""

    def test_appends_suffix_when_name_exists(self, tmp_path: Path) -> None:
        """A numeric suffix _1 is appended when same filename already exists.

        Validates: Requirement 3.4
        """
        source = tmp_path / "external" / "logo.png"
        source.parent.mkdir()
        source.write_bytes(b"new content")

        logo_folder = tmp_path / "media" / "logo"
        logo_folder.mkdir(parents=True)
        # Pre-existing file with same name
        (logo_folder / "logo.png").write_bytes(b"existing content")

        result = _copy_to_logo_folder(source, logo_folder)

        assert result is not None
        assert result.name == "logo_1.png"
        assert result.read_bytes() == b"new content"
        # Original file still untouched
        assert (logo_folder / "logo.png").read_bytes() == b"existing content"

    def test_increments_suffix_until_unused(self, tmp_path: Path) -> None:
        """Suffix increments past existing _1, _2, etc. until free name found.

        Validates: Requirement 3.4
        """
        source = tmp_path / "external" / "ancestry.png"
        source.parent.mkdir()
        source.write_bytes(b"new file")

        logo_folder = tmp_path / "media" / "logo"
        logo_folder.mkdir(parents=True)
        # Create conflicts: ancestry.png, ancestry_1.png, ancestry_2.png
        (logo_folder / "ancestry.png").write_bytes(b"v0")
        (logo_folder / "ancestry_1.png").write_bytes(b"v1")
        (logo_folder / "ancestry_2.png").write_bytes(b"v2")

        result = _copy_to_logo_folder(source, logo_folder)

        assert result is not None
        assert result.name == "ancestry_3.png"
        assert result.read_bytes() == b"new file"


class TestCopyErrorHandling:
    """Tests for error handling when file copy fails."""

    def test_returns_none_on_copy_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns None when shutil.copy2 raises OSError.

        Validates: Requirement 3.7
        """
        source = tmp_path / "external" / "logo.png"
        source.parent.mkdir()
        source.write_bytes(b"data")

        logo_folder = tmp_path / "media" / "logo"

        def mock_copy2(src, dst):
            raise OSError("Permission denied")

        monkeypatch.setattr("shutil.copy2", mock_copy2)

        result = _copy_to_logo_folder(source, logo_folder)

        assert result is None

    def test_logs_error_on_copy_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog
    ) -> None:
        """An error message is logged when the copy fails.

        Validates: Requirement 3.7
        """
        source = tmp_path / "external" / "logo.png"
        source.parent.mkdir()
        source.write_bytes(b"data")

        logo_folder = tmp_path / "media" / "logo"

        def mock_copy2(src, dst):
            raise OSError("Disk full")

        monkeypatch.setattr("shutil.copy2", mock_copy2)

        with caplog.at_level(logging.ERROR):
            result = _copy_to_logo_folder(source, logo_folder)

        assert result is None
        assert "Misslyckades kopiera logofil" in caplog.text
        assert "Disk full" in caplog.text

    def test_returns_none_on_folder_creation_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Returns None when the logo folder cannot be created.

        Validates: Requirement 3.7
        """
        source = tmp_path / "external" / "logo.png"
        source.parent.mkdir()
        source.write_bytes(b"data")

        logo_folder = tmp_path / "media" / "logo"

        original_mkdir = Path.mkdir

        def mock_mkdir(self, *args, **kwargs):
            raise OSError("Cannot create directory")

        monkeypatch.setattr(Path, "mkdir", mock_mkdir)

        result = _copy_to_logo_folder(source, logo_folder)

        assert result is None


# ---------------------------------------------------------------------------
# Unit tests for _on_choose_logo orchestration (Task 5.2)
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock, patch
import uuid

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from slaktbusken.model.dna import DnaCompany
from slaktbusken.model.media import MediaItem
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.editors.dna_editor import (
    DnaEditor,
    LOGO_FILE_FILTER,
    _find_media_by_path,
    _create_logo_media_item,
)


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def editor_setup(qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Create a DnaEditor instance with a minimal project for testing.

    Returns a dict with editor, project_data, company, and logo_folder.
    """
    project_file = tmp_path / "project.json.gz"
    project_file.touch()
    logo_folder = tmp_path / "media" / "logo"

    project_data = ProjectData(
        project=ProjectMetadata(title="Test"),
        dna_companies=[DnaCompany(id="company-1", name="AncestryDNA")],
    )

    editor = DnaEditor(
        project_data=project_data,
        project_path=project_file,
    )

    # Set the editing company so that _on_choose_logo doesn't bail
    editor._editing_company = project_data.dna_companies[0]

    return {
        "editor": editor,
        "project_data": project_data,
        "company": project_data.dna_companies[0],
        "logo_folder": logo_folder,
        "tmp_path": tmp_path,
    }


class TestOnChooseLogoOrchestration:
    """Tests for the _on_choose_logo method orchestration."""

    def test_file_dialog_opens_with_correct_filter_and_directory(
        self, editor_setup, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """QFileDialog is called with LOGO_FILE_FILTER and logo folder as initial dir.

        Validates: Requirements 1.3, 1.4, 1.5
        """
        editor = editor_setup["editor"]
        logo_folder = editor_setup["logo_folder"]

        captured_args = {}

        def mock_get_open_filename(*args, **kwargs):
            captured_args["args"] = args
            return ("", "")

        monkeypatch.setattr(
            QFileDialog, "getOpenFileName", mock_get_open_filename
        )

        editor._on_choose_logo()

        # Verify dialog was called with correct arguments
        call_args = captured_args["args"]
        # args: (parent, title, directory, filter)
        assert call_args[0] is editor
        assert call_args[1] == "Välj logo..."
        assert call_args[2] == str(logo_folder)
        assert call_args[3] == LOGO_FILE_FILTER

    def test_cancel_preserves_state(
        self, editor_setup, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When dialog returns empty string, company state remains unchanged.

        Validates: Requirement 4.5
        """
        editor = editor_setup["editor"]
        company = editor_setup["company"]

        # Set initial state
        company.logo_media_id = "original-id"
        editor._ui.company_logo_input.setText("original-id")

        monkeypatch.setattr(
            QFileDialog, "getOpenFileName", lambda *args, **kwargs: ("", "")
        )

        editor._on_choose_logo()

        assert company.logo_media_id == "original-id"
        assert editor._ui.company_logo_input.text() == "original-id"

    def test_selecting_file_in_logo_folder_no_copy(
        self, editor_setup, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Selecting a file already in logo folder creates MediaItem without copy.

        Validates: Requirement 2.1
        """
        editor = editor_setup["editor"]
        company = editor_setup["company"]
        logo_folder = editor_setup["logo_folder"]
        project_data = editor_setup["project_data"]

        # Create a file already in the logo folder
        logo_folder.mkdir(parents=True, exist_ok=True)
        logo_file = logo_folder / "ancestry.png"
        logo_file.write_bytes(b"fake png")

        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            lambda *args, **kwargs: (str(logo_file), ""),
        )

        copy_called = {"called": False}
        original_copy = _copy_to_logo_folder.__wrapped__ if hasattr(_copy_to_logo_folder, "__wrapped__") else None

        monkeypatch.setattr(
            "slaktbusken.ui.editors.dna_editor._copy_to_logo_folder",
            lambda src, dst: (copy_called.update({"called": True}), None)[1],
        )

        editor._on_choose_logo()

        # Copy should NOT have been called
        assert not copy_called["called"]
        # MediaItem should have been created and company updated
        assert company.logo_media_id is not None
        # A media item should exist with the expected relative path
        media_item = _find_media_by_path(
            project_data.media, "media/logo/ancestry.png"
        )
        assert media_item is not None
        assert media_item.type == "logo"
        assert company.logo_media_id == media_item.id

    def test_selecting_external_file_triggers_copy(
        self, editor_setup, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Selecting a file outside logo folder calls _copy_to_logo_folder.

        Validates: Requirement 3.1
        """
        editor = editor_setup["editor"]
        company = editor_setup["company"]
        tmp_path = editor_setup["tmp_path"]
        logo_folder = editor_setup["logo_folder"]
        project_data = editor_setup["project_data"]

        # Create an external file (not in logo folder)
        external_file = tmp_path / "downloads" / "mylogo.png"
        external_file.parent.mkdir(parents=True, exist_ok=True)
        external_file.write_bytes(b"external png")

        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            lambda *args, **kwargs: (str(external_file), ""),
        )

        # Make the logo folder exist so the _is_inside check works correctly
        logo_folder.mkdir(parents=True, exist_ok=True)

        copy_called = {"called": False, "source": None}
        dest_file = logo_folder / "mylogo.png"

        def mock_copy(source, folder):
            copy_called["called"] = True
            copy_called["source"] = source
            # Simulate successful copy
            dest_file.write_bytes(b"external png")
            return dest_file

        monkeypatch.setattr(
            "slaktbusken.ui.editors.dna_editor._copy_to_logo_folder",
            mock_copy,
        )

        editor._on_choose_logo()

        assert copy_called["called"]
        assert copy_called["source"] == external_file
        # Company should have a logo_media_id set
        assert company.logo_media_id is not None

    def test_deduplication_reuses_existing_media_item(
        self, editor_setup, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When _find_media_by_path returns existing item, no new item is created.

        Validates: Requirements 2.3, 4.2
        """
        editor = editor_setup["editor"]
        company = editor_setup["company"]
        logo_folder = editor_setup["logo_folder"]
        project_data = editor_setup["project_data"]

        # Create a file in the logo folder
        logo_folder.mkdir(parents=True, exist_ok=True)
        logo_file = logo_folder / "existing.png"
        logo_file.write_bytes(b"png data")

        # Pre-add a MediaItem for this file
        existing_media = MediaItem(
            id="existing-media-id",
            type="logo",
            file="media/logo/existing.png",
            title="existing",
        )
        project_data.media.append(existing_media)
        media_count_before = len(project_data.media)

        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            lambda *args, **kwargs: (str(logo_file), ""),
        )

        editor._on_choose_logo()

        # No new media item should be added
        assert len(project_data.media) == media_count_before
        # Company should reference the existing item
        assert company.logo_media_id == "existing-media-id"

    def test_overwrite_existing_logo_media_id(
        self, editor_setup, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When company already has logo_media_id, selecting new logo replaces it.

        Validates: Requirement 4.4
        """
        editor = editor_setup["editor"]
        company = editor_setup["company"]
        logo_folder = editor_setup["logo_folder"]

        # Set initial logo
        company.logo_media_id = "old-logo-id"
        editor._ui.company_logo_input.setText("old-logo-id")

        # Create a new file in logo folder
        logo_folder.mkdir(parents=True, exist_ok=True)
        new_logo = logo_folder / "new_logo.png"
        new_logo.write_bytes(b"new png data")

        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            lambda *args, **kwargs: (str(new_logo), ""),
        )

        editor._on_choose_logo()

        # The old ID should be replaced
        assert company.logo_media_id != "old-logo-id"
        assert company.logo_media_id is not None
        assert editor._ui.company_logo_input.text() == company.logo_media_id

    def test_error_on_copy_failure_shows_message_box(
        self, editor_setup, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When _copy_to_logo_folder returns None, QMessageBox.warning is shown.

        Validates: Requirement 3.7
        """
        editor = editor_setup["editor"]
        company = editor_setup["company"]
        tmp_path = editor_setup["tmp_path"]
        logo_folder = editor_setup["logo_folder"]

        # Reset company state
        company.logo_media_id = None
        editor._ui.company_logo_input.setText("")

        # Create an external file
        external_file = tmp_path / "external" / "bad_logo.png"
        external_file.parent.mkdir(parents=True, exist_ok=True)
        external_file.write_bytes(b"data")

        # Ensure logo folder exists for path check
        logo_folder.mkdir(parents=True, exist_ok=True)

        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            lambda *args, **kwargs: (str(external_file), ""),
        )

        # Simulate copy failure
        monkeypatch.setattr(
            "slaktbusken.ui.editors.dna_editor._copy_to_logo_folder",
            lambda src, dst: None,
        )

        warning_called = {"called": False, "title": None, "message": None}

        def mock_warning(parent, title, message):
            warning_called["called"] = True
            warning_called["title"] = title
            warning_called["message"] = message

        monkeypatch.setattr(QMessageBox, "warning", mock_warning)

        editor._on_choose_logo()

        # QMessageBox.warning should have been called
        assert warning_called["called"]
        assert warning_called["title"] == "Fel"
        assert "Kunde inte kopiera filen" in warning_called["message"]
        # Company state should remain unchanged
        assert company.logo_media_id is None
        assert editor._ui.company_logo_input.text() == ""


# ---------------------------------------------------------------------------
# Unit tests for match list logo display (Task 8.4)
# ---------------------------------------------------------------------------

from PySide6.QtGui import QIcon, QImage
from PySide6.QtCore import Qt

from slaktbusken.model.dna import DnaMatch, DnaProfile
from slaktbusken.ui.editors.dna_editor import (
    resolve_company_logo_icon,
    _LOGO_FILE_MISSING,
)


class TestMatchListLogoDisplay:
    """Tests for resolve_company_logo_icon used in the match list."""

    def test_icon_shown_when_logo_exists(self, qapp, tmp_path: Path) -> None:
        """A valid QIcon is returned when the full chain resolves to a file on disk.

        Validates: Requirement 6.1
        """
        # Arrange: build the full chain DnaMatch → DnaProfile → DnaCompany → MediaItem → file
        company = DnaCompany(id="c1", name="AncestryDNA", logo_media_id="media-1")
        profile = DnaProfile(id="p1", person_id="person-1", company_id="c1", test_type="autosomal")
        match = DnaMatch(id="m1", profile1_id="local-profile", profile2_id="p1", shared_cm=50.0)

        # Create the logo file on disk
        logo_dir = tmp_path / "media" / "logo"
        logo_dir.mkdir(parents=True)
        logo_file = logo_dir / "ancestry.png"
        img = QImage(1, 1, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.red)
        img.save(str(logo_file))

        media_item = MediaItem(id="media-1", type="logo", file="media/logo/ancestry.png", title="ancestry")

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=[company],
            dna_profiles=[profile],
            dna_matches=[match],
            media=[media_item],
        )

        # Act
        icon = resolve_company_logo_icon(match, project_data, tmp_path)

        # Assert
        assert not icon.isNull()

    def test_placeholder_when_no_logo_assigned(self, qapp, tmp_path: Path) -> None:
        """An empty/null QIcon is returned when the company has no logo_media_id.

        Validates: Requirement 6.2
        """
        # Arrange: company has no logo_media_id (None)
        company = DnaCompany(id="c1", name="AncestryDNA", logo_media_id=None)
        profile = DnaProfile(id="p1", person_id="person-1", company_id="c1", test_type="autosomal")
        match = DnaMatch(id="m1", profile1_id="local-profile", profile2_id="p1", shared_cm=50.0)

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=[company],
            dna_profiles=[profile],
            dna_matches=[match],
            media=[],
        )

        # Act
        icon = resolve_company_logo_icon(match, project_data, tmp_path)

        # Assert
        assert icon.isNull()

    def test_missing_file_placeholder_when_file_absent(self, qapp, tmp_path: Path) -> None:
        """A non-null 'missing' indicator icon is returned when the file does not exist on disk.

        Validates: Requirement 6.3
        """
        # Arrange: full chain resolves but file does NOT exist on disk
        company = DnaCompany(id="c1", name="AncestryDNA", logo_media_id="media-1")
        profile = DnaProfile(id="p1", person_id="person-1", company_id="c1", test_type="autosomal")
        match = DnaMatch(id="m1", profile1_id="local-profile", profile2_id="p1", shared_cm=50.0)

        # MediaItem points to a file that doesn't exist
        media_item = MediaItem(id="media-1", type="logo", file="media/logo/gone.png", title="gone")

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=[company],
            dna_profiles=[profile],
            dna_matches=[match],
            media=[media_item],
        )

        # Do NOT create the file on disk

        # Act
        icon = resolve_company_logo_icon(match, project_data, tmp_path)

        # Assert: should be a non-null icon (the red-bordered missing indicator)
        assert not icon.isNull()

        # Also verify it's different from the "no logo" case (which is null)
        no_logo_icon = resolve_company_logo_icon(
            DnaMatch(id="m2", profile1_id="x", profile2_id="p1", shared_cm=10.0),
            ProjectData(
                project=ProjectMetadata(title="Test"),
                dna_companies=[DnaCompany(id="c1", name="X", logo_media_id=None)],
                dna_profiles=[profile],
                dna_matches=[],
                media=[],
            ),
            tmp_path,
        )
        assert no_logo_icon.isNull()  # confirms the "no logo" case is null
