"""Utskrifts- och förhandsgranskningsdialog för diagramvyer.

Renderar den aktuella diagramscenen (familjevy, antavla eller ättlingar)
skalad efter den aktuella zoomnivån och delar upp den på flera sidor om
den inte får plats på en sida. Sidbrytningar justeras så att en personruta
inte delas mellan två sidor. Alla sidor använder samma skala och är
toppvänsterjusterade så att sidorna kan tejpas ihop. Dialogen erbjuder
förhandsgranskning samt utskrift till skrivare och export till PDF.
All text är på svenska.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPageLayout,
    QPageSize,
    QPainter,
    QPen,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGraphicsScene,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# Converting scene units (pixels at 96 DPI) to millimetres.
_MM_PER_INCH = 25.4
_SCREEN_DPI = 96.0
_MM_PER_SCENE_UNIT_AT_100 = _MM_PER_INCH / _SCREEN_DPI

# Preview rendering: pixels per mm on screen.
_SCREEN_SCALE = 2.5

# Target rasterisation resolution for print/PDF output (dots per inch).
# The entire diagram is rendered once to an image at this DPI (at the chosen
# zoom scale) and then split pixel-exactly across pages. This guarantees an
# identical scale on every page, seamless tiling, and correct font rendering.
_RASTER_DPI = 200.0

# Safety cap on the full-diagram raster size (pixels) to avoid excessive
# memory use for very large diagrams at high zoom.
_MAX_RASTER_PIXELS = 120_000_000  # ~120 MP (~480 MB for ARGB32)

# Preview page decoration.
_PAGE_GAP_PX = 16
_PAGE_SHADOW_OFFSET = 3
_PAGE_BORDER_COLOR = QColor(180, 180, 180)
_PAGE_SHADOW_COLOR = QColor(200, 200, 200)
_PAGE_BG_COLOR = QColor(255, 255, 255)
_CANVAS_BG_COLOR = QColor(230, 230, 230)

# Paper sizes in mm (portrait orientation: width x height).
_PAPER_SIZES_MM: dict[str, tuple[float, float]] = {
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "A5": (148.0, 210.0),
    "Letter": (215.9, 279.4),
}

_PAGE_SIZE_IDS: dict[str, QPageSize.PageSizeId] = {
    "A4": QPageSize.PageSizeId.A4,
    "A3": QPageSize.PageSizeId.A3,
    "A5": QPageSize.PageSizeId.A5,
    "Letter": QPageSize.PageSizeId.Letter,
}

_DEFAULT_MARGIN_MM = 10.0

# Height reserved at the top of each page's printable area for the heading.
_HEADING_HEIGHT_MM = 10.0


@dataclass
class _PageTile:
    """En sida i rutnätet som täcker scenen.

    Varje sida har en bestämd position (col, row) i rutnätet och ett
    scenintervall. Sidor delar en gemensam skala och är toppvänsterjusterade
    så att de kan tejpas ihop. ``page_extent_x/y`` anger den fulla
    sidstorleken i scenekoordinater (konstant för alla sidor), medan
    ``scene_rect`` kan vara mindre när en sidbrytning flyttats för att inte
    dela en personruta — resten av sidan lämnas då tom.

    Attribut:
        scene_rect: Delen av scenen (i scenekoordinater) som ska renderas
            på denna sida.
        col: Kolumnindex i sidrutnätet (0-baserat).
        row: Radindex i sidrutnätet (0-baserat).
    """

    scene_rect: QRectF
    col: int
    row: int


def _compute_cuts(
    start: float,
    end: float,
    page_extent: float,
    box_intervals: list[tuple[float, float]],
) -> list[float]:
    """Beräkna brytpunkter längs en axel som undviker att dela rutor.

    Delar intervallet [start, end] i segment som vart och ett är högst
    ``page_extent`` stort. En naiv brytpunkt flyttas bakåt till början av
    en ruta om brytpunkten annars skulle skära rutan. Om en ruta är större
    än en sida delas den oundvikligt (brytpunkten placeras då på maxlängd).

    Args:
        start: Startkoordinat (scenekoordinater).
        end: Slutkoordinat (scenekoordinater).
        page_extent: Maximal längd per sida (scenekoordinater).
        box_intervals: Lista med (box_start, box_end) för varje ruta längs
            denna axel.

    Returns:
        Sorterad lista med brytpunkter inklusive ``start`` och ``end``.
    """
    if page_extent <= 0:
        return [start, end]

    cuts = [start]
    while cuts[-1] + page_extent < end - 1e-6:
        current = cuts[-1]
        naive = current + page_extent

        # Hitta rutor som skärs av den naiva brytpunkten.
        straddling_starts = [
            b_start
            for (b_start, b_end) in box_intervals
            if b_start < naive < b_end
        ]

        cut = naive
        if straddling_starts:
            candidate = min(straddling_starts)
            # Flytta bara brytpunkten om det ger framsteg (undvik oändlig loop
            # när en ruta är större än en sida).
            if candidate > current + 1e-6:
                cut = candidate
            else:
                cut = naive

        cuts.append(cut)

    cuts.append(end)
    return cuts


def plan_pages(
    content_rect: QRectF,
    box_rects: list[QRectF],
    page_extent_x: float,
    page_extent_y: float,
) -> list[_PageTile]:
    """Planera sidrutnätet för en scen med hänsyn till personrutor.

    Args:
        content_rect: Scenens innehållsgräns (scenekoordinater).
        box_rects: Personrutornas gränser (scenekoordinater) som inte bör
            delas mellan sidor.
        page_extent_x: Utskriftsbar bredd per sida i scenekoordinater.
        page_extent_y: Utskriftsbar höjd per sida i scenekoordinater.

    Returns:
        Lista med sidor i läsordning (rad för rad, vänster till höger).
    """
    x_intervals = [(r.left(), r.right()) for r in box_rects]
    y_intervals = [(r.top(), r.bottom()) for r in box_rects]

    x_cuts = _compute_cuts(
        content_rect.left(), content_rect.right(), page_extent_x, x_intervals
    )
    y_cuts = _compute_cuts(
        content_rect.top(), content_rect.bottom(), page_extent_y, y_intervals
    )

    tiles: list[_PageTile] = []
    for row in range(len(y_cuts) - 1):
        y0 = y_cuts[row]
        y1 = y_cuts[row + 1]
        for col in range(len(x_cuts) - 1):
            x0 = x_cuts[col]
            x1 = x_cuts[col + 1]
            rect = QRectF(x0, y0, x1 - x0, y1 - y0)
            tiles.append(_PageTile(scene_rect=rect, col=col, row=row))
    return tiles


def _render_scene_to_image(
    scene: QGraphicsScene,
    content_rect: QRectF,
    px_per_scene_unit: float,
    print_background: bool,
) -> QImage:
    """Rastrera hela scenen en gång till en QImage vid en fast skala.

    Genom att rendera hela diagrammet i ett svep vid en enda skala blir
    textstorlekar korrekta och konsekventa, och efterföljande sidor kan
    klippas ut pixelexakt så att de kan tejpas ihop.

    Args:
        scene: Scenen att rendera.
        content_rect: Scenens innehållsgräns (scenekoordinater).
        px_per_scene_unit: Antal bildpunkter per scenenhet.
        print_background: True för att inkludera scenens bakgrundsfärg.

    Returns:
        En QImage som täcker ``content_rect`` vid angiven skala.
    """
    width_px = max(1, round(content_rect.width() * px_per_scene_unit))
    height_px = max(1, round(content_rect.height() * px_per_scene_unit))

    image = QImage(width_px, height_px, QImage.Format.Format_ARGB32_Premultiplied)
    if print_background:
        bg = scene.backgroundBrush()
        if bg.style() != Qt.BrushStyle.NoBrush:
            image.fill(bg.color())
        else:
            image.fill(Qt.GlobalColor.white)
    else:
        image.fill(Qt.GlobalColor.white)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    try:
        target = QRectF(0, 0, width_px, height_px)
        # Rendera utan scenens bakgrundspensel — bakgrunden har redan fyllts
        # ovan (eller lämnats vit). Detta ger full kontroll över bakgrunden.
        saved_brush = scene.backgroundBrush()
        try:
            scene.setBackgroundBrush(QBrush(Qt.BrushStyle.NoBrush))
            scene.render(painter, target, content_rect)
        finally:
            scene.setBackgroundBrush(saved_brush)
    finally:
        painter.end()

    return image


class _PreviewCanvas(QWidget):
    """Widget som ritar alla planerade sidor staplade vertikalt.

    Förhandsgranskningen använder samma renderingsmodell som utskriften:
    hela scenen rastreras en gång vid en fast skala och varje sida visar
    ett pixelexakt utsnitt, toppvänsterjusterat.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._image: Optional[QImage] = None
        self._tiles: list[_PageTile] = []
        self._content_rect = QRectF()
        self._page_w_mm = 210.0
        self._page_h_mm = 297.0
        # Scenekoordinater per sida (konstant för alla sidor).
        self._page_extent_x = 0.0
        self._page_extent_y = 0.0
        # Bildpunkter per scenenhet i rasterbilden.
        self._img_px_per_unit = 1.0
        self._heading: Optional[str] = None
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), _CANVAS_BG_COLOR)
        self.setPalette(palette)

    def set_content(
        self,
        image: Optional[QImage],
        tiles: list[_PageTile],
        content_rect: QRectF,
        page_w_mm: float,
        page_h_mm: float,
        page_extent_x: float,
        page_extent_y: float,
        img_px_per_unit: float,
        heading: Optional[str] = None,
    ) -> None:
        """Uppdatera rasterbild, sidor och mått och rita om."""
        self._image = image
        self._tiles = tiles
        self._content_rect = content_rect
        self._page_w_mm = page_w_mm
        self._page_h_mm = page_h_mm
        self._page_extent_x = page_extent_x
        self._page_extent_y = page_extent_y
        self._img_px_per_unit = img_px_per_unit
        self._heading = heading
        self._update_size()
        self.update()

    def _update_size(self) -> None:
        page_w_px = int(self._page_w_mm * _SCREEN_SCALE)
        page_h_px = int(self._page_h_mm * _SCREEN_SCALE)
        if not self._tiles:
            self.setFixedSize(
                page_w_px + 2 * _PAGE_GAP_PX, page_h_px + 2 * _PAGE_GAP_PX
            )
            return
        total_w = page_w_px + 2 * _PAGE_GAP_PX
        total_h = len(self._tiles) * (page_h_px + _PAGE_GAP_PX) + _PAGE_GAP_PX
        self.setFixedSize(total_w, total_h)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        page_w_px = self._page_w_mm * _SCREEN_SCALE
        page_h_px = self._page_h_mm * _SCREEN_SCALE
        margin_px = _DEFAULT_MARGIN_MM * _SCREEN_SCALE

        for i, tile in enumerate(self._tiles):
            x_off = _PAGE_GAP_PX
            y_off = _PAGE_GAP_PX + i * (page_h_px + _PAGE_GAP_PX)

            # Skugga.
            painter.fillRect(
                QRectF(
                    x_off + _PAGE_SHADOW_OFFSET,
                    y_off + _PAGE_SHADOW_OFFSET,
                    page_w_px,
                    page_h_px,
                ),
                _PAGE_SHADOW_COLOR,
            )
            # Sidbakgrund.
            painter.fillRect(QRectF(x_off, y_off, page_w_px, page_h_px), _PAGE_BG_COLOR)
            # Sidram.
            painter.setPen(QPen(_PAGE_BORDER_COLOR, 1))
            painter.drawRect(QRectF(x_off, y_off, page_w_px, page_h_px))

            printable = QRectF(
                x_off + margin_px,
                y_off + margin_px,
                page_w_px - 2 * margin_px,
                page_h_px - 2 * margin_px,
            )

            # Rubrikbandet reserveras på alla sidor så att skalan är
            # identisk överallt (för tejpning), men själva rubriktexten
            # ritas bara på första sidan.
            diagram_area = printable
            if self._heading:
                heading_h = _HEADING_HEIGHT_MM * _SCREEN_SCALE
                if i == 0:
                    heading_rect = QRectF(
                        printable.left(), printable.top(), printable.width(), heading_h
                    )
                    _draw_heading(painter, heading_rect, self._heading)
                diagram_area = QRectF(
                    printable.left(),
                    printable.top() + heading_h,
                    printable.width(),
                    printable.height() - heading_h,
                )

            if self._image is not None and not tile.scene_rect.isEmpty():
                painter.save()
                painter.setClipRect(diagram_area)
                self._draw_tile(painter, tile, diagram_area)
                painter.restore()

            # Sidnummer.
            painter.setPen(QPen(QColor(120, 120, 120)))
            footer = QRectF(x_off, y_off + page_h_px - margin_px, page_w_px, margin_px)
            painter.drawText(
                footer,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                f"Sida {i + 1} av {len(self._tiles)}",
            )

        painter.end()

    def _draw_tile(
        self, painter: QPainter, tile: _PageTile, printable: QRectF
    ) -> None:
        """Rita en sidas utsnitt av rasterbilden, toppvänsterjusterat.

        En hel sida motsvarar ``page_extent_x × page_extent_y`` scenenheter;
        när ``scene_rect`` är mindre (p.g.a. en flyttad sidbrytning) fylls bara
        motsvarande del av sidan, resten lämnas tom. Samma skala används på
        alla sidor så att de kan tejpas ihop.
        """
        if self._image is None:
            return
        # Visningsskala: hur många skärmpixlar en scenenhet upptar inom
        # den utskriftsbara ytan (konstant för alla sidor).
        if self._page_extent_x <= 0 or self._page_extent_y <= 0:
            return
        view_px_per_unit = min(
            printable.width() / self._page_extent_x,
            printable.height() / self._page_extent_y,
        )

        _blit_tile(
            painter,
            self._image,
            tile,
            self._content_rect,
            self._img_px_per_unit,
            printable.topLeft(),
            view_px_per_unit,
        )


def _blit_tile(
    painter: QPainter,
    image: QImage,
    tile: _PageTile,
    content_rect: QRectF,
    img_px_per_unit: float,
    dest_origin,
    dest_px_per_unit: float,
) -> None:
    """Kopiera en sidas utsnitt ur rasterbilden till målytan.

    Utsnittet hämtas pixelexakt ur ``image`` baserat på sidans scenintervall
    och placeras toppvänsterjusterat vid ``dest_origin``. Eftersom alla sidor
    delar samma ``dest_px_per_unit`` och källbild blir skalan identisk och
    sidorna går att tejpa ihop.

    Args:
        painter: Aktiv QPainter på målytan.
        image: Rasterbilden över hela scenen.
        tile: Sidan som ska ritas.
        content_rect: Scenens innehållsgräns (scenekoordinater).
        img_px_per_unit: Bildpunkter per scenenhet i ``image``.
        dest_origin: QPointF där sidans innehåll ska börja (övre vänstra hörn).
        dest_px_per_unit: Målpixlar per scenenhet.
    """
    # Källutsnitt i bildpunkter.
    src_x = (tile.scene_rect.left() - content_rect.left()) * img_px_per_unit
    src_y = (tile.scene_rect.top() - content_rect.top()) * img_px_per_unit
    src_w = tile.scene_rect.width() * img_px_per_unit
    src_h = tile.scene_rect.height() * img_px_per_unit
    source = QRectF(src_x, src_y, src_w, src_h)

    # Målrektangel: toppvänsterjusterad, samma skala för alla sidor.
    dest_w = tile.scene_rect.width() * dest_px_per_unit
    dest_h = tile.scene_rect.height() * dest_px_per_unit
    target = QRectF(dest_origin.x(), dest_origin.y(), dest_w, dest_h)

    painter.drawImage(target, image, source)


def _draw_heading(painter: QPainter, rect: QRectF, text: str) -> None:
    """Rita rubriktexten vänsterjusterad inom ``rect``.

    Teckenstorleken härleds från bandets höjd så att rubriken ser likadan ut
    i förhandsgranskning och utskrift oavsett enheternas upplösning.

    Args:
        painter: Aktiv QPainter.
        rect: Rektangel där rubriken ska ritas (enhetskoordinater).
        text: Rubriktext.
    """
    painter.save()
    font = QFont("Segoe UI")
    # Använd ~60 % av bandhöjden som pixelstorlek för teckensnittet.
    pixel_size = max(1, int(rect.height() * 0.6))
    font.setPixelSize(pixel_size)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QPen(QColor(20, 20, 20)))
    painter.drawText(
        rect,
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        text,
    )
    painter.restore()


class DiagramPrintDialog(QDialog):
    """Dialog för förhandsgranskning, utskrift och PDF-export av en diagramvy.

    Scenen renderas skalad efter den aktuella zoomnivån. Om innehållet inte
    får plats på en sida delas det upp på flera sidor. Alla sidor använder
    samma skala och är toppvänsterjusterade så att de kan tejpas ihop, och
    sidbrytningar undviker att dela personrutor.

    Args:
        scene: Diagramscenen som ska skrivas ut.
        box_rects: Personrutornas gränser i scenekoordinater (för att undvika
            delning).
        zoom_factor: Aktuell zoomnivå (1.0 = 100%).
        view_title: Titel som visas i fönstret.
        heading: Rubrik som skrivs ut överst på varje sida, eller None.
        default_paper_size: Förvald pappersstorlek.
        parent: Valfri föräldrawidget.
    """

    def __init__(
        self,
        scene: QGraphicsScene,
        box_rects: list[QRectF],
        zoom_factor: float,
        view_title: str = "Diagram",
        heading: Optional[str] = None,
        default_paper_size: str = "A4",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._scene = scene
        self._box_rects = box_rects
        self._zoom_factor = max(0.01, zoom_factor)
        self._heading = heading
        self._content_rect = scene.itemsBoundingRect()
        self._tiles: list[_PageTile] = []
        self._raster: Optional[QImage] = None
        self._raster_px_per_unit: float = 1.0
        self._raster_background: Optional[bool] = None

        self.setWindowTitle(f"Skriv ut — {view_title}")
        self.resize(820, 900)

        self._setup_ui(default_paper_size)
        self._replan()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self, default_paper_size: str) -> None:
        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()

        toolbar.addWidget(QLabel("Pappersstorlek:"))
        self._paper_combo = QComboBox()
        for size in _PAPER_SIZES_MM:
            self._paper_combo.addItem(size)
        idx = self._paper_combo.findText(default_paper_size)
        if idx >= 0:
            self._paper_combo.setCurrentIndex(idx)
        self._paper_combo.currentTextChanged.connect(self._replan)
        toolbar.addWidget(self._paper_combo)

        toolbar.addWidget(QLabel("Orientering:"))
        self._orientation_combo = QComboBox()
        self._orientation_combo.addItem("Stående", "portrait")
        self._orientation_combo.addItem("Liggande", "landscape")
        self._orientation_combo.currentIndexChanged.connect(self._replan)
        toolbar.addWidget(self._orientation_combo)

        self._background_check = QCheckBox("Skriv ut bakgrundsfärg")
        self._background_check.setChecked(True)
        self._background_check.setToolTip(
            "Inkludera diagrammets bakgrundsfärg i utskriften"
        )
        self._background_check.toggled.connect(self._on_background_toggled)
        toolbar.addWidget(self._background_check)

        self._info_label = QLabel("")
        toolbar.addWidget(self._info_label)

        toolbar.addStretch()

        self._print_btn = QPushButton("Skriv ut")
        self._print_btn.clicked.connect(self._print)
        toolbar.addWidget(self._print_btn)

        self._export_btn = QPushButton("Exportera PDF")
        self._export_btn.clicked.connect(self._export_pdf)
        toolbar.addWidget(self._export_btn)

        layout.addLayout(toolbar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._canvas = _PreviewCanvas()
        self._scroll.setWidget(self._canvas)
        layout.addWidget(self._scroll)

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def _current_paper_mm(self) -> tuple[float, float]:
        """Returnera (bredd_mm, höjd_mm) för vald pappersstorlek och orientering."""
        name = self._paper_combo.currentText()
        w, h = _PAPER_SIZES_MM.get(name, _PAPER_SIZES_MM["A4"])
        if self._orientation_combo.currentData() == "landscape":
            w, h = h, w
        return w, h

    def _mm_per_scene_unit(self) -> float:
        """Fysiskt mm per scenenhet vid aktuell zoomnivå."""
        return _MM_PER_SCENE_UNIT_AT_100 * self._zoom_factor

    def _diagram_area_mm(self) -> tuple[float, float]:
        """Utskriftsbar diagramyta i mm (efter marginaler och rubrikband)."""
        page_w_mm, page_h_mm = self._current_paper_mm()
        printable_w_mm = max(1.0, page_w_mm - 2 * _DEFAULT_MARGIN_MM)
        printable_h_mm = max(1.0, page_h_mm - 2 * _DEFAULT_MARGIN_MM)
        if self._heading:
            printable_h_mm = max(1.0, printable_h_mm - _HEADING_HEIGHT_MM)
        return (printable_w_mm, printable_h_mm)

    def _page_extents(self) -> tuple[float, float]:
        """Diagramytans storlek per sida uttryckt i scenekoordinater."""
        area_w_mm, area_h_mm = self._diagram_area_mm()
        mm_per_unit = self._mm_per_scene_unit()
        return (area_w_mm / mm_per_unit, area_h_mm / mm_per_unit)

    def _ensure_raster(self) -> None:
        """Rastrera hela scenen en gång (eller återanvänd befintlig bild).

        Rasterbilden beror bara på zoomnivån och bakgrundsvalet, inte på
        pappersstorlek eller orientering, så den återanvänds mellan omplaner.
        """
        want_bg = self._background_check.isChecked()
        if self._raster is not None and self._raster_background == want_bg:
            return

        if self._content_rect.isEmpty():
            self._raster = None
            return

        # Bildpunkter per scenenhet vid målupplösningen och aktuell zoom.
        px_per_unit = (_RASTER_DPI / _MM_PER_INCH) * self._mm_per_scene_unit()

        # Begränsa den totala bildstorleken av minnesskäl.
        est_pixels = (
            self._content_rect.width()
            * self._content_rect.height()
            * px_per_unit
            * px_per_unit
        )
        if est_pixels > _MAX_RASTER_PIXELS:
            px_per_unit *= (_MAX_RASTER_PIXELS / est_pixels) ** 0.5

        self._raster = _render_scene_to_image(
            self._scene, self._content_rect, px_per_unit, want_bg
        )
        self._raster_px_per_unit = px_per_unit
        self._raster_background = want_bg

    def _on_background_toggled(self, _checked: bool) -> None:
        """Bakgrundsvalet ändrades — invalidera rastret och planera om."""
        self._raster = None
        self._replan()

    def _replan(self) -> None:
        """Räkna om sidrutnätet och uppdatera förhandsgranskningen."""
        page_w_mm, page_h_mm = self._current_paper_mm()
        page_extent_x, page_extent_y = self._page_extents()

        content = self._content_rect
        if content.isEmpty():
            self._tiles = []
            self._canvas.set_content(
                None, [], content, page_w_mm, page_h_mm, 0.0, 0.0, 1.0, self._heading
            )
            self._update_info()
            return

        self._tiles = plan_pages(
            content, self._box_rects, page_extent_x, page_extent_y
        )

        self._ensure_raster()

        self._canvas.set_content(
            self._raster,
            self._tiles,
            content,
            page_w_mm,
            page_h_mm,
            page_extent_x,
            page_extent_y,
            self._raster_px_per_unit,
            self._heading,
        )
        self._update_info()

    def _update_info(self) -> None:
        n = len(self._tiles)
        self._info_label.setText(
            f"  {n} sid{'a' if n == 1 else 'or'} ({int(self._zoom_factor * 100)}%)"
        )
        has_pages = n > 0
        self._print_btn.setEnabled(has_pages)
        self._export_btn.setEnabled(has_pages)

    # ------------------------------------------------------------------
    # Printing / export
    # ------------------------------------------------------------------

    def _configure_printer(self, printer: QPrinter) -> None:
        name = self._paper_combo.currentText()
        page_size_id = _PAGE_SIZE_IDS.get(name, QPageSize.PageSizeId.A4)
        orientation = (
            QPageLayout.Orientation.Landscape
            if self._orientation_combo.currentData() == "landscape"
            else QPageLayout.Orientation.Portrait
        )
        margins = QMarginsF(
            _DEFAULT_MARGIN_MM, _DEFAULT_MARGIN_MM, _DEFAULT_MARGIN_MM, _DEFAULT_MARGIN_MM
        )
        printer.setPageLayout(
            QPageLayout(
                QPageSize(page_size_id),
                orientation,
                margins,
                QPageLayout.Unit.Millimeter,
            )
        )

    def _print(self) -> None:
        """Öppna utskriftsdialog och skriv ut alla sidor."""
        if not self._tiles:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        self._configure_printer(printer)
        dialog = QPrintDialog(printer, self)
        dialog.setWindowTitle("Skriv ut diagram")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        # Den inbyggda utskriftsdialogen kan återställa sidlayouten (t.ex.
        # orienteringen) till skrivarens standard. Återapplicera vårt val
        # innan vi målar så att liggande/stående följer dialogens inställning.
        self._configure_printer(printer)
        self._paint_to_device(printer)

    def _export_pdf(self) -> None:
        """Öppna fildialog och exportera alla sidor till PDF."""
        if not self._tiles:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Exportera diagram som PDF",
            "",
            "PDF-filer (*.pdf)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".pdf"):
            file_path += ".pdf"

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(file_path)
        self._configure_printer(printer)

        try:
            self._paint_to_device(printer)
            if not Path(file_path).exists():
                raise OSError("Filen skapades inte")
        except OSError as exc:
            logger.error("PDF-export misslyckades: %s", exc)
            QMessageBox.critical(
                self,
                "Exportfel",
                f"Kunde inte exportera PDF-filen.\n\nSökväg: {file_path}\nFel: {exc}",
            )

    def _paint_to_device(self, printer: QPrinter) -> None:
        """Rendera alla sidor till en QPrinter (utskrift eller PDF).

        Varje sida ritas från den gemensamma rasterbilden, toppvänsterjusterat
        och med samma skala, så att sidorna kan tejpas ihop.
        """
        self._ensure_raster()
        if self._raster is None or not self._tiles:
            return

        page_extent_x, page_extent_y = self._page_extents()
        if page_extent_x <= 0 or page_extent_y <= 0:
            return

        painter = QPainter()
        if not painter.begin(printer):
            raise OSError("Kunde inte starta utskriften")
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            page_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
            printable = QRectF(0, 0, page_rect.width(), page_rect.height())

            # Rubrikbandets höjd i enhetspixlar (härledd från sidans mm-höjd).
            _, printable_h_mm = self._diagram_area_mm()
            total_printable_h_mm = printable_h_mm + (
                _HEADING_HEIGHT_MM if self._heading else 0.0
            )
            heading_px = 0.0
            if self._heading and total_printable_h_mm > 0:
                heading_px = (
                    _HEADING_HEIGHT_MM / total_printable_h_mm
                ) * printable.height()

            diagram_area = QRectF(
                printable.left(),
                printable.top() + heading_px,
                printable.width(),
                printable.height() - heading_px,
            )

            # Målpixlar per scenenhet — konstant för alla sidor.
            dest_px_per_unit = min(
                diagram_area.width() / page_extent_x,
                diagram_area.height() / page_extent_y,
            )

            for i, tile in enumerate(self._tiles):
                if i > 0:
                    printer.newPage()

                # Rubriktexten visas bara på första sidan; bandet reserveras
                # dock på alla sidor så att skalan förblir identisk (tejpbar).
                if self._heading and i == 0:
                    heading_rect = QRectF(
                        printable.left(), printable.top(), printable.width(), heading_px
                    )
                    _draw_heading(painter, heading_rect, self._heading)

                if tile.scene_rect.isEmpty():
                    continue
                painter.save()
                painter.setClipRect(diagram_area)
                _blit_tile(
                    painter,
                    self._raster,
                    tile,
                    self._content_rect,
                    self._raster_px_per_unit,
                    diagram_area.topLeft(),
                    dest_px_per_unit,
                )
                painter.restore()
        finally:
            painter.end()
