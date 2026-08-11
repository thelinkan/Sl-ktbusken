"""Service for building map marker data from project events and places.

Also includes residence places, each labelled with the interval string
from the Residence_Formatter and ordered by the timeline order defined in
Requirement 11.10, via :func:`build_markers_for_person`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Optional

from slaktbusken.model.project import ProjectData
from slaktbusken.reports.geographic import residence_places_for_person


# --- Event type → Swedish display name mapping ---

EVENT_TYPE_DISPLAY: dict[str, str] = {
    "birth": "Födelse",
    "death": "Död",
    "marriage": "Vigsel",
    "divorce": "Skilsmässa",
    "baptism": "Dop",
    "burial": "Begravning",
    "immigration": "Invandring",
    "emigration": "Utvandring",
    "residence": "Bosättning",
    "occupation": "Yrke",
    "education": "Utbildning",
    "name_change": "Namnbyte",
    "confirmation": "Konfirmation",
}


# --- Dataclasses ---


@dataclass
class MapParticipant:
    """A participant to display in a map event card."""

    person_id: str
    display_name: str  # "given surname" or "(okänd)"


@dataclass
class MapEvent:
    """An event to display in a map marker popup."""

    event_id: str
    event_type: str
    event_type_display: str  # Swedish display name
    date_display: Optional[str]  # Formatted date string or None
    participants: list[MapParticipant]


@dataclass
class MapMarker:
    """A single map marker representing one place with its events."""

    place_id: str
    place_name: str
    latitude: float
    longitude: float
    events: list[MapEvent] = field(default_factory=list)


# --- Helper functions ---


def _get_event_type_display(event_type: str, custom_type_name: Optional[str]) -> str:
    """Return the Swedish display name for an event type."""
    if event_type == "custom":
        return custom_type_name or "Anpassad"
    return EVENT_TYPE_DISPLAY.get(event_type, event_type)


def _resolve_person_name(data: ProjectData, person_id: str) -> str:
    """Resolve a person's display name from project data.

    Returns "given surname" from the first Name entry, or "(okänd)" if
    the person cannot be found or has no names.
    """
    for person in data.persons:
        if person.id == person_id:
            if person.names:
                name = person.names[0]
                parts = []
                if name.given:
                    parts.append(name.given)
                if name.surname:
                    parts.append(name.surname)
                if parts:
                    return " ".join(parts)
            return "(okänd)"
    return "(okänd)"


def _format_date(date_value) -> Optional[str]:
    """Format a DateValue to a display string, or return None if no date."""
    if date_value is None:
        return None
    return date_value.value if date_value.value else None


def _sort_key_for_event(map_event: MapEvent):
    """Sort key: dated events first (by date string), undated events last."""
    if map_event.date_display is not None:
        return (0, map_event.date_display)
    return (1, "")


# --- Public API ---


def build_markers_for_person(data: ProjectData, person_id: str) -> list[MapMarker]:
    """Build map markers for all places where a person has events or residences.

    Filters events to those where person_id is a participant,
    then groups by place, resolving place coordinates and participant names.
    Additionally includes residence places, each labelled with the interval
    string from the Residence_Formatter, in the timeline order of
    Requirement 11.10.
    Only includes places with non-null latitude and longitude.

    Args:
        data: The full project data.
        person_id: The person to filter events for.

    Returns:
        List of MapMarker objects, one per qualifying place.
    """
    # Build lookup maps
    place_map = {place.id: place for place in data.places}

    # Group events by place for the given person
    markers_by_place: dict[str, MapMarker] = {}

    for event in data.events:
        # Check if this person is a participant
        if not any(p.person_id == person_id for p in event.participants):
            continue

        # Must have a place reference
        if event.place is None:
            continue

        place_id = event.place.place_id
        place = place_map.get(place_id)

        # Only include places with valid coordinates
        if place is None or place.latitude is None or place.longitude is None:
            continue

        # Get or create marker for this place
        if place_id not in markers_by_place:
            markers_by_place[place_id] = MapMarker(
                place_id=place_id,
                place_name=place.name,
                latitude=place.latitude,
                longitude=place.longitude,
            )

        # Build participants list
        participants = [
            MapParticipant(
                person_id=p.person_id,
                display_name=_resolve_person_name(data, p.person_id),
            )
            for p in event.participants
        ]

        # Build map event
        map_event = MapEvent(
            event_id=event.id,
            event_type=event.type,
            event_type_display=_get_event_type_display(event.type, event.custom_type_name),
            date_display=_format_date(event.date),
            participants=participants,
        )

        markers_by_place[place_id].events.append(map_event)

    # Include residence places, labelled with the formatter's interval string,
    # in the timeline order of Requirement 11.10.
    residence_entries = residence_places_for_person(data, person_id)
    person_display = _resolve_person_name(data, person_id)
    for entry in residence_entries:
        # Only include places with valid coordinates
        if entry.latitude is None or entry.longitude is None:
            continue

        # Get or create marker for this place
        if entry.place_id not in markers_by_place:
            markers_by_place[entry.place_id] = MapMarker(
                place_id=entry.place_id,
                place_name=entry.place_name,
                latitude=entry.latitude,
                longitude=entry.longitude,
            )

        # Build a MapEvent entry for the residence
        map_event = MapEvent(
            event_id=entry.residence_id,
            event_type="residence",
            event_type_display="Boende",
            date_display=entry.interval_display,
            participants=[
                MapParticipant(
                    person_id=person_id,
                    display_name=person_display,
                )
            ],
        )
        markers_by_place[entry.place_id].events.append(map_event)

    # Sort events within each marker chronologically
    for marker in markers_by_place.values():
        marker.events.sort(key=_sort_key_for_event)

    return list(markers_by_place.values())


def build_markers_all_events(data: ProjectData) -> list[MapMarker]:
    """Build map markers for all places in the project that have events.

    Groups all events by place, resolving coordinates and participant names.
    Only includes places with non-null latitude and longitude.

    Args:
        data: The full project data.

    Returns:
        List of MapMarker objects, one per qualifying place.
    """
    # Build lookup maps
    place_map = {place.id: place for place in data.places}

    # Group all events by place
    markers_by_place: dict[str, MapMarker] = {}

    for event in data.events:
        # Must have a place reference
        if event.place is None:
            continue

        place_id = event.place.place_id
        place = place_map.get(place_id)

        # Only include places with valid coordinates
        if place is None or place.latitude is None or place.longitude is None:
            continue

        # Get or create marker for this place
        if place_id not in markers_by_place:
            markers_by_place[place_id] = MapMarker(
                place_id=place_id,
                place_name=place.name,
                latitude=place.latitude,
                longitude=place.longitude,
            )

        # Build participants list
        participants = [
            MapParticipant(
                person_id=p.person_id,
                display_name=_resolve_person_name(data, p.person_id),
            )
            for p in event.participants
        ]

        # Build map event
        map_event = MapEvent(
            event_id=event.id,
            event_type=event.type,
            event_type_display=_get_event_type_display(event.type, event.custom_type_name),
            date_display=_format_date(event.date),
            participants=participants,
        )

        markers_by_place[place_id].events.append(map_event)

    # Sort events within each marker chronologically
    for marker in markers_by_place.values():
        marker.events.sort(key=_sort_key_for_event)

    return list(markers_by_place.values())


def markers_to_json(markers: list[MapMarker]) -> str:
    """Serialize markers to JSON string for injection into the HTML template.

    Returns a JSON array suitable for use in JavaScript.
    """
    return json.dumps([asdict(m) for m in markers], ensure_ascii=False)
