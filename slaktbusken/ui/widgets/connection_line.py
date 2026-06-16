"""Connection line graphics item for diagram relationships.

Draws lines between person boxes to represent parent-child
and partner connections with appropriate line styles.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Optional

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

# Line style constants
_PARENT_CHILD_COLOR = QColor(80, 80, 80)
_PARTNER_COLOR = QColor(120, 60, 60)
_PARENT_CHILD_WIDTH = 1.5
_PARTNER_WIDTH = 2.0


class ConnectionType(Enum):
    """Type of connection between person boxes."""

    PARENT_CHILD = auto()
    PARTNER = auto()


class ConnectionLineItem(QGraphicsItem):
    """A graphics item drawing a connection between two points.

    Supports different line styles for parent-child relationships
    (solid grey) and partner connections (solid darker, thicker).
    Routes the line with an orthogonal path (vertical-horizontal-vertical)
    for parent-child, and a simple horizontal line for partners.

    Args:
        start: The starting point (typically bottom-centre of parent).
        end: The ending point (typically top-centre of child).
        connection_type: The type of connection to render.
        parent: Optional parent QGraphicsItem.
    """

    def __init__(
        self,
        start: QPointF,
        end: QPointF,
        connection_type: ConnectionType = ConnectionType.PARENT_CHILD,
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        """Initialise the connection line.

        Args:
            start: Starting point of the connection.
            end: Ending point of the connection.
            connection_type: Type of relationship line.
            parent: Optional parent graphics item.
        """
        super().__init__(parent)
        self._start = start
        self._end = end
        self._connection_type = connection_type
        self._path = QPainterPath()
        self._build_path()

    @property
    def connection_type(self) -> ConnectionType:
        """The type of this connection."""
        return self._connection_type

    @property
    def start_point(self) -> QPointF:
        """The starting point."""
        return self._start

    @property
    def end_point(self) -> QPointF:
        """The ending point."""
        return self._end

    def set_points(self, start: QPointF, end: QPointF) -> None:
        """Update the start and end points and rebuild the path.

        Args:
            start: New starting point.
            end: New ending point.
        """
        self.prepareGeometryChange()
        self._start = start
        self._end = end
        self._build_path()
        self.update()

    def boundingRect(self) -> QRectF:
        """Return the bounding rectangle of the connection path.

        Returns:
            The bounding rect with extra margin for pen width.
        """
        margin = _PARTNER_WIDTH + 2.0
        return self._path.boundingRect().adjusted(-margin, -margin, margin, margin)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        """Paint the connection line.

        Uses different pen styles depending on connection type:
        - Parent-child: solid grey, thinner
        - Partner: solid darker red-brown, thicker

        Args:
            painter: The QPainter to draw with.
            option: Style options (unused).
            widget: The widget being painted on (unused).
        """
        if self._connection_type == ConnectionType.PARTNER:
            pen = QPen(_PARTNER_COLOR, _PARTNER_WIDTH, Qt.PenStyle.SolidLine)
        else:
            pen = QPen(_PARENT_CHILD_COLOR, _PARENT_CHILD_WIDTH, Qt.PenStyle.SolidLine)

        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._path)

    def _build_path(self) -> None:
        """Build the painter path for the connection.

        Draws a straight line between start and end for both
        connection types. Routing (orthogonal segments) is handled
        by the layout code which creates multiple line segments.
        """
        self._path = QPainterPath()
        self._path.moveTo(self._start)
        self._path.lineTo(self._end)
