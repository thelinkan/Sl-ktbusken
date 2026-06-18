"""Progress overlay widget for long-running operations.

Displays a semi-transparent dark backdrop with a centered spinning
indicator and message text. Blocks all user input while visible by
covering the entire parent window area.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEvent,
    QObject,
    QPropertyAnimation,
    QRect,
    Qt,
    Property,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import QWidget


class ProgressOverlay(QWidget):
    """Semi-transparent overlay with spinner and message text.

    Parented to the main window, this widget covers the entire window
    area to block all mouse and keyboard events during long operations.
    It displays a dark semi-transparent backdrop, a centered animated
    spinner, and a descriptive message below the spinner.
    """

    _BACKDROP_COLOR = QColor(0, 0, 0, 160)
    _SPINNER_SIZE = 48
    _SPINNER_THICKNESS = 5
    _SPINNER_COLOR = QColor(255, 255, 255)

    def __init__(self, parent: QWidget) -> None:
        """Initialise the progress overlay.

        Args:
            parent: The parent widget (typically MainWindow).
        """
        super().__init__(parent)
        self._message = ""
        self._angle = 0

        # Make the overlay invisible and non-interactive by default
        self.setVisible(False)

        # Install event filter on parent to track resize events
        if parent is not None:
            parent.installEventFilter(self)

        # Animation for the spinner rotation
        self._animation = QPropertyAnimation(self, b"angle")
        self._animation.setDuration(1000)
        self._animation.setStartValue(0)
        self._animation.setEndValue(360)
        self._animation.setLoopCount(-1)  # Infinite loop

    def _get_angle(self) -> int:
        """Get the current spinner angle."""
        return self._angle

    def _set_angle(self, value: int) -> None:
        """Set the spinner angle and trigger repaint."""
        self._angle = value
        self.update()

    angle = Property(int, _get_angle, _set_angle)

    def show_with_message(self, message: str) -> None:
        """Show the overlay with the given message.

        Displays the semi-transparent backdrop, starts the spinner
        animation, and shows the message text. Resizes to match the
        parent window and raises to the top of the widget stack.

        Args:
            message: The message to display (e.g. "Laddar projekt...").
        """
        self._message = message

        # Match parent size
        if self.parent() is not None:
            self.setGeometry(self.parentWidget().rect())

        self.raise_()
        self.setVisible(True)
        self._animation.start()

    def hide(self) -> None:
        """Hide the overlay and stop the animation.

        Removes the overlay from view and re-enables input on the
        parent window.
        """
        self._animation.stop()
        self.setVisible(False)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """Filter parent resize events to keep overlay matched in size.

        Args:
            obj: The object that generated the event.
            event: The event to filter.

        Returns:
            False to allow normal event processing to continue.
        """
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self.setGeometry(self.parentWidget().rect())
        return super().eventFilter(obj, event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Resize overlay to match parent window size.

        Args:
            event: The resize event.
        """
        if self.parent() is not None:
            self.setGeometry(self.parentWidget().rect())
        super().resizeEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the backdrop, spinner, and message.

        Args:
            event: The paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw semi-transparent dark backdrop
        painter.fillRect(self.rect(), self._BACKDROP_COLOR)

        # Calculate center
        center_x = self.width() // 2
        center_y = self.height() // 2

        # Draw spinner arc
        spinner_rect = QRect(
            center_x - self._SPINNER_SIZE // 2,
            center_y - self._SPINNER_SIZE // 2,
            self._SPINNER_SIZE,
            self._SPINNER_SIZE,
        )

        pen = QPen(self._SPINNER_COLOR, self._SPINNER_THICKNESS)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        # Draw an arc that rotates (270 degrees span, rotating start angle)
        start_angle = self._angle * 16  # Qt uses 1/16th of a degree
        span_angle = 270 * 16
        painter.drawArc(spinner_rect, start_angle, span_angle)

        # Draw message text below spinner
        if self._message:
            font = QFont("Segoe UI", 12)
            painter.setFont(font)
            painter.setPen(QPen(QColor(255, 255, 255)))

            text_rect = QRect(
                0,
                center_y + self._SPINNER_SIZE // 2 + 20,
                self.width(),
                40,
            )
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                self._message,
            )

        painter.end()
