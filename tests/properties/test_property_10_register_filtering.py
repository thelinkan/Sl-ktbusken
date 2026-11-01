"""Property 10: Register filtering, search and sorting.

**Validates: Requirements 3.8, 5.2, 5.3, 5.4, 15.2, 15.3, 15.4, 15.5, 15.9**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.merge_candidate import (
    CANDIDATE_ASSESSMENTS,
    MergeCandidate,
    MergeCandidateComment,
)
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.research_case import ResearchCase
from slaktbusken.services.candidate_register import (
    DEFAULT_ASSESSMENTS,
    RegisterFilters,
    _sort_key,
    build_rows,
    latest_comment_text,
    query_register,
    sort_rows,
)

_TEXT = st.text(alphabet="abcABCåäö ", max_size=5)
_DATES = st.one_of(
    st.sampled_from(["", "2020", "2021-05", "2019-12-31", "bad", "2020-13-01"]),
)


@st.composite
def _projects(draw):
    n_persons = draw(st.integers(2, 5))
    persons = [
        Person(
            id=f"P{i}",
            sex="U",
            names=[Name(type="birth", given=draw(_TEXT), surname=draw(_TEXT))],
        )
        for i in range(n_persons)
    ]
    cases = [
        ResearchCase(id=f"R{i}", title=draw(_TEXT))
        for i in range(draw(st.integers(0, 2)))
    ]
    cands = []
    for i in range(draw(st.integers(0, 8))):
        comments = [
            MergeCandidateComment(id=f"K{i}_{j}", date=draw(_DATES), text=draw(_TEXT))
            for j in range(draw(st.integers(0, 3)))
        ]
        cands.append(
            MergeCandidate(
                id=f"M{i}",
                person_1_id=f"P{draw(st.integers(0, n_persons - 1))}",
                person_2_id=f"P{draw(st.integers(0, n_persons - 1))}",
                assessment=draw(st.sampled_from(CANDIDATE_ASSESSMENTS)),
                enabled=draw(st.booleans()),
                research_case_id=draw(
                    st.one_of(st.none(), st.sampled_from([c.id for c in cases]))
                )
                if cases
                else None,
                comments=comments,
            )
        )
    return ProjectData(
        project=ProjectMetadata(title="T"),
        persons=persons,
        research_cases=cases,
        merge_candidates=cands,
    )


def _ids(rows) -> list[str]:
    return [r.candidate.id for r in rows]


def _matches(row, needle: str) -> bool:
    c = row.candidate
    fields = [row.person_1_name, row.person_2_name, c.person_1_id, c.person_2_id]
    fields += [row.case_title] + [cm.text for cm in c.comments]
    return any(needle in f.lower() for f in fields)


def _person_matches(row, needle: str) -> bool:
    c = row.candidate
    fields = [row.person_1_name, row.person_2_name, c.person_1_id, c.person_2_id]
    return any(needle in f.lower() for f in fields)


@settings(settings.get_profile("sbk"))
@given(_projects())
def test_default_view_is_enabled_active_assessments(data: ProjectData) -> None:
    got = _ids(query_register(data))
    expected = [
        c.id
        for c in data.merge_candidates
        if c.enabled and c.assessment in DEFAULT_ASSESSMENTS
    ]
    assert got == expected


@settings(settings.get_profile("sbk"))
@given(
    _projects(),
    st.sets(st.sampled_from(CANDIDATE_ASSESSMENTS), min_size=1),
    st.sampled_from([None, True, False]),
)
def test_filters_select_rejected_and_disabled(data, assessments, enabled) -> None:
    f = RegisterFilters(assessments=frozenset(assessments), enabled=enabled)
    got = _ids(query_register(data, f))
    expected = [
        c.id
        for c in data.merge_candidates
        if c.assessment in assessments
        and (c.enabled if enabled is None else c.enabled == enabled)
    ]
    assert got == expected


@settings(settings.get_profile("sbk"))
@given(_projects(), _TEXT.filter(lambda s: s.strip() != ""))
def test_search_matches_name_id_comment_case(data, text) -> None:
    needle = text.strip().lower()
    rows = build_rows(data)
    got = _ids(query_register(data, search=text))
    expected = []
    for r in rows:
        c = r.candidate
        if not _matches(r, needle) or c.assessment not in DEFAULT_ASSESSMENTS:
            continue
        # Disabled candidates appear only through a person match.
        if not c.enabled and not _person_matches(r, needle):
            continue
        expected.append(c.id)
    assert got == expected


@settings(settings.get_profile("sbk"))
@given(_projects(), st.integers(0, 5))
def test_sorting_twice_reverses(data, column) -> None:
    rows = build_rows(data)
    asc = sort_rows(rows, column)
    desc = sort_rows(rows, column, descending=True)
    asc_keys = [_sort_key(r, column) for r in asc]
    desc_keys = [_sort_key(r, column) for r in desc]
    assert desc_keys == list(reversed(asc_keys))
    if len(set(asc_keys)) == len(asc_keys):
        assert _ids(desc) == list(reversed(_ids(asc)))


@settings(settings.get_profile("sbk"))
@given(_projects())
def test_latest_comment_cell(data: ProjectData) -> None:
    from slaktbusken.model.research_case import is_valid_calendar_date

    for c in data.merge_candidates:
        valid = [
            cm for cm in c.comments if cm.date and is_valid_calendar_date(cm.date)
        ]
        if valid:
            top = max(cm.date for cm in valid)
            assert latest_comment_text(c.comments) in {
                cm.text for cm in valid if cm.date == top
            }
        elif c.comments:
            assert latest_comment_text(c.comments) == c.comments[-1].text
        else:
            assert latest_comment_text(c.comments) == ""
