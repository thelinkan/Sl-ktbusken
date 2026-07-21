"""Reusable widget for searching and selecting a person by name.

Provides a QLineEdit with QCompleter for searching persons, emitting
signals on selection and clearing. Used for linking entities (e.g.
DNA profiles) to a specific person.

Covers Requirements 4.3, 4.4.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCompleter,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)

from slaktbusken.model.person import Person


def _format_person_name(person: Person) -> str:
    """Return display name for a person: 'given surname' from first name entry."""
    if not person.names:
        return f"(Person {person.id})"
    name = person.names[0]
    given = name.given.replace("*", "")
    return f"{given} {name.surname}".strip()


class PersonSearchWidget(QWidget):
    """Widget for searching and selecting a single person by name.

    Combines a QLineEdit with a QCompleter for searching persons.
    Emits ``person_selected`` when a person is chosen from the completer,
    and ``person_cleared`` when the selection is cleared.

    Args:
        parent: Optional parent widget.
    """

    person_selected = Signal(str)  # Emits person_id
    person_cleared = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._persons: list[Person] = []
        self._name_to_id: dict[str, str] = {}
        self._selected_person_id: Optional[str] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the UI layout."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._line_edit = QLineEdit()
        self._line_edit.setPlaceholderText("Sök person...")
        layout.addWidget(self._line_edit, stretch=1)

        self._clear_btn = QPushButton("✕")
        self._clear_btn.setFixedWidth(28)
        self._clear_btn.setToolTip("Rensa val")
        self._clear_btn.clicked.connect(self.clear_selection)
        layout.addWidget(self._clear_btn)

        # Set up completer
        self._completer = QCompleter([], self)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.activated.connect(self._on_completer_activated)
        self._line_edit.setCompleter(self._completer)

        # Detect manual clearing of the text field
        self._line_edit.textChanged.connect(self._on_text_changed)

    def set_persons(self, persons: list[Person]) -> None:
        """Update the available persons list for search/completion.

        Args:
            persons: List of Person objects to populate the completer.
        """
        self._persons = persons
        self._name_to_id.clear()

        names: list[str] = []
        for person in persons:
            display = _format_person_name(person)
            # Handle duplicate display names by appending id
            if display in self._name_to_id:
                display = f"{display} [{person.id}]"
            self._name_to_id[display] = person.id
            names.append(display)

        model = self._completer.model()
        if model is not None:
            model.setStringList(names)
        else:
            from PySide6.QtCore import QStringListModel

            self._completer.setModel(QStringListModel(names, self))

    def set_selected_person(
        self, person_id: Optional[str], persons: list[Person]
    ) -> None:
        """Pre-populate the widget with a person's name.

        Updates the persons list and sets the displayed text to match
        the given person_id.

        Args:
            person_id: The ID of the person to select, or None to clear.
            persons: List of Person objects to populate the completer.
        """
        self.set_persons(persons)

        if person_id is None:
            self.clear_selection()
            return

        self._selected_person_id = person_id

        # Find the display name for this person_id
        for display_name, pid in self._name_to_id.items():
            if pid == person_id:
                # Block signals to avoid emitting person_cleared during setText
                self._line_edit.blockSignals(True)
                self._line_edit.setText(display_name)
                self._line_edit.blockSignals(False)
                return

        # Person not found in list — clear
        self._selected_person_id = None

    def selected_person_id(self) -> Optional[str]:
        """Return the currently selected person's ID, or None if no selection."""
        return self._selected_person_id

    def clear_selection(self) -> None:
        """Clear the current selection and emit person_cleared signal."""
        had_selection = self._selected_person_id is not None
        self._selected_person_id = None
        self._line_edit.blockSignals(True)
        self._line_edit.clear()
        self._line_edit.blockSignals(False)
        if had_selection:
            self.person_cleared.emit()

    def _on_completer_activated(self, text: str) -> None:
        """Handle selection from the completer popup."""
        person_id = self._name_to_id.get(text)
        if person_id is not None:
            self._selected_person_id = person_id
            # Ensure line edit shows the selected name (block signals to
            # avoid triggering _on_text_changed during programmatic update)
            self._line_edit.blockSignals(True)
            self._line_edit.setText(text)
            self._line_edit.blockSignals(False)
            self.person_selected.emit(person_id)

    def _on_text_changed(self, text: str) -> None:
        """Handle manual text changes — detect clearing."""
        if not text and self._selected_person_id is not None:
            self._selected_person_id = None
            self.person_cleared.emit()
