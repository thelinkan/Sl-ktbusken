"""Property 24: Read-only operations leave all stored state equal.

Building a merge plan (with and without a survivor), applying its change set
and building the sync view to *new* structures, generating the comparison table,
the candidate register and index, the research consistency report and driving a
comparison session leave ``ProjectData``, the translation data, the settings
and the dirty flag equal to their state before the operation.

**Validates: Requirements 11.8, 20.4, 20.11, 26.8, 31.6**
"""

from __future__ import annotations

import copy

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.settings_io import create_default_settings
from slaktbusken.persistence.translation_io import PersonMapping, TranslationData
from slaktbusken.reports.research_consistency import generate_research_consistency_report
from slaktbusken.services import candidate_register
from slaktbusken.services.candidate_index import CandidateIndex
from slaktbusken.services.comparison_session import ComparisonSession, build_rows
from slaktbusken.services.merge_planner import (
    MergeDecisions,
    MergePlanError,
    apply_change_set,
    build_plan,
    build_sync_view,
)
from slaktbusken.services.project_service import ProjectService, ValidationError
from tests.conftest import project_data_strategy


def _prepare(data: ProjectData, pick: tuple[int, int]) -> tuple[ProjectData, str, str]:
    """Unique person ids and at least two persons; returns two ids."""
    seen: set[str] = set()
    unique = []
    for p in data.persons:
        if p.id not in seen:
            seen.add(p.id)
            unique.append(p)
    data.persons = unique
    for n in range(max(0, 2 - len(unique))):
        pid = f"person_extra_{n}"
        data.persons.append(
            Person(id=pid, sex="U", names=[Name(type="birth", given="Anna", surname="Berg")])
        )
    a = data.persons[pick[0] % len(data.persons)].id
    b = data.persons[pick[1] % len(data.persons)].id
    if a == b:
        b = next(p.id for p in data.persons if p.id != a)
    return data, a, b


def _translation(a: str, b: str) -> TranslationData:
    return TranslationData(
        persons=[PersonMapping("@I1@", a, "fp1"), PersonMapping("@I2@", b, None)]
    )


def _state(data, translation, settings_obj, svc: ProjectService) -> tuple:
    return (
        copy.deepcopy(data),
        copy.deepcopy(translation),
        copy.deepcopy(settings_obj),
        svc.is_dirty,
    )


@settings(settings.get_profile("sbk"))
@given(
    project_data_strategy(),
    st.tuples(st.integers(0, 20), st.integers(0, 20)),
    st.sampled_from(["none", "first", "second"]),
    st.booleans(),
)
def test_property_24_planning_leaves_stored_state_equal(
    data: ProjectData, pick: tuple[int, int], survivor_choice: str, confirmed: bool
) -> None:
    data, a, b = _prepare(data, pick)
    translation = _translation(a, b)
    app_settings = create_default_settings()
    svc = ProjectService()
    svc._project_data = data
    before = _state(data, translation, app_settings, svc)

    survivor = {"none": None, "first": a, "second": b}[survivor_choice]
    decisions = MergeDecisions(a, b, survivor_id=survivor, survivor_confirmed=confirmed)

    try:
        plan = build_plan(data, translation, decisions, content_revision=svc.content_revision
                          if hasattr(svc, "content_revision") else 0)
    except MergePlanError:
        # Generated data may be inconsistent; a failed plan must not mutate either.
        assert _state(data, translation, app_settings, svc) == before
        return
    assert _state(data, translation, app_settings, svc) == before

    # Applying the change set and building the sync view yield new structures.
    apply_change_set(data, plan.change_set)
    assert _state(data, translation, app_settings, svc) == before
    build_sync_view(data, plan.change_set)
    assert _state(data, translation, app_settings, svc) == before

    # Planning again from the same inputs is repeatable (nothing was consumed).
    again = build_plan(data, translation, decisions)
    assert again.fingerprint == plan.fingerprint
    assert _state(data, translation, app_settings, svc) == before


@settings(settings.get_profile("sbk"))
@given(
    project_data_strategy(),
    st.tuples(st.integers(0, 20), st.integers(0, 20)),
    st.lists(st.tuples(st.integers(0, 1), st.integers(0, 20)), max_size=6),
)
def test_property_24_comparison_candidate_and_session_reads_leave_state_equal(
    data: ProjectData, pick: tuple[int, int], slot_ops: list
) -> None:
    data, a, b = _prepare(data, pick)
    translation = _translation(a, b)
    app_settings = create_default_settings()
    svc = ProjectService()
    svc._project_data = data
    before = _state(data, translation, app_settings, svc)

    build_rows(data, a, b)
    build_rows(data, a, None)
    generate_research_consistency_report(data)
    candidate_register.build_rows(data)
    candidate_register.query_register(data)
    index = CandidateIndex.build(data)
    for p in data.persons:
        index.relations(p.id)
        index.colour(p.id)
    assert _state(data, translation, app_settings, svc) == before

    session = ComparisonSession.from_pair(a, b)
    for slot, i in slot_ops:
        session.set_slot(slot, data.persons[i % len(data.persons)].id)
        session.select(slot, session.slots[slot])
        session.swap()
    session.compare_selected()
    session.back()
    session.clear_missing({p.id for p in data.persons})
    assert _state(data, translation, app_settings, svc) == before


@settings(settings.get_profile("sbk"))
@given(project_data_strategy(), st.tuples(st.integers(0, 20), st.integers(0, 20)))
def test_property_24_read_only_candidate_lookup_keeps_candidates(
    data: ProjectData, pick: tuple[int, int]
) -> None:
    data, a, b = _prepare(data, pick)
    svc = ProjectService()
    svc._project_data = data
    try:
        svc.add_merge_candidate(a, b)
    except ValidationError:
        pass
    translation = _translation(a, b)
    app_settings = create_default_settings()
    before = _state(data, translation, app_settings, svc)

    CandidateIndex.build(data).candidate_for_pair(a, b)
    candidate_register.query_register(data)
    try:
        build_plan(data, translation, MergeDecisions(a, b, survivor_id=a))
    except MergePlanError:
        pass
    assert _state(data, translation, app_settings, svc) == before
