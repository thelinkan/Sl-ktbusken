"""Offscreen tests for "Filtrera källans personer" in the source editor and app."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QVBoxLayout

import slaktbusken.ui.editors.source_editor as source_editor_module
from slaktbusken.app import Application
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Observation, ResidenceFact
from slaktbusken.model.source import Source
from slaktbusken.persistence.app_settings_io import AppSettings, AppSettingsService
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.editors.registry_participation import (
    CANCEL_CHOICE,
    DISCARD_CHOICE,
    SAVE_CHOICE,
)
from slaktbusken.ui.editors.source_editor import SourceEditor
from slaktbusken.ui.person_list_panel import PersonListPanel

LABEL = "Filtrera källans personer"
TIP = "Filtrerar på källa och stänger källredigerarfönstret"
TIP_NONE = "Vald källa har ingen person ansluten till sig"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _person(pid: str) -> Person:
    return Person(id=pid, sex="U", names=[Name(type="birth", given=pid, surname="Test")])


def _ref(source_id: str) -> SourceRef:
    return SourceRef(source_id=source_id, quality="high")


def _make_data() -> ProjectData:
    data = ProjectData()
    data.persons = [_person(f"p{i}") for i in range(1, 6)]
    data.sources = [
        Source(id="s-full", provider="", source_type="other", title="A full"),
        Source(id="s-event", provider="", source_type="other", title="B event"),
        Source(id="s-res", provider="", source_type="other", title="C res"),
        Source(id="s-none", provider="", source_type="other", title="D none"),
    ]
    data.events = [
        Event(id="e1", type="birth", participants=[Participant(person_id="p1", role="child"),
                                                    Participant(person_id="p2", role="mother")],
              date=DateValue(value="1850", precision="year", source_refs=[_ref("s-full")])),
        Event(id="e2", type="death", participants=[Participant(person_id="p1", role="deceased")],
              place=PlaceRef(place_id="pl", source_refs=[_ref("s-full"), _ref("s-event")])),
    ]
    data.residences = [
        ResidenceFact(id="r1", person_id="p3", place_id="pl",
                      observations=[Observation(source_ref=_ref("s-full"))]),
        ResidenceFact(id="r2", person_id="p4", place_id="pl",
                      observations=[Observation(source_ref=_ref("s-res"))]),
    ]
    return data


def _select(editor: SourceEditor, source_id: str) -> None:
    lst = editor._ui.source_list
    for i in range(lst.count()):
        if lst.item(i).data(Qt.ItemDataRole.UserRole) == source_id:
            lst.setCurrentRow(i)
            return
    raise AssertionError(source_id)


@pytest.fixture
def editor(qapp):
    ed = SourceEditor(project_data=_make_data())
    ed.resize(1100, 700)
    ed.show()
    QApplication.processEvents()
    yield ed
    ed.close()


def _label_for(editor: SourceEditor, source_id: str) -> str:
    lst = editor._ui.source_list
    for i in range(lst.count()):
        if lst.item(i).data(Qt.ItemDataRole.UserRole) == source_id:
            return lst.item(i).text()
    raise AssertionError(source_id)


def test_list_label_formats(editor):
    assert _label_for(editor, "s-full").endswith("[3 pers, 2 händ, 1 boende]")
    assert _label_for(editor, "s-event").endswith("[1 pers, 1 händ]")
    assert _label_for(editor, "s-res").endswith("[1 pers, 1 boende]")
    assert _label_for(editor, "s-none").endswith("[0 pers]")


def test_button_label_and_position(editor):
    button = editor._filter_persons_button
    assert button.text() == LABEL
    delete = editor._ui.delete_source_button
    save = editor._ui.save_button

    def rect(w):
        top_left = w.mapTo(editor, w.rect().topLeft())
        return top_left.x(), top_left.x() + w.width()

    b_left, b_right = rect(button)
    _d_left, d_right = rect(delete)
    s_left, _s_right = rect(save)
    assert b_left > d_right
    assert s_left - b_right >= 30
    assert editor.grab().width() > 0


def test_enablement_and_tooltips(editor):
    button = editor._filter_persons_button
    # No selection / unsaved new form
    assert not button.isEnabled() and button.toolTip() == TIP
    _select(editor, "s-full")
    assert button.isEnabled() and button.toolTip() == TIP
    _select(editor, "s-none")
    assert not button.isEnabled() and button.toolTip() == TIP_NONE
    _select(editor, "s-res")
    assert button.isEnabled() and button.toolTip() == TIP
    editor._ui.add_source_button.click()
    assert not button.isEnabled() and button.toolTip() == TIP


def test_state_after_remove(editor):
    _select(editor, "s-res")
    editor._ui.delete_source_button.click()
    assert not editor._filter_persons_button.isEnabled()


def test_click_without_changes_emits_without_prompt(editor, monkeypatch):
    def fail(*_a):
        raise AssertionError("no prompt expected")

    monkeypatch.setattr(source_editor_module, "prompt_resolution", fail)
    got: list[str] = []
    editor.filter_persons_requested.connect(got.append)
    _select(editor, "s-full")
    assert not editor.is_dirty()
    editor._filter_persons_button.click()
    assert got == ["s-full"]


def _dirty(editor: SourceEditor) -> None:
    _select(editor, "s-full")
    editor._ui.title_input.setText("A full changed")
    assert editor.is_dirty()


def _patch_choice(monkeypatch, choice: str) -> list[int]:
    calls: list[int] = []
    monkeypatch.setattr(
        source_editor_module, "prompt_resolution", lambda *_a: calls.append(1) or choice
    )
    return calls


def test_unsaved_save_saves_then_emits(editor, monkeypatch):
    calls = _patch_choice(monkeypatch, SAVE_CHOICE)
    got: list[str] = []
    editor.filter_persons_requested.connect(got.append)
    _dirty(editor)
    editor._filter_persons_button.click()
    assert calls == [1] and got == ["s-full"]
    saved = next(s for s in editor._project_data.sources if s.id == "s-full")
    assert saved.title == "A full changed"


def test_unsaved_discard_emits_without_saving(editor, monkeypatch):
    _patch_choice(monkeypatch, DISCARD_CHOICE)
    got: list[str] = []
    editor.filter_persons_requested.connect(got.append)
    _dirty(editor)
    editor._filter_persons_button.click()
    assert got == ["s-full"]
    saved = next(s for s in editor._project_data.sources if s.id == "s-full")
    assert saved.title == "A full"


def test_unsaved_cancel_does_nothing(editor, monkeypatch):
    _patch_choice(monkeypatch, CANCEL_CHOICE)
    got: list[str] = []
    editor.filter_persons_requested.connect(got.append)
    _dirty(editor)
    editor._filter_persons_button.click()
    assert got == [] and editor.isVisible()
    assert editor._ui.title_input.text() == "A full changed"


def test_failed_save_stays_open(editor, monkeypatch):
    _patch_choice(monkeypatch, SAVE_CHOICE)
    got: list[str] = []
    editor.filter_persons_requested.connect(got.append)
    _select(editor, "s-full")
    editor._ui.title_input.setText("")  # validation: title required
    editor._filter_persons_button.click()
    assert got == [] and editor.isVisible()


# --------------------------- app wiring ---------------------------------


@pytest.fixture
def app_like(qapp, tmp_path):
    svc = ProjectService()
    svc._project_data = _make_data()
    svc._project_path = Path(tmp_path / "project.json.gz")
    settings = AppSettingsService()
    settings.SETTINGS_PATH = tmp_path / "app_settings.json"
    settings._settings = AppSettings()
    main = QMainWindow()
    fake = SimpleNamespace(
        project_service=svc, main_window=main, editor_registry=None,
        app_settings_service=settings,
    )
    panel = PersonListPanel(fake)
    main.person_list_panel = panel
    main.setCentralWidget(panel)
    fake._update_status = lambda *_a: None
    fake._exec_source_editor_dialog = lambda d, e: Application._exec_source_editor_dialog(fake, d, e)
    fake._filter_persons_by_source = lambda sid: Application._filter_persons_by_source(fake, sid)
    panel.refresh()
    main.show()
    yield fake
    main.close()


def _shown_ids(panel: PersonListPanel) -> set[str]:
    tree = panel._tree_widget
    return {
        tree.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
        for i in range(tree.topLevelItemCount())
    }


def test_app_filters_person_list_after_dialog_closes(app_like):
    svc = app_like.project_service
    panel = app_like.main_window.person_list_panel
    assert len(_shown_ids(panel)) == 5
    svc._dirty = False

    def click() -> None:
        dialog = QApplication.activeModalWidget()
        editor = dialog.findChild(SourceEditor)
        _select(editor, "s-full")
        editor._filter_persons_button.click()

    QTimer.singleShot(50, click)
    Application.show_source_editor(app_like)

    assert panel._showing_filtered
    assert _shown_ids(panel) == {"p1", "p2", "p3"}  # p3 is residence-only
    assert svc._dirty is False

    panel._toggle_button.setChecked(False)  # "Visa alla"
    assert len(_shown_ids(panel)) == 5


def test_single_source_dialog_filters_too(app_like):
    panel = app_like.main_window.person_list_panel
    app_like._open_single_entity_editor = lambda t, i: Application._open_single_entity_editor(
        app_like, t, i
    )

    def click() -> None:
        editor = QApplication.activeModalWidget().findChild(SourceEditor)
        editor._filter_persons_button.click()

    QTimer.singleShot(50, click)
    Application._open_single_entity_editor(app_like, "source", "s-res")
    assert panel._showing_filtered
    assert _shown_ids(panel) == {"p4"}
