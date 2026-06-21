"""Reusable widget for managing persons mentioned in a photo.

Displays a list of persons (both database-linked and free-text),
provides a searchable dropdown for selecting existing persons from
the database, and a free-text input for non-database persons.

Covers Requirements 5.1–5.8, 9.4–9.6.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.media import MediaItem
from slaktbusken.model.person import Person
from slaktbusken.model.project import ProjectData


def _person_display_name(person: Person) -> str:
    """Return display name for a person: 'given surname' from first name entry."""
    if not person.names:
        return f"(Person {person.id})"
    name = person.names[0]
    return f"{name.given} {name.surname}".strip()


class PersonListWidget(QWidget):
    """Widget for managing persons mentioned in a photo.

    Emits `persons_changed` whenever the person list is modified.

    Args:
        project_data: The project data containing all persons.
        parent: Optional parent widget.
    """

    persons_changed = Signal()

    # Max length for free-text person names
    MAX_FREE_TEXT_LENGTH = 200

    def __init__(
        self,
        project_data: ProjectData,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._project_data = project_data

        # Internal state: current lists
        self._current_person_ids: list[str] = []
        self._current_mentioned_names: list[str] = []

        # Map person_id -> Person for quick lookup
        self._persons_by_id: dict[str, Person] = {
            p.id: p for p in project_data.persons
        }

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the UI layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Section label
        section_label = QLabel("Personer på fotot")
        section_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(section_label)

        # Person list display
        self._list_widget = QListWidget()
        self._list_widget.setMaximumHeight(120)
        layout.addWidget(self._list_widget)

        # Remove button
        remove_layout = QHBoxLayout()
        remove_layout.addStretch()
        self._remove_btn = QPushButton("Ta bort")
        self._remove_btn.setEnabled(False)
        self._remove_btn.clicked.connect(self._on_remove_person)
        remove_layout.addWidget(self._remove_btn)
        layout.addLayout(remove_layout)

        # Connect list selection to enable/disable remove button
        self._list_widget.currentItemChanged.connect(self._on_selection_changed)

        # --- Add DB person section ---
        db_label = QLabel("Lägg till person från databasen:")
        layout.addWidget(db_label)

        self._person_combo = QComboBox()
        self._person_combo.setEditable(True)
        self._person_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._person_combo.lineEdit().setPlaceholderText(
            "Sök person..."
        )
        self._populate_person_combo()

        # Set up completer for filtering
        completer = QCompleter(
            [self._person_combo.itemText(i) for i in range(self._person_combo.count())]
        )
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._person_combo.setCompleter(completer)

        db_add_layout = QHBoxLayout()
        db_add_layout.addWidget(self._person_combo, stretch=1)
        self._add_db_btn = QPushButton("Lägg till")
        self._add_db_btn.clicked.connect(self._on_add_db_person)
        db_add_layout.addWidget(self._add_db_btn)
        layout.addLayout(db_add_layout)

        # --- Add free-text person section ---
        free_label = QLabel("Lägg till person (ej i databasen):")
        layout.addWidget(free_label)

        free_add_layout = QHBoxLayout()
        self._free_text_input = QLineEdit()
        self._free_text_input.setPlaceholderText("Ange namn (max 200 tecken)")
        self._free_text_input.setMaxLength(self.MAX_FREE_TEXT_LENGTH)
        free_add_layout.addWidget(self._free_text_input, stretch=1)
        self._add_free_btn = QPushButton("Lägg till")
        self._add_free_btn.clicked.connect(self._on_add_free_person)
        free_add_layout.addWidget(self._add_free_btn)
        layout.addLayout(free_add_layout)

        # Allow Enter key in free text input to add
        self._free_text_input.returnPressed.connect(self._on_add_free_person)

    def _populate_person_combo(self) -> None:
        """Populate the combo box with all persons from project data."""
        self._person_combo.clear()
        self._person_combo.addItem("", "")  # Empty placeholder item
        for person in self._project_data.persons:
            display = _person_display_name(person)
            self._person_combo.addItem(display, person.id)

    def load_for_media_item(self, media_item: MediaItem) -> None:
        """Load current persons from a media item.

        Args:
            media_item: The media item whose mentioned persons to display.
        """
        self._current_person_ids = list(media_item.mentioned_person_ids)
        self._current_mentioned_names = list(media_item.mentioned_names)
        self._refresh_list()

    def get_person_ids(self) -> list[str]:
        """Return current list of mentioned person IDs."""
        return list(self._current_person_ids)

    def get_mentioned_names(self) -> list[str]:
        """Return current list of free-text names."""
        return list(self._current_mentioned_names)

    def clear(self) -> None:
        """Clear the widget state."""
        self._current_person_ids.clear()
        self._current_mentioned_names.clear()
        self._list_widget.clear()
        self._free_text_input.clear()
        self._person_combo.setCurrentIndex(0)

    def _refresh_list(self) -> None:
        """Refresh the QListWidget from internal state."""
        self._list_widget.clear()

        # Add database-linked persons
        for pid in self._current_person_ids:
            person = self._persons_by_id.get(pid)
            if person:
                display = _person_display_name(person)
            else:
                display = f"(Okänd person: {pid})"

            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, ("db", pid))
            self._list_widget.addItem(item)

        # Add free-text persons
        for name in self._current_mentioned_names:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, ("free", name))
            # Style free-text entries in italic
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
            self._list_widget.addItem(item)

    def _on_selection_changed(self) -> None:
        """Enable/disable remove button based on selection."""
        self._remove_btn.setEnabled(
            self._list_widget.currentItem() is not None
        )

    def _on_add_db_person(self) -> None:
        """Add a database person from the combo box."""
        index = self._person_combo.currentIndex()
        if index <= 0:
            # Nothing selected or placeholder
            return

        person_id = self._person_combo.currentData()
        if not person_id:
            return

        # Duplicate detection
        if person_id in self._current_person_ids:
            QMessageBox.information(
                self,
                "Redan tillagd",
                "Denna person finns redan i listan.",
            )
            return

        self._current_person_ids.append(person_id)
        self._refresh_list()
        self._person_combo.setCurrentIndex(0)
        self.persons_changed.emit()

    def _on_add_free_person(self) -> None:
        """Add a free-text person name."""
        name = self._free_text_input.text().strip()
        if not name:
            return

        if len(name) > self.MAX_FREE_TEXT_LENGTH:
            QMessageBox.warning(
                self,
                "För långt namn",
                f"Namnet får vara max {self.MAX_FREE_TEXT_LENGTH} tecken.",
            )
            return

        # Duplicate detection (exact match)
        if name in self._current_mentioned_names:
            QMessageBox.information(
                self,
                "Redan tillagd",
                "Denna person finns redan i listan.",
            )
            return

        self._current_mentioned_names.append(name)
        self._refresh_list()
        self._free_text_input.clear()
        self.persons_changed.emit()

    def _on_remove_person(self) -> None:
        """Remove the selected person from the list."""
        current_item = self._list_widget.currentItem()
        if current_item is None:
            return

        data = current_item.data(Qt.ItemDataRole.UserRole)
        if data is None:
            return

        entry_type, value = data

        if entry_type == "db":
            if value in self._current_person_ids:
                self._current_person_ids.remove(value)
        elif entry_type == "free":
            if value in self._current_mentioned_names:
                self._current_mentioned_names.remove(value)

        self._refresh_list()
        self.persons_changed.emit()
