"""Unit tests for PersonBoxItem tilltalsnamn (underline) rendering.

Verifies that the person box renders the tilltalsnamn part with an
underline decoration, and that names without a marker render without
underline. Covers Requirements 2.1, 2.2, 2.3, 2.4, 2.5.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QPen
from PySide6.QtWidgets import QApplication

from slaktbusken.model.name_parser import ParsedGivenName, parse_given_name
from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.widgets.person_box import PersonBoxItem


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestPersonBoxNameRendering:
    """Tests for PersonBoxItem._paint_name_line tilltalsnamn rendering."""

    def _create_item(
        self, name: str, name_parsed: ParsedGivenName | None
    ) -> PersonBoxItem:
        """Helper to create a PersonBoxItem with name data.

        Args:
            name: The display name string.
            name_parsed: The ParsedGivenName result (or None).

        Returns:
            A PersonBoxItem configured for testing.
        """
        config = PersonBoxConfig(name=True)
        display_data: dict = {"name": name}
        if name_parsed is not None:
            display_data["name_parsed"] = name_parsed
        return PersonBoxItem("test_person", display_data, config)

    def test_marked_name_sets_underline_on_tilltalsnamn_part(self) -> None:
        """Req 2.1: Marked name renders tilltalsnamn with underline.

        When name_parsed has a tilltalsnamn_index, the paint method
        should call setFont with underline=True for that part only.
        """
        parsed = parse_given_name("Kent Torbjörn*")
        item = self._create_item("Kent Torbjörn", parsed)

        painter = MagicMock()
        # QFontMetrics needs to return numeric values for horizontalAdvance
        with patch(
            "slaktbusken.ui.widgets.person_box.QFontMetrics"
        ) as mock_fm_class:
            mock_fm = MagicMock()
            mock_fm.horizontalAdvance.return_value = 50
            mock_fm_class.return_value = mock_fm

            item._paint_name_line(painter, 20.0)

        # Collect all setFont calls
        set_font_calls = [c for c in painter.method_calls if c[0] == "setFont"]
        assert len(set_font_calls) >= 2, (
            "Expected at least 2 setFont calls (one per name part)"
        )

        # The first name part "Kent" should NOT be underlined
        first_font = set_font_calls[0][1][0]  # first positional arg
        assert isinstance(first_font, QFont)
        assert not first_font.underline(), "First part 'Kent' should not be underlined"

        # The second name part "Torbjörn" should be underlined
        second_font = set_font_calls[1][1][0]
        assert isinstance(second_font, QFont)
        assert second_font.underline(), "Tilltalsnamn 'Torbjörn' should be underlined"

    def test_marked_name_draws_each_part_individually(self) -> None:
        """Req 2.4: All parts drawn in order on the same line.

        When tilltalsnamn is present, each name part is drawn
        individually with drawText(x, y, part).
        """
        parsed = parse_given_name("Kent Torbjörn*")
        item = self._create_item("Kent Torbjörn", parsed)

        painter = MagicMock()
        with patch(
            "slaktbusken.ui.widgets.person_box.QFontMetrics"
        ) as mock_fm_class:
            mock_fm = MagicMock()
            mock_fm.horizontalAdvance.return_value = 40
            mock_fm_class.return_value = mock_fm

            item._paint_name_line(painter, 20.0)

        # Verify drawText was called for each part
        draw_text_calls = [
            c for c in painter.method_calls if c[0] == "drawText"
        ]
        # Should have 2 drawText calls (one per name part)
        assert len(draw_text_calls) == 2
        # First call draws "Kent"
        assert draw_text_calls[0][1][2] == "Kent"
        # Second call draws "Torbjörn"
        assert draw_text_calls[1][1][2] == "Torbjörn"

    def test_no_marker_renders_without_underline(self) -> None:
        """Req 2.2: No marker means no underline.

        When name_parsed has tilltalsnamn_index=None, the paint method
        renders the full name string with drawText (via QRectF overload)
        without any underline font.
        """
        parsed = parse_given_name("Erik Johan")
        item = self._create_item("Erik Johan", parsed)

        painter = MagicMock()
        item._paint_name_line(painter, 20.0)

        # Verify setFont was called with a bold font WITHOUT underline
        set_font_calls = [c for c in painter.method_calls if c[0] == "setFont"]
        assert len(set_font_calls) >= 1
        for font_call in set_font_calls:
            font = font_call[1][0]
            assert isinstance(font, QFont)
            assert not font.underline(), (
                "No-marker name should never have underline set"
            )

        # Verify drawText is called once with the full name string
        draw_text_calls = [
            c for c in painter.method_calls if c[0] == "drawText"
        ]
        assert len(draw_text_calls) == 1
        # The QRectF overload: drawText(QRectF, alignment, text)
        assert draw_text_calls[0][1][2] == "Erik Johan"

    def test_no_name_parsed_key_renders_without_underline(self) -> None:
        """Req 2.2: Missing name_parsed falls back to normal rendering.

        If display_data has no "name_parsed" key, the paint method
        renders without underline.
        """
        item = self._create_item("Anna Svensson", None)

        painter = MagicMock()
        item._paint_name_line(painter, 20.0)

        # Verify no underlined font
        set_font_calls = [c for c in painter.method_calls if c[0] == "setFont"]
        for font_call in set_font_calls:
            font = font_call[1][0]
            assert not font.underline()

        # Single drawText call with full name
        draw_text_calls = [
            c for c in painter.method_calls if c[0] == "drawText"
        ]
        assert len(draw_text_calls) == 1
        assert draw_text_calls[0][1][2] == "Anna Svensson"

    def test_first_name_marked_underlines_first_part_only(self) -> None:
        """Req 2.1, 2.4: First name marked underlines only first part.

        When the marker is on the first name (index 0), only that part
        gets underlined; subsequent parts do not.
        """
        parsed = parse_given_name("Anna* Maria")
        item = self._create_item("Anna Maria", parsed)

        painter = MagicMock()
        with patch(
            "slaktbusken.ui.widgets.person_box.QFontMetrics"
        ) as mock_fm_class:
            mock_fm = MagicMock()
            mock_fm.horizontalAdvance.return_value = 40
            mock_fm_class.return_value = mock_fm

            item._paint_name_line(painter, 20.0)

        set_font_calls = [c for c in painter.method_calls if c[0] == "setFont"]
        # First font (for "Anna") should be underlined
        first_font = set_font_calls[0][1][0]
        assert first_font.underline(), "First part 'Anna' should be underlined"

        # Second font (for "Maria") should NOT be underlined
        second_font = set_font_calls[1][1][0]
        assert not second_font.underline(), "Second part 'Maria' should not be underlined"

    def test_asterisk_not_displayed_in_rendered_text(self) -> None:
        """Req 2.3: Raw asterisk is never displayed.

        The drawText calls should never include '*' in the text.
        """
        parsed = parse_given_name("Kent Torbjörn*")
        item = self._create_item("Kent Torbjörn", parsed)

        painter = MagicMock()
        with patch(
            "slaktbusken.ui.widgets.person_box.QFontMetrics"
        ) as mock_fm_class:
            mock_fm = MagicMock()
            mock_fm.horizontalAdvance.return_value = 40
            mock_fm_class.return_value = mock_fm

            item._paint_name_line(painter, 20.0)

        draw_text_calls = [
            c for c in painter.method_calls if c[0] == "drawText"
        ]
        for dt_call in draw_text_calls:
            # Check all string args for absence of '*'
            for arg in dt_call[1]:
                if isinstance(arg, str):
                    assert "*" not in arg, (
                        f"Asterisk found in rendered text: {arg}"
                    )

    def test_multiple_markers_underlines_only_first_marked(self) -> None:
        """Req 2.5: Multiple markers underlines only first marked part.

        If parse_given_name raises ValueError for multiple markers,
        the PersonBox falls back. But per Req 2.5, if we construct a
        ParsedGivenName manually with only the first marker index,
        only that part gets underlined.
        """
        # Simulate the case where the display layer has already resolved
        # multiple markers to just the first one (as per Req 2.5)
        parsed = ParsedGivenName(
            parts=["Karl", "Erik", "Lars"],
            tilltalsnamn_index=0,  # First marked part
            display_string="Karl Erik Lars",
            raw="Karl* Erik* Lars",
        )
        item = self._create_item("Karl Erik Lars", parsed)

        painter = MagicMock()
        with patch(
            "slaktbusken.ui.widgets.person_box.QFontMetrics"
        ) as mock_fm_class:
            mock_fm = MagicMock()
            mock_fm.horizontalAdvance.return_value = 35
            mock_fm_class.return_value = mock_fm

            item._paint_name_line(painter, 20.0)

        set_font_calls = [c for c in painter.method_calls if c[0] == "setFont"]
        # First part "Karl" should be underlined
        first_font = set_font_calls[0][1][0]
        assert first_font.underline(), "First marked part 'Karl' should be underlined"

        # Second part "Erik" should NOT be underlined
        second_font = set_font_calls[1][1][0]
        assert not second_font.underline(), "'Erik' should not be underlined"

        # Third part "Lars" should NOT be underlined
        third_font = set_font_calls[2][1][0]
        assert not third_font.underline(), "'Lars' should not be underlined"

    def test_single_name_with_marker_underlines_it(self) -> None:
        """Req 2.1: Single name with marker is underlined.

        A person with only one given name marked (e.g., "Anna*")
        should render that single name underlined.
        """
        parsed = parse_given_name("Anna*")
        item = self._create_item("Anna", parsed)

        painter = MagicMock()
        with patch(
            "slaktbusken.ui.widgets.person_box.QFontMetrics"
        ) as mock_fm_class:
            mock_fm = MagicMock()
            mock_fm.horizontalAdvance.return_value = 40
            mock_fm_class.return_value = mock_fm

            item._paint_name_line(painter, 20.0)

        set_font_calls = [c for c in painter.method_calls if c[0] == "setFont"]
        # The font for "Anna" should be underlined
        anna_font = set_font_calls[0][1][0]
        assert anna_font.underline(), "Single marked name 'Anna' should be underlined"

        # Verify drawText was called with "Anna" (no asterisk)
        draw_text_calls = [
            c for c in painter.method_calls if c[0] == "drawText"
        ]
        assert len(draw_text_calls) == 1
        assert draw_text_calls[0][1][2] == "Anna"

    def test_empty_parts_falls_back_to_normal(self) -> None:
        """Edge case: empty ParsedGivenName falls back to normal rendering.

        If name_parsed has empty parts but is not None, the method
        should fall back to normal rendering.
        """
        parsed = ParsedGivenName(
            parts=[],
            tilltalsnamn_index=None,
            display_string="",
            raw="",
        )
        config = PersonBoxConfig(name=True)
        display_data = {"name": "(okänd)", "name_parsed": parsed}
        item = PersonBoxItem("test_person", display_data, config)

        painter = MagicMock()
        item._paint_name_line(painter, 20.0)

        # Should fall back to normal rendering (no crash)
        set_font_calls = [c for c in painter.method_calls if c[0] == "setFont"]
        for font_call in set_font_calls:
            font = font_call[1][0]
            assert not font.underline()

    def test_surname_drawn_after_given_name_parts(self) -> None:
        """Surname must be drawn after given name parts.

        When the name line is "Kent Torbjörn Svensson" and name_parsed
        only has given-name parts ["Kent", "Torbjörn"], the surname
        "Svensson" must still be rendered after the given name parts.
        """
        parsed = parse_given_name("Kent Torbjörn*")
        # The display_data["name"] includes the surname
        config = PersonBoxConfig(name=True)
        display_data = {
            "name": "Kent Torbjörn Svensson",
            "name_parsed": parsed,
        }
        item = PersonBoxItem("test_person", display_data, config)

        painter = MagicMock()
        with patch(
            "slaktbusken.ui.widgets.person_box.QFontMetrics"
        ) as mock_fm_class:
            mock_fm = MagicMock()
            mock_fm.horizontalAdvance.return_value = 40
            mock_fm_class.return_value = mock_fm

            item._paint_name_line(painter, 20.0)

        draw_text_calls = [
            c for c in painter.method_calls if c[0] == "drawText"
        ]
        # Should have 3 drawText calls: "Kent", "Torbjörn", "Svensson"
        assert len(draw_text_calls) == 3
        assert draw_text_calls[0][1][2] == "Kent"
        assert draw_text_calls[1][1][2] == "Torbjörn"
        assert draw_text_calls[2][1][2] == "Svensson"

    def test_surname_not_underlined(self) -> None:
        """Surname must not be underlined even when tilltalsnamn is marked."""
        parsed = parse_given_name("Kent Torbjörn*")
        config = PersonBoxConfig(name=True)
        display_data = {
            "name": "Kent Torbjörn Svensson",
            "name_parsed": parsed,
        }
        item = PersonBoxItem("test_person", display_data, config)

        painter = MagicMock()
        with patch(
            "slaktbusken.ui.widgets.person_box.QFontMetrics"
        ) as mock_fm_class:
            mock_fm = MagicMock()
            mock_fm.horizontalAdvance.return_value = 40
            mock_fm_class.return_value = mock_fm

            item._paint_name_line(painter, 20.0)

        # The last setFont before drawing "Svensson" should have underline=False
        set_font_calls = [c for c in painter.method_calls if c[0] == "setFont"]
        # Last font set (for surname) should not be underlined
        last_font = set_font_calls[-2][1][0]  # -1 is the restore regular font
        assert isinstance(last_font, QFont)
        assert not last_font.underline(), "Surname should not be underlined"
