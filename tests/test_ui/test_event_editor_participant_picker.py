"""Unit tests for EventEditor participant-picker disambiguation and filtering.

Covers the three pieces added in tasks 13.1-13.3 for the participant picker
(Requirement 1B):

1. The pure, Qt-free ``is_plausible_parent`` predicate over the year portions
   of a candidate's birth/death dates and the child's birth year
   (Req 1B.6-1B.9).
2. The ``_get_person_display`` life-years suffix helper, which formats
   "Name (birth-death)" using the EN DASH (U+2013), degrading gracefully when a
   year is missing (Req 1B.1-1B.5).
3. The editor's Parent_Role candidate-list filtering: for placement events with
   a child of known birth year, implausible candidates are excluded while
   unknown-date candidates are kept; non-placement events (and unknown child
   birth year) offer the full person list unfiltered (Req 1B.6, 1B.7, 1B.9,
   1B.10).

The EN DASH character "\u2013" is used literally in expected display strings.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.editors.event_editor import (
    EventEditor,
    is_plausible_parent,
)

# EN DASH (U+2013), the separator used in the life-years suffix.
DASH = "\u2013"


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _person(person_id: str, given: str, surname: str = "") -> Person:
    """Build a person with a single birth name."""
    return Person(
        id=person_id,
        sex="female",
        names=[Name(type="birth", given=given, surname=surname)],
    )


def _life_event(
    event_id: str,
    event_type: str,
    person_id: str,
    year_value: str,
) -> Event:
    """Build a birth/death event for a person with a year-precision date."""
    return Event(
        id=event_id,
        type=event_type,
        participants=[Participant(person_id=person_id, role="huvudperson")],
        date=DateValue(value=year_value, precision="year"),
    )


class TestIsPlausibleParent:
    """The pure plausibility predicate (Req 1B.6-1B.9)."""

    def test_candidate_born_after_child_is_excluded(self) -> None:
        """**Validates: Requirements 1B.6**"""
        assert is_plausible_parent(1860, None, 1850) is False

    def test_candidate_born_same_year_as_child_is_excluded(self) -> None:
        """A parent must be strictly older than the child.

        **Validates: Requirements 1B.6**
        """
        assert is_plausible_parent(1850, None, 1850) is False

    def test_candidate_born_before_child_is_plausible(self) -> None:
        """**Validates: Requirements 1B.6**"""
        assert is_plausible_parent(1820, None, 1850) is True

    def test_candidate_died_before_child_birth_is_excluded(self) -> None:
        """**Validates: Requirements 1B.7**"""
        assert is_plausible_parent(1820, 1840, 1850) is False

    def test_candidate_died_same_year_as_child_birth_is_plausible(self) -> None:
        """Only a death strictly before the child's birth excludes.

        **Validates: Requirements 1B.7**
        """
        assert is_plausible_parent(1820, 1850, 1850) is True

    def test_unknown_child_birth_year_never_filters(self) -> None:
        """No judgement is possible without the child's birth year.

        **Validates: Requirements 1B.9**
        """
        assert is_plausible_parent(1900, 1800, None) is True

    def test_missing_candidate_dates_are_kept(self) -> None:
        """Unknown/partial candidate dates never exclude.

        **Validates: Requirements 1B.8**
        """
        assert is_plausible_parent(None, None, 1850) is True

    def test_candidate_born_before_child_with_unknown_death_is_kept(self) -> None:
        """**Validates: Requirements 1B.8**"""
        assert is_plausible_parent(1820, None, 1850) is True


class TestLifeYearSuffixDisplay:
    """``_get_person_display`` renders the life-years suffix (Req 1B.1-1B.5)."""

    def test_both_years_known(self) -> None:
        """**Validates: Requirements 1B.1**"""
        pd = ProjectData()
        pd.persons.append(_person("p1", "Anna"))
        pd.events.append(_life_event("b1", "birth", "p1", "1914"))
        pd.events.append(_life_event("d1", "death", "p1", "1978"))
        editor = EventEditor(pd)
        assert editor._get_person_display("p1") == f"Anna (1914{DASH}1978)"

    def test_birth_only(self) -> None:
        """**Validates: Requirements 1B.2**"""
        pd = ProjectData()
        pd.persons.append(_person("p1", "Bertil"))
        pd.events.append(_life_event("b1", "birth", "p1", "1914"))
        editor = EventEditor(pd)
        assert editor._get_person_display("p1") == f"Bertil (1914{DASH})"

    def test_death_only(self) -> None:
        """**Validates: Requirements 1B.3**"""
        pd = ProjectData()
        pd.persons.append(_person("p1", "Cecilia"))
        pd.events.append(_life_event("d1", "death", "p1", "1978"))
        editor = EventEditor(pd)
        assert editor._get_person_display("p1") == f"Cecilia ({DASH}1978)"

    def test_neither_known_has_no_parentheses(self) -> None:
        """Neither year known -> bare name, no parentheses or trailing space.

        **Validates: Requirements 1B.4**
        """
        pd = ProjectData()
        pd.persons.append(_person("p1", "David"))
        editor = EventEditor(pd)
        assert editor._get_person_display("p1") == "David"

    def test_full_date_value_yields_first_four_chars_as_year(self) -> None:
        """A full date "1914-03-05" still yields year "1914".

        **Validates: Requirements 1B.5**
        """
        pd = ProjectData()
        pd.persons.append(_person("p1", "Eva"))
        pd.events.append(_life_event("b1", "birth", "p1", "1914-03-05"))
        editor = EventEditor(pd)
        assert editor._get_person_display("p1") == f"Eva (1914{DASH})"


def _filtering_project() -> ProjectData:
    """Build a project: a child (born 1850) and four candidate parents.

    - plausible: born 1820, alive (no death event)
    - too_young: born 1860 (after the child) -> implausible
    - died_early: born 1810, died 1840 (before the child's birth) -> implausible
    - no_dates: no birth/death events at all -> unknown, always kept
    """
    pd = ProjectData()
    pd.persons.append(_person("child", "Child", "Barn"))
    pd.persons.append(_person("plausible", "Plaus", "Parent"))
    pd.persons.append(_person("too_young", "Young", "Parent"))
    pd.persons.append(_person("died_early", "Dead", "Parent"))
    pd.persons.append(_person("no_dates", "Unknown", "Parent"))

    pd.events.append(_life_event("cb", "birth", "child", "1850"))
    pd.events.append(_life_event("pb", "birth", "plausible", "1820"))
    pd.events.append(_life_event("yb", "birth", "too_young", "1860"))
    pd.events.append(_life_event("db", "birth", "died_early", "1810"))
    pd.events.append(_life_event("dd", "death", "died_early", "1840"))
    return pd


def _combo_person_ids(editor: EventEditor) -> list[str]:
    """Collect the non-empty person ids offered in the participant combo."""
    combo = editor._ui.participant_person_combo
    ids: list[str] = []
    for i in range(combo.count()):
        data = combo.itemData(i)
        if data:
            ids.append(data)
    return ids


def _select_type(editor: EventEditor, event_type: str) -> None:
    """Select the given event type in the editor's type combo."""
    index = editor._ui.type_combo.findData(event_type)
    assert index >= 0, f"event type {event_type!r} not registered in combo"
    editor._ui.type_combo.setCurrentIndex(index)


class TestParentCandidateFiltering:
    """The Parent_Role candidate list honours plausibility (Req 1B.6-1B.10)."""

    def test_placement_type_filters_implausible_parents(self) -> None:
        """Placement event with a known-birth child filters the candidate list.

        The plausible parent and the unknown-date parent are offered; the
        too-young parent and the parent who died before the child's birth are
        excluded.

        **Validates: Requirements 1B.6, 1B.7**
        """
        pd = _filtering_project()
        editor = EventEditor(pd, subject_person_id="child")
        _select_type(editor, "foster_home")

        offered = _combo_person_ids(editor)
        assert "plausible" in offered
        assert "too_young" not in offered
        assert "died_early" not in offered

    def test_placement_type_keeps_unknown_date_parent(self) -> None:
        """A candidate with unknown dates is never excluded.

        **Validates: Requirements 1B.8**
        """
        pd = _filtering_project()
        editor = EventEditor(pd, subject_person_id="child")
        _select_type(editor, "foster_home")

        assert "no_dates" in _combo_person_ids(editor)

    def test_non_placement_type_offers_full_list(self) -> None:
        """Switching to a non-placement type reinstates the full person list.

        The previously-excluded people reappear, confirming the filter only
        applies to placement types.

        **Validates: Requirements 1B.10**
        """
        pd = _filtering_project()
        editor = EventEditor(pd, subject_person_id="child")

        _select_type(editor, "foster_home")
        filtered = set(_combo_person_ids(editor))
        assert "too_young" not in filtered
        assert "died_early" not in filtered

        _select_type(editor, "baptism")
        full = set(_combo_person_ids(editor))
        assert "too_young" in full
        assert "died_early" in full
        assert "plausible" in full
        assert "no_dates" in full

    def test_unknown_child_birth_year_disables_filtering(self) -> None:
        """A placement event whose child has no birth year does no filtering.

        With the child's birth year unknown, no plausibility judgement is
        possible, so the full person list is offered even for a placement type.

        **Validates: Requirements 1B.9**
        """
        pd = _filtering_project()
        # Remove the child's birth event so its birth year is unknown.
        pd.events = [e for e in pd.events if e.id != "cb"]

        editor = EventEditor(pd, subject_person_id="child")
        _select_type(editor, "foster_home")

        offered = set(_combo_person_ids(editor))
        assert "too_young" in offered
        assert "died_early" in offered
        assert "plausible" in offered
        assert "no_dates" in offered
