"""Content of history entries written by the real MergeEngine (task 20.13).

Requirements 28.1, 28.5, 28.6, 36.1, 36.2, 36.3 and design 15.12. A project is
saved with ``ProjectService``, merged with the real ``MergeEngine`` and the
persisted ``MergeHistoryEntry`` is checked after the merge and after
save/reopen.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.merge_candidate import (
    ArchivedCandidate,
    MergeCandidate,
    MergeCandidateComment,
    MergedIdentityMapping,
)
from slaktbusken.model.person import Name, Person
from slaktbusken.persistence import translation_io
from slaktbusken.persistence.file_io import FilePersistence
from slaktbusken.persistence.translation_io import PersonMapping
from slaktbusken.services.merge_engine import MergeEngine
from slaktbusken.services.merge_rules import name_identity
from slaktbusken.services.merge_planner import MergeDecisions, build_plan
from slaktbusken.services.project_service import ProjectService


def _person(pid: str, given: str | None = "Anna", surname: str = "Berg") -> Person:
    names = [Name("birth", given, surname)] if given is not None else []
    return Person(id=pid, sex="F", names=names)


def _event(eid: str, kind: str, pid: str, year: str) -> Event:
    return Event(
        id=eid, type=kind, participants=[Participant(pid, "self")],
        date=DateValue(year, "year", []),
    )


def _cand(cid, a, b, assessment, comments=()):
    return MergeCandidate(
        id=cid, person_1_id=a, person_2_id=b, assessment=assessment, enabled=True,
        research_case_id=None, comments=list(comments),
    )


def _save(svc: ProjectService) -> None:
    svc._dirty = True
    svc.save_project()


def _service(root: Path, persons, events=(), candidates=(), mappings=()) -> ProjectService:
    svc = ProjectService()
    svc.create_project("Test", root)
    svc.data.persons.extend(persons)
    svc.data.events.extend(events)
    svc.data.merge_candidates.extend(candidates)
    if mappings:
        translation_io.write_persons(
            list(mappings), [], svc.project_path.parent / "translation" / "persons.json"
        )
    _save(svc)
    return svc


def _merge(svc: ProjectService, survivor: str, retired: str):
    """Merge with the real engine; return the confirmed plan."""
    translation = translation_io.read_all(svc.project_path.parent / "translation")
    survivor_person = next(p for p in svc.data.persons if p.id == survivor)
    decisions = MergeDecisions(
        survivor, retired, survivor_id=survivor, survivor_confirmed=True,
        primary_name=name_identity(survivor_person.names[0]),
    )
    plan = build_plan(svc.data, translation, decisions, svc.content_revision)
    assert plan.can_execute, ([c.message for c in plan.blocking], plan.unresolved)
    outcome = MergeEngine(svc, None).execute(plan)
    assert outcome.success, outcome.message
    return plan


def _reopen(svc: ProjectService) -> ProjectService:
    reopened = ProjectService()
    reopened.open_project(svc.project_path)
    return reopened


def _today_range(action):
    before = date.today().isoformat()
    result = action()
    return result, {before, date.today().isoformat()}


@pytest.fixture
def full_merge(tmp_path: Path):
    """person_2 (Åsa Öberg 1829–1890) merged into person_1; candidates of every role."""
    comments = [
        MergeCandidateComment("mergecomment_1", "2024-01-05", "Samma födelseort"),
        MergeCandidateComment("mergecomment_2", "2024-02-06", "Åke menar att det stämmer"),
    ]
    svc = _service(
        tmp_path,
        [_person("person_1"), _person("person_2", "Åsa", "Öberg"), _person("person_3")],
        events=[_event("event_1", "birth", "person_2", "1829"),
                _event("event_2", "death", "person_2", "1890")],
        candidates=[
            _cand("mergecand_1", "person_1", "person_2", "confirmed", comments),
            _cand("mergecand_2", "person_2", "person_3", "possible"),
            _cand("mergecand_3", "person_1", "person_3", "unreviewed"),
        ],
        mappings=[PersonMapping("@I2@", "person_2", "fp2"), PersonMapping("@I9@", "person_2", None)],
    )
    original_direct = ArchivedCandidate(
        "mergecand_1", "person_1", "person_2", "confirmed", True, None,
        [MergeCandidateComment(c.id, c.date, c.text) for c in comments], "direct",
    )
    plan, dates = _today_range(lambda: _merge(svc, "person_1", "person_2"))
    return svc, plan, dates, original_direct


def _check_entry(svc, plan, dates, original_direct) -> None:
    assert len(svc.data.merge_history) == 1
    entry = svc.data.merge_history[0]
    assert entry.id == "merge_1"
    assert entry.surviving_person_id == "person_1"
    assert entry.merged_person_id == "person_2"
    assert entry.merged_person_name == "Åsa Öberg"
    assert entry.merged_person_lifespan == "1829\u20131890"
    assert entry.merge_date in dates
    assert entry.merge_candidate_id == "mergecand_1"

    archived = {a.id: a for a in entry.archived_candidates}
    assert set(archived) == {"mergecand_1", "mergecand_2"}
    assert archived["mergecand_1"] == original_direct  # full original with comments
    assert archived["mergecand_2"].role == "collision"
    assert archived["mergecand_2"].assessment == "possible"
    assert (archived["mergecand_2"].person_1_id, archived["mergecand_2"].person_2_id) == (
        "person_2", "person_3")

    assert entry.identity_mappings == [
        MergedIdentityMapping("@I2@", "fp2"), MergedIdentityMapping("@I9@", None)]

    assert len(entry.summary_lines) == 11
    assert all(isinstance(line, str) and line for line in entry.summary_lines)
    (planned,) = plan.change_set.added["merge_history"]
    assert entry.summary_lines == planned.summary_lines  # snapshot of the confirmed plan

    marks = svc.data.id_high_water_marks
    assert marks.get("person_", 0) >= 2
    assert marks.get("merge_", 0) >= 1


def test_entry_content_after_merge(full_merge) -> None:
    _check_entry(*full_merge)


def test_entry_content_after_save_and_reopen(full_merge) -> None:
    svc, plan, dates, original_direct = full_merge
    reopened = _reopen(svc)
    _check_entry(reopened, plan, dates, original_direct)
    assert reopened.data.merge_history == svc.data.merge_history
    assert FilePersistence.load(svc.project_path).merge_history == svc.data.merge_history
    assert reopened.data.id_high_water_marks.get("person_", 0) >= 2
    assert reopened.data.id_high_water_marks.get("merge_", 0) >= 1


def test_summary_lines_state_the_counts_of_the_plan(full_merge) -> None:
    svc, *_ = full_merge
    lines = svc.data.merge_history[0].summary_lines
    assert lines[0].startswith("Namn tillagda:")
    assert "Händelser flyttade: 2" in lines
    assert "Kandidater arkiverade: 2" in lines


@pytest.mark.parametrize(
    "birth, death, expected",
    [("1829", "1890", "1829\u20131890"), ("1829", None, "(1829)"),
     (None, "1890", "(\u20131890)"), (None, None, "")],
)
def test_lifespan_variants(tmp_path: Path, birth, death, expected) -> None:
    events = []
    if birth:
        events.append(_event("event_1", "birth", "person_2", birth))
    if death:
        events.append(_event("event_2", "death", "person_2", death))
    svc = _service(tmp_path, [_person("person_1"), _person("person_2")], events=events)
    _merge(svc, "person_1", "person_2")
    assert svc.data.merge_history[0].merged_person_lifespan == expected
    assert _reopen(svc).data.merge_history[0].merged_person_lifespan == expected


def test_nameless_retired_person_has_empty_name(tmp_path: Path) -> None:
    svc = _service(tmp_path, [_person("person_1"), _person("person_2", None)])
    _merge(svc, "person_1", "person_2")
    assert svc.data.merge_history[0].merged_person_name == ""
    reopened = _reopen(svc)
    assert reopened.data.merge_history[0].merged_person_name == ""
    assert reopened.data.merge_history == svc.data.merge_history


def test_entry_without_candidates_or_mappings(tmp_path: Path) -> None:
    svc = _service(tmp_path, [_person("person_1"), _person("person_2")])
    _merge(svc, "person_1", "person_2")
    entry = _reopen(svc).data.merge_history[0]
    assert entry.merge_candidate_id is None
    assert entry.archived_candidates == []
    assert entry.identity_mappings == []
    assert len(entry.summary_lines) == 11


def test_second_merge_keeps_first_entry_unchanged(tmp_path: Path) -> None:
    svc = _service(
        tmp_path,
        [_person("person_1"), _person("person_2", "Åsa", "Öberg"), _person("person_3", "Per", "Ek")],
        events=[_event("event_1", "birth", "person_2", "1829")],
        mappings=[PersonMapping("@I2@", "person_2", "fp2")],
    )
    _merge(svc, "person_1", "person_2")
    first = svc.data.merge_history[0]
    first_copy = type(first)(**{**first.__dict__})  # independent snapshot of the fields
    first_fields = repr(first)

    _merge(svc, "person_1", "person_3")

    for data in (svc.data, _reopen(svc).data):
        assert [e.id for e in data.merge_history] == ["merge_1", "merge_2"]
        assert repr(data.merge_history[0]) == first_fields
        assert data.merge_history[0] == first_copy
        second = data.merge_history[1]
        assert (second.merged_person_id, second.merged_person_name) == ("person_3", "Per Ek")
        assert second.merged_person_lifespan == ""
        assert second.surviving_person_id == "person_1"
        assert data.id_high_water_marks.get("person_", 0) >= 3
        assert data.id_high_water_marks.get("merge_", 0) >= 2
