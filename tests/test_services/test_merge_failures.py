"""Failed merges leave everything unchanged (task 13.11, Mandatory group c).

Property 39: a failing merge leaves everything unchanged in memory (and on
disk). Requirements 22.12, 27.3, 27.5, 27.8, 28.12, 29.11.

Never skipped. Fault injection uses the real engine with failures injected at
the documented step boundaries (plan, post-merge validation, research rewire,
encode, write).
"""

from __future__ import annotations

import copy
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import pytest
from hypothesis import given, settings, strategies as st

from slaktbusken.model.person import Name, Person
from slaktbusken.persistence import translation_io
from slaktbusken.persistence.file_io import FilePersistence
from slaktbusken.persistence.translation_io import PersonMapping
from slaktbusken.services import merge_engine as me
from slaktbusken.services import merge_planner as mp
from slaktbusken.services.merge_engine import MergeEngine
from slaktbusken.services.merge_planner import MergeDecisions, MergePlanError, build_plan
from slaktbusken.services.project_service import ProjectService
from tests.helpers.fault_fs import CountingFs, FaultFs, snapshot_dir

pytestmark = pytest.mark.mandatory_integrity

SCENARIOS = (
    "plan_invalid",
    "post_merge_validation_failure",
    "research_rewire_error",
    "encode_error",
    "write_error",
)


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _person(pid: str, given: str) -> Person:
    return Person(id=pid, sex="F", names=[Name("birth", given, "Berg")])


def _make_service(root: Path) -> ProjectService:
    svc = ProjectService()
    svc.create_project("Test", root)
    svc.data.persons.extend([_person("person_1", "Anna"), _person("person_2", "Anna")])
    translation_io.write_persons(
        [PersonMapping("@I2@", "person_2", "fp2")],
        [],
        svc.project_path.parent / "translation" / "persons.json",
    )
    svc._dirty = True
    svc.save_project()
    return svc


def _decisions(confirmed: bool = True) -> MergeDecisions:
    return MergeDecisions(
        "person_1", "person_2", survivor_id="person_1", survivor_confirmed=confirmed
    )


def _build(svc: ProjectService, confirmed: bool = True):
    translation = translation_io.read_all(svc.project_path.parent / "translation")
    return build_plan(svc.data, translation, _decisions(confirmed), svc.content_revision)


class _BadLedger:
    def differences(self, _other):
        return {"persons": 1}


def _first_replace_index(svc: ProjectService) -> int:
    """Dry run on a counting fs (on a throw-away project) to find the first replace."""
    with tempfile.TemporaryDirectory() as tmp:
        other = _make_service(Path(tmp))
        counting = CountingFs()
        assert MergeEngine(other, None, fs=counting).execute(_build(other)).success
        return counting.names().index("replace") + 1


@contextmanager
def _inject(scenario: str, svc: ProjectService, write_op: int = 4):
    """Yield ``(plan_or_None, fs_or_None)`` with the failure of *scenario* armed."""
    if scenario == "plan_invalid":
        yield _build(svc, confirmed=False), None
    elif scenario == "post_merge_validation_failure":
        plan = _build(svc)
        with mock.patch.object(me, "compute_ledger", return_value=_BadLedger()):
            yield plan, None
    elif scenario == "research_rewire_error":
        with mock.patch.object(
            mp, "rewire_entity_merge", side_effect=RuntimeError("rewire failed")
        ):
            with pytest.raises(MergePlanError):
                _build(svc)
            yield None, None
    elif scenario == "encode_error":
        plan = _build(svc)
        with mock.patch.object(FilePersistence, "encode", side_effect=ValueError("encode")):
            yield plan, None
    elif scenario == "write_error":
        yield _build(svc), FaultFs(write_op, "io_error_before")
    else:  # pragma: no cover
        raise AssertionError(scenario)


def _state(svc: ProjectService):
    return {
        "data": copy.deepcopy(svc.data),
        "disk": snapshot_dir(svc.project_path.parent),
        "dirty": svc.is_dirty,
        "revision": svc.revision,
        "content_revision": svc.content_revision,
        "history": list(svc.data.merge_history),
        "persons": [p.id for p in svc.data.persons],
    }


def _run_failing(scenario: str, svc: ProjectService, write_op: int = 4):
    calls: list[int] = []
    svc.add_merge_listener(lambda: calls.append(1))
    with _inject(scenario, svc, write_op) as (plan, fs):
        outcome = None
        if plan is not None:
            outcome = MergeEngine(svc, None, fs=fs).execute(plan)
    return outcome, calls


def _assert_unchanged(svc: ProjectService, before: dict) -> None:
    assert svc.data == before["data"]
    assert [p.id for p in svc.data.persons] == before["persons"]
    assert svc.data.merge_history == before["history"]
    assert svc.is_dirty == before["dirty"]
    assert svc.revision == before["revision"]
    assert svc.content_revision == before["content_revision"]
    assert svc.is_saved_state()
    after = snapshot_dir(svc.project_path.parent)
    assert after == before["disk"]
    assert not list(svc.project_path.parent.glob("*.merge-journal.json"))
    assert not svc.project_path.with_suffix(".lock").exists()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def service(tmp_path: Path) -> ProjectService:
    return _make_service(tmp_path)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_failed_merge_leaves_data_unchanged(service: ProjectService, scenario: str) -> None:
    before = _state(service)

    outcome, calls = _run_failing(scenario, service)

    if scenario != "research_rewire_error":  # there the plan itself cannot be built
        assert outcome is not None and not outcome.success
        assert outcome.message
    assert calls == []  # no merge listener notified
    _assert_unchanged(service, before)
    service.save_project()  # the in-progress flag was released


def test_failed_merge_leaves_translation_files_unchanged(
    service: ProjectService,
) -> None:
    translation_dir = service.project_path.parent / "translation"
    for scenario in SCENARIOS:
        before = snapshot_dir(translation_dir)
        before_tr = translation_io.read_all(translation_dir)

        _run_failing(scenario, service)

        assert snapshot_dir(translation_dir) == before, scenario
        after_tr = translation_io.read_all(translation_dir)
        assert [(m.gedcom_id, m.app_id) for m in after_tr.persons] == [
            (m.gedcom_id, m.app_id) for m in before_tr.persons
        ]
        assert after_tr.person_aliases == before_tr.person_aliases == []


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_failed_merge_leaves_dirty_flag_unchanged(
    service: ProjectService, scenario: str
) -> None:
    dirty, revision, content = service.is_dirty, service.revision, service.content_revision
    history = len(service.data.merge_history)

    _run_failing(scenario, service)

    assert service.is_dirty == dirty
    assert service.revision == revision
    assert service.content_revision == content
    assert len(service.data.merge_history) == history


# Feature: person-comparison-and-merge, Property 39:
@settings(max_examples=100, deadline=None)
@given(scenario=st.sampled_from(SCENARIOS), op_offset=st.integers(min_value=0, max_value=100))
def test_property_39_failing_merge_leaves_everything_unchanged(
    scenario: str, op_offset: int
) -> None:
    """**Validates: Requirements 22.12, 27.3, 27.5, 27.8, 28.12, 29.11**"""
    with tempfile.TemporaryDirectory() as tmp:
        svc = _make_service(Path(tmp))
        # Write errors are injected at any operation before the first replace.
        write_op = 1 + op_offset % (_first_replace_index(svc) - 1)
        before = _state(svc)

        outcome, calls = _run_failing(scenario, svc, write_op)

        if scenario != "research_rewire_error":
            assert outcome is not None and not outcome.success
        assert calls == []
        _assert_unchanged(svc, before)
