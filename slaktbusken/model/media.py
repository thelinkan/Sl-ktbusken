"""Media item and linked-entity data containers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LinkedEntity:
    """A link from a media item (or note) to another entity."""

    entity_type: str
    entity_id: str
    role: str = ""


@dataclass
class MediaItem:
    """A media item such as an image, document, or recording."""

    id: str
    type: str
    file: str
    title: str
    linked_entities: list[LinkedEntity] = field(default_factory=list)
    publication: Optional[dict] = None
    transcription: Optional[str] = None
    mentioned_person_ids: list[str] = field(default_factory=list)
