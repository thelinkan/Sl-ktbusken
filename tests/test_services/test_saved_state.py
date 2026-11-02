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


# Feature: person-comparison-and-merge, Property 47:
@settings(max_examples=100, deadline=None)
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


# ---------------------------------------------------------------------------
# Commit bookkeeping and plan staleness (task 13.23)
#
# Property 48: Commit bookkeeping and plan staleness.
# Validates: Requirements 26.9, 26.12, 27.1, 27.8, 27.24
# ---------------------------------------------------------------------------

import os
from unittest import mock

from slaktbusken.services.merge_engine import PLAN_STALE_MESSAGE
from slaktbusken.ui.merge import merge_review_wizard as mrw
from slaktbusken.ui.merge.merge_gateway import MergeExecutionResult
from tests.helpers.fault_fs import CountingFs, FaultFs


def _first_replace_op(root: Path) -> int:
    """1-based index of the first ``replace`` operation of a successful commit."""
    other = _merge_service(root)
    counting = CountingFs()
    assert MergeEngine(other, None, fs=counting).execute(_merge_plan(other)).success
    return counting.names().index("replace") + 1


def _counters(svc: ProjectService) -> tuple[bool, int, int]:
    return svc.is_dirty, svc.revision, svc.content_revision


def test_successful_merge_bookkeeping(tmp_path: Path) -> None:
    svc = _merge_service(tmp_path)
    plan = _merge_plan(svc)
    calls: list[int] = []
    svc.add_merge_listener(lambda: calls.append(1))
    _, rev, content = _counters(svc)
    outcome = MergeEngine(svc, None).execute(plan)
    assert outcome.success, outcome.message
    assert not svc.is_dirty
    assert svc.revision == rev + 1
    assert svc.content_revision == content + 1
    assert len(calls) == 1
    assert svc.is_saved_state()


@pytest.mark.parametrize("kind", ["io_error_before", "crash_before"])
def test_failed_and_rolled_back_merge_changes_no_bookkeeping(
    tmp_path: Path, kind: str
) -> None:
    first_replace = _first_replace_op(tmp_path / "dry")
    svc = _merge_service(tmp_path / "real")
    plan = _merge_plan(svc)
    calls: list[int] = []
    svc.add_merge_listener(lambda: calls.append(1))
    before = _counters(svc)
    disk = snapshot_dir(svc.project_path.parent)
    # Failure before any replace (plain failure) and at the first replace
    # (the commit has started and is rolled back).
    for op in (1, first_replace):
        fs = FaultFs(op, "io_error_before")
        outcome = MergeEngine(svc, None, fs=fs).execute(plan)
        assert fs.triggered
        assert not outcome.success
        assert _counters(svc) == before
        assert calls == []
        assert svc.is_saved_state()
        assert snapshot_dir(svc.project_path.parent) == disk


def test_plain_save_keeps_content_revision_so_plan_is_not_rebuilt(
    tmp_path: Path,
) -> None:
    svc = _merge_service(tmp_path)
    svc._dirty = True  # an unsaved change that the plan already contains
    plan = _merge_plan(svc)
    content = svc.content_revision
    planner_calls: list[int] = []
    real_build = build_plan

    def counting_build(*args, **kwargs):
        planner_calls.append(1)
        return real_build(*args, **kwargs)

    with mock.patch.object(mrw, "build_plan", counting_build):
        svc.save_project()
    assert planner_calls == []
    assert svc.content_revision == content
    assert plan.content_revision == svc.content_revision
    # The saved plan is still executable: no stale report.
    outcome = MergeEngine(svc, None).execute(plan)
    assert outcome.success, outcome.message
    assert not outcome.stale


def test_content_change_between_plan_and_execution_is_stale_and_rebuilt(
    tmp_path: Path,
) -> None:
    svc = _merge_service(tmp_path)
    plan = _merge_plan(svc)
    # A real content change that was then saved: the saved-state check passes.
    svc.data.persons[0].occupation = "Bonde"
    svc._dirty = True
    svc.save_project()
    assert svc.is_saved_state()
    before = _counters(svc)
    disk = snapshot_dir(svc.project_path.parent)
    outcome = MergeEngine(svc, None).execute(plan)
    assert not outcome.success
    assert outcome.stale
    assert outcome.message == PLAN_STALE_MESSAGE
    assert _counters(svc) == before
    assert snapshot_dir(svc.project_path.parent) == disk
    # Rebuilding the plan makes the merge succeed.
    fresh = _merge_plan(svc)
    assert fresh.content_revision == svc.content_revision
    assert MergeEngine(svc, None).execute(fresh).success


@settings(max_examples=100, deadline=None)
@given(
    outcome_kind=st.sampled_from(["success", "failure", "rolled_back"]),
    save_first=st.booleans(),
)
def test_property_48_commit_bookkeeping(outcome_kind: str, save_first: bool) -> None:
    """**Validates: Requirements 26.9, 26.12, 27.1, 27.8, 27.24**"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        first_replace = _first_replace_op(root / "dry")
        svc = _merge_service(root / "real")
        if save_first:  # a plain save before planning changes only ``revision``
            svc._dirty = True
            svc.save_project()
        plan = _merge_plan(svc)
        calls: list[int] = []
        svc.add_merge_listener(lambda: calls.append(1))
        dirty, rev, content = _counters(svc)
        fs = None
        if outcome_kind == "failure":
            fs = FaultFs(1, "io_error_before")
        elif outcome_kind == "rolled_back":
            fs = FaultFs(first_replace, "io_error_before")
        outcome = MergeEngine(svc, None, fs=fs).execute(plan)
        if outcome_kind == "success":
            assert outcome.success, outcome.message
            assert not svc.is_dirty
            assert svc.revision == rev + 1
            assert svc.content_revision == content + 1
            assert len(calls) == 1
        else:
            assert not outcome.success
            assert _counters(svc) == (dirty, rev, content)
            assert calls == []
        assert svc.is_saved_state()


# --- Wizard flow ------------------------------------------------------------

from PySide6.QtWidgets import QApplication, QMessageBox

from slaktbusken.ui.merge.merge_review_wizard import MergeReviewWizard


class _EngineExecutor:
    """Runs the real MergeEngine; the wizard reaches it only through this."""

    def __init__(self, svc: ProjectService, registry: EditorRegistry) -> None:
        self.engine = MergeEngine(svc, registry)
        self.runs = 0
        self.plans: list = []

    def execute(self, plan):
        self.runs += 1
        self.plans.append(plan)
        outcome = self.engine.execute(plan)
        return MergeExecutionResult(outcome.success, outcome.message)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _wizard_for(svc: ProjectService, registry: EditorRegistry):
    executor = _EngineExecutor(svc, registry)
    translation_dir = svc.project_path.parent / "translation"
    wiz = MergeReviewWizard(
        svc,
        ["person_1", "person_2"],
        editor_registry=registry,
        executor=executor,
        translation_provider=lambda: translation_io.read_all(translation_dir),
        use_worker=False,
    )
    wiz.survivor_page.radios["person_1"].setChecked(True)
    wiz.survivor_page.confirm_button.click()
    assert wiz.preview.can_execute()
    return wiz, executor


def _patch_boxes(monkeypatch, choice: str | None):
    """Record every QMessageBox button row and click *choice* (or none)."""
    shown: list[tuple[str, list[str]]] = []

    def fake_exec(box):
        texts = [b.text() for b in box.buttons()]
        shown.append((box.text(), texts))
        if choice is not None:
            next(b for b in box.buttons() if b.text() == choice).click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    return shown


def test_wizard_unsaved_editor_blocks_and_resolution_only_on_button(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    svc = _merge_service(tmp_path)
    editor = FakeEditor("Personredigerare", True)
    registry = _registry_with(editor)
    wiz, executor = _wizard_for(svc, registry)
    disk = snapshot_dir(svc.project_path.parent)
    dialogs: list[mrw.UnsavedEditorsDialog] = []

    def show_block(editors):
        dlg = mrw.UnsavedEditorsDialog(editors, wiz)
        dialogs.append(dlg)
        # Shown, but the user does not press the button.

    boxes = _patch_boxes(monkeypatch, None)
    monkeypatch.setattr(wiz, "_show_editor_block", show_block)
    wiz.preview.execute_button.click()
    assert len(dialogs) == 1
    assert [b.text() for b in dialogs[0].buttons] == [mrw.GO_TO_EDITOR_TEXT]
    assert any(
        mrw.EDITOR_BLOCK_TEXT.format(title="Personredigerare") == lbl.text()
        for lbl in dialogs[0].findChildren(mrw.QLabel)
    )
    # No "Spara och fortsätt", no second confirmation, no resolution yet.
    assert boxes == []
    assert editor.resolutions == 0 and editor.saves == 0 and editor.discards == 0
    assert executor.runs == 0 and not wiz.executed
    assert snapshot_dir(svc.project_path.parent) == disk
    # Only the button press asks the editor to resolve.
    dialogs[0].buttons[0].click()
    assert editor.resolutions == 1
    assert editor.saves == 0 and editor.discards == 0


def test_wizard_dirty_project_offers_exactly_two_buttons_and_cancel_saves_nothing(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    svc = _merge_service(tmp_path)
    svc._dirty = True  # before the wizard opens, so its plan contains the change
    wiz, executor = _wizard_for(svc, EditorRegistry())
    disk = snapshot_dir(svc.project_path.parent)
    saves: list[int] = []
    monkeypatch.setattr(svc, "save_project", lambda: saves.append(1))
    boxes = _patch_boxes(monkeypatch, mrw.CANCEL_TEXT)
    wiz.preview.execute_button.click()
    assert [texts for _, texts in boxes] == [[mrw.SAVE_AND_CONTINUE_TEXT, mrw.CANCEL_TEXT]]
    assert boxes[0][0] == _DIRTY_TEXT
    assert saves == []
    assert executor.runs == 0 and not wiz.executed
    assert svc.is_dirty
    assert snapshot_dir(svc.project_path.parent) == disk


def test_wizard_failing_save_starts_no_merge_and_leaves_files_unchanged(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    svc = _merge_service(tmp_path)
    svc._dirty = True  # before the wizard opens, so its plan contains the change
    wiz, executor = _wizard_for(svc, EditorRegistry())
    disk = snapshot_dir(svc.project_path.parent)
    rev, content = svc.revision, svc.content_revision
    messages: list[str] = []
    monkeypatch.setattr(wiz, "_show_message", messages.append)
    monkeypatch.setattr(wiz, "_confirm_merge", lambda t: pytest.fail("no confirmation"))
    _patch_boxes(monkeypatch, mrw.SAVE_AND_CONTINUE_TEXT)
    real_replace = os.replace

    def failing_replace(src, dst, *a, **kw):
        # The save path (FilePersistence.save) replaces the project file.
        if Path(dst) == svc.project_path:
            raise OSError(5, "simulated I/O error on save")
        return real_replace(src, dst, *a, **kw)

    monkeypatch.setattr(os, "replace", failing_replace)
    wiz.preview.execute_button.click()
    monkeypatch.undo()
    assert messages == [mrw.SAVE_FAILED_TEXT]
    assert executor.runs == 0 and not wiz.executed
    assert svc.is_dirty
    assert (svc.revision, svc.content_revision) == (rev, content)
    after = snapshot_dir(svc.project_path.parent)
    assert {k: v for k, v in after.items() if not k.endswith(".tmp")} == {
        k: v for k, v in disk.items() if not k.endswith(".tmp")
    }


def test_wizard_second_confirmation_has_no_saving_sentence_and_merge_runs(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    svc = _merge_service(tmp_path)
    wiz, executor = _wizard_for(svc, EditorRegistry())
    plan_before = wiz.plan
    texts: list[str] = []
    monkeypatch.setattr(wiz, "_confirm_merge", lambda t: texts.append(t) or True)
    rev, content = svc.revision, svc.content_revision
    wiz.preview.execute_button.click()
    assert len(texts) == 1
    assert "spar" not in texts[0].lower()
    assert executor.plans == [plan_before]  # the plan was not rebuilt
    assert executor.runs == 1 and wiz.executed
    assert svc.revision == rev + 1 and svc.content_revision == content + 1
    assert svc.is_saved_state()


def test_wizard_save_and_continue_does_not_rebuild_plan(
    qapp, tmp_path: Path, monkeypatch
) -> None:
    svc = _merge_service(tmp_path)
    svc._dirty = True  # a pending change that the plan already contains
    wiz, executor = _wizard_for(svc, EditorRegistry())
    builds: list[int] = []
    real_build = mrw.build_plan
    monkeypatch.setattr(
        mrw, "build_plan", lambda *a, **k: builds.append(1) or real_build(*a, **k)
    )
    _patch_boxes(monkeypatch, mrw.SAVE_AND_CONTINUE_TEXT)
    texts: list[str] = []
    builds_at_confirmation: list[int] = []

    def confirm(text):
        texts.append(text)
        builds_at_confirmation.append(len(builds))
        return True

    monkeypatch.setattr(wiz, "_confirm_merge", confirm)
    # The dirty flag was set without a content change, so the plan is current.
    plan_before = wiz.plan
    wiz.preview.execute_button.click()
    assert builds_at_confirmation == [0]  # save did not rebuild the plan
    assert executor.plans == [plan_before]
    assert len(texts) == 1 and executor.runs == 1
