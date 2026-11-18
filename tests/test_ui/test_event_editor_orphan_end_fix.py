"""Unit tests for EventEditor's orphan placement-end one-click fix.

When the user saves a Placement_End_Event (``foster_home_ended`` /
``adoption_ended``) that pairs to no existing Placement_Start_Event, the editor
offers to create a matching dateless start (same child, same parents) so the end
is no longer orphaned (Requirement 2A.5).

The modal confirmation dialog is NOT exercised here; the testable core logic is
factored into two helpers, verified directly:

- ``_find_matching_placement_start`` — returns the matching start event, or
  ``None`` when the end is an orphan (same child + same parent set,
  order-independent, for both foster and adoptive types).
- ``_build_matching_placement_start`` — produces a dateless start of the mapped
  type naming the same child/parents in the correct roles.

Covers Requirement 2A.5.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.editors.event_editor import (
    PLACEMENT_END_TO_START,
    EventEditor,
)


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def project_data() -> ProjectData:
    """Return project data with one child and two parents."""
    pd = ProjectData()
    pd.persons.append(
        Person(
            id="child1",
            sex="female",
            names=[Name(type="birth", given="Anna", surname="Larsson")],
        )
    )
    pd.persons.append(
        Person(
            id="parent1",
            sex="female",
            names=[Name(type="birth", given="Karin", surname="Nilsson")],
        )
    )
    pd.persons.append(
        Person(
            id="parent2",
            sex="male",
            names=[Name(type="birth", given="Erik", surname="Nilsson")],
        )
    )
    return pd


def _end_event(
    end_type: str,
    child_id: str,
    parent_ids: list[str],
) -> Event:
    """Build a Placement_End_Event with the given child and parents."""
    child_role = "fosterbarn" if end_type == "foster_home_ended" else "adopterad"
    parent_role = (
        "fosterförälder" if end_type == "foster_home_ended" else "adoptivförälder"
    )
    participants = [Participant(person_id=child_id, role=child_role)]
    for pid in parent_ids:
        participants.append(Participant(person_id=pid, role=parent_role))
    return Event(id="end1", type=end_type, participants=participants)


def _start_event(
    start_type: str,
    child_id: str,
    parent_ids: list[str],
    event_id: str = "start1",
) -> Event:
    """Build a Placement_Start_Event with the given child and parents."""
    child_role = "fosterbarn" if start_type == "foster_home" else "adopterad"
    parent_role = (
        "fosterförälder" if start_type == "foster_home" else "adoptivförälder"
    )
    participants = [Participant(person_id=child_id, role=child_role)]
    for pid in parent_ids:
        participants.append(Participant(person_id=pid, role=parent_role))
    return Event(id=event_id, type=start_type, participants=participants)


class TestEndToStartMapping:
    """The end→start type mapping is complete and correct."""

    def test_mapping(self) -> None:
        assert PLACEMENT_END_TO_START["foster_home_ended"] == "foster_home"
        assert PLACEMENT_END_TO_START["adoption_ended"] == "adoption"


class TestFindMatchingStartOrphan:
    """`_find_matching_placement_start` returns None when no start matches."""

    def test_foster_orphan_returns_none(self, project_data: ProjectData) -> None:
        editor = EventEditor(project_data)
        end = _end_event("foster_home_ended", "child1", ["parent1"])
        assert editor._find_matching_placement_start(end) is None

    def test_adoption_orphan_returns_none(self, project_data: ProjectData) -> None:
        editor = EventEditor(project_data)
        end = _end_event("adoption_ended", "child1", ["parent1"])
        assert editor._find_matching_placement_start(end) is None

    def test_different_child_is_orphan(self, project_data: ProjectData) -> None:
        # A start exists but for a different child — still orphan.
        project_data.events.append(
            _start_event("foster_home", "child1", ["parent1"])
        )
        editor = EventEditor(project_data)
        end = _end_event("foster_home_ended", "parent2", ["parent1"])
        assert editor._find_matching_placement_start(end) is None

    def test_different_parent_set_is_orphan(
        self, project_data: ProjectData
    ) -> None:
        # Same child but a different parent set — still orphan.
        project_data.events.append(
            _start_event("foster_home", "child1", ["parent1"])
        )
        editor = EventEditor(project_data)
        end = _end_event("foster_home_ended", "child1", ["parent2"])
        assert editor._find_matching_placement_start(end) is None

    def test_wrong_start_type_is_orphan(self, project_data: ProjectData) -> None:
        # An adoption start does not pair with a foster end.
        project_data.events.append(
            _start_event("adoption", "child1", ["parent1"])
        )
        editor = EventEditor(project_data)
        end = _end_event("foster_home_ended", "child1", ["parent1"])
        assert editor._find_matching_placement_start(end) is None


class TestFindMatchingStartMatch:
    """`_find_matching_placement_start` returns the start when one matches."""

    def test_foster_single_parent_match(self, project_data: ProjectData) -> None:
        start = _start_event("foster_home", "child1", ["parent1"])
        project_data.events.append(start)
        editor = EventEditor(project_data)
        end = _end_event("foster_home_ended", "child1", ["parent1"])
        assert editor._find_matching_placement_start(end) is start

    def test_adoption_single_parent_match(
        self, project_data: ProjectData
    ) -> None:
        start = _start_event("adoption", "child1", ["parent1"])
        project_data.events.append(start)
        editor = EventEditor(project_data)
        end = _end_event("adoption_ended", "child1", ["parent1"])
        assert editor._find_matching_placement_start(end) is start

    def test_match_is_order_independent(self, project_data: ProjectData) -> None:
        # Start lists parents [parent1, parent2]; end lists [parent2, parent1].
        start = _start_event("foster_home", "child1", ["parent1", "parent2"])
        project_data.events.append(start)
        editor = EventEditor(project_data)
        end = _end_event("foster_home_ended", "child1", ["parent2", "parent1"])
        assert editor._find_matching_placement_start(end) is start


class TestBuildMatchingStart:
    """`_build_matching_placement_start` builds the right dateless start."""

    def test_foster_build(self, project_data: ProjectData) -> None:
        editor = EventEditor(project_data)
        end = _end_event("foster_home_ended", "child1", ["parent1", "parent2"])
        start = editor._build_matching_placement_start(end)

        assert start.type == "foster_home"
        assert start.date is None
        assert start.place is None
        assert start.id != end.id

        children = [p.person_id for p in start.participants if p.role == "fosterbarn"]
        parents = {
            p.person_id for p in start.participants if p.role == "fosterförälder"
        }
        assert children == ["child1"]
        assert parents == {"parent1", "parent2"}

    def test_adoption_build(self, project_data: ProjectData) -> None:
        editor = EventEditor(project_data)
        end = _end_event("adoption_ended", "child1", ["parent1"])
        start = editor._build_matching_placement_start(end)

        assert start.type == "adoption"
        assert start.date is None
        assert start.place is None

        children = [p.person_id for p in start.participants if p.role == "adopterad"]
        parents = {
            p.person_id for p in start.participants if p.role == "adoptivförälder"
        }
        assert children == ["child1"]
        assert parents == {"parent1"}

    def test_built_start_pairs_the_end(self, project_data: ProjectData) -> None:
        # Building the start and appending it makes the end no longer orphaned.
        editor = EventEditor(project_data)
        end = _end_event("foster_home_ended", "child1", ["parent1"])
        assert editor._find_matching_placement_start(end) is None

        start = editor._build_matching_placement_start(end)
        project_data.events.append(start)
        assert editor._find_matching_placement_start(end) is start

    def test_built_start_ignores_end_date(self, project_data: ProjectData) -> None:
        # Even if the end carries a date, the built start is dateless.
        editor = EventEditor(project_data)
        end = _end_event("foster_home_ended", "child1", ["parent1"])
        end.date = DateValue(value="1850", precision="year")
        start = editor._build_matching_placement_start(end)
        assert start.date is None
