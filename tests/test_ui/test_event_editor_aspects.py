"""Unit tests for EventEditor source aspect checkboxes.

Verifies that:
- Aspect checkboxes display with correct Swedish labels for each event type.
- Checkboxes are all unselected when a source is first linked.
- Selecting a source row loads its stored aspects into checkboxes.
- Toggling checkboxes updates the stored aspects for the selected row.
- Saving persists aspects with the SourceRef.
- Saving with no aspects selected is allowed.
- Changing event type updates the available checkboxes.

Covers Requirements 9.1, 9.2, 9.3.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    SourceRef,
)
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.model.source import Source
from slaktbusken.services.source_aspects import (
    ASPECT_LABELS,
    get_aspects_for_event_type,
)
from slaktbusken.ui.editors.event_editor import EventEditor


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def person() -> Person:
    """Return a test person."""
    return Person(
        id="p1",
        sex="male",
        names=[Name(type="birth", given="Erik", surname="Svensson")],
    )


@pytest.fixture()
def source() -> Source:
    """Return a test source."""
    return Source(id="src1", provider="Arkiv Digital", source_type="church_book", title="Husförhörslängd Ljusdal")


@pytest.fixture()
def project_data(person: Person, source: Source) -> ProjectData:
    """Return project data with a person and a source."""
    pd = ProjectData()
    pd.persons.append(person)
    pd.sources.append(source)
    return pd


class TestAspectCheckboxesDisplay:
    """Test that aspect checkboxes are shown with correct labels per event type."""

    def test_birth_event_shows_four_aspects(self, project_data: ProjectData) -> None:
        """Birth events should show date, place, parents, witnesses checkboxes."""
        event = Event(
            id="evt1",
            type="birth",
            participants=[Participant(person_id="p1", role="född")],
        )
        editor = EventEditor(project_data, event=event)
        aspect_keys = [cb.property("aspect_key") for cb in editor._aspect_checkboxes]
        assert aspect_keys == ["date", "place", "parents", "witnesses"]

    def test_death_event_shows_three_aspects(self, project_data: ProjectData) -> None:
        """Death events should show date, place, cause_of_death checkboxes."""
        event = Event(
            id="evt1",
            type="death",
            participants=[Participant(person_id="p1", role="avliden")],
        )
        editor = EventEditor(project_data, event=event)
        aspect_keys = [cb.property("aspect_key") for cb in editor._aspect_checkboxes]
        assert aspect_keys == ["date", "place", "cause_of_death"]

    def test_marriage_event_shows_three_aspects(self, project_data: ProjectData) -> None:
        """Marriage events should show date, place, spouse checkboxes."""
        event = Event(
            id="evt1",
            type="marriage",
            participants=[Participant(person_id="p1", role="make/maka")],
        )
        editor = EventEditor(project_data, event=event)
        aspect_keys = [cb.property("aspect_key") for cb in editor._aspect_checkboxes]
        assert aspect_keys == ["date", "place", "spouse"]

    def test_other_event_shows_default_aspects(self, project_data: ProjectData) -> None:
        """Other event types should show date, place checkboxes."""
        event = Event(
            id="evt1",
            type="emigration",
            participants=[Participant(person_id="p1", role="emigrant")],
        )
        editor = EventEditor(project_data, event=event)
        aspect_keys = [cb.property("aspect_key") for cb in editor._aspect_checkboxes]
        assert aspect_keys == ["date", "place"]

    def test_checkboxes_use_swedish_labels(self, project_data: ProjectData) -> None:
        """Checkboxes should use Swedish labels from ASPECT_LABELS."""
        event = Event(
            id="evt1",
            type="birth",
            participants=[Participant(person_id="p1", role="född")],
        )
        editor = EventEditor(project_data, event=event)
        labels = [cb.text() for cb in editor._aspect_checkboxes]
        assert labels == ["Datum", "Plats", "Föräldrar", "Vittnen"]


class TestAspectCheckboxesInitialState:
    """Test that checkboxes are unchecked when a source is first linked."""

    def test_new_source_has_unchecked_aspects(self, project_data: ProjectData) -> None:
        """When a source is first added, all aspect checkboxes should be unchecked."""
        event = Event(
            id="evt1",
            type="birth",
            participants=[Participant(person_id="p1", role="född")],
        )
        editor = EventEditor(project_data, event=event)

        # Add a source via the UI fields
        editor._ui.source_combo.setCurrentIndex(
            editor._ui.source_combo.findData("src1")
        )
        editor._ui.source_quality_combo.setCurrentIndex(0)
        editor._on_add_source()

        # Select the newly added row
        editor._ui.sources_table.selectRow(0)

        # All checkboxes should be unchecked
        for cb in editor._aspect_checkboxes:
            assert not cb.isChecked()


class TestAspectCheckboxesPersistence:
    """Test that aspects are persisted with SourceRef on save."""

    def test_checked_aspects_collected_on_save(self, project_data: ProjectData) -> None:
        """Saving should include the selected aspects in the SourceRef."""
        event = Event(
            id="evt1",
            type="birth",
            participants=[Participant(person_id="p1", role="född")],
        )
        editor = EventEditor(project_data, event=event)

        # Add a source
        editor._ui.source_combo.setCurrentIndex(
            editor._ui.source_combo.findData("src1")
        )
        editor._ui.source_quality_combo.setCurrentIndex(0)
        editor._on_add_source()

        # Select the row and check some aspects
        editor._ui.sources_table.selectRow(0)
        for cb in editor._aspect_checkboxes:
            if cb.property("aspect_key") in ("date", "parents"):
                cb.setChecked(True)

        # Collect source refs
        refs = editor._collect_source_refs()
        assert len(refs) == 1
        assert sorted(refs[0].aspects) == ["date", "parents"]

    def test_no_aspects_selected_is_allowed(self, project_data: ProjectData) -> None:
        """Saving with no aspects selected should result in an empty aspects list."""
        event = Event(
            id="evt1",
            type="birth",
            participants=[Participant(person_id="p1", role="född")],
        )
        editor = EventEditor(project_data, event=event)

        # Add a source (no aspects checked)
        editor._ui.source_combo.setCurrentIndex(
            editor._ui.source_combo.findData("src1")
        )
        editor._ui.source_quality_combo.setCurrentIndex(0)
        editor._on_add_source()

        # Collect source refs
        refs = editor._collect_source_refs()
        assert len(refs) == 1
        assert refs[0].aspects == []

    def test_existing_aspects_preserved_on_load(self, project_data: ProjectData) -> None:
        """Loading an event with existing aspects should preserve them in the table."""
        source_ref = SourceRef(
            source_id="src1", quality="primary", note="", aspects=["date", "place"]
        )
        event = Event(
            id="evt1",
            type="birth",
            participants=[Participant(person_id="p1", role="född")],
            date=DateValue(value="1880-01-01", precision="exact", source_refs=[source_ref]),
        )
        editor = EventEditor(project_data, event=event)

        # Select the loaded source row
        editor._ui.sources_table.selectRow(0)

        # Verify stored aspects
        refs = editor._collect_source_refs()
        assert len(refs) == 1
        assert sorted(refs[0].aspects) == ["date", "place"]

        # Verify checkboxes are checked
        checked_keys = [
            cb.property("aspect_key")
            for cb in editor._aspect_checkboxes
            if cb.isChecked()
        ]
        assert sorted(checked_keys) == ["date", "place"]


class TestAspectCheckboxesInteraction:
    """Test checkbox interaction with row selection."""

    def test_selecting_row_loads_aspects(self, project_data: ProjectData) -> None:
        """Selecting a source row should load its aspects into checkboxes."""
        source_ref = SourceRef(
            source_id="src1", quality="primary", note="", aspects=["place"]
        )
        event = Event(
            id="evt1",
            type="birth",
            participants=[Participant(person_id="p1", role="född")],
            date=DateValue(value="1880-01-01", precision="exact", source_refs=[source_ref]),
        )
        editor = EventEditor(project_data, event=event)

        # Select the row
        editor._ui.sources_table.selectRow(0)

        # Only "place" should be checked
        for cb in editor._aspect_checkboxes:
            if cb.property("aspect_key") == "place":
                assert cb.isChecked()
            else:
                assert not cb.isChecked()

    def test_type_change_rebuilds_checkboxes(self, project_data: ProjectData) -> None:
        """Changing event type should rebuild aspect checkboxes."""
        editor = EventEditor(project_data, subject_person_id="p1")

        # Initially type is the first one (adoption) - should have default aspects
        # Change to death
        death_index = editor._ui.type_combo.findData("death")
        editor._ui.type_combo.setCurrentIndex(death_index)

        aspect_keys = [cb.property("aspect_key") for cb in editor._aspect_checkboxes]
        assert aspect_keys == ["date", "place", "cause_of_death"]

        # Change to birth
        birth_index = editor._ui.type_combo.findData("birth")
        editor._ui.type_combo.setCurrentIndex(birth_index)

        aspect_keys = [cb.property("aspect_key") for cb in editor._aspect_checkboxes]
        assert aspect_keys == ["date", "place", "parents", "witnesses"]
