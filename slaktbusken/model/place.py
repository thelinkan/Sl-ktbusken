"""Place data container."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Place:
    """A place, optionally nested within a parent place hierarchy."""

    id: str
    type: str
    name: str
    parent_place_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    notes: str = ""
