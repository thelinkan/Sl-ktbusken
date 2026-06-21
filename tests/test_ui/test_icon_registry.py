"""Unit tests for IconRegistry event type and gender icon lookup.

Verifies that:
- All 23 recognized event types return distinct non-null icons.
- All 4 gender values return distinct non-null icons.
- Invalid sex values fall back to the unknown icon.
- Pixmap caching returns the same object on repeated calls.

Covers Requirements 1.1, 1.5, 2.1.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.ui.icons.icon_registry import IconRegistry


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def registry() -> IconRegistry:
    """Return a fresh IconRegistry instance with cleared cache."""
    # Reset singleton so each test gets a clean cache
    IconRegistry._instance = None
    return IconRegistry()


ALL_EVENT_TYPES = [
    "birth",
    "baptism",
    "death",
    "burial",
    "cremation",
    "marriage",
    "divorce",
    "divorce_filed",
    "engagement",
    "emigration",
    "immigration",
    "census",
    "confirmation",
    "first_communion",
    "adoption",
    "blessing",
    "graduation",
    "retirement",
    "will",
    "name_change",
    "gender_correction",
    "custom_individual_event",
    "custom_family_event",
]

ALL_GENDER_VALUES = ["M", "F", "X", "U"]


class TestEventIcons:
    """Tests for event type icon lookup via IconRegistry."""

    def test_all_event_types_return_non_null_icons(self, registry: IconRegistry):
        """Every recognized event type produces a non-null QPixmap."""
        for event_type in ALL_EVENT_TYPES:
            pixmap = registry.get_event_icon(event_type)
            assert pixmap is not None, f"Icon for '{event_type}' was None"
            assert not pixmap.isNull(), f"Icon for '{event_type}' is a null pixmap"

    def test_event_icons_are_distinct(self, registry: IconRegistry):
        """Each event type maps to a visually distinct icon (unique cacheKey).

        Note: custom_individual_event and custom_family_event intentionally
        share the same icon file, so that pair is excluded from the
        uniqueness check.
        """
        cache_keys: dict[int, str] = {}
        for event_type in ALL_EVENT_TYPES:
            pixmap = registry.get_event_icon(event_type)
            key = pixmap.cacheKey()

            # Allow the known shared pair
            if key in cache_keys:
                existing = cache_keys[key]
                shared_pair = {"custom_individual_event", "custom_family_event"}
                assert {existing, event_type} == shared_pair, (
                    f"Icon collision: '{event_type}' has the same cacheKey as "
                    f"'{existing}', but they are not the allowed shared pair"
                )
            else:
                cache_keys[key] = event_type


class TestGenderIcons:
    """Tests for gender/sex icon lookup via IconRegistry."""

    def test_all_gender_values_return_non_null_icons(self, registry: IconRegistry):
        """Every recognized sex value produces a non-null QPixmap."""
        for sex in ALL_GENDER_VALUES:
            pixmap = registry.get_gender_icon(sex)
            assert pixmap is not None, f"Icon for sex='{sex}' was None"
            assert not pixmap.isNull(), f"Icon for sex='{sex}' is a null pixmap"

    def test_gender_icons_are_distinct(self, registry: IconRegistry):
        """Each sex value maps to a visually distinct icon (unique cacheKey)."""
        cache_keys: dict[int, str] = {}
        for sex in ALL_GENDER_VALUES:
            pixmap = registry.get_gender_icon(sex)
            key = pixmap.cacheKey()
            assert key not in cache_keys, (
                f"Icon collision: sex='{sex}' has the same cacheKey as "
                f"sex='{cache_keys.get(key)}'"
            )
            cache_keys[key] = sex


class TestFallbackBehavior:
    """Tests for invalid/unrecognized input fallback behavior."""

    def test_invalid_sex_returns_unknown_icon(self, registry: IconRegistry):
        """An invalid sex value ('Z') returns the same icon as 'U' (unknown)."""
        unknown_pixmap = registry.get_gender_icon("U")
        invalid_pixmap = registry.get_gender_icon("Z")
        assert invalid_pixmap.cacheKey() == unknown_pixmap.cacheKey()


class TestDnaCompanyLogo:
    """Tests for DNA company logo loading via IconRegistry."""

    def test_returns_scaled_pixmap_on_success(self, registry: IconRegistry):
        """A valid media_loader result is scaled to 16×16 (max dimension)."""
        from PySide6.QtGui import QPixmap

        source = QPixmap(64, 32)  # 2:1 aspect ratio
        source.fill()

        def loader(mid: str) -> QPixmap:
            return source

        result = registry.get_dna_company_logo("logo1", loader)
        assert result is not None
        assert not result.isNull()
        # KeepAspectRatio with 64×32 scaled to fit 16×16 → 16×8
        assert result.width() == 16
        assert result.height() == 8

    def test_returns_none_when_loader_returns_none(self, registry: IconRegistry):
        """Returns None when media_loader cannot load the media."""

        def loader(mid: str):
            return None

        result = registry.get_dna_company_logo("missing", loader)
        assert result is None

    def test_returns_none_when_loader_returns_null_pixmap(self, registry: IconRegistry):
        """Returns None when media_loader returns a null QPixmap."""
        from PySide6.QtGui import QPixmap

        def loader(mid: str) -> QPixmap:
            return QPixmap()  # null pixmap

        result = registry.get_dna_company_logo("null_px", loader)
        assert result is None

    def test_caches_result_by_media_id(self, registry: IconRegistry):
        """Subsequent calls with the same media_id return cached pixmap."""
        from PySide6.QtGui import QPixmap

        source = QPixmap(16, 16)
        source.fill()
        call_count = 0

        def loader(mid: str) -> QPixmap:
            nonlocal call_count
            call_count += 1
            return source

        result1 = registry.get_dna_company_logo("cached", loader)
        result2 = registry.get_dna_company_logo("cached", loader)
        assert result1 is result2
        assert call_count == 1, "Loader should only be called once due to caching"

    def test_does_not_cache_failures(self, registry: IconRegistry):
        """Failed loads (None) are not cached — loader is called again."""
        from PySide6.QtGui import QPixmap

        call_count = 0

        def loader(mid: str):
            nonlocal call_count
            call_count += 1
            return None

        registry.get_dna_company_logo("fail_id", loader)
        registry.get_dna_company_logo("fail_id", loader)
        assert call_count == 2, "Loader should be called each time since failures aren't cached"


class TestCaching:
    """Tests for pixmap caching behavior."""

    def test_same_pixmap_returned_on_repeated_calls(self, registry: IconRegistry):
        """Calling get_event_icon with the same type returns the same object."""
        pixmap1 = registry.get_event_icon("birth")
        pixmap2 = registry.get_event_icon("birth")
        assert pixmap1 is pixmap2, (
            "Expected the same pixmap object (identity), got different objects"
        )
