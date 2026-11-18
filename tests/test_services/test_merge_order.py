"""Confluence and order independence of merges (task 13.10, Req 25, 32.6).

Property 36: two merges whose affected persons do not overlap give equivalent
projects in either order; unmerged relatives stay separate and attached.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings, strategies as st

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services import merge_planner as mp
from slaktbusken.services.merge_planner import MergeDecisions, build_plan

pytestmark = pytest.mark.mandatory_integrity

# Generations: parents (x*) -> merge candidates (p1..p4) -> children (y*).
PARENTS = ["x0", "x1", "x2"]
MIDDLE = ["p1", "p2", "p3", "p4"]
CHILDREN = ["y0", "y1", "y2", "y3"]


def _person(pid: str, occupation=None) -> Person:
    # Relatives get distinct names (no automatic pairing); the two persons of a
    # merge pair share a name so the plan has no unresolved name choice.
    given = {"p1": "Pa", "p2": "Pa", "p3": "Pb", "p4": "Pb"}.get(pid, "N" + pid)
    return Person(id=pid, sex="M", names=[Name("birth", given, "Berg")], occupation=occupation)


@st.composite
def projects(draw):
    persons = []
    for pid in PARENTS + MIDDLE + CHILDREN:
        occ = draw(st.sampled_from([None, "Smed"])) if pid in ("p1", "p3") else None
        persons.append(_person(pid, occ))
    families = []
    fid = 0

    def add(partners, children):
        nonlocal fid
        fid += 1
        families.append(
            Family(
                id=f"F{fid}",
                partners=[FamilyPartner(p, "partner") for p in partners],
                children=list(children),
                parent_child_links=[
                    ParentChildLink(c, p, "biological") for c in children for p in partners
                ],
            )
        )

    for _ in range(draw(st.integers(0, 4))):
        parent = draw(st.lists(st.sampled_from(PARENTS), min_size=1, max_size=2, unique=True))
        add(parent, draw(st.lists(st.sampled_from(MIDDLE), min_size=1, max_size=3, unique=True)))
    for _ in range(draw(st.integers(0, 4))):
        # One merge candidate per family so no self-partner conflict arises.
        parent = [draw(st.sampled_from(MIDDLE))]
        add(parent, draw(st.lists(st.sampled_from(CHILDREN), min_size=1, max_size=3, unique=True)))
    return ProjectData(persons=persons, families=families)


def _merge(data: ProjectData, survivor: str, merged: str):
    plan = build_plan(
        data, None, MergeDecisions(survivor, merged, survivor_id=survivor, survivor_confirmed=True)
    )
    return plan, (mp.apply_change_set(data, plan.change_set) if plan.can_execute else data)


def _canonical(data: ProjectData):
    """Persons, field values and relationships; ignores family ids and entry order."""
    persons = {
        p.id: (
            p.sex,
            p.title,
            p.occupation,
            tuple(sorted((n.type, n.given, n.surname) for n in p.names)),
        )
        for p in data.persons
    }
    families = {
        (
            frozenset(fp.person_id for fp in f.partners),
            frozenset(f.children),
        )
        for f in data.families
    }
    links = {
        (l.child_id, l.parent_id, l.parentage_type)
        for f in data.families
        for l in f.parent_child_links
    }
    return persons, families, links


@settings(max_examples=100, deadline=None)
@given(projects())
def test_property_36_independent_merges_commute(data):
    """**Validates: Requirements 25.1, 25.2, 25.3, 25.4**"""
    first_a = build_plan(data, None, MergeDecisions("p1", "p2", survivor_id="p1", survivor_confirmed=True))
    first_c = build_plan(data, None, MergeDecisions("p3", "p4", survivor_id="p3", survivor_confirmed=True))
    assume(first_a.can_execute and first_c.can_execute)

    # Order 1: (p2 into p1) then (p4 into p3)
    _, after_a = _merge(data, "p1", "p2")
    plan_c2, ab = _merge(after_a, "p3", "p4")
    assert plan_c2.can_execute
    # Order 2: (p4 into p3) then (p2 into p1)
    _, after_c = _merge(data, "p3", "p4")
    plan_a2, ba = _merge(after_c, "p1", "p2")
    assert plan_a2.can_execute

    assert _canonical(ab) == _canonical(ba)

    persons, _, links = _canonical(ab)
    # Unmerged relatives stay separate persons and all attach to the survivors.
    for pid in PARENTS + CHILDREN:
        assert pid in persons
    assert "p2" not in persons and "p4" not in persons
    orig = _canonical(data)[2]
    rename = {"p2": "p1", "p4": "p3"}
    expected = {(rename.get(c, c), rename.get(p, p), t) for c, p, t in orig}
    assert links == expected
