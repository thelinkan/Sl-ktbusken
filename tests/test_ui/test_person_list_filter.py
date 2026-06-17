"""Property-based tests for person list filtering logic.

Tests the pure filtering functions without any Qt/GUI dependency.

Property 7: Filter Matches on Clean Name
Property 8: Sort Uses Clean Name
Property 10: Person List Filtering
Property 11: Place Hierarchy Event Filtering
"""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.name_parser import parse_given_name
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
    get_person_cluster_names,
    _year_in_range,
)


# ---------------------------------------------------------------------------
# Strategies for generating test data
# ---------------------------------------------------------------------------

_SAFE_NAME = st.text(
    alphabet=st.characters(categories=("L",)),
    min_size=1,
    max_size=20,
)

_ALL_EVENT_TYPES = [
    "adoption", "baptism", "birth", "blessing", "burial", "census",
    "confirmation", "cremation", "death", "emigration", "first_communion",
    "gender_correction", "graduation", "immigration", "name_change",
    "retirement", "will", "custom_individual_event",
    "divorce", "divorce_filed", "engagement", "marriage", "custom_family_event",
]


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
    title = draw(st.one_of(st.just(""), _SAFE_NAME))
    given = draw(st.one_of(st.just(""), _SAFE_NAME))
    surname = draw(st.one_of(st.just(""), _SAFE_NAME))
    event_types = draw(st.frozensets(
        st.sampled_from(_ALL_EVENT_TYPES), min_size=0, max_size=3
    ))
    birth_year_from = draw(st.one_of(
        st.just(""),
        st.integers(min_value=1000, max_value=2100).map(str),
    ))
    birth_year_to = draw(st.one_of(
        st.just(""),
        st.integers(min_value=1000, max_value=2100).map(str),
    ))
    death_year_from = draw(st.one_of(
        st.just(""),
        st.integers(min_value=1000, max_value=2100).map(str),
    ))
    death_year_to = draw(st.one_of(
        st.just(""),
        st.integers(min_value=1000, max_value=2100).map(str),
    ))
    marriage_year_from = draw(st.one_of(
        st.just(""),
        st.integers(min_value=1000, max_value=2100).map(str),
    ))
    marriage_year_to = draw(st.one_of(
        st.just(""),
        st.integers(min_value=1000, max_value=2100).map(str),
    ))
    parish = draw(st.one_of(st.just(""), _SAFE_NAME))
    cluster = draw(st.one_of(st.just(""), _SAFE_NAME))
    return FilterCriteria(
        title=title,
        given=given,
        surname=surname,
        event_types=set(event_types),
        birth_year_from=birth_year_from,
        birth_year_to=birth_year_to,
        death_year_from=death_year_from,
        death_year_to=death_year_to,
        marriage_year_from=marriage_year_from,
        marriage_year_to=marriage_year_to,
        parish=parish,
        cluster=cluster,
    )


@st.composite
def person_display_info_strategy(draw: DrawFn) -> PersonDisplayInfo:
    """Generate a PersonDisplayInfo with predictable fields."""
    person_id = draw(st.integers(min_value=1, max_value=9999).map(lambda n: f"person_{n}"))
    given = draw(_SAFE_NAME)
    surname = draw(_SAFE_NAME)
    title = draw(st.one_of(st.just(""), _SAFE_NAME))
    birth_year = draw(st.one_of(
        st.just(""),
        st.integers(min_value=1000, max_value=2100).map(str),
    ))
    death_year = draw(st.one_of(
        st.just(""),
        st.integers(min_value=1000, max_value=2100).map(str),
    ))
    marriage_year = draw(st.one_of(
        st.just(""),
        st.integers(min_value=1000, max_value=2100).map(str),
    ))
    event_types = draw(st.frozensets(
        st.sampled_from(_ALL_EVENT_TYPES), min_size=0, max_size=5
    ))
    parish_names = draw(st.frozensets(_SAFE_NAME.map(str.lower), min_size=0, max_size=3))
    cluster_names = draw(st.frozensets(_SAFE_NAME.map(str.lower), min_size=0, max_size=3))
    return PersonDisplayInfo(
        person_id=person_id,
        given=given,
        surname=surname,
        title=title,
        birth_year=birth_year,
        death_year=death_year,
        marriage_year=marriage_year,
        event_types=set(event_types),
        parish_names=set(parish_names),
        cluster_names=set(cluster_names),
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


def _matches_criteria(person: PersonDisplayInfo, criteria: FilterCriteria) -> bool:
    """Reference implementation of filter logic for property test oracle."""
    # Title filter
    title_lower = criteria.title.strip().lower()
    if title_lower and title_lower not in person.title.lower():
        return False

    # Given name filter
    given_lower = criteria.given.strip().lower()
    if given_lower and given_lower not in person.given.lower():
        return False

    # Surname filter
    surname_lower = criteria.surname.strip().lower()
    if surname_lower and surname_lower not in person.surname.lower():
        return False

    # Event types filter
    if criteria.event_types:
        if not criteria.event_types.intersection(person.event_types):
            return False

    # Birth year range
    if not _year_in_range(person.birth_year, criteria.birth_year_from, criteria.birth_year_to):
        return False

    # Death year range
    if not _year_in_range(person.death_year, criteria.death_year_from, criteria.death_year_to):
        return False

    # Marriage year range
    if not _year_in_range(person.marriage_year, criteria.marriage_year_from, criteria.marriage_year_to):
        return False

    # Parish filter
    parish_lower = criteria.parish.strip().lower()
    if parish_lower and parish_lower not in person.parish_names:
        return False

    # Cluster filter
    cluster_lower = criteria.cluster.strip().lower()
    if cluster_lower:
        if not any(cluster_lower in cn for cn in person.cluster_names):
            return False

    return True


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

    expected_ids: set[str] = set()
    for person in persons:
        if _matches_criteria(person, criteria):
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


@given(
    persons=st.lists(person_display_info_strategy(), min_size=1, max_size=10),
    criteria=filter_criteria_strategy(),
)
@settings(max_examples=100)
def test_filter_result_is_subset(
    persons: list[PersonDisplayInfo],
    criteria: FilterCriteria,
) -> None:
    """Filter results should always be a subset of the input."""
    result = filter_persons(persons, criteria)
    result_ids = {p.person_id for p in result}
    input_ids = {p.person_id for p in persons}
    assert result_ids.issubset(input_ids)


@given(
    persons=st.lists(person_display_info_strategy(), min_size=1, max_size=10),
    title_fragment=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz",
        min_size=1,
        max_size=5,
    ),
)
@settings(max_examples=100)
def test_title_filter_is_case_insensitive(
    persons: list[PersonDisplayInfo],
    title_fragment: str,
) -> None:
    """Title filter should be case-insensitive."""
    criteria_lower = FilterCriteria(title=title_fragment.lower())
    criteria_upper = FilterCriteria(title=title_fragment.upper())

    result_lower = filter_persons(persons, criteria_lower)
    result_upper = filter_persons(persons, criteria_upper)

    assert {p.person_id for p in result_lower} == {p.person_id for p in result_upper}


@given(
    persons=st.lists(person_display_info_strategy(), min_size=1, max_size=10),
    event_type=st.sampled_from(_ALL_EVENT_TYPES),
)
@settings(max_examples=100)
def test_event_type_filter(
    persons: list[PersonDisplayInfo],
    event_type: str,
) -> None:
    """Event type filter should only return persons with at least one matching event."""
    criteria = FilterCriteria(event_types={event_type})
    result = filter_persons(persons, criteria)

    for person in result:
        assert event_type in person.event_types


# ---------------------------------------------------------------------------
# Year range filter tests
# ---------------------------------------------------------------------------


@given(
    year=st.one_of(
        st.just(""),
        st.integers(min_value=1000, max_value=2100).map(str),
    ),
    from_year=st.one_of(
        st.just(""),
        st.integers(min_value=1000, max_value=2100).map(str),
    ),
    to_year=st.one_of(
        st.just(""),
        st.integers(min_value=1000, max_value=2100).map(str),
    ),
)
@settings(max_examples=200)
def test_year_in_range_consistency(year: str, from_year: str, to_year: str) -> None:
    """_year_in_range should be consistent with integer comparison."""
    result = _year_in_range(year, from_year, to_year)

    # No range constraints -> always true
    if not from_year.strip() and not to_year.strip():
        assert result is True
        return

    # Empty year with range -> false
    if not year:
        assert result is False
        return

    # Valid year with range
    try:
        y = int(year)
    except ValueError:
        return  # skip non-integer years

    expected = True
    if from_year.strip():
        try:
            if y < int(from_year.strip()):
                expected = False
        except ValueError:
            pass
    if to_year.strip():
        try:
            if y > int(to_year.strip()):
                expected = False
        except ValueError:
            pass

    assert result == expected


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
        title="",
        birth_year="1850",
        death_year="",
        marriage_year="",
        event_types={"baptism"},
        parish_names=parish_names,
        cluster_names=set(),
    )
    criteria = FilterCriteria(parish=parish_name)
    result = filter_persons([display_info], criteria)
    assert len(result) == 1
    assert result[0].person_id == "person_test"


# ---------------------------------------------------------------------------
# Example-based unit tests for Person List Panel rendering and filtering
# (Task 4.5)
# ---------------------------------------------------------------------------

import pytest

from slaktbusken.model.name_parser import parse_given_name
from slaktbusken.model.person import Name, Person


class TestFilterFindsByTilltalsnamn:
    """Test that filter matches on clean given name parts (Requirements 4.1, 4.2)."""

    def test_filter_finds_person_by_tilltalsnamn(self) -> None:
        """Searching for 'Torbjörn' finds person with given='Kent Torbjörn' (from 'Kent Torbjörn*').

        **Validates: Requirements 4.1, 4.2**
        """
        person = PersonDisplayInfo(
            person_id="p1",
            given="Kent Torbjörn",
            surname="Andersson",
            title="",
            birth_year="1950",
            death_year="",
            marriage_year="",
            event_types=set(),
            parish_names=set(),
            cluster_names=set(),
            tilltalsnamn_index=1,
        )
        criteria = FilterCriteria(given="Torbjörn")
        result = filter_persons([person], criteria)
        assert len(result) == 1
        assert result[0].person_id == "p1"

    def test_filter_finds_person_by_non_tilltalsnamn(self) -> None:
        """Searching for 'Kent' finds person with given='Kent Torbjörn' (from 'Kent Torbjörn*').

        **Validates: Requirements 4.1, 4.3**
        """
        person = PersonDisplayInfo(
            person_id="p1",
            given="Kent Torbjörn",
            surname="Andersson",
            title="",
            birth_year="1950",
            death_year="",
            marriage_year="",
            event_types=set(),
            parish_names=set(),
            cluster_names=set(),
            tilltalsnamn_index=1,
        )
        criteria = FilterCriteria(given="Kent")
        result = filter_persons([person], criteria)
        assert len(result) == 1
        assert result[0].person_id == "p1"


class TestFilterLiteralAsterisk:
    """Test that literal asterisk in search term is treated as literal (Requirement 4.5)."""

    def test_filter_literal_asterisk_in_search_term(self) -> None:
        """Searching for '*' does not match clean given name 'Kent Torbjörn'.

        **Validates: Requirements 4.5**
        """
        person = PersonDisplayInfo(
            person_id="p1",
            given="Kent Torbjörn",
            surname="Andersson",
            title="",
            birth_year="",
            death_year="",
            marriage_year="",
            event_types=set(),
            parish_names=set(),
            cluster_names=set(),
            tilltalsnamn_index=1,
        )
        criteria = FilterCriteria(given="*")
        result = filter_persons([person], criteria)
        assert len(result) == 0

    def test_filter_literal_asterisk_does_not_match_clean_name(self) -> None:
        """Searching for 'Torbjörn*' does not match clean name 'Kent Torbjörn'.

        The stored given name has no asterisk, so literal '*' in search won't match.

        **Validates: Requirements 4.5**
        """
        person = PersonDisplayInfo(
            person_id="p1",
            given="Kent Torbjörn",
            surname="Andersson",
            title="",
            birth_year="",
            death_year="",
            marriage_year="",
            event_types=set(),
            parish_names=set(),
            cluster_names=set(),
            tilltalsnamn_index=1,
        )
        criteria = FilterCriteria(given="Torbjörn*")
        result = filter_persons([person], criteria)
        assert len(result) == 0


class TestSortUsesCleanName:
    """Test that sort uses clean name ignoring asterisk (Requirement 4.4)."""

    def test_sort_uses_clean_name_ignoring_asterisk(self) -> None:
        """build_person_display_list sorts by surname then clean given name.

        Person with 'Kent Torbjörn*' should sort by 'Kent Torbjörn' (asterisk removed).

        **Validates: Requirements 4.4**
        """
        person1 = Person(
            id="p1",
            sex="M",
            names=[Name(type="birth", given="Kent Torbjörn*", surname="Andersson")],
        )
        person2 = Person(
            id="p2",
            sex="F",
            names=[Name(type="birth", given="Anna", surname="Andersson")],
        )
        result = build_person_display_list(
            persons=[person1, person2],
            events=[],
            places=[],
        )
        # Both have surname "Andersson", so sort by given name:
        # "Anna" < "Kent Torbjörn" alphabetically
        assert result[0].person_id == "p2"  # Anna comes first
        assert result[1].person_id == "p1"  # Kent Torbjörn comes second
        # Verify the clean name is stored (no asterisk)
        assert result[1].given == "Kent Torbjörn"
        assert result[1].tilltalsnamn_index == 1


class TestHtmlRenderingWithTilltalsnamn:
    """Test HTML rendering of tilltalsnamn in Person List Panel (Requirements 3.1, 3.2, 3.3, 3.4)."""

    def test_html_rendering_with_tilltalsnamn(self) -> None:
        """_format_person_html wraps the tilltalsnamn in <u> tags.

        **Validates: Requirements 3.1, 3.4**
        """
        from slaktbusken.ui.person_list_panel import PersonListPanel

        info = PersonDisplayInfo(
            person_id="p1",
            given="Kent Torbjörn",
            surname="Andersson",
            title="",
            birth_year="1950",
            death_year="2020",
            marriage_year="",
            event_types=set(),
            parish_names=set(),
            cluster_names=set(),
            tilltalsnamn_index=1,
        )
        # Call the static-like method directly (it only uses 'info', not 'self' state)
        html = PersonListPanel._format_person_html(None, info)  # type: ignore[arg-type]
        assert "<u>Torbjörn</u>" in html
        assert "Kent" in html
        assert "*" not in html

    def test_html_rendering_without_tilltalsnamn(self) -> None:
        """_format_person_html renders without underline when no tilltalsnamn.

        **Validates: Requirements 3.2**
        """
        from slaktbusken.ui.person_list_panel import PersonListPanel

        info = PersonDisplayInfo(
            person_id="p2",
            given="Erik Johan",
            surname="Svensson",
            title="",
            birth_year="1900",
            death_year="1980",
            marriage_year="",
            event_types=set(),
            parish_names=set(),
            cluster_names=set(),
            tilltalsnamn_index=None,
        )
        html = PersonListPanel._format_person_html(None, info)  # type: ignore[arg-type]
        assert "<u>" not in html
        assert "Erik Johan" in html
        assert "*" not in html


# ---------------------------------------------------------------------------
# Strategies for Property 7 and 8 (tilltalsnamn asterisk handling)
# ---------------------------------------------------------------------------

# Swedish-style name part characters (letters including Swedish chars)
_SWEDISH_NAME_CHAR = st.sampled_from(
    "abcdefghijklmnopqrstuvwxyzåäöABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ"
)

_SWEDISH_NAME_PART = st.text(
    alphabet=_SWEDISH_NAME_CHAR,
    min_size=1,
    max_size=10,
)


@st.composite
def given_name_with_optional_marker(draw: DrawFn) -> tuple[str, str]:
    """Generate a given-name string optionally containing one asterisk marker.

    Returns:
        Tuple of (raw_given_name, clean_given_name).
        raw_given_name may contain a trailing '*' on one part.
        clean_given_name has the marker removed.
    """
    num_parts = draw(st.integers(min_value=1, max_value=4))
    parts = [draw(_SWEDISH_NAME_PART) for _ in range(num_parts)]
    has_marker = draw(st.booleans())

    clean_name = " ".join(parts)

    if has_marker:
        marker_index = draw(st.integers(min_value=0, max_value=num_parts - 1))
        raw_parts = list(parts)
        raw_parts[marker_index] = raw_parts[marker_index] + "*"
        raw_name = " ".join(raw_parts)
    else:
        raw_name = clean_name

    return raw_name, clean_name


@st.composite
def person_display_info_with_tilltalsnamn_strategy(draw: DrawFn) -> PersonDisplayInfo:
    """Generate a PersonDisplayInfo with clean given name and optional tilltalsnamn_index."""
    person_id = draw(st.integers(min_value=1, max_value=9999).map(lambda n: f"person_{n}"))
    raw_given, clean_given = draw(given_name_with_optional_marker())

    # Parse the raw name to get the tilltalsnamn_index
    parsed = parse_given_name(raw_given)

    surname = draw(_SWEDISH_NAME_PART)
    return PersonDisplayInfo(
        person_id=person_id,
        given=clean_given,
        surname=surname,
        title="",
        birth_year="",
        death_year="",
        marriage_year="",
        event_types=set(),
        parish_names=set(),
        cluster_names=set(),
        tilltalsnamn_index=parsed.tilltalsnamn_index,
    )


# ---------------------------------------------------------------------------
# Property 7: Filter Matches on Clean Name
# Feature: primary-name-asterisk, Property 7: Filter Matches on Clean Name
# ---------------------------------------------------------------------------


@given(
    person_data=given_name_with_optional_marker(),
    search_substring=st.text(
        alphabet=_SWEDISH_NAME_CHAR,
        min_size=1,
        max_size=8,
    ),
)
@settings(max_examples=200)
def test_filter_matches_on_clean_name(
    person_data: tuple[str, str],
    search_substring: str,
) -> None:
    """**Validates: Requirements 4.1**

    Property 7: For any person with a given-name string containing an asterisk
    marker and for any search substring, filtering SHALL produce the same result
    as filtering against the clean name (asterisk removed), using case-insensitive
    substring matching.
    """
    raw_given, clean_given = person_data
    parsed = parse_given_name(raw_given)

    # Build a PersonDisplayInfo with the clean given name (as build_person_display_list does)
    person = PersonDisplayInfo(
        person_id="person_1",
        given=parsed.display_string,
        surname="Testsson",
        title="",
        birth_year="",
        death_year="",
        marriage_year="",
        event_types=set(),
        parish_names=set(),
        cluster_names=set(),
        tilltalsnamn_index=parsed.tilltalsnamn_index,
    )

    # Filter using the search substring
    criteria = FilterCriteria(given=search_substring)
    result = filter_persons([person], criteria)

    # Expected: match against the clean name (asterisk removed)
    expected_match = search_substring.lower() in clean_given.lower()

    if expected_match:
        assert len(result) == 1, (
            f"Expected person to match filter '{search_substring}' "
            f"against clean name '{clean_given}', but got no results."
        )
    else:
        assert len(result) == 0, (
            f"Expected person NOT to match filter '{search_substring}' "
            f"against clean name '{clean_given}', but got a match."
        )


# ---------------------------------------------------------------------------
# Property 8: Sort Uses Clean Name
# Feature: primary-name-asterisk, Property 8: Sort Uses Clean Name
# ---------------------------------------------------------------------------


@given(
    persons_data=st.lists(
        st.tuples(_SWEDISH_NAME_PART, given_name_with_optional_marker()),
        min_size=1,
        max_size=8,
    ),
)
@settings(max_examples=200)
def test_sort_uses_clean_name(
    persons_data: list[tuple[str, tuple[str, str]]],
) -> None:
    """**Validates: Requirements 4.4**

    Property 8: For any list of persons where some have asterisk markers in
    their given names, sorting alphabetically SHALL produce the same ordering
    as sorting by the clean given name (asterisk removed).
    """
    # Build Person objects with raw given names (some with asterisk markers)
    persons: list[Person] = []
    for i, (surname, (raw_given, _clean_given)) in enumerate(persons_data):
        person = Person(
            id=f"person_{i}",
            sex="U",
            names=[Name(type="birth", given=raw_given, surname=surname)],
        )
        persons.append(person)

    # Build the display list (which sorts by clean name)
    display_list = build_person_display_list(
        persons=persons,
        events=[],
        places=[],
        families=[],
        dna_clusters=[],
    )

    # Verify the output is sorted by (surname.lower(), given.lower())
    # where given is the clean name (asterisk removed)
    for i in range(len(display_list) - 1):
        curr = display_list[i]
        nxt = display_list[i + 1]
        curr_key = (curr.surname.lower(), curr.given.lower())
        nxt_key = (nxt.surname.lower(), nxt.given.lower())
        assert curr_key <= nxt_key, (
            f"Sort order violated: {curr_key} should come before {nxt_key}\n"
            f"Person {i}: surname='{curr.surname}', given='{curr.given}'\n"
            f"Person {i+1}: surname='{nxt.surname}', given='{nxt.given}'"
        )
