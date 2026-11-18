"""Place id de-duplication.

Historically some code paths (GEDCOM import / re-import, older data) could
append more than one :class:`~slaktbusken.model.place.Place` record sharing the
same ``id`` but with different ``parent_place_id`` chains. Because place ids are
assumed unique throughout the app, a duplicate id causes different code to
resolve the "same" place to different records — e.g. one dropdown showing
"..., Gävleborgs län, Sverige, Europa" and another showing
"..., Gävleborgs län, Stockholm".

This module removes such duplicates deterministically: for each colliding id it
keeps the single record whose parent chain resolves furthest up the hierarchy
(preferring a chain that reaches a country/continent), and drops the rest. The
kept record retains the shared id, so every reference elsewhere
(``parent_place_id``, ``Event.place`` / ``Event.from_place``,
``ResidenceFact.place_id``) stays valid without re-pointing.
"""

from __future__ import annotations

from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData

# Types that represent the top of a well-formed hierarchy. A chain that reaches
# one of these is considered "complete".
_ROOT_TYPES: frozenset[str] = frozenset({"country", "continent"})


def _chain_score(
    place: Place, places_by_id: dict[str, list[Place]]
) -> tuple[int, int]:
    """Score a candidate place by how complete its parent chain is.

    Walks up ``parent_place_id`` (circular-ref safe) and returns a tuple used
    for ranking, higher is better:

    - element 0: 1 if the chain reaches a country/continent, else 0.
    - element 1: the number of ancestors reachable (chain depth).

    When multiple records share the ``current_id`` at some step, resolution
    follows the first record found for that id (mirroring the linear-scan the
    editors use), which is sufficient because we only need a stable, comparable
    measure of chain completeness.
    """
    reaches_root = 0
    depth = 0
    visited: set[str] = {place.id}
    current: Place | None = place

    while current is not None and current.parent_place_id:
        parent_id = current.parent_place_id
        if parent_id in visited:
            break  # circular reference — stop walking
        visited.add(parent_id)
        candidates = places_by_id.get(parent_id)
        if not candidates:
            break  # dangling parent reference — chain ends here
        parent = candidates[0]
        depth += 1
        if parent.type in _ROOT_TYPES:
            reaches_root = 1
            break
        current = parent

    return (reaches_root, depth)


def deduplicate_places(places: list[Place]) -> tuple[list[Place], list[str]]:
    """Return a place list with at most one record per id.

    For each id that appears more than once, the record with the most complete
    parent chain is kept (see :func:`_chain_score`); ties are broken by keeping
    the earliest occurrence, so a clean list is returned unchanged.

    Args:
        places: The raw list of places (may contain duplicate ids).

    Returns:
        A ``(deduped_places, messages)`` tuple. ``deduped_places`` preserves the
        original ordering of the kept records. ``messages`` contains one
        human-readable diagnostic per removed duplicate.
    """
    # Group every record by id while remembering original position for stable
    # ordering and tie-breaking.
    by_id: dict[str, list[tuple[int, Place]]] = {}
    for index, place in enumerate(places):
        by_id.setdefault(place.id, []).append((index, place))

    # No duplicates: return the input untouched (cheap fast path).
    if all(len(group) == 1 for group in by_id.values()):
        return places, []

    # Build an id -> [places] lookup for chain scoring across all records.
    places_by_id: dict[str, list[Place]] = {}
    for place in places:
        places_by_id.setdefault(place.id, []).append(place)

    kept_by_index: dict[int, Place] = {}
    messages: list[str] = []

    for place_id, group in by_id.items():
        if len(group) == 1:
            index, place = group[0]
            kept_by_index[index] = place
            continue

        # Choose the best record: highest chain score, then earliest index.
        best_index, best_place = min(
            group,
            key=lambda item: (
                # Negate the score so higher completeness sorts first, then
                # prefer the smaller original index.
                tuple(-s for s in _chain_score(item[1], places_by_id)),
                item[0],
            ),
        )
        kept_by_index[best_index] = best_place

        for index, place in group:
            if index == best_index:
                continue
            messages.append(
                f"Plats-id '{place_id}' förekom flera gånger; "
                f"behöll posten '{best_place.name}' och tog bort en dubblett "
                f"'{place.name}'."
            )

    # Emit kept records in their original relative order.
    deduped = [kept_by_index[i] for i in sorted(kept_by_index)]
    return deduped, messages


def deduplicate_project_places(
    project_data: ProjectData, *, log: list[str] | None = None
) -> int:
    """De-duplicate ``project_data.places`` in place.

    Args:
        project_data: The project whose ``places`` list is cleaned.
        log: Optional list to receive one diagnostic message per removed
            duplicate.

    Returns:
        The number of duplicate records removed.
    """
    original_count = len(project_data.places)
    deduped, messages = deduplicate_places(project_data.places)
    project_data.places = deduped
    if log is not None:
        log.extend(messages)
    return original_count - len(deduped)
