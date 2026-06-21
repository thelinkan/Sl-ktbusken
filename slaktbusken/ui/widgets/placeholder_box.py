"""Placeholder box graphics item for missing relatives.

Displays a dashed-border box in positions where a parent or child
is missing, allowing the user to click to add a person.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

# Box dimensions (same width as PersonBoxItem for alignment)
_BOX_WIDTH = 240.0
_BOX_HEIGHT = 50.0
_CORNER_RADIUS = 4.0
_DASH_PATTERN = [6.0, 4.0]

# Colours
_BG_COLOR = QColor(245, 245, 245)
_BORDER_COLOR = QColor(160, 160, 160)
_TEXT_COLOR = QColor(120, 120, 120)
_PLUS_COLOR = QColor(80, 150, 80)


class PlaceholderRole(Enum):
    """The role of a placeholder box in the family diagram."""

    MOTHER = auto()
    FATHER = auto()
    CHILD = auto()
    PARTNER = auto()


# Swedish labels for each role
_ROLE_LABELS: dict[PlaceholderRole, str] = {
    PlaceholderRole.MOTHER: "Lägg till mor",
    PlaceholderRole.FATHER: "Lägg till far",
    PlaceholderRole.CHILD: "Lägg till barn",
    PlaceholderRole.PARTNER: "Lägg till partner",
}


class PlaceholderBoxItem(QGraphicsItem):
    """A placeholder graphics item for missing relatives.

    Displays a dashed-border box with a "+" icon and Swedish text
    indicating the role (mother, father, or child). Clicking the
    placeholder triggers add-person functionality.

    Args:
        role: The placeholder role (MOTHER, FATHER, or CHILD).
        family_id: Optional family ID context for child placeholders.
        parent: Optional parent QGraphicsItem.
    """

    def __init__(
        self,
        role: PlaceholderRole,
        family_id: Optional[str] = None,
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        """Initialise the placeholder box.

        Args:
            role: The role this placeholder represents.
            family_id: Optional family ID for child placeholders.
            parent: Optional parent graphics item.
        """
        super().__init__(parent)
        self._role = role
        self._family_id = family_id

        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @property
    def role(self) -> PlaceholderRole:
        """The placeholder role."""
        return self._role

    @property
    def family_id(self) -> Optional[str]:
        """The associated family ID, if any."""
        return self._family_id

    def boundingRect(self) -> QRectF:
        """Return the bounding rectangle.

        Returns:
            The bounding rect for the placeholder box.
        """
        return QRectF(-1, -1, _BOX_WIDTH + 2, _BOX_HEIGHT + 2)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        """Paint the placeholder box with dashed border.

        Renders a light background with a dashed border, a "+" symbol,
        and the role label in Swedish.

        Args:
            painter: The QPainter to draw with.
            option: Style options (unused).
            widget: The widget being painted on (unused).
        """
        rect = QRectF(0, 0, _BOX_WIDTH, _BOX_HEIGHT)

        # Background
        painter.setBrush(QBrush(_BG_COLOR))

        # Dashed border
        pen = QPen(_BORDER_COLOR, 1.5, Qt.PenStyle.CustomDashLine)
        pen.setDashPattern(_DASH_PATTERN)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, _CORNER_RADIUS, _CORNER_RADIUS)

        # "+" symbol
        plus_font = QFont("Segoe UI", 16, QFont.Weight.Bold)
        painter.setFont(plus_font)
        painter.setPen(QPen(_PLUS_COLOR))
        plus_rect = QRectF(0, 0, _BOX_WIDTH, _BOX_HEIGHT * 0.55)
        painter.drawText(plus_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, "+")

        # Role label
        label_font = QFont("Segoe UI", 8)
        painter.setFont(label_font)
        painter.setPen(QPen(_TEXT_COLOR))
        label = _ROLE_LABELS.get(self._role, "Lägg till")
        label_rect = QRectF(0, _BOX_HEIGHT * 0.55, _BOX_WIDTH, _BOX_HEIGHT * 0.45)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, label)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle mouse press to trigger add-person.

        Args:
            event: The mouse press event.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            # Click handling is managed by the scene/panel via
            # scene selection or custom signal mechanism.
            pass
        super().mousePressEvent(event)
