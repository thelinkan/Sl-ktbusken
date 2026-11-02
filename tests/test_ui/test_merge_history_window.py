"""Widget tests for the Merge_History_Window (requirement 36.2 to 36.9)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time

import pytest
from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.merge_candidate import (
    ArchivedCandidate,
    MergeCandidateComment,
    MergeHistoryEntry,
)
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.redirect_resolution import RedirectResolver
from slaktbusken.ui.merge.merge_history_window import (
    COLUMN_HEADERS,
    MergeHistoryWindow,
)


class FakeGateway(QObject):
    merge_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.shown: list[str] = []

    def show_person(self, person_id: str) -> None:
        self.shown.append(person_id)


def _person(pid: str, given: str, surname: str) -> Person:
    return Person(id=pid, sex="U", names=[Name(type="birth", given=given, surname=surname)])


def _service(history, persons=None) -> ProjectService:
    svc = ProjectService()
    data = ProjectData()
    data.persons = persons or [
        _person("p1", "Anna", "Berg"),
        _person("p2", "Bo", "Ek"),
    ]
    data.merge_history = list(history)
    svc._project_data = data
    return svc


def _entry(n, survivor="p1", date="2020-01-01", **kw) -> MergeHistoryEntry:
    kw.setdefault("merged_person_name", f"Namn {n}")
    kw.setdefault("merged_person_lifespan", "1829–1890")
    return MergeHistoryEntry(
        id=f"merge_{n}",
        surviving_person_id=survivor,
        merged_person_id=f"gone_{n}",
        merge_date=date,
        **kw,
    )


@pytest.fixture
def make_window(qtbot):
    made = []

    def make(history, person_id=None, persons=None, gateway=None):
        svc = _service(history, persons)
        gw = gateway if gateway is not None else FakeGateway()
        win = MergeHistoryWindow(svc, person_id=person_id, gateway=gw)
        qtbot.addWidget(win)
        made.append(win)
        return win, svc, gw

    yield make
    for w in made:
        w.close()


def _cell(win, row, col):
    return win._table.item(row, col).text()


# -- columns and rows --------------------------------------------------------


def test_column_order_and_headers(make_window):
    win, _, _ = make_window([_entry(1)])
    table = win._table
    assert table.columnCount() == 6
    headers = [table.horizontalHeaderItem(i).text() for i in range(6)]
    assert headers == [
        "Sammanslagen person",
        "Livstid",
        "Id",
        "Datum",
        "Behållen person",
        "Sammanfattning",
    ]
    assert tuple(headers) == COLUMN_HEADERS


def test_rows_newest_first_with_id_suffix_tiebreak(make_window):
    history = [
        _entry(1, date="2020-01-01"),
        _entry(2, date="2021-05-05"),
        _entry(9, date="2021-05-05"),
        _entry(10, date="2021-05-05"),
    ]
    win, _, _ = make_window(history)
    ids = [_cell(win, r, 2) for r in range(win.row_count())]
    assert ids == ["gone_10", "gone_9", "gone_2", "gone_1"]


def test_cell_values_equal_stored_fields_and_survivor(make_window):
    entry = _entry(1, date="2022-03-04", summary_lines=["1 namn flyttades.", "2 händelser flyttades."])
    win, _, _ = make_window([entry])
    assert win.row_count() == 1
    assert _cell(win, 0, 0) == "Namn 1"
    assert _cell(win, 0, 1) == "1829–1890"
    assert _cell(win, 0, 2) == "gone_1"
    assert _cell(win, 0, 3) == "2022-03-04"
    survivor = _cell(win, 0, 4)
    assert "Anna" in survivor and survivor.endswith("(p1)")
    assert _cell(win, 0, 5) == "1 namn flyttades. 2 händelser flyttades."


def test_rows_equal_stored_entries_count(make_window):
    history = [_entry(i, date=f"2020-01-{i:02d}") for i in range(1, 6)]
    win, _, _ = make_window(history)
    assert win.row_count() == len(history) == win._table.rowCount()


# -- details pane ---------------------------------------------------------


def test_details_show_summary_lines(make_window):
    entry = _entry(1, summary_lines=["3 namn flyttades.", "Beslut: 2."])
    win, _, _ = make_window([entry])
    win._table.selectRow(0)
    text = win._details.toPlainText()
    assert "Namn 1" in text and "gone_1" in text and "1829–1890" in text
    assert "3 namn flyttades." in text
    assert "Beslut: 2." in text
    assert "Ingen sammanfattning sparades." not in text


def test_details_no_summary_and_no_archived_text(make_window):
    win, _, _ = make_window([_entry(1)])
    assert win._details.toPlainText() == ""
    win._table.selectRow(0)
    text = win._details.toPlainText()
    assert "Ingen sammanfattning sparades." in text
    assert "Ingen kandidat arkiverades." in text
    assert "Ingen sammanfattning sparades." in _cell(win, 0, 5)


def test_details_show_archived_candidate(make_window):
    archived = ArchivedCandidate(
        id="c1",
        person_1_id="gone_1",
        person_2_id="p2",
        assessment="possible",
        enabled=True,
        comments=[
            MergeCandidateComment(id="k1", date="2020-01-01", text="a"),
            MergeCandidateComment(id="k2", date="2020-01-02", text="b"),
        ],
    )
    win, _, _ = make_window([_entry(1, archived_candidates=[archived])])
    win._table.selectRow(0)
    text = win._details.toPlainText()
    assert "Bo" in text and "(p2)" in text
    assert "Möjlig dubblett" in text
    assert "kommentarer: 2" in text
    assert "Ingen kandidat arkiverades." not in text


def test_details_cleared_when_selection_cleared(make_window):
    win, _, _ = make_window([_entry(1)])
    win._table.selectRow(0)
    assert win._details.toPlainText()
    win._table.clearSelection()
    assert win._details.toPlainText() == ""
    assert not win._navigate_button.isEnabled()


# -- empty state ------------------------------------------------------------


def test_empty_state(make_window):
    win, _, _ = make_window([])
    win.show()
    assert win.row_count() == 0
    assert win._empty_label.isVisible()
    assert win._empty_label.text() == "Inga sammanslagningar finns."
    assert not win._table.isVisible()
    assert not win._navigate_button.isEnabled()


def test_non_empty_hides_empty_label(make_window):
    win, _, _ = make_window([_entry(1)])
    win.show()
    assert not win._empty_label.isVisible()
    assert win._table.isVisible()


# -- unresolved survivor ----------------------------------------------------


def _cycle_history():
    a = MergeHistoryEntry("merge_1", "gone_2", "gone_1", "A", "", "2020-01-01")
    b = MergeHistoryEntry("merge_2", "gone_1", "gone_2", "B", "", "2020-01-02")
    return [a, b]


def _ambiguous_history():
    return [
        MergeHistoryEntry("merge_1", "p1", "gone_x", "X", "", "2020-01-01"),
        MergeHistoryEntry("merge_2", "p2", "gone_x", "X", "", "2020-01-02"),
    ]


@pytest.mark.parametrize(
    "history",
    [
        pytest.param(_cycle_history(), id="cycle"),
        pytest.param(_ambiguous_history(), id="ambiguous"),
        pytest.param([_entry(1, survivor="missing")], id="missing"),
    ],
)
def test_unresolved_survivor(make_window, history):
    win, _, gw = make_window(history)
    assert win.row_count() == len(history)
    for row in range(win.row_count()):
        assert "Behållen person kan inte fastställas." in _cell(win, row, 4)
        win._table.selectRow(row)
        assert "Behållen person kan inte fastställas." in win._details.toPlainText()
        assert not win._navigate_button.isEnabled()
        win.navigate_to_survivor()
    assert gw.shown == []


# -- navigation -------------------------------------------------------------


def test_navigation_via_button(make_window, qtbot):
    win, _, gw = make_window([_entry(1)])
    assert not win._navigate_button.isEnabled()
    assert win._navigate_button.text() == "Gå till behållen person"
    win._table.selectRow(0)
    assert win._navigate_button.isEnabled()
    with qtbot.waitSignal(win.navigate_requested, timeout=1000) as blocker:
        win._navigate_button.click()
    assert blocker.args == ["p1"]
    assert gw.shown == ["p1"]


def test_navigation_resolves_through_redirect(make_window):
    history = [
        _entry(1, survivor="gone_2", date="2020-01-01"),
        _entry(2, survivor="p1", date="2020-02-01"),
    ]
    win, _, gw = make_window(history)
    win._table.selectRow(win.row_count() - 1)  # oldest: merged gone_1 into gone_2
    assert win._navigate_button.isEnabled()
    win._navigate_button.click()
    assert gw.shown == ["p1"]


def test_navigation_via_double_click(make_window, qtbot):
    win, _, gw = make_window([_entry(1)])
    win.show()
    qtbot.waitExposed(win)
    table = win._table
    rect = table.visualItemRect(table.item(0, 0))
    QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    with qtbot.waitSignal(win.navigate_requested, timeout=1000) as blocker:
        QTest.mouseDClick(
            table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center()
        )
    assert blocker.args == ["p1"]
    assert gw.shown == ["p1"]


def test_double_click_on_unresolved_does_nothing(make_window, qtbot):
    win, _, gw = make_window([_entry(1, survivor="missing")])
    win.show()
    qtbot.waitExposed(win)
    table = win._table
    rect = table.visualItemRect(table.item(0, 0))
    QTest.mouseDClick(table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    assert gw.shown == []


def test_navigation_without_selection_does_nothing(make_window):
    win, _, gw = make_window([_entry(1)])
    win.navigate_to_survivor()
    assert gw.shown == []


# -- refresh -----------------------------------------------------------------


def test_refresh_on_gateway_merge_changed_keeps_selection(make_window, qtbot):
    history = [_entry(1, date="2020-01-01"), _entry(2, date="2021-01-01")]
    win, svc, gw = make_window(history)
    win.select_entry("merge_1")
    assert win.selected_entry_id() == "merge_1"
    svc.data.merge_history.append(_entry(3, date="2022-01-01"))
    start = time.monotonic()
    gw.merge_changed.emit()
    qtbot.waitUntil(lambda: win.row_count() == 3, timeout=2000)
    assert time.monotonic() - start < 0.9
    assert win.selected_entry_id() == "merge_1"
    assert _cell(win, 0, 2) == "gone_3"
    assert win._navigate_button.isEnabled()
    assert "Namn 1" in win._details.toPlainText()


def test_refresh_on_service_notification(make_window, qtbot):
    win, svc, _ = make_window([_entry(1)])
    win.select_entry("merge_1")
    svc.data.merge_history.append(_entry(2, date="2021-01-01"))
    svc.notify_merge_changed()
    qtbot.waitUntil(lambda: win.row_count() == 2, timeout=2000)
    assert win.selected_entry_id() == "merge_1"


def test_refresh_drops_selection_when_entry_removed(make_window, qtbot):
    win, svc, gw = make_window([_entry(1), _entry(2, date="2021-01-01")])
    win.select_entry("merge_1")
    svc.data.merge_history[:] = [svc.data.merge_history[1]]
    win.refresh()
    assert win.row_count() == 1
    assert win.selected_entry_id() is None
    assert win._details.toPlainText() == ""


def test_refresh_from_empty_to_non_empty(make_window, qtbot):
    win, svc, gw = make_window([])
    win.show()
    svc.data.merge_history.append(_entry(1))
    gw.merge_changed.emit()
    qtbot.waitUntil(lambda: win.row_count() == 1, timeout=2000)
    assert not win._empty_label.isVisible()


def test_no_refresh_after_close(make_window, qtbot):
    win, svc, gw = make_window([_entry(1)])
    win.close()
    svc.data.merge_history.append(_entry(2, date="2021-01-01"))
    gw.merge_changed.emit()
    svc.notify_merge_changed()
    qtbot.wait(700)
    assert win.row_count() == 1


# -- scope -------------------------------------------------------------------


def _scoped_history():
    return [
        _entry(1, survivor="p1", date="2020-01-01"),
        _entry(2, survivor="p2", date="2020-02-01"),
        _entry(3, survivor="p1", date="2020-03-01"),
        _entry(4, survivor="gone_3", date="2020-04-01"),  # chain into p1
    ]


def test_scoped_window_lists_only_that_survivor(make_window):
    win, _, _ = make_window(_scoped_history(), person_id="p2")
    assert win.person_id == "p2"
    assert [_cell(win, r, 2) for r in range(win.row_count())] == ["gone_2"]


def test_scoped_rows_equal_reversed_merged_into(make_window):
    history = _scoped_history()
    win, _, _ = make_window(history, person_id="p1")
    expected = [e.merged_person_id for e in reversed(RedirectResolver(history).merged_into("p1"))]
    assert [_cell(win, r, 2) for r in range(win.row_count())] == expected
    assert expected  # sanity: the scope is not empty


def test_unscoped_window_lists_all(make_window):
    history = _scoped_history()
    win, _, _ = make_window(history)
    assert win.person_id is None
    assert win.row_count() == len(history)


def test_scoped_window_without_entries_shows_empty_state(make_window):
    win, _, _ = make_window(_scoped_history(), person_id="nobody")
    win.show()
    assert win.row_count() == 0
    assert win._empty_label.isVisible()


# -- accessibility and keyboard ---------------------------------------------


def test_accessible_names(make_window):
    win, _, _ = make_window([_entry(1)])
    assert win.accessibleName() == "Sammanslagningshistorik"
    assert win._table.accessibleName() == "Sammanslagningar"
    assert win._details.accessibleName() == "Detaljer om vald sammanslagning"
    assert win._navigate_button.accessibleName() == "Gå till behållen person"
    assert win._empty_label.accessibleName() == "Tom historik"


def test_tab_order_table_details_button(make_window):
    win, _, _ = make_window([_entry(1)])
    # Skip the table's own viewport/scroll bars (inner focus targets).
    chain = []
    w = win._table
    for _ in range(40):
        w = w.nextInFocusChain()
        if w in (win._details, win._navigate_button):
            chain.append(w)
        if len(chain) == 2:
            break
    assert chain == [win._details, win._navigate_button]
    assert not win._table.tabKeyNavigation()


def test_keyboard_selection_and_button_activation(make_window, qtbot):
    win, _, gw = make_window([_entry(1, date="2020-01-01"), _entry(2, date="2021-01-01")])
    win.show()
    qtbot.waitExposed(win)
    win._table.setFocus()
    win._table.setCurrentCell(0, 0)
    QTest.keyClick(win._table, Qt.Key.Key_Down)
    assert win.selected_entry_id() == "merge_1"
    assert win._navigate_button.isEnabled()
    QTest.keyClick(win._table, Qt.Key.Key_Enter)  # must not break the window
    assert win.selected_entry_id() == "merge_1"
    win._navigate_button.setFocus()
    QTest.keyClick(win._navigate_button, Qt.Key.Key_Space)
    assert gw.shown == ["p1"]


def test_table_not_editable_and_row_selection(make_window):
    win, _, _ = make_window([_entry(1)])
    assert not (win._table.editTriggers() & win._table.EditTrigger.AnyKeyPressed)
    assert win._table.selectionBehavior() == win._table.SelectionBehavior.SelectRows
    assert win._table.selectionMode() == win._table.SelectionMode.SingleSelection


def test_text_is_selectable(make_window):
    win, _, _ = make_window([_entry(1)])
    assert win._details.isReadOnly()
    flags = win._details.textInteractionFlags()
    assert flags & Qt.TextInteractionFlag.TextSelectableByMouse
    assert flags & Qt.TextInteractionFlag.TextSelectableByKeyboard
    assert win._empty_label.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse
    win._table.selectRow(0)
    win._details.selectAll()
    assert win._details.textCursor().selectedText()
