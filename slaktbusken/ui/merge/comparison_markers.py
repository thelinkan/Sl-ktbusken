"""Graphics markers drawn on person boxes of the comparison window.

* :class:`SharedPersonMarker`: a green diamond with "=" on the box of a person
  whose id is visible in both views. It differs in symbol (diamond) and colour
  (green) from the Candidate_Indicator (a round blue/orange/grey dot).
* :class:`CandidateAssessmentBadge`: a purple label with the Candidate_Assessment
  of a saved candidate whose two persons are shown, one in each view. Activating
  it (click, Enter or Space) calls a callback that opens the comments.

Both are keyboard focusable and show their tooltip at once (well within 500 ms)
when the pointer enters or the marker receives focus.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QToolTip

SHARED_COLOUR = "#2E7D32"
BADGE_COLOUR = "#6A1B9A"
MARKER_SIZE = 18.0
BADGE_HEIGHT = 16.0


class _TooltipItem(QGraphicsItem):
    """Focusable item that shows its tooltip immediately."""

    def __init__(self, tooltip: str, parent: Optional[QGraphicsItem] = None) -> None:
        super().__init__(parent)
        self.setToolTip(tooltip)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setZValue(10)
        self.tooltip_text = tooltip

    def _show_tip(self) -> None:
        scene = self.scene()
        views = scene.views() if scene is not None else []
        if not views:
            return
        view = views[0]
        top_left = view.mapFromScene(self.mapToScene(self.boundingRect().bottomLeft()))
        QToolTip.showText(view.viewport().mapToGlobal(top_left), self.tooltip_text, view.viewport())

    def hoverEnterEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._show_tip()
        super().hoverEnterEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._show_tip()
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().focusOutEvent(event)
        self.update()

    def _paint_focus(self, painter: QPainter) -> None:
        if self.hasFocus():
            painter.setPen(QPen(QColor("#000000"), 1.5, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())


class SharedPersonMarker(_TooltipItem):
    """Marker for a person shown in both family views."""

    kind = "shared"

    def __init__(self, tooltip: str, parent: Optional[QGraphicsItem] = None) -> None:
        super().__init__(tooltip, parent)

    def activate(self) -> None:
        """Nothing to open; the marker only informs."""

    def boundingRect(self) -> QRectF:  # noqa: N802 - Qt API
        return QRectF(0, 0, MARKER_SIZE, MARKER_SIZE)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        half = MARKER_SIZE / 2.0
        diamond = QPolygonF(
            [QPointF(half, 0), QPointF(MARKER_SIZE, half), QPointF(half, MARKER_SIZE), QPointF(0, half)]
        )
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#FFFFFF"), 1))
        painter.setBrush(QBrush(QColor(SHARED_COLOUR)))
        painter.drawPolygon(diamond)
        painter.setPen(QPen(QColor("#FFFFFF"), 1.6))
        painter.drawLine(QPointF(half - 3.5, half - 1.6), QPointF(half + 3.5, half - 1.6))
        painter.drawLine(QPointF(half - 3.5, half + 1.6), QPointF(half + 3.5, half + 1.6))
        self._paint_focus(painter)


class CandidateAssessmentBadge(_TooltipItem):
    """Candidate_Assessment label of a saved candidate; activating opens its comments."""

    kind = "candidate"

    def __init__(
        self,
        text: str,
        tooltip: str,
        candidate_id: str,
        callback: Callable[[str], None],
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        super().__init__(tooltip, parent)
        self.text = text
        self.candidate_id = candidate_id
        self._callback = callback
        self._font = QFont()
        self._font.setPointSize(8)
        self._width = max(40.0, QFontMetricsF(self._font).horizontalAdvance(text) + 12.0)

    def activate(self) -> None:
        self._callback(self.candidate_id)

    def boundingRect(self) -> QRectF:  # noqa: N802 - Qt API
        return QRectF(0, 0, self._width, BADGE_HEIGHT)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(BADGE_COLOUR)))
        painter.drawRoundedRect(self.boundingRect(), 4, 4)
        painter.setPen(QPen(QColor("#FFFFFF")))
        painter.setFont(self._font)
        painter.drawText(self.boundingRect(), Qt.AlignmentFlag.AlignCenter, self.text)
        self._paint_focus(painter)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.activate()
            event.accept()
            return
        super().keyPressEvent(event)
