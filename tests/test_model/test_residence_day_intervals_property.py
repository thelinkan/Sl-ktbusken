# Feature: residence-periods, Property 4: Day-interval derivations match their definitions and mutate nothing
"""Property-based test for the residence day-interval derivations.

Feature: residence-periods, Property 4: Day-interval derivations match their definitions and mutate nothing

For any ISO 8601 value, expansion yields exactly the closed day interval it
denotes (ÅÅÅÅ → 1 Jan through 31 Dec, ÅÅÅÅ-MM → first through last day of the
month, ÅÅÅÅ-MM-DD → that day), and value A counts as earlier than value B only
when the last day of A precedes the first day of B; for any Residence_Fact, the
derived Certain_Core equals the interval from the last day of `start.latest`
through the first day of `end.earliest` and is empty when either bound is absent
or the interval inverts, the derived Possible_Span equals the first day of
`start.earliest` through the last day of `end.latest` and is unbounded where a
bound is absent, and the Residence_Fact is unchanged after both derivations.

**Validates: Requirements 2.13, 2.15, 2.16**
"""

from __future__ import annotations

import calendar
import copy
import re
from datetime import date
from typing import Optional

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.date_span import expand_iso, strictly_earlier
from slaktbusken.model.residence import ResidenceFact, certain_core, possible_span
from tests.test_model.residence_strategies import (
    ABSENT_ISO_VALUES,
    MALFORMED_ISO_VALUES,
    MAX_PLAUSIBLE_YEAR,
    MIN_PLAUSIBLE_YEAR,
    iso_values,
    residence_facts,
)


# ---------------------------------------------------------------------------
# An independent reading of the definitions in Requirement 2.15
# ---------------------------------------------------------------------------

_WELL_FORMED = re.compile(r"^\d{4}(?:-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?)?$")


def _denoted_interval(value: Optional[str]) -> Optional[tuple[date, date]]:
    """The closed day interval *value* denotes, spelled out from Requirement 2.15.

    Returns ``None`` when the value denotes no interval: absent (``None``, empty,
    whitespace-only) or malformed, a calendar day that does not exist included.
    Written independently of :mod:`slaktbusken.model.date_span` so the test
    checks the definition rather than echoing the implementation.
    """
    if value is None:
        return None
    trimmed = value.strip()
    if not _WELL_FORMED.match(trimmed):
        return None

    parts = [int(part) for part in trimmed.split("-")]
    year = parts[0]
    if len(parts) == 1:
        return (date(year, 1, 1), date(year, 12, 31))

    month = parts[1]
    days_in_month = calendar.monthrange(year, month)[1]
    if len(parts) == 2:
        return (date(year, month, 1), date(year, month, days_in_month))

    day = parts[2]
    if day > days_in_month:
        return None
    return (date(year, month, day), date(year, month, day))


_well_formed_iso = iso_values(include_absent=False, include_malformed=False)
_no_interval_iso = st.sampled_from(list(ABSENT_ISO_VALUES) + list(MALFORMED_ISO_VALUES))


class TestDayIntervalDerivations:
    """Feature: residence-periods, Property 4: Day-interval derivations match their definitions and mutate nothing

    For any ISO 8601 value, expansion yields exactly the closed day interval it
    denotes, and A is earlier than B only when the last day of A precedes the
    first day of B; for any Residence_Fact the Certain_Core and Possible_Span
    match their definitions and the fact is left unchanged.

    **Validates: Requirements 2.13, 2.15, 2.16**
    """

    @given(value=_well_formed_iso)
    @settings(max_examples=100, deadline=None)
    def test_expansion_yields_the_denoted_day_interval(self, value: str) -> None:
        """Each ISO precision expands to exactly the day interval it denotes.

        **Validates: Requirements 2.15**
        """
        expected = _denoted_interval(value)
        assert expected is not None, f"{value!r} should denote a day interval"

        span = expand_iso(value)
        assert span is not None, f"expand_iso({value!r}) denoted no interval"
        assert (span.first, span.last) == expected, (
            f"expand_iso({value!r}) gave {span.first}..{span.last}, "
            f"expected {expected[0]}..{expected[1]}"
        )

    @given(value=_no_interval_iso)
    @settings(max_examples=100, deadline=None)
    def test_absent_and_malformed_values_denote_no_interval(
        self, value: Optional[str]
    ) -> None:
        """An absent or malformed value expands to no day interval.

        **Validates: Requirements 2.15**
        """
        assert _denoted_interval(value) is None, f"{value!r} should denote no interval"
        assert expand_iso(value) is None, f"expand_iso({value!r}) denoted an interval"

    @given(a=_well_formed_iso, b=_well_formed_iso)
    @settings(max_examples=100, deadline=None)
    def test_earlier_only_when_last_day_precedes_first_day(self, a: str, b: str) -> None:
        """A is earlier than B exactly when the last day of A precedes B's first day.

        **Validates: Requirements 2.15**
        """
        span_a = _denoted_interval(a)
        span_b = _denoted_interval(b)
        assert span_a is not None and span_b is not None

        expected = span_a[1] < span_b[0]
        assert strictly_earlier(a, b) is expected, (
            f"strictly_earlier({a!r}, {b!r}) should be {expected}: "
            f"{a!r} ends {span_a[1]}, {b!r} begins {span_b[0]}"
        )

    @given(year=st.integers(min_value=MIN_PLAUSIBLE_YEAR, max_value=MAX_PLAUSIBLE_YEAR))
    @settings(max_examples=100, deadline=None)
    def test_a_year_is_neither_earlier_nor_later_than_a_month_inside_it(
        self, year: int
    ) -> None:
        """A whole year is neither earlier nor later than a month inside it.

        **Validates: Requirements 2.15**
        """
        whole_year = f"{year:04d}"
        month_inside = f"{year:04d}-06"

        assert not strictly_earlier(whole_year, month_inside)
        assert not strictly_earlier(month_inside, whole_year)

    @given(fact=residence_facts())
    @settings(max_examples=100, deadline=None)
    def test_certain_core_matches_its_definition(self, fact: ResidenceFact) -> None:
        """The Certain_Core runs from start.latest's last day to end.earliest's first.

        **Validates: Requirements 2.13**
        """
        start_latest = _denoted_interval(fact.start.latest)
        end_earliest = _denoted_interval(fact.end.earliest)
        core = certain_core(fact)

        if start_latest is None or end_earliest is None:
            assert core is None, (
                f"core should be empty: start.latest={fact.start.latest!r}, "
                f"end.earliest={fact.end.earliest!r}"
            )
            return

        first, last = start_latest[1], end_earliest[0]
        if first > last:
            assert core is None, f"inverted core {first}..{last} should be empty"
            return

        assert core is not None, f"core {first}..{last} should not be empty"
        assert (core.first, core.last) == (first, last), (
            f"core gave {core.first}..{core.last}, expected {first}..{last}"
        )

    @given(fact=residence_facts())
    @settings(max_examples=100, deadline=None)
    def test_possible_span_matches_its_definition(self, fact: ResidenceFact) -> None:
        """The Possible_Span runs from start.earliest's first day to end.latest's last.

        **Validates: Requirements 2.16**
        """
        start_earliest = _denoted_interval(fact.start.earliest)
        end_latest = _denoted_interval(fact.end.latest)
        span = possible_span(fact)

        expected_first = None if start_earliest is None else start_earliest[0]
        expected_last = None if end_latest is None else end_latest[1]

        assert span.first == expected_first, (
            f"span.first {span.first} does not match start.earliest="
            f"{fact.start.earliest!r} (expected {expected_first})"
        )
        assert span.last == expected_last, (
            f"span.last {span.last} does not match end.latest="
            f"{fact.end.latest!r} (expected {expected_last})"
        )
        assert (span.first is None) == (start_earliest is None)
        assert (span.last is None) == (end_latest is None)

    @given(fact=residence_facts())
    @settings(max_examples=100, deadline=None)
    def test_derivations_leave_the_fact_unchanged(self, fact: ResidenceFact) -> None:
        """Both derivations are pure: the Residence_Fact is untouched.

        **Validates: Requirements 2.13, 2.16**
        """
        before = copy.deepcopy(fact)

        certain_core(fact)
        possible_span(fact)
        # A second round must see exactly the same input as the first.
        certain_core(fact)
        possible_span(fact)

        assert fact == before, "a derivation mutated the Residence_Fact"
        assert fact.start == before.start and fact.end == before.end
        assert fact.observations == before.observations
