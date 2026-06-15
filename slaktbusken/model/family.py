"""Family, partner, and parent-child link data containers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FamilyPartner:
    """A partner within a family with an associated role."""

    person_id: str
    role: str


@dataclass
class ParentChildLink:
    """A link describing the parentage relationship between a child and parent."""

    child_id: str
    parent_id: Optional[str]
    parentage_type: str


@dataclass
class Family:
    """A family grouping of partners and children."""

    id: str
    partners: list[FamilyPartner]
    children: list[str]
    parent_child_links: list[ParentChildLink] = field(default_factory=list)
    event_ids: list[str] = field(default_factory=list)
