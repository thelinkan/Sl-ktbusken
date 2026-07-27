"""Property-based tests for person check engine results grouping.

Feature: kontrollera-personer, Property 3: Results grouped per person

Validates: Requirements 3.7
"""

from __future__ import annotations

from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.family import Family
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.settings_io import PersonCheckConfig
from slaktbusken.services.person_check_engine import (
    CheckFinding,
    PersonCheckEngine,
    format_person_display,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

sex_st = st.sampled_from(["M", "F", "U"])

given_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("L",)), min_size=2, max_size=10
)

surname_st = st.text(
    alphabet=st.characters(whitelist_categories=("L",)), min_size=2, max_size=12
)


@st.composite
def person_st(draw: st.DrawFn, person_id: str | None = None) -> Person:
    """Generate a Person with a random name and sex."""
    pid = person_id if person_id else draw(
        st.text(alphabet="abcdefghijklmnop0123456789", min_size=5, max_size=10)
    )
    sex = draw(sex_st)
    given = draw(given_name_st)
    surname = draw(surname_st)
    return Person(id=pid, sex=sex, names=[Name(type="birth", given=given, surname=surname)])


@st.composite
def project_with_persons(draw: st.DrawFn) -> ProjectData:
    """Generate a ProjectData with 2-10 distinct persons and BIRTH events."""
    num_persons = draw(st.integers(min_value=2, max_value=10))

    # Generate unique person IDs
    person_ids = [f"p{i}" for i in range(num_persons)]

    persons: list[Person] = []
    events: list[Event] = []

    for pid in person_ids:
        sex = draw(sex_st)
        given = draw(given_name_st)
        surname = draw(surname_st)
        person = Person(id=pid, sex=sex, names=[Name(type="birth", given=given, surname=surname)])
        persons.append(person)

        # Give each person a BIRTH event with a year
        year = draw(st.integers(min_value=1700, max_value=2000))
        birth_event = Event(
            id=f"ev_birth_{pid}",
            type="birth",
            participants=[Participant(person_id=pid, role="subject")],
            date=DateValue(value=str(year), precision="exact"),
        )
        events.append(birth_event)

    return ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=persons,
        events=events,
        families=[],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def is_grouped_by_person(findings: list[CheckFinding]) -> bool:
    """Check that all findings for same person_id are contiguous."""
    seen: set[str] = set()
    last_person_id: str | None = None
    for f in findings:
        if f.person_id != last_person_id:
            if f.person_id in seen:
                return False  # This person appeared before but not contiguously
            seen.add(f.person_id)
            last_person_id = f.person_id
    return True


def fake_age_checks(
    self: PersonCheckEngine,
    person: Person,
    events: list[Event],
    families: list[Family],
    person_display: str,
) -> list[CheckFinding]:
    """Produce at least one finding per person to test grouping."""
    return [
        CheckFinding(
            person_id=person.id,
            person_display=person_display,
            person_sex=person.sex,
            message="test age finding 1",
        ),
        CheckFinding(
            person_id=person.id,
            person_display=person_display,
            person_sex=person.sex,
            message="test age finding 2",
        ),
    ]


def fake_chronology_checks(
    self: PersonCheckEngine,
    person: Person,
    events: list[Event],
    families: list[Family],
    person_display: str,
) -> list[CheckFinding]:
    """Produce a finding per person from chronology checks."""
    return [
        CheckFinding(
            person_id=person.id,
            person_display=person_display,
            person_sex=person.sex,
            message="test chronology finding",
        ),
    ]


def fake_no_findings(
    self: PersonCheckEngine,
    person: Person,
    events: list[Event],
    families: list[Family],
    person_display: str,
) -> list[CheckFinding]:
    """Return no findings."""
    return []


# ---------------------------------------------------------------------------
# Property 3: Results grouped per person
# ---------------------------------------------------------------------------


class TestResultsGroupingProperty:
    """Feature: kontrollera-personer, Property 3: Results grouped per person

    For any list of CheckFinding results produced by PersonCheckEngine,
    all findings for the same person_id SHALL appear as a contiguous group
    in the output list.

    **Validates: Requirements 3.7**
    """

    @given(data=project_with_persons())
    @settings(max_examples=200)
    def test_findings_are_contiguous_per_person(self, data: ProjectData) -> None:
        """All findings for the same person_id are contiguous in the output."""
        config = PersonCheckConfig()

        with (
            patch.object(PersonCheckEngine, "_run_age_checks", fake_age_checks),
            patch.object(PersonCheckEngine, "_run_chronology_checks", fake_chronology_checks),
            patch.object(PersonCheckEngine, "_run_structure_checks", fake_no_findings),
            patch.object(PersonCheckEngine, "_run_calendar_checks", fake_no_findings),
        ):
            engine = PersonCheckEngine(data=data, config=config)
            findings = engine.run_checks()

        # Must have findings (each person produces 3 findings)
        assert len(findings) > 0
        assert is_grouped_by_person(findings)

    @given(data=project_with_persons())
    @settings(max_examples=200)
    def test_findings_within_person_maintain_relative_order(self, data: ProjectData) -> None:
        """Findings for the same person maintain the order produced by sequential check calls."""
        config = PersonCheckConfig()

        with (
            patch.object(PersonCheckEngine, "_run_age_checks", fake_age_checks),
            patch.object(PersonCheckEngine, "_run_chronology_checks", fake_chronology_checks),
            patch.object(PersonCheckEngine, "_run_structure_checks", fake_no_findings),
            patch.object(PersonCheckEngine, "_run_calendar_checks", fake_no_findings),
        ):
            engine = PersonCheckEngine(data=data, config=config)
            findings = engine.run_checks()

        # Group findings by person_id preserving order
        from itertools import groupby

        for person_id, group in groupby(findings, key=lambda f: f.person_id):
            messages = [f.message for f in group]
            # Age check findings come first (2 items), then chronology (1 item)
            assert messages == [
                "test age finding 1",
                "test age finding 2",
                "test chronology finding",
            ]

    @given(data=project_with_persons())
    @settings(max_examples=200)
    def test_all_persons_with_findings_appear_in_output(self, data: ProjectData) -> None:
        """Every person that produces findings appears in the output exactly once as a group."""
        config = PersonCheckConfig()

        with (
            patch.object(PersonCheckEngine, "_run_age_checks", fake_age_checks),
            patch.object(PersonCheckEngine, "_run_chronology_checks", fake_no_findings),
            patch.object(PersonCheckEngine, "_run_structure_checks", fake_no_findings),
            patch.object(PersonCheckEngine, "_run_calendar_checks", fake_no_findings),
        ):
            engine = PersonCheckEngine(data=data, config=config)
            findings = engine.run_checks()

        # Each person should have exactly 2 findings (from fake_age_checks)
        person_ids_in_findings = [f.person_id for f in findings]
        expected_person_ids = [p.id for p in data.persons]

        # All persons should be represented
        assert set(person_ids_in_findings) == set(expected_person_ids)

        # Each person_id should appear exactly twice
        for pid in expected_person_ids:
            assert person_ids_in_findings.count(pid) == 2

