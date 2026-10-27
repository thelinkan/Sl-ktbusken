"""Unit tests for EventEditor participant collection on save.

Regression coverage for a data-loss bug: when creating a placement event
(foster_home/adoption/..) from the person editor, the editor auto-adds the
subject as the child and the user adds foster/adoptive parents to the
participants table. On save, the parents must NOT be discarded — participants
must be collected from the table for placement events, exactly like family and
edited/standalone events.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.event import Participant
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.editors.event_editor import EventEditor


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def project_data() -> ProjectData:
    """Return project data with a child and a parent person."""
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


class TestPlacementSaveKeepsParents:
    """Placement events save the child subject AND the added parent(s)."""

    def test_foster_home_saves_child_and_foster_parent(
        self, project_data: ProjectData
    ) -> None:
        editor = EventEditor(project_data, subject_person_id="child1")
        _select_type(editor, "foster_home")
        # Simulate the real flow: the user adds a foster parent row.
        editor._add_participant_row(
            Participant(person_id="parent1", role="fosterförälder")
        )

        editor._on_save()

        saved = editor.saved_event
        assert saved is not None, "save should succeed"
        pairs = {(p.person_id, p.role) for p in saved.participants}
        # The auto-added subject is kept as the child.
        assert ("child1", "fosterbarn") in pairs
        # The foster parent is NOT discarded.
        assert ("parent1", "fosterförälder") in pairs
        assert len(saved.participants) == 2

    def test_adoption_saves_child_and_adoptive_parent(
        self, project_data: ProjectData
    ) -> None:
        editor = EventEditor(project_data, subject_person_id="child1")
        _select_type(editor, "adoption")
        editor._add_participant_row(
            Participant(person_id="parent1", role="adoptivförälder")
        )

        editor._on_save()

        saved = editor.saved_event
        assert saved is not None
        pairs = {(p.person_id, p.role) for p in saved.participants}
        assert ("child1", "adopterad") in pairs
        assert ("parent1", "adoptivförälder") in pairs
        assert len(saved.participants) == 2


class TestIndividualSaveUnchanged:
    """A plain individual event still saves with just the subject."""

    def test_birth_saves_only_subject(self, project_data: ProjectData) -> None:
        editor = EventEditor(project_data, subject_person_id="child1")
        _select_type(editor, "birth")
        # No table edits.

        editor._on_save()

        saved = editor.saved_event
        assert saved is not None
        assert len(saved.participants) == 1
        assert saved.participants[0].person_id == "child1"
        assert saved.participants[0].role == "född"
