"""Change-path coverage (Requirements 4.3, 5.3, 17.6, 18.1 to 18.7).

The registry lists every path through which an editor or service changes
project data, one entry per path and owner. Property 20 applies each path to a
generated project and checks that the project is marked changed exactly when
the Canonical_Form differs.

The GEDCOM import path (``ImportService.run``, which adopts its working copy
through ``ProjectService.adopt_working_copy``) is registered as
``gedcom_import``.
"""

from __future__ import annotations

import ast
import copy
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import ResidenceFact
from slaktbusken.model.source import Source
from slaktbusken.persistence.serialization import serialize
from slaktbusken.services.delete_service import DeleteService
from slaktbusken.services.project_service import ProjectService

pytestmark = pytest.mark.mandatory_integrity

_PACKAGE = Path(__file__).resolve().parents[2] / "slaktbusken"


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


def build_project(
    n_persons: int, n_places: int, n_sources: int, n_events: int
) -> ProjectData:
    data = ProjectData(project=ProjectMetadata(title="Test"))
    data.persons = [
        Person(
            id=f"person_{i}",
            sex="M" if i % 2 == 0 else "F",
            names=[Name(type="birth", given=f"Förnamn{i}", surname="Efternamn")],
        )
        for i in range(n_persons)
    ]
    data.places = [
        Place(id=f"place_{i}", type="parish", name=f"Plats {i}") for i in range(n_places)
    ]
    data.sources = [
        Source(
            id=f"source_{i}",
            provider="Arkiv Digital",
            source_type="church_book",
            title=f"Källa {i}",
        )
        for i in range(n_sources)
    ]
    data.events = [
        Event(
            id=f"event_{i}",
            type="birth",
            participants=[
                Participant(person_id=f"person_{i % n_persons}", role="principal")
            ],
            date=DateValue(value=f"{1700 + i}", precision="year"),
            place=PlaceRef(place_id=f"place_{i % n_places}"),
        )
        for i in range(n_events)
    ]
    return data


def make_service(data: ProjectData) -> ProjectService:
    service = ProjectService()
    service._project_data = data
    service._dirty_value = False
    return service


@dataclass(frozen=True)
class ChangePath:
    """One mutation path of an editor or service.

    ``apply_change`` changes the data (and marks it the way the owner does).
    ``apply_noop`` is the same path run so that it changes nothing, if the
    owner has such a case.
    ``covers`` names the ProjectService methods the path exercises.
    """

    name: str
    owner: str
    apply_change: Callable[[ProjectService, int], None]
    apply_noop: Optional[Callable[[ProjectService, int], None]] = None
    covers: tuple[str, ...] = ()


def _pick(items: list, k: int):
    return items[k % len(items)]


# --- Person_Editor ----------------------------------------------------


def _add_person(svc: ProjectService, k: int) -> None:
    svc.add_person(
        Person(
            id="person_new",
            sex="F",
            names=[Name(type="birth", given="Ny", surname="Person")],
        )
    )


def _add_family(svc: ProjectService, k: int) -> None:
    data = svc.data
    a = _pick(data.persons, k).id
    svc.add_family(
        Family(
            id="family_new",
            partners=[FamilyPartner(person_id=a, role="partner")],
            children=[],
        )
    )


def _session_edit_person(svc: ProjectService, k: int) -> None:
    session = svc.begin_edit_session("Personredigeraren")
    person = _pick(svc.data.persons, k)
    person.notes = person.notes + "ändrad"
    session.commit()


def _session_untouched(svc: ProjectService, k: int) -> None:
    session = svc.begin_edit_session("Personredigeraren")
    session.commit()


def _session_cancelled(svc: ProjectService, k: int) -> None:
    session = svc.begin_edit_session("Personredigeraren")
    person = _pick(svc.data.persons, k)
    person.notes = person.notes + "ändrad"
    svc.data.places.append(Place(id="place_nested", type="parish", name="Ny"))
    session.rollback()


# --- Event_Editor -----------------------------------------------------


def _add_event(svc: ProjectService, k: int) -> None:
    person = _pick(svc.data.persons, k)
    svc.add_event(
        Event(
            id="event_new",
            type="death",
            participants=[Participant(person_id=person.id, role="principal")],
        )
    )


def _update_event(svc: ProjectService, k: int) -> None:
    data = svc.data
    if not data.events:
        _add_event(svc, k)
        return
    event = copy.deepcopy(_pick(data.events, k))
    event.cause_of_death = (event.cause_of_death or "") + "x"
    svc.update_event(event)


def _delete_event(svc: ProjectService, k: int) -> None:
    data = svc.data
    if not data.events:
        _add_event(svc, k)
        return
    svc.delete_event(_pick(data.events, k).id)


def _session_edit_event(svc: ProjectService, k: int) -> None:
    data = svc.data
    session = svc.begin_edit_session("Händelseredigeraren")
    if data.events:
        event = _pick(data.events, k)
        event.cause_of_death = (event.cause_of_death or "") + "x"
    else:
        data.events.append(
            Event(
                id="event_new",
                type="death",
                participants=[
                    Participant(person_id=_pick(data.persons, k).id, role="principal")
                ],
            )
        )
    session.commit()


# --- Residence_Editor -------------------------------------------------


def _session_add_residence(svc: ProjectService, k: int) -> None:
    data = svc.data
    session = svc.begin_edit_session("Boendeeditor")
    data.residences.append(
        ResidenceFact(
            id="residence_new",
            person_id=_pick(data.persons, k).id,
            place_id=_pick(data.places, k).id,
        )
    )
    session.commit()


def _session_edit_residence(svc: ProjectService, k: int) -> None:
    data = svc.data
    session = svc.begin_edit_session("Boendeeditor")
    if not data.residences:
        data.residences.append(
            ResidenceFact(
                id="residence_new",
                person_id=_pick(data.persons, k).id,
                place_id=_pick(data.places, k).id,
            )
        )
    else:
        fact = _pick(data.residences, k)
        fact.notes = fact.notes + "x"
    session.commit()


# --- Place_Editor -----------------------------------------------------


def _add_place(svc: ProjectService, k: int) -> None:
    svc.add_place(Place(id="place_new", type="continent", name="Ny plats"))


def _save_place_edit(svc: ProjectService, k: int) -> None:
    # PlaceEditor._on_save edits the place in place; app.show_place_editor
    # connects save_requested to mark_changed.
    place = _pick(svc.data.places, k)
    place.notes = place.notes + "x"
    svc.mark_changed("Plats sparad")


def _delete_place(svc: ProjectService, k: int) -> None:
    svc.delete_place(_pick(svc.data.places, k).id)


def _delete_unknown_place(svc: ProjectService, k: int) -> None:
    svc.delete_place("place_unknown")


# --- Place_Translation_Editor ----------------------------------------


def _create_places(svc: ProjectService, k: int) -> None:
    count = 1 + k % 3
    svc.add_places(
        [Place(id=f"place_created_{i}", type="parish", name=f"Skapad {i}") for i in range(count)]
    )


def _create_no_places(svc: ProjectService, k: int) -> None:
    svc.add_places([])


# --- Source_Editor ----------------------------------------------------


def _add_source(svc: ProjectService, k: int) -> None:
    svc.add_source(
        Source(id="source_new", provider="Arkiv Digital", source_type="church_book", title="Ny")
    )


def _save_source_edit(svc: ProjectService, k: int) -> None:
    # SourceEditor._on_save edits the source in place; app.show_source_editor
    # connects save_requested to mark_changed.
    source = _pick(svc.data.sources, k)
    source.title = source.title + "x"
    svc.mark_changed("Källa sparad")


# --- Delete service ---------------------------------------------------


def _delete_person(svc: ProjectService, k: int) -> None:
    DeleteService(svc).execute_deletion(_pick(svc.data.persons, k).id)


# --- Import_Service ---------------------------------------------------


def _run_import(svc: ProjectService, text: str) -> None:
    from slaktbusken.services.import_service import ImportService
    from slaktbusken.services.validation_service import ValidationService

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "import.ged"
        path.write_text(text, encoding="utf-8")
        ImportService(ValidationService()).run(svc.data, path, Path(folder), svc)


def _import_person(svc: ProjectService, k: int) -> None:
    _run_import(
        svc,
        "\n".join(
            [
                "0 HEAD",
                "1 CHAR UTF-8",
                "0 @I1@ INDI",
                f"1 NAME Importerad{k} /Person/",
                "1 SEX F",
                "1 BIRT",
                f"2 DATE {1800 + k}",
                "0 TRLR",
            ]
        ),
    )


def _import_nothing(svc: ProjectService, k: int) -> None:
    _run_import(svc, "0 HEAD\n1 CHAR UTF-8\n0 TRLR")


CHANGE_PATH_REGISTRY: tuple[ChangePath, ...] = (
    ChangePath("person_add", "Person_Editor", _add_person, covers=("add_person",)),
    ChangePath("family_add", "Person_Editor", _add_family, covers=("add_family",)),
    ChangePath(
        "person_session_edit",
        "Person_Editor",
        _session_edit_person,
        _session_untouched,
    ),
    ChangePath(
        "person_session_cancel",
        "Person_Editor",
        _session_cancelled,
        _session_cancelled,
    ),
    ChangePath("event_add", "Event_Editor", _add_event, covers=("add_event",)),
    ChangePath("event_update", "Event_Editor", _update_event, covers=("update_event",)),
    ChangePath("event_delete", "Event_Editor", _delete_event, covers=("delete_event",)),
    ChangePath(
        "event_session_edit", "Event_Editor", _session_edit_event, _session_untouched
    ),
    ChangePath(
        "residence_session_add",
        "Residence_Editor",
        _session_add_residence,
        _session_untouched,
    ),
    ChangePath(
        "residence_session_edit",
        "Residence_Editor",
        _session_edit_residence,
        _session_untouched,
    ),
    ChangePath("place_add", "Place_Editor", _add_place, covers=("add_place",)),
    ChangePath("place_save_edit", "Place_Editor", _save_place_edit),
    ChangePath(
        "place_delete",
        "Place_Editor",
        _delete_place,
        _delete_unknown_place,
        covers=("delete_place",),
    ),
    ChangePath(
        "places_create",
        "Place_Translation_Editor",
        _create_places,
        _create_no_places,
        covers=("add_places",),
    ),
    ChangePath("source_add", "Source_Editor", _add_source, covers=("add_source",)),
    ChangePath("source_save_edit", "Source_Editor", _save_source_edit),
    ChangePath("person_delete", "Delete_Service", _delete_person),
    ChangePath(
        "gedcom_import",
        "Import_Service",
        _import_person,
        _import_nothing,
        covers=("adopt_working_copy",),
    ),
)

REQUIRED_OWNERS = frozenset(
    {
        "Person_Editor",
        "Event_Editor",
        "Residence_Editor",
        "Place_Editor",
        "Place_Translation_Editor",
        "Source_Editor",
        "Delete_Service",
        "Import_Service",
    }
)

# Public ProjectService methods that mark the project changed but are not
# editor change paths, each with the reason.
SERVICE_METHODS_NOT_IN_REGISTRY = {
    "mark_changed": "the primitive every path ends in",
    "open_project": "normalises placement links on load; the loaded state is the clean state",
    "add_media": "reached from the media editor under the same _dirty mark as add_source",
    "add_repository": "same pattern as add_source",
    "add_dna_company": "DNA editor; marked by app.show_dna_editor",
    "add_dna_profile": "DNA editor; marked by app.show_dna_editor",
    "add_dna_match": "DNA editor; marked by app.show_dna_editor",
    "add_dna_segment": "DNA editor; marked by app.show_dna_editor",
    "add_dna_cluster": "DNA editor; marked by app.show_dna_editor",
    "add_dna_triangulation": "DNA editor; marked by app.show_dna_editor",
    "add_research_note": "research objects; covered by the research tests",
}

# Every place where application or UI code references mark_changed, with the
# owner that makes the call.
KNOWN_MARK_SITES = {
    ("app.py", "_handle_connection_override"): "Person_Editor",
    ("app.py", "show_source_editor"): "Source_Editor",
    ("app.py", "show_place_editor"): "Place_Editor",
    ("app.py", "show_place_translation_editor"): "Place_Translation_Editor",
    ("app.py", "show_source_translation_editor"): "Source_Editor",
    ("app.py", "show_dna_editor"): "Dna_Editor",
    ("app.py", "_open_single_entity_editor"): "Source_Editor",
    ("app.py", "show_provider_editor"): "Provider_Editor",
    ("app.py", "_prompt_select_main_person"): "Person_Editor",
    ("ui/editors/place_editor.py", "_on_photo_add"): "Place_Editor",
    ("services/delete_service.py", "execute_deletion"): "Delete_Service",
}


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

project_shapes = st.tuples(
    st.integers(1, 4), st.integers(1, 4), st.integers(1, 3), st.integers(0, 4)
)


def _measure(path_apply, shape, k):
    data = build_project(*shape)
    svc = make_service(data)
    notifications: list[int] = []
    svc.add_merge_listener(lambda: notifications.append(1))
    before = serialize(data)
    rev_before = svc.content_revision
    path_apply(svc, k)
    after = serialize(svc.data)
    return svc, before != after, svc.content_revision - rev_before, len(notifications)


def _assert_marks_exactly_when_changed(path: ChangePath, apply, shape, k) -> None:
    svc, differs, rev_delta, notified = _measure(apply, shape, k)
    label = f"{path.owner}/{path.name}"
    if differs:
        assert rev_delta == 1, f"{label}: content_revision moved by {rev_delta}"
        assert svc.is_dirty, f"{label}: changed data but not dirty"
        assert notified == 1, f"{label}: listeners notified {notified} times"
    else:
        assert rev_delta == 0, f"{label}: no change but revision moved by {rev_delta}"
        assert not svc.is_dirty, f"{label}: no change but dirty"
        assert notified <= 1, f"{label}: listeners notified {notified} times"


# ----------------------------------------------------------------------
# Property 20
# ----------------------------------------------------------------------


# Feature: data-integrity-0-3-0, Property 20: Every mutation path marks the project changed exactly when data changed
@settings(max_examples=60, deadline=None)
@given(
    path=st.sampled_from(CHANGE_PATH_REGISTRY),
    shape=project_shapes,
    k=st.integers(0, 20),
    use_noop=st.booleans(),
)
def test_dp_property_20_every_path_marks_exactly_when_changed(
    path: ChangePath, shape, k: int, use_noop: bool
) -> None:
    """**Validates: Requirements 3.1, 4.1, 5.1, 5.2, 17.1, 18.2, 18.3**"""
    apply = path.apply_noop if use_noop and path.apply_noop else path.apply_change
    _assert_marks_exactly_when_changed(path, apply, shape, k)


def test_every_registered_path_marks_exactly_when_changed() -> None:
    """Every path, in its changing and its no-op form, on a fixed project."""
    for path in CHANGE_PATH_REGISTRY:
        for apply in (path.apply_change, path.apply_noop):
            if apply is None:
                continue
            _assert_marks_exactly_when_changed(path, apply, (3, 2, 2, 2), 1)


def test_changing_paths_actually_change_data() -> None:
    """Guards the registry: a changing path that changes nothing proves nothing."""
    for path in CHANGE_PATH_REGISTRY:
        if path.name == "person_session_cancel":
            continue
        _svc, differs, rev_delta, _n = _measure(path.apply_change, (3, 2, 2, 2), 1)
        assert differs and rev_delta == 1, path.name


# ----------------------------------------------------------------------
# Registry coverage
# ----------------------------------------------------------------------


def _marking_service_methods() -> set[str]:
    tree = ast.parse(
        (_PACKAGE / "services" / "project_service.py").read_text(encoding="utf-8-sig")
    )
    found: set[str] = set()
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        if cls.name != "ProjectService":
            continue
        for fn in cls.body:
            if not isinstance(fn, ast.FunctionDef) or fn.name.startswith("_"):
                continue
            for node in ast.walk(fn):
                is_dirty = (
                    isinstance(node, ast.Assign)
                    and any(
                        isinstance(t, ast.Attribute)
                        and t.attr == "_dirty"
                        and isinstance(t.value, ast.Name)
                        and t.value.id == "self"
                        for t in node.targets
                    )
                )
                is_mark = (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "mark_changed"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "self"
                )
                if is_dirty or is_mark:
                    found.add(fn.name)
    return found


def _mark_sites() -> set[tuple[str, str]]:
    sites: set[tuple[str, str]] = set()
    candidates = [_PACKAGE / "app.py", _PACKAGE / "services" / "delete_service.py"]
    candidates += sorted((_PACKAGE / "ui").rglob("*.py"))
    for path in candidates:
        rel = path.relative_to(_PACKAGE).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))

        def walk(node: ast.AST, function: str) -> None:
            for child in ast.iter_child_nodes(node):
                name = (
                    child.name
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    else function
                )
                if isinstance(child, ast.Attribute) and child.attr == "mark_changed":
                    sites.add((rel, name))
                walk(child, name)

        walk(tree, "<module>")
    return sites


def test_change_path_registry_covers_known_paths() -> None:
    owners = {p.owner for p in CHANGE_PATH_REGISTRY}
    assert REQUIRED_OWNERS <= owners, f"owners missing: {REQUIRED_OWNERS - owners}"
    names = [p.name for p in CHANGE_PATH_REGISTRY]
    assert len(names) == len(set(names)), "duplicate registry names"

    covered = {m for p in CHANGE_PATH_REGISTRY for m in p.covers}
    marking = _marking_service_methods()
    missing = marking - covered - set(SERVICE_METHODS_NOT_IN_REGISTRY)
    assert not missing, f"ProjectService methods without a registered path: {sorted(missing)}"
    unknown = covered - marking
    assert not unknown, f"registry names methods that do not mark: {sorted(unknown)}"
    assert all(SERVICE_METHODS_NOT_IN_REGISTRY.values())

    sites = _mark_sites()
    assert sites == set(KNOWN_MARK_SITES), (
        "mark_changed call sites changed; register the new path.\n"
        f"new: {sorted(sites - set(KNOWN_MARK_SITES))}\n"
        f"gone: {sorted(set(KNOWN_MARK_SITES) - sites)}"
    )


# ----------------------------------------------------------------------
# Place delete and place creation (Requirements 4.3, 5.3)
# ----------------------------------------------------------------------


def _place_editor(project: ProjectData, svc: Optional[ProjectService], place: Place):
    from slaktbusken.ui.editors.place_editor import PlaceEditor

    with patch.object(PlaceEditor, "__init__", lambda self, *a, **kw: None):
        editor = PlaceEditor.__new__(PlaceEditor)
    editor._project_data = project
    editor._project_service = svc
    editor._editing_place = place
    item = MagicMock()
    item.data.return_value = place.id
    editor._ui = MagicMock()
    editor._ui.place_list.currentItem.return_value = item
    editor._find_place_by_id = MagicMock(return_value=place)
    editor._find_referencing_events = MagicMock(return_value=[])
    editor._update_status = MagicMock()
    editor._clear_form = MagicMock()
    editor._refresh_place_list = MagicMock()
    editor._clear_status = MagicMock()
    return editor


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_place_delete_marks_dirty_and_bumps_revision(qapp) -> None:
    from PySide6.QtWidgets import QMessageBox

    data = build_project(2, 2, 1, 0)
    svc = make_service(data)
    notifications: list[int] = []
    svc.add_merge_listener(lambda: notifications.append(1))
    editor = _place_editor(data, svc, data.places[0])
    revision = svc.content_revision

    with patch.object(
        QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
    ):
        editor._on_delete_place()

    assert [p.id for p in data.places] == ["place_1"]
    assert svc.is_dirty
    assert svc.content_revision == revision + 1
    assert len(notifications) == 1


def test_place_delete_refused_does_not_mark_dirty(qapp) -> None:
    from PySide6.QtWidgets import QMessageBox

    data = build_project(2, 2, 1, 0)
    data.residences = [
        ResidenceFact(id="res_1", person_id="person_0", place_id="place_0")
    ]
    svc = make_service(data)
    editor = _place_editor(data, svc, data.places[0])
    revision = svc.content_revision
    before = serialize(data)

    with patch.object(
        QMessageBox, "warning", return_value=QMessageBox.StandardButton.Ok
    ):
        editor._on_delete_place()

    assert serialize(data) == before
    assert not svc.is_dirty
    assert svc.content_revision == revision


def test_create_places_marks_dirty_once() -> None:
    data = build_project(1, 1, 1, 0)
    svc = make_service(data)
    notifications: list[int] = []
    svc.add_merge_listener(lambda: notifications.append(1))
    revision = svc.content_revision

    added = svc.add_places(
        [Place(id=f"place_c{i}", type="parish", name=f"C{i}") for i in range(3)]
    )

    assert added == 3
    assert len(data.places) == 4
    assert svc.is_dirty
    assert svc.content_revision == revision + 1
    assert len(notifications) == 1


def test_create_places_none_created_stays_clean() -> None:
    data = build_project(1, 1, 1, 0)
    svc = make_service(data)
    revision = svc.content_revision

    assert svc.add_places([]) == 0

    assert not svc.is_dirty
    assert svc.content_revision == revision


def test_mark_changed_sets_dirty_bumps_revision_notifies_once() -> None:
    svc = make_service(build_project(1, 1, 1, 0))
    notifications: list[int] = []
    svc.add_merge_listener(lambda: notifications.append(1))
    revision = svc.revision
    content_revision = svc.content_revision

    svc.mark_changed("test")

    assert svc.is_dirty
    assert svc.revision == revision + 1
    assert svc.content_revision == content_revision + 1
    assert len(notifications) == 1


def test_service_methods_for_place_delete_and_create_call_mark_changed_once() -> None:
    data = build_project(1, 2, 1, 0)
    svc = make_service(data)

    with patch.object(svc, "mark_changed", wraps=svc.mark_changed) as spy:
        svc.delete_place("place_0")
        assert spy.call_count == 1
        svc.delete_place("place_unknown")
        assert spy.call_count == 1  # unknown id marks nothing
        svc.add_places([Place(id="place_x", type="parish", name="X")])
        assert spy.call_count == 2
        svc.add_places([])
        assert spy.call_count == 2


def test_source_editor_add_media_signals_change(qapp, tmp_path) -> None:
    """Media added before Spara is in the project data, so the editor signals it.

    Standalone owners (app.show_source_editor) connect media_added to
    mark_changed; inside a Person_Editor session rollback covers it.
    """
    from PySide6.QtWidgets import QFileDialog

    from slaktbusken.ui.editors.source_editor import SourceEditor

    picture = tmp_path / "bild.jpg"
    picture.write_bytes(b"jpg")
    data = build_project(1, 1, 1, 0)
    editor = SourceEditor(project_data=data, project_folder=tmp_path / "projekt")
    (tmp_path / "projekt").mkdir()
    signals: list[int] = []
    editor.media_added.connect(lambda: signals.append(1))
    with patch.object(QFileDialog, "getOpenFileName", return_value=(str(picture), "")):
        editor._on_add_media()
    assert len(data.media) == 1
    assert signals == [1]
