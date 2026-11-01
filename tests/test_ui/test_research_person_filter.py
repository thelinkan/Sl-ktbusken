"""Property 50: Research overview person filter (task 9.14).

Pure tests, no Qt.

**Validates: Requirements 17.6, 17.8, 17.15, 17.16, 18.14**
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import (
    ResearchAction,
    ResearchCase,
    ResearchEntityLink,
    ResearchHypothesis,
)
from slaktbusken.services.research_index import ResearchIndex
from slaktbusken.ui.research_overview import (
    CaseFilter,
    build_overview_case_rows,
    build_overview_hypothesis_rows,
    build_person_scope,
    build_todo_rows,
)

PERSON_IDS = ["person_1", "person_2", "person_3"]
# "person_ghost" does not exist in the project; a link to it involves nobody.
LINK_TARGETS = PERSON_IDS + ["person_ghost"]
CASE_IDS = [f"case_{i}" for i in range(5)]


def _link(kind: str, entity_id: str) -> ResearchEntityLink:
    return ResearchEntityLink(kind, entity_id)


links = st.lists(
    st.builds(
        _link,
        st.sampled_from(["person", "person", "family"]),
        st.sampled_from(LINK_TARGETS),
    ),
    max_size=3,
)


@st.composite
def projects(draw) -> ProjectData:
    data = ProjectData()
    data.persons = [
        Person(id=pid, sex="M", names=[Name(type="birth", given=pid, surname="T")])
        for pid in PERSON_IDS
    ]
    for case_id in CASE_IDS[: draw(st.integers(0, len(CASE_IDS)))]:
        primary = draw(st.one_of(st.none(), st.builds(_link, st.just("person"), st.sampled_from(LINK_TARGETS))))
        data.research_cases.append(
            ResearchCase(
                id=case_id,
                title=case_id,
                status=draw(st.sampled_from(["open", "in_progress", "on_hold", "closed"])),
                primary_entity_ref=primary,
                linked_entities=draw(links),
            )
        )
    case_pool = CASE_IDS + ["case_missing"]
    for i in range(draw(st.integers(0, 8))):
        data.research_actions.append(
            ResearchAction(
                id=f"action_{i}",
                research_case_id=draw(st.sampled_from(case_pool)),
                completed_date=draw(st.sampled_from([None, "2026-01-01"])),
                sort_order=draw(st.integers(0, 3)),
            )
        )
    for i in range(draw(st.integers(0, 8))):
        data.research_hypotheses.append(
            ResearchHypothesis(
                id=f"hyp_{i}",
                research_case_id=draw(st.sampled_from(case_pool)),
                linked_entities=draw(links),
            )
        )
    return data


def _involved_case_ids(data: ProjectData, pid: str) -> set[str]:
    """Independent definition: the case links the person (primary or linked)."""
    result = set()
    for case in data.research_cases:
        refs = list(case.linked_entities)
        if case.primary_entity_ref is not None:
            refs.append(case.primary_entity_ref)
        if any(r.entity_type == "person" and r.entity_id == pid for r in refs):
            result.add(case.id)
    return result


@given(projects(), st.sampled_from(PERSON_IDS))
def test_person_scope_rows_match_brute_force(data: ProjectData, pid: str) -> None:
    scope = build_person_scope(ResearchIndex(data), pid)
    case_ids = _involved_case_ids(data, pid)
    existing_cases = {c.id for c in data.research_cases}

    # Cases: closed ones included, project order.
    case_rows = build_overview_case_rows(data, person_scope=scope)
    assert [r.case_id for r in case_rows] == [
        c.id for c in data.research_cases if c.id in case_ids
    ]

    # To-do: pending actions of those cases, closed cases included.
    expected_todo = {
        a.id
        for a in data.research_actions
        if a.completed_date is None and a.research_case_id in case_ids
    }
    todo_rows = build_todo_rows(data, person_scope=scope)
    assert {r.action_id for r in todo_rows} == expected_todo
    assert len(todo_rows) == len(expected_todo)

    # Hypotheses: of those cases, or naming the person; owner case must exist.
    expected_hyp = {
        h.id
        for h in data.research_hypotheses
        if h.research_case_id in existing_cases
        and (
            h.research_case_id in case_ids
            or any(l.entity_type == "person" and l.entity_id == pid for l in h.linked_entities)
        )
    }
    hyp_rows = build_overview_hypothesis_rows(data, person_scope=scope)
    assert {r.hypothesis_id for r in hyp_rows} == expected_hyp
    assert len(hyp_rows) == len(expected_hyp)


@given(projects(), st.sampled_from(PERSON_IDS))
def test_case_rows_equal_index_and_indicator_total(data: ProjectData, pid: str) -> None:
    index = ResearchIndex(data)
    scope = build_person_scope(index, pid)
    rows = build_overview_case_rows(data, person_scope=scope)
    assert {r.case_id for r in rows} == {c.id for c in index.cases_for_entity("person", pid)}
    assert len(rows) == index.counts_for_entity("person", pid).total


@given(projects())
def test_none_scope_returns_pre_feature_rows(data: ProjectData) -> None:
    open_ids = [c.id for c in data.research_cases if c.status != "closed"]
    assert [r.case_id for r in build_overview_case_rows(data, None, None)] == open_ids
    assert [r.case_id for r in build_overview_case_rows(data)] == open_ids
    assert [r.case_id for r in build_overview_case_rows(data, CaseFilter(include_closed=True))] == [
        c.id for c in data.research_cases
    ]

    status = {c.id: c.status for c in data.research_cases}
    pending = [
        a.id
        for a in data.research_actions
        if a.completed_date is None and a.research_case_id in status
        and status[a.research_case_id] != "closed"
    ]
    assert {r.action_id for r in build_todo_rows(data, person_scope=None)} == set(pending)

    assert {r.hypothesis_id for r in build_overview_hypothesis_rows(data, person_scope=None)} == {
        h.id for h in data.research_hypotheses if h.research_case_id in status
    }
