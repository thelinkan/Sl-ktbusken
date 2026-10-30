"""Unit tests for the PersonEditor widget.

Tests person loading, name management, validation, and save logic
using a QApplication instance for widget creation.
"""

from __future__ import annotations

import pytest

from PySide6.QtWidgets import QApplication, QMessageBox

from slaktbusken.model.dna import DnaCluster, DnaMatch, DnaProfile
from slaktbusken.model.event import Event, Participant
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.editors.person_editor import PersonEditor


# ---------------------------------------------------------------------------
# Inline-editing test helpers
#
# The Namn tab edits names directly in the table: Förnamn/Efternamn are editable
# cells, the Typ column holds a Namntyp QComboBox, and "Lägg till namn" appends a
# blank row. These helpers drive that model so tests read like user actions.
# ---------------------------------------------------------------------------

_NAME_TYPE_INDEX = {"birth": 0, "married": 1, "adopted": 2, "other": 3}


def _set_row_type(editor: PersonEditor, row: int, name_type: str) -> None:
    """Set the Namntyp combo for a table row by internal type key."""
    from PySide6.QtWidgets import QComboBox

    combo = editor._ui.names_table.cellWidget(row, 0)
    assert isinstance(combo, QComboBox)
    combo.setCurrentIndex(_NAME_TYPE_INDEX[name_type])


def _set_row_text(editor: PersonEditor, row: int, given: str, surname: str) -> None:
    """Set the Förnamn/Efternamn cell text for a table row."""
    table = editor._ui.names_table
    table.item(row, 1).setText(given)
    table.item(row, 2).setText(surname)


def _add_name(
    editor: PersonEditor,
    given: str,
    surname: str,
    name_type: str = "birth",
) -> int:
    """Append a name row and populate it, mirroring the inline workflow.

    Returns the index of the newly added row.
    """
    editor._on_add_name()
    row = editor._ui.names_table.rowCount() - 1
    if name_type != "birth":
        _set_row_type(editor, row, name_type)
    _set_row_text(editor, row, given, surname)
    return row


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
        assert editor._ui.sex_combo.currentText() == "Man"
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
        """Adding a name inline and saving should produce a valid Person."""
        editor = PersonEditor(empty_project, person=None)

        # Add a name by appending a row and typing into its cells
        _add_name(editor, "Anna", "Svensson", name_type="birth")

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

    def test_add_name_appends_blank_editable_row(
        self, qapp, empty_project: ProjectData
    ):
        """"Lägg till namn" should append a blank row ready for inline editing."""
        editor = PersonEditor(empty_project, person=None)
        editor._on_add_name()

        table = editor._ui.names_table
        assert table.rowCount() == 1
        assert table.item(0, 1).text() == ""
        assert table.item(0, 2).text() == ""
        # Förnamn/Efternamn cells must be editable
        from PySide6.QtCore import Qt

        assert table.item(0, 1).flags() & Qt.ItemFlag.ItemIsEditable
        assert table.item(0, 2).flags() & Qt.ItemFlag.ItemIsEditable

    def test_save_blank_name_requires_given_or_surname(
        self, qapp, empty_project: ProjectData
    ):
        """Saving with only a blank name row should be blocked with an error."""
        editor = PersonEditor(empty_project, person=None)
        editor._on_add_name()  # one blank row, no text

        editor._on_save()

        assert editor.saved_person is None
        assert (
            editor._ui.status_label.text()
            == "Minst ett namn med förnamn eller efternamn krävs"
        )


class TestPersonEditorExistingPerson:
    """Tests for editing an existing person."""

    def test_load_person_populates_fields(
        self, qapp, empty_project: ProjectData, sample_person: Person
    ):
        """Loading an existing person should populate all fields."""
        editor = PersonEditor(empty_project, person=sample_person)

        assert editor._ui.sex_combo.currentText() == "Man"
        assert editor._ui.title_input.text() == "Fil.Dr"
        assert editor._ui.occupation_input.text() == "Lektor"
        assert editor._ui.notes_input.toPlainText() == "Test notes"
        assert editor._ui.names_table.rowCount() == 2

    def test_load_person_names_in_table(
        self, qapp, empty_project: ProjectData, sample_person: Person
    ):
        """Person names should appear in the table with type combos per row."""
        from PySide6.QtWidgets import QComboBox

        editor = PersonEditor(empty_project, person=sample_person)
        table = editor._ui.names_table

        type_combo_0 = table.cellWidget(0, 0)
        assert isinstance(type_combo_0, QComboBox)
        assert type_combo_0.currentText() == "Födelsenamn"
        assert table.item(0, 1).text() == "Erik"
        assert table.item(0, 2).text() == "Johansson"

        type_combo_1 = table.cellWidget(1, 0)
        assert isinstance(type_combo_1, QComboBox)
        assert type_combo_1.currentText() == "Gift namn"
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

    def test_edit_name_inline(
        self, qapp, empty_project: ProjectData, sample_person: Person
    ):
        """Editing cells inline should update the table and save correctly."""
        from PySide6.QtWidgets import QComboBox

        editor = PersonEditor(empty_project, person=sample_person)
        table = editor._ui.names_table

        # Edit the first row directly in its cells
        _set_row_text(editor, 0, "Karl", "Karlsson")
        _set_row_type(editor, 0, "other")

        type_combo = table.cellWidget(0, 0)
        assert isinstance(type_combo, QComboBox)
        assert type_combo.currentText() == "Annat"
        assert table.item(0, 1).text() == "Karl"
        assert table.item(0, 2).text() == "Karlsson"

        editor._on_save()
        assert editor.saved_person is not None
        assert editor.saved_person.names[0].type == "other"
        assert editor.saved_person.names[0].given == "Karl"
        assert editor.saved_person.names[0].surname == "Karlsson"


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
        """Profile photo should store the media ID when set."""
        editor = PersonEditor(project_with_linked_data, person=sample_person)
        assert editor._profile_media_id == "media_1"

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

    def test_dna_clusters_visible_when_no_profiles(
        self, qapp, empty_project: ProjectData
    ):
        """Klustermedlemskap section should be visible even when person has no DNA profiles."""
        person = Person(id="person_no_dna", sex="M", names=[Name(type="birth", given="Test", surname="Person")])
        editor = PersonEditor(empty_project, person=person)
        assert not editor._ui.dna_clusters_label.isHidden()
        assert not editor._ui.dna_clusters_list.isHidden()

    def test_dna_clusters_shows_no_clusters_message(self, qapp, sample_person: Person):
        """When person has profiles but no clusters exist, show suggestion message."""
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_profiles=[
                DnaProfile(
                    id="dnaprofile_1",
                    person_id="person_1",
                    company_id="dnacompany_1",
                    test_type="autosomal",
                    kit_name="Eriks kit",
                ),
            ],
            dna_clusters=[],
        )
        editor = PersonEditor(project, person=sample_person)
        assert editor._ui.dna_clusters_list.count() == 1
        assert "Inga kluster finns i projektet" in editor._ui.dna_clusters_list.item(0).text()
        assert "DNA-redigeraren" in editor._ui.dna_clusters_list.item(0).text()

    def test_dna_clusters_shows_company_name(self, qapp, sample_person: Person):
        """Cluster display should include associated company name."""
        from slaktbusken.model.dna import DnaCompany

        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_profiles=[
                DnaProfile(
                    id="dnaprofile_1",
                    person_id="person_1",
                    company_id="dnacompany_1",
                    test_type="autosomal",
                    kit_name="Eriks kit",
                ),
            ],
            dna_companies=[
                DnaCompany(id="dnacompany_1", name="AncestryDNA"),
            ],
            dna_clusters=[
                DnaCluster(
                    id="dnacluster_1",
                    name="Västergötland-kluster",
                    person_ids=["person_1"],
                    company_ids=["dnacompany_1"],
                ),
            ],
        )
        editor = PersonEditor(project, person=sample_person)
        assert editor._ui.dna_clusters_list.count() == 1
        item_text = editor._ui.dna_clusters_list.item(0).text()
        assert "Västergötland-kluster" in item_text
        assert "AncestryDNA" in item_text

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
        _add_name(editor, "Test", "Testsson")
        editor._on_save()

        assert editor._ui.status_label.text() == ""
        assert editor.saved_person is not None

    def test_cancel_does_not_save(self, qapp, empty_project: ProjectData):
        """Cancelling should not produce a saved person."""
        editor = PersonEditor(empty_project, person=None)
        _add_name(editor, "Test", "Testsson")
        editor._on_cancel()

        assert editor.saved_person is None

    def test_save_collects_title_and_occupation(
        self, qapp, empty_project: ProjectData
    ):
        """Save should include title and occupation fields."""
        editor = PersonEditor(empty_project, person=None)
        editor._ui.title_input.setText("Professor")
        editor._ui.occupation_input.setText("Lärare")
        _add_name(editor, "Test", "Testsson")
        editor._on_save()

        person = editor.saved_person
        assert person is not None
        assert person.title == "Professor"
        assert person.occupation == "Lärare"

    def test_save_collects_notes(self, qapp, empty_project: ProjectData):
        """Save should include notes from the text edit."""
        editor = PersonEditor(empty_project, person=None)
        editor._ui.notes_input.setPlainText("Viktiga anteckningar")
        _add_name(editor, "Test", "Testsson")
        editor._on_save()

        person = editor.saved_person
        assert person is not None
        assert person.notes == "Viktiga anteckningar"


class TestPersonEditorTilltalsnamn:
    """Tests for tilltalsnamn marker validation in the inline save flow.

    With inline editing, marker validation runs when a Förnamn cell loses focus
    (via itemChanged) and again at save time across all rows. Invalid markers
    block the save rather than blocking a separate add-name step.
    """

    def test_valid_single_marker_saves_successfully(
        self, qapp, empty_project: ProjectData
    ):
        """A given name with one valid marker should save without errors."""
        editor = PersonEditor(empty_project, person=None)
        _add_name(editor, "Kent Torbjörn*", "Johansson")
        editor._on_save()

        assert editor.saved_person is not None
        assert editor.saved_person.names[0].given == "Kent Torbjörn*"

    def test_multiple_markers_blocks_save(
        self, qapp, empty_project: ProjectData
    ):
        """Multiple asterisk markers should block save and show error."""
        editor = PersonEditor(empty_project, person=None)
        _add_name(editor, "Kent* Torbjörn*", "Johansson")
        editor._on_save()

        assert editor.saved_person is None
        assert "Endast ett tilltalsnamn kan markeras" in editor._ui.status_label.text()

    def test_marker_validation_fires_on_cell_commit(
        self, qapp, empty_project: ProjectData
    ):
        """Committing an invalid Förnamn cell should surface the error immediately."""
        editor = PersonEditor(empty_project, person=None)
        _add_name(editor, "Kent* Torbjörn*", "Johansson")

        # _set_row_text -> item.setText triggers itemChanged (focus-loss analogue)
        assert "Endast ett tilltalsnamn kan markeras" in editor._ui.status_label.text()

    def test_multiple_markers_switches_to_names_tab(
        self, qapp, empty_project: ProjectData
    ):
        """A blocked save should move focus to the names tab."""
        editor = PersonEditor(empty_project, person=None)
        _add_name(editor, "Kent* Torbjörn*", "Johansson")
        editor._ui.tab_widget.setCurrentIndex(1)
        editor._on_save()

        assert editor.saved_person is None
        assert editor._ui.tab_widget.currentWidget() == editor._ui.names_tab
        assert "Endast ett tilltalsnamn kan markeras" in editor._ui.status_label.text()

    def test_standalone_asterisk_blocks_save(
        self, qapp, empty_project: ProjectData
    ):
        """A standalone asterisk (not after a name) should block save."""
        editor = PersonEditor(empty_project, person=None)
        _add_name(editor, "Kent * Torbjörn", "Johansson")
        editor._on_save()

        assert editor.saved_person is None
        assert "Markören måste placeras direkt efter ett namn" in editor._ui.status_label.text()

    def test_leading_asterisk_blocks_save(
        self, qapp, empty_project: ProjectData
    ):
        """A leading asterisk on a name part should block save."""
        editor = PersonEditor(empty_project, person=None)
        _add_name(editor, "*Kent Torbjörn", "Johansson")
        editor._on_save()

        assert editor.saved_person is None
        assert "Markören måste placeras direkt efter ett namn" in editor._ui.status_label.text()

    def test_no_marker_saves_successfully(
        self, qapp, empty_project: ProjectData
    ):
        """A given name without any marker should save without issues."""
        editor = PersonEditor(empty_project, person=None)
        _add_name(editor, "Kent Torbjörn", "Johansson")
        editor._on_save()

        assert editor.saved_person is not None
        assert editor.saved_person.names[0].given == "Kent Torbjörn"

    def test_given_name_cell_max_length(
        self, qapp, empty_project: ProjectData
    ):
        """Förnamn values up to 100 characters should be preserved on save."""
        editor = PersonEditor(empty_project, person=None)
        long_given = "A" * 100
        _add_name(editor, long_given, "Johansson")
        editor._on_save()

        assert editor.saved_person is not None
        assert editor.saved_person.names[0].given == long_given

    def test_raw_asterisk_preserved_in_saved_name(
        self, qapp, empty_project: ProjectData
    ):
        """The raw asterisk should remain in the stored Name.given field."""
        editor = PersonEditor(empty_project, person=None)
        _add_name(editor, "Anna*", "Svensson")
        editor._on_save()

        assert editor.saved_person is not None
        assert editor.saved_person.names[0].given == "Anna*"

    def test_validation_only_checks_nonempty_given(
        self, qapp, empty_project: ProjectData
    ):
        """A name with empty given but valid surname should save fine."""
        editor = PersonEditor(empty_project, person=None)
        _add_name(editor, "", "Johansson")
        editor._on_save()

        assert editor.saved_person is not None
        assert editor.saved_person.names[0].given == ""
        assert editor.saved_person.names[0].surname == "Johansson"

    def test_edit_cell_to_invalid_marker_blocks_save(
        self, qapp, empty_project: ProjectData
    ):
        """Editing a cell to an invalid marker should block the save."""
        editor = PersonEditor(empty_project, person=None)
        # First add a valid name
        _add_name(editor, "Kent Torbjörn*", "Johansson")
        assert editor._ui.names_table.rowCount() == 1

        # Edit the cell to an invalid value, then attempt to save
        _set_row_text(editor, 0, "Kent* Torbjörn*", "Johansson")
        editor._on_save()

        assert editor.saved_person is None
        assert editor._ui.names_table.item(0, 1).text() == "Kent* Torbjörn*"
        assert "Endast ett tilltalsnamn kan markeras" in editor._ui.status_label.text()


class TestPersonEditorEditEvent:
    """Tests for the edit event functionality (Task 45.1)."""

    def test_edit_event_button_exists(
        self, qapp, project_with_linked_data: ProjectData, sample_person: Person
    ):
        """The edit event button should be present in the events tab."""
        editor = PersonEditor(project_with_linked_data, person=sample_person)
        assert editor._edit_event_button is not None
        assert editor._edit_event_button.text() == "Redigera händelse"

    def test_edit_event_without_selection_shows_error(
        self, qapp, project_with_linked_data: ProjectData, sample_person: Person
    ):
        """Clicking edit without selecting an event should show error."""
        editor = PersonEditor(project_with_linked_data, person=sample_person)
        editor._on_edit_event()

        assert editor._ui.status_label.text() == "Välj en händelse att redigera."

    def test_open_event_editor_nonexistent_event_shows_error(
        self, qapp, project_with_linked_data: ProjectData, sample_person: Person
    ):
        """Opening event editor for a non-existent event ID shows error."""
        editor = PersonEditor(project_with_linked_data, person=sample_person)
        editor._open_event_editor("nonexistent_id")

        assert editor._ui.status_label.text() == "Händelsen hittades inte."

    def test_double_click_handler_connected(
        self, qapp, project_with_linked_data: ProjectData, sample_person: Person
    ):
        """Double-click on events list should be connected to edit handler."""
        from PySide6.QtCore import SIGNAL

        editor = PersonEditor(project_with_linked_data, person=sample_person)
        # Verify double-click signal is connected by checking receivers count
        assert editor._ui.events_list.receivers(
            SIGNAL("itemDoubleClicked(QListWidgetItem*)")
        ) > 0


class TestPersonEditorClusterMembership:
    """Tests for DNA cluster membership add/remove (Task 14.2)."""

    def test_cluster_buttons_exist(
        self, qapp, project_with_linked_data: ProjectData, sample_person: Person
    ):
        """Add and remove cluster buttons should be present in the DNA tab."""
        editor = PersonEditor(project_with_linked_data, person=sample_person)
        assert editor._add_cluster_button is not None
        assert editor._remove_cluster_button is not None
        assert editor._add_cluster_button.text() == "Lägg till kluster"
        assert editor._remove_cluster_button.text() == "Ta bort"

    def test_cluster_buttons_visible_when_person_has_profiles(
        self, qapp, project_with_linked_data: ProjectData, sample_person: Person
    ):
        """Cluster buttons should be visible when person has DNA profiles."""
        editor = PersonEditor(project_with_linked_data, person=sample_person)
        assert not editor._add_cluster_button.isHidden()
        assert not editor._remove_cluster_button.isHidden()

    def test_cluster_buttons_visible_when_no_profiles(
        self, qapp, empty_project: ProjectData
    ):
        """Cluster buttons should be visible even when person has no DNA profiles."""
        person = Person(
            id="person_no_dna", sex="M",
            names=[Name(type="birth", given="Test", surname="Person")],
        )
        editor = PersonEditor(empty_project, person=person)
        assert not editor._add_cluster_button.isHidden()
        assert not editor._remove_cluster_button.isHidden()

    def test_remove_cluster_without_selection_shows_error(
        self, qapp, project_with_linked_data: ProjectData, sample_person: Person
    ):
        """Removing without selecting a cluster shows Swedish error message."""
        editor = PersonEditor(project_with_linked_data, person=sample_person)
        # Ensure nothing is selected
        editor._ui.dna_clusters_list.clearSelection()
        editor._ui.dna_clusters_list.setCurrentItem(None)
        editor._on_remove_cluster()

        assert editor._ui.status_label.text() == "Välj ett kluster att ta bort."

    def test_remove_cluster_removes_person_from_cluster(
        self, qapp, sample_person: Person
    ):
        """Removing a cluster membership should remove person_id from cluster.person_ids."""
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_profiles=[
                DnaProfile(
                    id="dnaprofile_1",
                    person_id="person_1",
                    company_id="dnacompany_1",
                    test_type="autosomal",
                    kit_name="Eriks kit",
                ),
            ],
            dna_clusters=[
                DnaCluster(
                    id="dnacluster_1",
                    name="Kluster A",
                    person_ids=["person_1", "person_3"],
                ),
                DnaCluster(
                    id="dnacluster_2",
                    name="Kluster B",
                    person_ids=["person_1"],
                ),
            ],
        )
        editor = PersonEditor(project, person=sample_person)

        # Verify initial state: person is in 2 clusters
        assert editor._ui.dna_clusters_list.count() == 2

        # Select the first cluster and remove
        editor._ui.dna_clusters_list.setCurrentRow(0)
        editor._on_remove_cluster()

        # person_1 should be removed from dnacluster_1
        cluster_1 = project.dna_clusters[0]
        assert "person_1" not in cluster_1.person_ids
        assert "person_3" in cluster_1.person_ids  # Other members remain

        # List should now show 1 cluster
        assert editor._ui.dna_clusters_list.count() == 1

    def test_add_cluster_all_clusters_already_member_shows_message(
        self, qapp, sample_person: Person
    ):
        """If person is already in all clusters, show appropriate message."""
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_profiles=[
                DnaProfile(
                    id="dnaprofile_1",
                    person_id="person_1",
                    company_id="dnacompany_1",
                    test_type="autosomal",
                ),
            ],
            dna_clusters=[
                DnaCluster(
                    id="dnacluster_1",
                    name="Kluster A",
                    person_ids=["person_1"],
                ),
            ],
        )
        editor = PersonEditor(project, person=sample_person)
        editor._on_add_cluster()

        assert "redan medlem" in editor._ui.status_label.text()

    def test_cluster_buttons_disabled_when_no_clusters_in_project(
        self, qapp, sample_person: Person
    ):
        """Buttons should be disabled when no clusters exist in project."""
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_profiles=[
                DnaProfile(
                    id="dnaprofile_1",
                    person_id="person_1",
                    company_id="dnacompany_1",
                    test_type="autosomal",
                ),
            ],
            dna_clusters=[],
        )
        editor = PersonEditor(project, person=sample_person)
        assert not editor._add_cluster_button.isEnabled()
        assert not editor._remove_cluster_button.isEnabled()

    def test_add_cluster_updates_cluster_person_ids(
        self, qapp, sample_person: Person
    ):
        """Adding a cluster membership should add person_id to cluster.person_ids.

        This test simulates the effect of _on_add_cluster by directly calling
        the internal logic (since the dialog requires user interaction).
        """
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_profiles=[
                DnaProfile(
                    id="dnaprofile_1",
                    person_id="person_1",
                    company_id="dnacompany_1",
                    test_type="autosomal",
                ),
            ],
            dna_clusters=[
                DnaCluster(
                    id="dnacluster_1",
                    name="Kluster A",
                    person_ids=["person_3"],
                ),
            ],
        )
        editor = PersonEditor(project, person=sample_person)

        # Initially person is not in the cluster
        assert "person_1" not in project.dna_clusters[0].person_ids
        assert editor._ui.dna_clusters_list.count() == 0

        # Simulate what _on_add_cluster does after dialog returns cluster IDs
        cluster = project.dna_clusters[0]
        cluster.person_ids.append(sample_person.id)
        editor._refresh_dna_clusters()

        # Verify person was added
        assert "person_1" in project.dna_clusters[0].person_ids
        assert editor._ui.dna_clusters_list.count() == 1

    def test_remove_cluster_no_person_does_nothing(
        self, qapp, empty_project: ProjectData
    ):
        """Remove cluster with no person set should do nothing."""
        editor = PersonEditor(empty_project, person=None)
        # Should not crash
        editor._on_remove_cluster()

    def test_add_cluster_no_person_does_nothing(
        self, qapp, empty_project: ProjectData
    ):
        """Add cluster with no person set should do nothing."""
        editor = PersonEditor(empty_project, person=None)
        # Should not crash
        editor._on_add_cluster()


class TestPersonEditorNameEventAssociation:
    """Tests for name-event association control (Task 10.1).

    Validates Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7.
    """

    @pytest.fixture()
    def person_with_events(self) -> tuple[Person, ProjectData]:
        """Create a person with events where they participate."""
        from slaktbusken.model.event import DateValue

        person = Person(
            id="person_1",
            sex="M",
            names=[
                Name(type="birth", given="Erik", surname="Johansson"),
                Name(type="married", given="Erik", surname="Eriksson", event_id="event_marriage"),
            ],
        )
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=[person],
            events=[
                Event(
                    id="event_marriage",
                    type="marriage",
                    participants=[
                        Participant(person_id="person_1", role="husband"),
                        Participant(person_id="person_2", role="wife"),
                    ],
                    date=DateValue(value="1920-06-15", precision="exact"),
                ),
                Event(
                    id="event_name_change",
                    type="name_change",
                    participants=[
                        Participant(person_id="person_1", role="subject"),
                    ],
                ),
            ],
        )
        return person, project

    def test_names_table_has_event_column(self, qapp, empty_project: ProjectData):
        """Names table should have 4 columns including event association."""
        editor = PersonEditor(empty_project, person=None)
        table = editor._ui.names_table
        assert table.columnCount() == 4
        assert table.horizontalHeaderItem(3).text() == "Händelse"

    def test_birth_name_has_no_event_combo(self, qapp, person_with_events):
        """Birth name rows should not have an event association combo."""
        from PySide6.QtWidgets import QComboBox

        person, project = person_with_events
        editor = PersonEditor(project, person=person)
        table = editor._ui.names_table

        # Row 0 is birth type - should have no combo widget
        widget = table.cellWidget(0, 3)
        assert widget is None or not isinstance(widget, QComboBox)

    def test_non_birth_name_has_event_combo(self, qapp, person_with_events):
        """Non-birth name rows should have an event association combo."""
        from PySide6.QtWidgets import QComboBox

        person, project = person_with_events
        editor = PersonEditor(project, person=person)
        table = editor._ui.names_table

        # Row 1 is married type - should have a combo widget
        widget = table.cellWidget(1, 3)
        assert isinstance(widget, QComboBox)

    def test_event_combo_populated_with_participant_events(self, qapp, person_with_events):
        """Event combo should contain events where person is participant."""
        from PySide6.QtWidgets import QComboBox

        person, project = person_with_events
        editor = PersonEditor(project, person=person)
        table = editor._ui.names_table

        combo = table.cellWidget(1, 3)
        assert isinstance(combo, QComboBox)

        # Should have: blank + 2 events = 3 items
        assert combo.count() == 3

    def test_event_combo_displays_type_and_date(self, qapp, person_with_events):
        """Event combo items should show event type and date."""
        from PySide6.QtWidgets import QComboBox

        person, project = person_with_events
        editor = PersonEditor(project, person=person)
        table = editor._ui.names_table

        combo = table.cellWidget(1, 3)
        assert isinstance(combo, QComboBox)

        # Find the marriage event item (should include date)
        found_marriage = False
        for i in range(combo.count()):
            text = combo.itemText(i)
            if "1920-06-15" in text:
                found_marriage = True
                break
        assert found_marriage, "Event combo should display the date for events with dates"

    def test_event_combo_selects_existing_event_id(self, qapp, person_with_events):
        """When a name has event_id set, the combo should select that event."""
        from PySide6.QtWidgets import QComboBox

        person, project = person_with_events
        editor = PersonEditor(project, person=person)
        table = editor._ui.names_table

        combo = table.cellWidget(1, 3)
        assert isinstance(combo, QComboBox)

        # The married name has event_id="event_marriage", combo should select it
        assert combo.currentData() == "event_marriage"

    def test_save_captures_event_id_from_combo(self, qapp, person_with_events):
        """Saving should store the selected event_id on the Name record."""
        from PySide6.QtWidgets import QComboBox

        person, project = person_with_events
        editor = PersonEditor(project, person=person)
        editor._on_save()

        saved = editor.saved_person
        assert saved is not None
        assert saved.names[1].event_id == "event_marriage"

    def test_save_clears_event_id_when_blank_selected(self, qapp, person_with_events):
        """Clearing the combo selection should set event_id to None on save."""
        from PySide6.QtWidgets import QComboBox

        person, project = person_with_events
        editor = PersonEditor(project, person=person)
        table = editor._ui.names_table

        combo = table.cellWidget(1, 3)
        assert isinstance(combo, QComboBox)

        # Select the blank item (index 0 = "– Välj händelse –")
        combo.setCurrentIndex(0)

        editor._on_save()
        saved = editor.saved_person
        assert saved is not None
        assert saved.names[1].event_id is None

    def test_orphaned_event_id_shows_warning(self, qapp):
        """When event_id references a non-existent event, show warning item."""
        from PySide6.QtWidgets import QComboBox

        person = Person(
            id="person_1",
            sex="M",
            names=[
                Name(type="birth", given="Erik", surname="Johansson"),
                Name(type="married", given="Erik", surname="Eriksson", event_id="deleted_event"),
            ],
        )
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=[person],
            events=[
                Event(
                    id="event_1",
                    type="marriage",
                    participants=[Participant(person_id="person_1", role="husband")],
                ),
            ],
        )
        editor = PersonEditor(project, person=person)
        table = editor._ui.names_table

        combo = table.cellWidget(1, 3)
        assert isinstance(combo, QComboBox)

        # Should show warning item and select it
        current_text = combo.currentText()
        assert "saknas" in current_text or "⚠" in current_text

    def test_no_events_disables_combo(self, qapp):
        """When no events exist for person, the combo should be disabled."""
        from PySide6.QtWidgets import QComboBox

        person = Person(
            id="person_1",
            sex="M",
            names=[
                Name(type="birth", given="Erik", surname="Johansson"),
                Name(type="married", given="Erik", surname="Eriksson"),
            ],
        )
        # Project with no events where person_1 participates
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=[person],
            events=[],
        )
        editor = PersonEditor(project, person=person)
        table = editor._ui.names_table

        combo = table.cellWidget(1, 3)
        assert isinstance(combo, QComboBox)
        assert not combo.isEnabled()

    def test_birth_name_event_id_not_saved(self, qapp):
        """Birth names should have None event_id regardless of any combo state."""
        person = Person(
            id="person_1",
            sex="M",
            names=[
                Name(type="birth", given="Erik", surname="Johansson"),
            ],
        )
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=[person],
            events=[
                Event(
                    id="event_1",
                    type="birth",
                    participants=[Participant(person_id="person_1", role="child")],
                ),
            ],
        )
        editor = PersonEditor(project, person=person)
        editor._on_save()

        saved = editor.saved_person
        assert saved is not None
        assert saved.names[0].event_id is None

    def test_add_non_birth_name_gets_event_combo(self, qapp):
        """Adding a non-birth name should create an event combo for the new row."""
        from PySide6.QtWidgets import QComboBox

        person = Person(
            id="person_1",
            sex="M",
            names=[Name(type="birth", given="Erik", surname="Johansson")],
        )
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=[person],
            events=[
                Event(
                    id="event_1",
                    type="marriage",
                    participants=[Participant(person_id="person_1", role="husband")],
                ),
            ],
        )
        editor = PersonEditor(project, person=person)

        # Add a married name inline; setting the Typ combo to "Gift namn" builds
        # the Händelse association control for the row.
        row = _add_name(editor, "Erik", "Larsson", name_type="married")

        table = editor._ui.names_table
        assert table.rowCount() == 2

        # New row should have an enabled event combo in the Händelse column
        combo = table.cellWidget(row, 3)
        assert isinstance(combo, QComboBox)
        assert combo.isEnabled()


class TestPersonEditorFosterAdoptiveReadOnly:
    """Tests for read-only event-derived foster/adoptive parent links.

    Covers Requirements 2.6 (read-only derived rows, disabled retype/remove,
    defensive guards) and 2.7 (declining a direct foster/adoptive add in favour
    of creating a placement event).
    """

    @staticmethod
    def _child_with_parents() -> tuple[Person, ProjectData]:
        """Build a project with a child having a biological and a foster parent."""
        from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink

        child = Person(id="child_1", sex="M", names=[Name(type="birth", given="Kalle", surname="Ek")])
        bio = Person(id="bio_1", sex="M", names=[Name(type="birth", given="Bo", surname="Ek")])
        foster = Person(id="foster_1", sex="F", names=[Name(type="birth", given="Fia", surname="Dahl")])
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=[child, bio, foster],
            families=[
                Family(
                    id="family_bio",
                    partners=[FamilyPartner(person_id="bio_1", role="father")],
                    children=["child_1"],
                    parent_child_links=[
                        ParentChildLink(
                            child_id="child_1", parent_id="bio_1", parentage_type="biological"
                        )
                    ],
                ),
                Family(
                    id="family_foster",
                    partners=[FamilyPartner(person_id="foster_1", role="mother")],
                    children=["child_1"],
                    parent_child_links=[
                        ParentChildLink(
                            child_id="child_1", parent_id="foster_1", parentage_type="foster"
                        )
                    ],
                ),
            ],
        )
        return child, project

    def _find_row_by_parentage(self, editor: PersonEditor, parentage_type: str) -> int:
        """Return the parents-table row index whose link is of the given type."""
        from PySide6.QtCore import Qt

        table = editor._parents_table
        for row in range(table.rowCount()):
            if table.item(row, 1).data(Qt.ItemDataRole.UserRole) == parentage_type:
                return row
        raise AssertionError(f"No row with parentage_type={parentage_type}")

    def test_foster_row_shows_via_handelse_label(self, qapp):
        """A foster link row shows the '(via händelse)' read-only label."""
        child, project = self._child_with_parents()
        editor = PersonEditor(project, person=child)

        row = self._find_row_by_parentage(editor, "foster")
        assert editor._parents_table.item(row, 1).text() == "fosterförälder (via händelse)"

    def test_biological_row_has_plain_label(self, qapp):
        """A biological link row keeps its plain label without the suffix."""
        child, project = self._child_with_parents()
        editor = PersonEditor(project, person=child)

        row = self._find_row_by_parentage(editor, "biological")
        assert editor._parents_table.item(row, 1).text() == "biologisk"

    def test_selecting_foster_row_disables_edit_and_remove(self, qapp):
        """Selecting a foster row disables 'Ändra typ' and 'Ta bort'."""
        child, project = self._child_with_parents()
        editor = PersonEditor(project, person=child)

        row = self._find_row_by_parentage(editor, "foster")
        editor._parents_table.selectRow(row)

        assert editor._edit_parent_button.isEnabled() is False
        assert editor._remove_parent_button.isEnabled() is False

    def test_selecting_biological_row_enables_edit_and_remove(self, qapp):
        """Selecting a biological row enables 'Ändra typ' and 'Ta bort'."""
        child, project = self._child_with_parents()
        editor = PersonEditor(project, person=child)

        row = self._find_row_by_parentage(editor, "biological")
        editor._parents_table.selectRow(row)

        assert editor._edit_parent_button.isEnabled() is True
        assert editor._remove_parent_button.isEnabled() is True

    def test_edit_parent_refuses_on_derived_row(self, qapp):
        """The retype handler refuses on a foster row and leaves data unchanged."""
        child, project = self._child_with_parents()
        editor = PersonEditor(project, person=child)

        row = self._find_row_by_parentage(editor, "foster")
        editor._parents_table.selectRow(row)
        editor._on_edit_parent()

        # Link type is unchanged and a directing message is shown.
        service = editor._parent_service
        types = {p.parentage_type for p in service.get_parents_for_person("child_1")}
        assert "foster" in types
        assert "Händelser" in editor._ui.status_label.text()

    def test_remove_parent_refuses_on_derived_row(self, qapp):
        """The remove handler refuses on a foster row and leaves data unchanged."""
        child, project = self._child_with_parents()
        editor = PersonEditor(project, person=child)

        row = self._find_row_by_parentage(editor, "foster")
        editor._parents_table.selectRow(row)
        editor._on_remove_parent()

        service = editor._parent_service
        parents = service.get_parents_for_person("child_1")
        assert any(p.parentage_type == "foster" for p in parents)
        assert "Händelser" in editor._ui.status_label.text()

    def test_add_foster_declines_direct_and_offers_event(self, qapp, monkeypatch):
        """Choosing a foster type in the add flow declines the direct add.

        It must NOT call ParentService.add_parent for foster, and must route to
        the placement-event creation flow instead (Requirement 2.7).
        """
        child, project = self._child_with_parents()
        editor = PersonEditor(project, person=child)

        # Guard: add_parent must never be called for a foster/adoptive type.
        called = {"add": False, "placement": None}
        orig_add = editor._parent_service.add_parent

        def _spy_add(**kwargs):
            called["add"] = True
            return orig_add(**kwargs)

        monkeypatch.setattr(editor._parent_service, "add_parent", _spy_add)
        monkeypatch.setattr(
            editor,
            "_open_placement_event_editor",
            lambda event_type, parent_id=None: called.__setitem__(
                "placement", (event_type, parent_id)
            ),
        )
        # Auto-confirm the QMessageBox offer.
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *a, **k: QMessageBox.StandardButton.Yes,
        )

        # Select the foster parent and the 'fosterförälder' type, then add.
        idx = editor._parent_person_combo.findData("foster_1")
        editor._parent_person_combo.setCurrentIndex(idx)
        type_idx = editor._parent_type_combo.findText("fosterförälder")
        editor._parent_type_combo.setCurrentIndex(type_idx)
        editor._on_add_parent()

        assert called["add"] is False
        assert called["placement"] == ("foster_home", "foster_1")

    def test_add_foster_declined_when_user_cancels_offer(self, qapp, monkeypatch):
        """Declining the offer adds no link and shows a directing message."""
        child, project = self._child_with_parents()
        editor = PersonEditor(project, person=child)

        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *a, **k: QMessageBox.StandardButton.No,
        )
        before = len(editor._parent_service.get_parents_for_person("child_1"))

        idx = editor._parent_person_combo.findData("foster_1")
        editor._parent_person_combo.setCurrentIndex(idx)
        type_idx = editor._parent_type_combo.findText("fosterförälder")
        editor._parent_type_combo.setCurrentIndex(type_idx)
        editor._on_add_parent()

        after = len(editor._parent_service.get_parents_for_person("child_1"))
        assert after == before
        assert "Händelser" in editor._ui.status_label.text()

    def test_add_biological_still_works(self, qapp):
        """A biological add is unaffected and creates the link directly."""
        child, project = self._child_with_parents()
        new_parent = Person(
            id="bio_2", sex="F", names=[Name(type="birth", given="Berit", surname="Ek")]
        )
        project.persons.append(new_parent)
        editor = PersonEditor(project, person=child)

        idx = editor._parent_person_combo.findData("bio_2")
        editor._parent_person_combo.setCurrentIndex(idx)
        type_idx = editor._parent_type_combo.findText("biologisk")
        editor._parent_type_combo.setCurrentIndex(type_idx)
        editor._on_add_parent()

        parents = editor._parent_service.get_parents_for_person("child_1")
        assert any(p.parent_id == "bio_2" and p.parentage_type == "biological" for p in parents)

    def test_placement_event_flow_derives_foster_link_immediately(
        self, qapp, monkeypatch
    ):
        """Creating a foster placement event derives its link without a reload.

        End-to-end test chosen: rather than exercising only the three-line
        committed sequence, this drives ``_open_placement_event_editor`` through
        a simulated modal dialog. ``QDialog.exec`` is monkeypatched to locate the
        inner EventEditor, invoke its real ``_on_save()`` (which populates
        ``saved_event`` from the pre-added child subject + parent participant
        rows) and return Accepted. This proves that the method's post-append call
        to ``sync_parentage_links`` reconciles the derived ParentChildLink before
        the parents table refreshes (Requirement 2.3).
        """
        from PySide6.QtWidgets import QDialog
        from slaktbusken.ui.editors.event_editor import EventEditor

        # Start from a clean project: one child, one prospective foster parent,
        # no pre-existing families/links so the derived link must come from the
        # new event's sync run.
        child = Person(
            id="child_1", sex="M", names=[Name(type="birth", given="Kalle", surname="Ek")]
        )
        foster = Person(
            id="foster_1", sex="F", names=[Name(type="birth", given="Fia", surname="Dahl")]
        )
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=[child, foster],
        )
        editor = PersonEditor(project, person=child)

        def _fake_exec(dialog_self):
            # Find the EventEditor embedded in the placement dialog and run its
            # real save path with the participants the method pre-added.
            inner = dialog_self.findChild(EventEditor)
            assert inner is not None, "EventEditor not found in placement dialog"
            inner._on_save()
            return QDialog.DialogCode.Accepted

        monkeypatch.setattr(QDialog, "exec", _fake_exec)

        editor._open_placement_event_editor("foster_home", parent_id="foster_1")

        # A foster_home event was created and committed to the project.
        assert any(e.type == "foster_home" for e in project.events)

        # The derived read-only foster link now exists from foster_1 to child_1,
        # proving sync_parentage_links ran inside the method after the append.
        links = [
            link
            for family in project.families
            for link in family.parent_child_links
            if link.child_id == "child_1"
            and link.parent_id == "foster_1"
            and link.parentage_type == "foster"
        ]
        assert links, "Expected a derived foster ParentChildLink after placement event"
