"""Report preview dialog for viewing, printing, and exporting reports.

Displays a paginated report in a scrollable area with paper size selection,
print-to-printer, and PDF export functionality. All UI text is in Swedish.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPageLayout,
    QPageSize,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from slaktbusken.persistence.settings_io import VALID_PAPER_SIZES, ProjectSettings
from slaktbusken.reports.content import ReportContent
from slaktbusken.reports.paginator import (
    PAPER_SIZES,
    PageLayout,
    RenderedElement,
    RenderedPage,
    ReportPaginator,
)

logger = logging.getLogger(__name__)

# Screen rendering scale: pixels per mm
_SCREEN_SCALE = 3.0

# Page shadow/border constants
_PAGE_MARGIN_PX = 16
_PAGE_SHADOW_OFFSET = 3
_PAGE_BORDER_COLOR = QColor(180, 180, 180)
_PAGE_SHADOW_COLOR = QColor(200, 200, 200)
_PAGE_BG_COLOR = QColor(255, 255, 255)
_CANVAS_BG_COLOR = QColor(230, 230, 230)

# Font sizes (points) for different element types
_FONT_SIZES = {
    "heading_1": 18,
    "heading_2": 14,
    "heading_3": 12,
    "body": 10,
}

# Page number footer height in mm
_PAGE_NUMBER_HEIGHT_MM = 6.0


class _PageCanvasWidget(QWidget):
    """Widget that paints all rendered pages vertically stacked."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pages: list[RenderedPage] = []
        self._layout: PageLayout = PAPER_SIZES["A4"]
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), _CANVAS_BG_COLOR)
        self.setPalette(palette)

    def set_pages(self, pages: list[RenderedPage], layout: PageLayout) -> None:
        """Update the pages to render and recalculate widget size."""
        self._pages = pages
        self._layout = layout
        self._update_size()
        self.update()

    def _update_size(self) -> None:
        """Calculate and set the total widget size based on page count."""
        if not self._pages:
            self.setMinimumSize(100, 100)
            return

        page_w_px = int(self._layout.width_mm * _SCREEN_SCALE)
        page_h_px = int(self._layout.height_mm * _SCREEN_SCALE)

        total_width = page_w_px + 2 * _PAGE_MARGIN_PX
        total_height = (
            len(self._pages) * (page_h_px + _PAGE_MARGIN_PX) + _PAGE_MARGIN_PX
        )

        self.setMinimumSize(total_width, total_height)
        self.setFixedSize(total_width, total_height)

    def paintEvent(self, event) -> None:  # noqa: N802
        """Paint all pages with borders, content, and page numbers."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        page_w_px = int(self._layout.width_mm * _SCREEN_SCALE)
        page_h_px = int(self._layout.height_mm * _SCREEN_SCALE)
        margin_px = int(self._layout.margin_mm * _SCREEN_SCALE)

        for i, page in enumerate(self._pages):
            # Page position
            x_offset = _PAGE_MARGIN_PX
            y_offset = _PAGE_MARGIN_PX + i * (page_h_px + _PAGE_MARGIN_PX)

            # Draw shadow
            painter.fillRect(
                x_offset + _PAGE_SHADOW_OFFSET,
                y_offset + _PAGE_SHADOW_OFFSET,
                page_w_px,
                page_h_px,
                _PAGE_SHADOW_COLOR,
            )

            # Draw page background
            painter.fillRect(x_offset, y_offset, page_w_px, page_h_px, _PAGE_BG_COLOR)

            # Draw page border
            painter.setPen(QPen(_PAGE_BORDER_COLOR, 1))
            painter.drawRect(x_offset, y_offset, page_w_px, page_h_px)

            # Draw elements
            for element in page.elements:
                self._paint_element(
                    painter,
                    element,
                    x_offset + margin_px,
                    y_offset + margin_px,
                )

            # Draw page number footer: "Sida X av Y"
            self._paint_page_number(
                painter, page, x_offset, y_offset, page_w_px, page_h_px, margin_px
            )

        painter.end()

    def _paint_element(
        self,
        painter: QPainter,
        element: RenderedElement,
        content_x: int,
        content_y: int,
    ) -> None:
        """Paint a single rendered element."""
        x = content_x + int(element.x_mm * _SCREEN_SCALE)
        y = content_y + int(element.y_mm * _SCREEN_SCALE)
        w = int(element.width_mm * _SCREEN_SCALE)
        h = int(element.height_mm * _SCREEN_SCALE)

        if element.element_type == "heading":
            font = self._get_heading_font(element.level or 1)
            painter.setFont(font)
            painter.setPen(QPen(QColor(0, 0, 0)))
            painter.drawText(
                QRectF(x, y, w, h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                element.text or "",
            )

        elif element.element_type in (
            "paragraph_line",
            "list_item_line",
            "empty_state",
            "caption",
        ):
            font = self._get_body_font()
            if element.element_type == "caption":
                font.setItalic(True)
            elif element.element_type == "empty_state":
                font.setItalic(True)
            painter.setFont(font)
            painter.setPen(QPen(QColor(0, 0, 0)))
            painter.drawText(
                QRectF(x, y, w, h),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                element.text or "",
            )

        elif element.element_type == "image":
            if element.image_path and element.image_path.exists():
                pixmap = QPixmap(str(element.image_path))
                if not pixmap.isNull():
                    painter.drawPixmap(
                        x,
                        y,
                        w,
                        h,
                        pixmap.scaled(
                            w,
                            h,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        ),
                    )
                else:
                    self._paint_image_placeholder(painter, x, y, w, h)
            else:
                self._paint_image_placeholder(painter, x, y, w, h)

    def _paint_image_placeholder(
        self, painter: QPainter, x: int, y: int, w: int, h: int
    ) -> None:
        """Paint a placeholder rectangle for missing images."""
        painter.setPen(QPen(QColor(150, 150, 150)))
        painter.drawRect(x, y, w, h)
        font = self._get_body_font()
        font.setItalic(True)
        painter.setFont(font)
        painter.drawText(
            QRectF(x, y, w, h),
            Qt.AlignmentFlag.AlignCenter,
            "Bilden kunde inte laddas",
        )

    def _paint_page_number(
        self,
        painter: QPainter,
        page: RenderedPage,
        page_x: int,
        page_y: int,
        page_w: int,
        page_h: int,
        margin_px: int,
    ) -> None:
        """Paint 'Sida X av Y' at the bottom of the page."""
        font = self._get_body_font()
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(QPen(QColor(100, 100, 100)))

        footer_h = int(_PAGE_NUMBER_HEIGHT_MM * _SCREEN_SCALE)
        footer_y = page_y + page_h - margin_px
        footer_rect = QRectF(
            page_x + margin_px,
            footer_y,
            page_w - 2 * margin_px,
            footer_h,
        )

        text = f"Sida {page.page_number} av {page.total_pages}"
        painter.drawText(
            footer_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            text,
        )

    def _get_heading_font(self, level: int) -> QFont:
        """Return a font appropriate for the given heading level."""
        font = QFont()
        font.setBold(True)
        size_key = f"heading_{level}"
        font.setPointSize(_FONT_SIZES.get(size_key, _FONT_SIZES["body"]))
        return font

    def _get_body_font(self) -> QFont:
        """Return a font for body text."""
        font = QFont()
        font.setPointSize(_FONT_SIZES["body"])
        return font


class ReportPreviewDialog(QDialog):
    """Dialog for previewing, printing, and exporting a paginated report.

    Displays the report content paginated for the selected paper size in a
    scrollable area. Provides controls for changing paper size, printing to
    an OS printer, and exporting to PDF.

    Args:
        content: The report content to display.
        settings: Project settings (used for paper size persistence).
        parent: Optional parent widget.
    """

    def __init__(
        self,
        content: ReportContent,
        settings: ProjectSettings,
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialise the report preview dialog.

        Args:
            content: The report content to display.
            settings: Project settings containing paper size preference.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self._content = content
        self._settings = settings
        self._paginator = ReportPaginator()
        self._pages: list[RenderedPage] = []

        self.setWindowTitle(f"Förhandsgranskning — {content.title}")
        self.resize(800, 900)

        self._setup_ui()
        self._initial_paginate()

    def _setup_ui(self) -> None:
        """Build the dialog layout with toolbar and scroll area."""
        layout = QVBoxLayout(self)

        # Toolbar row
        toolbar = QHBoxLayout()

        # Paper size selector
        toolbar.addWidget(QLabel("Pappersstorlek:"))
        self._paper_size_combo = QComboBox()
        for size in VALID_PAPER_SIZES:
            self._paper_size_combo.addItem(size)
        toolbar.addWidget(self._paper_size_combo)

        toolbar.addStretch()

        # Print button
        self._print_btn = QPushButton("Skriv ut")
        self._print_btn.clicked.connect(self._print_report)
        toolbar.addWidget(self._print_btn)

        # Export PDF button
        self._export_btn = QPushButton("Exportera PDF")
        self._export_btn.clicked.connect(self._export_pdf)
        toolbar.addWidget(self._export_btn)

        layout.addLayout(toolbar)

        # Scroll area with page canvas
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(False)
        self._scroll_area.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._canvas = _PageCanvasWidget()
        self._scroll_area.setWidget(self._canvas)

        layout.addWidget(self._scroll_area)

        # Connect paper size change signal
        self._paper_size_combo.currentTextChanged.connect(self._on_paper_size_changed)

    def _initial_paginate(self) -> None:
        """Perform the initial pagination using the stored paper size."""
        # Determine initial paper size, falling back to A4 if unrecognized
        paper_size = self._settings.report_paper_size
        if paper_size not in PAPER_SIZES:
            paper_size = "A4"

        # Set combo box to the current paper size (without triggering signal)
        self._paper_size_combo.blockSignals(True)
        idx = self._paper_size_combo.findText(paper_size)
        if idx >= 0:
            self._paper_size_combo.setCurrentIndex(idx)
        self._paper_size_combo.blockSignals(False)

        self._repaginate(paper_size)

    def _on_paper_size_changed(self, paper_size: str) -> None:
        """Handle paper size combo box change.

        Re-paginates the report and persists the new paper size to settings.

        Args:
            paper_size: The newly selected paper size string.
        """
        if paper_size not in PAPER_SIZES:
            paper_size = "A4"

        # Persist the new paper size to settings
        self._settings.report_paper_size = paper_size

        self._repaginate(paper_size)

    def _repaginate(self, paper_size: str) -> None:
        """Re-paginate the report and update the canvas.

        Args:
            paper_size: The paper size to paginate for.
        """
        self._pages = self._paginator.paginate(self._content, paper_size)
        page_layout = PAPER_SIZES.get(paper_size, PAPER_SIZES["A4"])
        self._canvas.set_pages(self._pages, page_layout)

    def _print_report(self) -> None:
        """Open a print dialog and print all pages to the selected printer."""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        self._configure_printer_page(printer)

        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            # User cancelled — no action
            return

        self._paint_to_device(printer)

    def _export_pdf(self) -> None:
        """Open a file dialog and export the report as PDF."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportera rapport som PDF",
            "",
            "PDF-filer (*.pdf)",
        )

        if not file_path:
            # User cancelled
            return

        # Ensure .pdf extension
        if not file_path.lower().endswith(".pdf"):
            file_path += ".pdf"

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(file_path)
        self._configure_printer_page(printer)

        try:
            self._paint_to_device(printer)

            # Verify the file was actually created
            if not Path(file_path).exists():
                raise OSError("Filen skapades inte")

        except OSError as e:
            logger.error("PDF export failed: %s", e)
            QMessageBox.critical(
                self,
                "Exportfel",
                f"Kunde inte exportera PDF-filen.\n\n"
                f"Sökväg: {file_path}\n"
                f"Fel: {e}",
            )

    def _configure_printer_page(self, printer: QPrinter) -> None:
        """Configure the printer's page size and margins based on current paper size."""
        paper_size = self._paper_size_combo.currentText()
        page_layout = PAPER_SIZES.get(paper_size, PAPER_SIZES["A4"])

        # Map paper size to QPageSize
        page_size_map = {
            "A4": QPageSize.PageSizeId.A4,
            "A3": QPageSize.PageSizeId.A3,
            "A5": QPageSize.PageSizeId.A5,
        }
        q_page_size = QPageSize(page_size_map.get(paper_size, QPageSize.PageSizeId.A4))

        margin = page_layout.margin_mm
        margins = QMarginsF(margin, margin, margin, margin)

        printer.setPageLayout(
            QPageLayout(q_page_size, QPageLayout.Orientation.Portrait, margins, QPageLayout.Unit.Millimeter)
        )

    def _paint_to_device(self, printer: QPrinter) -> None:
        """Paint all pages to a QPrinter device (for both printing and PDF export).

        Args:
            printer: The configured QPrinter to paint onto.
        """
        painter = QPainter()
        if not painter.begin(printer):
            raise OSError("Kunde inte starta utskriften")

        try:
            page_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
            printable_w = page_rect.width()
            printable_h = page_rect.height()

            for i, page in enumerate(self._pages):
                if i > 0:
                    printer.newPage()

                self._paint_page_to_printer(painter, page, printable_w, printable_h)
        finally:
            painter.end()

    def _paint_page_to_printer(
        self,
        painter: QPainter,
        page: RenderedPage,
        printable_w: float,
        printable_h: float,
    ) -> None:
        """Paint a single page's content onto the printer painter.

        Scales from mm coordinates to the printer's device coordinates.

        Args:
            painter: The active QPainter on the printer device.
            page: The rendered page to paint.
            printable_w: Printable width in device pixels.
            printable_h: Printable height in device pixels.
        """
        paper_size = self._paper_size_combo.currentText()
        layout = PAPER_SIZES.get(paper_size, PAPER_SIZES["A4"])

        # Scale factor from mm to device pixels
        scale_x = printable_w / layout.printable_width
        scale_y = printable_h / layout.printable_height

        for element in page.elements:
            x = element.x_mm * scale_x
            y = element.y_mm * scale_y
            w = element.width_mm * scale_x
            h = element.height_mm * scale_y

            if element.element_type == "heading":
                font = QFont()
                font.setBold(True)
                level = element.level or 1
                size_key = f"heading_{level}"
                base_size = _FONT_SIZES.get(size_key, _FONT_SIZES["body"])
                # Scale font for printer resolution
                font.setPointSize(base_size)
                painter.setFont(font)
                painter.setPen(QPen(QColor(0, 0, 0)))
                painter.drawText(
                    QRectF(x, y, w, h),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    element.text or "",
                )

            elif element.element_type in (
                "paragraph_line",
                "list_item_line",
                "empty_state",
                "caption",
            ):
                font = QFont()
                font.setPointSize(_FONT_SIZES["body"])
                if element.element_type in ("caption", "empty_state"):
                    font.setItalic(True)
                painter.setFont(font)
                painter.setPen(QPen(QColor(0, 0, 0)))
                painter.drawText(
                    QRectF(x, y, w, h),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    element.text or "",
                )

            elif element.element_type == "image":
                if element.image_path and element.image_path.exists():
                    pixmap = QPixmap(str(element.image_path))
                    if not pixmap.isNull():
                        target_rect = QRectF(x, y, w, h)
                        source_rect = QRectF(pixmap.rect())
                        painter.drawPixmap(target_rect, pixmap, source_rect)

        # Draw page number footer
        footer_font = QFont()
        footer_font.setPointSize(9)
        painter.setFont(footer_font)
        painter.setPen(QPen(QColor(100, 100, 100)))

        footer_h = _PAGE_NUMBER_HEIGHT_MM * scale_y
        footer_rect = QRectF(0, printable_h - footer_h, printable_w, footer_h)
        page_text = f"Sida {page.page_number} av {page.total_pages}"
        painter.drawText(
            footer_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            page_text,
        )
