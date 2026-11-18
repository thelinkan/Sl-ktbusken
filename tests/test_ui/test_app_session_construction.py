"""A PersonEditor that fails to construct must not leave the edit session active."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

import slaktbusken.ui.editors.person_editor as pe_mod
from slaktbusken.app import Application, _construct_editor_in_session
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.serialization import serialize
from slaktbusken.services.project_service import ProjectService
from tests.test_ui.test_add_child_parent_link import _make_app


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _boom(*_a, **_k):
    raise RuntimeError("konstruktionen misslyckades")


def test_construction_failure_rolls_session_back():
    data = ProjectData()
    data.persons = [Person(id="p1", sex="U", names=[Name(type="birth", given="A", surname="B")])]
    service = ProjectService()
    service._project_data = data
    session = service.begin_edit_session("Personredigerare")
    before = serialize(data)
    data.persons[0].notes = "ändrad före felet"
    with pytest.raises(RuntimeError):
        _construct_editor_in_session(session, _boom)
    assert service.active_edit_session is None
    assert serialize(data) == before


def test_add_relative_construction_failure_leaves_no_session(qapp, monkeypatch):
    data = ProjectData()
    data.persons = [Person(id="p1", sex="U", names=[Name(type="birth", given="A", surname="B")])]
    monkeypatch.setattr(pe_mod, "PersonEditor", _boom)
    fake, main = _make_app(qapp, data)
    try:
        with pytest.raises(RuntimeError):
            Application.handle_placeholder_click(fake, "child", "", "p1")
    finally:
        main.close()
    assert fake.project_service.active_edit_session is None
