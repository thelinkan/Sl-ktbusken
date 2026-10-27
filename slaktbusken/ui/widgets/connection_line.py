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

# Foster and adoptive connections are drawn dashed, each in its own colour,
# distinct from the biological grey (80, 80, 80) and the partner dark red
# (120, 60, 60). Foster is a teal/green; adoptive is a purple/blue.
_FOSTER_COLOR = QColor(0, 140, 120)
_ADOPTIVE_COLOR = QColor(110, 70, 200)
_FOSTER_WIDTH = 1.5
_ADOPTIVE_WIDTH = 1.5

# Badge text colour: a dark neutral so the label stays legible against the
# diagram background regardless of the connector colour.
_BADGE_COLOR = QColor(40, 40, 40)
# Small offset from the path midpoint so the badge does not sit on the line.
_BADGE_OFFSET_X = 4.0
_BADGE_OFFSET_Y = -4.0


class ConnectionType(Enum):
    """Type of connection between person boxes.

    ``PARENT_CHILD`` and ``PARTNER`` are the original biological/solid styles.
    ``FOSTER`` and ``ADOPTIVE`` mark non-biological parent-child connections,
    each rendered as a dashed line in its own distinct colour.
    """

    PARENT_CHILD = auto()
    PARTNER = auto()
    FOSTER = auto()
    ADOPTIVE = auto()


class ConnectionLineItem(QGraphicsItem):
    """A graphics item drawing a connection between two points.

    Supports different line styles for parent-child relationships
    (solid grey) and partner connections (solid darker, thicker), plus
    dashed foster (teal/green) and adoptive (purple/blue) connections in
    their own distinct colours.
    Routes the line with an orthogonal path (vertical-horizontal-vertical)
    for parent-child, and a simple horizontal line for partners.

    When ``badge_text`` is provided, the item paints that text near the
    midpoint of its path (e.g. "foster"/"adoptiv"). Callers pass a badge
    only when the diagram's badge setting is enabled.

    Args:
        start: The starting point (typically bottom-centre of parent).
        end: The ending point (typically top-centre of child).
        connection_type: The type of connection to render.
        badge_text: Optional text label painted near the path midpoint;
            no badge is drawn when ``None`` or empty.
        parent: Optional parent QGraphicsItem.
    """

    def __init__(
        self,
        start: QPointF,
        end: QPointF,
        connection_type: ConnectionType = ConnectionType.PARENT_CHILD,
        badge_text: Optional[str] = None,
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        """Initialise the connection line.

        Args:
            start: Starting point of the connection.
            end: Ending point of the connection.
            connection_type: Type of relationship line.
            badge_text: Optional label painted near the path midpoint.
                No badge is drawn when ``None`` or empty.
            parent: Optional parent graphics item.
        """
        super().__init__(parent)
        self._start = start
        self._end = end
        self._connection_type = connection_type
        self._badge_text = badge_text
        self._path = QPainterPath()
        self._build_path()

    @property
    def badge_text(self) -> Optional[str]:
        """The optional badge text painted near the path midpoint."""
        return self._badge_text

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
        - Foster: dashed teal/green, ~1.5 wide
        - Adoptive: dashed purple/blue, ~1.5 wide

        When ``badge_text`` is set, the text is drawn near the path midpoint.

        Args:
            painter: The QPainter to draw with.
            option: Style options (unused).
            widget: The widget being painted on (unused).
        """
        if self._connection_type == ConnectionType.PARTNER:
            pen = QPen(_PARTNER_COLOR, _PARTNER_WIDTH, Qt.PenStyle.SolidLine)
        elif self._connection_type == ConnectionType.FOSTER:
            pen = QPen(_FOSTER_COLOR, _FOSTER_WIDTH, Qt.PenStyle.DashLine)
        elif self._connection_type == ConnectionType.ADOPTIVE:
            pen = QPen(_ADOPTIVE_COLOR, _ADOPTIVE_WIDTH, Qt.PenStyle.DashLine)
        else:
            pen = QPen(_PARENT_CHILD_COLOR, _PARENT_CHILD_WIDTH, Qt.PenStyle.SolidLine)

        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._path)

        if self._badge_text:
            self._paint_badge(painter)

    def _paint_badge(self, painter: QPainter) -> None:
        """Paint the badge text near the midpoint of the path.

        Args:
            painter: The QPainter to draw with.
        """
        midpoint = self._path.pointAtPercent(0.5)
        badge_pen = QPen(_BADGE_COLOR)
        painter.setPen(badge_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawText(
            QPointF(midpoint.x() + _BADGE_OFFSET_X, midpoint.y() + _BADGE_OFFSET_Y),
            self._badge_text,
        )

    def _build_path(self) -> None:
        """Build the painter path for the connection.

        Draws a straight line between start and end for both
        connection types. Routing (orthogonal segments) is handled
        by the layout code which creates multiple line segments.
        """
        self._path = QPainterPath()
        self._path.moveTo(self._start)
        self._path.lineTo(self._end)
