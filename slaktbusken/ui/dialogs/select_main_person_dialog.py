"""Dialog för att välja huvudperson efter GEDCOM-import.

Visar en sökbar lista med alla importerade personer sorterade efter
efternamn och förnamn. Användaren kan filtrera listan med ett sökfält
och välja en person som projektets huvudperson.

Validates: Requirements 4.3
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.event import Event
from slaktbusken.model.person import Person
from slaktbusken.ui.person_list_panel import get_person_birth_death_years


class SelectMainPersonDialog(QDialog):
    """Dialog som låter användaren välja huvudperson för projektet.

    Presenterar en filtrerad lista av personer med namn och
    födelseår/dödsår. Sorterad efter efternamn sedan förnamn.

    Args:
        persons: Lista med alla personer i projektet.
        events: Lista med alla händelser i projektet (för att hämta årtal).
        parent: Valfri föräldrawidget.
    """

    def __init__(
        self,
        persons: list[Person],
        events: list[Event],
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initiera dialogen med personlista och händelser.

        Args:
            persons: Alla personer i projektet.
            events: Alla händelser i projektet.
            parent: Valfri föräldrawidget.
        """
        super().__init__(parent)
        self.setWindowTitle("Välj huvudperson")
        self.setMinimumWidth(450)
        self.setMinimumHeight(400)

        self._persons = persons
        self._events = events
        self._selected_person_id: Optional[str] = None

        # Build sorted display data
        self._display_data = self._build_display_data()

        self._setup_ui()
        self._populate_list()
        self._connect_signals()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def selected_person_id(self) -> Optional[str]:
        """ID för den valda personen, eller None om ingen valdes."""
        return self._selected_person_id

    # ------------------------------------------------------------------
    # Private setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Bygg dialogens UI-layout."""
        layout = QVBoxLayout(self)

        # Instruction label
        info_label = QLabel(
            "Välj den person som ska vara huvudperson i projektet.\n"
            "Denna person visas som startpunkt i släktdiagrammet."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Search field
        self._search_field = QLineEdit()
        self._search_field.setPlaceholderText("Sök person...")
        self._search_field.setClearButtonEnabled(True)
        layout.addWidget(self._search_field)

        # Person list
        self._list_widget = QListWidget()
        layout.addWidget(self._list_widget)

        # Button box
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText("Välj")
            ok_button.setEnabled(False)
        layout.addWidget(self._button_box)

    def _connect_signals(self) -> None:
        """Koppla signaler för sökning och val."""
        self._search_field.textChanged.connect(self._on_search_changed)
        self._list_widget.currentItemChanged.connect(self._on_selection_changed)
        self._list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._button_box.accepted.connect(self._on_accept)
        self._button_box.rejected.connect(self.reject)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_display_data(self) -> list[tuple[str, str, str]]:
        """Bygg sorterad visningsdata från personlistan.

        Returns:
            Lista av tupler (person_id, visningstext, sökbar text i lowercase).
        """
        items: list[tuple[str, str, str, str]] = []
        for person in self._persons:
            if not person.names:
                continue
            first_name = person.names[0]
            surname = first_name.surname
            given = first_name.given

            birth_year, death_year = get_person_birth_death_years(
                person, self._events
            )

            # Format: "Efternamn, Förnamn (född–död)"
            name_part = f"{surname}, {given}"
            if birth_year or death_year:
                birth = birth_year if birth_year else "?"
                death = death_year if death_year else "?"
                display_text = f"{name_part} ({birth}\u2013{death})"
            else:
                display_text = name_part

            # Searchable text includes all parts
            search_text = f"{surname} {given} {birth_year} {death_year}".lower()

            items.append((person.id, display_text, search_text, surname.lower() + given.lower()))

        # Sort by surname then given name
        items.sort(key=lambda x: x[3])

        return [(pid, display, search) for pid, display, search, _ in items]

    def _populate_list(self, filter_text: str = "") -> None:
        """Fyll listan med personer, filtrerade efter söktext.

        Args:
            filter_text: Text att filtrera på (case-insensitive substring).
        """
        self._list_widget.clear()
        filter_lower = filter_text.lower().strip()

        for person_id, display_text, search_text in self._display_data:
            if filter_lower and filter_lower not in search_text:
                continue
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, person_id)
            self._list_widget.addItem(item)

        # Update OK button state
        self._update_ok_button()

    def _update_ok_button(self) -> None:
        """Aktivera/avaktivera OK-knappen baserat på val."""
        ok_button = self._button_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            current = self._list_widget.currentItem()
            ok_button.setEnabled(current is not None)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_search_changed(self, text: str) -> None:
        """Hantera ändring i sökfältet.

        Args:
            text: Nuvarande söktext.
        """
        self._populate_list(text)

    def _on_selection_changed(
        self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]
    ) -> None:
        """Hantera ändring av markerad person.

        Args:
            current: Nytt markerat objekt.
            previous: Tidigare markerat objekt.
        """
        self._update_ok_button()

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Hantera dubbelklick — välj och stäng direkt.

        Args:
            item: Det dubbelklickade objektet.
        """
        if item is not None:
            person_id = item.data(Qt.ItemDataRole.UserRole)
            if person_id:
                self._selected_person_id = person_id
                self.accept()

    def _on_accept(self) -> None:
        """Hantera OK-klick — spara vald person och stäng."""
        current = self._list_widget.currentItem()
        if current is not None:
            person_id = current.data(Qt.ItemDataRole.UserRole)
            if person_id:
                self._selected_person_id = person_id
                self.accept()
