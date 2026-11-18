"""Research section of the source editor.

Two distinct parts (Requirement 23):

* "Forskningsärenden om denna källa": cases that link the source directly;
* "Forskningsåtgärder där källan används": every action that cites the source as
  an examined source, including actions whose case is not itself linked to it.

An action's source reference records a source that was examined, which is not
the same as evidence for a hypothesis. This section therefore never presents
the reference as support for, or against, anything. It also changes no content
of the source.

The row builders are pure functions so they can be tested without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import is_pending
from slaktbusken.services.research_index import ResearchIndex
from slaktbusken.ui.swedish_locale import get_research_status_label
from slaktbusken.ui.widgets.research_tab import CaseRow, build_case_rows

CASES_HEADING = "Forskningsärenden om denna källa"
ACTIONS_HEADING = "Forskningsåtgärder där källan används"
EMPTY_CASES_TEXT = "Inga forskningsärenden handlar om denna källa."
EMPTY_ACTIONS_TEXT = "Ingen forskningsåtgärd har granskat denna källa."

_NO_TITLE = "(utan rubrik)"

STATE_PENDING = "Väntande"
STATE_COMPLETED = "Genomförd"


@dataclass(frozen=True)
class ActionUsageRow:
    """One action that cites the source as an examined source."""

    action_id: str
    case_id: str
    title: str
    state_label: str
    completed_date: str
    case_title: str
    case_status_label: str


def build_source_case_rows(index: ResearchIndex, source_id: str) -> list[CaseRow]:
    """Return the cases that link the source directly, each once."""
    return build_case_rows(index, "source", source_id)


def build_action_usage_rows(
    data: ProjectData, index: ResearchIndex, source_id: str
) -> list[ActionUsageRow]:
    """Return every action citing the source, whether or not its case links it.

    An action that cites the source more than once is listed once. Actions
    whose case is missing are left out; the consistency report covers those.
    """
    cases = {case.id: case for case in data.research_cases}
    rows: list[ActionUsageRow] = []
    seen: set[str] = set()
    for action in index.actions_for_source(source_id):
        if action.id in seen:
            continue
        seen.add(action.id)
        case = cases.get(action.research_case_id)
        if case is None:
            continue
        pending = is_pending(action)
        rows.append(
            ActionUsageRow(
                action_id=action.id,
                case_id=case.id,
                title=action.title.strip() or _NO_TITLE,
                state_label=STATE_PENDING if pending else STATE_COMPLETED,
                completed_date="" if pending else (action.completed_date or ""),
                case_title=case.title.strip() or _NO_TITLE,
                case_status_label=get_research_status_label(case.status),
            )
        )
    return rows


def distinct_case_count(
    case_rows: list[CaseRow], usage_rows: list[ActionUsageRow]
) -> int:
    """Count the distinct cases that concern the source or have examined it.

    A case counts once however many of its actions cite the source and even if
    it also links the source directly.
    """
    return len({row.case_id for row in case_rows} | {row.case_id for row in usage_rows})


def summary_text(distinct_cases: int, action_count: int) -> str:
    """Return the aggregate line, or an empty string when there is nothing."""
    if distinct_cases <= 0 and action_count <= 0:
        return ""
    cases = "1 forskningsärende" if distinct_cases == 1 else f"{distinct_cases} forskningsärenden"
    actions = "1 åtgärd" if action_count == 1 else f"{action_count} åtgärder"
    return f"{cases}, {actions} har granskat källan"


class SourceResearchSection(QWidget):
    """The source editor's "Forskning" content.

    Signals:
        open_case_requested(str): Open a case (one about the source, or the one
            owning a listed action).
        open_action_requested(str, str): Open the owning case (first argument)
            and show the action (second argument).
        create_case_requested: Create a case about the current source.

    Args:
        project_data: The project data.
        resolver: Returns the id of the source the editor shows, or None for a
            new, unsaved source.
        parent: Optional parent widget.
    """

    open_case_requested = Signal(str)
    open_action_requested = Signal(str, str)
    create_case_requested = Signal()

    _ROLE_ID = Qt.ItemDataRole.UserRole
    _ROLE_CASE = Qt.ItemDataRole.UserRole + 1

    def __init__(self, project_data: ProjectData, resolver, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._data = project_data
        self._resolver = resolver
        self._setup_ui()
        self.refresh()

    def source_id(self) -> Optional[str]:
        """The source the section currently shows."""
        return self._resolver() or None

    def refresh(self) -> None:
        """Rebuild both parts from a fresh index."""
        source_id = self.source_id()
        index = ResearchIndex(self._data)
        case_rows = build_source_case_rows(index, source_id) if source_id else []
        usage_rows = build_action_usage_rows(self._data, index, source_id) if source_id else []

        self._cases_tree.clear()
        for row in case_rows:
            item = QTreeWidgetItem([row.title, row.status_label, row.priority_label, row.pending_text])
            item.setData(0, self._ROLE_ID, row.case_id)
            self._cases_tree.addTopLevelItem(item)
        self._cases_tree.setVisible(bool(case_rows))
        self._cases_empty.setVisible(not case_rows)

        self._actions_tree.clear()
        for row in usage_rows:
            item = QTreeWidgetItem(
                [row.title, row.state_label, row.completed_date, row.case_title, row.case_status_label]
            )
            item.setData(0, self._ROLE_ID, row.action_id)
            item.setData(0, self._ROLE_CASE, row.case_id)
            self._actions_tree.addTopLevelItem(item)
        self._actions_tree.setVisible(bool(usage_rows))
        self._actions_empty.setVisible(not usage_rows)

        text = summary_text(distinct_case_count(case_rows, usage_rows), len(usage_rows))
        self._summary.setText(text)
        self._summary.setVisible(bool(text))
        self._new_button.setEnabled(source_id is not None)
        self._new_button.setToolTip("" if source_id else "Spara källan först.")
        self._update_buttons()

    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._summary = QLabel("")
        layout.addWidget(self._summary)

        heading = QLabel(CASES_HEADING)
        heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading)
        self._cases_empty = QLabel(EMPTY_CASES_TEXT)
        layout.addWidget(self._cases_empty)
        self._cases_tree = QTreeWidget()
        self._cases_tree.setHeaderLabels(["Rubrik", "Status", "Prioritet", "Nästa åtgärder"])
        self._cases_tree.setRootIsDecorated(False)
        self._cases_tree.itemSelectionChanged.connect(self._update_buttons)
        self._cases_tree.itemDoubleClicked.connect(lambda _i, _c: self._open_selected_case())
        layout.addWidget(self._cases_tree)
        case_buttons = QHBoxLayout()
        self._new_button = QPushButton("Nytt ärende om källan")
        self._open_case_button = QPushButton("Öppna ärendet")
        case_buttons.addWidget(self._new_button)
        case_buttons.addWidget(self._open_case_button)
        case_buttons.addStretch()
        layout.addLayout(case_buttons)
        self._new_button.clicked.connect(self.create_case_requested.emit)
        self._open_case_button.clicked.connect(self._open_selected_case)

        heading2 = QLabel(ACTIONS_HEADING)
        heading2.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading2)
        note = QLabel("Källan är angiven som granskad i åtgärden. Det är inte ett stöd för någon hypotes.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self._actions_empty = QLabel(EMPTY_ACTIONS_TEXT)
        layout.addWidget(self._actions_empty)
        self._actions_tree = QTreeWidget()
        self._actions_tree.setHeaderLabels(
            ["Åtgärd", "Tillstånd", "Färdigdatum", "Forskningsärende", "Ärendets status"]
        )
        self._actions_tree.setRootIsDecorated(False)
        self._actions_tree.itemSelectionChanged.connect(self._update_buttons)
        self._actions_tree.itemDoubleClicked.connect(lambda _i, _c: self._open_selected_action())
        layout.addWidget(self._actions_tree)
        action_buttons = QHBoxLayout()
        self._open_action_button = QPushButton("Öppna åtgärden")
        self._open_action_case_button = QPushButton("Öppna åtgärdens ärende")
        action_buttons.addWidget(self._open_action_button)
        action_buttons.addWidget(self._open_action_case_button)
        action_buttons.addStretch()
        layout.addLayout(action_buttons)
        self._open_action_button.clicked.connect(self._open_selected_action)
        self._open_action_case_button.clicked.connect(self._open_selected_action_case)

    def _selected(self, tree: QTreeWidget) -> Optional[QTreeWidgetItem]:
        items = tree.selectedItems()
        return items[0] if items else None

    def _update_buttons(self) -> None:
        self._open_case_button.setEnabled(self._selected(self._cases_tree) is not None)
        has_action = self._selected(self._actions_tree) is not None
        self._open_action_button.setEnabled(has_action)
        self._open_action_case_button.setEnabled(has_action)

    def _open_selected_case(self) -> None:
        item = self._selected(self._cases_tree)
        if item is not None:
            self.open_case_requested.emit(item.data(0, self._ROLE_ID))

    def _open_selected_action(self) -> None:
        item = self._selected(self._actions_tree)
        if item is not None:
            self.open_action_requested.emit(
                item.data(0, self._ROLE_CASE), item.data(0, self._ROLE_ID)
            )

    def _open_selected_action_case(self) -> None:
        item = self._selected(self._actions_tree)
        if item is not None:
            self.open_case_requested.emit(item.data(0, self._ROLE_CASE))
