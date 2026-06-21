"""Person box graphics item for diagram views.

Renders a person's information in a configurable box within the
QGraphicsScene. Which fields are displayed is controlled by a
PersonBoxConfig instance from settings_io.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QToolTip,
    QWidget,
)

from slaktbusken.ui.icons.icon_registry import icon_registry

if TYPE_CHECKING:
    from slaktbusken.model.name_parser import ParsedGivenName
    from slaktbusken.persistence.settings_io import PersonBoxConfig

# Default box dimensions
_BOX_WIDTH = 240.0
_BOX_HEIGHT_MIN = 50.0
_LINE_HEIGHT = 16.0
_PADDING = 8.0
_CORNER_RADIUS = 4.0
_GENDER_ICON_SIZE = 14.0
_EVENT_ICON_SIZE = 12.0
_EVENT_ICON_GAP = 2.0

# Photo and icon sizes
_PHOTO_SIZE = 40.0
_PHOTO_GAP = 8.0
_DNA_LOGO_SIZE = 16.0
_MULTIPLE_NAMES_ICON_SIZE = 14.0

# Limits
_MAX_DNA_LOGOS = 5
_MAX_CLUSTERS = 5
_CAUSE_OF_DEATH_MAX_LEN = 50

# Colours
_BG_COLOR = QColor(255, 255, 255)
_BORDER_COLOR = QColor(80, 80, 80)
_SELECTED_BORDER_COLOR = QColor(0, 120, 215)
_ANCESTOR_BORDER_COLOR = QColor(0xC0, 0x39, 0x2B)
_DESCENDANT_BORDER_COLOR = QColor(0x27, 0xAE, 0x60)
_MAIN_PERSON_BORDER_COLOR = QColor(0xF3, 0x9C, 0x12)
_TEXT_COLOR = QColor(30, 30, 30)
_LABEL_COLOR = QColor(100, 100, 100)
_MULTI_NAMES_COLOR = QColor("#2980B9")  # Blue marker for multiple names


class PersonBoxItem(QGraphicsItem):
    """A graphics item displaying a person's configured fields.

    Renders a rectangular box with a subset of person data fields
    as determined by the PersonBoxConfig. Supports visual selection
    highlighting and click/double-click interactions.

    Args:
        person_id: The unique ID of the person.
        display_data: Dictionary of field values to render. Keys
            correspond to PersonBoxConfig field names; values are
            the display strings (or None if no data).
        config: PersonBoxConfig controlling which fields are shown.
        parent: Optional parent QGraphicsItem.
    """

    def __init__(
        self,
        person_id: str,
        display_data: dict[str, Optional[str]],
        config: PersonBoxConfig,
        parent: Optional[QGraphicsItem] = None,
    ) -> None:
        """Initialise the person box item.

        Args:
            person_id: The unique ID of the person.
            display_data: Dictionary mapping field names to display values.
            config: PersonBoxConfig determining visible fields.
            parent: Optional parent graphics item.
        """
        super().__init__(parent)
        self._person_id = person_id
        self._display_data = display_data
        self._config = config
        self._selected = False
        self._is_ancestor: bool = bool(display_data.get("is_ancestor"))
        self._is_descendant: bool = bool(display_data.get("is_descendant"))
        self._is_main_person: bool = bool(display_data.get("is_main_person"))
        self._lines: list[str] = []
        self._line_event_types: list[Optional[str]] = []
        self._cluster_line_start: int = 0

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self._build_lines()

    @property
    def person_id(self) -> str:
        """The person ID associated with this box."""
        return self._person_id

    @property
    def box_height(self) -> float:
        """The actual rendered height of this box."""
        return max(
            _BOX_HEIGHT_MIN,
            len(self._lines) * _LINE_HEIGHT + 2 * _PADDING,
        )

    @property
    def is_selected(self) -> bool:
        """Whether this box is visually selected."""
        return self._selected

    @property
    def is_ancestor(self) -> bool:
        """Whether this person is marked as a direct ancestor."""
        return self._is_ancestor

    @property
    def is_descendant(self) -> bool:
        """Whether this person is marked as a direct descendant."""
        return self._is_descendant

    @property
    def is_main_person(self) -> bool:
        """Whether this person is the main/root person of the project."""
        return self._is_main_person

    def set_selected(self, selected: bool) -> None:
        """Set the visual selection state.

        Args:
            selected: True to show selection highlight.
        """
        self._selected = selected
        self.update()

    def boundingRect(self) -> QRectF:
        """Return the bounding rectangle of this item.

        Returns:
            The bounding rect encompassing the box and border.
        """
        height = max(
            _BOX_HEIGHT_MIN,
            len(self._lines) * _LINE_HEIGHT + 2 * _PADDING,
        )
        # Extra pixel for pen width
        return QRectF(-1, -1, _BOX_WIDTH + 2, height + 2)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: Optional[QWidget] = None,
    ) -> None:
        """Paint the person box.

        Renders the box background, border (highlighted if selected),
        and configured content fields. Fields with no data are omitted
        per Req 20.4. The name line renders the tilltalsnamn (if any)
        with an underline decoration.

        Args:
            painter: The QPainter to draw with.
            option: Style options (unused).
            widget: The widget being painted on (unused).
        """
        height = max(
            _BOX_HEIGHT_MIN,
            len(self._lines) * _LINE_HEIGHT + 2 * _PADDING,
        )
        rect = QRectF(0, 0, _BOX_WIDTH, height)

        # Background
        painter.setBrush(QBrush(_BG_COLOR))

        # Border
        if self._selected:
            pen = QPen(_SELECTED_BORDER_COLOR, 2.5)
        elif self._is_main_person:
            pen = QPen(_MAIN_PERSON_BORDER_COLOR, 2.5)
        elif self._is_ancestor:
            pen = QPen(_ANCESTOR_BORDER_COLOR, 2.0)
        elif self._is_descendant:
            pen = QPen(_DESCENDANT_BORDER_COLOR, 2.0)
        else:
            pen = QPen(_BORDER_COLOR, 1.0)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, _CORNER_RADIUS, _CORNER_RADIUS)

        # Gender icon in top-right corner (Req 2.2, 2.4)
        sex = self._display_data.get("sex")
        if sex:
            gender_pixmap = icon_registry.get_gender_icon(sex)
            if not gender_pixmap.isNull():
                icon_x = _BOX_WIDTH - _GENDER_ICON_SIZE - _PADDING / 2
                icon_y = _PADDING / 2
                icon_rect = QRectF(
                    icon_x, icon_y, _GENDER_ICON_SIZE, _GENDER_ICON_SIZE
                )
                painter.drawPixmap(icon_rect.toRect(), gender_pixmap)

        # Multiple names indicator in top-left corner (Req 1.1, 1.2, 1.4)
        self._paint_multiple_names_icon(painter)

        # Profile photo (Req 4.1, 4.6)
        self._paint_profile_photo(painter)

        # Compute text x-offset for profile photo (Req 4.2, 4.3, 4.4)
        photo_offset = self._get_photo_text_offset()

        # Text content
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        painter.setPen(QPen(_TEXT_COLOR))

        y = _PADDING + _LINE_HEIGHT * 0.8
        for i, line in enumerate(self._lines):
            # Skip cluster placeholder lines — rendered by _paint_cluster_lines
            if i >= self._cluster_line_start:
                break
            if i == 0:
                # Name line in bold — with optional tilltalsnamn underline
                self._paint_name_line(painter, y, photo_offset)
            else:
                painter.setPen(QPen(_LABEL_COLOR))
                # Check if this line has an associated event icon
                event_type = (
                    self._line_event_types[i]
                    if i < len(self._line_event_types)
                    else None
                )
                text_x = _PADDING + photo_offset
                if event_type:
                    event_pixmap = icon_registry.get_event_icon(event_type)
                    if not event_pixmap.isNull():
                        icon_y = y - _LINE_HEIGHT * 0.8 + (_LINE_HEIGHT - _EVENT_ICON_SIZE) / 2
                        icon_rect = QRectF(
                            _PADDING + photo_offset, icon_y,
                            _EVENT_ICON_SIZE, _EVENT_ICON_SIZE,
                        )
                        painter.drawPixmap(icon_rect.toRect(), event_pixmap)
                        text_x = _PADDING + photo_offset + _EVENT_ICON_SIZE + _EVENT_ICON_GAP
                available_width = _BOX_WIDTH - text_x - _PADDING
                fm = QFontMetrics(painter.font())
                elided_line = fm.elidedText(
                    line,
                    Qt.TextElideMode.ElideRight,
                    int(available_width),
                )
                painter.drawText(
                    QRectF(
                        text_x,
                        y - _LINE_HEIGHT * 0.8,
                        available_width,
                        _LINE_HEIGHT,
                    ),
                    Qt.AlignmentFlag.AlignLeft,
                    elided_line,
                )
                painter.setPen(QPen(_TEXT_COLOR))
            y += _LINE_HEIGHT

        # Cluster names (Req 7.1–7.6)
        self._paint_cluster_lines(painter)

        # DNA company logos in bottom-right corner (Req 2.1–2.6)
        self._paint_dna_logos(painter)

    def _paint_multiple_names_icon(self, painter: QPainter) -> None:
        """Paint the multiple-names indicator to the left of the name line.

        Draws a bold blue "≡" character (matching the personlista style)
        vertically centered on the name line, at x = _PADDING / 2.
        The name line is shifted right by _MULTIPLE_NAMES_ICON_SIZE
        to make room. This indicator is always shown regardless of
        PersonBoxConfig toggles (Req 1.4).

        Args:
            painter: The QPainter to draw with.
        """
        if not self._display_data.get("has_multiple_names"):
            return

        painter.save()
        painter.setPen(QPen(_MULTI_NAMES_COLOR))
        font = QFont("Segoe UI", 8)
        font.setBold(True)
        painter.setFont(font)
        # Position vertically centered on the name line (first line)
        name_line_top = _PADDING
        marker_rect = QRectF(
            _PADDING / 2, name_line_top,
            _MULTIPLE_NAMES_ICON_SIZE, _LINE_HEIGHT,
        )
        painter.drawText(marker_rect, Qt.AlignmentFlag.AlignCenter, "≡")
        painter.restore()

    def _get_photo_text_offset(self) -> float:
        """Compute the horizontal text offset when a profile photo is present.

        Returns 48.0 (photo width + gap) when photo config is enabled AND
        a valid profile_photo pixmap exists. Otherwise returns 0.0, meaning
        text uses normal left padding (Req 4.2, 4.3, 4.4).

        Returns:
            The x-offset in pixels to add to text positions.
        """
        if not self._config.photo:
            return 0.0
        photo: QPixmap | None = self._display_data.get("profile_photo")
        if photo is None or photo.isNull():
            return 0.0
        return _PHOTO_SIZE + _PHOTO_GAP

    def _paint_profile_photo(self, painter: QPainter) -> None:
        """Paint the profile photo thumbnail on the left side of the card.

        Draws the pre-scaled pixmap centered within a 40×40 area at
        (_PADDING, _PADDING). The source image is scaled to fit within
        40×40 preserving aspect ratio. If no valid photo is available,
        nothing is drawn and no space is reserved (Req 4.1, 4.3, 4.4, 4.6).

        Args:
            painter: The QPainter to draw with.
        """
        if not self._config.photo:
            return
        photo: QPixmap | None = self._display_data.get("profile_photo")
        if photo is None or photo.isNull():
            return

        # Scale to fit within _PHOTO_SIZE x _PHOTO_SIZE preserving aspect ratio
        scaled = photo.scaled(
            int(_PHOTO_SIZE),
            int(_PHOTO_SIZE),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        # Center the scaled pixmap within the 40×40 area
        x_offset = (_PHOTO_SIZE - scaled.width()) / 2.0
        y_offset = (_PHOTO_SIZE - scaled.height()) / 2.0

        draw_x = _PADDING + x_offset
        draw_y = _PADDING + y_offset

        painter.drawPixmap(
            QRectF(draw_x, draw_y, scaled.width(), scaled.height()).toRect(),
            scaled,
        )

    def _paint_name_line(self, painter: QPainter, y: float, photo_offset: float = 0.0) -> None:
        """Paint the name line with selective underline for tilltalsnamn.

        If display_data contains a valid ParsedGivenName with a
        tilltalsnamn_index, draws each name part individually with
        the tilltalsnamn part underlined. Otherwise renders the name
        as a single string without underline (existing behaviour).

        Args:
            painter: The QPainter to draw with.
            y: The baseline y-coordinate for text rendering.
            photo_offset: Horizontal offset for profile photo (0 if no photo).
        """
        name_parsed: ParsedGivenName | None = self._display_data.get("name_parsed")

        bold_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setPen(QPen(_TEXT_COLOR))

        # Shift name right when multiple-names marker is present
        name_x_start = _PADDING + photo_offset
        if self._display_data.get("has_multiple_names"):
            name_x_start = _PADDING + photo_offset + _MULTIPLE_NAMES_ICON_SIZE

        if (
            name_parsed is not None
            and name_parsed.tilltalsnamn_index is not None
            and name_parsed.parts
            and 0 <= name_parsed.tilltalsnamn_index < len(name_parsed.parts)
        ):
            # Draw name parts individually with selective underline
            fm = QFontMetrics(bold_font)
            x = name_x_start
            space_width = fm.horizontalAdvance(" ")

            for idx, part in enumerate(name_parsed.parts):
                if idx == name_parsed.tilltalsnamn_index:
                    # Underline the tilltalsnamn part
                    underline_font = QFont(bold_font)
                    underline_font.setUnderline(True)
                    painter.setFont(underline_font)
                else:
                    bold_font.setUnderline(False)
                    painter.setFont(bold_font)

                painter.drawText(
                    x,
                    y,
                    part,
                )
                part_width = fm.horizontalAdvance(part)
                x += part_width + space_width

            # Draw surname (if present) after the given name parts
            # The full name line includes the surname after the given display string
            bold_font.setUnderline(False)
            painter.setFont(bold_font)
            name_line = self._lines[0] if self._lines else ""
            given_display = name_parsed.display_string
            if name_line.startswith(given_display) and len(name_line) > len(given_display):
                surname_part = name_line[len(given_display):].lstrip()
                if surname_part:
                    painter.drawText(x, y, surname_part)
        else:
            # No tilltalsnamn marker — render name line normally (no underline)
            painter.setFont(bold_font)
            name_text = self._lines[0] if self._lines else ""
            painter.drawText(
                QRectF(
                    name_x_start,
                    y - _LINE_HEIGHT * 0.8,
                    _BOX_WIDTH - name_x_start - _PADDING,
                    _LINE_HEIGHT,
                ),
                Qt.AlignmentFlag.AlignLeft,
                name_text,
            )

        # Restore regular font for subsequent lines
        regular_font = QFont("Segoe UI", 9)
        painter.setFont(regular_font)

    def _paint_dna_logos(self, painter: QPainter) -> None:
        """Paint DNA company logos in the bottom-right corner of the card.

        Draws up to 5 company logos (16×16) horizontally, ordered
        alphabetically by company name from left to right. For companies
        without a logo pixmap, a 2-character text placeholder is rendered
        on a light gray background (Req 2.1, 2.2, 2.3, 2.4, 2.5, 2.6).

        Does nothing when the dna_info config toggle is disabled or when
        there are no DNA profiles for this person.

        Args:
            painter: The QPainter to draw with.
        """
        if not self._config.dna_info:
            return

        dna_companies: list[dict] | None = self._display_data.get("dna_companies")
        if not dna_companies:
            return

        # Limit to max 5 logos
        logos = dna_companies[:_MAX_DNA_LOGOS]
        n = len(logos)

        # Calculate positions: right-aligned in bottom-right corner
        gap = 2.0
        total_width = n * _DNA_LOGO_SIZE + (n - 1) * gap
        start_x = _BOX_WIDTH - _PADDING / 2 - total_width
        y = self.box_height - _DNA_LOGO_SIZE - _PADDING / 2

        painter.save()
        for i, company in enumerate(logos):
            x = start_x + i * (_DNA_LOGO_SIZE + gap)
            logo_rect = QRectF(x, y, _DNA_LOGO_SIZE, _DNA_LOGO_SIZE)

            logo: QPixmap | None = company.get("logo")
            if logo is not None and not logo.isNull():
                painter.drawPixmap(logo_rect.toRect(), logo)
            else:
                # Text placeholder: first 2 characters on light gray background
                painter.setBrush(QBrush(QColor(220, 220, 220)))
                painter.setPen(QPen(QColor(120, 120, 120), 0.5))
                painter.drawRoundedRect(logo_rect, 2.0, 2.0)

                name = company.get("name", "??")
                placeholder_text = name[:2]
                placeholder_font = QFont("Segoe UI", 7)
                painter.setFont(placeholder_font)
                painter.setPen(QPen(QColor(60, 60, 60)))
                painter.drawText(
                    logo_rect,
                    Qt.AlignmentFlag.AlignCenter,
                    placeholder_text,
                )
        painter.restore()

    def _paint_cluster_lines(self, painter: QPainter) -> None:
        """Paint DNA cluster names after the standard text lines.

        Renders cluster names in alphabetical order, each in its assigned
        color (or default label color when None). Shows a maximum of 5
        cluster entries; if more exist, appends a "+N more" overflow
        indicator (Req 7.1, 7.2, 7.3, 7.4, 7.5, 7.6).

        Does nothing when the clusters config toggle is disabled or when
        the person belongs to no clusters.

        Args:
            painter: The QPainter to draw with.
        """
        if not self._config.clusters:
            return

        clusters: list[dict] | None = self._display_data.get("clusters")
        if not clusters:
            return

        # Sort alphabetically by name
        sorted_clusters = sorted(clusters, key=lambda c: c.get("name", ""))

        # Determine visible entries and overflow
        total = len(sorted_clusters)
        visible = sorted_clusters[:_MAX_CLUSTERS]
        overflow_count = total - _MAX_CLUSTERS if total > _MAX_CLUSTERS else 0

        # Compute y start position: after standard lines
        # Standard lines are stored in self._lines (before cluster placeholders were added)
        # Cluster placeholder lines start at index self._cluster_line_start
        y_start = _PADDING + self._cluster_line_start * _LINE_HEIGHT + _LINE_HEIGHT * 0.8

        photo_offset = self._get_photo_text_offset()
        font = QFont("Segoe UI", 9)
        painter.setFont(font)

        y = y_start
        text_x = _PADDING + photo_offset
        available_width = _BOX_WIDTH - text_x - _PADDING
        fm = QFontMetrics(font)

        for cluster in visible:
            color_str: str | None = cluster.get("color")
            if color_str:
                text_color = QColor(color_str)
                if not text_color.isValid():
                    text_color = _LABEL_COLOR
            else:
                text_color = _LABEL_COLOR

            painter.setPen(QPen(text_color))
            name = cluster.get("name", "")
            elided = fm.elidedText(
                name,
                Qt.TextElideMode.ElideRight,
                int(available_width),
            )
            painter.drawText(
                QRectF(text_x, y - _LINE_HEIGHT * 0.8, available_width, _LINE_HEIGHT),
                Qt.AlignmentFlag.AlignLeft,
                elided,
            )
            y += _LINE_HEIGHT

        # Overflow indicator
        if overflow_count > 0:
            painter.setPen(QPen(_LABEL_COLOR))
            overflow_text = f"+{overflow_count} more"
            painter.drawText(
                QRectF(text_x, y - _LINE_HEIGHT * 0.8, available_width, _LINE_HEIGHT),
                Qt.AlignmentFlag.AlignLeft,
                overflow_text,
            )

        # Restore text color
        painter.setPen(QPen(_TEXT_COLOR))

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle mouse press for selection.

        Args:
            event: The mouse press event.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            # Selection is managed by the scene/panel
            pass
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle double-click for editing.

        Args:
            event: The mouse double-click event.
        """
        if event.button() == Qt.MouseButton.LeftButton:
            # Edit signal is emitted via the scene/panel
            pass
        super().mouseDoubleClickEvent(event)

    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        """Show names tooltip when hovering over the multiple-names indicator.

        Args:
            event: The hover move event.
        """
        if self._display_data.get("has_multiple_names"):
            marker_rect = QRectF(
                _PADDING / 2, _PADDING,
                _MULTIPLE_NAMES_ICON_SIZE, _LINE_HEIGHT,
            )
            if marker_rect.contains(event.pos()):
                tooltip = self._display_data.get("names_tooltip", "")
                if tooltip:
                    screen_pos = event.screenPos()
                    QToolTip.showText(screen_pos, tooltip)
                    return
        QToolTip.hideText()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        """Hide tooltip when leaving the item.

        Args:
            event: The hover leave event.
        """
        QToolTip.hideText()
        super().hoverLeaveEvent(event)

    def _build_lines(self) -> None:
        """Build the list of display lines from config and data.

        Only includes fields that are both enabled in config and
        have non-None/non-empty data (Req 20.4).
        Also builds a parallel list of event type strings for icon
        rendering (None for lines without an event icon).

        Date and place are combined on the same line when both are
        available (e.g. "f. 1953-03-29, Stockholm").
        """
        self._lines = []
        self._line_event_types = []

        # Mapping from field names to event type strings for icon lookup
        _FIELD_EVENT_TYPE_MAP: dict[str, str] = {
            "birth_date": "birth",
            "death_date": "death",
            "marriage_date": "marriage",
        }

        # Date fields paired with their corresponding place fields
        _DATE_PLACE_PAIRS: dict[str, str] = {
            "birth_date": "birth_place",
            "death_date": "death_place",
            "marriage_date": "marriage_place",
        }

        # Fields that are handled as part of a date line (skip standalone)
        _PLACE_FIELDS = {"birth_place", "death_place", "marriage_place"}

        # Ordered fields and their display labels
        field_order: list[tuple[str, str]] = [
            ("name", ""),
            ("birth_date", "f. "),
            ("birth_place", "fp. "),
            ("death_date", "d. "),
            ("death_place", "dp. "),
            ("cause_of_death", "Dödsorsak: "),
            ("marriage_date", "g. "),
            ("marriage_place", "gp. "),
            ("occupation", "Yrke: "),
            ("dna_info", "DNA: "),
            ("notes", "Ant: "),
        ]

        for field_name, prefix in field_order:
            if not getattr(self._config, field_name, False):
                continue

            # Skip place fields — they're merged into the date line
            if field_name in _PLACE_FIELDS:
                continue

            value = self._display_data.get(field_name)
            if not value:
                continue

            if field_name == "name":
                self._lines.append(value)
                self._line_event_types.append(None)
            else:
                # Truncate cause_of_death if it exceeds max length (Req 6.4)
                if field_name == "cause_of_death" and len(value) > _CAUSE_OF_DEATH_MAX_LEN:
                    value = value[:_CAUSE_OF_DEATH_MAX_LEN] + "\u2026"

                # Append place to the date line if both are enabled and available
                line_text = f"{prefix}{value}"
                place_field = _DATE_PLACE_PAIRS.get(field_name)
                if place_field and getattr(self._config, place_field, False):
                    place_value = self._display_data.get(place_field)
                    if place_value:
                        line_text += f", {place_value}"

                self._lines.append(line_text)
                self._line_event_types.append(
                    _FIELD_EVENT_TYPE_MAP.get(field_name)
                )

        # If place is enabled but date is not, show place on its own line
        for place_field, place_prefix in [("birth_place", "fp. "), ("death_place", "dp. "), ("marriage_place", "gp. ")]:
            if not getattr(self._config, place_field, False):
                continue
            # Find the corresponding date field
            date_field = place_field.replace("_place", "_date")
            # Only show standalone if date is NOT enabled (otherwise it was merged)
            if getattr(self._config, date_field, False):
                continue
            place_value = self._display_data.get(place_field)
            if place_value:
                self._lines.append(f"{place_prefix}{place_value}")
                self._line_event_types.append(None)

        # Ensure at least one line (fallback)
        if not self._lines:
            self._lines.append("(okänd)")
            self._line_event_types.append(None)

        # Track where cluster lines start for painting (Req 7.1–7.6)
        self._cluster_line_start = len(self._lines)

        if self._config.clusters:
            clusters: list[dict] | None = self._display_data.get("clusters")
            if clusters:
                sorted_clusters = sorted(clusters, key=lambda c: c.get("name", ""))
                total = len(sorted_clusters)
                visible_count = min(total, _MAX_CLUSTERS)
                # Add placeholder lines so box height accounts for cluster entries
                for i in range(visible_count):
                    self._lines.append("")  # placeholder, painted by _paint_cluster_lines
                    self._line_event_types.append(None)
                # Add overflow indicator line if needed
                if total > _MAX_CLUSTERS:
                    self._lines.append("")  # placeholder for "+N more"
                    self._line_event_types.append(None)
