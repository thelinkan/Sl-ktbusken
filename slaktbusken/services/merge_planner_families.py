"""Planning of families and relatives, and reconciliation with the sync.

Qt-free. Registered through :func:`merge_planner.plan_step` in the slots
``families`` (before the sync) and ``reconcile`` (after the real
``sync_parentage_links`` has run on the structural-clone sync view), see
Requirements 23, 24, 25 and 26.2 and design sections 10.12 and 10.13.

``families`` rewires the families that reference the retired person on deep
clones (partners, children, parent-child links), collapses duplicates, checks
self-relationships and records the intended links. ``reconcile`` reads the
synchronised view only: it compares intended and synchronised links, warns
about different-type links for one pair, detects cycles through the survivor,
warns about equivalent families (which stay separate, nothing is combined) and
runs ``validate_family`` on every changed family.

Relatives with different ids are never paired, merged or flagged as
duplicates. The only thing said about same-named relatives is the
informational note of Requirement 24.5, produced by
:func:`same_name_relatives_note`.
"""

from __future__ import annotations

from collections import deque
from typing import Iterable, Optional

from slaktbusken.model.family import Family
from slaktbusken.model.person import Person
from slaktbusken.model.validators import validate_family
from slaktbusken.services import merge_rules as rules
from slaktbusken.services import person_reference_index as pri
from slaktbusken.services.merge_planner import (
    SEVERITY_BLOCKING,
    SEVERITY_WARNING,
    Disposition,
    PlanContext,
    plan_step,
)
from slaktbusken.services.merge_planner_person import MISSING_NAME, _display_name

SAME_NAME_NOTE = (
    "Flera släktingar har samma namn; de förblir separata personer om du inte "
    "slår samman dem särskilt."
)

_PLACEMENT_START_TYPES = frozenset({"foster_home", "adoption"})

_STATE_INTENDED = "families.intended_links"
_STATE_AFFECTED = "families.affected_ids"
_STATE_RETIRED_PAIRS = "families.retired_pairs"


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def same_name_relatives_note(relatives: Iterable[Person]) -> Optional[str]:
    """The note of Requirement 24.5, or ``None``.

    Groups the given relatives by the case-insensitive display name and
    returns the note once when any group holds two or more different ids. It
    names nobody, pairs nobody and creates no candidates (24.8).
    """
    ids_by_name: dict[str, set[str]] = {}
    for person in relatives:
        name = _display_name(person)
        if name == MISSING_NAME:
            continue
        ids_by_name.setdefault(name.casefold(), set()).add(person.id)
    if any(len(ids) >= 2 for ids in ids_by_name.values()):
        return SAME_NAME_NOTE
    return None


def find_cycle_through(
    parents_by_child: dict[str, set[str]], start: str
) -> Optional[list[str]]:
    """Shortest ancestry path ``[start, ..., start]`` or ``None``.

    Upward search from *start* over all parentage types (design 10.12.8).
    Self loops are the business of the self-relationship check and are
    ignored here.
    """
    prev: dict[str, str] = {}
    seen = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for parent in sorted(parents_by_child.get(node, ())):
            if parent == node:
                continue
            if parent == start:
                chain = [node]
                while chain[-1] != start:
                    chain.append(prev[chain[-1]])
                chain.reverse()
                return chain + [start]
            if parent not in seen:
                seen.add(parent)
                prev[parent] = node
                queue.append(parent)
    return None


def _map(value: Optional[str], retired: str, survivor: str) -> Optional[str]:
    return survivor if value == retired else value


def _link_key(family_id: str, link) -> tuple:
    return (family_id, link.child_id, link.parent_id, link.parentage_type)


def _names(ctx: PlanContext) -> dict[str, Person]:
    return {p.id: p for p in ctx.data.persons}


def _label(persons: dict[str, Person], pid: Optional[str]) -> str:
    if pid is None:
        return "okänd förälder"
    person = persons.get(pid)
    return f"{_display_name(person)} ({pid})" if person is not None else pid


def _lost_information(original: Family, clone: Family, s: str, r: str) -> list[str]:
    """Descriptions of original information the rewired clone no longer holds."""
    lost: list[str] = []
    partner_ids = [p.person_id for p in clone.partners]
    for partner in original.partners:
        if _map(partner.person_id, r, s) not in partner_ids:
            lost.append(f"partner {partner.person_id}")
    for child in original.children:
        if _map(child, r, s) not in clone.children:
            lost.append(f"barn {child}")
    kept = {(l.child_id, l.parent_id, l.parentage_type) for l in clone.parent_child_links}
    for link in original.parent_child_links:
        key = (
            _map(link.child_id, r, s), _map(link.parent_id, r, s), link.parentage_type,
        )
        if key not in kept:
            lost.append(f"länk {link.child_id}→{link.parent_id} ({link.parentage_type})")
    return lost


# ---------------------------------------------------------------------------
# Step "families": rewire on clones (23.1 to 23.8, 24.x)
# ---------------------------------------------------------------------------


def _affected_families(ctx: PlanContext) -> list[Family]:
    keys = (
        "family.partners", "family.children",
        "family.parent_child_links.child", "family.parent_child_links.parent",
    )
    ids: set[int] = set()
    for key in keys:
        ids.update(id(f) for f in ctx.index.references(key, ctx.retired_id))
    return [f for f in ctx.data.families if id(f) in ids]


def _plan_relatives(ctx: PlanContext) -> None:
    """List the relatives as separate persons and add the 24.5 note once."""
    s, r = ctx.survivor_id, ctx.retired_id
    persons = _names(ctx)
    relative_ids: list[str] = []
    seen: set[str] = set()
    for fam in ctx.data.families:
        members = [p.person_id for p in fam.partners] + list(fam.children)
        members += [l.parent_id for l in fam.parent_child_links if l.parent_id]
        if s not in members and r not in members:
            continue
        for pid in members:
            if pid not in (s, r) and pid not in seen and pid in persons:
                seen.add(pid)
                relative_ids.append(pid)
    for pid in relative_ids:
        ctx.add_item(
            "relatives", pid, _label(persons, pid), Disposition.LEFT_SEPARATE,
            "Släkting med eget id; lämnas som egen person",
        )
    note = same_name_relatives_note(persons[pid] for pid in relative_ids)
    if note is not None:
        ctx.add_item(
            "relatives", "same_name_note", "Släktingar med samma namn",
            Disposition.LEFT_SEPARATE, note,
        )


@plan_step("families")
def plan_families(ctx: PlanContext) -> None:
    s, r = ctx.survivor_id, ctx.retired_id
    persons = _names(ctx)
    s_label, r_label = _label(persons, s), _label(persons, r)
    intended: set[tuple] = set()
    affected_ids: set[str] = set()
    retired_pairs: set[tuple] = set()
    reported_self: set[tuple] = set()

    # Pairs that involve the retired person anywhere, for the different-type
    # warning of 23.4 (evaluated on the synchronised view).
    for fam in ctx.data.families:
        for link in fam.parent_child_links:
            if r in (link.child_id, link.parent_id) and link.parent_id is not None:
                retired_pairs.add((_map(link.child_id, r, s), _map(link.parent_id, r, s)))

    for fam in _affected_families(ctx):
        affected_ids.add(fam.id)
        partner_ids = [p.person_id for p in fam.partners]
        blocked = False

        if s in partner_ids and r in partner_ids:
            blocked = True
            ctx.add_conflict(
                SEVERITY_BLOCKING, "self_partner", "families",
                f"{s_label} och {r_label} är båda partner i familjen {fam.id}; "
                "efter sammanslagningen skulle personen vara sin egen partner.",
                (fam.id, s, r),
            )
        if (s in partner_ids and r in fam.children) or (r in partner_ids and s in fam.children):
            blocked = True
            ctx.add_conflict(
                SEVERITY_BLOCKING, "self_parent_child", "families",
                f"{s_label} och {r_label} är partner respektive barn i familjen {fam.id}; "
                "efter sammanslagningen skulle personen vara sitt eget barn.",
                (fam.id, s, r),
            )
        if s in fam.children and r in fam.children:
            ctx.add_conflict(
                SEVERITY_WARNING, "duplicate_child", "families",
                f"Båda personerna är barn i familjen {fam.id}; de slås ihop till ett barn.",
                (fam.id, s, r),
            )

        clone: Family = ctx.work.edit("families", fam.id)
        for partner in clone.partners:
            if partner.person_id == r:
                partner.person_id = s
        children: list[str] = []
        for child in fam.children:
            mapped = _map(child, r, s)
            if mapped not in children:
                children.append(mapped)  # type: ignore[arg-type]
        clone.children = children
        collapse = rules.collapse_parent_child_links(fam.parent_child_links, r, s)
        clone.parent_child_links = collapse.links

        for link, orig in zip_links(collapse.links, fam.parent_child_links, r, s):
            if (
                link.parent_id is not None
                and link.child_id == link.parent_id
                and orig.child_id != orig.parent_id
                and (fam.id, link.child_id) not in reported_self
            ):
                reported_self.add((fam.id, link.child_id))
                blocked = True
                ctx.add_conflict(
                    SEVERITY_BLOCKING, "self_parent_child", "families",
                    f"{s_label} skulle bli sin egen förälder i familjen {fam.id} "
                    f"(länk mellan {_label(persons, orig.child_id)} och "
                    f"{_label(persons, orig.parent_id)}).",
                    (fam.id, s, r),
                )

        lost = _lost_information(fam, clone, s, r)
        if lost:
            blocked = True
            ctx.add_conflict(
                SEVERITY_BLOCKING, "family_information_loss", "families",
                f"Familjen {fam.id} kan inte skrivas om utan att information går "
                f"förlorad: {', '.join(lost)}.",
                (fam.id,),
            )

        intended.update(_link_key(fam.id, l) for l in clone.parent_child_links)

        collapsed = (
            collapse.collapsed or len(children) < len(fam.children)
        )
        if blocked:
            disp, detail = Disposition.FLAGGED, "Blockerande konflikt, se konflikter"
        elif collapsed:
            disp, detail = Disposition.COMBINED, "Dubbla länkar och barn slås ihop till en"
        else:
            disp, detail = Disposition.REASSIGNED, "Familjen skrivs om till behållen person"
        ctx.add_item("families", fam.id, f"Familj {fam.id}", disp, detail)

    ctx.state[_STATE_INTENDED] = intended
    ctx.state[_STATE_AFFECTED] = affected_ids
    ctx.state[_STATE_RETIRED_PAIRS] = retired_pairs
    _plan_relatives(ctx)


def zip_links(new_links, old_links, retired: str, survivor: str):
    """Pairs each collapsed link with an original link that maps onto it."""
    originals = {}
    for old in old_links:
        key = (_map(old.child_id, retired, survivor), _map(old.parent_id, retired, survivor),
               old.parentage_type)
        originals.setdefault(key, old)
    for link in new_links:
        yield link, originals[(link.child_id, link.parent_id, link.parentage_type)]


# ---------------------------------------------------------------------------
# Step "reconcile": checks on the synchronised view (23.3 to 23.13, 26.2)
# ---------------------------------------------------------------------------


def _family_text(view_persons: dict[str, Person], fam: Family) -> str:
    names = [_label(view_persons, p.person_id) for p in fam.partners]
    return ", ".join(names) if names else "inga partner"


@plan_step("reconcile")
def reconcile_families(ctx: PlanContext) -> None:
    view = ctx.sync_view
    if view is None:  # pragma: no cover - build_plan always sets the view
        return
    s, r = ctx.survivor_id, ctx.retired_id
    data = ctx.data
    persons = _names(ctx)
    originals = {f.id: f for f in data.families}
    synced_links = {_link_key(f.id, l) for f in view.families for l in f.parent_child_links}

    # 10.13: links the plan retains must survive the sync unchanged.
    for key in sorted(ctx.state.get(_STATE_INTENDED, ()), key=str):
        if key in synced_links:
            continue
        fam_id, child, parent, ptype = key
        ctx.add_conflict(
            SEVERITY_BLOCKING, "sync_drops_link", "families",
            f"Synkroniseringen av fosterhem och adoptioner skulle ta bort eller ändra "
            f"länken {_label(persons, child)} → {_label(persons, parent)} "
            f"({ptype}) i familjen {fam_id}.",
            (fam_id, child or "", parent or ""),
        )

    # 23.4: several types for one child-parent pair stay as historical
    # assertions, one warning per pair.
    types_by_pair: dict[tuple, list[str]] = {}
    for fam in view.families:
        for link in fam.parent_child_links:
            if link.parent_id is None:
                continue
            types = types_by_pair.setdefault((link.child_id, link.parent_id), [])
            if link.parentage_type not in types:
                types.append(link.parentage_type)
    for pair in sorted(ctx.state.get(_STATE_RETIRED_PAIRS, ())):
        types = types_by_pair.get(pair, [])
        if len(types) > 1:
            ctx.add_conflict(
                SEVERITY_WARNING, "parentage_type_conflict", "families",
                f"{_label(persons, pair[0])} har flera relationer till "
                f"{_label(persons, pair[1])} av olika typ ({' och '.join(types)}); "
                "alla länkar behålls.",
                pair,
            )

    # 23.6: cycle through the survivor, all parentage types, any depth.
    parents_by_child: dict[str, set[str]] = {}
    for fam in view.families:
        for link in fam.parent_child_links:
            if link.parent_id is not None:
                parents_by_child.setdefault(link.child_id, set()).add(link.parent_id)
    cycle = find_cycle_through(parents_by_child, s)
    if cycle is not None:
        path = " → ".join(_label(persons, pid) for pid in cycle)
        ctx.add_conflict(
            SEVERITY_BLOCKING, "cycle", "families",
            f"Sammanslagningen skulle göra {_label(persons, s)} till sin egen "
            f"förfader: {path}.",
            tuple(dict.fromkeys(cycle)),
        )

    # 23.9, 23.10: equivalent families stay separate, one warning per pair.
    event_types = {e.id: e.type for e in view.events}
    affected = ctx.state.get(_STATE_AFFECTED, set())
    candidates = [
        f for f in view.families
        if any(p.person_id == s for p in f.partners)
        and not any(event_types.get(eid) in _PLACEMENT_START_TYPES for eid in f.event_ids)
    ]
    for i, first in enumerate(candidates):
        for second in candidates[i + 1:]:
            if first.id not in affected and second.id not in affected:
                continue
            set_1 = frozenset(p.person_id for p in first.partners)
            if set_1 and set_1 == frozenset(p.person_id for p in second.partners):
                ctx.add_conflict(
                    SEVERITY_WARNING, "duplicate_family", "families",
                    f"Familjerna {first.id} och {second.id} har samma partner efter "
                    f"sammanslagningen: {_family_text(persons, first)}. "
                    "De behålls som separata familjer.",
                    (first.id, second.id),
                )

    # 23.13: validate every changed family of the synchronised view.
    valid_ids = {p.id for p in view.persons}
    for fam in view.families:
        if fam.id in originals and fam == originals[fam.id]:
            continue
        for error in validate_family(fam, valid_ids):
            ctx.add_conflict(
                SEVERITY_BLOCKING, "family_validation", "families",
                f"Familjen {fam.id} klarar inte valideringen: {error}", (fam.id,),
            )

    # Ledger: the expected counts follow the synchronised view exactly.
    for key, after, before in (
        ("families", len(view.families), len(data.families)),
        (
            "parent_child_links",
            sum(len(f.parent_child_links) for f in view.families),
            sum(len(f.parent_child_links) for f in data.families),
        ),
    ):
        ctx.ledger_deltas[key] = after - before


# ---------------------------------------------------------------------------
# Handler registration (inventory rows this module applies)
# ---------------------------------------------------------------------------

_HANDLERS = {
    "family.partners": plan_families,
    "family.children": plan_families,
    "family.parent_child_links.child": plan_families,
    "family.parent_child_links.parent": plan_families,
}

for _key, _func in _HANDLERS.items():
    pri.register_handler(_key, _func)
