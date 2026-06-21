"""Property-based tests for PersonBoxItem DNA logo alphabetical ordering.

Feature: enhanced-name-cards, Property 4: DNA logos are ordered alphabetically

Validates: Requirements 2.2
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


class TestDnaLogoOrderingProperty:
    """Feature: enhanced-name-cards, Property 4: DNA logos are ordered alphabetically

    Generate sets of DNA companies with random names (pre-sorted alphabetically
    as the view renderer would do). Verify logos are rendered left-to-right in
    alphabetical order by company name.

    **Validates: Requirements 2.2**
    """

    @given(
        company_names=st.lists(
            st.text(
                min_size=2,
                max_size=20,
                alphabet=st.characters(whitelist_categories=("L",)),
            ),
            min_size=2,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_dna_logos_rendered_in_alphabetical_order(
        self,
        company_names: list[str],
    ) -> None:
        """Property 4: DNA logos are ordered alphabetically.

        The view renderer pre-sorts the dna_companies list alphabetically.
        When PersonBoxItem renders them, the x positions must increase
        left-to-right matching the alphabetical order of company names.

        Feature: enhanced-name-cards, Property 4: DNA logos are ordered alphabetically
        **Validates: Requirements 2.2**
        """
        # Sort alphabetically as the view renderer would
        sorted_names = sorted(company_names)

        # Build dna_companies list with logo=None to trigger text placeholders
        dna_companies = [
            {"name": name, "logo": None} for name in sorted_names
        ]

        display_data: dict = {
            "name": "Test Person",
            "dna_companies": dna_companies,
        }
        config = PersonBoxConfig(name=True, dna_info=True)
        item = PersonBoxItem(
            person_id="person_1",
            display_data=display_data,
            config=config,
        )

        # Use a mock painter to capture draw calls
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

        # Extract drawText calls that use AlignCenter (DNA placeholders)
        # DNA placeholders are drawn with:
        #   painter.drawText(logo_rect, Qt.AlignmentFlag.AlignCenter, text)
        draw_text_calls = [
            c for c in painter.method_calls if c[0] == "drawText"
        ]

        # Filter for AlignCenter calls (DNA placeholder text)
        # These calls have signature: drawText(QRectF, AlignCenter, str)
        dna_text_calls = []
        for call in draw_text_calls:
            args = call[1]
            if len(args) == 3 and args[1] == Qt.AlignmentFlag.AlignCenter:
                dna_text_calls.append(args)

        # We should have exactly len(sorted_names) placeholder texts
        assert len(dna_text_calls) == len(sorted_names), (
            f"Expected {len(sorted_names)} DNA placeholder drawText calls, "
            f"got {len(dna_text_calls)}"
        )

        # Verify texts match the expected order (first 2 chars of each name)
        expected_texts = [name[:2] for name in sorted_names]
        actual_texts = [call[2] for call in dna_text_calls]

        assert actual_texts == expected_texts, (
            f"DNA placeholder texts not in alphabetical order. "
            f"Expected: {expected_texts}, got: {actual_texts}"
        )

        # Verify x positions are strictly increasing (left-to-right)
        x_positions = [call[0].x() for call in dna_text_calls]
        for i in range(1, len(x_positions)):
            assert x_positions[i] > x_positions[i - 1], (
                f"DNA logo x positions not increasing at index {i}: "
                f"x[{i-1}]={x_positions[i-1]}, x[{i}]={x_positions[i]}. "
                f"Names: {sorted_names}"
            )
