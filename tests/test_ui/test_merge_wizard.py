"""Offscreen widget tests for the Merge_Review wizard (task 11.9) and the GEDCOM
update warning in its preview (task 11.18).

**Validates: Requirements 20.1, 20.5, 20.6, 20.8, 20.10, 20.12, 26.1, 26.4, 26.5,
26.6, 26.7, 26.9, 26.11, 26.12, 26.13, 26.14, 26.15**
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.gedcom import capabilities
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.editor_registry import EditorRegistry, ResolutionResult
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge import merge_review_wizard as mrw
from slaktbusken.ui.merge.merge_gateway import MergeExecutionResult
from slaktbusken.ui.merge.merge_preview import (
    BLOCKING_ICON,
    EXECUTE_TEXT,
    GEDCOM_WARNING_TEXT,
    PREVIEW_TITLE,
    STALE_NOTICE,
)
from slaktbusken.ui.merge.merge_review_wizard import (
    CANCEL,
    SAVE,
    MergeReviewWizard,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _person(pid: str, title: str) -> Person:
    return Person(
        id=pid, sex="U", title=title, names=[Name(type="birth", given="Anna", surname="Test")]
    )


@pytest.fixture
def service() -> ProjectService:
    svc = ProjectService()
    data = ProjectData()
    data.persons = [_person("person_1", "Smed"), _person("person_2", "Snickare")]
    svc._project_data = data
    return svc


class FakeExecutor:
    def __init__(self, success: bool = True) -> None:
        self.plans: list = []
        self.success = success

    def execute(self, plan):
        self.plans.append(plan)
        return MergeExecutionResult(self.success, "" if self.success else "Misslyckades.")


class FakeEditor:
    editor_title = "Personredigerare: Anna (person_1)"

    def __init__(self) -> None:
        self.unsaved = True

    def has_unsaved_changes(self) -> bool:
        return self.unsaved

    def request_resolution(self) -> ResolutionResult:
        self.unsaved = False
        return ResolutionResult.SAVED


def _wizard(qapp, service, executor=None, registry=None) -> MergeReviewWizard:
    return MergeReviewWizard(
        service, ["person_1", "person_2"], editor_registry=registry,
        executor=executor or FakeExecutor(), use_worker=False,
    )


def _ready(wiz: MergeReviewWizard) -> None:
    """Choose a survivor, confirm and resolve the title conflict."""
    wiz.survivor_page.radios["person_1"].setChecked(True)
    wiz.survivor_page.confirm_button.click()
    page = wiz.section_pages[0]
    page.choice_radio("title", "person_1").setChecked(True)


def _no_dialogs(wiz, monkeypatch, messages=None):
    monkeypatch.setattr(wiz, "_show_message", lambda t: (messages if messages is not None else []).append(t))


def test_no_default_survivor_and_sections_locked(qapp, service):
    wiz = _wizard(qapp, service)
    assert wiz.survivor_page.selected() is None
    assert not wiz.survivor_page.confirm_button.isEnabled()
    assert wiz.is_section_enabled(0)
    assert not any(wiz.is_section_enabled(r) for r in range(1, wiz.section_list.count()))
    assert not wiz.preview.execute_button.isEnabled()
    assert wiz.preview.title_label.text() == PREVIEW_TITLE == "Förhandsgranskning av sammanslagning"


def test_confirming_survivor_opens_first_section_only(qapp, service):
    wiz = _wizard(qapp, service)
    wiz.survivor_page.radios["person_1"].setChecked(True)
    wiz.survivor_page.confirm_button.click()
    assert wiz.is_section_enabled(1)
    assert not wiz.is_section_enabled(2)
    wiz.section_pages[0].confirm_button.click()
    assert wiz.is_section_enabled(2)


def test_unresolved_choice_disables_execute_until_made(qapp, service):
    wiz = _wizard(qapp, service)
    wiz.survivor_page.radios["person_1"].setChecked(True)
    wiz.survivor_page.confirm_button.click()
    assert wiz.plan is not None and wiz.plan.unresolved
    assert not wiz.preview.execute_button.isEnabled()
    wiz.section_pages[0].choice_radio("title", "person_1").setChecked(True)
    assert not wiz.plan.unresolved
    assert wiz.preview.execute_button.isEnabled()
    assert wiz.preview.execute_button.text() == EXECUTE_TEXT


def test_changing_survivor_resets_choices_and_shows_message(qapp, service):
    wiz = _wizard(qapp, service)
    _ready(wiz)
    wiz.survivor_page.radios["person_2"].setChecked(True)
    assert wiz.survivor_page.reset_label.text()
    assert not wiz.is_section_enabled(1)
    assert wiz.build_decisions().title_from is None
    assert not wiz.preview.execute_button.isEnabled()


def test_preview_lists_blocking_with_icon_and_label(qapp, service):
    service.data.persons[0].sex = "M"
    service.data.persons[1].sex = "F"
    wiz = _wizard(qapp, service)
    wiz.survivor_page.radios["person_1"].setChecked(True)
    wiz.survivor_page.confirm_button.click()
    lines = [wiz.preview.problem_list.item(i).text() for i in range(wiz.preview.problem_list.count())]
    assert any(l.startswith(f"{BLOCKING_ICON} Konflikt:") for l in lines)
    assert not wiz.preview.execute_button.isEnabled()


def test_unsaved_editor_blocks_without_save_or_confirmation(qapp, service, monkeypatch):
    editor = FakeEditor()
    registry = EditorRegistry()
    registry.register(editor)
    executor = FakeExecutor()
    wiz = _wizard(qapp, service, executor, registry)
    _ready(wiz)
    shown = []
    monkeypatch.setattr(wiz, "_show_editor_block", lambda eds: shown.append(list(eds)))
    monkeypatch.setattr(wiz, "_ask_save_choice", lambda: pytest.fail("no save choice"))
    monkeypatch.setattr(wiz, "_confirm_merge", lambda t: pytest.fail("no confirmation"))
    wiz.preview.execute_button.click()
    assert shown == [[editor]]
    assert executor.plans == []


def test_editor_block_dialog_message_and_button(qapp):
    editor = FakeEditor()
    dlg = mrw.UnsavedEditorsDialog([editor])
    texts = [w.text() for w in dlg.findChildren(mrw.QLabel)]
    assert (
        "Redigeraren Personredigerare: Anna (person_1) har osparade ändringar. Spara eller "
        "kasta ändringarna i redigeraren och försök igen." in texts
    )
    assert [b.text() for b in dlg.buttons] == ["Gå till redigeraren"]
    dlg.buttons[0].click()
    assert not editor.unsaved


class _Cancelling(FakeEditor):
    editor_title = "Anteckningar"

    def request_resolution(self) -> ResolutionResult:
        return ResolutionResult.STILL_UNSAVED


def test_editor_block_rechecks_after_each_resolution(qapp):
    a, b = FakeEditor(), _Cancelling()
    dlg = mrw.UnsavedEditorsDialog([a, b])
    dlg.show()
    dlg.buttons[1].click()  # user cancels inside the editor: still listed
    assert dlg.buttons[1].isVisibleTo(dlg) and dlg.buttons[0].isVisibleTo(dlg)
    dlg.buttons[0].click()
    assert not a.unsaved and not dlg.buttons[0].isVisibleTo(dlg)
    assert dlg.buttons[1].isVisibleTo(dlg)
    assert b.unsaved  # the wizard dialog never saves or discards on its own


def test_editor_resolved_then_dirty_project_offers_save_choice(qapp, service, monkeypatch):
    editor = FakeEditor()
    registry = EditorRegistry()
    registry.register(editor)
    executor = FakeExecutor()
    wiz = _wizard(qapp, service, executor, registry)
    _ready(wiz)
    service._dirty = True
    monkeypatch.setattr(wiz, "_show_editor_block", lambda eds: eds[0].request_resolution())
    asked = []
    monkeypatch.setattr(wiz, "_ask_save_choice", lambda: asked.append(1) or CANCEL)
    assert wiz.check_saved_state() is False
    assert asked == [1] and executor.plans == []


def test_wizard_texts_never_mention_saving_with_the_merge(qapp):
    assert mrw.SAVE_AND_CONTINUE_TEXT == "Spara och fortsätt" and mrw.CANCEL_TEXT == "Avbryt"
    assert "spar" not in mrw.CONFIRM_QUESTION.lower()


def test_dirty_project_cancel_keeps_decisions_and_saves_nothing(qapp, service, monkeypatch):
    executor = FakeExecutor()
    wiz = _wizard(qapp, service, executor)
    _ready(wiz)
    service._dirty = True  # unsaved project (content changes, plan becomes stale)
    wiz._plan = wiz._plan  # keep reference
    wiz._needs_reconfirm = False
    wiz.preview.set_plan(wiz.plan)
    saved = []
    monkeypatch.setattr(service, "save_project", lambda: saved.append(1))
    monkeypatch.setattr(wiz, "_ask_save_choice", lambda: CANCEL)
    monkeypatch.setattr(wiz, "_confirm_merge", lambda t: pytest.fail("no confirmation"))
    assert wiz.check_saved_state() is False
    assert saved == [] and executor.plans == []
    assert wiz.build_decisions().title_from == "person_1"


def test_save_and_continue_keeps_plan_and_asks_confirmation(qapp, service, monkeypatch):
    service._dirty = True
    executor = FakeExecutor()
    wiz = _wizard(qapp, service, executor)
    _ready(wiz)
    plan_before = wiz.plan

    def fake_save():
        service._dirty_value = False
        service._clean_content_revision = service._content_revision
        service._record_change(content=False)

    monkeypatch.setattr(service, "save_project", fake_save)
    monkeypatch.setattr(wiz, "_ask_save_choice", lambda: SAVE)
    texts = []
    monkeypatch.setattr(wiz, "_confirm_merge", lambda t: texts.append(t) or True)
    wiz.preview.execute_button.click()
    assert wiz.plan is plan_before  # a plain save never rebuilds the plan
    assert len(executor.plans) == 1
    assert wiz.executed
    assert texts == [
        "Slå samman Anna Test (person_1) som behålls med Anna Test (person_2) som tas bort?"
    ]
    assert "spar" not in texts[0].lower()


def test_save_failure_shows_message_and_starts_no_merge(qapp, service, monkeypatch):
    service._dirty = True
    executor = FakeExecutor()
    wiz = _wizard(qapp, service, executor)
    _ready(wiz)
    messages: list[str] = []
    _no_dialogs(wiz, monkeypatch, messages)

    def boom():
        raise OSError("disk full")

    monkeypatch.setattr(service, "save_project", boom)
    monkeypatch.setattr(wiz, "_ask_save_choice", lambda: SAVE)
    monkeypatch.setattr(wiz, "_confirm_merge", lambda t: pytest.fail("no confirmation"))
    wiz.preview.execute_button.click()
    assert messages == ["Projektet kunde inte sparas. Ingenting har slagits samman."]
    assert executor.plans == [] and not wiz.executed


def test_declined_second_confirmation_keeps_wizard_open(qapp, service, monkeypatch):
    executor = FakeExecutor()
    wiz = _wizard(qapp, service, executor)
    _ready(wiz)
    monkeypatch.setattr(wiz, "_confirm_merge", lambda t: False)
    wiz.preview.execute_button.click()
    assert executor.plans == [] and not wiz.executed
    assert wiz.preview.execute_button.isEnabled()


def test_executor_failure_shows_message(qapp, service, monkeypatch):
    executor = FakeExecutor(success=False)
    wiz = _wizard(qapp, service, executor)
    _ready(wiz)
    messages: list[str] = []
    _no_dialogs(wiz, monkeypatch, messages)
    monkeypatch.setattr(wiz, "_confirm_merge", lambda t: True)
    wiz.preview.execute_button.click()
    assert messages == ["Misslyckades."] and not wiz.executed


def test_content_change_marks_preview_stale_until_reconfirmed(qapp, service):
    wiz = _wizard(qapp, service)
    _ready(wiz)
    assert wiz.preview.execute_button.isEnabled()
    service.data.persons[0].occupation = "Bonde"
    service._dirty = True  # a real content change notifies listeners
    assert wiz.preview.status_label.text() == STALE_NOTICE
    assert not wiz.preview.execute_button.isEnabled()
    assert not wiz.preview.reconfirm_button.isHidden()
    wiz.preview.reconfirm_button.click()
    assert wiz.preview.execute_button.isEnabled()


def test_cancel_closes_without_executing(qapp, service):
    executor = FakeExecutor()
    wiz = _wizard(qapp, service, executor)
    _ready(wiz)
    wiz.cancel_button.click()
    assert wiz.result() == 0 and executor.plans == [] and not service._dirty


def test_plan_builds_on_worker_thread(qapp, service):
    wiz = MergeReviewWizard(service, ["person_1", "person_2"], executor=FakeExecutor())
    wiz.wait_for_plan()
    qapp.processEvents()
    assert wiz.plan is not None
    wiz.survivor_page.radios["person_1"].setChecked(True)
    wiz.wait_for_plan()
    qapp.processEvents()
    assert wiz.plan.survivor_id == "person_1"
    wiz.reject()


# ---------------------------------------------------------------------------
# Task 11.10 additions: sections, exact reset text, real dialogs, preview styles
# ---------------------------------------------------------------------------

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from slaktbusken.services.merge_planner import MergeConflict  # noqa: E402
from slaktbusken.ui.merge import merge_preview as mp  # noqa: E402


def _click_active_box(button_text: str, seen: list) -> None:
    """Inspect the open modal QMessageBox, then click the named button."""
    box = QApplication.activeModalWidget()
    assert isinstance(box, QMessageBox)
    seen.append((box.text(), [b.text() for b in box.buttons()]))
    next(b for b in box.buttons() if b.text() == button_text).click()


def test_wizard_sections_in_order_with_titles(qapp, service):
    wiz = _wizard(qapp, service)
    titles = [wiz.section_list.item(i).text() for i in range(wiz.section_list.count())]
    assert titles == [
        "Välj person som behålls", "Personuppgifter", "Namn", "Händelser", "Boenden",
        "Familj", "Källor, media och DNA", "Forskning och övriga referenser",
        "Förhandsgranskning av sammanslagning",
    ]


def test_survivor_reset_message_exact_text_and_cleared_on_confirm(qapp, service):
    wiz = _wizard(qapp, service)
    _ready(wiz)
    wiz.survivor_page.radios["person_2"].setChecked(True)
    assert wiz.survivor_page.reset_label.text() == (
        "Personen som behålls ändrades. Alla övriga val har nollställts och behöver göras om."
    )
    wiz.survivor_page.confirm_button.click()
    assert wiz.survivor_page.reset_label.text() == ""


def test_save_prompt_dialog_text_and_buttons(qapp, service):
    wiz = _wizard(qapp, service)
    seen: list = []
    QTimer.singleShot(0, lambda: _click_active_box("Spara och fortsätt", seen))
    assert wiz._ask_save_choice() == SAVE
    text, buttons = seen[0]
    assert text == "Projektet har osparade ändringar. Spara projektet innan sammanslagningen."
    assert buttons == ["Spara och fortsätt", "Avbryt"]
    QTimer.singleShot(0, lambda: _click_active_box("Avbryt", seen))
    assert wiz._ask_save_choice() == CANCEL


def test_merge_confirmation_dialog_text_has_no_save_sentence(qapp, service):
    wiz = _wizard(qapp, service)
    seen: list = []
    question = "Slå samman Anna Test (person_1) som behålls med Anna Test (person_2) som tas bort?"
    QTimer.singleShot(0, lambda: _click_active_box("Slå samman", seen))
    assert wiz._confirm_merge(question) is True
    text, buttons = seen[0]
    assert text == question and "spar" not in text.lower()
    assert buttons == ["Slå samman", "Avbryt"]
    QTimer.singleShot(0, lambda: _click_active_box("Avbryt", seen))
    assert wiz._confirm_merge(question) is False


def test_preview_warning_and_blocking_styles_differ(qapp):
    blocking = MergeConflict("blocking", "c1", "names", "Samma namn.")
    warning = MergeConflict("warning", "c2", "names", "Liknande namn.")
    b, w = mp.format_conflict(blocking), mp.format_conflict(warning)
    assert b.startswith("⛔ Konflikt:") and w.startswith("⚠ Varning:")
    assert b.endswith("(Avsnitt: Namn)") and w.endswith("(Avsnitt: Namn)")
    assert mp.BLOCKING_ICON != mp.WARNING_ICON and mp.BLOCKING_LABEL != mp.WARNING_LABEL


def test_preview_lists_unresolved_choice_and_gedcom_warning(qapp, service):
    wiz = _wizard(qapp, service)
    wiz.survivor_page.radios["person_1"].setChecked(True)
    wiz.survivor_page.confirm_button.click()
    lines = [wiz.preview.problem_list.item(i).text() for i in range(wiz.preview.problem_list.count())]
    assert any(l.startswith("Val saknas:") for l in lines)
    assert wiz.preview.gedcom_label.text() == GEDCOM_WARNING_TEXT
    assert wiz.preview.gedcom_label.isHidden() == (not mp.gedcom_warning_visible())


def test_synchronous_merge_does_not_treat_own_adoption_as_foreign_change(
    qapp, tmp_path, monkeypatch
) -> None:
    """Real engine on a saved project, synchronous path: no rebuild, plan kept."""
    from tests.test_services.test_saved_state import _merge_service, _wizard_for

    svc = _merge_service(tmp_path)
    wiz, executor = _wizard_for(svc, EditorRegistry())
    plan_before = wiz.plan
    assert plan_before is not None
    rebuilds: list[int] = []
    real_rebuild = wiz._rebuild_plan
    monkeypatch.setattr(wiz, "_rebuild_plan", lambda: rebuilds.append(1) or real_rebuild())
    monkeypatch.setattr(wiz, "_confirm_merge", lambda text: True)
    wiz.preview.execute_button.click()
    assert wiz.executed
    assert wiz.last_result is not None and wiz.last_result.success
    assert rebuilds == []
    assert wiz.plan is plan_before
    assert wiz._finishing is False
