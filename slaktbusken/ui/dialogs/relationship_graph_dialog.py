"""Relationship probability graph dialog for Släktbusken.

Displays a horizontal bar chart showing possible relationship types and their
probabilities based on shared centimorgan values. Uses QPainter for rendering.
All UI text is in Swedish.

Data source: The Shared cM Project v4.0 (March 2020) by Blaine T. Bettinger.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.services.relationship_lookup import (
    RelationshipProbability,
    get_relationship_probabilities,
)


class _BarChartWidget(QWidget):
    """Custom widget that draws a horizontal bar chart using QPainter.

    Each bar represents a relationship type with its probability percentage.
    Bars are sorted by probability descending.
    """

    # Layout constants
    BAR_HEIGHT = 24
    BAR_SPACING = 6
    LABEL_WIDTH = 220
    PERCENT_LABEL_WIDTH = 50
    LEFT_MARGIN = 10
    RIGHT_MARGIN = 10
    TOP_MARGIN = 10
    BOTTOM_MARGIN = 10

    # Colors
    BAR_COLOR = QColor(70, 130, 180)  # Steel blue - good contrast on white
    BAR_BORDER_COLOR = QColor(40, 90, 140)
    TEXT_COLOR = QColor(30, 30, 30)
    BACKGROUND_COLOR = QColor(255, 255, 255)

    def __init__(
        self,
        probabilities: list[RelationshipProbability],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._probabilities = probabilities
        self._max_probability = (
            max(p.probability for p in probabilities) if probabilities else 1.0
        )

        # Calculate minimum size
        total_height = (
            self.TOP_MARGIN
            + len(probabilities) * (self.BAR_HEIGHT + self.BAR_SPACING)
            + self.BOTTOM_MARGIN
        )
        self.setMinimumHeight(total_height)
        self.setMinimumWidth(450)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:  # noqa: N802
        """Draw the horizontal bar chart."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Fill background
        painter.fillRect(self.rect(), self.BACKGROUND_COLOR)

        if not self._probabilities:
            painter.end()
            return

        # Calculate available bar width
        available_width = (
            self.width()
            - self.LEFT_MARGIN
            - self.LABEL_WIDTH
            - self.PERCENT_LABEL_WIDTH
            - self.RIGHT_MARGIN
        )
        available_width = max(available_width, 50)

        # Font setup
        label_font = QFont()
        label_font.setPointSize(9)
        percent_font = QFont()
        percent_font.setPointSize(9)
        percent_font.setBold(True)

        y = self.TOP_MARGIN

        for prob in self._probabilities:
            # Draw relationship label (left side)
            painter.setFont(label_font)
            painter.setPen(QPen(self.TEXT_COLOR))
            label_rect = QRectF(
                self.LEFT_MARGIN,
                y,
                self.LABEL_WIDTH - 5,
                self.BAR_HEIGHT,
            )
            painter.drawText(
                label_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                prob.relationship,
            )

            # Calculate bar width proportional to probability
            bar_width = (
                (prob.probability / self._max_probability) * available_width
                if self._max_probability > 0
                else 0
            )

            # Draw bar
            bar_x = self.LEFT_MARGIN + self.LABEL_WIDTH
            bar_rect = QRectF(
                bar_x,
                y + 2,
                bar_width,
                self.BAR_HEIGHT - 4,
            )
            painter.setPen(QPen(self.BAR_BORDER_COLOR, 1))
            painter.setBrush(self.BAR_COLOR)
            painter.drawRoundedRect(bar_rect, 3, 3)

            # Draw percentage label (right of bar)
            painter.setFont(percent_font)
            painter.setPen(QPen(self.TEXT_COLOR))
            percent_rect = QRectF(
                bar_x + available_width + 5,
                y,
                self.PERCENT_LABEL_WIDTH,
                self.BAR_HEIGHT,
            )
            painter.drawText(
                percent_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                f"{prob.probability:.1f}%",
            )

            y += self.BAR_HEIGHT + self.BAR_SPACING

        painter.end()


class RelationshipGraphDialog(QDialog):
    """Modal dialog displaying a horizontal bar chart of relationship probabilities.

    Shows possible relationships and their probabilities based on shared cM value,
    using data from The Shared cM Project v4.0.

    Args:
        shared_cm: The shared centimorgan value to look up.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        shared_cm: float,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._shared_cm = shared_cm

        self.setWindowTitle("Relationsdiagram")
        self.setMinimumWidth(550)
        self.setModal(True)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build the dialog UI."""
        layout = QVBoxLayout(self)

        # Header showing the cM value
        header_label = QLabel(f"Delad DNA: {self._shared_cm:.1f} cM")
        header_font = QFont()
        header_font.setPointSize(11)
        header_font.setBold(True)
        header_label.setFont(header_font)
        layout.addWidget(header_label)

        # Get probabilities
        probabilities = get_relationship_probabilities(self._shared_cm)

        if not probabilities:
            # No data available - show informational message
            no_data_label = QLabel(
                "Inga relationsdata finns tillgängliga för detta cM-värde."
            )
            no_data_label.setWordWrap(True)
            no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_data_font = QFont()
            no_data_font.setPointSize(10)
            no_data_label.setFont(no_data_font)
            no_data_label.setStyleSheet("color: #555; padding: 20px;")
            layout.addWidget(no_data_label)
        else:
            # Draw the bar chart
            chart_widget = _BarChartWidget(probabilities, self)
            layout.addWidget(chart_widget)

        # Attribution text
        attribution_label = QLabel(
            "Data: The Shared cM Project v4.0 (mars 2020) av Blaine T. Bettinger"
        )
        attribution_label.setWordWrap(True)
        attribution_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        attribution_label.setStyleSheet(
            "color: #666; font-style: italic; padding-top: 10px;"
        )
        layout.addWidget(attribution_label)

        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
