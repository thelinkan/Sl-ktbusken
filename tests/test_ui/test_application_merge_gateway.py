"""Offscreen tests for the Application merge gateway comparison methods."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QMainWindow

from slaktbusken.app import Application
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.project_service import ProjectService


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def app_like(qapp):
    svc = ProjectService()
    data = ProjectData()
    data.persons = [
        Person(id=f"person_{i}", sex="U", names=[Name(type="birth", given=g, surname="Test")])
        for i, g in enumerate(["Anna", "Bo", "Cia"], start=1)
    ]
    svc._project_data = data
    svc._project_path = Path("project.json.gz")
    main = QMainWindow()
    fake = SimpleNamespace(
        project_service=svc, main_window=main, editor_registry=None, _comparison_window=None,
        open_merge_review=lambda *_a: None,
    )
    fake._forget_comparison_window = lambda w: Application._forget_comparison_window(fake, w)
    yield fake
    for w in main.findChildren(QMainWindow):
        w.close()
    main.close()


def test_open_comparison_uses_main_window_and_ids(app_like):
    Application.open_comparison(app_like, "person_1", "person_2")
    window = app_like._comparison_window
    assert window is not None
    assert window.parent() is app_like.main_window
    assert window.slot_persons() == ("person_1", "person_2")


def test_open_comparison_reuses_window_for_same_pair(app_like):
    Application.open_comparison(app_like, "person_1", "person_2")
    first = app_like._comparison_window
    Application.open_comparison(app_like, "person_2", "person_1")
    Application.open_comparison(app_like)
    assert app_like._comparison_window is first


def test_open_comparison_opens_new_window_for_other_pair(app_like):
    Application.open_comparison(app_like, "person_1", "person_2")
    first = app_like._comparison_window
    Application.open_comparison(app_like, "person_1", "person_3")
    assert app_like._comparison_window is not first
    assert app_like._comparison_window.slot_persons() == ("person_1", "person_3")


def test_open_comparison_without_ids_opens_empty_window(app_like):
    Application.open_comparison(app_like)
    assert app_like._comparison_window.slot_persons() == (None, None)


def test_mark_candidates_creates_candidate_and_opens_it(app_like):
    opened: list[str] = []
    app_like._update_status = lambda: None
    app_like.open_candidate = opened.append
    Application.mark_candidates(app_like, "person_1", "person_2")
    assert len(app_like.project_service.data.merge_candidates) == 1
    assert opened == [app_like.project_service.data.merge_candidates[0].id]
