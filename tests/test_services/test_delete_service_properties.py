"""Property-based tests for DeleteService.

Feature: delete-person, Property 7: Event Classification Is Exhaustive and Correct

Validates: Requirements 1.1, 2.3, 2.4
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.event import Event, Participant
from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.delete_service import classify_events


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_VALID_SEX_VALUES = ["M", "F", "X", "U"]
_EVENT_TYPES = ["birth", "death", "marriage", "baptism", "burial", "census"]


def _make_person(person_id: str) -> Person:
    """Create a Person with a minimal name entry."""
    return Person(
        id=person_id,
        sex="U",
        names=[Name(type="birth", given="Test", surname="Person")],
    )


@st.composite
def event_classification_scenario(draw: st.DrawFn) -> tuple[ProjectData, str]:
    """Generate a ProjectData with a target person and various event configurations.

    Ensures:
    - At least one person (the target) exists
    - Events reference actual person IDs from the persons list
    - Some events are in family.event_ids, some are not
    - Mix of exclusive (single participant), shared (multiple participants),
      and family events

    Returns (project_data, target_person_id).
    """
    # Generate 2-5 persons
    num_persons = draw(st.integers(min_value=2, max_value=5))
    person_ids = [f"person_{i}" for i in range(1, num_persons + 1)]
    persons = [_make_person(pid) for pid in person_ids]

    # The target person is always person_1
    target_id = "person_1"

    # Generate events with controlled participant configurations
    num_events = draw(st.integers(min_value=1, max_value=8))
    events: list[Event] = []
    family_event_ids: list[str] = []

    for i in range(num_events):
        event_id = f"event_{i + 1}"
        event_type = draw(st.sampled_from(_EVENT_TYPES))

        # Decide what kind of event this is:
        # 0 = exclusive to target, 1 = shared with target, 2 = not involving target,
        # 3 = empty participants
        event_kind = draw(st.sampled_from([0, 1, 2, 3]))

        if event_kind == 0:
            # Exclusive: only target as participant (possibly repeated)
            num_roles = draw(st.integers(min_value=1, max_value=2))
            participants = [
                Participant(person_id=target_id, role="principal")
                for _ in range(num_roles)
            ]
        elif event_kind == 1:
            # Shared: target + at least one other person
            other_ids = [pid for pid in person_ids if pid != target_id]
            num_others = draw(st.integers(min_value=1, max_value=min(3, len(other_ids))))
            chosen_others = draw(
                st.lists(
                    st.sampled_from(other_ids),
                    min_size=num_others,
                    max_size=num_others,
                    unique=True,
                )
            )
            participants = [Participant(person_id=target_id, role="principal")]
            for oid in chosen_others:
                participants.append(Participant(person_id=oid, role="witness"))
        elif event_kind == 2:
            # Not involving target at all
            other_ids = [pid for pid in person_ids if pid != target_id]
            num_participants = draw(st.integers(min_value=1, max_value=min(3, len(other_ids))))
            chosen = draw(
                st.lists(
                    st.sampled_from(other_ids),
                    min_size=num_participants,
                    max_size=num_participants,
                    unique=True,
                )
            )
            participants = [Participant(person_id=pid, role="principal") for pid in chosen]
        else:
            # Empty participants
            participants = []

        events.append(
            Event(id=event_id, type=event_type, participants=participants)
        )

        # Decide if this event should be a family event (in some family's event_ids)
        is_family_event = draw(st.booleans())
        if is_family_event:
            family_event_ids.append(event_id)

    # Create 0-2 families, distributing family_event_ids among them
    num_families = draw(st.integers(min_value=0, max_value=2))
    families: list[Family] = []

    if num_families > 0 and family_event_ids:
        # Split family_event_ids across families
        for fam_idx in range(num_families):
            fam_id = f"family_{fam_idx + 1}"
            # Each family gets a subset of the family event IDs
            fam_events = [
                eid for j, eid in enumerate(family_event_ids)
                if j % num_families == fam_idx
            ]
            # Partners from available person IDs
            partner_ids = draw(
                st.lists(
                    st.sampled_from(person_ids),
                    min_size=1,
                    max_size=2,
                    unique=True,
                )
            )
            partners = [
                FamilyPartner(person_id=pid, role="partner") for pid in partner_ids
            ]
            families.append(
                Family(
                    id=fam_id,
                    partners=partners,
                    children=[],
                    event_ids=fam_events,
                )
            )
    elif num_families > 0:
        # Families with no events
        for fam_idx in range(num_families):
            fam_id = f"family_{fam_idx + 1}"
            partner_ids = draw(
                st.lists(
                    st.sampled_from(person_ids),
                    min_size=1,
                    max_size=2,
                    unique=True,
                )
            )
            partners = [
                FamilyPartner(person_id=pid, role="partner") for pid in partner_ids
            ]
            families.append(
                Family(
                    id=fam_id,
                    partners=partners,
                    children=[],
                    event_ids=[],
                )
            )

    project_data = ProjectData(
        project=ProjectMetadata(title="Property Test"),
        persons=persons,
        families=families,
        events=events,
    )

    return project_data, target_id


# ---------------------------------------------------------------------------
# Property 7: Event Classification Is Exhaustive and Correct
# ---------------------------------------------------------------------------


class TestEventClassificationExhaustiveAndCorrect:
    """Feature: delete-person, Property 7: Event Classification Is Exhaustive and Correct

    For any valid ProjectData and any person in it, the event classification
    function shall partition all events involving that person into exactly three
    mutually exclusive categories (exclusive, family, non-family shared), and:
    exclusive events have only the target person as participant (or empty
    participants), family events appear in at least one Family.event_ids, and
    non-family shared events have 2+ participants including the target and do
    not appear in any Family.event_ids.

    **Validates: Requirements 1.1, 2.3, 2.4**
    """

    @given(scenario=event_classification_scenario())
    @settings(max_examples=100, deadline=None)
    def test_event_classification_is_exhaustive_and_correct(
        self, scenario: tuple[ProjectData, str]
    ) -> None:
        """Property 7: Event Classification Is Exhaustive and Correct.

        Feature: delete-person, Property 7: Event Classification Is Exhaustive and Correct
        **Validates: Requirements 1.1, 2.3, 2.4**
        """
        project_data, target_id = scenario

        exclusive, family_events, non_family_shared = classify_events(
            target_id, project_data
        )

        # Build the set of all family event IDs across all families
        all_family_event_ids: set[str] = set()
        for family in project_data.families:
            all_family_event_ids.update(family.event_ids)

        # Collect event IDs from each category
        exclusive_ids = {e.id for e in exclusive}
        family_ids = {e.id for e in family_events}
        non_family_shared_ids = {e.id for e in non_family_shared}

        # --- Assertion 1: Three lists are mutually exclusive ---
        assert exclusive_ids.isdisjoint(family_ids), (
            f"Overlap between exclusive and family: "
            f"{exclusive_ids & family_ids}"
        )
        assert exclusive_ids.isdisjoint(non_family_shared_ids), (
            f"Overlap between exclusive and non-family shared: "
            f"{exclusive_ids & non_family_shared_ids}"
        )
        assert family_ids.isdisjoint(non_family_shared_ids), (
            f"Overlap between family and non-family shared: "
            f"{family_ids & non_family_shared_ids}"
        )

        # --- Assertion 2: Collectively exhaustive ---
        # All events involving the target (or with empty participants) should
        # be covered by the three categories
        involving_target: set[str] = set()
        for event in project_data.events:
            if not event.participants:
                involving_target.add(event.id)
            elif any(p.person_id == target_id for p in event.participants):
                involving_target.add(event.id)

        classified_ids = exclusive_ids | family_ids | non_family_shared_ids
        assert classified_ids == involving_target, (
            f"Classification is not exhaustive.\n"
            f"  Missing from classification: {involving_target - classified_ids}\n"
            f"  Extra in classification: {classified_ids - involving_target}"
        )

        # --- Assertion 3: Exclusive events have only target as participant ---
        for event in exclusive:
            if event.participants:
                assert all(
                    p.person_id == target_id for p in event.participants
                ), (
                    f"Exclusive event '{event.id}' has non-target participant: "
                    f"{[p.person_id for p in event.participants]}"
                )

        # --- Assertion 4: Family events appear in at least one Family.event_ids ---
        for event in family_events:
            assert event.id in all_family_event_ids, (
                f"Family event '{event.id}' not found in any Family.event_ids"
            )

        # --- Assertion 5: Non-family shared events have 2+ participants,
        #     target is one of them, event NOT in any Family.event_ids ---
        for event in non_family_shared:
            assert len(event.participants) >= 2, (
                f"Non-family shared event '{event.id}' has fewer than 2 "
                f"participants: {len(event.participants)}"
            )
            assert any(
                p.person_id == target_id for p in event.participants
            ), (
                f"Non-family shared event '{event.id}' does not include "
                f"target '{target_id}' as participant"
            )
            assert event.id not in all_family_event_ids, (
                f"Non-family shared event '{event.id}' appears in "
                f"Family.event_ids but should not"
            )


# ---------------------------------------------------------------------------
# Strategies for Property 8
# ---------------------------------------------------------------------------

from collections import deque

from slaktbusken.model.project import ProjectMetadata
from slaktbusken.services.delete_service import compute_disconnection
from slaktbusken.relationship.graph_builder import build_relationship_graph


@st.composite
def connected_graph_scenario(draw: st.DrawFn) -> tuple[ProjectData, str, str]:
    """Generate a connected ProjectData graph with a main person and a target person.

    Generates 3-6 persons connected through families via partner and
    parent-child links. A main_person_id is set to one person, and a target
    person (different from main) is chosen for disconnection testing.

    The graph structure is explicitly controlled so we can independently
    verify whether removal of the target disconnects remaining persons from
    the main person.

    Returns (project_data, main_person_id, target_person_id).
    """
    # Generate 3-6 persons
    num_persons = draw(st.integers(min_value=3, max_value=6))
    person_ids = [f"p_{i}" for i in range(num_persons)]
    persons = [_make_person(pid) for pid in person_ids]

    # Choose main person and target person (different from main)
    main_idx = draw(st.integers(min_value=0, max_value=num_persons - 1))
    main_person_id = person_ids[main_idx]

    target_idx = draw(
        st.integers(min_value=0, max_value=num_persons - 1).filter(
            lambda i: i != main_idx
        )
    )
    target_person_id = person_ids[target_idx]

    # Generate families to connect persons.
    # We create 1 to (num_persons - 1) families.
    # Each family connects persons via partner links and/or parent-child links.
    num_families = draw(st.integers(min_value=1, max_value=num_persons - 1))
    families: list[Family] = []

    for fam_idx in range(num_families):
        fam_id = f"fam_{fam_idx}"

        # Choose connection type: partners, parent-child, or both
        connection_type = draw(st.sampled_from(["partners", "parent_child", "both"]))

        if connection_type == "partners":
            # Pick 2 distinct persons as partners
            partner_indices = draw(
                st.lists(
                    st.integers(min_value=0, max_value=num_persons - 1),
                    min_size=2,
                    max_size=2,
                    unique=True,
                )
            )
            partners = [
                FamilyPartner(person_id=person_ids[i], role="partner")
                for i in partner_indices
            ]
            families.append(
                Family(
                    id=fam_id,
                    partners=partners,
                    children=[],
                    parent_child_links=[],
                    event_ids=[],
                )
            )

        elif connection_type == "parent_child":
            # Pick a parent and a child (distinct)
            parent_idx = draw(st.integers(min_value=0, max_value=num_persons - 1))
            child_idx = draw(
                st.integers(min_value=0, max_value=num_persons - 1).filter(
                    lambda i, p=parent_idx: i != p
                )
            )
            parent_id = person_ids[parent_idx]
            child_id = person_ids[child_idx]

            from slaktbusken.model.family import ParentChildLink

            partners = [FamilyPartner(person_id=parent_id, role="partner")]
            families.append(
                Family(
                    id=fam_id,
                    partners=partners,
                    children=[child_id],
                    parent_child_links=[
                        ParentChildLink(
                            child_id=child_id,
                            parent_id=parent_id,
                            parentage_type="biological",
                        )
                    ],
                    event_ids=[],
                )
            )

        else:  # "both"
            # Two partners + a child linked to one of them
            partner_indices = draw(
                st.lists(
                    st.integers(min_value=0, max_value=num_persons - 1),
                    min_size=2,
                    max_size=2,
                    unique=True,
                )
            )
            # Pick a child distinct from both partners
            available_for_child = [
                i for i in range(num_persons) if i not in partner_indices
            ]
            if available_for_child:
                child_idx = draw(st.sampled_from(available_for_child))
            else:
                # Fall back: just use partners, no child
                child_idx = None

            from slaktbusken.model.family import ParentChildLink

            partners = [
                FamilyPartner(person_id=person_ids[i], role="partner")
                for i in partner_indices
            ]

            if child_idx is not None:
                child_id = person_ids[child_idx]
                parent_id = person_ids[partner_indices[0]]
                families.append(
                    Family(
                        id=fam_id,
                        partners=partners,
                        children=[child_id],
                        parent_child_links=[
                            ParentChildLink(
                                child_id=child_id,
                                parent_id=parent_id,
                                parentage_type="biological",
                            )
                        ],
                        event_ids=[],
                    )
                )
            else:
                families.append(
                    Family(
                        id=fam_id,
                        partners=partners,
                        children=[],
                        parent_child_links=[],
                        event_ids=[],
                    )
                )

    project_data = ProjectData(
        project=ProjectMetadata(title="Disconnection Test", main_person_id=main_person_id),
        persons=persons,
        families=families,
    )

    return project_data, main_person_id, target_person_id


# ---------------------------------------------------------------------------
# Property 8: Tree Disconnection Detection Correctness
# ---------------------------------------------------------------------------


class TestTreeDisconnectionDetectionCorrectness:
    """Feature: delete-person, Property 8: Tree Disconnection Detection Correctness

    For any valid ProjectData with main_person_id set (and target ≠ main person),
    the disconnection computation shall return true if and only if removing the
    target person from the relationship graph makes at least one remaining person
    unreachable from main_person_id via family partner and parent-child links.

    **Validates: Requirements 7.1**
    """

    @given(scenario=connected_graph_scenario())
    @settings(max_examples=100, deadline=None)
    def test_disconnection_detection_correctness(
        self, scenario: tuple[ProjectData, str, str]
    ) -> None:
        """Property 8: Tree Disconnection Detection Correctness.

        Feature: delete-person, Property 8: Tree Disconnection Detection Correctness
        **Validates: Requirements 7.1**
        """
        project_data, main_person_id, target_person_id = scenario

        # Call the function under test
        would_disconnect, disconnected_count = compute_disconnection(
            target_person_id, project_data
        )

        # --- Independent oracle: BFS from main_person_id, skipping target ---
        graph = build_relationship_graph(project_data)

        remaining_persons: set[str] = {
            p.id for p in project_data.persons if p.id != target_person_id
        }

        # BFS from main_person_id, skipping edges to target_person_id
        visited: set[str] = set()
        queue: deque[str] = deque()

        if main_person_id in remaining_persons:
            queue.append(main_person_id)
            visited.add(main_person_id)

        while queue:
            current = queue.popleft()
            for edge in graph.get_edges(current):
                if edge.target == target_person_id:
                    continue
                if edge.target not in visited:
                    visited.add(edge.target)
                    queue.append(edge.target)

        reachable = visited & remaining_persons
        expected_disconnected_count = len(remaining_persons) - len(reachable)
        expected_would_disconnect = expected_disconnected_count > 0

        # --- Assertions ---
        assert would_disconnect == expected_would_disconnect, (
            f"Disconnection mismatch for target='{target_person_id}', "
            f"main='{main_person_id}'.\n"
            f"  Function returned would_disconnect={would_disconnect}, "
            f"expected={expected_would_disconnect}.\n"
            f"  Remaining persons: {remaining_persons}\n"
            f"  Reachable from main (excluding target): {reachable}\n"
            f"  Disconnected count: function={disconnected_count}, "
            f"expected={expected_disconnected_count}"
        )

        assert disconnected_count == expected_disconnected_count, (
            f"Disconnected count mismatch for target='{target_person_id}', "
            f"main='{main_person_id}'.\n"
            f"  Function returned count={disconnected_count}, "
            f"expected={expected_disconnected_count}"
        )

    def test_skip_when_main_person_is_none(self) -> None:
        """When main_person_id is None, compute_disconnection returns (False, 0).

        **Validates: Requirements 7.1**
        """
        persons = [_make_person("p_0"), _make_person("p_1")]
        project_data = ProjectData(
            project=ProjectMetadata(title="No Main Person"),
            persons=persons,
            families=[
                Family(
                    id="fam_0",
                    partners=[
                        FamilyPartner(person_id="p_0", role="partner"),
                        FamilyPartner(person_id="p_1", role="partner"),
                    ],
                    children=[],
                    event_ids=[],
                )
            ],
        )
        # main_person_id is None by default
        assert project_data.project.main_person_id is None

        result = compute_disconnection("p_1", project_data)
        assert result == (False, 0)

    def test_skip_when_target_equals_main_person(self) -> None:
        """When target == main_person_id, compute_disconnection returns (False, 0).

        **Validates: Requirements 7.1**
        """
        persons = [_make_person("p_0"), _make_person("p_1")]
        project_data = ProjectData(
            project=ProjectMetadata(title="Target Is Main", main_person_id="p_0"),
            persons=persons,
            families=[
                Family(
                    id="fam_0",
                    partners=[
                        FamilyPartner(person_id="p_0", role="partner"),
                        FamilyPartner(person_id="p_1", role="partner"),
                    ],
                    children=[],
                    event_ids=[],
                )
            ],
        )

        result = compute_disconnection("p_0", project_data)
        assert result == (False, 0)


# ---------------------------------------------------------------------------
# Strategies for Property 1
# ---------------------------------------------------------------------------

from slaktbusken.model.family import ParentChildLink
from slaktbusken.services.delete_service import execute_person_deletion


@st.composite
def deletable_person_scenario(draw: st.DrawFn) -> tuple[ProjectData, str]:
    """Generate a valid ProjectData with a deletable person (not main person).

    The target person is embedded in various event/family configurations:
    - Participates in exclusive events (only the target)
    - Participates in shared events (target + others)
    - Appears as a family partner
    - Appears as a family child
    - Appears in ParentChildLinks as child or parent

    Returns (project_data, target_person_id).
    """
    # Generate 3-6 persons
    num_persons = draw(st.integers(min_value=3, max_value=6))
    person_ids = [f"person_{i}" for i in range(num_persons)]
    persons = [_make_person(pid) for pid in person_ids]

    # Main person is always person_0; target is always person_1 (deletable)
    main_person_id = "person_0"
    target_id = "person_1"
    other_ids = [pid for pid in person_ids if pid != target_id]

    # --- Generate events ---
    events: list[Event] = []
    event_counter = 0

    # Generate 0-3 exclusive events for target (only target as participant)
    num_exclusive = draw(st.integers(min_value=0, max_value=3))
    for _ in range(num_exclusive):
        event_counter += 1
        events.append(
            Event(
                id=f"evt_{event_counter}",
                type="birth",
                participants=[Participant(person_id=target_id, role="principal")],
            )
        )

    # Generate 0-3 shared events (target + at least one other)
    num_shared = draw(st.integers(min_value=0, max_value=3))
    for _ in range(num_shared):
        event_counter += 1
        num_others = draw(st.integers(min_value=1, max_value=min(3, len(other_ids))))
        chosen_others = draw(
            st.lists(
                st.sampled_from(other_ids),
                min_size=num_others,
                max_size=num_others,
                unique=True,
            )
        )
        participants = [Participant(person_id=target_id, role="principal")]
        for oid in chosen_others:
            participants.append(Participant(person_id=oid, role="witness"))
        events.append(
            Event(
                id=f"evt_{event_counter}",
                type="census",
                participants=participants,
            )
        )

    # Generate 0-2 events that do NOT involve target (for non-interference)
    num_uninvolved = draw(st.integers(min_value=0, max_value=2))
    for _ in range(num_uninvolved):
        event_counter += 1
        num_participants = draw(
            st.integers(min_value=1, max_value=min(2, len(other_ids)))
        )
        chosen = draw(
            st.lists(
                st.sampled_from(other_ids),
                min_size=num_participants,
                max_size=num_participants,
                unique=True,
            )
        )
        events.append(
            Event(
                id=f"evt_{event_counter}",
                type="marriage",
                participants=[
                    Participant(person_id=pid, role="principal") for pid in chosen
                ],
            )
        )

    # --- Generate families ---
    families: list[Family] = []
    family_counter = 0

    # Generate 0-2 families where target is a partner
    num_partner_families = draw(st.integers(min_value=0, max_value=2))
    for _ in range(num_partner_families):
        family_counter += 1
        # Pick 1 other person as co-partner
        co_partner = draw(st.sampled_from(other_ids))
        partners = [
            FamilyPartner(person_id=target_id, role="partner"),
            FamilyPartner(person_id=co_partner, role="partner"),
        ]
        # Optionally add children (not the target)
        num_children = draw(st.integers(min_value=0, max_value=2))
        available_children = [pid for pid in other_ids if pid != co_partner]
        children: list[str] = []
        if available_children and num_children > 0:
            children = draw(
                st.lists(
                    st.sampled_from(available_children),
                    min_size=min(num_children, len(available_children)),
                    max_size=min(num_children, len(available_children)),
                    unique=True,
                )
            )
        # Optionally assign some events as family events
        family_event_ids: list[str] = []
        if events:
            use_family_events = draw(st.booleans())
            if use_family_events:
                family_event_ids = draw(
                    st.lists(
                        st.sampled_from([e.id for e in events]),
                        min_size=0,
                        max_size=min(2, len(events)),
                        unique=True,
                    )
                )
        families.append(
            Family(
                id=f"fam_{family_counter}",
                partners=partners,
                children=children,
                parent_child_links=[],
                event_ids=family_event_ids,
            )
        )

    # Generate 0-2 families where target is a child
    num_child_families = draw(st.integers(min_value=0, max_value=2))
    for _ in range(num_child_families):
        family_counter += 1
        # Pick 1-2 parents from other_ids
        num_parents = draw(st.integers(min_value=1, max_value=min(2, len(other_ids))))
        parent_ids = draw(
            st.lists(
                st.sampled_from(other_ids),
                min_size=num_parents,
                max_size=num_parents,
                unique=True,
            )
        )
        partners = [
            FamilyPartner(person_id=pid, role="partner") for pid in parent_ids
        ]
        # Target is a child; also add a ParentChildLink
        parent_for_link = parent_ids[0]
        families.append(
            Family(
                id=f"fam_{family_counter}",
                partners=partners,
                children=[target_id],
                parent_child_links=[
                    ParentChildLink(
                        child_id=target_id,
                        parent_id=parent_for_link,
                        parentage_type="biological",
                    )
                ],
                event_ids=[],
            )
        )

    # Generate 0-1 families where target is a parent in a ParentChildLink
    num_parent_link_families = draw(st.integers(min_value=0, max_value=1))
    for _ in range(num_parent_link_families):
        family_counter += 1
        # Target is a partner (parent) and has a child link
        available_children = [pid for pid in other_ids if pid != main_person_id]
        if available_children:
            child_for_link = draw(st.sampled_from(available_children))
            families.append(
                Family(
                    id=f"fam_{family_counter}",
                    partners=[FamilyPartner(person_id=target_id, role="partner")],
                    children=[child_for_link],
                    parent_child_links=[
                        ParentChildLink(
                            child_id=child_for_link,
                            parent_id=target_id,
                            parentage_type="biological",
                        )
                    ],
                    event_ids=[],
                )
            )

    # Generate 0-1 families with no connection to target (for non-interference)
    num_other_families = draw(st.integers(min_value=0, max_value=1))
    for _ in range(num_other_families):
        family_counter += 1
        if len(other_ids) >= 2:
            partner_pair = draw(
                st.lists(
                    st.sampled_from(other_ids),
                    min_size=2,
                    max_size=2,
                    unique=True,
                )
            )
            families.append(
                Family(
                    id=f"fam_{family_counter}",
                    partners=[
                        FamilyPartner(person_id=pid, role="partner")
                        for pid in partner_pair
                    ],
                    children=[],
                    parent_child_links=[],
                    event_ids=[],
                )
            )

    project_data = ProjectData(
        project=ProjectMetadata(
            title="Property 1 Test", main_person_id=main_person_id
        ),
        persons=persons,
        families=families,
        events=events,
    )

    return project_data, target_id


# ---------------------------------------------------------------------------
# Property 1: No Dangling Person References After Deletion
# ---------------------------------------------------------------------------


class TestNoDanglingReferencesAfterDeletion:
    """Feature: delete-person, Property 1: No Dangling Person References After Deletion

    For any valid ProjectData containing a deletable person (not main person),
    after executing deletion of that person, no Event shall contain a Participant
    with person_id equal to the deleted person's id, no Family shall contain a
    FamilyPartner with that person_id, no Family shall contain that id in its
    children list, and no ParentChildLink shall have child_id or parent_id equal
    to that id.

    **Validates: Requirements 1.2, 2.1, 3.1, 3.3, 4.1, 4.2, 4.3, 8.1, 8.2, 8.3, 8.4**
    """

    @given(scenario=deletable_person_scenario())
    @settings(max_examples=100, deadline=None)
    def test_no_dangling_references_after_deletion(
        self, scenario: tuple[ProjectData, str]
    ) -> None:
        """Property 1: No Dangling Person References After Deletion.

        Feature: delete-person, Property 1: No Dangling Person References After Deletion
        **Validates: Requirements 1.2, 2.1, 3.1, 3.3, 4.1, 4.2, 4.3, 8.1, 8.2, 8.3, 8.4**
        """
        project_data, target_id = scenario

        # Execute deletion
        execute_person_deletion(target_id, project_data)

        # --- Assertion 1: No Event.participants contains target_id ---
        for event in project_data.events:
            assert not any(
                p.person_id == target_id for p in event.participants
            ), (
                f"Event '{event.id}' still has participant referencing "
                f"deleted person '{target_id}': "
                f"{[p.person_id for p in event.participants]}"
            )

        # --- Assertion 2: No Family.partners contains target_id ---
        for family in project_data.families:
            assert not any(
                fp.person_id == target_id for fp in family.partners
            ), (
                f"Family '{family.id}' still has partner referencing "
                f"deleted person '{target_id}': "
                f"{[fp.person_id for fp in family.partners]}"
            )

        # --- Assertion 3: No Family.children contains target_id ---
        for family in project_data.families:
            assert target_id not in family.children, (
                f"Family '{family.id}' still has '{target_id}' in children list: "
                f"{family.children}"
            )

        # --- Assertion 4: No ParentChildLink references target_id ---
        for family in project_data.families:
            for link in family.parent_child_links:
                assert link.child_id != target_id, (
                    f"Family '{family.id}' has ParentChildLink with "
                    f"child_id='{target_id}'"
                )
                assert link.parent_id != target_id, (
                    f"Family '{family.id}' has ParentChildLink with "
                    f"parent_id='{target_id}'"
                )


# ---------------------------------------------------------------------------
# Strategies for Property 2
# ---------------------------------------------------------------------------

import copy

from slaktbusken.model.media import Annotation, LinkedEntity, MediaItem
from slaktbusken.services.delete_service import execute_person_deletion


@st.composite
def media_integrity_scenario(draw: st.DrawFn) -> tuple[ProjectData, str]:
    """Generate ProjectData with media items referencing a deletable person.

    Ensures:
    - At least 2 persons exist (target is not main person)
    - MediaItems exist that reference the target person via:
      - mentioned_person_ids containing the person's id
      - linked_entities with entity_type="person" and entity_id=person's id
      - annotations with entity_type="person" and entity_id=person's id
    - Some media items may also reference other persons (to verify selective removal)

    Returns (project_data, target_person_id).
    """
    # Generate 2-5 persons
    num_persons = draw(st.integers(min_value=2, max_value=5))
    person_ids = [f"person_{i}" for i in range(1, num_persons + 1)]
    persons = [_make_person(pid) for pid in person_ids]

    # The target person is always person_1 (not main person)
    target_id = "person_1"
    main_id = "person_2"  # main person is someone else

    # Generate 1-4 media items
    num_media = draw(st.integers(min_value=1, max_value=4))
    media_items: list[MediaItem] = []

    for i in range(num_media):
        media_id = f"media_{i + 1}"

        # Decide which persons are mentioned in this media item
        # Target is always mentioned in at least the first media item
        include_target = (i == 0) or draw(st.booleans())

        # Build mentioned_person_ids
        mentioned_person_ids: list[str] = []
        if include_target:
            mentioned_person_ids.append(target_id)
        # Optionally add other persons
        other_ids = [pid for pid in person_ids if pid != target_id]
        if other_ids:
            num_others = draw(st.integers(min_value=0, max_value=min(2, len(other_ids))))
            for j in range(num_others):
                mentioned_person_ids.append(other_ids[j % len(other_ids)])

        # Build linked_entities
        linked_entities: list[LinkedEntity] = []
        if include_target:
            linked_entities.append(
                LinkedEntity(entity_type="person", entity_id=target_id, role="subject")
            )
        # Optionally add other linked entities (person or non-person)
        num_extra_le = draw(st.integers(min_value=0, max_value=2))
        for j in range(num_extra_le):
            le_type = draw(st.sampled_from(["person", "place", "source"]))
            if le_type == "person" and other_ids:
                le_id = draw(st.sampled_from(other_ids))
            else:
                le_id = f"entity_{j}"
            linked_entities.append(
                LinkedEntity(entity_type=le_type, entity_id=le_id, role="reference")
            )

        # Build annotations
        annotations: list[Annotation] = []
        if include_target:
            annotations.append(
                Annotation(
                    x=draw(st.floats(min_value=0.0, max_value=1.0)),
                    y=draw(st.floats(min_value=0.0, max_value=1.0)),
                    width=draw(st.floats(min_value=0.01, max_value=1.0)),
                    height=draw(st.floats(min_value=0.01, max_value=1.0)),
                    entity_type="person",
                    entity_id=target_id,
                )
            )
        # Optionally add other annotations
        num_extra_ann = draw(st.integers(min_value=0, max_value=2))
        for j in range(num_extra_ann):
            ann_type = draw(st.sampled_from(["person", "place"]))
            if ann_type == "person" and other_ids:
                ann_id = draw(st.sampled_from(other_ids))
            else:
                ann_id = f"ann_entity_{j}"
            annotations.append(
                Annotation(
                    x=draw(st.floats(min_value=0.0, max_value=1.0)),
                    y=draw(st.floats(min_value=0.0, max_value=1.0)),
                    width=draw(st.floats(min_value=0.01, max_value=1.0)),
                    height=draw(st.floats(min_value=0.01, max_value=1.0)),
                    entity_type=ann_type,
                    entity_id=ann_id,
                )
            )

        # Build mentioned_names (these must remain unchanged after deletion)
        num_names = draw(st.integers(min_value=0, max_value=3))
        mentioned_names = [f"Name_{k}" for k in range(num_names)]

        media_items.append(
            MediaItem(
                id=media_id,
                type="image",
                file=f"/path/to/{media_id}.jpg",
                title=f"Media {i + 1}",
                mentioned_person_ids=mentioned_person_ids,
                linked_entities=linked_entities,
                annotations=annotations,
                mentioned_names=mentioned_names,
            )
        )

    project_data = ProjectData(
        project=ProjectMetadata(title="Media Integrity Test", main_person_id=main_id),
        persons=persons,
        families=[],
        media=media_items,
    )

    return project_data, target_id


# ---------------------------------------------------------------------------
# Property 2: Media Integrity After Deletion
# ---------------------------------------------------------------------------


class TestMediaIntegrityAfterDeletion:
    """Feature: delete-person, Property 2: Media Integrity After Deletion

    For any valid ProjectData with media items referencing a person, after
    executing deletion of that person: the media list length remains unchanged,
    the person's id is removed from mentioned_person_ids, linked_entities
    (where entity_type=="person"), and annotations (where entity_type=="person"),
    and all mentioned_names lists remain identical to their pre-deletion state.

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**
    """

    @given(scenario=media_integrity_scenario())
    @settings(max_examples=100, deadline=None)
    def test_media_integrity_after_deletion(
        self, scenario: tuple[ProjectData, str]
    ) -> None:
        """Property 2: Media Integrity After Deletion.

        Feature: delete-person, Property 2: Media Integrity After Deletion
        **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**
        """
        project_data, target_id = scenario

        # Snapshot pre-deletion state
        pre_media_count = len(project_data.media)
        pre_mentioned_names = [
            copy.deepcopy(media_item.mentioned_names)
            for media_item in project_data.media
        ]

        # Execute deletion
        execute_person_deletion(target_id, project_data)

        # --- Assertion 1: Media list length unchanged (Req 5.1) ---
        assert len(project_data.media) == pre_media_count, (
            f"Media list length changed after deletion: "
            f"before={pre_media_count}, after={len(project_data.media)}"
        )

        # --- Assertion 2: No mentioned_person_ids contains person_id (Req 5.2) ---
        for media_item in project_data.media:
            assert target_id not in media_item.mentioned_person_ids, (
                f"MediaItem '{media_item.id}' still has target '{target_id}' "
                f"in mentioned_person_ids: {media_item.mentioned_person_ids}"
            )

        # --- Assertion 3: No linked_entities has entity_type=="person" and
        #     entity_id==person_id (Req 5.3) ---
        for media_item in project_data.media:
            for le in media_item.linked_entities:
                assert not (le.entity_type == "person" and le.entity_id == target_id), (
                    f"MediaItem '{media_item.id}' still has LinkedEntity "
                    f"referencing target: entity_type='{le.entity_type}', "
                    f"entity_id='{le.entity_id}'"
                )

        # --- Assertion 4: No annotations has entity_type=="person" and
        #     entity_id==person_id (Req 5.4) ---
        for media_item in project_data.media:
            for ann in media_item.annotations:
                assert not (ann.entity_type == "person" and ann.entity_id == target_id), (
                    f"MediaItem '{media_item.id}' still has Annotation "
                    f"referencing target: entity_type='{ann.entity_type}', "
                    f"entity_id='{ann.entity_id}'"
                )

        # --- Assertion 5: All mentioned_names identical to pre-deletion (Req 5.5) ---
        for idx, media_item in enumerate(project_data.media):
            assert media_item.mentioned_names == pre_mentioned_names[idx], (
                f"MediaItem '{media_item.id}' mentioned_names changed after "
                f"deletion: before={pre_mentioned_names[idx]}, "
                f"after={media_item.mentioned_names}"
            )


# ---------------------------------------------------------------------------
# Strategies for Property 3
# ---------------------------------------------------------------------------

from slaktbusken.services.delete_service import execute_person_deletion


@st.composite
def no_empty_families_scenario(draw: st.DrawFn) -> tuple[ProjectData, str]:
    """Generate a ProjectData with a target person in family memberships.

    Ensures:
    - At least 2 persons exist (target + others)
    - Target is NOT the main person
    - Target appears in family partners, children, or both
    - Families are structured so that removing the target MIGHT create an
      empty family (testing the edge case where target is the sole partner
      and the family has no children)

    Returns (project_data, target_person_id).
    """
    # Generate 2-6 persons
    num_persons = draw(st.integers(min_value=2, max_value=6))
    person_ids = [f"person_{i}" for i in range(1, num_persons + 1)]
    persons = [_make_person(pid) for pid in person_ids]

    # The target is always person_1 (not the main person)
    target_id = "person_1"
    # Main person is someone else
    main_person_id = "person_2"

    other_ids = [pid for pid in person_ids if pid != target_id]

    # Generate 1-4 families with controlled structure
    num_families = draw(st.integers(min_value=1, max_value=4))
    families: list[Family] = []

    for fam_idx in range(num_families):
        fam_id = f"fam_{fam_idx}"

        # Decide how the target is involved in this family
        # 0 = sole partner, no children (empty after removal)
        # 1 = sole partner, has children (not empty after removal)
        # 2 = one of multiple partners, no children
        # 3 = target is a child only
        # 4 = target not in this family at all
        involvement = draw(st.sampled_from([0, 1, 2, 3, 4]))

        if involvement == 0:
            # Target is the ONLY partner, family has NO children
            # This family SHOULD be removed after deletion (empty)
            partners = [FamilyPartner(person_id=target_id, role="partner")]
            children: list[str] = []

        elif involvement == 1:
            # Target is the ONLY partner, but family HAS children
            # Family should remain after deletion (has children)
            partners = [FamilyPartner(person_id=target_id, role="partner")]
            num_children = draw(st.integers(min_value=1, max_value=min(2, len(other_ids))))
            children = draw(
                st.lists(
                    st.sampled_from(other_ids),
                    min_size=num_children,
                    max_size=num_children,
                    unique=True,
                )
            )

        elif involvement == 2:
            # Target is one of multiple partners, no children
            # Family should remain (still has other partner)
            other_partner = draw(st.sampled_from(other_ids))
            partners = [
                FamilyPartner(person_id=target_id, role="partner"),
                FamilyPartner(person_id=other_partner, role="partner"),
            ]
            children = []

        elif involvement == 3:
            # Target is a child, partners are others
            # Family should remain (still has partners)
            num_partners = draw(st.integers(min_value=1, max_value=min(2, len(other_ids))))
            partner_ids = draw(
                st.lists(
                    st.sampled_from(other_ids),
                    min_size=num_partners,
                    max_size=num_partners,
                    unique=True,
                )
            )
            partners = [
                FamilyPartner(person_id=pid, role="partner") for pid in partner_ids
            ]
            # Include other children optionally
            available_children = [pid for pid in other_ids if pid not in partner_ids]
            extra_children = draw(
                st.lists(
                    st.sampled_from(available_children) if available_children else st.nothing(),
                    min_size=0,
                    max_size=min(2, len(available_children)),
                    unique=True,
                )
            ) if available_children else []
            children = [target_id] + extra_children

        else:
            # Target not involved — family has other partners/children
            num_partners = draw(st.integers(min_value=1, max_value=min(2, len(other_ids))))
            partner_ids = draw(
                st.lists(
                    st.sampled_from(other_ids),
                    min_size=num_partners,
                    max_size=num_partners,
                    unique=True,
                )
            )
            partners = [
                FamilyPartner(person_id=pid, role="partner") for pid in partner_ids
            ]
            children = []

        families.append(
            Family(
                id=fam_id,
                partners=partners,
                children=children,
                event_ids=[],
            )
        )

    # Ensure the target is in at least one family (as partner or child)
    target_in_family = any(
        any(fp.person_id == target_id for fp in f.partners) or target_id in f.children
        for f in families
    )
    if not target_in_family:
        # Add a family where target is a sole partner with no children
        # (edge case: should be removed)
        families.append(
            Family(
                id=f"fam_forced",
                partners=[FamilyPartner(person_id=target_id, role="partner")],
                children=[],
                event_ids=[],
            )
        )

    project_data = ProjectData(
        project=ProjectMetadata(title="No Empty Families Test", main_person_id=main_person_id),
        persons=persons,
        families=families,
        events=[],
    )

    return project_data, target_id


# ---------------------------------------------------------------------------
# Property 3: No Empty Families After Deletion
# ---------------------------------------------------------------------------


class TestNoEmptyFamiliesAfterDeletion:
    """Feature: delete-person, Property 3: No Empty Families After Deletion

    For any valid ProjectData containing a deletable person, after executing
    deletion, no Family remaining in ProjectData shall have both an empty
    partners list and an empty children list.

    **Validates: Requirements 1.5, 4.4**
    """

    @given(scenario=no_empty_families_scenario())
    @settings(max_examples=100, deadline=None)
    def test_no_empty_families_after_deletion(
        self, scenario: tuple[ProjectData, str]
    ) -> None:
        """Property 3: No Empty Families After Deletion.

        Feature: delete-person, Property 3: No Empty Families After Deletion
        **Validates: Requirements 1.5, 4.4**
        """
        project_data, target_id = scenario

        # Execute the deletion
        execute_person_deletion(target_id, project_data)

        # Assert: no remaining family has both empty partners AND empty children
        for family in project_data.families:
            assert len(family.partners) > 0 or len(family.children) > 0, (
                f"Family '{family.id}' is empty after deletion of "
                f"'{target_id}': partners={family.partners}, "
                f"children={family.children}"
            )


# ---------------------------------------------------------------------------
# Strategies for Property 10
# ---------------------------------------------------------------------------

from slaktbusken.services.delete_service import execute_person_deletion


@st.composite
def person_removal_scenario(draw: st.DrawFn) -> tuple[ProjectData, str]:
    """Generate a ProjectData with a target person suitable for deletion.

    Ensures:
    - At least 2 persons exist (target + at least one other)
    - The target person is NOT the main person
    - The target has various event/family configurations

    Returns (project_data, target_person_id).
    """
    # Generate 2-6 persons
    num_persons = draw(st.integers(min_value=2, max_value=6))
    person_ids = [f"person_{i}" for i in range(1, num_persons + 1)]
    persons = [_make_person(pid) for pid in person_ids]

    # Main person is always person_1; target is chosen from the rest
    main_person_id = "person_1"
    target_id = draw(st.sampled_from(person_ids[1:]))

    # Generate 0-4 events with various participant configurations
    num_events = draw(st.integers(min_value=0, max_value=4))
    events: list[Event] = []
    family_event_ids: list[str] = []

    for i in range(num_events):
        event_id = f"ev_{i + 1}"
        event_type = draw(st.sampled_from(_EVENT_TYPES))

        # Decide participant configuration:
        # 0 = exclusive to target, 1 = shared with target, 2 = not involving target
        event_kind = draw(st.sampled_from([0, 1, 2]))

        if event_kind == 0:
            # Exclusive: only target as participant
            participants = [Participant(person_id=target_id, role="principal")]
        elif event_kind == 1:
            # Shared: target + at least one other person
            other_ids = [pid for pid in person_ids if pid != target_id]
            chosen_other = draw(st.sampled_from(other_ids))
            participants = [
                Participant(person_id=target_id, role="principal"),
                Participant(person_id=chosen_other, role="witness"),
            ]
        else:
            # Not involving target
            other_ids = [pid for pid in person_ids if pid != target_id]
            chosen = draw(st.sampled_from(other_ids))
            participants = [Participant(person_id=chosen, role="principal")]

        events.append(Event(id=event_id, type=event_type, participants=participants))

        # Optionally mark as family event
        if draw(st.booleans()):
            family_event_ids.append(event_id)

    # Generate 0-2 families
    num_families = draw(st.integers(min_value=0, max_value=2))
    families: list[Family] = []

    for fam_idx in range(num_families):
        fam_id = f"fam_{fam_idx + 1}"
        # Pick 1-2 partners from person_ids
        partner_ids = draw(
            st.lists(
                st.sampled_from(person_ids),
                min_size=1,
                max_size=2,
                unique=True,
            )
        )
        partners = [
            FamilyPartner(person_id=pid, role="partner") for pid in partner_ids
        ]
        # Distribute family event IDs
        fam_events = [
            eid for j, eid in enumerate(family_event_ids)
            if j % max(num_families, 1) == fam_idx
        ]
        families.append(
            Family(
                id=fam_id,
                partners=partners,
                children=[],
                event_ids=fam_events,
            )
        )

    project_data = ProjectData(
        project=ProjectMetadata(
            title="Property 10 Test", main_person_id=main_person_id
        ),
        persons=persons,
        families=families,
        events=events,
    )

    return project_data, target_id


# ---------------------------------------------------------------------------
# Property 10: Deleted Person Is Removed From Persons List
# ---------------------------------------------------------------------------


class TestDeletedPersonIsRemovedFromPersonsList:
    """Feature: delete-person, Property 10: Deleted Person Is Removed From Persons List

    For any valid ProjectData containing a deletable person, after executing
    deletion, the person shall not appear in ProjectData.persons, and the
    persons list length shall be exactly one less than before deletion.

    **Validates: Requirements 1.2**
    """

    @given(scenario=person_removal_scenario())
    @settings(max_examples=100, deadline=None)
    def test_deleted_person_removal(
        self, scenario: tuple[ProjectData, str]
    ) -> None:
        """Property 10: Deleted Person Is Removed From Persons List.

        Feature: delete-person, Property 10: Deleted Person Is Removed From Persons List
        **Validates: Requirements 1.2**
        """
        project_data, target_id = scenario

        # Record original persons count
        original_count = len(project_data.persons)

        # Execute deletion
        execute_person_deletion(target_id, project_data)

        # Assertion 1: No person in data.persons has id equal to target
        remaining_ids = [p.id for p in project_data.persons]
        assert target_id not in remaining_ids, (
            f"Deleted person '{target_id}' still present in persons list. "
            f"Remaining IDs: {remaining_ids}"
        )

        # Assertion 2: Persons list length decreased by exactly one
        assert len(project_data.persons) == original_count - 1, (
            f"Expected persons list length {original_count - 1}, "
            f"got {len(project_data.persons)}. "
            f"Original count: {original_count}, target: '{target_id}'"
        )


# ---------------------------------------------------------------------------
# Strategies for Property 4
# ---------------------------------------------------------------------------

import copy

from slaktbusken.services.delete_service import execute_person_deletion


@st.composite
def removed_family_events_scenario(
    draw: st.DrawFn,
) -> tuple[ProjectData, str]:
    """Generate ProjectData where deleting target causes families to be removed.

    Ensures:
    - At least 2 persons exist (target + at least one other)
    - Target person is NOT the main person
    - At least one family exists where target is the sole partner AND has no
      children (so the family becomes empty and is removed during deletion)
    - That family references event_ids for events whose participants include
      OTHER persons (so the events should be preserved after deletion)

    Returns (project_data, target_person_id).
    """
    # Generate 2-5 persons
    num_persons = draw(st.integers(min_value=2, max_value=5))
    person_ids = [f"person_{i}" for i in range(num_persons)]
    persons = [_make_person(pid) for pid in person_ids]

    # Target is always person_0; main person is person_1 (so target != main)
    target_id = "person_0"
    main_person_id = "person_1"

    # Other person IDs (not the target)
    other_ids = [pid for pid in person_ids if pid != target_id]

    # --- Create events that will be referenced by the removable family ---
    # These events involve other persons (not exclusively the target)
    num_family_events = draw(st.integers(min_value=1, max_value=3))
    family_ref_events: list[Event] = []
    for i in range(num_family_events):
        event_id = f"fam_ref_event_{i}"
        # Decide if the target is a participant (shared) or not at all
        include_target = draw(st.booleans())
        # Always include at least one other person
        chosen_other = draw(st.sampled_from(other_ids))
        participants = [Participant(person_id=chosen_other, role="witness")]
        if include_target:
            participants.append(Participant(person_id=target_id, role="principal"))
        family_ref_events.append(
            Event(id=event_id, type="marriage", participants=participants)
        )

    family_ref_event_ids = [e.id for e in family_ref_events]

    # --- Create additional events (some exclusive to target, some shared) ---
    num_extra_events = draw(st.integers(min_value=0, max_value=3))
    extra_events: list[Event] = []
    for i in range(num_extra_events):
        event_id = f"extra_event_{i}"
        event_kind = draw(st.sampled_from(["exclusive", "shared", "other_only"]))
        if event_kind == "exclusive":
            # Only the target as participant
            participants = [Participant(person_id=target_id, role="principal")]
        elif event_kind == "shared":
            # Target + another person, NOT in any family event_ids
            chosen_other = draw(st.sampled_from(other_ids))
            participants = [
                Participant(person_id=target_id, role="principal"),
                Participant(person_id=chosen_other, role="witness"),
            ]
        else:
            # Only other persons
            chosen_other = draw(st.sampled_from(other_ids))
            participants = [Participant(person_id=chosen_other, role="principal")]
        extra_events.append(
            Event(id=event_id, type="birth", participants=participants)
        )

    all_events = family_ref_events + extra_events

    # --- Create the removable family (target is sole partner, no children) ---
    removable_family = Family(
        id="removable_family_0",
        partners=[FamilyPartner(person_id=target_id, role="partner")],
        children=[],
        parent_child_links=[],
        event_ids=family_ref_event_ids,
    )

    # --- Optionally create additional non-removable families ---
    num_other_families = draw(st.integers(min_value=0, max_value=2))
    other_families: list[Family] = []
    for i in range(num_other_families):
        # These families have at least 2 partners or children, so won't be empty
        partner_ids_for_fam = draw(
            st.lists(
                st.sampled_from(person_ids),
                min_size=2,
                max_size=2,
                unique=True,
            )
        )
        partners = [
            FamilyPartner(person_id=pid, role="partner")
            for pid in partner_ids_for_fam
        ]
        # Optionally add some event_ids from extra_events
        fam_event_ids: list[str] = []
        if extra_events:
            use_extra = draw(st.booleans())
            if use_extra:
                chosen_extra = draw(
                    st.sampled_from([e.id for e in extra_events])
                )
                fam_event_ids = [chosen_extra]
        other_families.append(
            Family(
                id=f"other_family_{i}",
                partners=partners,
                children=[],
                parent_child_links=[],
                event_ids=fam_event_ids,
            )
        )

    all_families = [removable_family] + other_families

    project_data = ProjectData(
        project=ProjectMetadata(title="Property 4 Test", main_person_id=main_person_id),
        persons=persons,
        families=all_families,
        events=all_events,
    )

    return project_data, target_id


# ---------------------------------------------------------------------------
# Property 4: Events From Removed Families Are Preserved
# ---------------------------------------------------------------------------


class TestEventsFromRemovedFamiliesArePreserved:
    """Feature: delete-person, Property 4: Events From Removed Families Are Preserved

    For any valid ProjectData where deleting a person causes a Family to be
    removed (due to becoming empty), the Event records that were referenced by
    that Family's event_ids shall still exist in ProjectData.events (unless
    those events were independently removed as exclusive or family events of
    the deleted person).

    **Validates: Requirements 4.5**
    """

    @given(scenario=removed_family_events_scenario())
    @settings(max_examples=100, deadline=None)
    def test_events_from_removed_families_are_preserved(
        self, scenario: tuple[ProjectData, str]
    ) -> None:
        """Property 4: Events From Removed Families Are Preserved.

        Feature: delete-person, Property 4: Events From Removed Families Are Preserved
        **Validates: Requirements 4.5**
        """
        project_data, target_id = scenario

        # --- Before deletion: identify families that will become empty ---
        # A family becomes empty when target is the only partner AND there
        # are no children (after removing target from partners/children).
        families_to_be_removed: list[Family] = []
        for family in project_data.families:
            remaining_partners = [
                fp for fp in family.partners if fp.person_id != target_id
            ]
            remaining_children = [
                cid for cid in family.children if cid != target_id
            ]
            if len(remaining_partners) == 0 and len(remaining_children) == 0:
                families_to_be_removed.append(family)

        # Collect event_ids from families that will be removed
        event_ids_from_removed_families: set[str] = set()
        for family in families_to_be_removed:
            event_ids_from_removed_families.update(family.event_ids)

        # --- Identify events that would be legitimately removed ---
        exclusive_events, family_events, _ = classify_events(
            target_id, project_data
        )
        legitimately_removed_ids: set[str] = {e.id for e in exclusive_events} | {
            e.id for e in family_events
        }

        # --- Execute deletion ---
        execute_person_deletion(target_id, project_data)

        # --- After deletion: verify events from removed families are preserved ---
        remaining_event_ids: set[str] = {e.id for e in project_data.events}

        for event_id in event_ids_from_removed_families:
            assert (
                event_id in remaining_event_ids
                or event_id in legitimately_removed_ids
            ), (
                f"Event '{event_id}' referenced by a removed family was not "
                f"preserved in ProjectData.events and was NOT classified as "
                f"an exclusive or family event.\n"
                f"  Remaining event IDs: {remaining_event_ids}\n"
                f"  Legitimately removed IDs: {legitimately_removed_ids}\n"
                f"  Event IDs from removed families: {event_ids_from_removed_families}"
            )


# ---------------------------------------------------------------------------
# Strategies for Property 5
# ---------------------------------------------------------------------------

import copy

from slaktbusken.services.delete_service import DeleteService
from slaktbusken.services.project_service import ProjectService


@st.composite
def main_person_scenario(draw: st.DrawFn) -> tuple[ProjectData, str]:
    """Generate a ProjectData where main_person_id is set to one of the persons.

    Ensures:
    - At least 2 persons exist
    - main_person_id is set to one of the existing person IDs
    - The project may include some events and families for realism

    Returns (project_data, main_person_id).
    """
    # Generate 2-5 persons
    num_persons = draw(st.integers(min_value=2, max_value=5))
    person_ids = [f"person_{i}" for i in range(num_persons)]
    persons = [_make_person(pid) for pid in person_ids]

    # Pick one person as the main person
    main_person_id = draw(st.sampled_from(person_ids))

    # Optionally generate a few events
    num_events = draw(st.integers(min_value=0, max_value=3))
    events: list[Event] = []
    for i in range(num_events):
        event_type = draw(st.sampled_from(_EVENT_TYPES))
        # Pick 1-2 random participants from persons
        num_participants = draw(st.integers(min_value=1, max_value=min(2, num_persons)))
        chosen = draw(
            st.lists(
                st.sampled_from(person_ids),
                min_size=num_participants,
                max_size=num_participants,
                unique=True,
            )
        )
        participants = [
            Participant(person_id=pid, role="principal") for pid in chosen
        ]
        events.append(
            Event(id=f"evt_{i}", type=event_type, participants=participants)
        )

    # Optionally generate a family
    families: list[Family] = []
    if num_persons >= 2:
        add_family = draw(st.booleans())
        if add_family:
            partner_ids = draw(
                st.lists(
                    st.sampled_from(person_ids),
                    min_size=2,
                    max_size=2,
                    unique=True,
                )
            )
            partners = [
                FamilyPartner(person_id=pid, role="partner") for pid in partner_ids
            ]
            families.append(
                Family(
                    id="fam_0",
                    partners=partners,
                    children=[],
                    event_ids=[],
                )
            )

    project_data = ProjectData(
        project=ProjectMetadata(title="Main Person Guard Test", main_person_id=main_person_id),
        persons=persons,
        families=families,
        events=events,
    )

    return project_data, main_person_id


# ---------------------------------------------------------------------------
# Property 5: Main Person Cannot Be Deleted
# ---------------------------------------------------------------------------


class TestMainPersonCannotBeDeleted:
    """Feature: delete-person, Property 5: Main Person Cannot Be Deleted"""

    @given(scenario=main_person_scenario())
    @settings(max_examples=100, deadline=None)
    def test_main_person_cannot_be_deleted(
        self, scenario: tuple[ProjectData, str]
    ) -> None:
        """Property 5: Main Person Cannot Be Deleted.

        For any valid ProjectData where main_person_id is set and the target
        person equals main_person_id, can_delete shall return (False, error_message)
        and ProjectData shall be unmodified.

        Feature: delete-person, Property 5: Main Person Cannot Be Deleted
        **Validates: Requirements 1.4**
        """
        project_data, main_person_id = scenario

        # Set up a real ProjectService with the generated data
        project_service = ProjectService()
        project_service._project_data = project_data
        project_service._dirty = False

        # Snapshot the data before calling can_delete
        data_before = copy.deepcopy(project_data)

        # Create DeleteService and call can_delete with the main person
        delete_service = DeleteService(project_service)
        allowed, error_message = delete_service.can_delete(main_person_id)

        # --- Assertion 1: Deletion is not allowed ---
        assert allowed is False, (
            f"can_delete returned allowed=True for main_person_id='{main_person_id}', "
            f"but the main person should never be deletable."
        )

        # --- Assertion 2: Error message is correct ---
        assert error_message == "Huvudpersonen kan inte tas bort.", (
            f"Expected error message 'Huvudpersonen kan inte tas bort.' "
            f"but got '{error_message}'."
        )

        # --- Assertion 3: ProjectData is unmodified ---
        assert project_data == data_before, (
            f"ProjectData was modified after calling can_delete on the main person. "
            f"can_delete should be a read-only check."
        )

        # --- Assertion 4: Dirty flag unchanged ---
        assert project_service._dirty is False, (
            "ProjectService._dirty was changed after calling can_delete. "
            "can_delete should not modify project state."
        )


# ---------------------------------------------------------------------------
# Property 6: Round-Trip Integrity After Deletion
# ---------------------------------------------------------------------------

from slaktbusken.persistence.serialization import deserialize, serialize


class TestRoundTripIntegrityAfterDeletion:
    """Feature: delete-person, Property 6: Round-Trip Integrity After Deletion"""

    @given(scenario=deletable_person_scenario())
    @settings(max_examples=100, deadline=None)
    def test_round_trip_integrity_after_deletion(
        self, scenario: tuple[ProjectData, str]
    ) -> None:
        """Property 6: Round-Trip Integrity After Deletion.

        For any valid ProjectData containing a deletable person, after executing
        deletion, serializing to JSON and deserializing back shall produce
        equivalent ProjectData.

        Feature: delete-person, Property 6: Round-Trip Integrity After Deletion
        **Validates: Requirements 8.6**
        """
        project_data, target_id = scenario

        # Execute deletion (mutates project_data in-place)
        execute_person_deletion(target_id, project_data)

        # Serialize to JSON
        json_str = serialize(project_data)

        # Deserialize back to ProjectData
        restored = deserialize(json_str)

        # Assert equivalence: the deserialized result must equal the
        # post-deletion state
        assert restored == project_data, (
            f"Round-trip integrity failed after deleting '{target_id}'.\n"
            f"  Serialized JSON length: {len(json_str)}\n"
            f"  Persons before round-trip: "
            f"{[p.id for p in project_data.persons]}\n"
            f"  Persons after round-trip: "
            f"{[p.id for p in restored.persons]}\n"
            f"  Families before: {len(project_data.families)}, "
            f"after: {len(restored.families)}\n"
            f"  Events before: {len(project_data.events)}, "
            f"after: {len(restored.events)}"
        )


# ---------------------------------------------------------------------------
# Strategies for Property 9
# ---------------------------------------------------------------------------

from slaktbusken.services.delete_service import DeletionConsequences
from slaktbusken.ui.dialogs.delete_person_dialog import build_warning_lines


@st.composite
def warning_list_scenario(draw: st.DrawFn) -> DeletionConsequences:
    """Generate DeletionConsequences with varying event counts.

    Produces 0 to 25 family_events and 0 to 25 non_family_shared_events
    to test the warning list cap behaviour across a range of total event counts.
    """
    num_family_events = draw(st.integers(min_value=0, max_value=25))
    num_shared_events = draw(st.integers(min_value=0, max_value=25))

    family_events: list[Event] = []
    for i in range(num_family_events):
        event_type = draw(st.sampled_from(_EVENT_TYPES))
        family_events.append(
            Event(
                id=f"fam_evt_{i}",
                type=event_type,
                participants=[],
            )
        )

    shared_events: list[Event] = []
    for i in range(num_shared_events):
        event_type = draw(st.sampled_from(_EVENT_TYPES))
        shared_events.append(
            Event(
                id=f"shared_evt_{i}",
                type=event_type,
                participants=[],
            )
        )

    return DeletionConsequences(
        person_name="Test Person",
        exclusive_events=[],
        family_events=family_events,
        non_family_shared_events=shared_events,
        affected_families=[],
        would_disconnect=False,
        disconnected_person_count=0,
    )


# ---------------------------------------------------------------------------
# Property 9: Warning List Caps At 10 Events
# ---------------------------------------------------------------------------


class TestWarningListCapsAt10Events:
    """Feature: delete-person, Property 9: Warning List Caps At 10 Events

    For any DeletionConsequences with N total family + shared events, the warning
    text builder shall list at most 10 events and, if N > 10, shall indicate the
    count of remaining events not shown.

    **Validates: Requirements 6.4**
    """

    @given(scenario=warning_list_scenario())
    @settings(max_examples=100, deadline=None)
    def test_warning_list_caps_at_10_events(
        self, scenario: DeletionConsequences
    ) -> None:
        """Property 9: Warning List Caps At 10 Events.

        Feature: delete-person, Property 9: Warning List Caps At 10 Events
        **Validates: Requirements 6.4**
        """
        consequences = scenario
        total_events = len(consequences.family_events) + len(
            consequences.non_family_shared_events
        )

        lines = build_warning_lines(consequences)

        # Count lines that match event listing format (start with "  • ")
        event_lines = [line for line in lines if line.startswith("  \u2022 ")]

        # Assert: at most 10 event lines are listed
        assert len(event_lines) <= 10, (
            f"Expected at most 10 event lines but got {len(event_lines)}.\n"
            f"  Total events: {total_events}\n"
            f"  Family events: {len(consequences.family_events)}\n"
            f"  Shared events: {len(consequences.non_family_shared_events)}"
        )

        # Assert: when total events > 10, overflow indicator is present
        if total_events > 10:
            overflow = total_events - 10
            overflow_lines = [line for line in lines if "...och" in line]
            assert len(overflow_lines) == 1, (
                f"Expected exactly 1 overflow line when total={total_events}, "
                f"but found {len(overflow_lines)}.\n"
                f"  Lines: {lines}"
            )
            expected_overflow_text = f"...och {overflow} till"
            assert overflow_lines[0] == expected_overflow_text, (
                f"Overflow line mismatch.\n"
                f"  Expected: '{expected_overflow_text}'\n"
                f"  Got: '{overflow_lines[0]}'"
            )

        # Assert: when total events <= 10, no overflow line is present
        if total_events <= 10:
            overflow_lines = [line for line in lines if "...och" in line]
            assert len(overflow_lines) == 0, (
                f"Expected no overflow line when total={total_events}, "
                f"but found: {overflow_lines}"
            )
