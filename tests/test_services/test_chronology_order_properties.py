"""Property-based tests for chronological order violation checks.

Feature: kontrollera-personer, Property 7: Chronological order violations

Validates: Requirements 8.2, 8.3, 8.4, 8.5, 8.6, 8.7
"""

from __future__ import annotations

import datetime

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.person import Name, Person
from slaktbusken.persistence.settings_io import PersonCheckConfig, LogicCheckConfig
from slaktbusken.services.checks.chronology_checks import (
    check_no_event_before_birth,
    check_burial_not_before_death,
    check_only_burial_after_death,
    check_no_own_events_after_death,
    check_birth_not_after_parent_death,
    check_no_event_before_parent_birth,
)
from slaktbusken.services.person_check_engine import CheckContext


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

year_st = st.integers(min_value=1700, max_value=2020)


@st.composite
def date_value_st(draw: st.DrawFn, year: int | None = None) -> DateValue:
    """Generate a full-precision DateValue (YYYY-MM-DD)."""
    y = year if year is not None else draw(year_st)
    m = draw(st.integers(min_value=1, max_value=12))
    d = draw(st.integers(min_value=1, max_value=28))  # safe day range
    return DateValue(value=f"{y:04d}-{m:02d}-{d:02d}", precision="exact")


# Non-burial, non-death, non-allowed event types for testing
_REGULAR_EVENT_TYPES = [
    "baptism", "CONFIRMATION", "marriage", "RESIDENCE",
    "OCCUPATION", "EMIGRATION", "IMMIGRATION",
]

_ALLOWED_AFTER_DEATH_TYPES = ["burial", "probate", "will"]

regular_event_type_st = st.sampled_from(_REGULAR_EVENT_TYPES)
allowed_after_death_type_st = st.sampled_from(_ALLOWED_AFTER_DEATH_TYPES)
burial_type_st = st.sampled_from(["burial", "probate"])


def _make_person(person_id: str = "p1") -> Person:
    """Create a simple test person."""
    return Person(
        id=person_id,
        sex="M",
        names=[Name(type="birth", given="Test", surname="Person")],
    )


def _make_config(
    no_event_before_birth: bool = True,
    burial_not_before_death: bool = True,
    only_burial_after_death: bool = True,
    no_own_events_after_death: bool = True,
    birth_not_after_parent_death: bool = True,
    no_event_before_parent_birth: bool = True,
) -> PersonCheckConfig:
    """Create a PersonCheckConfig with specified logic check flags."""
    return PersonCheckConfig(
        logic_checks=LogicCheckConfig(
            no_event_before_birth=no_event_before_birth,
            burial_not_before_death=burial_not_before_death,
            only_burial_after_death=only_burial_after_death,
            no_own_events_after_death=no_own_events_after_death,
            birth_not_after_parent_death=birth_not_after_parent_death,
            no_event_before_parent_birth=no_event_before_parent_birth,
        )
    )


# ---------------------------------------------------------------------------
# Property 7: Chronological order violations
# ---------------------------------------------------------------------------


class TestNoEventBeforeBirth:
    """check_no_event_before_birth: event date < birth date → finding.

    **Validates: Requirements 8.2**
    """

    @given(
        birth_year=st.integers(min_value=1750, max_value=2000),
        offset_years=st.integers(min_value=1, max_value=50),
        event_type=regular_event_type_st,
    )
    @settings(max_examples=200)
    def test_event_before_birth_produces_finding(
        self, birth_year: int, offset_years: int, event_type: str
    ) -> None:
        """An event with a date before birth SHALL produce a finding."""
        person = _make_person()
        event_year = birth_year - offset_years

        birth_event = Event(
            id="ev_birth",
            type="birth",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value=f"{birth_year:04d}-06-15", precision="exact"),
        )
        early_event = Event(
            id="ev_early",
            type=event_type,
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value=f"{event_year:04d}-06-15", precision="exact"),
        )

        events = [birth_event, early_event]
        config = _make_config()

        findings = check_no_event_before_birth(person, events, config)
        assert len(findings) >= 1
        assert any("före födelsen" in f.message for f in findings)

    @given(
        birth_year=st.integers(min_value=1750, max_value=2000),
        offset_years=st.integers(min_value=0, max_value=80),
        event_type=regular_event_type_st,
    )
    @settings(max_examples=200)
    def test_event_on_or_after_birth_no_finding(
        self, birth_year: int, offset_years: int, event_type: str
    ) -> None:
        """An event with date >= birth SHALL NOT produce a finding."""
        person = _make_person()
        event_year = birth_year + offset_years

        birth_event = Event(
            id="ev_birth",
            type="birth",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value=f"{birth_year:04d}-06-15", precision="exact"),
        )
        later_event = Event(
            id="ev_later",
            type=event_type,
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value=f"{event_year:04d}-06-15", precision="exact"),
        )

        events = [birth_event, later_event]
        config = _make_config()

        findings = check_no_event_before_birth(person, events, config)
        assert len(findings) == 0


class TestBurialNotBeforeDeath:
    """check_burial_not_before_death: BURIAL/ESTATE_INVENTORY date < death → finding.

    **Validates: Requirements 8.3**
    """

    @given(
        death_year=st.integers(min_value=1750, max_value=2000),
        offset_years=st.integers(min_value=1, max_value=50),
        burial_type=burial_type_st,
    )
    @settings(max_examples=200)
    def test_burial_before_death_produces_finding(
        self, death_year: int, offset_years: int, burial_type: str
    ) -> None:
        """A BURIAL/ESTATE_INVENTORY before death SHALL produce a finding."""
        person = _make_person()
        burial_year = death_year - offset_years

        death_event = Event(
            id="ev_death",
            type="death",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value=f"{death_year:04d}-06-15", precision="exact"),
        )
        burial_event = Event(
            id="ev_burial",
            type=burial_type,
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value=f"{burial_year:04d}-06-15", precision="exact"),
        )

        events = [death_event, burial_event]
        config = _make_config()

        findings = check_burial_not_before_death(person, events, config)
        assert len(findings) >= 1
        assert any("före döden" in f.message for f in findings)

    @given(
        death_year=st.integers(min_value=1750, max_value=2000),
        offset_days=st.integers(min_value=0, max_value=365),
        burial_type=burial_type_st,
    )
    @settings(max_examples=200)
    def test_burial_on_or_after_death_no_finding(
        self, death_year: int, offset_days: int, burial_type: str
    ) -> None:
        """A BURIAL/ESTATE_INVENTORY on or after death SHALL NOT produce a finding."""
        person = _make_person()
        # Use same year, later month to ensure it's after death
        burial_year = death_year + (1 if offset_days > 180 else 0)
        # Ensure burial is on or after death
        death_date_str = f"{death_year:04d}-03-15"
        burial_date_str = f"{death_year:04d}-03-{15 + min(offset_days, 13):02d}"
        if offset_days > 13:
            burial_date_str = f"{death_year:04d}-06-15"

        death_event = Event(
            id="ev_death",
            type="death",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value=death_date_str, precision="exact"),
        )
        burial_event = Event(
            id="ev_burial",
            type=burial_type,
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value=burial_date_str, precision="exact"),
        )

        events = [death_event, burial_event]
        config = _make_config()

        findings = check_burial_not_before_death(person, events, config)
        assert len(findings) == 0


class TestOnlyBurialAfterDeath:
    """check_only_burial_after_death: non-allowed event after death → finding.

    **Validates: Requirements 8.4**
    """

    @given(
        death_year=st.integers(min_value=1750, max_value=2000),
        offset_years=st.integers(min_value=1, max_value=50),
        event_type=regular_event_type_st,
    )
    @settings(max_examples=200)
    def test_regular_event_after_death_produces_finding(
        self, death_year: int, offset_years: int, event_type: str
    ) -> None:
        """A non-allowed event after death SHALL produce a finding."""
        person = _make_person()
        event_year = death_year + offset_years

        death_event = Event(
            id="ev_death",
            type="death",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value=f"{death_year:04d}-06-15", precision="exact"),
        )
        after_event = Event(
            id="ev_after",
            type=event_type,
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value=f"{event_year:04d}-06-15", precision="exact"),
        )

        events = [death_event, after_event]
        config = _make_config()

        findings = check_only_burial_after_death(person, events, config)
        assert len(findings) >= 1
        assert any("efter döden" in f.message for f in findings)

    @given(
        death_year=st.integers(min_value=1750, max_value=2000),
        offset_years=st.integers(min_value=1, max_value=10),
        allowed_type=allowed_after_death_type_st,
    )
    @settings(max_examples=200)
    def test_allowed_event_after_death_no_finding(
        self, death_year: int, offset_years: int, allowed_type: str
    ) -> None:
        """BURIAL/ESTATE_INVENTORY/WILL after death SHALL NOT produce a finding."""
        person = _make_person()
        event_year = death_year + offset_years

        death_event = Event(
            id="ev_death",
            type="death",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value=f"{death_year:04d}-06-15", precision="exact"),
        )
        allowed_event = Event(
            id="ev_allowed",
            type=allowed_type,
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value=f"{event_year:04d}-06-15", precision="exact"),
        )

        events = [death_event, allowed_event]
        config = _make_config()

        findings = check_only_burial_after_death(person, events, config)
        assert len(findings) == 0


class TestNoOwnEventsAfterDeath:
    """check_no_own_events_after_death: principal event after death → finding.

    **Validates: Requirements 8.5**
    """

    @given(
        death_year=st.integers(min_value=1750, max_value=2000),
        offset_years=st.integers(min_value=1, max_value=50),
        event_type=regular_event_type_st,
    )
    @settings(max_examples=200)
    def test_principal_event_after_death_produces_finding(
        self, death_year: int, offset_years: int, event_type: str
    ) -> None:
        """A principal event (non-allowed) after death SHALL produce a finding."""
        person = _make_person()
        event_year = death_year + offset_years

        death_event = Event(
            id="ev_death",
            type="death",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value=f"{death_year:04d}-06-15", precision="exact"),
        )
        own_event = Event(
            id="ev_own",
            type=event_type,
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value=f"{event_year:04d}-06-15", precision="exact"),
        )

        events = [death_event, own_event]
        config = _make_config()

        findings = check_no_own_events_after_death(person, events, config)
        assert len(findings) >= 1
        assert any("efter döden" in f.message for f in findings)

    @given(
        death_year=st.integers(min_value=1750, max_value=2000),
        offset_years=st.integers(min_value=1, max_value=50),
        event_type=regular_event_type_st,
    )
    @settings(max_examples=200)
    def test_witness_event_after_death_no_finding(
        self, death_year: int, offset_years: int, event_type: str
    ) -> None:
        """A non-principal (witness) event after death SHALL NOT produce a finding."""
        person = _make_person()
        event_year = death_year + offset_years

        death_event = Event(
            id="ev_death",
            type="death",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value=f"{death_year:04d}-06-15", precision="exact"),
        )
        witness_event = Event(
            id="ev_witness",
            type=event_type,
            participants=[Participant(person_id="p1", role="witness")],
            date=DateValue(value=f"{event_year:04d}-06-15", precision="exact"),
        )

        events = [death_event, witness_event]
        config = _make_config()

        findings = check_no_own_events_after_death(person, events, config)
        assert len(findings) == 0


class TestBirthNotAfterParentDeath:
    """check_birth_not_after_parent_death: child birth > 270 days after parent death → finding.

    **Validates: Requirements 8.6**
    """

    @given(
        parent_death_year=st.integers(min_value=1750, max_value=2000),
    )
    @settings(max_examples=200)
    def test_birth_more_than_270_days_after_parent_death_produces_finding(
        self, parent_death_year: int
    ) -> None:
        """Child birth > 270 days after parent death SHALL produce a finding."""
        child = _make_person("child1")
        parent = Person(
            id="parent1",
            sex="M",
            names=[Name(type="birth", given="Parent", surname="Person")],
        )

        # Parent dies on Jan 1, child born on Dec 1 (335 days later > 270)
        parent_death_event = Event(
            id="ev_parent_death",
            type="death",
            participants=[Participant(person_id="parent1", role="subject")],
            date=DateValue(value=f"{parent_death_year:04d}-01-01", precision="exact"),
        )
        parent_birth_event = Event(
            id="ev_parent_birth",
            type="birth",
            participants=[Participant(person_id="parent1", role="subject")],
            date=DateValue(value=f"{parent_death_year - 50:04d}-06-15", precision="exact"),
        )
        child_birth_event = Event(
            id="ev_child_birth",
            type="birth",
            participants=[Participant(person_id="child1", role="subject")],
            date=DateValue(value=f"{parent_death_year:04d}-12-01", precision="exact"),
        )

        child_events = [child_birth_event]
        parent_events = [parent_birth_event, parent_death_event]

        context = CheckContext(
            persons_by_id={"child1": child, "parent1": parent},
            events_by_person={"parent1": parent_events, "child1": child_events},
            parents_of={"child1": ["parent1"]},
            current_year=datetime.date.today().year,
        )
        config = _make_config()

        findings = check_birth_not_after_parent_death(child, child_events, config, context)
        assert len(findings) >= 1
        assert any("270 dagar" in f.message for f in findings)

    @given(
        parent_death_year=st.integers(min_value=1750, max_value=2000),
        offset_days=st.integers(min_value=0, max_value=269),
    )
    @settings(max_examples=200)
    def test_birth_within_270_days_after_parent_death_no_finding(
        self, parent_death_year: int, offset_days: int
    ) -> None:
        """Child birth <= 270 days after parent death SHALL NOT produce a finding."""
        child = _make_person("child1")
        parent = Person(
            id="parent1",
            sex="M",
            names=[Name(type="birth", given="Parent", surname="Person")],
        )

        # Parent dies on Mar 1, child born within offset_days
        # Use a base date and add days manually (staying in safe date range)
        # Parent death: March 1, child birth within 270 days (before Nov 26)
        parent_death_date = f"{parent_death_year:04d}-03-01"
        # Calculate child birth date by adding offset_days months (approximation for safe range)
        # For simplicity, use June 1 (92 days after March 1, always < 270)
        # We use a fixed date that is guaranteed within 270 days
        month_offset = offset_days // 28
        if month_offset > 8:
            month_offset = 8
        child_birth_month = 3 + month_offset
        if child_birth_month > 12:
            child_birth_month = 12
        child_birth_date = f"{parent_death_year:04d}-{child_birth_month:02d}-01"

        # Ensure parent death is before child birth at this level
        # If month is same (3), child born same month as parent death = 0 days apart
        # That's valid (within 270 days)

        parent_death_event = Event(
            id="ev_parent_death",
            type="death",
            participants=[Participant(person_id="parent1", role="subject")],
            date=DateValue(value=parent_death_date, precision="exact"),
        )
        parent_birth_event = Event(
            id="ev_parent_birth",
            type="birth",
            participants=[Participant(person_id="parent1", role="subject")],
            date=DateValue(value=f"{parent_death_year - 50:04d}-06-15", precision="exact"),
        )
        child_birth_event = Event(
            id="ev_child_birth",
            type="birth",
            participants=[Participant(person_id="child1", role="subject")],
            date=DateValue(value=child_birth_date, precision="exact"),
        )

        child_events = [child_birth_event]
        parent_events = [parent_birth_event, parent_death_event]

        context = CheckContext(
            persons_by_id={"child1": child, "parent1": parent},
            events_by_person={"parent1": parent_events, "child1": child_events},
            parents_of={"child1": ["parent1"]},
            current_year=datetime.date.today().year,
        )
        config = _make_config()

        findings = check_birth_not_after_parent_death(child, child_events, config, context)
        assert len(findings) == 0


class TestNoEventBeforeParentBirth:
    """check_no_event_before_parent_birth: event date < parent birth → finding.

    **Validates: Requirements 8.7**
    """

    @given(
        parent_birth_year=st.integers(min_value=1750, max_value=2000),
        offset_years=st.integers(min_value=1, max_value=50),
        event_type=regular_event_type_st,
    )
    @settings(max_examples=200)
    def test_event_before_parent_birth_produces_finding(
        self, parent_birth_year: int, offset_years: int, event_type: str
    ) -> None:
        """An event before a parent's birth SHALL produce a finding."""
        child = _make_person("child1")
        parent = Person(
            id="parent1",
            sex="F",
            names=[Name(type="birth", given="Mamma", surname="Person")],
        )

        event_year = parent_birth_year - offset_years

        parent_birth_event = Event(
            id="ev_parent_birth",
            type="birth",
            participants=[Participant(person_id="parent1", role="subject")],
            date=DateValue(value=f"{parent_birth_year:04d}-06-15", precision="exact"),
        )
        child_event = Event(
            id="ev_child",
            type=event_type,
            participants=[Participant(person_id="child1", role="subject")],
            date=DateValue(value=f"{event_year:04d}-06-15", precision="exact"),
        )

        child_events = [child_event]
        parent_events = [parent_birth_event]

        context = CheckContext(
            persons_by_id={"child1": child, "parent1": parent},
            events_by_person={"parent1": parent_events, "child1": child_events},
            parents_of={"child1": ["parent1"]},
            current_year=datetime.date.today().year,
        )
        config = _make_config()

        findings = check_no_event_before_parent_birth(child, child_events, config, context)
        assert len(findings) >= 1
        assert any("före förälders" in f.message for f in findings)

    @given(
        parent_birth_year=st.integers(min_value=1750, max_value=1970),
        offset_years=st.integers(min_value=15, max_value=50),
        event_type=regular_event_type_st,
    )
    @settings(max_examples=200)
    def test_event_after_parent_birth_no_finding(
        self, parent_birth_year: int, offset_years: int, event_type: str
    ) -> None:
        """An event after a parent's birth SHALL NOT produce a finding."""
        child = _make_person("child1")
        parent = Person(
            id="parent1",
            sex="F",
            names=[Name(type="birth", given="Mamma", surname="Person")],
        )

        event_year = parent_birth_year + offset_years

        parent_birth_event = Event(
            id="ev_parent_birth",
            type="birth",
            participants=[Participant(person_id="parent1", role="subject")],
            date=DateValue(value=f"{parent_birth_year:04d}-06-15", precision="exact"),
        )
        child_event = Event(
            id="ev_child",
            type=event_type,
            participants=[Participant(person_id="child1", role="subject")],
            date=DateValue(value=f"{event_year:04d}-06-15", precision="exact"),
        )

        child_events = [child_event]
        parent_events = [parent_birth_event]

        context = CheckContext(
            persons_by_id={"child1": child, "parent1": parent},
            events_by_person={"parent1": parent_events, "child1": child_events},
            parents_of={"child1": ["parent1"]},
            current_year=datetime.date.today().year,
        )
        config = _make_config()

        findings = check_no_event_before_parent_birth(child, child_events, config, context)
        assert len(findings) == 0

