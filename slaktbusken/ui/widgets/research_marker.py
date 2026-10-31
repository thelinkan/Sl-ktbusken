"""Research markers for list views.

A small coloured dot after an item's text shows that research cases link the
entity directly: orange when at least one is not closed, grey when all are
closed (never green; see ``research_indicator``). Only directly linked cases are
counted, and a link to a deleted entity contributes nothing because the
``ResearchIndex`` never returns it.

Usage in a list view::

    index = ResearchIndex(project_data)
    ...
    apply_research_marker(item, index.counts_for_entity("place", place.id))
    list_widget.setItemDelegate(ResearchMarkerDelegate(list_widget))
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QListWidgetItem, QStyledItemDelegate, QStyleOptionViewItem

from slaktbusken.services.research_index import ResearchCaseCounts
from slaktbusken.ui.widgets.research_indicator import (
    indicator_color,
    indicator_state,
    indicator_tooltip,
)

#: Item data role holding the marker colour (a "#RRGGBB" string); absent for no marker.
MARKER_COLOR_ROLE = Qt.ItemDataRole.UserRole + 20

DOT_DIAMETER = 12  # width of the marker icon in lists
DOT_SPACING = 4

_icon_cache: dict[tuple[str, int], QPixmap] = {}


def research_icon(color: str, size: int = 14) -> QPixmap:
    """Return a magnifying-glass pixmap in the given colour.

    The glass is drawn rather than loaded from a file so it can take the
    indicator colour (orange for open research, grey when all is closed).
    """
    key = (color, size)
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached

    scale = 4  # draw large and scale down for smooth edges
    big = size * scale
    pixmap = QPixmap(big, big)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(big * 0.13)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    # Lens: upper-left circle; handle: diagonal to the lower-right corner.
    lens = big * 0.60
    margin = big * 0.10
    painter.drawEllipse(QRectF(margin, margin, lens, lens))
    start = margin + lens * 0.5 + (lens * 0.5) * 0.7071
    end = big - margin * 1.3
    painter.drawLine(QPointF(start, start), QPointF(end, end))
    painter.end()

    result = pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    _icon_cache[key] = result
    return result


def apply_research_marker(item: QListWidgetItem, counts: ResearchCaseCounts) -> bool:
    """Mark a list item according to its entity's research counts.

    Sets the colour role and appends the indicator text to the tooltip. An entity
    with no research leaves the item untouched.

    Returns:
        True if a marker was set.
    """
    color = indicator_color(indicator_state(counts))
    if color is None:
        item.setData(MARKER_COLOR_ROLE, None)
        return False
    item.setData(MARKER_COLOR_ROLE, color)
    tooltip = indicator_tooltip(counts)
    existing = item.toolTip()
    item.setToolTip(f"{existing}\n{tooltip}" if existing else tooltip)
    return True


def paint_research_dot(
    painter: QPainter,
    option: QStyleOptionViewItem,
    index,
    extra_offset: int = 0,
    icon_width: int = 0,
) -> None:
    """Draw the research dot after the item text, if the item is marked.

    Args:
        painter: The painter used by the delegate.
        option: The delegate's style option.
        index: The model index being painted.
        extra_offset: Pixels already used after the text by another marker.
        icon_width: Width taken by a leading decoration, when there is one.
    """
    color = index.data(MARKER_COLOR_ROLE)
    if not color:
        return

    text = index.data(Qt.ItemDataRole.DisplayRole) or ""
    text_width = option.fontMetrics.horizontalAdvance(text)
    style = option.widget.style() if option.widget else None
    text_margin = (
        style.pixelMetric(style.PixelMetric.PM_FocusFrameHMargin, option, option.widget) + 1
        if style
        else 4
    )
    if icon_width == 0 and index.data(Qt.ItemDataRole.DecorationRole) is not None:
        icon_width = option.decorationSize.width() + 4

    x = option.rect.left() + text_margin + icon_width + text_width + DOT_SPACING + extra_offset
    y = option.rect.top() + (option.rect.height() - DOT_DIAMETER) // 2

    painter.drawPixmap(x, y, research_icon(color, DOT_DIAMETER))


# ---------------------------------------------------------------------------
# Diagram render context
# ---------------------------------------------------------------------------
#
# The diagram builds the display data of dozens of boxes per render. Building a
# ResearchIndex for each would be wasteful, so the panel builds one index at the
# start of a render and the box data builders read counts from it.

_diagram_index = None


def begin_diagram_render(project_data, enabled: bool = True) -> None:
    """Build the research index used by the person boxes of one render.

    Pass ``enabled=False`` (or no data) when the diagram research indicator is
    switched off, so no index is built.
    """
    global _diagram_index
    from slaktbusken.services.research_index import ResearchIndex

    _diagram_index = ResearchIndex(project_data) if enabled and project_data is not None else None


def diagram_research_counts(person_id: str) -> ResearchCaseCounts:
    """Return the direct research counts of a person for the current render."""
    if _diagram_index is None:
        return ResearchCaseCounts(0, 0)
    return _diagram_index.counts_for_entity("person", person_id)


class ResearchMarkerDelegate(QStyledItemDelegate):
    """Delegate that paints the research dot after an item's text."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        super().paint(painter, option, index)
        paint_research_dot(painter, option, index)
