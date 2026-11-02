"""Basic smoke tests for the Merge_History_Window (full tests: task 20.14)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.merge_candidate import MergeHistoryEntry
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge.merge_history_window import (
    MergeHistoryWindow,
    open_merge_history_window,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeGateway:
    def __init__(self) -> None:
        self.shown: list[str] = []

    def show_person(self, person_id: str) -> None:
        self.shown.append(person_id)


def _service(history: list[MergeHistoryEntry]) -> ProjectService:
    svc = ProjectService()
    data = ProjectData()
    data.persons = [
        Person(id="p1", sex="U", names=[Name(type="birth", given="Anna", surname="Berg")])
    ]
    data.merge_history = history
    svc._project_data = data
    return svc


def _entry(n: int, survivor: str, date: str, **kw) -> MergeHistoryEntry:
    return MergeHistoryEntry(f"merge_{n}", survivor, f"gone_{n}", f"Namn {n}", "", date, **kw)


def test_empty_state(qapp):
    win = MergeHistoryWindow(_service([]))
    try:
        win.show()
        assert win.windowTitle() == "Sammanslagningshistorik"
        assert win._empty_label.isVisible()
        assert win._empty_label.text() == "Inga sammanslagningar finns."
        assert not win._navigate_button.isEnabled()
    finally:
        win.close()


def test_rows_newest_first_and_navigation(qapp):
    svc = _service([_entry(1, "p1", "2020-01-01"), _entry(2, "p1", "2021-01-01")])
    gateway = FakeGateway()
    win = MergeHistoryWindow(svc, gateway=gateway)
    try:
        assert win.row_count() == 2
        assert win._table.item(0, 2).text() == "gone_2"
        assert not win._navigate_button.isEnabled()
        win._table.selectRow(0)
        assert "Ingen sammanfattning sparades." in win._details.toPlainText()
        assert "Ingen kandidat arkiverades." in win._details.toPlainText()
        assert win._navigate_button.isEnabled()
        win._navigate_button.click()
        assert gateway.shown == ["p1"]
    finally:
        win.close()


def test_unresolved_survivor_disables_navigation(qapp):
    win = MergeHistoryWindow(_service([_entry(1, "missing", "2020-01-01")]))
    try:
        win._table.selectRow(0)
        assert "Behållen person kan inte fastställas." in win._table.item(0, 4).text()
        assert not win._navigate_button.isEnabled()
    finally:
        win.close()


def test_refresh_keeps_selection(qapp):
    svc = _service([_entry(1, "p1", "2020-01-01")])
    win = MergeHistoryWindow(svc)
    try:
        win._table.selectRow(0)
        svc.data.merge_history.append(_entry(2, "p1", "2021-01-01"))
        win.refresh()
        assert win.row_count() == 2
        assert win.selected_entry_id() == "merge_1"
    finally:
        win.close()


def test_open_reuses_window_per_scope(qapp):
    svc = _service([_entry(1, "p1", "2020-01-01")])
    first = open_merge_history_window(svc, "p1")
    try:
        assert open_merge_history_window(svc, "p1") is first
        assert open_merge_history_window(svc, None) is not first
    finally:
        first.close()
