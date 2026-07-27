"""Property-based tests for age check threshold comparisons.

Feature: kontrollera-personer, Property 4: Age check threshold comparison

Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.persistence.settings_io import (
    AgeCheckConfig,
    AgeCheckThreshold,
    LogicCheckConfig,
    PersonCheckConfig,
)
from slaktbusken.services.checks.age_checks import (
    check_max_age,
    check_max_age_at_baptism,
    check_max_age_at_childbirth,
    check_max_age_at_marriage,
    check_max_days_death_to_burial,
    check_max_partner_age_diff,
    check_min_age_at_childbirth,
    check_min_age_at_marriage,
    check_min_days_between_births,
)
from slaktbusken.services.person_check_engine import CheckContext


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

sex_st = st.sampled_from(["M", "F"])

# Threshold values that make sense for testing
threshold_st = st.integers(min_value=1, max_value=150)

# Birth years in a reasonable genealogical range
birth_year_st = st.integers(min_value=1600, max_value=1990)

# Age offset — used to produce ages above or below thresholds
age_offset_st = st.integers(min_value=0, max_value=200)

# Day intervals for birth spacing and death-to-burial
day_interval_st = st.integers(min_value=1, max_value=1000)


def _make_person(person_id: str = "p1", sex: str = "M") -> Person:
    """Create a minimal Person."""
    return Person(id=person_id, sex=sex, names=[Name(type="birth", given="Test", surname="Person")])


def _make_birth_event(person_id: str, year: int, month: int = 6, day: int = 15) -> Event:
    """Create a BIRTH event for a person."""
    return Event(
        id=f"evt-birth-{person_id}",
        type="birth",
        participants=[Participant(person_id=person_id, role="subject")],
        date=DateValue(value=f"{year:04d}-{month:02d}-{day:02d}", precision="exact"),
    )


def _make_death_event(person_id: str, year: int, month: int = 6, day: int = 15) -> Event:
    """Create a DEATH event for a person."""
    return Event(
        id=f"evt-death-{person_id}",
        type="death",
        participants=[Participant(person_id=person_id, role="subject")],
        date=DateValue(value=f"{year:04d}-{month:02d}-{day:02d}", precision="exact"),
    )


def _make_event(event_id: str, event_type: str, person_id: str, year: int, month: int = 6, day: int = 15) -> Event:
    """Create an event of given type for a person."""
    return Event(
        id=event_id,
        type=event_type,
        participants=[Participant(person_id=person_id, role="subject")],
        date=DateValue(value=f"{year:04d}-{month:02d}-{day:02d}", precision="exact"),
    )


def _make_config(
    max_age: AgeCheckThreshold | None = None,
    max_age_at_baptism: AgeCheckThreshold | None = None,
    min_age_at_marriage: AgeCheckThreshold | None = None,
    max_age_at_marriage: AgeCheckThreshold | None = None,
    max_partner_age_diff: int = 50,
    max_partner_age_diff_enabled: bool = True,
    min_age_at_childbirth: AgeCheckThreshold | None = None,
    max_age_at_childbirth: AgeCheckThreshold | None = None,
    min_days_between_births: int = 240,
    min_days_between_births_enabled: bool = True,
    max_days_death_to_burial: AgeCheckThreshold | None = None,
) -> PersonCheckConfig:
    """Create a PersonCheckConfig with specific thresholds."""
    age_config = AgeCheckConfig(
        master_enabled=True,
        max_age=max_age or AgeCheckThreshold(enabled=False),
        max_age_at_baptism=max_age_at_baptism or AgeCheckThreshold(enabled=False),
        min_age_at_marriage=min_age_at_marriage or AgeCheckThreshold(enabled=False),
        max_age_at_marriage=max_age_at_marriage or AgeCheckThreshold(enabled=False),
        max_partner_age_diff=max_partner_age_diff,
        max_partner_age_diff_enabled=max_partner_age_diff_enabled,
        min_age_at_childbirth=min_age_at_childbirth or AgeCheckThreshold(enabled=False),
        max_age_at_childbirth=max_age_at_childbirth or AgeCheckThreshold(enabled=False),
        min_days_between_births=min_days_between_births,
        min_days_between_births_enabled=min_days_between_births_enabled,
        max_days_death_to_burial=max_days_death_to_burial or AgeCheckThreshold(enabled=False),
    )
    return PersonCheckConfig(age_checks=age_config, logic_checks=LogicCheckConfig())


def _make_context(
    events_by_person: dict[str, list[Event]] | None = None,
    events_by_id: dict[str, Event] | None = None,
    children_of: dict[str, list[str]] | None = None,
    families_by_person: dict[str, list[Family]] | None = None,
    persons_by_id: dict[str, Person] | None = None,
    current_year: int = 2024,
) -> CheckContext:
    """Create a minimal CheckContext."""
    ctx = CheckContext()
    ctx.events_by_person = events_by_person or {}
    ctx.events_by_id = events_by_id or {}
    ctx.children_of = children_of or {}
    ctx.families_by_person = families_by_person or {}
    ctx.persons_by_id = persons_by_id or {}
    ctx.current_year = current_year
    return ctx


# ---------------------------------------------------------------------------
# Property 4: Age check threshold comparison
# ---------------------------------------------------------------------------


class TestAgeCheckThresholdProperty:
    """Feature: kontrollera-personer, Property 4: Age check threshold comparison

    For each age check function, a finding is produced if and only if the
    computed value violates the threshold. Tests generate controlled data
    with known ages/intervals and verify the threshold comparison logic.

    **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9**
    """

    # --- Req 6.1: check_max_age ---

    @given(
        sex=sex_st,
        birth_year=birth_year_st,
        age=st.integers(min_value=1, max_value=200),
        limit=st.integers(min_value=1, max_value=200),
    )
    @settings(max_examples=200)
    def test_check_max_age_threshold(self, sex: str, birth_year: int, age: int, limit: int) -> None:
        """Req 6.1: Finding produced iff person's age > threshold."""
        death_year = birth_year + age
        person = _make_person("p1", sex)
        birth_event = _make_birth_event("p1", birth_year)
        death_event = _make_death_event("p1", death_year)
        events = [birth_event, death_event]

        threshold = AgeCheckThreshold(enabled=True, male=limit, female=limit)
        config = _make_config(max_age=threshold)
        context = _make_context(current_year=2024)

        findings = check_max_age(person, events, config, context)

        if age > limit:
            assert len(findings) == 1, (
                f"Expected 1 finding for age={age} > limit={limit}, got {len(findings)}"
            )
        else:
            assert len(findings) == 0, (
                f"Expected 0 findings for age={age} <= limit={limit}, got {len(findings)}"
            )

    # --- Req 6.2: check_max_age_at_baptism ---

    @given(
        sex=sex_st,
        birth_year=birth_year_st,
        age=st.integers(min_value=0, max_value=50),
        limit=st.integers(min_value=0, max_value=50),
    )
    @settings(max_examples=200)
    def test_check_max_age_at_baptism_threshold(self, sex: str, birth_year: int, age: int, limit: int) -> None:
        """Req 6.2: Finding produced iff age at baptism > threshold."""
        baptism_year = birth_year + age
        person = _make_person("p1", sex)
        birth_event = _make_birth_event("p1", birth_year)
        baptism_event = _make_event("evt-baptism-p1", "baptism", "p1", baptism_year)
        events = [birth_event, baptism_event]

        threshold = AgeCheckThreshold(enabled=True, male=limit, female=limit)
        config = _make_config(max_age_at_baptism=threshold)

        findings = check_max_age_at_baptism(person, events, config)

        if age > limit:
            assert len(findings) == 1, (
                f"Expected 1 finding for age={age} > limit={limit}, got {len(findings)}"
            )
        else:
            assert len(findings) == 0, (
                f"Expected 0 findings for age={age} <= limit={limit}, got {len(findings)}"
            )

    # --- Req 6.3: check_min_age_at_marriage ---

    @given(
        sex=sex_st,
        birth_year=birth_year_st,
        age=st.integers(min_value=1, max_value=100),
        limit=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=200)
    def test_check_min_age_at_marriage_threshold(self, sex: str, birth_year: int, age: int, limit: int) -> None:
        """Req 6.3: Finding produced iff age at marriage < threshold."""
        marriage_year = birth_year + age
        person = _make_person("p1", sex)
        birth_event = _make_birth_event("p1", birth_year)
        events = [birth_event]

        marriage_event = Event(
            id="evt-marriage-f1",
            type="marriage",
            participants=[],
            date=DateValue(value=f"{marriage_year:04d}-06-15", precision="exact"),
        )
        family = Family(
            id="f1",
            partners=[FamilyPartner(person_id="p1", role="HUSBAND")],
            children=[],
            event_ids=["evt-marriage-f1"],
        )

        threshold = AgeCheckThreshold(enabled=True, male=limit, female=limit)
        config = _make_config(min_age_at_marriage=threshold)
        context = _make_context(events_by_id={"evt-marriage-f1": marriage_event})

        findings = check_min_age_at_marriage(person, events, [family], config, context)

        if age < limit:
            assert len(findings) == 1, (
                f"Expected 1 finding for age={age} < limit={limit}, got {len(findings)}"
            )
        else:
            assert len(findings) == 0, (
                f"Expected 0 findings for age={age} >= limit={limit}, got {len(findings)}"
            )

    # --- Req 6.4: check_max_age_at_marriage ---

    @given(
        sex=sex_st,
        birth_year=birth_year_st,
        age=st.integers(min_value=1, max_value=150),
        limit=st.integers(min_value=1, max_value=150),
    )
    @settings(max_examples=200)
    def test_check_max_age_at_marriage_threshold(self, sex: str, birth_year: int, age: int, limit: int) -> None:
        """Req 6.4: Finding produced iff age at marriage > threshold."""
        marriage_year = birth_year + age
        person = _make_person("p1", sex)
        birth_event = _make_birth_event("p1", birth_year)
        events = [birth_event]

        marriage_event = Event(
            id="evt-marriage-f1",
            type="marriage",
            participants=[],
            date=DateValue(value=f"{marriage_year:04d}-06-15", precision="exact"),
        )
        family = Family(
            id="f1",
            partners=[FamilyPartner(person_id="p1", role="HUSBAND")],
            children=[],
            event_ids=["evt-marriage-f1"],
        )

        threshold = AgeCheckThreshold(enabled=True, male=limit, female=limit)
        config = _make_config(max_age_at_marriage=threshold)
        context = _make_context(events_by_id={"evt-marriage-f1": marriage_event})

        findings = check_max_age_at_marriage(person, events, [family], config, context)

        if age > limit:
            assert len(findings) == 1, (
                f"Expected 1 finding for age={age} > limit={limit}, got {len(findings)}"
            )
        else:
            assert len(findings) == 0, (
                f"Expected 0 findings for age={age} <= limit={limit}, got {len(findings)}"
            )

    # --- Req 6.5: check_max_partner_age_diff ---

    @given(
        birth_year=birth_year_st,
        diff=st.integers(min_value=0, max_value=100),
        limit=st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=200)
    def test_check_max_partner_age_diff_threshold(self, birth_year: int, diff: int, limit: int) -> None:
        """Req 6.5: Finding produced iff partner age difference > threshold.

        We test from the younger partner's perspective (the check only reports
        on the younger partner).
        """
        # p1 is the younger partner, p2 is older
        person = _make_person("p1", "M")
        partner = _make_person("p2", "F")

        p1_birth_year = birth_year + diff  # younger (born later)
        p2_birth_year = birth_year  # older

        p1_birth = _make_birth_event("p1", p1_birth_year)
        p2_birth = _make_birth_event("p2", p2_birth_year)

        person_events = [p1_birth]

        family = Family(
            id="f1",
            partners=[
                FamilyPartner(person_id="p1", role="HUSBAND"),
                FamilyPartner(person_id="p2", role="WIFE"),
            ],
            children=[],
        )

        config = _make_config(max_partner_age_diff=limit, max_partner_age_diff_enabled=True)
        context = _make_context(
            events_by_person={"p2": [p2_birth]},
        )

        findings = check_max_partner_age_diff(person, person_events, [family], config, context)

        if diff > limit:
            assert len(findings) == 1, (
                f"Expected 1 finding for diff={diff} > limit={limit}, got {len(findings)}"
            )
        else:
            assert len(findings) == 0, (
                f"Expected 0 findings for diff={diff} <= limit={limit}, got {len(findings)}"
            )

    # --- Req 6.6: check_min_age_at_childbirth ---

    @given(
        sex=sex_st,
        birth_year=birth_year_st,
        age_at_child=st.integers(min_value=1, max_value=80),
        limit=st.integers(min_value=1, max_value=80),
    )
    @settings(max_examples=200)
    def test_check_min_age_at_childbirth_threshold(
        self, sex: str, birth_year: int, age_at_child: int, limit: int
    ) -> None:
        """Req 6.6: Finding produced iff parent's age at childbirth < threshold."""
        child_birth_year = birth_year + age_at_child
        person = _make_person("p1", sex)
        parent_birth = _make_birth_event("p1", birth_year)
        events = [parent_birth]

        child_birth = _make_birth_event("child1", child_birth_year)

        threshold = AgeCheckThreshold(enabled=True, male=limit, female=limit)
        config = _make_config(min_age_at_childbirth=threshold)
        context = _make_context(
            children_of={"p1": ["child1"]},
            events_by_person={"child1": [child_birth]},
        )

        findings = check_min_age_at_childbirth(person, events, config, context)

        if age_at_child < limit:
            assert len(findings) == 1, (
                f"Expected 1 finding for age={age_at_child} < limit={limit}, got {len(findings)}"
            )
        else:
            assert len(findings) == 0, (
                f"Expected 0 findings for age={age_at_child} >= limit={limit}, got {len(findings)}"
            )

    # --- Req 6.7: check_max_age_at_childbirth ---

    @given(
        sex=sex_st,
        birth_year=birth_year_st,
        age_at_child=st.integers(min_value=1, max_value=150),
        limit=st.integers(min_value=1, max_value=150),
    )
    @settings(max_examples=200)
    def test_check_max_age_at_childbirth_threshold(
        self, sex: str, birth_year: int, age_at_child: int, limit: int
    ) -> None:
        """Req 6.7: Finding produced iff parent's age at childbirth > threshold."""
        child_birth_year = birth_year + age_at_child
        person = _make_person("p1", sex)
        parent_birth = _make_birth_event("p1", birth_year)
        events = [parent_birth]

        child_birth = _make_birth_event("child1", child_birth_year)

        threshold = AgeCheckThreshold(enabled=True, male=limit, female=limit)
        config = _make_config(max_age_at_childbirth=threshold)
        context = _make_context(
            children_of={"p1": ["child1"]},
            events_by_person={"child1": [child_birth]},
        )

        findings = check_max_age_at_childbirth(person, events, config, context)

        if age_at_child > limit:
            assert len(findings) == 1, (
                f"Expected 1 finding for age={age_at_child} > limit={limit}, got {len(findings)}"
            )
        else:
            assert len(findings) == 0, (
                f"Expected 0 findings for age={age_at_child} <= limit={limit}, got {len(findings)}"
            )

    # --- Req 6.8: check_min_days_between_births ---

    @given(
        base_year=st.integers(min_value=1700, max_value=1950),
        interval_days=st.integers(min_value=1, max_value=800),
        limit=st.integers(min_value=1, max_value=800),
    )
    @settings(max_examples=200)
    def test_check_min_days_between_births_threshold(
        self, base_year: int, interval_days: int, limit: int
    ) -> None:
        """Req 6.8: Finding produced iff days between births < threshold.

        Only applies to females. We use a fixed base date and compute the
        second child's birth date by adding interval_days.
        """
        person = _make_person("p1", "F")
        parent_birth = _make_birth_event("p1", base_year - 30)
        events = [parent_birth]

        # First child born on a fixed date
        child1_birth = Event(
            id="evt-birth-child1",
            type="birth",
            participants=[Participant(person_id="child1", role="subject")],
            date=DateValue(value=f"{base_year:04d}-01-15", precision="exact"),
        )

        # Compute second child's birth date by adding interval_days
        # Use a simple date calculation: start from Jan 15 of base_year
        from datetime import date, timedelta

        start_date = date(base_year, 1, 15)
        end_date = start_date + timedelta(days=interval_days)
        child2_date_str = end_date.strftime("%Y-%m-%d")

        child2_birth = Event(
            id="evt-birth-child2",
            type="birth",
            participants=[Participant(person_id="child2", role="subject")],
            date=DateValue(value=child2_date_str, precision="exact"),
        )

        config = _make_config(min_days_between_births=limit, min_days_between_births_enabled=True)
        context = _make_context(
            children_of={"p1": ["child1", "child2"]},
            events_by_person={
                "child1": [child1_birth],
                "child2": [child2_birth],
            },
        )

        findings = check_min_days_between_births(person, events, config, context)

        if interval_days < limit:
            assert len(findings) == 1, (
                f"Expected 1 finding for interval={interval_days} < limit={limit}, got {len(findings)}"
            )
        else:
            assert len(findings) == 0, (
                f"Expected 0 findings for interval={interval_days} >= limit={limit}, got {len(findings)}"
            )

    # --- Req 6.9: check_max_days_death_to_burial ---

    @given(
        sex=sex_st,
        base_year=st.integers(min_value=1700, max_value=2020),
        interval_days=st.integers(min_value=1, max_value=500),
        limit=st.integers(min_value=1, max_value=500),
    )
    @settings(max_examples=200)
    def test_check_max_days_death_to_burial_threshold(
        self, sex: str, base_year: int, interval_days: int, limit: int
    ) -> None:
        """Req 6.9: Finding produced iff days between death and burial > threshold."""
        from datetime import date, timedelta

        person = _make_person("p1", sex)

        death_date = date(base_year, 6, 15)
        burial_date = death_date + timedelta(days=interval_days)

        death_event = Event(
            id="evt-death-p1",
            type="death",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value=death_date.strftime("%Y-%m-%d"), precision="exact"),
        )
        burial_event = Event(
            id="evt-burial-p1",
            type="burial",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value=burial_date.strftime("%Y-%m-%d"), precision="exact"),
        )
        events = [death_event, burial_event]

        threshold = AgeCheckThreshold(enabled=True, male=limit, female=limit)
        config = _make_config(max_days_death_to_burial=threshold)

        findings = check_max_days_death_to_burial(person, events, config)

        if interval_days > limit:
            assert len(findings) == 1, (
                f"Expected 1 finding for interval={interval_days} > limit={limit}, got {len(findings)}"
            )
        else:
            assert len(findings) == 0, (
                f"Expected 0 findings for interval={interval_days} <= limit={limit}, got {len(findings)}"
            )

