"""Offscreen smoke tests for the merge candidate editor dialog."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.editor_registry import EditorRegistry, UnsavedChangesParticipant
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge import candidate_editor_dialog as ced
from slaktbusken.ui.merge.candidate_editor_dialog import CandidateEditorDialog
from slaktbusken.ui.merge.merge_gateway import get_merge_gateway, set_merge_gateway
from slaktbusken.ui.swedish_locale import (
    get_candidate_assessment_label,
    get_candidate_section_label,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def service() -> ProjectService:
    svc = ProjectService()
    data = ProjectData()
    data.persons = [
        Person(id="person_1", sex="M", names=[Name(type="birth", given="Anna", surname="B")]),
        Person(id="person_2", sex="F", names=[Name(type="birth", given="Bo", surname="B")]),
    ]
    svc._project_data = data
    return svc


@pytest.fixture
def dialog(qapp, service):
    cand = service.add_merge_candidate("person_1", "person_2")
    registry = EditorRegistry()
    dlg = CandidateEditorDialog(service, cand.id, registry=registry)
    dlg._registry = registry
    yield dlg
    dlg.setEnabled(True)
    dlg._text_edit.clear()
    dlg.close()


def _comments(service):
    return service.data.merge_candidates[0].comments


def test_labels():
    assert get_candidate_assessment_label("possible") == "Möjlig dubblett"
    assert get_candidate_assessment_label("zzz") == "zzz"
    assert get_candidate_section_label("history") == "Sammanslagningshistorik"


def test_gateway_registration():
    assert get_merge_gateway() is None
    set_merge_gateway(None)


def test_assessment_change_keeps_comments(dialog, service):
    dialog._text_edit.setPlainText("Samma födelseort")
    assert dialog.save_comment()
    dialog._assessment.setCurrentIndex(dialog._assessment.findData("rejected"))
    cand = service.data.merge_candidates[0]
    assert cand.assessment == "rejected"
    assert [c.text for c in cand.comments] == ["Samma födelseort"]
    dialog._enabled.setChecked(False)
    assert service.data.merge_candidates[0].enabled is False


def test_default_date_is_today(dialog):
    assert dialog._date_edit.text() == ced.today_text()


def test_comment_add_and_delete_prompt(dialog, service, monkeypatch):
    dialog._text_edit.setPlainText("Ny")
    dialog._date_edit.setText("1850-01-02")
    assert dialog.save_comment()
    assert len(_comments(service)) == 1

    prompts = []

    def deny(comment):
        prompts.append(ced.delete_prompt_text(comment))
        return False

    monkeypatch.setattr(dialog, "_confirm_delete", deny)
    dialog._comments.setCurrentRow(0)
    dialog._delete_button.click()
    assert len(_comments(service)) == 1
    assert "1850-01-02" in prompts[0]

    monkeypatch.setattr(dialog, "_confirm_delete", lambda c: True)
    dialog._delete_button.click()
    assert _comments(service) == []


def test_unsaved_text_prompt(dialog, service, monkeypatch):
    participant: UnsavedChangesParticipant = dialog
    assert isinstance(participant, UnsavedChangesParticipant)
    assert dialog._registry.unsaved_editors() == []
    dialog._text_edit.setPlainText("Osparad")
    assert dialog._registry.unsaved_editors() == [dialog]

    monkeypatch.setattr(dialog, "_ask_unsaved", lambda: ced.STAY)
    dialog.show()
    dialog.close()
    assert dialog.isVisible()
    assert dialog._text_edit.toPlainText() == "Osparad"

    monkeypatch.setattr(dialog, "_ask_unsaved", lambda: ced.SAVE)
    dialog.close()
    assert not dialog.isVisible()
    assert [c.text for c in _comments(service)] == ["Osparad"]


def test_unsaved_text_discard(dialog, service, monkeypatch):
    dialog._text_edit.setPlainText("Kastas")
    monkeypatch.setattr(dialog, "_ask_unsaved", lambda: ced.DISCARD)
    dialog.show()
    dialog.close()
    assert not dialog.isVisible()
    assert _comments(service) == []
