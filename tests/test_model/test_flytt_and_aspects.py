"""Unit tests for constant registrations and dataclass defaults.

Verifies the residence and flytt source aspect lists with their Swedish labels,
the ``flytt`` event-type label, the ``Event.from_place`` field shape, and the
default values of :class:`ResidenceFact`, :class:`Endpoint` and
:class:`Observation`.

Covers Requirements 1.1, 4.14, 18.1, 18.2, 18.5.
"""

from __future__ import annotations

from slaktbusken.model.event import Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.services.source_aspects import (
    ASPECT_LABELS,
    ENTITY_SOURCE_ASPECTS,
    EVENT_SOURCE_ASPECTS,
    get_aspects_for_entity_type,
    get_aspects_for_event_type,
)
from slaktbusken.ui.swedish_locale import INDIVIDUAL_EVENT_TYPE_LABELS


# --- Residence source aspects (Requirement 4.14) ---


class TestResidenceSourceAspects:
    """ENTITY_SOURCE_ASPECTS["residence"] contains the specified aspects."""

    def test_residence_aspect_list_is_exact(self) -> None:
        """**Validates: Requirements 4.14**"""
        assert ENTITY_SOURCE_ASPECTS["residence"] == [
            "place",
            "period",
            "household_role",
            "household_members",
        ]

    def test_residence_aspect_labels_are_swedish(self) -> None:
        """**Validates: Requirements 4.14**"""
        expected_labels = {
            "place": "Plats",
            "period": "Period",
            "household_role": "Hushållsroll",
            "household_members": "Hushållsmedlemmar",
        }
        for aspect, label in expected_labels.items():
            assert ASPECT_LABELS[aspect] == label

    def test_get_aspects_for_entity_type_returns_residence_list(self) -> None:
        """**Validates: Requirements 4.14**"""
        assert get_aspects_for_entity_type("residence") == [
            "place",
            "period",
            "household_role",
            "household_members",
        ]

    def test_get_aspects_for_unknown_entity_type_returns_empty(self) -> None:
        """**Validates: Requirements 4.14**"""
        assert get_aspects_for_entity_type("unknown_entity") == []


# --- Flytt source aspects (Requirement 18.5) ---


class TestFlyttSourceAspects:
    """EVENT_SOURCE_ASPECTS["flytt"] contains the specified aspects."""

    def test_flytt_aspect_list_is_exact(self) -> None:
        """**Validates: Requirements 18.5**"""
        assert EVENT_SOURCE_ASPECTS["flytt"] == ["date", "from_place", "to_place"]

    def test_flytt_aspect_labels_are_swedish(self) -> None:
        """**Validates: Requirements 18.5**"""
        expected_labels = {
            "date": "Datum",
            "from_place": "Från",
            "to_place": "Till",
        }
        for aspect, label in expected_labels.items():
            assert ASPECT_LABELS[aspect] == label

    def test_get_aspects_for_event_type_returns_flytt_list(self) -> None:
        """**Validates: Requirements 18.5**"""
        assert get_aspects_for_event_type("flytt") == ["date", "from_place", "to_place"]


# --- Flytt event-type label (Requirement 18.1) ---


class TestFlyttLabel:
    """INDIVIDUAL_EVENT_TYPE_LABELS registers the flytt type as "Flytt"."""

    def test_flytt_label_is_registered(self) -> None:
        """**Validates: Requirements 18.1**"""
        assert INDIVIDUAL_EVENT_TYPE_LABELS["flytt"] == "Flytt"


# --- Event.from_place field shape (Requirement 18.2) ---


class TestEventFromPlace:
    """Event.from_place defaults to None and accepts a PlaceRef."""

    def test_from_place_defaults_to_none(self) -> None:
        """**Validates: Requirements 18.2**"""
        event = Event(
            id="event_1",
            type="flytt",
            participants=[Participant(person_id="person_1", role="primary")],
        )
        assert event.from_place is None

    def test_from_place_accepts_a_place_ref(self) -> None:
        """**Validates: Requirements 18.2**"""
        ref = PlaceRef(
            place_id="place_1",
            source_refs=[SourceRef(source_id="source_1", quality="primary")],
        )
        event = Event(
            id="event_1",
            type="flytt",
            participants=[Participant(person_id="person_1", role="primary")],
            from_place=ref,
        )
        assert event.from_place is not None
        assert event.from_place.place_id == "place_1"
        assert len(event.from_place.source_refs) == 1
        assert event.from_place.source_refs[0].source_id == "source_1"

    def test_from_place_is_independent_of_place(self) -> None:
        """**Validates: Requirements 18.2**"""
        event = Event(
            id="event_1",
            type="flytt",
            participants=[Participant(person_id="person_1", role="primary")],
            from_place=PlaceRef(place_id="place_origin"),
            place=PlaceRef(place_id="place_destination"),
        )
        assert event.from_place is not None and event.place is not None
        assert event.from_place.place_id == "place_origin"
        assert event.place.place_id == "place_destination"


# --- ResidenceFact, Endpoint, Observation defaults (Requirement 1.1) ---


class TestResidenceFactDefaults:
    """ResidenceFact has the expected field defaults per the dataclass."""

    def test_start_and_end_default_to_unknown_endpoints(self) -> None:
        """**Validates: Requirements 1.1**"""
        fact = ResidenceFact(id="r1", person_id="p1", place_id="pl1")
        assert fact.start.earliest is None
        assert fact.start.latest is None
        assert fact.end.earliest is None
        assert fact.end.latest is None

    def test_role_in_household_defaults_to_empty(self) -> None:
        """**Validates: Requirements 1.1**"""
        fact = ResidenceFact(id="r1", person_id="p1", place_id="pl1")
        assert fact.role_in_household == ""

    def test_observations_defaults_to_empty_list(self) -> None:
        """**Validates: Requirements 1.1**"""
        fact = ResidenceFact(id="r1", person_id="p1", place_id="pl1")
        assert fact.observations == []

    def test_notes_defaults_to_empty(self) -> None:
        """**Validates: Requirements 1.1**"""
        fact = ResidenceFact(id="r1", person_id="p1", place_id="pl1")
        assert fact.notes == ""


class TestEndpointDefaults:
    """Endpoint fields default to None or empty as specified."""

    def test_all_fields_default_to_none(self) -> None:
        """**Validates: Requirements 1.1**"""
        ep = Endpoint()
        assert ep.earliest is None
        assert ep.latest is None
        assert ep.precision is None
        assert ep.event_id is None
        assert ep.note is None


class TestObservationDefaults:
    """Observation text fields default to empty strings."""

    def test_observed_from_and_to_default_to_empty(self) -> None:
        """**Validates: Requirements 1.1**"""
        obs = Observation(source_ref=SourceRef(source_id="s1", quality="primary"))
        assert obs.observed_from == ""
        assert obs.observed_to == ""

    def test_page_note_defaults_to_empty(self) -> None:
        """**Validates: Requirements 1.1**"""
        obs = Observation(source_ref=SourceRef(source_id="s1", quality="primary"))
        assert obs.page_note == ""
