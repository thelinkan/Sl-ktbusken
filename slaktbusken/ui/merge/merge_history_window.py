"""The Merge_History_Window "Sammanslagningshistorik" (requirement 36).

Non-modal window listing the stored merge history, newest first. The rows come
from :func:`slaktbusken.services.merge_history_view.build_history_rows`; the
window only displays them. Navigation to the surviving person goes through the
merge gateway (``show_person``); without a gateway the action does nothing.
"""

from __future__ import annotations

import weakref
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.services.merge_history_view import (
    EMPTY_HISTORY_TEXT,
    NO_ARCHIVED_CANDIDATE_TEXT,
    HistoryRow,
    build_history_rows,
)
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge.merge_gateway import get_merge_gateway
from slaktbusken.ui.swedish_locale import get_candidate_assessment_label

WINDOW_TITLE = "Sammanslagningshistorik"
NAVIGATE_BUTTON_TEXT = "Gå till behållen person"
REFRESH_DELAY_MS = 500  # requirement 36.9
COLUMN_HEADERS = (
    "Sammanslagen person",
    "Livstid",
    "Id",
    "Datum",
    "Behållen person",
    "Sammanfattning",
)


class MergeHistoryWindow(QWidget):
    """Table of merge history entries with a details pane.

    Args:
        project_service: The project service owning the data.
        person_id: Show only the entries merged into this person, or all
            entries when ``None``.
        parent: Optional parent widget.
        gateway: Optional merge gateway; defaults to the registered one.
    """

    #: Emitted with the surviving person id when navigation is requested.
    navigate_requested = Signal(str)

    def __init__(
        self,
        project_service: ProjectService,
        person_id: Optional[str] = None,
        parent: Optional[QWidget] = None,
        gateway=None,
    ) -> None:
        super().__init__(parent)
        if parent is not None:
            self.setWindowFlag(Qt.WindowType.Window, True)
        self._service = project_service
        self._person_id = person_id
        self._gateway = gateway
        self._rows: list[HistoryRow] = []
        self._remove_listener = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(REFRESH_DELAY_MS)
        self._refresh_timer.timeout.connect(self.refresh)
        self.setWindowTitle(WINDOW_TITLE)
        self.setAccessibleName(WINDOW_TITLE)
        self.resize(960, 540)
        self._build_ui()
        self.refresh()
        self._remove_listener = self._service.add_merge_listener(self.schedule_refresh)
        gateway_now = self._active_gateway()
        signal = getattr(gateway_now, "merge_changed", None)
        self._connected_signal = None
        if signal is not None and hasattr(signal, "connect"):
            signal.connect(self.schedule_refresh)
            self._connected_signal = signal

    @property
    def person_id(self) -> Optional[str]:
        return self._person_id

    # -- construction ----------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._empty_label = QLabel(EMPTY_HISTORY_TEXT)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setAccessibleName("Tom historik")
        self._empty_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._empty_label)

        self._table = QTableWidget(0, len(COLUMN_HEADERS))
        self._table.setHorizontalHeaderLabels(list(COLUMN_HEADERS))
        self._table.setAccessibleName("Sammanslagningar")
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setTabKeyNavigation(False)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)

        self._details = QPlainTextEdit()
        self._details.setReadOnly(True)
        self._details.setAccessibleName("Detaljer om vald sammanslagning")
        self._details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._table)
        splitter.addWidget(self._details)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        self._navigate_button = QPushButton(NAVIGATE_BUTTON_TEXT)
        self._navigate_button.setAccessibleName(NAVIGATE_BUTTON_TEXT)
        self._navigate_button.setToolTip("Markera den behållna personen i personlistan")
        buttons.addWidget(self._navigate_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.setTabOrder(self._table, self._details)
        self.setTabOrder(self._details, self._navigate_button)

        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.cellDoubleClicked.connect(lambda *_: self.navigate_to_survivor())
        self._navigate_button.clicked.connect(self.navigate_to_survivor)

    # -- data ------------------------------------------------------------

    def _active_gateway(self):
        return self._gateway if self._gateway is not None else get_merge_gateway()

    def schedule_refresh(self) -> None:
        """Refresh within 500 ms; repeated calls share one timer."""
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def row_count(self) -> int:
        return len(self._rows)

    def selected_entry_id(self) -> Optional[str]:
        row = self._selected_row()
        return row.entry_id if row is not None else None

    def select_entry(self, entry_id: str) -> bool:
        for index, row in enumerate(self._rows):
            if row.entry_id == entry_id:
                self._table.selectRow(index)
                return True
        return False

    def refresh(self) -> None:
        """Rebuild the table, keeping the selected entry when it still exists."""
        keep = self.selected_entry_id()
        self._rows = build_history_rows(self._service.data, self._person_id)
        blocked = self._table.blockSignals(True)
        try:
            self._table.setRowCount(len(self._rows))
            for index, row in enumerate(self._rows):
                values = (
                    row.display_name,
                    row.merged_lifespan,
                    row.merged_id,
                    row.merge_date,
                    self._survivor_cell(row),
                    " ".join(row.summary_text_lines),
                )
                for column, text in enumerate(values):
                    item = QTableWidgetItem(text)
                    item.setToolTip(text)
                    self._table.setItem(index, column, item)
            self._table.clearSelection()
            for index, row in enumerate(self._rows):
                if row.entry_id == keep:
                    self._table.selectRow(index)
                    break
        finally:
            self._table.blockSignals(blocked)
        empty = not self._rows
        self._empty_label.setVisible(empty)
        self._table.setVisible(not empty)
        self._on_selection_changed()

    @staticmethod
    def _survivor_cell(row: HistoryRow) -> str:
        if not row.survivor_id:
            return row.survivor_text
        return f"{row.survivor_name} ({row.survivor_id})"

    def _selected_row(self) -> Optional[HistoryRow]:
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            return None
        position = indexes[0].row()
        if 0 <= position < len(self._rows):
            return self._rows[position]
        return None

    def _on_selection_changed(self) -> None:
        row = self._selected_row()
        self._details.setPlainText(self._details_text(row) if row is not None else "")
        self._navigate_button.setEnabled(row is not None and row.can_navigate)

    @staticmethod
    def _details_text(row: HistoryRow) -> str:
        lines = [
            f"{row.display_name} ({row.merged_id}) {row.merged_lifespan}".rstrip(),
            f"Datum: {row.merge_date}",
            f"Behållen person: {row.survivor_text}"
            + (f" ({row.survivor_id})" if row.survivor_id else ""),
            "",
            "Sammanfattning:",
            *(f"  {line}" for line in row.summary_text_lines),
            "",
            "Arkiverade kandidater:",
        ]
        if not row.archived:
            lines.append(f"  {NO_ARCHIVED_CANDIDATE_TEXT}")
        for archived in row.archived:
            try:
                assessment = get_candidate_assessment_label(archived.assessment)
            except Exception:  # noqa: BLE001 - unknown stored value is shown as is
                assessment = archived.assessment
            name = archived.other_person_name or archived.other_person_id
            lines.append(
                f"  {name} ({archived.other_person_id}), bedömning: {assessment}, "
                f"kommentarer: {archived.comment_count}"
            )
        return "\n".join(lines)

    # -- navigation ------------------------------------------------------

    def navigate_to_survivor(self) -> None:
        """Select the surviving person of the selected entry in the list."""
        row = self._selected_row()
        if row is None or not row.can_navigate or not row.survivor_id:
            return
        self.navigate_requested.emit(row.survivor_id)
        gateway = self._active_gateway()
        show_person = getattr(gateway, "show_person", None)
        if show_person is not None:
            show_person(row.survivor_id)

    # -- lifecycle -------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
        if self._connected_signal is not None:
            try:
                self._connected_signal.disconnect(self.schedule_refresh)
            except (RuntimeError, TypeError):
                pass
            self._connected_signal = None
        self._refresh_timer.stop()
        super().closeEvent(event)


_windows: "dict[tuple[int, Optional[str]], weakref.ref[MergeHistoryWindow]]" = {}


def open_merge_history_window(
    project_service: ProjectService,
    person_id: Optional[str] = None,
    parent: Optional[QWidget] = None,
) -> MergeHistoryWindow:
    """Show the history window for a scope, reusing one window per scope."""
    key = (id(project_service), person_id)
    ref = _windows.get(key)
    window = ref() if ref is not None else None
    try:
        alive = window is not None and window.isVisible()
    except RuntimeError:  # underlying C++ object already deleted
        alive = False
    if not alive:
        window = MergeHistoryWindow(project_service, person_id, parent=parent)
        _windows[key] = weakref.ref(window)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    else:
        window.refresh()
    window.show()
    window.raise_()
    window.activateWindow()
    return window
