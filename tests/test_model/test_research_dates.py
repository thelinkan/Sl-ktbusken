"""Tests for the research date helpers and the pending/completed rule.

Covers ``normalize_completed_date``, ``is_valid_calendar_date`` and how
``ResearchAction`` classifies itself as pending or completed.

**Validates: Requirements 6.1, 6.4, 6.9, 7.8**
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.research_case import (
    ResearchAction,
    is_pending,
    is_valid_calendar_date,
    normalize_completed_date,
)
from tests.test_model.research_strategies import (
    BLANK_DATES,
    IMPOSSIBLE_DATES,
    MALFORMED_DATES,
    actions,
    invalid_dates,
    valid_dates,
)


def _action(completed_date: object) -> ResearchAction:
    return ResearchAction(id="action_1", research_case_id="case_1", completed_date=completed_date)  # type: ignore[arg-type]


class TestNormalizeCompletedDate:
    """An empty value never means "completed"."""

    @pytest.mark.parametrize("blank", [None, "", " ", "   ", "\t", "\n ", " \t\n "])
    def test_blank_values_become_none(self, blank: str | None) -> None:
        """**Validates: Requirements 6.4, 7.8**"""
        assert normalize_completed_date(blank) is None

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("2026", "2026"),
            ("2026-05", "2026-05"),
            ("2026-05-01", "2026-05-01"),
            (" 2026-05-01 ", "2026-05-01"),
            ("\t2026-05-01\n", "2026-05-01"),
        ],
    )
    def test_non_blank_values_are_trimmed_not_dropped(self, value: str, expected: str) -> None:
        """**Validates: Requirements 6.4**"""
        assert normalize_completed_date(value) == expected

    def test_none_stays_none(self) -> None:
        assert normalize_completed_date(None) is None

    @given(value=st.one_of(st.none(), st.text(max_size=30), valid_dates()))
    @settings(max_examples=100, deadline=None)
    def test_result_is_none_or_non_empty_and_idempotent(self, value: str | None) -> None:
        """The result is never an empty string, and normalizing twice changes nothing.

        Feature: research-cases, Property: completion dates normalize to None or non-empty text

        **Validates: Requirements 6.4, 7.8**
        """
        once = normalize_completed_date(value)
        assert once is None or (once != "" and once == once.strip())
        assert normalize_completed_date(once) == once

    @given(blank=st.text(alphabet=" \t\n\r", max_size=12))
    @settings(max_examples=100, deadline=None)
    def test_any_whitespace_only_string_becomes_none(self, blank: str) -> None:
        """**Validates: Requirements 6.4, 7.8**"""
        assert normalize_completed_date(blank) is None


class TestIsValidCalendarDate:
    """A date must be a real calendar date, not merely ISO-shaped."""

    @pytest.mark.parametrize(
        "value",
        ["2026", "2026-05", "2026-05-01", "2026-12-31", "2024-02-29", "2000-02-29", "1760-02-29"],
    )
    def test_real_dates_are_valid(self, value: str) -> None:
        """**Validates: Requirements 6.9**"""
        assert is_valid_calendar_date(value) is True

    @pytest.mark.parametrize("value", ["2026-02-30", "2026-02-29", "2025-02-29", "1900-02-29"])
    def test_day_that_does_not_exist_is_invalid(self, value: str) -> None:
        """"2026-02-30" has the right shape but is not a date.

        **Validates: Requirements 5.5, 6.7**
        """
        assert is_valid_calendar_date(value) is False

    @pytest.mark.parametrize(
        "value", ["2026-04-31", "2026-13-01", "2026-00-10", "2026-06-00", "2026-06-32"]
    )
    def test_out_of_range_month_or_day_is_invalid(self, value: str) -> None:
        """**Validates: Requirements 5.5, 6.7**"""
        assert is_valid_calendar_date(value) is False

    def test_leap_years_follow_the_gregorian_rule(self) -> None:
        """2000 and 2024 are leap years; 1900 and 2025 are not."""
        assert is_valid_calendar_date("2000-02-29") is True
        assert is_valid_calendar_date("2024-02-29") is True
        assert is_valid_calendar_date("1900-02-29") is False
        assert is_valid_calendar_date("2025-02-29") is False

    def test_dates_lost_in_the_swedish_calendar_change_are_invalid(self) -> None:
        """Sweden skipped 1753-02-18 to 1753-02-28."""
        assert is_valid_calendar_date("1753-02-20") is False
        assert is_valid_calendar_date("1753-03-01") is True

    @pytest.mark.parametrize("value", list(MALFORMED_DATES))
    def test_malformed_values_are_invalid(self, value: str) -> None:
        """**Validates: Requirements 5.5, 6.7**"""
        assert is_valid_calendar_date(value) is False

    @pytest.mark.parametrize("blank", [None, *BLANK_DATES])
    def test_blank_is_not_a_date(self, blank: str | None) -> None:
        """Blank input is "no date", which is handled by normalization, not validity."""
        assert is_valid_calendar_date(blank) is False

    def test_surrounding_whitespace_is_ignored(self) -> None:
        assert is_valid_calendar_date(" 2026-05-01 ") is True

    @given(value=valid_dates())
    @settings(max_examples=100, deadline=None)
    def test_every_generated_real_date_is_valid(self, value: str) -> None:
        """Feature: research-cases, Property: real dates validate at every precision

        **Validates: Requirements 6.9**
        """
        assert is_valid_calendar_date(value) is True

    @given(value=invalid_dates())
    @settings(max_examples=100, deadline=None)
    def test_every_generated_impossible_or_malformed_date_is_invalid(self, value: str) -> None:
        """Feature: research-cases, Property: impossible and malformed dates are rejected

        **Validates: Requirements 5.5, 6.7**
        """
        assert is_valid_calendar_date(value) is False

    def test_the_strategy_pools_cover_the_cases_named_in_the_requirements(self) -> None:
        assert "2026-02-30" in IMPOSSIBLE_DATES
        assert "2026-13-01" in IMPOSSIBLE_DATES


class TestPendingAndCompleted:
    """An action is pending exactly when it has no completion date."""

    @pytest.mark.parametrize("blank", [None, *BLANK_DATES])
    def test_blank_completion_date_is_pending(self, blank: str | None) -> None:
        """An empty string must never be read as a completed action.

        **Validates: Requirements 6.4, 7.8**
        """
        action = _action(blank)
        assert action.completed_date is None
        assert is_pending(action) is True

    @pytest.mark.parametrize("value", ["2026", "2026-05", "2026-05-01"])
    def test_a_date_of_any_precision_is_completed(self, value: str) -> None:
        """**Validates: Requirements 6.4, 6.9**"""
        action = _action(value)
        assert action.completed_date == value
        assert is_pending(action) is False

    def test_padded_date_is_stored_trimmed(self) -> None:
        assert _action("  2026-05-01  ").completed_date == "2026-05-01"

    def test_clearing_a_date_after_construction_is_detected_by_the_validator_not_hidden(self) -> None:
        """Assigning "" after construction bypasses ``__post_init__``.

        The model does not silently coerce that assignment; the normalization
        happens on construction and in the editor. This pins the behavior so the
        validator test in task 3.2 knows an empty string can still reach it.
        """
        action = _action("2026-05-01")
        action.completed_date = ""
        assert action.completed_date == ""

    @given(action=actions())
    @settings(max_examples=100, deadline=None)
    def test_generated_actions_are_pending_exactly_when_no_date(self, action: ResearchAction) -> None:
        """No generated action ever holds an empty-string completion date.

        Feature: research-cases, Property: pending means no completion date

        **Validates: Requirements 6.4, 7.8**
        """
        assert action.completed_date != ""
        assert is_pending(action) == (action.completed_date is None)
        if action.completed_date is not None:
            assert is_valid_calendar_date(action.completed_date)

    @given(action=actions(pending=True, include_blank_completed=True))
    @settings(max_examples=100, deadline=None)
    def test_forced_pending_actions_are_always_pending(self, action: ResearchAction) -> None:
        """Even when built from a blank date, a pending action is pending.

        **Validates: Requirements 6.4, 7.8**
        """
        assert is_pending(action) is True
        assert action.completed_date is None

    @given(action=actions(pending=False))
    @settings(max_examples=100, deadline=None)
    def test_forced_completed_actions_are_never_pending(self, action: ResearchAction) -> None:
        """**Validates: Requirements 6.4, 6.9**"""
        assert is_pending(action) is False
