"""Merge_Summary recorded by the planner (task 20.2, Requirement 36.1, design 15.12)."""

from __future__ import annotations

import copy

from slaktbusken.model.event import DateValue, Event, Participant, SourceRef
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.merge_candidate import MergeCandidate
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Observation, ResidenceFact
from slaktbusken.services import merge_planner as mp
from slaktbusken.services.merge_planner import MergeDecisions, build_plan


def _person(pid, given="Åke", surname="Öberg", **kw):
    return Person(id=pid, sex="M", names=[Name("birth", given, surname)], **kw)


def _cand(cid, a, b, assessment):
    return MergeCandidate(
        id=cid, person_1_id=a, person_2_id=b, assessment=assessment, enabled=True,
        research_case_id=None, comments=[],
    )


def _data():
    p2 = _person("p2", notes="B", title="Fil.Dr")
    p2.names.append(Name("married", "Åke", "Lind"))
    refs = [SourceRef("s1", "primary"), SourceRef("s2", "primary")]
    return ProjectData(
        persons=[_person("p1", notes="A", title="Dr"), p2, _person("p3")],
        events=[
            Event(id="e1", type="birth", participants=[Participant("p2", "self")],
                  date=DateValue("1900", "year", refs)),
            Event(id="e2", type="death", participants=[Participant("p1", "self")]),
        ],
        residences=[
            ResidenceFact(id="r1", person_id="p2", place_id="pl1",
                          observations=[Observation(SourceRef("s3", "primary"))]),
        ],
        media=[
            MediaItem(id="m1", type="image", file="a.jpg", title="Bild",
                      linked_entities=[LinkedEntity("person", "p2")]),
        ],
        merge_candidates=[
            _cand("merge_candidate_1", "p1", "p2", "confirmed"),
            _cand("merge_candidate_2", "p2", "p3", "possible"),
        ],
    )


def _plan(data, **choices):
    choices.setdefault("survivor_id", "p1")
    choices.setdefault("survivor_confirmed", True)
    return build_plan(data, None, MergeDecisions("p1", "p2", **choices))


def _lines(plan):
    (entry,) = plan.change_set.added["merge_history"]
    return entry.summary_lines


def test_summary_counts_match_the_plan():
    plan = _plan(_data(), title_from="p2")
    assert _lines(plan) == [
        "Namn tillagda: 1",
        "Händelser flyttade: 1",
        "Boenden flyttade: 1",
        "Källhänvisningar flyttade: 3",
        "Mediaobjekt med flyttade personlänkar: 1",
        "Familjer berörda: 0",
        "Forskningslänkar flyttade: 0",
        "Beslut för motstridiga fält: 1",
        "Anteckningar sammanslagna: ja",
        "Kandidater omdirigerade: 1",
        "Kandidater arkiverade: 1",
    ]


def test_summary_is_deterministic_and_planning_stays_read_only():
    data = _data()
    before = copy.deepcopy(data)
    first = _plan(data, title_from="p2")
    second = _plan(data, title_from="p2")
    assert _lines(first) == _lines(second)
    assert first.fingerprint == second.fingerprint
    assert data == before
    assert data.merge_history == []


def test_fingerprint_does_not_depend_on_the_summary():
    data = _data()
    plan = _plan(data)
    (entry,) = plan.change_set.added["merge_history"]
    assert entry.summary_lines
    # The fingerprint reads project data only, never the entry the plan creates.
    index = mp.pri.PersonReferenceIndex.build(data, ("p1", "p2"), None)
    assert plan.fingerprint == mp.compute_fingerprint(data, ("p1", "p2"), index, None)


def test_decisions_and_notes_flags_change_the_summary():
    plain = _lines(_plan(_data(), title_from="p2", notes_mode="keep_other"))
    assert "Anteckningar sammanslagna: nej" in plain
    assert "Beslut för motstridiga fält: 2" in plain


def test_nameless_retired_person_keeps_empty_name():
    data = _data()
    data.persons[1].names = []
    plan = _plan(data, title_from="p2")
    (entry,) = plan.change_set.added["merge_history"]
    assert entry.merged_person_name == ""
