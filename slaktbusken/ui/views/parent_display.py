"""Shared parent-display resolver for the three diagram views.

Given a child, the current Show_Level, the child's per-connection override, and
the Parentage_Fallback flag, this module decides *which* parent links a diagram
should draw and *with which connection style*, and it reports that answer
**grouped by Parent_Set** with each set's cardinality. The three Diagram_Views
(:mod:`family_view`, :mod:`ancestry_view`, :mod:`descendants_view`) all route
through :func:`resolve_parent_display` so that the precedence rule
(override > show-level > fallback) and the single-parent rule hold identically
across views by construction (Requirement 4.6).

Precedence (Design Decision 6):

* A :class:`Connection_Override` for the child **wins** over the Show_Level
  (Req 5.2). Override values are ``"biological"`` / ``"foster"`` / ``"adoptive"``.
  An override naming a parent set the child *lacks* is ignored and the resolver
  falls through to the Show_Level (Req 5.6).
* Otherwise the Show_Level decides (Req 4.2–4.4): ``"biological"`` draws
  biological links; ``"non_biological"`` draws **both** foster and adoptive;
  ``"all"`` draws everything.
* The Parentage_Fallback applies **only** under Show_Level ``"biological"`` when
  the child has **no** biological parents and the fallback is enabled and no
  override is in force (Req 6.2). It then draws the child's non-biological
  parents instead of empty placeholders. Under fallback with both foster *and*
  adoptive parents present, **both** are drawn (Req 6.6).

Set grouping / cardinality (Requirement 3.8–3.10): the resolver groups the drawn
links by Parent_Set — the derived :class:`Family` a link belongs to — and marks
each set as a one-parent or two-parent set, and whether it is a *derived*
(foster/adoptive) set or a *biological pair*. This is what lets a view render a
one-parent derived set with no partner connector and no second-parent
placeholder, while a biological pair keeps its two-slot father/mother layout.

The resolver is **pure**: it imports the :class:`ConnectionType` enum from
:mod:`connection_line` but constructs no Qt graphics items and performs no I/O.
``FOSTER`` and ``ADOPTIVE`` are added to that enum by a concurrent task; this
module resolves them by name at call time (never defining a duplicate enum), so
it imports cleanly whether or not that task has landed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from slaktbusken.model.family import Family, ParentChildLink
from slaktbusken.ui.widgets.connection_line import ConnectionType

# Show_Level internal values (Requirement 4.1).
SHOW_BIOLOGICAL = "biological"
SHOW_NON_BIOLOGICAL = "non_biological"
SHOW_ALL = "all"

# Parentage_Type values this resolver reasons about.
_BIOLOGICAL = "biological"
_FOSTER = "foster"
_ADOPTIVE = "adoptive"
_NON_BIOLOGICAL = frozenset({_FOSTER, _ADOPTIVE})


def _connection_type_for(parentage_type: str) -> ConnectionType:
    """Map a link's ``parentage_type`` to its drawn :class:`ConnectionType`.

    Biological links draw with the existing solid ``PARENT_CHILD`` style; foster
    and adoptive links draw with the ``FOSTER`` / ``ADOPTIVE`` styles added to
    the enum by the visual-layer task. Those members are resolved by name so
    this module does not hard-depend on that task having landed; if a member is
    absent the link falls back to ``PARENT_CHILD`` rather than raising.
    """
    if parentage_type == _FOSTER:
        return getattr(ConnectionType, "FOSTER", ConnectionType.PARENT_CHILD)
    if parentage_type == _ADOPTIVE:
        return getattr(ConnectionType, "ADOPTIVE", ConnectionType.PARENT_CHILD)
    return ConnectionType.PARENT_CHILD


def link_identity(link: ParentChildLink) -> str:
    """Return a stable per-link identity key for connection-type lookup.

    A :class:`ParentChildLink` is an unhashable dataclass, so the per-link
    connection-type map is keyed by this string. The triple
    ``(child_id, parent_id, parentage_type)`` uniquely identifies a drawn link
    within a child's parent sets.
    """
    return f"{link.child_id}|{link.parent_id}|{link.parentage_type}"


@dataclass
class ParentSetDisplay:
    """One Parent_Set to draw, grouped from a single derived/biological family.

    A Parent_Set is the one or two parents taken together that a view renders as
    a unit. ``cardinality`` is the number of parents in the set (1 or 2). A
    *biological pair* (``is_derived`` False) keeps the two-slot father/mother
    layout and its placeholder for an unknown parent; a *derived* foster/adoptive
    set (``is_derived`` True) with ``cardinality == 1`` must be drawn as a single
    complete parent — no partner connector, no second-parent placeholder
    (Requirement 3.8–3.10).

    Attributes:
        family_id: The id of the :class:`Family` this set was grouped from, or
            ``None`` for a synthetic biological group with no backing family.
        parentage_type: The set's parentage type (``"biological"``, ``"foster"``
            or ``"adoptive"``). Every link in ``links`` shares it.
        connection_type: The :class:`ConnectionType` every link in the set draws
            with, chosen from ``parentage_type``.
        links: The drawn :class:`ParentChildLink` rows of this set.
        cardinality: The number of parents in the set (``len(links)``), 1 or 2.
        is_derived: ``True`` for a foster/adoptive set, ``False`` for a
            biological pair.
    """

    family_id: Optional[str]
    parentage_type: str
    connection_type: ConnectionType
    links: list[ParentChildLink]
    cardinality: int
    is_derived: bool


@dataclass
class ParentDisplay:
    """The resolver's answer: which parents to draw and how, grouped by set.

    ``sets`` is the primary, grouping-aware result each view iterates to obey the
    single-parent rule. ``links_to_draw`` and ``connection_type_for`` are a flat
    convenience view over the same links for the simplest consumers (keyed by
    :func:`link_identity`). The three are always consistent: every link in
    ``links_to_draw`` belongs to exactly one set in ``sets``.

    Attributes:
        sets: The drawn Parent_Sets, biological groups first then derived sets,
            in the order the input families were supplied.
        links_to_draw: Every drawn link, flattened across ``sets``.
        connection_type_for: Per-link :class:`ConnectionType`, keyed by
            :func:`link_identity`.
    """

    sets: list[ParentSetDisplay] = field(default_factory=list)
    links_to_draw: list[ParentChildLink] = field(default_factory=list)
    connection_type_for: dict[str, ConnectionType] = field(default_factory=dict)


def _family_parentage_type(family: Family, child_id: str) -> Optional[str]:
    """Return the single parentage type of ``family``'s links for ``child_id``.

    A derived (foster/adoptive) or biological family holds links of one
    parentage type for a given child. Returns ``None`` when the family records
    no link for this child (so it contributes no Parent_Set).
    """
    types = {
        link.parentage_type
        for link in family.parent_child_links
        if link.child_id == child_id
    }
    if not types:
        return None
    # A well-formed family carries one parentage type per child; if somehow
    # mixed, prefer biological (the spine) so it is never hidden.
    if _BIOLOGICAL in types:
        return _BIOLOGICAL
    # Deterministic pick among non-biological (foster before adoptive).
    if _FOSTER in types:
        return _FOSTER
    return next(iter(sorted(types)))


def _links_for_child(family: Family, child_id: str) -> list[ParentChildLink]:
    """Return ``family``'s parent-child links naming ``child_id``, in order."""
    return [
        link for link in family.parent_child_links if link.child_id == child_id
    ]


def _make_set(family: Family, child_id: str) -> Optional[ParentSetDisplay]:
    """Build a :class:`ParentSetDisplay` from one family, or ``None``.

    Returns ``None`` when the family contributes no drawable link for the child
    (no links, or every link's ``parent_id`` is empty).
    """
    parentage_type = _family_parentage_type(family, child_id)
    if parentage_type is None:
        return None
    links = [
        link
        for link in _links_for_child(family, child_id)
        if link.parentage_type == parentage_type and link.parent_id is not None
    ]
    if not links:
        return None
    is_derived = parentage_type in _NON_BIOLOGICAL
    return ParentSetDisplay(
        family_id=family.id,
        parentage_type=parentage_type,
        connection_type=_connection_type_for(parentage_type),
        links=links,
        cardinality=len(links),
        is_derived=is_derived,
    )


def _assemble(sets: list[ParentSetDisplay]) -> ParentDisplay:
    """Flatten resolved Parent_Sets into a :class:`ParentDisplay`."""
    links_to_draw: list[ParentChildLink] = []
    connection_type_for: dict[str, ConnectionType] = {}
    for parent_set in sets:
        for link in parent_set.links:
            links_to_draw.append(link)
            connection_type_for[link_identity(link)] = parent_set.connection_type
    return ParentDisplay(
        sets=sets,
        links_to_draw=links_to_draw,
        connection_type_for=connection_type_for,
    )


def resolve_parent_display(
    child_id: str,
    parent_families: list[Family],
    show_level: str,
    override: Optional[str],
    fallback_enabled: bool,
) -> ParentDisplay:
    """Resolve which of a child's parent sets to draw and with which style.

    Args:
        child_id: The person id of the child whose parents are being drawn.
        parent_families: Every :class:`Family` in which ``child_id`` is a child
            — biological families and derived foster/adoptive families alike.
            Each family is one Parent_Set; the resolver derives each family's
            parentage type and parent count from its links (so set grouping and
            cardinality come straight from the existing Family grouping, Design
            Decision 2). Families contributing no link for the child are ignored.
        show_level: The Show_Level: ``"biological"``, ``"non_biological"`` or
            ``"all"`` (Req 4.1). Unknown values are treated as ``"biological"``.
        override: The child's Connection_Override, one of ``"biological"`` /
            ``"foster"`` / ``"adoptive"``, or ``None`` for no override. An
            override naming a parent set the child lacks is ignored (Req 5.6).
        fallback_enabled: Whether the Parentage_Fallback is on (Req 6.1). Only
            consulted under Show_Level ``"biological"`` with no override and no
            biological parents.

    Returns:
        A :class:`ParentDisplay` grouping the drawn links by Parent_Set with each
        set's cardinality and derived/biological nature, plus a flat
        ``links_to_draw`` and a per-link ``connection_type_for`` lookup.
    """
    # Build one candidate Parent_Set per supplied family, in input order.
    all_sets: list[ParentSetDisplay] = []
    for family in parent_families:
        parent_set = _make_set(family, child_id)
        if parent_set is not None:
            all_sets.append(parent_set)

    def _of_type(parentage_type: str) -> list[ParentSetDisplay]:
        return [s for s in all_sets if s.parentage_type == parentage_type]

    biological = _of_type(_BIOLOGICAL)
    foster = _of_type(_FOSTER)
    adoptive = _of_type(_ADOPTIVE)
    non_biological = [s for s in all_sets if s.is_derived]

    # --- Precedence 1: a valid Connection_Override wins (Req 5.2, 5.6). ------
    if override is not None:
        chosen = {
            _BIOLOGICAL: biological,
            _FOSTER: foster,
            _ADOPTIVE: adoptive,
        }.get(override)
        if chosen:
            # Override names a set the child actually has: honour it.
            return _assemble(chosen)
        # Override names a missing set: ignore it and fall through to the
        # Show_Level (Req 5.6) by leaving ``override`` resolved to nothing.

    # --- Precedence 2: the Show_Level (Req 4.2–4.4). -------------------------
    if show_level == SHOW_ALL:
        return _assemble(all_sets)

    if show_level == SHOW_NON_BIOLOGICAL:
        # Draw both foster and adoptive, biological omitted (Req 4.3).
        return _assemble(non_biological)

    # Default / "biological": draw biological links (Req 4.2), subject to the
    # Parentage_Fallback (Req 6.2).
    if biological:
        return _assemble(biological)

    # --- Precedence 3: Parentage_Fallback (Req 6.2, 6.6). --------------------
    # Only when biological is shown, the child has no biological parents, the
    # fallback is enabled, and no override is in force. Draws both foster and
    # adoptive when both are present (Req 6.6).
    if fallback_enabled and non_biological:
        return _assemble(non_biological)

    # Biological shown, no biological parents, fallback off (or no non-biological
    # parents): draw nothing, so the view shows its empty biological placeholders
    # (Req 6.3).
    return _assemble([])
