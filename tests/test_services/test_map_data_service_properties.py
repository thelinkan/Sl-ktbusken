"""Property-based tests for MapDataService.

Feature: map-view
- Property 1: One marker per place invariant
- Property 2: All qualifying events are represented
- Property 3: Person filter correctness
- Property 4: Markers only include places with coordinates
- Property 5: Event chronological ordering

Validates: Requirements 2.2, 2.3, 3.1, 5.1, 5.6
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.map_data_service import (
    build_markers_all_events,
    build_markers_for_person,
)


# ---------------------------------------------------------------------------
# Strategies for generating random project data
# ---------------------------------------------------------------------------

EVENT_TYPES = [
    "birth", "death", "marriage", "divorce", "baptism", "burial",
    "immigration", "emigration", "residence", "occupation", "education",
    "name_change", "confirmation", "custom",
]


@st.composite
def project_data_strategy(draw: st.DrawFn) -> ProjectData:
    """Generate random ProjectData with persons, places, and events.

    Generates 2-10 persons, 1-5 places (some with coordinates, some without),
    and 1-15 events linking participants to places.
    """
    # Generate unique person IDs
    num_persons = draw(st.integers(min_value=2, max_value=10))
    person_ids = [f"p{i}" for i in range(num_persons)]

    persons = [
        Person(
            id=pid,
            sex=draw(st.sampled_from(["M", "F", "U"])),
            names=[
                Name(
                    type="birth",
                    given=draw(st.text(
                        alphabet=st.characters(categories=("L",)),
                        min_size=2, max_size=8,
                    )),
                    surname=draw(st.text(
                        alphabet=st.characters(categories=("L",)),
                        min_size=2, max_size=8,
                    )),
                )
            ],
        )
        for pid in person_ids
    ]

    # Generate places — some with coordinates, some without
    num_places = draw(st.integers(min_value=1, max_value=5))
    places: list[Place] = []
    for i in range(num_places):
        has_coords = draw(st.booleans())
        if has_coords:
            lat = draw(st.floats(min_value=-90.0, max_value=90.0, allow_nan=False, allow_infinity=False))
            lng = draw(st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False))
        else:
            lat = None
            lng = None
        places.append(
            Place(
                id=f"place{i}",
                type="city",
                name=f"Place {i}",
                latitude=lat,
                longitude=lng,
            )
        )

    place_ids = [p.id for p in places]

    # Generate events
    num_events = draw(st.integers(min_value=1, max_value=15))
    events: list[Event] = []
    for i in range(num_events):
        # 1-3 participants sampled from person IDs
        num_participants = draw(st.integers(min_value=1, max_value=min(3, num_persons)))
        participant_ids = draw(
            st.lists(
                st.sampled_from(person_ids),
                min_size=num_participants,
                max_size=num_participants,
                unique=True,
            )
        )
        participants = [
            Participant(person_id=pid, role="primary")
            for pid in participant_ids
        ]

        # Optional place reference
        has_place = draw(st.booleans())
        place_ref = None
        if has_place:
            place_id = draw(st.sampled_from(place_ids))
            place_ref = PlaceRef(place_id=place_id)

        # Optional date
        has_date = draw(st.booleans())
        date_value = None
        if has_date:
            year = draw(st.integers(min_value=1600, max_value=2023))
            month = draw(st.integers(min_value=1, max_value=12))
            day = draw(st.integers(min_value=1, max_value=28))
            date_value = DateValue(
                value=f"{year:04d}-{month:02d}-{day:02d}",
                precision="exact",
            )

        event_type = draw(st.sampled_from(EVENT_TYPES))
        custom_name = None
        if event_type == "custom":
            custom_name = "Anpassad händelse"

        events.append(
            Event(
                id=f"evt{i}",
                type=event_type,
                participants=participants,
                date=date_value,
                place=place_ref,
                custom_type_name=custom_name,
            )
        )

    return ProjectData(
        project=ProjectMetadata(title="Property Test"),
        persons=persons,
        places=places,
        events=events,
    )


# ---------------------------------------------------------------------------
# Property 1: One marker per place invariant
# ---------------------------------------------------------------------------

class TestOneMarkerPerPlace:
    """Feature: map-view, Property 1: One marker per place invariant

    For any ProjectData with events linking to places, build_markers_all_events
    and build_markers_for_person SHALL produce a result where no two MapMarker
    objects share the same place_id.

    **Validates: Requirements 2.2, 2.3**
    """

    @given(data=project_data_strategy())
    @settings(max_examples=100, deadline=None)
    def test_all_events_unique_place_ids(self, data: ProjectData) -> None:
        """Property 1: No two markers share the same place_id (all events view).

        Feature: map-view, Property 1: One marker per place invariant
        **Validates: Requirements 2.2, 2.3**
        """
        markers = build_markers_all_events(data)
        place_ids = [m.place_id for m in markers]
        assert len(place_ids) == len(set(place_ids)), (
            f"Duplicate place_ids found in all-events markers: {place_ids}"
        )

    @given(data=project_data_strategy())
    @settings(max_examples=100, deadline=None)
    def test_person_view_unique_place_ids(self, data: ProjectData) -> None:
        """Property 1: No two markers share the same place_id (person view).

        Feature: map-view, Property 1: One marker per place invariant
        **Validates: Requirements 2.2, 2.3**
        """
        if not data.persons:
            return
        # Test with the first person
        person_id = data.persons[0].id
        markers = build_markers_for_person(data, person_id)
        place_ids = [m.place_id for m in markers]
        assert len(place_ids) == len(set(place_ids)), (
            f"Duplicate place_ids found in person markers: {place_ids}"
        )


# ---------------------------------------------------------------------------
# Property 2: All qualifying events are represented
# ---------------------------------------------------------------------------

class TestAllQualifyingEventsRepresented:
    """Feature: map-view, Property 2: All qualifying events are represented

    For any ProjectData with events that have a PlaceRef pointing to a place
    with non-null coordinates, every such event SHALL appear in exactly one
    MapMarker's events list (in the all-events view).

    **Validates: Requirements 2.2, 5.1**
    """

    @given(data=project_data_strategy())
    @settings(max_examples=100, deadline=None)
    def test_all_qualifying_events_in_markers(self, data: ProjectData) -> None:
        """Property 2: Every qualifying event appears in exactly one marker.

        Feature: map-view, Property 2: All qualifying events are represented
        **Validates: Requirements 2.2, 5.1**
        """
        # Determine qualifying events: have a PlaceRef pointing to a place with coordinates
        place_map = {p.id: p for p in data.places}
        qualifying_event_ids = set()
        for event in data.events:
            if event.place is None:
                continue
            place = place_map.get(event.place.place_id)
            if place is None:
                continue
            if place.latitude is not None and place.longitude is not None:
                qualifying_event_ids.add(event.id)

        # Collect all event IDs from markers
        markers = build_markers_all_events(data)
        marker_event_ids: list[str] = []
        for marker in markers:
            for map_event in marker.events:
                marker_event_ids.append(map_event.event_id)

        # Every qualifying event must appear exactly once
        assert set(marker_event_ids) == qualifying_event_ids, (
            f"Event set mismatch.\n"
            f"  Expected: {qualifying_event_ids}\n"
            f"  Got: {set(marker_event_ids)}\n"
            f"  Missing: {qualifying_event_ids - set(marker_event_ids)}\n"
            f"  Extra: {set(marker_event_ids) - qualifying_event_ids}"
        )
        # Each event appears exactly once (no duplicates)
        assert len(marker_event_ids) == len(set(marker_event_ids)), (
            f"Duplicate events found in markers: {marker_event_ids}"
        )


# ---------------------------------------------------------------------------
# Property 3: Person filter correctness
# ---------------------------------------------------------------------------

class TestPersonFilterCorrectness:
    """Feature: map-view, Property 3: Person filter correctness

    For any person_id and ProjectData, every event in the result of
    build_markers_for_person SHALL have at least one participant with
    person_id matching the filter person.

    **Validates: Requirements 3.1, 5.6**
    """

    @given(data=project_data_strategy())
    @settings(max_examples=100, deadline=None)
    def test_all_events_have_target_person(self, data: ProjectData) -> None:
        """Property 3: Every event in person view has the filtered person as participant.

        Feature: map-view, Property 3: Person filter correctness
        **Validates: Requirements 3.1, 5.6**
        """
        if not data.persons:
            return

        # Test with each person
        for person in data.persons:
            markers = build_markers_for_person(data, person.id)
            for marker in markers:
                for map_event in marker.events:
                    participant_ids = [p.person_id for p in map_event.participants]
                    assert person.id in participant_ids, (
                        f"Event '{map_event.event_id}' in person view for '{person.id}' "
                        f"does not have that person as participant. "
                        f"Participants: {participant_ids}"
                    )


# ---------------------------------------------------------------------------
# Property 4: Markers only include places with coordinates
# ---------------------------------------------------------------------------

class TestMarkersOnlyWithCoordinates:
    """Feature: map-view, Property 4: Markers only include places with coordinates

    For any result from build_markers_for_person or build_markers_all_events,
    every MapMarker SHALL have non-null latitude and non-null longitude values.

    **Validates: Requirements 2.2, 5.1**
    """

    @given(data=project_data_strategy())
    @settings(max_examples=100, deadline=None)
    def test_all_events_markers_have_coordinates(self, data: ProjectData) -> None:
        """Property 4: All markers in all-events view have non-null coordinates.

        Feature: map-view, Property 4: Markers only include places with coordinates
        **Validates: Requirements 2.2, 5.1**
        """
        markers = build_markers_all_events(data)
        for marker in markers:
            assert marker.latitude is not None, (
                f"Marker for place '{marker.place_id}' has None latitude"
            )
            assert marker.longitude is not None, (
                f"Marker for place '{marker.place_id}' has None longitude"
            )

    @given(data=project_data_strategy())
    @settings(max_examples=100, deadline=None)
    def test_person_markers_have_coordinates(self, data: ProjectData) -> None:
        """Property 4: All markers in person view have non-null coordinates.

        Feature: map-view, Property 4: Markers only include places with coordinates
        **Validates: Requirements 2.2, 5.1**
        """
        if not data.persons:
            return
        person_id = data.persons[0].id
        markers = build_markers_for_person(data, person_id)
        for marker in markers:
            assert marker.latitude is not None, (
                f"Marker for place '{marker.place_id}' has None latitude"
            )
            assert marker.longitude is not None, (
                f"Marker for place '{marker.place_id}' has None longitude"
            )


# ---------------------------------------------------------------------------
# Property 5: Event chronological ordering
# ---------------------------------------------------------------------------

class TestEventChronologicalOrdering:
    """Feature: map-view, Property 5: Event chronological ordering

    For any MapMarker with multiple events, the events list SHALL be ordered
    such that events with dates come first (sorted chronologically by date value)
    and events without dates come last.

    **Validates: Requirements 5.1, 5.6**
    """

    @given(data=project_data_strategy())
    @settings(max_examples=100, deadline=None)
    def test_all_events_ordering(self, data: ProjectData) -> None:
        """Property 5: Events are ordered dated-first chronologically, undated last.

        Feature: map-view, Property 5: Event chronological ordering
        **Validates: Requirements 5.1, 5.6**
        """
        markers = build_markers_all_events(data)
        for marker in markers:
            self._assert_events_ordered(marker.events, marker.place_id)

    @given(data=project_data_strategy())
    @settings(max_examples=100, deadline=None)
    def test_person_events_ordering(self, data: ProjectData) -> None:
        """Property 5: Events in person view are ordered dated-first, undated last.

        Feature: map-view, Property 5: Event chronological ordering
        **Validates: Requirements 5.1, 5.6**
        """
        if not data.persons:
            return
        person_id = data.persons[0].id
        markers = build_markers_for_person(data, person_id)
        for marker in markers:
            self._assert_events_ordered(marker.events, marker.place_id)

    @staticmethod
    def _assert_events_ordered(events: list, place_id: str) -> None:
        """Check that dated events come first (sorted) and undated come last."""
        if len(events) <= 1:
            return

        dated = [e for e in events if e.date_display is not None]
        undated = [e for e in events if e.date_display is None]

        # All dated events should come before all undated events
        if dated and undated:
            last_dated_idx = max(events.index(e) for e in dated)
            first_undated_idx = min(events.index(e) for e in undated)
            assert last_dated_idx < first_undated_idx, (
                f"Place '{place_id}': Dated events not before undated events. "
                f"Last dated idx={last_dated_idx}, first undated idx={first_undated_idx}"
            )

        # Dated events should be in chronological order
        if len(dated) > 1:
            dates = [e.date_display for e in dated]
            assert dates == sorted(dates), (
                f"Place '{place_id}': Dated events not in chronological order. "
                f"Got: {dates}"
            )
