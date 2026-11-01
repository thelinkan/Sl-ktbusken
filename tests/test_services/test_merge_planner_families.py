"""Family planning details (task 11.4): handlers, sync reconciliation, same-name note."""

from __future__ import annotations

from slaktbusken.model.event import Event, Participant
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services import merge_planner as mp
from slaktbusken.services import person_reference_index as pri
from slaktbusken.services.merge_planner import MergeDecisions, build_plan
from slaktbusken.services.merge_planner_families import (
    SAME_NAME_NOTE,
    find_cycle_through,
    same_name_relatives_note,
)


def _person(pid, given="Anna", surname="Berg"):
    return Person(id=pid, sex="M", names=[Name("birth", given, surname)])


def test_only_candidate_and_translation_handlers_are_missing():
    assert {loc.key for loc in pri.missing_handlers()} == {
        "merge_candidate.persons", "translation.person_mappings",
        "translation.identity_aliases",
    }


def test_sync_that_drops_a_retained_link_is_blocking():
    event = Event(
        id="E1", type="foster_home",
        participants=[Participant("c", "fosterbarn"), Participant("p2", "fosterförälder")],
    )
    fam = Family(
        "F1", [FamilyPartner("p2", "father"), FamilyPartner("z", "father")], ["c"],
        [ParentChildLink("c", "p2", "foster"), ParentChildLink("c", "z", "foster")], ["E1"],
    )
    data = ProjectData(
        persons=[_person("p1"), _person("p2"), _person("c"), _person("z")],
        events=[event], families=[fam],
    )
    plan = build_plan(
        data, None, MergeDecisions("p1", "p2", survivor_id="p1", survivor_confirmed=True)
    )
    dropped = [c for c in plan.blocking if c.code == "sync_drops_link"]
    assert len(dropped) == 1 and "z" in dropped[0].message


def test_same_name_note_only_for_different_ids_with_equal_names():
    assert same_name_relatives_note([_person("a", "Kalle"), _person("b", "KALLE")]) == SAME_NAME_NOTE
    assert same_name_relatives_note([_person("a", "Kalle"), _person("b", "Olle")]) is None
    assert same_name_relatives_note([_person("a", "Kalle"), _person("a", "Kalle")]) is None


def test_find_cycle_through_returns_path_or_none():
    assert find_cycle_through({"a": {"b"}, "b": {"c"}}, "a") is None
    path = find_cycle_through({"a": {"b"}, "b": {"c"}, "c": {"a"}}, "a")
    assert path[0] == path[-1] == "a" and set(path) == {"a", "b", "c"}
