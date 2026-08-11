"""Unit tests for pure residence edit operations.

Covers prefill_span_from_years: reading a Source ``years`` value as an
Observation span suggestion (Requirements 4.1, 4.7, 4.8, 4.9, 4.10, 9.2).
"""

from __future__ import annotations

import pytest

from slaktbusken.services.residence_edit_ops import prefill_span_from_years


class TestPrefillTwoYears:
    """Two ascending years separated by a hyphen or an en dash (Req 4.7)."""

    def test_hyphen_separated_pair(self) -> None:
        assert prefill_span_from_years("1866-1870") == ("1866", "1870")

    def test_en_dash_separated_pair(self) -> None:
        assert prefill_span_from_years("1866\u20131870") == ("1866", "1870")

    @pytest.mark.parametrize(
        "value",
        [
            "1866 - 1870",
            "1866  -  1870",
            "1866 \u2013 1870",
            "  1866-1870  ",
            "\t1866\t-\t1870\t",
        ],
    )
    def test_surrounding_spaces_are_ignored(self, value: str) -> None:
        assert prefill_span_from_years(value) == ("1866", "1870")

    def test_range_bounds_are_accepted(self) -> None:
        assert prefill_span_from_years("1500-2100") == ("1500", "2100")

    def test_equal_years_read_as_that_year(self) -> None:
        assert prefill_span_from_years("1866-1866") == ("1866", "1866")


class TestPrefillSingleYear:
    """A single year fills both bounds (Req 4.8)."""

    def test_single_year(self) -> None:
        assert prefill_span_from_years("1866") == ("1866", "1866")

    def test_single_year_with_spaces(self) -> None:
        assert prefill_span_from_years("  1866  ") == ("1866", "1866")

    @pytest.mark.parametrize("value", ["1500", "2100"])
    def test_single_year_at_range_bounds(self, value: str) -> None:
        assert prefill_span_from_years(value) == (value, value)


class TestPrefillSkipped:
    """Unreadable values yield None, which drives the Swedish message (Req 4.9)."""

    def test_absent_value(self) -> None:
        assert prefill_span_from_years(None) is None

    @pytest.mark.parametrize("value", ["", "   ", "\t\n"])
    def test_empty_and_whitespace_only(self, value: str) -> None:
        assert prefill_span_from_years(value) is None

    def test_descending_pair(self) -> None:
        assert prefill_span_from_years("1870-1866") is None

    @pytest.mark.parametrize(
        "value",
        ["1499", "2101", "1499-1870", "1866-2101", "0999", "1499-2101"],
    )
    def test_year_outside_range(self, value: str) -> None:
        assert prefill_span_from_years(value) is None

    @pytest.mark.parametrize(
        "value",
        [
            "ca 1866",
            "1866-1870 (AI:18)",
            "1866/1870",
            "1866 till 1870",
            "1866\u20141870",       # em dash is not a separator we read
            "1866-1870-1875",
            "186-1870",
            "18666",
            "1866-187",
            "-1866",
            "1866-",
            "AI:18",
        ],
    )
    def test_unparsable_values(self, value: str) -> None:
        assert prefill_span_from_years(value) is None


class TestPrefillIsPure:
    """The Source years value is only read, never written back (Req 4.1, 4.10)."""

    def test_input_string_is_unchanged(self) -> None:
        years = "  1866 - 1870  "
        prefill_span_from_years(years)
        assert years == "  1866 - 1870  "

    def test_repeated_calls_give_the_same_result(self) -> None:
        assert prefill_span_from_years("1866-1870") == prefill_span_from_years("1866-1870")

    def test_narrower_user_span_is_not_affected(self) -> None:
        """A user-typed narrower span is untouched: prefill only reports a suggestion."""
        observed_from, observed_to = "1868", "1869"
        suggestion = prefill_span_from_years("1866-1870")
        assert suggestion == ("1866", "1870")
        assert (observed_from, observed_to) == ("1868", "1869")
