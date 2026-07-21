"""Chromosome browser dialog for visualizing shared DNA segments.

Renders 22 autosomal chromosome bars (plus optional X) using QPainter,
with colored segment overlays, inline cM labels, and tooltips.
All UI text is in Swedish.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.services.chromosome_data import (
    CHROMOSOME_LENGTHS,
    segment_relative_position,
    segment_relative_width,
)
from slaktbusken.services.dna_match_csv_parser import MatchSegmentRecord

# Autosomal chromosomes in display order
_AUTOSOMAL_CHROMS = [str(i) for i in range(1, 23)]

# Visual constants
_BAR_HEIGHT = 18
_ROW_HEIGHT = 28
_LEFT_MARGIN = 40
_RIGHT_MARGIN = 10
_TOP_MARGIN = 10
_SEGMENT_COLOR = QColor(70, 130, 210)
_BAR_BG_COLOR = QColor(230, 230, 230)
_LABEL_MIN_WIDTH_PX = 40


class ChromosomeWidget(QWidget):
    """Custom widget that paints chromosome bars with segment overlays."""

    def __init__(
        self,
        segments: list[MatchSegmentRecord],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._segments = segments
        self._has_x = any(seg.chromosome.upper() == "X" for seg in segments)
        self._chroms = list(_AUTOSOMAL_CHROMS)
        if self._has_x:
            self._chroms.append("X")

        # Group segments by chromosome
        self._seg_by_chrom: dict[str, list[MatchSegmentRecord]] = {}
        for seg in segments:
            key = seg.chromosome.upper() if seg.chromosome.upper() == "X" else seg.chromosome
            self._seg_by_chrom.setdefault(key, []).append(seg)

        # Pre-compute segment rects for tooltip hit-testing
        self._segment_rects: list[tuple[QRectF, MatchSegmentRecord]] = []

        self.setMouseTracking(True)
        self._update_size()

    def _update_size(self) -> None:
        """Set fixed height based on number of chromosomes."""
        height = _TOP_MARGIN + len(self._chroms) * _ROW_HEIGHT + 10
        self.setMinimumHeight(height)
        self.setMinimumWidth(400)

    def paintEvent(self, event) -> None:  # noqa: N802
        """Paint all chromosome bars and segment overlays."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._segment_rects.clear()

        max_length = max(CHROMOSOME_LENGTHS[c] for c in self._chroms)
        available_width = self.width() - _LEFT_MARGIN - _RIGHT_MARGIN

        label_font = QFont()
        label_font.setPointSize(8)
        chrom_label_font = QFont()
        chrom_label_font.setPointSize(9)
        chrom_label_font.setBold(True)

        for row_idx, chrom in enumerate(self._chroms):
            y = _TOP_MARGIN + row_idx * _ROW_HEIGHT
            bar_width = (CHROMOSOME_LENGTHS[chrom] / max_length) * available_width

            # Draw chromosome label
            painter.setFont(chrom_label_font)
            painter.setPen(QPen(Qt.GlobalColor.black))
            painter.drawText(
                QRectF(0, y, _LEFT_MARGIN - 5, _BAR_HEIGHT),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                chrom,
            )

            # Draw neutral background bar
            bar_rect = QRectF(_LEFT_MARGIN, y, bar_width, _BAR_HEIGHT)
            painter.setBrush(QBrush(_BAR_BG_COLOR))
            painter.setPen(QPen(QColor(200, 200, 200)))
            painter.drawRoundedRect(bar_rect, 3, 3)

            # Draw segments for this chromosome
            chrom_segments = self._seg_by_chrom.get(chrom, [])
            for seg in chrom_segments:
                rel_pos = segment_relative_position(seg.start_position, chrom)
                rel_width = segment_relative_width(
                    seg.start_position, seg.end_position, chrom
                )

                seg_x = _LEFT_MARGIN + rel_pos * bar_width
                seg_w = rel_width * bar_width
                seg_rect = QRectF(seg_x, y, seg_w, _BAR_HEIGHT)

                # Draw segment rectangle
                painter.setBrush(QBrush(_SEGMENT_COLOR))
                painter.setPen(QPen(_SEGMENT_COLOR.darker(120)))
                painter.drawRect(seg_rect)

                # Store for tooltip hit-testing
                self._segment_rects.append((seg_rect, seg))

                # Inline cM label when segment is wide enough
                if seg_w >= _LABEL_MIN_WIDTH_PX:
                    painter.setFont(label_font)
                    painter.setPen(QPen(Qt.GlobalColor.white))
                    cm_text = f"{seg.centimorgans:.1f}"
                    painter.drawText(
                        seg_rect,
                        Qt.AlignmentFlag.AlignCenter,
                        cm_text,
                    )

        painter.end()

    def event(self, ev: QEvent) -> bool:  # noqa: N802
        """Handle tooltip events for segment hover."""
        if ev.type() == QEvent.Type.ToolTip:
            pos = ev.pos()
            for rect, seg in self._segment_rects:
                if rect.contains(QPointF(pos)):
                    tooltip = (
                        f"Kromosom: {seg.chromosome}\n"
                        f"Start: {seg.start_position:,}\n"
                        f"Slut: {seg.end_position:,}\n"
                        f"cM: {seg.centimorgans:.1f}\n"
                        f"SNP: {seg.snp_count:,}"
                    )
                    from PySide6.QtWidgets import QToolTip

                    QToolTip.showText(ev.globalPos(), tooltip, self)
                    return True
            from PySide6.QtWidgets import QToolTip

            QToolTip.hideText()
            return True
        return super().event(ev)


class ChromosomeBrowserDialog(QDialog):
    """Modal dialog displaying a chromosome browser view of shared DNA segments.

    Args:
        segments: List of MatchSegmentRecord to visualize.
        person_name: Display name of the match person (or "(okänd)" fallback).
        parent: Optional parent widget.
    """

    def __init__(
        self,
        segments: list[MatchSegmentRecord],
        person_name: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._segments = segments
        self._person_name = person_name if person_name else "(okänd)"

        self.setWindowTitle("Kromosomvy")
        self.setMinimumSize(600, 400)
        self.resize(800, 550)
        self.setModal(True)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build the dialog layout."""
        layout = QVBoxLayout(self)

        # Summary header
        total_cm = sum(seg.centimorgans for seg in self._segments)
        total_segments = len(self._segments)

        header_name = QLabel(f"<b>{self._person_name}</b>")
        header_name.setStyleSheet("font-size: 14px;")
        layout.addWidget(header_name)

        header_summary = QLabel(
            f"Totalt delad cM: {total_cm:.2f}  |  Antal segment: {total_segments}"
        )
        layout.addWidget(header_summary)

        # Scroll area with chromosome widget
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        chrom_widget = ChromosomeWidget(self._segments)
        scroll.setWidget(chrom_widget)
        layout.addWidget(scroll, stretch=1)

        # Close button
        close_btn = QPushButton("Stäng")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
