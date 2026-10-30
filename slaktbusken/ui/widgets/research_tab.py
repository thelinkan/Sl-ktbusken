"""Research tab for entity editors.

Shows the research cases that link one entity directly, and, in a separate
section, the hypotheses that name the entity. The host editor (person, place,
media, event, source, DNA match) inserts this one widget and connects its
signals; the tab itself never changes project data.

The hypotheses section never feeds the indicator summary: only directly linked
cases are counted (Requirement 22).

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
from slaktbusken.services.research_index import ResearchIndex
from slaktbusken.ui.swedish_locale import (
    get_hypothesis_assessment_label,
    get_research_priority_label,
    get_research_status_label,
)
from slaktbusken.ui.widgets.research_indicator import (
    indicator_color,
    indicator_state,
    indicator_tooltip,
)

_NO_TITLE = "(utan rubrik)"
_NO_STATEMENT = "(utan formulering)"

EMPTY_CASES_TEXT = "Inga forskningsärenden kopplade."
EMPTY_HYPOTHESES_TEXT = "Inga hypoteser nämner detta objekt."


@dataclass(frozen=True)
class CaseRow:
    """One directly linked case, ready for display."""

    case_id: str
    title: str
    status_label: str
    priority_label: str
    pending_actions: int
    pending_text: str


@dataclass(frozen=True)
class HypothesisRow:
    """One hypothesis that names the entity, ready for display."""

    hypothesis_id: str
    case_id: str
    statement: str
    assessment_label: str
    case_title: str


def pending_actions_text(count: int) -> str:
    """Return the "Nästa åtgärder" cell text: empty when nothing is pending."""
    if count <= 0:
        return ""
    return "1 åtgärd" if count == 1 else f"{count} åtgärder"


def build_case_rows(
    index: ResearchIndex, entity_type: str, entity_id: str
) -> list[CaseRow]:
    """Return one row per case that links the entity directly, each exactly once."""
    rows: list[CaseRow] = []
    for case in index.cases_for_entity(entity_type, entity_id):
        pending = index.pending_action_count(case.id)
        rows.append(
            CaseRow(
                case_id=case.id,
                title=case.title.strip() or _NO_TITLE,
                status_label=get_research_status_label(case.status),
                priority_label=get_research_priority_label(case.priority),
                pending_actions=pending,
                pending_text=pending_actions_text(pending),
            )
        )
    return rows


def build_hypothesis_rows(
    index: ResearchIndex, entity_type: str, entity_id: str
) -> list[HypothesisRow]:
    """Return one row per hypothesis that names the entity, with its owning case."""
    rows: list[HypothesisRow] = []
    for hypothesis, case in index.hypotheses_for_entity(entity_type, entity_id):
        rows.append(
            HypothesisRow(
                hypothesis_id=hypothesis.id,
                case_id=case.id,
                statement=hypothesis.statement.strip() or _NO_STATEMENT,
                assessment_label=get_hypothesis_assessment_label(hypothesis.assessment),
                case_title=case.title.strip() or _NO_TITLE,
            )
        )
    return rows


class ResearchTab(QWidget):
    """Tab listing the research cases and hypotheses that concern one entity.

    Signals:
        open_case_requested(str): Open the case with this id.
        create_case_requested: Create a new case with this entity as its
            primary entity.
        link_existing_requested: Link this entity to an existing case.
        remove_association_requested(str): Remove this entity's links from the
            case with this id (the case itself is kept).
        open_hypothesis_case_requested(str): Open the case that owns a
            hypothesis shown in the hypotheses section.

    Args:
        project_data: The project data.
        entity_type: The research entity type of the host entity.
        entity_id: The id of the host entity.
        parent: Optional parent widget.
    """

    open_case_requested = Signal(str)
    create_case_requested = Signal()
    link_existing_requested = Signal()
    remove_association_requested = Signal(str)
    open_hypothesis_case_requested = Signal(str)

    _CASE_ID_ROLE = Qt.ItemDataRole.UserRole

    def __init__(
        self,
        project_data: ProjectData,
        entity_type: str,
        entity_id: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._project_data = project_data
        self._entity_type = entity_type
        self._entity_id = entity_id

        self._setup_ui()
        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Rebuild both sections from a fresh index of the current project data."""
        index = ResearchIndex(self._project_data)
        case_rows = build_case_rows(index, self._entity_type, self._entity_id)
        hypothesis_rows = build_hypothesis_rows(index, self._entity_type, self._entity_id)

        self._fill_cases(case_rows)
        self._fill_hypotheses(hypothesis_rows)
        self._update_summary(index)
        self._update_button_states()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._summary_label = QLabel("")
        layout.addWidget(self._summary_label)

        self._cases_empty_label = QLabel(EMPTY_CASES_TEXT)
        self._cases_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._cases_empty_label)

        self._cases_tree = QTreeWidget()
        self._cases_tree.setHeaderLabels(["Rubrik", "Status", "Prioritet", "Nästa åtgärder"])
        self._cases_tree.setRootIsDecorated(False)
        self._cases_tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self._cases_tree.itemSelectionChanged.connect(self._update_button_states)
        self._cases_tree.itemDoubleClicked.connect(self._on_case_double_clicked)
        layout.addWidget(self._cases_tree)

        buttons = QHBoxLayout()
        self._open_button = QPushButton("Öppna")
        self._new_button = QPushButton("Nytt ärende")
        self._link_button = QPushButton("Koppla befintligt")
        self._remove_button = QPushButton("Ta bort kopplingen")
        for button in (
            self._open_button,
            self._new_button,
            self._link_button,
            self._remove_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)

        self._open_button.clicked.connect(self._on_open_clicked)
        self._new_button.clicked.connect(self.create_case_requested.emit)
        self._link_button.clicked.connect(self.link_existing_requested.emit)
        self._remove_button.clicked.connect(self._on_remove_clicked)

        heading = QLabel("Förekommer i hypoteser")
        heading.setStyleSheet("font-weight: bold;")
        layout.addWidget(heading)

        self._hypotheses_empty_label = QLabel(EMPTY_HYPOTHESES_TEXT)
        self._hypotheses_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._hypotheses_empty_label)

        self._hypotheses_tree = QTreeWidget()
        self._hypotheses_tree.setHeaderLabels(["Hypotes", "Bedömning", "Forskningsärende"])
        self._hypotheses_tree.setRootIsDecorated(False)
        self._hypotheses_tree.itemDoubleClicked.connect(self._on_hypothesis_double_clicked)
        layout.addWidget(self._hypotheses_tree)

    def _fill_cases(self, rows: list[CaseRow]) -> None:
        self._cases_tree.clear()
        for row in rows:
            item = QTreeWidgetItem(
                [row.title, row.status_label, row.priority_label, row.pending_text]
            )
            item.setData(0, self._CASE_ID_ROLE, row.case_id)
            self._cases_tree.addTopLevelItem(item)
        self._cases_tree.setVisible(bool(rows))
        self._cases_empty_label.setVisible(not rows)

    def _fill_hypotheses(self, rows: list[HypothesisRow]) -> None:
        self._hypotheses_tree.clear()
        for row in rows:
            item = QTreeWidgetItem([row.statement, row.assessment_label, row.case_title])
            item.setData(0, self._CASE_ID_ROLE, row.case_id)
            self._hypotheses_tree.addTopLevelItem(item)
        self._hypotheses_tree.setVisible(bool(rows))
        self._hypotheses_empty_label.setVisible(not rows)

    def _update_summary(self, index: ResearchIndex) -> None:
        """Show the indicator summary for the directly linked cases only."""
        counts = index.counts_for_entity(self._entity_type, self._entity_id)
        color = indicator_color(indicator_state(counts))
        text = indicator_tooltip(counts)
        self._summary_label.setText(text)
        self._summary_label.setVisible(bool(text))
        self._summary_label.setStyleSheet(f"color: {color};" if color else "")

    def _selected_case_id(self) -> Optional[str]:
        items = self._cases_tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, self._CASE_ID_ROLE)

    def _update_button_states(self) -> None:
        has_selection = self._selected_case_id() is not None
        self._open_button.setEnabled(has_selection)
        self._remove_button.setEnabled(has_selection)

    def _on_open_clicked(self) -> None:
        case_id = self._selected_case_id()
        if case_id:
            self.open_case_requested.emit(case_id)

    def _on_remove_clicked(self) -> None:
        case_id = self._selected_case_id()
        if case_id:
            self.remove_association_requested.emit(case_id)

    def _on_case_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        case_id = item.data(0, self._CASE_ID_ROLE)
        if case_id:
            self.open_case_requested.emit(case_id)

    def _on_hypothesis_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        case_id = item.data(0, self._CASE_ID_ROLE)
        if case_id:
            self.open_hypothesis_case_requested.emit(case_id)
