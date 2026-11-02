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

from typing import Optional

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
_diagram_candidate_index = None
_diagram_data = None
_diagram_summaries = None


def begin_diagram_render(
    project_data, enabled: bool = True, candidates_enabled: bool = False
) -> None:
    """Build the research and candidate indexes used by the person boxes of one render.

    Pass ``enabled=False`` (or no data) when the diagram research indicator is
    switched off, so no research index is built. ``candidates_enabled`` is
    ``PersonBoxConfig.merge_candidates``; when false no ``CandidateIndex`` is
    built at all. Exactly one of each index is built per render.
    """
    global _diagram_index, _diagram_candidate_index, _diagram_data, _diagram_summaries
    from slaktbusken.services.research_index import ResearchIndex

    _diagram_index = ResearchIndex(project_data) if enabled and project_data is not None else None

    _diagram_data = project_data
    _diagram_summaries = None
    _diagram_candidate_index = None
    if candidates_enabled and project_data is not None:
        from slaktbusken.services.candidate_index import CandidateIndex

        _diagram_candidate_index = CandidateIndex.build(project_data)

    # Render-scoped lookup that replaces the per-box scans of the diagram views.
    from slaktbusken.services.diagram_lookup import begin_lookup

    begin_lookup(project_data)


def diagram_research_counts(person_id: str) -> ResearchCaseCounts:
    """Return the direct research counts of a person for the current render."""
    if _diagram_index is None:
        return ResearchCaseCounts(0, 0)
    return _diagram_index.counts_for_entity("person", person_id)


def diagram_candidate_state(person_id: str) -> Optional[dict]:
    """Return the candidate indicator state of a person for the current render.

    ``None`` when the candidate setting is off or the person has no indicator.
    Otherwise a dict with ``colour`` ("blue", "orange" or "grey"), ``kind``
    ("candidates", or "history" when grey only because of Merge_History) and
    ``tooltip`` (a callable building the lines lazily on hover).
    """
    index = _diagram_candidate_index
    if index is None:
        return None
    from slaktbusken.services.candidate_index import NONE

    colour = index.colour(person_id)
    if colour == NONE:
        return None
    kind = "candidates" if index.relations(person_id).candidates else "history"

    return {
        "colour": colour,
        "kind": kind,
        "tooltip": CandidateTooltip(index, person_id),
    }


class CandidateTooltip:
    """Lazy, comparable builder of a person's candidate tooltip lines.

    Two instances are equal when they describe the same person in the same
    render's candidate index, so display data built by different views compares
    equal.
    """

    __slots__ = ("_index", "_person_id")

    def __init__(self, index, person_id: str) -> None:
        self._index = index
        self._person_id = person_id

    def __call__(self) -> list[str]:
        global _diagram_summaries
        if _diagram_summaries is None:
            from slaktbusken.services.person_summary import PersonSummaryIndex

            _diagram_summaries = PersonSummaryIndex.build(_diagram_data)
        return self._index.tooltip_lines(self._person_id, _diagram_summaries)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CandidateTooltip):
            return NotImplemented
        return self._index is other._index and self._person_id == other._person_id

    def __hash__(self) -> int:
        return hash((id(self._index), self._person_id))


class ResearchMarkerDelegate(QStyledItemDelegate):
    """Delegate that paints the research dot after an item's text."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        super().paint(painter, option, index)
        paint_research_dot(painter, option, index)
