"""Parentage_Sync_Service — placement events are the source of truth.

A placement *start* event is the single source of truth for its derived links:
a Fosterhem event (``type="foster_home"``) backs ``parentage_type="foster"``
links, and an Adoption event (``type="adoption"``) backs
``parentage_type="adoptive"`` links. The user edits the event; the derived links
are reconciled from it here. This keeps ordering (by event date) and set
membership (the one or two parents named in one event) unambiguous, identically
for both parentage types.

The two parentage types share one code path parameterised by
:data:`_PLACEMENT_START`, a small table mapping start event type → parentage
type → participant roles, so foster and adoptive cannot drift apart in
behaviour. :data:`_PLACEMENT_END` maps each end event type to the start type it
closes; end events never create or remove a link — they annotate an existing
placement by riding along on its derived family's ``event_ids``.

The service reuses the existing :class:`Family` grouping: each placement start
event maps to a dedicated *derived family* for that (child, event) pair,
recording the originating event id in the existing ``Family.event_ids`` list.
A derived family whose ``event_ids`` points at a still-existing placement start
event is updated in place; one whose start event is gone is deleted. Biological
links and every other parentage type are left exactly as found.

Pure module: no Qt, no I/O. ``sync_parentage_links`` mutates the Project in
place and is idempotent.
"""

from __future__ import annotations

from typing import Optional

from slaktbusken.model.event import Event, Participant
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.id_generator import IDGenerator
from slaktbusken.model.person import Person
from slaktbusken.model.project import ProjectData


# The single place foster/adoptive link-derivation behaviour is defined. Only
# START types derive links. END types annotate an existing placement and are
# deliberately absent here so the sync ignores them for link existence
# (Requirement 2.10 / 2A.2).
_PLACEMENT_START: dict[str, dict[str, str]] = {
    "foster_home": {
        "parentage": "foster",
        "child_role": "fosterbarn",
        "parent_role": "fosterförälder",
    },
    "adoption": {
        "parentage": "adoptive",
        "child_role": "adopterad",
        "parent_role": "adoptivförälder",
    },
}

# Each placement end type -> the placement start type it closes.
_PLACEMENT_END: dict[str, str] = {
    "foster_home_ended": "foster_home",
    "adoption_ended": "adoption",
}

# The parentage types this service owns. Any link whose parentage is not in
# this set is never created, removed, or otherwise touched.
_DERIVED_PARENTAGE_TYPES = frozenset(
    cfg["parentage"] for cfg in _PLACEMENT_START.values()
)

# Maximum parents in a single Parent_Set (Requirement 2.9). There is no
# project-wide cap on foster or adoptive parents for a child.
_MAX_PARENTS_PER_SET = 2


def _role_for_sex(sex: str) -> str:
    """Map a person's sex to a FamilyPartner role, matching ParentService."""
    if sex == "M":
        return "father"
    if sex == "F":
        return "mother"
    return "partner"


def _placement_participants(
    event: Event, child_role: str, parent_role: str
) -> tuple[Optional[str], list[str]]:
    """Return ``(child_id, parent_ids)`` named by a placement event.

    The child is the single participant in ``child_role`` (``None`` when the
    event names no valid child); parents are the participants in ``parent_role``
    in participant order, capped at :data:`_MAX_PARENTS_PER_SET`, with duplicate
    ids collapsed so a Parent_Set never holds the same person twice.
    """
    child_id: Optional[str] = None
    parent_ids: list[str] = []
    for participant in event.participants:
        if participant.role == child_role and child_id is None:
            child_id = participant.person_id
        elif participant.role == parent_role:
            if participant.person_id not in parent_ids:
                parent_ids.append(participant.person_id)
    return child_id, parent_ids[:_MAX_PARENTS_PER_SET]


class _ProjectIndex:
    """Lightweight lookups over a project, built once per sync."""

    def __init__(self, project: ProjectData) -> None:
        self._persons = {person.id: person for person in project.persons}
        self._person_ids = set(self._persons)

    def is_person(self, person_id: str) -> bool:
        return person_id in self._person_ids

    def role_for(self, person_id: str) -> str:
        person = self._persons.get(person_id)
        return _role_for_sex(person.sex) if person is not None else "partner"


def _derived_family_for(
    event_id: str, families: list[Family]
) -> Optional[Family]:
    """Return the derived family whose ``event_ids`` records ``event_id``."""
    for family in families:
        if event_id in family.event_ids:
            return family
    return None


def sync_parentage_links(project: ProjectData) -> None:
    """Make the set of foster/adoptive links agree with placement START events.

    - Collect every start event (type in :data:`_PLACEMENT_START`) that names a
      valid child and one or two parents in the configured roles.
    - For each such event, ensure a derived :class:`Family` exists keyed by the
      event id (found via ``Family.event_ids``), containing the parents as
      partners, the child in ``children``, and one :class:`ParentChildLink` per
      ``(parent -> child)`` with the event's parentage type.
    - Delete derived (foster/adoptive) families whose originating START event no
      longer exists; never touch biological links or any link whose parentage is
      neither ``"foster"`` nor ``"adoptive"``.
    - END events never create or remove a link; each is paired to the derived
      family of its matching start by Parent_Set (its id appended to that
      family's ``event_ids``) so the pairing persists. An end whose start is
      gone is detached rather than deleted, leaving the orphan end for the
      validator to flag.
    - Per-set cap of two parents; no project-wide cap on foster or adoptive
      parents for a child.

    Mutates ``project`` in place and is idempotent.
    """
    index = _ProjectIndex(project)
    id_generator = _make_id_generator(project)

    events_by_id = {event.id: event for event in project.events}

    # --- 1. Reconcile derived families against START events. -----------------

    # Every start event id that still exists and names a valid placement.
    live_start_ids: set[str] = set()
    for event in project.events:
        if event.type not in _PLACEMENT_START:
            continue
        config = _PLACEMENT_START[event.type]
        child_id, parent_ids = _placement_participants(
            event, config["child_role"], config["parent_role"]
        )
        if child_id is None or not index.is_person(child_id):
            # A start event that names no valid child derives nothing
            # (Requirement 1.9 / 13.5), so it owns no derived family.
            continue
        valid_parents = [pid for pid in parent_ids if index.is_person(pid)]
        if not valid_parents:
            # No parent named: the event derives no links (e.g. a pre-feature
            # descriptive Adoption event). It is left alone.
            continue
        live_start_ids.add(event.id)
        _reconcile_derived_family(
            project, index, id_generator, event, config["parentage"],
            child_id, valid_parents,
        )

    # Delete derived families whose originating START event is gone. A family
    # is a derived placement family only when it records a placement start id
    # on ``event_ids`` and every parentage type among its links is one this
    # service owns; biological and mixed families are never deleted here.
    project.families = [
        family
        for family in project.families
        if _family_survives(family, live_start_ids, events_by_id)
    ]

    # --- 2. Reconcile END-event pairings (never a link change). --------------

    for family in project.families:
        _reattach_end_events(family, events_by_id, live_start_ids)

    for event in project.events:
        if event.type not in _PLACEMENT_END:
            continue
        _pair_end_event(project, index, event)


def _reconcile_derived_family(
    project: ProjectData,
    index: _ProjectIndex,
    id_generator: IDGenerator,
    event: Event,
    parentage: str,
    child_id: str,
    parent_ids: list[str],
) -> None:
    """Ensure the derived family for ``event`` matches its named Parent_Set."""
    family = _derived_family_for(event.id, project.families)
    if family is None:
        family = Family(
            id=id_generator.generate("family"),
            partners=[],
            children=[],
            parent_child_links=[],
            event_ids=[event.id],
        )
        project.families.append(family)

    # Partners: exactly the named parents, in order, with their sex-derived role.
    family.partners = [
        FamilyPartner(person_id=pid, role=index.role_for(pid))
        for pid in parent_ids
    ]

    # Children: exactly the named child.
    family.children = [child_id]

    # Links: exactly one (parent -> child) link of the derived parentage type.
    family.parent_child_links = [
        ParentChildLink(
            child_id=child_id,
            parent_id=pid,
            parentage_type=parentage,
        )
        for pid in parent_ids
    ]

    # Keep the start event id recorded; drop any end-event ids whose pairing is
    # re-established in step 2 so ordering stays start-first.
    if event.id not in family.event_ids:
        family.event_ids.insert(0, event.id)


def _is_derived_family(family: Family) -> bool:
    """True when every parentage type among a family's links is ours.

    An empty family (no links) is not treated as derived on its own; derived
    status for an empty family is decided together with its recorded start ids
    in :func:`_family_survives`.
    """
    types = {link.parentage_type for link in family.parent_child_links}
    if not types:
        return False
    return types.issubset(_DERIVED_PARENTAGE_TYPES)


def _family_survives(
    family: Family,
    live_start_ids: set[str],
    events_by_id: dict[str, Event],
) -> bool:
    """Decide whether a family is kept after START-event reconciliation.

    A family is removed only when it is a *derived placement family* whose
    backing placement START event is gone. The survival decision is made
    independently of any END-event pairing so it is stable across repeated syncs
    (Requirement 2.8): END ids a previous sync appended to a family are ignored
    here. Concretely:

    * END ids (ids naming a live placement END event) are discarded from the
      recorded set — they are mere annotations, never evidence that a family was
      derived from a START event.
    * What remains are the family's would-be START ids. If any is still a live
      start, the family is backed and survives. If none remain (e.g. an *orphan*
      link family that recorded only an END id, or never recorded anything), the
      family is not a derived placement family and is preserved unchanged
      (Requirement 13.3). Only when a remaining recorded id is a *vanished*
      start — and the family's links are all ours — is the derived family
      dropped.
    """
    recorded = set(family.event_ids)
    # Drop END-event annotations: they never make a family a deletion target,
    # and ignoring them keeps the decision identical on a re-run after an end
    # id was paired in (idempotence, Req 2.8 / 13.3).
    end_ids = {
        event_id
        for event_id in recorded
        if events_by_id.get(event_id) is not None
        and events_by_id[event_id].type in _PLACEMENT_END
    }
    start_candidates = recorded - end_ids
    if not start_candidates:
        # No recorded START id (orphan link family or event-less family): never
        # a derived placement family to delete.
        return True
    if start_candidates & live_start_ids:
        # Still backed by at least one live start event.
        return True
    has_links = bool(family.parent_child_links)
    is_derived = _is_derived_family(family) if has_links else True
    # A derived family whose backing start event is gone is dropped; anything
    # else (e.g. a biological family that merely happens to record an event id)
    # is preserved.
    return not is_derived


def _reattach_end_events(
    family: Family, events_by_id: dict[str, Event], live_start_ids: set[str]
) -> None:
    """Strip end-event ids from a family before they are re-paired.

    Keeps the start event id(s) still backing the family and discards every
    other recorded id (stale end pairings), so :func:`_pair_end_event` can
    rebuild the pairings from scratch and detach ends whose start is gone.
    """
    family.event_ids = [
        event_id
        for event_id in family.event_ids
        if event_id in live_start_ids
        and events_by_id.get(event_id) is not None
        and events_by_id[event_id].type in _PLACEMENT_START
    ]


def _pair_end_event(
    project: ProjectData, index: _ProjectIndex, end_event: Event
) -> None:
    """Pair an end event to its matching start's derived family by Parent_Set.

    Appends the end event's id to the derived family whose start event names the
    same child, the same parent set, and the matching derived parentage type. An
    end whose start is gone (no matching family) is left detached — never
    deleted — so the validator can flag the orphan (Requirement 2A.4).
    """
    start_type = _PLACEMENT_END[end_event.type]
    config = _PLACEMENT_START[start_type]
    child_id, parent_ids = _placement_participants(
        end_event, config["child_role"], config["parent_role"]
    )
    if child_id is None:
        return
    parent_set = frozenset(parent_ids)

    match = _find_matching_start_family(
        project, config["parentage"], child_id, parent_set
    )
    if match is None:
        # Orphan end: no matching start. Leave it detached for the validator.
        return
    if end_event.id not in match.event_ids:
        match.event_ids.append(end_event.id)


def _find_matching_start_family(
    project: ProjectData,
    parentage: str,
    child_id: str,
    parent_set: frozenset[str],
) -> Optional[Family]:
    """Return the derived family matching a (type, child, parent set)."""
    for family in project.families:
        if child_id not in family.children:
            continue
        link_types = {link.parentage_type for link in family.parent_child_links}
        if parentage not in link_types:
            continue
        family_parents = frozenset(
            link.parent_id
            for link in family.parent_child_links
            if link.parentage_type == parentage and link.parent_id is not None
        )
        if family_parents == parent_set:
            return family
    return None


def _make_id_generator(project: ProjectData) -> IDGenerator:
    """Build an :class:`IDGenerator` seeded with the project's known ids."""
    existing: set[str] = set()
    for family in project.families:
        existing.add(family.id)
    for person in project.persons:
        existing.add(person.id)
    for event in project.events:
        existing.add(event.id)
    return IDGenerator(existing)


def parent_sets_in_order(
    project: ProjectData, child_id: str, parentage_type: str
) -> list[Family]:
    """Return a child's derived Parent_Sets of a given type, in display order.

    A Parent_Set is the derived :class:`Family` created for one
    Placement_Start_Event (keyed via ``Family.event_ids``). The sets are ordered
    by their start event's ``date.value``; a set whose start event has no date is
    placed after all dated sets, preserving its existing project order (the order
    its start event appears in ``project.events``). This is a read-only sort: it
    mutates neither the project nor any of its families (Requirement 2.5).

    Args:
        project: The project to read from.
        child_id: The person id of the placed child.
        parentage_type: Either ``"foster"`` or ``"adoptive"``.

    Returns:
        The matching derived families ordered by start date ascending, with
        undated start events last in project order.
    """
    # The start event type that backs this parentage type (``None`` for a
    # parentage type this service does not derive).
    start_type = next(
        (
            etype
            for etype, cfg in _PLACEMENT_START.items()
            if cfg["parentage"] == parentage_type
        ),
        None,
    )
    if start_type is None:
        return []

    # Index events by id and record each event's project position for a stable
    # order among undated sets.
    event_by_id: dict[str, Event] = {}
    event_position: dict[str, int] = {}
    for position, event in enumerate(project.events):
        event_by_id[event.id] = event
        event_position[event.id] = position

    def _start_event(family: Family) -> Optional[Event]:
        """Return the family's backing Placement_Start_Event of the wanted type."""
        for event_id in family.event_ids:
            event = event_by_id.get(event_id)
            if event is not None and event.type == start_type:
                return event
        return None

    # Collect the derived Parent_Sets for this child and type with their start.
    sets: list[tuple[Family, Event]] = []
    for family in project.families:
        if child_id not in family.children:
            continue
        start_event = _start_event(family)
        if start_event is None:
            continue
        if any(
            link.child_id == child_id and link.parentage_type == parentage_type
            for link in family.parent_child_links
        ):
            sets.append((family, start_event))

    def _sort_key(item: tuple[Family, Event]) -> tuple[int, str, int]:
        _, start_event = item
        position = event_position.get(start_event.id, len(project.events))
        if start_event.date is not None and start_event.date.value:
            # Dated sets first, ordered by their date value.
            return (0, start_event.date.value, position)
        # Undated sets last, preserving project order via position.
        return (1, "", position)

    return [family for family, _ in sorted(sets, key=_sort_key)]


# ---------------------------------------------------------------------------
# Pre-feature orphan-link migration (Requirement 13.3 / 13.5)
# ---------------------------------------------------------------------------
#
# A project saved before this feature may already contain foster/adoptive
# ``ParentChildLink`` rows that have no backing Placement_Start_Event — the new
# model requires each such link to be derived from an event, but the old model
# added them directly. Running :func:`sync_parentage_links` on such a project
# would delete those orphan links as unbacked. The migration below rescues them
# first: for every orphan foster/adoptive Parent_Set it back-fills a *dateless*
# placement start event (a Fosterhem event for a foster set, an Adoption event
# for an adoptive set) naming the child and the one or two parents, and records
# that event's id on the family's ``event_ids`` so the subsequent sync adopts it
# as the source of truth. No foster or adoptive data is ever deleted.
#
# The GEDCOM importer (task 10.3) shares :func:`backfill_orphan_placement_events`
# so importer and on-load migration cannot diverge.


def _event_backs_parent_set(
    event: Event,
    parentage: str,
    child_id: str,
    parent_set: frozenset[str],
) -> bool:
    """True when ``event`` is a START event that backs the given Parent_Set.

    A descriptive event (a start event naming the child but *no* parent in its
    parent role) backs nothing and must be preserved untouched (Req 13.5); it
    returns ``False`` here because its parent set is empty and therefore never
    equals a non-empty orphan Parent_Set.
    """
    if event.type not in _PLACEMENT_START:
        return False
    config = _PLACEMENT_START[event.type]
    if config["parentage"] != parentage:
        return False
    event_child, event_parents = _placement_participants(
        event, config["child_role"], config["parent_role"]
    )
    if event_child != child_id:
        return False
    return frozenset(event_parents) == parent_set


def _orphan_parent_sets(
    project: ProjectData,
) -> list[tuple[Family, str, str, list[str]]]:
    """Return each orphan foster/adoptive Parent_Set needing a back-fill event.

    An orphan Parent_Set is a group of foster (or adoptive) links within one
    :class:`Family`, sharing a child and a parent set, for which *no*
    Placement_Start_Event of the matching type already names that exact
    (child, parent set). The family may already be backed for a *different* set
    (e.g. a two-parent family that lost one link) — only unbacked sets are
    returned.

    Each entry is ``(family, parentage, child_id, parent_ids)`` with
    ``parent_ids`` in first-seen link order and capped at two, matching the
    per-set cardinality the sync enforces.
    """
    start_events = [ev for ev in project.events if ev.type in _PLACEMENT_START]
    orphans: list[tuple[Family, str, str, list[str]]] = []

    for family in project.families:
        # Group this family's derived links by (parentage, child), preserving
        # link order so a two-parent set keeps a stable parent ordering.
        grouped: dict[tuple[str, str], list[str]] = {}
        for link in family.parent_child_links:
            if link.parentage_type not in _DERIVED_PARENTAGE_TYPES:
                continue
            if link.parent_id is None:
                continue
            key = (link.parentage_type, link.child_id)
            parents = grouped.setdefault(key, [])
            if link.parent_id not in parents:
                parents.append(link.parent_id)

        for (parentage, child_id), parent_ids in grouped.items():
            parent_ids = parent_ids[:_MAX_PARENTS_PER_SET]
            parent_set = frozenset(parent_ids)
            already_backed = any(
                _event_backs_parent_set(ev, parentage, child_id, parent_set)
                for ev in start_events
            )
            if not already_backed:
                orphans.append((family, parentage, child_id, parent_ids))

    return orphans


def _start_type_for_parentage(parentage: str) -> str:
    """Return the START event type that derives ``parentage`` links."""
    for event_type, config in _PLACEMENT_START.items():
        if config["parentage"] == parentage:
            return event_type
    raise ValueError(f"No placement start type for parentage {parentage!r}")


def backfill_orphan_placement_events(project: ProjectData) -> list[Event]:
    """Back-fill a dateless placement start event for each orphan Parent_Set.

    For every orphan foster/adoptive Parent_Set in ``project`` (a set of
    foster/adoptive links with no backing Placement_Start_Event of the matching
    type), create one dateless start event — a Fosterhem event (roles
    ``fosterbarn``/``fosterförälder``) for a foster set, an Adoption event
    (``adopterad``/``adoptivförälder``) for an adoptive set — naming the child
    and the one or two parents, append it to ``project.events``, and record its
    id on the originating family's ``event_ids`` so a subsequent
    :func:`sync_parentage_links` keys off it.

    Pre-feature descriptive Adoption events (a start naming a child but no
    adoptive-parent participant) are preserved untouched and are never counted
    as backing a link (Req 13.5). A family already backed for a Parent_Set gains
    no duplicate event, so running this twice is a no-op on the second run
    (idempotent). No foster or adoptive link or event is ever deleted.

    This helper is shared with the GEDCOM importer (task 10.3). It is pure (no
    Qt, no I/O) and mutates ``project`` in place.

    Args:
        project: The project to migrate in place.

    Returns:
        The list of newly created back-fill events, in creation order (empty
        when the project has no orphan Parent_Sets).
    """
    orphans = _orphan_parent_sets(project)
    if not orphans:
        return []

    id_generator = _make_id_generator(project)
    created: list[Event] = []

    for family, parentage, child_id, parent_ids in orphans:
        start_type = _start_type_for_parentage(parentage)
        config = _PLACEMENT_START[start_type]

        participants = [Participant(person_id=child_id, role=config["child_role"])]
        for parent_id in parent_ids:
            participants.append(
                Participant(person_id=parent_id, role=config["parent_role"])
            )

        event = Event(
            id=id_generator.generate("event"),
            type=start_type,
            participants=participants,
            date=None,  # dateless back-fill
        )
        project.events.append(event)
        created.append(event)

        # Record the back-fill event id on the family so sync keys off it.
        if event.id not in family.event_ids:
            family.event_ids.insert(0, event.id)

    return created


def migrate_orphan_links(project: ProjectData) -> list[Event]:
    """Establish the placement-event source-of-truth invariant on load.

    The one-time, pre-feature migration (Requirement 13.3): back-fill a dateless
    placement start event for every orphan foster/adoptive Parent_Set, then run
    :func:`sync_parentage_links` so the back-filled events become the source of
    truth. The net effect is that no foster or adoptive link is deleted while the
    invariant (every derived link backed by an event) is established. Descriptive
    Adoption events are preserved (Req 13.5).

    Idempotent: after the first run every family is backed, so a second run finds
    no orphans, creates no events, and the trailing sync is a no-op.

    This function is pure (no Qt, no I/O) and mutates ``project`` in place; it is
    *not* wired into project load here (that app wiring is task 11.4). It returns
    the back-fill events it created so callers can report or test them.

    Args:
        project: The project to migrate in place.

    Returns:
        The list of back-fill events created (empty when nothing was orphaned).
    """
    created = backfill_orphan_placement_events(project)
    sync_parentage_links(project)
    return created
