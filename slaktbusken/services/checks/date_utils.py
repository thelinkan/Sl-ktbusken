"""Date parsing, comparison, and calendar validation utilities.

Provides ParsedDate for representing dates with precision, and functions for
parsing DateValue objects, computing ages and intervals, comparing dates at
common precision, and validating against the Swedish calendar transition of 1753.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from slaktbusken.model.event import DateValue


# Days per month for non-leap years
_DAYS_IN_MONTH = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# Date parsing pattern: YYYY, YYYY-MM, or YYYY-MM-DD
_DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")


@dataclass
class ParsedDate:
    """A parsed date with precision information."""

    year: int
    month: int | None = None  # 1-12
    day: int | None = None  # 1-31
    precision: str = "exact"  # "exact", "about", "before", "after"


def parse_date_value(dv: DateValue) -> ParsedDate | None:
    """Parse a DateValue into a ParsedDate, or None if unparseable.

    Handles formats: "YYYY", "YYYY-MM", "YYYY-MM-DD".
    """
    if not dv or not dv.value:
        return None

    m = _DATE_RE.match(dv.value.strip())
    if not m:
        return None

    year = int(m.group(1))
    month: int | None = int(m.group(2)) if m.group(2) else None
    day: int | None = int(m.group(3)) if m.group(3) else None

    # Basic validation of month and day ranges
    if month is not None and (month < 1 or month > 12):
        return None
    if day is not None and (day < 1 or day > 31):
        return None

    return ParsedDate(
        year=year,
        month=month,
        day=day,
        precision=dv.precision,
    )


def age_in_years(birth: ParsedDate, event: ParsedDate) -> int | None:
    """Compute age in whole years between birth and event.

    Returns None if precision is insufficient (both need at least year+month,
    or if only year is available, uses year difference minus 1 as minimum).
    For a reliable calculation, both dates need at least month precision.
    If only year precision is available, returns the year difference assuming
    the birthday has not yet occurred (conservative estimate).
    """
    if birth is None or event is None:
        return None

    # Both must have at least year
    if birth.month is not None and event.month is not None:
        # Full month (and possibly day) precision
        age = event.year - birth.year
        # Check if birthday has occurred this year
        if event.month < birth.month:
            age -= 1
        elif event.month == birth.month:
            birth_day = birth.day if birth.day is not None else 1
            event_day = event.day if event.day is not None else 1
            if event_day < birth_day:
                age -= 1
        return age

    # Only year precision available — return difference
    # This is an approximation; could be off by 1
    return event.year - birth.year


def days_between(d1: ParsedDate, d2: ParsedDate) -> int | None:
    """Compute the number of days between two dates.

    Returns None if either date lacks a day component.
    Returns a positive value if d2 is after d1, negative if before.
    """
    if d1 is None or d2 is None:
        return None
    if d1.day is None or d2.day is None:
        return None
    if d1.month is None or d2.month is None:
        return None

    jdn1 = _to_julian_day_number(d1.year, d1.month, d1.day)
    jdn2 = _to_julian_day_number(d2.year, d2.month, d2.day)
    return jdn2 - jdn1


def compare_dates(d1: ParsedDate, d2: ParsedDate) -> int | None:
    """Compare two dates at their common precision level.

    Returns:
        < 0 if d1 is before d2
        0 if equal at common precision
        > 0 if d1 is after d2
        None if precision doesn't allow comparison

    Comparison is performed at the most specific common precision:
    - If both have day: compare full dates
    - If both have month (but one or both lack day): compare year+month
    - If both have only year: compare years
    """
    if d1 is None or d2 is None:
        return None

    # Compare years first
    if d1.year != d2.year:
        return d1.year - d2.year

    # Both have month?
    if d1.month is not None and d2.month is not None:
        if d1.month != d2.month:
            return d1.month - d2.month

        # Both have day?
        if d1.day is not None and d2.day is not None:
            return d1.day - d2.day

        # Same year and month, but one or both lack day — equal at this precision
        return 0

    # One or both lack month — equal at year precision
    return 0


def is_valid_swedish_calendar(d: ParsedDate) -> bool:
    """Validate a date against the Swedish calendar.

    Sweden transitioned from Julian to Gregorian in 1753:
    - Julian calendar applies up to and including 1753-02-17
    - Gregorian calendar applies from 1753-03-01 onwards
    - Dates 1753-02-18 through 1753-02-28 do NOT exist

    Leap year rules:
    - Julian: divisible by 4
    - Gregorian: divisible by 4, not by 100, except by 400
    """
    if d is None:
        return False

    # If no month or day, we can only validate at year level — always valid
    if d.month is None:
        return True

    # Validate month range
    if d.month < 1 or d.month > 12:
        return False

    # If no day specified, month-level is valid as long as month is in range
    if d.day is None:
        return True

    # Check the non-existent dates during Swedish calendar transition
    if d.year == 1753 and d.month == 2 and d.day >= 18:
        return False

    # Determine which calendar system applies
    is_julian = _is_julian_date(d.year, d.month, d.day)

    # Get max days for the month
    if is_julian:
        leap = _is_julian_leap_year(d.year)
    else:
        leap = _is_gregorian_leap_year(d.year)

    max_day = _DAYS_IN_MONTH[d.month]
    if d.month == 2 and leap:
        max_day = 29

    return 1 <= d.day <= max_day


# --- Private helpers ---


def _is_julian_date(year: int, month: int, day: int) -> bool:
    """Determine if a date falls under the Julian calendar in Sweden."""
    if year < 1753:
        return True
    if year > 1753:
        return False
    # year == 1753
    if month < 2:
        return True
    if month == 2 and day <= 17:
        return True
    return False


def _is_julian_leap_year(year: int) -> bool:
    """Julian leap year: divisible by 4."""
    return year % 4 == 0


def _is_gregorian_leap_year(year: int) -> bool:
    """Gregorian leap year: divisible by 4, not by 100, except by 400."""
    if year % 400 == 0:
        return True
    if year % 100 == 0:
        return False
    return year % 4 == 0


def _to_julian_day_number(year: int, month: int, day: int) -> int:
    """Convert a date to Julian Day Number for day arithmetic.

    Uses a standard algorithm that works for both Julian and Gregorian dates.
    We use Gregorian here since we're computing intervals and the difference
    is consistent regardless of calendar system used.
    """
    # Algorithm from Meeus, Astronomical Algorithms
    if month <= 2:
        year -= 1
        month += 12

    a = year // 100
    b = 2 - a + a // 4  # Gregorian correction

    return (
        int(365.25 * (year + 4716))
        + int(30.6001 * (month + 1))
        + day
        + b
        - 1524
    )
