"""UI wiring of commit execution and recovery messages (task 13.7).

**Validates: Requirements 27.6, 27.7, 27.11, 27.12, 27.13, 27.25, 28.9, 28.10**
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from slaktbusken.app import Application
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.commit.recovery import RecoveryRefusal, RecoveryRefusedError
from slaktbusken.services.merge_engine import MergeOutcome
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge import merge_review_wizard as mrw
from slaktbusken.ui.merge import recovery_dialogs
from slaktbusken.ui.merge.merge_gateway import MergeExecutionResult
from slaktbusken.ui.merge.merge_review_wizard import MergeReviewWizard
from slaktbusken.ui.merge.merge_runner import ThreadedMergeExecutor


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def service() -> ProjectService:
    svc = ProjectService()
    data = ProjectData()
    data.persons = [
        Person(id=pid, sex="U", title=t, names=[Name(type="birth", given="Anna", surname="Test")])
        for pid, t in (("person_1", "Smed"), ("person_2", "Snickare"))
    ]
    svc._project_data = data
    return svc


class GatedExecutor:
    """Two-phase executor whose disk phase waits for a gate."""

    def __init__(self, result: MergeExecutionResult) -> None:
        self.gate = threading.Event()
        self.result = result
        self.disk_thread = None
        self.finish_thread = None

    def execute(self, plan):  # pragma: no cover - the wizard must use the two phases
        raise AssertionError("synchronous path used")

    def run_disk_phase(self, plan):
        self.disk_thread = threading.get_ident()
        assert self.gate.wait(10)
        return plan

    def finish(self, token):
        self.finish_thread = threading.get_ident()
        return self.result


def _ready_wizard(qapp, service, executor, monkeypatch) -> MergeReviewWizard:
    wiz = MergeReviewWizard(service, ["person_1", "person_2"], executor=executor, use_worker=True)
    wiz.wait_for_plan()
    qapp.processEvents()
    wiz.survivor_page.radios["person_1"].setChecked(True)
    wiz.survivor_page.confirm_button.click()
    wiz.wait_for_plan()
    qapp.processEvents()
    wiz.section_pages[0].choice_radio("title", "person_1").setChecked(True)
    wiz.wait_for_plan()
    qapp.processEvents()
    monkeypatch.setattr(wiz, "_confirm_merge", lambda t: True)
    return wiz


def _pump(qapp, wiz) -> None:
    wiz.wait_for_execution()
    for _ in range(5):
        qapp.processEvents()


def test_disk_phase_runs_on_worker_with_overlay_and_no_cancel(qapp, service, monkeypatch):
    executor = GatedExecutor(MergeExecutionResult(True, "Klar.", survivor_id="person_1"))
    wiz = _ready_wizard(qapp, service, executor, monkeypatch)
    wiz.show()
    wiz.preview.execute_button.click()

    assert wiz.is_busy
    assert wiz._overlay.isVisible()
    assert not wiz.cancel_button.isEnabled()
    wiz.reject()  # ignored while the commit runs
    assert wiz.result() == 0 and wiz.is_busy

    executor.gate.set()
    _pump(qapp, wiz)

    assert not wiz.is_busy and not wiz._overlay.isVisible()
    assert wiz.executed and wiz.last_result.survivor_id == "person_1"
    assert executor.disk_thread != threading.get_ident()
    assert executor.finish_thread == threading.get_ident()  # adoption on the UI thread


def test_failed_commit_shows_message_and_stays_open(qapp, service, monkeypatch):
    executor = GatedExecutor(MergeExecutionResult(False, "Sammanslagningen kunde inte sparas."))
    executor.gate.set()
    wiz = _ready_wizard(qapp, service, executor, monkeypatch)
    messages: list[str] = []
    monkeypatch.setattr(wiz, "_show_message", messages.append)
    wiz.preview.execute_button.click()
    _pump(qapp, wiz)
    assert messages == ["Sammanslagningen kunde inte sparas."]
    assert not wiz.executed and not wiz.is_busy and wiz.cancel_button.isEnabled()


def test_refusal_result_opens_refusal_dialog_and_closes_wizard(qapp, service, monkeypatch):
    executor = GatedExecutor(MergeExecutionResult(False, "x", refusal_message="REFUSAL TEXT"))
    executor.gate.set()
    wiz = _ready_wizard(qapp, service, executor, monkeypatch)
    shown: list[str] = []
    monkeypatch.setattr(mrw, "show_recovery_refusal", lambda parent, text: shown.append(text))
    wiz.preview.execute_button.click()
    _pump(qapp, wiz)
    assert shown == ["REFUSAL TEXT"]
    assert not wiz.executed and wiz.result() == 0


def test_refusal_box_is_modal_and_text_is_selectable(qapp):
    box = recovery_dialogs.build_refusal_box(None, "Projektfil: C:\\a b\\p.json.gz")
    assert box.isModal()
    assert "C:\\a b\\p.json.gz" in box.text()
    flags = box.textInteractionFlags()
    assert flags & Qt.TextInteractionFlag.TextSelectableByMouse
    labels = [lbl for lbl in box.findChildren(QLabel) if "p.json.gz" in lbl.text()]
    assert labels and labels[0].textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse


class _StubEngine:
    def __init__(self, outcome: MergeOutcome, adopt_error: bool = False) -> None:
        self.outcome = outcome
        self.adopted = 0
        self.discarded = 0
        self.adopt_error = adopt_error

    def execute(self, plan):
        return self.outcome

    def adopt_pending(self):
        if self.adopt_error:
            raise RuntimeError("boom")
        self.adopted += 1

    def discard_pending(self):
        self.discarded += 1


def _refusal() -> RecoveryRefusal:
    return RecoveryRefusal("R1", Path("p.json.gz"), Path("j"), (Path("t.new"),), Path("b"))


def test_executor_adopts_only_in_finish_and_reports_recovery():
    engine = _StubEngine(MergeOutcome(True, "Klar.", recovery_message="Sammanslagningen slutfördes."))
    executor = ThreadedMergeExecutor(None, engine=engine)  # type: ignore[arg-type]
    plan = SimpleNamespace(survivor_id="person_7")
    token = executor.run_disk_phase(plan)
    assert engine.adopted == 0
    result = executor.finish(token)
    assert engine.adopted == 1
    assert result.success and result.survivor_id == "person_7"
    assert result.recovery_message == "Sammanslagningen slutfördes."


def test_executor_failure_adopts_nothing_and_refusal_carries_message():
    engine = _StubEngine(MergeOutcome(False, "msg", refusal=_refusal()))
    executor = ThreadedMergeExecutor(None, engine=engine)  # type: ignore[arg-type]
    result = executor.execute(SimpleNamespace(survivor_id="a"))
    assert engine.adopted == 0 and engine.discarded >= 1
    assert not result.success and "Alla dessa filer har sparats orörda" in result.refusal_message


def test_executor_adopt_failure_is_reported():
    engine = _StubEngine(MergeOutcome(True, "Klar."), adopt_error=True)
    executor = ThreadedMergeExecutor(None, engine=engine)  # type: ignore[arg-type]
    result = executor.execute(SimpleNamespace(survivor_id="a"))
    assert not result.success and "Starta om Släktbusken" in result.message


def _fake_app(message: str = ""):
    progress = []
    return SimpleNamespace(
        main_window=SimpleNamespace(hide_progress=lambda: progress.append(1)),
        project_service=SimpleNamespace(last_recovery_message=message),
        progress=progress,
    )


def test_open_failure_with_refusal_shows_dialog_and_logs(monkeypatch, caplog):
    shown = []
    monkeypatch.setattr(recovery_dialogs, "show_recovery_refusal", lambda p, t: shown.append(t))
    app = _fake_app()
    exc = RecoveryRefusedError(_refusal())
    with caplog.at_level("ERROR"):
        assert Application._report_open_failure(app, exc) is True
    assert shown == [str(exc)] and app.progress == [1]
    assert any("R1" in r.getMessage() for r in caplog.records)
    assert Application._report_open_failure(app, RuntimeError("x")) is False


def test_recovery_message_shown_after_open(monkeypatch):
    shown = []
    monkeypatch.setattr(recovery_dialogs, "show_recovery_outcome", lambda p, t: shown.append(t))
    Application._show_recovery_message(_fake_app("Sammanslagningen återställdes."))
    assert shown == ["Sammanslagningen återställdes."]
