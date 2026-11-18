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



# ---------------------------------------------------------------------------
# Property 44: Consistency report findings
# **Validates: Requirements 5.8, 6.7, 31.2, 31.3, 31.4, 31.5**
# ---------------------------------------------------------------------------

from collections import Counter  # noqa: E402

# Defect kind -> the single error check_type it must produce.
_DEFECTS: dict[str, str] = {
    "missing_person": "missing_person",
    "same_person": "same_person",
    "duplicate_pair": "duplicate_pair",
    "invalid_assessment": "invalid_assessment",
    "invalid_comment": "invalid_comment",
    "missing_case": "missing_case",
    "history_survivor": "history_survivor",
    "redirect_cycle": "redirect_cycle",
    "retired_reference": "retired_reference",
    "family_cycle": "invalid_relationship",
}

_INFO_KINDS = ("confirmed", "disabled", "rejected", "merged")


def _inject(data: ProjectData, kind: str, k: int) -> None:
    """Inject one defect (or information item) using ids unique to index ``k``."""
    a, b, gone = f"pa_{k}", f"pb_{k}", f"pgone_{k}"
    cid, hid = f"mergecand_{k}", f"merge_{k}"
    if kind not in ("redirect_cycle", "history_survivor"):
        data.persons.extend([_person(a), _person(b, "Bo", "Berg")])
    if kind == "missing_person":
        data.merge_candidates.append(MergeCandidate(cid, a, gone))
    elif kind == "same_person":
        data.merge_candidates.append(MergeCandidate(cid, a, a))
    elif kind == "duplicate_pair":
        data.merge_candidates.append(MergeCandidate(cid, a, b))
        data.merge_candidates.append(MergeCandidate(cid + "_dup", b, a))
    elif kind == "invalid_assessment":
        data.merge_candidates.append(MergeCandidate(cid, a, b, assessment="bogus"))
    elif kind == "invalid_comment":
        data.merge_candidates.append(MergeCandidate(
            cid, a, b, comments=[MergeCandidateComment(f"c_{k}", "2020-13-45", "x")]))
    elif kind == "missing_case":
        data.merge_candidates.append(MergeCandidate(cid, a, b, research_case_id=f"rc_{k}"))
    elif kind == "history_survivor":
        data.merge_history.append(
            MergeHistoryEntry(hid, gone, f"pretired_{k}", "X", "", "2020-01-01"))
    elif kind == "redirect_cycle":
        data.merge_history.append(MergeHistoryEntry(hid, f"px_{k}", f"py_{k}", "X", "", "2020-01-01"))
        data.merge_history.append(MergeHistoryEntry(hid + "b", f"py_{k}", f"px_{k}", "Y", "", "2020-01-02"))
    elif kind == "retired_reference":
        retired = f"pretired_{k}"
        data.merge_history.append(MergeHistoryEntry(hid, a, retired, "X", "", "2020-01-01"))
        data.families.append(Family(f"f_{k}", [FamilyPartner(retired, "partner")], []))
    elif kind == "family_cycle":
        data.families.append(Family(
            f"f_{k}a", [FamilyPartner(a, "partner")], [b],
            [ParentChildLink(b, a, "biological")]))
        data.families.append(Family(
            f"f_{k}b", [FamilyPartner(b, "partner")], [a],
            [ParentChildLink(a, b, "biological")]))
    elif kind == "confirmed":
        data.merge_candidates.append(MergeCandidate(cid, a, b, assessment="confirmed"))
    elif kind == "disabled":
        data.merge_candidates.append(MergeCandidate(cid, a, b, enabled=False))
    elif kind == "rejected":
        data.merge_candidates.append(MergeCandidate(cid, a, b, assessment="rejected"))
    elif kind == "merged":
        data.merge_history.append(MergeHistoryEntry(hid, a, f"pretired_{k}", "X", "", "2020-01-01"))
    else:  # pragma: no cover
        raise AssertionError(kind)


def _build(kinds: list[str]) -> ProjectData:
    data = ProjectData()
    for k, kind in enumerate(kinds):
        _inject(data, kind, k)
    return data


@settings(max_examples=100, deadline=None)
@given(st.lists(st.sampled_from(list(_DEFECTS) + list(_INFO_KINDS)), max_size=10))
def test_property_44_consistency_report_findings(kinds):
    """**Validates: Requirements 5.8, 6.7, 31.2, 31.3, 31.4, 31.5**"""
    data = _build(kinds)
    before = copy.deepcopy(data)
    issues = check_merge_consistency(data)

    errors = Counter(i.check_type for i in issues if i.severity == "error")
    expected_errors = Counter(_DEFECTS[kd] for kd in kinds if kd in _DEFECTS)
    assert errors == expected_errors

    infos = Counter(i.check_type for i in issues if i.severity == "info")
    expected_infos = Counter({
        "confirmed_not_merged": kinds.count("confirmed"),
        "disabled_candidate": kinds.count("disabled"),
        "rejected_candidate": kinds.count("rejected"),
        "completed_merge": len(data.merge_history),
    })
    assert infos == +expected_infos

    # Messages carry the display name and id, or a Swedish placeholder for missing persons.
    for i in issues:
        if i.check_type == "missing_person":
            assert "Okänd person (pgone_" in i.message
        if i.check_type in ("same_person", "invalid_assessment", "duplicate_pair"):
            assert "Anna Svensson (pa_" in i.message

    # Clean data yields no errors; the report is read-only.
    if not any(kd in _DEFECTS for kd in kinds):
        assert not [i for i in issues if i.severity == "error"]
    generate_merge_consistency_report(data)
    assert data == before
