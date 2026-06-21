"""Property-based tests for multiple names indicator on PersonBoxItem.

Feature: enhanced-name-cards

Validates: Requirements 1.1, 1.3, 1.4
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from PySide6.QtCore import QRectF, Qt
from PySide6.QtWidgets import QApplication

from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.widgets.person_box import (
    PersonBoxItem,
    _MULTIPLE_NAMES_ICON_SIZE,
    _PADDING,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def person_box_config_strategy(draw: DrawFn) -> PersonBoxConfig:
    """Generate PersonBoxConfig with all boolean fields randomized."""
    return PersonBoxConfig(
        name=draw(st.booleans()),
        birth_date=draw(st.booleans()),
        birth_place=draw(st.booleans()),
        death_date=draw(st.booleans()),
        death_place=draw(st.booleans()),
        marriage_date=draw(st.booleans()),
        marriage_place=draw(st.booleans()),
        occupation=draw(st.booleans()),
        photo=draw(st.booleans()),
        dna_info=draw(st.booleans()),
        notes=draw(st.booleans()),
        cause_of_death=draw(st.booleans()),
        clusters=draw(st.booleans()),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _drawText_called_with_marker(painter_mock: MagicMock) -> bool:
    """Check if painter.drawText was called with the '≡' marker character."""
    for c in painter_mock.drawText.call_args_list:
        args = c[0] if c[0] else ()
        if len(args) >= 3 and args[2] == "≡":
            return True
    return False


# ---------------------------------------------------------------------------
# Fixture for QApplication (required for Qt widget tests)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# Property 1: Multiple names indicator biconditional
# ---------------------------------------------------------------------------


class TestMultipleNamesIndicatorBiconditional:
    """Feature: enhanced-name-cards, Property 1: Multiple names indicator biconditional

    For any Person, the multiple names indicator is drawn if and only if
    len(person.names) > 1. When len(names) == 1, no indicator is drawn;
    when len(names) > 1, the indicator is always drawn.

    **Validates: Requirements 1.1, 1.3**
    """

    @given(name_count=st.integers(min_value=1, max_value=15))
    @settings(max_examples=100)
    def test_indicator_drawn_iff_multiple_names(
        self, qapp, name_count: int
    ) -> None:
        """Multiple names indicator is drawn iff has_multiple_names is True.

        Feature: enhanced-name-cards, Property 1: Multiple names indicator biconditional
        **Validates: Requirements 1.1, 1.3**
        """
        has_multiple = name_count > 1

        display_data = {
            "name": "Test Person",
            "has_multiple_names": has_multiple,
            "sex": "M",
        }

        config = PersonBoxConfig()
        box = PersonBoxItem("person_1", display_data, config)

        # Mock painter — need to mock save/restore too
        painter = MagicMock()

        box._paint_multiple_names_icon(painter)

        if has_multiple:
            # Indicator MUST be drawn when person has multiple names
            assert _drawText_called_with_marker(painter), (
                "Expected '≡' marker to be drawn when has_multiple_names is True"
            )
        else:
            # Indicator MUST NOT be drawn when person has exactly one name
            assert not _drawText_called_with_marker(painter), (
                "Expected no '≡' marker when has_multiple_names is False"
            )


# ---------------------------------------------------------------------------
# Property 2: Multiple names indicator is config-independent
# ---------------------------------------------------------------------------


class TestMultipleNamesIndicatorConfigIndependence:
    """Feature: enhanced-name-cards, Property 2: Multiple names indicator is config-independent

    For any PersonBoxConfig toggle combination and any Person with multiple
    names, the multiple names indicator is always rendered regardless of
    which config fields are enabled or disabled.

    **Validates: Requirements 1.4**
    """

    @given(config=person_box_config_strategy())
    @settings(max_examples=100)
    def test_indicator_always_drawn_regardless_of_config(
        self, qapp, config: PersonBoxConfig
    ) -> None:
        """Multiple names indicator is always rendered regardless of config toggles.

        Feature: enhanced-name-cards, Property 2: Multiple names indicator is config-independent
        **Validates: Requirements 1.4**
        """
        display_data = {
            "name": "Test Person",
            "has_multiple_names": True,
            "sex": "M",
        }

        box = PersonBoxItem("person_1", display_data, config)

        # Mock painter
        painter = MagicMock()

        box._paint_multiple_names_icon(painter)

        # Assert the "≡" marker was drawn regardless of config
        assert _drawText_called_with_marker(painter), (
            f"Expected '≡' marker to be drawn with config={config}"
        )
