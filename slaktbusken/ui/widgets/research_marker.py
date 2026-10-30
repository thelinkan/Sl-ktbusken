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

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QBrush, QColor, QPainter
from PySide6.QtWidgets import QListWidgetItem, QStyledItemDelegate, QStyleOptionViewItem

from slaktbusken.services.research_index import ResearchCaseCounts
from slaktbusken.ui.widgets.research_indicator import (
    indicator_color,
    indicator_state,
    indicator_tooltip,
)

#: Item data role holding the marker colour (a "#RRGGBB" string); absent for no marker.
MARKER_COLOR_ROLE = Qt.ItemDataRole.UserRole + 20

DOT_DIAMETER = 8
DOT_SPACING = 4


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

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(QBrush(QColor(color)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRect(x, y, DOT_DIAMETER, DOT_DIAMETER))
    painter.restore()


class ResearchMarkerDelegate(QStyledItemDelegate):
    """Delegate that paints the research dot after an item's text."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        super().paint(painter, option, index)
        paint_research_dot(painter, option, index)
