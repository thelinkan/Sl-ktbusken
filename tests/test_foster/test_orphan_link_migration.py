"""Tests for the pre-feature orphan-link placement-event migration.

Feature: foster-parents, task 3.2

The system under test is the back-fill migration in
``slaktbusken/services/foster_sync.py``:

* ``backfill_orphan_placement_events(project)`` — the reusable, pure helper the
  GEDCOM importer (task 10.3) also calls. For each orphan foster/adoptive
  Parent_Set (a group of foster/adoptive links with no backing
  Placement_Start_Event) it creates one *dateless* placement start event and
  records it on the family's ``event_ids``.
* ``migrate_orphan_links(project)`` — back-fill then
  ``sync_parentage_links``, establishing the "every derived link is backed by an
  event" invariant without deleting any foster/adoptive data (Req 13.3). It
  preserves pre-feature descriptive adoption events (Req 13.5).

These are production-behaviour tests (expected to PASS), not bugfix exploration
tests.

Validates: Requirements 13.3, 13.5
Supports: Property 8 (task 3.4) — no foster/adoptive link lost across
migrate+sync.
"""

from __future__ import annotations

import copy

from hypothesis import given, settings

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.foster_sync import (
    backfill_orphan_placement_events,
    migrate_orphan_links,
    sync_parentage_links,
)

from tests.test_foster.foster_strategies import (
    DERIVED_PARENTAGE,
    foster_project,
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _person(person_id: str, sex: str = "U") -> Person:
    return Person(
        id=person_id,
        sex=sex,
        names=[Name(type="birth", given="A", surname="B")],
    )


def _orphan_family(
    family_id: str, parentage: str, child_id: str, parent_ids: list[str]
) -> Family:
    """A family carrying foster/adoptive links with NO backing event."""
    return Family(
        id=family_id,
        partners=[FamilyPartner(person_id=p, role="partner") for p in parent_ids],
        children=[child_id],
        parent_child_links=[
            ParentChildLink(child_id=child_id, parent_id=p, parentage_type=parentage)
            for p in parent_ids
        ],
        event_ids=[],
    )


def _project(persons: list[Person], families: list[Family], events: list[Event]) -> ProjectData:
    return ProjectData(
        project=ProjectMetadata(title="Orphan Migration Test"),
        persons=persons,
        families=families,
        events=events,
    )


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------


def _derived_link_set(project: ProjectData) -> set[tuple[str, str, str]]:
    """Every foster/adoptive link as ``(parentage_type, child_id, parent_id)``."""
    out: set[tuple[str, str, str]] = set()
    for family in project.families:
        for link in family.parent_child_links:
            if link.parentage_type in DERIVED_PARENTAGE and link.parent_id is not None:
                out.add((link.parentage_type, link.child_id, link.parent_id))
    return out


def _derived_link_count(project: ProjectData) -> int:
    return sum(
        1
        for family in project.families
        for link in family.parent_child_links
        if link.parentage_type in DERIVED_PARENTAGE
    )


def _events_of_type(project: ProjectData, event_type: str) -> list[Event]:
    return [ev for ev in project.events if ev.type == event_type]


def _child_of(event: Event, child_role: str) -> str | None:
    for p in event.participants:
        if p.role == child_role:
            return p.person_id
    return None


def _parents_of(event: Event, parent_role: str) -> list[str]:
    return [p.person_id for p in event.participants if p.role == parent_role]


# ---------------------------------------------------------------------------
# Orphan foster family
# ---------------------------------------------------------------------------


class TestOrphanFosterFamily:
    """An orphan foster family gains a dateless foster_home event and keeps
    its link after migrate+sync.

    **Validates: Requirement 13.3**
    """

    def test_orphan_foster_backfilled_and_link_survives(self) -> None:
        persons = [_person("child"), _person("fp", "F")]
        family = _orphan_family("fam1", "foster", "child", ["fp"])
        project = _project(persons, [family], [])

        before = _derived_link_set(project)
        assert ("foster", "child", "fp") in before

        migrate_orphan_links(project)

        # A dateless Fosterhem event was created naming the child and parent.
        foster_events = _events_of_type(project, "foster_home")
        assert len(foster_events) == 1
        event = foster_events[0]
        assert event.date is None
        assert _child_of(event, "fosterbarn") == "child"
        assert _parents_of(event, "fosterförälder") == ["fp"]

        # The foster link survived (nothing deleted).
        assert ("foster", "child", "fp") in _derived_link_set(project)
        assert _derived_link_count(project) >= 1


# ---------------------------------------------------------------------------
# Orphan adoptive family
# ---------------------------------------------------------------------------


class TestOrphanAdoptiveFamily:
    """An orphan adoptive family gains a dateless adoption event and keeps its
    link after migrate+sync.

    **Validates: Requirement 13.3**
    """

    def test_orphan_adoptive_backfilled_and_link_survives(self) -> None:
        persons = [_person("child"), _person("ap", "M")]
        family = _orphan_family("fam1", "adoptive", "child", ["ap"])
        project = _project(persons, [family], [])

        migrate_orphan_links(project)

        adoption_events = _events_of_type(project, "adoption")
        assert len(adoption_events) == 1
        event = adoption_events[0]
        assert event.date is None
        assert _child_of(event, "adopterad") == "child"
        assert _parents_of(event, "adoptivförälder") == ["ap"]

        assert ("adoptive", "child", "ap") in _derived_link_set(project)


# ---------------------------------------------------------------------------
# Two-parent orphan set -> single event naming both
# ---------------------------------------------------------------------------


class TestTwoParentOrphanSet:
    """A two-parent orphan set yields a SINGLE event naming both parents.

    **Validates: Requirement 13.3**
    """

    def test_two_parent_orphan_single_event(self) -> None:
        persons = [_person("child"), _person("p1", "M"), _person("p2", "F")]
        family = _orphan_family("fam1", "foster", "child", ["p1", "p2"])
        project = _project(persons, [family], [])

        migrate_orphan_links(project)

        foster_events = _events_of_type(project, "foster_home")
        assert len(foster_events) == 1, "a two-parent set must yield exactly one event"
        parents = _parents_of(foster_events[0], "fosterförälder")
        assert set(parents) == {"p1", "p2"}
        assert len(parents) == 2

        # Both links survive.
        links = _derived_link_set(project)
        assert ("foster", "child", "p1") in links
        assert ("foster", "child", "p2") in links


# ---------------------------------------------------------------------------
# Pre-feature descriptive adoption event is preserved and derives nothing
# ---------------------------------------------------------------------------


class TestDescriptiveAdoptionPreserved:
    """A pre-feature descriptive adoption event (child, NO parent) is preserved
    and derives no link.

    **Validates: Requirement 13.5**
    """

    def test_descriptive_adoption_untouched(self) -> None:
        persons = [_person("child")]
        descriptive = Event(
            id="event_desc",
            type="adoption",
            participants=[Participant(person_id="child", role="adopterad")],
            date=DateValue(value="1950", precision="year"),
        )
        project = _project(persons, [], [descriptive])

        created = migrate_orphan_links(project)

        # No back-fill event created for a parent-less descriptive adoption.
        assert created == []
        # The descriptive event is unchanged and still present.
        assert descriptive in project.events
        assert descriptive.date is not None and descriptive.date.value == "1950"
        assert _parents_of(descriptive, "adoptivförälder") == []
        # It derived no foster/adoptive links.
        assert _derived_link_count(project) == 0

    def test_descriptive_adoption_alongside_orphan_adoptive(self) -> None:
        """A descriptive adoption for the same child does not back an orphan set
        that names a parent — the orphan still gets its own event."""
        persons = [_person("child"), _person("ap", "M")]
        descriptive = Event(
            id="event_desc",
            type="adoption",
            participants=[Participant(person_id="child", role="adopterad")],
            date=None,
        )
        family = _orphan_family("fam1", "adoptive", "child", ["ap"])
        project = _project(persons, [family], [descriptive])

        created = migrate_orphan_links(project)

        # The descriptive event stays parent-less; a new event backs the orphan.
        assert descriptive in project.events
        assert _parents_of(descriptive, "adoptivförälder") == []
        assert len(created) == 1
        assert _parents_of(created[0], "adoptivförälder") == ["ap"]
        assert ("adoptive", "child", "ap") in _derived_link_set(project)


# ---------------------------------------------------------------------------
# An already-backed family is not duplicated
# ---------------------------------------------------------------------------


class TestAlreadyBackedNotDuplicated:
    """A family already backed by a placement event gains no duplicate event.

    **Validates: Requirement 13.3**
    """

    def test_backed_family_no_duplicate(self) -> None:
        persons = [_person("child"), _person("fp", "F")]
        start = Event(
            id="event_start",
            type="foster_home",
            participants=[
                Participant(person_id="child", role="fosterbarn"),
                Participant(person_id="fp", role="fosterförälder"),
            ],
            date=None,
        )
        # Build the project then sync so the derived family records the event id.
        project = _project(persons, [], [start])
        sync_parentage_links(project)
        assert ("foster", "child", "fp") in _derived_link_set(project)

        foster_events_before = len(_events_of_type(project, "foster_home"))

        created = backfill_orphan_placement_events(project)

        assert created == [], "an already-backed family must not be duplicated"
        assert len(_events_of_type(project, "foster_home")) == foster_events_before


# ---------------------------------------------------------------------------
# Idempotence: migrate twice == migrate once
# ---------------------------------------------------------------------------


class TestMigrationIdempotent:
    """Running the migration twice must not create duplicate back-fill events.

    **Validates: Requirement 13.3**
    """

    def test_migrate_twice_equals_once(self) -> None:
        persons = [_person("child"), _person("p1", "M"), _person("p2", "F")]
        families = [
            _orphan_family("fam_f", "foster", "child", ["p1"]),
            _orphan_family("fam_a", "adoptive", "child", ["p1", "p2"]),
        ]
        project = _project(persons, families, [])

        migrate_orphan_links(project)
        foster_count = len(_events_of_type(project, "foster_home"))
        adoption_count = len(_events_of_type(project, "adoption"))
        links_once = _derived_link_set(project)

        # Second run must be a no-op with respect to event creation.
        created_second = backfill_orphan_placement_events(project)
        assert created_second == []
        migrate_orphan_links(project)

        assert len(_events_of_type(project, "foster_home")) == foster_count
        assert len(_events_of_type(project, "adoption")) == adoption_count
        assert _derived_link_set(project) == links_once


# ---------------------------------------------------------------------------
# No foster/adoptive link count decreases across migrate+sync
# ---------------------------------------------------------------------------


class TestNoLinkLoss:
    """No foster/adoptive link is lost across migrate+sync.

    **Validates: Requirement 13.3**
    """

    def test_link_count_does_not_decrease(self) -> None:
        persons = [
            _person("c1"),
            _person("c2"),
            _person("p1", "M"),
            _person("p2", "F"),
        ]
        families = [
            _orphan_family("fam1", "foster", "c1", ["p1"]),
            _orphan_family("fam2", "adoptive", "c2", ["p1", "p2"]),
        ]
        project = _project(persons, families, [])

        before = _derived_link_set(project)

        migrate_orphan_links(project)

        after = _derived_link_set(project)
        assert before.issubset(after), "a foster/adoptive link was lost by migrate+sync"
        assert len(after) >= len(before)


# ---------------------------------------------------------------------------
# Property test: no foster/adoptive link lost across migrate+sync
# ---------------------------------------------------------------------------


class TestNoLinkLostProperty:
    """Feature: foster-parents, Property 8 (support): migrate+sync loses no link.

    Over arbitrary generated projects — including ones carrying orphan
    foster/adoptive links and pre-feature descriptive adoption events — running
    the on-load migration (back-fill then sync) deletes no foster/adoptive link
    that existed before. Every derived link present before the migration is
    present after it.

    **Validates: Requirement 13.3**
    """

    @given(fp=foster_project())
    @settings(max_examples=100, deadline=None)
    def test_no_foster_adoptive_link_lost(self, fp) -> None:
        """migrate+sync preserves every pre-existing foster/adoptive link.

        Feature: foster-parents, Property 8 (support)
        **Validates: Requirement 13.3**
        """
        project = copy.deepcopy(fp.project)
        before = _derived_link_set(project)

        migrate_orphan_links(project)

        after = _derived_link_set(project)
        missing = before - after
        assert not missing, f"migrate+sync dropped foster/adoptive links: {missing}"
