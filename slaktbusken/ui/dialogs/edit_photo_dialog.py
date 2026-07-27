"""Edit photo dialog for editing all metadata of a single photo.

Provides a modal dialog with scrollable sections for title/type,
date, persons, events, places, and notes. All UI text is in Swedish.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.services.photo_tagging_service import PhotoTaggingService
from slaktbusken.ui.widgets.person_list_widget import PersonListWidget

if TYPE_CHECKING:
    from slaktbusken.model.media import MediaItem
    from slaktbusken.model.project import ProjectData
    from slaktbusken.services.photo_service import PhotoService


class EditPhotoDialog(QDialog):
    """Modal dialog for editing all metadata of a single photo."""

    def __init__(
        self,
        media_item: "MediaItem",
        project_data: "ProjectData",
        photo_service: "PhotoService",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._media_item = media_item
        self._project_data = project_data
        self._photo_service = photo_service
        self._saved = False

        self.setWindowTitle("Redigera foto")
        self.setModal(True)
        self.setMinimumSize(600, 700)

        self._build_ui()
        self._load_title_type_data()
        self._load_date_data()
        self._load_notes_data()

    def _build_ui(self) -> None:
        """Build the dialog layout with scroll area and footer buttons."""
        main_layout = QVBoxLayout(self)

        # Scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        # Sections
        self._title_type_group = self._build_title_type_section()
        scroll_layout.addWidget(self._title_type_group)

        self._date_group = self._build_date_section()
        scroll_layout.addWidget(self._date_group)

        self._persons_group = self._build_persons_section()
        scroll_layout.addWidget(self._persons_group)

        self._events_group = self._build_events_section()
        scroll_layout.addWidget(self._events_group)

        self._places_group = self._build_places_section()
        scroll_layout.addWidget(self._places_group)

        self._notes_group = self._build_notes_section()
        scroll_layout.addWidget(self._notes_group)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

        # Footer buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._save_button = QPushButton("Spara")
        self._save_button.clicked.connect(self._on_save)
        button_layout.addWidget(self._save_button)

        self._cancel_button = QPushButton("Avbryt")
        self._cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self._cancel_button)

        main_layout.addLayout(button_layout)

    def _build_title_type_section(self) -> QGroupBox:
        """Build the 'Titel och typ' section with title field and type combo."""
        group = QGroupBox("Titel och typ")
        layout = QFormLayout(group)

        # Title field
        self._title_edit = QLineEdit()
        self._title_edit.setMaxLength(200)
        self._title_edit.setPlaceholderText("Ange titel...")
        layout.addRow("Titel:", self._title_edit)

        # Title validation error label
        self._title_error_label = QLabel("")
        self._title_error_label.setStyleSheet("color: red;")
        self._title_error_label.setWordWrap(True)
        self._title_error_label.hide()
        layout.addRow("", self._title_error_label)

        # Photo type combo
        self._type_combo = QComboBox()
        self._type_combo.addItems(self._photo_service.FOTO_TYPES)
        layout.addRow("Fototyp:", self._type_combo)

        return group

    def _load_title_type_data(self) -> None:
        """Parse the media item title and populate title/type fields."""
        foto_typ, title = self._photo_service.parse_title(self._media_item.title)
        self._title_edit.setText(title)
        self._type_combo.setCurrentText(foto_typ)

    def _validate_title(self) -> list[str]:
        """Validate the title field. Returns error messages (empty = valid)."""
        errors = self._photo_service.validate_title(self._title_edit.text())
        if errors:
            self._title_error_label.setText(errors[0])
            self._title_error_label.show()
        else:
            self._title_error_label.setText("")
            self._title_error_label.hide()
        return errors

    def _get_composed_title(self) -> str:
        """Compose the full title in '[Fototyp] Titel' format."""
        return self._photo_service.format_title(
            self._type_combo.currentText(), self._title_edit.text()
        )

    def _build_date_section(self) -> QGroupBox:
        """Build the 'Fotodatum' section with a text input and precision combo.

        Matches the event editor date pattern: a QLineEdit for flexible date
        entry (ÅÅÅÅ-MM-DD, ÅÅÅÅ-MM, or ÅÅÅÅ) plus a precision QComboBox.
        """
        from slaktbusken.ui.swedish_locale import DATE_PRECISION_LABELS

        group = QGroupBox("Fotodatum")
        layout = QHBoxLayout(group)

        # Date label
        date_label = QLabel("Datum:")
        layout.addWidget(date_label)

        # Date text input
        self._date_input = QLineEdit()
        self._date_input.setPlaceholderText("ÅÅÅÅ-MM-DD, ÅÅÅÅ-MM, eller ÅÅÅÅ")
        self._date_input.setMaxLength(10)
        layout.addWidget(self._date_input)

        # Precision label
        precision_label = QLabel("Precision:")
        layout.addWidget(precision_label)

        # Precision combo
        self._date_precision_combo = QComboBox()
        for key, label in DATE_PRECISION_LABELS.items():
            self._date_precision_combo.addItem(label, key)
        layout.addWidget(self._date_precision_combo)

        return group

    def _load_date_data(self) -> None:
        """Load existing photo date from media item into the date input field."""
        from slaktbusken.services.photo_date_validator import PhotoDateValidator

        photo_date = PhotoDateValidator.from_storage_format(self._media_item.photo_date)

        if photo_date.year is None:
            self._date_input.setText("")
            self._date_precision_combo.setCurrentIndex(0)
        elif photo_date.month is None:
            self._date_input.setText(str(photo_date.year))
            # Set precision to "year"
            idx = self._date_precision_combo.findData("year")
            if idx >= 0:
                self._date_precision_combo.setCurrentIndex(idx)
        elif photo_date.day is None:
            self._date_input.setText(f"{photo_date.year}-{photo_date.month:02d}")
            idx = self._date_precision_combo.findData("month")
            if idx >= 0:
                self._date_precision_combo.setCurrentIndex(idx)
        else:
            self._date_input.setText(
                f"{photo_date.year}-{photo_date.month:02d}-{photo_date.day:02d}"
            )
            idx = self._date_precision_combo.findData("day")
            if idx >= 0:
                self._date_precision_combo.setCurrentIndex(idx)

    def _build_persons_section(self) -> QGroupBox:
        """Build the 'Personer på fotot' section with PersonListWidget.

        Uses the existing PersonListWidget which provides:
        - Person list display (DB-linked and free-text persons)
        - 'Lägg till person' button with duplicate detection
        - 'Ta bort' button (disabled when no person selected)
        - Searchable combo box for database persons
        - Free-text input for non-database persons
        """
        group = QGroupBox("Personer på fotot")
        layout = QVBoxLayout(group)

        self._person_list_widget = PersonListWidget(
            self._project_data, parent=self
        )
        self._person_list_widget.load_for_media_item(self._media_item)
        layout.addWidget(self._person_list_widget)

        return group

    def _build_events_section(self) -> QGroupBox:
        """Build the 'Händelser' section with event list and add/remove buttons."""
        group = QGroupBox("Händelser")
        layout = QVBoxLayout(group)

        # Event list
        self._event_list = QListWidget()
        layout.addWidget(self._event_list)

        # Buttons
        button_layout = QHBoxLayout()
        self._add_event_btn = QPushButton("Lägg till")
        self._remove_event_btn = QPushButton("Ta bort")
        self._remove_event_btn.setEnabled(False)
        button_layout.addWidget(self._add_event_btn)
        button_layout.addWidget(self._remove_event_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Connect signals
        self._event_list.currentRowChanged.connect(self._on_event_selection_changed)
        self._add_event_btn.clicked.connect(self._on_add_event)
        self._remove_event_btn.clicked.connect(self._on_remove_event)

        # Internal state
        self._event_ids: list[str] = []

        # Load existing events
        self._load_events_data()

        return group

    def _load_events_data(self) -> None:
        """Load existing event tags from media item into the event list."""
        self._event_ids = []
        self._event_list.clear()

        for le in self._media_item.linked_entities:
            if le.entity_type == "event":
                event_id = le.entity_id
                self._event_ids.append(event_id)
                label = self._get_event_label(event_id)
                self._event_list.addItem(label)

    def _get_event_label(self, event_id: str) -> str:
        """Get a display label for an event by its ID.

        Format: "Händelsetyp (datum) – Person1, Person2"
        Uses Swedish event type labels and resolves participant names.
        """
        from slaktbusken.ui.swedish_locale import get_event_type_label

        for event in self._project_data.events:
            if event.id == event_id:
                label = get_event_type_label(event.type)
                if event.date:
                    label = f"{label} ({event.date.value})"
                # Add participant names
                names = self._get_participant_names(event)
                if names:
                    label = f"{label} \u2013 {', '.join(names)}"
                return label
        return event_id

    def _get_participant_names(self, event) -> list[str]:
        """Resolve participant person IDs to display names."""
        names: list[str] = []
        for participant in event.participants:
            name = participant.person_id  # fallback
            for person in self._project_data.persons:
                if person.id == participant.person_id:
                    if person.names:
                        n = person.names[0]
                        parts = []
                        if n.given:
                            parts.append(n.given)
                        if n.surname:
                            parts.append(n.surname)
                        if parts:
                            name = " ".join(parts)
                    break
            names.append(name)
        return names

    def _on_event_selection_changed(self, row: int) -> None:
        """Enable/disable 'Ta bort' button based on event selection."""
        self._remove_event_btn.setEnabled(row >= 0)

    def _on_add_event(self) -> None:
        """Show event selection dialog filtered by linked persons."""
        person_ids = self._get_person_ids()
        tagging_service = PhotoTaggingService(self._project_data)
        available_events = tagging_service.get_available_events(
            self._media_item, person_ids
        )

        # Also exclude events already added locally but not yet saved
        available_events = [
            e for e in available_events if e.id not in self._event_ids
        ]

        if not available_events:
            QMessageBox.information(
                self, "Händelser", "Inga tillgängliga händelser."
            )
            return

        # Build labels for selection
        labels = [self._get_event_label(e.id) for e in available_events]
        selected, ok = QInputDialog.getItem(
            self, "Lägg till händelse", "Välj händelse:", labels, 0, False
        )
        if ok and selected:
            idx = labels.index(selected)
            event = available_events[idx]
            self._event_ids.append(event.id)
            self._event_list.addItem(selected)

    def _on_remove_event(self) -> None:
        """Remove the selected event from the list."""
        row = self._event_list.currentRow()
        if row >= 0:
            self._event_list.takeItem(row)
            self._event_ids.pop(row)

    def _get_event_ids(self) -> list[str]:
        """Return current list of event IDs for save logic."""
        return list(self._event_ids)

    def _build_places_section(self) -> QGroupBox:
        """Build the 'Platser' section with place list and add/remove buttons."""
        group = QGroupBox("Platser")
        layout = QVBoxLayout(group)

        # Place list
        self._place_list = QListWidget()
        layout.addWidget(self._place_list)

        # Buttons
        button_layout = QHBoxLayout()
        self._add_place_btn = QPushButton("Lägg till")
        self._remove_place_btn = QPushButton("Ta bort")
        self._remove_place_btn.setEnabled(False)
        button_layout.addWidget(self._add_place_btn)
        button_layout.addWidget(self._remove_place_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Connect signals
        self._place_list.currentRowChanged.connect(self._on_place_selection_changed)
        self._add_place_btn.clicked.connect(self._on_add_place)
        self._remove_place_btn.clicked.connect(self._on_remove_place)

        # Internal state
        self._place_ids: list[str] = []

        # Load existing places
        self._load_places_data()

        return group

    def _load_places_data(self) -> None:
        """Load existing place tags from media item into the place list."""
        self._place_ids = []
        self._place_list.clear()

        for le in self._media_item.linked_entities:
            if le.entity_type == "place":
                place_id = le.entity_id
                self._place_ids.append(place_id)
                label = self._get_place_label(place_id)
                self._place_list.addItem(label)

    def _get_place_label(self, place_id: str) -> str:
        """Get a display label for a place by its ID."""
        for place in self._project_data.places:
            if place.id == place_id:
                return place.name
        return place_id

    def _on_place_selection_changed(self, row: int) -> None:
        """Enable/disable 'Ta bort' button based on place selection."""
        self._remove_place_btn.setEnabled(row >= 0)

    def _on_add_place(self) -> None:
        """Show place selection dialog filtered by already-linked places."""
        from slaktbusken.model.media import LinkedEntity, MediaItem

        # Build a temporary MediaItem-like object reflecting current dialog state
        # so that get_available_places filters out places already added locally
        temp_linked_entities = [
            LinkedEntity(entity_type="place", entity_id=pid)
            for pid in self._place_ids
        ]
        temp_media_item = MediaItem(
            id=self._media_item.id,
            type=self._media_item.type,
            file=self._media_item.file,
            title=self._media_item.title,
            linked_entities=temp_linked_entities,
        )

        tagging_service = PhotoTaggingService(self._project_data)
        available_places = tagging_service.get_available_places(temp_media_item)

        if not available_places:
            QMessageBox.information(
                self, "Platser", "Inga tillgängliga platser."
            )
            return

        # Build labels for selection
        labels = [p.name for p in available_places]
        selected, ok = QInputDialog.getItem(
            self, "Lägg till plats", "Välj plats:", labels, 0, False
        )
        if ok and selected:
            idx = labels.index(selected)
            place = available_places[idx]
            self._place_ids.append(place.id)
            self._place_list.addItem(place.name)

    def _on_remove_place(self) -> None:
        """Remove the selected place from the list."""
        row = self._place_list.currentRow()
        if row >= 0:
            self._place_list.takeItem(row)
            self._place_ids.pop(row)

    def _get_place_ids(self) -> list[str]:
        """Return current list of place IDs for save logic."""
        return list(self._place_ids)

    def _build_notes_section(self) -> QGroupBox:
        """Build the 'Anteckningar' section with a multi-line text edit."""
        group = QGroupBox("Anteckningar")
        layout = QVBoxLayout(group)

        self._notes_edit = QPlainTextEdit()
        self._notes_edit.setMinimumHeight(80)
        self._notes_edit.setPlaceholderText("Skriv anteckningar här...")
        self._notes_edit.textChanged.connect(self._on_notes_text_changed)
        layout.addWidget(self._notes_edit)

        return group

    def _load_notes_data(self) -> None:
        """Load existing notes from media item into the text edit."""
        self._notes_edit.setPlainText(self._media_item.notes)

    def _get_notes(self) -> str:
        """Return the notes text, truncated to 2000 characters."""
        return self._notes_edit.toPlainText()[:2000]

    def _on_notes_text_changed(self) -> None:
        """Enforce the 2000 character limit on notes."""
        text = self._notes_edit.toPlainText()
        if len(text) > 2000:
            self._notes_edit.blockSignals(True)
            cursor = self._notes_edit.textCursor()
            pos = cursor.position()
            self._notes_edit.setPlainText(text[:2000])
            # Restore cursor position (clamped to new length)
            cursor = self._notes_edit.textCursor()
            cursor.setPosition(min(pos, 2000))
            self._notes_edit.setTextCursor(cursor)
            self._notes_edit.blockSignals(False)

    @staticmethod
    def _create_section(title: str) -> QGroupBox:
        """Create a QGroupBox section with a vertical layout."""
        group = QGroupBox(title)
        QVBoxLayout(group)
        return group

    def _get_person_ids(self) -> list[str]:
        """Return current list of person IDs from the persons section."""
        return self._person_list_widget.get_person_ids()

    def _get_person_names(self) -> list[str]:
        """Return current list of free-text person names from the persons section."""
        return self._person_list_widget.get_mentioned_names()

    def _get_date_values(self) -> tuple[int | None, int | None, int | None]:
        """Parse the date input text into (year, month, day).

        Supports formats: ÅÅÅÅ-MM-DD, ÅÅÅÅ-MM, ÅÅÅÅ, or empty.
        """
        text = self._date_input.text().strip()
        if not text:
            return (None, None, None)

        parts = text.split("-")
        try:
            year = int(parts[0]) if len(parts) >= 1 and parts[0] else None
            month = int(parts[1]) if len(parts) >= 2 and parts[1] else None
            day = int(parts[2]) if len(parts) >= 3 and parts[2] else None
        except ValueError:
            return (None, None, None)

        return (year, month, day)

    def _validate_date(self) -> list[str]:
        """Validate the date fields. Returns error messages (empty = valid).

        Shows/hides the date error label if it exists.
        """
        from slaktbusken.services.photo_date_validator import PhotoDateValidator

        year, month, day = self._get_date_values()
        errors = PhotoDateValidator.validate(year, month, day)

        if hasattr(self, "_date_error_label"):
            if errors:
                self._date_error_label.setText(errors[0])
                self._date_error_label.show()
            else:
                self._date_error_label.setText("")
                self._date_error_label.hide()

        return errors

    def _on_save(self) -> None:
        """Validate all sections and save if valid."""
        # Validate title
        title_errors = self._validate_title()
        if title_errors:
            return  # Dialog stays open, error shown at title section

        # Validate date
        date_errors = self._validate_date()
        if date_errors:
            return  # Dialog stays open, error shown at date section

        # All valid — update the MediaItem
        from slaktbusken.model.media import LinkedEntity
        from slaktbusken.services.photo_date_validator import PhotoDateValidator

        self._media_item.title = self._get_composed_title()
        self._media_item.photo_date = PhotoDateValidator.to_storage_format(
            *self._get_date_values()
        )
        self._media_item.notes = self._get_notes()
        self._media_item.mentioned_person_ids = self._get_person_ids()
        self._media_item.mentioned_names = self._get_person_names()

        # Update linked entities for events and places:
        # Remove old event/place links, keep all others
        self._media_item.linked_entities = [
            le
            for le in self._media_item.linked_entities
            if le.entity_type not in ("event", "place")
        ]

        # Add current event links
        for event_id in self._get_event_ids():
            self._media_item.linked_entities.append(
                LinkedEntity(entity_type="event", entity_id=event_id)
            )

        # Add current place links
        for place_id in self._get_place_ids():
            self._media_item.linked_entities.append(
                LinkedEntity(entity_type="place", entity_id=place_id)
            )

        # Sync person linked entities
        self._photo_service.sync_linked_entities(
            self._media_item, self._get_person_ids()
        )

        self._saved = True
        self.accept()

    def get_updated_media_item(self) -> "MediaItem | None":
        """Return the updated MediaItem if saved, or None if cancelled."""
        if not self._saved:
            return None
        return self._media_item
