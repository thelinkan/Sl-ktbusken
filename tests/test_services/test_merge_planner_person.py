"""Planning of attributes, names, events and residences (task 11.2, Req 21)."""

from __future__ import annotations

import copy

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import ResidenceFact
from slaktbusken.services import merge_planner as mp
from slaktbusken.services.merge_planner import Disposition, MergeDecisions, build_plan


def _person(pid, sex="M", given="Anna", surname="Berg", **kw):
    return Person(id=pid, sex=sex, names=[Name("birth", given, surname)], **kw)


def _event(eid, etype, people, date=None, place=None, roles=None):
    roles = roles or ["self"] * len(people)
    return Event(
        id=eid, type=etype,
        participants=[Participant(p, r) for p, r in zip(people, roles)],
        date=DateValue(date, "day") if date else None,
        place=PlaceRef(place) if place else None,
    )


def _data(persons, events=(), residences=()):
    return ProjectData(persons=list(persons), events=list(events), residences=list(residences))


def _plan(data, **choices):
    choices.setdefault("survivor_id", "p1")
    choices.setdefault("survivor_confirmed", True)
    return build_plan(data, None, MergeDecisions("p1", "p2", **choices))


def _keys(plan):
    return {u.key for u in plan.unresolved}


def _merged_person(plan):
    return plan.change_set.replaced["persons"]["p1"]


def test_steps_are_registered_through_merge_planner_import():
    from slaktbusken.services import merge_planner_person as mpp

    for slot, func in (
        ("attributes", mpp.plan_attributes), ("names", mpp.plan_names),
        ("events", mpp.plan_events), ("residences", mpp.plan_residences),
    ):
        assert func in mp.registered_steps(slot)


def test_sex_conflict_blocks_until_chosen():
    data = _data([_person("p1", "M"), _person("p2", "F")])
    plan = _plan(data)
    assert any(c.code == "sex_conflict" and c.is_blocking for c in plan.conflicts)
    assert "sex" in _keys(plan) and not plan.can_execute
    chosen = _plan(data, sex="F")
    assert not any(c.code == "sex_conflict" for c in chosen.conflicts)
    assert _merged_person(chosen).sex == "F"


def test_unknown_sex_is_replaced_without_conflict():
    plan = _plan(_data([_person("p1", "U"), _person("p2", "F")]))
    assert _merged_person(plan).sex == "F"
    assert not [c for c in plan.conflicts if c.code == "sex_conflict"]


def test_title_conflict_is_unresolved_until_chosen_and_empty_never_overwrites():
    data = _data([
        _person("p1", title="Dr", occupation="Lärare"),
        _person("p2", title="Fil.Dr", occupation=""),
    ])
    plan = _plan(data)
    assert "title" in _keys(plan) and "occupation" not in _keys(plan)
    assert _merged_person(plan).occupation == "Lärare"
    chosen = _plan(data, title_from="p2")
    assert "title" not in _keys(chosen)
    assert _merged_person(chosen).title == "Fil.Dr"


def test_profile_media_conflict_uses_decision_value():
    data = _data([_person("p1", profile_media_id="m1"), _person("p2", profile_media_id="m2")])
    assert "profile_media_id" in _keys(_plan(data))
    assert _merged_person(_plan(data, profile_media_id="m2")).profile_media_id == "m2"


def test_notes_default_concatenate_and_modes():
    data = _data([_person("p1", notes="A"), _person("p2", notes="B")])
    notes = _merged_person(_plan(data)).notes
    assert notes.startswith("A\n\n--- Anteckningar från Anna Berg (p2) ---\n\nB")
    assert _merged_person(_plan(data, notes_mode="keep_other")).notes == "B"
    assert _merged_person(_plan(data, notes_mode="keep_survivor")).notes == "A"


def test_names_union_requires_primary_choice_and_orders_it_first():
    p1 = _person("p1", given="Anna", surname="Berg")
    p2 = _person("p2", given="Anna", surname="Berg")
    p2.names.append(Name("married", "Anna", "Lind", "ev1"))
    data = _data([p1, p2])
    plan = _plan(data)
    assert "primary_name" in _keys(plan)
    assert [n.surname for n in _merged_person(plan).names] == ["Berg", "Lind"]
    chosen = _plan(data, primary_name=("Anna", "Lind", "married", "ev1"))
    assert "primary_name" not in _keys(chosen)
    assert _merged_person(chosen).names[0].surname == "Lind"
    # the identical name is one documented deduplication
    assert chosen.ledger_before["names"] - chosen.ledger_after_expected["names"] == 1


def test_same_strings_other_type_both_kept():
    p1 = _person("p1")
    p2 = _person("p2")
    p2.names[0] = Name("alias", "Anna", "Berg")
    plan = _plan(_data([p1, p2]))
    assert len(_merged_person(plan).names) == 2


def test_event_participants_rewritten_and_both_persons_deduplicated():
    ev = _event("e1", "marriage", ["p1", "p2", "x"], roles=["spouse", "spouse", "witness"])
    ev2 = _event("e2", "death", ["p2"])
    plan = _plan(_data([_person("p1"), _person("p2")], [ev, ev2]))
    edited = plan.change_set.replaced["events"]
    assert [p.person_id for p in edited["e1"].participants] == ["p1", "x"]
    assert [p.person_id for p in edited["e2"].participants] == ["p1"]
    assert any(c.code == "both_participants" and not c.is_blocking for c in plan.conflicts)
    disp = {i.item_id: i.disposition for i in plan.items if i.category == "events"}
    assert disp == {"e1": Disposition.COMBINED, "e2": Disposition.REASSIGNED}
    assert plan.ledger_before["participants"] - plan.ledger_after_expected["participants"] == 1
    assert plan.ledger_before["events"] == plan.ledger_after_expected["events"]


def test_role_conflict_blocks_until_role_chosen():
    ev = _event("e1", "baptism", ["p1", "p2"], roles=["godparent", "witness"])
    data = _data([_person("p1"), _person("p2")], [ev])
    plan = _plan(data)
    assert any(c.code == "participant_role" and c.is_blocking for c in plan.conflicts)
    assert "participant_role:e1" in _keys(plan)
    chosen = _plan(data, participant_roles={"e1": "witness"})
    assert not [c for c in chosen.conflicts if c.code == "participant_role"]
    assert chosen.change_set.replaced["events"]["e1"].participants[0].role == "witness"


def test_similar_event_warning_across_records_only_and_events_kept():
    births = [
        _event("b1", "birth", ["p1"], "1850-03-12", "pl1"),
        _event("b2", "birth", ["p2"], "1850-03-12"),
        _event("b3", "birth", ["p1"], "1850-03-12", "pl1"),  # same record as b1
    ]
    plan = _plan(_data([_person("p1"), _person("p2")], births))
    similar = [c for c in plan.conflicts if c.code == "similar_event"]
    assert sorted(c.subjects for c in similar) == [("b1", "b2"), ("b3", "b2")]
    assert all(not c.is_blocking and c.section == "events" for c in similar)
    assert similar[0].message.startswith("Händelserna kan vara dubbletter: Födelse 1850-03-12 och")
    assert not plan.unresolved or "participant_role" not in " ".join(_keys(plan))
    removed = plan.change_set.removed.get("events", set())
    assert not removed and not plan.change_set.added.get("events")
    assert plan.ledger_before["events"] == plan.ledger_after_expected["events"]


def test_no_warning_within_one_record():
    births = [
        _event("b1", "birth", ["p1"], "1850-03-12"),
        _event("b3", "birth", ["p1"], "1850-03-12"),
    ]
    plan = _plan(_data([_person("p1"), _person("p2")], births))
    assert not [c for c in plan.conflicts if c.code == "similar_event"]


def test_residences_reassigned_never_collapsed():
    r1 = ResidenceFact(id="r1", person_id="p1", place_id="pl1")
    r2 = ResidenceFact(id="r2", person_id="p2", place_id="pl1")
    plan = _plan(_data([_person("p1"), _person("p2")], residences=[r1, r2]))
    assert plan.change_set.replaced["residences"]["r2"].person_id == "p1"
    assert "r1" not in plan.change_set.replaced.get("residences", {})
    assert not plan.change_set.removed.get("residences")
    disp = {i.item_id: i.disposition for i in plan.items if i.category == "residences"}
    assert disp == {"r1": Disposition.PRESERVED, "r2": Disposition.REASSIGNED}
    assert plan.ledger_before["residences"] == plan.ledger_after_expected["residences"]


def test_one_disposition_per_item_and_clean_plan_can_execute():
    data = _data(
        [_person("p1"), _person("p2", given="Lisa")],
        [_event("e1", "death", ["p2"])],
        [ResidenceFact(id="r1", person_id="p2", place_id="pl1")],
    )
    plan = _plan(data, primary_name=("Anna", "Berg", "birth", None))
    keys = [(i.category, i.item_id) for i in plan.items]
    assert len(keys) == len(set(keys))
    assert plan.can_execute


def test_planning_does_not_mutate_project():
    data = _data(
        [_person("p1", "M", notes="A", title="x"), _person("p2", "F", notes="B", title="y")],
        [
            _event("e1", "marriage", ["p1", "p2"], roles=["a", "b"]),
            _event("b1", "birth", ["p1"], "1850-03-12"),
            _event("b2", "birth", ["p2"], "1850-03-12"),
        ],
        [ResidenceFact(id="r1", person_id="p2", place_id="pl1")],
    )
    before = copy.deepcopy(data)
    _plan(data)
    assert data == before
