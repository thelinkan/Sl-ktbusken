"""Unit tests for EventEditor placement parent-role offering.

Verifies that the event editor offers the correct parent role when a user adds
a participant to a placement event:
- "fosterförälder" for foster placement types (foster_home, foster_home_ended)
- "adoptivförälder" for adoptive placement types (adoption, adoption_ended)

The child role ("fosterbarn"/"adopterad") remains driven by the existing
EVENT_TYPE_ROLES default-role map and is not re-tested here.

Covers Requirement 1.2.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.event import Event, Participant
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.editors.event_editor import (
    PLACEMENT_PARENT_ROLES,
    EventEditor,
)


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def project_data() -> ProjectData:
    """Return project data with two persons (a child and a parent)."""
    pd = ProjectData()
    pd.persons.append(
        Person(
            id="child1",
            sex="female",
            names=[Name(type="birth", given="Anna", surname="Larsson")],
        )
    )
    pd.persons.append(
        Person(
            id="parent1",
            sex="female",
            names=[Name(type="birth", given="Karin", surname="Nilsson")],
        )
    )
    return pd


def _select_type(editor: EventEditor, event_type: str) -> None:
    """Select the given event type in the editor's type combo."""
    index = editor._ui.type_combo.findData(event_type)
    assert index >= 0, f"event type {event_type!r} not registered in combo"
    editor._ui.type_combo.setCurrentIndex(index)


class TestPlacementParentRoleMap:
    """The module-level mapping offers the right parent role per placement type."""

    def test_foster_types_offer_fosterforalder(self) -> None:
        assert PLACEMENT_PARENT_ROLES["foster_home"] == "fosterförälder"
        assert PLACEMENT_PARENT_ROLES["foster_home_ended"] == "fosterförälder"

    def test_adoptive_types_offer_adoptivforalder(self) -> None:
        assert PLACEMENT_PARENT_ROLES["adoption"] == "adoptivförälder"
        assert PLACEMENT_PARENT_ROLES["adoption_ended"] == "adoptivförälder"


class TestParentRoleOffered:
    """The role input is pre-filled with the parent role for placement events."""

    def test_foster_home_offers_fosterforalder(
        self, project_data: ProjectData
    ) -> None:
        editor = EventEditor(project_data, subject_person_id="child1")
        _select_type(editor, "foster_home")
        assert editor._ui.participant_role_input.text().strip() == "fosterförälder"

    def test_adoption_offers_adoptivforalder(
        self, project_data: ProjectData
    ) -> None:
        editor = EventEditor(project_data, subject_person_id="child1")
        _select_type(editor, "adoption")
        assert editor._ui.participant_role_input.text().strip() == "adoptivförälder"

    def test_non_placement_event_offers_no_parent_role(
        self, project_data: ProjectData
    ) -> None:
        editor = EventEditor(project_data, subject_person_id="child1")
        _select_type(editor, "birth")
        assert editor._ui.participant_role_input.text().strip() == ""

    def test_user_override_is_not_clobbered(
        self, project_data: ProjectData
    ) -> None:
        """A role the user already typed is not replaced by the suggestion."""
        editor = EventEditor(project_data, subject_person_id="child1")
        editor._ui.participant_role_input.setText("vårdnadshavare")
        _select_type(editor, "foster_home")
        assert editor._ui.participant_role_input.text().strip() == "vårdnadshavare"


class TestParticipantsSectionVisible:
    """The participants section is usable so a parent can be added."""

    def test_placement_event_shows_participants_for_new_subject(
        self, project_data: ProjectData
    ) -> None:
        editor = EventEditor(project_data, subject_person_id="child1")
        _select_type(editor, "foster_home")
        assert editor._ui.participants_group.isVisibleTo(editor)

    def test_non_placement_individual_event_hides_participants(
        self, project_data: ProjectData
    ) -> None:
        editor = EventEditor(project_data, subject_person_id="child1")
        _select_type(editor, "birth")
        assert not editor._ui.participants_group.isVisibleTo(editor)


class TestAddParentParticipant:
    """Adding a parent uses the offered role and re-offers it for a second parent."""

    def test_adds_foster_parent_with_offered_role(
        self, project_data: ProjectData
    ) -> None:
        editor = EventEditor(project_data, subject_person_id="child1")
        _select_type(editor, "foster_home")
        # Select the parent person in the combo.
        combo = editor._ui.participant_person_combo
        combo.setCurrentIndex(combo.findData("parent1"))
        editor._on_add_participant()

        table = editor._ui.participants_table
        roles = [table.item(r, 1).text() for r in range(table.rowCount())]
        assert "fosterförälder" in roles
        # The role field is re-offered so a second parent is easy to add.
        assert editor._ui.participant_role_input.text().strip() == "fosterförälder"
