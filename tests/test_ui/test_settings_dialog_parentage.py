"""Tests for the Diagram tab parentage controls on the settings dialog.

Covers the Show_Level combo, the badge checkbox, and the fallback checkbox
added to ``SettingsDialog``'s Diagram tab, and that the ``diagram_settings``
property round-trips the three ``DiagramSettings`` parentage fields alongside
the existing depth/compact/background fields.

Requirements: 7.1, 7.2, 7.3, 7.5, 4.1, 4.5, 4.7, 6.1
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.persistence.settings_io import (
    DiagramSettings,
    PersonBoxConfig,
    PersonListConfig,
)
from slaktbusken.ui.dialogs.settings_dialog import SettingsDialog


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_dialog(diagram_settings: DiagramSettings) -> SettingsDialog:
    """Construct a SettingsDialog with the given diagram settings."""
    return SettingsDialog(
        person_box_config=PersonBoxConfig(),
        diagram_settings=diagram_settings,
        person_list_config=PersonListConfig(),
    )


class TestDiagramTabExposesControls:
    """The Diagram tab exposes the three parentage controls."""

    def test_controls_exist(self, qapp):
        """Show_Level combo, badge checkbox, and fallback checkbox are present."""
        dialog = _make_dialog(DiagramSettings())
        assert dialog._combo_parentage_show_level is not None
        assert dialog._check_parentage_badge is not None
        assert dialog._check_parentage_fallback is not None

    def test_show_level_combo_has_three_items(self, qapp):
        """The Show_Level combo offers the three internal values."""
        dialog = _make_dialog(DiagramSettings())
        combo = dialog._combo_parentage_show_level
        values = {combo.itemData(i) for i in range(combo.count())}
        assert values == {"biological", "non_biological", "all"}


class TestControlsReflectConstructionSettings:
    """Constructing the dialog pre-selects/checks the controls."""

    def test_non_default_settings_preselect_controls(self, qapp):
        """Non-default parentage settings are reflected in the controls."""
        settings = DiagramSettings(
            parentage_show_level="non_biological",
            parentage_badge=True,
            parentage_fallback=False,
        )
        dialog = _make_dialog(settings)
        assert dialog._combo_parentage_show_level.currentData() == "non_biological"
        assert dialog._check_parentage_badge.isChecked() is True
        assert dialog._check_parentage_fallback.isChecked() is False

    def test_all_show_level_preselected(self, qapp):
        """The 'all' show level is pre-selected when requested."""
        dialog = _make_dialog(DiagramSettings(parentage_show_level="all"))
        assert dialog._combo_parentage_show_level.currentData() == "all"


class TestDiagramSettingsPropertyRoundTrip:
    """The diagram_settings property reflects the controls and keeps other fields."""

    def test_roundtrip_non_default(self, qapp):
        """Non-default parentage settings round-trip through the property."""
        settings = DiagramSettings(
            ancestry_depth=7,
            descendants_depth=5,
            ancestry_compact=True,
            background_color="#123456",
            parentage_show_level="non_biological",
            parentage_badge=True,
            parentage_fallback=False,
        )
        dialog = _make_dialog(settings)
        result = dialog.diagram_settings

        # Parentage fields round-trip.
        assert result.parentage_show_level == "non_biological"
        assert result.parentage_badge is True
        assert result.parentage_fallback is False

        # Existing fields are unchanged.
        assert result.ancestry_depth == 7
        assert result.descendants_depth == 5
        assert result.ancestry_compact is True
        assert result.background_color == "#123456"

    def test_roundtrip_reflects_control_edits(self, qapp):
        """Editing the controls is reflected in the returned property."""
        dialog = _make_dialog(DiagramSettings())
        idx = dialog._combo_parentage_show_level.findData("all")
        dialog._combo_parentage_show_level.setCurrentIndex(idx)
        dialog._check_parentage_badge.setChecked(True)
        dialog._check_parentage_fallback.setChecked(False)

        result = dialog.diagram_settings
        assert result.parentage_show_level == "all"
        assert result.parentage_badge is True
        assert result.parentage_fallback is False


class TestDefaultsRegression:
    """Default construction yields the documented defaults in the property."""

    def test_default_property_values(self, qapp):
        """Defaults: show_level biological, badge off, fallback on."""
        dialog = _make_dialog(DiagramSettings())
        result = dialog.diagram_settings
        assert result.parentage_show_level == "biological"
        assert result.parentage_badge is False
        assert result.parentage_fallback is True
