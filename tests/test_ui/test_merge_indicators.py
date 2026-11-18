"""Example tests for the settings of research and merge-candidate indicators (task 9.6).

Label strings are already covered by ``test_settings_dialog_labels.py`` (dialog
checkboxes) and ``test_person_list_indicators.py`` (column header and header
context-menu toggle); this module covers the persistence and independence rules.

**Validates: Requirements 17.1, 17.2, 17.3, 17.13, 17.14, 18.1, 18.2, 18.3**
"""

from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.persistence.app_settings_io import AppSettings, AppSettingsService
from slaktbusken.persistence.settings_io import (
    DiagramSettings,
    PersonBoxConfig,
    PersonListConfig,
    ProjectSettings,
    read_settings,
    write_settings,
)
from slaktbusken.ui.dialogs.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def service(tmp_path) -> AppSettingsService:
    svc = AppSettingsService()
    svc.SETTINGS_PATH = tmp_path / ".slaktbusken" / "app_settings.json"
    return svc


def _write_app_json(service: AppSettingsService, payload: dict) -> None:
    service.SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    service.SETTINGS_PATH.write_text(json.dumps(payload), encoding="utf-8")


def _dialog(box=None, plc=None) -> SettingsDialog:
    return SettingsDialog(
        box or PersonBoxConfig(), DiagramSettings(), plc or PersonListConfig()
    )


# --- Labels (exact strings, one place) -------------------------------------


def test_exact_label_strings(qapp) -> None:
    dialog = _dialog()
    assert dialog._pl_check_research.text() == "Forskningsuppslag och dubletter"
    assert dialog._check_research.text() == "Forskningsuppslag"
    assert dialog._check_merge_candidates.text() == "Sammanslagningskandidater"


def test_attribute_names_are_unchanged(qapp) -> None:
    dialog = _dialog()
    assert hasattr(dialog, "_pl_check_research")
    assert hasattr(dialog, "_check_research")


# --- Old research value -> combined setting (17.13, 17.14) -----------------


@pytest.mark.parametrize("old_value", [True, False])
def test_old_person_list_research_value_is_the_combined_setting(
    tmp_path, service, qapp, old_value: bool
) -> None:
    payload = {"person_list_config": {"research": old_value}}

    path = tmp_path / "settings.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    project = read_settings(path)
    assert project.person_list_config.research is old_value

    _write_app_json(service, payload)
    app = service.load()
    assert app.person_list_config.research is old_value

    dialog = _dialog(plc=app.person_list_config)
    assert dialog._pl_check_research.isChecked() is old_value


def test_missing_person_list_research_value_means_enabled(
    tmp_path, service, qapp
) -> None:
    payload = {"person_list_config": {"sex": False}}

    path = tmp_path / "settings.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert read_settings(path).person_list_config.research is True

    _write_app_json(service, payload)
    app = service.load()
    assert app.person_list_config.research is True
    assert _dialog(plc=app.person_list_config)._pl_check_research.isChecked()


# --- merge_candidates key missing / round trip (18.2, 18.3) ----------------


def test_default_is_true() -> None:
    assert PersonBoxConfig().merge_candidates is True


def test_project_settings_without_merge_candidates_key_default_true(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"person_box_config": {"name": True, "research": False}}),
        encoding="utf-8",
    )
    box = read_settings(path).person_box_config
    assert box.merge_candidates is True
    assert box.research is False


def test_app_settings_without_merge_candidates_key_default_true(service) -> None:
    _write_app_json(service, {"person_box_config": {"name": True, "research": False}})
    box = service.load().person_box_config
    assert box.merge_candidates is True
    assert box.research is False


@pytest.mark.parametrize("value", [True, False])
def test_project_settings_round_trip(tmp_path, value: bool) -> None:
    path = tmp_path / "nested" / "settings.json"
    write_settings(
        ProjectSettings(person_box_config=PersonBoxConfig(merge_candidates=value)),
        path,
    )
    assert read_settings(path).person_box_config.merge_candidates is value


@pytest.mark.parametrize("value", [True, False])
def test_app_settings_round_trip(service, value: bool) -> None:
    settings = AppSettings()
    settings.person_box_config.merge_candidates = value
    service.save(settings)

    again = AppSettingsService()
    again.SETTINGS_PATH = service.SETTINGS_PATH
    assert again.load().person_box_config.merge_candidates is value


# --- Independence of the three settings (18.1, 18.5) -----------------------


def test_stored_values_are_independent_in_project_settings(tmp_path) -> None:
    path = tmp_path / "settings.json"
    write_settings(
        ProjectSettings(
            person_box_config=PersonBoxConfig(research=False, merge_candidates=True),
            person_list_config=PersonListConfig(research=True),
        ),
        path,
    )
    loaded = read_settings(path)
    assert loaded.person_box_config.research is False
    assert loaded.person_box_config.merge_candidates is True
    assert loaded.person_list_config.research is True

    loaded.person_box_config.merge_candidates = False
    write_settings(loaded, path)
    again = read_settings(path)
    assert again.person_box_config.research is False
    assert again.person_box_config.merge_candidates is False
    assert again.person_list_config.research is True


def test_stored_values_are_independent_in_app_settings(service) -> None:
    settings = AppSettings()
    settings.person_box_config.research = False
    settings.person_box_config.merge_candidates = True
    settings.person_list_config.research = True
    service.save(settings)

    loaded = service.load()
    loaded.person_list_config.research = False
    service.save(loaded)
    loaded = service.load()
    assert loaded.person_box_config.research is False
    assert loaded.person_box_config.merge_candidates is True
    assert loaded.person_list_config.research is False


def test_dialog_checkboxes_never_change_each_others_stored_value(qapp) -> None:
    dialog = _dialog(
        PersonBoxConfig(research=True, merge_candidates=True),
        PersonListConfig(research=True),
    )

    def state():
        return (
            dialog.person_box_config.research,
            dialog.person_box_config.merge_candidates,
            dialog.person_list_config.research,
        )

    dialog._pl_check_research.setChecked(False)
    assert state() == (True, True, False)
    dialog._pl_check_research.setChecked(True)
    dialog._check_merge_candidates.setChecked(False)
    assert state() == (True, False, True)
    dialog._check_merge_candidates.setChecked(True)
    dialog._check_research.setChecked(False)
    assert state() == (False, True, True)
