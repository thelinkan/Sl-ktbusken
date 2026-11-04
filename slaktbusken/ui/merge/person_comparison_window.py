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
from typing import Any, Callable, Optional

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
from slaktbusken.services.comparison_session import (
    DEPTH_REACHED_MESSAGE,
    SHARED_PERSON_TOOLTIP,
    ComparisonSession,
    PushResult,
)
from slaktbusken.services.editor_registry import EditorRegistry
from slaktbusken.services.diagram_lookup import active_lookup, set_active_lookup
from slaktbusken.services.person_search import PersonSearchIndex
from slaktbusken.services.person_summary import PersonSummaryIndex
from slaktbusken.services.project_service import ProjectNotOpenError, ProjectService
from slaktbusken.ui.merge.candidate_editor_dialog import SAVE, DISCARD, CandidatePanel
from slaktbusken.ui.merge.comparison_family_view import MAX_EXPANDED, ComparisonFamilyView
from slaktbusken.ui.merge.comparison_table import ComparisonTable
from slaktbusken.ui.merge.merge_gateway import get_merge_gateway
from slaktbusken.ui.merge.slot_search import SlotSearchControl
from slaktbusken.ui.swedish_locale import get_candidate_assessment_label
from slaktbusken.ui.widgets.research_marker import begin_diagram_render
from slaktbusken.ui.window_geometry import geometry_key

logger = logging.getLogger(__name__)

WINDOW_TITLE = "Jämför personer"
SWAP_TEXT = "Byt plats"
HISTORY_TEXT = "Sammanslagningshistorik"
BACK_TEXT = "Tillbaka till föregående jämförelse"
CONTINUE_TEXT = "Fortsätt till sammanslagning"
MARK_TEXT = "Markera valda som kandidater"
MARK_SLOTS_TEXT = "Markera dessa som kandidater"
COMPARE_TEXT = "Jämför dessa"
REGISTER_ERROR_TEXT = "Kandidaterna kunde inte registreras."
SAVE_ERROR_TEXT = "Kommentaren kunde inte sparas."
NO_PAIR_TEXT = "Välj en person i vardera familjevyn för att markera eller jämföra dem."
MAX_BADGES_PER_BOX = 3
SPLITTER_PROPORTIONS = (0.35, 0.35, 0.30)
REFRESH_DELAY_MS = 50

#: Zoom range a restored value must fall in; mirrors ZoomableGraphicsView.
MIN_ZOOM = 0.01
MAX_ZOOM = 4.0
#: How close the three restored splitter sizes must sum to the splitter width
#: before they are applied (a few pixels of rounding slack).
_SPLITTER_SUM_TOLERANCE = 16

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
        state_store: Zero-arg callable returning the dict map the window's
            internal state (splitter sizes and per-view zoom) is kept in, keyed
            by window type. A callable (rather than the dict itself), like
            ``WindowGeometryKeeper``, so the window always writes into the
            settings object that is current when it closes. ``None`` disables
            persistence of this state.
    """

    refreshed = Signal()
    #: Emitted with (person_1_id, person_2_id) by "Fortsätt till sammanslagning".
    #: The Merge_Review wizard (a later task) connects here or sets
    #: :attr:`continue_to_merge_callback`; this window never merges anything.
    continue_to_merge_requested = Signal(str, str)

    def __init__(
        self,
        project_service: ProjectService,
        person_1_id: Optional[str] = None,
        person_2_id: Optional[str] = None,
        parent: Optional[QWidget] = None,
        person_box_config: Optional[PersonBoxConfig] = None,
        diagram_settings: Optional[DiagramSettings] = None,
        editor_registry: Optional[EditorRegistry] = None,
        state_store: Optional[Callable[[], dict[str, dict]]] = None,
    ) -> None:
        super().__init__(parent)
        self._service = project_service
        self._registry = editor_registry or getattr(parent, "editor_registry", None)
        self._state_store = state_store
        self.continue_to_merge_callback: Optional[Callable[[str, str], None]] = None
        self._panel: Optional[CandidatePanel] = None
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
        self._state_restored = False
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
        self._back_button = QPushButton(BACK_TEXT, central)
        self._back_button.clicked.connect(self.go_back)
        self.toolbar_layout.addWidget(self._back_button)
        self.toolbar_layout.addStretch(1)
        self._mark_slots_button = QPushButton(MARK_SLOTS_TEXT, central)
        self._mark_slots_button.clicked.connect(self.mark_slots_as_candidates)
        self.toolbar_layout.addWidget(self._mark_slots_button)
        self._continue_button = QPushButton(CONTINUE_TEXT, central)
        self._continue_button.clicked.connect(self.continue_to_merge)
        self.toolbar_layout.addWidget(self._continue_button)
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
        self._history_buttons: list[QPushButton] = []
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
            history = QPushButton(HISTORY_TEXT, pane)
            history.setVisible(False)
            history.setEnabled(False)
            history.clicked.connect(lambda _=False, slot=i: self.open_slot_history(slot))
            layout.addWidget(history)
            self._history_buttons.append(history)
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

        # The candidate panel (embedded, never a nested dialog) sits here.
        self.candidate_panel_host = QFrame(central)
        host_layout = QVBoxLayout(self.candidate_panel_host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        self.candidate_panel_host.setMaximumHeight(360)
        self.candidate_panel_host.setVisible(False)
        outer.addWidget(self.candidate_panel_host)

        self.pair_action_bar = QFrame(central)
        bar = QHBoxLayout(self.pair_action_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        self._pair_label = QLabel(NO_PAIR_TEXT, self.pair_action_bar)
        self._pair_label.setWordWrap(True)
        self._pair_label.setAccessibleName("Valt par")
        bar.addWidget(self._pair_label, 1)
        self._mark_button = QPushButton(MARK_TEXT, self.pair_action_bar)
        self._compare_button = QPushButton(COMPARE_TEXT, self.pair_action_bar)
        self._mark_button.clicked.connect(self.mark_as_candidates)
        self._compare_button.clicked.connect(self.compare_selected)
        bar.addWidget(self._mark_button)
        bar.addWidget(self._compare_button)
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

    @property
    def back_button(self) -> QPushButton:
        return self._back_button

    @property
    def continue_button(self) -> QPushButton:
        return self._continue_button

    @property
    def mark_slots_button(self) -> QPushButton:
        """Toolbar button marking the two slot persons as candidates."""
        return self._mark_slots_button

    @property
    def mark_button(self) -> QPushButton:
        return self._mark_button

    @property
    def compare_button(self) -> QPushButton:
        return self._compare_button

    @property
    def candidate_panel(self) -> Optional[CandidatePanel]:
        """The embedded candidate panel while it is open, else None."""
        return self._panel

    def pair_text(self) -> str:
        return self._pair_label.text()

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
        # The geometry keeper restores size/position on the first show through
        # the application event filter; once the window has its final width the
        # saved splitter sizes and zoom can be applied on top of the defaults.
        if not self._state_restored:
            self._state_restored = True
            self._restore_saved_state()
        if self._focus_pending is not None:
            slot = self._focus_pending
            self._focus_pending = None
            self.focus_slot_search(slot)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if not self._splitter_touched and self.isVisible():
            self.apply_initial_proportions()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if not self.resolve_unsaved_comment():
            event.ignore()
            return
        self._save_state()
        self._remove_listener()
        self._refresh_timer.stop()
        _open_windows.discard(self)
        super().closeEvent(event)

    # ------------------------------------------------- remembered state

    def _save_state(self) -> None:
        """Record this window's splitter sizes and per-view zoom.

        Stored under the same key the geometry uses, so there is one entry per
        window type. A missing store (``state_store`` was ``None``) or any
        failure is ignored so closing the window can never break.
        """
        if self._state_store is None:
            return
        try:
            self._state_store()[geometry_key(self)] = {
                "splitter_sizes": list(self._splitter.sizes()),
                "zoom": [self._session.zoom(0), self._session.zoom(1)],
            }
        except Exception:  # noqa: BLE001 - never break closing a window
            logger.exception("Kunde inte spara jämförelsefönstrets läge.")

    def _restore_saved_state(self) -> None:
        """Apply saved splitter sizes and per-view zoom, if any are valid.

        Garbage or missing entries fall back to the 35/35/30 proportions and
        the default zoom without error.
        """
        if self._state_store is None:
            return
        try:
            state = self._state_store().get(geometry_key(self))
        except Exception:  # noqa: BLE001 - a bad store must not stop opening
            logger.exception("Kunde inte läsa jämförelsefönstrets läge.")
            return
        if not isinstance(state, dict):
            return
        self._restore_splitter_sizes(state.get("splitter_sizes"))
        self._restore_zoom(state.get("zoom"))

    def _restore_splitter_sizes(self, sizes: Any) -> None:
        """Apply three saved splitter sizes when they match the splitter width.

        Keeps the default 35/35/30 proportions (and the ``_splitter_touched``
        logic intact) when ``sizes`` is not a list of three numbers whose sum
        is close to the current splitter width.
        """
        if not isinstance(sizes, (list, tuple)) or len(sizes) != 3:
            return
        if any(isinstance(s, bool) or not isinstance(s, (int, float)) for s in sizes):
            return
        if any(s < 0 for s in sizes):
            return
        total = self._splitter.width()
        if total <= 0:
            return
        if abs(sum(sizes) - total) > _SPLITTER_SUM_TOLERANCE:
            return
        self._splitter.setSizes([int(s) for s in sizes])
        self._splitter_touched = True

    def _restore_zoom(self, zoom: Any) -> None:
        """Apply saved per-view zoom, clamped to the allowed range.

        Each entry must be a finite number; anything else leaves that view at
        its current (default) zoom.
        """
        if not isinstance(zoom, (list, tuple)) or len(zoom) != 2:
            return
        for view, value in enumerate(zoom):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if value != value or value in (float("inf"), float("-inf")):
                continue
            clamped = max(MIN_ZOOM, min(MAX_ZOOM, float(value)))
            self._session.set_zoom(view, clamped)
            self._family_views[view].set_zoom(clamped)

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
        self._update_controls()

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

    # ------------------------------------------------- markers (Requirement 12)

    def _update_markers(self, data: ProjectData) -> None:
        """Shared_Person markers and candidate badges, rebuilt from current content."""
        views = self._family_views
        for view in views:
            view.clear_markers()
        left_ids = views[0].visible_person_ids()
        right_ids = views[1].visible_person_ids()
        for pid in sorted(self._session.shared_person_ids(left_ids, right_ids)):
            for view in views:
                view.add_shared_marker(pid, SHARED_PERSON_TOOLTIP)
        index = CandidateIndex.build(data)
        placed: dict[tuple[int, str], int] = {}
        done: set[tuple[int, str, str]] = set()
        for a in sorted(left_ids):
            for b in sorted(right_ids):
                candidate = self._session.candidate_relation(a, b, index)
                if candidate is None:
                    continue
                label = get_candidate_assessment_label(candidate.assessment)
                tip = f"Kandidatbedömning: {label}. Aktivera för att öppna kommentarerna."
                for view_index, pid in ((0, a), (1, b)):
                    key = (view_index, pid, candidate.id)
                    if key in done:
                        continue
                    done.add(key)
                    slot = placed.get((view_index, pid), 0)
                    if slot >= MAX_BADGES_PER_BOX:
                        continue
                    placed[(view_index, pid)] = slot + 1
                    views[view_index].add_candidate_badge(
                        pid, label, tip, candidate.id, self.open_candidate_comments, slot
                    )

    def open_candidate_comments(self, candidate_id: str) -> None:
        """Open the comments of a candidate inside this window (12.4)."""
        self.open_candidate_panel(candidate_id)

    # ----------------------------------------- pair actions (Requirements 13, 14)

    def _update_controls(self) -> None:
        state = self._session.pair_action_state()
        self._mark_button.setEnabled(state.enabled)
        self._compare_button.setEnabled(state.enabled)
        summaries = self._summaries
        if state.left_id and state.right_id and summaries is not None:
            text = f"{_fmt(state.left_id, summaries)} ({state.left_id})  \u2194  " \
                   f"{_fmt(state.right_id, summaries)} ({state.right_id})"
            if state.reason:
                text += f"\n{state.reason}"
        elif state.reason:
            text = state.reason
        else:
            text = NO_PAIR_TEXT
        self._pair_label.setText(text)
        self._back_button.setEnabled(self._session.can_go_back())
        self._continue_button.setEnabled(self._session.can_continue_to_merge())
        left, right = self._session.slot_persons()
        self._mark_slots_button.setEnabled(bool(left and right and left != right))

    def resolve_unsaved_comment(self) -> bool:
        """Ask save / discard / stay for unsaved comment text; True to go on (14.6)."""
        panel = self._panel
        if panel is None or not shiboken6.isValid(panel) or not panel.has_unsaved_text():
            return True
        choice = panel._ask_unsaved()
        if choice == SAVE:
            if panel.save_comment():
                return True
            self._show_message(SAVE_ERROR_TEXT)
            return False
        if choice == DISCARD:
            panel._start_new_comment()
            return True
        return False

    def open_candidate_panel(self, candidate_id: str) -> bool:
        """Show the candidate panel for ``candidate_id`` inside the window."""
        if self._panel is not None and self._panel.candidate_id == candidate_id:
            return True
        if not self.resolve_unsaved_comment():
            return False
        self._close_panel()
        panel = CandidatePanel(
            self._service, candidate_id, self.candidate_panel_host, self._registry
        )
        panel.close_requested.connect(self._close_panel)
        self.candidate_panel_host.layout().addWidget(panel)
        self.candidate_panel_host.setVisible(True)
        self._panel = panel
        self._show_message("")
        return True

    def _close_panel(self) -> None:
        panel = self._panel
        self._panel = None
        if panel is not None and shiboken6.isValid(panel):
            if self._registry is not None:
                self._registry.unregister(panel)
            panel.setParent(None)
            panel.deleteLater()
        self.candidate_panel_host.setVisible(False)

    def mark_as_candidates(self) -> bool:
        """"Markera som kandidater": get or create, then open the panel (13.6, 13.7)."""
        state = self._session.pair_action_state()
        if not state.enabled:
            return False
        if not self.resolve_unsaved_comment():
            return False
        try:
            candidate, _created = self._service.get_or_create_merge_candidate(
                state.left_id, state.right_id
            )
        except Exception:  # noqa: BLE001 - any failure is reported, selection kept
            logger.exception("Kandidaterna kunde inte registreras.")
            self._show_message(REGISTER_ERROR_TEXT)
            return False
        self._show_message("")
        return self.open_candidate_panel(candidate.id)

    def mark_slots_as_candidates(self) -> bool:
        """Mark the two slot persons as candidates, independent of in-view selection.

        Enabled whenever both slots are filled with two different persons. On
        success it gets or creates the candidate for the slot pair and opens the
        candidate panel; on failure it shows ``REGISTER_ERROR_TEXT`` and keeps
        the current state unchanged.
        """
        left, right = self._session.slot_persons()
        if not left or not right or left == right:
            return False
        if not self.resolve_unsaved_comment():
            return False
        try:
            candidate, _created = self._service.get_or_create_merge_candidate(left, right)
        except Exception:  # noqa: BLE001 - any failure is reported, state kept
            logger.exception("Kandidaterna kunde inte registreras.")
            self._show_message(REGISTER_ERROR_TEXT)
            return False
        self._show_message("")
        return self.open_candidate_panel(candidate.id)

    def compare_selected(self) -> bool:
        """"Jämför dessa": show the selected pair in the slots (13.8, 14.1)."""
        if not self._session.pair_action_state().enabled:
            return False
        if not self.resolve_unsaved_comment():
            return False
        result = self._session.compare_selected()
        if result is PushResult.DEPTH_REACHED:
            self._show_message(DEPTH_REACHED_MESSAGE)
            return False
        if result is not PushResult.PUSHED:
            return False
        self._close_panel()
        self._expansion_order = [[], []]
        self._show_message("")
        self.refresh()
        return True

    def go_back(self) -> bool:
        """"Tillbaka till föregående jämförelse": pop exactly one level (14.4)."""
        if not self._session.can_go_back():
            return False
        if not self.resolve_unsaved_comment():
            return False
        self._session.back()
        self._close_panel()
        self._expansion_order = [[], []]
        self._show_message("")
        self.refresh()
        return True

    def continue_to_merge(self) -> bool:
        """"Fortsätt till sammanslagning": only signals; nothing is merged here (20.1)."""
        if not self._session.can_continue_to_merge():
            return False
        left, right = self._session.slot_persons()
        self.continue_to_merge_requested.emit(left, right)
        if self.continue_to_merge_callback is not None:
            self.continue_to_merge_callback(left, right)
        return True

    def _project_folder(self) -> Optional[Path]:
        path = self._service.project_path
        return path.parent if path else None

    def _render_views(self, views: list[int], data: Optional[ProjectData] = None) -> None:
        data = data if data is not None else self._data()
        if data is None:
            for view in views:
                self._family_views[view].render(ProjectData(), None, self._config)
            self._table.set_rows([], filled=(False, False))
            self._update_history_buttons(None)
            self._update_controls()
            return
        begin_diagram_render(
            data,
            bool(getattr(self._config, "research", False)),
            bool(getattr(self._config, "merge_candidates", False)),
        )
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
        self._update_history_buttons(data)
        self._update_markers(data)
        self._swap_button.setEnabled(True)
        self._update_controls()

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

    @property
    def history_buttons(self) -> list[QPushButton]:
        """The per-slot "Sammanslagningshistorik" buttons."""
        return list(self._history_buttons)

    def _update_history_buttons(self, data: Optional[ProjectData]) -> None:
        """Show a slot's history button only while its person has history."""
        index = CandidateIndex.build(data) if data is not None else None
        for slot, button in enumerate(self._history_buttons):
            pid = self._session.slots[slot]
            has = bool(
                index is not None and pid and index.relations(pid).has_history
            )
            button.setVisible(has)
            button.setEnabled(has)

    def open_slot_history(self, slot: int) -> None:
        """Open the merge history of the person in ``slot`` via the gateway."""
        pid = self._session.slots[slot]
        gateway = get_merge_gateway()
        if pid and gateway is not None:
            gateway.open_history(pid)

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
    editor_registry: Optional[EditorRegistry] = None,
    state_store: Optional[Callable[[], dict[str, dict]]] = None,
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
        editor_registry: Registry that lets the embedded candidate panel take
            part in unsaved-text checks (defaults to ``parent.editor_registry``).
        state_store: Zero-arg callable returning the dict map the window's
            internal state (splitter sizes and per-view zoom) is kept in, or
            None to not persist it.
    """
    window = PersonComparisonWindow(
        project_service,
        person_1_id or None,
        person_2_id or None,
        parent,
        person_box_config,
        diagram_settings,
        editor_registry,
        state_store,
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
