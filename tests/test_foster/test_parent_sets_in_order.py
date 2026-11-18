"""Unit tests for the Parent_Set ordering helper (task 2.2, Requirement 2.5)."""

from __future__ import annotations

import copy

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.project import ProjectData
from slaktbusken.services.foster_sync import parent_sets_in_order


def _date(value: str) -> DateValue:
    return DateValue(value=value, precision="day")


def _foster_start(event_id: str, child_id: str, parent_id: str,
                  date: DateValue | None = None) -> Event:
    return Event(
        id=event_id,
        type="foster_home",
        participants=[
            Participant(person_id=child_id, role="fosterbarn"),
            Participant(person_id=parent_id, role="fosterförälder"),
        ],
        date=date,
    )


def _foster_family(family_id: str, event_id: str, child_id: str,
                   parent_ids: list[str]) -> Family:
    return Family(
        id=family_id,
        partners=[FamilyPartner(person_id=pid, role="partner") for pid in parent_ids],
        children=[child_id],
        parent_child_links=[
            ParentChildLink(child_id=child_id, parent_id=pid, parentage_type="foster")
            for pid in parent_ids
        ],
        event_ids=[event_id],
    )


def test_orders_dated_parent_sets_by_start_date() -> None:
    """Dated Parent_Sets are returned earliest start date first."""
    project = ProjectData(
        families=[
            _foster_family("fam_b", "ev_b", "child", ["p2"]),
            _foster_family("fam_a", "ev_a", "child", ["p1"]),
        ],
        events=[
            _foster_start("ev_b", "child", "p2", _date("1960-01-01")),
            _foster_start("ev_a", "child", "p1", _date("1950-01-01")),
        ],
    )

    result = parent_sets_in_order(project, "child", "foster")

    assert [f.id for f in result] == ["fam_a", "fam_b"]


def test_undated_sets_come_last_in_project_order() -> None:
    """Undated start events sort after all dated ones, keeping project order."""
    project = ProjectData(
        families=[
            _foster_family("fam_undated_1", "ev_u1", "child", ["p1"]),
            _foster_family("fam_dated", "ev_d", "child", ["p2"]),
            _foster_family("fam_undated_2", "ev_u2", "child", ["p3"]),
        ],
        events=[
            # Project order: u1 before u2; both undated.
            _foster_start("ev_u1", "child", "p1"),
            _foster_start("ev_d", "child", "p2", _date("1970-05-05")),
            _foster_start("ev_u2", "child", "p3"),
        ],
    )

    result = parent_sets_in_order(project, "child", "foster")

    assert [f.id for f in result] == ["fam_dated", "fam_undated_1", "fam_undated_2"]


def test_filters_by_parentage_type_and_child() -> None:
    """Only the requested child's sets of the requested type are returned."""
    adoption_event = Event(
        id="ev_adopt",
        type="adoption",
        participants=[
            Participant(person_id="child", role="adopterad"),
            Participant(person_id="p9", role="adoptivförälder"),
        ],
        date=_date("1955-01-01"),
    )
    adoption_family = Family(
        id="fam_adopt",
        partners=[FamilyPartner(person_id="p9", role="partner")],
        children=["child"],
        parent_child_links=[
            ParentChildLink(child_id="child", parent_id="p9", parentage_type="adoptive")
        ],
        event_ids=["ev_adopt"],
    )
    project = ProjectData(
        families=[
            _foster_family("fam_foster", "ev_foster", "child", ["p1"]),
            _foster_family("fam_other_child", "ev_other", "other", ["p2"]),
            adoption_family,
        ],
        events=[
            _foster_start("ev_foster", "child", "p1", _date("1950-01-01")),
            _foster_start("ev_other", "other", "p2", _date("1951-01-01")),
            adoption_event,
        ],
    )

    foster = parent_sets_in_order(project, "child", "foster")
    adoptive = parent_sets_in_order(project, "child", "adoptive")

    assert [f.id for f in foster] == ["fam_foster"]
    assert [f.id for f in adoptive] == ["fam_adopt"]


def test_does_not_mutate_project() -> None:
    """The helper performs a read-only sort without touching stored data."""
    project = ProjectData(
        families=[
            _foster_family("fam_b", "ev_b", "child", ["p2"]),
            _foster_family("fam_a", "ev_a", "child", ["p1"]),
        ],
        events=[
            _foster_start("ev_b", "child", "p2", _date("1960-01-01")),
            _foster_start("ev_a", "child", "p1", _date("1950-01-01")),
        ],
    )
    before = copy.deepcopy(project)

    parent_sets_in_order(project, "child", "foster")

    assert [f.id for f in project.families] == [f.id for f in before.families]
    assert [e.id for e in project.events] == [e.id for e in before.events]
    assert project == before


def test_unknown_parentage_type_returns_empty() -> None:
    """A parentage type the helper does not derive yields no sets."""
    project = ProjectData(
        families=[_foster_family("fam_a", "ev_a", "child", ["p1"])],
        events=[_foster_start("ev_a", "child", "p1", _date("1950-01-01"))],
    )

    assert parent_sets_in_order(project, "child", "biological") == []


def test_two_parent_set_returned_once() -> None:
    """A two-parent Parent_Set is a single family returned once."""
    project = ProjectData(
        families=[_foster_family("fam_pair", "ev_pair", "child", ["p1", "p2"])],
        events=[_foster_start("ev_pair", "child", "p1", _date("1950-01-01"))],
    )

    result = parent_sets_in_order(project, "child", "foster")

    assert [f.id for f in result] == ["fam_pair"]
