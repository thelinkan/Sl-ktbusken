"""Comparison_Table: row-by-row comparison of the two slot persons.

The table only displays :class:`ComparisonRow` objects computed by
``ComparisonSession`` from the project data at render time. It keeps no
authoritative copy of any value and never modifies data. A value with source
references offers a link per source; the source opens in a read-only dialog.
"""

from __future__ import annotations

import html
from typing import Mapping, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.model.source import Source
from slaktbusken.services.comparison_session import (
    LEGEND_TEXT,
    STATUS_DIFFERS,
    STATUS_MISSING_LEFT,
    STATUS_MISSING_RIGHT,
    ComparisonRow,
)

COLUMN_HEADERS = ("Rad", "Person 1", "Person 2", "Markering")
EMPTY_TABLE_TEXT = "Ingen person är vald."
SOURCE_UNAVAILABLE_TEXT = "Källan är inte tillgänglig."

_DIFFERS_BRUSH = QBrush(QColor("#FFE0B2"))
_MISSING_BRUSH = QBrush(QColor("#E0E0E0"))
_MARK_COLUMN = 3


class SourceInfoDialog(QDialog):
    """Read-only view of one source."""

    def __init__(self, source: Source, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Källa: {source.title}")
        layout = QVBoxLayout(self)
        text = QPlainTextEdit(self)
        text.setReadOnly(True)
        lines = [
            f"Titel: {source.title}",
            f"Id: {source.id}",
            f"Leverantör: {source.provider}",
            f"Typ: {source.source_type}",
        ]
        for label, value in (
            ("Referens", source.reference_text),
            ("Anteckning", source.short_note),
            ("Fri anteckning", source.free_note),
        ):
            if value:
                lines.append(f"{label}: {value}")
        text.setPlainText("\n".join(lines))
        layout.addWidget(text)
        self.resize(480, 320)


class ComparisonTable(QWidget):
    """The 30 % column of the comparison window."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._rows: list[ComparisonRow] = []
        self._sources: Mapping[str, Source] = {}
        self._source_dialogs: list[SourceInfoDialog] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._title = QLabel("Jämförelse", self)
        font = self._title.font()
        font.setBold(True)
        self._title.setFont(font)
        layout.addWidget(self._title)

        self._table = QTableWidget(0, len(COLUMN_HEADERS), self)
        self._table.setHorizontalHeaderLabels(list(COLUMN_HEADERS))
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setWordWrap(True)
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        # "Rad" and "Markering" hug their content; the two person columns take
        # the remaining width so long values wrap instead of being clipped.
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_MARK_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeaderItem(_MARK_COLUMN).setToolTip(LEGEND_TEXT)
        self._table.setAccessibleName("Jämförelsetabell")
        layout.addWidget(self._table, stretch=1)

        self._empty_label = QLabel(EMPTY_TABLE_TEXT, self)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_label)

        self._error_label = QLabel("", self)
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("color: #B71C1C;")
        self._error_label.setAccessibleName("Felmeddelande för källa")
        layout.addWidget(self._error_label)

        self._legend = QLabel(f"Förklaring: {LEGEND_TEXT}", self)
        self._legend.setWordWrap(True)
        self._legend.setToolTip(LEGEND_TEXT)
        layout.addWidget(self._legend)

    # -- accessors -----------------------------------------------------------

    @property
    def table(self) -> QTableWidget:
        return self._table

    def row_count(self) -> int:
        return self._table.rowCount()

    def cell_text(self, row: int, column: int) -> str:
        """The value shown in a cell.

        When a source cell widget renders the value, the underlying item text
        is empty (so the value is not drawn twice); the plain value is read back
        from the widget instead.
        """
        widget = self._table.cellWidget(row, column)
        if widget is not None:
            value = widget.property("value_text")
            if value is not None:
                return str(value)
        item = self._table.item(row, column)
        return item.text() if item is not None else ""

    def row_mark(self, row: int) -> str:
        """Mark text of a row: ``"Avviker"``, ``"Saknas"`` or empty."""
        return self.cell_text(row, _MARK_COLUMN)

    def row_marks(self) -> dict[str, str]:
        """Mark per row key, for rows that carry one."""
        return {r.key: r.status_label for r in self._rows if r.status_label}

    def row_index(self, key: str) -> int:
        for i, row in enumerate(self._rows):
            if row.key == key:
                return i
        return -1

    def legend_text(self) -> str:
        return self._legend.text()

    def empty_state_visible(self) -> bool:
        return not self._empty_label.isHidden()

    def error_text(self) -> str:
        return self._error_label.text()

    # -- content ---------------------------------------------------------------

    def set_rows(
        self,
        rows: Sequence[ComparisonRow],
        left_title: str = "Person 1",
        right_title: str = "Person 2",
        sources: Optional[Mapping[str, Source]] = None,
        filled: tuple[bool, bool] = (True, True),
    ) -> None:
        """Show ``rows``; an empty slot's column stays blank (11.9, 10.13)."""
        self._rows = list(rows)
        self._sources = sources or {}
        self._table.setUpdatesEnabled(False)
        try:
            self._table.clearContents()
            self._table.setRowCount(len(self._rows))
            self._table.setHorizontalHeaderItem(1, QTableWidgetItem(left_title))
            self._table.setHorizontalHeaderItem(2, QTableWidgetItem(right_title))
            self._table.setHorizontalHeaderItem(3, QTableWidgetItem(COLUMN_HEADERS[3]))
            self._table.horizontalHeaderItem(_MARK_COLUMN).setToolTip(LEGEND_TEXT)
            for r, row in enumerate(self._rows):
                self._fill_row(r, row)
            self._table.resizeRowsToContents()
        finally:
            self._table.setUpdatesEnabled(True)
        self._empty_label.setVisible(not any(filled))
        if self._error_label.text():
            self._error_label.clear()

    def _fill_row(self, r: int, row: ComparisonRow) -> None:
        label = QTableWidgetItem(row.label)
        label.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._table.setItem(r, 0, label)
        for column, values, source_ids, missing in (
            (1, row.left, row.left_source_ids, row.status == STATUS_MISSING_LEFT),
            (2, row.right, row.right_source_ids, row.status == STATUS_MISSING_RIGHT),
        ):
            text = "\n".join(values)
            if missing:
                text = "Saknas"
            use_source_widget = bool(source_ids) and not missing
            # When a source cell widget renders the value, the underlying item
            # keeps no text so the value is not drawn twice behind the widget
            # (the empty item still carries background, row sizing and tooltip).
            item = QTableWidgetItem("" if use_source_widget else text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            if row.status == STATUS_DIFFERS:
                item.setBackground(_DIFFERS_BRUSH)
                item.setToolTip(LEGEND_TEXT)
            elif missing:
                item.setBackground(_MISSING_BRUSH)
                font = QFont(item.font())
                font.setItalic(True)
                item.setFont(font)
            self._table.setItem(r, column, item)
            if use_source_widget:
                self._table.setCellWidget(r, column, self._source_cell(text, source_ids))
        mark = QTableWidgetItem(row.status_label)
        mark.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        if row.status == STATUS_DIFFERS:
            font = QFont(mark.font())
            font.setBold(True)
            mark.setFont(font)
            mark.setBackground(_DIFFERS_BRUSH)
            mark.setToolTip(LEGEND_TEXT)
        elif row.status_label:
            font = QFont(mark.font())
            font.setItalic(True)
            mark.setFont(font)
            mark.setBackground(_MISSING_BRUSH)
        self._table.setItem(r, _MARK_COLUMN, mark)

    def _source_cell(self, text: str, source_ids: Sequence[str]) -> QLabel:
        """Value text with the "Källa: [n]" links on their own line below it."""
        links = " ".join(
            f'<a href="{html.escape(sid, quote=True)}">[{i}]</a>'
            for i, sid in enumerate(source_ids, start=1)
        )
        value_html = html.escape(text).replace(chr(10), "<br>")
        label = QLabel(f"{value_html}<br>Källa: {links}")
        label.setProperty("value_text", text)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        label.setToolTip("Öppna källan")
        label.linkActivated.connect(self.open_source)
        return label

    # -- sources -------------------------------------------------------------

    def open_source(self, source_id: str) -> bool:
        """Open a referenced source read-only; show an error when unavailable.

        The window and all displayed values stay unchanged either way (11.10).
        """
        source = self._sources.get(source_id)
        if source is None:
            self._error_label.setText(SOURCE_UNAVAILABLE_TEXT)
            return False
        self._error_label.clear()
        dialog = SourceInfoDialog(source, self.window())
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.destroyed.connect(lambda _=None, d=dialog: self._forget(d))
        self._source_dialogs.append(dialog)
        dialog.show()
        return True

    def _forget(self, dialog: SourceInfoDialog) -> None:
        if dialog in self._source_dialogs:
            self._source_dialogs.remove(dialog)
