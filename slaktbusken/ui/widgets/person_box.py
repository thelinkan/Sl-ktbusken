"""Person box graphics item for diagram views.

Renders a person's information in a configurable box within the
QGraphicsScene. Which fields are displayed is controlled by a
PersonBoxConfig instance from settings_io.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from slaktbusken.ui.icons.icon_registry import icon_registry

if TYPE_CHECKING:
    from slaktbusken.model.name_parser import ParsedGivenName
    from slaktbusken.persistence.settings_io import PersonBoxConfig

# Default box dimensions
_BOX_WIDTH = 180.0
_BOX_HEIGHT_MIN = 50.0
_LINE_HEIGHT = 16.0
_PADDING = 8.0
_CORNER_RADIUS = 4.0
_GENDER_ICON_SIZE = 14.0
_EVENT_ICON_SIZE = 12.0
_EVENT_ICON_GAP = 2.0

# Colours
_BG_COLOR = QColor(255, 255, 255)
_BORDER_COLOR = QColor(80, 80, 80)
_SELECTED_BORDER_COLOR = QColor(0, 120, 215)
_ANCESTOR_BORDER_COLOR = QColor(0xC0, 0x39, 0x2B)
_DESCENDANT_BORDER_COLOR = QColor(0x27, 0xAE, 0x60)
_TEXT_COLOR = QColor(30, 30, 30)
_LABEL_COLOR = QColor(100, 100, 100)


class PersonBoxItem(QGraphicsItem):
    """A graphics item displaying a person's configured fields.

    Renders a rectangular box with a subset of person data fields
    as determined by the PersonBoxConfig. Supports visual selection
    highlighting and click/double-click interactions.

    Args:
        person_id: The unique ID of the person.
        display_data: Dictionary of field values to render. Keys
            correspond to PersonBoxConfig field names; values are
            the display strings (or None if no data).
        config: PersonBoxConfig controlling which fields are shown.
        parent: Optional parent QGraphicsItem.
    """

    def __init__(
        self,
        person_id: str,
        display_data: dict[str, Optional[str]],
        config: PersonBoxConfig,
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        """Initialise the person box item.

        Args:
            person_id: The unique ID of the person.
            display_data: Dictionary mapping field names to display values.
            config: PersonBoxConfig determining visible fields.
            parent: Optional parent graphics item.
        """
        super().__init__(parent)
        self._person_id = person_id
        self._display_data = display_data
        self._config = config
        self._selected = False
        self._is_ancestor: bool = bool(display_data.get("is_ancestor"))
        self._is_descendant: bool = bool(display_data.get("is_descendant"))
        self._lines: list[str] = []
        self._line_event_types: list[Optional[str]] = []

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self._build_lines()

    @property
    def person_id(self) -> str:
        """The person ID associated with this box."""
        return self._person_id

    @property
    def box_height(self) -> float:
        """The actual rendered height of this box."""
        return max(
            _BOX_HEIGHT_MIN,
            len(self._lines) * _LINE_HEIGHT + 2 * _PADDING,
        )

    @property
    def is_selected(self) -> bool:
        """Whether this box is visually selected."""
        return self._selected

    @property
    def is_ancestor(self) -> bool:
        """Whether this person is marked as a direct ancestor."""
        return self._is_ancestor

    @property
    def is_descendant(self) -> bool:
        """Whether this person is marked as a direct descendant."""
        return self._is_descendant

    def set_selected(self, selected: bool) -> None:
        """Set the visual selection state.

        Args:
            selected: True to show selection highlight.
        """
        self._selected = selected
        self.update()

    def boundingRect(self) -> QRectF:
        """Return the bounding rectangle of this item.

        Returns:
            The bounding rect encompassing the box and border.
        """
        height = max(
            _BOX_HEIGHT_MIN,
            len(self._lines) * _LINE_HEIGHT + 2 * _PADDING,
        )
        # Extra pixel for pen width
        return QRectF(-1, -1, _BOX_WIDTH + 2, height + 2)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        """Paint the person box.

        Renders the box background, border (highlighted if selected),
        and configured content fields. Fields with no data are omitted
        per Req 20.4. The name line renders the tilltalsnamn (if any)
        with an underline decoration.

        Args:
            painter: The QPainter to draw with.
            option: Style options (unused).
            widget: The widget being painted on (unused).
        """
        height = max(
            _BOX_HEIGHT_MIN,
            len(self._lines) * _LINE_HEIGHT + 2 * _PADDING,
        )
        rect = QRectF(0, 0, _BOX_WIDTH, height)

        # Background
        painter.setBrush(QBrush(_BG_COLOR))

        # Border
        if self._selected:
            pen = QPen(_SELECTED_BORDER_COLOR, 2.5)
        elif self._is_ancestor:
            pen = QPen(_ANCESTOR_BORDER_COLOR, 2.0)
        elif self._is_descendant:
            pen = QPen(_DESCENDANT_BORDER_COLOR, 2.0)
        else:
            pen = QPen(_BORDER_COLOR, 1.0)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, _CORNER_RADIUS, _CORNER_RADIUS)

        # Gender icon in top-right corner (Req 2.2, 2.4)
        sex = self._display_data.get("sex")
        if sex:
            gender_pixmap = icon_registry.get_gender_icon(sex)
            if not gender_pixmap.isNull():
                icon_x = _BOX_WIDTH - _GENDER_ICON_SIZE - _PADDING / 2
                icon_y = _PADDING / 2
                icon_rect = QRectF(
                    icon_x, icon_y, _GENDER_ICON_SIZE, _GENDER_ICON_SIZE
                )
                painter.drawPixmap(icon_rect.toRect(), gender_pixmap)

        # Text content
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        painter.setPen(QPen(_TEXT_COLOR))

        y = _PADDING + _LINE_HEIGHT * 0.8
        for i, line in enumerate(self._lines):
            if i == 0:
                # Name line in bold — with optional tilltalsnamn underline
                self._paint_name_line(painter, y)
            else:
                painter.setPen(QPen(_LABEL_COLOR))
                # Check if this line has an associated event icon
                event_type = (
                    self._line_event_types[i]
                    if i < len(self._line_event_types)
                    else None
                )
                text_x = _PADDING
                if event_type:
                    event_pixmap = icon_registry.get_event_icon(event_type)
                    if not event_pixmap.isNull():
                        icon_y = y - _LINE_HEIGHT * 0.8 + (_LINE_HEIGHT - _EVENT_ICON_SIZE) / 2
                        icon_rect = QRectF(
                            _PADDING, icon_y,
                            _EVENT_ICON_SIZE, _EVENT_ICON_SIZE,
                        )
                        painter.drawPixmap(icon_rect.toRect(), event_pixmap)
                        text_x = _PADDING + _EVENT_ICON_SIZE + _EVENT_ICON_GAP
                painter.drawText(
                    QRectF(
                        text_x,
                        y - _LINE_HEIGHT * 0.8,
                        _BOX_WIDTH - text_x - _PADDING,
                        _LINE_HEIGHT,
                    ),
                    Qt.AlignmentFlag.AlignLeft,
                    line,
                )
                painter.setPen(QPen(_TEXT_COLOR))
            y += _LINE_HEIGHT

    def _paint_name_line(self, painter: QPainter, y: float) -> None:
        """Paint the name line with selective underline for tilltalsnamn.

        If display_data contains a valid ParsedGivenName with a
        tilltalsnamn_index, draws each name part individually with
        the tilltalsnamn part underlined. Otherwise renders the name
        as a single string without underline (existing behaviour).

        Args:
            painter: The QPainter to draw with.
            y: The baseline y-coordinate for text rendering.
        """
        name_parsed: ParsedGivenName | None = self._display_data.get("name_parsed")

        bold_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setPen(QPen(_TEXT_COLOR))

        if (
            name_parsed is not None
            and name_parsed.tilltalsnamn_index is not None
            and name_parsed.parts
            and 0 <= name_parsed.tilltalsnamn_index < len(name_parsed.parts)
        ):
            # Draw name parts individually with selective underline
            fm = QFontMetrics(bold_font)
            x = _PADDING
            space_width = fm.horizontalAdvance(" ")

            for idx, part in enumerate(name_parsed.parts):
                if idx == name_parsed.tilltalsnamn_index:
                    # Underline the tilltalsnamn part
                    underline_font = QFont(bold_font)
                    underline_font.setUnderline(True)
                    painter.setFont(underline_font)
                else:
                    bold_font.setUnderline(False)
                    painter.setFont(bold_font)

                painter.drawText(
                    x,
                    y,
                    part,
                )
                part_width = fm.horizontalAdvance(part)
                x += part_width + space_width

            # Draw surname (if present) after the given name parts
            # The full name line includes the surname after the given display string
            bold_font.setUnderline(False)
            painter.setFont(bold_font)
            name_line = self._lines[0] if self._lines else ""
            given_display = name_parsed.display_string
            if name_line.startswith(given_display) and len(name_line) > len(given_display):
                surname_part = name_line[len(given_display):].lstrip()
                if surname_part:
                    painter.drawText(x, y, surname_part)
        else:
            # No tilltalsnamn marker — render name line normally (no underline)
            painter.setFont(bold_font)
            name_text = self._lines[0] if self._lines else ""
            painter.drawText(
                QRectF(
                    _PADDING,
                    y - _LINE_HEIGHT * 0.8,
                    _BOX_WIDTH - 2 * _PADDING,
                    _LINE_HEIGHT,
                ),
                Qt.AlignmentFlag.AlignLeft,
                name_text,
            )

        # Restore regular font for subsequent lines
        regular_font = QFont("Segoe UI", 9)
        painter.setFont(regular_font)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle mouse press for selection.

        Args:
            event: The mouse press event.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            # Selection is managed by the scene/panel
            pass
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle double-click for editing.

        Args:
            event: The mouse double-click event.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            # Edit signal is emitted via the scene/panel
            pass
        super().mouseDoubleClickEvent(event)

    def _build_lines(self) -> None:
        """Build the list of display lines from config and data.

        Only includes fields that are both enabled in config and
        have non-None/non-empty data (Req 20.4).
        Also builds a parallel list of event type strings for icon
        rendering (None for lines without an event icon).
        """
        self._lines = []
        self._line_event_types = []

        # Mapping from field names to event type strings for icon lookup
        _FIELD_EVENT_TYPE_MAP: dict[str, str] = {
            "birth_date": "birth",
            "death_date": "death",
            "marriage_date": "marriage",
        }

        # Ordered fields and their display labels
        field_order: list[tuple[str, str]] = [
            ("name", ""),
            ("birth_date", "f. "),
            ("birth_place", "fp. "),
            ("death_date", "d. "),
            ("death_place", "dp. "),
            ("marriage_date", "g. "),
            ("marriage_place", "gp. "),
            ("occupation", "Yrke: "),
            ("dna_info", "DNA: "),
            ("notes", "Ant: "),
        ]

        for field_name, prefix in field_order:
            if not getattr(self._config, field_name, False):
                continue
            value = self._display_data.get(field_name)
            if not value:
                # Omit field if no data (Req 20.4)
                continue
            if field_name == "name":
                self._lines.append(value)
                self._line_event_types.append(None)
            else:
                self._lines.append(f"{prefix}{value}")
                self._line_event_types.append(
                    _FIELD_EVENT_TYPE_MAP.get(field_name)
                )

        # Ensure at least one line (fallback)
        if not self._lines:
            self._lines.append("(okänd)")
            self._line_event_types.append(None)
