"""Offscreen tests for the history buttons of register and comparison window (36.11)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.merge_candidate import MergeHistoryEntry
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.merge.candidate_register_window import CandidateRegisterWindow
from slaktbusken.ui.merge.merge_gateway import set_merge_gateway
from slaktbusken.ui.merge.person_comparison_window import PersonComparisonWindow


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeGateway:
    def __init__(self) -> None:
        self.history_calls: list = []

    def open_history(self, person_id=None) -> None:
        self.history_calls.append(person_id)


@pytest.fixture
def gateway():
    gw = FakeGateway()
    set_merge_gateway(gw)
    yield gw
    set_merge_gateway(None)


@pytest.fixture
def service() -> ProjectService:
    svc = ProjectService()
    data = ProjectData()
    data.persons = [
        Person(id=f"person_{i}", sex="U", names=[Name(type="birth", given=g, surname="Test")])
        for i, g in enumerate(["Anna", "Bo", "Cia"], start=1)
    ]
    data.merge_history = [
        MergeHistoryEntry(
            id="mh_1",
            surviving_person_id="person_1",
            merged_person_id="person_9",
            merged_person_name="Nils Test",
            merged_person_lifespan="1900–1970",
            merge_date="2024-01-01",
        )
    ]
    svc._project_data = data
    return svc


def test_register_button_opens_all_without_filter(qapp, service, gateway):
    win = CandidateRegisterWindow(service)
    try:
        assert win._history_button.text() == "Sammanslagningshistorik"
        win._history_button.click()
        assert gateway.history_calls == [None]
    finally:
        win.close()


def test_register_button_uses_filtered_person(qapp, service, gateway):
    service.add_merge_candidate("person_1", "person_2")
    win = CandidateRegisterWindow(service)
    try:
        win.set_person_filter("person_2")
        win._history_button.click()
        assert gateway.history_calls == ["person_2"]
    finally:
        win.close()


def test_register_button_without_gateway_does_nothing(qapp, service):
    set_merge_gateway(None)
    win = CandidateRegisterWindow(service)
    try:
        win._history_button.click()
    finally:
        win.close()


def test_comparison_slot_button_visible_only_with_history(qapp, service, gateway):
    win = PersonComparisonWindow(service, "person_1", "person_2")
    try:
        win.show()
        first, second = win.history_buttons
        assert first.text() == "Sammanslagningshistorik"
        assert first.isVisible() and first.isEnabled()
        assert not second.isVisible()
        first.click()
        assert gateway.history_calls == ["person_1"]
    finally:
        win.close()
