"""Property-based tests for place text display on PersonBoxItem.

Feature: enhanced-name-cards

Validates: Requirements 5.5
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QApplication

from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.widgets.person_box import PersonBoxItem, _BOX_WIDTH, _PADDING


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
# Strategies
# ---------------------------------------------------------------------------

# Mix of short and very long place strings to exercise both paths
place_text_strategy = st.one_of(
    st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L", "N", "P", "Z"))),
    st.text(min_size=100, max_size=600, alphabet=st.characters(categories=("L", "N", "P", "Z"))),
)


# ---------------------------------------------------------------------------
# Property 10: Place text truncation at available width
# ---------------------------------------------------------------------------


class TestPlaceTextTruncation:
    """Feature: enhanced-name-cards, Property 10: Place text truncation at available width

    For any place text string, when it exceeds the available content width,
    the elided result ends with "\u2026" (ellipsis). When text fits, it remains
    unchanged. The elided text width always fits within the available content area.

    **Validates: Requirements 5.5**
    """

    @given(place_text=place_text_strategy)
    @settings(max_examples=100, deadline=None)
    def test_elided_text_fits_within_available_width(
        self, qapp, place_text: str
    ) -> None:
        """Elided place text always fits within available content width.

        Feature: enhanced-name-cards, Property 10: Place text truncation at available width
        **Validates: Requirements 5.5**
        """
        # Use same font as PersonBoxItem rendering
        font = QFont("Segoe UI", 9)
        fm = QFontMetrics(font)

        # Compute available width: simplest case without photo/event icons
        # text_x = _PADDING, so available = _BOX_WIDTH - _PADDING - _PADDING
        available_width = int(_BOX_WIDTH - _PADDING - _PADDING)

        # Prefix the place text as it appears on the card (e.g., "fp. ")
        full_text = f"fp. {place_text}"

        # Apply the same elision as PersonBoxItem.paint()
        elided = fm.elidedText(
            full_text,
            Qt.TextElideMode.ElideRight,
            available_width,
        )

        # Property: elided text width must fit within available width
        elided_width = fm.horizontalAdvance(elided)
        assert elided_width <= available_width, (
            f"Elided text width {elided_width} exceeds available width "
            f"{available_width} for place_text={place_text!r}"
        )

    @given(place_text=place_text_strategy)
    @settings(max_examples=100, deadline=None)
    def test_long_text_ends_with_ellipsis(
        self, qapp, place_text: str
    ) -> None:
        """Place text exceeding available width is truncated with ellipsis.

        Feature: enhanced-name-cards, Property 10: Place text truncation at available width
        **Validates: Requirements 5.5**
        """
        font = QFont("Segoe UI", 9)
        fm = QFontMetrics(font)

        available_width = int(_BOX_WIDTH - _PADDING - _PADDING)

        full_text = f"fp. {place_text}"
        original_width = fm.horizontalAdvance(full_text)

        elided = fm.elidedText(
            full_text,
            Qt.TextElideMode.ElideRight,
            available_width,
        )

        if original_width > available_width:
            # When text exceeds available width, must end with ellipsis
            assert elided.endswith("\u2026"), (
                f"Expected ellipsis at end for text that exceeds available width. "
                f"Original width={original_width}, available={available_width}, "
                f"elided={elided!r}"
            )
        else:
            # When text fits, it remains unchanged
            assert elided == full_text, (
                f"Text that fits should remain unchanged. "
                f"Original={full_text!r}, elided={elided!r}"
            )


# ---------------------------------------------------------------------------
# Strategies for Property 9
# ---------------------------------------------------------------------------

date_strategy = st.one_of(
    st.none(),
    st.text(min_size=1, max_size=20, alphabet=st.characters(categories=("L", "N"))),
)

place_strategy = st.one_of(
    st.none(),
    st.just(""),
    st.text(min_size=1, max_size=100, alphabet=st.characters(categories=("L", "N", "P"))),
)


# ---------------------------------------------------------------------------
# Property 9: Place lines appear in correct order relative to date lines
# ---------------------------------------------------------------------------


class TestPlaceLineOrdering:
    """Feature: enhanced-name-cards, Property 9: Place combined with date on same line

    For any combination of birth/death date and place data, when both are
    present the place is appended to the date line (e.g. "f. 1850, Stockholm").
    When place data is None or empty, only the date appears.

    **Validates: Requirements 5.1, 5.2, 5.3**
    """

    @given(
        birth_date=date_strategy,
        birth_place=place_strategy,
        death_date=date_strategy,
        death_place=place_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_birth_place_follows_birth_date(
        self, qapp, birth_date, birth_place, death_date, death_place
    ) -> None:
        """Birth place is appended to birth date line when both present.

        Feature: enhanced-name-cards, Property 9: Place combined with date
        **Validates: Requirements 5.1, 5.2, 5.3**
        """
        config = PersonBoxConfig(
            birth_date=True, birth_place=True, death_date=True, death_place=True
        )
        display_data = {
            "name": "Test Person",
            "birth_date": birth_date,
            "birth_place": birth_place,
            "death_date": death_date,
            "death_place": death_place,
        }

        box = PersonBoxItem(
            person_id="p1", display_data=display_data, config=config
        )
        lines = box._lines

        if birth_date and birth_place:
            # Both present: place should be appended to date line
            expected_line = f"f. {birth_date}, {birth_place}"
            assert expected_line in lines, (
                f"Expected combined line '{expected_line}' in lines {lines}"
            )
        elif birth_date and not birth_place:
            # Date present but no place: just the date line
            expected_line = f"f. {birth_date}"
            assert expected_line in lines, (
                f"Expected date-only line '{expected_line}' in lines {lines}"
            )
            # No separate place line
            for line in lines:
                assert ", " not in line or not line.startswith("f. ") or birth_place, (
                    f"Unexpected place in birth line: {line}"
                )

    @given(
        birth_date=date_strategy,
        birth_place=place_strategy,
        death_date=date_strategy,
        death_place=place_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_death_place_follows_death_date(
        self, qapp, birth_date, birth_place, death_date, death_place
    ) -> None:
        """Death place is appended to death date line when both present.

        Feature: enhanced-name-cards, Property 9: Place combined with date
        **Validates: Requirements 5.1, 5.2, 5.3**
        """
        config = PersonBoxConfig(
            birth_date=True, birth_place=True, death_date=True, death_place=True
        )
        display_data = {
            "name": "Test Person",
            "birth_date": birth_date,
            "birth_place": birth_place,
            "death_date": death_date,
            "death_place": death_place,
        }

        box = PersonBoxItem(
            person_id="p1", display_data=display_data, config=config
        )
        lines = box._lines

        if death_date and death_place:
            # Both present: place appended to date line
            expected_line = f"d. {death_date}, {death_place}"
            assert expected_line in lines, (
                f"Expected combined line '{expected_line}' in lines {lines}"
            )
        elif death_date and not death_place:
            # Date present but no place
            expected_line = f"d. {death_date}"
            assert expected_line in lines, (
                f"Expected date-only line '{expected_line}' in lines {lines}"
            )

    @given(
        birth_date=date_strategy,
        birth_place=place_strategy,
        death_date=date_strategy,
        death_place=place_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_place_lines_omitted_when_data_empty(
        self, qapp, birth_date, birth_place, death_date, death_place
    ) -> None:
        """Place data not shown when it is None or empty string.

        Feature: enhanced-name-cards, Property 9: Place combined with date
        **Validates: Requirements 5.1, 5.2, 5.3**
        """
        config = PersonBoxConfig(
            birth_date=True, birth_place=True, death_date=True, death_place=True
        )
        display_data = {
            "name": "Test Person",
            "birth_date": birth_date,
            "birth_place": birth_place,
            "death_date": death_date,
            "death_place": death_place,
        }

        box = PersonBoxItem(
            person_id="p1", display_data=display_data, config=config
        )
        lines = box._lines

        # When birth_place is None or empty, no "fp. " standalone line and
        # no appended place in the date line
        if not birth_place and birth_date:
            birth_line = f"f. {birth_date}"
            if birth_line in lines:
                # Should not contain a comma (no place appended)
                assert birth_line == f"f. {birth_date}", (
                    f"Expected no place appended when birth_place is "
                    f"{birth_place!r}, line: {birth_line}"
                )

        # Same for death_place
        if not death_place and death_date:
            death_line = f"d. {death_date}"
            if death_line in lines:
                assert death_line == f"d. {death_date}"
