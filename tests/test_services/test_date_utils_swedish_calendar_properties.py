"""Property-based tests for Swedish calendar validation.

Feature: kontrollera-personer, Property 12: Swedish calendar validation

Validates: Requirements 9.5
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.services.checks.date_utils import ParsedDate, is_valid_swedish_calendar


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Days in the non-existent range during the Swedish calendar transition
non_existent_day_st = st.integers(min_value=18, max_value=28)

# Julian years (before 1753, reasonable range for genealogy)
julian_year_st = st.integers(min_value=1000, max_value=1752)

# Gregorian years (after 1753)
gregorian_year_st = st.integers(min_value=1754, max_value=2100)

# Month strategy
month_st = st.integers(min_value=1, max_value=12)

# Day strategy (1-31, will be validated by the function)
day_st = st.integers(min_value=1, max_value=31)


# ---------------------------------------------------------------------------
# Property 12: Swedish calendar validation
# ---------------------------------------------------------------------------


class TestSwedishCalendarValidationProperty:
    """Feature: kontrollera-personer, Property 12: Swedish calendar validation

    For any date, if it falls in the non-existent range 1753-02-18 to 1753-02-28,
    or is an invalid day-of-month for the applicable calendar system (Julian for
    dates <= 1753-02-17, Gregorian for dates >= 1753-03-01), and the Swedish
    calendar check is enabled, a finding SHALL be produced. For valid dates
    according to the Swedish calendar, no finding SHALL be produced by this check.

    **Validates: Requirements 9.5**
    """

    @given(day=non_existent_day_st)
    @settings(max_examples=200)
    def test_non_existent_dates_always_invalid(self, day: int) -> None:
        """Dates 1753-02-18 through 1753-02-28 are ALWAYS invalid.

        These dates do not exist in the Swedish calendar due to the transition
        from Julian to Gregorian calendar.
        """
        d = ParsedDate(year=1753, month=2, day=day)
        assert is_valid_swedish_calendar(d) is False

    @given(year=julian_year_st)
    @settings(max_examples=200)
    def test_julian_leap_year_feb_29_valid(self, year: int) -> None:
        """Julian leap year rules apply for dates <= 1753-02-17.

        A year divisible by 4 is a Julian leap year, so Feb 29 is valid.
        """
        # Only test years that are Julian leap years (divisible by 4)
        year = year - (year % 4)  # Round down to nearest multiple of 4
        if year < 1000:
            year = 1000  # Keep in valid range
        d = ParsedDate(year=year, month=2, day=29)
        assert is_valid_swedish_calendar(d) is True

    @given(year=julian_year_st)
    @settings(max_examples=200)
    def test_julian_non_leap_year_feb_29_invalid(self, year: int) -> None:
        """Julian non-leap years: Feb 29 is invalid.

        In Julian calendar, a year NOT divisible by 4 is NOT a leap year.
        """
        # Ensure year is NOT divisible by 4
        if year % 4 == 0:
            year += 1
        if year > 1752:
            year = 1751  # Keep in Julian range
        d = ParsedDate(year=year, month=2, day=29)
        assert is_valid_swedish_calendar(d) is False

    @given(year=gregorian_year_st)
    @settings(max_examples=200)
    def test_gregorian_leap_year_feb_29_valid(self, year: int) -> None:
        """Gregorian leap year rules apply for dates >= 1753-03-01.

        Divisible by 4 but not 100 (except 400) is a leap year.
        """
        # Generate a Gregorian leap year: div by 4, not by 100, except by 400
        # Use multiples of 400 and multiples of 4 that aren't multiples of 100
        if year % 400 == 0:
            pass  # Already a leap year
        elif year % 100 == 0:
            # Not a leap year, adjust to nearest multiple of 4 that isn't mult of 100
            year += 4 - (year % 4) if year % 4 != 0 else 4
            if year % 100 == 0:
                year += 4
        elif year % 4 != 0:
            year = year - (year % 4) + 4
            if year % 100 == 0:
                year += 4

        # Verify we have a Gregorian leap year
        is_leap = (year % 400 == 0) or (year % 4 == 0 and year % 100 != 0)
        if not is_leap:
            return  # Skip if we couldn't generate a valid leap year

        d = ParsedDate(year=year, month=2, day=29)
        assert is_valid_swedish_calendar(d) is True

    @given(year=gregorian_year_st)
    @settings(max_examples=200)
    def test_gregorian_non_leap_year_feb_29_invalid(self, year: int) -> None:
        """Gregorian non-leap years: Feb 29 is invalid.

        Divisible by 100 but not 400 is NOT a leap year (e.g. 1900, 2100).
        Also, years not divisible by 4 are NOT leap years.
        """
        # Generate a non-leap year in Gregorian calendar
        if year % 4 != 0:
            pass  # Already non-leap
        elif year % 100 == 0 and year % 400 != 0:
            pass  # Century year but not 400-multiple, non-leap
        else:
            # It's a leap year, make it non-leap
            year += 1
            if year % 4 == 0:
                year += 1

        # Verify it's NOT a Gregorian leap year
        is_leap = (year % 400 == 0) or (year % 4 == 0 and year % 100 != 0)
        if is_leap:
            return  # Skip if we couldn't generate a valid non-leap year

        d = ParsedDate(year=year, month=2, day=29)
        assert is_valid_swedish_calendar(d) is False

    @given(
        year=st.integers(min_value=1000, max_value=2100),
        month=month_st,
        day=day_st,
    )
    @settings(max_examples=200)
    def test_day_exceeding_max_for_month_invalid(
        self, year: int, month: int, day: int
    ) -> None:
        """Dates with day > max days in that month (for applicable calendar) are invalid.

        For each calendar system, a day exceeding the month's maximum is invalid.
        """
        # Determine which calendar applies
        if year < 1753 or (year == 1753 and month < 2) or (year == 1753 and month == 2 and day <= 17):
            # Julian
            is_leap = year % 4 == 0
        elif year == 1753 and month == 2 and day >= 18:
            # Non-existent dates, tested separately
            return
        else:
            # Gregorian
            is_leap = (year % 400 == 0) or (year % 4 == 0 and year % 100 != 0)

        days_in_month = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        max_day = days_in_month[month]
        if month == 2 and is_leap:
            max_day = 29

        d = ParsedDate(year=year, month=month, day=day)
        result = is_valid_swedish_calendar(d)

        if day > max_day:
            assert result is False, (
                f"Day {day} exceeds max {max_day} for {year}-{month:02d}, "
                f"expected invalid but got valid"
            )

    @given(
        year=st.integers(min_value=1000, max_value=2100),
        month=month_st,
    )
    @settings(max_examples=200)
    def test_date_without_day_always_valid(self, year: int, month: int) -> None:
        """Dates without day component (day=None) are always valid if month is 1-12."""
        d = ParsedDate(year=year, month=month, day=None)
        assert is_valid_swedish_calendar(d) is True

    @given(year=st.integers(min_value=1000, max_value=2100))
    @settings(max_examples=200)
    def test_date_without_month_always_valid(self, year: int) -> None:
        """Dates without month component (month=None) are always valid."""
        d = ParsedDate(year=year, month=None, day=None)
        assert is_valid_swedish_calendar(d) is True

    @given(
        year=st.one_of(
            # Years divisible by 100 but not 400 (non-leap in Gregorian)
            st.sampled_from([1800, 1900, 2100]),
            # Years not divisible by 4
            st.integers(min_value=1754, max_value=2100).filter(
                lambda y: y % 4 != 0
            ),
        )
    )
    @settings(max_examples=200)
    def test_feb_29_non_leap_year_gregorian_invalid(self, year: int) -> None:
        """Feb 29 in a Gregorian non-leap year is invalid.

        Non-leap in Gregorian: divisible by 100 but not 400, or not divisible by 4.
        """
        d = ParsedDate(year=year, month=2, day=29)
        assert is_valid_swedish_calendar(d) is False
