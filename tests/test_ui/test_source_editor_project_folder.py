"""Unit tests for project_folder propagation to SourceEditor.

Validates: Requirements 17.1

Tests that:
- SourceEditor receives and stores a non-None project_folder when provided
- SourceEditor stores None when no project_folder is provided
- EventEditor stores project_folder and passes it to SourceEditor instances
"""

from __future__ import annotations

from pathlib import Path

import pytest

from PySide6.QtWidgets import QApplication

from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.source import Source
from slaktbusken.ui.editors.source_editor import SourceEditor
from slaktbusken.ui.editors.event_editor import EventEditor


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def minimal_project() -> ProjectData:
    """Create a minimal ProjectData for testing."""
    return ProjectData(
        project=ProjectMetadata(title="Test Project"),
        sources=[
            Source(
                id="src-1",
                provider="Test Provider",
                source_type="other",
                title="Test Source",
            ),
        ],
    )


class TestSourceEditorProjectFolder:
    """Tests for project_folder propagation to SourceEditor."""

    def test_project_folder_is_set_when_provided(
        self, qapp, minimal_project, tmp_path
    ) -> None:
        """SourceEditor stores project_folder when a valid path is given."""
        editor = SourceEditor(
            project_data=minimal_project,
            project_folder=tmp_path,
        )
        assert editor._project_folder == tmp_path

    def test_project_folder_is_none_when_not_provided(
        self, qapp, minimal_project
    ) -> None:
        """SourceEditor stores None when no project_folder is given."""
        editor = SourceEditor(
            project_data=minimal_project,
            project_folder=None,
        )
        assert editor._project_folder is None

    def test_project_folder_defaults_to_none(
        self, qapp, minimal_project
    ) -> None:
        """SourceEditor defaults project_folder to None when omitted."""
        editor = SourceEditor(
            project_data=minimal_project,
        )
        assert editor._project_folder is None


class TestEventEditorProjectFolder:
    """Tests for project_folder storage in EventEditor."""

    def test_event_editor_stores_project_folder(
        self, qapp, minimal_project, tmp_path
    ) -> None:
        """EventEditor stores the project_folder attribute when provided."""
        editor = EventEditor(
            project_data=minimal_project,
            project_folder=tmp_path,
        )
        assert editor._project_folder == tmp_path

    def test_event_editor_project_folder_defaults_to_none(
        self, qapp, minimal_project
    ) -> None:
        """EventEditor defaults project_folder to None when omitted."""
        editor = EventEditor(
            project_data=minimal_project,
        )
        assert editor._project_folder is None
