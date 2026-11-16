"""UI integration of save conflicts, refusals and blocked states (Requirements 20.8 to 20.20)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import slaktbusken.app as app_module  # noqa: E402
from slaktbusken.services.commit.translation_commit import (  # noqa: E402
    MSG_RECOVERY_COMPLETED,
    ImportSaveUnfinished,
    SaveConflict,
    SaveFailed,
)
from slaktbusken.ui.merge import recovery_dialogs  # noqa: E402
from slaktbusken.ui.merge.recovery_dialogs import (  # noqa: E402
    MSG_PENDING_TRANSLATION,
    translation_edit_refusal,
)

pytestmark = pytest.mark.mandatory_integrity

UNFINISHED = (
    "En sparning av en import är inte avslutad. Starta om Släktbusken för att "
    "slutföra eller kontrollera filerna."
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _fake_app(error=None, **service_attrs):
    service = MagicMock()
    service.save_project.side_effect = error
    for key, value in service_attrs.items():
        setattr(service, key, value)
    fake = SimpleNamespace(
        main_window=MagicMock(),
        project_service=service,
        _update_status=MagicMock(),
    )
    return fake


@pytest.fixture
def boxes(monkeypatch):
    box = MagicMock()
    monkeypatch.setattr(app_module, "QMessageBox", box)
    monkeypatch.setattr(app_module.QApplication, "processEvents", staticmethod(lambda: None))
    monkeypatch.setattr(recovery_dialogs, "QMessageBox", box)
    return box


@pytest.mark.parametrize(
    "error",
    [
        SaveConflict(["translation/places.json"]),
        SaveFailed(),
        ImportSaveUnfinished(()),
        ImportSaveUnfinished(["translation/sources.json"]),
    ],
)
def test_save_refusals_show_message_and_refresh_status(qapp, boxes, error):
    fake = _fake_app(error=error)
    app_module.Application.save_project(fake)

    boxes.warning.assert_called_once()
    assert boxes.warning.call_args.args[2] == error.message
    boxes.critical.assert_not_called()
    fake._update_status.assert_called_once()
    # The project is not closed and not marked saved by the handler.
    fake.project_service.close_project.assert_not_called()
    fake.main_window.statusBar.return_value.showMessage.assert_not_called()


def test_conflict_message_names_files_and_next_steps(qapp, boxes):
    error = SaveConflict(["translation/places.json", "translation/sources.json"])
    app_module.Application.save_project(_fake_app(error=error))
    text = boxes.warning.call_args.args[2]
    assert "translation/places.json" in text
    assert "translation/sources.json" in text
    assert "Spara igen" in text


def test_import_gedcom_refused_while_import_save_unfinished(qapp, boxes, monkeypatch):
    fake = _fake_app(import_save_unfinished=True)
    dialog = MagicMock()
    monkeypatch.setattr(app_module, "QFileDialog", dialog)
    app_module.Application.import_gedcom(fake)
    assert boxes.warning.call_args.args[2] == UNFINISHED
    dialog.getOpenFileName.assert_not_called()


def test_translation_edit_refusal_texts():
    assert translation_edit_refusal(
        SimpleNamespace(import_save_unfinished=False, pending_translation=None)
    ) == ""
    assert (
        translation_edit_refusal(
            SimpleNamespace(import_save_unfinished=False, pending_translation=object())
        )
        == MSG_PENDING_TRANSLATION
    )
    assert MSG_PENDING_TRANSLATION == (
        "Spara projektet innan du redigerar översättningarna. En import väntar på att sparas."
    )
    # An unfinished import save takes precedence.
    assert (
        translation_edit_refusal(
            SimpleNamespace(import_save_unfinished=True, pending_translation=object())
        )
        == UNFINISHED
    )


@pytest.mark.parametrize("which", ["show_place_translation_editor", "show_source_translation_editor"])
@pytest.mark.parametrize(
    "attrs, expected",
    [
        ({"pending_translation": object(), "import_save_unfinished": False}, MSG_PENDING_TRANSLATION),
        ({"pending_translation": None, "import_save_unfinished": True}, UNFINISHED),
    ],
)
def test_app_entry_points_refuse_translation_editors(qapp, boxes, monkeypatch, which, attrs, expected):
    fake = _fake_app(**attrs)
    fake._refuse_translation_editor = lambda title: app_module.Application._refuse_translation_editor(
        fake, title
    )
    dialog = MagicMock()
    monkeypatch.setattr(app_module, "QDialog", dialog)
    getattr(app_module.Application, which)(fake)
    assert boxes.warning.call_args.args[2] == expected
    dialog.assert_not_called()


def test_recovery_message_of_interrupted_import_save_uses_own_title(qapp, boxes):
    fake = _fake_app(last_recovery_message=MSG_RECOVERY_COMPLETED)
    app_module.Application._show_recovery_message(fake)
    args = boxes.information.call_args.args
    assert args[1] == "Avbruten sparning"
    assert args[2] == MSG_RECOVERY_COMPLETED


def test_show_recovery_outcome_default_title_is_merge(qapp, boxes):
    recovery_dialogs.show_recovery_outcome(None, "Sammanslagningen slutfördes.")
    assert boxes.information.call_args.args[1] == recovery_dialogs.MERGE_TITLE
