"""Offscreen tests for the Merge_History block in the candidate section (36.10)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from slaktbusken.model.merge_candidate import MergeHistoryEntry
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.merge.candidate_section import CandidatesSection
from slaktbusken.ui.merge.merge_gateway import set_merge_gateway


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeGateway(QObject):
    merge_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple] = []

    def open_history(self, pid=None):
        self.calls.append(("history", pid))


@pytest.fixture
def gateway():
    gw = FakeGateway()
    set_merge_gateway(gw)
    yield gw
    set_merge_gateway(None)


def _data() -> ProjectData:
    data = ProjectData()
    data.persons = [
        Person(id="p1", sex="U", names=[Name(type="birth", given="Anna", surname="Berg")])
    ]
    return data


def _section(data, pid="p1") -> CandidatesSection:
    return CandidatesSection(data, lambda: pid)


def test_empty_note_when_no_history(qapp, gateway):
    section = _section(_data())
    section.show()
    block = section._history_block
    assert block._empty_label.isVisible()
    assert block._empty_label.text() == "Inga sammanslagningar finns."
    assert block.row_texts() == []
    assert block._button.text() == "Visa sammanslagningshistorik"
    assert block._button.accessibleName() == "Visa sammanslagningshistorik"


def test_rows_and_refresh_on_merge_changed(qapp, gateway):
    data = _data()
    section = _section(data)
    section.show()
    data.merge_history.append(
        MergeHistoryEntry("merge_1", "p1", "gone_1", "Bo Berg", "1800–1870", "2020-01-01")
    )
    gateway.merge_changed.emit()
    block = section._history_block
    rows = block.row_texts()
    assert len(rows) == 1
    for part in ("Bo Berg", "1800–1870", "gone_1", "2020-01-01"):
        assert part in rows[0]
    assert not block._empty_label.isVisible()


def test_button_opens_history_for_person(qapp, gateway):
    section = _section(_data())
    section._history_block._button.click()
    assert gateway.calls == [("history", "p1")]


def test_hidden_for_unsaved_person(qapp, gateway):
    section = _section(_data(), pid="")
    section.show()
    assert not section._history_block.isVisible()
