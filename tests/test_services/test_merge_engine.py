"""MergeEngine: preconditions, atomic commit and adopt step (task 13.5)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from slaktbusken.model.person import Name, Person
from slaktbusken.persistence import translation_io
from slaktbusken.persistence.file_io import FilePersistence
from slaktbusken.persistence.translation_io import PersonMapping
from slaktbusken.services.merge_engine import MergeEngine
from slaktbusken.services.merge_planner import MergeDecisions, build_plan
from slaktbusken.services.project_service import ProjectService
from tests.helpers.fault_fs import FaultFs


class FakeEditor:
    editor_title = "Personredigerare: Anna (p1)"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def has_unsaved_changes(self) -> bool:
        self.calls.append("has_unsaved_changes")
        return True

    def request_resolution(self):  # pragma: no cover - must never be called
        self.calls.append("request_resolution")


def _person(pid: str, given: str) -> Person:
    return Person(id=pid, sex="F", names=[Name("birth", given, "Berg")])


@pytest.fixture
def service(tmp_path: Path) -> ProjectService:
    svc = ProjectService()
    svc.create_project("Test", tmp_path)
    svc.data.persons.extend([_person("person_1", "Anna"), _person("person_2", "Anna")])
    translation_dir = svc.project_path.parent / "translation"
    translation_io.write_persons(
        [PersonMapping("@I2@", "person_2", "fp2")], [], translation_dir / "persons.json"
    )
    svc._dirty = True
    svc.save_project()
    return svc


def _plan(svc: ProjectService):
    translation = translation_io.read_all(svc.project_path.parent / "translation")
    decisions = MergeDecisions(
        "person_1", "person_2", survivor_id="person_1", survivor_confirmed=True
    )
    return build_plan(svc.data, translation, decisions, svc.content_revision)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _files(svc: ProjectService) -> tuple[str, str]:
    return (
        _digest(svc.project_path),
        _digest(svc.project_path.parent / "translation" / "persons.json"),
    )


def test_successful_merge_commits_and_adopts(service: ProjectService) -> None:
    plan = _plan(service)
    assert plan.can_execute
    live = service.data
    calls: list[int] = []
    service.add_merge_listener(lambda: calls.append(1))
    rev, content = service.revision, service.content_revision

    outcome = MergeEngine(service, None).execute(plan)

    assert outcome.success, outcome.message
    assert service.data is live  # same instance, fields adopted
    assert [p.id for p in service.data.persons] == ["person_1"]
    assert service.data.id_high_water_marks["person_"] == 2
    assert [h.merged_person_id for h in service.data.merge_history] == ["person_2"]
    assert not service.is_dirty and service.is_saved_state()
    assert service.revision == rev + 1 and service.content_revision == content + 1
    assert len(calls) == 1

    reloaded = FilePersistence.load(service.project_path)
    assert [p.id for p in reloaded.persons] == ["person_1"]
    tr = translation_io.read_all(service.project_path.parent / "translation")
    assert tr.persons == []
    assert [(a.gedcom_id, a.person_id) for a in tr.person_aliases] == [("@I2@", "person_1")]
    assert not list(service.project_path.parent.glob("*.merge-journal.json"))
    assert not service.project_path.with_suffix(".lock").exists()


def test_dirty_project_is_refused_without_changes(service: ProjectService) -> None:
    plan = _plan(service)
    service._dirty = True
    before, rev = _files(service), service.revision

    outcome = MergeEngine(service, None).execute(plan)

    assert not outcome.success
    assert outcome.message == (
        "Projektet har osparade ändringar. Spara projektet innan sammanslagningen."
    )
    assert _files(service) == before
    assert service.is_dirty and service.revision == rev
    assert len(service.data.persons) == 2


def test_unsaved_editor_is_refused_and_only_asked(service: ProjectService) -> None:
    from slaktbusken.services.editor_registry import EditorRegistry

    plan = _plan(service)
    registry = EditorRegistry()
    editor = FakeEditor()
    registry.register(editor)
    before, rev = _files(service), service.revision

    outcome = MergeEngine(service, registry).execute(plan)

    assert not outcome.success
    assert "Personredigerare: Anna (p1)" in outcome.message
    assert editor.calls and set(editor.calls) == {"has_unsaved_changes"}
    assert _files(service) == before and service.revision == rev


def test_stale_plan_is_reported(service: ProjectService) -> None:
    plan = _plan(service)
    service.data.persons[0].title = "Dr"
    service._dirty = True
    service.save_project()  # saved again, but content changed

    outcome = MergeEngine(service, None).execute(plan)

    assert not outcome.success and outcome.stale
    assert outcome.message == "Projektet har ändrats; granska förhandsgranskningen igen."
    assert len(service.data.persons) == 2


def test_save_does_not_make_plan_stale(service: ProjectService) -> None:
    plan = _plan(service)
    service.save_project()
    assert MergeEngine(service, None).execute(plan).success


def test_failed_commit_leaves_everything_unchanged(service: ProjectService) -> None:
    plan = _plan(service)
    before, rev, content = _files(service), service.revision, service.content_revision
    calls: list[int] = []
    service.add_merge_listener(lambda: calls.append(1))

    outcome = MergeEngine(service, None, fs=FaultFs(4, "io_error_before")).execute(plan)

    assert not outcome.success
    assert _files(service) == before
    assert len(service.data.persons) == 2 and service.data.merge_history == []
    assert not service.is_dirty and service.is_saved_state()
    assert service.revision == rev and service.content_revision == content
    assert calls == []
    service.save_project()  # engine released the in-progress flag


def test_missing_handler_refuses_merge(service: ProjectService, monkeypatch) -> None:
    plan = _plan(service)
    from slaktbusken.services import person_reference_index as pri

    monkeypatch.setattr(pri, "HANDLER_REGISTRY", {})
    before = _files(service)

    outcome = MergeEngine(service, None).execute(plan)

    assert not outcome.success and "family.partners" in outcome.message
    assert _files(service) == before and len(service.data.persons) == 2


# --- Task 13.24: Saved_State_Precondition as step 0 of execute ---------------


def test_precondition_runs_before_plan_validation(service: ProjectService) -> None:
    from dataclasses import replace

    plan = replace(_plan(service), content_revision=service.content_revision - 1)  # stale
    service._dirty = True

    outcome = MergeEngine(service, None).execute(plan)

    assert not outcome.success and not outcome.stale
    assert outcome.step == "precondition"
    assert outcome.message.startswith("Projektet har osparade ändringar.")


def test_refusal_calls_no_save_commit_or_adopt(service: ProjectService, monkeypatch) -> None:
    from slaktbusken.services.editor_registry import EditorRegistry

    plan = _plan(service)
    registry = EditorRegistry()
    editor = FakeEditor()
    registry.register(editor)
    called: list[str] = []
    for name in ("save_project", "adopt_committed_state"):
        monkeypatch.setattr(service, name, lambda *a, _n=name, **k: called.append(_n))
    from slaktbusken.services.commit import transaction

    monkeypatch.setattr(
        transaction.MergeTransaction, "commit",
        lambda *a, **k: called.append("commit"),
    )
    rev, content, dirty = service.revision, service.content_revision, service.is_dirty

    outcome = MergeEngine(service, registry).execute(plan)

    assert not outcome.success and outcome.step == "precondition"
    assert called == []
    assert (service.revision, service.content_revision, service.is_dirty) == (
        rev, content, dirty,
    )
    assert set(editor.calls) == {"has_unsaved_changes"}
    assert len(service.data.persons) == 2


def test_refusal_names_every_unsaved_editor(service: ProjectService) -> None:
    from slaktbusken.services.editor_registry import EditorRegistry

    class Second(FakeEditor):
        editor_title = "Familjeredigerare: F1"

    plan = _plan(service)
    registry = EditorRegistry()
    first, second = FakeEditor(), Second()  # registry holds weak references
    registry.register(first)
    registry.register(second)

    outcome = MergeEngine(service, registry).execute(plan)

    assert not outcome.success
    assert "Personredigerare: Anna (p1)" in outcome.message
    assert "Familjeredigerare: F1" in outcome.message
    assert outcome.message.count("har osparade ändringar") == 2
