"""Render-scoped lookup indexes for the diagram views (Qt-free).

The family, ancestry and descendants views build ``display_data`` for dozens of
boxes per render. Before this module each box scanned every event, DNA profile,
DNA cluster and person. :class:`DiagramLookup` is built in one pass per render
(or per comparison refresh) and answers the same questions with dictionary
lookups.

The module also holds the active render context. The module-level helper
functions (``find_person``, ``person_events`` ...) use the active lookup when
it belongs to the given project data and otherwise fall back to the original
linear scans, so behaviour outside a render context is unchanged.
"""

from __future__ import annotations

from typing import Any, Optional

# Event types retained per person; the box shows nothing else.
_BOX_EVENT_TYPES = frozenset({"birth", "death", "marriage"})


class DiagramLookup:
    """Read-only indexes over one ``ProjectData`` state."""

    def __init__(self, data: Any) -> None:
        self.data = data
        self._counts = _counts_of(data)

        self.person_by_id: dict[str, Any] = {}
        for person in data.persons:
            self.person_by_id.setdefault(person.id, person)

        self.family_by_id: dict[str, Any] = {}
        self.parent_families_by_child: dict[str, list[Any]] = {}
        self.partner_families_by_person: dict[str, list[Any]] = {}
        for family in data.families:
            self.family_by_id.setdefault(family.id, family)
            for child_id in dict.fromkeys(family.children):
                self.parent_families_by_child.setdefault(child_id, []).append(family)
            for partner_id in dict.fromkeys(p.person_id for p in family.partners):
                self.partner_families_by_person.setdefault(partner_id, []).append(family)

        self.place_by_id: dict[str, Any] = {}
        for place in data.places:
            self.place_by_id.setdefault(place.id, place)

        # Only birth, death and marriage events, in project order.
        self.events_by_person: dict[str, list[Any]] = {}
        by_person = self.events_by_person
        box_types = _BOX_EVENT_TYPES
        for event in data.events:
            if event.type not in box_types:
                continue
            participants = event.participants
            if len(participants) == 1:
                person_ids: Any = (participants[0].person_id,)
            else:
                person_ids = dict.fromkeys([p.person_id for p in participants])
            for person_id in person_ids:
                bucket = by_person.get(person_id)
                if bucket is None:
                    by_person[person_id] = [event]
                else:
                    bucket.append(event)

        self.dna_company_ids_by_person: dict[str, set[str]] = {}
        for profile in data.dna_profiles:
            self.dna_company_ids_by_person.setdefault(profile.person_id, set()).add(
                profile.company_id
            )

        self.clusters_by_person: dict[str, list[Any]] = {}
        for cluster in data.dna_clusters:
            for person_id in dict.fromkeys(cluster.person_ids):
                self.clusters_by_person.setdefault(person_id, []).append(cluster)

    @classmethod
    def build(cls, data: Any) -> "DiagramLookup":
        """Build a lookup from ``data`` in one pass per collection."""
        return cls(data)

    def matches(self, data: Any) -> bool:
        """Return whether this lookup was built for the current state of ``data``."""
        return data is self.data and _counts_of(data) == self._counts

    def siblings_of(self, person_id: str, family_id: Optional[str] = None) -> list[str]:
        """Return the siblings of a person (Requirement 10.5).

        Siblings are the other children of the family given by ``family_id`` or,
        when it is omitted or unknown, of the person's first parent family.
        """
        family = self.family_by_id.get(family_id) if family_id is not None else None
        if family is None:
            families = self.parent_families_by_child.get(person_id)
            family = families[0] if families else None
        if family is None:
            return []
        return [cid for cid in family.children if cid != person_id]


def _counts_of(data: Any) -> tuple[int, ...]:
    return (
        len(data.persons),
        len(data.families),
        len(data.events),
        len(data.places),
        len(data.dna_profiles),
        len(data.dna_clusters),
    )


# ---------------------------------------------------------------------------
# Active render context
# ---------------------------------------------------------------------------

_active: Optional[DiagramLookup] = None


def begin_lookup(data: Any) -> Optional[DiagramLookup]:
    """Build and activate the lookup of a render (``None`` clears it)."""
    global _active
    _active = DiagramLookup.build(data) if data is not None else None
    return _active


def set_active_lookup(lookup: Optional[DiagramLookup]) -> None:
    """Activate a lookup built elsewhere (e.g. shared by both comparison views)."""
    global _active
    _active = lookup


def active_lookup(data: Any) -> Optional[DiagramLookup]:
    """Return the active lookup if it is valid for ``data``, else ``None``."""
    if _active is not None and _active.matches(data):
        return _active
    return None


# ---------------------------------------------------------------------------
# Lookups with scan fallback (identical results with and without a lookup)
# ---------------------------------------------------------------------------


def find_person(data: Any, person_id: str) -> Any:
    lookup = active_lookup(data)
    if lookup is not None:
        return lookup.person_by_id.get(person_id)
    for p in data.persons:
        if p.id == person_id:
            return p
    return None


def find_place(data: Any, place_id: str) -> Any:
    lookup = active_lookup(data)
    if lookup is not None:
        return lookup.place_by_id.get(place_id)
    for place in data.places:
        if place.id == place_id:
            return place
    return None


def find_parent_families(data: Any, person_id: str) -> list[Any]:
    lookup = active_lookup(data)
    if lookup is not None:
        return list(lookup.parent_families_by_child.get(person_id, ()))
    return [family for family in data.families if person_id in family.children]


def find_partner_families(data: Any, person_id: str) -> list[Any]:
    lookup = active_lookup(data)
    if lookup is not None:
        return list(lookup.partner_families_by_person.get(person_id, ()))
    families = []
    for family in data.families:
        for partner in family.partners:
            if partner.person_id == person_id:
                families.append(family)
                break
    return families


def find_family_by_id(data: Any, family_id: str) -> Any:
    lookup = active_lookup(data)
    if lookup is not None:
        return lookup.family_by_id.get(family_id)
    for family in data.families:
        if family.id == family_id:
            return family
    return None


def person_box_events(data: Any, person_id: str) -> list[Any]:
    """Birth, death and marriage events of a person in project order."""
    lookup = active_lookup(data)
    if lookup is not None:
        return list(lookup.events_by_person.get(person_id, ()))
    return [
        event
        for event in data.events
        if event.type in _BOX_EVENT_TYPES
        and any(p.person_id == person_id for p in event.participants)
    ]


def person_dna_company_ids(data: Any, person_id: str) -> set[str]:
    lookup = active_lookup(data)
    if lookup is not None:
        return set(lookup.dna_company_ids_by_person.get(person_id, ()))
    return {p.company_id for p in data.dna_profiles if p.person_id == person_id}


def person_clusters(data: Any, person_id: str) -> list[Any]:
    lookup = active_lookup(data)
    if lookup is not None:
        return list(lookup.clusters_by_person.get(person_id, ()))
    return [c for c in data.dna_clusters if person_id in c.person_ids]
