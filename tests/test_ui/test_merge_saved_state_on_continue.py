"""The saved-state prompt appears when continuing from the comparison window.

``Application.open_merge_review`` asks before the Merge_Review wizard is
created; the wizard's own check at execute is only a safety net.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from slaktbusken.app import Application
from slaktbusken.model.person import Name, Person
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge import merge_review_wizard as mrw


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _FakeBox:
    """Stand-in for QMessageBox: records prompts and clicks a scripted button."""

    Icon = QMessageBox.Icon
    ButtonRole = QMessageBox.ButtonRole
    answer = mrw.SAVE
    prompts: list[str] = []

    def __init__(self, parent=None):
        self._buttons: dict[str, str] = {}
        self._clicked = None

    def setWindowTitle(self, _t): ...
    def setIcon(self, _i): ...

    def setText(self, text):
        self._text = text

    def addButton(self, text, _role):
        key = mrw.SAVE if text == mrw.SAVE_AND_CONTINUE_TEXT else mrw.CANCEL
        self._buttons[key] = text
        return text

    def exec(self):
        type(self).prompts.append(self._text)
        self._clicked = self._buttons[type(self).answer]
        return 0

    def clickedButton(self):
        return self._clicked

    @staticmethod
    def warning(*_a):
        raise AssertionError("unexpected warning")


class _Registry:
    def __init__(self, unsaved):
        self.unsaved = list(unsaved)

    def unsaved_editors(self):
        return list(self.unsaved)


def _service(tmp_path, dirty: bool) -> ProjectService:
    svc = ProjectService()
    svc.create_project("P", tmp_path)
    for pid in ("person_1", "person_2"):
        svc.add_person(Person(id=pid, sex="U", names=[Name(type="birth", given="A", surname="T")]))
    svc.save_project()
    if dirty:
        svc.add_person(Person(id="person_3", sex="U", names=[Name(type="birth", given="B", surname="T")]))
        assert not svc.is_saved_state()
    return svc


@pytest.fixture
def env(qapp, tmp_path, monkeypatch):
    _FakeBox.prompts = []
    _FakeBox.answer = mrw.SAVE
    monkeypatch.setattr(mrw, "QMessageBox", _FakeBox)
    created: list[mrw.MergeReviewWizard] = []
    real_init = mrw.MergeReviewWizard.__init__

    def init(self, *a, **kw):
        # The prompt must already have happened when the wizard is built.
        init.prompts_at_build = list(_FakeBox.prompts)
        real_init(self, *a, **kw)
        created.append(self)

    init.prompts_at_build = None
    monkeypatch.setattr(mrw.MergeReviewWizard, "__init__", init)
    monkeypatch.setattr(mrw.MergeReviewWizard, "exec", lambda self: 0)
    main = QMainWindow()

    def make_app(dirty: bool, registry=None):
        svc = _service(tmp_path, dirty)
        app = SimpleNamespace(
            project_service=svc,
            main_window=main,
            editor_registry=registry,
            _comparison_window=None,
            _translation_for_planning=lambda: None,
        )
        app._status_updates = 0

        def update_status():
            app._status_updates += 1

        app._update_status = update_status
        app._after_merge_review = lambda *_a: None
        return app

    yield SimpleNamespace(make_app=make_app, created=created, init=init)
    for w in created:
        w.wait_for_plan()
    main.close()


def test_dirty_project_prompts_before_wizard_and_cancel_blocks(env):
    app = env.make_app(dirty=True)
    _FakeBox.answer = mrw.CANCEL
    Application.open_merge_review(app, "person_1", "person_2")
    assert _FakeBox.prompts == [mrw.SAVE_PROMPT_TEXT]
    assert env.created == []
    assert not app.project_service.is_saved_state()


def test_dirty_project_save_opens_wizard_without_second_prompt(env):
    app = env.make_app(dirty=True)
    Application.open_merge_review(app, "person_1", "person_2")
    assert _FakeBox.prompts == [mrw.SAVE_PROMPT_TEXT]
    assert env.init.prompts_at_build == [mrw.SAVE_PROMPT_TEXT]
    assert app.project_service.is_saved_state()
    assert app._status_updates >= 1
    (wizard,) = env.created
    wizard.wait_for_plan()
    assert wizard.check_saved_state() is True  # safety net: nothing to ask
    assert _FakeBox.prompts == [mrw.SAVE_PROMPT_TEXT]


def test_clean_project_opens_wizard_without_prompt(env):
    app = env.make_app(dirty=False)
    Application.open_merge_review(app, "person_1", "person_2")
    assert _FakeBox.prompts == []
    assert len(env.created) == 1


def test_unsaved_editor_blocks_before_wizard(env, monkeypatch):
    shown: list[object] = []

    class _Block:
        def __init__(self, editors, parent=None):
            shown.append(editors)

        def exec(self):
            return 0

    monkeypatch.setattr(mrw, "UnsavedEditorsDialog", _Block)
    registry = _Registry([object()])
    app = env.make_app(dirty=False, registry=registry)
    Application.open_merge_review(app, "person_1", "person_2")
    assert len(shown) == 1
    assert env.created == []
    assert _FakeBox.prompts == []
