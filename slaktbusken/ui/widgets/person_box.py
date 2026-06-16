"""Person box graphics item for diagram views.

Renders a person's information in a configurable box within the
QGraphicsScene. Which fields are displayed is controlled by a
PersonBoxConfig instance from settings_io.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

if TYPE_CHECKING:
    from slaktbusken.persistence.settings_io import PersonBoxConfig

# Default box dimensions
_BOX_WIDTH = 180.0
_BOX_HEIGHT_MIN = 50.0
_LINE_HEIGHT = 16.0
_PADDING = 8.0
_CORNER_RADIUS = 4.0

# Colours
_BG_COLOR = QColor(255, 255, 255)
_BORDER_COLOR = QColor(80, 80, 80)
_SELECTED_BORDER_COLOR = QColor(0, 120, 215)
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
        self._lines: list[str] = []

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
        per Req 20.4.

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
        else:
            pen = QPen(_BORDER_COLOR, 1.0)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, _CORNER_RADIUS, _CORNER_RADIUS)

        # Text content
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        painter.setPen(QPen(_TEXT_COLOR))

        y = _PADDING + _LINE_HEIGHT * 0.8
        for i, line in enumerate(self._lines):
            if i == 0:
                # Name line in bold
                bold_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
                painter.setFont(bold_font)
                painter.drawText(QRectF(_PADDING, y - _LINE_HEIGHT * 0.8, _BOX_WIDTH - 2 * _PADDING, _LINE_HEIGHT), Qt.AlignmentFlag.AlignLeft, line)
                painter.setFont(font)
            else:
                painter.setPen(QPen(_LABEL_COLOR))
                painter.drawText(QRectF(_PADDING, y - _LINE_HEIGHT * 0.8, _BOX_WIDTH - 2 * _PADDING, _LINE_HEIGHT), Qt.AlignmentFlag.AlignLeft, line)
                painter.setPen(QPen(_TEXT_COLOR))
            y += _LINE_HEIGHT

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
        """
        self._lines = []

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
            else:
                self._lines.append(f"{prefix}{value}")

        # Ensure at least one line (fallback)
        if not self._lines:
            self._lines.append("(okänd)")
