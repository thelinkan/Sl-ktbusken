"""Event-type-specific and entity-type-specific source aspect mapping.

Defines which source aspects (e.g. date, place, parents) are relevant
for each event type and for each non-event entity type, along with
Swedish display labels for the UI.
"""

from __future__ import annotations

EVENT_SOURCE_ASPECTS: dict[str, list[str]] = {
    "birth": ["date", "place", "parents", "witnesses"],
    "death": ["date", "place", "cause_of_death"],
    "marriage": ["date", "place", "spouse"],
    "flytt": ["date", "from_place", "to_place"],
    "_default": ["date", "place"],
}
"""Mapping from event type to the list of relevant source aspects."""

ENTITY_SOURCE_ASPECTS: dict[str, list[str]] = {
    "residence": ["place", "period", "household_role", "household_members"],
}
"""Mapping from non-event entity type to the list of relevant source aspects."""

ASPECT_LABELS: dict[str, str] = {
    "date": "Datum",
    "place": "Plats",
    "parents": "Föräldrar",
    "witnesses": "Vittnen",
    "cause_of_death": "Dödsorsak",
    "spouse": "Make/maka",
    "from_place": "Från",
    "to_place": "Till",
    "period": "Period",
    "household_role": "Hushållsroll",
    "household_members": "Hushållsmedlemmar",
}
"""Swedish display labels for each aspect key."""


def get_aspects_for_event_type(event_type: str) -> list[str]:
    """Return the list of relevant source aspects for the given event type.

    For known event types (birth, death, marriage), returns the specific
    aspect list. For all other/unknown event types, returns the default
    list of ["date", "place"].

    Args:
        event_type: The event type string (e.g. "birth", "death", "marriage").

    Returns:
        A list of aspect keys relevant to the event type.
    """
    return EVENT_SOURCE_ASPECTS.get(event_type, EVENT_SOURCE_ASPECTS["_default"])


def get_aspects_for_entity_type(entity_type: str) -> list[str]:
    """Return the list of relevant source aspects for a non-event entity type.

    For known entity types (currently "residence"), returns the specific
    aspect list. For all other/unknown entity types, returns an empty list.

    Args:
        entity_type: The internal entity key (e.g. "residence").

    Returns:
        A list of aspect keys relevant to the entity type.
    """
    return ENTITY_SOURCE_ASPECTS.get(entity_type, [])
