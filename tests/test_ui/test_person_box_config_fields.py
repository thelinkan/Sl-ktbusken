"""Unit tests for PersonBoxConfig new fields and _BOX_WIDTH constant.

Verifies that the cause_of_death and clusters fields default to False,
and that the _BOX_WIDTH constant is 240.0 pixels.
Covers Requirements 6.3, 7.5, 8.1.
"""

from __future__ import annotations

from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.widgets.person_box import _BOX_WIDTH


class TestPersonBoxConfigNewFields:
    """Tests for cause_of_death and clusters fields on PersonBoxConfig."""

    def test_cause_of_death_defaults_to_true(self) -> None:
        """cause_of_death field defaults to True (enabled by default)."""
        config = PersonBoxConfig()
        assert config.cause_of_death is True

    def test_clusters_defaults_to_true(self) -> None:
        """clusters field defaults to True (enabled by default)."""
        config = PersonBoxConfig()
        assert config.clusters is True

    def test_cause_of_death_can_be_disabled(self) -> None:
        config = PersonBoxConfig(cause_of_death=False)
        assert config.cause_of_death is False

    def test_clusters_can_be_disabled(self) -> None:
        config = PersonBoxConfig(clusters=False)
        assert config.clusters is False


class TestBoxWidth:
    """Tests for the _BOX_WIDTH constant in person_box.py."""

    def test_box_width_is_240(self) -> None:
        """Requirement 8.1: Name card default width is 240 pixels."""
        assert _BOX_WIDTH == 240.0
