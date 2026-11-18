"""Person-list research click -> gateway -> Application -> ResearchOverview (task 9.13).

The click goes through the real ``ResearchColumnDelegate`` and
``PersonListPanel``; the gateway is either a recording fake or the real
``Application`` methods bound to a light stand-in, ending in a real
``ResearchOverview``.

**Validates: Requirements 17.6, 17.8, 17.16**
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import types
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from slaktbusken.app import Application
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import (
    ResearchAction,
    ResearchCase,
    ResearchEntityLink,
    ResearchHypothesis,
)
from slaktbusken.persistence.app_settings_io import AppSettings, AppSettingsService
from slaktbusken.ui import research_gateway
from slaktbusken.ui.person_list_panel import (
    _RESEARCH_COLUMN,
    _ROLE_RESEARCH_COLOR,
    PersonListPanel,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _Signal:
    def connect(self, fn) -> None:
        pass


class _FakeResearchGateway:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def show_research_for_entity(self, entity_type, entity_id, person_filter=None) -> None:
        self.calls.append((entity_type, entity_id, person_filter))


def _person(pid: str, given: str) -> Person:
    return Person(id=pid, sex="M", names=[Name(type="birth", given=given, surname="Test")])


def _data() -> ProjectData:
    data = ProjectData()
    data.persons = [_person("p1", "Anna"), _person("p2", "Bo")]
    link = ResearchEntityLink
    data.research_cases = [
        ResearchCase(id="c1", title="Annas ärende", status="open", primary_entity_ref=link("person", "p1")),
        ResearchCase(id="c2", title="Bos ärende", status="open", primary_entity_ref=link("person", "p2")),
        ResearchCase(id="c3", title="Annas stängda", status="closed", linked_entities=[link("person", "p1")]),
    ]
    data.research_actions = [
        ResearchAction(id="a1", research_case_id="c1"),
        ResearchAction(id="a2", research_case_id="c2"),
    ]
    data.research_hypotheses = [
        ResearchHypothesis(id="h1", research_case_id="c1"),
        ResearchHypothesis(id="h2", research_case_id="c2"),
    ]
    return data


def _make_panel(tmp_path, data: ProjectData) -> PersonListPanel:
    service = AppSettingsService()
    service.SETTINGS_PATH = tmp_path / "app_settings.json"
    service._settings = AppSettings()
    project_service = SimpleNamespace(
        data=data,
        project_path=None,
        add_merge_listener=lambda fn: (lambda: None),
    )
    app = SimpleNamespace(app_settings_service=service, project_service=project_service)
    return PersonListPanel(app)


def _click_research_glyph(panel: PersonListPanel, person_id: str) -> None:
    tree = panel._tree_widget
    item = next(
        tree.topLevelItem(r)
        for r in range(tree.topLevelItemCount())
        if tree.topLevelItem(r).data(0, Qt.ItemDataRole.UserRole) == person_id
    )
    item.setData(_RESEARCH_COLUMN, _ROLE_RESEARCH_COLOR, "#F39C12")
    item.setText(_RESEARCH_COLUMN, "1/2")
    option = QStyleOptionViewItem()
    option.initFrom(tree.viewport())
    option.rect = QRect(0, 0, 200, 24)
    index = tree.indexFromItem(item, _RESEARCH_COLUMN)
    research_rect, _ = panel._research_delegate._rects_for(option, index)
    pos = QPointF(research_rect.center())
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    assert panel._research_delegate.editorEvent(event, tree.model(), option, index)


def _application_like(data: ProjectData):
    """The real Application research methods bound to a light stand-in."""
    stub = SimpleNamespace(
        project_service=SimpleNamespace(project_path="x.slkt", data=data),
        main_window=None,
        research_changed=_Signal(),
        open_research_case=lambda *a, **k: None,
        _research_overview=None,
    )
    stub._forget_research_overview = lambda: setattr(stub, "_research_overview", None)
    for name in ("show_research_for_entity", "show_research_overview"):
        setattr(stub, name, types.MethodType(getattr(Application, name), stub))
    return stub


@pytest.fixture(autouse=True)
def _clean_gateway():
    yield
    research_gateway.set_research_gateway(None)


@pytest.fixture
def stub_app(qapp):
    stub = _application_like(_data())
    research_gateway.set_research_gateway(stub)
    yield stub
    if stub._research_overview is not None:
        stub._research_overview.close()


def test_click_reaches_gateway_with_person_filter(qapp, tmp_path) -> None:
    fake = _FakeResearchGateway()
    research_gateway.set_research_gateway(fake)
    panel = _make_panel(tmp_path, _data())
    panel.refresh()
    _click_research_glyph(panel, "p1")
    assert fake.calls == [("person", "p1", "p1")]


def test_click_opens_overview_filtered_to_person(qapp, tmp_path, stub_app) -> None:
    panel = _make_panel(tmp_path, _data())
    panel.refresh()
    _click_research_glyph(panel, "p1")

    window = stub_app._research_overview
    assert window is not None
    assert window.person_filter() == "p1"
    assert window.mode() == "cases"
    assert not window._banner.isHidden()
    assert "Anna" in window._banner_label.text() and "p1" in window._banner_label.text()
    assert {r.case_id for r in window.case_rows()} == {"c1", "c3"}
    assert {r.action_id for r in window.todo_rows()} == {"a1"}
    assert {r.hypothesis_id for r in window.hypothesis_rows()} == {"h1"}


def test_calls_without_person_filter_are_unchanged(qapp, stub_app) -> None:
    # Unfiltered overview: everything, no banner.
    stub_app.show_research_overview("todo")
    window = stub_app._research_overview
    assert window.person_filter() is None
    assert window._banner.isHidden()
    assert window.mode() == "todo"
    assert {r.action_id for r in window.todo_rows()} == {"a1", "a2"}
    assert {r.hypothesis_id for r in window.hypothesis_rows()} == {"h1", "h2"}

    # Entity call without person filter: entity filter only, no person filter.
    stub_app.show_research_for_entity("person", "p2")
    assert stub_app._research_overview is window
    assert window.person_filter() is None
    assert window._banner.isHidden()
    assert [r.case_id for r in window.case_rows()] == ["c2"]
    assert {r.action_id for r in window.todo_rows()} == {"a1", "a2"}


def test_later_call_without_filter_clears_person_filter(qapp, stub_app) -> None:
    stub_app.show_research_for_entity("person", "p1", person_filter="p1")
    window = stub_app._research_overview
    assert window.person_filter() == "p1"

    stub_app.show_research_overview("hypotheses")
    assert stub_app._research_overview is window
    assert window.person_filter() is None
    assert window._banner.isHidden()
    assert window.mode() == "hypotheses"
    assert {r.hypothesis_id for r in window.hypothesis_rows()} == {"h1", "h2"}
    assert {r.action_id for r in window.todo_rows()} == {"a1", "a2"}
