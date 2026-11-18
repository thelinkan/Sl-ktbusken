"""Offscreen tests for multi-selection and right-click handling (7.18)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QItemSelectionModel, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractItemView, QApplication, QMenu, QTreeWidgetItem

from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.app_settings_io import AppSettings, AppSettingsService
from slaktbusken.ui.person_list_panel import PersonListPanel, rows_after_right_click

COMPARE = "Jämför personer..."
MARK = "Markera som sammanslagningskandidater"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def shown_menus() -> list[QMenu]:
    return []


@pytest.fixture
def panel(qapp, tmp_path, shown_menus):
    # Keep the panel away from the real settings file.
    service = AppSettingsService()
    service.SETTINGS_PATH = tmp_path / "app_settings.json"
    service._settings = AppSettings()
    app = SimpleNamespace(
        app_settings_service=service,
        project_service=SimpleNamespace(data=ProjectData(), project_path="p.json.gz"),
    )
    p = PersonListPanel(app)
    # Replace the blocking menu call with a recorder. Some platforms (offscreen
    # among them) deliver the context menu event on the press itself.
    p._exec_menu = lambda menu, _pos: shown_menus.append(menu)
    tree = p._tree_widget
    for i in range(1, 5):
        item = QTreeWidgetItem([f"Person {i}"])
        item.setData(0, Qt.ItemDataRole.UserRole, f"person_{i}")
        tree.addTopLevelItem(item)
    p.resize(400, 300)
    p.show()
    QApplication.processEvents()
    yield p
    p.close()


def _right_press(tree, item) -> QPoint:
    # Press inside the visible name column (the full row is wider than the view).
    pos = QPoint(10, tree.visualItemRect(item).center().y())
    assert tree.itemAt(pos) is item
    QTest.mousePress(tree.viewport(), Qt.MouseButton.RightButton, pos=pos)
    return pos


def _select_two(tree) -> None:
    tree.topLevelItem(0).setSelected(True)
    tree.topLevelItem(1).setSelected(True)


def _selected(tree) -> list[str]:
    return sorted(i.data(0, Qt.ItemDataRole.UserRole) for i in tree.selectedItems())


def _entries(menu: QMenu) -> dict:
    return {a.text(): a for a in menu.actions() if a.text() in (COMPARE, MARK)}


def test_rows_after_right_click_rule():
    assert rows_after_right_click([1, 2], None) == []
    assert rows_after_right_click([1, 2], 2) == [1, 2]
    assert rows_after_right_click([1, 2], 3) == [3]
    assert rows_after_right_click([], 0) == [0]


def test_extended_selection_mode(panel):
    assert (
        panel._tree_widget.selectionMode()
        == QAbstractItemView.SelectionMode.ExtendedSelection
    )


def test_right_click_inside_selection_keeps_selection_and_current(panel):
    tree = panel._tree_widget
    _select_two(tree)
    tree.setCurrentItem(
        tree.topLevelItem(0), 0, QItemSelectionModel.SelectionFlag.NoUpdate
    )
    _right_press(tree, tree.topLevelItem(1))
    assert _selected(tree) == ["person_1", "person_2"]
    assert tree.currentItem() is tree.topLevelItem(0)


def test_right_click_outside_selection_selects_only_that_row(panel, shown_menus):
    tree = panel._tree_widget
    _select_two(tree)
    pos = _right_press(tree, tree.topLevelItem(3))
    assert _selected(tree) == ["person_4"]
    panel._on_context_menu_requested(pos)
    compare = _entries(shown_menus[-1])[COMPARE]
    assert compare.data()[1] == ("person_4",)


def test_context_menu_uses_both_ids_for_multi_selection(panel, shown_menus):
    tree = panel._tree_widget
    _select_two(tree)
    pos = _right_press(tree, tree.topLevelItem(1))
    panel._on_context_menu_requested(pos)
    entries = _entries(shown_menus[-1])
    assert entries[COMPARE].isEnabled()
    assert entries[COMPARE].data()[1] == ("person_1", "person_2")
    assert entries[MARK].isEnabled()
    assert _selected(tree) == ["person_1", "person_2"]


def test_context_menu_on_empty_space_disables_entries(panel, shown_menus):
    tree = panel._tree_widget
    pos = QPoint(5, tree.viewport().height() - 2)
    assert tree.itemAt(pos) is None
    panel._on_context_menu_requested(pos)
    entries = _entries(shown_menus[-1])
    assert set(entries) == {COMPARE, MARK}
    assert not any(a.isEnabled() for a in entries.values())


def test_plain_left_click_selects_one_row_and_navigates(panel):
    tree = panel._tree_widget
    _select_two(tree)
    emitted: list[str] = []
    panel.person_selected.connect(emitted.append)
    pos = QPoint(10, tree.visualItemRect(tree.topLevelItem(2)).center().y())
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    assert _selected(tree) == ["person_3"]
    assert emitted == ["person_3"]


# --- Property 51 (task 7.19) -------------------------------------------------
from hypothesis import HealthCheck, given, settings, strategies as st


@st.composite
def _selection_and_click(draw):
    n = draw(st.integers(min_value=0, max_value=12))
    rows = draw(st.lists(st.integers(0, max(n - 1, 0)), unique=True, max_size=n)) if n else []
    # Selected rows in an arbitrary (but fixed) order, as given by the caller.
    clicked = draw(st.one_of(st.none(), st.integers(0, 15)))
    return rows, clicked


# Feature: person-comparison-and-merge, Property 51: Right-click selection rule
# **Validates: Requirements 8.14, 8.15**
@given(_selection_and_click())
def test_property_51_rows_after_right_click(data):
    selected, clicked = data
    result = rows_after_right_click(selected, clicked)
    if clicked is None:
        assert result == []
    elif clicked in selected:
        assert result == selected
    else:
        assert result == [clicked]


# Feature: person-comparison-and-merge, Property 51: Right-click selection rule
# **Validates: Requirements 8.14, 8.15**
@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    rows=st.lists(st.integers(0, 3), unique=True, min_size=2, max_size=4),
    pick=st.integers(0, 3),
)
def test_property_51_menu_ids_equal_ids_before_click(panel, shown_menus, rows, pick):
    tree = panel._tree_widget
    tree.clearSelection()
    for r in rows:
        tree.topLevelItem(r).setSelected(True)
    before = tuple(
        tree.topLevelItem(r).data(0, Qt.ItemDataRole.UserRole) for r in sorted(rows)
    )
    clicked = rows[pick % len(rows)]
    pos = _right_press(tree, tree.topLevelItem(clicked))
    panel._on_context_menu_requested(pos)
    entries = _entries(shown_menus[-1])
    assert entries[COMPARE].data()[1] == before
    assert tuple(
        sorted(i.data(0, Qt.ItemDataRole.UserRole) for i in tree.selectedItems())
    ) == tuple(sorted(before))


# --- Selection regression tests (task 7.20, Req 8.16) ------------------------
def _click(tree, row, modifier=Qt.KeyboardModifier.NoModifier) -> None:
    item = tree.topLevelItem(row)
    pos = QPoint(10, tree.visualItemRect(item).center().y())
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, modifier, pos)


def _menu_for_selection(panel, shown_menus, rows):
    tree = panel._tree_widget
    tree.clearSelection()
    for r in rows:
        tree.topLevelItem(r).setSelected(True)
    pos = QPoint(5, tree.viewport().height() - 2)
    if rows:
        pos = QPoint(10, tree.visualItemRect(tree.topLevelItem(rows[0])).center().y())
    panel._on_context_menu_requested(pos)
    return _entries(shown_menus[-1])


def test_7_20_plain_click_selects_one_row_and_sets_current(panel):
    tree = panel._tree_widget
    emitted: list[str] = []
    panel.person_selected.connect(emitted.append)
    _click(tree, 1)
    assert _selected(tree) == ["person_2"]
    assert tree.currentItem() is tree.topLevelItem(1)
    assert emitted == ["person_2"]


def test_7_20_ctrl_click_adds_and_removes_row(panel):
    tree = panel._tree_widget
    ctrl = Qt.KeyboardModifier.ControlModifier
    _click(tree, 0)
    _click(tree, 2, ctrl)
    assert _selected(tree) == ["person_1", "person_3"]
    _click(tree, 2, ctrl)
    assert _selected(tree) == ["person_1"]


def test_7_20_shift_click_selects_contiguous_range(panel):
    tree = panel._tree_widget
    _click(tree, 0)
    _click(tree, 2, Qt.KeyboardModifier.ShiftModifier)
    assert _selected(tree) == ["person_1", "person_2", "person_3"]


@pytest.mark.parametrize(
    "rows, compare_on, mark_on",
    [([0, 1], True, True), ([0], True, False), ([0, 1, 2], False, False), ([], False, False)],
)
def test_7_20_menu_entry_enablement_by_selection_size(
    panel, shown_menus, rows, compare_on, mark_on
):
    entries = _menu_for_selection(panel, shown_menus, rows)
    assert entries[COMPARE].isEnabled() is compare_on
    assert entries[MARK].isEnabled() is mark_on


def test_7_20_right_click_inside_selection_opens_menu_with_both_ids(panel, shown_menus):
    tree = panel._tree_widget
    _select_two(tree)
    pos = _right_press(tree, tree.topLevelItem(0))
    assert _selected(tree) == ["person_1", "person_2"]
    panel._on_context_menu_requested(pos)
    assert _selected(tree) == ["person_1", "person_2"]
    assert _entries(shown_menus[-1])[COMPARE].data()[1] == ("person_1", "person_2")


def test_7_20_right_click_outside_selection_selects_only_that_row(panel, shown_menus):
    tree = panel._tree_widget
    _select_two(tree)
    pos = _right_press(tree, tree.topLevelItem(2))
    assert _selected(tree) == ["person_3"]
    panel._on_context_menu_requested(pos)
    assert _entries(shown_menus[-1])[COMPARE].data()[1] == ("person_3",)


def test_7_20_right_click_on_empty_space_disables_both_entries(panel, shown_menus):
    tree = panel._tree_widget
    _select_two(tree)
    pos = QPoint(5, tree.viewport().height() - 2)
    assert tree.itemAt(pos) is None
    QTest.mousePress(tree.viewport(), Qt.MouseButton.RightButton, pos=pos)
    panel._on_context_menu_requested(pos)
    entries = _entries(shown_menus[-1])
    assert set(entries) == {COMPARE, MARK}
    assert not any(a.isEnabled() for a in entries.values())


def test_7_20_ctrl_click_changing_current_item_still_navigates(panel):
    tree = panel._tree_widget
    emitted: list[str] = []
    _click(tree, 0)
    panel.person_selected.connect(emitted.append)
    _click(tree, 3, Qt.KeyboardModifier.ControlModifier)
    assert tree.currentItem() is tree.topLevelItem(3)
    assert emitted == ["person_4"]
