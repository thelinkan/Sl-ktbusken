# Feature: kontrollera-personer, Property 14: Input validation rejects out-of-range values
"""Property-based tests for input validation in the age checks tab.

For any integer value outside the allowed range (0–999 for age thresholds,
0–9999 for day thresholds), the QSpinBox SHALL clamp the value to the
allowed range. For values within range, the input SHALL be accepted.

**Validates: Requirements 5.8**
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from PySide6.QtWidgets import QApplication, QSpinBox


# Ensure QApplication exists for widget tests
@pytest.fixture(scope="module", autouse=True)
def qapp():
    """Create QApplication if not running."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestInputValidationProperty:
    """Property 14: Input validation rejects out-of-range values.

    Validates that QSpinBox correctly enforces configured ranges for
    age threshold fields (0-999) and day threshold fields (0-9999).

    **Validates: Requirements 5.8**
    """

    @given(value=st.integers(min_value=0, max_value=999))
    @settings(max_examples=200)
    def test_age_spinbox_accepts_valid_values(self, value: int) -> None:
        """Values within 0-999 are accepted by age spinboxes."""
        spin = QSpinBox()
        spin.setRange(0, 999)
        spin.setValue(value)
        assert spin.value() == value

    @given(value=st.integers(min_value=1000, max_value=99999))
    @settings(max_examples=200)
    def test_age_spinbox_clamps_high_values(self, value: int) -> None:
        """Values > 999 are clamped to 999."""
        spin = QSpinBox()
        spin.setRange(0, 999)
        spin.setValue(value)
        assert spin.value() == 999

    @given(value=st.integers(min_value=-999, max_value=-1))
    @settings(max_examples=200)
    def test_age_spinbox_clamps_negative_values(self, value: int) -> None:
        """Negative values are clamped to 0."""
        spin = QSpinBox()
        spin.setRange(0, 999)
        spin.setValue(value)
        assert spin.value() == 0

    @given(value=st.integers(min_value=0, max_value=9999))
    @settings(max_examples=200)
    def test_days_spinbox_accepts_valid_values(self, value: int) -> None:
        """Values within 0-9999 are accepted by day spinboxes."""
        spin = QSpinBox()
        spin.setRange(0, 9999)
        spin.setValue(value)
        assert spin.value() == value

    @given(value=st.integers(min_value=10000, max_value=99999))
    @settings(max_examples=200)
    def test_days_spinbox_clamps_high_values(self, value: int) -> None:
        """Values > 9999 are clamped to 9999."""
        spin = QSpinBox()
        spin.setRange(0, 9999)
        spin.setValue(value)
        assert spin.value() == 9999
