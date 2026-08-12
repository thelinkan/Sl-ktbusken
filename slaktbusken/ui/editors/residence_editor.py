"""Residence editor widget ("Boende").

Provides a form-based editor for ResidenceFact records: four endpoint bound
fields, a free-text household role field with non-binding suggestions, an
Observation table ordered by observed_from then observed_to, and per-Endpoint
Event selectors that link an endpoint to one of the person's Events.

All UI text is in Swedish.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
from slaktbusken.model.event import Event
from slaktbusken.model.residence import (
    Endpoint,
    Observation,
    ResidenceFact,
    normalize_role_in_household,
)
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.swedish_locale import (
    format_date,
    format_observation_span,
    get_event_type_label,
)

logger = logging.getLogger(__name__)

# Maximum allowed code points for role_in_household after trimming.
_ROLE_MAX_LENGTH = 100

# Minimum visible rows for the Observation table.
_OBSERVATION_MIN_ROWS = 15

# Column indices for the Observation table.
_COL_SOURCE_TITLE = 0
_COL_SPAN = 1
_COL_PAGE_NOTE = 2

# Event types that trigger the "wrong-side" warning.
_WRONG_SIDE_BIRTH = "birth"
_WRONG_SIDE_DEATH = "death"

# Swedish messages for the endpoint event selector.
_MSG_DATE_MISMATCH = (
    "Kopplad händelse har ett annat datum än endpunkten – uppdatera endpunkten."
)
_MSG_MISSING_EVENT = "Händelsen saknas – rensa kopplingen."
_MSG_WRONG_SIDE = (
    "Vald händelse hör normalt till boendets andra endpunkt – kontrollera kopplingen."
)


def _sort_events_for_selector(events: list[Event]) -> list[Event]:
    """Sort events: dated by date ascending, undated last.

    Within undated events the original order is preserved.
    """

    def _sort_key(event: Event) -> tuple[int, str]:
        if event.date and event.date.value:
            return (0, event.date.value)
        return (1, "")

    return sorted(events, key=_sort_key)


def _build_event_label(event: Event) -> str:
    """Build the display label for an event in the selector.

    Format: "Swedish event type label (formatted date)" for dated events,
    or just "Swedish event type label" for undated events.
    """
    label = get_event_type_label(event.type)
    if event.date and event.date.value:
        formatted = format_date(event.date.value)
        return f"{label} ({formatted})"
    return label


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
        person_id: Optional[str] = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialise the residence editor.

        Args:
            project_data: The current project data containing all entities.
            residence: Optional existing ResidenceFact to edit.
            person_id: The person whose events are shown in the selectors.
                       Falls back to residence.person_id if not given.
            parent: Optional parent widget.
        """
        super().__init__(parent)

        self._project_data = project_data
        self._residence = residence
        self._person_id = person_id or (
            residence.person_id if residence else None
        )

        # Suppress recursive signal handling during programmatic changes.
        self._updating = False

        # Tracked event link state for each endpoint.
        self._start_event_id: Optional[str] = None
        self._end_event_id: Optional[str] = None
        self._start_precision: Optional[str] = None
        self._end_precision: Optional[str] = None

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

        # Start Endpoint Event selector
        self._start_event_combo = QComboBox()
        self._start_event_combo.setToolTip(
            "Koppla startpunkten till en händelse"
        )
        bounds_form.addRow("Händelse (början):", self._start_event_combo)

        # Start event info/warning label
        self._start_event_label = QLabel()
        self._start_event_label.setWordWrap(True)
        self._start_event_label.setVisible(False)
        bounds_form.addRow("", self._start_event_label)

        self._end_earliest_edit = QLineEdit()
        self._end_earliest_edit.setPlaceholderText("ÅÅÅÅ, ÅÅÅÅ-MM eller ÅÅÅÅ-MM-DD")
        bounds_form.addRow("Tidigast slut:", self._end_earliest_edit)

        self._end_latest_edit = QLineEdit()
        self._end_latest_edit.setPlaceholderText("ÅÅÅÅ, ÅÅÅÅ-MM eller ÅÅÅÅ-MM-DD")
        bounds_form.addRow("Senast slut:", self._end_latest_edit)

        # End Endpoint Event selector
        self._end_event_combo = QComboBox()
        self._end_event_combo.setToolTip(
            "Koppla slutpunkten till en händelse"
        )
        bounds_form.addRow("Händelse (slut):", self._end_event_combo)

        # End event info/warning label
        self._end_event_label = QLabel()
        self._end_event_label.setWordWrap(True)
        self._end_event_label.setVisible(False)
        bounds_form.addRow("", self._end_event_label)

        main_layout.addWidget(bounds_group)

        # Populate event selectors
        self._populate_event_selectors()

        # Connect event selector signals
        self._start_event_combo.currentIndexChanged.connect(
            self._on_start_event_changed
        )
        self._end_event_combo.currentIndexChanged.connect(
            self._on_end_event_changed
        )

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

        self._updating = True
        try:
            # Endpoint bounds
            self._start_earliest_edit.setText(self._residence.start.earliest or "")
            self._start_latest_edit.setText(self._residence.start.latest or "")
            self._end_earliest_edit.setText(self._residence.end.earliest or "")
            self._end_latest_edit.setText(self._residence.end.latest or "")

            # Precision from residence
            self._start_precision = self._residence.start.precision
            self._end_precision = self._residence.end.precision

            # Event links
            self._start_event_id = self._residence.start.event_id
            self._end_event_id = self._residence.end.event_id

            # Set combo selection for start event
            self._select_event_in_combo(
                self._start_event_combo, self._start_event_id
            )
            # Set combo selection for end event
            self._select_event_in_combo(
                self._end_event_combo, self._end_event_id
            )

            # Role
            self._role_edit.setText(self._residence.role_in_household)

            # Observations
            self.set_observations(self._residence.observations)
        finally:
            self._updating = False

        # Evaluate messages after loading (outside the guard so labels update)
        self._update_event_messages()

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

    # ------------------------------------------------------------------
    # Private: Event selector support
    # ------------------------------------------------------------------

    def _get_person_events(self) -> list[Event]:
        """Return the person's events sorted for the selector."""
        if not self._person_id:
            return []
        events = [
            event
            for event in self._project_data.events
            if any(
                p.person_id == self._person_id for p in event.participants
            )
        ]
        return _sort_events_for_selector(events)

    def _populate_event_selectors(self) -> None:
        """Fill both event combo boxes with the person's events.

        First item is the empty choice (no linked event), followed by events
        ordered by date ascending with undated last.
        """
        events = self._get_person_events()

        for combo in (self._start_event_combo, self._end_event_combo):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("", None)  # empty choice
            for event in events:
                label = _build_event_label(event)
                combo.addItem(label, event.id)
            combo.blockSignals(False)

    def _find_event_by_id(self, event_id: str) -> Optional[Event]:
        """Find an event in the project by its id."""
        for event in self._project_data.events:
            if event.id == event_id:
                return event
        return None

    def _select_event_in_combo(
        self, combo: QComboBox, event_id: Optional[str]
    ) -> None:
        """Set the combo box selection to match the given event_id.

        If the event_id is None or not found among the combo items,
        selects the empty first choice (index 0).
        """
        if not event_id:
            combo.setCurrentIndex(0)
            return
        for i in range(combo.count()):
            if combo.itemData(i) == event_id:
                combo.setCurrentIndex(i)
                return
        # event_id not in the combo (event may be missing) — stay at empty
        combo.setCurrentIndex(0)

    def _on_start_event_changed(self, index: int) -> None:
        """Handle selection change in the start endpoint event combo."""
        if self._updating:
            return
        self._apply_event_selection("start", self._start_event_combo, index)

    def _on_end_event_changed(self, index: int) -> None:
        """Handle selection change in the end endpoint event combo."""
        if self._updating:
            return
        self._apply_event_selection("end", self._end_event_combo, index)

    def _apply_event_selection(
        self, side: str, combo: QComboBox, index: int
    ) -> None:
        """Apply the effect of selecting an event in a combo.

        For the empty choice: clears event_id only.
        For a dated event: writes event_id, earliest, latest, precision.
        For an undated event: writes event_id only.
        Bounds fields stay editable regardless.
        """
        event_id = combo.itemData(index)

        if not event_id:
            # Empty choice selected: clear event_id only, keep bounds.
            if side == "start":
                self._start_event_id = None
            else:
                self._end_event_id = None
            self._update_event_messages()
            return

        event = self._find_event_by_id(event_id)

        if side == "start":
            self._start_event_id = event_id
            if event and event.date and event.date.value:
                self._start_earliest_edit.setText(event.date.value)
                self._start_latest_edit.setText(event.date.value)
                self._start_precision = event.date.precision
            # If undated, only event_id is set; bounds unchanged.
        else:
            self._end_event_id = event_id
            if event and event.date and event.date.value:
                self._end_earliest_edit.setText(event.date.value)
                self._end_latest_edit.setText(event.date.value)
                self._end_precision = event.date.precision
            # If undated, only event_id is set; bounds unchanged.

        self._update_event_messages()

    def _update_event_messages(self) -> None:
        """Re-evaluate and display event-related messages for both endpoints.

        Checks for:
        - Missing event (event_id present but not in project)
        - Date mismatch (event date differs from endpoint bounds)
        - Wrong-side (death on start, birth on end — but not flytt)
        """
        self._update_single_event_message(
            "start",
            self._start_event_id,
            self._start_event_combo,
            self._start_event_label,
        )
        self._update_single_event_message(
            "end",
            self._end_event_id,
            self._end_event_combo,
            self._end_event_label,
        )

    def _update_single_event_message(
        self,
        side: str,
        event_id: Optional[str],
        combo: QComboBox,
        label: QLabel,
    ) -> None:
        """Update the warning/info label for one endpoint's event link."""
        if not event_id:
            label.setVisible(False)
            return

        event = self._find_event_by_id(event_id)

        if event is None:
            # Requirement 3.10: missing event
            label.setText(_MSG_MISSING_EVENT)
            label.setStyleSheet("color: red;")
            label.setVisible(True)
            return

        messages: list[str] = []

        # Requirement 3.7: date mismatch check
        if event.date and event.date.value:
            if side == "start":
                ep_earliest = self._start_earliest_edit.text().strip()
                ep_latest = self._start_latest_edit.text().strip()
            else:
                ep_earliest = self._end_earliest_edit.text().strip()
                ep_latest = self._end_latest_edit.text().strip()

            event_date_val = event.date.value
            # Mismatch if event date differs from either bound
            if ep_earliest != event_date_val or ep_latest != event_date_val:
                messages.append(_MSG_DATE_MISMATCH)

        # Requirement 3.9: wrong-side check (not for flytt)
        if event.type != "flytt":
            if side == "start" and event.type == _WRONG_SIDE_DEATH:
                messages.append(_MSG_WRONG_SIDE)
            elif side == "end" and event.type == _WRONG_SIDE_BIRTH:
                messages.append(_MSG_WRONG_SIDE)

        if messages:
            label.setText("\n".join(messages))
            label.setStyleSheet("color: #b36b00;")  # warning orange
            label.setVisible(True)
        else:
            # Requirement 3.5: show linked event label when no warnings
            event_label_text = _build_event_label(event)
            label.setText(event_label_text)
            label.setStyleSheet("color: #555;")
            label.setVisible(True)

    # ------------------------------------------------------------------
    # Public: event_id access
    # ------------------------------------------------------------------

    @property
    def start_event_id(self) -> Optional[str]:
        """The event_id currently linked to the start endpoint."""
        return self._start_event_id

    @property
    def end_event_id(self) -> Optional[str]:
        """The event_id currently linked to the end endpoint."""
        return self._end_event_id

    @property
    def start_precision(self) -> Optional[str]:
        """The precision for the start endpoint, set by event selection."""
        return self._start_precision

    @property
    def end_precision(self) -> Optional[str]:
        """The precision for the end endpoint, set by event selection."""
        return self._end_precision
