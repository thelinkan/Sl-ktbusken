"""Person list column widths: Namn gets a good default and widths are saved."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.app_settings_io import AppSettings, AppSettingsService
from slaktbusken.ui.person_list_panel import PERSON_LIST_COLUMN_KEYS, PersonListPanel


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _panel(settings: AppSettings, tmp_path) -> tuple[PersonListPanel, AppSettingsService]:
    # The panel saves on some actions: keep it away from the real settings file.
    service = AppSettingsService()
    service.SETTINGS_PATH = tmp_path / "app_settings.json"
    service._settings = settings
    app = SimpleNamespace(
        app_settings_service=service,
        project_service=SimpleNamespace(data=ProjectData(), project_path=None),
    )
    return PersonListPanel(app), service


def test_one_key_per_column(qapp, tmp_path) -> None:
    panel, _ = _panel(AppSettings(), tmp_path)
    assert len(PERSON_LIST_COLUMN_KEYS) == panel._tree_widget.columnCount()
    assert len(set(PERSON_LIST_COLUMN_KEYS)) == len(PERSON_LIST_COLUMN_KEYS)


def test_name_column_has_a_good_default_width_in_a_narrow_panel(qapp, tmp_path) -> None:
    panel, _ = _panel(AppSettings(), tmp_path)
    panel.resize(400, 500)
    panel.show()
    qapp.processEvents()
    header = panel._tree_widget.header()
    assert header.sectionSize(0) >= 200
    assert header.sectionSize(0) == max(
        header.sectionSize(i) for i in range(header.count()) if not header.isSectionHidden(i)
    )
    panel.hide()


def test_widths_are_saved_and_restored(qapp, tmp_path) -> None:
    settings = AppSettings()
    panel, service = _panel(settings, tmp_path)
    header = panel._tree_widget.header()
    header.resizeSection(0, 260)
    header.resizeSection(1, 123)
    panel.save_column_widths()
    service.save(settings)

    reloaded = AppSettingsService()
    reloaded.SETTINGS_PATH = service.SETTINGS_PATH
    loaded = reloaded.load()
    assert loaded.person_list_column_widths["name"] == 260
    assert loaded.person_list_column_widths["birth_date"] == 123

    again, _ = _panel(loaded, tmp_path)
    assert again._tree_widget.header().sectionSize(0) == 260
    assert again._tree_widget.header().sectionSize(1) == 123


def test_hidden_column_keeps_its_width_and_stays_hidden(qapp, tmp_path) -> None:
    settings = AppSettings()
    settings.person_list_column_widths = {"boende": 150}
    assert settings.column_visibility.boende is False
    panel, _ = _panel(settings, tmp_path)
    header = panel._tree_widget.header()
    assert header.isSectionHidden(9)

    panel.save_column_widths()
    # Hidden, so its earlier width is kept rather than overwritten with 0.
    assert settings.person_list_column_widths["boende"] == 150

    header.setSectionHidden(9, False)
    assert header.sectionSize(9) == 150


def test_unusable_saved_widths_are_ignored(qapp, tmp_path) -> None:
    settings = AppSettings()
    settings.person_list_column_widths = {"name": 5, "birth_date": 99_999, "unknown": 100}
    panel, _ = _panel(settings, tmp_path)
    header = panel._tree_widget.header()
    assert header.sectionSize(0) == 200
    assert header.sectionSize(1) == 90


def test_malformed_widths_in_the_file_are_dropped(tmp_path) -> None:
    service = AppSettingsService()
    service.SETTINGS_PATH = tmp_path / "app_settings.json"
    service.SETTINGS_PATH.write_text(
        '{"person_list_column_widths": {"name": 240, "a": "wide", "b": true, "c": -4}}',
        encoding="utf-8",
    )
    assert service.load().person_list_column_widths == {"name": 240}
