"""Merge candidate section of the person editor (Requirement 16).

``CandidatesSection`` lists the merge candidates of one person, read from the
project-level ``merge_candidates`` collection through ``CandidateIndex``. It
stores nothing on ``Person``. Opening a candidate, opening the comparison and
the register go through the merge gateway; without one those buttons do
nothing.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.merge_candidate import MergeCandidate
from slaktbusken.model.project import ProjectData
from slaktbusken.services.candidate_index import CandidateIndex
from slaktbusken.services.merge_candidate_service import (
    MSG_DUPLICATE_PAIR,
    MSG_SELF_PAIR,
)
from slaktbusken.services.merge_history_view import (
    EMPTY_HISTORY_TEXT,
    build_history_rows,
)
from slaktbusken.services.person_summary import UNKNOWN_PERSON, PersonSummaryIndex
from slaktbusken.services.project_service import ValidationError
from slaktbusken.ui.merge.merge_gateway import get_merge_gateway
from slaktbusken.ui.swedish_locale import (
    get_candidate_assessment_label,
    get_candidate_section_label,
)
from slaktbusken.ui.widgets.person_search_widget import PersonSearchWidget

MAX_COMMENT_CHARS = 100
YEAR_PLACEHOLDER = "–"

MSG_EMPTY = "Inga sammanslagningskandidater."
MSG_SAVE_FIRST = "Spara personen först."
MSG_NO_SELECTION = "Välj en person först."
MSG_NO_SERVICE = "Projektet är inte tillgängligt."
HISTORY_HEADING = "Sammanslagningshistorik"
HISTORY_BUTTON_TEXT = "Visa sammanslagningshistorik"

CANDIDATE_ID_ROLE = Qt.ItemDataRole.UserRole


def truncate_comment(text: str, limit: int = MAX_COMMENT_CHARS) -> str:
    """Return ``text`` cut to ``limit`` characters, ending in an ellipsis if cut."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def latest_comment_text(candidate: MergeCandidate) -> str:
    """Text of the most recent comment (latest date, later entry on ties)."""
    if not candidate.comments:
        return ""
    best = max(
        enumerate(candidate.comments), key=lambda pair: (pair[1].date or "", pair[0])
    )[1]
    return best.text or ""


class MergeHistoryBlock(QWidget):
    """The "Sammanslagningshistorik" block: merges into one person (Req 36.10).

    Lists merged name, lifespan, id and date plus a short summary per merge
    (``build_history_rows``), or an empty note, and a button that opens the
    Merge_History_Window scoped to the person. Hidden for an unsaved person.
    """

    def __init__(
        self,
        data: ProjectData,
        person_id: Callable[[], str],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._data = data
        self._person_id = person_id
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._heading = QLabel(HISTORY_HEADING, self)
        self._heading.setAccessibleName(HISTORY_HEADING)
        layout.addWidget(self._heading)

        self._empty_label = QLabel(EMPTY_HISTORY_TEXT, self)
        self._empty_label.setAccessibleName("Ingen sammanslagningshistorik")
        layout.addWidget(self._empty_label)

        self._list = QListWidget(self)
        self._list.setAccessibleName("Sammanslagningar in i personen")
        self._list.setMaximumHeight(140)
        layout.addWidget(self._list)

        buttons = QHBoxLayout()
        self._button = QPushButton(HISTORY_BUTTON_TEXT, self)
        self._button.setAccessibleName(HISTORY_BUTTON_TEXT)
        self._button.clicked.connect(self._on_show_history)
        buttons.addWidget(self._button)
        buttons.addStretch()
        layout.addLayout(buttons)

        gateway = get_merge_gateway()
        if gateway is not None:
            gateway.merge_changed.connect(self.refresh)
        self.refresh()

    def row_texts(self) -> list[str]:
        return [self._list.item(i).text() for i in range(self._list.count())]

    def refresh(self) -> None:
        pid = self._person_id()
        saved = bool(pid) and any(p.id == pid for p in self._data.persons)
        rows = build_history_rows(self._data, pid) if saved else []
        self._list.clear()
        for row in rows:
            lifespan = f" ({row.merged_lifespan})" if row.merged_lifespan else ""
            text = f"{row.display_name}{lifespan} · {row.merged_id} · {row.merge_date}"
            summary = row.summary_text_lines[0]
            item = QListWidgetItem(f"{text} · {summary}")
            item.setToolTip("\n".join(row.summary_text_lines))
            self._list.addItem(item)
        self._empty_label.setVisible(saved and not rows)
        self._list.setVisible(bool(rows))
        self._button.setEnabled(saved)
        self.setVisible(saved)

    def _on_show_history(self) -> None:
        gateway = get_merge_gateway()
        pid = self._person_id()
        if gateway is not None and pid:
            gateway.open_history(pid)


class CandidatesSection(QGroupBox):
    """The "Sammanslagningskandidater" group box.

    Args:
        data: The project data (read for candidates and persons).
        person_id: Returns the id of the edited person, or "" while unknown.
        service_getter: Returns the ProjectService used for creation, or None.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        data: ProjectData,
        person_id: Callable[[], str],
        service_getter: Callable[[], object] = lambda: None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(get_candidate_section_label("candidates"), parent)
        self._data = data
        self._person_id = person_id
        self._service_getter = service_getter
        self._remove_listener: Optional[Callable[[], None]] = None

        layout = QVBoxLayout(self)

        self._save_first_label = QLabel(MSG_SAVE_FIRST, self)
        layout.addWidget(self._save_first_label)

        self._toggle = QCheckBox(get_candidate_section_label("show_historical"), self)
        self._toggle.setChecked(False)
        self._toggle.toggled.connect(lambda _checked: self.refresh())
        layout.addWidget(self._toggle)

        self._empty_label = QLabel(MSG_EMPTY, self)
        layout.addWidget(self._empty_label)

        self._list = QListWidget(self)
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list.itemSelectionChanged.connect(self._update_buttons)
        self._list.itemDoubleClicked.connect(lambda _item: self._on_open())
        layout.addWidget(self._list)

        buttons = QHBoxLayout()
        self._open_button = QPushButton("Öppna", self)
        self._compare_button = QPushButton("Jämför", self)
        self._register_button = QPushButton("Öppna register", self)
        self._open_button.clicked.connect(self._on_open)
        self._compare_button.clicked.connect(self._on_compare)
        self._register_button.clicked.connect(self._on_register)
        for button in (self._open_button, self._compare_button, self._register_button):
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)

        add_row = QHBoxLayout()
        self._search = PersonSearchWidget(self)
        self._add_button = QPushButton("Lägg till kandidat…", self)
        self._add_button.clicked.connect(self._on_add)
        add_row.addWidget(self._search, stretch=1)
        add_row.addWidget(self._add_button)
        layout.addLayout(add_row)

        self._error_label = QLabel("", self)
        self._error_label.setStyleSheet("color: #b00020;")
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        self._history_block = MergeHistoryBlock(data, person_id, self)
        layout.addWidget(self._history_block)

        gateway = get_merge_gateway()
        if gateway is not None:
            gateway.merge_changed.connect(self.refresh)

        self.refresh()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_historical(self) -> bool:
        """Whether rejected and disabled candidates are listed."""
        return self._toggle.isChecked()

    def set_show_historical(self, value: bool) -> None:
        self._toggle.setChecked(value)

    def connect_service(self, service) -> None:
        """Refresh on the project service's merge notifications."""
        self.disconnect_service()
        if service is not None and hasattr(service, "add_merge_listener"):
            remove = service.add_merge_listener(self.refresh)
            self._remove_listener = remove
            # A deleted widget must not stay registered (remove is idempotent).
            self.destroyed.connect(lambda *_: remove())

    def disconnect_service(self) -> None:
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None

    def is_saved(self) -> bool:
        """True once the edited person exists in the project."""
        pid = self._person_id()
        return bool(pid) and any(p.id == pid for p in self._data.persons)

    def refresh(self) -> None:
        """Rebuild the list from the project collection, keeping the toggle."""
        pid = self._person_id()
        selected = self._selected_candidate_id()
        saved = self.is_saved()

        self._save_first_label.setVisible(not saved)
        self._history_block.refresh()
        self._add_button.setEnabled(saved)
        self._search.setEnabled(saved)
        self._add_button.setToolTip("" if saved else MSG_SAVE_FIRST)
        self._search.set_persons(
            [p for p in self._data.persons if p.id != pid]
        )

        self._list.blockSignals(True)
        self._list.clear()
        if pid:
            index = CandidateIndex.build(self._data)
            summaries = PersonSummaryIndex.build(self._data)
            rows = []
            for cand in index.candidates_for(pid):
                if not self.show_historical() and (
                    cand.assessment == "rejected" or not cand.enabled
                ):
                    continue
                other = cand.person_2_id if cand.person_1_id == pid else cand.person_1_id
                summary = summaries.get(other)
                name = (summary.name or other) if summary else UNKNOWN_PERSON
                rows.append((name.casefold(), cand.id, self._row_text(cand, name, summary), cand))
            rows.sort(key=lambda r: (r[0], r[1]))
            for _key, _cid, text, cand in rows:
                item = QListWidgetItem(text)
                item.setData(CANDIDATE_ID_ROLE, cand.id)
                self._list.addItem(item)
        self._list.blockSignals(False)

        if selected is not None:
            self.select_candidate(selected)
        self._empty_label.setVisible(self._list.count() == 0)
        self._list.setVisible(self._list.count() > 0)
        self._update_buttons()

    def candidate_ids(self) -> list[str]:
        """Candidate ids in list order."""
        return [
            self._list.item(i).data(CANDIDATE_ID_ROLE) for i in range(self._list.count())
        ]

    def select_candidate(self, candidate_id: str) -> bool:
        for i in range(self._list.count()):
            if self._list.item(i).data(CANDIDATE_ID_ROLE) == candidate_id:
                self._list.setCurrentRow(i)
                return True
        return False

    def add_candidate_with(self, other_id: Optional[str]) -> bool:
        """Create a candidate between the edited person and ``other_id``.

        Returns True when a candidate was created; otherwise an error message
        is shown and nothing changes.
        """
        self._set_error("")
        pid = self._person_id()
        if not self.is_saved():
            self._set_error(MSG_SAVE_FIRST)
            return False
        if not other_id:
            self._set_error(MSG_NO_SELECTION)
            return False
        if other_id == pid:
            self._set_error(MSG_SELF_PAIR)
            return False
        existing = CandidateIndex.build(self._data).candidate_for_pair(pid, other_id)
        if existing is not None:
            self._set_error(MSG_DUPLICATE_PAIR)
            self._reveal(existing)
            return False
        service = self._service_getter()
        if service is None:
            self._set_error(MSG_NO_SERVICE)
            return False
        try:
            candidate, created = service.get_or_create_merge_candidate(pid, other_id)
        except ValidationError as exc:
            self._set_error(" ".join(exc.errors))
            return False
        self.refresh()
        self.select_candidate(candidate.id)
        if created:
            self._search.clear_selection()
        else:
            self._set_error(MSG_DUPLICATE_PAIR)
            self._reveal(candidate)
        return created

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _row_text(cand: MergeCandidate, name: str, summary) -> str:
        birth = (summary.birth_year if summary else "") or YEAR_PLACEHOLDER
        death = (summary.death_year if summary else "") or YEAR_PLACEHOLDER
        parts = [
            f"{name} (f. {birth}, d. {death})",
            get_candidate_assessment_label(cand.assessment),
            "Aktiv" if cand.enabled else "Avstängd",
        ]
        comment = truncate_comment(latest_comment_text(cand))
        if comment:
            parts.append(comment)
        return " · ".join(parts)

    def _reveal(self, cand: MergeCandidate) -> None:
        """Show an existing pair, switching the toggle on if it is hidden."""
        if not self.select_candidate(cand.id):
            self._toggle.setChecked(True)  # refreshes
            self.select_candidate(cand.id)

    def _set_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(bool(message))

    def error_text(self) -> str:
        return self._error_label.text()

    def _selected_candidate_id(self) -> Optional[str]:
        item = self._list.currentItem()
        return item.data(CANDIDATE_ID_ROLE) if item is not None else None

    def _selected_candidate(self) -> Optional[MergeCandidate]:
        cid = self._selected_candidate_id()
        return next((c for c in self._data.merge_candidates if c.id == cid), None)

    def _update_buttons(self) -> None:
        has = self._selected_candidate_id() is not None
        self._open_button.setEnabled(has)
        self._compare_button.setEnabled(has)

    def _on_open(self) -> None:
        gateway = get_merge_gateway()
        cid = self._selected_candidate_id()
        if gateway is not None and cid:
            gateway.open_candidate(cid)

    def _on_compare(self) -> None:
        gateway = get_merge_gateway()
        cand = self._selected_candidate()
        if gateway is not None and cand is not None:
            gateway.open_comparison(cand.person_1_id, cand.person_2_id)

    def _on_register(self) -> None:
        gateway = get_merge_gateway()
        if gateway is not None:
            gateway.open_register(self._person_id() or None)

    def _on_add(self) -> None:
        self.add_candidate_with(self._search.selected_person_id())

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.disconnect_service()
        super().closeEvent(event)
