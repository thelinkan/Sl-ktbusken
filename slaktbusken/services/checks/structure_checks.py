"""Structural person validation checks.

Implements checks for incest (sibling/parent-child partnerships), isolated
persons without family relations, ancestor cycles, and connectivity to the
main person in the family graph.
"""

from __future__ import annotations

from collections import deque
from collections import defaultdict

from slaktbusken.model.event import Event
from slaktbusken.model.family import Family
from slaktbusken.model.person import Person
from slaktbusken.persistence.settings_io import PersonCheckConfig
from slaktbusken.services.person_check_engine import (
    CheckContext,
    CheckFinding,
    format_person_display,
)

# Module-level cache for connectivity reachable set.
# Computed once per engine run (first call to check_connected_to_main_person).
_reachable_from_main: set[str] | None = None
_reachable_main_person_id: str | None = None


def _make_finding(person: Person, events: list[Event], message: str) -> CheckFinding:
    """Create a CheckFinding for the given person."""
    return CheckFinding(
        person_id=person.id,
        person_display=format_person_display(person, events),
        person_sex=person.sex,
        message=message,
    )


def _has_ancestor_cycle(person_id: str, parents_of: dict[str, list[str]]) -> bool:
    """Check if a person is their own ancestor via BFS upward.

    Returns True if person_id is found while traversing the parent graph
    starting from the person's parents.
    """
    visited: set[str] = set()
    queue = deque(parents_of.get(person_id, []))
    while queue:
        current = queue.popleft()
        if current == person_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        queue.extend(parents_of.get(current, []))
    return False


def _compute_reachable_from_main(
    main_person_id: str,
    context: CheckContext,
) -> set[str]:
    """BFS from main person through all family relationships.

    Builds an adjacency graph from families (partners + children) and
    returns all person IDs reachable from the main person.
    """
    # Build adjacency: person_id -> set of connected person_ids
    adjacency: dict[str, set[str]] = defaultdict(set)
    for family in _all_families_from_context(context):
        members: set[str] = set()
        for partner in family.partners:
            members.add(partner.person_id)
        for child_id in family.children:
            members.add(child_id)
        for m in members:
            adjacency[m].update(members - {m})

    # BFS from main person
    visited: set[str] = set()
    queue = deque([main_person_id])
    visited.add(main_person_id)
    while queue:
        current = queue.popleft()
        for neighbor in adjacency.get(current, set()):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)

    return visited


def _all_families_from_context(context: CheckContext) -> list[Family]:
    """Collect all unique families from the context's families_by_person map."""
    seen_ids: set[str] = set()
    families: list[Family] = []
    for family_list in context.families_by_person.values():
        for family in family_list:
            if family.id not in seen_ids:
                seen_ids.add(family.id)
                families.append(family)
    return families


def check_incest(
    person: Person,
    events: list[Event],
    families: list[Family],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Check if person is in a partnership with a sibling or parent/child (Req 9.1).

    For each family where this person is a partner, checks:
    1. If the other partner is a sibling (shares a parent via siblings_of)
    2. If one partner is a parent of the other (via parents_of)
    """
    if not config.logic_checks.no_incest:
        return []

    findings: list[CheckFinding] = []

    for family in families:
        # Only check families where this person is a partner
        is_partner = any(p.person_id == person.id for p in family.partners)
        if not is_partner:
            continue

        # Find the other partner(s)
        for partner_ref in family.partners:
            if partner_ref.person_id == person.id:
                continue

            other_id = partner_ref.person_id

            # Check 1: Are they siblings? (share a parent)
            siblings = context.siblings_of.get(person.id, set())
            if other_id in siblings:
                findings.append(_make_finding(
                    person, events,
                    "Partner delar förälder (incest)",
                ))
                continue

            # Check 2: Is one partner the parent of the other?
            person_parents = context.parents_of.get(person.id, [])
            other_parents = context.parents_of.get(other_id, [])

            if other_id in person_parents:
                # The other partner is a parent of this person
                findings.append(_make_finding(
                    person, events,
                    "Partner är förälder till den andre (incest)",
                ))
            elif person.id in other_parents:
                # This person is a parent of the other partner
                findings.append(_make_finding(
                    person, events,
                    "Partner är förälder till den andre (incest)",
                ))

    return findings


def check_must_have_relations(
    person: Person,
    events: list[Event],
    families: list[Family],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Check if person has no family relations at all (Req 9.2).

    Flags persons who do not appear in any Family (not as partner or child).
    """
    if not config.logic_checks.must_have_relations:
        return []

    person_families = context.families_by_person.get(person.id, [])
    if not person_families:
        return [_make_finding(
            person, events,
            "Personen saknar familjerelationer",
        )]

    return []


def check_no_ancestor_cycle(
    person: Person,
    events: list[Event],
    families: list[Family],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Check if person is their own ancestor (Req 9.3).

    BFS upward through parents_of. If the person is found in their own
    ancestor chain, a cycle exists.
    """
    if not config.logic_checks.no_ancestor_cycle:
        return []

    if _has_ancestor_cycle(person.id, context.parents_of):
        return [_make_finding(
            person, events,
            "Personen är sin egen förfader (cykel i släktträdet)",
        )]

    return []


def check_connected_to_main_person(
    person: Person,
    events: list[Event],
    families: list[Family],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Check if person is reachable from the main person (Req 9.6).

    BFS from the main person through all family relationships. Persons
    not in the reachable set are flagged.

    Skips check entirely if no main person is defined (Req 9.7).
    """
    if not config.logic_checks.connected_to_main_person:
        return []

    # Skip if no main person defined (Req 9.7)
    if context.main_person_id is None:
        return []

    global _reachable_from_main, _reachable_main_person_id

    # Compute reachable set once and cache it
    if (
        _reachable_from_main is None
        or _reachable_main_person_id != context.main_person_id
    ):
        _reachable_from_main = _compute_reachable_from_main(
            context.main_person_id, context
        )
        _reachable_main_person_id = context.main_person_id

    # Don't flag the main person themselves
    if person.id == context.main_person_id:
        return []

    if person.id not in _reachable_from_main:
        return [_make_finding(
            person, events,
            "Personen saknar koppling till huvudpersonen",
        )]

    return []


def reset_connectivity_cache() -> None:
    """Reset the module-level connectivity cache.

    Should be called before a new check run to ensure fresh computation.
    """
    global _reachable_from_main, _reachable_main_person_id
    _reachable_from_main = None
    _reachable_main_person_id = None


def check_structure(
    person: Person,
    events: list[Event],
    families: list[Family],
    config: PersonCheckConfig,
    context: CheckContext,
) -> list[CheckFinding]:
    """Run all structural checks for a person.

    This is the main entry point called by PersonCheckEngine.
    """
    findings: list[CheckFinding] = []

    findings.extend(check_incest(person, events, families, config, context))
    findings.extend(check_must_have_relations(person, events, families, config, context))
    findings.extend(check_no_ancestor_cycle(person, events, families, config, context))
    findings.extend(check_connected_to_main_person(person, events, families, config, context))

    return findings
