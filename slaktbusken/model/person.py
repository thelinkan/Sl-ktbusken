"""Person and name data containers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Name:
    """A single name entry for a person."""

    type: str
    given: str
    surname: str
    event_id: Optional[str] = None  # Links to the event that caused this name (e.g., marriage, name_change)


@dataclass
class Person:
    """A person record."""

    id: str
    sex: str
    names: list[Name]
    profile_media_id: Optional[str] = None
    notes: str = ""
    title: Optional[str] = None        # e.g., 'Fil.Dr' (max 100 chars)
    occupation: Optional[str] = None   # e.g., 'Lektor' (max 100 chars)
