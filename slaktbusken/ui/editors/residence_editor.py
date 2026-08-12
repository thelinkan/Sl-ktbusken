"""Residence editor widget ("Boende").

Provides a form-based editor for ResidenceFact records: four endpoint bound
fields, a free-text household role field with non-binding suggestions, and an
Observation table ordered by observed_from then observed_to.

This module implements the widget structure and fields only. Event selectors,
edit operation wiring, dialogs, bulk panel and person-editor tab integration
are separate tasks.

All UI text is in Swedish.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.date_span import is_valid_iso
from slaktbusken.model.residence import (
    Observation,
    ResidenceFact,
    normalize_role_in_household,
)
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.swedish_locale import format_observation_span

logger = logging.getLogger(__name__)

# Maximum allowed code points for role_in_household after trimming.
_ROLE_MAX_LENGTH = 100

# Minimum visible rows for the Observation table.
_OBSERVATION_MIN_ROWS = 15

# Column indices for the Observation table.
_COL_SOURCE_TITLE = 0
_COL_SPAN = 1
_COL_PAGE_NOTE = 2


class ResidenceEditor(QWidget):
    """Editor widget for ResidenceFact records.

    Displays and edits a ResidenceFact with four endpoint bound fields,
    a household role field with project-derived suggestions, and an
    Observation table showing source title, span, and page_note.

    Signals:
        save_requested: Emitted when a successful save is completed.
        cancel_requested: Emitted when the user cancels editing.

    Args:
        project_data: The current project data containing all entities.
        residence: Optional existing ResidenceFact to edit.
        parent: Optional parent widget.
    """

    save_requested = Signal()
    cancel_requested = Signal()

    def __init__(
        self,
        project_data: ProjectData,
        residence: Optional[ResidenceFact] = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the residence editor.

        Args:
            project_data: The current project data containing all entities.
            residence: Optional existing ResidenceFact to edit.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._project_data = project_data
        self._residence = residence

        self._setup_ui()
        self._setup_role_completer()

        if self._residence is not None:
            self._load_residence()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def residence(self) -> Optional[ResidenceFact]:
        """The residence being edited, or None for a new one."""
        return self._residence

    def validate_role(self) -> bool:
        """Check whether the current role_in_household value is within limits.

        Returns True if valid (≤100 code points after trim), False otherwise.
        The entered text is always kept unchanged in the field.
        """
        text = normalize_role_in_household(self._role_edit.text())
        if len(text) > _ROLE_MAX_LENGTH:
            self._role_error_label.setText(
                "Roll i hushållet får vara högst 100 tecken."
            )
            self._role_error_label.setVisible(True)
            return False
        self._role_error_label.setVisible(False)
        return True

    def get_role_in_household(self) -> str:
        """Return the normalized role_in_household value from the field."""
        return normalize_role_in_household(self._role_edit.text())

    def get_start_earliest(self) -> Optional[str]:
        """Return the start.earliest field value, or None if empty/invalid."""
        return self._get_bound_value(self._start_earliest_edit)

    def get_start_latest(self) -> Optional[str]:
        """Return the start.latest field value, or None if empty/invalid."""
        return self._get_bound_value(self._start_latest_edit)

    def get_end_earliest(self) -> Optional[str]:
        """Return the end.earliest field value, or None if empty/invalid."""
        return self._get_bound_value(self._end_earliest_edit)

    def get_end_latest(self) -> Optional[str]:
        """Return the end.latest field value, or None if empty/invalid."""
        return self._get_bound_value(self._end_latest_edit)

    def set_observations(self, observations: Sequence[Observation]) -> None:
        """Populate the Observation table with the given list.

        Observations are displayed ordered by observed_from then observed_to.
        """
        sorted_obs = sorted(
            observations, key=lambda o: (o.observed_from, o.observed_to)
        )
        self._observations_table.setRowCount(len(sorted_obs))
        for row, obs in enumerate(sorted_obs):
            self._set_observation_row(row, obs)

    # ------------------------------------------------------------------
    # Private: UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the editor layout with bound fields, role field, and table."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # --- Endpoint bounds group ---
        bounds_group = QGroupBox("Period")
        bounds_form = QFormLayout(bounds_group)

        self._start_earliest_edit = QLineEdit()
        self._start_earliest_edit.setPlaceholderText("ÅÅÅÅ, ÅÅÅÅ-MM eller ÅÅÅÅ-MM-DD")
        bounds_form.addRow("Tidigast början:", self._start_earliest_edit)

        self._start_latest_edit = QLineEdit()
        self._start_latest_edit.setPlaceholderText("ÅÅÅÅ, ÅÅÅÅ-MM eller ÅÅÅÅ-MM-DD")
        bounds_form.addRow("Senast början:", self._start_latest_edit)

        self._end_earliest_edit = QLineEdit()
        self._end_earliest_edit.setPlaceholderText("ÅÅÅÅ, ÅÅÅÅ-MM eller ÅÅÅÅ-MM-DD")
        bounds_form.addRow("Tidigast slut:", self._end_earliest_edit)

        self._end_latest_edit = QLineEdit()
        self._end_latest_edit.setPlaceholderText("ÅÅÅÅ, ÅÅÅÅ-MM eller ÅÅÅÅ-MM-DD")
        bounds_form.addRow("Senast slut:", self._end_latest_edit)

        main_layout.addWidget(bounds_group)

        # --- Role in household ---
        role_group = QGroupBox("Hushållsroll")
        role_layout = QVBoxLayout(role_group)

        role_row = QHBoxLayout()
        role_label = QLabel("Roll i hushållet:")
        self._role_edit = QLineEdit()
        self._role_edit.setPlaceholderText("t.ex. husbonde, piga, inhyses")
        role_row.addWidget(role_label)
        role_row.addWidget(self._role_edit)
        role_layout.addLayout(role_row)

        self._role_error_label = QLabel()
        self._role_error_label.setStyleSheet("color: red;")
        self._role_error_label.setVisible(False)
        role_layout.addWidget(self._role_error_label)

        main_layout.addWidget(role_group)

        # --- Observations table ---
        obs_group = QGroupBox("Observationer")
        obs_layout = QVBoxLayout(obs_group)

        self._observations_table = QTableWidget()
        self._observations_table.setColumnCount(3)
        self._observations_table.setHorizontalHeaderLabels(
            ["Källa", "Period", "Sidanteckning"]
        )
        self._observations_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._observations_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._observations_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )

        # Size for at least 15 visible rows
        row_height = self._observations_table.verticalHeader().defaultSectionSize()
        header_height = self._observations_table.horizontalHeader().height()
        self._observations_table.setMinimumHeight(
            row_height * _OBSERVATION_MIN_ROWS + header_height + 4
        )

        # Stretch source title column, reasonable widths for others
        header = self._observations_table.horizontalHeader()
        header.setSectionResizeMode(
            _COL_SOURCE_TITLE, QHeaderView.ResizeMode.Stretch
        )
        header.setSectionResizeMode(
            _COL_SPAN, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            _COL_PAGE_NOTE, QHeaderView.ResizeMode.ResizeToContents
        )

        obs_layout.addWidget(self._observations_table)
        main_layout.addWidget(obs_group)

        # Let the observations table take remaining vertical space
        main_layout.setStretch(2, 1)

    def _setup_role_completer(self) -> None:
        """Set up non-binding autocomplete suggestions for role_in_household.

        Collects all distinct non-empty role values from the project's existing
        residence facts and offers them as suggestions. The user may ignore them.
        """
        existing_roles = sorted(
            {
                r.role_in_household
                for r in self._project_data.residences
                if r.role_in_household
            }
        )
        if existing_roles:
            completer = QCompleter(existing_roles, self)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            self._role_edit.setCompleter(completer)

    # ------------------------------------------------------------------
    # Private: loading data
    # ------------------------------------------------------------------

    def _load_residence(self) -> None:
        """Populate all fields from the stored residence."""
        if self._residence is None:
            return

        # Endpoint bounds
        self._start_earliest_edit.setText(self._residence.start.earliest or "")
        self._start_latest_edit.setText(self._residence.start.latest or "")
        self._end_earliest_edit.setText(self._residence.end.earliest or "")
        self._end_latest_edit.setText(self._residence.end.latest or "")

        # Role
        self._role_edit.setText(self._residence.role_in_household)

        # Observations
        self.set_observations(self._residence.observations)

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    def _get_bound_value(self, edit: QLineEdit) -> Optional[str]:
        """Extract a bound value from a line edit.

        Returns the trimmed text if non-empty, None otherwise.
        The field accepts ÅÅÅÅ, ÅÅÅÅ-MM, ÅÅÅÅ-MM-DD or empty.
        """
        text = edit.text().strip()
        if not text:
            return None
        return text

    def _set_observation_row(self, row: int, obs: Observation) -> None:
        """Fill one row of the Observation table.

        Shows the source title (resolved from the project), the formatted span,
        and the page_note.
        """
        # Source title
        source_title = self._resolve_source_title(obs.source_ref.source_id)
        title_item = QTableWidgetItem(source_title)
        title_item.setFlags(title_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._observations_table.setItem(row, _COL_SOURCE_TITLE, title_item)

        # Span
        span_text = format_observation_span(obs.observed_from, obs.observed_to)
        span_item = QTableWidgetItem(span_text)
        span_item.setFlags(span_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._observations_table.setItem(row, _COL_SPAN, span_item)

        # Page note
        note_item = QTableWidgetItem(obs.page_note)
        note_item.setFlags(note_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._observations_table.setItem(row, _COL_PAGE_NOTE, note_item)

    def _resolve_source_title(self, source_id: str) -> str:
        """Look up the title of a source by id.

        Returns the source title if found, or the source_id as a fallback.
        """
        for source in self._project_data.sources:
            if source.id == source_id:
                return source.title or source_id
        return source_id
