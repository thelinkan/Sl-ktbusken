"""Example tests for the Qt-free merge history view model (Requirement 36)."""

from __future__ import annotations

from slaktbusken.model.merge_candidate import (
    ArchivedCandidate,
    MergeCandidateComment,
    MergeHistoryEntry,
)
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.merge_history_view import (
    NO_SUMMARY_TEXT,
    UNRESOLVED_SURVIVOR_TEXT,
    build_history_rows,
)
from slaktbusken.services.redirect_resolution import RedirectResolver


def _person(pid: str, given: str) -> Person:
    return Person(id=pid, sex="unknown", names=[Name("birth", given, "Åkesson")])


def _entry(n: int, merged: str, survivor: str, date: str, **kw) -> MergeHistoryEntry:
    return MergeHistoryEntry(
        id=f"merge_{n}",
        surviving_person_id=survivor,
        merged_person_id=merged,
        merged_person_name=f"Namn {merged}",
        merged_person_lifespan="1900–1970",
        merge_date=date,
        **kw,
    )


def _data(history, persons=("p1", "p2")) -> ProjectData:
    return ProjectData(
        persons=[_person(p, p.upper()) for p in persons], merge_history=history
    )


def test_empty_history_gives_no_rows() -> None:
    assert build_history_rows(_data([])) == []


def test_newest_first_by_date_then_sequence() -> None:
    history = [
        _entry(2, "r2", "p1", "2024-01-01"),
        _entry(10, "r10", "p1", "2024-01-01"),
        _entry(3, "r3", "p1", "2025-01-01"),
        _entry(1, "r1", "p1", "2023-01-01"),
    ]
    rows = build_history_rows(_data(history))
    assert [r.entry_id for r in rows] == ["merge_3", "merge_10", "merge_2", "merge_1"]


def test_rows_copy_stored_fields_and_summary() -> None:
    entry = _entry(1, "r1", "p1", "2024-05-06", summary_lines=["2 namn flyttades."])
    (row,) = build_history_rows(_data([entry]))
    assert (row.merged_name, row.merged_lifespan, row.merged_id, row.merge_date) == (
        "Namn r1", "1900–1970", "r1", "2024-05-06",
    )
    assert row.survivor_id == "p1" and row.survivor_name == "P1 Åkesson"
    assert row.can_navigate
    assert row.summary_text_lines == ("2 namn flyttades.",)


def test_missing_summary_uses_shared_text() -> None:
    (row,) = build_history_rows(_data([_entry(1, "r1", "p1", "2024-01-01")]))
    assert row.summary_text_lines == (NO_SUMMARY_TEXT,)


def test_person_scope_equals_merged_into_reversed() -> None:
    history = [
        _entry(1, "r1", "p1", "2023-01-01"),
        _entry(2, "r2", "p2", "2023-06-01"),
        _entry(3, "p2", "p1", "2024-01-01"),
    ]
    data = _data(history)
    rows = build_history_rows(data, "p1")
    expected = list(reversed(RedirectResolver(history).merged_into("p1")))
    assert [r.entry_id for r in rows] == [e.id for e in expected]
    assert {r.entry_id for r in build_history_rows(data, "p2")} == set()
    assert len(build_history_rows(data)) == 3


def test_unresolved_survivor_cycle_disables_navigation() -> None:
    history = [
        _entry(1, "a", "b", "2024-01-01"),
        _entry(2, "b", "a", "2024-02-01"),
    ]
    rows = build_history_rows(_data(history, persons=()))
    assert len(rows) == 2
    for row in rows:
        assert row.survivor_id is None and not row.can_navigate
        assert row.survivor_state == "cycle"
        assert row.survivor_text == UNRESOLVED_SURVIVOR_TEXT


def test_ambiguous_retired_id_is_marked() -> None:
    history = [
        _entry(1, "r", "p1", "2024-01-01"),
        _entry(2, "r", "p2", "2024-02-01"),
    ]
    rows = build_history_rows(_data(history))
    assert [r.survivor_state for r in rows] == ["ambiguous", "ambiguous"]
    assert not any(r.can_navigate for r in rows)


def test_missing_survivor_person_is_unresolved() -> None:
    (row,) = build_history_rows(_data([_entry(1, "r1", "gone", "2024-01-01")]))
    assert row.survivor_id is None and row.survivor_state == "missing"


def test_archived_candidate_details() -> None:
    archived = ArchivedCandidate(
        id="cand_1",
        person_1_id="r1",
        person_2_id="p2",
        assessment="possible",
        enabled=True,
        comments=[MergeCandidateComment(id="c1", text="x", date="2024-01-01")],
    )
    entry = _entry(1, "r1", "p1", "2024-01-01", archived_candidates=[archived])
    (row,) = build_history_rows(_data([entry]))
    (a,) = row.archived
    assert (a.other_person_id, a.other_person_name) == ("p2", "P2 Åkesson")
    assert (a.assessment, a.comment_count) == ("possible", 1)
