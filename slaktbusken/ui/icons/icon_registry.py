"""Centralized icon registry for event types and gender values."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtSvg import QSvgRenderer

logger = logging.getLogger(__name__)

_ICONS_DIR = Path(__file__).parent

_EVENTS_DIR = _ICONS_DIR / "events"
_GENDER_DIR = _ICONS_DIR / "gender"
_MISC_DIR = _ICONS_DIR / "misc"

# All recognized event types and their corresponding SVG filenames.
_EVENT_TYPE_MAP: dict[str, str] = {
    "birth": "birth.svg",
    "baptism": "baptism.svg",
    "death": "death.svg",
    "burial": "burial.svg",
    "cremation": "cremation.svg",
    "marriage": "marriage.svg",
    "divorce": "divorce.svg",
    "divorce_filed": "divorce_filed.svg",
    "engagement": "engagement.svg",
    "emigration": "emigration.svg",
    "immigration": "immigration.svg",
    "census": "census.svg",
    "confirmation": "confirmation.svg",
    "first_communion": "first_communion.svg",
    "adoption": "adoption.svg",
    "blessing": "blessing.svg",
    "graduation": "graduation.svg",
    "retirement": "retirement.svg",
    "will": "will.svg",
    "name_change": "name_change.svg",
    "gender_correction": "gender_correction.svg",
    "custom_individual_event": "custom_event.svg",
    "custom_family_event": "custom_event.svg",
}

_FALLBACK_EVENT_ICON = "generic_event.svg"

# Gender/sex value mapping.
_GENDER_MAP: dict[str, str] = {
    "M": "male.svg",
    "F": "female.svg",
    "X": "other.svg",
    "U": "unknown.svg",
}

_FALLBACK_GENDER_ICON = "unknown.svg"


class IconRegistry:
    """Singleton providing icon lookup for event types and sex values.

    Pixmaps are cached after first load to avoid repeated disk I/O
    and SVG rendering overhead.
    """

    _instance: IconRegistry | None = None

    def __new__(cls) -> IconRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._pixmap_cache = {}  # type: ignore[attr-defined]
        return cls._instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_event_icon(self, event_type: str) -> QPixmap:
        """Return a QPixmap for the given event type.

        Falls back to a generic icon for unrecognized types.
        """
        path = self.get_event_icon_path(event_type)
        return self._load_pixmap(path)

    def get_gender_icon(self, sex: str) -> QPixmap:
        """Return a QPixmap for sex value ('M', 'F', 'X', 'U').

        Falls back to the unknown icon for invalid values.
        """
        path = self.get_gender_icon_path(sex)
        return self._load_pixmap(path)

    def get_multiple_names_icon(self) -> QPixmap:
        """Return a 14×14 QPixmap for the multiple-names indicator icon."""
        path = _MISC_DIR / "multiple_names.svg"
        return self._load_pixmap_sized(path, 14)

    def get_dna_company_logo(self, media_id: str, media_loader) -> QPixmap | None:
        """Return a 16×16 QPixmap for a DNA company logo.

        Uses *media_loader* (a callable accepting a media_id and returning
        QPixmap | None) to fetch the logo image, then scales it to 16×16
        keeping aspect ratio with smooth transformation.

        Results are cached by media_id.  Returns None if the media cannot
        be loaded or the resulting pixmap is null.
        """
        cache_key = f"dna_logo:{media_id}"
        if cache_key in self._pixmap_cache:
            return self._pixmap_cache[cache_key]

        pixmap = media_loader(media_id)
        if pixmap is None or pixmap.isNull():
            return None

        scaled = pixmap.scaled(
            16,
            16,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._pixmap_cache[cache_key] = scaled
        return scaled

    def get_event_icon_path(self, event_type: str) -> Path:
        """Return the file path to the SVG icon for the given event type."""
        filename = _EVENT_TYPE_MAP.get(event_type)
        if filename is None:
            logger.warning(
                "Unrecognized event type '%s', using generic fallback icon.",
                event_type,
            )
            filename = _FALLBACK_EVENT_ICON
        return _EVENTS_DIR / filename

    def get_gender_icon_path(self, sex: str) -> Path:
        """Return the file path to the SVG icon for the given sex value."""
        filename = _GENDER_MAP.get(sex)
        if filename is None:
            logger.warning(
                "Invalid sex value '%s', using unknown fallback icon.",
                sex,
            )
            filename = _FALLBACK_GENDER_ICON
        return _GENDER_DIR / filename

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_pixmap(self, svg_path: Path) -> QPixmap:
        """Load an SVG file as a 16×16 QPixmap, caching the result."""
        return self._load_pixmap_sized(svg_path, 16)

    def _load_pixmap_sized(self, svg_path: Path, size: int) -> QPixmap:
        """Load an SVG file as a size×size QPixmap, caching the result."""
        cache_key = f"{svg_path}@{size}"
        if cache_key in self._pixmap_cache:
            return self._pixmap_cache[cache_key]

        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        renderer = QSvgRenderer(str(svg_path))
        if renderer.isValid():
            from PySide6.QtGui import QPainter

            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
        else:
            logger.error("Failed to render SVG icon: %s", svg_path)

        self._pixmap_cache[cache_key] = pixmap
        return pixmap


# Module-level singleton instance for convenient access.
icon_registry = IconRegistry()
