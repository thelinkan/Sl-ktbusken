"""Consolidated widget tests: every history entry point reaches the same window (task 20.15).

Each entry point is driven through its real widget and ends in a gateway that
runs the real ``Application.open_history`` on a real ``ProjectService``. The
assertions look at the resulting ``MergeHistoryWindow`` (scope, rows, reuse).

Requirements: 36.10, 36.11, 36.12, 36.15.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QEvent, QObject, QPointF, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsSceneMouseEvent,
    QMainWindow,
    QMessageBox,
    QStyleOptionViewItem,
    QWidget,
)

from slaktbusken.app import Application
from slaktbusken.model.merge_candidate import MergeHistoryEntry
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.app_settings_io import AppSettings, AppSettingsService
from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.context_menu_builder import ContextMenuBuilder
from slaktbusken.ui.merge import merge_gateway, recovery_dialogs
from slaktbusken.ui.merge.candidate_register_window import CandidateRegisterWindow
from slaktbusken.ui.merge.candidate_section import CandidatesSection
from slaktbusken.ui.merge import merge_history_window as history_module
from slaktbusken.ui.merge.merge_history_window import MergeHistoryWindow
from slaktbusken.ui.merge.person_comparison_window import PersonComparisonWindow
from slaktbusken.ui.person_list_panel import _RESEARCH_COLUMN, PersonListPanel
from slaktbusken.ui.widgets import person_box as pb
from slaktbusken.ui.widgets import research_marker as rm

FALLBACK_TEXT = "Sammanslagningshistoriken är inte tillgänglig."
HISTORY_MENU_TEXT = "Visa sammanslagningshistorik"
EMPTY_TEXT = "Inga sammanslagningar finns."


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# Environment: a real service and a gateway running the real Application code
# ---------------------------------------------------------------------------


class AppGateway(QObject):
    """Gateway whose ``open_history`` is the real ``Application.open_history``."""

    merge_changed = Signal()

    def __init__(self, service: ProjectService, main_window: QMainWindow) -> None:
        super().__init__()
        self.project_service = service
        self.main_window = main_window
        self.history_calls: list = []
        real = Application.open_history
        self.open_history = lambda person_id=None: (
            self.history_calls.append(person_id),
            real(self, person_id),
        )[1]


def _person(pid: str, given: str) -> Person:
    return Person(id=pid, sex="U", names=[Name(type="birth", given=given, surname="Berg")])


def _data() -> ProjectData:
    data = ProjectData()
    data.persons = [_person("person_1", "Anna"), _person("person_2", "Bo"), _person("person_3", "Cia")]
    data.merge_history = [
        MergeHistoryEntry("merge_1", "person_1", "gone_1", "Åsa Berg", "1800–1870", "2020-01-01"),
        MergeHistoryEntry("merge_2", "person_3", "gone_2", "Dan Berg", "1810–1880", "2020-01-02"),
        MergeHistoryEntry("merge_3", "person_1", "gone_3", "Eva Berg", "1820–1890", "2020-01-03"),
    ]
    return data


class Env(SimpleNamespace):
    pass


@pytest.fixture
def env(qapp, monkeypatch):
    svc = ProjectService()
    svc._project_data = _data()
    svc._project_path = Path("project.json.gz")
    main = QMainWindow()
    gateway = AppGateway(svc, main)
    merge_gateway.set_merge_gateway(gateway)
    messages: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: messages.append(str(a[2])))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: messages.append(str(a[2])))
    yield Env(service=svc, main=main, gateway=gateway, messages=messages)
    merge_gateway.set_merge_gateway(None)
    for window in _open_windows():
        window.close()
    main.close()
    rm.begin_diagram_render(ProjectData(), True, False)


def _open_windows() -> list[MergeHistoryWindow]:
    found = []
    for ref in list(history_module._windows.values()):
        widget = ref()
        try:
            if widget is not None and widget.isVisible():
                found.append(widget)
        except RuntimeError:  # deleted C++ object
            continue
    return found


def _only_window(env, person_id, rows) -> MergeHistoryWindow:
    """Exactly one history window is open, with the given scope and row count."""
    windows = _open_windows()
    assert len(windows) == 1, windows
    window = windows[0]
    assert window.person_id == person_id
    assert window.row_count() == rows
    # No entry point shows the old fallback text anywhere.
    assert FALLBACK_TEXT not in env.messages
    assert FALLBACK_TEXT not in env.main.statusBar().currentMessage()
    return window


def _assert_nothing_opened(env) -> None:
    assert _open_windows() == []
    assert not any(FALLBACK_TEXT in m for m in env.messages)
    assert FALLBACK_TEXT not in env.main.statusBar().currentMessage()


# ---------------------------------------------------------------------------
# Person editor block (36.10)
# ---------------------------------------------------------------------------


def _section(env, pid="person_1") -> CandidatesSection:
    return CandidatesSection(env.service.data, lambda: pid)


def test_editor_block_button_opens_scoped_window(env):
    section = _section(env)
    section.show()
    block = section._history_block
    assert block._button.text() == HISTORY_MENU_TEXT
    assert len(block.row_texts()) == 2
    assert not block._empty_label.isVisible()
    block._button.click()
    _only_window(env, "person_1", 2)
    assert env.gateway.history_calls == ["person_1"]


def test_editor_block_empty_state_still_scoped(env):
    section = _section(env, "person_2")
    section.show()
    block = section._history_block
    assert block._empty_label.isVisible() and block._empty_label.text() == EMPTY_TEXT
    assert block.row_texts() == []
    block._button.click()
    window = _only_window(env, "person_2", 0)
    assert window.isVisible()


def test_editor_block_hidden_for_unsaved_person(env):
    section = _section(env, "")
    section.show()
    assert not section._history_block.isVisible()


# ---------------------------------------------------------------------------
# Person list: context menu entry and grey indicator
# ---------------------------------------------------------------------------


def _panel(tmp_path, env) -> PersonListPanel:
    settings = AppSettingsService()
    settings.SETTINGS_PATH = tmp_path / "app_settings.json"
    settings._settings = AppSettings()
    app = SimpleNamespace(app_settings_service=settings, project_service=env.service)
    panel = PersonListPanel(app)
    panel.refresh()
    return panel


def _item(panel, pid):
    tree = panel._tree_widget
    for row in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(row)
        if item.data(0, Qt.ItemDataRole.UserRole) == pid:
            return item
    raise AssertionError(pid)


def _right_click_menu(panel, pid):
    """Open the person context menu for ``pid``; return the captured menu."""
    captured = {}

    def fake_exec(menu, global_pos):
        captured["menu"] = menu
        entries = [a for a in menu.actions() if a.text() == HISTORY_MENU_TEXT]
        captured["entry"] = entries[0]
        return entries[0] if entries and entries[0].isEnabled() else None

    panel._exec_menu = fake_exec  # stubbed before any press, so no modal menu is shown
    panel._tree_widget.setCurrentItem(_item(panel, pid))
    panel._on_context_menu_requested(panel._tree_widget.visualItemRect(_item(panel, pid)).center(), keyboard=True)
    return captured


def test_context_menu_entry_opens_scoped_window(qapp, env, tmp_path):
    panel = _panel(tmp_path, env)
    captured = _right_click_menu(panel, "person_1")
    assert captured["entry"].isEnabled()
    _only_window(env, "person_1", 2)
    assert env.gateway.history_calls == ["person_1"]


def test_context_menu_entry_disabled_without_history(qapp, env, tmp_path):
    panel = _panel(tmp_path, env)
    captured = _right_click_menu(panel, "person_2")
    assert not captured["entry"].isEnabled()
    _assert_nothing_opened(env)
    assert env.gateway.history_calls == []


def test_context_menu_entry_disabled_without_project(qapp, env, tmp_path):
    panel = _panel(tmp_path, env)
    env.service._project_path = None
    captured = _right_click_menu(panel, "person_1")
    assert not captured["entry"].isEnabled()
    _assert_nothing_opened(env)


def test_context_menu_entry_disabled_for_multi_selection(qapp):
    menu = ContextMenuBuilder().build_person_menu(
        "p1", None, QWidget(), selected_ids=["p1", "p2"], project_open=True, has_history=True
    )
    entry = [a for a in menu.actions() if a.text() == HISTORY_MENU_TEXT][0]
    assert not entry.isEnabled()


def _release(pos) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(pos),
        QPointF(pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _click_list_indicator(panel, pid) -> bool:
    delegate = panel._research_delegate
    option = QStyleOptionViewItem()
    option.initFrom(panel._tree_widget.viewport())
    from PySide6.QtCore import QRect

    option.rect = QRect(0, 0, 200, 24)
    index = panel._tree_widget.indexFromItem(_item(panel, pid), _RESEARCH_COLUMN)
    _, candidate_rect = delegate._rects_for(option, index)
    if candidate_rect.isNull():
        return False
    return delegate.editorEvent(_release(candidate_rect.center()), panel._tree_widget.model(), option, index)


def test_person_list_grey_indicator_opens_scoped_window(qapp, env, tmp_path):
    panel = _panel(tmp_path, env)
    assert _click_list_indicator(panel, "person_1")
    _only_window(env, "person_1", 2)
    assert env.gateway.history_calls == ["person_1"]


def test_person_list_has_no_indicator_without_history(qapp, env, tmp_path):
    panel = _panel(tmp_path, env)
    assert not _click_list_indicator(panel, "person_2")
    _assert_nothing_opened(env)


# ---------------------------------------------------------------------------
# Diagram box indicator
# ---------------------------------------------------------------------------


def _box(pid):
    display = {"name": pid, "candidate_state": rm.diagram_candidate_state(pid)}
    return pb.PersonBoxItem(pid, display, PersonBoxConfig(merge_candidates=True))


def _press(item, pos) -> None:
    event = QGraphicsSceneMouseEvent(QGraphicsSceneMouseEvent.Type.GraphicsSceneMousePress)
    event.setButton(Qt.MouseButton.LeftButton)
    event.setPos(pos)
    item.mousePressEvent(event)


def test_diagram_box_grey_indicator_opens_scoped_window(qapp, env):
    rm.begin_diagram_render(env.service.data, True, True)
    state = rm.diagram_candidate_state("person_3")
    assert state["kind"] == "history"
    box = _box("person_3")
    _press(box, box._candidate_indicator()[0].center())
    _only_window(env, "person_3", 1)
    assert env.gateway.history_calls == ["person_3"]


def test_diagram_box_has_no_indicator_without_history(qapp, env):
    rm.begin_diagram_render(env.service.data, True, True)
    assert rm.diagram_candidate_state("person_2") is None
    assert _box("person_2")._candidate_indicator() is None


# ---------------------------------------------------------------------------
# Main / research menu
# ---------------------------------------------------------------------------


def test_main_menu_item_opens_all_entries(qapp, env):
    from slaktbusken.ui.main_window import MainWindow

    window = MainWindow(MagicMock())
    try:
        env.gateway.main_window = window
        window._update_project_actions(True)
        actions = window.menu_research.actions()
        action = window.action_research_history
        assert action.text().replace("&", "") == "Sammanslagningshistorik"
        assert action in actions
        # Directly after the candidates entry.
        assert actions.index(action) == actions.index(window.action_research_candidates) + 1
        assert action.isEnabled()
        action.trigger()
        _only_window_for(env, window, None, 3)
        assert env.gateway.history_calls == [None]
    finally:
        for w in _open_windows():
            w.close()
        window.close()


def _only_window_for(env, main, person_id, rows) -> None:
    windows = _open_windows()
    assert len(windows) == 1
    assert windows[0].person_id == person_id and windows[0].row_count() == rows
    assert FALLBACK_TEXT not in main.statusBar().currentMessage()


def test_main_menu_item_disabled_without_project_and_opens_nothing(qapp, env):
    from slaktbusken.ui.main_window import MainWindow

    window = MainWindow(MagicMock())
    try:
        env.gateway.main_window = window
        window._update_project_actions(False)
        assert not window.action_research_history.isEnabled()
        # Even when triggered programmatically the application opens no window.
        env.service._project_path = None
        window._open_merge_history()
        assert _open_windows() == []
        assert window.statusBar().currentMessage() == "Inget projekt är öppet."
    finally:
        window.close()


# ---------------------------------------------------------------------------
# Candidate register button
# ---------------------------------------------------------------------------


def test_register_button_all_entries_without_filter(qapp, env):
    win = CandidateRegisterWindow(env.service)
    try:
        win._history_button.click()
        _only_window(env, None, 3)
        assert env.gateway.history_calls == [None]
    finally:
        win.close()


def test_register_button_scoped_to_filtered_person(qapp, env):
    env.service.add_merge_candidate("person_1", "person_2")
    win = CandidateRegisterWindow(env.service)
    try:
        win.set_person_filter("person_1")
        win._history_button.click()
        _only_window(env, "person_1", 2)
        assert env.gateway.history_calls == ["person_1"]
    finally:
        win.close()


# ---------------------------------------------------------------------------
# Comparison window slot buttons (36.15)
# ---------------------------------------------------------------------------


def test_comparison_slot_buttons_visible_only_with_history(qapp, env):
    win = PersonComparisonWindow(env.service, "person_1", "person_2")
    try:
        win.show()
        first, second = win.history_buttons
        assert first.isVisible() and first.isEnabled()
        assert first.text() == "Sammanslagningshistorik"
        assert not second.isVisible()
        first.click()
        _only_window(env, "person_1", 2)
    finally:
        win.close()


def test_comparison_second_slot_scoped_to_its_person(qapp, env):
    win = PersonComparisonWindow(env.service, "person_2", "person_3")
    try:
        win.show()
        first, second = win.history_buttons
        assert not first.isVisible() and second.isVisible()
        second.click()
        _only_window(env, "person_3", 1)
        assert env.gateway.history_calls == ["person_3"]
    finally:
        win.close()


def test_comparison_without_history_has_no_visible_button(qapp, env):
    env.service.data.merge_history.clear()
    win = PersonComparisonWindow(env.service, "person_1", "person_2")
    try:
        win.show()
        assert not any(b.isVisible() for b in win.history_buttons)
    finally:
        win.close()


# ---------------------------------------------------------------------------
# Post-merge success box
# ---------------------------------------------------------------------------


def _run_after_merge(env, click_text, survivor="person_1"):
    def fake_exec(box):
        for button in box.buttons():
            if button.text() == click_text:
                button.click()
                return 0
        raise AssertionError([b.text() for b in box.buttons()])

    ns = SimpleNamespace(
        project_service=env.service,
        main_window=env.main,
        _update_status=lambda: None,
        _update_diagram_panel=lambda: None,
    )
    ns.open_history = lambda pid=None: Application.open_history(ns, pid)
    wizard = SimpleNamespace(
        executed=True,
        last_result=SimpleNamespace(message="Klart.", recovery_message="", survivor_id=survivor),
    )
    original = QMessageBox.exec
    QMessageBox.exec = fake_exec
    try:
        Application._after_merge_review(ns, wizard, env.main)
    finally:
        QMessageBox.exec = original


def test_success_box_button_opens_window_for_survivor(qapp, env):
    _run_after_merge(env, recovery_dialogs.SHOW_HISTORY_TEXT)
    _only_window(env, "person_1", 2)


def test_success_box_close_button_opens_nothing(qapp, env):
    _run_after_merge(env, recovery_dialogs.CLOSE_TEXT)
    _assert_nothing_opened(env)


# ---------------------------------------------------------------------------
# Cross entry point behaviour
# ---------------------------------------------------------------------------


def test_all_entry_points_share_one_window_per_scope(qapp, env, tmp_path):
    rm.begin_diagram_render(env.service.data, True, True)
    panel = _panel(tmp_path, env)
    section = _section(env)
    win = CandidateRegisterWindow(env.service)
    try:
        section._history_block._button.click()
        first = _only_window(env, "person_1", 2)

        _click_list_indicator(panel, "person_1")
        box = _box("person_1")
        _press(box, box._candidate_indicator()[0].center())
        _right_click_menu(panel, "person_1")
        _run_after_merge(env, recovery_dialogs.SHOW_HISTORY_TEXT)
        section._history_block._button.click()
        assert _open_windows() == [first]
        # editor x2, list indicator, diagram box, context menu (the success box
        # calls Application.open_history directly, not through the gateway).
        assert len(env.gateway.history_calls) == 5

        # The all-entries scope is a different window, also shared.
        win._history_button.click()
        env.main.show()
        env.gateway.open_history(None)
        windows = _open_windows()
        assert len(windows) == 2
        scopes = {w.person_id: w for w in windows}
        assert set(scopes) == {"person_1", None}
        assert scopes[None].row_count() == 3 and scopes["person_1"] is first
    finally:
        win.close()


def test_application_open_history_never_shows_fallback_text(qapp, env):
    env.gateway.open_history("person_1")
    env.service._project_path = None
    for window in _open_windows():
        window.close()
    env.gateway.open_history("person_1")
    assert env.main.statusBar().currentMessage() == "Inget projekt är öppet."
    assert FALLBACK_TEXT not in env.messages
    assert _open_windows() == []


def test_entry_points_do_nothing_without_gateway(qapp, env, tmp_path):
    merge_gateway.set_merge_gateway(None)
    _section(env)._history_block._button.click()
    win = CandidateRegisterWindow(env.service)
    try:
        win._history_button.click()
    finally:
        win.close()
    assert _click_list_indicator(_panel(tmp_path, env), "person_1") in (True, False)
    rm.begin_diagram_render(env.service.data, True, True)
    box = _box("person_1")
    _press(box, box._candidate_indicator()[0].center())
    _assert_nothing_opened(env)
