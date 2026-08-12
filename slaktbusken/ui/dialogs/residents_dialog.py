"""Residents dialog — place/year query over Residence_Facts.

Presents a QDialog where the user selects a place and enters a year, then
displays all matching residents via :func:`residents_of_place` with support
for role-based grouping (Requirement 8.10) and the place chain column
(Requirement 8.6).

Requirements: 8.1, 8.5, 8.6, 8.10
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.project import ProjectData
from slaktbusken.services.residence_query import (
    LABEL_ROLE_MISSING,
    ResidentEntry,
    residents_grouped_by_role,
    residents_of_place,
)


class ResidentsDialog(QDialog):
    """Dialog querying and displaying residents of a place for a given year.

    The user selects a place from a searchable combo box and enters a year,
    then clicks "Sök" to populate a results table. The table shows person
    display name, place chain, interval, label (säker/möjlig), and role.

    A "Gruppera efter roll" toggle switches to a role-grouped view where
    entries are partitioned by their exact ``role_in_household`` text, with
    empty roles in a final "Roll saknas" group.

    Args:
        parent: Optional parent widget.
        project_data: The active project data to query.
    """

    # Column indices for the flat results table
    _COL_PERSON = 0
    _COL_PLACE_CHAIN = 1
    _COL_INTERVAL = 2
    _COL_LABEL = 3
    _COL_ROLE = 4
    _NUM_COLUMNS = 5

    _COLUMN_HEADERS = ["Person", "Platskedja", "Period", "Säkerhet", "Roll"]

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        project_data: Optional[ProjectData] = None,
    ) -> None:
        super().__init__(parent)
        self._project_data = project_data or ProjectData()
        self._last_entries: list[ResidentEntry] = []
        self._grouped = False

        self.setWindowTitle("Boende på plats")
        self.setMinimumWidth(700)
        self.setMinimumHeight(450)

        self._setup_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the dialog layout."""
        layout = QVBoxLayout(self)

        # --- Query row ---
        query_group = QGroupBox("Sök boende")
        query_layout = QHBoxLayout(query_group)

        # Place combo
        place_label = QLabel("Plats:")
        self._place_combo = QComboBox()
        self._place_combo.setEditable(True)
        self._place_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._place_combo.setMinimumWidth(250)
        self._populate_place_combo()

        # Year spin box
        year_label = QLabel("År:")
        self._year_spin = QSpinBox()
        self._year_spin.setRange(1000, 2999)
        self._year_spin.setValue(1800)

        # Search button
        self._search_button = QPushButton("Sök")

        # Group toggle
        self._group_button = QPushButton("Gruppera efter roll")
        self._group_button.setCheckable(True)

        query_layout.addWidget(place_label)
        query_layout.addWidget(self._place_combo, 1)
        query_layout.addWidget(year_label)
        query_layout.addWidget(self._year_spin)
        query_layout.addWidget(self._search_button)
        query_layout.addWidget(self._group_button)

        layout.addWidget(query_group)

        # --- Results summary ---
        self._summary_label = QLabel("")
        layout.addWidget(self._summary_label)

        # --- Results table ---
        self._table = QTableWidget()
        self._table.setColumnCount(self._NUM_COLUMNS)
        self._table.setHorizontalHeaderLabels(self._COLUMN_HEADERS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.verticalHeader().setVisible(False)

        layout.addWidget(self._table)

    def _connect_signals(self) -> None:
        """Wire button clicks."""
        self._search_button.clicked.connect(self._on_search)
        self._group_button.toggled.connect(self._on_group_toggled)

    # ------------------------------------------------------------------
    # Place combo population
    # ------------------------------------------------------------------

    def _populate_place_combo(self) -> None:
        """Fill the place combo with all places from the project."""
        self._place_combo.clear()
        self._place_combo.addItem("(välj plats)", "")

        places_with_display: list[tuple[str, str]] = []
        for place in self._project_data.places:
            display = self._format_place_display(place.id)
            places_with_display.append((display, place.id))
        places_with_display.sort(key=lambda x: x[0].lower())

        place_names: list[str] = []
        for display, place_id in places_with_display:
            self._place_combo.addItem(display, place_id)
            place_names.append(display)

        # Substring completer for searching
        completer = QCompleter(place_names, self._place_combo)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._place_combo.setCompleter(completer)

    def _format_place_display(self, place_id: str) -> str:
        """Format a place name with its parent hierarchy for display."""
        places_by_id = {p.id: p for p in self._project_data.places}
        place = places_by_id.get(place_id)
        if place is None:
            return place_id

        parts = [place.name]
        current = place
        visited: set[str] = {place.id}
        while current.parent_place_id and current.parent_place_id not in visited:
            parent = places_by_id.get(current.parent_place_id)
            if parent is None:
                break
            visited.add(parent.id)
            parts.append(parent.name)
            current = parent

        return ", ".join(parts)

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    def _on_search(self) -> None:
        """Execute the residents query and display results."""
        place_id = self._place_combo.currentData()
        if not place_id:
            self._summary_label.setText("Välj en plats.")
            self._table.setRowCount(0)
            self._last_entries = []
            return

        year = self._year_spin.value()
        self._last_entries = residents_of_place(
            self._project_data, place_id, year
        )

        place_name = self._place_combo.currentText()
        count = len(self._last_entries)
        self._summary_label.setText(
            f"{count} boende på {place_name} år {year}"
        )

        if self._grouped:
            self._display_grouped(self._last_entries)
        else:
            self._display_flat(self._last_entries)

    # ------------------------------------------------------------------
    # Display modes
    # ------------------------------------------------------------------

    def _on_group_toggled(self, checked: bool) -> None:
        """Toggle between flat and role-grouped display."""
        self._grouped = checked
        if self._last_entries:
            if checked:
                self._display_grouped(self._last_entries)
            else:
                self._display_flat(self._last_entries)

    def _display_flat(self, entries: list[ResidentEntry]) -> None:
        """Show entries in a flat table without grouping."""
        self._table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            self._set_row(row, entry)

    def _display_grouped(self, entries: list[ResidentEntry]) -> None:
        """Show entries grouped by role with group headers as spanning rows."""
        groups = residents_grouped_by_role(entries)

        # Count total rows: one header per group plus one per entry
        total_rows = sum(1 + len(members) for _, members in groups)
        self._table.setRowCount(total_rows)

        row = 0
        for group_label, members in groups:
            # Group header row
            header_item = QTableWidgetItem(group_label)
            header_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            font = header_item.font()
            font.setBold(True)
            header_item.setFont(font)
            self._table.setItem(row, 0, header_item)
            self._table.setSpan(row, 0, 1, self._NUM_COLUMNS)
            row += 1

            # Entry rows within the group
            for entry in members:
                self._set_row(row, entry)
                row += 1

    def _set_row(self, row: int, entry: ResidentEntry) -> None:
        """Populate a single table row from a ResidentEntry."""
        person_item = QTableWidgetItem(entry.person_display)
        person_item.setData(Qt.ItemDataRole.UserRole, entry.person_id)

        # Place chain: show the chain joined with " > "
        chain_text = " \u203a ".join(entry.place_chain) if entry.place_chain else entry.place_display
        chain_item = QTableWidgetItem(chain_text)

        interval_item = QTableWidgetItem(entry.interval_display)

        label_text = entry.label
        if entry.undated:
            label_text = f"{entry.label} (odaterat)"
        label_item = QTableWidgetItem(label_text)

        role_item = QTableWidgetItem(entry.role_in_household)

        self._table.setItem(row, self._COL_PERSON, person_item)
        self._table.setItem(row, self._COL_PLACE_CHAIN, chain_item)
        self._table.setItem(row, self._COL_INTERVAL, interval_item)
        self._table.setItem(row, self._COL_LABEL, label_item)
        self._table.setItem(row, self._COL_ROLE, role_item)

    # ------------------------------------------------------------------
    # Public accessors for testing
    # ------------------------------------------------------------------

    @property
    def place_combo(self) -> QComboBox:
        """The place selection combo box."""
        return self._place_combo

    @property
    def year_spin(self) -> QSpinBox:
        """The year spin box."""
        return self._year_spin

    @property
    def search_button(self) -> QPushButton:
        """The search button."""
        return self._search_button

    @property
    def group_button(self) -> QPushButton:
        """The role grouping toggle button."""
        return self._group_button

    @property
    def results_table(self) -> QTableWidget:
        """The results table widget."""
        return self._table

    @property
    def summary_label(self) -> QLabel:
        """The summary label showing result count."""
        return self._summary_label

    @property
    def last_entries(self) -> list[ResidentEntry]:
        """The last query result entries."""
        return self._last_entries
