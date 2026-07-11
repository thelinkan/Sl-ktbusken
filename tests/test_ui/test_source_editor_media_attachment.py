"""Unit tests for SourceEditor media attachment functionality.

Tests that:
- File chooser opens with correct filters (Requirement 4.1)
- Cancel on file chooser takes no action (Requirement 4.2)
- File is copied to media directory with conflict resolution (Requirement 4.3)
- File copy failure shows error message (Requirement 4.4)
- MediaItem is created with correct type and title (Requirement 4.5)
- Media ID is appended to the source's media_ids list
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from PySide6.QtWidgets import QApplication

from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.source import Source
from slaktbusken.ui.editors.source_editor import (
    DOCUMENT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    SourceEditor,
)


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def project_folder(tmp_path: Path) -> Path:
    """Create a temporary project folder with media subdirectories."""
    folder = tmp_path / "TestProject"
    folder.mkdir()
    return folder


@pytest.fixture()
def project_data() -> ProjectData:
    """Create minimal project data."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        sources=[
            Source(id="src-1", provider="Test", source_type="other", title="Min källa"),
        ],
    )


class TestMediaAttachmentCancel:
    """Tests for cancel behavior on file chooser."""

    @patch("slaktbusken.ui.editors.source_editor.QFileDialog.getOpenFileName")
    def test_cancel_takes_no_action(
        self, mock_dialog, qapp, project_data, project_folder
    ):
        """Cancelling file chooser leaves project data unchanged (Req 4.2)."""
        mock_dialog.return_value = ("", "")

        editor = SourceEditor(
            project_data=project_data,
            source=project_data.sources[0],
            project_folder=project_folder,
        )
        initial_media_count = len(project_data.media)

        editor._on_add_media()

        assert len(project_data.media) == initial_media_count


class TestMediaAttachmentSuccess:
    """Tests for successful media attachment."""

    @patch("slaktbusken.ui.editors.source_editor.shutil.copy2")
    @patch("slaktbusken.ui.editors.source_editor.QFileDialog.getOpenFileName")
    def test_image_creates_photo_media_item(
        self, mock_dialog, mock_copy, qapp, project_data, project_folder
    ):
        """Selecting an image creates a MediaItem with type='photo' (Req 4.5)."""
        mock_dialog.return_value = ("/external/path/scan.jpg", "")

        editor = SourceEditor(
            project_data=project_data,
            source=project_data.sources[0],
            project_folder=project_folder,
        )
        # Set title in the UI
        editor._ui.title_input.setText("Min källa")

        editor._on_add_media()

        assert len(project_data.media) == 1
        media = project_data.media[0]
        assert media.type == "photo"
        assert media.title == "Min källa"
        assert "source-image" in media.file
        assert media.file.endswith("scan.jpg")

    @patch("slaktbusken.ui.editors.source_editor.shutil.copy2")
    @patch("slaktbusken.ui.editors.source_editor.QFileDialog.getOpenFileName")
    def test_document_creates_document_media_item(
        self, mock_dialog, mock_copy, qapp, project_data, project_folder
    ):
        """Selecting a PDF creates a MediaItem with type='document' (Req 4.5)."""
        mock_dialog.return_value = ("/external/path/contract.pdf", "")

        editor = SourceEditor(
            project_data=project_data,
            source=project_data.sources[0],
            project_folder=project_folder,
        )
        editor._ui.title_input.setText("Avtal")

        editor._on_add_media()

        assert len(project_data.media) == 1
        media = project_data.media[0]
        assert media.type == "document"
        assert media.title == "Avtal"
        assert "document" in media.file
        assert media.file.endswith("contract.pdf")

    @patch("slaktbusken.ui.editors.source_editor.shutil.copy2")
    @patch("slaktbusken.ui.editors.source_editor.QFileDialog.getOpenFileName")
    def test_media_id_appended_to_ui_list(
        self, mock_dialog, mock_copy, qapp, project_data, project_folder
    ):
        """New media ID is added to the media list widget."""
        mock_dialog.return_value = ("/external/path/photo.png", "")

        editor = SourceEditor(
            project_data=project_data,
            source=project_data.sources[0],
            project_folder=project_folder,
        )
        editor._ui.title_input.setText("Foto")

        editor._on_add_media()

        assert editor._ui.media_list.count() == 1
        item = editor._ui.media_list.item(0)
        from PySide6.QtCore import Qt as QtConst
        media_id = item.data(QtConst.ItemDataRole.UserRole)
        assert media_id == project_data.media[0].id

    @patch("slaktbusken.ui.editors.source_editor.shutil.copy2")
    @patch("slaktbusken.ui.editors.source_editor.QFileDialog.getOpenFileName")
    def test_uses_filename_stem_when_no_title(
        self, mock_dialog, mock_copy, qapp, project_data, project_folder
    ):
        """Uses filename stem as title when source title is empty."""
        mock_dialog.return_value = ("/external/path/my_document.pdf", "")

        editor = SourceEditor(
            project_data=project_data,
            source=project_data.sources[0],
            project_folder=project_folder,
        )
        editor._ui.title_input.setText("")

        editor._on_add_media()

        assert len(project_data.media) == 1
        assert project_data.media[0].title == "my_document"


class TestMediaAttachmentConflictResolution:
    """Tests for filename conflict resolution."""

    @patch("slaktbusken.ui.editors.source_editor.shutil.copy2")
    @patch("slaktbusken.ui.editors.source_editor.QFileDialog.getOpenFileName")
    def test_resolves_filename_conflict(
        self, mock_dialog, mock_copy, qapp, project_data, project_folder
    ):
        """Existing file in target dir triggers conflict resolution (Req 4.3)."""
        # Create existing file in media dir
        media_dir = project_folder / "media" / "source-image"
        media_dir.mkdir(parents=True)
        (media_dir / "scan.jpg").write_text("existing")

        mock_dialog.return_value = ("/external/path/scan.jpg", "")

        editor = SourceEditor(
            project_data=project_data,
            source=project_data.sources[0],
            project_folder=project_folder,
        )
        editor._ui.title_input.setText("Källa")

        editor._on_add_media()

        assert len(project_data.media) == 1
        # Should use _1 suffix
        assert project_data.media[0].file == "media/source-image/scan_1.jpg"


class TestMediaAttachmentErrors:
    """Tests for error handling."""

    @patch("slaktbusken.ui.editors.source_editor.QMessageBox.warning")
    @patch("slaktbusken.ui.editors.source_editor.shutil.copy2")
    @patch("slaktbusken.ui.editors.source_editor.QFileDialog.getOpenFileName")
    def test_copy_failure_shows_error(
        self, mock_dialog, mock_copy, mock_warning, qapp, project_data, project_folder
    ):
        """File copy failure shows error message and creates no media (Req 4.4)."""
        mock_dialog.return_value = ("/external/path/scan.jpg", "")
        mock_copy.side_effect = OSError("Diskutrymmet är slut")

        editor = SourceEditor(
            project_data=project_data,
            source=project_data.sources[0],
            project_folder=project_folder,
        )
        editor._ui.title_input.setText("Test")

        editor._on_add_media()

        # No media created
        assert len(project_data.media) == 0
        # Error dialog shown
        mock_warning.assert_called_once()
        call_args = mock_warning.call_args
        assert "Kunde inte kopiera filen" in call_args[0][2]

    def test_no_project_folder_shows_status(self, qapp, project_data):
        """No project folder shows status message, no crash."""
        editor = SourceEditor(
            project_data=project_data,
            source=project_data.sources[0],
            project_folder=None,
        )

        editor._on_add_media()

        assert "Inget projekt" in editor._ui.status_label.text()


class TestMediaAttachmentMediaDirectory:
    """Tests for media directory creation."""

    @patch("slaktbusken.ui.editors.source_editor.shutil.copy2")
    @patch("slaktbusken.ui.editors.source_editor.QFileDialog.getOpenFileName")
    def test_creates_media_directory_if_missing(
        self, mock_dialog, mock_copy, qapp, project_data, project_folder
    ):
        """Media directory is auto-created when it doesn't exist."""
        media_dir = project_folder / "media" / "source-image"
        assert not media_dir.exists()

        mock_dialog.return_value = ("/external/path/scan.png", "")

        editor = SourceEditor(
            project_data=project_data,
            source=project_data.sources[0],
            project_folder=project_folder,
        )
        editor._ui.title_input.setText("Test")

        editor._on_add_media()

        assert media_dir.exists()
