"""Editors take part in the unsaved-changes registry (Requirements 26.14, 27.23)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import shiboken6
from PySide6.QtWidgets import QApplication

from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.editor_registry import EditorRegistry, ResolutionResult
from slaktbusken.ui.editors import registry_participation
from slaktbusken.ui.editors.person_editor import PersonEditor
from slaktbusken.ui.editors.provider_editor import ProviderEditor


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def data() -> ProjectData:
    person = Person(
        id="person_12",
        sex="F",
        names=[Name(type="birth", given="Anna", surname="Svensson")],
    )
    return ProjectData(project=ProjectMetadata(title="T"), persons=[person])


def _editor(data, registry=None) -> PersonEditor:
    return PersonEditor(data, data.persons[0], registry=registry)


def test_no_unsaved_changes_after_load(qapp, data):
    editor = _editor(data)
    assert editor.has_unsaved_changes() is False
    assert "Anna Svensson" in editor.editor_title
    assert "person_12" in editor.editor_title


def test_unsaved_after_edit_and_clean_after_save(qapp, data):
    editor = _editor(data)
    editor._ui.title_input.setText("Bonde")
    assert editor.has_unsaved_changes() is True
    editor._on_save()
    assert editor.saved_person is not None
    assert editor.has_unsaved_changes() is False


def test_name_edit_is_detected(qapp, data):
    editor = _editor(data)
    editor._ui.names_table.item(0, 1).setText("Britta")
    assert editor.has_unsaved_changes() is True


@pytest.mark.parametrize(
    "choice, result, saved",
    [
        ("save", ResolutionResult.SAVED, True),
        ("discard", ResolutionResult.DISCARDED, False),
        ("cancel", ResolutionResult.STILL_UNSAVED, False),
    ],
)
def test_request_resolution_follows_user_choice(
    qapp, data, monkeypatch, choice, result, saved
):
    editor = _editor(data)
    editor._ui.title_input.setText("Bonde")
    monkeypatch.setattr(
        registry_participation, "prompt_resolution", lambda parent, title: choice
    )
    assert editor.request_resolution() is result
    assert (editor.saved_person is not None) is saved
    if result is ResolutionResult.DISCARDED:
        assert editor._ui.title_input.text() == ""
        assert editor.has_unsaved_changes() is False
    if result is ResolutionResult.STILL_UNSAVED:
        assert editor.has_unsaved_changes() is True


def test_nothing_resolved_without_a_user_choice(qapp, data):
    """has_unsaved_changes and the registry never save or discard."""
    registry = EditorRegistry()
    editor = _editor(data, registry)
    editor._ui.title_input.setText("Bonde")
    assert registry.unsaved_editors() == [editor]
    assert editor.saved_person is None
    assert editor._ui.title_input.text() == "Bonde"


def test_registration_and_unregistration(qapp, data):
    registry = EditorRegistry()
    editor = _editor(data, registry)
    assert registry.unsaved_editors() == []
    editor._ui.title_input.setText("Bonde")
    assert registry.unsaved_editors() == [editor]
    shiboken6.delete(editor)  # emits destroyed while the Python object lives
    assert registry.unsaved_editors() == []
    assert registry._refs == []


def test_other_editor_registers_and_delegates(qapp, data):
    registry = EditorRegistry()
    editor = ProviderEditor(data, registry=registry)
    assert editor in [r() for r in registry._refs]
    assert editor.has_unsaved_changes() is False
    assert editor.editor_title


def test_editor_without_registry_still_works(qapp, data):
    editor = _editor(data)
    assert editor.has_unsaved_changes() is False
    assert ProviderEditor(data).has_unsaved_changes() is False
