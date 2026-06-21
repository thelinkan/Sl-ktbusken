"""Unit tests for name_event_service helper functions."""

from __future__ import annotations

from slaktbusken.model.event import Event, Participant
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.name_event_service import (
    get_events_for_person,
    is_event_id_valid,
    set_name_event_id,
)


def _make_project(*events: Event) -> ProjectData:
    """Create a minimal ProjectData with the given events."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        events=list(events),
    )


def _make_event(event_id: str, participant_ids: list[str]) -> Event:
    """Create an Event with participants from a list of person IDs."""
    return Event(
        id=event_id,
        type="marriage",
        participants=[
            Participant(person_id=pid, role="primary") for pid in participant_ids
        ],
    )


class TestGetEventsForPerson:
    """Tests for get_events_for_person."""

    def test_returns_events_where_person_is_participant(self) -> None:
        event1 = _make_event("evt_1", ["person_1", "person_2"])
        event2 = _make_event("evt_2", ["person_1"])
        event3 = _make_event("evt_3", ["person_3"])
        project = _make_project(event1, event2, event3)

        result = get_events_for_person(project, "person_1")

        assert len(result) == 2
        assert event1 in result
        assert event2 in result

    def test_returns_empty_list_when_person_has_no_events(self) -> None:
        event = _make_event("evt_1", ["person_2"])
        project = _make_project(event)

        result = get_events_for_person(project, "person_1")

        assert result == []

    def test_returns_empty_list_when_no_events_exist(self) -> None:
        project = _make_project()

        result = get_events_for_person(project, "person_1")

        assert result == []

    def test_handles_multiple_participants_in_event(self) -> None:
        event = Event(
            id="evt_1",
            type="marriage",
            participants=[
                Participant(person_id="person_1", role="bride"),
                Participant(person_id="person_2", role="groom"),
                Participant(person_id="person_3", role="witness"),
            ],
        )
        project = _make_project(event)

        # All three should find this event
        assert len(get_events_for_person(project, "person_1")) == 1
        assert len(get_events_for_person(project, "person_2")) == 1
        assert len(get_events_for_person(project, "person_3")) == 1


class TestSetNameEventId:
    """Tests for set_name_event_id."""

    def test_sets_event_id_on_name(self) -> None:
        name = Name(type="married", given="Anna", surname="Svensson")

        set_name_event_id(name, "evt_1")

        assert name.event_id == "evt_1"

    def test_clears_event_id_when_none(self) -> None:
        name = Name(type="married", given="Anna", surname="Svensson", event_id="evt_1")

        set_name_event_id(name, None)

        assert name.event_id is None

    def test_replaces_existing_event_id(self) -> None:
        name = Name(type="married", given="Anna", surname="Svensson", event_id="evt_old")

        set_name_event_id(name, "evt_new")

        assert name.event_id == "evt_new"


class TestIsEventIdValid:
    """Tests for is_event_id_valid."""

    def test_returns_true_when_event_exists(self) -> None:
        event = _make_event("evt_1", ["person_1"])
        project = _make_project(event)

        assert is_event_id_valid(project, "evt_1") is True

    def test_returns_false_when_event_does_not_exist(self) -> None:
        event = _make_event("evt_1", ["person_1"])
        project = _make_project(event)

        assert is_event_id_valid(project, "evt_999") is False

    def test_returns_false_when_no_events_exist(self) -> None:
        project = _make_project()

        assert is_event_id_valid(project, "evt_1") is False
