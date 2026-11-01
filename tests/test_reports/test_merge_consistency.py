"""Tests for the merge consistency report ("Sammanslagning och dubletter")."""

from __future__ import annotations

import copy

import pytest
from hypothesis import given, settings, strategies as st

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.merge_candidate import (
    MergeCandidate,
    MergeCandidateComment,
    MergeHistoryEntry,
)
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.reports.content import EmptyStateBlock, ListBlock
from slaktbusken.reports.generator import ReportGeneratorService
from slaktbusken.reports.merge_consistency import (
    check_merge_consistency,
    generate_merge_consistency_report,
)


def _person(pid: str, given: str = "Anna", surname: str = "Svensson") -> Person:
    return Person(id=pid, sex="F", names=[Name(type="birth", given=given, surname=surname)])


def _data(**kw) -> ProjectData:
    data = ProjectData()
    data.persons = [_person("p_1"), _person("p_2", "Bo", "Berg")]
    for key, value in kw.items():
        setattr(data, key, value)
    return data


def _types(data: ProjectData) -> list[str]:
    return [i.check_type for i in check_merge_consistency(data)]


def _texts(report) -> list[str]:
    out: list[str] = []
    for b in report.blocks:
        if isinstance(b, ListBlock):
            out.extend(b.items)
        elif isinstance(b, EmptyStateBlock):
            out.append(b.text)
    return out


def test_empty_project_shows_only_empty_text():
    report = generate_merge_consistency_report(_data())
    assert report.title == "Sammanslagning och dubletter"
    assert _texts(report) == [
        "Det finns inga sammanslagningskandidater eller sammanslagningar att kontrollera."
    ]


def test_clean_candidate_has_empty_error_sections():
    data = _data(merge_candidates=[MergeCandidate("mergecand_1", "p_1", "p_2")])
    report = generate_merge_consistency_report(data)
    assert "Inga problem hittades." in _texts(report)
    assert not [i for i in check_merge_consistency(data) if i.severity == "error"]


def test_missing_person_uses_placeholder_and_id():
    data = _data(merge_candidates=[MergeCandidate("mergecand_1", "p_1", "p_gone")])
    issues = check_merge_consistency(data)
    msg = next(i.message for i in issues if i.check_type == "missing_person")
    assert "Okänd person (p_gone)" in msg
    assert "Anna Svensson (p_1)" in msg


def test_error_findings_detected():
    cands = [
        MergeCandidate("mergecand_1", "p_1", "p_1"),
        MergeCandidate("mergecand_2", "p_1", "p_2", assessment="bogus", research_case_id="rc_x",
                       comments=[MergeCandidateComment("", "2020-13-45", "x")]),
        MergeCandidate("mergecand_3", "p_2", "p_1"),
    ]
    types = _types(_data(merge_candidates=cands))
    for expected in ("same_person", "invalid_assessment", "missing_case",
                     "invalid_comment", "duplicate_pair"):
        assert expected in types


def test_history_cycle_and_retired_reference():
    hist = [
        MergeHistoryEntry("merge_1", "p_1", "p_9", "X", "", "2020-01-01"),
        MergeHistoryEntry("merge_2", "p_9", "p_1", "Y", "", "2020-01-02"),
    ]
    fam = Family("f_1", [FamilyPartner("p_9", "partner")], [])
    data = _data(merge_history=hist, families=[fam])
    data.persons = [_person("p_2")]
    types = _types(data)
    assert "redirect_cycle" in types
    assert "retired_reference" in types


def test_survivor_missing_and_parent_child_cycle():
    hist = [MergeHistoryEntry("merge_1", "p_gone", "p_9", "X", "", "2020-01-01")]
    fams = [
        Family("f_1", [FamilyPartner("p_1", "partner")], ["p_2"],
               [ParentChildLink("p_2", "p_1", "biological")]),
        Family("f_2", [FamilyPartner("p_2", "partner")], ["p_1"],
               [ParentChildLink("p_1", "p_2", "biological")]),
    ]
    types = _types(_data(merge_history=hist, families=fams))
    assert "history_survivor" in types
    assert types.count("invalid_relationship") == 1


def test_info_findings():
    cands = [
        MergeCandidate("mergecand_1", "p_1", "p_2", assessment="confirmed", enabled=False),
        MergeCandidate("mergecand_2", "p_2", "p_3", assessment="rejected"),
    ]
    data = _data(
        merge_candidates=cands,
        merge_history=[MergeHistoryEntry("merge_1", "p_1", "p_9", "X", "", "2020-01-01")],
    )
    types = _types(data)
    for expected in ("confirmed_not_merged", "disabled_candidate",
                     "rejected_candidate", "completed_merge"):
        assert expected in types


def test_report_is_read_only():
    data = _data(
        merge_candidates=[MergeCandidate("mergecand_1", "p_1", "p_gone", assessment="x")],
        merge_history=[MergeHistoryEntry("merge_1", "p_1", "p_2", "X", "", "bad")],
    )
    before = copy.deepcopy(data)
    generate_merge_consistency_report(data)
    assert data == before


def test_service_delegates_and_errors_propagate():
    data = _data(merge_candidates=[MergeCandidate("mergecand_1", "p_1", "p_2")])
    assert ReportGeneratorService().generate_merge_consistency(data).title == (
        "Sammanslagning och dubletter"
    )
    data.merge_candidates = [None]  # type: ignore[list-item]
    with pytest.raises(Exception):
        ReportGeneratorService().generate_merge_consistency(data)


@settings(max_examples=50, deadline=None)
@given(
    st.lists(
        st.tuples(st.sampled_from(["p_1", "p_2", "p_x", ""]), st.sampled_from(["p_1", "p_2", "p_x"]),
                  st.sampled_from(["unreviewed", "confirmed", "rejected", "zzz"]), st.booleans()),
        max_size=8,
    )
)
def test_property_never_crashes_and_one_info_per_item(rows):
    cands = [MergeCandidate(f"mergecand_{i}", a, b, s, e) for i, (a, b, s, e) in enumerate(rows)]
    data = _data(merge_candidates=cands)
    issues = check_merge_consistency(data)
    assert sum(i.check_type == "disabled_candidate" for i in issues) == sum(not c.enabled for c in cands)
    assert sum(i.check_type == "rejected_candidate" for i in issues) == sum(
        c.assessment == "rejected" for c in cands
    )
    generate_merge_consistency_report(data)

