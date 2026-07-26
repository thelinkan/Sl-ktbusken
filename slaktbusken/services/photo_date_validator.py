"""Service for validating photo dates with flexible precision.

PhotoDateValidator encapsulates pure validation logic for the flexible-precision
photo date fields used in photo metadata editing. It supports year-only,
year+month, and full date precision, as well as round-trip storage conversion.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass


@dataclass
class PhotoDate:
    """A date with flexible precision for photo metadata."""

    year: int | None = None
    month: int | None = None
    day: int | None = None


class PhotoDateValidator:
    """Validates photo dates with flexible precision rules."""

    @staticmethod
    def validate(year: int | None, month: int | None, day: int | None) -> list[str]:
        """Validate a photo date. Returns list of error messages (empty = valid).

        Rules:
        - All empty: valid (no date)
        - Year only: valid if year 1-9999
        - Year + month: valid if month 1-12
        - Year + month + day: valid if day valid for month/year
        - Month without year: invalid
        - Day without month or year: invalid
        """
        errors: list[str] = []

        # All None is valid (no date specified)
        if year is None and month is None and day is None:
            return errors

        # Month without year
        if month is not None and year is None:
            errors.append("År krävs om månad anges.")
            return errors

        # Day without month or year
        if day is not None and (month is None or year is None):
            errors.append("År och månad krävs om dag anges.")
            return errors

        # Year range validation
        if year is not None and (year < 1 or year > 9999):
            errors.append("År måste vara mellan 1 och 9999.")
            return errors

        # Month range validation
        if month is not None and (month < 1 or month > 12):
            errors.append("Månad måste vara mellan 1 och 12.")
            return errors

        # Day validation against month/year
        if day is not None and month is not None and year is not None:
            _, max_day = calendar.monthrange(year, month)
            if day < 1 or day > max_day:
                errors.append("Ogiltigt datum.")

        return errors

    @staticmethod
    def to_storage_format(
        year: int | None, month: int | None, day: int | None
    ) -> dict | None:
        """Convert to storage format. Returns None if no date, or dict with precision info."""
        if year is None and month is None and day is None:
            return None

        result: dict = {"year": year}

        if month is not None:
            result["month"] = month

        if day is not None:
            result["day"] = day

        return result

    @staticmethod
    def from_storage_format(stored: dict | None) -> PhotoDate:
        """Parse stored date back into PhotoDate."""
        if stored is None:
            return PhotoDate()

        return PhotoDate(
            year=stored.get("year"),
            month=stored.get("month"),
            day=stored.get("day"),
        )
