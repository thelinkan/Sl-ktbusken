"""Delete person service: consequence analysis and cascading deletion.

This module provides pure functions for analyzing the consequences of
deleting a person from a genealogy project, and the DeleteService class
that orchestrates the full deletion workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from collections import deque

from slaktbusken.model.event import Event
from slaktbusken.model.family import Family
from slaktbusken.model.project import ProjectData
from slaktbusken.relationship.graph_builder import build_relationship_graph

if TYPE_CHECKING:
    from slaktbusken.services.project_service import ProjectService


@dataclass
class DeletionConsequences:
    """Results of analyzing what a deletion would affect."""

    person_name: str
    exclusive_events: list[Event]
    family_events: list[Event]
    non_family_shared_events: list[Event]
    affected_families: list[Family]
    would_disconnect: bool
    disconnected_person_count: int


def classify_events(
    person_id: str, data: ProjectData
) -> tuple[list[Event], list[Event], list[Event]]:
    """Classify events into (exclusive, family, non_family_shared).

    Partitions all events where person_id is a participant (or events with
    empty participants) into three mutually exclusive categories:

    - Exclusive: all participants reference only person_id, or participants
      list is empty.
    - Family: event_id appears in any Family.event_ids AND person is a
      participant.
    - Non-family shared: person is one of 2+ participants and the event does
      not appear in any Family.event_ids.

    Args:
        person_id: The id of the person being evaluated.
        data: The project data containing events and families.

    Returns:
        A tuple of (exclusive_events, family_events, non_family_shared_events).
    """
    # Build a set of all event IDs referenced by any family.
    family_event_ids: set[str] = set()
    for family in data.families:
        family_event_ids.update(family.event_ids)

    exclusive: list[Event] = []
    family_events: list[Event] = []
    non_family_shared: list[Event] = []

    for event in data.events:
        # Check if person is a participant in this event.
        person_is_participant = any(
            p.person_id == person_id for p in event.participants
        )

        # Events with empty participants are treated as exclusive.
        if not event.participants:
            exclusive.append(event)
            continue

        # Skip events where the person is not a participant.
        if not person_is_participant:
            continue

        # Check if ALL participants reference only person_id.
        all_are_person = all(
            p.person_id == person_id for p in event.participants
        )

        if all_are_person:
            exclusive.append(event)
        elif event.id in family_event_ids:
            family_events.append(event)
        else:
            non_family_shared.append(event)

    return exclusive, family_events, non_family_shared


def find_affected_families(person_id: str, data: ProjectData) -> list[Family]:
    """Find all families where the person appears as partner, child, or in links.

    A family is affected if the person appears in any of:
    - The partners list (FamilyPartner.person_id)
    - The children list
    - A ParentChildLink (as child_id or parent_id)

    Args:
        person_id: The id of the person being evaluated.
        data: The project data containing families.

    Returns:
        A list of Family records that reference the person.
    """
    affected: list[Family] = []

    for family in data.families:
        # Check partners.
        if any(fp.person_id == person_id for fp in family.partners):
            affected.append(family)
            continue

        # Check children.
        if person_id in family.children:
            affected.append(family)
            continue

        # Check parent-child links.
        if any(
            link.child_id == person_id or link.parent_id == person_id
            for link in family.parent_child_links
        ):
            affected.append(family)

    return affected


def compute_disconnection(
    person_id: str, data: ProjectData
) -> tuple[bool, int]:
    """Check if removing person_id would disconnect the tree.

    Uses BFS from main_person_id on the relationship graph, excluding the
    target person, to determine if any remaining persons become unreachable.

    Returns (would_disconnect, disconnected_person_count).
    Skips check (returns (False, 0)) if main_person_id is None or equals
    person_id.

    Args:
        person_id: The id of the person being evaluated for deletion.
        data: The project data containing persons and families.

    Returns:
        A tuple of (would_disconnect, disconnected_person_count).
    """
    main_person_id = data.project.main_person_id

    # Skip conditions: no main person set, or deleting the main person itself.
    if main_person_id is None or person_id == main_person_id:
        return (False, 0)

    # Build the relationship graph from family data.
    graph = build_relationship_graph(data)

    # All person IDs in the project, excluding the person to be deleted.
    remaining_persons: set[str] = {
        p.id for p in data.persons if p.id != person_id
    }

    # If main_person_id is not in remaining persons, we can't perform BFS.
    if main_person_id not in remaining_persons:
        return (False, 0)

    # BFS from main_person_id, skipping edges to person_id.
    visited: set[str] = set()
    queue: deque[str] = deque()
    queue.append(main_person_id)
    visited.add(main_person_id)

    while queue:
        current = queue.popleft()
        for edge in graph.get_edges(current):
            if edge.target == person_id:
                continue
            if edge.target not in visited:
                visited.add(edge.target)
                queue.append(edge.target)

    # Only count persons that are both remaining AND in the graph.
    # Persons with no family connections won't appear in the graph at all,
    # so we only consider persons that exist in remaining_persons.
    reachable = visited & remaining_persons
    disconnected_count = len(remaining_persons) - len(reachable)

    return (disconnected_count > 0, disconnected_count)


def execute_person_deletion(person_id: str, data: ProjectData) -> None:
    """Remove person and cascade through all data structures.

    Mutates data in place. Order of operations:
    1. Remove exclusive events from data.events
    2. Remove family events from data.events
    3. Remove deleted event IDs from all family.event_ids
    4. Remove person's Participant from remaining shared events
    5. Remove events left with zero participants
    6. Remove person from family partners lists
    7. Remove person from family children lists
    8. Remove ParentChildLinks referencing person
    9. Remove empty families (zero partners AND zero children)
    10. Clean media: remove from mentioned_person_ids, linked_entities, annotations
    11. Remove person from data.persons
    """
    # Step 1 & 2: Classify events and collect IDs to remove.
    exclusive_events, family_events, _ = classify_events(person_id, data)

    deleted_event_ids: set[str] = set()
    for event in exclusive_events:
        deleted_event_ids.add(event.id)
    for event in family_events:
        deleted_event_ids.add(event.id)

    # Remove exclusive and family events from data.events.
    data.events = [e for e in data.events if e.id not in deleted_event_ids]

    # Step 3: Remove deleted event IDs from all family.event_ids.
    for family in data.families:
        family.event_ids = [
            eid for eid in family.event_ids if eid not in deleted_event_ids
        ]

    # Step 4: Remove person's Participant entry from remaining shared events.
    for event in data.events:
        event.participants = [
            p for p in event.participants if p.person_id != person_id
        ]

    # Step 5: Remove events left with zero participants.
    data.events = [e for e in data.events if len(e.participants) > 0]

    # Step 6: Remove person from family partners lists.
    for family in data.families:
        family.partners = [
            fp for fp in family.partners if fp.person_id != person_id
        ]

    # Step 7: Remove person from family children lists.
    for family in data.families:
        family.children = [
            child_id for child_id in family.children if child_id != person_id
        ]

    # Step 8: Remove ParentChildLinks referencing person.
    for family in data.families:
        family.parent_child_links = [
            link
            for link in family.parent_child_links
            if link.child_id != person_id and link.parent_id != person_id
        ]

    # Step 9: Remove empty families (zero partners AND zero children).
    data.families = [
        f for f in data.families if len(f.partners) > 0 or len(f.children) > 0
    ]

    # Step 10: Clean media references.
    for media_item in data.media:
        # Remove person_id from mentioned_person_ids.
        media_item.mentioned_person_ids = [
            pid for pid in media_item.mentioned_person_ids if pid != person_id
        ]
        # Remove LinkedEntity entries where entity_type=="person" and entity_id==person_id.
        media_item.linked_entities = [
            le
            for le in media_item.linked_entities
            if not (le.entity_type == "person" and le.entity_id == person_id)
        ]
        # Remove Annotation entries where entity_type=="person" and entity_id==person_id.
        media_item.annotations = [
            ann
            for ann in media_item.annotations
            if not (ann.entity_type == "person" and ann.entity_id == person_id)
        ]

    # Step 11: Remove person from data.persons.
    data.persons = [p for p in data.persons if p.id != person_id]


class DeleteService:
    """Service for deleting a person and cascading cleanup.

    Orchestrates the deletion workflow: checking eligibility, computing
    consequences (warnings for the UI), and executing the actual deletion
    with cascading cleanup.
    """

    def __init__(self, project_service: "ProjectService") -> None:
        self._project_service = project_service

    def can_delete(self, person_id: str) -> tuple[bool, str]:
        """Check if a person can be deleted.

        Returns (allowed, error_message). The error_message is an empty
        string when deletion is allowed.

        The main person (ProjectData.project.main_person_id) cannot be
        deleted.
        """
        data = self._project_service.data
        if data.project.main_person_id == person_id:
            return (False, "Huvudpersonen kan inte tas bort.")
        return (True, "")

    def compute_consequences(self, person_id: str) -> DeletionConsequences:
        """Analyze what would happen if the person were deleted.

        Orchestrates classify_events, find_affected_families, and
        compute_disconnection to build a full consequences report.
        """
        data = self._project_service.data

        # Extract person's primary display name.
        person = next((p for p in data.persons if p.id == person_id), None)
        if person is not None and person.names:
            name = person.names[0]
            person_name = f"{name.given} {name.surname}".strip()
        else:
            person_name = ""

        # Classify events.
        exclusive_events, family_events, non_family_shared_events = (
            classify_events(person_id, data)
        )

        # Find affected families.
        affected_families = find_affected_families(person_id, data)

        # Compute disconnection.
        would_disconnect, disconnected_person_count = compute_disconnection(
            person_id, data
        )

        return DeletionConsequences(
            person_name=person_name,
            exclusive_events=exclusive_events,
            family_events=family_events,
            non_family_shared_events=non_family_shared_events,
            affected_families=affected_families,
            would_disconnect=would_disconnect,
            disconnected_person_count=disconnected_person_count,
        )

    def execute_deletion(self, person_id: str) -> None:
        """Execute the deletion with all cascading cleanup.

        Calls execute_person_deletion to mutate ProjectData, then marks
        the project as dirty (unsaved changes).
        """
        data = self._project_service.data
        execute_person_deletion(person_id, data)
        self._project_service._dirty = True
