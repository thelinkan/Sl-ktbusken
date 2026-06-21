"""Property-based tests for PersonBoxItem DNA company text placeholder.

Feature: enhanced-name-cards, Property 5: DNA company text placeholder uses first 2 characters

Validates: Requirements 2.4
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.widgets.person_box import PersonBoxItem


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestDnaCompanyTextPlaceholder:
    """Feature: enhanced-name-cards, Property 5: DNA company text placeholder uses first 2 characters

    For any DNA company with no logo_media_id, the text placeholder
    rendered is exactly the first 2 characters of the company name.

    **Validates: Requirements 2.4**
    """

    @given(
        company_name=st.text(
            min_size=2,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("L", "N")),
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_dna_placeholder_uses_first_2_characters(
        self,
        company_name: str,
    ) -> None:
        """Property 5: DNA company text placeholder uses first 2 characters.

        Generate DNA companies with no logo and various name strings.
        Verify that the text placeholder is exactly the first 2 characters
        of the company name.

        Feature: enhanced-name-cards, Property 5: DNA company text placeholder uses first 2 characters
        **Validates: Requirements 2.4**
        """
        display_data: dict = {
            "name": "Test Person",
            "dna_companies": [{"name": company_name, "logo": None}],
        }
        config = PersonBoxConfig(name=True, dna_info=True)
        item = PersonBoxItem(
            person_id="person_1",
            display_data=display_data,
            config=config,
        )

        # Use a mock painter to capture drawText calls during paint()
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

        # Find the drawText call that uses AlignCenter — this is the DNA
        # placeholder (other text uses AlignLeft or positional drawText).
        draw_text_calls = [
            c for c in painter.method_calls if c[0] == "drawText"
        ]

        # Filter for calls using Qt.AlignmentFlag.AlignCenter
        placeholder_calls = [
            c
            for c in draw_text_calls
            if len(c[1]) >= 3
            and c[1][1] == Qt.AlignmentFlag.AlignCenter
        ]

        assert len(placeholder_calls) >= 1, (
            f"Expected at least one drawText call with AlignCenter for "
            f"DNA placeholder, but found none. "
            f"All drawText calls: {draw_text_calls}"
        )

        # The text argument is the third positional arg (rect, alignment, text)
        placeholder_text = placeholder_calls[0][1][2]
        expected_text = company_name[:2]

        assert placeholder_text == expected_text, (
            f"With company_name={company_name!r}: "
            f"expected placeholder text {expected_text!r}, "
            f"got {placeholder_text!r}"
        )
