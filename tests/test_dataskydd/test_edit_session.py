"""Edit-session tests (Requirements 1.1 to 1.14, 2.1 to 2.6, 17.2).

Property 1 and Property 2 run on generated projects and mutation sequences
(``strategies_session``). The example tests cover the cancel and save paths,
the Session_Start_Conditions, the deferral of ``mark_changed`` and the two B1
reproductions with the real ``PersonEditor`` methods.
"""

from __future__ import annotations

import copy
import dataclasses
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from slaktbusken.model.event import Event, Participant
from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.media import MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.model.record_origin import RecordOrigin
from slaktbusken.model.research_case import ResearchCase
from slaktbusken.model.residence import ResidenceFact
from slaktbusken.model.source import Leverantor, Source
from slaktbusken.persistence.serialization import serialize
from slaktbusken.services import edit_session as es_module
from slaktbusken.services.edit_session import (
    SESSION_EXCLUDED_FIELDS,
    EditSessionBusy,
    EditSessionConflict,
    EditSessionRefused,
    UnsavedEditorsBlock,
)
from slaktbusken.services.editor_registry import EditorRegistry
from slaktbusken.services.parent_service import ParentService
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.editors.person_editor import PersonEditor

from tests.test_dataskydd.strategies_session import (
    apply_op,
    make_session_project,
    ops_strategy,
    project_strategy,
)

pytestmark = pytest.mark.mandatory_integrity


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def make_service(data: ProjectData) -> ProjectService:
    service = ProjectService()
    service._project_data = data
    service._dirty_value = False
    return service


def _list_fields() -> list[str]:
    probe = ProjectData()
    return [
        f.name
        for f in dataclasses.fields(ProjectData)
        if isinstance(getattr(probe, f.name), list)
    ]


def _identity_state(data: ProjectData) -> dict:
    """Identity of every list object and of every entity in it."""
    return {
        name: (getattr(data, name), [id(e) for e in getattr(data, name)])
        for name in _list_fields()
    }


# ----------------------------------------------------------------------
# Property 1 and Property 2
# ----------------------------------------------------------------------


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=project_strategy, ops=ops_strategy)
def test_dp_property_1_cancel_restores_state_exactly(data, ops):
    """**Property 1: Cancelling an edit session restores state exactly**

    **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.2, 2.3**
    """
    service = make_service(data)
    before = serialize(data)
    identity = _identity_state(data)
    counters = (
        service.is_saved_state(),
        service._dirty_value,
        service.content_revision,
        service.clean_content_revision,
    )
    session = service.begin_edit_session("Personredigerare")
    for op, n in ops:
        apply_op(data, op, n)
    session.rollback()

    assert serialize(data) == before
    after = _identity_state(data)
    for name, (list_obj, ids) in identity.items():
        assert after[name][0] is list_obj, f"{name} is a different list object"
        assert after[name][1] == ids, f"{name} entities are different objects"
    assert (
        service.is_saved_state(),
        service._dirty_value,
        service.content_revision,
        service.clean_content_revision,
    ) == counters
    assert service.active_edit_session is None


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=project_strategy, ops=ops_strategy)
def test_dp_property_2_commit_marks_changed_exactly_when_data_changed(data, ops):
    """**Property 2: Committing an edit session marks the project changed exactly
    when data changed**

    **Validates: Requirements 1.5, 1.6, 17.2**
    """
    service = make_service(data)
    before = serialize(data)
    revision = service.content_revision
    session = service.begin_edit_session("Personredigerare")
    for op, n in ops:
        apply_op(data, op, n)
    differs = serialize(data) != before
    session.commit()

    assert service._dirty_value is differs
    assert service.content_revision == revision + (1 if differs else 0)
    assert service.active_edit_session is None


# ----------------------------------------------------------------------
# Cancel and save examples
# ----------------------------------------------------------------------


def _small() -> tuple[ProjectData, ProjectService]:
    data = make_session_project(3, 2, 2, 3, 2)
    return data, make_service(data)


def test_cancel_restores_identity_of_entities():
    data, service = _small()
    persons = list(data.persons)
    events_list = data.events
    events = list(data.events)
    session = service.begin_edit_session("Personredigerare")
    data.persons[0].notes = "ändrad"
    data.events = [e for e in data.events if e is not events[0]]
    session.rollback()
    assert data.persons[0] is persons[0] and data.persons[0].notes != "ändrad"
    assert data.events is events_list
    assert all(a is b for a, b in zip(data.events, events)) and len(data.events) == 3


def test_cancel_leaves_dirty_and_revision_unchanged():
    data, service = _small()
    service.mark_changed("tidigare")
    revision, clean = service.content_revision, service.clean_content_revision
    notified: list[int] = []
    service.add_merge_listener(lambda: notified.append(1))
    session = service.begin_edit_session("Personredigerare")
    data.places.append(Place(id="place_x", type="parish", name="X"))
    session.rollback()
    assert service._dirty_value is True
    assert (service.content_revision, service.clean_content_revision) == (revision, clean)
    assert notified == [1]  # one notification from rollback


def test_save_unchanged_does_not_mark_dirty():
    data, service = _small()
    revision = service.content_revision
    original = data.persons[0].notes
    session = service.begin_edit_session("Personredigerare")
    data.persons[0].notes = "x"
    data.persons[0].notes = original  # back to the saved value
    assert session.commit() is False
    assert service._dirty_value is False
    assert service.content_revision == revision


def test_save_changed_marks_once():
    data, service = _small()
    revision = service.content_revision
    notified: list[int] = []
    service.add_merge_listener(lambda: notified.append(1))
    session = service.begin_edit_session("Personredigerare")
    data.persons[0].notes = "ny anteckning"
    assert session.commit() is True
    assert service._dirty_value is True
    assert service.content_revision == revision + 1
    assert notified == [1]


def test_second_session_refused():
    _, service = _small()
    service.begin_edit_session("Personredigerare")
    with pytest.raises(EditSessionBusy):
        service.begin_edit_session("Personredigerare")


def test_conflict_detected_refuses_rollback():
    data, service = _small()
    session = service.begin_edit_session("Personredigerare")
    data.persons[0].notes = "ändrad"
    service._dirty = True  # a change from outside the session
    with pytest.raises(EditSessionConflict):
        session.rollback()
    assert data.persons[0].notes == "ändrad"  # nothing restored
    assert service.active_edit_session is session


# ----------------------------------------------------------------------
# Session_Start_Conditions
# ----------------------------------------------------------------------


class _UnsavedEditor:
    editor_title = "Källredigerare: Kyrkbok"

    def has_unsaved_changes(self) -> bool:
        return True

    def request_resolution(self):  # pragma: no cover - never called
        raise AssertionError


def _refuse_a(service):
    service.begin_edit_session("Personredigerare")
    return EditSessionBusy, None


def _refuse_b(service):
    registry = EditorRegistry()
    editor = _UnsavedEditor()
    registry.register(editor)
    service.set_editor_registry(registry)
    service._keep = editor
    return UnsavedEditorsBlock, editor.editor_title


def _refuse_c(service):
    service._merge_in_progress = True
    return EditSessionRefused, None


def _refuse_c2(service):
    service._import_save_unfinished = True
    return EditSessionRefused, None


def _refuse_d(service):
    service.set_import_in_progress(True)
    return EditSessionRefused, None


def _refuse_e(service):
    service._project_data = None
    return EditSessionRefused, None


@pytest.mark.parametrize(
    "arrange",
    [_refuse_a, _refuse_b, _refuse_c, _refuse_c2, _refuse_d, _refuse_e],
    ids=["a", "b", "c", "c2", "d", "e"],
)
def test_session_start_refused_when_unsafe(arrange):
    _, service = _small()
    exc_type, title = arrange(service)
    revision = service.content_revision
    with pytest.raises(exc_type) as info:
        service.begin_edit_session("Personredigerare")
    assert str(info.value)
    if title is not None:
        assert title in str(info.value)
    assert service.content_revision == revision


def test_session_start_refused_when_unsafe_f_snapshot_fails():
    data, service = _small()
    real = copy.deepcopy
    with patch.object(es_module.copy, "deepcopy", side_effect=MemoryError):
        with pytest.raises(EditSessionRefused) as info:
            service.begin_edit_session("Personredigerare")
    assert copy.deepcopy is real
    assert "Inget har ändrats" in str(info.value)
    assert service.active_edit_session is None


def test_session_snapshot_covers_every_project_data_field():
    data, service = _small()
    session = service.begin_edit_session("Personredigerare")
    field_names = {f.name for f in dataclasses.fields(ProjectData)}
    assert set(SESSION_EXCLUDED_FIELDS) <= field_names
    covered = set(session._pairs) | {"project", "connection_overrides"}
    assert covered == field_names - set(SESSION_EXCLUDED_FIELDS)
    # Every covered list field has a snapshot entry per entity.
    for name, pairs in session._pairs.items():
        assert len(pairs) == len(getattr(data, name))
    session.rollback()


# ----------------------------------------------------------------------
# Structure edits
# ----------------------------------------------------------------------


def test_cancel_after_parent_family_edit_restores_families():
    data = make_session_project(4, 2, 1, 2, 1)
    service = make_service(data)
    family = data.families[0]
    before = serialize(data)
    session = service.begin_edit_session("Personredigerare")
    ParentService(data).add_parent("person_1", "person_2", "biological")
    assert serialize(data) != before
    session.rollback()
    assert serialize(data) == before
    assert data.families[0] is family and len(data.families) == 1


def test_cancel_after_new_family_removes_family():
    data = make_session_project(4, 2, 1, 2, 1)
    service = make_service(data)
    before = serialize(data)
    session = service.begin_edit_session("Personredigerare")
    ParentService(data).add_parent("person_3", "person_2", "biological")
    assert any("person_3" in f.children for f in data.families)
    assert len(data.families) == 2
    session.rollback()
    assert len(data.families) == 1
    assert serialize(data) == before


# ----------------------------------------------------------------------
# Nested creations and deletions
# ----------------------------------------------------------------------


def test_cancel_removes_nested_created_place():
    data, service = _small()
    session = service.begin_edit_session("Personredigerare")
    data.places.append(Place(id="place_new", type="parish", name="Ny"))
    session.rollback()
    assert [p.id for p in data.places] == ["place_0", "place_1"]


def test_cancel_removes_nested_created_source():
    data, service = _small()
    session = service.begin_edit_session("Personredigerare")
    data.sources.append(Source(id="source_new", provider="p", source_type="t", title="Ny"))
    session.rollback()
    assert [s.id for s in data.sources] == ["source_0", "source_1"]


def test_cancel_restores_nested_deleted_place():
    data, service = _small()
    place = data.places[0]
    session = service.begin_edit_session("Personredigerare")
    data.places = [p for p in data.places if p is not place]
    session.rollback()
    assert data.places[0] is place and len(data.places) == 2


def test_cancel_removes_nested_created_media(tmp_path):
    data, service = _small()
    created = tmp_path / "bild.jpg"
    session = service.begin_edit_session("Personredigerare")
    created.write_bytes(b"x")
    session.register_created_file(created)
    data.media.append(MediaItem(id="media_new", type="photo", file="bild.jpg", title="Ny"))
    session.rollback()
    assert [m.id for m in data.media] == ["media_0"]
    assert not created.exists()


def test_save_keeps_nested_created_entities(tmp_path):
    data, service = _small()
    created = tmp_path / "bild.jpg"
    session = service.begin_edit_session("Personredigerare")
    created.write_bytes(b"x")
    session.register_created_file(created)
    data.media.append(MediaItem(id="media_new", type="photo", file="bild.jpg", title="Ny"))
    data.places.append(Place(id="place_new", type="parish", name="Ny"))
    session.commit()
    assert "media_new" in [m.id for m in data.media]
    assert "place_new" in [p.id for p in data.places]
    assert created.exists()
    assert service._dirty_value is True


def test_cancel_removes_nested_creation_in_leverantorer_and_research():
    data, service = _small()
    before = serialize(data)
    session = service.begin_edit_session("Personredigerare")
    data.leverantorer.append(Leverantor(id="lev_new", name="Ny"))
    data.research_cases.append(ResearchCase(id="case_new"))
    session.rollback()
    assert [x.id for x in data.leverantorer] == ["lev_0"]
    assert [x.id for x in data.research_cases] == ["case_0"]
    assert serialize(data) == before


def test_edit_session_restores_residence_origins():
    data, service = _small()
    residence = data.residences[0]
    origins_before = copy.deepcopy(residence.origins)
    session = service.begin_edit_session("Personredigerare")
    residence.origins.append(
        RecordOrigin(owner_kind="person", owner_id="person_0", owner_xref="@X@",
                     tag_key="RESI", index=9, record_hash="zz")
    )
    residence.origins[0].record_hash = "ändrad"
    session.rollback()
    assert data.residences[0] is residence
    assert residence.origins == origins_before


# ----------------------------------------------------------------------
# mark_changed deferral
# ----------------------------------------------------------------------


def test_mark_changed_deferred_in_edit_session():
    data, service = _small()
    notified: list[int] = []
    service.add_merge_listener(lambda: notified.append(1))
    revision = service.content_revision

    session = service.begin_edit_session("Personredigerare")
    service.mark_changed("under redigering")
    service.mark_changed("igen")
    assert service._dirty_value is False
    assert service.content_revision == revision
    assert notified == []
    session.commit()  # nothing differs from the snapshot
    assert service._dirty_value is False and notified == []

    session = service.begin_edit_session("Personredigerare")
    service.mark_changed("a")
    data.persons[0].notes = "ändrad"
    service.mark_changed("b")
    session.commit()
    assert service._dirty_value is True
    assert service.content_revision == revision + 1
    assert notified == [1]

    service.mark_changed("efter sessionen")  # direct again
    assert service.content_revision == revision + 2


# ----------------------------------------------------------------------
# B1: real PersonEditor methods, headless
# ----------------------------------------------------------------------


def _b1_project() -> ProjectData:
    data = make_session_project(2, 2, 1, 0, 0)
    data.events = [
        Event(id="event_a", type="birth",
              participants=[Participant(person_id="person_0", role="principal")]),
        Event(id="event_b", type="death",
              participants=[Participant(person_id="person_0", role="principal")]),
    ]
    data.residences = [ResidenceFact(id="res_a", person_id="person_0", place_id="place_0")]
    return data


def test_cancel_after_remove_event_restores_event(qapp):
    data = _b1_project()
    service = make_service(data)
    person = data.persons[0]
    event = next(e for e in data.events if e.id == "event_a")
    events_list = data.events
    before = serialize(data)
    session = service.begin_edit_session("Personredigerare")
    editor = PersonEditor(data, person=person, project_service=service)
    for row in range(editor._ui.events_list.count()):
        item = editor._ui.events_list.item(row)
        if item.data(Qt.ItemDataRole.UserRole) == "event_a":
            editor._ui.events_list.setCurrentRow(row)
    editor._on_remove_event()
    assert all(e.id != "event_a" for e in data.events)
    session.rollback()
    assert any(e is event for e in data.events)
    assert data.events is events_list
    assert serialize(data) == before
    assert service._dirty_value is False


def test_cancel_after_delete_residence_restores_residence(qapp):
    data = _b1_project()
    service = make_service(data)
    person = data.persons[0]
    residence = data.residences[0]
    residences_list = data.residences
    before = serialize(data)
    session = service.begin_edit_session("Personredigerare")
    editor = PersonEditor(data, person=person, project_service=service)
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        editor._on_delete_residence("res_a")
    assert data.residences == []
    session.rollback()
    assert data.residences is residences_list
    assert data.residences[0] is residence
    assert serialize(data) == before
