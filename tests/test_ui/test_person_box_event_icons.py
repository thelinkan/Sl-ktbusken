"""Unit tests for PersonBoxItem event icon rendering.

Verifies that the person box renders 12×12 event icons adjacent to
birth_date, death_date, and marriage_date lines, offsetting the text
to the right. Covers Requirements 1.3, 1.4.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QPen
from PySide6.QtWidgets import QApplication

from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.widgets.person_box import (
    PersonBoxItem,
    _EVENT_ICON_GAP,
    _EVENT_ICON_SIZE,
    _PADDING,
)


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestPersonBoxEventIcons:
    """Tests for PersonBoxItem event icon rendering (Req 1.3, 1.4)."""

    def test_build_lines_tracks_event_types_for_date_fields(self) -> None:
        """_build_lines populates _line_event_types with correct event types.

        birth_date -> "birth", death_date -> "death", marriage_date -> "marriage".
        Other fields get None.
        """
        config = PersonBoxConfig(
            name=True,
            birth_date=True,
            birth_place=True,
            death_date=True,
            marriage_date=True,
            occupation=True,
        )
        display_data = {
            "name": "Anna Svensson",
            "birth_date": "1850-01-01",
            "birth_place": "Stockholm",
            "death_date": "1920-05-15",
            "marriage_date": "1875-06-20",
            "occupation": "Jordbrukare",
        }
        item = PersonBoxItem("p1", display_data, config)

        # Lines: name, birth_date, birth_place, death_date, marriage_date, occupation
        assert item._line_event_types[0] is None  # name
        assert item._line_event_types[1] == "birth"  # birth_date
        assert item._line_event_types[2] is None  # birth_place
        assert item._line_event_types[3] == "death"  # death_date
        assert item._line_event_types[4] == "marriage"  # marriage_date
        assert item._line_event_types[5] is None  # occupation

    def test_build_lines_no_event_types_for_non_date_fields(self) -> None:
        """Fields without event type mapping get None in _line_event_types."""
        config = PersonBoxConfig(
            name=True,
            birth_place=True,
            occupation=True,
            notes=True,
        )
        display_data = {
            "name": "Erik Larsson",
            "birth_place": "Göteborg",
            "occupation": "Smed",
            "notes": "Anteckning",
        }
        item = PersonBoxItem("p2", display_data, config)

        # All should be None (name, birth_place, occupation, notes)
        assert all(et is None for et in item._line_event_types)

    def test_line_event_types_length_matches_lines(self) -> None:
        """_line_event_types always has same length as _lines."""
        config = PersonBoxConfig(
            name=True,
            birth_date=True,
            death_date=True,
        )
        display_data = {
            "name": "Test Person",
            "birth_date": "1900-01-01",
            "death_date": "1980-12-31",
        }
        item = PersonBoxItem("p3", display_data, config)

        assert len(item._line_event_types) == len(item._lines)

    def test_paint_draws_event_icon_for_birth_date(self) -> None:
        """Req 1.3: Event icon drawn adjacent to birth date line.

        When birth_date is present, paint() should call drawPixmap
        for the birth event icon.
        """
        config = PersonBoxConfig(name=True, birth_date=True)
        display_data = {
            "name": "Test Person",
            "birth_date": "1900-01-01",
        }
        item = PersonBoxItem("p4", display_data, config)

        painter = MagicMock()
        option = MagicMock()

        with patch(
            "slaktbusken.ui.widgets.person_box.icon_registry"
        ) as mock_registry:
            mock_pixmap = MagicMock()
            mock_pixmap.isNull.return_value = False
            mock_registry.get_event_icon.return_value = mock_pixmap
            mock_registry.get_gender_icon.return_value = MagicMock(
                isNull=MagicMock(return_value=True)
            )

            item.paint(painter, option, None)

            # Verify get_event_icon was called with "birth"
            mock_registry.get_event_icon.assert_called_with("birth")

        # Verify drawPixmap was called (for the event icon)
        draw_pixmap_calls = [
            c for c in painter.method_calls if c[0] == "drawPixmap"
        ]
        assert len(draw_pixmap_calls) >= 1, (
            "Expected drawPixmap for birth event icon"
        )

    def test_paint_draws_event_icon_for_death_date(self) -> None:
        """Req 1.3: Event icon drawn adjacent to death date line."""
        config = PersonBoxConfig(name=True, death_date=True)
        display_data = {
            "name": "Test Person",
            "death_date": "1980-12-31",
        }
        item = PersonBoxItem("p5", display_data, config)

        painter = MagicMock()
        option = MagicMock()

        with patch(
            "slaktbusken.ui.widgets.person_box.icon_registry"
        ) as mock_registry:
            mock_pixmap = MagicMock()
            mock_pixmap.isNull.return_value = False
            mock_registry.get_event_icon.return_value = mock_pixmap
            mock_registry.get_gender_icon.return_value = MagicMock(
                isNull=MagicMock(return_value=True)
            )

            item.paint(painter, option, None)

            mock_registry.get_event_icon.assert_called_with("death")

    def test_paint_offsets_text_when_event_icon_present(self) -> None:
        """Req 1.4: Text is offset right by 14px (12 icon + 2 gap) when icon present.

        The drawText call for the birth_date line should use an x offset
        of _PADDING + _EVENT_ICON_SIZE + _EVENT_ICON_GAP.
        """
        config = PersonBoxConfig(name=True, birth_date=True)
        display_data = {
            "name": "Test Person",
            "birth_date": "1900-01-01",
        }
        item = PersonBoxItem("p6", display_data, config)

        painter = MagicMock()
        option = MagicMock()

        with patch(
            "slaktbusken.ui.widgets.person_box.icon_registry"
        ) as mock_registry:
            mock_pixmap = MagicMock()
            mock_pixmap.isNull.return_value = False
            mock_registry.get_event_icon.return_value = mock_pixmap
            mock_registry.get_gender_icon.return_value = MagicMock(
                isNull=MagicMock(return_value=True)
            )

            item.paint(painter, option, None)

        # Find the drawText call for the birth date line
        draw_text_calls = [
            c for c in painter.method_calls if c[0] == "drawText"
        ]
        # Filter to find the one with "f. 1900-01-01"
        expected_text_x = _PADDING + _EVENT_ICON_SIZE + _EVENT_ICON_GAP
        found = False
        for dt_call in draw_text_calls:
            args = dt_call[1]
            if len(args) >= 1 and isinstance(args[0], QRectF):
                rect = args[0]
                if abs(rect.x() - expected_text_x) < 0.01:
                    found = True
                    break
        assert found, (
            f"Expected drawText with x={expected_text_x} for event icon offset"
        )

    def test_paint_no_icon_for_non_event_lines(self) -> None:
        """Lines without event types (e.g. occupation) don't get icons.

        The text_x for non-event lines should remain at _PADDING.
        """
        config = PersonBoxConfig(name=True, occupation=True)
        display_data = {
            "name": "Test Person",
            "occupation": "Smed",
        }
        item = PersonBoxItem("p7", display_data, config)

        painter = MagicMock()
        option = MagicMock()

        with patch(
            "slaktbusken.ui.widgets.person_box.icon_registry"
        ) as mock_registry:
            mock_registry.get_gender_icon.return_value = MagicMock(
                isNull=MagicMock(return_value=True)
            )
            # get_event_icon should NOT be called for occupation
            item.paint(painter, option, None)

            mock_registry.get_event_icon.assert_not_called()

    def test_paint_icon_size_is_12x12(self) -> None:
        """Req 1.4: Event icons in Person_Boxes are 12×12 px."""
        config = PersonBoxConfig(name=True, birth_date=True)
        display_data = {
            "name": "Test Person",
            "birth_date": "1900-01-01",
        }
        item = PersonBoxItem("p8", display_data, config)

        painter = MagicMock()
        option = MagicMock()

        with patch(
            "slaktbusken.ui.widgets.person_box.icon_registry"
        ) as mock_registry:
            mock_pixmap = MagicMock()
            mock_pixmap.isNull.return_value = False
            mock_registry.get_event_icon.return_value = mock_pixmap
            mock_registry.get_gender_icon.return_value = MagicMock(
                isNull=MagicMock(return_value=True)
            )

            item.paint(painter, option, None)

        # Find the drawPixmap call and check the rect size
        draw_pixmap_calls = [
            c for c in painter.method_calls if c[0] == "drawPixmap"
        ]
        assert len(draw_pixmap_calls) >= 1
        # drawPixmap is called with (QRect, QPixmap) — check the QRect dimensions
        icon_rect = draw_pixmap_calls[0][1][0]  # First positional arg: QRect
        assert icon_rect.width() == int(_EVENT_ICON_SIZE)
        assert icon_rect.height() == int(_EVENT_ICON_SIZE)

    def test_fallback_line_with_no_data_does_not_have_event_type(self) -> None:
        """The fallback '(okänd)' line has no event type."""
        config = PersonBoxConfig()  # All fields disabled
        display_data: dict = {}
        item = PersonBoxItem("p9", display_data, config)

        assert item._lines == ["(okänd)"]
        assert item._line_event_types == [None]
