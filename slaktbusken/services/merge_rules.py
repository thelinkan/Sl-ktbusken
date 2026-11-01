"""Pure merge rule functions for the person merge.

Qt-free and free of I/O. Every function takes values and returns new values;
no argument is modified. No function picks a survivor by a computed criterion:
the survivor is always passed in by the caller (the user's choice).

Covers: attribute resolution (Requirement 21.2 to 21.7), names (21.8 to 21.10),
event participants (21.12, 21.13), the Similar_Event_Rule (21.14, 21.15) and
link collapse for media links, research note links, id lists and parent-child
links (22.3, 22.9, 22.13, 23.2 to 23.4).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional, Sequence

from slaktbusken.model import date_span
from slaktbusken.model.event import Event, Participant
from slaktbusken.model.family import ParentChildLink
from slaktbusken.model.media import Annotation, LinkedEntity
from slaktbusken.model.person import Name

# ---------------------------------------------------------------------------
# Attributes (21.2 to 21.7)
# ---------------------------------------------------------------------------

SINGLE_VALUE_BOTH_EMPTY = "both_empty"
SINGLE_VALUE_ONE = "keep_non_empty"
SINGLE_VALUE_EQUAL = "equal"
SINGLE_VALUE_CONFLICT = "conflict"

NOTES_KEEP_SURVIVOR = "keep_survivor"
NOTES_KEEP_OTHER = "keep_other"
NOTES_CONCATENATE = "concatenate"


def is_blank(value: Optional[str]) -> bool:
    """Whether *value* is ``None``, empty or whitespace-only."""
    return value is None or not value.strip()


@dataclass(frozen=True)
class SingleValueResolution:
    """Outcome of comparing one single-valued attribute of two persons.

    ``value`` is the kept value (``None`` when both are empty or when the
    status is ``conflict``, which needs an explicit user choice).
    """

    status: str
    value: Optional[str]


def resolve_single_value(
    survivor_value: Optional[str], other_value: Optional[str]
) -> SingleValueResolution:
    """Resolve title, occupation or profile media id.

    Whitespace-only counts as empty. A non-empty value is never replaced by an
    empty one. Equality compares the stripped strings; the survivor's original
    text is kept.
    """
    s_empty = is_blank(survivor_value)
    o_empty = is_blank(other_value)
    if s_empty and o_empty:
        return SingleValueResolution(SINGLE_VALUE_BOTH_EMPTY, None)
    if o_empty:
        return SingleValueResolution(SINGLE_VALUE_ONE, survivor_value)
    if s_empty:
        return SingleValueResolution(SINGLE_VALUE_ONE, other_value)
    if survivor_value.strip() == other_value.strip():  # type: ignore[union-attr]
        return SingleValueResolution(SINGLE_VALUE_EQUAL, survivor_value)
    return SingleValueResolution(SINGLE_VALUE_CONFLICT, None)


def resolve_sex(survivor_sex: Optional[str], other_sex: Optional[str]) -> SingleValueResolution:
    """Resolve ``sex``. Empty and ``U`` (unknown) count as no information."""

    def _known(value: Optional[str]) -> Optional[str]:
        if is_blank(value):
            return None
        stripped = value.strip()  # type: ignore[union-attr]
        return None if stripped.upper() == "U" else stripped

    s = _known(survivor_sex)
    o = _known(other_sex)
    if s is None and o is None:
        return SingleValueResolution(SINGLE_VALUE_BOTH_EMPTY, None)
    if o is None:
        return SingleValueResolution(SINGLE_VALUE_ONE, s)
    if s is None:
        return SingleValueResolution(SINGLE_VALUE_ONE, o)
    if s == o:
        return SingleValueResolution(SINGLE_VALUE_EQUAL, s)
    return SingleValueResolution(SINGLE_VALUE_CONFLICT, None)


def notes_separator(other_name: str, other_id: str) -> str:
    """The visible separator line placed between concatenated notes."""
    return f"--- Anteckningar från {other_name} ({other_id}) ---"


def concatenate_notes(
    survivor_notes: Optional[str],
    other_notes: Optional[str],
    other_name: str,
    other_id: str,
) -> str:
    """Concatenate notes with a blank line, a visible separator and a blank line.

    If either side is blank the other side is returned unchanged, with no
    separator.
    """
    s_empty = is_blank(survivor_notes)
    o_empty = is_blank(other_notes)
    if s_empty and o_empty:
        return ""
    if o_empty:
        return survivor_notes  # type: ignore[return-value]
    if s_empty:
        return other_notes  # type: ignore[return-value]
    if survivor_notes.strip() == other_notes.strip():  # type: ignore[union-attr]
        return survivor_notes  # type: ignore[return-value]
    return f"{survivor_notes}\n\n{notes_separator(other_name, other_id)}\n\n{other_notes}"


def resolve_notes(
    survivor_notes: Optional[str],
    other_notes: Optional[str],
    other_name: str,
    other_id: str,
    mode: str = NOTES_CONCATENATE,
) -> str:
    """Resolve notes with the user's mode (default: concatenate).

    A blank side never overwrites a non-blank one, whatever the mode.
    """
    s_empty = is_blank(survivor_notes)
    o_empty = is_blank(other_notes)
    if s_empty and o_empty:
        return ""
    if o_empty:
        return survivor_notes  # type: ignore[return-value]
    if s_empty:
        return other_notes  # type: ignore[return-value]
    if mode == NOTES_KEEP_SURVIVOR:
        return survivor_notes  # type: ignore[return-value]
    if mode == NOTES_KEEP_OTHER:
        return other_notes  # type: ignore[return-value]
    return concatenate_notes(survivor_notes, other_notes, other_name, other_id)


# ---------------------------------------------------------------------------
# Names (21.8 to 21.10)
# ---------------------------------------------------------------------------


def name_identity(name: Name) -> tuple[str, str, str, Optional[str]]:
    """Identity of a name entry: (given, surname, type, event_id).

    The strings are stripped; the tilltalsnamn marker ``*`` is not removed.
    """
    return (name.given.strip(), name.surname.strip(), name.type, name.event_id)


def union_names(
    survivor_names: Sequence[Name],
    other_names: Sequence[Name],
    primary: Optional[Name | tuple] = None,
) -> list[Name]:
    """Union of two name lists.

    The survivor's names come first in order, followed by the other person's
    names that are not identical (by :func:`name_identity`) to an earlier one.
    Entries with equal strings but another type or event_id are all kept.
    When *primary* (a ``Name`` or an identity tuple) matches an entry, that
    entry is moved to index 0 and the rest keep their relative order. Without
    *primary* the order is not rearranged. Input names are copied.
    """
    merged: list[Name] = []
    seen: set[tuple] = set()
    for name in list(survivor_names) + list(other_names):
        identity = name_identity(name)
        if identity in seen:
            continue
        seen.add(identity)
        merged.append(replace(name))

    if primary is not None:
        wanted = name_identity(primary) if isinstance(primary, Name) else primary
        for index, name in enumerate(merged):
            if name_identity(name) == wanted:
                if index:
                    merged.insert(0, merged.pop(index))
                break
    return merged


# ---------------------------------------------------------------------------
# Event participants (21.12, 21.13)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParticipantRewrite:
    """Result of :func:`rewrite_participants`.

    ``participants`` is a new list. ``conflicting_roles`` is non-empty (roles
    in first-seen order) only when the entries resolving to the survivor carry
    different roles and no valid *chosen_role* was given; the kept entry then
    holds the first entry's role provisionally. ``removed`` counts the entries
    dropped by deduplication.
    """

    participants: list[Participant]
    conflicting_roles: tuple[str, ...]
    removed: int

    @property
    def has_conflict(self) -> bool:
        return bool(self.conflicting_roles)


def rewrite_participants(
    participants: Sequence[Participant],
    retired: str,
    survivor: str,
    chosen_role: Optional[str] = None,
) -> ParticipantRewrite:
    """Rewrite a participant list for a merge.

    Entries for *retired* or *survivor* form one group. One entry remains, at
    the position of the first group entry, with the survivor id. If all roles
    in the group are equal that role is kept. If they differ, *chosen_role*
    selects one of the roles present; otherwise a conflict is reported.
    Other participants are copied unchanged.
    """
    result: list[Participant] = []
    group_roles: list[str] = []
    group_index: Optional[int] = None

    for participant in participants:
        if participant.person_id in (retired, survivor):
            if group_index is None:
                group_index = len(result)
                result.append(Participant(person_id=survivor, role=participant.role))
            if participant.role not in group_roles:
                group_roles.append(participant.role)
        else:
            result.append(replace(participant))

    removed = 0
    if group_index is not None:
        total = sum(1 for p in participants if p.person_id in (retired, survivor))
        removed = total - 1

    conflicting: tuple[str, ...] = ()
    if len(group_roles) > 1:
        if chosen_role is not None and chosen_role in group_roles:
            result[group_index] = Participant(person_id=survivor, role=chosen_role)  # type: ignore[index]
        else:
            conflicting = tuple(group_roles)

    return ParticipantRewrite(result, conflicting, removed)


# ---------------------------------------------------------------------------
# Similar_Event_Rule (21.14, 21.15)
# ---------------------------------------------------------------------------

_PRECISION_RANK = {"year": 0, "month": 1, "day": 2}
_PRECISION_LENGTH = {"year": 4, "month": 7, "day": 10}


def _events_same_type(event_1: Event, event_2: Event) -> bool:
    if event_1.type != event_2.type:
        return False
    if event_1.type == "custom":
        return (event_1.custom_type_name or "") == (event_2.custom_type_name or "")
    return True


def _date_value(event: Event) -> Optional[str]:
    if event.date is None:
        return None
    value = event.date.value
    if date_span.precision_of(value) is None:
        return None
    return value.strip()


def _dates_compatible(value_1: str, value_2: str, max_day_distance: int) -> bool:
    p1 = date_span.precision_of(value_1)
    p2 = date_span.precision_of(value_2)
    if p1 is None or p2 is None:
        return False
    coarser = p1 if _PRECISION_RANK[p1] <= _PRECISION_RANK[p2] else p2
    length = _PRECISION_LENGTH[coarser]
    if value_1[:length] == value_2[:length]:
        return True
    if p1 == "day" and p2 == "day":
        day_1 = date_span.expand_iso(value_1).first  # type: ignore[union-attr]
        day_2 = date_span.expand_iso(value_2).first  # type: ignore[union-attr]
        return abs((day_1 - day_2).days) <= max_day_distance
    return False


def _place_id(event: Event) -> Optional[str]:
    if event.place is None or not event.place.place_id:
        return None
    return event.place.place_id


def is_similar_event_pair(event_1: Event, event_2: Event, max_day_distance: int = 365) -> bool:
    """Similar_Event_Rule: True only when type, dates and places all agree.

    (a) same type (custom type name too); (b) both dated with compatible dates:
    equal at the coarser shared precision, or both full dates at most
    *max_day_distance* days apart; (c) places do not contradict: at least one
    side has none, or both ids are equal.
    """
    if not _events_same_type(event_1, event_2):
        return False
    value_1 = _date_value(event_1)
    value_2 = _date_value(event_2)
    if value_1 is None or value_2 is None:
        return False
    if not _dates_compatible(value_1, value_2, max_day_distance):
        return False
    place_1 = _place_id(event_1)
    place_2 = _place_id(event_2)
    return place_1 is None or place_2 is None or place_1 == place_2


def find_similar_event_pairs(
    events_person_1: Sequence[Event], events_person_2: Sequence[Event]
) -> list[tuple[str, str]]:
    """Sorted ``(event_id_of_person_1, event_id_of_person_2)`` for similar pairs.

    Events of the same person are never compared. An event present in both
    lists (same id, shared by both persons) is skipped.
    """
    shared = {e.id for e in events_person_1} & {e.id for e in events_person_2}
    pairs: set[tuple[str, str]] = set()
    for event_1 in events_person_1:
        if event_1.id in shared:
            continue
        for event_2 in events_person_2:
            if event_2.id in shared:
                continue
            if is_similar_event_pair(event_1, event_2):
                pairs.add((event_1.id, event_2.id))
    return sorted(pairs)


# ---------------------------------------------------------------------------
# Link collapse (22.3, 22.9, 22.13, 23.2 to 23.4)
# ---------------------------------------------------------------------------


def collapse_linked_entities(
    entities: Sequence[LinkedEntity],
    retired: str,
    survivor: str,
    entity_type: str = "person",
) -> list[LinkedEntity]:
    """Rewrite person links to the survivor and collapse duplicates.

    Links of *entity_type* pointing at *retired* or *survivor* become one link
    to the survivor at the position of the first such link, with the first
    non-empty ``role`` in original order. Other links are copied unchanged.
    """
    result: list[LinkedEntity] = []
    index: Optional[int] = None
    role = ""
    for link in entities:
        if link.entity_type == entity_type and link.entity_id in (retired, survivor):
            if index is None:
                index = len(result)
                result.append(LinkedEntity(entity_type, survivor, ""))
            if not role and not is_blank(link.role):
                role = link.role
        else:
            result.append(replace(link))
    if index is not None:
        result[index] = LinkedEntity(entity_type, survivor, role)
    return result


def collapse_id_list(ids: Sequence[str], retired: str, survivor: str) -> list[str]:
    """Replace *retired* by *survivor* and keep each survivor once.

    Used for ``mentioned_person_ids`` and ``DnaCluster.person_ids``: the
    survivor stays at the first position where either id occurred and the
    order of the other entries is preserved. Other duplicates are untouched.
    """
    result: list[str] = []
    placed = False
    for value in ids:
        if value in (retired, survivor):
            if not placed:
                result.append(survivor)
                placed = True
        else:
            result.append(value)
    return result


def rewrite_annotations(
    annotations: Sequence[Annotation], retired: str, survivor: str
) -> list[Annotation]:
    """Rewrite person annotations; annotations are kept separate, never collapsed."""
    return [
        replace(a, entity_id=survivor)
        if a.entity_type == "person" and a.entity_id == retired
        else replace(a)
        for a in annotations
    ]


@dataclass(frozen=True)
class ParentChildLinkCollapse:
    """Result of :func:`collapse_parent_child_links`.

    ``type_conflicts`` lists ``(child_id, parent_id, types)`` for each child and
    parent pair that keeps links with different ``parentage_type`` values
    (Merge_Warning, not blocking); ``collapsed`` counts removed duplicates.
    """

    links: list[ParentChildLink]
    type_conflicts: list[tuple[str, Optional[str], tuple[str, ...]]]
    collapsed: int


def collapse_parent_child_links(
    links: Sequence[ParentChildLink], retired: str, survivor: str
) -> ParentChildLinkCollapse:
    """Rewrite ids in parent-child links and collapse equivalent ones.

    Links with the same child, parent and ``parentage_type`` collapse to the
    first. Links for the same pair with different types are all kept and the
    pair is reported once in ``type_conflicts`` (types in first-seen order).
    """
    result: list[ParentChildLink] = []
    seen: set[tuple] = set()
    types_by_pair: dict[tuple, list[str]] = {}
    collapsed = 0
    for link in links:
        child = survivor if link.child_id == retired else link.child_id
        parent = survivor if link.parent_id == retired else link.parent_id
        key = (child, parent, link.parentage_type)
        types = types_by_pair.setdefault((child, parent), [])
        if key in seen:
            collapsed += 1
            continue
        seen.add(key)
        types.append(link.parentage_type)
        result.append(ParentChildLink(child, parent, link.parentage_type))
    conflicts = [
        (child, parent, tuple(types))
        for (child, parent), types in types_by_pair.items()
        if len(types) > 1
    ]
    return ParentChildLinkCollapse(result, conflicts, collapsed)
