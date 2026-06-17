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

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCompleter,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.model.project import ProjectData
from slaktbusken.model.source import Source
from slaktbusken.ui.generated.ui_event_editor import Ui_EventEditor
from slaktbusken.ui.swedish_locale import get_event_type_label, SOURCE_QUALITY_LABELS, DATE_PRECISION_LABELS

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

# Default participant role per event type
EVENT_TYPE_ROLES: dict[str, str] = {
    "adoption": "adopterad",
    "baptism": "döpt",
    "birth": "född",
    "blessing": "välsignad",
    "burial": "begravd",
    "census": "folkbokförd",
    "confirmation": "konfirmand",
    "cremation": "kremerad",
    "death": "avliden",
    "emigration": "emigrant",
    "first_communion": "kommunikant",
    "gender_correction": "huvudperson",
    "graduation": "examinerad",
    "immigration": "immigrant",
    "name_change": "huvudperson",
    "retirement": "pensionär",
    "will": "testator",
    "custom_individual_event": "huvudperson",
    "divorce": "make/maka",
    "divorce_filed": "make/maka",
    "engagement": "förlovad",
    "marriage": "make/maka",
    "custom_family_event": "deltagare",
}


class EventEditor(QWidget):
    """Editor widget for Event records.

    Displays and edits an Event record with type selection, participants,
    date with precision, place reference, source references with quality
    levels, and linked media items.

    When opened with a subject_person_id, individual events automatically
    include that person as the sole participant. For family events (marriage,
    divorce, etc.), a second participant can be added.

    Signals:
        save_requested: Emitted when the user saves successfully.
        cancel_requested: Emitted when the user cancels editing.

    Args:
        project_data: The current project data containing all entities.
        event: Optional existing Event to edit. If None, creates a new event.
        subject_person_id: Optional person ID to auto-add as participant.
        parent: Optional parent widget.
    """

    save_requested = Signal()
    cancel_requested = Signal()

    def __init__(
        self,
        project_data: ProjectData,
        event: Optional[Event] = None,
        subject_person_id: Optional[str] = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the event editor.

        Args:
            project_data: The current project data containing all entities.
            event: Optional existing Event to edit. If None, creates a new event.
            subject_person_id: Optional person ID to auto-add as participant.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._project_data = project_data
        self._event = event
        self._subject_person_id = subject_person_id
        self._saved_event: Optional[Event] = None

        # Set up UI inside a scroll area so content is accessible even in
        # smaller windows (edit mode shows all sections simultaneously).
        from PySide6.QtWidgets import QScrollArea

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        inner_widget = QWidget()
        self._ui = Ui_EventEditor()
        self._ui.setupUi(inner_widget)
        scroll_area.setWidget(inner_widget)

        outer_layout.addWidget(scroll_area)

        self._setup_tables()
        self._populate_combos()
        self._setup_reference_paste()
        self._setup_new_place_button()
        self._connect_signals()
        self._update_type_specific_fields()

        if self._event is not None:
            self._load_event()
        elif self._subject_person_id:
            # Pre-add the subject as a participant for new events
            self._add_participant_row(
                Participant(person_id=self._subject_person_id, role="huvudperson")
            )
            self._update_participants_visibility()

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
        """Configure table appearances and sizing."""
        # Participants table
        table = self._ui.participants_table
        table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(table.EditTrigger.NoEditTriggers)
        table.setMaximumHeight(100)

        # Sources table — give it more room so entries are readable
        table = self._ui.sources_table
        table.horizontalHeader().setStretchLastSection(True)
        table.setEditTriggers(table.EditTrigger.NoEditTriggers)
        table.setMinimumHeight(80)
        # Set column widths: Källa gets more space, Kvalitet and Anteckning narrower
        header = table.horizontalHeader()
        header.resizeSection(0, 300)
        header.resizeSection(1, 80)

    def _setup_reference_paste(self) -> None:
        """Add a paste-reference row below the source combo for matching by reference text.

        Inserts a layout with a label, text input, and a lookup button into
        the sources group, between the source selection row and the note row.
        """
        # Create the reference paste layout
        ref_layout = QHBoxLayout()
        ref_label = QLabel("Referens:", self._ui.sources_group)
        self._ref_paste_input = QLineEdit(self._ui.sources_group)
        self._ref_paste_input.setPlaceholderText(
            "Klistra in referenstext för att söka efter källa"
        )
        self._ref_lookup_button = QPushButton("Sök", self._ui.sources_group)
        ref_layout.addWidget(ref_label)
        ref_layout.addWidget(self._ref_paste_input)
        ref_layout.addWidget(self._ref_lookup_button)

        # Insert after the source_edit_layout (source combo row)
        # The sources_group_layout order is: table, source_edit_layout, source_note_layout, buttons
        # We insert the reference paste layout at index 2 (after source_edit_layout)
        self._ui.sources_group_layout.insertLayout(2, ref_layout)

    def _setup_new_place_button(self) -> None:
        """Add a 'Ny plats' button next to the place combo.

        Inserts a button into the place group layout that opens the place
        editor to create a new place when the desired place is not in the list.
        """
        self._new_place_button = QPushButton("Ny plats...", self._ui.place_group)
        # Add the button to the place group layout (after the place combo)
        self._ui.place_group_layout.addWidget(self._new_place_button)

    def _populate_combos(self) -> None:
        """Fill combo boxes with available options from project data."""
        # Event type combo (Swedish labels, English keys as data)
        self._ui.type_combo.clear()
        for event_type in ALL_EVENT_TYPES:
            self._ui.type_combo.addItem(get_event_type_label(event_type), event_type)

        # Person combo for participants
        self._ui.participant_person_combo.clear()
        self._ui.participant_person_combo.addItem("", "")
        for person in self._project_data.persons:
            display = self._get_person_display(person.id)
            self._ui.participant_person_combo.addItem(display, person.id)

        # Place combo (full hierarchy, sorted alphabetically, searchable)
        self._ui.place_combo.clear()
        self._ui.place_combo.setEditable(True)
        self._ui.place_combo.setInsertPolicy(self._ui.place_combo.InsertPolicy.NoInsert)
        self._ui.place_combo.addItem("(ingen plats)", "")
        places_with_display: list[tuple[str, str]] = []
        for place in self._project_data.places:
            display = self._format_place_hierarchy(place)
            places_with_display.append((display, place.id))
        places_with_display.sort(key=lambda x: x[0].lower())
        place_names: list[str] = []
        for display, place_id in places_with_display:
            self._ui.place_combo.addItem(display, place_id)
            place_names.append(display)
        # Substring completer for searching
        place_completer = QCompleter(place_names, self._ui.place_combo)
        place_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        place_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._ui.place_combo.setCompleter(place_completer)

        # Source combo (searchable, sorted alphabetically by title)
        self._ui.source_combo.clear()
        self._ui.source_combo.setEditable(True)
        self._ui.source_combo.setInsertPolicy(self._ui.source_combo.InsertPolicy.NoInsert)
        self._ui.source_combo.addItem("", "")
        sources_sorted = sorted(
            self._project_data.sources,
            key=lambda s: (s.title or "").lower(),
        )
        source_titles: list[str] = []
        for source in sources_sorted:
            display = self._format_source_display(source)
            self._ui.source_combo.addItem(display, source.id)
            source_titles.append(display)
        # Add substring completer for searching
        completer = QCompleter(source_titles, self._ui.source_combo)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._ui.source_combo.setCompleter(completer)

        # Media combo
        self._ui.media_combo.clear()
        self._ui.media_combo.addItem("", "")
        for media_item in self._project_data.media:
            display = media_item.title or media_item.file or media_item.id
            self._ui.media_combo.addItem(display, media_item.id)

        # Source quality combo (Swedish labels, English keys as data)
        self._ui.source_quality_combo.clear()
        self._ui.source_quality_combo.addItem("Primär", "primary")
        self._ui.source_quality_combo.addItem("Sekundär", "secondary")
        self._ui.source_quality_combo.addItem("Tertiär", "tertiary")

        # Date precision combo (Swedish labels, English keys as data)
        self._ui.date_precision_combo.clear()
        for key, label in DATE_PRECISION_LABELS.items():
            self._ui.date_precision_combo.addItem(label, key)

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
        self._ref_lookup_button.clicked.connect(self._on_lookup_reference)
        self._ref_paste_input.returnPressed.connect(self._on_lookup_reference)

        # Place
        self._new_place_button.clicked.connect(self._on_new_place)

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
        """Show/hide type-specific fields based on current type selection.

        For individual events with a subject person, the participants section
        is hidden (person is added automatically). For family events, the
        participants section is shown so additional persons can be added.
        """
        current_type = self._ui.type_combo.currentData() or ""

        # Custom type name: visible only for custom event types
        is_custom = current_type in CUSTOM_EVENT_TYPES
        self._ui.custom_type_label.setVisible(is_custom)
        self._ui.custom_type_input.setVisible(is_custom)

        # Cause of death: visible only for death events
        is_death = current_type == "death"
        self._ui.cause_of_death_label.setVisible(is_death)
        self._ui.cause_of_death_input.setVisible(is_death)

        # Update participants visibility
        self._update_participants_visibility()

    def _update_participants_visibility(self) -> None:
        """Show/hide the participants section based on event type and context.

        When a subject_person_id is set and the event is an individual type,
        the participants section is hidden since the person is implied.
        For family events, the section is shown for adding a second person.
        When editing an existing individual event with a single participant,
        the participants section is hidden (the sole participant is implicit).
        When editing an event with multiple participants, it is always shown.
        """
        current_type = self._ui.type_combo.currentData() or ""
        is_family_event = current_type in FAMILY_EVENT_TYPES

        if self._subject_person_id and not self._event:
            # New event from person editor: hide participants for individual events
            self._ui.participants_group.setVisible(is_family_event)

            # For family events, update the subject's role and ensure they're added
            if is_family_event:
                role = EVENT_TYPE_ROLES.get(current_type, "deltagare")
                # Clear and re-add subject with correct role
                self._ui.participants_table.setRowCount(0)
                self._add_participant_row(
                    Participant(person_id=self._subject_person_id, role=role)
                )
        elif self._event and not is_family_event:
            # Editing an individual event: hide participants if only one
            # (the sole participant is implicit — it's the person being edited)
            has_multiple = self._ui.participants_table.rowCount() > 1
            self._ui.participants_group.setVisible(has_multiple)
        else:
            # Family events or standalone: always show participants
            self._ui.participants_group.setVisible(True)

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
            precision_index = self._ui.date_precision_combo.findData(
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

        quality_label = SOURCE_QUALITY_LABELS.get(source_ref.quality, source_ref.quality)
        quality_item = QTableWidgetItem(quality_label)
        quality_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        quality_item.setData(Qt.ItemDataRole.UserRole, source_ref.quality)

        note_item = QTableWidgetItem(source_ref.note)
        note_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)

        table.setItem(row, 0, source_item)
        table.setItem(row, 1, quality_item)
        table.setItem(row, 2, note_item)

    def _on_add_source(self) -> None:
        """Add a new source reference from the edit fields."""
        source_id = self._ui.source_combo.currentData()
        quality = self._ui.source_quality_combo.currentData()
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

    def _on_lookup_reference(self) -> None:
        """Look up a source by pasted reference text.

        Searches existing sources for a match on reference_text, title,
        or provider_ref. If found, selects it in the source combo.
        If not found, offers to create a new source with the reference text.
        """
        ref_text = self._ref_paste_input.text().strip()
        if not ref_text:
            self._update_status("Klistra in en referenstext att söka efter.")
            return

        ref_lower = ref_text.lower()

        # Try exact match on reference_text first, then substring match
        best_match: Optional[Source] = None
        for source in self._project_data.sources:
            if source.reference_text and source.reference_text.lower() == ref_lower:
                best_match = source
                break
            if source.provider_ref and source.provider_ref.lower() == ref_lower:
                best_match = source
                break

        # If no exact match, try substring matching
        if best_match is None:
            for source in self._project_data.sources:
                if source.reference_text and ref_lower in source.reference_text.lower():
                    best_match = source
                    break
                if source.title and ref_lower in source.title.lower():
                    best_match = source
                    break

        if best_match is not None:
            # Select in combo
            idx = self._ui.source_combo.findData(best_match.id)
            if idx >= 0:
                self._ui.source_combo.setCurrentIndex(idx)
            self._ref_paste_input.clear()
            self._clear_status()
        else:
            # Not found — offer to create a new source
            self._create_source_from_reference(ref_text)

    def _create_source_from_reference(self, reference_text: str) -> None:
        """Open the source editor to create a new source pre-filled with reference text.

        If the reference text matches the ArkivDigital church book pattern
        (e.g. "Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915"),
        auto-fills provider, source type, and structured reference fields.

        After the source is created, adds it to project data, updates the
        combo box, and selects it.

        Args:
            reference_text: The reference text to pre-fill in the new source.
        """
        from slaktbusken.gedcom.translation.source_translation import (
            parse_church_book_citation,
        )
        from slaktbusken.ui.editors.source_editor import SourceEditor

        dialog = QDialog(self)
        dialog.setWindowTitle("Skapa ny källa")
        dialog.setMinimumSize(800, 600)
        layout = QVBoxLayout(dialog)

        editor = SourceEditor(
            project_data=self._project_data,
            source=None,
            parent=dialog,
        )
        layout.addWidget(editor)

        # Connect editor signals to dialog accept/reject
        editor.save_requested.connect(dialog.accept)
        editor.cancel_requested.connect(dialog.reject)

        # Strip "ArkivDigital:" prefix if present
        clean_ref = reference_text
        if clean_ref.lower().startswith("arkivdigital:"):
            clean_ref = clean_ref[len("arkivdigital:"):].strip()

        # Pre-fill reference text
        if hasattr(editor, '_ui') and hasattr(editor._ui, 'reference_text_input'):
            editor._ui.reference_text_input.setText(clean_ref)

        # Try to parse as ArkivDigital church book reference
        parsed = parse_church_book_citation(clean_ref)
        if parsed is not None:
            # Auto-fill provider and source type
            editor._ui.provider_input.setText("ArkivDigital")

            # Set source type to church_book
            type_idx = editor._ui.source_type_combo.findData("church_book")
            if type_idx >= 0:
                editor._ui.source_type_combo.setCurrentIndex(type_idx)

            # Auto-fill structured reference fields
            fields = parsed.fields
            if fields.get("parish"):
                editor._ui.parish_input.setText(str(fields["parish"]))
            if fields.get("county_code"):
                editor._ui.county_code_input.setText(str(fields["county_code"]))
            if fields.get("series"):
                editor._ui.series_input.setText(str(fields["series"]))
            if fields.get("volume"):
                editor._ui.volume_input.setText(str(fields["volume"]))
            if fields.get("years"):
                editor._ui.years_input.setText(str(fields["years"]))
            if fields.get("image") is not None:
                editor._ui.image_input.setText(str(fields["image"]))
            if fields.get("page") is not None:
                editor._ui.page_input.setText(str(fields["page"]))

            # Generate a title from parish + series
            parish = fields.get("parish", "")
            series = fields.get("series", "")
            volume = fields.get("volume", "")
            if parish and series:
                title = f"{parish} {series}:{volume}" if volume else f"{parish} {series}"
                editor._ui.title_input.setText(title)

        # Show modal
        dialog.exec()

        # Check if a source was saved
        saved_source = editor.saved_source
        if saved_source is not None:
            # Add to project data
            self._project_data.sources.append(saved_source)

            # Add to combo and select it
            display = self._format_source_display(saved_source)
            self._ui.source_combo.addItem(display, saved_source.id)
            idx = self._ui.source_combo.findData(saved_source.id)
            if idx >= 0:
                self._ui.source_combo.setCurrentIndex(idx)

            self._ref_paste_input.clear()
            self._clear_status()

    # ------------------------------------------------------------------
    # Private: place management
    # ------------------------------------------------------------------

    def _on_new_place(self) -> None:
        """Open the place editor to create a new place.

        After the place is created, adds it to project data, updates the
        place combo, and selects it.
        """
        from slaktbusken.ui.editors.place_editor import PlaceEditor

        dialog = QDialog(self)
        dialog.setWindowTitle("Skapa ny plats")
        dialog.setMinimumSize(700, 500)
        layout = QVBoxLayout(dialog)

        editor = PlaceEditor(
            project_data=self._project_data,
            place=None,
            parent=dialog,
        )
        layout.addWidget(editor)

        # PlaceEditor signals
        editor.save_requested.connect(dialog.accept)
        editor.cancel_requested.connect(dialog.reject)

        dialog.exec()

        saved_place = editor.saved_place
        if saved_place is not None:
            # Add to project data
            self._project_data.places.append(saved_place)

            # Add to combo and select it
            display = self._format_place_hierarchy(saved_place)
            self._ui.place_combo.addItem(display, saved_place.id)
            idx = self._ui.place_combo.findData(saved_place.id)
            if idx >= 0:
                self._ui.place_combo.setCurrentIndex(idx)

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
        For individual events with a subject person, the subject is added
        automatically. For family events, at least two participants are
        expected (validated with a warning but not enforced).
        On success, stores the result in saved_event.
        """
        # Validate: type required
        event_type = self._ui.type_combo.currentData()
        if not event_type:
            self._update_status("Välj en händelsetyp.")
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
        is_family_event = event_type in FAMILY_EVENT_TYPES

        if self._subject_person_id and not self._event and not is_family_event:
            # Individual event from person editor: subject is the sole participant
            role = EVENT_TYPE_ROLES.get(event_type, "huvudperson")
            participants.append(
                Participant(person_id=self._subject_person_id, role=role)
            )
        else:
            # Collect from table (family events, editing existing, standalone)
            table = self._ui.participants_table
            for row in range(table.rowCount()):
                person_id = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                role = table.item(row, 1).text()
                participants.append(Participant(person_id=person_id, role=role))

        # Validate: at least one participant
        if not participants:
            self._update_status("Minst en deltagare krävs.")
            return

        # Date
        date: Optional[DateValue] = None
        date_value = self._ui.date_value_input.text().strip()
        if date_value:
            precision = self._ui.date_precision_combo.currentData()
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
        self.save_requested.emit()
        self.close()

    def _on_cancel(self) -> None:
        """Close the editor without saving."""
        self._saved_event = None
        self.cancel_requested.emit()
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
            quality = table.item(row, 1).data(Qt.ItemDataRole.UserRole)
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
            A display string with the source title and reference text.
        """
        for source in self._project_data.sources:
            if source.id == source_id:
                return self._format_source_display(source)
        return source_id

    @staticmethod
    def _format_source_display(source: Source) -> str:
        """Format a source for display in combo boxes and tables.

        Shows title combined with reference_text to distinguish sources
        that share the same title. If no title, falls back to reference_text.

        Args:
            source: The source to format.

        Returns:
            A formatted display string.
        """
        title = source.title or ""
        ref = source.reference_text or ""

        if title and ref:
            return f"{title} — {ref}"
        if title:
            return title
        if ref:
            return ref
        return source.id

    def _format_place_hierarchy(self, place) -> str:
        """Format a place with its full hierarchy path.

        Walks up parent_place_id to build a comma-separated string from
        most specific to least specific (e.g. "Ljusdals kyrka, Ljusdal,
        Gävleborgs län, Sverige").

        Args:
            place: The Place to format.

        Returns:
            Full hierarchy string.
        """
        parts = [place.name]
        current = place
        visited: set[str] = {current.id}
        while current.parent_place_id:
            parent = None
            for p in self._project_data.places:
                if p.id == current.parent_place_id:
                    parent = p
                    break
            if parent is None or parent.id in visited:
                break
            parts.append(parent.name)
            visited.add(parent.id)
            current = parent
        return ", ".join(parts)

    def _update_status(self, message: str) -> None:
        """Update the status label text with an error/info message.

        Args:
            message: The status message to display.
        """
        self._ui.status_label.setText(message)

    def _clear_status(self) -> None:
        """Clear the status label."""
        self._ui.status_label.setText("")
