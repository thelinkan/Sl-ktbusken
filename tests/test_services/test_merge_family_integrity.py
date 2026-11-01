"""Family and relationship integrity of the merge plan (task 11.4, Req 23 to 26.2).

Mandatory group (b): family relationship integrity. Never skipped.
"""

from __future__ import annotations

import copy

import pytest

from slaktbusken.model.event import Event, Participant
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services import merge_planner as mp
from slaktbusken.services.merge_planner import MergeDecisions, build_plan
from slaktbusken.services.merge_planner_families import SAME_NAME_NOTE

pytestmark = pytest.mark.mandatory_integrity


def _person(pid, given="Anna", surname="Berg", sex="M"):
    return Person(id=pid, sex=sex, names=[Name("birth", given, surname)])


def _fam(fid, partners, children, links=(), event_ids=()):
    return Family(
        id=fid,
        partners=[FamilyPartner(p, "partner") for p in partners],
        children=list(children),
        parent_child_links=[ParentChildLink(c, p, t) for c, p, t in links],
        event_ids=list(event_ids),
    )


def _bio(child, parent):
    return (child, parent, "biological")


def _plan(data):
    """Plan the merge of p1 and p2 (survivor p1) and prove the project is untouched."""
    before = copy.deepcopy(data)
    plan = build_plan(
        data, None, MergeDecisions("p1", "p2", survivor_id="p1", survivor_confirmed=True)
    )
    assert data == before
    return plan


def _final(data, plan):
    return mp.apply_change_set(data, plan.change_set)


def _codes(plan, blocking=None):
    return [c.code for c in plan.conflicts if blocking is None or c.is_blocking == blocking]


def test_cycle_blocks_merge():
    # p1 is a parent of x and x is a parent of p2: p1 = p2 would be its own ancestor.
    data = ProjectData(
        persons=[_person("p1"), _person("p2"), _person("x", "Kalle")],
        families=[
            _fam("F1", ["p1"], ["x"], [_bio("x", "p1")]),
            _fam("F2", ["x"], ["p2"], [_bio("p2", "x")]),
        ],
    )
    plan = _plan(data)
    cycle = [c for c in plan.blocking if c.code == "cycle"]
    assert len(cycle) == 1
    assert "p1" in cycle[0].message and "x" in cycle[0].message
    assert not plan.can_execute


def test_self_partner_blocks_merge():
    data = ProjectData(
        persons=[_person("p1"), _person("p2")],
        families=[_fam("F1", ["p1", "p2"], [])],
    )
    plan = _plan(data)
    blocking = [c for c in plan.blocking if c.code == "self_partner"]
    assert len(blocking) == 1 and "F1" in blocking[0].message
    assert not plan.can_execute


def test_self_parent_child_link_blocks_merge():
    data = ProjectData(
        persons=[_person("p1"), _person("p2")],
        families=[_fam("F1", ["p1"], ["p2"], [_bio("p2", "p1")])],
    )
    plan = _plan(data)
    assert "self_parent_child" in _codes(plan, blocking=True)
    assert not plan.can_execute


def test_parent_child_link_types_preserved():
    data = ProjectData(
        persons=[_person("p1"), _person("p2"), _person("c", "Kalle")],
        families=[
            _fam("F1", ["p1"], ["c"], [_bio("c", "p1")]),
            _fam("F2", ["p2"], ["c"], [("c", "p2", "legal")]),
            _fam("F3", ["p2"], ["c"], [("c", "p2", "legal")]),
        ],
    )
    plan = _plan(data)
    assert not plan.blocking
    warnings = [c for c in plan.warnings if c.code == "parentage_type_conflict"]
    assert len(warnings) == 1
    assert "biological" in warnings[0].message and "legal" in warnings[0].message
    final = _final(data, plan)
    links = {
        (l.child_id, l.parent_id, l.parentage_type)
        for f in final.families for l in f.parent_child_links
    }
    assert links == {("c", "p1", "biological"), ("c", "p1", "legal")}
    # Several parent sets of different types never block by themselves.
    assert plan.can_execute


def test_foster_adoptive_families_resynchronised():
    foster = Event(
        id="E1", type="foster_home",
        participants=[Participant("c", "fosterbarn"), Participant("p2", "fosterförälder")],
    )
    adoption = Event(
        id="E2", type="adoption",
        participants=[Participant("d", "adopterad"), Participant("p2", "adoptivförälder")],
    )
    data = ProjectData(
        persons=[_person("p1"), _person("p2"), _person("c", "Kalle"), _person("d", "Lisa", "F")],
        events=[foster, adoption],
        families=[
            Family("F1", [FamilyPartner("p2", "father")], ["c"],
                   [ParentChildLink("c", "p2", "foster")], ["E1"]),
            Family("F2", [FamilyPartner("p2", "father")], ["d"],
                   [ParentChildLink("d", "p2", "adoptive")], ["E2"]),
        ],
    )
    plan = _plan(data)
    assert not plan.blocking
    final = _final(data, plan)
    by_id = {f.id: f for f in final.families}
    assert [p.person_id for p in by_id["F1"].partners] == ["p1"]
    assert [(l.child_id, l.parent_id, l.parentage_type) for l in by_id["F1"].parent_child_links] == [
        ("c", "p1", "foster")
    ]
    assert by_id["F1"].event_ids == ["E1"] and by_id["F2"].event_ids == ["E2"]
    assert set(plan.preview.changed_family_ids) == {"F1", "F2"}
    assert plan.preview.family_count == 2
    # The new foster/adoptive links are the ones the real sync produces: a second
    # sync of the synchronised result changes nothing.
    from slaktbusken.services.foster_sync import sync_parentage_links

    again = copy.deepcopy(final)
    sync_parentage_links(again)
    assert again.families == final.families


def test_two_brita_seven_distinct_children():
    kids_1 = ["pelle", "kalle1", "olle1"]
    kids_2 = ["stina", "fia", "kalle2", "olle2"]
    names = {"pelle": "Pelle", "kalle1": "Kalle", "olle1": "Olle", "stina": "Stina",
             "fia": "Fia", "kalle2": "Kalle", "olle2": "Olle"}
    data = ProjectData(
        persons=[_person("p1", "Brita", sex="F"), _person("p2", "Brita", sex="F"),
                 _person("h1", "Per"), _person("h2", "Nils")]
        + [_person(k, n) for k, n in names.items()],
        families=[
            _fam("F1", ["p1", "h1"], kids_1, [_bio(k, "p1") for k in kids_1]),
            _fam("F2", ["p2", "h2"], kids_2, [_bio(k, "p2") for k in kids_2]),
        ],
    )
    plan = _plan(data)
    assert not plan.blocking
    final = _final(data, plan)
    assert len(final.families) == 2
    children = [c for f in final.families if any(p.person_id == "p1" for p in f.partners)
                for c in f.children]
    assert len(children) == 7 and set(children) == set(names)
    assert {p.id for p in final.persons} == {"p1", "h1", "h2", *names}
    assert len([l for f in final.families for l in f.parent_child_links]) == 7
    assert plan.change_set.replaced["persons"].keys() == {"p1"}


def test_same_name_siblings_stay_distinct():
    data = ProjectData(
        persons=[_person("p1"), _person("p2"), _person("k1", "Kalle"), _person("k2", "kalle"),
                 _person("m1", "Mor", sex="F"), _person("m2", "Mamma", sex="F")],
        families=[
            _fam("F1", ["m1"], ["p1", "k1"], [_bio("p1", "m1"), _bio("k1", "m1")]),
            _fam("F2", ["m2"], ["p2", "k2"], [_bio("p2", "m2"), _bio("k2", "m2")]),
        ],
    )
    plan = _plan(data)
    assert not plan.blocking
    notes = [i for i in plan.items if i.item_id == "same_name_note"]
    assert len(notes) == 1 and notes[0].detail == SAME_NAME_NOTE
    # Nothing is paired, merged or proposed for the two Kalle.
    assert plan.change_set.replaced["persons"].keys() == {"p1"}
    assert not plan.change_set.removed.get("persons", set()) - {"p2"}
    assert not any({"k1", "k2"} <= set(c.subjects) for c in plan.conflicts)
    assert {i.disposition for i in plan.items if i.item_id in ("k1", "k2")} == {
        mp.Disposition.LEFT_SEPARATE
    }
    final = _final(data, plan)
    assert {"k1", "k2"} <= {p.id for p in final.persons}
    assert [l.parent_id for f in final.families for l in f.parent_child_links
            if l.child_id in ("k1", "k2")] == ["m1", "m2"]


def test_duplicate_families_stay_separate_with_warning():
    data = ProjectData(
        persons=[_person("p1"), _person("p2"), _person("x", "Eva", sex="F"),
                 _person("c1", "Ola"), _person("c2", "Lina", sex="F")],
        families=[
            _fam("F1", ["p1", "x"], ["c1"], [_bio("c1", "p1"), _bio("c1", "x")]),
            _fam("F2", ["p2", "x"], ["c2"], [_bio("c2", "p2"), _bio("c2", "x")]),
        ],
    )
    plan = _plan(data)
    assert not plan.blocking and plan.can_execute
    dup = [c for c in plan.warnings if c.code == "duplicate_family"]
    assert len(dup) == 1 and set(dup[0].subjects) == {"F1", "F2"}
    assert "F1" in dup[0].message and "F2" in dup[0].message
    final = _final(data, plan)
    by_id = {f.id: f for f in final.families}
    assert set(by_id) == {"F1", "F2"}
    assert by_id["F1"].children == ["c1"] and by_id["F2"].children == ["c2"]
    assert len(by_id["F1"].parent_child_links) == 2 and len(by_id["F2"].parent_child_links) == 2
