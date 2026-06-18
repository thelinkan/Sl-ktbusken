"""Property-based tests for PersonBoxItem border precedence.

Feature: ui-enhancements, Property 6: Ancestor border precedence

Validates: Requirements 4.4
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QApplication

from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.widgets.person_box import (
    PersonBoxItem,
    _ANCESTOR_BORDER_COLOR,
    _BORDER_COLOR,
    _DESCENDANT_BORDER_COLOR,
)


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestAncestorBorderPrecedence:
    """Feature: ui-enhancements, Property 6: Ancestor border precedence

    Generate random boolean pairs (is_ancestor, is_descendant), verify
    when both True the border color is always ancestor red.

    **Validates: Requirements 4.4**
    """

    @given(
        is_ancestor=st.booleans(),
        is_descendant=st.booleans(),
    )
    @settings(max_examples=100, deadline=None)
    def test_ancestor_border_takes_precedence_over_descendant(
        self, is_ancestor: bool, is_descendant: bool
    ) -> None:
        """Property 6: When is_ancestor is True, the border color is
        always ancestor red (#C0392B) regardless of is_descendant value.

        Feature: ui-enhancements, Property 6: Ancestor border precedence
        **Validates: Requirements 4.4**
        """
        display_data: dict = {
            "name": "Test Person",
            "is_ancestor": is_ancestor,
            "is_descendant": is_descendant,
        }
        config = PersonBoxConfig(name=True)
        item = PersonBoxItem(
            person_id="person_1",
            display_data=display_data,
            config=config,
        )

        # Use a mock painter to capture the pen set during paint()
        painter = MagicMock()
        option = MagicMock()

        with patch(
            "slaktbusken.ui.widgets.person_box.icon_registry"
        ) as mock_registry:
            mock_pixmap = MagicMock()
            mock_pixmap.isNull.return_value = True
            mock_registry.get_gender_icon.return_value = mock_pixmap
            item.paint(painter, option, None)

        # Extract the pen that was set for the border (the setPen call
        # before drawRoundedRect). The first setPen call in paint() is
        # for the border.
        set_pen_calls = [
            c for c in painter.method_calls if c[0] == "setPen"
        ]
        assert len(set_pen_calls) >= 1, "Expected at least one setPen call"

        # The first setPen call is the border pen
        border_pen: QPen = set_pen_calls[0][1][0]
        border_color: QColor = border_pen.color()

        if is_ancestor:
            # Ancestor always takes precedence — border must be red
            assert border_color == _ANCESTOR_BORDER_COLOR, (
                f"When is_ancestor=True, is_descendant={is_descendant}: "
                f"expected ancestor red {_ANCESTOR_BORDER_COLOR.name()}, "
                f"got {border_color.name()}"
            )
        elif is_descendant:
            # Only descendant — border must be green
            assert border_color == _DESCENDANT_BORDER_COLOR, (
                f"When is_ancestor=False, is_descendant=True: "
                f"expected descendant green {_DESCENDANT_BORDER_COLOR.name()}, "
                f"got {border_color.name()}"
            )
        else:
            # Neither — default border color
            assert border_color == _BORDER_COLOR, (
                f"When is_ancestor=False, is_descendant=False: "
                f"expected default {_BORDER_COLOR.name()}, "
                f"got {border_color.name()}"
            )
