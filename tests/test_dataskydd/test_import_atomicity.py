"""A GEDCOM import is all-or-nothing (Requirements 3.1 to 3.6, 18.1, 18.2, 20.1 to 20.5, 20.12 to 20.15).

Property 18: a failed or cancelled import changes nothing.
Property 19: a successful import marks the project changed exactly once, and a
no-op import not at all.

Every test imports through ``ImportService.run`` into a real project on disk,
so the Translation_Files, the Pending_Translation and the Translation_Base are
the real ones.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 18.1, 18.2, 20.1, 20.2,
20.3, 20.4, 20.5, 20.12, 20.13, 20.14, 20.15**
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from hypothesis import HealthCheck, given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import slaktbusken.app as app_module  # noqa: E402
from slaktbusken.gedcom.importer import GEDCOMImporter  # noqa: E402
from slaktbusken.model.person import Name, Person  # noqa: E402
from slaktbusken.persistence.serialization import serialize  # noqa: E402
from slaktbusken.persistence.translation_io import (  # noqa: E402
    dumps_persons,
    dumps_places,
    dumps_sources,
    read_all,
)
from slaktbusken.services.edit_session import MSG_IMPORT_SAVE_UNFINISHED  # noqa: E402
from slaktbusken.services.id_registry import issue_person_id  # noqa: E402
from slaktbusken.services.import_service import (  # noqa: E402
    MSG_TRANSLATION_CHANGED,
    ImportError as ImportServiceError,
    ImportService,
)
from slaktbusken.services.project_service import ProjectService  # noqa: E402
from slaktbusken.services.validation_service import ValidationService  # noqa: E402
from slaktbusken.ui.merge import recovery_dialogs  # noqa: E402
from slaktbusken.ui.merge.recovery_dialogs import MSG_PENDING_TRANSLATION  # noqa: E402

pytestmark = pytest.mark.mandatory_integrity

_PROPERTY_SETTINGS = dict(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)

_TRANSLATION_NAMES = ("persons.json", "places.json", "sources.json")


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class _InjectedFailure(BaseException):
    """Raised by a test inside the importer. A ``BaseException`` so that the
    importer's own per-record ``except Exception`` handlers cannot swallow it;
    it stands for any error or user cancellation that escapes the importer."""


class World:
    """A real project on disk and the service that imports into it."""

    def __init__(self, root: Path, validation: Optional[ValidationService] = None) -> None:
        self.root = root
        self.ps = ProjectService()
        self.ps.create_project("Projekt", root)
        self.folder = self.ps.project_path.parent
        self.translation = self.folder / "translation"
        self.service = ImportService(validation or ValidationService())
        self._n = 0

    @property
    def data(self):
        return self.ps.data

    def write(self, text: str) -> Path:
        self._n += 1
        path = self.folder / f"import_{self._n}.ged"
        path.write_text(text, encoding="utf-8")
        return path

    def run(self, text: str):
        return self.service.run(self.ps.data, self.write(text), self.folder, self.ps)

    def translation_bytes(self) -> dict[str, Optional[bytes]]:
        return {
            n: (self.translation / n).read_bytes() if (self.translation / n).exists() else None
            for n in _TRANSLATION_NAMES
        }

    def effective_translation(self) -> tuple[bytes, bytes, bytes]:
        pending = self.ps.pending_translation
        data = pending.data if pending is not None else read_all(self.translation)
        return (
            dumps_persons(data.persons, data.families, data.person_aliases),
            dumps_places(data.places),
            dumps_sources(data.sources),
        )

    def snapshot(self) -> tuple:
        pending = self.ps.pending_translation
        return (
            serialize(self.ps.data),
            None
            if pending is None
            else (
                dumps_persons(
                    pending.data.persons, pending.data.families, pending.data.person_aliases
                ),
                dumps_places(pending.data.places),
                dumps_sources(pending.data.sources),
                dict(pending.base),
            ),
            self.translation_bytes(),
            self.ps.is_dirty,
            self.ps.content_revision,
            self.ps.revision,
        )


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def person_lines(
    n: int,
    given: str = "Anna",
    surname: str = "Svensson",
    birth: str = "1900",
    place: str = "Testby, Sverige",
    resi: Optional[str] = "Boplats, Sverige",
) -> list[str]:
    lines = [f"0 @I{n}@ INDI", f"1 NAME {given} /{surname}/", "1 SEX F"]
    if birth:
        lines += ["1 BIRT", f"2 DATE {birth}", f"2 PLAC {place}"]
    if resi:
        lines += ["1 RESI", "2 DATE 1910", f"2 PLAC {resi}"]
    return lines


def ged(*persons: list[str]) -> str:
    lines = ["0 HEAD", "1 CHAR UTF-8"]
    for p in persons:
        lines += p
    lines.append("0 TRLR")
    return "\n".join(lines)


ONE = ged(person_lines(1))
TWO = ged(person_lines(1), person_lines(2, "Erik", "Olsson", "1905", "Annanby, Sverige", "Hemma, Sverige"))
NO_HEAD = "0 @I1@ INDI\n1 NAME Anna /Svensson/\n0 TRLR"


# ---------------------------------------------------------------------------
# Generators and failure points
# ---------------------------------------------------------------------------

_GIVEN = ["Anna", "Erik", "Karin", "Lars", "Maja"]
_FRESH_GIVEN = ["Zacharias", "Ylva", "Xenia"]
_SURNAME = ["Svensson", "Olsson", "Berg"]
_PLACES = ["Testby, Sverige", "Annanby, Sverige", "Bergsby, Sverige"]
_YEARS = ["1880", "1900", "1925"]


@st.composite
def gedcom_files(draw, min_persons: int = 1, fresh: bool = False) -> str:
    """A GEDCOM file whose persons all have a birth and a residence.

    ``fresh`` gives the persons other xrefs and names than an ordinary file, so
    importing one after the other creates every person of the second file.
    """
    n = draw(st.integers(min_persons, 3))
    persons = []
    for i in range(1, n + 1):
        persons.append(
            person_lines(
                i + 10 if fresh else i,
                draw(st.sampled_from(_FRESH_GIVEN if fresh else _GIVEN)),
                draw(st.sampled_from(_SURNAME)),
                draw(st.sampled_from(_YEARS)),
                draw(st.sampled_from(_PLACES)),
                draw(st.sampled_from(_PLACES)),
            )
        )
    return ged(*persons)


BASE_STATES = ("empty", "saved", "pending")
FAILURE_POINTS = ("parse", "event", "residence", "validation", "translation_changed", "cancel")


def prepare(world: World, state: str, first: str) -> None:
    """Bring the project to a base state with the *first* file imported (or not)."""
    if state == "empty":
        return
    world.run(first)
    if state == "saved":
        world.ps.save_project()


class _ValidationHook(ValidationService):
    """Validation service that runs a callback, as a stand-in for a later pipeline step."""

    def __init__(self, hook=None) -> None:
        super().__init__()
        self.hook = hook

    def validate_project(self, data):
        if self.hook is not None:
            self.hook()
        return super().validate_project(data)


def run_with_failure(world: World, point: str, text: str) -> None:
    """Run an import that fails at *point*; ``text`` has events and residences."""
    service = world.service
    with ExitStack() as stack:
        if point == "parse":
            text = NO_HEAD
        elif point == "event":
            original = GEDCOMImporter._create_event
            calls = {"n": 0}

            def failing_create_event(self, *a, **kw):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise _InjectedFailure()
                return original(self, *a, **kw)

            stack.enter_context(patch.object(GEDCOMImporter, "_create_event", failing_create_event))
        elif point in ("residence", "cancel"):
            original_add = GEDCOMImporter._add_residence

            def failing_add_residence(self, *a, **kw):
                if point == "cancel":
                    # Cancelled after the residence was added to the working copy.
                    original_add(self, *a, **kw)
                raise _InjectedFailure()

            stack.enter_context(patch.object(GEDCOMImporter, "_add_residence", failing_add_residence))
        elif point == "validation":
            def failing_validation(data):
                raise RuntimeError("valideringen misslyckades")

            stack.enter_context(
                patch.object(service._validation_service, "validate_project", failing_validation)
            )
        elif point == "translation_changed":
            def touch_translation_file():
                world.translation.mkdir(parents=True, exist_ok=True)
                (world.translation / "places.json").write_text(
                    '{"version": "1.0", "mappings": [], "andrad": true}', encoding="utf-8"
                )

            service._validation_service = _ValidationHook(touch_translation_file)
        try:
            world.run(text)
        except (ImportServiceError, RuntimeError, _InjectedFailure):
            return
    raise AssertionError(f"import with failure point {point!r} did not fail")


# ---------------------------------------------------------------------------
# Property 18
# ---------------------------------------------------------------------------


# Feature: data-integrity-0-3-0, Property 18: A failed or cancelled import changes nothing
@settings(**_PROPERTY_SETTINGS)
@given(
    state=st.sampled_from(BASE_STATES),
    point=st.sampled_from(FAILURE_POINTS),
    first=gedcom_files(),
    second=gedcom_files(min_persons=2, fresh=True),
)
def test_dp_property_18_failed_or_cancelled_import_changes_nothing(
    state: str, point: str, first: str, second: str
) -> None:
    """**Validates: Requirements 20.1, 20.2, 20.5**"""
    root = Path(tempfile.mkdtemp())
    try:
        world = World(root)
        prepare(world, state, first)
        before = world.snapshot()
        if point == "translation_changed" and state == "pending":
            # With a Pending_Translation the files are not read, so there is no
            # base to compare; that point does not apply.
            return
        run_with_failure(world, point, second)
        after = world.snapshot()
        if point == "translation_changed":
            # The test itself rewrote the places file; everything else is unchanged.
            before = before[:2] + (None,) + before[3:]
            after = after[:2] + (None,) + after[3:]
        assert after == before, f"state {state!r}, failure point {point!r}"
        assert not world.ps.import_in_progress
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# Property 19
# ---------------------------------------------------------------------------


# Feature: data-integrity-0-3-0, Property 19: A successful import marks the project changed exactly once, and a no-op import not at all
@settings(**_PROPERTY_SETTINGS)
@given(
    state=st.sampled_from(BASE_STATES),
    first=gedcom_files(),
    second=gedcom_files(),
    repeat_first=st.booleans(),
)
def test_dp_property_19_success_marks_once_noop_not_at_all(
    state: str, first: str, second: str, repeat_first: bool
) -> None:
    """**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 20.3, 20.4**"""
    root = Path(tempfile.mkdtemp())
    try:
        world = World(root)
        prepare(world, state, first)
        text = first if (repeat_first and state != "empty") else second
        notifications: list[int] = []
        world.ps.add_merge_listener(lambda: notifications.append(1))
        before_project = serialize(world.ps.data)
        before_translation = world.effective_translation()
        before_dirty = world.ps.is_dirty
        before_revision = world.ps.content_revision
        before_pending = world.ps.pending_translation

        world.run(text)

        changed = (
            serialize(world.ps.data) != before_project
            or world.effective_translation() != before_translation
        )
        if changed:
            assert world.ps.content_revision == before_revision + 1
            assert world.ps.is_dirty
            assert world.ps.pending_translation is not None
            assert len(notifications) == 1
        else:
            assert world.ps.content_revision == before_revision
            assert world.ps.is_dirty == before_dirty
            assert world.ps.pending_translation is before_pending
            assert notifications == []
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# Marking (Requirements 3.1 to 3.6)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def boxes(monkeypatch):
    box = MagicMock()
    monkeypatch.setattr(app_module, "QMessageBox", box)
    monkeypatch.setattr(app_module.QApplication, "processEvents", staticmethod(lambda: None))
    monkeypatch.setattr(recovery_dialogs, "QMessageBox", box)
    return box


def _fake_app(world: World, **extra):
    return SimpleNamespace(
        main_window=MagicMock(),
        project_service=world.ps,
        import_service=world.service,
        _update_status=MagicMock(),
        _update_diagram_panel=MagicMock(),
        _write_import_log=MagicMock(return_value=None),
        _prompt_select_main_person=MagicMock(),
        **extra,
    )


def test_import_marks_dirty_and_bumps_revision(qapp, boxes, monkeypatch, world: World) -> None:
    """Headless reproduction of B2: an import through the application marks the project changed."""
    path = world.write(TWO)
    dialog = MagicMock()
    dialog.getOpenFileName.return_value = (str(path), "")
    monkeypatch.setattr(app_module, "QFileDialog", dialog)
    fake = _fake_app(world)
    revision = world.ps.content_revision
    assert not world.ps.is_dirty

    app_module.Application.import_gedcom(fake)

    assert len(world.data.persons) == 2
    assert world.ps.is_dirty
    assert world.ps.content_revision == revision + 1
    boxes.critical.assert_not_called()
    fake._update_status.assert_called()


def test_noop_import_does_not_mark_dirty(world: World) -> None:
    world.run(ONE)
    world.ps.save_project()
    revision = world.ps.content_revision
    assert not world.ps.is_dirty

    world.run(ONE)

    assert not world.ps.is_dirty
    assert world.ps.content_revision == revision
    assert world.ps.pending_translation is None


def test_import_notifies_listeners_once(world: World) -> None:
    notifications: list[int] = []
    world.ps.add_merge_listener(lambda: notifications.append(1))

    world.run(TWO)

    assert len(notifications) == 1


def test_close_after_import_prompts_to_save(qapp, boxes) -> None:
    root = Path(tempfile.mkdtemp())
    try:
        world = World(root)
        world.run(ONE)
        boxes.question.return_value = boxes.StandardButton.Cancel
        fake = _fake_app(world)
        fake._confirm_discard_changes = lambda: app_module.Application._confirm_discard_changes(fake)
        fake.save_project = MagicMock()

        app_module.Application.close_project(fake)

        boxes.question.assert_called_once()
        assert boxes.question.call_args.args[1] == "Osparade ändringar"
        assert world.ps.pending_translation is not None  # cancelled: still open
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_translation_only_change_marks_dirty(world: World) -> None:
    """A staged translation that differs from the effective one is a change on its own."""
    world.run(ONE)
    world.ps.save_project()
    persons_file = world.translation / "persons.json"
    document = json.loads(persons_file.read_text(encoding="utf-8"))
    for mapping in document["person_mappings"]:
        mapping.pop("fingerprint", None)
    persons_file.write_text(json.dumps(document), encoding="utf-8")
    project_before = serialize(world.data)
    revision = world.ps.content_revision

    world.run(ONE)

    assert serialize(world.data) == project_before
    assert world.ps.is_dirty
    assert world.ps.content_revision == revision + 1
    assert world.ps.pending_translation is not None


# ---------------------------------------------------------------------------
# Failure and cancellation (Requirements 20.1, 20.2, 20.5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("point", ["parse", "event", "residence", "validation"])
def test_failed_import_leaves_project_unchanged(world: World, point: str) -> None:
    world.run(ONE)
    before = world.snapshot()

    run_with_failure(world, point, TWO)

    assert world.snapshot() == before
    assert not world.ps.import_in_progress


@pytest.mark.parametrize("point", ["parse", "event", "residence", "validation"])
def test_failed_import_leaves_translation_files_byte_identical(world: World, point: str) -> None:
    world.run(ONE)
    world.ps.save_project()
    files = world.translation_bytes()
    assert all(content is not None for content in files.values())

    run_with_failure(world, point, TWO)

    assert world.translation_bytes() == files


def test_cancelled_import_leaves_project_unchanged(qapp, boxes, monkeypatch, world: World) -> None:
    world.run(ONE)
    before = world.snapshot()

    # The user cancels the file dialog: the import service is never called.
    dialog = MagicMock()
    dialog.getOpenFileName.return_value = ("", "")
    monkeypatch.setattr(app_module, "QFileDialog", dialog)
    fake = _fake_app(world)
    fake.import_service = MagicMock()
    app_module.Application.import_gedcom(fake)
    fake.import_service.run.assert_not_called()
    assert world.snapshot() == before

    # The import is cancelled while it runs.
    run_with_failure(world, "cancel", TWO)
    assert world.snapshot() == before


def test_import_writes_no_translation_file_before_save(world: World) -> None:
    world.translation.mkdir(parents=True, exist_ok=True)
    before = world.translation_bytes()

    world.run(TWO)

    assert world.translation_bytes() == before
    assert world.ps.pending_translation is not None
    assert world.ps.pending_translation.data.persons

    world.ps.save_project()

    after = world.translation_bytes()
    assert all(content is not None for content in after.values())
    assert world.ps.pending_translation is None


# ---------------------------------------------------------------------------
# Adoption (Requirements 20.3, 20.4)
# ---------------------------------------------------------------------------


def test_successful_import_adopts_once(world: World) -> None:
    instance = world.data
    with patch.object(
        world.ps, "adopt_working_copy", wraps=world.ps.adopt_working_copy
    ) as adopt, patch.object(world.ps, "mark_changed", wraps=world.ps.mark_changed) as mark:
        world.run(TWO)

    assert adopt.call_count == 1
    assert mark.call_count == 1
    assert world.ps.data is instance
    assert len(instance.persons) == 2


def test_noop_import_adopts_nothing(world: World) -> None:
    world.run(ONE)
    world.ps.save_project()
    before = world.snapshot()
    with patch.object(world.ps, "adopt_working_copy") as adopt:
        world.run(ONE)

    adopt.assert_not_called()
    assert world.snapshot() == before


# ---------------------------------------------------------------------------
# Refusals (Requirement 20.13)
# ---------------------------------------------------------------------------


def test_import_refused_with_unsaved_editor(world: World) -> None:
    editor = SimpleNamespace(editor_title="Personredigeraren")
    registry = SimpleNamespace(unsaved_editors=lambda: [editor])
    world.ps.set_editor_registry(registry)
    before = world.snapshot()

    with pytest.raises(ImportServiceError) as excinfo:
        world.run(ONE)

    assert "Personredigeraren" in excinfo.value.message
    assert world.snapshot() == before


def test_import_refused_with_active_edit_session(world: World) -> None:
    session = world.ps.begin_edit_session("Händelseredigeraren")
    try:
        with pytest.raises(ImportServiceError) as excinfo:
            world.run(ONE)
        assert "Händelseredigeraren" in excinfo.value.message
    finally:
        session.rollback()
    assert world.data.persons == []


def test_import_refused_while_import_save_unfinished(world: World) -> None:
    world.ps._import_save_unfinished = True
    with pytest.raises(ImportServiceError) as excinfo:
        world.run(ONE)
    assert excinfo.value.message == MSG_IMPORT_SAVE_UNFINISHED


# ---------------------------------------------------------------------------
# Translation_Base and the pending translation (Requirements 20.1, 20.14, 20.15)
# ---------------------------------------------------------------------------


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "absent"


def test_import_records_translation_base(world: World) -> None:
    world.translation.mkdir(parents=True, exist_ok=True)
    (world.translation / "places.json").write_text(
        '{"version": "1.0", "mappings": []}', encoding="utf-8"
    )
    (world.translation / "sources.json").unlink(missing_ok=True)
    expected = {f"translation/{n}": _digest(world.translation / n) for n in _TRANSLATION_NAMES}
    assert expected["translation/sources.json"] == "absent"
    assert expected["translation/places.json"] != "absent"

    world.run(ONE)

    pending = world.ps.pending_translation
    assert pending is not None
    assert pending.base == expected


def test_translation_file_changed_during_import_aborts_import(world: World) -> None:
    world.run(ONE)
    world.ps.save_project()
    before = world.snapshot()

    def change_file() -> None:
        (world.translation / "sources.json").write_text(
            '{"version": "1.0", "mappings": []}', encoding="utf-8"
        )

    world.service._validation_service = _ValidationHook(change_file)
    changed_bytes = None
    with pytest.raises(ImportServiceError) as excinfo:
        world.run(TWO)
    changed_bytes = (world.translation / "sources.json").read_bytes()

    assert excinfo.value.message == MSG_TRANSLATION_CHANGED
    after = world.snapshot()
    # Only the file the test itself rewrote differs.
    assert after[:2] == before[:2]
    assert after[3:] == before[3:]
    assert after[2]["sources.json"] == changed_bytes
    assert after[2]["persons.json"] == before[2]["persons.json"]
    assert after[2]["places.json"] == before[2]["places.json"]


def test_second_import_uses_pending_translation(world: World) -> None:
    first = ged(person_lines(1))
    second = ged(person_lines(1, resi=None), person_lines(2, "Erik", "Olsson", "1905", "Annanby, Sverige", None))
    world.run(first)
    first_pending = world.ps.pending_translation
    assert first_pending is not None
    base = dict(first_pending.base)
    first_mapping = {m.gedcom_id: m.app_id for m in first_pending.data.persons}

    world.run(second)

    pending = world.ps.pending_translation
    assert pending is not None
    assert pending.base == base
    mappings = {m.gedcom_id: m.app_id for m in pending.data.persons}
    # @I1@ was found through the pending mapping, not created a second time.
    assert mappings["@I1@"] == first_mapping["@I1@"]
    assert set(mappings) == {"@I1@", "@I2@"}
    assert len(world.data.persons) == 2

    world.ps.save_project()

    saved = {m.gedcom_id: m.app_id for m in read_all(world.translation).persons}
    assert saved == mappings
    assert world.ps.pending_translation is None


def test_close_without_save_discards_pending_translation(world: World) -> None:
    world.translation.mkdir(parents=True, exist_ok=True)
    files = world.translation_bytes()
    world.run(TWO)
    assert world.ps.pending_translation is not None
    project_file = world.ps.project_path

    world.ps.close_project()

    assert world.ps.pending_translation is None
    assert world.translation_bytes() == files

    other = ProjectService()
    other.open_project(project_file)
    assert other.pending_translation is None
    assert other.data.persons == []

    # Opening another project without saving discards it as well.
    again = World(world.root / "again")
    again.run(ONE)
    assert again.ps.pending_translation is not None
    again.ps.open_project(project_file)
    assert again.ps.pending_translation is None


@pytest.mark.parametrize("which", ["show_place_translation_editor", "show_source_translation_editor"])
def test_translation_editors_refuse_while_pending(qapp, boxes, monkeypatch, world: World, which: str) -> None:
    world.run(ONE)
    assert world.ps.pending_translation is not None
    fake = _fake_app(world)
    fake._refuse_translation_editor = lambda title: app_module.Application._refuse_translation_editor(
        fake, title
    )
    dialog = MagicMock()
    monkeypatch.setattr(app_module, "QDialog", dialog)

    getattr(app_module.Application, which)(fake)

    assert boxes.warning.call_args.args[2] == MSG_PENDING_TRANSLATION
    dialog.assert_not_called()

    # After the save the editors are allowed again.
    world.ps.save_project()
    assert recovery_dialogs.translation_edit_refusal(world.ps) == ""


def test_unsaved_import_then_new_person_never_aliases_mapping(world: World) -> None:
    """An import that was never saved leaves no mapping behind that could alias a new person."""
    world.run(ONE)
    imported_id = world.data.persons[0].id
    project_file = world.ps.project_path
    world.ps.close_project()  # discard without saving

    reopened = ProjectService()
    reopened.open_project(project_file)
    data = reopened.data
    assert data.persons == []
    # The user creates a person; the id generator may hand out the id the lost import used.
    new_id = issue_person_id(data, set())
    manual = Person(id=new_id, sex="M", names=[Name(type="birth", given="Manuell", surname="Person")])
    reopened.add_person(manual)
    reopened.save_project()
    assert new_id == imported_id  # the situation the old behaviour aliased
    assert read_all(project_file.parent / "translation").persons == []

    service = ImportService(ValidationService())
    path = world.write(ONE)
    service.run(data, path, project_file.parent, reopened)

    kept = next(p for p in data.persons if p.id == new_id)
    assert kept.names[0].given == "Manuell"
    assert len(data.persons) == 2
    pending = reopened.pending_translation
    assert pending is not None
    mapped = [m.app_id for m in pending.data.persons]
    assert len(mapped) == 1 and mapped[0] != new_id
