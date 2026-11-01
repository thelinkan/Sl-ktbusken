"""Additional offscreen widget tests for the candidate editor dialog, panel,
register and person editor section (task 5.11).

Complements test_candidate_editor_dialog.py, test_candidate_register_window.py
and test_person_editor_candidates.py without duplicating them.

**Validates: Requirements 4.4, 4.7, 4.8, 15.1, 15.12, 16.1**
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.merge_candidate import MAX_COMMENT_TEXT, MergeCandidateComment
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.candidate_register import NO_MATCH_MESSAGE
from slaktbusken.services.editor_registry import EditorRegistry, ResolutionResult
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.editors.person_editor import PersonEditor
from slaktbusken.ui.merge import candidate_editor_dialog as ced
from slaktbusken.ui.merge.candidate_editor_dialog import CandidateEditorDialog, CandidatePanel
from slaktbusken.ui.merge.candidate_register_window import CandidateRegisterWindow


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def service() -> ProjectService:
    svc = ProjectService()
    data = ProjectData()
    data.persons = [
        Person(id=f"person_{i}", sex="U", names=[Name(type="birth", given=g, surname="T")])
        for i, g in enumerate(["Anna", "Bo", "Cia"], start=1)
    ]
    svc._project_data = data
    return svc


@pytest.fixture
def candidate(service):
    return service.add_merge_candidate("person_1", "person_2")


@pytest.fixture
def registry():
    return EditorRegistry()


@pytest.fixture
def dialog(qapp, service, candidate, registry):
    dlg = CandidateEditorDialog(service, candidate.id, registry=registry)
    yield dlg
    dlg._text_edit.clear()
    dlg.close()


@pytest.fixture
def panel(qapp, service, candidate, registry):
    pnl = CandidatePanel(service, candidate.id, registry=registry)
    yield pnl
    pnl._text_edit.clear()
    pnl.close()


def _comments(service):
    return service.data.merge_candidates[0].comments


# -- comment deletion prompt (4.7) -------------------------------------------


def test_delete_prompt_names_date_or_missing_date():
    dated = MergeCandidateComment(id="c1", date="1850-01-02", text="x")
    undated = MergeCandidateComment(id="c2", date="", text="x")
    assert "1850-01-02" in ced.delete_prompt_text(dated)
    assert ced.MSG_NO_DATE in ced.delete_prompt_text(undated)


def test_delete_button_needs_selection(dialog):
    assert not dialog._delete_button.isEnabled()
    assert not dialog._edit_button.isEnabled()


def test_declined_delete_keeps_comment_and_confirm_prompt_is_asked_once(
    dialog, service, monkeypatch
):
    dialog._text_edit.setPlainText("Behålls")
    assert dialog.save_comment()
    asked = []
    monkeypatch.setattr(dialog, "_confirm_delete", lambda c: asked.append(c.text) or False)
    dialog._comments.setCurrentRow(0)
    dialog._delete_button.click()
    assert asked == ["Behålls"]
    assert [c.text for c in _comments(service)] == ["Behålls"]


# -- unsaved text protection (4.8) -------------------------------------------


def test_new_comment_button_asks_when_text_unsaved(dialog, service, monkeypatch):
    dialog._text_edit.setPlainText("Pågår")
    monkeypatch.setattr(dialog, "_ask_unsaved", lambda: ced.STAY)
    dialog._new_button.click()
    assert dialog._text_edit.toPlainText() == "Pågår"
    monkeypatch.setattr(dialog, "_ask_unsaved", lambda: ced.DISCARD)
    dialog._new_button.click()
    assert dialog._text_edit.toPlainText() == ""
    assert _comments(service) == []


def test_editing_existing_comment_detects_changes(dialog, service, monkeypatch):
    dialog._text_edit.setPlainText("Original")
    assert dialog.save_comment()
    dialog._comments.setCurrentRow(0)
    dialog._edit_button.click()
    assert not dialog.has_unsaved_text()
    dialog._text_edit.setPlainText("Ändrad")
    assert dialog.has_unsaved_text()
    assert dialog.has_unsaved_changes()
    assert dialog.save_comment()
    assert [c.text for c in _comments(service)] == ["Ändrad"]


def test_whitespace_only_text_is_not_unsaved(dialog):
    dialog._text_edit.setPlainText("   \n ")
    assert not dialog.has_unsaved_text()


def test_empty_and_too_long_comment_rejected(dialog, service):
    dialog._text_edit.setPlainText("  ")
    assert dialog.save_comment() is False
    assert dialog._error_label.text()
    dialog._text_edit.setPlainText("x" * (MAX_COMMENT_TEXT + 1))
    assert dialog.save_comment() is False
    assert dialog._text_edit.toPlainText() == "x" * (MAX_COMMENT_TEXT + 1)
    assert _comments(service) == []


@pytest.mark.parametrize(
    "choice, expected",
    [
        (ced.SAVE, ResolutionResult.SAVED),
        (ced.DISCARD, ResolutionResult.DISCARDED),
        (ced.STAY, ResolutionResult.STILL_UNSAVED),
    ],
)
def test_request_resolution_outcomes(dialog, service, monkeypatch, choice, expected):
    dialog._text_edit.setPlainText("Via registret")
    monkeypatch.setattr(dialog, "_ask_unsaved", lambda: choice)
    assert dialog.request_resolution() == expected
    assert len(_comments(service)) == (1 if choice == ced.SAVE else 0)


def test_request_resolution_without_unsaved_text_is_saved(dialog):
    assert dialog.request_resolution() == ResolutionResult.SAVED


def test_registry_sees_dialog_only_while_text_unsaved(dialog, registry):
    assert registry.unsaved_editors() == []
    dialog._text_edit.setPlainText("Osparad")
    assert registry.unsaved_editors() == [dialog]
    assert "Kandidatredigerare" in dialog.editor_title
    dialog._text_edit.clear()
    assert registry.unsaved_editors() == []


def test_missing_candidate_disables_dialog(dialog, service):
    service.data.merge_candidates.clear()
    dialog.refresh()
    assert not dialog.isEnabled()


# -- embedded CandidatePanel variant -----------------------------------------


def test_panel_close_emits_when_nothing_unsaved(panel):
    seen = []
    panel.close_requested.connect(lambda: seen.append(True))
    panel._close_button.click()
    assert seen == [True]
    assert panel._close_button.text() == CandidatePanel.CLOSE_TEXT


def test_panel_close_blocked_by_unsaved_text(panel, service, registry, monkeypatch):
    seen = []
    panel.close_requested.connect(lambda: seen.append(True))
    panel._text_edit.setPlainText("Osparad i panelen")
    assert registry.unsaved_editors() == [panel]

    monkeypatch.setattr(panel, "_ask_unsaved", lambda: ced.STAY)
    assert panel.request_close() is False
    panel._close_button.click()
    assert seen == []

    monkeypatch.setattr(panel, "_ask_unsaved", lambda: ced.SAVE)
    assert panel.request_close() is True
    assert seen == [True]
    assert [c.text for c in _comments(service)] == ["Osparad i panelen"]


# -- register: empty table (15.12), columns (15.1) ----------------------------


def test_register_empty_project_shows_empty_table(qapp, service):
    win = CandidateRegisterWindow(service)
    try:
        win.show()
        assert win.row_count() == 0
        assert win._table.columnCount() == 6
        assert win._empty_label.text() == NO_MATCH_MESSAGE
        assert win._empty_label.isVisible()
        assert not win._edit_button.isEnabled()
    finally:
        win.close()


def test_register_edit_uses_registry_and_refreshes(qapp, service, candidate, registry, monkeypatch):
    from slaktbusken.ui.merge import candidate_register_window as crw

    seen = {}

    class FakeDialog:
        def __init__(self, svc, candidate_id, parent=None, registry=None):
            seen["registry"] = registry
            svc.add_candidate_comment(candidate_id, "2024-05-05", "Från dialog")

        def exec(self):
            return 0

    monkeypatch.setattr(crw, "CandidateEditorDialog", FakeDialog)
    win = CandidateRegisterWindow(service, registry=registry)
    try:
        win._table.selectRow(0)
        assert win._edit_button.isEnabled()
        win.edit_selected()
        assert seen["registry"] is registry
        assert win.cell_text(0, 4) == "Från dialog"
    finally:
        win.close()


# -- person editor section visibility (16.1) ----------------------------------


def test_editor_section_shows_new_candidate_after_refresh(qapp, service, candidate):
    person = service.data.persons[0]
    editor = PersonEditor(service.data, person, project_service=service)
    section = editor._candidates_section
    assert section.candidate_ids() == [candidate.id]
    service.set_candidate_assessment(candidate.id, "rejected")
    assert section.candidate_ids() == []
    section.set_show_historical(True)
    assert section.candidate_ids() == [candidate.id]
