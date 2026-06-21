"""Unit tests for EventEditor event media section (death/funeral events).

Verifies that:
- The event media section is visible only for death and funeral event types.
- Media type combo is populated correctly per event type.
- File selection and title input are required (add disabled when missing).
- Linked media items display type and title.
- Remove action unlinks without deleting MediaItem.
- Validation shows indication of missing fields.

Covers Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from slaktbusken.model.event import Event, Participant
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.event_media_service import EventMediaService
from slaktbusken.ui.editors.event_editor import EventEditor, EVENT_MEDIA_TYPES


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
def project_data(person: Person) -> ProjectData:
    """Return project data with a person."""
    pd = ProjectData()
    pd.persons.append(person)
    return pd


@pytest.fixture()
def death_event(person: Person) -> Event:
    """Return a death event linked to the test person."""
    return Event(
        id="evt1",
        type="death",
        participants=[Participant(person_id="p1", role="avliden")],
    )


@pytest.fixture()
def funeral_event(person: Person) -> Event:
    """Return a funeral event linked to the test person."""
    return Event(
        id="evt2",
        type="funeral",
        participants=[Participant(person_id="p1", role="begravd")],
    )


class TestEventMediaSectionVisibility:
    """Test that the event media section is shown/hidden based on event type."""

    def test_hidden_for_birth_event(self, project_data: ProjectData) -> None:
        """Event media section hidden for non-death/funeral event types."""
        event = Event(
            id="evt_birth",
            type="birth",
            participants=[Participant(person_id="p1", role="född")],
        )
        editor = EventEditor(project_data, event=event)
        assert editor._event_media_group.isHidden()

    def test_visible_for_death_event(
        self, project_data: ProjectData, death_event: Event
    ) -> None:
        """Event media section visible for death events."""
        editor = EventEditor(project_data, event=death_event)
        assert not editor._event_media_group.isHidden()

    def test_visible_for_funeral_event(
        self, project_data: ProjectData, funeral_event: Event
    ) -> None:
        """Event media section visible for funeral events."""
        editor = EventEditor(project_data, event=funeral_event)
        assert not editor._event_media_group.isHidden()

    def test_hidden_for_marriage_event(self, project_data: ProjectData) -> None:
        """Event media section hidden for marriage events."""
        event = Event(
            id="evt_marriage",
            type="marriage",
            participants=[Participant(person_id="p1", role="make/maka")],
        )
        editor = EventEditor(project_data, event=event)
        assert editor._event_media_group.isHidden()


class TestEventMediaTypeCombo:
    """Test that the media type combo is populated correctly per event type."""

    def test_death_event_media_types(
        self, project_data: ProjectData, death_event: Event
    ) -> None:
        """Death events offer dödruna, dödsannons, bouppteckning, dödsbevis."""
        editor = EventEditor(project_data, event=death_event)
        combo = editor._event_media_type_combo
        types = [combo.itemData(i) for i in range(combo.count())]
        assert types == ["dödruna", "dödsannons", "bouppteckning", "dödsbevis"]

    def test_funeral_event_media_types(
        self, project_data: ProjectData, funeral_event: Event
    ) -> None:
        """Funeral events offer begravningsprogram, minnesord."""
        editor = EventEditor(project_data, event=funeral_event)
        combo = editor._event_media_type_combo
        types = [combo.itemData(i) for i in range(combo.count())]
        assert types == ["begravningsprogram", "minnesord"]


class TestEventMediaValidation:
    """Test validation and add button state for event media fields."""

    def test_add_button_disabled_initially(
        self, project_data: ProjectData, death_event: Event
    ) -> None:
        """Add button is disabled when no file or title is provided."""
        editor = EventEditor(project_data, event=death_event)
        assert not editor._event_media_add_button.isEnabled()

    def test_add_button_disabled_file_only(
        self, project_data: ProjectData, death_event: Event
    ) -> None:
        """Add button disabled when only file is set (no title)."""
        editor = EventEditor(project_data, event=death_event)
        editor._event_media_file_path = "/some/file.pdf"
        editor._update_event_media_validation()
        assert not editor._event_media_add_button.isEnabled()

    def test_add_button_disabled_title_only(
        self, project_data: ProjectData, death_event: Event
    ) -> None:
        """Add button disabled when only title is set (no file)."""
        editor = EventEditor(project_data, event=death_event)
        editor._event_media_title_input.setText("Test titel")
        assert not editor._event_media_add_button.isEnabled()

    def test_add_button_enabled_both_set(
        self, project_data: ProjectData, death_event: Event
    ) -> None:
        """Add button enabled when both file and title are provided."""
        editor = EventEditor(project_data, event=death_event)
        editor._event_media_file_path = "/some/file.pdf"
        editor._event_media_title_input.setText("Test titel")
        assert editor._event_media_add_button.isEnabled()

    def test_validation_label_shows_missing_fields(
        self, project_data: ProjectData, death_event: Event
    ) -> None:
        """Validation label shows which fields are missing."""
        editor = EventEditor(project_data, event=death_event)
        label_text = editor._event_media_validation_label.text()
        assert "fil" in label_text
        assert "titel" in label_text

    def test_validation_label_shows_only_title_missing(
        self, project_data: ProjectData, death_event: Event
    ) -> None:
        """Validation label shows only title missing when file is set."""
        editor = EventEditor(project_data, event=death_event)
        editor._event_media_file_path = "/some/file.pdf"
        editor._update_event_media_validation()
        label_text = editor._event_media_validation_label.text()
        assert "titel" in label_text
        assert "fil" not in label_text


class TestEventMediaAdd:
    """Test adding media items to an event."""

    def test_add_media_creates_item_in_list(
        self, project_data: ProjectData, death_event: Event
    ) -> None:
        """Adding media appends to the event media list."""
        editor = EventEditor(project_data, event=death_event)
        editor._event_media_file_path = "/docs/dodsruna.pdf"
        editor._event_media_title_input.setText("Min dödruna")
        editor._event_media_type_combo.setCurrentIndex(0)  # dödruna

        editor._on_event_media_add()

        assert editor._event_media_list.count() == 1
        item = editor._event_media_list.item(0)
        assert "dödruna" in item.text()
        assert "Min dödruna" in item.text()

    def test_add_media_resets_inputs(
        self, project_data: ProjectData, death_event: Event
    ) -> None:
        """After adding, file and title inputs are cleared."""
        editor = EventEditor(project_data, event=death_event)
        editor._event_media_file_path = "/docs/dodsruna.pdf"
        editor._event_media_title_input.setText("Min dödruna")
        editor._event_media_type_combo.setCurrentIndex(0)

        editor._on_event_media_add()

        assert editor._event_media_file_path == ""
        assert editor._event_media_title_input.text() == ""
        assert not editor._event_media_add_button.isEnabled()

    def test_add_media_creates_media_item_in_project_data(
        self, project_data: ProjectData, death_event: Event
    ) -> None:
        """Adding media creates a MediaItem in project_data.media."""
        initial_count = len(project_data.media)
        editor = EventEditor(project_data, event=death_event)
        editor._event_media_file_path = "/docs/dodsruna.pdf"
        editor._event_media_title_input.setText("Min dödruna")
        editor._event_media_type_combo.setCurrentIndex(0)

        editor._on_event_media_add()

        assert len(project_data.media) == initial_count + 1
        new_item = project_data.media[-1]
        assert new_item.type == "dödruna"
        assert new_item.file == "/docs/dodsruna.pdf"
        assert new_item.title == "Min dödruna"


class TestEventMediaRemove:
    """Test removing media items from an event."""

    def test_remove_unlinks_from_list(
        self, project_data: ProjectData, death_event: Event
    ) -> None:
        """Removing media removes it from the event media list display."""
        editor = EventEditor(project_data, event=death_event)
        editor._event_media_file_path = "/docs/dodsruna.pdf"
        editor._event_media_title_input.setText("Min dödruna")
        editor._event_media_type_combo.setCurrentIndex(0)
        editor._on_event_media_add()

        # Select and remove
        editor._event_media_list.setCurrentRow(0)
        editor._on_event_media_remove()

        assert editor._event_media_list.count() == 0

    def test_remove_preserves_media_item_in_project_data(
        self, project_data: ProjectData
    ) -> None:
        """Removing media from event preserves the MediaItem in project_data."""
        # Create a death event with linked media
        media_item = MediaItem(
            id="media1",
            type="dödruna",
            file="/docs/dodsruna.pdf",
            title="Min dödruna",
            linked_entities=[LinkedEntity(entity_type="event", entity_id="evt1")],
        )
        project_data.media.append(media_item)
        event = Event(
            id="evt1",
            type="death",
            participants=[Participant(person_id="p1", role="avliden")],
            media_ids=["media1"],
        )

        editor = EventEditor(project_data, event=event)

        # Select and remove
        editor._event_media_list.setCurrentRow(0)
        editor._on_event_media_remove()

        # MediaItem should still exist in project_data
        assert any(m.id == "media1" for m in project_data.media)


class TestEventMediaDisplay:
    """Test that linked media items are displayed correctly."""

    def test_existing_event_media_loaded(self, project_data: ProjectData) -> None:
        """When editing an event with media, items appear in the list."""
        media_item = MediaItem(
            id="media_x",
            type="dödsannons",
            file="/docs/annons.pdf",
            title="Dödsannons familjen Svensson",
            linked_entities=[LinkedEntity(entity_type="event", entity_id="evt_x")],
        )
        project_data.media.append(media_item)
        event = Event(
            id="evt_x",
            type="death",
            participants=[Participant(person_id="p1", role="avliden")],
            media_ids=["media_x"],
        )

        editor = EventEditor(project_data, event=event)

        assert editor._event_media_list.count() == 1
        item = editor._event_media_list.item(0)
        assert "dödsannons" in item.text()
        assert "Dödsannons familjen Svensson" in item.text()
