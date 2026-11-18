"""Offscreen tests for the merge history menu entries (task 20.8)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from slaktbusken.ui.context_menu_builder import (
    SHOW_HISTORY_ACTION,
    ContextMenuBuilder,
)

HISTORY = "Visa sammanslagningshistorik"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _entry(menu):
    found = [a for a in menu.actions() if a.text() == HISTORY]
    assert len(found) == 1
    return found[0]


@pytest.mark.parametrize(
    "ids, has_history, project_open, enabled",
    [
        (["p1"], True, True, True),
        (["p1"], False, True, False),
        (["p1", "p2"], True, True, False),
        (["p1"], True, False, False),
    ],
)
def test_history_entry_enablement(qapp, ids, has_history, project_open, enabled):
    menu = ContextMenuBuilder().build_person_menu(
        "p1", None, QWidget(), selected_ids=ids,
        project_open=project_open, has_history=has_history,
    )
    entry = _entry(menu)
    assert entry.isEnabled() is enabled
    assert entry.data() == (SHOW_HISTORY_ACTION, "p1")


def test_history_entry_absent_without_selection_info(qapp):
    menu = ContextMenuBuilder().build_person_menu("p1", None, QWidget())
    assert all(a.text() != HISTORY for a in menu.actions())


def test_main_menu_action_opens_history_for_all(qapp, monkeypatch):
    from types import SimpleNamespace
    from slaktbusken.ui import main_window as mw
    from slaktbusken.ui.merge import merge_gateway

    calls = []
    gateway = SimpleNamespace(open_history=lambda pid=None: calls.append(pid))
    monkeypatch.setattr(merge_gateway, "get_merge_gateway", lambda: gateway)
    mw.MainWindow._open_merge_history(SimpleNamespace())
    assert calls == [None]
