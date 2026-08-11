"""Unit tests for the day-interval algebra in slaktbusken/model/date_span.py.

Covers Requirements 2.1 (whitespace-only counts as absent) and 2.15 (day-interval
expansion and the strictly-earlier comparison).
"""

from datetime import date

import pytest

from slaktbusken.model.date_span import (
    DaySpan,
    OpenSpan,
    expand_iso,
    intersect,
    is_valid_iso,
    overlaps,
    precision_of,
    strictly_earlier,
    year_of,
    year_span,
)


# --- is_valid_iso ---


@pytest.mark.parametrize("value", ["1840", "1840-06", "1840-06-15", "  1840-06  ", "2100-12-31"])
def test_is_valid_iso_accepts_the_three_forms(value):
    assert is_valid_iso(value) is True


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        "184",
        "18400",
        "1840-",
        "1840-13",
        "1840-00",
        "1840-06-32",
        "1840-06-00",
        "1840/06/15",
        "1840-6-1",
        "1840-02-30",  # day does not exist in that month
        "1841-02-29",  # not a leap year
        "abcd",
    ],
)
def test_is_valid_iso_rejects_absent_and_malformed(value):
    assert is_valid_iso(value) is False


# --- expand_iso ---


def test_expand_iso_year_spans_the_whole_year():
    assert expand_iso("1840") == DaySpan(date(1840, 1, 1), date(1840, 12, 31))


def test_expand_iso_month_spans_first_to_last_day():
    assert expand_iso("1840-06") == DaySpan(date(1840, 6, 1), date(1840, 6, 30))


def test_expand_iso_month_respects_leap_years():
    assert expand_iso("1840-02") == DaySpan(date(1840, 2, 1), date(1840, 2, 29))
    assert expand_iso("1841-02") == DaySpan(date(1841, 2, 1), date(1841, 2, 28))


def test_expand_iso_day_spans_a_single_day():
    assert expand_iso("1840-06-15") == DaySpan(date(1840, 6, 15), date(1840, 6, 15))


@pytest.mark.parametrize("value", [None, "", "   ", "\t\n", "1840-13", "nonsense"])
def test_expand_iso_returns_none_for_absent_or_malformed(value):
    assert expand_iso(value) is None


def test_expand_iso_trims_surrounding_whitespace():
    assert expand_iso("  1840-06-15  ") == expand_iso("1840-06-15")


# --- strictly_earlier ---


def test_strictly_earlier_requires_non_touching_intervals():
    assert strictly_earlier("1840", "1841") is True
    assert strictly_earlier("1840-06", "1840-07") is True
    assert strictly_earlier("1840-06-15", "1840-06-16") is True


def test_strictly_earlier_is_false_for_overlapping_precisions():
    # "1840" is neither earlier nor later than "1840-06" (Requirement 2.15)
    assert strictly_earlier("1840", "1840-06") is False
    assert strictly_earlier("1840-06", "1840") is False


def test_strictly_earlier_is_false_for_equal_values():
    assert strictly_earlier("1840-06-15", "1840-06-15") is False


@pytest.mark.parametrize("a,b", [(None, "1840"), ("1840", None), ("junk", "1840"), (None, None)])
def test_strictly_earlier_is_false_when_a_side_is_absent(a, b):
    assert strictly_earlier(a, b) is False


# --- year_of / precision_of ---


def test_year_of_reads_the_year_part():
    assert year_of("1840") == 1840
    assert year_of("1840-06") == 1840
    assert year_of("1840-06-15") == 1840


def test_year_of_is_none_for_absent_or_malformed():
    assert year_of("  ") is None
    assert year_of("1840-13") is None


def test_precision_of_classifies_the_three_forms():
    assert precision_of("1840") == "year"
    assert precision_of("1840-06") == "month"
    assert precision_of("1840-06-15") == "day"


def test_precision_of_is_none_for_absent_or_malformed():
    assert precision_of(None) is None
    assert precision_of("   ") is None
    assert precision_of("1840-99") is None


# --- overlaps / intersect / year_span ---


def test_overlaps_is_true_for_shared_days_including_a_single_boundary_day():
    a = DaySpan(date(1840, 1, 1), date(1840, 6, 30))
    b = DaySpan(date(1840, 6, 30), date(1841, 1, 1))
    assert overlaps(a, b) is True
    assert overlaps(b, a) is True


def test_overlaps_is_false_for_adjacent_but_disjoint_spans():
    a = DaySpan(date(1840, 1, 1), date(1840, 6, 30))
    b = DaySpan(date(1840, 7, 1), date(1840, 12, 31))
    assert overlaps(a, b) is False


def test_intersect_returns_the_shared_interval():
    a = expand_iso("1840")
    b = expand_iso("1840-06")
    assert intersect(a, b) == DaySpan(date(1840, 6, 1), date(1840, 6, 30))


def test_intersect_returns_none_for_disjoint_spans():
    assert intersect(expand_iso("1840"), expand_iso("1841")) is None


def test_year_span_covers_the_whole_year():
    assert year_span(1875) == DaySpan(date(1875, 1, 1), date(1875, 12, 31))


# --- OpenSpan ---


def test_open_span_bounded_contains_and_overlaps_years():
    span = OpenSpan(date(1840, 6, 1), date(1845, 6, 1))
    assert span.contains_year(1841) is True
    assert span.contains_year(1840) is False  # partial year
    assert span.overlaps_year(1840) is True
    assert span.overlaps_year(1845) is True
    assert span.overlaps_year(1839) is False
    assert span.overlaps_year(1846) is False


def test_open_span_unbounded_start_reaches_every_earlier_year():
    span = OpenSpan(None, date(1845, 6, 1))
    assert span.contains_year(1500) is True
    assert span.overlaps_year(1500) is True
    assert span.contains_year(1845) is False
    assert span.overlaps_year(1845) is True
    assert span.overlaps_year(1846) is False


def test_open_span_unbounded_end_reaches_every_later_year():
    span = OpenSpan(date(1840, 1, 1), None)
    assert span.contains_year(2100) is True
    assert span.overlaps_year(1839) is False
    assert span.contains_year(1840) is True


def test_open_span_unbounded_both_matches_every_year():
    span = OpenSpan()
    assert span.is_unbounded_both() is True
    assert span.contains_year(1) is True
    assert span.overlaps_year(9999) is True


def test_open_span_with_one_bound_is_not_unbounded_both():
    assert OpenSpan(date(1840, 1, 1), None).is_unbounded_both() is False
    assert OpenSpan(None, date(1840, 1, 1)).is_unbounded_both() is False


# --- purity ---


def test_day_span_and_open_span_are_frozen():
    with pytest.raises(Exception):
        DaySpan(date(1840, 1, 1), date(1840, 12, 31)).first = date(1841, 1, 1)
    with pytest.raises(Exception):
        OpenSpan().first = date(1841, 1, 1)
