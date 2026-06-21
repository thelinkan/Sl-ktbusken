"""Property-based tests for PersonBoxItem border color precedence.

Feature: enhanced-name-cards, Property 6: Border color precedence chain

Validates: Requirements 3.1, 3.2, 3.3, 3.4
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
    _MAIN_PERSON_BORDER_COLOR,
    _SELECTED_BORDER_COLOR,
)


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestBorderColorPrecedenceChain:
    """Feature: enhanced-name-cards, Property 6: Border color precedence chain

    Generate all boolean combinations of (is_selected, is_main_person,
    is_ancestor, is_descendant) and verify the correct border color and
    width is applied per the priority chain:

    selected (blue, 2.5px) > main person (orange, 2.5px) >
    ancestor (red, 2.0px) > descendant (green, 2.0px) > default (gray, 1.0px)

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
    """

    @given(
        is_selected=st.booleans(),
        is_main_person=st.booleans(),
        is_ancestor=st.booleans(),
        is_descendant=st.booleans(),
    )
    @settings(max_examples=100, deadline=None)
    def test_border_color_precedence_chain(
        self,
        is_selected: bool,
        is_main_person: bool,
        is_ancestor: bool,
        is_descendant: bool,
    ) -> None:
        """Property 6: Border color follows strict priority chain.

        Priority: selected (blue, 2.5) > main person (orange, 2.5) >
        ancestor (red, 2.0) > descendant (green, 2.0) > default (gray, 1.0).

        Feature: enhanced-name-cards, Property 6: Border color precedence chain
        **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
        """
        display_data: dict = {
            "name": "Test Person",
            "is_ancestor": is_ancestor,
            "is_descendant": is_descendant,
            "is_main_person": is_main_person,
        }
        config = PersonBoxConfig(name=True)
        item = PersonBoxItem(
            person_id="person_1",
            display_data=display_data,
            config=config,
        )

        # Set selection state
        item.set_selected(is_selected)

        # Use a mock painter to capture the pen set during paint()
        painter = MagicMock()
        option = MagicMock()

        with patch(
            "slaktbusken.ui.widgets.person_box.icon_registry"
        ) as mock_registry:
            mock_pixmap = MagicMock()
            mock_pixmap.isNull.return_value = True
            mock_registry.get_gender_icon.return_value = mock_pixmap
            mock_registry.get_multiple_names_icon.return_value = mock_pixmap
            item.paint(painter, option, None)

        # Extract the pen that was set for the border (the first setPen call)
        set_pen_calls = [
            c for c in painter.method_calls if c[0] == "setPen"
        ]
        assert len(set_pen_calls) >= 1, "Expected at least one setPen call"

        # The first setPen call is the border pen
        border_pen: QPen = set_pen_calls[0][1][0]
        border_color: QColor = border_pen.color()
        border_width: float = border_pen.widthF()

        # Determine expected color and width based on priority chain
        if is_selected:
            expected_color = _SELECTED_BORDER_COLOR
            expected_width = 2.5
            label = "selected (blue)"
        elif is_main_person:
            expected_color = _MAIN_PERSON_BORDER_COLOR
            expected_width = 2.5
            label = "main person (orange)"
        elif is_ancestor:
            expected_color = _ANCESTOR_BORDER_COLOR
            expected_width = 2.0
            label = "ancestor (red)"
        elif is_descendant:
            expected_color = _DESCENDANT_BORDER_COLOR
            expected_width = 2.0
            label = "descendant (green)"
        else:
            expected_color = _BORDER_COLOR
            expected_width = 1.0
            label = "default (gray)"

        assert border_color == expected_color, (
            f"With is_selected={is_selected}, is_main_person={is_main_person}, "
            f"is_ancestor={is_ancestor}, is_descendant={is_descendant}: "
            f"expected {label} color {expected_color.name()}, "
            f"got {border_color.name()}"
        )
        assert border_width == pytest.approx(expected_width, abs=0.01), (
            f"With is_selected={is_selected}, is_main_person={is_main_person}, "
            f"is_ancestor={is_ancestor}, is_descendant={is_descendant}: "
            f"expected {label} width {expected_width}, got {border_width}"
        )
