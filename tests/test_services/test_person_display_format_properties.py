"""Property-based tests for person display format.

Feature: kontrollera-personer, Property 2: Person display format

Validates: Requirements 1.2
"""

from __future__ import annotations

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.person import Name, Person
from slaktbusken.services.person_check_engine import format_person_display


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid years for genealogical data
year_st = st.integers(min_value=1000, max_value=2100)

# Sex values
sex_st = st.sampled_from(["M", "F", "U"])

# Precision qualifiers
precision_st = st.sampled_from(["exact", "about", "before", "after"])

# Simple text for names (non-empty, no newlines/parentheses to keep things sane)
name_text_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "Nd", "Zs"), min_codepoint=65, max_codepoint=122),
    min_size=1,
    max_size=20,
).filter(lambda s: s.strip() != "")


@st.composite
def name_entry(draw: st.DrawFn) -> Name:
    """Generate a Name entry with random given/surname."""
    return Name(
        type="birth",
        given=draw(name_text_st),
        surname=draw(name_text_st),
    )


@st.composite
def date_value_st(draw: st.DrawFn) -> DateValue:
    """Generate a valid DateValue with format YYYY, YYYY-MM, or YYYY-MM-DD."""
    y = draw(year_st)
    fmt = draw(st.sampled_from(["year", "year_month", "full"]))
    if fmt == "year":
        value = f"{y:04d}"
    elif fmt == "year_month":
        m = draw(st.integers(min_value=1, max_value=12))
        value = f"{y:04d}-{m:02d}"
    else:
        m = draw(st.integers(min_value=1, max_value=12))
        d = draw(st.integers(min_value=1, max_value=28))
        value = f"{y:04d}-{m:02d}-{d:02d}"
    return DateValue(value=value, precision=draw(precision_st))


@st.composite
def person_st(draw: st.DrawFn) -> Person:
    """Generate a Person with 0-3 Name entries."""
    person_id = draw(st.text(alphabet="abcdefghijklmnop0123456789", min_size=5, max_size=10))
    sex = draw(sex_st)
    num_names = draw(st.integers(min_value=0, max_value=3))
    names = [draw(name_entry()) for _ in range(num_names)]
    return Person(id=person_id, sex=sex, names=names)


@st.composite
def events_for_person(draw: st.DrawFn, person_id: str) -> list[Event]:
    """Generate a list of events with optional BIRTH and DEATH events for a person."""
    events: list[Event] = []
    has_birth = draw(st.booleans())
    has_death = draw(st.booleans())

    if has_birth:
        birth_date = draw(date_value_st())
        events.append(Event(
            id=draw(st.text(alphabet="abcdef0123456789", min_size=5, max_size=10)),
            type="birth",
            participants=[Participant(person_id=person_id, role="subject")],
            date=birth_date,
        ))

    if has_death:
        death_date = draw(date_value_st())
        events.append(Event(
            id=draw(st.text(alphabet="abcdef0123456789", min_size=5, max_size=10)),
            type="death",
            participants=[Participant(person_id=person_id, role="subject")],
            date=death_date,
        ))

    return events


# Pattern for the output: optional name part, then " (year–year)" where year is \d{4} or ?
_OUTPUT_PATTERN = re.compile(r"^(.*) \((\d{4}|\?)\u2013(\d{4}|\?)\)$")


# ---------------------------------------------------------------------------
# Property 2: Person display format
# ---------------------------------------------------------------------------


class TestPersonDisplayFormatProperty:
    """Feature: kontrollera-personer, Property 2: Person display format

    For any person with zero or more names and zero or more birth/death events,
    format_person_display() SHALL produce a string matching the pattern
    "<given> <surname> (<birth_year>–<death_year>)" where missing years are
    replaced with "?" and the name is taken from the first name entry (or empty
    string if no names).

    **Validates: Requirements 1.2**
    """

    @given(data=st.data())
    @settings(max_examples=200)
    def test_output_always_matches_pattern(self, data: st.DataObject) -> None:
        """Output always matches the expected pattern with parentheses and years/question marks."""
        person = data.draw(person_st())
        events = data.draw(events_for_person(person.id))

        result = format_person_display(person, events)

        # Must match: "<name_part> (<birth>–<death>)" or "(<birth>–<death>)" if no name
        # The name_part can be empty, so we check the tail pattern
        assert "\u2013" in result, f"En-dash missing in: {result!r}"
        assert result.endswith(")"), f"Must end with ')': {result!r}"
        assert "(" in result, f"Must contain '(': {result!r}"

        # Extract the parenthesized part
        paren_start = result.rfind("(")
        paren_content = result[paren_start + 1:-1]
        parts = paren_content.split("\u2013")
        assert len(parts) == 2, f"Expected exactly one en-dash in parens: {result!r}"

        birth_part, death_part = parts
        # Each part must be a 4-digit year or "?"
        assert re.match(r"^(\d{4}|\?)$", birth_part), f"Invalid birth part: {birth_part!r} in {result!r}"
        assert re.match(r"^(\d{4}|\?)$", death_part), f"Invalid death part: {death_part!r} in {result!r}"

    @given(data=st.data())
    @settings(max_examples=200)
    def test_birth_year_correctly_extracted(self, data: st.DataObject) -> None:
        """When a BIRTH event with valid date exists, birth year in output matches event year."""
        person = data.draw(person_st())
        birth_date = data.draw(date_value_st())
        birth_event = Event(
            id="birth-evt-001",
            type="birth",
            participants=[Participant(person_id=person.id, role="subject")],
            date=birth_date,
        )
        events = [birth_event]

        result = format_person_display(person, events)

        # Extract the birth year from the date value
        expected_year = birth_date.value[:4]

        # Extract birth year from the result
        paren_start = result.rfind("(")
        paren_content = result[paren_start + 1:-1]
        birth_part = paren_content.split("\u2013")[0]

        assert birth_part == expected_year, (
            f"Birth year mismatch: expected {expected_year}, got {birth_part} "
            f"for date value {birth_date.value!r}"
        )

    @given(data=st.data())
    @settings(max_examples=200)
    def test_death_year_correctly_extracted(self, data: st.DataObject) -> None:
        """When a DEATH event with valid date exists, death year in output matches event year."""
        person = data.draw(person_st())
        death_date = data.draw(date_value_st())
        death_event = Event(
            id="death-evt-001",
            type="death",
            participants=[Participant(person_id=person.id, role="subject")],
            date=death_date,
        )
        events = [death_event]

        result = format_person_display(person, events)

        # Extract the death year from the date value
        expected_year = death_date.value[:4]

        # Extract death year from the result
        paren_start = result.rfind("(")
        paren_content = result[paren_start + 1:-1]
        death_part = paren_content.split("\u2013")[1]

        assert death_part == expected_year, (
            f"Death year mismatch: expected {expected_year}, got {death_part} "
            f"for date value {death_date.value!r}"
        )

    @given(data=st.data())
    @settings(max_examples=200)
    def test_missing_years_show_question_mark(self, data: st.DataObject) -> None:
        """When no BIRTH or DEATH event exists, the corresponding position shows '?'."""
        person = data.draw(person_st())
        has_birth = data.draw(st.booleans())
        has_death = data.draw(st.booleans())

        events: list[Event] = []
        if has_birth:
            events.append(Event(
                id="birth-evt-001",
                type="birth",
                participants=[Participant(person_id=person.id, role="subject")],
                date=data.draw(date_value_st()),
            ))
        if has_death:
            events.append(Event(
                id="death-evt-001",
                type="death",
                participants=[Participant(person_id=person.id, role="subject")],
                date=data.draw(date_value_st()),
            ))

        result = format_person_display(person, events)

        paren_start = result.rfind("(")
        paren_content = result[paren_start + 1:-1]
        birth_part, death_part = paren_content.split("\u2013")

        if not has_birth:
            assert birth_part == "?", f"Expected '?' for missing birth, got {birth_part!r}"
        if not has_death:
            assert death_part == "?", f"Expected '?' for missing death, got {death_part!r}"

    @given(data=st.data())
    @settings(max_examples=200)
    def test_name_from_first_entry(self, data: st.DataObject) -> None:
        """The name part uses given + surname from person.names[0]. If no names, name part is empty."""
        person = data.draw(person_st())
        events = data.draw(events_for_person(person.id))

        result = format_person_display(person, events)

        # The name part is everything before the last " ("
        paren_start = result.rfind(" (")
        if paren_start == -1:
            # Edge case: output is "(birth–death)" with no leading space
            name_part = ""
        else:
            name_part = result[:paren_start]

        if person.names:
            expected_given = person.names[0].given
            expected_surname = person.names[0].surname
            expected_name = f"{expected_given} {expected_surname}".strip()
            assert name_part == expected_name, (
                f"Name mismatch: expected {expected_name!r}, got {name_part!r}"
            )
        else:
            assert name_part == "", (
                f"Expected empty name part for person with no names, got {name_part!r}"
            )

    @given(data=st.data())
    @settings(max_examples=200)
    def test_en_dash_used(self, data: st.DataObject) -> None:
        """The separator between years must be '\\u2013' (en-dash), not hyphen '-'."""
        person = data.draw(person_st())
        events = data.draw(events_for_person(person.id))

        result = format_person_display(person, events)

        # Extract the parenthesized section
        paren_start = result.rfind("(")
        paren_content = result[paren_start + 1:-1]

        # Must contain en-dash
        assert "\u2013" in paren_content, (
            f"Expected en-dash (\\u2013) in year section, got: {paren_content!r}"
        )
        # Must not use regular hyphen as separator between year parts
        # (Note: hyphen might appear in names, but not in the year section)
        assert "-" not in paren_content, (
            f"Regular hyphen found in year section (should be en-dash): {paren_content!r}"
        )

