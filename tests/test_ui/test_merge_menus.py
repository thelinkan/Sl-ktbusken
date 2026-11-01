"""Offscreen tests for the comparison and candidate menu entry points (7.7)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from slaktbusken.app import Application
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.context_menu_builder import (
    COMPARE_ACTION,
    MARK_CANDIDATES_ACTION,
    ContextMenuBuilder,
    merge_action_ids,
)
from slaktbusken.ui.diagram_panel import DiagramPanel
from slaktbusken.ui.person_list_panel import PersonListPanel

COMPARE = "Jämför personer..."
MARK = "Markera som sammanslagningskandidater"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _entries(menu):
    return {a.text(): a for a in menu.actions() if a.text() in (COMPARE, MARK)}


@pytest.mark.parametrize(
    "count, compare, mark",
    [(0, False, False), (1, True, False), (2, True, True), (3, False, False)],
)
def test_context_menu_enablement_by_selection_size(qapp, count, compare, mark):
    ids = [f"person_{i}" for i in range(1, count + 1)]
    menu = ContextMenuBuilder().build_person_menu(
        "person_1", None, QWidget(), selected_ids=ids
    )
    entries = _entries(menu)
    assert set(entries) == {COMPARE, MARK}
    assert entries[COMPARE].isEnabled() is compare
    assert entries[MARK].isEnabled() is mark
    assert merge_action_ids(entries[COMPARE]) == (COMPARE_ACTION, ids)
    assert merge_action_ids(entries[MARK]) == (MARK_CANDIDATES_ACTION, ids)


def test_context_menu_entries_disabled_without_project(qapp):
    menu = ContextMenuBuilder().build_person_menu(
        "person_1",
        None,
        QWidget(),
        selected_ids=["person_1", "person_2"],
        project_open=False,
    )
    assert not any(a.isEnabled() for a in _entries(menu).values())


def test_no_merge_command_in_menu(qapp):
    menu = ContextMenuBuilder().build_person_menu(
        "person_1", None, QWidget(), selected_ids=["person_1", "person_2"]
    )
    labels = " ".join(a.text().lower() for a in menu.actions())
    assert "slå ihop" not in labels
    assert "merge" not in labels
    assert "sammanslag" in labels  # only the candidate marking entry


def test_panels_expose_ordered_id_signals():
    for cls in (DiagramPanel, PersonListPanel):
        assert hasattr(cls, "compare_requested")
        assert hasattr(cls, "mark_candidates_requested")


@pytest.fixture
def gateway_app(qapp):
    svc = ProjectService()
    svc._project_path = Path("project.json.gz")
    fake = SimpleNamespace(project_service=svc, calls=[])
    fake.open_comparison = lambda *a: fake.calls.append(("compare", a))
    fake.mark_candidates = lambda *a: fake.calls.append(("mark", a))
    return fake


def test_compare_routes_to_gateway(gateway_app):
    Application._on_compare_requested(gateway_app, ["person_1", "person_2"])
    Application._on_compare_requested(gateway_app, ["person_3"])
    assert gateway_app.calls == [
        ("compare", ("person_1", "person_2")),
        ("compare", ("person_3", "")),
    ]


def test_mark_candidates_routes_only_for_two_ids(gateway_app):
    Application._on_mark_candidates_requested(gateway_app, ["person_1", "person_2"])
    Application._on_mark_candidates_requested(gateway_app, ["person_1"])
    Application._on_mark_candidates_requested(gateway_app, ["a", "b", "c"])
    assert gateway_app.calls == [("mark", ("person_1", "person_2"))]


def test_routing_ignored_without_project(gateway_app):
    gateway_app.project_service._project_path = None
    Application._on_compare_requested(gateway_app, ["person_1"])
    Application._on_mark_candidates_requested(gateway_app, ["person_1", "person_2"])
    assert gateway_app.calls == []


def test_person_menu_entry_opens_empty_comparison_and_follows_project(qapp):
    from slaktbusken.ui.main_window import MainWindow

    app_mock = MagicMock()
    window = MainWindow(app_mock)
    try:
        action = window.action_compare_persons
        assert action in window.menu_person.actions()
        assert action.text() == "&Jämför personer..."
        window._update_project_actions(False)
        assert not action.isEnabled()
        window._update_project_actions(True)
        assert action.isEnabled()
        action.trigger()
        app_mock.open_comparison.assert_called_once_with()
        # No merge command is added to the Person menu.
        assert not any(
            "slå ihop" in a.text().lower() for a in window.menu_person.actions()
        )
    finally:
        window.close()
