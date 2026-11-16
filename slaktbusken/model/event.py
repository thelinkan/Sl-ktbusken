"""Event and related reference data containers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from slaktbusken.model.record_origin import RecordOrigin


@dataclass
class SourceRef:
    """A reference to a source with a quality assessment."""

    source_id: str
    quality: str
    note: str = ""
    aspects: list[str] = field(default_factory=list)


@dataclass
class DateValue:
    """A date with precision and supporting source references."""

    value: str
    precision: str
    source_refs: list[SourceRef] = field(default_factory=list)
    qualifier: str = "exact"
    value_to: Optional[str] = None      # range end for between / from_to
    calendar: str = "gregorian"         # as written, never converted
    original_text: Optional[str] = None


@dataclass
class PlaceRef:
    """A reference to a place with supporting source references."""

    place_id: str
    source_refs: list[SourceRef] = field(default_factory=list)


@dataclass
class Participant:
    """A person participating in an event with a role."""

    person_id: str
    role: str


@dataclass
class Event:
    """An event involving one or more participants."""

    id: str
    type: str
    participants: list[Participant]
    date: Optional[DateValue] = None
    place: Optional[PlaceRef] = None
    media_ids: list[str] = field(default_factory=list)
    custom_type_name: Optional[str] = None
    cause_of_death: Optional[str] = None
    # Flytt origin; ``place`` is the destination of the move. Both are optional:
    # an absent value means that side of the move is unknown.
    from_place: Optional[PlaceRef] = None
    # Event-level citations and the GEDCOM record the event was imported from.
    source_refs: list[SourceRef] = field(default_factory=list)
    origin: Optional[RecordOrigin] = None
