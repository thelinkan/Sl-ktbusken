"""Property 3 (retired-person part): ids of persons retired by a merge are never reissued.

Mandatory group e (Requirement 35.1(e)). Merges are performed with the real
MergeEngine; the candidate, comment and history prefixes are covered by
test_id_registry.py.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from slaktbusken.gedcom.importer import GEDCOMImporter
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence import translation_io
from slaktbusken.persistence.file_io import FilePersistence
from slaktbusken.services.id_registry import issue_person_id, retired_person_ids
from slaktbusken.services.merge_engine import MergeEngine
from slaktbusken.services.merge_planner import MergeDecisions, build_plan
from slaktbusken.services.project_service import ProjectService

pytestmark = pytest.mark.mandatory_integrity


def _person(pid: str, given_name: str) -> Person:
    return Person(id=pid, sex="F", names=[Name("birth", given_name, "Berg")])


def _new_service(base: Path, person_ids: list[str]) -> ProjectService:
    svc = ProjectService()
    svc.create_project("Test", base)
    svc.data.persons.extend(_person(pid, "Anna") for pid in person_ids)
    svc._dirty = True
    svc.save_project()
    return svc


def _merge(svc: ProjectService, survivor: str, retired: str) -> None:
    """Merge *retired* into *survivor* with the real engine and assert success."""
    translation = translation_io.read_all(svc.project_path.parent / "translation")
    decisions = MergeDecisions(survivor, retired, survivor_id=survivor, survivor_confirmed=True)
    plan = build_plan(svc.data, translation, decisions, svc.content_revision)
    assert plan.can_execute, [c.message for c in plan.blocking]
    outcome = MergeEngine(svc, None).execute(plan)
    assert outcome.success, outcome.message


def _add_person(svc: ProjectService, data: ProjectData | None = None) -> str:
    """Issue an id the way a creator must and add the person; return the id."""
    target = data if data is not None else svc.data
    new_id = issue_person_id(target)
    target.persons.append(_person(new_id, "Anna"))
    svc._dirty = True
    svc.save_project()
    return new_id


def _number(pid: str) -> int:
    match = re.fullmatch(r"person_(\d+)", pid)
    assert match, pid
    return int(match.group(1))


def test_retired_id_never_reissued(tmp_path: Path) -> None:
    """**Validates: Requirements 2.3, 7.5, 28.3**"""
    svc = _new_service(tmp_path, ["person_1", "person_2", "person_3"])
    _merge(svc, "person_1", "person_2")
    assert retired_person_ids(svc.data) == {"person_2"}

    issued = [_add_person(svc) for _ in range(4)]

    assert "person_2" not in issued
    assert len(set(issued)) == len(issued)
    live = {p.id for p in svc.data.persons}
    assert "person_2" not in live
    assert not live & retired_person_ids(svc.data)


def test_retired_id_with_highest_suffix_not_reissued(tmp_path: Path) -> None:
    """**Validates: Requirements 7.5, 7.6, 28.3**"""
    svc = _new_service(tmp_path, ["person_1", "person_2", "person_3"])
    _merge(svc, "person_1", "person_3")  # the highest suffix is retired
    assert [p.id for p in svc.data.persons] == ["person_1", "person_2"]

    new_id = issue_person_id(svc.data)

    assert new_id != "person_3"
    assert _number(new_id) > 3


def test_retired_id_not_reissued_after_save_and_reopen(tmp_path: Path) -> None:
    """**Validates: Requirements 2.3, 7.5, 7.6, 34.9**"""
    svc = _new_service(tmp_path, ["person_1", "person_2", "person_3"])
    _merge(svc, "person_1", "person_3")
    project_path = svc.project_path

    reopened = ProjectService()
    reopened.open_project(project_path)
    assert retired_person_ids(reopened.data) == {"person_3"}
    assert "person_3" not in {p.id for p in reopened.data.persons}

    new_id = _add_person(reopened)
    assert new_id != "person_3" and _number(new_id) > 3

    # A second reopen of the file written by the reopened service still protects it.
    again = FilePersistence.load(project_path)
    assert retired_person_ids(again) == {"person_3"}
    assert issue_person_id(again) not in {"person_3", new_id}


_GEDCOM = """0 HEAD
1 GEDC
2 VERS 5.5.1
2 FORM LINEAGE-LINKED
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Karin /Lind/
1 SEX F
0 @I2@ INDI
1 NAME Erik /Lind/
1 SEX M
0 @I3@ INDI
1 NAME Olof /Lind/
1 SEX M
0 TRLR
"""


def test_importer_seeded_with_retired_ids(tmp_path: Path) -> None:
    """**Validates: Requirements 7.5, 7.6, 28.3, 34.9**"""
    svc = _new_service(tmp_path, ["person_1", "person_2", "person_3"])
    _merge(svc, "person_1", "person_3")
    data = svc.data
    assert retired_person_ids(data) == {"person_3"}

    gedcom_path = tmp_path / "ny.ged"
    gedcom_path.write_text(_GEDCOM, encoding="utf-8")
    importer = GEDCOMImporter(data, svc.project_path.parent / "translation")
    importer.import_file(gedcom_path)

    new_ids = {p.id for p in data.persons} - {"person_1", "person_2"}
    assert len(new_ids) == 3
    assert "person_3" not in new_ids
    assert all(_number(pid) > 3 for pid in new_ids)


_op = st.one_of(
    st.tuples(st.just("create")),
    st.tuples(st.just("merge"), st.integers(0, 20), st.integers(0, 20)),
    st.tuples(st.just("reopen")),
)


@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)
@given(ops=st.lists(_op, max_size=8))
def test_property_3_retired_ids(ops: list) -> None:
    """**Validates: Requirements 2.3, 7.5, 7.6, 28.3, 34.9**"""
    with tempfile.TemporaryDirectory() as tmp:
        svc = _new_service(Path(tmp), ["person_1", "person_2"])
        ever_issued: set[str] = {"person_1", "person_2"}
        retired: set[str] = set()

        for op in ops:
            if op[0] == "create":
                new_id = _add_person(svc)
                assert new_id not in ever_issued, f"{new_id} was reissued"
                assert new_id not in retired
                ever_issued.add(new_id)
            elif op[0] == "merge":
                live = [p.id for p in svc.data.persons]
                if len(live) < 2:
                    continue
                first = live[op[1] % len(live)]
                second = live[op[2] % len(live)]
                if first == second:
                    continue
                _merge(svc, first, second)
                retired.add(second)
            else:
                path = svc.project_path
                svc = ProjectService()
                svc.open_project(path)

            assert retired_person_ids(svc.data) == retired
            assert not {p.id for p in svc.data.persons} & retired

        # Whatever happened, the next id is fresh.
        assert issue_person_id(svc.data) not in ever_issued
