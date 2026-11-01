"""The Candidate_Register window "Sammanslagningskandidater" (requirement 15).

Lists every merge candidate in a sortable table with search and filters. The
rows come from :func:`slaktbusken.services.candidate_register.query_register`;
the window only displays them. Edits go through ``CandidateEditorDialog`` and
therefore through ``ProjectService``; no merge is ever started from here.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.merge_candidate import CANDIDATE_ASSESSMENTS
from slaktbusken.services.candidate_register import (
    COLUMN_HEADERS,
    MAX_SEARCH_LENGTH,
    NO_MATCH_MESSAGE,
    RegisterFilters,
    query_register,
)
from slaktbusken.services.editor_registry import EditorRegistry
from slaktbusken.services.parent_service import _format_person_name
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge.candidate_editor_dialog import CandidateEditorDialog
from slaktbusken.ui.swedish_locale import get_candidate_assessment_label

WINDOW_TITLE = "Sammanslagningskandidater"
REFRESH_DELAY_MS = 50  # well inside the 1 second of requirement 15.10

_ALL = "__all__"
_DEFAULT = "__default__"


class CandidateRegisterWindow(QWidget):
    """Searchable, sortable, filterable table of merge candidates.

    Args:
        service: The project service owning the data.
        gateway: Optional merge gateway; a double-click calls
            ``gateway.open_comparison(person_1_id, person_2_id)``.
        registry: Optional editor registry handed to candidate editors.
        parent: Optional parent widget.
    """

    candidate_activated = Signal(str, str)

    def __init__(
        self,
        service: ProjectService,
        gateway=None,
        registry: Optional[EditorRegistry] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._gateway = gateway
        self._registry = registry
        self._sort_column: Optional[int] = None
        self._descending = False
        self._building = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(REFRESH_DELAY_MS)
        self._refresh_timer.timeout.connect(self.refresh)
        self._remove_listener = None
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(980, 520)
        self._build_ui()
        self._reload_filter_choices()
        self.refresh()
        self._remove_listener = self._service.add_merge_listener(self.schedule_refresh)

    # -- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._search = QLineEdit()
        self._search.setMaxLength(MAX_SEARCH_LENGTH)
        self._search.setPlaceholderText("Sök i personer, kommentarer och forskningsärenden")
        self._search.setClearButtonEnabled(True)
        layout.addWidget(self._search)

        filters = QHBoxLayout()
        self._assessment = QComboBox()
        self._assessment.addItem("Bedömning: standard", _DEFAULT)
        for key in CANDIDATE_ASSESSMENTS:
            self._assessment.addItem(get_candidate_assessment_label(key), key)
        self._assessment.addItem("Bedömning: alla", _ALL)
        self._enabled = QComboBox()
        self._enabled.addItem("Aktiva", None)
        self._enabled.addItem("Inaktiva", False)
        self._person = QComboBox()
        self._case = QComboBox()
        self._candidate_text = QLineEdit()
        self._candidate_text.setPlaceholderText("Kandidatnamn eller id")
        self._candidate_text.setClearButtonEnabled(True)
        self._assessment.setToolTip("Filtrera på bedömning")
        self._enabled.setToolTip("Visa aktiva eller inaktiva kandidater")
        self._person.setToolTip("Filtrera på en viss person")
        self._case.setToolTip("Filtrera på kopplat forskningsärende")
        for widget in (
            self._assessment,
            self._enabled,
            self._person,
            self._case,
            self._candidate_text,
        ):
            filters.addWidget(widget, 1)
        layout.addLayout(filters)

        self._table = QTableWidget(0, len(COLUMN_HEADERS))
        self._table.setHorizontalHeaderLabels(list(COLUMN_HEADERS))
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        layout.addWidget(self._table, 1)

        self._empty_label = QLabel(NO_MATCH_MESSAGE)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_label)

        buttons = QHBoxLayout()
        self._edit_button = QPushButton("Redigera kandidat…")
        self._open_button = QPushButton("Öppna jämförelse")
        buttons.addWidget(self._edit_button)
        buttons.addWidget(self._open_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._search.textChanged.connect(self.refresh)
        self._candidate_text.textChanged.connect(self.refresh)
        for combo in (self._assessment, self._enabled, self._person, self._case):
            combo.currentIndexChanged.connect(self.refresh)
        header.sectionClicked.connect(self._on_header_clicked)
        self._table.cellDoubleClicked.connect(self._on_double_clicked)
        self._table.itemSelectionChanged.connect(self._update_buttons)
        self._edit_button.clicked.connect(self.edit_selected)
        self._open_button.clicked.connect(self.open_selected)

    # -- filters ---------------------------------------------------------

    def _reload_filter_choices(self) -> None:
        """Rebuild the person and case choices, keeping the current selection."""
        data = self._service.data
        keep_person = self._person.currentData()
        keep_case = self._case.currentData()
        self._building = True
        try:
            self._person.clear()
            self._person.addItem("Person: alla", None)
            used: set[str] = set()
            for cand in data.merge_candidates:
                used.add(cand.person_1_id)
                used.add(cand.person_2_id)
            names = {p.id: _format_person_name(p) for p in data.persons}
            for pid in sorted(used, key=lambda i: (names.get(i, i).casefold(), i)):
                shown = names.get(pid) or pid
                self._person.addItem(f"{shown} ({pid})", pid)
            self._case.clear()
            self._case.addItem("Ärende: alla", None)
            for case in data.research_cases:
                self._case.addItem(case.title.strip() or case.id, case.id)
            self._select_data(self._person, keep_person)
            self._select_data(self._case, keep_case)
        finally:
            self._building = False

    @staticmethod
    def _select_data(combo: QComboBox, value) -> None:
        index = combo.findData(value) if value is not None else 0
        combo.setCurrentIndex(index if index >= 0 else 0)

    def set_person_filter(self, person_id: Optional[str]) -> None:
        """Filter the register to one person (None clears the filter)."""
        self._reload_filter_choices()
        if person_id and self._person.findData(person_id) < 0:
            self._person.addItem(person_id, person_id)
        self._select_data(self._person, person_id)

    def current_filters(self) -> RegisterFilters:
        """The filters selected in the controls."""
        choice = self._assessment.currentData()
        if choice == _DEFAULT:
            assessments = None
        elif choice == _ALL:
            assessments = frozenset(CANDIDATE_ASSESSMENTS)
        else:
            assessments = frozenset({choice})
        return RegisterFilters(
            assessments=assessments,
            enabled=self._enabled.currentData(),
            person_id=self._person.currentData(),
            candidate_text=self._candidate_text.text(),
            research_case_id=self._case.currentData(),
        )

    # -- table -----------------------------------------------------------

    def schedule_refresh(self) -> None:
        """Refresh shortly; many notifications in a row cost one rebuild."""
        self._refresh_timer.start()

    def refresh(self, *_args) -> None:
        """Rebuild rows keeping sort, search text and filters."""
        if self._building:
            return
        self._reload_filter_choices_if_needed()
        selected = self.selected_candidate_id()
        rows = query_register(
            self._service.data,
            self.current_filters(),
            self._search.text(),
            self._sort_column,
            self._descending,
        )
        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = (
                row.person_1_name,
                row.person_2_name,
                row.assessment_text,
                "Ja" if row.enabled else "Nej",
                row.latest_comment,
                row.case_title,
            )
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row.candidate.id)
                self._table.setItem(r, c, item)
            if row.candidate.id == selected:
                self._table.selectRow(r)
        header = self._table.horizontalHeader()
        if self._sort_column is not None:
            order = (
                Qt.SortOrder.DescendingOrder
                if self._descending
                else Qt.SortOrder.AscendingOrder
            )
            header.setSortIndicator(self._sort_column, order)
            header.setSortIndicatorShown(True)
        else:
            header.setSortIndicatorShown(False)
        self._empty_label.setVisible(not rows)
        self._update_buttons()

    def _reload_filter_choices_if_needed(self) -> None:
        """Keep the person and case choices in step with the data."""
        data = self._service.data
        wanted_cases = 1 + len(data.research_cases)
        used = {
            pid
            for cand in data.merge_candidates
            for pid in (cand.person_1_id, cand.person_2_id)
        }
        have_people = {
            self._person.itemData(i) for i in range(1, self._person.count())
        }
        if self._case.count() != wanted_cases or not used <= have_people:
            self._reload_filter_choices()

    def _on_header_clicked(self, column: int) -> None:
        if self._sort_column == column:
            self._descending = not self._descending
        else:
            self._sort_column = column
            self._descending = False
        self.refresh()

    def row_count(self) -> int:
        """Number of rows currently shown."""
        return self._table.rowCount()

    def cell_text(self, row: int, column: int) -> str:
        """Text of one cell."""
        item = self._table.item(row, column)
        return item.text() if item is not None else ""

    def selected_candidate_id(self) -> Optional[str]:
        """Id of the selected row's candidate, or None."""
        rows = self._table.selectionModel().selectedRows() if self._table.selectionModel() else []
        if not rows:
            return None
        item = self._table.item(rows[0].row(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _update_buttons(self) -> None:
        has_selection = self.selected_candidate_id() is not None
        self._edit_button.setEnabled(has_selection)
        self._open_button.setEnabled(has_selection)

    # -- actions ---------------------------------------------------------

    def _candidate(self, candidate_id: Optional[str]):
        return next(
            (c for c in self._service.data.merge_candidates if c.id == candidate_id),
            None,
        )

    def _on_double_clicked(self, row: int, _column: int) -> None:
        item = self._table.item(row, 0)
        if item is not None:
            self._open_comparison(item.data(Qt.ItemDataRole.UserRole))

    def open_selected(self) -> None:
        """Open the comparison for the selected row."""
        self._open_comparison(self.selected_candidate_id())

    def _open_comparison(self, candidate_id: Optional[str]) -> None:
        cand = self._candidate(candidate_id)
        if cand is None:
            return
        self.candidate_activated.emit(cand.person_1_id, cand.person_2_id)
        if self._gateway is not None:
            self._gateway.open_comparison(cand.person_1_id, cand.person_2_id)

    def edit_selected(self) -> None:
        """Edit assessment, active flag, research case and comments."""
        candidate_id = self.selected_candidate_id()
        if candidate_id is None:
            return
        dialog = CandidateEditorDialog(
            self._service, candidate_id, parent=self, registry=self._registry
        )
        dialog.exec()
        self.refresh()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
        self._refresh_timer.stop()
        super().closeEvent(event)
