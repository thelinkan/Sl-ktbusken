"""Lookup of person ids that may have been retired by a merge (Qt-free)."""

from __future__ import annotations

from dataclasses import dataclass

from slaktbusken.model.project import ProjectData
from slaktbusken.services.redirect_resolution import RedirectResolver


@dataclass(frozen=True)
class LookupResult:
    """``person_id`` is the person to open (None when nothing resolves);
    ``redirected_from`` is the requested retired id when redirected;
    ``retired_name`` is the stored name of the retired person."""

    person_id: str | None
    redirected_from: str | None = None
    retired_name: str = ""


def resolve_person_request(data: ProjectData, person_id: str) -> LookupResult:
    """Active id unchanged; retired id to its final survivor; a cycle, an
    ambiguous id or a missing survivor gives no person."""
    active = {p.id for p in data.persons}
    if person_id in active:
        return LookupResult(person_id)
    history = data.merge_history
    entries = [e for e in history if e.merged_person_id == person_id]
    if not entries:
        return LookupResult(person_id if person_id in active else None)
    name = entries[0].merged_person_name
    survivor = RedirectResolver(history).resolve(person_id)
    if survivor is None or survivor == person_id or survivor not in active:
        return LookupResult(None, None, name)
    return LookupResult(survivor, person_id, name)
