"""Offscreen tests for Application history, show_person and retired-id redirects."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from slaktbusken.app import Application
from slaktbusken.model.merge_candidate import MergeHistoryEntry
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge.merge_gateway import MergeGateway


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def fake(qapp, monkeypatch):
    svc = ProjectService()
    data = ProjectData()
    data.persons = [
        Person(id="person_1", sex="U", names=[Name(type="birth", given="Anna", surname="Berg")]),
        Person(id="person_2", sex="U", names=[Name(type="birth", given="Bo", surname="Berg")]),
    ]
    data.merge_history = [
        MergeHistoryEntry("merge_1", "person_1", "gone_1", "Åsa Berg", "", "2020-01-01"),
        MergeHistoryEntry("merge_2", "person_missing", "gone_2", "Cia Berg", "", "2020-01-02"),
    ]
    svc._project_data = data
    svc._project_path = Path("project.json.gz")
    main = QMainWindow()
    selected: list[str] = []
    panel = SimpleNamespace(select_person_from_diagram=selected.append)
    main.person_list_panel = panel
    ns = SimpleNamespace(project_service=svc, main_window=main, selected=selected, edited=[])
    ns._resolve_person_request = lambda pid: Application._resolve_person_request(ns, pid)
    ns.open_person_editor = ns.edited.append
    ns.messages = []
    monkeypatch.setattr(
        QMessageBox, "information", lambda *a, **k: ns.messages.append(a[2])
    )
    yield ns
    main.close()


def test_application_implements_gateway_protocol():
    for name in ("open_history", "show_person", "open_register"):
        assert callable(getattr(Application, name))
    for name in ("open_history", "show_person", "open_register"):
        assert hasattr(MergeGateway, name)


def test_show_person_active_selects_and_opens(fake):
    Application.show_person(fake, "person_2")
    assert fake.selected == ["person_2"]
    assert fake.edited == ["person_2"]
    assert fake.messages == []


def test_show_person_retired_redirects_with_message(fake):
    Application.show_person(fake, "gone_1")
    assert fake.edited == ["person_1"]
    assert fake.main_window.statusBar().currentMessage() == (
        "Personen gone_1 slogs samman med Anna Berg."
    )


def test_show_person_unresolved_opens_nothing_and_names_id(fake):
    Application.show_person(fake, "gone_2")
    assert fake.edited == [] and fake.selected == []
    assert "gone_2" in fake.messages[0]
    Application.show_person(fake, "nobody")
    assert "nobody" in fake.messages[1]


def test_open_history_without_project_shows_message(fake):
    fake.project_service._project_path = None
    Application.open_history(fake)
    assert fake.main_window.statusBar().currentMessage() == "Inget projekt är öppet."


def test_open_history_opens_scoped_window(fake):
    Application.open_history(fake, "person_1")
    windows = [
        w for w in QApplication.topLevelWidgets()
        if type(w).__name__ == "MergeHistoryWindow" and w.isVisible()
    ]
    try:
        assert windows
    finally:
        for w in windows:
            w.close()
