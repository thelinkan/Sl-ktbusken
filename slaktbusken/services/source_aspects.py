"""Event-type-specific source aspect mapping.

Defines which source aspects (e.g. date, place, parents) are relevant
for each event type, along with Swedish display labels for the UI.
"""

from __future__ import annotations

EVENT_SOURCE_ASPECTS: dict[str, list[str]] = {
    "birth": ["date", "place", "parents", "witnesses"],
    "death": ["date", "place", "cause_of_death"],
    "marriage": ["date", "place", "spouse"],
    "_default": ["date", "place"],
}
"""Mapping from event type to the list of relevant source aspects."""

ASPECT_LABELS: dict[str, str] = {
    "date": "Datum",
    "place": "Plats",
    "parents": "Föräldrar",
    "witnesses": "Vittnen",
    "cause_of_death": "Dödsorsak",
    "spouse": "Make/maka",
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
