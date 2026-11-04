"""Regression tests for ComparisonTable cell rendering (ITEM 1 and ITEM 2).

The source cell previously rendered the value twice: once in the underlying
QTableWidgetItem and again inside the cell widget, so the two overlapped (for
example "1888-11-14 Källa: 1888-11-14 [1]"). These tests pin that the value
appears exactly once and that the "Källa: [n]" links are present and placed on
their own line, plus the column/alignment layout from ITEM 1.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHeaderView, QLabel

from slaktbusken.model.source import Source
from slaktbusken.services.comparison_session import (
    STATUS_DIFFERS,
    STATUS_MISSING_RIGHT,
    ComparisonRow,
)
from slaktbusken.ui.merge.comparison_table import ComparisonTable


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _source(sid: str = "source_1") -> Source:
    return Source(id=sid, provider="Arkiv", source_type="Kyrkobok", title="Födelsebok")


def _value_cell_widget(table: ComparisonTable, row: int, column: int) -> QLabel:
    widget = table.table.cellWidget(row, column)
    assert isinstance(widget, QLabel)
    return widget


def test_source_cell_shows_value_once_and_keeps_links(qapp):
    table = ComparisonTable()
    row = ComparisonRow(
        key="birth",
        label="Född",
        left=("1888-11-14",),
        right=("1888-11-14",),
        status=STATUS_DIFFERS,
        left_source_ids=("source_1",),
        right_source_ids=("source_1",),
    )
    table.set_rows([row], sources={"source_1": _source()})

    label = _value_cell_widget(table, 0, 1)
    html = label.text()
    # The value appears exactly once in the rendered widget.
    assert html.count("1888-11-14") == 1
    # The links row is present, on its own line below the value.
    assert "Källa:" in html
    assert 'href="source_1"' in html
    assert "<br>" in html.split("Källa:")[0]
    # The underlying item carries no visible text, so nothing is drawn behind
    # the widget, but it still exists for background/row sizing.
    assert table.table.item(0, 1) is not None
    assert table.table.item(0, 1).text() == ""
    # cell_text reports the value once via the widget (public accessor contract).
    assert table.cell_text(0, 1) == "1888-11-14"


def test_cells_without_sources_keep_value_in_item(qapp):
    table = ComparisonTable()
    row = ComparisonRow(
        key="name",
        label="Namn",
        left=("Anna Svensson",),
        right=("Anna Svensson",),
    )
    table.set_rows([row])
    # No source widget: the value lives in the item and renders once.
    assert table.table.cellWidget(0, 1) is None
    assert table.cell_text(0, 1) == "Anna Svensson"


def test_missing_cell_has_no_source_widget_and_reads_saknas(qapp):
    table = ComparisonTable()
    row = ComparisonRow(
        key="death",
        label="Död",
        left=("1920-05-05",),
        right=(),
        status=STATUS_MISSING_RIGHT,
        left_source_ids=("source_1",),
    )
    table.set_rows([row], sources={"source_1": _source()})
    # Missing side: no source widget, italic "Saknas".
    assert table.table.cellWidget(0, 2) is None
    assert table.cell_text(0, 2) == "Saknas"
    # Present side keeps its source widget and shows the value once.
    label = _value_cell_widget(table, 0, 1)
    assert label.text().count("1920-05-05") == 1


def test_column_resize_modes_and_top_alignment(qapp):
    table = ComparisonTable()
    row = ComparisonRow(key="name", label="Namn", left=("A",), right=("B",))
    table.set_rows([row])
    header = table.table.horizontalHeader()
    # Rad and Markering hug content; the two person columns stretch.
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.ResizeToContents
    assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Stretch
    assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.Stretch
    assert header.sectionResizeMode(3) == QHeaderView.ResizeMode.ResizeToContents
    assert not header.stretchLastSection()
    assert table.table.wordWrap()
    # Cell contents are top-aligned.
    item = table.table.item(0, 1)
    assert item.textAlignment() & Qt.AlignmentFlag.AlignTop
