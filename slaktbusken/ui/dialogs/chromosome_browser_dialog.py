"""Chromosome browser dialog for visualizing shared DNA segments.

Renders 22 autosomal chromosome bars (plus optional X) using QPainter,
with colored segment overlays, inline cM labels, and tooltips.

Supports two modes:
- Match mode: single row per chromosome (flat segment list)
- Triangulation mode: one row per person per chromosome (grouped segments)

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
_BAR_BG_COLOR = QColor(230, 230, 230)
_LABEL_MIN_WIDTH_PX = 40

# Colors for multiple persons (triangulation mode)
_PERSON_COLORS = [
    QColor(70, 130, 210),   # Blue
    QColor(210, 90, 70),    # Red
    QColor(80, 180, 80),    # Green
    QColor(180, 130, 50),   # Orange/brown
    QColor(150, 70, 180),   # Purple
    QColor(50, 170, 170),   # Teal
]


class ChromosomeWidget(QWidget):
    """Custom widget that paints chromosome bars with segment overlays.

    Supports both single-person (match) and multi-person (triangulation) modes.
    In multi-person mode, each chromosome gets one sub-row per person.
    """

    def __init__(
        self,
        segments_by_person: dict[str, list[MatchSegmentRecord]],
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the chromosome widget.

        Args:
            segments_by_person: Dict mapping person name to their segments.
                For match mode, use a single key (e.g. the match person name).
                For triangulation mode, use one key per other person.
        """
        super().__init__(parent)
        self._segments_by_person = segments_by_person
        self._person_names = list(segments_by_person.keys())
        self._num_persons = len(self._person_names)

        # Determine which chromosomes to show
        all_segments = [
            seg for segs in segments_by_person.values() for seg in segs
        ]
        self._has_x = any(seg.chromosome.upper() == "X" for seg in all_segments)
        self._chroms = list(_AUTOSOMAL_CHROMS)
        if self._has_x:
            self._chroms.append("X")

        # Group segments by (person, chromosome)
        self._seg_by_person_chrom: dict[str, dict[str, list[MatchSegmentRecord]]] = {}
        for person_name, segs in segments_by_person.items():
            by_chrom: dict[str, list[MatchSegmentRecord]] = {}
            for seg in segs:
                key = seg.chromosome.upper() if seg.chromosome.upper() == "X" else seg.chromosome
                by_chrom.setdefault(key, []).append(seg)
            self._seg_by_person_chrom[person_name] = by_chrom

        # Pre-compute segment rects for tooltip hit-testing
        self._segment_rects: list[tuple[QRectF, MatchSegmentRecord, str]] = []

        self.setMouseTracking(True)
        self._update_size()

    def _update_size(self) -> None:
        """Set fixed height based on number of chromosomes and persons per chromosome."""
        rows_per_chrom = max(1, self._num_persons)
        height = _TOP_MARGIN + len(self._chroms) * (rows_per_chrom * _ROW_HEIGHT + 6) + 10
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

        rows_per_chrom = max(1, self._num_persons)
        chrom_block_height = rows_per_chrom * _ROW_HEIGHT

        for chrom_idx, chrom in enumerate(self._chroms):
            block_y = _TOP_MARGIN + chrom_idx * (chrom_block_height + 6)
            bar_width = (CHROMOSOME_LENGTHS[chrom] / max_length) * available_width

            # Draw chromosome label (centered vertically in the block)
            painter.setFont(chrom_label_font)
            painter.setPen(QPen(Qt.GlobalColor.black))
            painter.drawText(
                QRectF(0, block_y, _LEFT_MARGIN - 5, chrom_block_height),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                chrom,
            )

            # Draw one row per person
            for person_idx, person_name in enumerate(self._person_names):
                y = block_y + person_idx * _ROW_HEIGHT
                color = _PERSON_COLORS[person_idx % len(_PERSON_COLORS)]

                # Draw neutral background bar
                bar_rect = QRectF(_LEFT_MARGIN, y, bar_width, _BAR_HEIGHT)
                painter.setBrush(QBrush(_BAR_BG_COLOR))
                painter.setPen(QPen(QColor(200, 200, 200)))
                painter.drawRoundedRect(bar_rect, 3, 3)

                # Draw segments for this person on this chromosome
                chrom_segments = self._seg_by_person_chrom.get(
                    person_name, {}
                ).get(chrom, [])

                for seg in chrom_segments:
                    rel_pos = segment_relative_position(seg.start_position, chrom)
                    rel_width = segment_relative_width(
                        seg.start_position, seg.end_position, chrom
                    )

                    seg_x = _LEFT_MARGIN + rel_pos * bar_width
                    seg_w = rel_width * bar_width
                    seg_rect = QRectF(seg_x, y, seg_w, _BAR_HEIGHT)

                    # Draw segment rectangle
                    painter.setBrush(QBrush(color))
                    painter.setPen(QPen(color.darker(120)))
                    painter.drawRect(seg_rect)

                    # Store for tooltip hit-testing
                    self._segment_rects.append((seg_rect, seg, person_name))

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
            for rect, seg, person_name in self._segment_rects:
                if rect.contains(QPointF(pos)):
                    tooltip = (
                        f"Person: {person_name}\n"
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

    Supports two usage patterns:
    - Match mode: pass segments + person_name (single person, one row per chromosome)
    - Triangulation mode: pass segments_by_person dict (multiple persons, stacked rows)

    Args:
        segments: List of MatchSegmentRecord (match mode). Ignored if segments_by_person is set.
        person_name: Display name for match mode header.
        segments_by_person: Dict mapping person name to their segments (triangulation mode).
        title: Custom window/header title. If None, uses person_name.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        segments: list[MatchSegmentRecord] | None = None,
        person_name: str = "",
        segments_by_person: dict[str, list[MatchSegmentRecord]] | None = None,
        title: str | None = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        # Build the segments_by_person dict from either input
        if segments_by_person is not None:
            self._segments_by_person = segments_by_person
        elif segments is not None:
            name = person_name if person_name else "(okänd)"
            self._segments_by_person = {name: segments}
        else:
            self._segments_by_person = {}

        self._title = title if title else (person_name if person_name else "(okänd)")

        self.setWindowTitle("Kromosomvy")
        self.setMinimumSize(600, 400)
        self.resize(800, 550)
        self.setModal(True)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build the dialog layout."""
        layout = QVBoxLayout(self)

        # Summary header
        all_segments = [
            seg for segs in self._segments_by_person.values() for seg in segs
        ]
        total_cm = sum(seg.centimorgans for seg in all_segments)
        total_segments = len(all_segments)

        header_name = QLabel(f"<b>{self._title}</b>")
        header_name.setStyleSheet("font-size: 14px;")
        layout.addWidget(header_name)

        header_summary = QLabel(
            f"Totalt delad cM: {total_cm:.2f}  |  Antal segment: {total_segments}"
        )
        layout.addWidget(header_summary)

        # Legend (show person colors when multiple persons)
        if len(self._segments_by_person) > 1:
            legend_layout = QVBoxLayout()
            for idx, person_name in enumerate(self._segments_by_person.keys()):
                color = _PERSON_COLORS[idx % len(_PERSON_COLORS)]
                color_hex = color.name()
                person_segs = self._segments_by_person[person_name]
                person_cm = sum(s.centimorgans for s in person_segs)
                legend_label = QLabel(
                    f'<span style="color: {color_hex};">■</span> '
                    f'{person_name} ({person_cm:.2f} cM, {len(person_segs)} segment)'
                )
                legend_layout.addWidget(legend_label)
            layout.addLayout(legend_layout)

        # Scroll area with chromosome widget
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        chrom_widget = ChromosomeWidget(self._segments_by_person)
        scroll.setWidget(chrom_widget)
        layout.addWidget(scroll, stretch=1)

        # Close button
        close_btn = QPushButton("Stäng")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
