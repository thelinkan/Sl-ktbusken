"""Offscreen tests for the candidate section of the person editor (Req 16)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.merge_candidate import MergeCandidateComment
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.project_service import ProjectService
from slaktbusken.ui.editors.person_editor import PersonEditor
from slaktbusken.ui.merge.candidate_section import CandidatesSection
from slaktbusken.ui.merge.merge_gateway import set_merge_gateway


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeGateway(QObject):
    merge_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple] = []

    def open_comparison(self, a="", b=""):
        self.calls.append(("compare", a, b))

    def mark_candidates(self, a, b):
        self.calls.append(("mark", a, b))

    def open_candidate(self, cid):
        self.calls.append(("open", cid))

    def open_register(self, pid=None):
        self.calls.append(("register", pid))

    def open_history(self, pid=None):
        self.calls.append(("history", pid))


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
        Person(id=f"person_{i}", sex="M", names=[Name(type="birth", given=g, surname="B")])
        for i, g in ((1, "Anna"), (2, "Bo"), (3, "Cia"), (4, "Dan"))
    ]
    data.events = [
        Event(
            id="e1",
            type="birth",
            date=DateValue(value="1829-01-01", precision="exact"),
            participants=[Participant(person_id="person_2", role="child")],
        )
    ]
    svc._project_data = data
    return svc


def _editor(service, person_id="person_1", **kw):
    person = next(p for p in service.data.persons if p.id == person_id)
    return PersonEditor(service.data, person, project_service=service, **kw)


def _section(editor) -> CandidatesSection:
    return editor._candidates_section


def test_section_title_and_empty_state(qapp, service, gateway):
    section = _section(_editor(service))
    assert section.title() == "Sammanslagningskandidater"
    assert section.candidate_ids() == []
    assert not section._empty_label.isHidden()


def test_lists_candidate_with_details(qapp, service, gateway):
    cand = service.add_merge_candidate("person_1", "person_2")
    cand.comments.append(MergeCandidateComment(id="c1", date="2020-01-01", text="x" * 150))
    cand.comments.append(MergeCandidateComment(id="c2", date="2021-01-01", text="y" * 150))
    section = _section(_editor(service))
    assert section.candidate_ids() == [cand.id]
    text = section._list.item(0).text()
    assert "Bo B" in text and "f. 1829" in text and "d. –" in text
    assert "Ej granskad" in text or "granskad" in text.lower()
    assert "Aktiv" in text
    assert "y" * 99 + "…" in text and "x" not in text.replace("Ex", "")


def test_historical_toggle_hides_rejected_and_disabled(qapp, service, gateway):
    rejected = service.add_merge_candidate("person_1", "person_2")
    service.set_candidate_assessment(rejected.id, "rejected")
    disabled = service.add_merge_candidate("person_1", "person_3")
    service.set_candidate_enabled(disabled.id, False)
    open_ = service.add_merge_candidate("person_1", "person_4")
    section = _section(_editor(service))
    assert section.show_historical() is False
    assert section.candidate_ids() == [open_.id]
    section.set_show_historical(True)
    assert set(section.candidate_ids()) == {rejected.id, disabled.id, open_.id}
    section.set_show_historical(False)
    assert section.candidate_ids() == [open_.id]


def test_open_and_compare_use_gateway(qapp, service, gateway):
    cand = service.add_merge_candidate("person_2", "person_1")
    section = _section(_editor(service))
    section.select_candidate(cand.id)
    section._open_button.click()
    section._compare_button.click()
    section._register_button.click()
    assert gateway.calls == [
        ("open", cand.id),
        ("compare", "person_2", "person_1"),
        ("register", "person_1"),
    ]


def test_buttons_do_nothing_without_gateway(qapp, service):
    cand = service.add_merge_candidate("person_1", "person_2")
    section = _section(_editor(service))
    section.select_candidate(cand.id)
    section._open_button.click()
    section._compare_button.click()
    section._register_button.click()


def test_create_candidate_and_refresh(qapp, service, gateway):
    section = _section(_editor(service))
    assert section.add_candidate_with("person_3") is True
    assert len(section.candidate_ids()) == 1
    assert len(service.data.merge_candidates) == 1
    assert section.error_text() == ""


def test_reject_self_and_duplicate(qapp, service, gateway):
    cand = service.add_merge_candidate("person_1", "person_2")
    service.set_candidate_assessment(cand.id, "rejected")
    section = _section(_editor(service))
    assert section.add_candidate_with("person_1") is False
    assert "själv" in section.error_text()
    assert section.add_candidate_with("person_2") is False
    assert "redan registrerat" in section.error_text()
    assert len(service.data.merge_candidates) == 1
    # The hidden existing pair is revealed and selected.
    assert section.candidate_ids() == [cand.id]
    assert section._selected_candidate_id() == cand.id


def test_refresh_on_service_and_gateway_events(qapp, service, gateway):
    section = _section(_editor(service))
    assert section.candidate_ids() == []
    cand = service.add_merge_candidate("person_1", "person_2")  # notifies listeners
    assert section.candidate_ids() == [cand.id]
    section.set_show_historical(True)
    service.data.merge_candidates.clear()
    gateway.merge_changed.emit()
    assert section.candidate_ids() == []
    assert section.show_historical() is True


def test_new_unsaved_person_disables_creation_until_stored(qapp, service, gateway):
    new_person = Person(id="person_9", sex="M", names=[Name(type="birth", given="Ny", surname="B")])
    editor = PersonEditor(service.data, new_person, project_service=service)
    section = _section(editor)
    assert not section._add_button.isEnabled()
    assert not section._save_first_label.isHidden()
    assert section.add_candidate_with("person_1") is False
    assert len(service.data.merge_candidates) == 0

    service.data.persons.append(new_person)
    editor.refresh_candidates()
    assert section._add_button.isEnabled()
    assert section._save_first_label.isHidden()
    assert section.add_candidate_with("person_1") is True
