"""Property tests for event⇒link coverage and the per-set parent cap.

Feature: foster-parents, Property 3: Event ⇒ link coverage, both types
Feature: foster-parents, Property 4: Set cap, project no-cap

Validates: Requirements 2.1, 2.9

These properties exercise ``slaktbusken/services/foster_sync.py:sync_parentage_links``
symmetrically for *foster* (``foster_home`` start events) and *adoptive*
(``adoption`` start events) parentage, over the shared Hypothesis strategies in
``tests/test_foster/foster_strategies.py``.

Property 3 (Req 2.1): after a sync, every placement START event that names a
valid child and one or two valid parents has, for each named parent, exactly one
derived link of the event's parentage type from that parent to that child; and
conversely every foster/adoptive derived link traces back to such a start event
(no orphan derived links remain after the sync). A parent-less descriptive
adoption event derives nothing.

Property 4 (Req 2.9): after a sync, each individual derived Parent_Set (derived
family) holds at most two parent links; but a single child may accumulate more
than two foster parents and more than two adoptive parents in total across
multiple sets - the project is uncapped per child.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.event import Event
from slaktbusken.model.project import ProjectData
from slaktbusken.services.foster_sync import sync_parentage_links

from tests.test_foster.foster_strategies import (
    DERIVED_PARENTAGE,
    PLACEMENT_START,
    foster_project,
)


_MAX_PARENTS_PER_SET = 2


# ---------------------------------------------------------------------------
# Helpers that read the same "named Parent_Set" a start event implies, using
# exactly the sync service's own rules (first child-role participant is the
# child; parent-role participants, de-duplicated and capped at two, are the
# set). Kept independent of the service internals so the property genuinely
# checks the derived state rather than echoing the implementation.
# ---------------------------------------------------------------------------


def _named_placement(event: Event, person_ids: set[str]) -> tuple[str | None, list[str]]:
    """Return ``(child_id, parent_ids)`` a start event names, validity-filtered.

    Mirrors ``foster_sync._placement_participants`` + the validity checks in
    ``sync_parentage_links``: the child is the first participant in the child
    role (and must be a real person); parents are the participants in the parent
    role, de-duplicated in order, capped at two, and filtered to real persons.
    """
    spec = PLACEMENT_START[event.type]
    child_id: str | None = None
    parent_ids: list[str] = []
    for participant in event.participants:
        if participant.role == spec["child_role"] and child_id is None:
            child_id = participant.person_id
        elif participant.role == spec["parent_role"]:
            if participant.person_id not in parent_ids:
                parent_ids.append(participant.person_id)
    if child_id is None or child_id not in person_ids:
        return None, []
    valid_parents = [pid for pid in parent_ids[:_MAX_PARENTS_PER_SET] if pid in person_ids]
    return child_id, valid_parents


def _derived_links(
    project: ProjectData, exclude_family_ids: frozenset[str] = frozenset()
) -> list[tuple[str, str, str]]:
    """Every foster/adoptive link as ``(child_id, parent_id, parentage_type)``.

    Families in ``exclude_family_ids`` are skipped. This lets a property ignore
    pre-existing *orphan* derived families (foster/adoptive links with no
    backing placement event): the sync service deliberately preserves those for
    the separate on-load migration to adopt, rather than deleting them (design
    backward-compatibility guard, Req 13.3). They are therefore not "orphan
    links introduced by sync" and must be excluded from the event-coverage
    direction of Property 3.
    """
    out: list[tuple[str, str, str]] = []
    for family in project.families:
        if family.id in exclude_family_ids:
            continue
        for link in family.parent_child_links:
            if link.parentage_type in DERIVED_PARENTAGE and link.parent_id is not None:
                out.append((link.child_id, link.parent_id, link.parentage_type))
    return out


# ---------------------------------------------------------------------------
# Property 3: Event ⇒ link coverage, both types
# ---------------------------------------------------------------------------


class TestEventLinkCoverage:
    """Feature: foster-parents, Property 3: Event ⇒ link coverage, both types

    After sync, every placement START event that names a valid child and one or
    two valid parents has exactly its links of its parentage type, and every
    foster/adoptive derived link traces back to such a start event.

    **Validates: Requirements 2.1**
    """

    @given(fp=foster_project())
    @settings(max_examples=100, deadline=None)
    def test_every_event_has_its_links_and_vice_versa(self, fp) -> None:
        """Property 3: event⇒link coverage both directions.

        Feature: foster-parents, Property 3: Event ⇒ link coverage, both types
        **Validates: Requirements 2.1**
        """
        project = fp.project
        person_ids = {person.id for person in project.persons}
        orphan_families = frozenset(fp.orphan_link_family_ids)

        sync_parentage_links(project)

        derived = _derived_links(project, exclude_family_ids=orphan_families)
        derived_set = set(derived)

        # Forward: every derivable start event implies exactly its links, one
        # per (parent -> child) of the event's parentage type.
        expected: set[tuple[str, str, str]] = set()
        for event in project.events:
            if event.type not in PLACEMENT_START:
                continue
            child_id, parent_ids = _named_placement(event, person_ids)
            if child_id is None or not parent_ids:
                # A parent-less descriptive adoption event (or an event with no
                # valid child/parent) derives nothing - Req 1.9 / 13.5.
                continue
            parentage = PLACEMENT_START[event.type]["parentage"]
            for pid in parent_ids:
                triple = (child_id, pid, parentage)
                expected.add(triple)
                assert triple in derived_set, (
                    f"Start event {event.id} ({event.type}) should imply link "
                    f"{triple}, but it is missing after sync. Derived: {derived_set}"
                )

        # Backward: no orphan derived links remain. Every foster/adoptive link
        # must correspond to a derivable start event's named Parent_Set.
        for triple in derived:
            assert triple in expected, (
                f"Derived link {triple} has no backing start event after sync. "
                f"Expected from events: {expected}"
            )

    @given(fp=foster_project())
    @settings(max_examples=100, deadline=None)
    def test_descriptive_adoption_events_derive_no_family(self, fp) -> None:
        """A parent-less (descriptive) adoption start event owns no derived
        family after sync, so it contributes no adoptive link.

        A derived family records its backing start event id in ``event_ids``.
        Because a descriptive adoption names no parent-role participant, the
        sync service never creates a derived family keyed by its id - so the
        event cannot introduce any link (Req 1.9 / 13.5).

        Feature: foster-parents, Property 3: Event ⇒ link coverage, both types
        **Validates: Requirements 2.1**
        """
        project = fp.project
        person_ids = {person.id for person in project.persons}

        sync_parentage_links(project)

        for event in project.events:
            if event.type != "adoption":
                continue
            _, parent_ids = _named_placement(event, person_ids)
            if parent_ids:
                continue
            # Descriptive adoption: no derived family may be keyed to this event.
            for family in project.families:
                assert event.id not in family.event_ids, (
                    f"Descriptive adoption event {event.id} should derive no "
                    f"family, but family {family.id} records it in event_ids"
                )


# ---------------------------------------------------------------------------
# Property 4: Set cap, project no-cap
# ---------------------------------------------------------------------------


class TestSetCapProjectUncapped:
    """Feature: foster-parents, Property 4: Set cap, project no-cap

    After sync, each derived Parent_Set (derived family) holds at most two
    parent links, while a child may have more than two foster parents and more
    than two adoptive parents in total across multiple sets.

    **Validates: Requirements 2.9**
    """

    @given(fp=foster_project())
    @settings(max_examples=100, deadline=None)
    def test_no_derived_set_exceeds_two_parents(self, fp) -> None:
        """Property 4a: no single derived family has more than two parent links.

        Feature: foster-parents, Property 4: Set cap, project no-cap
        **Validates: Requirements 2.9**
        """
        project = fp.project
        sync_parentage_links(project)

        for family in project.families:
            derived_links = [
                link
                for link in family.parent_child_links
                if link.parentage_type in DERIVED_PARENTAGE
            ]
            if not derived_links:
                continue
            distinct_parents = {
                link.parent_id for link in derived_links if link.parent_id is not None
            }
            assert len(distinct_parents) <= _MAX_PARENTS_PER_SET, (
                f"Derived family {family.id} holds {len(distinct_parents)} "
                f"parents, exceeding the per-set cap of {_MAX_PARENTS_PER_SET}: "
                f"{distinct_parents}"
            )

    @given(
        parentage=st.sampled_from(list(DERIVED_PARENTAGE)),
        n_sets=st.integers(min_value=3, max_value=5),
    )
    @settings(max_examples=100, deadline=None)
    def test_child_may_exceed_two_parents_across_sets(
        self, parentage: str, n_sets: int
    ) -> None:
        """Property 4b: the project is uncapped per child.

        A child with several single-parent placement sets of one type ends up
        with more than two derived parents of that type in total, even though no
        single set exceeds two.

        Feature: foster-parents, Property 4: Set cap, project no-cap
        **Validates: Requirements 2.9**
        """
        from slaktbusken.model.event import Event, Participant
        from slaktbusken.model.person import Name, Person
        from slaktbusken.model.project import ProjectData, ProjectMetadata

        start_type = next(
            etype
            for etype, cfg in PLACEMENT_START.items()
            if cfg["parentage"] == parentage
        )
        spec = PLACEMENT_START[start_type]

        child = Person(
            id="child_1",
            sex="U",
            names=[Name(type="birth", given="Child", surname="Capped")],
        )
        persons = [child]
        events: list[Event] = []
        for i in range(n_sets):
            parent_id = f"parent_{i}"
            persons.append(
                Person(
                    id=parent_id,
                    sex="M" if i % 2 else "F",
                    names=[Name(type="birth", given=f"P{i}", surname="X")],
                )
            )
            events.append(
                Event(
                    id=f"ev_{i}",
                    type=start_type,
                    participants=[
                        Participant(person_id="child_1", role=spec["child_role"]),
                        Participant(person_id=parent_id, role=spec["parent_role"]),
                    ],
                )
            )

        project = ProjectData(
            project=ProjectMetadata(title="Uncapped Test"),
            persons=persons,
            events=events,
            families=[],
        )

        sync_parentage_links(project)

        total_parents_for_child = {
            link.parent_id
            for family in project.families
            for link in family.parent_child_links
            if link.child_id == "child_1"
            and link.parentage_type == parentage
            and link.parent_id is not None
        }
        assert len(total_parents_for_child) == n_sets > _MAX_PARENTS_PER_SET, (
            f"Child should accumulate {n_sets} {parentage} parents across sets, "
            f"got {len(total_parents_for_child)}: {total_parents_for_child}"
        )

        # And still no single derived family exceeds the cap.
        for family in project.families:
            derived = {
                link.parent_id
                for link in family.parent_child_links
                if link.parentage_type == parentage and link.parent_id is not None
            }
            assert len(derived) <= _MAX_PARENTS_PER_SET
