"""Single reader for the citations of an event.

An event carries Source_References in four locations: on the event itself,
on its date, on its place and on its from-place. All code outside the model
and the serializer reads them through this module. Pure; no Qt.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from slaktbusken.model.event import Event, SourceRef


class CitationContext(str, Enum):
    EVENT = "event"
    DATE = "date"
    PLACE = "place"
    FROM_PLACE = "from_place"


@dataclass(frozen=True)
class EventCitation:
    context: CitationContext
    ref: SourceRef  # the stored object, not a copy


_LABELS_SV = {
    CitationContext.EVENT: "Händelse",
    CitationContext.DATE: "Datum",
    CitationContext.PLACE: "Plats",
    CitationContext.FROM_PLACE: "Från plats",
}


def event_citations(event: Event) -> list[EventCitation]:
    """Return every citation of ``event``: event, date, place, from_place."""
    result: list[EventCitation] = []
    for ref in event.source_refs:
        result.append(EventCitation(CitationContext.EVENT, ref))
    if event.date is not None:
        for ref in event.date.source_refs:
            result.append(EventCitation(CitationContext.DATE, ref))
    if event.place is not None:
        for ref in event.place.source_refs:
            result.append(EventCitation(CitationContext.PLACE, ref))
    if event.from_place is not None:
        for ref in event.from_place.source_refs:
            result.append(EventCitation(CitationContext.FROM_PLACE, ref))
    return result


def cited_source_ids(event: Event) -> set[str]:
    return {c.ref.source_id for c in event_citations(event)}


def event_cites_source(event: Event, source_id: str) -> bool:
    return any(c.ref.source_id == source_id for c in event_citations(event))


def context_label_sv(context: CitationContext) -> str:
    return _LABELS_SV[CitationContext(context)]


def identical_reference(a: SourceRef, b: SourceRef) -> bool:
    """True when source id, quality, note and aspects (ordered) are equal."""
    return (
        a.source_id == b.source_id
        and a.quality == b.quality
        and a.note == b.note
        and list(a.aspects) == list(b.aspects)
    )
