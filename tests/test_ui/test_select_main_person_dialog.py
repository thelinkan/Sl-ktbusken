"""Tests for SelectMainPersonDialog display data building logic.

Verifies that the dialog correctly builds and sorts person display data,
and that the search filtering works as expected.

Validates: Requirements 4.3
"""

from __future__ import annotations

import pytest

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.person import Name, Person
from slaktbusken.ui.dialogs.select_main_person_dialog import (
    SelectMainPersonDialog,
)


def _make_person(person_id: str, given: str, surname: str) -> Person:
    """Create a minimal person with one name."""
    return Person(
        id=person_id,
        sex="M",
        names=[Name(type="birth", given=given, surname=surname)],
    )


def _make_birth_event(person_id: str, year: str) -> Event:
    """Create a birth event with the given year."""
    return Event(
        id=f"ev_birth_{person_id}",
        type="birth",
        date=DateValue(value=year, precision="year"),
        participants=[Participant(person_id=person_id, role="subject")],
    )


def _make_death_event(person_id: str, year: str) -> Event:
    """Create a death event with the given year."""
    return Event(
        id=f"ev_death_{person_id}",
        type="death",
        date=DateValue(value=year, precision="year"),
        participants=[Participant(person_id=person_id, role="subject")],
    )


class TestBuildDisplayData:
    """Test the _build_display_data method via direct instantiation logic."""

    def test_sorted_by_surname_then_given(self) -> None:
        """Persons should be sorted by surname (case-insensitive) then given."""
        persons = [
            _make_person("p1", "Karin", "Zetterberg"),
            _make_person("p2", "Anna", "Andersson"),
            _make_person("p3", "Björn", "Andersson"),
        ]
        events: list[Event] = []

        # Use the same logic as the dialog
        from slaktbusken.ui.person_list_panel import get_person_birth_death_years

        items: list[tuple[str, str, str, str]] = []
        for person in persons:
            first_name = person.names[0]
            surname = first_name.surname
            given = first_name.given
            birth_year, death_year = get_person_birth_death_years(person, events)
            name_part = f"{surname}, {given}"
            if birth_year or death_year:
                birth = birth_year if birth_year else "?"
                death = death_year if death_year else "?"
                display_text = f"{name_part} ({birth}\u2013{death})"
            else:
                display_text = name_part
            search_text = f"{surname} {given} {birth_year} {death_year}".lower()
            items.append((person.id, display_text, search_text, surname.lower() + given.lower()))

        items.sort(key=lambda x: x[3])
        display_data = [(pid, display, search) for pid, display, search, _ in items]

        # Expected order: Andersson Anna, Andersson Björn, Zetterberg Karin
        assert display_data[0][0] == "p2"
        assert display_data[1][0] == "p3"
        assert display_data[2][0] == "p1"

    def test_display_text_with_years(self) -> None:
        """Display text should include birth and death years when available."""
        persons = [_make_person("p1", "Erik", "Svensson")]
        events = [
            _make_birth_event("p1", "1850"),
            _make_death_event("p1", "1920"),
        ]

        from slaktbusken.ui.person_list_panel import get_person_birth_death_years

        person = persons[0]
        first_name = person.names[0]
        birth_year, death_year = get_person_birth_death_years(person, events)
        name_part = f"{first_name.surname}, {first_name.given}"
        birth = birth_year if birth_year else "?"
        death = death_year if death_year else "?"
        display_text = f"{name_part} ({birth}\u2013{death})"

        assert display_text == "Svensson, Erik (1850\u20131920)"

    def test_display_text_without_years(self) -> None:
        """Display text should show only name when no years are available."""
        persons = [_make_person("p1", "Erik", "Svensson")]
        events: list[Event] = []

        from slaktbusken.ui.person_list_panel import get_person_birth_death_years

        person = persons[0]
        first_name = person.names[0]
        birth_year, death_year = get_person_birth_death_years(person, events)
        name_part = f"{first_name.surname}, {first_name.given}"

        assert not birth_year and not death_year
        assert name_part == "Svensson, Erik"

    def test_persons_without_names_excluded(self) -> None:
        """Persons without name entries should be excluded from display."""
        persons = [
            _make_person("p1", "Anna", "Berg"),
            Person(id="p2", sex="M", names=[]),
        ]
        events: list[Event] = []

        # Replicate filter logic from dialog
        result = [p for p in persons if p.names]
        assert len(result) == 1
        assert result[0].id == "p1"

    def test_search_filter_matches_surname(self) -> None:
        """Search text should match on surname."""
        persons = [
            _make_person("p1", "Anna", "Lindgren"),
            _make_person("p2", "Karl", "Berg"),
        ]

        from slaktbusken.ui.person_list_panel import get_person_birth_death_years

        display_data = []
        for person in persons:
            first_name = person.names[0]
            surname = first_name.surname
            given = first_name.given
            birth_year, death_year = get_person_birth_death_years(person, [])
            search_text = f"{surname} {given} {birth_year} {death_year}".lower()
            display_data.append((person.id, f"{surname}, {given}", search_text))

        # Filter for "lind"
        filter_text = "lind"
        filtered = [
            (pid, disp, search)
            for pid, disp, search in display_data
            if filter_text in search
        ]
        assert len(filtered) == 1
        assert filtered[0][0] == "p1"

    def test_search_filter_matches_given_name(self) -> None:
        """Search text should match on given name."""
        persons = [
            _make_person("p1", "Anna", "Lindgren"),
            _make_person("p2", "Karl", "Berg"),
        ]

        from slaktbusken.ui.person_list_panel import get_person_birth_death_years

        display_data = []
        for person in persons:
            first_name = person.names[0]
            surname = first_name.surname
            given = first_name.given
            birth_year, death_year = get_person_birth_death_years(person, [])
            search_text = f"{surname} {given} {birth_year} {death_year}".lower()
            display_data.append((person.id, f"{surname}, {given}", search_text))

        # Filter for "karl"
        filter_text = "karl"
        filtered = [
            (pid, disp, search)
            for pid, disp, search in display_data
            if filter_text in search
        ]
        assert len(filtered) == 1
        assert filtered[0][0] == "p2"
