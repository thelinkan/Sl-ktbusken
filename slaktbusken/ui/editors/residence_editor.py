"""Residence editor widget ("Boende").

Provides a form-based editor for ResidenceFact records: four endpoint bound
fields, a free-text household role field with non-binding suggestions, an
Observation table ordered by observed_from then observed_to, and per-Endpoint
Event selectors that link an endpoint to one of the person's Events.

Action buttons delegate to pure operations in ``residence_edit_ops.py``,
each working on a staging copy and committing the result atomically.

All UI text is in Swedish.
"""

from __future__ import annotations

import copy
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
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.date_span import is_valid_iso, expand_iso
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.id_generator import IDGenerator
from slaktbusken.model.residence import (
    Endpoint,
    Observation,
    ResidenceFact,
    normalize_role_in_household,
    possible_span,
)
from slaktbusken.model.project import ProjectData
from slaktbusken.model.source import Source, StructuredReference
from slaktbusken.services.residence_coverage import CoverageGap, coverage_gaps
from slaktbusken.services.residence_edit_ops import (
    BulkLimitError,
    BulkPlan,
    BulkRequest,
    ResidenceMergeError,
    ResidenceSplitError,
    attach_observations,
    is_merge_suppressed,
    merge,
    plan_bulk_attach,
    should_offer_merge,
    split_at_gap,
    use_as_exact_end,
    use_as_exact_start,
)
from slaktbusken.services.residence_validation import (
    ResidenceFinding,
    residence_findings,
)
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

        # --- Action buttons ---
        actions_group = QGroupBox("Åtgärder")
        actions_layout = QVBoxLayout(actions_group)

        obs_actions_row = QHBoxLayout()
        self._btn_exact_start = QPushButton("Använd som exakt början")
        self._btn_exact_start.setToolTip(
            "Sätt periodstart till markerad observations startår"
        )
        self._btn_exact_start.clicked.connect(self._on_use_as_exact_start)
        obs_actions_row.addWidget(self._btn_exact_start)

        self._btn_exact_end = QPushButton("Använd som exakt slut")
        self._btn_exact_end.setToolTip(
            "Sätt periodslut till markerad observations slutår"
        )
        self._btn_exact_end.clicked.connect(self._on_use_as_exact_end)
        obs_actions_row.addWidget(self._btn_exact_end)
        actions_layout.addLayout(obs_actions_row)

        split_merge_row = QHBoxLayout()
        self._btn_split = QPushButton("Dela boendet här")
        self._btn_split.setToolTip(
            "Dela boendet vid en täckningslucka"
        )
        self._btn_split.clicked.connect(self._on_split)
        split_merge_row.addWidget(self._btn_split)

        self._btn_merge = QPushButton("Slå samman boenden")
        self._btn_merge.setToolTip(
            "Slå samman med ett annat boende på samma plats"
        )
        self._btn_merge.clicked.connect(self._on_merge)
        split_merge_row.addWidget(self._btn_merge)
        actions_layout.addLayout(split_merge_row)

        flytt_row = QHBoxLayout()
        self._btn_create_flytt = QPushButton("Skapa flytt mellan boendena")
        self._btn_create_flytt.setToolTip(
            "Skapa en flytt-händelse som länkar de två boendena"
        )
        self._btn_create_flytt.clicked.connect(self._on_create_flytt)
        flytt_row.addWidget(self._btn_create_flytt)
        actions_layout.addLayout(flytt_row)

        # Warnings display label
        self._warnings_label = QLabel()
        self._warnings_label.setWordWrap(True)
        self._warnings_label.setStyleSheet("color: #b36b00;")
        self._warnings_label.setVisible(False)
        actions_layout.addWidget(self._warnings_label)

        main_layout.addWidget(actions_group)

        # --- Bulk paste panel (collapsible) ---
        self._setup_bulk_panel(main_layout)

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

    def _setup_bulk_panel(self, main_layout: QVBoxLayout) -> None:
        """Build the collapsible 'Klistra in referenser' bulk paste panel.

        The panel contains:
        - A multi-line text field for pasting reference lines.
        - A "Planera" button that parses lines and displays the plan.
        - A candidate list with prefilled spans (unselectable when incomplete).
        - An "Kunde inte tolkas" section (lines truncated at 200 chars).
        - A Swedish summary of the five counts.
        - An "Utför" button that applies the plan atomically via deep copies.

        Requirements: 9.1, 9.2, 9.3, 9.5, 9.6, 9.8, 9.9, 9.10.
        """
        self._bulk_group = QGroupBox("Klistra in referenser")
        self._bulk_group.setCheckable(True)
        self._bulk_group.setChecked(False)
        bulk_layout = QVBoxLayout(self._bulk_group)

        # Multi-line paste field
        paste_label = QLabel("Klistra in källreferenser (en per rad):")
        bulk_layout.addWidget(paste_label)

        self._bulk_paste_edit = QPlainTextEdit()
        self._bulk_paste_edit.setPlaceholderText(
            "Klistra in referensrader här, t.ex.:\n"
            "Ljusdal AI:15 1866-1870 bild 25 sid 10\n"
            "Ljusdal AI:16 1871-1875 bild 30 sid 12"
        )
        self._bulk_paste_edit.setMaximumHeight(100)
        bulk_layout.addWidget(self._bulk_paste_edit)

        # "Planera" button
        plan_row = QHBoxLayout()
        self._btn_bulk_plan = QPushButton("Planera")
        self._btn_bulk_plan.setToolTip(
            "Analysera de inklistrade referenserna och visa en plan"
        )
        self._btn_bulk_plan.clicked.connect(self._on_bulk_plan)
        plan_row.addWidget(self._btn_bulk_plan)
        plan_row.addStretch()
        bulk_layout.addLayout(plan_row)

        # Plan results area (initially hidden)
        self._bulk_results_widget = QWidget()
        results_layout = QVBoxLayout(self._bulk_results_widget)
        results_layout.setContentsMargins(0, 0, 0, 0)

        # Candidate table showing parsed references with spans
        self._bulk_candidates_label = QLabel("Tolkade kandidater:")
        results_layout.addWidget(self._bulk_candidates_label)

        self._bulk_candidates_table = QTableWidget()
        self._bulk_candidates_table.setColumnCount(3)
        self._bulk_candidates_table.setHorizontalHeaderLabels(
            ["Referens", "Från", "Till"]
        )
        self._bulk_candidates_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._bulk_candidates_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._bulk_candidates_table.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )
        self._bulk_candidates_table.setMaximumHeight(150)
        header = self._bulk_candidates_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        results_layout.addWidget(self._bulk_candidates_table)

        # "Kunde inte tolkas" section
        self._bulk_unparsed_label = QLabel()
        self._bulk_unparsed_label.setWordWrap(True)
        self._bulk_unparsed_label.setStyleSheet("color: #b36b00;")
        self._bulk_unparsed_label.setVisible(False)
        results_layout.addWidget(self._bulk_unparsed_label)

        # Summary label (five counts)
        self._bulk_summary_label = QLabel()
        self._bulk_summary_label.setWordWrap(True)
        results_layout.addWidget(self._bulk_summary_label)

        # "Utför" button
        execute_row = QHBoxLayout()
        self._btn_bulk_execute = QPushButton("Utför")
        self._btn_bulk_execute.setToolTip(
            "Tillämpa planen – skapar/utökar boenden atomiskt"
        )
        self._btn_bulk_execute.clicked.connect(self._on_bulk_execute)
        execute_row.addWidget(self._btn_bulk_execute)
        execute_row.addStretch()
        results_layout.addLayout(execute_row)

        self._bulk_results_widget.setVisible(False)
        bulk_layout.addWidget(self._bulk_results_widget)

        # Error label for the bulk panel
        self._bulk_error_label = QLabel()
        self._bulk_error_label.setWordWrap(True)
        self._bulk_error_label.setStyleSheet("color: red;")
        self._bulk_error_label.setVisible(False)
        bulk_layout.addWidget(self._bulk_error_label)

        main_layout.addWidget(self._bulk_group)

        # State for the current bulk plan
        self._bulk_plan: BulkPlan | None = None

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

    # ------------------------------------------------------------------
    # Public: action methods (thin wrappers over pure edit ops)
    # ------------------------------------------------------------------

    def build_fact_from_fields(self) -> ResidenceFact:
        """Build a ResidenceFact from the current field state.

        This is a snapshot of the editor's state assembled into a fresh
        ResidenceFact that can be used as a staging copy.
        """
        start = Endpoint(
            earliest=self.get_start_earliest(),
            latest=self.get_start_latest(),
            precision=self._start_precision,
            event_id=self._start_event_id,
            note=(
                self._residence.start.note
                if self._residence and self._residence.start
                else None
            ),
        )
        end = Endpoint(
            earliest=self.get_end_earliest(),
            latest=self.get_end_latest(),
            precision=self._end_precision,
            event_id=self._end_event_id,
            note=(
                self._residence.end.note
                if self._residence and self._residence.end
                else None
            ),
        )
        return ResidenceFact(
            id=self._residence.id if self._residence else "",
            person_id=self._person_id or "",
            place_id=(
                self._residence.place_id if self._residence else ""
            ),
            start=start,
            end=end,
            role_in_household=self.get_role_in_household(),
            observations=(
                list(self._residence.observations) if self._residence else []
            ),
            notes=self._residence.notes if self._residence else "",
        )

    def save_with_warnings(self) -> bool:
        """Save the current fact, displaying any warning-level findings.

        Requirement 6.9: a fact whose findings are all warning-level is saved;
        every entered value is retained; each warning is displayed.

        Returns True if the fact was saved (possibly with warnings), False if
        saving was blocked (e.g. hard validation errors from the caller).
        """
        fact = self.build_fact_from_fields()
        findings = residence_findings(fact, self._project_data)

        if findings:
            messages = [f.message for f in findings]
            self._warnings_label.setText("\n".join(messages))
            self._warnings_label.setVisible(True)
        else:
            self._warnings_label.setVisible(False)

        # Commit the staging copy into the project collection atomically.
        self._commit_fact(fact)
        return True

    def offer_merge_after_attach(
        self, fact: ResidenceFact, other: ResidenceFact, new_obs: Observation
    ) -> bool:
        """Offer a merge after attaching an observation that bridges two facts.

        Requirement 17.13: offer the merge when the Observation covers every
        separating year. Returns True if the user accepts the merge, False
        otherwise.
        """
        if not should_offer_merge(fact, other, new_obs, self._project_data):
            return False

        # Check for suppression warning (Requirement 17.15)
        suppressed = is_merge_suppressed(fact, other, self._project_data)
        if suppressed:
            reply = QMessageBox.question(
                self,
                "Slå samman boenden",
                "En flytt eller ett annat boende förklarar mellanrummet "
                "– kontrollera att perioderna hör ihop.\n\n"
                "Vill du slå samman boendena ändå?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False
        else:
            reply = QMessageBox.question(
                self,
                "Slå samman boenden",
                "Den nya observationen överbryggar mellanrummet till ett "
                "annat boende på samma plats.\n\n"
                "Vill du slå samman boendena?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False

        # Perform the merge
        self._perform_merge(fact, other)
        return True

    # ------------------------------------------------------------------
    # Private: action handlers
    # ------------------------------------------------------------------

    def _on_use_as_exact_start(self) -> None:
        """Handle 'Använd som exakt början' button click.

        Sets both start bounds to the selected Observation's observed_from.
        Requirement 16.10, 16.11: explicit user invocation only.
        """
        obs = self._get_selected_observation()
        if obs is None:
            return
        if self._residence is None:
            return

        # Work on a staging copy, swap atomically.
        staging = copy.deepcopy(self._residence)
        result = use_as_exact_start(staging, obs)
        self._commit_fact(result)
        self._residence = result
        self._load_residence()

    def _on_use_as_exact_end(self) -> None:
        """Handle 'Använd som exakt slut' button click.

        Sets both end bounds to the selected Observation's observed_to.
        Requirement 16.10, 16.11: explicit user invocation only.
        """
        obs = self._get_selected_observation()
        if obs is None:
            return
        if self._residence is None:
            return

        # Work on a staging copy, swap atomically.
        staging = copy.deepcopy(self._residence)
        result = use_as_exact_end(staging, obs)
        self._commit_fact(result)
        self._residence = result
        self._load_residence()

    def _on_split(self) -> None:
        """Handle 'Dela boendet här' button click.

        Requirement 5.10: split at a coverage gap that has observations on
        both sides.
        """
        if self._residence is None:
            return

        # Compute coverage gaps and find those that are splittable.
        gaps = coverage_gaps(self._residence, self._project_data)
        splittable_gaps = [g for g in gaps if g.splittable]

        if not splittable_gaps:
            QMessageBox.information(
                self,
                "Dela boendet",
                "Inga täckningsluckor med observationer på båda sidor "
                "finns att dela vid.",
            )
            return

        # If multiple gaps, pick the first one (user can split iteratively).
        # In a more complete UI this could present a choice.
        gap = splittable_gaps[0]

        # Generate two new IDs.
        id_gen = self._make_id_generator()
        new_id_1 = id_gen.generate("residence")
        new_id_2 = id_gen.generate("residence")

        try:
            staging = copy.deepcopy(self._residence)
            first_fact, second_fact = split_at_gap(
                staging, gap, (new_id_1, new_id_2)
            )
        except ResidenceSplitError as exc:
            QMessageBox.warning(self, "Kan inte dela", str(exc))
            return

        # Atomic commit: remove the original, add the two new facts.
        self._remove_fact_from_project(self._residence.id)
        self._project_data.residences.append(first_fact)
        self._project_data.residences.append(second_fact)

        # Load the first resulting fact into the editor.
        self._residence = first_fact
        self._load_residence()
        self.save_requested.emit()

    def _on_merge(self) -> None:
        """Handle 'Slå samman boenden' button click.

        Requirement 17.1: merges two facts with same person_id and place_id.
        The user must have a second fact selected (or we pick the best candidate).
        """
        if self._residence is None:
            return

        other = self._find_merge_candidate()
        if other is None:
            QMessageBox.information(
                self,
                "Slå samman boenden",
                "Inget annat boende på samma plats för samma person "
                "hittades att slå samman med.",
            )
            return

        self._perform_merge(self._residence, other)

    def _on_create_flytt(self) -> None:
        """Handle 'Skapa flytt mellan boendena' button click.

        Requirement 18.12: create a Flytt event linking two residences at
        different places whose periods meet or are separated by at most one year.
        """
        if self._residence is None:
            return

        other = self._find_flytt_candidate()
        if other is None:
            QMessageBox.information(
                self,
                "Skapa flytt",
                "Inget annat boende för samma person på en annan plats "
                "som angränsar hittades.",
            )
            return

        # Determine which is earlier in the timeline.
        earlier, later = self._timeline_order_pair(self._residence, other)

        # Generate the new event ID.
        id_gen = self._make_id_generator()
        flytt_id = id_gen.generate("event")

        # Prefill date from the boundary between the two periods.
        flytt_date = self._compute_flytt_date(earlier, later)

        # Create the Flytt event.
        flytt_event = Event(
            id=flytt_id,
            type="flytt",
            participants=[
                Participant(person_id=self._person_id or "", role="subject")
            ],
            date=flytt_date,
            place=PlaceRef(place_id=later.place_id) if later.place_id else None,
            from_place=(
                PlaceRef(place_id=earlier.place_id)
                if earlier.place_id
                else None
            ),
        )

        # Add the event to the project.
        self._project_data.events.append(flytt_event)

        # Link the flytt to both residences' endpoints atomically.
        # Earlier fact: end endpoint linked to the flytt.
        earlier_staging = copy.deepcopy(earlier)
        new_earlier_end = Endpoint(
            earliest=earlier_staging.end.earliest,
            latest=earlier_staging.end.latest,
            precision=(
                flytt_date.precision if flytt_date else earlier_staging.end.precision
            ),
            event_id=flytt_id,
            note=earlier_staging.end.note,
        )
        if flytt_date and flytt_date.value:
            new_earlier_end = Endpoint(
                earliest=flytt_date.value,
                latest=flytt_date.value,
                precision=flytt_date.precision,
                event_id=flytt_id,
                note=earlier_staging.end.note,
            )
        updated_earlier = ResidenceFact(
            id=earlier_staging.id,
            person_id=earlier_staging.person_id,
            place_id=earlier_staging.place_id,
            start=earlier_staging.start,
            end=new_earlier_end,
            role_in_household=earlier_staging.role_in_household,
            observations=list(earlier_staging.observations),
            notes=earlier_staging.notes,
        )

        # Later fact: start endpoint linked to the flytt.
        later_staging = copy.deepcopy(later)
        new_later_start = Endpoint(
            earliest=later_staging.start.earliest,
            latest=later_staging.start.latest,
            precision=(
                flytt_date.precision if flytt_date else later_staging.start.precision
            ),
            event_id=flytt_id,
            note=later_staging.start.note,
        )
        if flytt_date and flytt_date.value:
            new_later_start = Endpoint(
                earliest=flytt_date.value,
                latest=flytt_date.value,
                precision=flytt_date.precision,
                event_id=flytt_id,
                note=later_staging.start.note,
            )
        updated_later = ResidenceFact(
            id=later_staging.id,
            person_id=later_staging.person_id,
            place_id=later_staging.place_id,
            start=new_later_start,
            end=later_staging.end,
            role_in_household=later_staging.role_in_household,
            observations=list(later_staging.observations),
            notes=later_staging.notes,
        )

        # Swap both into the project atomically.
        self._replace_fact_in_project(updated_earlier)
        self._replace_fact_in_project(updated_later)

        # Reload the current one into the editor.
        if self._residence.id == earlier.id:
            self._residence = updated_earlier
        else:
            self._residence = updated_later
        self._load_residence()
        self._populate_event_selectors()
        self._update_event_messages()
        self.save_requested.emit()

    def _perform_merge(
        self, fact_a: ResidenceFact, fact_b: ResidenceFact
    ) -> None:
        """Perform the merge of two facts, handling confirmations and warnings.

        Requirements 17.10 (separation confirmation) and 17.15 (suppression
        warning) are handled here.
        """
        # Check for >10-year separation warning (Requirement 17.10).
        id_gen = self._make_id_generator()
        new_id = id_gen.generate("residence")

        try:
            merged_fact, warning = merge(fact_a, fact_b, new_id)
        except ResidenceMergeError as exc:
            QMessageBox.warning(self, "Kan inte slå samman", str(exc))
            return

        # If there's a separation warning, confirm before proceeding.
        if warning:
            reply = QMessageBox.question(
                self,
                "Slå samman boenden",
                f"{warning}\n\nVill du slå samman boendena ändå?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Check suppression (Requirement 17.15).
        if is_merge_suppressed(fact_a, fact_b, self._project_data):
            reply = QMessageBox.question(
                self,
                "Slå samman boenden",
                "En flytt eller ett annat boende förklarar mellanrummet "
                "– kontrollera att perioderna hör ihop.\n\n"
                "Vill du slå samman boendena ändå?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Atomic commit: remove both originals, add the merged fact.
        self._remove_fact_from_project(fact_a.id)
        self._remove_fact_from_project(fact_b.id)
        self._project_data.residences.append(merged_fact)

        # Load the merged fact into the editor.
        self._residence = merged_fact
        self._load_residence()
        self.save_requested.emit()

    # ------------------------------------------------------------------
    # Private: action helpers
    # ------------------------------------------------------------------

    def _get_selected_observation(self) -> Optional[Observation]:
        """Return the Observation corresponding to the selected table row.

        Observations in the table are ordered by observed_from then observed_to,
        matching how set_observations sorts them.
        """
        if self._residence is None:
            return None
        row = self._observations_table.currentRow()
        if row < 0:
            return None

        sorted_obs = sorted(
            self._residence.observations,
            key=lambda o: (o.observed_from, o.observed_to),
        )
        if row >= len(sorted_obs):
            return None
        return sorted_obs[row]

    def _find_merge_candidate(self) -> Optional[ResidenceFact]:
        """Find another Residence_Fact eligible for merging with the current one.

        Looks for same person_id and same place_id (Requirement 17.1).
        Returns the first match in collection order, or None.
        """
        if self._residence is None:
            return None
        for fact in self._project_data.residences:
            if fact.id == self._residence.id:
                continue
            if (
                fact.person_id == self._residence.person_id
                and fact.place_id == self._residence.place_id
            ):
                return fact
        return None

    def _find_flytt_candidate(self) -> Optional[ResidenceFact]:
        """Find another Residence_Fact eligible for creating a Flytt between.

        Requirement 18.12: same person, different place, periods meet or are
        separated by at most one whole year.
        """
        if self._residence is None:
            return None

        for fact in self._project_data.residences:
            if fact.id == self._residence.id:
                continue
            if fact.person_id != self._residence.person_id:
                continue
            if fact.place_id == self._residence.place_id:
                continue
            # Check that the periods meet or are separated by at most one year.
            if self._periods_adjacent(self._residence, fact):
                return fact
        return None

    def _periods_adjacent(
        self, fact_a: ResidenceFact, fact_b: ResidenceFact
    ) -> bool:
        """Whether two facts' Possible_Spans meet or are ≤1 year apart."""
        span_a = possible_span(fact_a)
        span_b = possible_span(fact_b)

        # If either is unbounded in the direction of the other, consider them
        # adjacent (they could be touching).
        if span_a.last is None or span_b.first is None:
            return True
        if span_b.last is None or span_a.first is None:
            return True

        # Check both directions: a before b, or b before a.
        a_end_year = span_a.last.year
        b_start_year = span_b.first.year
        b_end_year = span_b.last.year
        a_start_year = span_a.first.year

        # Direction a → b
        if b_start_year - a_end_year <= 1:
            return True
        # Direction b → a
        if a_start_year - b_end_year <= 1:
            return True

        return False

    def _timeline_order_pair(
        self, a: ResidenceFact, b: ResidenceFact
    ) -> tuple[ResidenceFact, ResidenceFact]:
        """Return (earlier, later) in the residence timeline order."""

        def _key(fact: ResidenceFact) -> tuple:
            def _absent_first(val: Optional[str]) -> tuple[int, str]:
                if val is None or not val.strip():
                    return (0, "")
                return (1, val.strip())

            return (
                _absent_first(fact.start.earliest),
                _absent_first(fact.start.latest),
                _absent_first(fact.end.earliest),
                _absent_first(fact.end.latest),
                fact.id,
            )

        if _key(a) <= _key(b):
            return (a, b)
        return (b, a)

    def _compute_flytt_date(
        self, earlier: ResidenceFact, later: ResidenceFact
    ) -> Optional[DateValue]:
        """Compute the prefilled date for a Flytt event from the boundary.

        Uses the end of the earlier fact or the start of the later fact as the
        date, preferring a more precise value.
        """
        # Prefer end.latest of the earlier fact, then start.earliest of the
        # later fact. Use whichever is available and more precise.
        candidates: list[str] = []
        if earlier.end.latest:
            candidates.append(earlier.end.latest)
        if earlier.end.earliest:
            candidates.append(earlier.end.earliest)
        if later.start.earliest:
            candidates.append(later.start.earliest)
        if later.start.latest:
            candidates.append(later.start.latest)

        if not candidates:
            return None

        # Pick the most precise value (longest string → ÅÅÅÅ-MM-DD > ÅÅÅÅ-MM > ÅÅÅÅ).
        best = max(candidates, key=len)
        # Determine precision from the value form.
        if len(best) == 10:
            precision = "day"
        elif len(best) == 7:
            precision = "month"
        else:
            precision = "year"

        return DateValue(value=best, precision=precision)

    def _make_id_generator(self) -> IDGenerator:
        """Create an IDGenerator initialized with all existing project IDs."""
        existing_ids: set[str] = set()
        for person in self._project_data.persons:
            existing_ids.add(person.id)
        for event in self._project_data.events:
            existing_ids.add(event.id)
        for place in self._project_data.places:
            existing_ids.add(place.id)
        for source in self._project_data.sources:
            existing_ids.add(source.id)
        for residence in self._project_data.residences:
            existing_ids.add(residence.id)
        return IDGenerator(existing_ids)

    def _commit_fact(self, fact: ResidenceFact) -> None:
        """Write a fact into the project, replacing any existing fact with the same id.

        This is the single point at which changes reach ProjectData, giving
        atomicity: the caller builds the full result in a staging copy and calls
        this once.
        """
        # Replace in-place if the fact already exists in the collection.
        for i, existing in enumerate(self._project_data.residences):
            if existing.id == fact.id:
                self._project_data.residences[i] = fact
                return
        # New fact — append.
        self._project_data.residences.append(fact)

    def _replace_fact_in_project(self, fact: ResidenceFact) -> None:
        """Replace a fact in the project's residences list by its id."""
        for i, existing in enumerate(self._project_data.residences):
            if existing.id == fact.id:
                self._project_data.residences[i] = fact
                return
        # Not found — append (shouldn't happen normally).
        self._project_data.residences.append(fact)

    def _remove_fact_from_project(self, fact_id: str) -> None:
        """Remove a fact from the project's residences list by id."""
        self._project_data.residences = [
            r for r in self._project_data.residences if r.id != fact_id
        ]

    # ------------------------------------------------------------------
    # Private: bulk paste panel handlers
    # ------------------------------------------------------------------

    def _on_bulk_plan(self) -> None:
        """Handle 'Planera' button click in the bulk paste panel.

        Parses the pasted text via plan_bulk_attach and displays the plan:
        candidates with prefilled spans, unparsed lines truncated at 200 chars,
        and a Swedish summary of the five counts.

        Requirements: 9.1, 9.2, 9.6, 9.8, 9.10.
        """
        self._bulk_error_label.setVisible(False)
        self._bulk_results_widget.setVisible(False)
        self._bulk_plan = None

        text = self._bulk_paste_edit.toPlainText()
        if not text.strip():
            self._bulk_error_label.setText("Klistra in minst en referensrad.")
            self._bulk_error_label.setVisible(True)
            return

        # Determine person_ids and place_id from the current residence context.
        person_ids = [self._person_id] if self._person_id else []
        place_id = self._residence.place_id if self._residence else ""

        if not person_ids:
            self._bulk_error_label.setText(
                "Ingen person vald – kan inte skapa plan."
            )
            self._bulk_error_label.setVisible(True)
            return

        if not place_id:
            self._bulk_error_label.setText(
                "Ingen plats vald – kan inte skapa plan."
            )
            self._bulk_error_label.setVisible(True)
            return

        role = self.get_role_in_household()

        request = BulkRequest(
            text=text,
            person_ids=person_ids,
            place_id=place_id,
            role_in_household=role,
        )

        try:
            plan = plan_bulk_attach(request, self._project_data)
        except BulkLimitError as exc:
            # Requirement 9.8: refuse and display which limit was exceeded.
            self._bulk_error_label.setText(str(exc))
            self._bulk_error_label.setVisible(True)
            return

        self._bulk_plan = plan
        self._display_bulk_plan(plan)

    def _display_bulk_plan(self, plan: BulkPlan) -> None:
        """Populate the plan results area from the computed BulkPlan.

        Shows candidates with prefilled spans (unselectable when incomplete),
        unparsed lines truncated at 200 chars, and the five summary counts.
        """
        # --- Candidates table ---
        candidates = plan.candidates
        self._bulk_candidates_table.setRowCount(len(candidates))

        for row, candidate in enumerate(candidates):
            # Reference title from parsed data
            ref_text = (
                candidate.parsed.title
                if hasattr(candidate.parsed, "title")
                else str(candidate.parsed)
            )
            ref_item = QTableWidgetItem(ref_text)
            ref_item.setFlags(ref_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            from_item = QTableWidgetItem(candidate.observed_from)
            from_item.setFlags(from_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            to_item = QTableWidgetItem(candidate.observed_to)
            to_item.setFlags(to_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self._bulk_candidates_table.setItem(row, 0, ref_item)
            self._bulk_candidates_table.setItem(row, 1, from_item)
            self._bulk_candidates_table.setItem(row, 2, to_item)

            # Requirement 9.2: candidates with incomplete spans are unselectable
            is_complete = bool(candidate.observed_from and candidate.observed_to)
            if is_complete:
                # Selectable — preselect it
                self._bulk_candidates_table.selectRow(row)
            else:
                # Unselectable: disable selection for this row
                for col in range(3):
                    item = self._bulk_candidates_table.item(row, col)
                    if item:
                        item.setFlags(
                            item.flags() & ~Qt.ItemFlag.ItemIsSelectable
                        )

        # --- Unparsed lines (Requirement 9.6) ---
        if plan.unparsed_lines:
            truncated_lines = plan.unparsed_lines  # already truncated at 200
            unparsed_text = "Kunde inte tolkas:\n" + "\n".join(
                line[:200] for line in truncated_lines
            )
            self._bulk_unparsed_label.setText(unparsed_text)
            self._bulk_unparsed_label.setVisible(True)
        else:
            self._bulk_unparsed_label.setVisible(False)

        # --- Summary of five counts (Requirement 9.10) ---
        summary_parts = [
            f"Boenden att skapa: {plan.facts_to_create}",
            f"Boenden att utöka: {plan.facts_to_extend}",
            f"Observationer att bifoga: {plan.observations_to_attach}",
            f"Källor återanvända: {plan.sources_reused}",
            f"Rader ej tolkade: {len(plan.unparsed_lines)}",
        ]
        self._bulk_summary_label.setText("\n".join(summary_parts))

        self._bulk_results_widget.setVisible(True)

    def _on_bulk_execute(self) -> None:
        """Handle 'Utför' button click — apply the bulk plan atomically.

        Creates/extends Residence_Facts with deep copies so that a failure at
        any point leaves the Project in its prior state (all-or-nothing).

        Requirements: 9.3, 9.5, 9.9, 9.10.
        """
        if self._bulk_plan is None:
            return

        plan = self._bulk_plan

        # Collect selected candidate indices from the table
        selected_rows = set()
        for index in self._bulk_candidates_table.selectedIndexes():
            selected_rows.add(index.row())

        # Filter to only complete (selectable) candidates
        selected_candidates = []
        for row in sorted(selected_rows):
            if row < len(plan.candidates):
                candidate = plan.candidates[row]
                # Only include candidates that have both observed_from and
                # observed_to (the complete ones).
                if candidate.observed_from and candidate.observed_to:
                    selected_candidates.append(candidate)

        if not selected_candidates:
            self._bulk_error_label.setText(
                "Inga giltiga kandidater valda att tillämpa."
            )
            self._bulk_error_label.setVisible(True)
            return

        # Deep-copy the project state for atomic rollback on failure.
        backup_residences = copy.deepcopy(self._project_data.residences)
        backup_sources = copy.deepcopy(self._project_data.sources)

        try:
            self._apply_bulk_plan(plan, selected_candidates)
        except Exception as exc:
            # Requirement 9.9: all-or-nothing — restore the project state.
            self._project_data.residences = backup_residences
            self._project_data.sources = backup_sources
            logger.exception("Bulk operation failed, rolled back.")
            QMessageBox.warning(
                self,
                "Massåtgärd misslyckades",
                "Ingen del av massåtgärden tillämpades. "
                "Projektet är oförändrat.\n\n"
                f"Fel: {exc}",
            )
            return

        # Success — show summary (Requirement 9.10).
        facts_created = plan.facts_to_create
        facts_extended = plan.facts_to_extend
        obs_attached = len(selected_candidates) * len(plan.person_plans)
        sources_reused = plan.sources_reused
        unparsed_count = len(plan.unparsed_lines)

        summary = (
            f"Massåtgärd klar.\n"
            f"Boenden skapade: {facts_created}\n"
            f"Boenden utökade: {facts_extended}\n"
            f"Observationer bifogade: {obs_attached}\n"
            f"Källor återanvända: {sources_reused}\n"
            f"Rader ej tolkade: {unparsed_count}\n\n"
            f"Avvikande perioder per person justeras genom att "
            f"redigera varje boende efteråt."
        )

        QMessageBox.information(
            self,
            "Massåtgärd slutförd",
            summary,
        )

        # Clear the bulk panel state.
        self._bulk_plan = None
        self._bulk_paste_edit.clear()
        self._bulk_results_widget.setVisible(False)
        self._bulk_error_label.setVisible(False)

        # Reload the current residence if it was extended.
        if self._residence:
            for fact in self._project_data.residences:
                if fact.id == self._residence.id:
                    self._residence = fact
                    self._load_residence()
                    break

        self.save_requested.emit()

    def _apply_bulk_plan(
        self, plan: BulkPlan, selected_candidates: list
    ) -> None:
        """Apply the bulk plan by creating/extending facts for each person.

        Works on deep copies and commits atomically. If any step fails,
        the exception propagates and the caller restores the backup.

        Requirements: 9.3, 9.5, 9.9.
        """
        id_gen = self._make_id_generator()
        role = self.get_role_in_household()
        place_id = self._residence.place_id if self._residence else ""

        for person_plan in plan.person_plans:
            person_id = person_plan.person_id

            # Build the Observations for this person from selected candidates.
            new_observations: list[Observation] = []
            for candidate in selected_candidates:
                # Determine or create the source for this candidate.
                source_id = candidate.source_id
                if source_id is None:
                    # Create a new Source from the parsed reference.
                    source_id = self._create_source_from_candidate(
                        candidate, id_gen
                    )

                obs = Observation(
                    source_ref=SourceRef(
                        source_id=source_id, quality="primary"
                    ),
                    observed_from=candidate.observed_from,
                    observed_to=candidate.observed_to,
                    page_note="",
                )
                new_observations.append(obs)

            if person_plan.existing_fact_id:
                # Extend existing fact (Requirement 9.5: adjust core per Req 16).
                existing_fact = None
                for fact in self._project_data.residences:
                    if fact.id == person_plan.existing_fact_id:
                        existing_fact = fact
                        break
                if existing_fact is None:
                    raise RuntimeError(
                        f"Boende {person_plan.existing_fact_id} saknas."
                    )

                updated = attach_observations(existing_fact, new_observations)
                # Apply role if the existing fact has no role set.
                if role and not updated.role_in_household:
                    updated = ResidenceFact(
                        id=updated.id,
                        person_id=updated.person_id,
                        place_id=updated.place_id,
                        start=updated.start,
                        end=updated.end,
                        role_in_household=role,
                        observations=updated.observations,
                        notes=updated.notes,
                    )
                self._replace_fact_in_project(updated)
            else:
                # Create a new Residence_Fact.
                new_id = id_gen.generate("residence")
                new_fact = ResidenceFact(
                    id=new_id,
                    person_id=person_id,
                    place_id=place_id,
                    start=Endpoint(),
                    end=Endpoint(),
                    role_in_household=role,
                    observations=[],
                )
                # Attach observations (which also tightens the core).
                new_fact = attach_observations(new_fact, new_observations)
                self._project_data.residences.append(new_fact)

    def _create_source_from_candidate(
        self, candidate, id_gen: IDGenerator
    ) -> str:
        """Create a new Source from a parsed reference candidate.

        Adds the Source to the project and returns its id.
        """
        parsed = candidate.parsed
        new_id = id_gen.generate("source")

        # Build structured reference fields from the parsed data.
        fields: dict = {}
        if hasattr(parsed, "structured_fields"):
            for key, value in parsed.structured_fields.items():
                fields[key] = value

        source = Source(
            id=new_id,
            provider=getattr(parsed, "leverantor_name", ""),
            source_type=self._map_kalltyp_to_source_type(
                getattr(parsed, "kalltyp_name", "")
            ),
            title=getattr(parsed, "title", ""),
            reference_text=getattr(parsed, "reference_text", ""),
            structured_reference=StructuredReference(fields=fields),
        )
        self._project_data.sources.append(source)
        return new_id

    @staticmethod
    def _map_kalltyp_to_source_type(kalltyp_name: str) -> str:
        """Map a kalltyp name to a source_type string.

        This mirrors the mapping in residence_edit_ops._map_kalltyp_to_source_type.
        """
        church_book_types = {
            "Husförhörslängd",
            "Församlingsbok",
            "Födelse- och dopbok",
            "Lysnings- och vigselbok",
            "Död- och begravningsbok",
            "Inflyttningslängd",
            "Utflyttningslängd",
            "In- och Utflyttningslängd",
            "Konfirmationsbok",
            "Mantalslängd",
        }
        if kalltyp_name in church_book_types:
            return "church_book"
        if kalltyp_name == "Folkräkning":
            return "census"
        if kalltyp_name in ("Sveriges Dödbok Webb",):
            return "database"
        return "other"
