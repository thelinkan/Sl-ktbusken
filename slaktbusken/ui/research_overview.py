"""Research overview window.

One window with three modes over the same project data:

* cases ("Forskningsöversikt"): a searchable, sortable table of research cases;
* to-do ("Att göra"): the pending actions;
* hypotheses ("Hypoteser"): one row per hypothesis, not per case.

The row building and filtering are pure functions at the top of the module so
they can be tested without Qt. The window itself only presents them and asks its
host to open things through signals; it never changes project data.

``refresh()`` rebuilds all three tables from a fresh :class:`ResearchIndex` and
keeps the current selection and sort order, so the window can be registered for
the research-changed notification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import ResearchCase, case_entity_links, is_pending
from slaktbusken.services.research_entities import (
    LINKABLE_ENTITY_TYPES,
    entity_label,
    entity_label_or_marker,
)
from slaktbusken.services.research_index import ResearchIndex
from slaktbusken.ui.dialogs.entity_picker_dialog import EntityPickerDialog
from slaktbusken.ui.swedish_locale import (
    RESEARCH_PRIORITY_LABELS,
    RESEARCH_STATUS_LABELS,
    get_hypothesis_assessment_label,
    get_research_entity_type_label,
    get_research_priority_label,
    get_research_status_label,
)

MODE_CASES = "cases"
MODE_TODO = "todo"
MODE_HYPOTHESES = "hypotheses"
_MODES = (MODE_CASES, MODE_TODO, MODE_HYPOTHESES)

_NO_TITLE = "(utan rubrik)"
_NO_STATEMENT = "(utan formulering)"

_ROLE_ID = Qt.ItemDataRole.UserRole
_ROLE_CASE = Qt.ItemDataRole.UserRole + 1


# ---------------------------------------------------------------------------
# Pure logic: case mode
# ---------------------------------------------------------------------------


@dataclass
class CaseFilter:
    """Filter for the case table. Empty / "all" values do not filter.

    Attributes:
        status: A status key, or "" for any.
        priority: A priority key, or "" for any.
        entity_type: Only cases linking an entity of this type, or "" for any.
        entity_id: With *entity_type*, only cases linking this exact entity.
        pending: ``"all"``, ``"has"`` (has pending actions) or ``"none"``.
        hypotheses: ``"all"``, ``"has"`` or ``"none"``.
        text: Case-insensitive substring of the title or the question.
        include_closed: Show closed cases. A status filter of ``closed`` shows
            them regardless, since that is what was asked for.
    """

    status: str = ""
    priority: str = ""
    entity_type: str = ""
    entity_id: str = ""
    pending: str = "all"
    hypotheses: str = "all"
    text: str = ""
    include_closed: bool = False


@dataclass(frozen=True)
class OverviewCaseRow:
    """One case row; ``primary_label`` is resolved from the project at build time."""

    case_id: str
    title: str
    status: str
    status_label: str
    priority: str
    priority_label: str
    primary_label: str
    hypothesis_count: int
    pending_count: int
    action_count: int


def _has_filter(mode: str, present: bool) -> bool:
    if mode == "has":
        return present
    if mode == "none":
        return not present
    return True


def _case_matches(
    case: ResearchCase,
    index: ResearchIndex,
    criteria: CaseFilter,
) -> bool:
    if criteria.status:
        if case.status != criteria.status:
            return False
    elif case.status == "closed" and not criteria.include_closed:
        return False
    if criteria.priority and case.priority != criteria.priority:
        return False

    if criteria.entity_type:
        links = case_entity_links(case)
        if criteria.entity_id:
            if not any(
                link.entity_type == criteria.entity_type
                and link.entity_id == criteria.entity_id
                for link in links
            ):
                return False
        elif not any(link.entity_type == criteria.entity_type for link in links):
            return False

    if not _has_filter(criteria.pending, index.pending_action_count(case.id) > 0):
        return False
    if not _has_filter(criteria.hypotheses, bool(index.hypotheses_for_case(case.id))):
        return False

    needle = criteria.text.strip().lower()
    if needle and needle not in case.title.lower() and needle not in case.description.lower():
        return False
    return True


def build_overview_case_rows(
    data: ProjectData, criteria: Optional[CaseFilter] = None
) -> list[OverviewCaseRow]:
    """Return the case table rows that pass *criteria*, in project order."""
    criteria = criteria or CaseFilter()
    index = ResearchIndex(data)
    rows: list[OverviewCaseRow] = []
    for case in data.research_cases:
        if not _case_matches(case, index, criteria):
            continue
        primary = case.primary_entity_ref
        primary_label = (
            entity_label_or_marker(data, primary.entity_type, primary.entity_id)
            if primary is not None
            else ""
        )
        rows.append(
            OverviewCaseRow(
                case_id=case.id,
                title=case.title.strip() or _NO_TITLE,
                status=case.status,
                status_label=get_research_status_label(case.status),
                priority=case.priority,
                priority_label=get_research_priority_label(case.priority),
                primary_label=primary_label,
                hypothesis_count=len(index.hypotheses_for_case(case.id)),
                pending_count=index.pending_action_count(case.id),
                action_count=len(index.actions_for_case(case.id)),
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Pure logic: to-do mode
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TodoRow:
    """One pending action with its owning case."""

    action_id: str
    case_id: str
    title: str
    case_title: str
    case_status: str
    case_status_label: str


def build_todo_rows(
    data: ProjectData, include_closed: bool = False, text: str = ""
) -> list[TodoRow]:
    """Return the pending actions.

    By default only actions of cases that are not closed are listed;
    *include_closed* adds those of closed cases. *text* filters on the action
    title or the case title. Actions whose case is missing are skipped (the
    consistency report covers them). Order: case order, then ``sort_order``.
    """
    cases = {case.id: case for case in data.research_cases}
    case_position = {case.id: i for i, case in enumerate(data.research_cases)}
    needle = text.strip().lower()
    rows: list[tuple[int, int, int, TodoRow]] = []
    for position, action in enumerate(data.research_actions):
        if not is_pending(action):
            continue
        case = cases.get(action.research_case_id)
        if case is None:
            continue
        if case.status == "closed" and not include_closed:
            continue
        title = action.title.strip() or _NO_TITLE
        case_title = case.title.strip() or _NO_TITLE
        if needle and needle not in title.lower() and needle not in case_title.lower():
            continue
        rows.append(
            (
                case_position[case.id],
                action.sort_order,
                position,
                TodoRow(
                    action_id=action.id,
                    case_id=case.id,
                    title=title,
                    case_title=case_title,
                    case_status=case.status,
                    case_status_label=get_research_status_label(case.status),
                ),
            )
        )
    rows.sort(key=lambda r: r[:3])
    return [r[3] for r in rows]


# ---------------------------------------------------------------------------
# Pure logic: hypothesis mode
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OverviewHypothesisRow:
    """One hypothesis with its owning case."""

    hypothesis_id: str
    case_id: str
    statement: str
    assessment: str
    assessment_label: str
    case_title: str


def build_overview_hypothesis_rows(
    data: ProjectData, text: str = ""
) -> list[OverviewHypothesisRow]:
    """Return one row per hypothesis, in project order.

    *text* filters on the statement or the owning case title. A hypothesis whose
    case is missing is skipped; it has no case to open.
    """
    cases = {case.id: case for case in data.research_cases}
    needle = text.strip().lower()
    rows: list[OverviewHypothesisRow] = []
    for hypothesis in data.research_hypotheses:
        case = cases.get(hypothesis.research_case_id)
        if case is None:
            continue
        statement = hypothesis.statement.strip() or _NO_STATEMENT
        case_title = case.title.strip() or _NO_TITLE
        if needle and needle not in statement.lower() and needle not in case_title.lower():
            continue
        rows.append(
            OverviewHypothesisRow(
                hypothesis_id=hypothesis.id,
                case_id=case.id,
                statement=statement,
                assessment=hypothesis.assessment,
                assessment_label=get_hypothesis_assessment_label(hypothesis.assessment),
                case_title=case_title,
            )
        )
    return rows


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------


class _SortItem(QTableWidgetItem):
    """Table item that sorts by an explicit key instead of its text."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        mine = self.data(Qt.ItemDataRole.UserRole + 5)
        theirs = other.data(Qt.ItemDataRole.UserRole + 5)
        if mine is not None and theirs is not None:
            return mine < theirs
        return super().__lt__(other)


def _item(text: str, sort_key=None) -> QTableWidgetItem:
    item = _SortItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if sort_key is None:
        sort_key = text.lower()
    item.setData(Qt.ItemDataRole.UserRole + 5, sort_key)
    return item


class ResearchOverview(QWidget):
    """The research overview window (cases, to-do and hypotheses).

    Signals:
        open_case_requested(str): Open the case with this id for editing.
        create_case_requested: Create a new case.
        open_action_requested(str, str): Open the owning case (first argument)
            and show the action (second argument).

    Args:
        project_data: The project data.
        initial_mode: ``"cases"``, ``"todo"`` or ``"hypotheses"``.
        parent: Optional parent widget.
    """

    open_case_requested = Signal(str)
    create_case_requested = Signal()
    open_action_requested = Signal(str, str)
    delete_case_requested = Signal(str)

    def __init__(
        self,
        project_data: ProjectData,
        initial_mode: str = MODE_CASES,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Forskning")
        self._data = project_data
        self._entity_filter: tuple[str, str] = ("", "")
        self._setup_ui()
        self.set_mode(initial_mode)
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        """Show one of the three modes."""
        if mode not in _MODES:
            mode = MODE_CASES
        self._tabs.setCurrentIndex(_MODES.index(mode))

    def mode(self) -> str:
        """Return the mode currently shown."""
        return _MODES[self._tabs.currentIndex()]

    def refresh(self) -> None:
        """Rebuild all three tables, keeping selection and sort order."""
        self._fill_cases()
        self._fill_todo()
        self._fill_hypotheses()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)
        self._tabs.addTab(self._build_cases_page(), "Forskningsöversikt")
        self._tabs.addTab(self._build_todo_page(), "Att göra")
        self._tabs.addTab(self._build_hypotheses_page(), "Hypoteser")

    @staticmethod
    def _make_table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSortingEnabled(True)
        return table

    def _build_cases_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        bar = QHBoxLayout()
        self._status_filter = QComboBox()
        self._status_filter.addItem("Alla statusar", "")
        for key, label in RESEARCH_STATUS_LABELS.items():
            self._status_filter.addItem(label, key)
        self._priority_filter = QComboBox()
        self._priority_filter.addItem("Alla prioriteter", "")
        for key, label in RESEARCH_PRIORITY_LABELS.items():
            self._priority_filter.addItem(label, key)
        self._type_filter = QComboBox()
        self._type_filter.addItem("Alla objekttyper", "")
        for entity_type in LINKABLE_ENTITY_TYPES:
            self._type_filter.addItem(get_research_entity_type_label(entity_type), entity_type)
        self._entity_button = QPushButton("Valfritt objekt...")
        self._entity_clear = QPushButton("Rensa objekt")
        self._pending_filter = QComboBox()
        self._pending_filter.addItem("Åtgärder: alla", "all")
        self._pending_filter.addItem("Har väntande åtgärder", "has")
        self._pending_filter.addItem("Saknar väntande åtgärder", "none")
        self._hyp_filter = QComboBox()
        self._hyp_filter.addItem("Hypoteser: alla", "all")
        self._hyp_filter.addItem("Har hypoteser", "has")
        self._hyp_filter.addItem("Saknar hypoteser", "none")
        for widget in (
            self._status_filter,
            self._priority_filter,
            self._type_filter,
            self._entity_button,
            self._entity_clear,
            self._pending_filter,
            self._hyp_filter,
        ):
            bar.addWidget(widget)
        layout.addLayout(bar)

        bar2 = QHBoxLayout()
        self._case_search = QLineEdit()
        self._case_search.setPlaceholderText("Sök i rubrik och frågeställning...")
        self._case_search.setClearButtonEnabled(True)
        self._show_closed = QCheckBox("Visa avslutade")
        self._new_case_button = QPushButton("Nytt ärende")
        self._open_case_button = QPushButton("Öppna")
        self._delete_case_button = QPushButton("Ta bort forskningsärendet...")
        bar2.addWidget(self._case_search, 1)
        bar2.addWidget(self._show_closed)
        bar2.addWidget(self._new_case_button)
        bar2.addWidget(self._open_case_button)
        bar2.addWidget(self._delete_case_button)
        layout.addLayout(bar2)

        self._cases_table = self._make_table(
            [
                "Rubrik",
                "Status",
                "Prioritet",
                "Huvudobjekt",
                "Antal hypoteser",
                "Nästa åtgärder",
                "Antal åtgärder",
            ]
        )
        layout.addWidget(self._cases_table)

        for combo in (
            self._status_filter,
            self._priority_filter,
            self._type_filter,
            self._pending_filter,
            self._hyp_filter,
        ):
            combo.currentIndexChanged.connect(self._fill_cases)
        self._type_filter.currentIndexChanged.connect(self._on_type_filter_changed)
        self._case_search.textChanged.connect(self._fill_cases)
        self._show_closed.toggled.connect(self._fill_cases)
        self._entity_button.clicked.connect(self._on_pick_entity)
        self._entity_clear.clicked.connect(self._on_clear_entity)
        self._new_case_button.clicked.connect(self.create_case_requested.emit)
        self._open_case_button.clicked.connect(self._on_open_selected_case)
        self._delete_case_button.clicked.connect(self._on_delete_selected_case)
        self._cases_table.itemDoubleClicked.connect(lambda _i: self._on_open_selected_case())
        self._cases_table.itemSelectionChanged.connect(self._update_buttons)
        return page

    def _build_todo_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        bar = QHBoxLayout()
        self._todo_search = QLineEdit()
        self._todo_search.setPlaceholderText("Sök åtgärd eller ärende...")
        self._todo_search.setClearButtonEnabled(True)
        self._todo_include_closed = QCheckBox("Inkludera avslutade ärenden")
        self._todo_open_action = QPushButton("Öppna åtgärden")
        self._todo_open_case = QPushButton("Öppna ärendet")
        bar.addWidget(self._todo_search, 1)
        bar.addWidget(self._todo_include_closed)
        bar.addWidget(self._todo_open_action)
        bar.addWidget(self._todo_open_case)
        layout.addLayout(bar)
        self._todo_table = self._make_table(["Åtgärd", "Forskningsärende", "Ärendets status"])
        layout.addWidget(self._todo_table)

        self._todo_search.textChanged.connect(self._fill_todo)
        self._todo_include_closed.toggled.connect(self._fill_todo)
        self._todo_open_action.clicked.connect(self._on_open_selected_action)
        self._todo_open_case.clicked.connect(self._on_open_selected_todo_case)
        self._todo_table.itemDoubleClicked.connect(lambda _i: self._on_open_selected_action())
        self._todo_table.itemSelectionChanged.connect(self._update_buttons)
        return page

    def _build_hypotheses_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        bar = QHBoxLayout()
        self._hyp_search = QLineEdit()
        self._hyp_search.setPlaceholderText("Sök hypotes eller ärende...")
        self._hyp_search.setClearButtonEnabled(True)
        self._hyp_open_case = QPushButton("Öppna ärendet")
        bar.addWidget(self._hyp_search, 1)
        bar.addWidget(self._hyp_open_case)
        layout.addLayout(bar)
        self._hyp_table = self._make_table(["Hypotes", "Bedömning", "Forskningsärende"])
        layout.addWidget(self._hyp_table)

        self._hyp_search.textChanged.connect(self._fill_hypotheses)
        self._hyp_open_case.clicked.connect(self._on_open_selected_hypothesis_case)
        self._hyp_table.itemDoubleClicked.connect(
            lambda _i: self._on_open_selected_hypothesis_case()
        )
        self._hyp_table.itemSelectionChanged.connect(self._update_buttons)
        return page

    # ------------------------------------------------------------------
    # Filling (keeps selection and sort)
    # ------------------------------------------------------------------

    @staticmethod
    def _selected_key(table: QTableWidget) -> Optional[str]:
        rows = table.selectionModel().selectedRows() if table.selectionModel() else []
        if not rows:
            return None
        item = table.item(rows[0].row(), 0)
        return item.data(_ROLE_ID) if item else None

    @staticmethod
    def _fill_table(table: QTableWidget, rows: list[list[QTableWidgetItem]], keys: list[str]) -> None:
        selected = ResearchOverview._selected_key(table)
        header = table.horizontalHeader()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        sorted_before = header.isSortIndicatorShown()

        table.setSortingEnabled(False)
        table.setRowCount(len(rows))
        for row, items in enumerate(rows):
            for column, item in enumerate(items):
                table.setItem(row, column, item)
            items[0].setData(_ROLE_ID, keys[row])
        table.setSortingEnabled(True)
        if sorted_before:
            table.sortItems(sort_column, sort_order)

        if selected is not None:
            for row in range(table.rowCount()):
                if table.item(row, 0).data(_ROLE_ID) == selected:
                    table.selectRow(row)
                    break

    def _current_case_filter(self) -> CaseFilter:
        return CaseFilter(
            status=self._status_filter.currentData() or "",
            priority=self._priority_filter.currentData() or "",
            entity_type=self._type_filter.currentData() or "",
            entity_id=self._entity_filter[1] if self._type_filter.currentData() else "",
            pending=self._pending_filter.currentData(),
            hypotheses=self._hyp_filter.currentData(),
            text=self._case_search.text(),
            include_closed=self._show_closed.isChecked(),
        )

    def case_rows(self) -> list[OverviewCaseRow]:
        """The rows the case table currently shows (before user sorting)."""
        return build_overview_case_rows(self._data, self._current_case_filter())

    def _fill_cases(self, *_args) -> None:
        rows = self.case_rows()
        items = [
            [
                _item(r.title),
                _item(r.status_label),
                _item(r.priority_label),
                _item(r.primary_label),
                _item(str(r.hypothesis_count), r.hypothesis_count),
                _item(str(r.pending_count), r.pending_count),
                _item(str(r.action_count), r.action_count),
            ]
            for r in rows
        ]
        self._fill_table(self._cases_table, items, [r.case_id for r in rows])
        self._update_buttons()

    def todo_rows(self) -> list[TodoRow]:
        """The rows the to-do table currently shows."""
        return build_todo_rows(
            self._data, self._todo_include_closed.isChecked(), self._todo_search.text()
        )

    def _fill_todo(self, *_args) -> None:
        rows = self.todo_rows()
        items = []
        for r in rows:
            first = _item(r.title)
            first.setData(_ROLE_CASE, r.case_id)
            items.append([first, _item(r.case_title), _item(r.case_status_label)])
        self._fill_table(self._todo_table, items, [r.action_id for r in rows])
        for row in range(self._todo_table.rowCount()):
            action_id = self._todo_table.item(row, 0).data(_ROLE_ID)
            case_id = next((r.case_id for r in rows if r.action_id == action_id), "")
            self._todo_table.item(row, 0).setData(_ROLE_CASE, case_id)
        self._update_buttons()

    def hypothesis_rows(self) -> list[OverviewHypothesisRow]:
        """The rows the hypothesis table currently shows."""
        return build_overview_hypothesis_rows(self._data, self._hyp_search.text())

    def _fill_hypotheses(self, *_args) -> None:
        rows = self.hypothesis_rows()
        items = [
            [_item(r.statement), _item(r.assessment_label), _item(r.case_title)] for r in rows
        ]
        self._fill_table(self._hyp_table, items, [r.hypothesis_id for r in rows])
        for row in range(self._hyp_table.rowCount()):
            hypothesis_id = self._hyp_table.item(row, 0).data(_ROLE_ID)
            case_id = next((r.case_id for r in rows if r.hypothesis_id == hypothesis_id), "")
            self._hyp_table.item(row, 0).setData(_ROLE_CASE, case_id)
        self._update_buttons()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_type_filter_changed(self, _index: int) -> None:
        # A specific entity only makes sense for the type it belongs to.
        if self._entity_filter[0] != self._type_filter.currentData():
            self._entity_filter = ("", "")
            self._update_entity_button()

    def _update_entity_button(self) -> None:
        entity_type, entity_id = self._entity_filter
        label = entity_label(self._data, entity_type, entity_id) if entity_id else None
        self._entity_button.setText(label if label else "Valfritt objekt...")

    def _on_pick_entity(self) -> None:
        entity_type = self._type_filter.currentData()
        types = (entity_type,) if entity_type else LINKABLE_ENTITY_TYPES
        picked = EntityPickerDialog.pick(self._data, types, "Filtrera på objekt", self)
        if picked is None:
            return
        self._entity_filter = picked
        index = self._type_filter.findData(picked[0])
        self._type_filter.blockSignals(True)
        self._type_filter.setCurrentIndex(index)
        self._type_filter.blockSignals(False)
        self._update_entity_button()
        self._fill_cases()

    def _on_clear_entity(self) -> None:
        self._entity_filter = ("", "")
        self._update_entity_button()
        self._fill_cases()

    def _update_buttons(self) -> None:
        has_case = self._selected_key(self._cases_table) is not None
        self._open_case_button.setEnabled(has_case)
        self._delete_case_button.setEnabled(has_case)
        has_todo = self._selected_key(self._todo_table) is not None
        self._todo_open_action.setEnabled(has_todo)
        self._todo_open_case.setEnabled(has_todo)
        self._hyp_open_case.setEnabled(self._selected_key(self._hyp_table) is not None)

    def _on_open_selected_case(self) -> None:
        case_id = self._selected_key(self._cases_table)
        if case_id:
            self.open_case_requested.emit(case_id)

    def _on_delete_selected_case(self) -> None:
        case_id = self._selected_key(self._cases_table)
        if case_id:
            self.delete_case_requested.emit(case_id)

    @staticmethod
    def _selected_case_of(table: QTableWidget) -> Optional[str]:
        rows = table.selectionModel().selectedRows()
        if not rows:
            return None
        return table.item(rows[0].row(), 0).data(_ROLE_CASE)

    def _on_open_selected_action(self) -> None:
        action_id = self._selected_key(self._todo_table)
        case_id = self._selected_case_of(self._todo_table)
        if action_id and case_id:
            self.open_action_requested.emit(case_id, action_id)

    def _on_open_selected_todo_case(self) -> None:
        case_id = self._selected_case_of(self._todo_table)
        if case_id:
            self.open_case_requested.emit(case_id)

    def _on_open_selected_hypothesis_case(self) -> None:
        case_id = self._selected_case_of(self._hyp_table)
        if case_id:
            self.open_case_requested.emit(case_id)
