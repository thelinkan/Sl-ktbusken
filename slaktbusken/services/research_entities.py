"""Display labels and choices for the entities a research case can link to.

Pure lookups over ``ProjectData`` shared by the research case editor, the
research overview and the research tab. Nothing here changes the project.

``entity_label`` returns ``None`` for an entity that no longer exists, which is
how callers recognise a dangling reference.
"""

from __future__ import annotations

from typing import Optional

from slaktbusken.model.project import ProjectData
from slaktbusken.ui.swedish_locale import get_event_type_label

#: Entity types in the order they are offered to the user.
LINKABLE_ENTITY_TYPES: tuple[str, ...] = (
    "person",
    "family",
    "event",
    "place",
    "source",
    "media",
    "dna_match",
    "dna_cluster",
)

MISSING_ENTITY_MARKER = "(saknat objekt)"


def _person_label(person) -> str:
    if not person.names:
        return person.id
    name = person.names[0]
    text = f"{name.given.replace('*', '')} {name.surname}".strip()
    return text or person.id


def _family_label(data: ProjectData, family) -> str:
    persons = {p.id: p for p in data.persons}
    names = [
        _person_label(persons[partner.person_id])
        for partner in family.partners
        if partner.person_id in persons
    ]
    return " och ".join(names) if names else family.id


def _event_label(data: ProjectData, event) -> str:
    parts = [get_event_type_label(event.type)]
    if event.date is not None and event.date.value:
        parts.append(event.date.value)
    persons = {p.id: p for p in data.persons}
    for participant in event.participants[:1]:
        if participant.person_id in persons:
            parts.append(_person_label(persons[participant.person_id]))
    return " – ".join(parts)


def _dna_match_label(data: ProjectData, match) -> str:
    return f"DNA-matchning {match.id} ({match.shared_cm:g} cM)"


def _all_labels(data: ProjectData, entity_type: str) -> dict[str, str]:
    """Return ``{id: label}`` for every existing entity of one type."""
    if entity_type == "person":
        return {p.id: _person_label(p) for p in data.persons}
    if entity_type == "family":
        return {f.id: _family_label(data, f) for f in data.families}
    if entity_type == "event":
        return {e.id: _event_label(data, e) for e in data.events}
    if entity_type == "place":
        return {p.id: p.name or p.id for p in data.places}
    if entity_type == "source":
        return {s.id: s.title or s.id for s in data.sources}
    if entity_type == "media":
        return {m.id: m.title or m.file or m.id for m in data.media}
    if entity_type == "dna_match":
        return {m.id: _dna_match_label(data, m) for m in data.dna_matches}
    if entity_type == "dna_cluster":
        return {c.id: c.name or c.id for c in data.dna_clusters}
    return {}


def entity_label(data: ProjectData, entity_type: str, entity_id: str) -> Optional[str]:
    """Return the display label of an entity, or ``None`` when it does not exist."""
    return _all_labels(data, entity_type).get(entity_id)


def entity_choices(data: ProjectData, entity_type: str) -> list[tuple[str, str]]:
    """Return ``(id, label)`` pairs for one entity type, sorted by label."""
    labels = _all_labels(data, entity_type)
    return sorted(labels.items(), key=lambda pair: (pair[1].lower(), pair[0]))


def entity_label_or_marker(data: ProjectData, entity_type: str, entity_id: str) -> str:
    """Return the label, or the "(saknat objekt)" marker for a dangling reference."""
    label = entity_label(data, entity_type, entity_id)
    return label if label is not None else MISSING_ENTITY_MARKER
