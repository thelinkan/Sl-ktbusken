"""Regression: an unsaved person edit must trigger the merge saved-state prompt.

Steps: open a project from disk, edit a person through the application's
person editor path, then run the merge wizard. The wizard has to ask
"Spara och fortsätt" because the project is dirty.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from slaktbusken.app import Application
from slaktbusken.model.person import Name, Person
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.editors.person_editor import PersonEditor
from slaktbusken.ui.merge import merge_review_wizard as mrw
from slaktbusken.ui.merge.merge_gateway import MergeExecutionResult
from slaktbusken.ui.merge.merge_review_wizard import MergeReviewWizard
from slaktbusken.ui.merge.merge_runner import ThreadedMergeExecutor
from slaktbusken.services.merge_engine import DIRTY_MESSAGE


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _Executor:
    def __init__(self) -> None:
        self.executed = False

    def execute(self, plan):
        self.executed = True
        return MergeExecutionResult(True, "Klar.", survivor_id=plan.survivor_id)


def _open_fresh_project(tmp_path: Path) -> ProjectService:
    svc = ProjectService()
    svc.create_project("P", tmp_path)
    for pid, sex in (("person_1", "M"), ("person_2", "F")):
        svc.add_person(
            Person(id=pid, sex=sex, names=[Name(type="birth", given="Anna", surname="Test")])
        )
    svc.save_project()
    path = svc.project_path
    fresh = ProjectService()
    fresh.open_project(path)
    return fresh


def _edit_person_through_application(qapp, svc: ProjectService, monkeypatch) -> None:
    window = QWidget()
    for name in ("show_progress", "hide_progress", "person_list_panel", "diagram_panel"):
        setattr(window, name, MagicMock())
    app = SimpleNamespace(
        project_service=svc,
        main_window=window,
        app_settings_service=MagicMock(),
    )
    app._resolve_person_request = lambda pid: pid
    app._update_status = lambda: None

    def fake_exec(dialog) -> int:
        editor = dialog.findChild(PersonEditor)
        editor._ui.sex_combo.setCurrentText("Kvinna")
        editor._on_save()
        return dialog.result()

    monkeypatch.setattr(QDialog, "exec", fake_exec)
    Application.open_person_editor(app, "person_1")


def test_unsaved_person_edit_prompts_before_merge(qapp, tmp_path, monkeypatch):
    svc = _open_fresh_project(tmp_path)
    assert svc.is_saved_state()

    _edit_person_through_application(qapp, svc, monkeypatch)
    assert svc.data.persons[0].sex == "F"
    assert not svc.is_saved_state(), "edit must leave the project unsaved"

    executor = _Executor()
    wiz = MergeReviewWizard(svc, ["person_1", "person_2"], executor=executor)
    wiz.wait_for_plan()
    qapp.processEvents()
    assert not svc.is_saved_state(), "opening the wizard must not clean the project"

    prompts: list[str] = []
    monkeypatch.setattr(wiz, "_ask_save_choice", lambda: prompts.append("ask") or mrw.CANCEL)
    assert wiz.check_saved_state() is False
    assert prompts == ["ask"]
    assert not executor.executed

    # The engine refuses on its own as well (Saved_State_Precondition).
    wiz.survivor_page.radios["person_1"].setChecked(True)
    wiz.survivor_page.confirm_button.click()
    wiz.wait_for_plan()
    qapp.processEvents()
    result = ThreadedMergeExecutor(svc).execute(wiz.plan)
    assert not result.success
    assert result.message == DIRTY_MESSAGE
    assert not svc.is_saved_state()
    on_disk = ProjectService()
    on_disk.open_project(svc.project_path)
    assert next(p.sex for p in on_disk.data.persons if p.id == "person_1") == "M"
