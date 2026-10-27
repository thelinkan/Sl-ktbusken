"""Property test for end events annotating but never mutating links (task 2.6).

Feature: foster-parents, Property 9: End events annotate but never mutate links

For any synced project, an arbitrary mutation to END events only - adding an
end event, editing an end event's date, or removing an end event - leaves every
Derived_Link (foster/adoptive parent -> child link) unchanged. Each end event
that matches a start by Parent_Set is paired to exactly one derived family (its
id appended to that family's ``event_ids``); no derived family accumulates more
than one end-event id per start; and an orphan end event (no matching start) is
left detached in ``project.events`` rather than deleted.

System under test: ``slaktbusken/services/foster_sync.py:sync_parentage_links``.

Validates: Requirements 2.10, 2A.1, 2A.2, 2A.3, 2A.4
"""

from __future__ import annotations

import copy

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.project import ProjectData
from slaktbusken.services.foster_sync import sync_parentage_links

from tests.test_foster.foster_strategies import (
    PLACEMENT_END,
    PLACEMENT_START,
    foster_project,
)


# ---------------------------------------------------------------------------
# Helpers over a synced project
# ---------------------------------------------------------------------------


def _live_start_ids(project: ProjectData) -> set[str]:
    """Ids of placement START events still present in the project."""
    return {ev.id for ev in project.events if ev.type in PLACEMENT_START}


def _derived_link_set(project: ProjectData) -> set[tuple[str, str | None, str]]:
    """Return the canonical set of Derived_Links produced by START events.

    A Derived_Link is identified by ``(child_id, parent_id, parentage_type)``
    for every foster/adoptive ``ParentChildLink`` in a family that is backed by
    a live placement START event (its ``event_ids`` records a start). This is
    exactly the link population Property 9 concerns: links the Parentage_Sync_
    Service derives from placement START events. Pre-feature *orphan* link
    families with no backing start (owned by the on-load migration, task 3.2)
    are deliberately out of scope here. Comparing this set across an END-event
    mutation captures "the set of Derived_Links is unchanged" independently of
    family id or ordering.
    """
    live_starts = _live_start_ids(project)
    links: set[tuple[str, str | None, str]] = set()
    for family in project.families:
        if not (set(family.event_ids) & live_starts):
            continue
        for link in family.parent_child_links:
            if link.parentage_type in ("foster", "adoptive"):
                links.add((link.child_id, link.parent_id, link.parentage_type))
    return links


def _end_event_ids(project: ProjectData) -> list[str]:
    """Ids of every placement END event present in the project."""
    return [ev.id for ev in project.events if ev.type in PLACEMENT_END]


def _derived_family_for(
    project: ProjectData, event_id: str
):
    """Return the derived family whose ``event_ids`` records ``event_id``."""
    for family in project.families:
        if event_id in family.event_ids:
            return family
    return None


def _is_derived_family(family) -> bool:
    types = {link.parentage_type for link in family.parent_child_links}
    return bool(types) and types.issubset({"foster", "adoptive"})


def _end_signature(event: Event):
    """Return ``(parentage_type, child_id, parent_set)`` named by an end event.

    This is the pairing key the sync uses: the matching start type's parentage,
    the single child-role participant, and the frozenset of parent-role
    participants. Returns ``None`` when the event names no child.
    """
    start_type = PLACEMENT_END[event.type]
    spec = PLACEMENT_START[start_type]
    child_id = None
    parents: set[str] = set()
    for participant in event.participants:
        if participant.role == spec["child_role"] and child_id is None:
            child_id = participant.person_id
        elif participant.role == spec["parent_role"]:
            parents.add(participant.person_id)
    if child_id is None:
        return None
    return spec["parentage"], child_id, frozenset(parents)


def _has_matching_start_family(project: ProjectData, end_event: Event) -> bool:
    """True when some derived family matches an end event's Parent_Set.

    An end event is only semantically an orphan (Req 2A.4) when *no* derived
    family shares its parentage type, child, and exact parent set - regardless
    of how the generator labelled it.
    """
    signature = _end_signature(end_event)
    if signature is None:
        return False
    parentage, child_id, parent_set = signature
    for family in project.families:
        if child_id not in family.children:
            continue
        family_parents = frozenset(
            link.parent_id
            for link in family.parent_child_links
            if link.parentage_type == parentage and link.parent_id is not None
        )
        link_types = {link.parentage_type for link in family.parent_child_links}
        if parentage in link_types and family_parents == parent_set:
            return True
    return False


# ---------------------------------------------------------------------------
# A strategy that produces a synced project plus an END-only mutation to apply
# ---------------------------------------------------------------------------


@st.composite
def synced_project_and_end_mutation(draw: DrawFn):
    """Draw a freshly synced project and an END-only mutation to apply next.

    The mutation is one of: ``("add", event)`` appends a new end event,
    ``("edit", end_id, new_date)`` changes an existing end event's date, or
    ``("remove", end_id)`` drops an existing end event. All three touch END
    events only and never a START event or a derived link.
    """
    fp = draw(foster_project())
    project = fp.project

    # Establish the derived links from the START events before any mutation.
    sync_parentage_links(project)

    existing_end_ids = _end_event_ids(project)
    choices = ["add"]
    if existing_end_ids:
        choices += ["edit", "remove"]
    action = draw(st.sampled_from(choices))

    if action == "edit":
        end_id = draw(st.sampled_from(existing_end_ids))
        new_year = draw(st.integers(min_value=1500, max_value=2100))
        return project, fp, ("edit", end_id, str(new_year))

    if action == "remove":
        end_id = draw(st.sampled_from(existing_end_ids))
        return project, fp, ("remove", end_id)

    # action == "add": build a brand-new end event. Prefer one that matches an
    # existing derived family (so it pairs), otherwise an orphan end.
    end_type = draw(st.sampled_from(list(PLACEMENT_END)))
    start_type = PLACEMENT_END[end_type]
    spec = PLACEMENT_START[start_type]
    parentage = spec["parentage"]

    # Collect derived families of the matching type we could pair against.
    candidates = [
        family
        for family in project.families
        if _is_derived_family(family)
        and any(
            link.parentage_type == parentage for link in family.parent_child_links
        )
    ]
    pair_existing = bool(candidates) and draw(st.booleans())

    if pair_existing:
        family = draw(st.sampled_from(candidates))
        child_id = family.children[0]
        parent_ids = [
            link.parent_id
            for link in family.parent_child_links
            if link.parentage_type == parentage and link.parent_id is not None
        ]
    else:
        child_id = draw(st.sampled_from(fp.child_ids))
        n_parents = draw(st.integers(min_value=1, max_value=2))
        parent_ids = draw(
            st.lists(
                st.sampled_from(fp.parent_ids),
                min_size=n_parents,
                max_size=n_parents,
                unique=True,
            )
        )

    participants = [Participant(person_id=child_id, role=spec["child_role"])]
    for pid in parent_ids:
        participants.append(Participant(person_id=pid, role=spec["parent_role"]))

    dated = draw(st.booleans())
    new_event = Event(
        id=f"ev_added_end_{len(project.events)}",
        type=end_type,
        participants=participants,
        date=DateValue(value=str(draw(st.integers(1500, 2100))), precision="year")
        if dated
        else None,
    )
    return project, fp, ("add", new_event)


# ---------------------------------------------------------------------------
# Property 9
# ---------------------------------------------------------------------------


class TestEndEventsAnnotateOnly:
    """Feature: foster-parents, Property 9: End events annotate but never mutate links

    **Validates: Requirements 2.10, 2A.1, 2A.2, 2A.3, 2A.4**
    """

    @given(case=synced_project_and_end_mutation())
    @settings(max_examples=100, deadline=None)
    def test_end_event_mutation_never_changes_derived_links(self, case) -> None:
        """Property 9: mutating END events leaves every Derived_Link unchanged.

        Feature: foster-parents, Property 9: End events annotate but never mutate links
        **Validates: Requirements 2.10, 2A.2**
        """
        project, _fp, mutation = case

        links_before = _derived_link_set(project)

        # Apply an END-only mutation, then re-sync.
        if mutation[0] == "add":
            project.events.append(mutation[1])
        elif mutation[0] == "edit":
            _, end_id, new_date = mutation
            for event in project.events:
                if event.id == end_id:
                    event.date = DateValue(value=new_date, precision="year")
                    break
        else:  # remove
            _, end_id = mutation
            project.events = [ev for ev in project.events if ev.id != end_id]

        sync_parentage_links(project)

        links_after = _derived_link_set(project)

        assert links_after == links_before, (
            "An END-event mutation changed the set of Derived_Links.\n"
            f"  mutation: {mutation[0]}\n"
            f"  before:   {sorted(str(l) for l in links_before)}\n"
            f"  after:    {sorted(str(l) for l in links_after)}"
        )

    @given(fp=foster_project())
    @settings(max_examples=100, deadline=None)
    def test_each_end_pairs_to_the_one_family_matching_its_parent_set(
        self, fp
    ) -> None:
        """Property 9: each end that sync pairs is appended to exactly one
        derived family, and that family's Parent_Set is the one the end names.

        The service pairs by Parent_Set (Req 2A.1); enforcing the "at most one
        end per start" cap (Req 2A.3) is the validator's job (task 1.5), so this
        test asserts only what ``sync_parentage_links`` itself guarantees: an
        end is never appended to two families, and when it is appended the
        target family genuinely matches the end's (type, child, parent set).

        Feature: foster-parents, Property 9: End events annotate but never mutate links
        **Validates: Requirement 2A.1**
        """
        project = fp.project
        sync_parentage_links(project)

        for end_id in _end_event_ids(project):
            end_event = next(ev for ev in project.events if ev.id == end_id)
            owning = [
                family
                for family in project.families
                if end_id in family.event_ids
            ]

            # Sync never pairs one end event into more than one family.
            assert len(owning) <= 1, (
                f"End event '{end_id}' is paired to more than one derived "
                f"family: {[f.id for f in owning]}"
            )

            if owning:
                # A paired end must match the family's Parent_Set exactly.
                signature = _end_signature(end_event)
                assert signature is not None
                parentage, child_id, parent_set = signature
                family = owning[0]
                family_parents = frozenset(
                    link.parent_id
                    for link in family.parent_child_links
                    if link.parentage_type == parentage
                    and link.parent_id is not None
                )
                assert child_id in family.children, (
                    f"End '{end_id}' paired to family '{family.id}' that does "
                    f"not contain child '{child_id}'"
                )
                assert family_parents == parent_set, (
                    f"End '{end_id}' paired to family '{family.id}' whose "
                    f"Parent_Set {set(family_parents)} differs from the end's "
                    f"named set {set(parent_set)}"
                )
            else:
                # An unpaired end must have no matching start family.
                assert not _has_matching_start_family(project, end_event), (
                    f"End '{end_id}' was left unpaired despite a derived family "
                    f"matching its Parent_Set existing"
                )

    @given(fp=foster_project())
    @settings(max_examples=100, deadline=None)
    def test_orphan_end_events_are_flagged_not_dropped(self, fp) -> None:
        """Property 9: a genuinely orphan end event is left detached in the
        project (never deleted) and is paired to no derived family (Req 2A.4).

        The strategy's ``orphan_end_event_ids`` are *intended* orphans, but the
        sync pairs any end whose Parent_Set matches a start (Req 2A.1/2A.7) even
        when the generator labelled it orphan. So the test keeps the general
        guarantee - no end event is ever deleted by sync - and additionally
        asserts the stricter orphan behaviour only for ends that are orphan in
        the resulting project state (no derived family matches their Parent_Set).

        Feature: foster-parents, Property 9: End events annotate but never mutate links
        **Validates: Requirement 2A.4**
        """
        project = fp.project
        end_ids_before = set(_end_event_ids(project))

        sync_parentage_links(project)

        surviving_ids = {ev.id for ev in project.events}

        # No end event is ever deleted by the sync.
        for end_id in end_ids_before:
            assert end_id in surviving_ids, (
                f"End event '{end_id}' was dropped from the project by sync"
            )

        # Every end that has no matching start family stays detached.
        for end_event in [ev for ev in project.events if ev.type in PLACEMENT_END]:
            if _has_matching_start_family(project, end_event):
                continue
            paired = [
                family.id
                for family in project.families
                if end_event.id in family.event_ids
            ]
            assert paired == [], (
                f"Orphan end event '{end_event.id}' was paired to families "
                f"{paired} despite no derived family matching its Parent_Set"
            )

    @given(fp=foster_project())
    @settings(max_examples=100, deadline=None)
    def test_sync_does_not_mutate_end_events_themselves(self, fp) -> None:
        """Property 9: syncing never edits or removes the END events; it only
        annotates derived families with their ids.

        Feature: foster-parents, Property 9: End events annotate but never mutate links
        **Validates: Requirements 2.10, 2A.2**
        """
        project = fp.project
        ends_before = copy.deepcopy(
            [ev for ev in project.events if ev.type in PLACEMENT_END]
        )

        sync_parentage_links(project)

        ends_after = [ev for ev in project.events if ev.type in PLACEMENT_END]
        assert ends_after == ends_before, (
            "sync_parentage_links mutated the END events themselves"
        )
