"""Tests for the revision counters and saved state of ProjectService.

Mandatory group c (failed merges); required, never skipped.
"""

from pathlib import Path

import pytest

from slaktbusken.services.project_service import ProjectService

pytestmark = pytest.mark.mandatory_integrity


@pytest.fixture
def service(tmp_path: Path) -> ProjectService:
    svc = ProjectService()
    svc.create_project("Test", tmp_path)
    return svc


@pytest.fixture
def notifications(service: ProjectService) -> list[int]:
    calls: list[int] = []
    service.add_merge_listener(lambda: calls.append(1))
    return calls


def test_dirty_true_increments_both_counters_and_notifies_once(
    service: ProjectService, notifications: list[int]
) -> None:
    rev, content = service.revision, service.content_revision
    service._dirty = True
    assert service.revision == rev + 1
    assert service.content_revision == content + 1
    assert len(notifications) == 1
    assert service.is_dirty


def test_dirty_false_increments_nothing(
    service: ProjectService, notifications: list[int]
) -> None:
    service._dirty = True
    notifications.clear()
    rev, content = service.revision, service.content_revision
    service._dirty = False
    assert service.revision == rev
    assert service.content_revision == content
    assert notifications == []


def test_save_increments_revision_only(
    service: ProjectService, notifications: list[int]
) -> None:
    service._dirty = True
    notifications.clear()
    rev, content = service.revision, service.content_revision
    service.save_project()
    assert service.revision == rev + 1
    assert service.content_revision == content
    assert service.clean_content_revision == content
    assert len(notifications) == 1
    assert service.is_saved_state()


def test_is_saved_state_false_for_mutation_that_forgot_flag(
    service: ProjectService,
) -> None:
    assert service.is_saved_state()
    # A mutation that raised the content revision but never set the flag.
    service._record_change(content=True, notify=False)
    assert not service.is_dirty
    assert not service.is_saved_state()


def test_adopt_committed_state_clears_dirty_and_counts_once(
    service: ProjectService, notifications: list[int]
) -> None:
    service._dirty = True
    notifications.clear()
    rev, content = service.revision, service.content_revision
    service.adopt_committed_state()
    assert not service.is_dirty
    assert service.revision == rev + 1
    assert service.content_revision == content + 1
    assert service.clean_content_revision == service.content_revision
    assert len(notifications) == 1
    assert service.is_saved_state()


# ---------------------------------------------------------------------------
# Editor registry (task 5.20)
# ---------------------------------------------------------------------------

import gc
import importlib
import inspect
import pkgutil

from PySide6.QtWidgets import QWidget

import slaktbusken.ui.editors as editors_package
from slaktbusken.services.editor_registry import (
    EditorRegistry,
    ResolutionResult,
)
from slaktbusken.ui.editors.registry_participation import (
    EditorRegistryParticipant,
)


class FakeEditor:
    """Counts every call; the registry may only ask has_unsaved_changes."""

    def __init__(self, title: str, unsaved: bool) -> None:
        self.editor_title = title
        self.unsaved = unsaved
        self.asked = 0
        self.resolutions = 0
        self.saves = 0
        self.discards = 0

    def has_unsaved_changes(self) -> bool:
        self.asked += 1
        return self.unsaved

    def request_resolution(self) -> ResolutionResult:
        self.resolutions += 1
        return ResolutionResult.SAVED

    def save(self) -> None:
        self.saves += 1

    def discard(self) -> None:
        self.discards += 1


def test_registry_keeps_registration_order_and_ignores_duplicates() -> None:
    registry = EditorRegistry()
    a, b, c = (FakeEditor(n, True) for n in "abc")
    for editor in (b, a, c, a):
        registry.register(editor)
    assert registry.unsaved_editors() == [b, a, c]
    registry.unregister(a)
    assert registry.unsaved_editors() == [b, c]


def test_registry_holds_editors_weakly() -> None:
    registry = EditorRegistry()
    kept = FakeEditor("kept", True)
    dropped = FakeEditor("dropped", True)
    registry.register(kept)
    registry.register(dropped)
    del dropped
    gc.collect()
    assert registry.unsaved_editors() == [kept]


def test_unsaved_editors_only_asks_and_never_saves_or_discards() -> None:
    registry = EditorRegistry()
    dirty = FakeEditor("dirty", True)
    clean = FakeEditor("clean", False)
    registry.register(dirty)
    registry.register(clean)
    assert registry.unsaved_editors() == [dirty]
    assert dirty.asked == 1 and clean.asked == 1
    for editor in (dirty, clean):
        assert editor.saves == 0
        assert editor.discards == 0
        assert editor.resolutions == 0


# Classes in slaktbusken/ui/editors that are QWidget subclasses but do not use
# the registry-participation mixin, each with the reason why.
_EXEMPT_QWIDGETS = {
    "slaktbusken.ui.editors.place_translation_editor.CreatePlaceDialog": (
        "Transient modal QDialog opened from PlaceTranslationEditor; it is "
        "closed (accept/reject) before control returns, holds no project "
        "state of its own and cannot stay open with unsaved changes."
    ),
}


def _editor_widget_classes() -> list[type]:
    classes: list[type] = []
    for info in pkgutil.iter_modules(editors_package.__path__):
        module = importlib.import_module(f"{editors_package.__name__}.{info.name}")
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ == module.__name__ and issubclass(cls, QWidget):
                classes.append(cls)
    return classes


def test_every_editor_widget_is_registered_or_exempted_with_reason() -> None:
    classes = _editor_widget_classes()
    assert classes, "no QWidget subclasses found in slaktbusken/ui/editors"
    unaccounted = []
    for cls in classes:
        qualified = f"{cls.__module__}.{cls.__qualname__}"
        if issubclass(cls, EditorRegistryParticipant):
            continue
        if _EXEMPT_QWIDGETS.get(qualified, "").strip():
            continue
        unaccounted.append(qualified)
    assert unaccounted == []


def test_exemptions_refer_to_existing_unregistered_classes() -> None:
    existing = {f"{c.__module__}.{c.__qualname__}" for c in _editor_widget_classes()}
    assert set(_EXEMPT_QWIDGETS) <= existing


# ---------------------------------------------------------------------------
# Saved_State_Precondition of MergeEngine.execute (task 13.22)
#
# Property 47: a merge executes only from a saved state.
# Validates: Requirements 26.6, 26.11, 26.14, 27.22, 27.23, 27.24
# ---------------------------------------------------------------------------

import copy
import tempfile

from hypothesis import given, settings, strategies as st

from slaktbusken.model.person import Name, Person
from slaktbusken.persistence import translation_io
from slaktbusken.persistence.file_io import FilePersistence
from slaktbusken.persistence.translation_io import PersonMapping
from slaktbusken.services.merge_engine import MergeEngine
from slaktbusken.services.merge_planner import MergeDecisions, build_plan
from tests.helpers.fault_fs import snapshot_dir

_DIRTY_TEXT = "Projektet har osparade ändringar. Spara projektet innan sammanslagningen."


def _merge_person(pid: str) -> Person:
    return Person(id=pid, sex="F", names=[Name("birth", "Anna", "Berg")])


def _merge_service(root: Path) -> ProjectService:
    svc = ProjectService()
    svc.create_project("Test", root)
    svc.data.persons.extend([_merge_person("person_1"), _merge_person("person_2")])
    translation_io.write_persons(
        [PersonMapping("@I2@", "person_2", "fp2")],
        [],
        svc.project_path.parent / "translation" / "persons.json",
    )
    svc._dirty = True
    svc.save_project()
    return svc


def _merge_plan(svc: ProjectService):
    translation = translation_io.read_all(svc.project_path.parent / "translation")
    decisions = MergeDecisions(
        "person_1", "person_2", survivor_id="person_1", survivor_confirmed=True
    )
    return build_plan(svc.data, translation, decisions, svc.content_revision)


def _registry_with(*editors: FakeEditor) -> EditorRegistry:
    registry = EditorRegistry()
    for editor in editors:
        registry.register(editor)
    return registry


def _state(svc: ProjectService, editors: list[FakeEditor]) -> dict:
    return {
        "disk": snapshot_dir(svc.project_path.parent),
        "data": copy.deepcopy(svc.data),
        "dirty": svc.is_dirty,
        "revision": svc.revision,
        "content_revision": svc.content_revision,
        "unsaved": [e.unsaved for e in editors],
    }


def _assert_refused_untouched(
    svc: ProjectService, editors: list[FakeEditor], before: dict, outcome, notifications
) -> None:
    assert not outcome.success
    assert outcome.step == "precondition"
    assert svc.data == before["data"]
    assert svc.is_dirty == before["dirty"]
    assert svc.revision == before["revision"]
    assert svc.content_revision == before["content_revision"]
    assert [e.unsaved for e in editors] == before["unsaved"]
    assert snapshot_dir(svc.project_path.parent) == before["disk"]
    assert notifications == []
    for editor in editors:
        assert editor.saves == 0
        assert editor.discards == 0
        assert editor.resolutions == 0


def test_dirty_project_refused(tmp_path: Path) -> None:
    svc = _merge_service(tmp_path)
    plan = _merge_plan(svc)
    editors = [FakeEditor("A", False)]
    engine = MergeEngine(svc, _registry_with(*editors))
    # Dirty flag set: refused with the exact message.
    svc._dirty = True
    calls: list[int] = []
    svc.add_merge_listener(lambda: calls.append(1))
    calls.clear()
    before = _state(svc, editors)
    outcome = engine.execute(plan)
    assert outcome.message == _DIRTY_TEXT
    _assert_refused_untouched(svc, editors, before, outcome, calls)
    assert svc.is_dirty


def test_dirty_project_refused_when_content_revision_differs(tmp_path: Path) -> None:
    svc = _merge_service(tmp_path)
    plan = _merge_plan(svc)
    # A mutation that raised the content revision without setting the flag.
    svc._record_change(content=True, notify=False)
    assert not svc.is_dirty
    assert svc.content_revision != svc.clean_content_revision
    calls: list[int] = []
    svc.add_merge_listener(lambda: calls.append(1))
    before = _state(svc, [])
    outcome = MergeEngine(svc, EditorRegistry()).execute(plan)
    assert outcome.message == _DIRTY_TEXT
    _assert_refused_untouched(svc, [], before, outcome, calls)


@pytest.mark.parametrize("unsaved_flags", [[True], [True, False, True], [True, True]])
def test_unsaved_editor_refused(tmp_path: Path, unsaved_flags: list[bool]) -> None:
    svc = _merge_service(tmp_path)
    plan = _merge_plan(svc)
    editors = [FakeEditor(f"Editor {i}", flag) for i, flag in enumerate(unsaved_flags)]
    calls: list[int] = []
    svc.add_merge_listener(lambda: calls.append(1))
    before = _state(svc, editors)
    outcome = MergeEngine(svc, _registry_with(*editors)).execute(plan)
    for editor in editors:
        assert (f"Redigeraren {editor.editor_title} har osparade ändringar" in outcome.message) == (
            editor.unsaved
        )
    _assert_refused_untouched(svc, editors, before, outcome, calls)
    # Only has_unsaved_changes was consulted.
    assert all(e.asked >= 1 for e in editors)


def test_clean_state_merge_commits_plan_applied_to_saved_state(tmp_path: Path) -> None:
    svc = _merge_service(tmp_path)
    plan = _merge_plan(svc)
    editors = [FakeEditor("A", False)]
    outcome = MergeEngine(svc, _registry_with(*editors)).execute(plan)
    assert outcome.success, outcome.message
    assert [p.id for p in svc.data.persons] == ["person_1"]
    assert svc.project_path.read_bytes() == FilePersistence.encode(svc.data)
    assert svc.is_saved_state()
    assert not svc.is_dirty
    assert editors[0].saves == editors[0].discards == editors[0].resolutions == 0


@settings(max_examples=25, deadline=None)
@given(
    dirty=st.booleans(),
    stray_content_change=st.booleans(),
    editor_flags=st.lists(st.booleans(), max_size=4),
)
def test_property_47_merge_only_from_saved_state(
    dirty: bool, stray_content_change: bool, editor_flags: list[bool]
) -> None:
    """**Validates: Requirements 26.6, 26.11, 26.14, 27.22, 27.23, 27.24**"""
    with tempfile.TemporaryDirectory() as tmp:
        svc = _merge_service(Path(tmp))
        plan = _merge_plan(svc)
        if stray_content_change:
            svc._record_change(content=True, notify=False)
        if dirty:
            svc._dirty = True
        editors = [FakeEditor(f"E{i}", flag) for i, flag in enumerate(editor_flags)]
        calls: list[int] = []
        svc.add_merge_listener(lambda: calls.append(1))
        calls.clear()
        before = _state(svc, editors)
        saved = svc.is_saved_state()
        assert saved == (not dirty and not stray_content_change)
        outcome = MergeEngine(svc, _registry_with(*editors)).execute(plan)
        if saved and not any(editor_flags):
            assert outcome.success, outcome.message
            assert svc.is_saved_state()
        else:
            _assert_refused_untouched(svc, editors, before, outcome, calls)
            if not saved:
                assert outcome.message == _DIRTY_TEXT
            else:
                assert all(
                    f"Redigeraren {e.editor_title} har" in outcome.message
                    for e in editors
                    if e.unsaved
                )
