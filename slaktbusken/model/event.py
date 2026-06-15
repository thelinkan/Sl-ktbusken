"""Event and related reference data containers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SourceRef:
    """A reference to a source with a quality assessment."""

    source_id: str
    quality: str
    note: str = ""


@dataclass
class DateValue:
    """A date with precision and supporting source references."""

    value: str
    precision: str
    source_refs: list[SourceRef] = field(default_factory=list)


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
