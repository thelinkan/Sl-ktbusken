"""Property-based tests for name_event_service.

Feature: redigera-person-media, Property 6: Event filter returns only events with person as participant
Feature: redigera-person-media, Property 7: Name event_id association round-trip
Validates: Requirements 2.2, 2.4, 2.5
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.event import Event, Participant
from slaktbusken.model.person import Name
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.name_event_service import get_events_for_person, set_name_event_id


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_VALID_NAME_TYPES = ["birth", "married", "adopted", "custom"]
_VALID_EVENT_TYPES = ["marriage", "divorce", "name_change", "death", "birth", "custom"]


@st.composite
def name_strategy(draw: st.DrawFn) -> Name:
    """Generate a Name record with random type, given, and surname."""
    name_type = draw(st.sampled_from(_VALID_NAME_TYPES))
    given_name = draw(st.text(alphabet=st.characters(categories=("L",)), min_size=1, max_size=20))
    surname = draw(st.text(alphabet=st.characters(categories=("L",)), min_size=1, max_size=20))
    return Name(type=name_type, given=given_name, surname=surname)


@st.composite
def event_filter_scenario(draw: st.DrawFn) -> tuple[ProjectData, str]:
    """Generate a scenario with events and a target person_id.

    Returns (project_data, target_person_id) where project_data contains
    events with various participants, some including the target person.
    """
    target_person_id = draw(st.from_regex(r"person_[1-9][0-9]{0,2}", fullmatch=True))

    # Generate other person IDs (guaranteed different from target)
    other_ids = draw(
        st.lists(
            st.from_regex(r"other_[1-9][0-9]{0,2}", fullmatch=True),
            min_size=0,
            max_size=5,
            unique=True,
        )
    )

    # Generate events - each event may or may not include the target person
    num_events = draw(st.integers(min_value=0, max_value=8))
    events: list[Event] = []
    for i in range(num_events):
        includes_target = draw(st.booleans())
        participants: list[Participant] = []

        if includes_target:
            role = draw(st.sampled_from(["primary", "witness", "spouse"]))
            participants.append(Participant(person_id=target_person_id, role=role))

        # Add some other participants
        num_others = draw(st.integers(min_value=0, max_value=min(3, len(other_ids))))
        for j in range(num_others):
            if j < len(other_ids):
                participants.append(
                    Participant(person_id=other_ids[j], role="participant")
                )

        event_type = draw(st.sampled_from(_VALID_EVENT_TYPES))
        events.append(
            Event(
                id=f"evt_{i + 1}",
                type=event_type,
                participants=participants,
            )
        )

    project_data = ProjectData(
        project=ProjectMetadata(title="Property Test"),
        events=events,
    )

    return project_data, target_person_id


# ---------------------------------------------------------------------------
# Property 6: Event filter returns only events with person as participant
# ---------------------------------------------------------------------------


class TestEventFilterProperty:
    """**Validates: Requirements 2.5**"""

    @given(scenario=event_filter_scenario())
    @settings(max_examples=100)
    def test_event_filter_returns_exactly_participant_events(
        self, scenario: tuple[ProjectData, str]
    ) -> None:
        """get_events_for_person returns exactly those events where
        person_id appears in the participants list."""
        project_data, target_person_id = scenario

        result = get_events_for_person(project_data, target_person_id)

        # Compute expected: events where target person is a participant
        expected = [
            event
            for event in project_data.events
            if any(p.person_id == target_person_id for p in event.participants)
        ]

        # Same set of events (by id), same order
        assert len(result) == len(expected)
        assert [e.id for e in result] == [e.id for e in expected]

        # No event in result should be missing the target person
        for event in result:
            participant_ids = {p.person_id for p in event.participants}
            assert target_person_id in participant_ids

        # No event with the target person should be missing from result
        result_ids = {e.id for e in result}
        for event in project_data.events:
            if any(p.person_id == target_person_id for p in event.participants):
                assert event.id in result_ids


# ---------------------------------------------------------------------------
# Property 7: Name event_id association round-trip
# ---------------------------------------------------------------------------


class TestNameEventIdAssociationRoundTrip:
    """**Validates: Requirements 2.2, 2.4**"""

    @given(
        name=name_strategy(),
        event_id=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=100)
    def test_set_and_read_event_id_round_trip(self, name: Name, event_id: str) -> None:
        """Setting event_id on a Name and reading it back returns the same value."""
        set_name_event_id(name, event_id)
        assert name.event_id == event_id

    @given(
        name=name_strategy(),
        event_id=st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=100)
    def test_clear_event_id_returns_none(self, name: Name, event_id: str) -> None:
        """Setting event_id then clearing it results in None."""
        set_name_event_id(name, event_id)
        assert name.event_id == event_id

        set_name_event_id(name, None)
        assert name.event_id is None
