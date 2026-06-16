"""Event editor widget.

Provides a form-based editor for Event records: type selection,
participants management, date/place, source references, and media links.
Validates that type and at least one participant are set before save.
All UI text is in Swedish.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem, QTableWidgetItem, QWidget

from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.generated.ui_event_editor import Ui_EventEditor

logger = logging.getLogger(__name__)

# Individual event types
INDIVIDUAL_EVENT_TYPES: list[str] = [
    "adoption",
    "baptism",
    "birth",
    "blessing",
    "burial",
    "census",
    "confirmation",
    "cremation",
    "death",
    "emigration",
    "first_communion",
    "gender_correction",
    "graduation",
    "immigration",
    "name_change",
    "retirement",
    "will",
    "custom_individual_event",
]

# Family event types
FAMILY_EVENT_TYPES: list[str] = [
    "divorce",
    "divorce_filed",
    "engagement",
    "marriage",
    "custom_family_event",
]

# All event types combined
ALL_EVENT_TYPES: list[str] = INDIVIDUAL_EVENT_TYPES + FAMILY_EVENT_TYPES

# Custom event type identifiers (require custom_type_name)
CUSTOM_EVENT_TYPES: set[str] = {"custom_individual_event", "custom_family_event"}


class EventEditor(QWidget):
    """Editor widget for Event records.

    Displays and edits an Event record with type selection, participants,
    date with precision, place reference, source references with quality
    levels, and linked media items.

    Args:
        project_data: The current project data containing all entities.
        event: Optional existing Event to edit. If None, creates a new event.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        project_data: ProjectData,
        event: Optional[Event] = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the event editor.

        Args:
            project_data: The current project data containing all entities.
            event: Optional existing Event to edit. If None, creates a new event.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._project_data = project_data
        self._event = event
        self._saved_event: Optional[Event] = None

        # Set up UI from generated form
        self._ui = Ui_EventEditor()
        self._ui.setupUi(self)

        self._setup_tables()
        self._populate_combos()
        self._connect_signals()
        self._update_type_specific_fields()

        if self._event is not None:
            self._load_event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def saved_event(self) -> Optional[Event]:
        """The saved Event result, or None if not yet saved."""
        return self._saved_event

    def get_event(self) -> Optional[Event]:
        """Return the saved event, or None if save was not performed.

        Returns:
            The Event object if save was successful, None otherwise.
        """
        return self._saved_event

    # ------------------------------------------------------------------
    # Private: setup
    # ------------------------------------------------------------------

    def _setup_tables(self) -> None:
        """Configure table appearances."""
        # Participants table
        table = self._ui.participants_table
        table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(table.EditTrigger.NoEditTriggers)

        # Sources table
        table = self._ui.sources_table
        table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(table.EditTrigger.NoEditTriggers)

    def _populate_combos(self) -> None:
        """Fill combo boxes with available options from project data."""
        # Event type combo
        self._ui.type_combo.clear()
        for event_type in ALL_EVENT_TYPES:
            self._ui.type_combo.addItem(event_type, event_type)

        # Person combo for participants
        self._ui.participant_person_combo.clear()
        self._ui.participant_person_combo.addItem("", "")
        for person in self._project_data.persons:
            display = self._get_person_display(person.id)
            self._ui.participant_person_combo.addItem(display, person.id)

        # Place combo
        self._ui.place_combo.clear()
        self._ui.place_combo.addItem("(ingen plats)", "")
        for place in self._project_data.places:
            display = f"{place.name} ({place.type})" if place.type else place.name
            self._ui.place_combo.addItem(display, place.id)

        # Source combo
        self._ui.source_combo.clear()
        self._ui.source_combo.addItem("", "")
        for source in self._project_data.sources:
            display = f"{source.id} — {source.title}" if source.title else source.id
            self._ui.source_combo.addItem(display, source.id)

        # Media combo
        self._ui.media_combo.clear()
        self._ui.media_combo.addItem("", "")
        for media_item in self._project_data.media:
            display = media_item.title or media_item.file or media_item.id
            self._ui.media_combo.addItem(display, media_item.id)

    def _connect_signals(self) -> None:
        """Wire up UI signals to handler slots."""
        # Type change
        self._ui.type_combo.currentIndexChanged.connect(
            self._update_type_specific_fields
        )

        # Participants
        self._ui.add_participant_button.clicked.connect(self._on_add_participant)
        self._ui.remove_participant_button.clicked.connect(
            self._on_remove_participant
        )

        # Sources
        self._ui.add_source_button.clicked.connect(self._on_add_source)
        self._ui.remove_source_button.clicked.connect(self._on_remove_source)

        # Media
        self._ui.add_media_button.clicked.connect(self._on_add_media)
        self._ui.remove_media_button.clicked.connect(self._on_remove_media)

        # Save/Cancel
        self._ui.save_button.clicked.connect(self._on_save)
        self._ui.cancel_button.clicked.connect(self._on_cancel)

    # ------------------------------------------------------------------
    # Private: type-specific fields visibility
    # ------------------------------------------------------------------

    def _update_type_specific_fields(self) -> None:
        """Show/hide type-specific fields based on current type selection."""
        current_type = self._ui.type_combo.currentData() or ""

        # Custom type name: visible only for custom event types
        is_custom = current_type in CUSTOM_EVENT_TYPES
        self._ui.custom_type_label.setVisible(is_custom)
        self._ui.custom_type_input.setVisible(is_custom)

        # Cause of death: visible only for death events
        is_death = current_type == "death"
        self._ui.cause_of_death_label.setVisible(is_death)
        self._ui.cause_of_death_input.setVisible(is_death)

    # ------------------------------------------------------------------
    # Private: load event data
    # ------------------------------------------------------------------

    def _load_event(self) -> None:
        """Populate all fields from the current event."""
        if self._event is None:
            return

        # Type
        type_index = self._ui.type_combo.findData(self._event.type)
        if type_index >= 0:
            self._ui.type_combo.setCurrentIndex(type_index)

        # Custom type name
        if self._event.custom_type_name:
            self._ui.custom_type_input.setText(self._event.custom_type_name)

        # Cause of death
        if self._event.cause_of_death:
            self._ui.cause_of_death_input.setText(self._event.cause_of_death)

        # Participants
        for participant in self._event.participants:
            self._add_participant_row(participant)

        # Date
        if self._event.date:
            self._ui.date_value_input.setText(self._event.date.value)
            precision_index = self._ui.date_precision_combo.findText(
                self._event.date.precision
            )
            if precision_index >= 0:
                self._ui.date_precision_combo.setCurrentIndex(precision_index)

        # Place
        if self._event.place:
            place_index = self._ui.place_combo.findData(self._event.place.place_id)
            if place_index >= 0:
                self._ui.place_combo.setCurrentIndex(place_index)

        # Source refs (on the event level)
        if self._event.date and self._event.date.source_refs:
            for source_ref in self._event.date.source_refs:
                self._add_source_row(source_ref)

        # Media
        for media_id in self._event.media_ids:
            self._add_media_item(media_id)

    # ------------------------------------------------------------------
    # Private: participants management
    # ------------------------------------------------------------------

    def _add_participant_row(self, participant: Participant) -> None:
        """Append a participant row to the table.

        Args:
            participant: The Participant to display.
        """
        table = self._ui.participants_table
        row = table.rowCount()
        table.insertRow(row)

        person_display = self._get_person_display(participant.person_id)
        person_item = QTableWidgetItem(person_display)
        person_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        person_item.setData(Qt.ItemDataRole.UserRole, participant.person_id)

        role_item = QTableWidgetItem(participant.role)
        role_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)

        table.setItem(row, 0, person_item)
        table.setItem(row, 1, role_item)

    def _on_add_participant(self) -> None:
        """Add a new participant from the edit fields."""
        person_id = self._ui.participant_person_combo.currentData()
        role = self._ui.participant_role_input.text().strip()

        if not person_id:
            self._update_status("Välj en person.")
            return

        if not role:
            self._update_status("Ange en roll för deltagaren.")
            return

        participant = Participant(person_id=person_id, role=role)
        self._add_participant_row(participant)
        self._ui.participant_person_combo.setCurrentIndex(0)
        self._ui.participant_role_input.clear()
        self._clear_status()

    def _on_remove_participant(self) -> None:
        """Remove the currently selected participant."""
        selected = self._ui.participants_table.selectedItems()
        if not selected:
            self._update_status("Välj en deltagare att ta bort.")
            return

        row = selected[0].row()
        self._ui.participants_table.removeRow(row)
        self._clear_status()

    # ------------------------------------------------------------------
    # Private: source references management
    # ------------------------------------------------------------------

    def _add_source_row(self, source_ref: SourceRef) -> None:
        """Append a source reference row to the table.

        Args:
            source_ref: The SourceRef to display.
        """
        table = self._ui.sources_table
        row = table.rowCount()
        table.insertRow(row)

        source_display = self._get_source_display(source_ref.source_id)
        source_item = QTableWidgetItem(source_display)
        source_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        source_item.setData(Qt.ItemDataRole.UserRole, source_ref.source_id)

        quality_item = QTableWidgetItem(source_ref.quality)
        quality_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)

        note_item = QTableWidgetItem(source_ref.note)
        note_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)

        table.setItem(row, 0, source_item)
        table.setItem(row, 1, quality_item)
        table.setItem(row, 2, note_item)

    def _on_add_source(self) -> None:
        """Add a new source reference from the edit fields."""
        source_id = self._ui.source_combo.currentData()
        quality = self._ui.source_quality_combo.currentText()
        note = self._ui.source_note_input.text().strip()

        if not source_id:
            self._update_status("Välj en källa.")
            return

        source_ref = SourceRef(source_id=source_id, quality=quality, note=note)
        self._add_source_row(source_ref)
        self._ui.source_combo.setCurrentIndex(0)
        self._ui.source_quality_combo.setCurrentIndex(0)
        self._ui.source_note_input.clear()
        self._clear_status()

    def _on_remove_source(self) -> None:
        """Remove the currently selected source reference."""
        selected = self._ui.sources_table.selectedItems()
        if not selected:
            self._update_status("Välj en källhänvisning att ta bort.")
            return

        row = selected[0].row()
        self._ui.sources_table.removeRow(row)
        self._clear_status()

    # ------------------------------------------------------------------
    # Private: media management
    # ------------------------------------------------------------------

    def _add_media_item(self, media_id: str) -> None:
        """Add a media item to the list.

        Args:
            media_id: The media item ID to display.
        """
        display = media_id
        for media in self._project_data.media:
            if media.id == media_id:
                display = media.title or media.file or media.id
                break

        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, media_id)
        self._ui.media_list.addItem(item)

    def _on_add_media(self) -> None:
        """Add a media link from the combo selection."""
        media_id = self._ui.media_combo.currentData()

        if not media_id:
            self._update_status("Välj ett mediaobjekt.")
            return

        # Check if already added
        for i in range(self._ui.media_list.count()):
            existing_item = self._ui.media_list.item(i)
            if existing_item and existing_item.data(Qt.ItemDataRole.UserRole) == media_id:
                self._update_status("Detta mediaobjekt är redan tillagt.")
                return

        self._add_media_item(media_id)
        self._ui.media_combo.setCurrentIndex(0)
        self._clear_status()

    def _on_remove_media(self) -> None:
        """Remove the currently selected media item."""
        current = self._ui.media_list.currentItem()
        if not current:
            self._update_status("Välj ett mediaobjekt att ta bort.")
            return

        row = self._ui.media_list.row(current)
        self._ui.media_list.takeItem(row)
        self._clear_status()

    # ------------------------------------------------------------------
    # Private: save / cancel
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        """Validate and save the event data.

        Validates that type is selected and at least one participant exists.
        For custom event types, validates that custom_type_name is provided.
        On success, stores the result in saved_event.
        """
        # Validate: type required
        event_type = self._ui.type_combo.currentData()
        if not event_type:
            self._update_status("Välj en händelsetyp.")
            return

        # Validate: at least one participant
        if self._ui.participants_table.rowCount() == 0:
            self._update_status("Minst en deltagare krävs.")
            return

        # Validate: custom type name required for custom events
        custom_type_name: Optional[str] = None
        if event_type in CUSTOM_EVENT_TYPES:
            custom_type_name = self._ui.custom_type_input.text().strip()
            if not custom_type_name:
                self._update_status("Ange ett eget typnamn för anpassad händelsetyp.")
                return

        # Cause of death (only for death events)
        cause_of_death: Optional[str] = None
        if event_type == "death":
            cause_text = self._ui.cause_of_death_input.text().strip()
            if cause_text:
                cause_of_death = cause_text

        # Collect participants
        participants: list[Participant] = []
        table = self._ui.participants_table
        for row in range(table.rowCount()):
            person_id = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            role = table.item(row, 1).text()
            participants.append(Participant(person_id=person_id, role=role))

        # Date
        date: Optional[DateValue] = None
        date_value = self._ui.date_value_input.text().strip()
        if date_value:
            precision = self._ui.date_precision_combo.currentText()
            # Collect source refs from the sources table as date source refs
            source_refs = self._collect_source_refs()
            date = DateValue(
                value=date_value, precision=precision, source_refs=source_refs
            )

        # Place
        place: Optional[PlaceRef] = None
        place_id = self._ui.place_combo.currentData()
        if place_id:
            place = PlaceRef(place_id=place_id)

        # Media IDs
        media_ids: list[str] = []
        for i in range(self._ui.media_list.count()):
            item = self._ui.media_list.item(i)
            if item:
                media_id = item.data(Qt.ItemDataRole.UserRole)
                if media_id:
                    media_ids.append(media_id)

        # Determine event ID
        event_id = self._event.id if self._event else str(uuid.uuid4())

        self._saved_event = Event(
            id=event_id,
            type=event_type,
            participants=participants,
            date=date,
            place=place,
            media_ids=media_ids,
            custom_type_name=custom_type_name,
            cause_of_death=cause_of_death,
        )

        self._clear_status()
        logger.info("Händelse sparad: %s", event_id)
        self.close()

    def _on_cancel(self) -> None:
        """Close the editor without saving."""
        self._saved_event = None
        self.close()

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    def _collect_source_refs(self) -> list[SourceRef]:
        """Collect source references from the sources table.

        Returns:
            List of SourceRef objects from the table rows.
        """
        source_refs: list[SourceRef] = []
        table = self._ui.sources_table
        for row in range(table.rowCount()):
            source_id = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            quality = table.item(row, 1).text()
            note = table.item(row, 2).text()
            source_refs.append(
                SourceRef(source_id=source_id, quality=quality, note=note)
            )
        return source_refs

    def _get_person_display(self, person_id: str) -> str:
        """Get a human-readable display string for a person.

        Args:
            person_id: The person ID to look up.

        Returns:
            A display string with the person's name or ID.
        """
        for person in self._project_data.persons:
            if person.id == person_id:
                if person.names:
                    name = person.names[0]
                    parts = []
                    if name.given:
                        parts.append(name.given)
                    if name.surname:
                        parts.append(name.surname)
                    if parts:
                        return " ".join(parts)
                return person_id
        return person_id

    def _get_source_display(self, source_id: str) -> str:
        """Get a human-readable display string for a source.

        Args:
            source_id: The source ID to look up.

        Returns:
            A display string with the source title or ID.
        """
        for source in self._project_data.sources:
            if source.id == source_id:
                if source.title:
                    return f"{source.id} — {source.title}"
                return source.id
        return source_id

    def _update_status(self, message: str) -> None:
        """Update the status label text with an error/info message.

        Args:
            message: The status message to display.
        """
        self._ui.status_label.setText(message)

    def _clear_status(self) -> None:
        """Clear the status label."""
        self._ui.status_label.setText("")
