"""Property-based tests for person list filtering logic.

Tests the pure filtering functions without any Qt/GUI dependency.

Property 10: Person List Filtering
Property 11: Place Hierarchy Event Filtering
"""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.ui.person_list_panel import (
    FilterCriteria,
    PersonDisplayInfo,
    build_person_display_list,
    filter_persons,
    get_parish_place_ids,
    get_person_birth_death_years,
    get_person_parish_names,
)


# ---------------------------------------------------------------------------
# Strategies for generating test data
# ---------------------------------------------------------------------------

_SAFE_NAME = st.text(
    alphabet=st.characters(categories=("L",)),
    min_size=1,
    max_size=20,
)


@st.composite
def person_with_known_name(draw: DrawFn) -> Person:
    """Generate a person with a predictable first name entry."""
    person_id = draw(st.integers(min_value=1, max_value=9999).map(lambda n: f"person_{n}"))
    given = draw(_SAFE_NAME)
    surname = draw(_SAFE_NAME)
    name = Name(type="birth", given=given, surname=surname)
    extra_names = draw(st.lists(
        st.builds(
            Name,
            type=st.just("married"),
            given=_SAFE_NAME,
            surname=_SAFE_NAME,
            event_id=st.none(),
        ),
        min_size=0,
        max_size=2,
    ))
    return Person(
        id=person_id,
        sex=draw(st.sampled_from(["M", "F", "X", "U"])),
        names=[name] + extra_names,
    )


@st.composite
def filter_criteria_strategy(draw: DrawFn) -> FilterCriteria:
    """Generate a FilterCriteria with optional fields."""
    text = draw(st.one_of(st.just(""), _SAFE_NAME))
    birth_year = draw(st.one_of(
        st.just(""),
        st.integers(min_value=1000, max_value=2100).map(lambda y: str(y)),
    ))
    death_year = draw(st.one_of(
        st.just(""),
        st.integers(min_value=1000, max_value=2100).map(lambda y: str(y)),
    ))
    parish = draw(st.one_of(st.just(""), _SAFE_NAME))
    return FilterCriteria(
        text=text,
        birth_year=birth_year,
        death_year=death_year,
        parish=parish,
    )


@st.composite
def person_display_info_strategy(draw: DrawFn) -> PersonDisplayInfo:
    """Generate a PersonDisplayInfo with predictable fields."""
    person_id = draw(st.integers(min_value=1, max_value=9999).map(lambda n: f"person_{n}"))
    given = draw(_SAFE_NAME)
    surname = draw(_SAFE_NAME)
    birth_year = draw(st.one_of(
        st.just(""),
        st.integers(min_value=1000, max_value=2100).map(lambda y: str(y)),
    ))
    death_year = draw(st.one_of(
        st.just(""),
        st.integers(min_value=1000, max_value=2100).map(lambda y: str(y)),
    ))
    parish_names = draw(st.frozensets(_SAFE_NAME.map(str.lower), min_size=0, max_size=3))
    return PersonDisplayInfo(
        person_id=person_id,
        given=given,
        surname=surname,
        birth_year=birth_year,
        death_year=death_year,
        parish_names=set(parish_names),
    )


@st.composite
def parish_hierarchy_strategy(draw: DrawFn) -> tuple[list[Place], str]:
    """Generate a place hierarchy with a parish and sub-places.

    Returns:
        Tuple of (places list, parish name).
    """
    parish_name = draw(_SAFE_NAME)
    parish_id = draw(st.integers(min_value=1, max_value=999).map(lambda n: f"place_{n}"))
    parish = Place(id=parish_id, type="parish", name=parish_name)

    # Generate sub-places (churches and cemeteries) under this parish
    sub_places: list[Place] = []
    num_sub = draw(st.integers(min_value=0, max_value=3))
    for i in range(num_sub):
        sub_id = f"place_{1000 + i}"
        sub_type = draw(st.sampled_from(["church", "cemetery"]))
        sub_name = draw(_SAFE_NAME)
        sub_places.append(
            Place(id=sub_id, type=sub_type, name=sub_name, parent_place_id=parish_id)
        )

    # Optionally add unrelated places
    unrelated = draw(st.lists(
        st.builds(
            Place,
            id=st.integers(min_value=2000, max_value=2999).map(lambda n: f"place_{n}"),
            type=st.sampled_from(["county", "country"]),
            name=_SAFE_NAME,
            parent_place_id=st.none(),
        ),
        min_size=0,
        max_size=2,
    ))

    all_places = [parish] + sub_places + unrelated
    return all_places, parish_name


# ---------------------------------------------------------------------------
# Property 10: Person List Filtering
# ---------------------------------------------------------------------------


@given(
    persons=st.lists(person_display_info_strategy(), min_size=0, max_size=10),
    criteria=filter_criteria_strategy(),
)
@settings(max_examples=200)
def test_filter_persons_matches_all_criteria(
    persons: list[PersonDisplayInfo],
    criteria: FilterCriteria,
) -> None:
    """**Validates: Requirements 16.3, 16.4**

    Property 10: For any set of persons and any filter criteria, the filtered
    result SHALL contain exactly those persons whose data matches ALL active
    filter criteria simultaneously.
    """
    result = filter_persons(persons, criteria)
    result_ids = {p.person_id for p in result}

    # Manually compute expected results
    text_lower = criteria.text.strip().lower()
    parish_lower = criteria.parish.strip().lower()
    birth_year_stripped = criteria.birth_year.strip()
    death_year_stripped = criteria.death_year.strip()

    expected_ids: set[str] = set()
    for person in persons:
        # Text filter
        if text_lower:
            full_name = f"{person.given} {person.surname}".lower()
            if text_lower not in full_name:
                continue

        # Birth year filter
        if birth_year_stripped:
            if person.birth_year != birth_year_stripped:
                continue

        # Death year filter
        if death_year_stripped:
            if person.death_year != death_year_stripped:
                continue

        # Parish filter
        if parish_lower:
            if parish_lower not in person.parish_names:
                continue

        expected_ids.add(person.person_id)

    assert result_ids == expected_ids, (
        f"Filter mismatch.\n"
        f"Criteria: {criteria}\n"
        f"Expected IDs: {expected_ids}\n"
        f"Got IDs: {result_ids}"
    )


@given(
    persons=st.lists(person_display_info_strategy(), min_size=0, max_size=10),
)
@settings(max_examples=100)
def test_empty_filter_returns_all(persons: list[PersonDisplayInfo]) -> None:
    """**Validates: Requirements 16.3**

    With no active filters, the result should contain all persons.
    """
    criteria = FilterCriteria()
    result = filter_persons(persons, criteria)
    assert len(result) == len(persons)


# ---------------------------------------------------------------------------
# Property 11: Place Hierarchy Event Filtering
# ---------------------------------------------------------------------------


@given(data=st.data())
@settings(max_examples=200)
def test_parish_filter_includes_sub_place_events(data: st.DataObject) -> None:
    """**Validates: Requirements 10.2**

    Property 11: For any set of events with associated places in a hierarchy,
    filtering events by a parish-level place SHALL return all events whose
    place_id is either the parish itself or any descendant place (church,
    cemetery) of that parish.
    """
    places, parish_name = data.draw(parish_hierarchy_strategy())

    # Get the parish place IDs (parish + sub-places)
    expected_place_ids = get_parish_place_ids(parish_name, places)

    # Verify: the parish itself is included
    parish_places = [p for p in places if p.type == "parish" and p.name.lower() == parish_name.lower()]
    for pp in parish_places:
        assert pp.id in expected_place_ids

    # Verify: all sub-places (church/cemetery with parent = parish) are included
    parish_ids = {p.id for p in parish_places}
    for place in places:
        if place.type in ("church", "cemetery") and place.parent_place_id in parish_ids:
            assert place.id in expected_place_ids

    # Verify: unrelated places are NOT included
    for place in places:
        if place.id not in expected_place_ids:
            # This place should not be a parish with that name or a sub-place of it
            if place.type == "parish":
                assert place.name.lower() != parish_name.lower()
            elif place.type in ("church", "cemetery"):
                assert place.parent_place_id not in parish_ids


@given(data=st.data())
@settings(max_examples=200)
def test_person_parish_filter_through_event_hierarchy(data: st.DataObject) -> None:
    """**Validates: Requirements 10.2**

    Property 11 (integration): When filtering persons by parish, persons
    with events at sub-places (church, cemetery) of that parish are included
    in the results.
    """
    places, parish_name = data.draw(parish_hierarchy_strategy())
    assume(len(places) > 0)

    # Pick a place that belongs to the parish (parish itself or sub-place)
    parish_place_ids = get_parish_place_ids(parish_name, places)
    assume(len(parish_place_ids) > 0)

    target_place_id = data.draw(st.sampled_from(sorted(parish_place_ids)))

    # Create a person and an event at that place
    person = Person(
        id="person_test",
        sex="M",
        names=[Name(type="birth", given="Test", surname="Testsson")],
    )
    event = Event(
        id="event_test",
        type="baptism",
        participants=[Participant(person_id="person_test", role="child")],
        date=DateValue(value="1850", precision="year"),
        place=PlaceRef(place_id=target_place_id),
    )

    # Get parish names for this person
    parish_names = get_person_parish_names(person, [event], places)

    # The person should be associated with the parish
    assert parish_name.lower() in parish_names, (
        f"Person at place '{target_place_id}' should be associated with parish '{parish_name}'\n"
        f"Got parish_names: {parish_names}\n"
        f"Places: {[(p.id, p.type, p.name, p.parent_place_id) for p in places]}"
    )

    # Now test via the full filter_persons path
    display_info = PersonDisplayInfo(
        person_id="person_test",
        given="Test",
        surname="Testsson",
        birth_year="1850",
        death_year="",
        parish_names=parish_names,
    )
    criteria = FilterCriteria(parish=parish_name)
    result = filter_persons([display_info], criteria)
    assert len(result) == 1
    assert result[0].person_id == "person_test"
