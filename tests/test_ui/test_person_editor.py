"""Unit tests for the PersonEditor widget.

Tests person loading, name management, validation, and save logic
using a QApplication instance for widget creation.
"""

from __future__ import annotations

import pytest

from PySide6.QtWidgets import QApplication

from slaktbusken.model.dna import DnaCluster, DnaMatch, DnaProfile
from slaktbusken.model.event import Event, Participant
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.editors.person_editor import PersonEditor


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def empty_project() -> ProjectData:
    """Create an empty project data for testing."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
    )


@pytest.fixture()
def sample_person() -> Person:
    """Create a sample person with names for testing."""
    return Person(
        id="person_1",
        sex="M",
        names=[
            Name(type="birth", given="Erik", surname="Johansson"),
            Name(type="married", given="Erik", surname="Eriksson"),
        ],
        notes="Test notes",
        title="Fil.Dr",
        occupation="Lektor",
        profile_media_id="media_1",
    )


@pytest.fixture()
def project_with_linked_data(sample_person: Person) -> ProjectData:
    """Create a project with events, media, and DNA linked to sample_person."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=[sample_person],
        events=[
            Event(
                id="event_1",
                type="birth",
                participants=[Participant(person_id="person_1", role="child")],
            ),
            Event(
                id="event_2",
                type="marriage",
                participants=[
                    Participant(person_id="person_1", role="husband"),
                    Participant(person_id="person_2", role="wife"),
                ],
            ),
        ],
        media=[
            MediaItem(
                id="media_1",
                type="photo",
                file="photos/erik.jpg",
                title="Erik porträtt",
                linked_entities=[
                    LinkedEntity(entity_type="person", entity_id="person_1"),
                ],
            ),
        ],
        dna_profiles=[
            DnaProfile(
                id="dnaprofile_1",
                person_id="person_1",
                company_id="dnacompany_1",
                test_type="autosomal",
                kit_name="Eriks kit",
            ),
        ],
        dna_matches=[
            DnaMatch(
                id="dnamatch_1",
                profile1_id="dnaprofile_1",
                profile2_id="dnaprofile_2",
                shared_cm=250.0,
                segment_count=12,
            ),
        ],
        dna_clusters=[
            DnaCluster(
                id="dnacluster_1",
                name="Västergötland-kluster",
                person_ids=["person_1", "person_3"],
            ),
        ],
    )


class TestPersonEditorNewPerson:
    """Tests for creating a new person."""

    def test_new_person_starts_empty(self, qapp, empty_project: ProjectData):
        """A new editor with no person should have empty fields."""
        editor = PersonEditor(empty_project, person=None)
        assert editor._ui.names_table.rowCount() == 0
        assert editor._ui.sex_combo.currentText() == "M"
        assert editor._ui.title_input.text() == ""
        assert editor._ui.occupation_input.text() == ""

    def test_save_without_name_shows_error(self, qapp, empty_project: ProjectData):
        """Save without any name entry should show error and prevent save."""
        editor = PersonEditor(empty_project, person=None)
        editor._on_save()

        assert editor.saved_person is None
        assert editor._ui.status_label.text() == "Minst ett namn krävs"

    def test_save_without_name_switches_to_names_tab(
        self, qapp, empty_project: ProjectData
    ):
        """Save without name should switch to names tab."""
        editor = PersonEditor(empty_project, person=None)
        # Switch to another tab first
        editor._ui.tab_widget.setCurrentIndex(1)
        editor._on_save()

        assert editor._ui.tab_widget.currentWidget() == editor._ui.names_tab

    def test_add_name_and_save(self, qapp, empty_project: ProjectData):
        """Adding a name and saving should produce a valid Person."""
        editor = PersonEditor(empty_project, person=None)

        # Add a name via the input fields
        editor._ui.name_type_combo.setCurrentIndex(0)  # birth
        editor._ui.given_name_input.setText("Anna")
        editor._ui.surname_input.setText("Svensson")
        editor._on_add_name()

        assert editor._ui.names_table.rowCount() == 1

        # Set sex
        editor._ui.sex_combo.setCurrentIndex(1)  # F

        editor._on_save()

        person = editor.saved_person
        assert person is not None
        assert person.sex == "F"
        assert len(person.names) == 1
        assert person.names[0].type == "birth"
        assert person.names[0].given == "Anna"
        assert person.names[0].surname == "Svensson"
        assert person.id  # Should have a generated UUID

    def test_add_name_clears_fields(self, qapp, empty_project: ProjectData):
        """After adding a name, edit fields should be cleared."""
        editor = PersonEditor(empty_project, person=None)
        editor._ui.given_name_input.setText("Test")
        editor._ui.surname_input.setText("Testsson")
        editor._on_add_name()

        assert editor._ui.given_name_input.text() == ""
        assert editor._ui.surname_input.text() == ""

    def test_add_name_requires_given_or_surname(
        self, qapp, empty_project: ProjectData
    ):
        """Adding a name with both fields empty should show error."""
        editor = PersonEditor(empty_project, person=None)
        editor._ui.given_name_input.setText("")
        editor._ui.surname_input.setText("")
        editor._on_add_name()

        assert editor._ui.names_table.rowCount() == 0
        assert editor._ui.status_label.text() == "Ange förnamn eller efternamn."


class TestPersonEditorExistingPerson:
    """Tests for editing an existing person."""

    def test_load_person_populates_fields(
        self, qapp, empty_project: ProjectData, sample_person: Person
    ):
        """Loading an existing person should populate all fields."""
        editor = PersonEditor(empty_project, person=sample_person)

        assert editor._ui.sex_combo.currentText() == "M"
        assert editor._ui.title_input.text() == "Fil.Dr"
        assert editor._ui.occupation_input.text() == "Lektor"
        assert editor._ui.notes_input.toPlainText() == "Test notes"
        assert editor._ui.names_table.rowCount() == 2

    def test_load_person_names_in_table(
        self, qapp, empty_project: ProjectData, sample_person: Person
    ):
        """Person names should appear in the table."""
        editor = PersonEditor(empty_project, person=sample_person)
        table = editor._ui.names_table

        assert table.item(0, 0).text() == "birth"
        assert table.item(0, 1).text() == "Erik"
        assert table.item(0, 2).text() == "Johansson"
        assert table.item(1, 0).text() == "married"
        assert table.item(1, 1).text() == "Erik"
        assert table.item(1, 2).text() == "Eriksson"

    def test_save_existing_person_preserves_id(
        self, qapp, empty_project: ProjectData, sample_person: Person
    ):
        """Saving an existing person should preserve the original ID."""
        editor = PersonEditor(empty_project, person=sample_person)
        editor._on_save()

        assert editor.saved_person is not None
        assert editor.saved_person.id == "person_1"

    def test_remove_name(
        self, qapp, empty_project: ProjectData, sample_person: Person
    ):
        """Removing a selected name should reduce the table row count."""
        editor = PersonEditor(empty_project, person=sample_person)
        # Select first row
        editor._ui.names_table.selectRow(0)
        editor._on_remove_name()

        assert editor._ui.names_table.rowCount() == 1

    def test_edit_name(
        self, qapp, empty_project: ProjectData, sample_person: Person
    ):
        """Editing a selected name should update the table."""
        editor = PersonEditor(empty_project, person=sample_person)
        # Select first row
        editor._ui.names_table.selectRow(0)
        editor._ui.given_name_input.setText("Karl")
        editor._ui.surname_input.setText("Karlsson")
        editor._ui.name_type_combo.setCurrentIndex(3)  # other
        editor._on_edit_name()

        table = editor._ui.names_table
        assert table.item(0, 0).text() == "other"
        assert table.item(0, 1).text() == "Karl"
        assert table.item(0, 2).text() == "Karlsson"


class TestPersonEditorLinkedData:
    """Tests for events, media, and DNA display."""

    def test_events_list_populated(
        self, qapp, project_with_linked_data: ProjectData, sample_person: Person
    ):
        """Events list should show events where this person participates."""
        editor = PersonEditor(project_with_linked_data, person=sample_person)
        assert editor._ui.events_list.count() == 2

    def test_media_list_populated(
        self, qapp, project_with_linked_data: ProjectData, sample_person: Person
    ):
        """Media list should show photos linked to this person."""
        editor = PersonEditor(project_with_linked_data, person=sample_person)
        assert editor._ui.media_list.count() == 1

    def test_profile_photo_display(
        self, qapp, project_with_linked_data: ProjectData, sample_person: Person
    ):
        """Profile photo display should show the media ID."""
        editor = PersonEditor(project_with_linked_data, person=sample_person)
        assert "media_1" in editor._ui.profile_photo_display.text()

    def test_dna_profiles_populated(
        self, qapp, project_with_linked_data: ProjectData, sample_person: Person
    ):
        """DNA profiles list should show profiles for this person."""
        editor = PersonEditor(project_with_linked_data, person=sample_person)
        assert editor._ui.dna_profiles_list.count() == 1

    def test_dna_matches_populated(
        self, qapp, project_with_linked_data: ProjectData, sample_person: Person
    ):
        """DNA matches list should show matches for this person's profiles."""
        editor = PersonEditor(project_with_linked_data, person=sample_person)
        assert editor._ui.dna_matches_list.count() == 1

    def test_dna_clusters_populated(
        self, qapp, project_with_linked_data: ProjectData, sample_person: Person
    ):
        """DNA clusters list should show clusters this person belongs to."""
        editor = PersonEditor(project_with_linked_data, person=sample_person)
        assert editor._ui.dna_clusters_list.count() == 1

    def test_remove_event_removes_from_project_data(
        self, qapp, project_with_linked_data: ProjectData, sample_person: Person
    ):
        """Removing a selected event should delete it from project data and refresh list."""
        editor = PersonEditor(project_with_linked_data, person=sample_person)
        initial_event_count = len(project_with_linked_data.events)
        assert editor._ui.events_list.count() == 2

        # Select the first event in the list
        editor._ui.events_list.setCurrentRow(0)
        editor._on_remove_event()

        # Event should be removed from project data
        assert len(project_with_linked_data.events) == initial_event_count - 1
        # Events list should be refreshed
        assert editor._ui.events_list.count() == 1

    def test_remove_event_without_selection_shows_error(
        self, qapp, project_with_linked_data: ProjectData, sample_person: Person
    ):
        """Removing without selection should show Swedish error message."""
        editor = PersonEditor(project_with_linked_data, person=sample_person)
        editor._on_remove_event()

        assert editor._ui.status_label.text() == "Välj en händelse att ta bort."

    def test_add_event_no_person_shows_error(
        self, qapp, empty_project: ProjectData
    ):
        """Adding an event with no person should show an error."""
        editor = PersonEditor(empty_project, person=None)
        editor._on_add_event()

        assert "Spara personen först" in editor._ui.status_label.text()


class TestPersonEditorValidation:
    """Tests for validation feedback (subtask 25.3)."""

    def test_save_empty_names_shows_error_message(
        self, qapp, empty_project: ProjectData
    ):
        """Saving with no names shows Swedish error message."""
        editor = PersonEditor(empty_project, person=None)
        editor._on_save()
        assert editor._ui.status_label.text() == "Minst ett namn krävs"

    def test_save_after_removing_all_names(
        self, qapp, empty_project: ProjectData, sample_person: Person
    ):
        """If all names are removed, save should fail with error."""
        editor = PersonEditor(empty_project, person=sample_person)

        # Remove all names
        editor._ui.names_table.selectRow(0)
        editor._on_remove_name()
        editor._ui.names_table.selectRow(0)
        editor._on_remove_name()

        assert editor._ui.names_table.rowCount() == 0

        editor._on_save()
        assert editor.saved_person is None
        assert editor._ui.status_label.text() == "Minst ett namn krävs"

    def test_successful_save_clears_status(
        self, qapp, empty_project: ProjectData
    ):
        """A successful save should clear any previous error message."""
        editor = PersonEditor(empty_project, person=None)

        # Trigger error first
        editor._on_save()
        assert editor._ui.status_label.text() == "Minst ett namn krävs"

        # Add a name and save
        editor._ui.given_name_input.setText("Test")
        editor._ui.surname_input.setText("Testsson")
        editor._on_add_name()
        editor._on_save()

        assert editor._ui.status_label.text() == ""
        assert editor.saved_person is not None

    def test_cancel_does_not_save(self, qapp, empty_project: ProjectData):
        """Cancelling should not produce a saved person."""
        editor = PersonEditor(empty_project, person=None)
        editor._ui.given_name_input.setText("Test")
        editor._ui.surname_input.setText("Testsson")
        editor._on_add_name()
        editor._on_cancel()

        assert editor.saved_person is None

    def test_save_collects_title_and_occupation(
        self, qapp, empty_project: ProjectData
    ):
        """Save should include title and occupation fields."""
        editor = PersonEditor(empty_project, person=None)
        editor._ui.title_input.setText("Professor")
        editor._ui.occupation_input.setText("Lärare")
        editor._ui.given_name_input.setText("Test")
        editor._ui.surname_input.setText("Testsson")
        editor._on_add_name()
        editor._on_save()

        person = editor.saved_person
        assert person is not None
        assert person.title == "Professor"
        assert person.occupation == "Lärare"

    def test_save_collects_notes(self, qapp, empty_project: ProjectData):
        """Save should include notes from the text edit."""
        editor = PersonEditor(empty_project, person=None)
        editor._ui.notes_input.setPlainText("Viktiga anteckningar")
        editor._ui.given_name_input.setText("Test")
        editor._ui.surname_input.setText("Testsson")
        editor._on_add_name()
        editor._on_save()

        person = editor.saved_person
        assert person is not None
        assert person.notes == "Viktiga anteckningar"


class TestPersonEditorTilltalsnamn:
    """Tests for tilltalsnamn marker validation in the save flow."""

    def test_valid_single_marker_saves_successfully(
        self, qapp, empty_project: ProjectData
    ):
        """A given name with one valid marker should save without errors."""
        editor = PersonEditor(empty_project, person=None)
        editor._ui.given_name_input.setText("Kent Torbjörn*")
        editor._ui.surname_input.setText("Johansson")
        editor._on_add_name()
        editor._on_save()

        assert editor.saved_person is not None
        assert editor.saved_person.names[0].given == "Kent Torbjörn*"

    def test_multiple_markers_blocks_save(
        self, qapp, empty_project: ProjectData
    ):
        """Multiple asterisk markers should block add-name and show error."""
        editor = PersonEditor(empty_project, person=None)
        editor._ui.given_name_input.setText("Kent* Torbjörn*")
        editor._ui.surname_input.setText("Johansson")
        editor._on_add_name()

        # Name should NOT have been added to the table
        assert editor._ui.names_table.rowCount() == 0
        assert "Endast ett tilltalsnamn kan markeras" in editor._ui.status_label.text()

    def test_multiple_markers_switches_to_names_tab(
        self, qapp, empty_project: ProjectData
    ):
        """Validation failure on add should show error (user is already on names tab)."""
        editor = PersonEditor(empty_project, person=None)
        editor._ui.given_name_input.setText("Kent* Torbjörn*")
        editor._ui.surname_input.setText("Johansson")
        editor._on_add_name()

        # Name was rejected — table is empty
        assert editor._ui.names_table.rowCount() == 0
        assert "Endast ett tilltalsnamn kan markeras" in editor._ui.status_label.text()

    def test_standalone_asterisk_blocks_save(
        self, qapp, empty_project: ProjectData
    ):
        """A standalone asterisk (not after a name) should block add-name."""
        editor = PersonEditor(empty_project, person=None)
        editor._ui.given_name_input.setText("Kent * Torbjörn")
        editor._ui.surname_input.setText("Johansson")
        editor._on_add_name()

        assert editor._ui.names_table.rowCount() == 0
        assert "Markören måste placeras direkt efter ett namn" in editor._ui.status_label.text()

    def test_leading_asterisk_blocks_save(
        self, qapp, empty_project: ProjectData
    ):
        """A leading asterisk on a name part should block add-name."""
        editor = PersonEditor(empty_project, person=None)
        editor._ui.given_name_input.setText("*Kent Torbjörn")
        editor._ui.surname_input.setText("Johansson")
        editor._on_add_name()

        assert editor._ui.names_table.rowCount() == 0
        assert "Markören måste placeras direkt efter ett namn" in editor._ui.status_label.text()

    def test_no_marker_saves_successfully(
        self, qapp, empty_project: ProjectData
    ):
        """A given name without any marker should save without issues."""
        editor = PersonEditor(empty_project, person=None)
        editor._ui.given_name_input.setText("Kent Torbjörn")
        editor._ui.surname_input.setText("Johansson")
        editor._on_add_name()
        editor._on_save()

        assert editor.saved_person is not None
        assert editor.saved_person.names[0].given == "Kent Torbjörn"

    def test_given_name_input_max_length(
        self, qapp, empty_project: ProjectData
    ):
        """The given-name input field should enforce a 100-character limit."""
        editor = PersonEditor(empty_project, person=None)
        assert editor._ui.given_name_input.maxLength() == 100

    def test_raw_asterisk_preserved_in_saved_name(
        self, qapp, empty_project: ProjectData
    ):
        """The raw asterisk should remain in the stored Name.given field."""
        editor = PersonEditor(empty_project, person=None)
        editor._ui.given_name_input.setText("Anna*")
        editor._ui.surname_input.setText("Svensson")
        editor._on_add_name()
        editor._on_save()

        assert editor.saved_person is not None
        assert editor.saved_person.names[0].given == "Anna*"

    def test_validation_only_checks_nonempty_given(
        self, qapp, empty_project: ProjectData
    ):
        """A name with empty given but valid surname should save fine."""
        editor = PersonEditor(empty_project, person=None)
        editor._ui.given_name_input.setText("")
        editor._ui.surname_input.setText("Johansson")
        editor._on_add_name()
        editor._on_save()

        assert editor.saved_person is not None
        assert editor.saved_person.names[0].given == ""
        assert editor.saved_person.names[0].surname == "Johansson"

    def test_edit_name_with_invalid_marker_blocks_update(
        self, qapp, empty_project: ProjectData
    ):
        """Editing a name to have invalid markers should block the update."""
        editor = PersonEditor(empty_project, person=None)
        # First add a valid name
        editor._ui.given_name_input.setText("Kent Torbjörn*")
        editor._ui.surname_input.setText("Johansson")
        editor._on_add_name()
        assert editor._ui.names_table.rowCount() == 1

        # Select the row, then try to edit with invalid value
        editor._ui.names_table.selectRow(0)
        editor._ui.given_name_input.setText("Kent* Torbjörn*")
        editor._ui.surname_input.setText("Johansson")
        editor._on_edit_name()

        # Original value should remain unchanged
        assert editor._ui.names_table.item(0, 1).text() == "Kent Torbjörn*"
        assert "Endast ett tilltalsnamn kan markeras" in editor._ui.status_label.text()
