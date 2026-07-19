"""Unit tests for the media Visa (view) button in SourceEditor.

Validates: Requirements 16.1, 16.2

Tests that:
- The Visa button is disabled when no media item is selected
- The Visa button is enabled when a media item is selected
- Clicking Visa calls QDesktopServices.openUrl with the correct file:// URL
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QApplication

from slaktbusken.model.media import MediaItem
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.source import Source
from slaktbusken.ui.editors.source_editor import SourceEditor


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def media_item() -> MediaItem:
    """Create a test media item."""
    return MediaItem(
        id="media-1",
        type="image",
        file="media/photos/test_image.jpg",
        title="Test Image",
    )


@pytest.fixture()
def project_with_media(media_item: MediaItem) -> ProjectData:
    """Create a ProjectData with a source linked to a media item."""
    return ProjectData(
        project=ProjectMetadata(title="Test Project"),
        sources=[
            Source(
                id="src-1",
                provider="Test Provider",
                source_type="other",
                title="Test Source",
                media_ids=["media-1"],
            ),
        ],
        media=[media_item],
    )


class TestVisaButtonDisabledByDefault:
    """Tests that the Visa button is disabled when no media is selected."""

    def test_visa_button_disabled_initially(
        self, qapp, project_with_media, tmp_path
    ) -> None:
        """Visa button is disabled when SourceEditor is first opened."""
        editor = SourceEditor(
            project_data=project_with_media,
            source=project_with_media.sources[0],
            project_folder=tmp_path,
        )
        assert editor._view_media_button.isEnabled() is False


class TestVisaButtonEnabledOnSelection:
    """Tests that the Visa button is enabled when a media item is selected."""

    def test_visa_button_enabled_when_media_selected(
        self, qapp, project_with_media, tmp_path
    ) -> None:
        """Visa button becomes enabled when user selects a media item."""
        editor = SourceEditor(
            project_data=project_with_media,
            source=project_with_media.sources[0],
            project_folder=tmp_path,
        )

        # Select the first item in the media list
        editor._ui.media_list.setCurrentRow(0)

        assert editor._view_media_button.isEnabled() is True


class TestVisaButtonOpensMedia:
    """Tests that clicking Visa calls QDesktopServices.openUrl with correct URL."""

    @patch("slaktbusken.ui.editors.source_editor.QDesktopServices.openUrl")
    def test_view_media_calls_open_url_with_correct_path(
        self, mock_open_url, qapp, project_with_media, tmp_path
    ) -> None:
        """Clicking Visa opens the media file via QDesktopServices.openUrl."""
        editor = SourceEditor(
            project_data=project_with_media,
            source=project_with_media.sources[0],
            project_folder=tmp_path,
        )

        # Select the first media item
        editor._ui.media_list.setCurrentRow(0)

        # Trigger the view action
        editor._on_view_media()

        # Verify openUrl was called with correct file:// URL
        expected_path = tmp_path / "media/photos/test_image.jpg"
        expected_url = QUrl.fromLocalFile(str(expected_path))

        mock_open_url.assert_called_once()
        actual_url = mock_open_url.call_args[0][0]
        assert actual_url == expected_url
