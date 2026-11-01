"""Settings dialog labels for research and merge-candidate indicators.

**Validates: Requirements 17.1, 17.2, 17.3, 18.1, 18.2, 18.3**
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.persistence.settings_io import (
    DiagramSettings,
    PersonBoxConfig,
    PersonListConfig,
)
from slaktbusken.ui.dialogs.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _dialog(box: PersonBoxConfig | None = None) -> SettingsDialog:
    return SettingsDialog(
        box or PersonBoxConfig(), DiagramSettings(), PersonListConfig()
    )


def test_labels(qapp) -> None:
    dialog = _dialog()
    assert dialog._pl_check_research.text() == "Forskningsuppslag och dubletter"
    assert dialog._check_research.text() == "Forskningsuppslag"
    assert dialog._check_merge_candidates.text() == "Sammanslagningskandidater"


def test_diagram_checkboxes_are_independent(qapp) -> None:
    dialog = _dialog(PersonBoxConfig(research=True, merge_candidates=True))
    dialog._check_merge_candidates.setChecked(False)
    assert dialog.person_box_config.research is True
    assert dialog.person_box_config.merge_candidates is False
    dialog._check_merge_candidates.setChecked(True)
    dialog._check_research.setChecked(False)
    assert dialog.person_box_config.research is False
    assert dialog.person_box_config.merge_candidates is True
