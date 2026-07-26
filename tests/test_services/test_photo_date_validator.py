"""Unit tests for PhotoDateValidator service."""

from __future__ import annotations

import pytest

from slaktbusken.services.photo_date_validator import PhotoDate, PhotoDateValidator


class TestPhotoDateValidation:
    """Tests for PhotoDateValidator.validate()."""

    def test_all_none_is_valid(self) -> None:
        """All fields None means no date - valid."""
        errors = PhotoDateValidator.validate(None, None, None)
        assert errors == []

    def test_year_only_valid(self) -> None:
        """Year-only is valid."""
        errors = PhotoDateValidator.validate(1920, None, None)
        assert errors == []

    def test_year_and_month_valid(self) -> None:
        """Year + month is valid."""
        errors = PhotoDateValidator.validate(2000, 6, None)
        assert errors == []

    def test_full_date_valid(self) -> None:
        """Full date (year + month + day) is valid."""
        errors = PhotoDateValidator.validate(2023, 3, 15)
        assert errors == []

    def test_month_without_year_invalid(self) -> None:
        """Month without year is invalid."""
        errors = PhotoDateValidator.validate(None, 6, None)
        assert errors == ["År krävs om månad anges."]

    def test_day_without_month_and_year_invalid(self) -> None:
        """Day without month and year is invalid."""
        errors = PhotoDateValidator.validate(None, None, 15)
        assert errors == ["År och månad krävs om dag anges."]

    def test_day_without_month_invalid(self) -> None:
        """Day with year but without month is invalid."""
        errors = PhotoDateValidator.validate(2023, None, 15)
        assert errors == ["År och månad krävs om dag anges."]

    def test_invalid_day_for_month(self) -> None:
        """Feb 30 is invalid."""
        errors = PhotoDateValidator.validate(2023, 2, 30)
        assert errors == ["Ogiltigt datum."]

    def test_feb_29_leap_year_valid(self) -> None:
        """Feb 29 on a leap year is valid."""
        errors = PhotoDateValidator.validate(2024, 2, 29)
        assert errors == []

    def test_feb_29_non_leap_year_invalid(self) -> None:
        """Feb 29 on a non-leap year is invalid."""
        errors = PhotoDateValidator.validate(2023, 2, 29)
        assert errors == ["Ogiltigt datum."]

    def test_year_zero_invalid(self) -> None:
        """Year 0 is out of range."""
        errors = PhotoDateValidator.validate(0, None, None)
        assert errors == ["År måste vara mellan 1 och 9999."]

    def test_year_negative_invalid(self) -> None:
        """Negative year is out of range."""
        errors = PhotoDateValidator.validate(-1, None, None)
        assert errors == ["År måste vara mellan 1 och 9999."]

    def test_year_10000_invalid(self) -> None:
        """Year 10000 is out of range."""
        errors = PhotoDateValidator.validate(10000, None, None)
        assert errors == ["År måste vara mellan 1 och 9999."]

    def test_month_zero_invalid(self) -> None:
        """Month 0 is invalid."""
        errors = PhotoDateValidator.validate(2023, 0, None)
        assert errors == ["Månad måste vara mellan 1 och 12."]

    def test_month_13_invalid(self) -> None:
        """Month 13 is invalid."""
        errors = PhotoDateValidator.validate(2023, 13, None)
        assert errors == ["Månad måste vara mellan 1 och 12."]

    def test_day_zero_invalid(self) -> None:
        """Day 0 is invalid."""
        errors = PhotoDateValidator.validate(2023, 1, 0)
        assert errors == ["Ogiltigt datum."]

    def test_day_32_invalid(self) -> None:
        """Day 32 in January is invalid."""
        errors = PhotoDateValidator.validate(2023, 1, 32)
        assert errors == ["Ogiltigt datum."]

    def test_year_boundary_min(self) -> None:
        """Year 1 is valid."""
        errors = PhotoDateValidator.validate(1, None, None)
        assert errors == []

    def test_year_boundary_max(self) -> None:
        """Year 9999 is valid."""
        errors = PhotoDateValidator.validate(9999, None, None)
        assert errors == []


class TestPhotoDateStorageFormat:
    """Tests for to_storage_format and from_storage_format."""

    def test_all_none_to_storage(self) -> None:
        """All None produces None storage."""
        result = PhotoDateValidator.to_storage_format(None, None, None)
        assert result is None

    def test_year_only_to_storage(self) -> None:
        """Year-only produces dict with year key."""
        result = PhotoDateValidator.to_storage_format(1920, None, None)
        assert result == {"year": 1920}

    def test_year_month_to_storage(self) -> None:
        """Year+month produces dict with year and month keys."""
        result = PhotoDateValidator.to_storage_format(2000, 6, None)
        assert result == {"year": 2000, "month": 6}

    def test_full_date_to_storage(self) -> None:
        """Full date produces dict with all three keys."""
        result = PhotoDateValidator.to_storage_format(2023, 3, 15)
        assert result == {"year": 2023, "month": 3, "day": 15}

    def test_none_from_storage(self) -> None:
        """None input produces empty PhotoDate."""
        result = PhotoDateValidator.from_storage_format(None)
        assert result == PhotoDate()

    def test_year_only_from_storage(self) -> None:
        """Dict with year only produces PhotoDate with year."""
        result = PhotoDateValidator.from_storage_format({"year": 1920})
        assert result == PhotoDate(year=1920, month=None, day=None)

    def test_year_month_from_storage(self) -> None:
        """Dict with year and month produces PhotoDate with year+month."""
        result = PhotoDateValidator.from_storage_format({"year": 2000, "month": 6})
        assert result == PhotoDate(year=2000, month=6, day=None)

    def test_full_date_from_storage(self) -> None:
        """Dict with all three produces full PhotoDate."""
        result = PhotoDateValidator.from_storage_format(
            {"year": 2023, "month": 3, "day": 15}
        )
        assert result == PhotoDate(year=2023, month=3, day=15)

    def test_round_trip_none(self) -> None:
        """Round-trip: None -> storage -> PhotoDate."""
        stored = PhotoDateValidator.to_storage_format(None, None, None)
        restored = PhotoDateValidator.from_storage_format(stored)
        assert restored == PhotoDate()

    def test_round_trip_year_only(self) -> None:
        """Round-trip: year-only -> storage -> PhotoDate."""
        stored = PhotoDateValidator.to_storage_format(1850, None, None)
        restored = PhotoDateValidator.from_storage_format(stored)
        assert restored == PhotoDate(year=1850)

    def test_round_trip_year_month(self) -> None:
        """Round-trip: year+month -> storage -> PhotoDate."""
        stored = PhotoDateValidator.to_storage_format(1900, 12, None)
        restored = PhotoDateValidator.from_storage_format(stored)
        assert restored == PhotoDate(year=1900, month=12)

    def test_round_trip_full_date(self) -> None:
        """Round-trip: full date -> storage -> PhotoDate."""
        stored = PhotoDateValidator.to_storage_format(2024, 2, 29)
        restored = PhotoDateValidator.from_storage_format(stored)
        assert restored == PhotoDate(year=2024, month=2, day=29)
