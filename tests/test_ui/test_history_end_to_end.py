"""End-to-end merge history: wizard merge, history window, reopen, search, redirect.

A real saved project with two duplicate persons is merged through the real
``MergeReviewWizard`` and ``ThreadedMergeExecutor``/``MergeEngine``.

**Validates: Requirements 36.1, 36.3, 36.11, 36.13, 28.11**
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from slaktbusken.app import Application
from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.merge_candidate import MergeCandidate
from slaktbusken.model.person import Name, Person
from slaktbusken.persistence import translation_io
from slaktbusken.persistence.translation_io import PersonMapping
from slaktbusken.services.person_search import PersonSearchIndex
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge import merge_gateway
from slaktbusken.ui.merge import merge_history_window as mhw
from slaktbusken.ui.merge.merge_review_wizard import MergeReviewWizard
from slaktbusken.ui.merge.merge_runner import ThreadedMergeExecutor

SURVIVOR = "person_1"
RETIRED = "person_2"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _build_project(root: Path) -> ProjectService:
    svc = ProjectService()
    svc.create_project("Test", root)
    data = svc.data
    data.persons.extend(
        Person(id=pid, sex="F", names=[Name("birth", "Anna", "Berg")])
        for pid in (SURVIVOR, RETIRED)
    )
    data.events.extend(
        [
            Event("event_1", "baptism", [Participant(SURVIVOR, "child")],
                  DateValue("1850-01-05", "day")),
            Event("event_2", "birth", [Participant(RETIRED, "child")],
                  DateValue("1850-01-01", "day")),
            Event("event_3", "death", [Participant(RETIRED, "deceased")],
                  DateValue("1920-05-05", "day")),
        ]
    )
    data.merge_candidates.append(MergeCandidate("cand_1", SURVIVOR, RETIRED, "confirmed"))
    translation_io.write_persons(
        [PersonMapping("@I2@", RETIRED, "fp2")],
        [],
        svc.project_path.parent / "translation" / "persons.json",
    )
    svc._dirty = True
    svc.save_project()
    return svc


def _merge_through_wizard(qapp, svc: ProjectService, monkeypatch):
    translation_dir = svc.project_path.parent / "translation"
    wiz = MergeReviewWizard(
        svc,
        [SURVIVOR, RETIRED],
        executor=ThreadedMergeExecutor(svc),
        translation_provider=lambda: translation_io.read_all(translation_dir),
        use_worker=False,
    )
    wiz.survivor_page.radios[SURVIVOR].setChecked(True)
    wiz.survivor_page.confirm_button.click()
    assert wiz.preview.can_execute()
    monkeypatch.setattr(wiz, "_confirm_merge", lambda text: True)
    monkeypatch.setattr(wiz, "_show_message", lambda text: pytest.fail(text))
    wiz.preview.execute_button.click()
    assert wiz.executed
    return wiz


def _history_windows():
    return [
        w
        for w in QApplication.topLevelWidgets()
        if isinstance(w, mhw.MergeHistoryWindow) and w.isVisible()
    ]


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    for w in _history_windows():
        w.close()
    merge_gateway.set_merge_gateway(None)


def _fake_app(svc: ProjectService, shown: list[str]):
    main = QMainWindow()
    app = SimpleNamespace(
        project_service=svc,
        main_window=main,
        edited=[],
        selected=[],
        updates=0,
    )
    main.person_list_panel = SimpleNamespace(select_person_from_diagram=app.selected.append)
    app._update_status = lambda: None
    app._update_diagram_panel = lambda: None
    app.open_person_editor = app.edited.append
    app._resolve_person_request = lambda pid: Application._resolve_person_request(app, pid)
    app.show_person = lambda pid: Application.show_person(app, pid)
    app.open_history = lambda pid=None: mhw.open_merge_history_window(svc, pid, main)
    return app


def test_merge_history_end_to_end(qapp, tmp_path: Path, monkeypatch) -> None:
    svc = _build_project(tmp_path)
    app = _fake_app(svc, [])
    merge_gateway.set_merge_gateway(app)  # type: ignore[arg-type]

    wiz = _merge_through_wizard(qapp, svc, monkeypatch)

    # The success box offers "Visa sammanslagningshistorik"; the stub clicks it.
    box_buttons: list[list[str]] = []

    def fake_exec(box):
        texts = [b.text() for b in box.buttons()]
        box_buttons.append(texts)
        next(b for b in box.buttons() if b.text() == "Visa sammanslagningshistorik").click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    Application._after_merge_review(app, wiz, None)  # type: ignore[arg-type]
    assert box_buttons == [["Visa sammanslagningshistorik", "Stäng"]]

    # --- the window shows exactly the one entry of the survivor ------------
    windows = _history_windows()
    assert len(windows) == 1
    window = windows[0]
    assert window.person_id == SURVIVOR
    assert window.row_count() == 1
    entry = svc.data.merge_history[0]
    assert entry.merged_person_id == RETIRED and entry.surviving_person_id == SURVIVOR
    assert len(entry.summary_lines) == 11

    table = window._table
    cells = [table.item(0, c).text() for c in range(5)]
    assert cells[0] == "Anna Berg"
    assert cells[1] == "1850\u20131920"
    assert cells[2] == RETIRED
    assert cells[3] == entry.merge_date and entry.merge_date
    assert SURVIVOR in cells[4]

    table.selectRow(0)
    details = window._details.toPlainText()
    assert "Anna Berg" in details and RETIRED in details and "1850\u20131920" in details
    assert f"Datum: {entry.merge_date}" in details
    for line in entry.summary_lines:
        assert f"  {line}" in details
    assert sum(1 for l in details.splitlines() if l.startswith("  ") and ":" in l) >= 11

    # --- "Gå till behållen person" navigates to the survivor ---------------
    assert window._navigate_button.isEnabled()
    window._navigate_button.click()
    assert app.selected == [SURVIVOR] and app.edited == [SURVIVOR]
    window.close()

    # --- save, reopen with a fresh service, same row ------------------------
    svc.save_project()
    path = svc.project_path
    fresh = ProjectService()
    fresh.open_project(path)
    reopened = mhw.open_merge_history_window(fresh, SURVIVOR)
    assert reopened.row_count() == 1
    again = reopened._table
    assert [again.item(0, c).text() for c in range(5)] == cells
    reopened._table.selectRow(0)
    assert reopened._details.toPlainText() == details
    reopened.close()

    # --- search by the retired id finds the survivor ------------------------
    results = PersonSearchIndex.build(fresh.data).search(RETIRED)
    assert results and results[0].person_id == SURVIVOR
    assert results[0].retired_label.startswith("Sammanslagen med Anna Berg")
    assert "Sammanslagen med" in results[0].display_text

    # --- opening the retired id redirects to the survivor -------------------
    app2 = _fake_app(fresh, [])
    Application.show_person(app2, RETIRED)  # type: ignore[arg-type]
    assert app2.edited == [SURVIVOR] and app2.selected == [SURVIVOR]
    assert app2.main_window.statusBar().currentMessage() == (
        f"Personen {RETIRED} slogs samman med Anna Berg."
    )
    app.main_window.close()
    app2.main_window.close()
