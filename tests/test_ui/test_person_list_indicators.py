"""Person list research column: research glyph and candidate indicator (task 9.4)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QMenu, QStyleOptionViewItem

from slaktbusken.model.merge_candidate import MergeCandidate, MergeHistoryEntry
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.app_settings_io import AppSettings, AppSettingsService
from slaktbusken.persistence.settings_io import PersonListConfig
from slaktbusken.ui.merge import merge_gateway
from slaktbusken.ui import research_gateway
from slaktbusken.ui.person_list_panel import (
    _RESEARCH_COLUMN,
    _ROLE_CANDIDATE_COLOUR,
    _ROLE_CANDIDATE_KIND,
    _ROLE_CELL_PERSON_ID,
    _ROLE_RESEARCH_COLOR,
    PersonListPanel,
    ResearchColumnDelegate,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _Signal:
    def __init__(self) -> None:
        self._slots = []

    def connect(self, slot) -> None:
        self._slots.append(slot)

    def emit(self) -> None:
        for slot in list(self._slots):
            slot()


class _FakeMergeGateway:
    def __init__(self) -> None:
        self.merge_changed = _Signal()
        self.calls: list[tuple] = []

    def open_register(self, person_id=None) -> None:
        self.calls.append(("register", person_id))

    def open_history(self, person_id=None) -> None:
        self.calls.append(("history", person_id))


class _FakeResearchGateway:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def show_research_for_entity(self, entity_type, entity_id, person_filter=None) -> None:
        self.calls.append((entity_type, entity_id, person_filter))


def _person(pid: str, given: str) -> Person:
    return Person(id=pid, sex="M", names=[Name(type="birth", given=given, surname="Test")])


def _make_panel(tmp_path, data: ProjectData):
    service = AppSettingsService()
    service.SETTINGS_PATH = tmp_path / "app_settings.json"
    service._settings = AppSettings()
    listeners: list = []
    project_service = SimpleNamespace(
        data=data,
        project_path=None,
        add_merge_listener=lambda fn: (listeners.append(fn), lambda: listeners.remove(fn))[1],
    )
    app = SimpleNamespace(app_settings_service=service, project_service=project_service)
    panel = PersonListPanel(app)
    return panel, listeners


def _data() -> ProjectData:
    data = ProjectData()
    data.persons = [_person("p1", "Anna"), _person("p2", "Bo"), _person("p3", "Cecilia")]
    data.merge_candidates = [
        MergeCandidate(id="c1", person_1_id="p1", person_2_id="p3", assessment="confirmed")
    ]
    data.merge_history = [
        MergeHistoryEntry(
            id="h1",
            surviving_person_id="p2",
            merged_person_id="gone",
            merged_person_name="Gammal",
            merged_person_lifespan="1800–1850",
            merge_date="2024-01-01",
        )
    ]
    return data


def _item_for(panel: PersonListPanel, person_id: str):
    tree = panel._tree_widget
    for row in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(row)
        if item.data(0, Qt.ItemDataRole.UserRole) == person_id:
            return item
    raise AssertionError(person_id)


def _release(pos: QPoint) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(pos),
        QPointF(pos),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _option(panel: PersonListPanel) -> QStyleOptionViewItem:
    option = QStyleOptionViewItem()
    option.initFrom(panel._tree_widget.viewport())
    option.rect = QRect(0, 0, 200, 24)
    return option


@pytest.fixture(autouse=True)
def _clean_gateways():
    yield
    merge_gateway.set_merge_gateway(None)
    research_gateway.set_research_gateway(None)


def test_header_text_and_column_count(qapp, tmp_path) -> None:
    panel, _ = _make_panel(tmp_path, _data())
    tree = panel._tree_widget
    assert tree.columnCount() == 11
    assert tree.headerItem().text(_RESEARCH_COLUMN) == "Forskningsuppslag"
    assert PersonListPanel._FULL_HEADERS[10] == "Forskningsuppslag"


def test_header_context_menu_toggle_label(qapp, tmp_path, monkeypatch) -> None:
    panel, _ = _make_panel(tmp_path, _data())
    captured: list[str] = []

    class _CapturingMenu(QMenu):
        def exec(self, *args, **kwargs):  # noqa: A003 - mirrors QMenu.exec
            captured.extend(a.text() for a in self.actions())
            return None

    import slaktbusken.ui.person_list_panel as module

    monkeypatch.setattr(module, "QMenu", _CapturingMenu)
    panel._show_column_visibility_menu(QPoint(0, 0))
    assert "Forskningsuppslag och dubletter" in captured
    assert "Forskningsärenden" not in captured


def test_colour_mapping_through_delegate_data(qapp, tmp_path) -> None:
    panel, _ = _make_panel(tmp_path, _data())
    panel.refresh()
    p1 = _item_for(panel, "p1")
    p2 = _item_for(panel, "p2")
    p3 = _item_for(panel, "p3")
    assert p1.data(_RESEARCH_COLUMN, _ROLE_CANDIDATE_COLOUR) == "blue"
    assert p1.data(_RESEARCH_COLUMN, _ROLE_CANDIDATE_KIND) == "candidates"
    assert p3.data(_RESEARCH_COLUMN, _ROLE_CANDIDATE_COLOUR) == "blue"
    assert p2.data(_RESEARCH_COLUMN, _ROLE_CANDIDATE_COLOUR) == "grey"
    assert p2.data(_RESEARCH_COLUMN, _ROLE_CANDIDATE_KIND) == "history"

    data = ProjectData()
    data.persons = [_person("q1", "Dan")]
    panel2, _ = _make_panel(tmp_path, data)
    panel2.refresh()
    assert _item_for(panel2, "q1").data(_RESEARCH_COLUMN, _ROLE_CANDIDATE_COLOUR) is None


def test_hit_rectangles_never_overlap() -> None:
    for width in (60, 90, 110, 200, 400):
        for text_width in (0, 20, 60):
            cell = QRect(0, 0, width, 24)
            research, candidate = ResearchColumnDelegate.hit_rectangles(
                cell, text_width, True, True
            )
            assert not research.isNull() or width < 40
            if not research.isNull() and not candidate.isNull():
                assert not research.intersects(candidate)
                assert research.left() < candidate.left()
            for rect in (research, candidate):
                if not rect.isNull():
                    assert cell.contains(rect)


def test_missing_indicator_has_no_rectangle() -> None:
    cell = QRect(0, 0, 200, 24)
    research, candidate = ResearchColumnDelegate.hit_rectangles(cell, 20, True, False)
    assert candidate.isNull() and not research.isNull()
    research, candidate = ResearchColumnDelegate.hit_rectangles(cell, 20, False, True)
    assert research.isNull() and not candidate.isNull()


def _row_with_both(panel):
    item = _item_for(panel, "p1")
    item.setData(_RESEARCH_COLUMN, _ROLE_RESEARCH_COLOR, "#F39C12")
    item.setText(_RESEARCH_COLUMN, "1/2")
    return item


def test_click_routing_with_fake_gateways(qapp, tmp_path) -> None:
    panel, _ = _make_panel(tmp_path, _data())
    panel.refresh()
    merge = _FakeMergeGateway()
    research = _FakeResearchGateway()
    merge_gateway.set_merge_gateway(merge)
    research_gateway.set_research_gateway(research)

    item = _row_with_both(panel)
    delegate = panel._research_delegate
    option = _option(panel)
    index = panel._tree_widget.indexFromItem(item, _RESEARCH_COLUMN)
    research_rect, candidate_rect = delegate._rects_for(option, index)
    assert not research_rect.isNull() and not candidate_rect.isNull()

    # Click on the research glyph: only the research gateway is called.
    assert delegate.editorEvent(_release(research_rect.center()), panel._tree_widget.model(), option, index)
    assert research.calls == [("person", "p1", "p1")]
    assert merge.calls == []

    # Click on the candidate indicator: only the merge gateway is called.
    assert delegate.editorEvent(_release(candidate_rect.center()), panel._tree_widget.model(), option, index)
    assert merge.calls == [("register", "p1")]
    assert research.calls == [("person", "p1", "p1")]

    # Click elsewhere in the cell reaches neither.
    gap = QPoint(research_rect.right() + 2, research_rect.center().y())
    assert not candidate_rect.contains(gap) and not research_rect.contains(gap)
    delegate.editorEvent(_release(gap), panel._tree_widget.model(), option, index)
    assert len(research.calls) == 1 and len(merge.calls) == 1


def test_history_only_indicator_opens_history(qapp, tmp_path) -> None:
    panel, _ = _make_panel(tmp_path, _data())
    panel.refresh()
    merge = _FakeMergeGateway()
    merge_gateway.set_merge_gateway(merge)
    item = _item_for(panel, "p2")
    delegate = panel._research_delegate
    option = _option(panel)
    index = panel._tree_widget.indexFromItem(item, _RESEARCH_COLUMN)
    _, candidate_rect = delegate._rects_for(option, index)
    assert delegate.editorEvent(_release(candidate_rect.center()), panel._tree_widget.model(), option, index)
    assert merge.calls == [("history", "p2")]


def test_disabled_setting_hides_indicators(qapp, tmp_path) -> None:
    panel, _ = _make_panel(tmp_path, _data())
    panel.apply_person_list_config(PersonListConfig(research=False))
    panel.refresh()
    item = _item_for(panel, "p1")
    assert item.text(_RESEARCH_COLUMN) == ""
    delegate = panel._research_delegate
    index = panel._tree_widget.indexFromItem(item, _RESEARCH_COLUMN)
    assert delegate._rects_for(_option(panel), index) == (QRect(), QRect())
    assert not delegate.is_enabled()


def test_merge_change_refreshes_rows_in_place(qapp, tmp_path) -> None:
    data = _data()
    panel, listeners = _make_panel(tmp_path, data)
    panel.refresh()
    assert len(listeners) == 1
    first_item = _item_for(panel, "p3")
    assert first_item.data(_RESEARCH_COLUMN, _ROLE_CANDIDATE_COLOUR) == "blue"

    data.merge_candidates[0].assessment = "rejected"
    for listener in listeners:
        listener()

    # The same item object is updated: the list was not rebuilt.
    assert _item_for(panel, "p3") is first_item
    assert first_item.data(_RESEARCH_COLUMN, _ROLE_CANDIDATE_COLOUR) == "grey"
    assert first_item.data(_RESEARCH_COLUMN, _ROLE_CELL_PERSON_ID) == "p3"
