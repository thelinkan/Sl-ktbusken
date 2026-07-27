"""Unit tests for person checks menu integration and dialog opening.

Validates Requirements 1.1, 1.2, 1.3, 1.4:
- Menu action exists with correct text
- Action is disabled without an open project
- Action is enabled when a project is open
- Dialog opens as modal
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication

from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.settings_io import PersonCheckConfig
from slaktbusken.ui.dialogs.kontrollera_personer_dialog import KontrolleraPersonerDialog


# Ensure QApplication instance exists for widget tests
@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# Dialog modal tests (Req 1.4)
# ---------------------------------------------------------------------------


class TestPersonChecksDialogModal:
    """Test that the dialog opens as modal (Req 1.4)."""

    def test_dialog_is_modal(self) -> None:
        """KontrolleraPersonerDialog should be modal."""
        data = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=[],
            events=[],
            families=[],
        )
        config = PersonCheckConfig()
        dialog = KontrolleraPersonerDialog(
            data=data, config=config, project_folder=None
        )
        assert dialog.isModal()

    def test_dialog_has_three_tabs(self) -> None:
        """Dialog should have exactly three tabs."""
        data = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=[],
            events=[],
            families=[],
        )
        config = PersonCheckConfig()
        dialog = KontrolleraPersonerDialog(
            data=data, config=config, project_folder=None
        )
        assert dialog._tab_widget.count() == 3

    def test_result_tab_is_active_on_open(self) -> None:
        """Resultat tab (index 0) should be active when dialog opens."""
        data = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=[],
            events=[],
            families=[],
        )
        config = PersonCheckConfig()
        dialog = KontrolleraPersonerDialog(
            data=data, config=config, project_folder=None
        )
        assert dialog._tab_widget.currentIndex() == 0


# ---------------------------------------------------------------------------
# Menu action tests (Req 1.1, 1.2, 1.3)
# ---------------------------------------------------------------------------


class TestPersonChecksMenuAction:
    """Test menu action enabled/disabled state (Req 1.1, 1.2, 1.3)."""

    @pytest.fixture
    def main_window(self):
        """Create a MainWindow with a mocked Application."""
        from slaktbusken.ui.main_window import MainWindow

        app_mock = MagicMock()
        window = MainWindow(app_mock)
        yield window
        window.close()

    def test_action_exists_in_main_window(self, main_window) -> None:
        """MainWindow should have action_person_checks with correct text (Req 1.1)."""
        assert hasattr(main_window, "action_person_checks")
        assert main_window.action_person_checks.text() == "Kontrollera &personer..."

    def test_action_disabled_without_project(self, main_window) -> None:
        """action_person_checks should be disabled when no project is open (Req 1.2)."""
        main_window._update_project_actions(project_open=False)
        assert main_window.action_person_checks.isEnabled() is False

    def test_action_enabled_with_project(self, main_window) -> None:
        """action_person_checks should be enabled when a project is open (Req 1.3)."""
        main_window._update_project_actions(project_open=True)
        assert main_window.action_person_checks.isEnabled() is True
