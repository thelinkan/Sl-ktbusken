# Feature: kontrollera-personer, Property 6: Reasonable date range
"""Property-based tests for reasonable date range check.

For any event with a date, if the year is less than 1000 or greater than the
current year, and the "Rimliga datum" check is enabled, the engine SHALL produce
a finding. If the year is in range [1000, current_year], no finding SHALL be
produced by this check.

**Validates: Requirements 8.1**
"""

from __future__ import annotations

import datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.person import Name, Person
from slaktbusken.persistence.settings_io import LogicCheckConfig, PersonCheckConfig
from slaktbusken.services.checks.chronology_checks import check_reasonable_dates
from slaktbusken.services.person_check_engine import CheckContext


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

current_year = datetime.date.today().year

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Years outside range (should produce finding)
unreasonable_year_st = st.one_of(
    st.integers(min_value=1, max_value=999),  # before 1000
    st.integers(min_value=current_year + 1, max_value=9999),  # after current year
)

# Years inside range (should NOT produce finding)
reasonable_year_st = st.integers(min_value=1000, max_value=current_year)

# Month and day strategies for generating date strings
month_st = st.integers(min_value=1, max_value=12)
day_st = st.integers(min_value=1, max_value=28)  # safe day range

precision_st = st.sampled_from(["exact", "about", "before", "after"])


@st.composite
def date_value_with_year(draw: st.DrawFn, year_strategy: st.SearchStrategy[int]) -> DateValue:
    """Generate a DateValue with a year from the given strategy.

    Always uses 4-digit zero-padded year format since the date parser
    (parse_date_value) requires exactly 4 digits via regex \\d{4}.
    """
    year = draw(year_strategy)
    # Choose format: year only, year-month, or year-month-day
    fmt = draw(st.sampled_from(["year", "year-month", "year-month-day"]))
    if fmt == "year":
        value = f"{year:04d}"
    elif fmt == "year-month":
        m = draw(month_st)
        value = f"{year:04d}-{m:02d}"
    else:
        m = draw(month_st)
        d = draw(day_st)
        value = f"{year:04d}-{m:02d}-{d:02d}"
    precision = draw(precision_st)
    return DateValue(value=value, precision=precision)


def make_person(person_id: str = "p1") -> Person:
    """Create a minimal test person."""
    return Person(
        id=person_id,
        sex="M",
        names=[Name(type="birth", given="Test", surname="Person")],
    )


def make_event_with_date(date_value: DateValue, person_id: str = "p1") -> Event:
    """Create a BIRTH event with the given date for the specified person."""
    return Event(
        id="ev1",
        type="birth",
        participants=[Participant(person_id=person_id, role="subject")],
        date=date_value,
    )


def make_config(enabled: bool = True) -> PersonCheckConfig:
    """Create a PersonCheckConfig with reasonable_dates control set as specified."""
    config = PersonCheckConfig()
    config.logic_checks.reasonable_dates = enabled
    return config


def make_context() -> CheckContext:
    """Create a minimal CheckContext with current_year set."""
    ctx = CheckContext()
    ctx.current_year = current_year
    return ctx


# ---------------------------------------------------------------------------
# Property 6: Reasonable date range
# ---------------------------------------------------------------------------


class TestReasonableDateProperty:
    """Feature: kontrollera-personer, Property 6: Reasonable date range

    For any event with a date, if the year is less than 1000 or greater than
    the current year, and the "Rimliga datum" check is enabled, the engine
    SHALL produce a finding. If the year is in range [1000, current_year],
    no finding SHALL be produced by this check.

    **Validates: Requirements 8.1**
    """

    @given(date_value=date_value_with_year(unreasonable_year_st))
    @settings(max_examples=200)
    def test_unreasonable_year_produces_finding(self, date_value: DateValue) -> None:
        """Year < 1000 or year > current_year SHALL produce a finding."""
        person = make_person()
        events = [make_event_with_date(date_value)]
        config = make_config(enabled=True)
        context = make_context()

        findings = check_reasonable_dates(person, events, config, context)

        assert len(findings) >= 1
        assert findings[0].person_id == person.id

    @given(date_value=date_value_with_year(reasonable_year_st))
    @settings(max_examples=200)
    def test_reasonable_year_produces_no_finding(self, date_value: DateValue) -> None:
        """Year in [1000, current_year] SHALL NOT produce a finding."""
        person = make_person()
        events = [make_event_with_date(date_value)]
        config = make_config(enabled=True)
        context = make_context()

        findings = check_reasonable_dates(person, events, config, context)

        assert len(findings) == 0

    @given(date_value=date_value_with_year(unreasonable_year_st))
    @settings(max_examples=200)
    def test_disabled_check_produces_no_finding(self, date_value: DateValue) -> None:
        """When config.logic_checks.reasonable_dates = False, no findings."""
        person = make_person()
        events = [make_event_with_date(date_value)]
        config = make_config(enabled=False)
        context = make_context()

        findings = check_reasonable_dates(person, events, config, context)

        assert len(findings) == 0

