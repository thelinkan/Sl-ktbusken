"""Id registry: ids that are never reused, including retired person ids.

``IDGenerator`` derives its counter from the ids it is seeded with, so an id
whose entity was deleted can be handed out again after the project is saved
and reopened. ``ProjectData.id_high_water_marks`` records, per id prefix, the
highest suffix ever issued. This module generalises that mechanism from the
research entity types to the merge entity types, and protects the ids of
person records retired by a merge (derived from ``merge_history``).

A project without research or merge data keeps an empty ``id_high_water_marks``.

This module is pure: no Qt and no I/O.
"""

from __future__ import annotations

import re

from slaktbusken.model.id_generator import IDGenerator
from slaktbusken.model.project import ProjectData

#: Entity types whose ids are protected by high-water marks.
PROTECTED_ENTITY_TYPES: tuple[str, ...] = (
    "research_case",
    "research_hypothesis",
    "research_action",
    "hypothesis_comment",
    "merge_candidate",
    "merge_candidate_comment",
    "merge_history",
)

_PERSON_PREFIX = IDGenerator._PREFIXES["person"]


def protected_id_prefix(entity_type: str) -> str:
    """Return the id prefix for a protected entity type.

    Raises:
        ValueError: If *entity_type* is not a protected entity type.
    """
    if entity_type not in PROTECTED_ENTITY_TYPES:
        raise ValueError(f"Not a protected entity type: {entity_type!r}")
    return IDGenerator._PREFIXES[entity_type]


def live_protected_ids(data: ProjectData) -> dict[str, set[str]]:
    """Return the ids currently in use, grouped by protected id prefix.

    Includes hypothesis comments nested in hypotheses and candidate comments
    nested in merge candidates.
    """
    ids: dict[str, set[str]] = {
        protected_id_prefix(entity_type): set() for entity_type in PROTECTED_ENTITY_TYPES
    }
    ids[protected_id_prefix("research_case")].update(c.id for c in data.research_cases)
    ids[protected_id_prefix("research_hypothesis")].update(
        h.id for h in data.research_hypotheses
    )
    ids[protected_id_prefix("research_action")].update(a.id for a in data.research_actions)
    hypothesis_comments = ids[protected_id_prefix("hypothesis_comment")]
    for hypothesis in data.research_hypotheses:
        hypothesis_comments.update(c.id for c in hypothesis.comments)
    ids[protected_id_prefix("merge_candidate")].update(c.id for c in data.merge_candidates)
    candidate_comments = ids[protected_id_prefix("merge_candidate_comment")]
    for candidate in data.merge_candidates:
        candidate_comments.update(c.id for c in candidate.comments)
    ids[protected_id_prefix("merge_history")].update(e.id for e in data.merge_history)
    return ids


def _highest_suffix(ids: set[str], prefix: str) -> int:
    """Return the largest numeric suffix among *ids* of the form ``prefix + digits``."""
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    highest = 0
    for used in ids:
        match = pattern.match(used)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest


def reconcile_id_high_water_marks(data: ProjectData) -> None:
    """Raise each protected prefix's mark to at least its highest live suffix.

    A mark is only ever raised, never lowered, and a prefix with no live id and
    no stored mark is left out, so a project without research or merge data
    keeps an empty map.
    """
    for prefix, ids in live_protected_ids(data).items():
        highest = _highest_suffix(ids, prefix)
        if highest > data.id_high_water_marks.get(prefix, 0):
            data.id_high_water_marks[prefix] = highest


def retired_person_ids(data: ProjectData) -> set[str]:
    """Return the ids of person records retired by a merge."""
    return {entry.merged_person_id for entry in data.merge_history if entry.merged_person_id}


class ProtectedIdGenerator:
    """Issues protected ids that are never reused, even after reopening a project.

    Each id issued advances ``ProjectData.id_high_water_marks`` for its prefix,
    so the next id is greater even when the entity just issued has not been
    added to the project yet, and even when it is later deleted.
    """

    #: Entity types this generator accepts.
    ENTITY_TYPES: tuple[str, ...] = PROTECTED_ENTITY_TYPES

    def __init__(self, data: ProjectData) -> None:
        self._data = data
        reconcile_id_high_water_marks(data)

    def generate(self, entity_type: str) -> str:
        """Return a new id for *entity_type* and record its suffix.

        Raises:
            ValueError: If *entity_type* is not accepted by this generator.
        """
        if entity_type not in self.ENTITY_TYPES:
            raise ValueError(f"Not a protected entity type: {entity_type!r}")
        prefix = protected_id_prefix(entity_type)
        live = live_protected_ids(self._data)[prefix]

        # Seed with the live ids plus a stand-in for the stored mark, so the
        # generator starts above every id ever issued.
        seed = set(live)
        mark = self._data.id_high_water_marks.get(prefix, 0)
        if mark > 0:
            seed.add(f"{prefix}{mark}")

        new_id = IDGenerator(seed).generate(entity_type)
        self._data.id_high_water_marks[prefix] = int(new_id[len(prefix):])
        return new_id


def person_id_seed(data: ProjectData) -> set[str]:
    """Return the ids a person-id generator must treat as used.

    Live person ids, retired person ids and a stand-in for the stored
    ``person_`` high-water mark.
    """
    seed = {person.id for person in data.persons}
    seed |= retired_person_ids(data)
    mark = data.id_high_water_marks.get(_PERSON_PREFIX, 0)
    if mark > 0:
        seed.add(f"{_PERSON_PREFIX}{mark}")
    return seed


def issue_person_id(data: ProjectData, extra_used_ids: set[str] | None = None) -> str:
    """Return a new person id that is neither live nor retired nor below the mark.

    Does not write to ``id_high_water_marks`` (the merge engine does that at
    commit), so unmerged projects keep an empty map. *extra_used_ids* lets a
    caller add ids of other entity types it already knows are used.
    """
    seed = person_id_seed(data)
    if extra_used_ids:
        seed |= extra_used_ids
    return IDGenerator(seed).generate("person")
