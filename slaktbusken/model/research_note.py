"""Research note data container."""

from __future__ import annotations

from dataclasses import dataclass, field

from slaktbusken.model.media import LinkedEntity


@dataclass
class ResearchNote:
    """A free-form research note linked to one or more entities."""

    id: str
    title: str
    text: str
    linked_entities: list[LinkedEntity] = field(default_factory=list)
