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
