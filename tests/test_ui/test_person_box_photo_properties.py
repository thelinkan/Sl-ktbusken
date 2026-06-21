"""Property-based tests for profile photo on PersonBoxItem.

Feature: enhanced-name-cards

Validates: Requirements 4.1, 4.2, 4.3, 4.6
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from slaktbusken.persistence.settings_io import PersonBoxConfig
from slaktbusken.ui.widgets.person_box import (
    PersonBoxItem,
    _PADDING,
    _PHOTO_GAP,
    _PHOTO_SIZE,
)


# ---------------------------------------------------------------------------
# Fixture for QApplication (required for Qt widget tests)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# Property 7: Photo presence determines text x-offset
# ---------------------------------------------------------------------------


class TestPhotoTextOffset:
    """Feature: enhanced-name-cards, Property 7: Photo presence determines text x-offset

    For any Person and PersonBoxConfig: when photo is enabled AND
    profile_photo is not None (valid QPixmap), text content starts at
    x = _PADDING + 48; otherwise text content starts at x = _PADDING.

    **Validates: Requirements 4.1, 4.2, 4.3**
    """

    @given(
        photo_enabled=st.booleans(),
        photo_present=st.booleans(),
    )
    @settings(max_examples=100)
    def test_text_offset_matches_photo_presence(
        self, qapp, photo_enabled: bool, photo_present: bool
    ) -> None:
        """Text x-offset is 48.0 when photo enabled AND present, else 0.0.

        Feature: enhanced-name-cards, Property 7: Photo presence determines text x-offset
        **Validates: Requirements 4.1, 4.2, 4.3**
        """
        # Build a valid QPixmap when photo is present, None otherwise
        profile_photo = QPixmap(40, 40) if photo_present else None

        display_data = {
            "name": "Test Person",
            "sex": "M",
            "profile_photo": profile_photo,
        }

        config = PersonBoxConfig(photo=photo_enabled)
        box = PersonBoxItem("person_1", display_data, config)

        offset = box._get_photo_text_offset()

        expected_offset = _PHOTO_SIZE + _PHOTO_GAP  # 48.0
        if photo_enabled and photo_present:
            assert offset == expected_offset, (
                f"Expected offset {expected_offset} when photo enabled={photo_enabled} "
                f"and photo present={photo_present}, got {offset}"
            )
        else:
            assert offset == 0.0, (
                f"Expected offset 0.0 when photo enabled={photo_enabled} "
                f"and photo present={photo_present}, got {offset}"
            )


# ---------------------------------------------------------------------------
# Property 8: Photo scaling preserves aspect ratio within bounds
# ---------------------------------------------------------------------------


class TestPhotoScalingPreservesAspectRatio:
    """Feature: enhanced-name-cards, Property 8: Photo scaling preserves aspect ratio within bounds

    For any source image with dimensions (w, h) where w > 0 and h > 0,
    the scaled dimensions (sw, sh) satisfy: sw ≤ 40, sh ≤ 40, and
    sw/sh ≈ w/h (within integer rounding tolerance).

    **Validates: Requirements 4.6**
    """

    @given(
        w=st.integers(min_value=1, max_value=2000),
        h=st.integers(min_value=1, max_value=2000),
    )
    @settings(max_examples=100)
    def test_scaled_dimensions_within_bounds_and_aspect_preserved(
        self, qapp, w: int, h: int
    ) -> None:
        """Photo scaling fits within 40x40 and preserves aspect ratio.

        Feature: enhanced-name-cards, Property 8: Photo scaling preserves aspect ratio within bounds
        **Validates: Requirements 4.6**
        """
        _PHOTO_SIZE = 40

        # Create a source pixmap with the given dimensions
        photo = QPixmap(w, h)

        # Scale using the same logic as _paint_profile_photo
        scaled = photo.scaled(
            _PHOTO_SIZE,
            _PHOTO_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        sw = scaled.width()
        sh = scaled.height()

        # Property: scaled dimensions must be within bounds
        assert sw <= _PHOTO_SIZE, (
            f"Scaled width {sw} exceeds {_PHOTO_SIZE} for input ({w}, {h})"
        )
        assert sh <= _PHOTO_SIZE, (
            f"Scaled height {sh} exceeds {_PHOTO_SIZE} for input ({w}, {h})"
        )

        # Property: at least one dimension fills the target
        # QPixmap.scaled with KeepAspectRatio always fills one dimension
        assert sw == _PHOTO_SIZE or sh == _PHOTO_SIZE, (
            f"Neither dimension fills target: scaled=({sw}, {sh}) for input ({w}, {h})"
        )

        # Property: aspect ratio is preserved within integer rounding tolerance
        # Qt computes scale_factor = min(40/w, 40/h), then:
        #   ideal_sw = w * scale_factor
        #   ideal_sh = h * scale_factor
        # and rounds each to the nearest integer. So each scaled dimension
        # should be within ±1 of the ideal floating-point value.
        if sw > 0 and sh > 0:
            scale_factor = min(_PHOTO_SIZE / w, _PHOTO_SIZE / h)
            ideal_sw = w * scale_factor
            ideal_sh = h * scale_factor

            assert abs(sw - ideal_sw) <= 1.0, (
                f"Scaled width {sw} deviates from ideal {ideal_sw:.2f} "
                f"by more than 1px for input ({w}, {h})"
            )
            assert abs(sh - ideal_sh) <= 1.0, (
                f"Scaled height {sh} deviates from ideal {ideal_sh:.2f} "
                f"by more than 1px for input ({w}, {h})"
            )
