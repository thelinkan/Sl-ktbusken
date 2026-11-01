"""Property 7: Candidate operations never change genealogical data.

Candidate operations (create, assessment incl. ``confirmed``, enable/disable,
research case link/unlink, comment add/edit/delete) leave persons, families,
events, residences, media and DNA data deep-equal. Candidates are only created
by explicit calls: adding persons with equal names, and saving, opening or
editing, never creates, removes or changes candidates.

**Validates: Requirements 2.9, 5.5, 5.6, 5.7**
"""

from __future__ import annotations

import copy
import dataclasses
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.merge_candidate import CANDIDATE_ASSESSMENTS
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.file_io import FilePersistence
from slaktbusken.persistence.serialization import deserialize, serialize
from slaktbusken.services.project_service import ProjectService, ValidationError
from tests.conftest import project_data_strategy

_GENEALOGICAL = (
    "persons",
    "families",
    "events",
    "residences",
    "places",
    "sources",
    "media",
    "repositories",
    "dna_companies",
    "dna_profiles",
    "dna_matches",
    "dna_segments",
    "dna_clusters",
    "dna_triangulations",
)


def _snapshot(data: ProjectData) -> dict:
    return {name: copy.deepcopy(getattr(data, name)) for name in _GENEALOGICAL}


def _candidates(data: ProjectData) -> list:
    return copy.deepcopy(data.merge_candidates)


def _unique_persons(data: ProjectData) -> ProjectData:
    seen: set[str] = set()
    unique = []
    for p in data.persons:
        if p.id not in seen:
            seen.add(p.id)
            unique.append(p)
    data.persons = unique
    return data


def _service(data: ProjectData) -> ProjectService:
    svc = ProjectService()
    svc._project_data = data
    return svc


_op_strategy = st.tuples(
    st.sampled_from(
        [
            "create",
            "assess",
            "enable",
            "link",
            "unlink",
            "case",
            "add_comment",
            "edit_comment",
            "delete_comment",
        ]
    ),
    st.integers(0, 50),
    st.integers(0, 50),
    st.sampled_from(CANDIDATE_ASSESSMENTS),
    st.booleans(),
)


def _apply(svc: ProjectService, op: tuple) -> None:
    kind, i, j, assessment, flag = op
    data = svc.data
    persons = data.persons
    cands = data.merge_candidates
    try:
        if kind == "create":
            if len(persons) >= 2:
                svc.add_merge_candidate(
                    persons[i % len(persons)].id, persons[j % len(persons)].id
                )
            return
        if not cands:
            return
        cand = cands[i % len(cands)]
        if kind == "assess":
            svc.set_candidate_assessment(cand.id, assessment)
        elif kind == "enable":
            svc.set_candidate_enabled(cand.id, flag)
        elif kind == "link":
            if data.research_cases:
                case = data.research_cases[j % len(data.research_cases)]
                svc.set_candidate_research_case(cand.id, case.id)
        elif kind == "unlink":
            svc.set_candidate_research_case(cand.id, None)
        elif kind == "case":
            svc.create_research_case_for_candidate(cand.id, "Ärende")
        elif kind == "add_comment":
            svc.add_candidate_comment(cand.id, "1900", f"kommentar {j}")
        elif kind == "edit_comment" and cand.comments:
            c = cand.comments[j % len(cand.comments)]
            svc.update_candidate_comment(cand.id, c.id, "1901", "ändrad")
        elif kind == "delete_comment" and cand.comments:
            c = cand.comments[j % len(cand.comments)]
            svc.delete_candidate_comment(cand.id, c.id)
    except ValidationError:
        pass


@settings(settings.get_profile("sbk"))
@given(project_data_strategy(), st.lists(_op_strategy, max_size=15))
def test_property_07_candidate_operations_leave_genealogical_data_unchanged(
    data: ProjectData, ops: list
) -> None:
    data = _unique_persons(data)
    before = _snapshot(data)
    svc = _service(data)
    for op in ops:
        _apply(svc, op)
        assert _snapshot(svc.data) == before


@settings(settings.get_profile("sbk"))
@given(project_data_strategy(), st.lists(_op_strategy, max_size=10))
def test_property_07_save_load_and_person_edit_keep_candidates(
    data: ProjectData, ops: list
) -> None:
    data = _unique_persons(data)
    svc = _service(data)
    for op in ops:
        _apply(svc, op)
    cands = _candidates(data)

    # Serialise / deserialise keeps the candidate list and assessments.
    reloaded = deserialize(serialize(data))
    assert reloaded.merge_candidates == cands

    # A person edit (in place) does not touch candidates.
    if data.persons:
        data.persons[0].notes = "ändrad anteckning"
    assert data.merge_candidates == cands

    # Adding a person with an existing name creates no candidate.
    if data.persons:
        src = data.persons[0]
        twin = dataclasses.replace(
            src, id="person_twin_x", names=copy.deepcopy(src.names)
        )
        if twin.id not in {p.id for p in data.persons}:
            svc.add_person(twin)
    assert data.merge_candidates == cands


@settings(settings.get_profile("sbk"), max_examples=15, deadline=None)
@given(st.lists(_op_strategy, max_size=8), st.integers(0, 3))
def test_property_07_real_open_and_save_do_not_create_or_change_candidates(
    ops: list, extra_twins: int
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        svc = ProjectService()
        svc.create_project("P7", Path(tmp))
        names = [Name(type="birth", given="Anna", surname="Svensson")]
        for n in range(2 + extra_twins):
            svc.add_person(Person(id=f"person_{n + 1:03d}", sex="F", names=list(names)))
        # Equal names alone never create candidates.
        assert svc.data.merge_candidates == []

        for op in ops:
            _apply(svc, op)
        cands = _candidates(svc.data)
        snap = _snapshot(svc.data)

        svc.save_project()
        assert svc.data.merge_candidates == cands

        path = Path(tmp) / "P7" / "P7.json.gz"
        loaded = FilePersistence.load(path)
        assert loaded.merge_candidates == cands
        assert _snapshot(loaded) == snap

        reopened = ProjectService()
        reopened.open_project(path)
        assert reopened.data.merge_candidates == cands
        reopened.save_project()
        assert FilePersistence.load(path).merge_candidates == cands


def test_equal_names_do_not_create_candidates() -> None:
    data = ProjectData(project=ProjectMetadata(title="T"))
    svc = _service(data)
    for pid in ("person_001", "person_002"):
        svc.add_person(
            Person(
                id=pid,
                sex="M",
                names=[Name(type="birth", given="Erik", surname="Svensson")],
            )
        )
    assert data.merge_candidates == []
