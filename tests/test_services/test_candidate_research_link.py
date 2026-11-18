"""Tests for the candidate <-> research case integration (Requirement 6)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from slaktbusken.model.person import Name, Person
from slaktbusken.services import merge_candidate_service as mcs
from slaktbusken.services.project_service import ProjectService, ValidationError


@pytest.fixture
def svc(tmp_path: Path):
    service = ProjectService()
    service.create_project("T", tmp_path)
    for pid in ("a", "b"):
        service.add_person(
            Person(id=pid, sex="U", names=[Name(type="birth", given=pid, surname="S")])
        )
    cand = service.add_merge_candidate("a", "b")
    return service, cand.id


def test_create_case_success(svc) -> None:
    service, cid = svc
    service._dirty = False
    case = service.create_research_case_for_candidate(cid)
    data = service.data
    assert data.research_cases == [case]
    links = case.linked_entities
    assert len(links) == 2
    assert {(l.entity_type, l.entity_id) for l in links} == {
        ("person", "a"),
        ("person", "b"),
    }
    assert data.merge_candidates[0].research_case_id == case.id
    assert service.is_dirty


def test_create_case_does_not_touch_assessment(svc) -> None:
    service, cid = svc
    service.set_candidate_assessment(cid, "possible")
    service.create_research_case_for_candidate(cid)
    assert service.data.merge_candidates[0].assessment == "possible"
    assert service.data.research_hypotheses == []


def test_create_case_rolls_back_on_failure(svc, monkeypatch) -> None:
    service, cid = svc
    service._dirty = False
    before_cand = replace(service.data.merge_candidates[0])
    before_marks = dict(service.data.id_high_water_marks)

    def boom(*args, **kwargs):
        return ["fel"]

    monkeypatch.setattr(mcs, "validate_merge_candidate", boom)
    with pytest.raises(ValidationError):
        service.create_research_case_for_candidate(cid)
    data = service.data
    assert data.research_cases == []
    assert data.merge_candidates[0] == before_cand
    assert data.merge_candidates[0].research_case_id is None
    assert data.id_high_water_marks == before_marks
    assert not service.is_dirty


def test_create_case_rolls_back_on_case_validation_failure(svc, monkeypatch) -> None:
    service, cid = svc
    service._dirty = False
    monkeypatch.setattr(mcs, "validate_research_case", lambda *a, **k: ["fel"])
    with pytest.raises(ValidationError):
        service.create_research_case_for_candidate(cid)
    assert service.data.research_cases == []
    assert not service.is_dirty


def test_unlink_keeps_case_links_and_candidate(svc) -> None:
    service, cid = svc
    case = service.create_research_case_for_candidate(cid)
    service.set_candidate_research_case(cid, None)
    data = service.data
    assert data.merge_candidates[0].research_case_id is None
    assert [c.id for c in data.research_cases] == [case.id]
    assert len(data.research_cases[0].linked_entities) == 2
    assert len(data.merge_candidates) == 1


def test_case_deletion_leaves_candidate_unchanged(svc) -> None:
    service, cid = svc
    case = service.create_research_case_for_candidate(cid)
    before = replace(service.data.merge_candidates[0])
    assert service.delete_research_case(case.id)
    data = service.data
    assert data.research_cases == []
    assert data.merge_candidates == [before]
    assert data.merge_candidates[0].research_case_id == case.id


def test_service_defines_create_research_case_for_candidate_once() -> None:
    import ast
    import inspect

    from slaktbusken.services import project_service

    tree = ast.parse(inspect.getsource(project_service))
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ProjectService"
    )
    names = [n.name for n in cls.body if isinstance(n, ast.FunctionDef)]
    assert names.count("create_research_case_for_candidate") == 1
