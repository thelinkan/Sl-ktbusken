"""Offscreen tests for the Candidate_Register window (requirement 15)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.candidate_register import COLUMN_HEADERS, NO_MATCH_MESSAGE
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge.candidate_register_window import CandidateRegisterWindow


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def open_comparison(self, person_1_id: str = "", person_2_id: str = "") -> None:
        self.calls.append((person_1_id, person_2_id))


@pytest.fixture
def service() -> ProjectService:
    svc = ProjectService()
    data = ProjectData()
    data.persons = [
        Person(id=f"person_{i}", sex="U", names=[Name(type="birth", given=g, surname="Test")])
        for i, g in enumerate(["Anna", "Bo", "Cia", "Dag"], start=1)
    ]
    svc._project_data = data
    return svc


@pytest.fixture
def window(qapp, service):
    # Candidates: A (1,2) unreviewed, B (3,4) rejected, C (1,3) disabled.
    service.add_merge_candidate("person_1", "person_2")
    rejected = service.add_merge_candidate("person_3", "person_4")
    service.set_candidate_assessment(rejected.id, "rejected")
    disabled = service.add_merge_candidate("person_1", "person_3")
    service.set_candidate_enabled(disabled.id, False)
    service.add_candidate_comment(service.data.merge_candidates[0].id, "2024-01-02", "Samma by")
    gateway = FakeGateway()
    win = CandidateRegisterWindow(service, gateway=gateway)
    win.gateway = gateway
    yield win
    win.close()


def test_columns_and_title(window):
    assert window.windowTitle() == "Sammanslagningskandidater"
    headers = [window._table.horizontalHeaderItem(i).text() for i in range(6)]
    assert headers == list(COLUMN_HEADERS)
    assert headers == [
        "Person 1", "Person 2", "Bedömning", "Aktiv", "Senaste kommentar", "Forskningsärende",
    ]


def test_default_view_shows_only_active_non_rejected(window):
    assert window.row_count() == 1
    assert window.cell_text(0, 0) == "Anna Test"
    assert window.cell_text(0, 1) == "Bo Test"
    assert window.cell_text(0, 3) == "Ja"
    assert window.cell_text(0, 4) == "Samma by"


def test_search_length_limit(window):
    assert window._search.maxLength() == 200


def test_rejected_and_disabled_filters(window):
    window._assessment.setCurrentIndex(window._assessment.findData("rejected"))
    assert window.row_count() == 1
    assert window.cell_text(0, 0) == "Cia Test"
    window._assessment.setCurrentIndex(0)
    window._enabled.setCurrentIndex(window._enabled.findData(False))
    assert window.row_count() == 1
    assert window.cell_text(0, 3) == "Nej"


def test_search_includes_disabled_when_person_matches(window):
    window._search.setText("cia")
    assert window.row_count() == 1
    assert window.cell_text(0, 1) == "Cia Test"


def test_person_filter(window):
    window.set_person_filter("person_2")
    assert window.row_count() == 1
    window.set_person_filter("person_4")
    assert window.row_count() == 0
    window.set_person_filter(None)
    assert window.row_count() == 1


def test_empty_state_message(window):
    window.show()
    assert not window._empty_label.isVisible()
    window._search.setText("finns inte")
    assert window.row_count() == 0
    assert window._empty_label.text() == NO_MATCH_MESSAGE
    assert window._empty_label.isVisible()
    window._search.clear()
    assert not window._empty_label.isVisible()


def test_sort_toggles_and_survives_refresh(window):
    window._assessment.setCurrentIndex(window._assessment.findData("__all__"))
    window._enabled.setCurrentIndex(window._enabled.findData(False))
    window._on_header_clicked(0)
    assert (window._sort_column, window._descending) == (0, False)
    window._on_header_clicked(0)
    assert window._descending is True
    window._search.setText("test")
    window.refresh()
    assert (window._sort_column, window._descending) == (0, True)
    assert window._search.text() == "test"


def test_refresh_on_merge_listener(window, service):
    service.add_merge_candidate("person_2", "person_4")
    window._refresh_timer.timeout.emit()
    assert window.row_count() == 2


def test_double_click_opens_comparison(window):
    window._on_double_clicked(0, 2)
    assert window.gateway.calls == [("person_1", "person_2")]


def test_edit_does_not_start_merge(window, service, monkeypatch):
    from slaktbusken.ui.merge import candidate_register_window as crw

    opened: list[str] = []

    class FakeDialog:
        def __init__(self, svc, candidate_id, parent=None, registry=None):
            opened.append(candidate_id)

        def exec(self):
            return 0

    monkeypatch.setattr(crw, "CandidateEditorDialog", FakeDialog)
    window._table.selectRow(0)
    window.edit_selected()
    assert opened == [service.data.merge_candidates[0].id]
