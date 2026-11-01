"""Person_Comparison_Window: two persons side by side (comparison stage).

Layout (design 15.2): a toolbar row, a horizontal ``QSplitter`` with
Comparison_Family_View 1, Comparison_Family_View 2 and the Comparison_Table in
the proportions 35 / 35 / 30, and a pair-action bar below it. Each slot has a
Slot_Search_Control above its view.

The comparison stage is read-only: nothing in this module writes genealogical
data. State (slots, swap, per-view focus, expansion, selection and zoom) lives
in :class:`ComparisonSession`.

Hooks for later additions (shared markers, pair actions, sub-comparison, the
"Fortsätt till sammanslagning" button): :attr:`toolbar_layout`,
:attr:`pair_action_bar` (empty, hidden), :meth:`ComparisonFamilyView.add_overlay_hook`
and the :attr:`refreshed` signal.

Entry point for the application: :func:`open_comparison_window`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import shiboken6
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.settings_io import DiagramSettings, PersonBoxConfig
from slaktbusken.services.candidate_index import CandidateIndex
from slaktbusken.services.comparison_session import ComparisonSession
from slaktbusken.services.diagram_lookup import active_lookup, set_active_lookup
from slaktbusken.services.person_search import PersonSearchIndex
from slaktbusken.services.person_summary import PersonSummaryIndex
from slaktbusken.services.project_service import ProjectNotOpenError, ProjectService
from slaktbusken.ui.merge.comparison_family_view import MAX_EXPANDED, ComparisonFamilyView
from slaktbusken.ui.merge.comparison_table import ComparisonTable
from slaktbusken.ui.merge.slot_search import SlotSearchControl
from slaktbusken.ui.swedish_locale import get_candidate_assessment_label
from slaktbusken.ui.widgets.research_marker import begin_diagram_render

logger = logging.getLogger(__name__)

WINDOW_TITLE = "Jämför personer"
SWAP_TEXT = "Byt plats"
SPLITTER_PROPORTIONS = (0.35, 0.35, 0.30)
REFRESH_DELAY_MS = 50

_open_windows: set["PersonComparisonWindow"] = set()


def _fmt(person_id: Optional[str], summaries: PersonSummaryIndex) -> str:
    if not person_id:
        return ""
    name = summaries.name(person_id)
    life = summaries.lifespan_text(person_id)
    return f"{name} {life}".strip()


class PersonComparisonWindow(QMainWindow):
    """Non-modal, resizable and maximisable comparison window.

    Args:
        project_service: Owner of the project data (read only here).
        person_1_id: Person for slot 1, or None.
        person_2_id: Person for slot 2, or None.
        parent: Optional parent widget.
        person_box_config: Diagram person-box configuration; defaults to the
            main diagram's configuration found through ``parent.diagram_panel``
            and otherwise to :class:`PersonBoxConfig` defaults.
        diagram_settings: Diagram settings; same fallback as the config.
    """

    refreshed = Signal()

    def __init__(
        self,
        project_service: ProjectService,
        person_1_id: Optional[str] = None,
        person_2_id: Optional[str] = None,
        parent: Optional[QWidget] = None,
        person_box_config: Optional[PersonBoxConfig] = None,
        diagram_settings: Optional[DiagramSettings] = None,
    ) -> None:
        super().__init__(parent)
        self._service = project_service
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1400, 800)

        panel = getattr(parent, "diagram_panel", None)
        if person_box_config is None:
            person_box_config = getattr(panel, "_person_box_config", None)
        if diagram_settings is None:
            diagram_settings = getattr(panel, "_diagram_settings", None)
        self._config = person_box_config or PersonBoxConfig()
        self._diagram_settings = diagram_settings

        data = self._data()
        ids = {p.id for p in data.persons} if data is not None else set()
        first = person_1_id if person_1_id in ids else None
        second = person_2_id if person_2_id in ids else None
        self._session = ComparisonSession.from_pair(first, second)
        self._expansion_order: list[list[str]] = [[], []]
        self._summaries: Optional[PersonSummaryIndex] = None
        self._splitter_touched = False
        self._focus_pending: Optional[int] = None
        self.last_lookup = None

        self._build_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(REFRESH_DELAY_MS)
        self._refresh_timer.timeout.connect(self.refresh)
        self._remove_listener = self._service.add_merge_listener(self._on_project_changed)

        self.refresh()
        self.apply_initial_proportions()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(6, 6, 6, 6)

        self.toolbar_layout = QHBoxLayout()
        self._swap_button = QPushButton(SWAP_TEXT, central)
        self._swap_button.clicked.connect(self.swap)
        self.toolbar_layout.addWidget(self._swap_button)
        self.toolbar_layout.addStretch(1)
        outer.addLayout(self.toolbar_layout)

        self._message = QLabel("", central)
        self._message.setWordWrap(True)
        self._message.setAccessibleName("Meddelande")
        self._message.setStyleSheet("color: #B71C1C;")
        self._message.setVisible(False)
        outer.addWidget(self._message)

        self._splitter = QSplitter(Qt.Orientation.Horizontal, central)
        self._splitter.setChildrenCollapsible(False)
        self._searches: list[SlotSearchControl] = []
        self._family_views: list[ComparisonFamilyView] = []
        self._selected_labels: list[QLabel] = []
        for i in (0, 1):
            pane = QWidget(self._splitter)
            pane.setMinimumWidth(120)
            layout = QVBoxLayout(pane)
            layout.setContentsMargins(0, 0, 0, 0)
            search = SlotSearchControl(pane)
            search.line_edit().setPlaceholderText(f"Sök person {i + 1}...")
            search.person_selected.connect(lambda pid, slot=i: self.assign_person(slot, pid))
            search.person_cleared.connect(lambda slot=i: self.clear_slot(slot))
            layout.addWidget(search)
            view = ComparisonFamilyView(i, pane)
            view.person_clicked.connect(lambda pid, slot=i: self.select_in_view(slot, pid))
            view.person_navigated.connect(lambda pid, slot=i: self.navigate(slot, pid))
            view.use_as_slot_requested.connect(lambda pid, slot=i: self.assign_person(slot, pid))
            view.expansion_toggled.connect(lambda pid, slot=i: self.toggle_expansion(slot, pid))
            view.zoom_changed.connect(lambda z, slot=i: self._session.set_zoom(slot, z))
            layout.addWidget(view, stretch=1)
            selected = QLabel("", pane)
            selected.setWordWrap(True)
            layout.addWidget(selected)
            self._searches.append(search)
            self._family_views.append(view)
            self._selected_labels.append(selected)
            self._splitter.addWidget(pane)
        self._table = ComparisonTable(self._splitter)
        self._table.setMinimumWidth(120)
        self._splitter.addWidget(self._table)
        for i, weight in enumerate((35, 35, 30)):
            self._splitter.setStretchFactor(i, weight)
        self._splitter.splitterMoved.connect(self._on_splitter_moved)
        outer.addWidget(self._splitter, stretch=1)

        # Filled by the pair-action task; empty and hidden until then.
        self.pair_action_bar = QFrame(central)
        self.pair_action_bar.setLayout(QHBoxLayout())
        self.pair_action_bar.setVisible(False)
        outer.addWidget(self.pair_action_bar)

        self._candidate_label = QLabel("", central)
        self._candidate_label.setWordWrap(True)
        self._candidate_label.setAccessibleName("Kandidat för paret")
        self._candidate_label.setVisible(False)
        outer.addWidget(self._candidate_label)

        self.setCentralWidget(central)

    # ------------------------------------------------------------ accessors

    @property
    def session(self) -> ComparisonSession:
        return self._session

    @property
    def splitter(self) -> QSplitter:
        return self._splitter

    @property
    def table(self) -> ComparisonTable:
        return self._table

    @property
    def family_views(self) -> list[ComparisonFamilyView]:
        return list(self._family_views)

    @property
    def search_controls(self) -> list[SlotSearchControl]:
        return list(self._searches)

    @property
    def swap_button(self) -> QPushButton:
        return self._swap_button

    def slot_persons(self) -> tuple[Optional[str], Optional[str]]:
        return self._session.slot_persons()

    def message_text(self) -> str:
        return "" if self._message.isHidden() else self._message.text()

    def candidate_text(self) -> str:
        return "" if self._candidate_label.isHidden() else self._candidate_label.text()

    def selected_label_text(self, slot: int) -> str:
        return self._selected_labels[slot].text()

    def _data(self) -> Optional[ProjectData]:
        try:
            return self._service.data
        except ProjectNotOpenError:
            return None

    # ------------------------------------------------------------- layout

    def apply_initial_proportions(self) -> None:
        """Set the splitter to 35 / 35 / 30 percent of its current width."""
        total = self._splitter.width()
        if total <= 100:
            total = max(self.width() - 12, 300)
        a = int(total * SPLITTER_PROPORTIONS[0])
        b = int(total * SPLITTER_PROPORTIONS[1])
        self._splitter.setSizes([a, b, total - a - b])

    def _on_splitter_moved(self, *_args: Any) -> None:
        self._splitter_touched = True

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if not self._splitter_touched:
            self.apply_initial_proportions()
        if self._focus_pending is not None:
            slot = self._focus_pending
            self._focus_pending = None
            self.focus_slot_search(slot)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if not self._splitter_touched and self.isVisible():
            self.apply_initial_proportions()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._remove_listener()
        self._refresh_timer.stop()
        _open_windows.discard(self)
        super().closeEvent(event)

    # ----------------------------------------------------------- focus

    def focus_slot_search(self, slot: int) -> None:
        """Move keyboard focus to the Slot_Search_Control of ``slot`` (0 or 1)."""
        if not self.isVisible():
            self._focus_pending = slot
        self._searches[slot].focus_input()

    # -------------------------------------------------------- slot actions

    def _show_message(self, text: str) -> None:
        self._message.setText(text)
        self._message.setVisible(bool(text))

    def assign_person(self, slot: int, person_id: str) -> bool:
        """Place a person in a slot; rejects the other slot's person (9.10)."""
        data = self._data()
        if data is None or all(p.id != person_id for p in data.persons):
            self._show_message("")
            self.refresh()
            return False
        result = self._session.set_slot(slot, person_id)
        if not result.ok:
            self._show_message(result.message)
            self._restore_search_text(slot)
            return False
        self._show_message("")
        self._expansion_order[slot] = []
        self.refresh()
        return True

    def clear_slot(self, slot: int) -> None:
        """Empty a slot (the search field's clear button)."""
        if self._session.slots[slot] is None:
            return
        self._session.set_slot(slot, None)
        self._expansion_order[slot] = []
        self._show_message("")
        self.refresh()

    def swap(self) -> None:
        """"Byt plats": swap the slot persons (9.6)."""
        self._session.swap()
        self._expansion_order.reverse()
        self._show_message("")
        self.refresh()

    # --------------------------------------------------- per-view actions

    def select_in_view(self, view: int, person_id: Optional[str]) -> None:
        self._session.select(view, person_id)
        self._family_views[view].set_selected(self._session.selection(view))
        self._update_selected_labels()

    def navigate(self, view: int, person_id: str) -> None:
        """Re-centre one view; the slot person stays unchanged (10.9)."""
        data = self._data()
        if data is None or all(p.id != person_id for p in data.persons):
            return
        self._session.set_focus(view, person_id)
        self._render_views([view])

    def toggle_expansion(self, view: int, person_id: str) -> None:
        order = self._expansion_list(view)
        if person_id in order:
            order.remove(person_id)
        elif len(order) < MAX_EXPANDED:
            order.append(person_id)
        self._expansion_order[view] = order
        self._session.set_expansion(view, order)
        self._render_views([view])

    def _expansion_list(self, view: int) -> list[str]:
        current = self._session.expansion(view)
        ordered = [p for p in self._expansion_order[view] if p in current]
        ordered += sorted(p for p in current if p not in ordered)
        return ordered

    # ------------------------------------------------------------ refresh

    def _on_project_changed(self) -> None:
        if not shiboken6.isValid(self):
            return
        self._refresh_timer.start()

    def refresh(self) -> None:
        """Re-resolve everything from the project data (10.12, 11.11).

        Focus (when still present), expansion and zoom of each view are kept;
        a slot whose person was deleted is cleared (10.14).
        """
        data = self._data()
        if data is None:
            self._session.slots[:] = [None, None]
            self._session._reset_view(0)
            self._session._reset_view(1)
            self._summaries = None
            for search in self._searches:
                search.set_search_index(None)
            self._render_views([0, 1], data)
            return

        ids = {p.id for p in data.persons}
        self._session.clear_missing(ids)
        for view in (0, 1):
            slot_person = self._session.slots[view]
            if self._session.focus(view) not in ids:
                self._session.set_focus(view, slot_person)
            if self._session.selection(view) is not None and self._session.selection(view) not in ids:
                self._session.select(view, None)
            kept = [p for p in self._expansion_list(view) if p in ids]
            self._expansion_order[view] = kept
            self._session.set_expansion(view, kept)

        self._summaries = PersonSummaryIndex.build(data)
        search_index = PersonSearchIndex.build(data, self._summaries)
        for search in self._searches:
            search.set_search_index(search_index)
        self._update_search_text()
        self._render_views([0, 1], data)
        self.refreshed.emit()

    def _project_folder(self) -> Optional[Path]:
        path = self._service.project_path
        return path.parent if path else None

    def _render_views(self, views: list[int], data: Optional[ProjectData] = None) -> None:
        data = data if data is not None else self._data()
        if data is None:
            for view in views:
                self._family_views[view].render(ProjectData(), None, self._config)
            self._table.set_rows([], filled=(False, False))
            return
        begin_diagram_render(data, bool(getattr(self._config, "research", False)))
        lookup = active_lookup(data)
        self.last_lookup = lookup
        try:
            for view in views:
                self._family_views[view].set_zoom(self._session.zoom(view))
                self._family_views[view].render(
                    data,
                    self._session.focus(view),
                    self._config,
                    self._diagram_settings,
                    self._project_folder(),
                    tuple(self._expansion_list(view)),
                    self._session.selection(view),
                    lookup,
                )
        finally:
            set_active_lookup(None)
        self._update_table(data)
        self._update_selected_labels()
        self._update_candidate(data)
        self._swap_button.setEnabled(True)

    def _update_table(self, data: ProjectData) -> None:
        summaries = self._summaries or PersonSummaryIndex.build(data)
        left, right = self._session.slot_persons()
        self._table.set_rows(
            self._session.rows(data),
            _fmt(left, summaries) or "Person 1",
            _fmt(right, summaries) or "Person 2",
            {s.id: s for s in data.sources},
            (left is not None, right is not None),
        )

    def _update_selected_labels(self) -> None:
        for view in (0, 1):
            pid = self._session.selection(view)
            if pid is None or self._summaries is None:
                self._selected_labels[view].setText("Ingen person vald i vyn")
            else:
                self._selected_labels[view].setText(
                    f"Vald i vyn: {self._summaries.name(pid)} ({pid})"
                )

    def _update_candidate(self, data: ProjectData) -> None:
        """Assessment and comments of the saved candidate of the current pair."""
        candidate = self._session.current_candidate(CandidateIndex.build(data))
        if candidate is None:
            self._candidate_label.setText("")
            self._candidate_label.setVisible(False)
            return
        parts = [
            "Kandidat för paret: "
            f"Bedömning: {get_candidate_assessment_label(candidate.assessment)}, "
            f"{'aktiv' if candidate.enabled else 'inte aktiv'}."
        ]
        if candidate.comments:
            comments = "; ".join(
                f"{c.date} {c.text}".strip() for c in candidate.comments
            )
            parts.append(f"Kommentarer: {comments}")
        self._candidate_label.setText(" ".join(parts))
        self._candidate_label.setVisible(True)

    def _update_search_text(self) -> None:
        summaries = self._summaries
        if summaries is None:
            return
        for slot, search in enumerate(self._searches):
            pid = self._session.slots[slot]
            if search.selected_person_id() != pid or not search.line_edit().hasFocus():
                search.show_person(pid, _fmt(pid, summaries))

    def _restore_search_text(self, slot: int) -> None:
        if self._summaries is None:
            return
        pid = self._session.slots[slot]
        self._searches[slot].show_person(pid, _fmt(pid, self._summaries))


def open_comparison_window(
    parent: Optional[QWidget],
    project_service: ProjectService,
    person_1_id: Optional[str] = None,
    person_2_id: Optional[str] = None,
    focus_search: Optional[bool] = None,
    person_box_config: Optional[PersonBoxConfig] = None,
    diagram_settings: Optional[DiagramSettings] = None,
) -> PersonComparisonWindow:
    """Open a non-modal comparison window and return it.

    Args:
        parent: Parent widget (normally the main window), or None.
        project_service: The open project.
        person_1_id: Person for slot 1 (None or empty for none). When two
            persons come from the person list, pass them in list order.
        person_2_id: Person for slot 2 (None or empty for none).
        focus_search: True moves keyboard focus to the search control of slot
            2 (used when opened from the person editor); False leaves focus
            alone; None (default) focuses it exactly when slot 1 holds a
            person and slot 2 is empty (Requirement 9.2, 9.4).
        person_box_config: Optional person-box configuration override.
        diagram_settings: Optional diagram settings override.
    """
    window = PersonComparisonWindow(
        project_service,
        person_1_id or None,
        person_2_id or None,
        parent,
        person_box_config,
        diagram_settings,
    )
    window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    _open_windows.add(window)
    window.destroyed.connect(lambda _=None, w=window: _open_windows.discard(w))
    left, right = window.slot_persons()
    if focus_search is None:
        focus_search = left is not None and right is None
    if focus_search:
        window.focus_slot_search(1)
    window.show()
    window.raise_()
    window.activateWindow()
    return window
