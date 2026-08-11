"""Unit tests for the Flytt event: its two places never error, and the
same-place case is a warning-level finding.

Covers Requirements 18.1, 18.2, 18.3 and 18.7.
"""

from __future__ import annotations

from typing import Optional

from slaktbusken.model.event import Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.validators import event_findings, validate_event
from slaktbusken.ui.swedish_locale import EVENT_TYPE_LABELS, INDIVIDUAL_EVENT_TYPE_LABELS


SAME_PLACE_MESSAGE = "Flytten har samma plats som både från och till – kontrollera uppgifterna."


def make_flytt(
    from_place: Optional[PlaceRef] = None,
    place: Optional[PlaceRef] = None,
    event_type: str = "flytt",
) -> Event:
    """A Flytt_Event with the given origin and destination."""
    return Event(
        id="event_1",
        type=event_type,
        participants=[Participant(person_id="person_1", role="primary")],
        place=place,
        from_place=from_place,
    )


class TestFlyttPlacesNeverError:
    """Requirement 18.3 — an unknown origin or destination is not an error."""

    def test_absent_from_place_is_error_free(self) -> None:
        """**Validates: Requirements 18.3**"""
        event = make_flytt(place=PlaceRef(place_id="place_2"))
        assert validate_event(event) == []

    def test_absent_place_is_error_free(self) -> None:
        """**Validates: Requirements 18.3**"""
        event = make_flytt(from_place=PlaceRef(place_id="place_1"))
        assert validate_event(event) == []

    def test_both_places_absent_is_error_free(self) -> None:
        """**Validates: Requirements 18.3**"""
        assert validate_event(make_flytt()) == []

    def test_same_place_on_both_sides_is_error_free(self) -> None:
        """**Validates: Requirements 18.3, 18.7**"""
        event = make_flytt(
            from_place=PlaceRef(place_id="place_1"),
            place=PlaceRef(place_id="place_1"),
        )
        assert validate_event(event) == []


class TestFlyttSamePlaceFinding:
    """Requirement 18.7 — the same place on both sides warns."""

    def test_same_place_yields_the_required_warning(self) -> None:
        """**Validates: Requirements 18.7**"""
        event = make_flytt(
            from_place=PlaceRef(place_id="place_1"),
            place=PlaceRef(place_id="place_1"),
        )

        findings = event_findings(event)

        assert len(findings) == 1
        assert findings[0].event_id == "event_1"
        assert findings[0].severity == "warning"
        assert findings[0].message == SAME_PLACE_MESSAGE

    def test_different_places_yield_no_finding(self) -> None:
        """**Validates: Requirements 18.7**"""
        event = make_flytt(
            from_place=PlaceRef(place_id="place_1"),
            place=PlaceRef(place_id="place_2"),
        )
        assert event_findings(event) == []

    def test_one_absent_place_yields_no_finding(self) -> None:
        """**Validates: Requirements 18.3, 18.7**"""
        assert event_findings(make_flytt(from_place=PlaceRef(place_id="place_1"))) == []
        assert event_findings(make_flytt(place=PlaceRef(place_id="place_1"))) == []
        assert event_findings(make_flytt()) == []

    def test_other_event_types_are_untouched(self) -> None:
        """**Validates: Requirements 18.7**"""
        event = make_flytt(
            from_place=PlaceRef(place_id="place_1"),
            place=PlaceRef(place_id="place_1"),
            event_type="census",
        )
        assert event_findings(event) == []


class TestFlyttFieldAndLabel:
    """Requirements 18.1, 18.2 — the field and the Swedish label."""

    def test_from_place_defaults_to_absent(self) -> None:
        """**Validates: Requirements 18.2**"""
        event = Event(
            id="event_1",
            type="flytt",
            participants=[Participant(person_id="person_1", role="primary")],
        )
        assert event.from_place is None
        assert event.place is None

    def test_from_place_and_place_carry_their_own_source_refs(self) -> None:
        """**Validates: Requirements 18.2**"""
        event = make_flytt(
            from_place=PlaceRef(
                place_id="place_1",
                source_refs=[SourceRef(source_id="source_1", quality="primary")],
            ),
            place=PlaceRef(
                place_id="place_2",
                source_refs=[SourceRef(source_id="source_2", quality="primary")],
            ),
        )

        assert event.from_place is not None and event.place is not None
        assert [sr.source_id for sr in event.from_place.source_refs] == ["source_1"]
        assert [sr.source_id for sr in event.place.source_refs] == ["source_2"]

    def test_flytt_label_is_registered(self) -> None:
        """**Validates: Requirements 18.1**"""
        assert INDIVIDUAL_EVENT_TYPE_LABELS["flytt"] == "Flytt"
        assert EVENT_TYPE_LABELS["flytt"] == "Flytt"
