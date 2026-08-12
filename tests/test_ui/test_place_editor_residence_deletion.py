"""Unit tests for Place_Editor place deletion refusal with residence dependencies.

Verifies that the Place_Editor refuses to delete a place when Residence_Facts
reference it, showing one blocking entry per referencing fact and leaving the
place and residences collection unchanged.

Requirements: 1.9, 18.17
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QListWidgetItem, QMessageBox

from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import ResidenceFact
from slaktbusken.ui.editors.place_editor import PlaceEditor


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_project(
    places: list[Place],
    persons: list[Person] | None = None,
    residences: list[ResidenceFact] | None = None,
) -> ProjectData:
    """Create a minimal ProjectData."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        places=places,
        persons=persons or [],
        residences=residences or [],
    )


class TestPlaceDeletionRefusedWithResidences:
    """Place deletion is blocked when Residence_Facts reference the place."""

    def test_refuses_deletion_when_residence_references_place(self, qapp) -> None:
        """Deletion refused and place + residences unchanged when a residence exists."""
        place = Place(id="place_1", name="Testgård", type="farm")
        person = Person(
            id="p1", sex="F",
            names=[Name(type="birth", given="Anna", surname="Svensson")],
        )
        residence = ResidenceFact(
            id="res_1", person_id="p1", place_id="place_1"
        )
        project = _make_project(
            places=[place],
            persons=[person],
            residences=[residence],
        )

        with patch.object(PlaceEditor, "__init__", lambda self, *a, **kw: None):
            editor = PlaceEditor.__new__(PlaceEditor)
            editor._project_data = project
            editor._editing_place = place

            # Mock the UI to simulate a selected item
            mock_item = MagicMock()
            mock_item.data.return_value = "place_1"
            editor._ui = MagicMock()
            editor._ui.place_list.currentItem.return_value = mock_item

            # Mock _find_place_by_id to return the place
            editor._find_place_by_id = MagicMock(return_value=place)
            editor._update_status = MagicMock()
            editor._clear_form = MagicMock()
            editor._refresh_place_list = MagicMock()
            editor._clear_status = MagicMock()

            # Patch QMessageBox.warning to capture the call and simulate Ok
            with patch.object(
                QMessageBox, "warning", return_value=QMessageBox.StandardButton.Ok
            ) as mock_warning:
                editor._on_delete_place()

            # The warning was shown with blocking info
            mock_warning.assert_called_once()
            call_args = mock_warning.call_args
            message_text = call_args[0][2]  # third positional arg is the message
            assert "Boende" in message_text
            assert "Svensson, Anna" in message_text
            assert "res_1" in message_text

            # Place and residences remain unchanged
            assert len(project.places) == 1
            assert project.places[0].id == "place_1"
            assert len(project.residences) == 1
            assert project.residences[0].id == "res_1"

    def test_refuses_deletion_with_multiple_residences(self, qapp) -> None:
        """One blocking entry per referencing Residence_Fact is shown."""
        place = Place(id="place_1", name="Testgård", type="farm")
        persons = [
            Person(
                id="p1", sex="F",
                names=[Name(type="birth", given="Anna", surname="Svensson")],
            ),
            Person(
                id="p2", sex="M",
                names=[Name(type="birth", given="Erik", surname="Karlsson")],
            ),
        ]
        residences = [
            ResidenceFact(id="res_1", person_id="p1", place_id="place_1"),
            ResidenceFact(id="res_2", person_id="p2", place_id="place_1"),
            ResidenceFact(id="res_3", person_id="p1", place_id="other_place"),
        ]
        project = _make_project(
            places=[place, Place(id="other_place", name="Annan", type="farm")],
            persons=persons,
            residences=residences,
        )

        with patch.object(PlaceEditor, "__init__", lambda self, *a, **kw: None):
            editor = PlaceEditor.__new__(PlaceEditor)
            editor._project_data = project
            editor._editing_place = place

            mock_item = MagicMock()
            mock_item.data.return_value = "place_1"
            editor._ui = MagicMock()
            editor._ui.place_list.currentItem.return_value = mock_item
            editor._find_place_by_id = MagicMock(return_value=place)
            editor._update_status = MagicMock()

            with patch.object(
                QMessageBox, "warning", return_value=QMessageBox.StandardButton.Ok
            ) as mock_warning:
                editor._on_delete_place()

            mock_warning.assert_called_once()
            message_text = mock_warning.call_args[0][2]
            # Both referencing residences mentioned, not the third one
            assert "res_1" in message_text
            assert "res_2" in message_text
            assert "res_3" not in message_text

            # Place and all residences unchanged
            assert len(project.places) == 2
            assert len(project.residences) == 3

    def test_allows_deletion_when_no_residence_references_place(self, qapp) -> None:
        """Place can be deleted when no Residence_Facts reference it."""
        place = Place(id="place_1", name="Testgård", type="farm")
        other_place = Place(id="place_2", name="Annan", type="farm")
        residence = ResidenceFact(
            id="res_1", person_id="p1", place_id="place_2"
        )
        project = _make_project(
            places=[place, other_place],
            residences=[residence],
        )

        with patch.object(PlaceEditor, "__init__", lambda self, *a, **kw: None):
            editor = PlaceEditor.__new__(PlaceEditor)
            editor._project_data = project
            editor._editing_place = place

            mock_item = MagicMock()
            mock_item.data.return_value = "place_1"
            editor._ui = MagicMock()
            editor._ui.place_list.currentItem.return_value = mock_item
            editor._find_place_by_id = MagicMock(return_value=place)
            editor._find_referencing_events = MagicMock(return_value=[])
            editor._update_status = MagicMock()
            editor._clear_form = MagicMock()
            editor._refresh_place_list = MagicMock()
            editor._clear_status = MagicMock()

            # Patch QMessageBox to confirm deletion
            with patch.object(
                QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
            ):
                editor._on_delete_place()

            # Place was removed
            assert len(project.places) == 1
            assert project.places[0].id == "place_2"
            # Residences unchanged
            assert len(project.residences) == 1

    def test_residence_check_runs_before_event_warning(self, qapp) -> None:
        """Residence dependency check runs before event-referencing check."""
        place = Place(id="place_1", name="Testgård", type="farm")
        residence = ResidenceFact(
            id="res_1", person_id="p1", place_id="place_1"
        )
        project = _make_project(
            places=[place],
            residences=[residence],
        )

        with patch.object(PlaceEditor, "__init__", lambda self, *a, **kw: None):
            editor = PlaceEditor.__new__(PlaceEditor)
            editor._project_data = project
            editor._editing_place = place

            mock_item = MagicMock()
            mock_item.data.return_value = "place_1"
            editor._ui = MagicMock()
            editor._ui.place_list.currentItem.return_value = mock_item
            editor._find_place_by_id = MagicMock(return_value=place)
            editor._update_status = MagicMock()
            editor._clear_form = MagicMock()
            editor._refresh_place_list = MagicMock()
            editor._clear_status = MagicMock()

            # _find_referencing_events should NOT be called if residences block
            editor._find_referencing_events = MagicMock(return_value=[])

            with patch.object(
                QMessageBox, "warning", return_value=QMessageBox.StandardButton.Ok
            ):
                editor._on_delete_place()

            # Event check was never reached
            editor._find_referencing_events.assert_not_called()
