"""Event editor widget.

Provides a form-based editor for Event records: type selection,
participants management, date/place, source references, and media links.
Validates that type and at least one participant are set before save.
All UI text is in Swedish.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from slaktbusken.services.photo_service import PhotoService

from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.project import ProjectData
from slaktbusken.model.source import Source
from slaktbusken.services.event_media_service import EventMediaService
from slaktbusken.services.source_aspects import (
    ASPECT_LABELS,
    get_aspects_for_event_type,
)
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

# Event types that support the event-media section
EVENT_MEDIA_TYPES: set[str] = {"death", "funeral"}

# Non-photo media types available in the "Annan media" section.
# Label (Swedish) → stored type key.
NON_PHOTO_MEDIA_TYPES: list[tuple[str, str]] = [
    ("Film", "film"),
    ("Ljud", "ljud"),
    ("Inbjudan", "inbjudan"),
    ("Dödsannons", "dödsannons"),
    ("Tackannons", "tackannons"),
    ("Minnesruna", "minnesruna"),
    ("Program", "program"),
    ("Brev", "brev"),
    ("Tidningsklipp", "tidningsklipp"),
    ("Vigselbevis", "vigselbevis"),
    ("Dopbevis", "dopbevis"),
    ("Konfirmationsbevis", "konfirmationsbevis"),
    ("Testamente", "testamente"),
    ("Bouppteckning", "bouppteckning"),
    ("Betyg / Intyg", "betyg"),
    ("Flyttbetyg", "flyttbetyg"),
    ("Pass", "pass"),
    ("Militärpass", "militärpass"),
    ("Karta", "karta"),
    ("Ritning", "ritning"),
    ("Handskrivet dokument", "handskrivet_dokument"),
    ("Övrigt", "övrigt"),
]


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
        project_folder: Path | None = None,
        photo_service: "Optional[PhotoService]" = None,
    ) -> None:
        """Initialise the event editor.

        Args:
            project_data: The current project data containing all entities.
            event: Optional existing Event to edit. If None, creates a new event.
            subject_person_id: Optional person ID to auto-add as participant.
            parent: Optional parent widget.
            project_folder: Optional path to the project folder for media operations.
            photo_service: Optional PhotoService for photo management operations.
        """
        super().__init__(parent)

        self._project_data = project_data
        self._event = event
        self._subject_person_id = subject_person_id
        self._project_folder = project_folder
        self._photo_service = photo_service
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
        self._setup_aspect_checkboxes()
        self._setup_photo_section()
        self._setup_event_media_section()
        self._connect_signals()

        # Hide the old "Media" section from the .ui file (replaced by Foton + Annan media)
        self._ui.media_group.setVisible(False)

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

    def _setup_aspect_checkboxes(self) -> None:
        """Create the aspect checkboxes section in the sources group.

        Adds a horizontal layout with checkboxes for the aspects relevant
        to the current event type. The checkboxes are shown when a source
        row is selected in the sources table, and update the stored aspects
        for that row when toggled.
        """
        self._aspect_checkboxes: list[QCheckBox] = []
        self._aspect_checkbox_layout = QHBoxLayout()
        self._aspect_checkbox_layout.setContentsMargins(0, 4, 0, 4)

        aspect_label = QLabel("Aspekter:", self._ui.sources_group)
        self._aspect_checkbox_layout.addWidget(aspect_label)

        # Spacer at the end
        self._aspect_checkbox_layout.addItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        )

        # Insert after the sources_table (index 1, after the table at index 0)
        self._ui.sources_group_layout.insertLayout(1, self._aspect_checkbox_layout)

        # Initially hidden until a source row is selected
        self._set_aspect_checkboxes_visible(False)

    def _setup_new_place_button(self) -> None:
        """Add a 'Ny plats' button next to the place combo.

        Inserts a button into the place group layout that opens the place
        editor to create a new place when the desired place is not in the list.
        """
        self._new_place_button = QPushButton("Ny plats...", self._ui.place_group)
        # Add the button to the place group layout (after the place combo)
        self._ui.place_group_layout.addWidget(self._new_place_button)

    def _setup_photo_section(self) -> None:
        """Create the "Foton" section for death/funeral events.

        Uses PhotoSectionWidget in event mode with buttons:
        "Lägg till foto", "Redigera foto", "Ta bort foto".
        The section is inserted into the main layout before the status label.
        Visibility is controlled by _update_type_specific_fields.
        """
        from slaktbusken.ui.widgets.photo_section_widget import PhotoSectionWidget

        self._photo_section: Optional[PhotoSectionWidget] = None

        # Group box for the photo section
        self._photo_group = QGroupBox("Foton")
        self._photo_section_layout = QVBoxLayout(self._photo_group)

        # Insert into main layout before the status label
        main_layout = self._ui.main_layout
        status_index = main_layout.indexOf(self._ui.status_label)
        main_layout.insertWidget(status_index, self._photo_group)

        # Initially hidden (toggled by _update_type_specific_fields)
        self._photo_group.setVisible(False)

    def _setup_event_media_section(self) -> None:
        """Create the "Annan media" section for non-photo media.

        Builds a QGroupBox with:
        - A list showing currently linked non-photo event media items
        - "Lägg till media", "Redigera media", "Visa media", "Ta bort media" buttons
        """
        self._event_media_service = EventMediaService(self._project_data)
        self._event_media_items: list[MediaItem] = []

        # Group box
        self._event_media_group = QGroupBox("Annan media")
        event_media_layout = QVBoxLayout(self._event_media_group)

        # List of linked media items
        self._event_media_list = QListWidget(self._event_media_group)
        self._event_media_list.setMaximumHeight(120)
        event_media_layout.addWidget(self._event_media_list)

        # Buttons
        buttons_layout = QHBoxLayout()
        self._event_media_add_button = QPushButton(
            "Lägg till media", self._event_media_group
        )
        buttons_layout.addWidget(self._event_media_add_button)

        self._event_media_edit_button = QPushButton(
            "Redigera media", self._event_media_group
        )
        self._event_media_edit_button.setEnabled(False)
        buttons_layout.addWidget(self._event_media_edit_button)

        self._event_media_view_button = QPushButton(
            "Visa media", self._event_media_group
        )
        self._event_media_view_button.setEnabled(False)
        buttons_layout.addWidget(self._event_media_view_button)

        self._event_media_remove_button = QPushButton(
            "Ta bort media", self._event_media_group
        )
        self._event_media_remove_button.setEnabled(False)
        buttons_layout.addWidget(self._event_media_remove_button)
        buttons_layout.addItem(
            QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        )
        event_media_layout.addLayout(buttons_layout)

        # Insert into main layout before the status label
        main_layout = self._ui.main_layout
        status_index = main_layout.indexOf(self._ui.status_label)
        main_layout.insertWidget(status_index, self._event_media_group)

        # Initially visible (shown for all event types)
        self._event_media_group.setVisible(True)

        # Connect signals
        self._event_media_add_button.clicked.connect(self._on_event_media_add)
        self._event_media_edit_button.clicked.connect(self._on_event_media_edit)
        self._event_media_view_button.clicked.connect(self._on_event_media_view)
        self._event_media_remove_button.clicked.connect(
            self._on_event_media_remove
        )
        self._event_media_list.currentRowChanged.connect(
            self._on_event_media_selection_changed
        )

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
        self._ui.open_source_button.clicked.connect(self._on_open_source)
        self._ui.sources_table.itemSelectionChanged.connect(
            self._on_sources_selection_changed
        )
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
        The "Foton" and "Annan media" sections are visible only for death
        and funeral events.
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

        # Photo and Annan media sections: visible for all event types
        self._event_media_group.setVisible(True)
        self._refresh_photo_section()

        # Update participants visibility
        self._update_participants_visibility()

        # Update aspect checkboxes for the new event type
        self._update_aspect_checkboxes_for_event_type()

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

        # Load event media (photos and non-photo media) for all event types
        self._refresh_photo_section()
        self._load_event_media()

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
        # Store aspects in UserRole+1
        source_item.setData(Qt.ItemDataRole.UserRole + 1, list(source_ref.aspects))

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
        self._set_aspect_checkboxes_visible(False)
        self._clear_status()

    def _on_sources_selection_changed(self) -> None:
        """Enable/disable the 'Öppna källa' button based on table selection and update aspect checkboxes."""
        has_selection = bool(self._ui.sources_table.selectedItems())
        self._ui.open_source_button.setEnabled(has_selection)
        if has_selection:
            row = self._ui.sources_table.selectedItems()[0].row()
            self._load_aspects_for_row(row)
            self._set_aspect_checkboxes_visible(True)
        else:
            self._set_aspect_checkboxes_visible(False)

    def _on_open_source(self) -> None:
        """Open the SourceEditor with the currently selected source."""
        selected = self._ui.sources_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        source_id = self._ui.sources_table.item(row, 0).data(Qt.ItemDataRole.UserRole)

        # Find the Source object
        source: Optional[Source] = None
        for s in self._project_data.sources:
            if s.id == source_id:
                source = s
                break

        if source is None:
            self._update_status("Kunde inte hitta källan.")
            return

        from slaktbusken.ui.editors.source_editor import SourceEditor

        dialog = QDialog(self)
        dialog.setWindowTitle("Källredigerare")
        dialog.setMinimumSize(800, 600)
        layout = QVBoxLayout(dialog)

        editor = SourceEditor(
            project_data=self._project_data,
            source=source,
            project_folder=self._project_folder,
            parent=dialog,
        )
        layout.addWidget(editor)

        editor.save_requested.connect(dialog.accept)
        editor.cancel_requested.connect(dialog.reject)

        dialog.exec()

        # If source was saved, update in project data
        if editor.saved_source is not None:
            saved = editor.saved_source
            for i, existing in enumerate(self._project_data.sources):
                if existing.id == saved.id:
                    self._project_data.sources[i] = saved
                    break
            # Update the display in the sources table
            source_display = self._get_source_display(saved.id)
            self._ui.sources_table.item(row, 0).setText(source_display)

    # ------------------------------------------------------------------
    # Private: source aspect checkboxes
    # ------------------------------------------------------------------

    def _set_aspect_checkboxes_visible(self, visible: bool) -> None:
        """Show or hide all aspect checkbox widgets.

        Args:
            visible: Whether the checkboxes should be visible.
        """
        for i in range(self._aspect_checkbox_layout.count()):
            item = self._aspect_checkbox_layout.itemAt(i)
            if item and item.widget():
                item.widget().setVisible(visible)

    def _update_aspect_checkboxes_for_event_type(self) -> None:
        """Rebuild aspect checkboxes based on the current event type.

        Clears existing checkboxes and creates new ones for the aspects
        relevant to the currently selected event type.
        """
        # Remove existing checkboxes (keep the label at index 0 and spacer at end)
        while len(self._aspect_checkboxes) > 0:
            cb = self._aspect_checkboxes.pop()
            self._aspect_checkbox_layout.removeWidget(cb)
            cb.deleteLater()

        # Get aspects for current event type
        event_type = self._ui.type_combo.currentData() or ""
        aspects = get_aspects_for_event_type(event_type)

        # Insert checkboxes before the spacer (which is the last item)
        spacer_index = self._aspect_checkbox_layout.count() - 1
        for aspect in aspects:
            label = ASPECT_LABELS.get(aspect, aspect)
            cb = QCheckBox(label, self._ui.sources_group)
            cb.setProperty("aspect_key", aspect)
            cb.toggled.connect(self._on_aspect_checkbox_toggled)
            self._aspect_checkbox_layout.insertWidget(spacer_index, cb)
            self._aspect_checkboxes.append(cb)
            spacer_index += 1

        # Hide if no source row is selected
        has_selection = bool(self._ui.sources_table.selectedItems())
        self._set_aspect_checkboxes_visible(has_selection)

    def _load_aspects_for_row(self, row: int) -> None:
        """Load stored aspects for the given row into the checkboxes.

        Args:
            row: The row index in the sources table.
        """
        # Get stored aspects from the source item's UserRole+1 data
        item = self._ui.sources_table.item(row, 0)
        if item is None:
            return
        stored_aspects = item.data(Qt.ItemDataRole.UserRole + 1) or []

        # Block signals while updating checkboxes to avoid feedback loops
        for cb in self._aspect_checkboxes:
            cb.blockSignals(True)
            aspect_key = cb.property("aspect_key")
            cb.setChecked(aspect_key in stored_aspects)
            cb.blockSignals(False)

    def _on_aspect_checkbox_toggled(self, _checked: bool) -> None:
        """Handle aspect checkbox state change.

        Updates the stored aspects for the currently selected source row.
        """
        selected = self._ui.sources_table.selectedItems()
        if not selected:
            return

        row = selected[0].row()
        # Collect currently checked aspects
        checked_aspects: list[str] = []
        for cb in self._aspect_checkboxes:
            if cb.isChecked():
                aspect_key = cb.property("aspect_key")
                checked_aspects.append(aspect_key)

        # Store in the source item (column 0) using UserRole+1
        item = self._ui.sources_table.item(row, 0)
        if item:
            item.setData(Qt.ItemDataRole.UserRole + 1, checked_aspects)

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

        Sets the reference text in the editor, which triggers auto-parsing
        via _on_reference_text_changed to populate title, provider, source type,
        and structured reference fields.

        After the source is created, adds it to project data, updates the
        combo box, and selects it.

        Args:
            reference_text: The reference text to pre-fill in the new source.
        """
        from slaktbusken.ui.editors.source_editor import SourceEditor

        dialog = QDialog(self)
        dialog.setWindowTitle("Skapa ny källa")
        dialog.setMinimumSize(800, 600)
        layout = QVBoxLayout(dialog)

        editor = SourceEditor(
            project_data=self._project_data,
            source=None,
            project_folder=self._project_folder,
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

        # Pre-fill reference text — this triggers _on_reference_text_changed
        # which auto-populates title, provider, structured fields via parse_reference()
        if hasattr(editor, '_ui') and hasattr(editor._ui, 'reference_text_input'):
            editor._ui.reference_text_input.setText(clean_ref)

        # Show modal
        dialog.exec()

        # Check if a source was saved
        saved_source = editor.saved_source
        if saved_source is not None:
            # Source already added to project data by SourceEditor._on_save

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
        dialog.setMinimumSize(900, 750)
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
            # Place already added to project data by PlaceEditor._on_save

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
    # Private: photo section management (death/funeral)
    # ------------------------------------------------------------------

    def _refresh_photo_section(self) -> None:
        """Rebuild the PhotoSectionWidget for the current event.

        Creates or replaces the PhotoSectionWidget inside the photo group box,
        connecting its buttons to appropriate handlers.
        """
        from slaktbusken.ui.widgets.photo_section_widget import PhotoSectionWidget

        # Remove existing photo section widget if present
        if self._photo_section is not None:
            self._photo_section_layout.removeWidget(self._photo_section)
            self._photo_section.setParent(None)
            self._photo_section.deleteLater()
            self._photo_section = None

        if self._photo_service is None:
            self._photo_group.setVisible(False)
            return

        # Determine the event ID (existing event or temporary placeholder)
        event_id = self._event.id if self._event else ""
        if not event_id:
            # For new events, we can't show photos yet (no ID assigned)
            self._photo_group.setVisible(False)
            return

        # Create new PhotoSectionWidget for this event
        self._photo_section = PhotoSectionWidget(
            project_data=self._project_data,
            photo_service=self._photo_service,
            entity_type="event",
            entity_id=event_id,
            parent=self._photo_group,
        )
        self._photo_section_layout.addWidget(self._photo_section)

        # Connect button signals
        self._photo_section.add_button.clicked.connect(self._on_photo_add)
        self._photo_section.photo_edited.connect(self._on_photo_edit)
        if self._photo_section.remove_button:
            self._photo_section.remove_button.clicked.connect(self._on_photo_remove)

        self._photo_group.setVisible(True)

    def _on_photo_add(self) -> None:
        """Handle 'Lägg till foto' button click in the photo section.

        Opens a file dialog filtered to image formats. On file selection,
        creates a new MediaItem with type 'photo' and a LinkedEntity
        linking it to the current event.
        """
        if self._photo_service is None:
            return

        event_id = self._event.id if self._event else None
        if not event_id:
            self._update_status("Spara händelsen först innan du lägger till foton.")
            return

        file_filter = "Bildfiler (*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.tif)"
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Välj bild",
            "",
            file_filter,
        )

        if not file_path:
            # User cancelled — do nothing
            return

        # Create the new MediaItem
        new_media = MediaItem(
            id=str(uuid.uuid4()),
            type="photo",
            file=file_path,
            title=Path(file_path).stem,
            linked_entities=[
                LinkedEntity(entity_type="event", entity_id=event_id)
            ],
        )

        # Add to project data
        self._project_data.media.append(new_media)

        # Track the photo media ID for saving
        if self._event and new_media.id not in self._event.media_ids:
            self._event.media_ids.append(new_media.id)

        # Refresh the photo section and emit signal
        if self._photo_section is not None:
            self._photo_section.refresh()
            self._photo_section.emit_photo_added(new_media.id)

        self._clear_status()

    def _on_photo_edit(self, media_item_id: str) -> None:
        """Handle 'Redigera foto' button click.

        Opens EditPhotoDialog with the selected MediaItem.

        Args:
            media_item_id: The ID of the MediaItem to edit.
        """
        if self._photo_service is None:
            return

        media_item = self._find_media_item_by_id(media_item_id)
        if media_item is None:
            return

        from slaktbusken.ui.dialogs.edit_photo_dialog import EditPhotoDialog

        dialog = EditPhotoDialog(
            media_item=media_item,
            project_data=self._project_data,
            photo_service=self._photo_service,
            parent=self,
        )
        dialog.exec()

        # Refresh photo section after dialog closes (changes may have been saved)
        if self._photo_section is not None:
            self._photo_section.refresh()

    def _on_photo_remove(self) -> None:
        """Handle 'Ta bort foto' button click.

        Removes the selected photo from the event (unlinks, does not delete
        the MediaItem from project data).
        """
        if self._photo_section is None:
            return

        photo_id = self._photo_section.get_selected_photo_id()
        if photo_id is None:
            return

        # Unlink from event via service
        if self._event and photo_id in self._event.media_ids:
            self._event_media_service.remove_media_from_event(
                self._event, photo_id
            )

        # Refresh the photo section
        self._photo_section.refresh()
        self._clear_status()

    def _find_media_item_by_id(self, media_id: str) -> Optional[MediaItem]:
        """Find a MediaItem by its ID in the project data.

        Args:
            media_id: The MediaItem ID to search for.

        Returns:
            The MediaItem if found, None otherwise.
        """
        for media_item in self._project_data.media:
            if media_item.id == media_id:
                return media_item
        return None

    # ------------------------------------------------------------------
    # Private: event media management (death/funeral)
    # ------------------------------------------------------------------

    def _on_event_media_add(self) -> None:
        """Add a new media item by opening a type selector then file dialog.

        Flow: select media type → open file dialog → prompt for title → create MediaItem.
        """
        from PySide6.QtWidgets import QInputDialog

        # Step 1: Select media type
        type_labels = [label for label, _key in NON_PHOTO_MEDIA_TYPES]
        selected_label, ok = QInputDialog.getItem(
            self,
            "Välj mediatyp",
            "Typ:",
            type_labels,
            0,
            False,
        )
        if not ok:
            return  # User cancelled

        # Find the type key
        media_type = "övrigt"
        for label, key in NON_PHOTO_MEDIA_TYPES:
            if label == selected_label:
                media_type = key
                break

        # Step 2: Open file dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Välj mediafil",
            "",
            "Alla filer (*)",
        )
        if not file_path:
            return  # User cancelled

        # Step 3: Prompt for title
        title, ok = QInputDialog.getText(
            self,
            "Ange titel",
            "Titel för mediaobjektet:",
        )
        if not ok:
            return  # User cancelled

        title = title.strip()
        if not title:
            title = Path(file_path).stem

        # Create the MediaItem
        media_item = MediaItem(
            id=str(uuid.uuid4()),
            type=media_type,
            file=file_path,
            title=title,
        )

        # Add to project data
        self._project_data.media.append(media_item)

        # Track locally for linking during save
        self._event_media_items.append(media_item)

        # Display in list
        display = f"[{selected_label}] {media_item.title}"
        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, media_item.id)
        self._event_media_list.addItem(item)

        self._clear_status()

    def _on_event_media_selection_changed(self, row: int) -> None:
        """Enable/disable buttons based on media list selection."""
        has_selection = row >= 0
        self._event_media_edit_button.setEnabled(has_selection)
        self._event_media_view_button.setEnabled(has_selection)
        self._event_media_remove_button.setEnabled(has_selection)

    def _on_event_media_edit(self) -> None:
        """Edit the selected media item's type and title."""
        from PySide6.QtWidgets import QInputDialog

        current = self._event_media_list.currentItem()
        if not current:
            return

        media_id = current.data(Qt.ItemDataRole.UserRole)
        media_item = self._find_media_item_by_id(media_id)
        if media_item is None:
            return

        # Step 1: Edit type
        type_labels = [label for label, _key in NON_PHOTO_MEDIA_TYPES]
        # Pre-select current type
        current_index = 0
        for i, (label, key) in enumerate(NON_PHOTO_MEDIA_TYPES):
            if key == media_item.type:
                current_index = i
                break

        selected_label, ok = QInputDialog.getItem(
            self,
            "Ändra mediatyp",
            "Typ:",
            type_labels,
            current_index,
            False,
        )
        if not ok:
            return

        # Step 2: Edit title
        new_title, ok = QInputDialog.getText(
            self,
            "Ändra titel",
            "Titel:",
            QLineEdit.EchoMode.Normal,
            media_item.title,
        )
        if not ok:
            return

        new_title = new_title.strip()
        if not new_title:
            return

        # Apply changes
        for label, key in NON_PHOTO_MEDIA_TYPES:
            if label == selected_label:
                media_item.type = key
                break
        media_item.title = new_title

        # Update list display
        current.setText(f"[{selected_label}] {new_title}")

    def _on_event_media_view(self) -> None:
        """Open/show the selected media file using the system's default application.

        For images: shows in a modal dialog.
        For all other types (video, audio, documents): opens with the OS default app.
        """
        import os
        import subprocess

        current = self._event_media_list.currentItem()
        if not current:
            return

        media_id = current.data(Qt.ItemDataRole.UserRole)
        media_item = self._find_media_item_by_id(media_id)
        if media_item is None:
            return

        file_path = Path(media_item.file)
        if not file_path.is_absolute() and self._project_folder:
            file_path = self._project_folder / file_path

        if not file_path.exists():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Fil saknas",
                f"Filen kunde inte hittas:\n{file_path}",
            )
            return

        # For image files, show in a dialog
        image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".tif"}
        if file_path.suffix.lower() in image_extensions:
            from PySide6.QtGui import QPixmap
            dialog = QDialog(self)
            dialog.setWindowTitle(media_item.title)
            dialog.setModal(True)
            layout = QVBoxLayout(dialog)

            pixmap = QPixmap(str(file_path))
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    800, 600,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                image_label = QLabel()
                image_label.setPixmap(scaled)
                layout.addWidget(image_label)

            close_btn = QPushButton("Stäng")
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn)
            dialog.exec()
        else:
            # For video, audio, documents: open with OS default application
            try:
                os.startfile(str(file_path))
            except AttributeError:
                # Non-Windows fallback
                subprocess.Popen(["xdg-open", str(file_path)])

    def _on_event_media_remove(self) -> None:
        """Remove the selected event media item (unlink only, preserve MediaItem)."""
        current = self._event_media_list.currentItem()
        if not current:
            self._update_status("Välj ett mediaobjekt att ta bort.")
            return

        media_id = current.data(Qt.ItemDataRole.UserRole)
        row = self._event_media_list.row(current)
        self._event_media_list.takeItem(row)

        # If editing an existing event, unlink via service
        if self._event and media_id in self._event.media_ids:
            self._event_media_service.remove_media_from_event(
                self._event, media_id
            )

        # Remove from local tracking if it was newly added
        self._event_media_items = [
            m for m in self._event_media_items if m.id != media_id
        ]

        self._clear_status()

    def _load_event_media(self) -> None:
        """Load existing non-photo event media items into the Annan media list.

        Called during _load_event to populate the non-photo media section.
        Photos are loaded separately via the PhotoSectionWidget's refresh().
        """
        if not self._event:
            return

        for media_id in self._event.media_ids:
            for media_item in self._project_data.media:
                if media_item.id == media_id and media_item.type != "photo":
                    # Find Swedish label for the type
                    type_label = media_item.type
                    for label, key in NON_PHOTO_MEDIA_TYPES:
                        if key == media_item.type:
                            type_label = label
                            break
                    display = f"[{type_label}] {media_item.title}"
                    item = QListWidgetItem(display)
                    item.setData(Qt.ItemDataRole.UserRole, media_id)
                    self._event_media_list.addItem(item)
                    break

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

        # Collect event media IDs from the event media list (non-photo)
        event_media_ids: list[str] = []
        for i in range(self._event_media_list.count()):
            item = self._event_media_list.item(i)
            if item:
                    media_id = item.data(Qt.ItemDataRole.UserRole)
                    if media_id:
                        event_media_ids.append(media_id)

        # Collect photo IDs from the photo section
        photo_media_ids: list[str] = []
        if self._photo_section is not None:
            for i in range(self._photo_section.photo_list.count()):
                if i < len(self._photo_section._photo_ids):
                    photo_media_ids.append(self._photo_section._photo_ids[i])

        # Determine event ID
        event_id = self._event.id if self._event else str(uuid.uuid4())

        # Merge regular media_ids with event media_ids and photo_ids
        all_media_ids = media_ids + event_media_ids + photo_media_ids

        self._saved_event = Event(
            id=event_id,
            type=event_type,
            participants=participants,
            date=date,
            place=place,
            media_ids=all_media_ids,
            custom_type_name=custom_type_name,
            cause_of_death=cause_of_death,
        )

        # Link newly added event media items via EventMediaService
        for media_item in self._event_media_items:
            if media_item.id in event_media_ids:
                self._event_media_service.add_media_to_event(
                    self._saved_event, media_item
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
            List of SourceRef objects from the table rows, including aspects.
        """
        source_refs: list[SourceRef] = []
        table = self._ui.sources_table
        for row in range(table.rowCount()):
            source_id = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            quality = table.item(row, 1).data(Qt.ItemDataRole.UserRole)
            note = table.item(row, 2).text()
            aspects = table.item(row, 0).data(Qt.ItemDataRole.UserRole + 1) or []
            source_refs.append(
                SourceRef(source_id=source_id, quality=quality, note=note, aspects=aspects)
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
