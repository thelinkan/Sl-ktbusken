"""Property-based tests for date precision comparison.

Feature: kontrollera-personer, Property 8: Date precision comparison

Validates: Requirements 8.8
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.services.checks.date_utils import ParsedDate, compare_dates


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid years for genealogical data
year_st = st.integers(min_value=1000, max_value=2100)

# Valid months (1-12)
month_st = st.integers(min_value=1, max_value=12)

# Valid days (1-28 to avoid month-dependent edge cases)
day_st = st.integers(min_value=1, max_value=28)

# Precision qualifiers
precision_st = st.sampled_from(["exact", "about", "before", "after"])


@st.composite
def year_only_date(draw: st.DrawFn) -> ParsedDate:
    """Generate a ParsedDate with only year precision (month=None, day=None)."""
    return ParsedDate(
        year=draw(year_st),
        month=None,
        day=None,
        precision=draw(precision_st),
    )


@st.composite
def year_month_date(draw: st.DrawFn) -> ParsedDate:
    """Generate a ParsedDate with year+month precision (day=None)."""
    return ParsedDate(
        year=draw(year_st),
        month=draw(month_st),
        day=None,
        precision=draw(precision_st),
    )


@st.composite
def full_date(draw: st.DrawFn) -> ParsedDate:
    """Generate a ParsedDate with full precision (year, month, day)."""
    return ParsedDate(
        year=draw(year_st),
        month=draw(month_st),
        day=draw(day_st),
        precision=draw(precision_st),
    )


# A date at any precision level
any_parsed_date = st.one_of(year_only_date(), year_month_date(), full_date())


# ---------------------------------------------------------------------------
# Property 8: Date precision comparison
# ---------------------------------------------------------------------------


class TestDatePrecisionComparisonProperty:
    """Feature: kontrollera-personer, Property 8: Date precision comparison

    For any two ParsedDate instances where one or both lack day or month
    components, date comparison SHALL be performed at the most specific
    common precision (year-only or year-month). A chronological violation
    SHALL only be flagged if it is unambiguously impossible at the available
    precision level.

    **Validates: Requirements 8.8**
    """

    @given(d1=year_only_date(), d2=year_only_date())
    @settings(max_examples=200)
    def test_year_only_same_year_returns_zero(
        self, d1: ParsedDate, d2: ParsedDate
    ) -> None:
        """When both dates have only year precision and same year, compare_dates returns 0."""
        # Force same year
        d2_same = ParsedDate(
            year=d1.year, month=None, day=None, precision=d2.precision
        )
        result = compare_dates(d1, d2_same)
        assert result == 0

    @given(d1=year_only_date(), d2=st.one_of(year_month_date(), full_date()))
    @settings(max_examples=200)
    def test_one_year_only_same_year_returns_zero(
        self, d1: ParsedDate, d2: ParsedDate
    ) -> None:
        """When one date has only year and the other has more precision, same year → returns 0.

        The common precision is year-level, so comparison should only consider years.
        """
        # Force same year on d2
        d2_same_year = ParsedDate(
            year=d1.year, month=d2.month, day=d2.day, precision=d2.precision
        )
        result = compare_dates(d1, d2_same_year)
        assert result == 0

    @given(d1=year_month_date(), d2=year_month_date())
    @settings(max_examples=200)
    def test_both_month_same_year_different_months_correct_sign(
        self, d1: ParsedDate, d2: ParsedDate
    ) -> None:
        """When both have month precision, same year, different months → non-zero with correct sign."""
        # Force same year but different months
        d2_same_year = ParsedDate(
            year=d1.year, month=d2.month, day=d2.day, precision=d2.precision
        )
        result = compare_dates(d1, d2_same_year)

        if d1.month == d2_same_year.month:
            # Same year and month → equal at this precision
            assert result == 0
        else:
            # Different months → sign should reflect ordering
            assert result is not None
            if d1.month < d2_same_year.month:
                assert result < 0
            else:
                assert result > 0

    @given(d1=full_date(), d2=full_date())
    @settings(max_examples=200)
    def test_full_precision_correct_ordering(
        self, d1: ParsedDate, d2: ParsedDate
    ) -> None:
        """When both have full precision → correct ordering based on year, month, day."""
        result = compare_dates(d1, d2)
        assert result is not None

        # Determine expected ordering
        if d1.year != d2.year:
            expected_sign = 1 if d1.year > d2.year else -1
        elif d1.month != d2.month:
            expected_sign = 1 if d1.month > d2.month else -1
        elif d1.day != d2.day:
            expected_sign = 1 if d1.day > d2.day else -1
        else:
            expected_sign = 0

        if expected_sign == 0:
            assert result == 0
        elif expected_sign > 0:
            assert result > 0
        else:
            assert result < 0

    @given(d1=any_parsed_date, d2=any_parsed_date)
    @settings(max_examples=200)
    def test_antisymmetry(self, d1: ParsedDate, d2: ParsedDate) -> None:
        """Antisymmetry: compare_dates(a, b) == -compare_dates(b, a) (or both 0/None)."""
        result_ab = compare_dates(d1, d2)
        result_ba = compare_dates(d2, d1)

        if result_ab is None:
            assert result_ba is None
        else:
            assert result_ba is not None
            assert result_ab == -result_ba

    @given(d=any_parsed_date)
    @settings(max_examples=200)
    def test_reflexivity(self, d: ParsedDate) -> None:
        """Reflexivity: compare_dates(a, a) == 0."""
        result = compare_dates(d, d)
        assert result == 0
