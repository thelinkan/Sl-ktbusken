"""Tighten bounds confirmation dialog ("Snäva in från grannar").

Presents one preselected, individually deselectable row per DerivedBound from
the inference engine. Shows endpoint, bound name, the stored value or "okänt",
the proposed value and its origin. Nothing is written until confirmation, and
only selected rows are written, leaving `precision`, `event_id`, `note` and
Observations alone.

Derived values for absent bounds are shown read-only with the "härlett" suffix
and are never saved. Zero derived bounds shows "Inga härledda värden att
föreslå." with no dialog.

Validates: Requirements 7.7, 7.8, 7.9, 7.11
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.services.residence_inference import DerivedBound


# ---------------------------------------------------------------------------
# Swedish labels for endpoint and bound names
# ---------------------------------------------------------------------------

_ENDPOINT_LABELS = {
    "start": "Början",
    "end": "Slut",
}

_BOUND_LABELS = {
    "earliest": "Tidigast",
    "latest": "Senast",
}

# Table column indices
_COL_CHECKBOX = 0
_COL_ENDPOINT = 1
_COL_BOUND = 2
_COL_STORED = 3
_COL_PROPOSED = 4
_COL_ORIGIN = 5

_COLUMN_HEADERS = [
    "",           # checkbox
    "Endpunkt",
    "Gräns",
    "Nuvarande värde",
    "Föreslaget värde",
    "Källa",
]

# Message when there are no derived bounds
NO_DERIVED_BOUNDS_MESSAGE = "Inga härledda värden att föreslå."


def has_derived_bounds(derived: list[DerivedBound]) -> bool:
    """Check whether there are any derived bounds to propose.

    When False, the caller should display NO_DERIVED_BOUNDS_MESSAGE
    instead of opening the dialog (Requirement 7.11).
    """
    return len(derived) > 0


def format_harlett_display(derived_bound: DerivedBound) -> str:
    """Format a derived bound value for read-only display with härlett suffix.

    Used in the editor to show derived values for absent stored bounds
    (Requirement 7.7). The value is read-only and never saved.
    """
    return f"{derived_bound.value} (härlett)"


class TightenBoundsDialog(QDialog):
    """Confirmation dialog for writing inferred bound values.

    Presents one row per DerivedBound with a checkbox, endpoint label,
    bound name, stored value (or "okänt"), proposed value, and origin.
    All rows are preselected. The user can deselect any row individually.
    Only selected rows are applied on confirmation.

    Args:
        derived_bounds: List of DerivedBound from infer_bounds.
        stored_values: Dict mapping (endpoint, bound) tuples to the current
            stored value (or None if absent).
        parent: Optional parent widget.
    """

    def __init__(
        self,
        derived_bounds: list[DerivedBound],
        stored_values: dict[tuple[str, str], Optional[str]],
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the tighten bounds confirmation dialog.

        Args:
            derived_bounds: The inferred bounds to present for confirmation.
            stored_values: Mapping of (endpoint, bound) → stored value or None.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._derived_bounds = derived_bounds
        self._stored_values = stored_values

        self.setWindowTitle("Snäva in från grannar")
        self.setMinimumWidth(600)

        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def selected_bounds(self) -> list[DerivedBound]:
        """Return the list of DerivedBound entries whose rows are checked.

        Only these should be written to the Residence_Fact on confirmation
        (Requirement 7.9).
        """
        selected: list[DerivedBound] = []
        for row in range(self._table.rowCount()):
            item = self._table.item(row, _COL_CHECKBOX)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                selected.append(self._derived_bounds[row])
        return selected

    # ------------------------------------------------------------------
    # Private: UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the dialog layout with the bounds table and buttons."""
        layout = QVBoxLayout(self)

        # Description label
        description = QLabel(
            "Välj vilka härledda värden som ska skrivas till boendet:"
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        # Bounds table
        self._table = QTableWidget()
        self._table.setColumnCount(len(_COLUMN_HEADERS))
        self._table.setHorizontalHeaderLabels(_COLUMN_HEADERS)
        self._table.setRowCount(len(self._derived_bounds))

        # Populate rows
        for row, db in enumerate(self._derived_bounds):
            self._set_row(row, db)

        # Column sizing
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(
            _COL_CHECKBOX, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            _COL_ENDPOINT, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            _COL_BOUND, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            _COL_STORED, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            _COL_PROPOSED, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            _COL_ORIGIN, QHeaderView.ResizeMode.Stretch
        )

        self._table.setSelectionMode(
            QTableWidget.SelectionMode.NoSelection
        )

        layout.addWidget(self._table)

        # Button box
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._button_box.button(
            QDialogButtonBox.StandardButton.Ok
        ).setText("Bekräfta")
        self._button_box.button(
            QDialogButtonBox.StandardButton.Cancel
        ).setText("Avbryt")
        self._button_box.accepted.connect(self.accept)
        self._button_box.rejected.connect(self.reject)

        layout.addWidget(self._button_box)

    def _set_row(self, row: int, db: DerivedBound) -> None:
        """Populate one row of the table for a DerivedBound."""
        # Checkbox column — preselected (Requirement 7.8)
        check_item = QTableWidgetItem()
        check_item.setFlags(
            Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
        )
        check_item.setCheckState(Qt.CheckState.Checked)
        self._table.setItem(row, _COL_CHECKBOX, check_item)

        # Endpoint label
        endpoint_label = _ENDPOINT_LABELS.get(db.endpoint, db.endpoint)
        endpoint_item = QTableWidgetItem(endpoint_label)
        endpoint_item.setFlags(
            endpoint_item.flags() & ~Qt.ItemFlag.ItemIsEditable
        )
        self._table.setItem(row, _COL_ENDPOINT, endpoint_item)

        # Bound name
        bound_label = _BOUND_LABELS.get(db.bound, db.bound)
        bound_item = QTableWidgetItem(bound_label)
        bound_item.setFlags(bound_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._table.setItem(row, _COL_BOUND, bound_item)

        # Stored value or "okänt"
        stored = self._stored_values.get((db.endpoint, db.bound))
        stored_display = stored if stored else "okänt"
        stored_item = QTableWidgetItem(stored_display)
        stored_item.setFlags(stored_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._table.setItem(row, _COL_STORED, stored_item)

        # Proposed value
        proposed_item = QTableWidgetItem(db.value)
        proposed_item.setFlags(
            proposed_item.flags() & ~Qt.ItemFlag.ItemIsEditable
        )
        self._table.setItem(row, _COL_PROPOSED, proposed_item)

        # Origin (neighbouring place name or event label)
        origin_item = QTableWidgetItem(db.origin_label)
        origin_item.setFlags(
            origin_item.flags() & ~Qt.ItemFlag.ItemIsEditable
        )
        self._table.setItem(row, _COL_ORIGIN, origin_item)
