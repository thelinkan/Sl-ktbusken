"""List delegate drawing trailing "map pin" and "has source" icons.

Order after the item text: map pin (when ``HAS_COORDS_ROLE`` is set), source
icon (when ``HAS_SOURCE_ROLE`` is set), then the research dot. The source icon
is not clickable; hovering it shows the cited sources as a tooltip.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QToolTip, QWidget

from slaktbusken.ui.icons.icon_registry import icon_registry
from slaktbusken.ui.widgets.research_marker import paint_research_dot

#: True when the item's place has coordinates (draws the map pin).
HAS_COORDS_ROLE = Qt.ItemDataRole.UserRole + 1
#: True when the item cites at least one source (draws the source icon).
HAS_SOURCE_ROLE = Qt.ItemDataRole.UserRole + 40
#: List of cited source titles (distinct, in order) for the tooltip.
SOURCE_TITLES_ROLE = Qt.ItemDataRole.UserRole + 41

MAX_TOOLTIP_SOURCES = 10


def sources_tooltip(titles: list[str]) -> str:
    """Build the "Källor:" tooltip, capped at ``MAX_TOOLTIP_SOURCES`` lines."""
    lines = ["Källor:"] + [f"• {t}" for t in titles[:MAX_TOOLTIP_SOURCES]]
    rest = len(titles) - MAX_TOOLTIP_SOURCES
    if rest > 0:
        lines.append(f"… och {rest} till")
    return "\n".join(lines)


class ListIconDelegate(QStyledItemDelegate):
    """Draws map pin, source icon and research dot after an item's text."""

    _ICON_SIZE = 14
    _ICON_SPACING = 8
    _DECORATION_WIDTH = 16 + 4

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._map_pixmap: QPixmap | None = None
        self._source_pixmap: QPixmap | None = None

    def _get_map_pixmap(self) -> QPixmap:
        if self._map_pixmap is None:
            self._map_pixmap = icon_registry.get_map_icon()
        return self._map_pixmap

    def _get_source_pixmap(self) -> QPixmap:
        if self._source_pixmap is None:
            self._source_pixmap = icon_registry.get_source_icon()
        return self._source_pixmap

    def icon_rects(
        self, option: QStyleOptionViewItem, index
    ) -> tuple[QRect | None, QRect | None, int]:
        """Return ``(pin_rect, source_rect, research_dot_extra_offset)``."""
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        text_width = option.fontMetrics.horizontalAdvance(text)
        icon_offset = (
            self._DECORATION_WIDTH
            if index.data(Qt.ItemDataRole.DecorationRole) is not None
            else 0
        )
        style = option.widget.style() if option.widget else None
        text_margin = (
            style.pixelMetric(style.PixelMetric.PM_FocusFrameHMargin, option, option.widget) + 1
            if style
            else 4
        )
        x = option.rect.left() + text_margin + icon_offset + text_width
        y = option.rect.top() + (option.rect.height() - self._ICON_SIZE) // 2
        step = self._ICON_SPACING + self._ICON_SIZE

        pin_rect = source_rect = None
        used = 0
        if index.data(HAS_COORDS_ROLE):
            pin_rect = QRect(x + used + self._ICON_SPACING, y, self._ICON_SIZE, self._ICON_SIZE)
            used += step
        if index.data(HAS_SOURCE_ROLE):
            source_rect = QRect(
                x + used + self._ICON_SPACING, y, self._ICON_SIZE, self._ICON_SIZE
            )
            used += step
        return pin_rect, source_rect, used

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        super().paint(painter, option, index)
        pin_rect, source_rect, used = self.icon_rects(option, index)
        if pin_rect is not None:
            painter.drawPixmap(pin_rect, self._get_map_pixmap())
        if source_rect is not None:
            painter.drawPixmap(source_rect, self._get_source_pixmap())
        paint_research_dot(
            painter, option, index, extra_offset=used, icon_width=self._DECORATION_WIDTH
            if index.data(Qt.ItemDataRole.DecorationRole) is not None
            else 0,
        )

    def helpEvent(self, event, view, option, index) -> bool:
        """Show the sources tooltip over the source icon; otherwise the item tooltip."""
        if event.type() == QEvent.Type.ToolTip and index.isValid():
            _pin, source_rect, _used = self.icon_rects(option, index)
            titles = index.data(SOURCE_TITLES_ROLE)
            if source_rect is not None and titles and source_rect.contains(event.pos()):
                QToolTip.showText(event.globalPos(), sources_tooltip(list(titles)), view, source_rect)
                return True
        return super().helpEvent(event, view, option, index)
