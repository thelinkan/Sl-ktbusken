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


@dataclass
class Person:
    """A person record."""

    id: str
    sex: str
    names: list[Name]
    profile_media_id: Optional[str] = None
    notes: str = ""
