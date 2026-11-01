"""The GEDCOM update warning in the merge preview (task 11.19).

**Validates: Requirements 26.15, 30.13, 30.15**
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from slaktbusken.gedcom import capabilities
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge.merge_preview import GEDCOM_WARNING_TEXT
from slaktbusken.ui.merge.merge_review_wizard import MergeReviewWizard


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def wizard(qapp):
    svc = ProjectService()
    data = ProjectData()
    data.persons = [
        Person(id=f"person_{i}", sex="U", names=[Name(type="birth", given="Anna", surname="T")])
        for i in (1, 2)
    ]
    svc._project_data = data
    wiz = MergeReviewWizard(svc, ["person_1", "person_2"], use_worker=False)
    yield wiz
    wiz.reject()


def test_warning_shown_while_flag_false(wizard):
    assert capabilities.NON_DESTRUCTIVE_UPDATE_AVAILABLE is False
    assert not wizard.preview.gedcom_label.isHidden()
    assert wizard.preview.gedcom_label.text() == GEDCOM_WARNING_TEXT


def test_warning_text_appears_once(wizard):
    labels = [w for w in wizard.findChildren(QLabel) if w.text() == GEDCOM_WARNING_TEXT]
    assert len(labels) == 1


def test_warning_above_execute_button(wizard):
    layout = wizard.preview.layout()
    order = [layout.itemAt(i).widget() for i in range(layout.count())]
    assert order.index(wizard.preview.gedcom_label) < len(order) - 1  # buttons row follows


@pytest.mark.parametrize("flag, expected_visible", [(False, True), (True, False)])
def test_warning_state_at_second_confirmation(wizard, monkeypatch, flag, expected_visible):
    monkeypatch.setattr(capabilities, "NON_DESTRUCTIVE_UPDATE_AVAILABLE", flag)
    wizard.preview.refresh()
    seen = []

    def fake_confirm(text):
        seen.append(not wizard.preview.gedcom_label.isHidden())
        return False

    monkeypatch.setattr(wizard, "_confirm_merge", fake_confirm)
    wizard._on_survivor_selected("person_1")
    wizard._on_survivor_confirmed()
    wizard.preview.refresh()
    assert wizard.preview.can_execute(), wizard.preview.problem_list.count()
    wizard._on_execute()
    assert seen == [expected_visible]


def test_warning_hidden_when_flag_true(wizard, monkeypatch):
    monkeypatch.setattr(capabilities, "NON_DESTRUCTIVE_UPDATE_AVAILABLE", True)
    wizard.preview.refresh()
    assert wizard.preview.gedcom_label.isHidden()
