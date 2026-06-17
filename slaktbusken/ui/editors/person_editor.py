"""Person editor widget.

Provides a tabbed editor for Person records: Names, Events, Photos,
and DNA & Clusters. Validates that at least one name entry exists
before save. All UI text is in Swedish.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QListWidgetItem, QTableWidgetItem, QWidget

from slaktbusken.model.name_parser import validate_given_name_markers
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.generated.ui_person_editor import Ui_PersonEditor

logger = logging.getLogger(__name__)


class PersonEditor(QWidget):
    """Editor widget for Person records with tabs for names, events, photos, and DNA.

    Displays and edits a Person record with associated names, sex, profile photo,
    notes, linked events, linked media, and DNA information (profiles, matches,
    cluster memberships).

    Signals:
        save_requested: Emitted when the user saves successfully.
        cancel_requested: Emitted when the user cancels editing.

    Args:
        project_data: The current project data containing all entities.
        person: Optional existing Person to edit. If None, creates a new person.
        parent: Optional parent widget.
    """

    save_requested = Signal()
    cancel_requested = Signal()

    def __init__(
        self,
        project_data: ProjectData,
        person: Optional[Person] = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the person editor.

        Args:
            project_data: The current project data containing all entities.
            person: Optional existing Person to edit. If None, creates a new person.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._project_data = project_data
        self._person = person
        self._saved_person: Optional[Person] = None
        self._editing_name_row: Optional[int] = None

        # Set up UI from generated form
        self._ui = Ui_PersonEditor()
        self._ui.setupUi(self)

        self._setup_table()
        self._connect_signals()

        if self._person is not None:
            self._load_person()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def saved_person(self) -> Optional[Person]:
        """The saved Person result, or None if not yet saved."""
        return self._saved_person

    def get_person(self) -> Optional[Person]:
        """Return the saved person, or None if save was not performed.

        Returns:
            The Person object if save was successful, None otherwise.
        """
        return self._saved_person

    # ------------------------------------------------------------------
    # Private: setup
    # ------------------------------------------------------------------

    def _setup_table(self) -> None:
        """Configure the names table appearance."""
        table = self._ui.names_table
        table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(table.EditTrigger.NoEditTriggers)

        # Enforce maximum 100 characters for given-name input
        self._ui.given_name_input.setMaxLength(100)

    def _connect_signals(self) -> None:
        """Wire up UI signals to handler slots."""
        # Name management
        self._ui.add_name_button.clicked.connect(self._on_add_name)
        self._ui.edit_name_button.clicked.connect(self._on_edit_name)
        self._ui.remove_name_button.clicked.connect(self._on_remove_name)
        self._ui.names_table.itemSelectionChanged.connect(
            self._on_name_selection_changed
        )

        # Events
        self._ui.add_event_button.clicked.connect(self._on_add_event)
        self._ui.remove_event_button.clicked.connect(self._on_remove_event)

        # Photos
        self._ui.select_profile_button.clicked.connect(self._on_select_profile)

        # Save/Cancel
        self._ui.save_button.clicked.connect(self._on_save)
        self._ui.cancel_button.clicked.connect(self._on_cancel)

    # ------------------------------------------------------------------
    # Private: load person data
    # ------------------------------------------------------------------

    def _load_person(self) -> None:
        """Populate all fields from the current person."""
        if self._person is None:
            return

        # Sex
        sex_index = self._ui.sex_combo.findText(self._person.sex)
        if sex_index >= 0:
            self._ui.sex_combo.setCurrentIndex(sex_index)

        # Title and occupation
        if self._person.title:
            self._ui.title_input.setText(self._person.title)
        if self._person.occupation:
            self._ui.occupation_input.setText(self._person.occupation)

        # Notes
        if self._person.notes:
            self._ui.notes_input.setPlainText(self._person.notes)

        # Names
        self._refresh_names_table()

        # Events
        self._refresh_events_list()

        # Photos / media
        self._refresh_media_list()

        # DNA
        self._refresh_dna_profiles()
        self._refresh_dna_matches()
        self._refresh_dna_clusters()

    # ------------------------------------------------------------------
    # Private: names management
    # ------------------------------------------------------------------

    def _refresh_names_table(self) -> None:
        """Rebuild the names table from the current person's names."""
        table = self._ui.names_table
        table.setRowCount(0)

        if self._person is None:
            return

        for name in self._person.names:
            self._add_name_row(name)

    def _add_name_row(self, name: Name) -> None:
        """Append a single name row to the table.

        Args:
            name: The Name entry to display.
        """
        table = self._ui.names_table
        row = table.rowCount()
        table.insertRow(row)

        type_item = QTableWidgetItem(name.type)
        type_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)

        given_item = QTableWidgetItem(name.given)
        given_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)

        surname_item = QTableWidgetItem(name.surname)
        surname_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)

        table.setItem(row, 0, type_item)
        table.setItem(row, 1, given_item)
        table.setItem(row, 2, surname_item)

    def _on_add_name(self) -> None:
        """Add a new name entry from the edit fields."""
        name_type = self._ui.name_type_combo.currentText()
        given = self._ui.given_name_input.text().strip()
        surname = self._ui.surname_input.text().strip()

        if not given and not surname:
            self._update_status("Ange förnamn eller efternamn.")
            return

        # Validate tilltalsnamn markers before adding
        if given:
            errors = validate_given_name_markers(given)
            if errors:
                self._update_status(errors[0])
                return

        name = Name(type=name_type, given=given, surname=surname)
        self._add_name_row(name)
        self._clear_name_fields()
        self._clear_status()

    def _on_edit_name(self) -> None:
        """Update the selected name entry with current field values."""
        selected = self._ui.names_table.selectedItems()
        if not selected:
            self._update_status("Välj ett namn att redigera.")
            return

        row = selected[0].row()
        name_type = self._ui.name_type_combo.currentText()
        given = self._ui.given_name_input.text().strip()
        surname = self._ui.surname_input.text().strip()

        if not given and not surname:
            self._update_status("Ange förnamn eller efternamn.")
            return

        # Validate tilltalsnamn markers before updating
        if given:
            errors = validate_given_name_markers(given)
            if errors:
                self._update_status(errors[0])
                return

        table = self._ui.names_table
        table.item(row, 0).setText(name_type)
        table.item(row, 1).setText(given)
        table.item(row, 2).setText(surname)
        self._clear_name_fields()
        self._clear_status()

    def _on_remove_name(self) -> None:
        """Remove the currently selected name entry."""
        selected = self._ui.names_table.selectedItems()
        if not selected:
            self._update_status("Välj ett namn att ta bort.")
            return

        row = selected[0].row()
        self._ui.names_table.removeRow(row)
        self._clear_status()

    def _on_name_selection_changed(self) -> None:
        """Populate edit fields when a name row is selected."""
        selected = self._ui.names_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        table = self._ui.names_table

        name_type = table.item(row, 0).text()
        given = table.item(row, 1).text()
        surname = table.item(row, 2).text()

        # Set type combo
        type_index = self._ui.name_type_combo.findText(name_type)
        if type_index >= 0:
            self._ui.name_type_combo.setCurrentIndex(type_index)

        self._ui.given_name_input.setText(given)
        self._ui.surname_input.setText(surname)

    # ------------------------------------------------------------------
    # Private: events
    # ------------------------------------------------------------------

    def _refresh_events_list(self) -> None:
        """Populate the events list with events linked to this person."""
        self._ui.events_list.clear()

        if self._person is None:
            return

        for event in self._project_data.events:
            for participant in event.participants:
                if participant.person_id == self._person.id:
                    display = f"{event.type} ({participant.role})"
                    if event.date:
                        display += f" — {event.date.value}"
                    item = QListWidgetItem(display)
                    item.setData(Qt.ItemDataRole.UserRole, event.id)
                    self._ui.events_list.addItem(item)
                    break

    def _on_add_event(self) -> None:
        """Placeholder for adding an event link.

        Full event selection dialog to be implemented in a later task.
        """
        self._update_status("Händelselänkning implementeras i ett kommande steg.")

    def _on_remove_event(self) -> None:
        """Placeholder for removing an event link.

        Full event unlinking to be implemented in a later task.
        """
        current = self._ui.events_list.currentItem()
        if not current:
            self._update_status("Välj en händelse att ta bort.")
            return
        self._update_status("Händelseborttagning implementeras i ett kommande steg.")

    # ------------------------------------------------------------------
    # Private: photos / media
    # ------------------------------------------------------------------

    def _refresh_media_list(self) -> None:
        """Populate the media list with photo media linked to this person."""
        self._ui.media_list.clear()

        if self._person is None:
            return

        for media_item in self._project_data.media:
            # Show media linked to this person
            is_linked = any(
                le.entity_type == "person" and le.entity_id == self._person.id
                for le in media_item.linked_entities
            )
            if is_linked and media_item.type == "photo":
                display = media_item.title or media_item.file
                item = QListWidgetItem(display)
                item.setData(Qt.ItemDataRole.UserRole, media_item.id)
                self._ui.media_list.addItem(item)

        # Show profile photo indicator
        if self._person.profile_media_id:
            self._ui.profile_photo_display.setText(
                f"ID: {self._person.profile_media_id}"
            )
        else:
            self._ui.profile_photo_display.setText("Ingen bild")

    def _on_select_profile(self) -> None:
        """Set the selected media item as the profile photo."""
        current = self._ui.media_list.currentItem()
        if not current:
            self._update_status("Välj ett foto från listan.")
            return

        media_id = current.data(Qt.ItemDataRole.UserRole)
        self._ui.profile_photo_display.setText(f"ID: {media_id}")
        self._clear_status()

    # ------------------------------------------------------------------
    # Private: DNA
    # ------------------------------------------------------------------

    def _refresh_dna_profiles(self) -> None:
        """Populate the DNA profiles list for this person."""
        self._ui.dna_profiles_list.clear()

        if self._person is None:
            return

        for profile in self._project_data.dna_profiles:
            if profile.person_id == self._person.id:
                display = f"{profile.kit_name or profile.id} ({profile.test_type})"
                item = QListWidgetItem(display)
                item.setData(Qt.ItemDataRole.UserRole, profile.id)
                self._ui.dna_profiles_list.addItem(item)

    def _refresh_dna_matches(self) -> None:
        """Populate the DNA matches list for this person's profiles."""
        self._ui.dna_matches_list.clear()

        if self._person is None:
            return

        # Get profile IDs for this person
        person_profile_ids = {
            p.id
            for p in self._project_data.dna_profiles
            if p.person_id == self._person.id
        }

        for match in self._project_data.dna_matches:
            if match.profile1_id in person_profile_ids or match.profile2_id in person_profile_ids:
                display = f"Match {match.id}: {match.shared_cm} cM ({match.segment_count} segment)"
                item = QListWidgetItem(display)
                item.setData(Qt.ItemDataRole.UserRole, match.id)
                self._ui.dna_matches_list.addItem(item)

    def _refresh_dna_clusters(self) -> None:
        """Populate the DNA clusters list for this person."""
        self._ui.dna_clusters_list.clear()

        if self._person is None:
            return

        for cluster in self._project_data.dna_clusters:
            if self._person.id in cluster.person_ids:
                display = cluster.name or cluster.id
                item = QListWidgetItem(display)
                item.setData(Qt.ItemDataRole.UserRole, cluster.id)
                self._ui.dna_clusters_list.addItem(item)

    # ------------------------------------------------------------------
    # Private: save / cancel
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        """Validate and save the person data.

        Validates that at least one name entry exists and sex is set.
        On success, stores the result in saved_person.
        """
        # Validate: at least one name required
        if self._ui.names_table.rowCount() == 0:
            self._update_status("Minst ett namn krävs")
            self._ui.tab_widget.setCurrentWidget(self._ui.names_tab)
            return

        # Collect names from table
        names: list[Name] = []
        table = self._ui.names_table
        for row in range(table.rowCount()):
            name_type = table.item(row, 0).text()
            given = table.item(row, 1).text()
            surname = table.item(row, 2).text()
            names.append(Name(type=name_type, given=given, surname=surname))

        # Sex
        sex = self._ui.sex_combo.currentText()

        # Title and occupation
        title = self._ui.title_input.text().strip() or None
        occupation = self._ui.occupation_input.text().strip() or None

        # Notes
        notes = self._ui.notes_input.toPlainText()

        # Profile media ID
        profile_display = self._ui.profile_photo_display.text()
        profile_media_id: Optional[str] = None
        if profile_display.startswith("ID: "):
            profile_media_id = profile_display[4:]
        elif self._person and self._person.profile_media_id:
            profile_media_id = self._person.profile_media_id

        # Determine person ID
        person_id = self._person.id if self._person else str(uuid.uuid4())

        self._saved_person = Person(
            id=person_id,
            sex=sex,
            names=names,
            profile_media_id=profile_media_id,
            notes=notes,
            title=title,
            occupation=occupation,
        )

        self._clear_status()
        logger.info("Person sparad: %s", person_id)
        self.save_requested.emit()

    def _on_cancel(self) -> None:
        """Close the editor without saving."""
        self._saved_person = None
        self.cancel_requested.emit()

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    def _clear_name_fields(self) -> None:
        """Reset the name edit input fields to empty state."""
        self._ui.name_type_combo.setCurrentIndex(0)
        self._ui.given_name_input.clear()
        self._ui.surname_input.clear()

    def _update_status(self, message: str) -> None:
        """Update the status label text with an error/info message.

        Args:
            message: The status message to display.
        """
        self._ui.status_label.setText(message)

    def _clear_status(self) -> None:
        """Clear the status label."""
        self._ui.status_label.setText("")
