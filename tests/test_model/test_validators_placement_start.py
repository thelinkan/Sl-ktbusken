"""Unit tests for placement start-event participant-count validation.

A Placement_Start_Event (``foster_home`` → Fosterhem, ``adoption`` → Adoption)
must name exactly one participant in its child role and one or two participants
in its parent role. Covers Requirements 1.3, 1.4, 1.5, 1.6, 1.7, 1.9 and 13.5.
"""

from __future__ import annotations

from typing import Optional

import pytest

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.validators import (
    _MSG_PLACEMENT_MANY_CHILDREN_ADOPTION,
    _MSG_PLACEMENT_MANY_CHILDREN_FOSTER,
    _MSG_PLACEMENT_MANY_PARENTS_ADOPTION,
    _MSG_PLACEMENT_MANY_PARENTS_FOSTER,
    _MSG_PLACEMENT_NO_CHILD_ADOPTION,
    _MSG_PLACEMENT_NO_CHILD_FOSTER,
    validate_event,
)


# Per-type role strings and expected messages, so each test runs symmetrically
# over the foster and adoptive variants.
FOSTER = {
    "type": "foster_home",
    "child_role": "fosterbarn",
    "parent_role": "fosterförälder",
    "no_child": _MSG_PLACEMENT_NO_CHILD_FOSTER,
    "many_children": _MSG_PLACEMENT_MANY_CHILDREN_FOSTER,
    "many_parents": _MSG_PLACEMENT_MANY_PARENTS_FOSTER,
}
ADOPTION = {
    "type": "adoption",
    "child_role": "adopterad",
    "parent_role": "adoptivförälder",
    "no_child": _MSG_PLACEMENT_NO_CHILD_ADOPTION,
    "many_children": _MSG_PLACEMENT_MANY_CHILDREN_ADOPTION,
    "many_parents": _MSG_PLACEMENT_MANY_PARENTS_ADOPTION,
}

BOTH = [pytest.param(FOSTER, id="foster_home"), pytest.param(ADOPTION, id="adoption")]


def make_placement(
    spec: dict,
    children: int,
    parents: int,
    *,
    date: Optional[DateValue] = None,
    place: Optional[PlaceRef] = None,
    extra: Optional[list[Participant]] = None,
) -> Event:
    """A placement start event with the given number of child/parent participants."""
    participants: list[Participant] = []
    for i in range(children):
        participants.append(Participant(person_id=f"child_{i}", role=spec["child_role"]))
    for i in range(parents):
        participants.append(Participant(person_id=f"parent_{i}", role=spec["parent_role"]))
    if extra:
        participants.extend(extra)
    return Event(
        id="event_1",
        type=spec["type"],
        participants=participants,
        date=date,
        place=place,
    )


class TestChildCount:
    """Requirements 1.3, 1.4, 1.5 — exactly one child-role participant."""

    @pytest.mark.parametrize("spec", BOTH)
    def test_exactly_one_child_is_ok(self, spec: dict) -> None:
        """**Validates: Requirements 1.3**"""
        event = make_placement(spec, children=1, parents=1)
        assert validate_event(event) == []

    @pytest.mark.parametrize("spec", BOTH)
    def test_zero_children_yields_exact_message_once(self, spec: dict) -> None:
        """**Validates: Requirements 1.4**"""
        event = make_placement(spec, children=0, parents=1)
        errors = validate_event(event)
        assert errors.count(spec["no_child"]) == 1

    @pytest.mark.parametrize("spec", BOTH)
    def test_two_children_yields_exact_message_once(self, spec: dict) -> None:
        """**Validates: Requirements 1.5**"""
        event = make_placement(spec, children=2, parents=1)
        errors = validate_event(event)
        assert errors.count(spec["many_children"]) == 1


class TestParentCount:
    """Requirements 1.3, 1.6, 1.9, 13.5 — one or two parents; zero allowed."""

    @pytest.mark.parametrize("spec", BOTH)
    def test_one_parent_is_ok(self, spec: dict) -> None:
        """**Validates: Requirements 1.3**"""
        event = make_placement(spec, children=1, parents=1)
        assert validate_event(event) == []

    @pytest.mark.parametrize("spec", BOTH)
    def test_two_parents_is_ok(self, spec: dict) -> None:
        """**Validates: Requirements 1.3**"""
        event = make_placement(spec, children=1, parents=2)
        assert validate_event(event) == []

    @pytest.mark.parametrize("spec", BOTH)
    def test_three_parents_yields_exact_message_once(self, spec: dict) -> None:
        """**Validates: Requirements 1.6**"""
        event = make_placement(spec, children=1, parents=3)
        errors = validate_event(event)
        assert errors.count(spec["many_parents"]) == 1

    def test_adoption_with_zero_parents_stays_valid(self) -> None:
        """A pre-feature Adoption event with no adoptive parent is still valid.

        **Validates: Requirements 1.9, 13.5**
        """
        event = make_placement(ADOPTION, children=1, parents=0)
        assert validate_event(event) == []

    @pytest.mark.parametrize("spec", BOTH)
    def test_zero_parents_is_not_a_count_error(self, spec: dict) -> None:
        """Zero parents is permitted for both types (Req 1.9/13.5 symmetry).

        **Validates: Requirements 1.9, 13.5**
        """
        event = make_placement(spec, children=1, parents=0)
        assert validate_event(event) == []


class TestOptionalDateAndPlace:
    """Requirement 1.7 — date and place are optional and never cause an error."""

    @pytest.mark.parametrize("spec", BOTH)
    def test_valid_placement_with_date_and_place(self, spec: dict) -> None:
        """**Validates: Requirements 1.7**"""
        event = make_placement(
            spec,
            children=1,
            parents=1,
            date=DateValue(value="1850-06-01", precision="day"),
            place=PlaceRef(place_id="place_1"),
        )
        assert validate_event(event) == []

    @pytest.mark.parametrize("spec", BOTH)
    def test_valid_placement_without_date_or_place(self, spec: dict) -> None:
        """**Validates: Requirements 1.7**"""
        event = make_placement(spec, children=1, parents=1)
        assert validate_event(event) == []


class TestTypicalCombinations:
    """A foster home with one child and one parent is the canonical valid case."""

    def test_foster_home_one_child_one_parent_valid(self) -> None:
        """**Validates: Requirements 1.3**"""
        event = make_placement(FOSTER, children=1, parents=1)
        assert validate_event(event) == []

    @pytest.mark.parametrize("spec", BOTH)
    def test_unrelated_roles_are_ignored_for_counts(self, spec: dict) -> None:
        """Participants in neither configured role don't affect the counts.

        **Validates: Requirements 1.3**
        """
        extra = [Participant(person_id="witness_1", role="witness")]
        event = make_placement(spec, children=1, parents=1, extra=extra)
        assert validate_event(event) == []


class TestErrorsAppearExactlyOnce:
    """Each count error is returned exactly once, never duplicated."""

    @pytest.mark.parametrize("spec", BOTH)
    def test_zero_children_and_too_many_parents_each_once(self, spec: dict) -> None:
        """**Validates: Requirements 1.4, 1.6**"""
        event = make_placement(spec, children=0, parents=3)
        errors = validate_event(event)
        assert errors.count(spec["no_child"]) == 1
        assert errors.count(spec["many_parents"]) == 1
