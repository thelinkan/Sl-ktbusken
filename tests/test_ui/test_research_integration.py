"""Integration-logic tests for research in the entity editors (task 9.5).

The editors talk to the application through the research gateway, so a fake
gateway stands in for ``Application`` here; no real settings file or main window
is touched.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from slaktbusken.model.event import SourceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import (
    ResearchAction,
    ResearchCase,
    ResearchEntityLink,
    ResearchHypothesis,
)
from slaktbusken.model.source import Source
from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.research_editing import new_case_working_copy
from slaktbusken.services.research_index import ResearchIndex
from slaktbusken.ui import research_gateway
from slaktbusken.ui.widgets.research_tab import (
    ResearchTab,
    build_case_rows,
    build_hypothesis_rows,
)
from slaktbusken.ui.widgets.source_research_tab import (
    SourceResearchSection,
    build_action_usage_rows,
    build_source_case_rows,
    distinct_case_count,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _person(person_id: str, given: str) -> Person:
    return Person(id=person_id, sex="M", names=[Name(type="birth", given=given, surname="B")])


@pytest.fixture
def service() -> ProjectService:
    svc = ProjectService()
    data = ProjectData()
    data.persons = [_person("person_1", "Anna"), _person("person_2", "Bo")]
    data.places = [Place(id="place_1", type="parish", name="Socken")]
    data.sources = [Source(id="source_1", provider="p", source_type="t", title="Kyrkbok")]
    svc._project_data = data
    return svc


class _Signals(QObject):
    changed = Signal()


class FakeGateway:
    """Records what the editors ask for, the way Application would handle it."""

    def __init__(self, service: ProjectService) -> None:
        self._service = service
        self._signals = _Signals()
        service.add_research_listener(self._signals.changed.emit)
        self.calls: list[tuple] = []
        self.link_choice: str | None = None

    @property
    def research_changed(self):
        return self._signals.changed

    def open_research_case(self, case_id: str) -> None:
        self.calls.append(("open", case_id))

    def open_research_action(self, case_id: str, action_id: str) -> None:
        self.calls.append(("open_action", case_id, action_id))

    def create_research_case(self, entity_type: str, entity_id: str) -> None:
        self.calls.append(("create", entity_type, entity_id))
        wc = new_case_working_copy(
            self._service.data, ResearchEntityLink(entity_type, entity_id)
        )
        wc.case.title = "Skapad från redigeraren"
        self._service.commit_research_case_working_copy(wc)

    def link_research_case(self, entity_type: str, entity_id: str) -> None:
        self.calls.append(("link", entity_type, entity_id))
        if self.link_choice:
            self._service.link_research_case_entity(self.link_choice, entity_type, entity_id)

    def unlink_research_case(self, case_id: str, entity_type: str, entity_id: str) -> None:
        self.calls.append(("unlink", case_id, entity_type, entity_id))
        self._service.unlink_research_case_entity(case_id, entity_type, entity_id)

    def show_research_for_entity(self, entity_type: str, entity_id: str) -> None:
        self.calls.append(("show", entity_type, entity_id))


@pytest.fixture
def gateway(service: ProjectService):
    fake = FakeGateway(service)
    research_gateway.set_research_gateway(fake)
    yield fake
    research_gateway.set_research_gateway(None)


class TestCreateAndLinkFromAnEditor:
    def test_create_from_person_sets_the_primary_entity(self, qapp, service, gateway) -> None:
        tab = ResearchTab(service.data, "person", "person_1")
        research_gateway.connect_research_tab(tab)

        tab._new_button.click()

        (case,) = service.data.research_cases
        assert case.primary_entity_ref == ResearchEntityLink("person", "person_1")
        # The tab refreshed itself through research_changed.
        assert tab._cases_tree.topLevelItemCount() == 1

    def test_link_existing_and_remove_the_association(self, qapp, service, gateway) -> None:
        case = service.add_research_case(ResearchCase(id="", title="Befintligt"))
        service.add_research_action(ResearchAction(id="", research_case_id=case.id))
        tab = ResearchTab(service.data, "place", "place_1")
        research_gateway.connect_research_tab(tab)

        gateway.link_choice = case.id
        tab._link_button.click()
        assert tab._cases_tree.topLevelItemCount() == 1

        tab._cases_tree.topLevelItem(0).setSelected(True)
        tab._remove_button.click()
        assert tab._cases_tree.topLevelItemCount() == 0
        # The case and its action are kept.
        assert [c.id for c in service.data.research_cases] == [case.id]
        assert len(service.data.research_actions) == 1

    def test_unsaved_entity_cannot_create_or_link(self, qapp, service, gateway) -> None:
        section = research_gateway.ResearchSection(service.data, "place", lambda: None)
        assert not section.tab._new_button.isEnabled()
        assert not section.tab._link_button.isEnabled()
        section.tab._new_button.click()
        assert gateway.calls == []

    def test_open_goes_through_the_gateway(self, qapp, service, gateway) -> None:
        case = service.add_research_case(
            ResearchCase(id="", title="x", primary_entity_ref=ResearchEntityLink("person", "person_2"))
        )
        tab = ResearchTab(service.data, "person", "person_2")
        research_gateway.connect_research_tab(tab)
        tab._cases_tree.topLevelItem(0).setSelected(True)
        tab._open_button.click()
        assert gateway.calls == [("open", case.id)]

    def test_section_follows_the_editor_selection(self, qapp, service, gateway) -> None:
        service.add_research_case(
            ResearchCase(id="", title="Om socknen", primary_entity_ref=ResearchEntityLink("place", "place_1"))
        )
        current = {"id": None}
        section = research_gateway.ResearchSection(service.data, "place", lambda: current["id"])
        assert section.tab._cases_tree.topLevelItemCount() == 0
        current["id"] = "place_1"
        section.refresh()
        assert section.tab._cases_tree.topLevelItemCount() == 1


class TestSharedModel:
    def test_same_case_for_every_linked_entity(self, service) -> None:
        case = service.add_research_case(
            ResearchCase(
                id="",
                title="Gemensam",
                primary_entity_ref=ResearchEntityLink("person", "person_1"),
                linked_entities=[
                    ResearchEntityLink("place", "place_1"),
                    ResearchEntityLink("source", "source_1"),
                ],
            )
        )
        index = ResearchIndex(service.data)
        for entity in [("person", "person_1"), ("place", "place_1"), ("source", "source_1")]:
            assert [c.id for c in index.cases_for_entity(*entity)] == [case.id]

        # An edit made from one place is current everywhere.
        case.title = "Ändrad"
        service.update_research_case(case)
        for entity in [("person", "person_1"), ("place", "place_1")]:
            assert build_case_rows(ResearchIndex(service.data), *entity)[0].title == "Ändrad"

    def test_hypotheses_section_does_not_change_counts(self, service) -> None:
        case = service.add_research_case(
            ResearchCase(id="", title="Om Anna", primary_entity_ref=ResearchEntityLink("person", "person_1"))
        )
        service.add_research_hypothesis(
            ResearchHypothesis(
                id="",
                research_case_id=case.id,
                statement="Bo är Annas bror",
                linked_entities=[ResearchEntityLink("person", "person_2")],
            )
        )
        index = ResearchIndex(service.data)
        rows = build_hypothesis_rows(index, "person", "person_2")
        assert [(r.statement, r.case_title) for r in rows] == [("Bo är Annas bror", "Om Anna")]
        # Bo appears in a hypothesis, but no case is linked to him directly.
        assert build_case_rows(index, "person", "person_2") == []
        counts = index.counts_for_entity("person", "person_2")
        assert (counts.non_closed, counts.total) == (0, 0)


class TestSourceResearch:
    @pytest.fixture
    def source_data(self, service: ProjectService) -> ProjectService:
        about = service.add_research_case(
            ResearchCase(id="", title="Om källan", primary_entity_ref=ResearchEntityLink("source", "source_1"))
        )
        other = service.add_research_case(ResearchCase(id="", title="Annat ärende"))
        service.add_research_action(
            ResearchAction(id="", research_case_id=other.id, title="Granska",
                           source_refs=[SourceRef("source_1", "primary")])
        )
        service.add_research_action(
            ResearchAction(id="", research_case_id=other.id, title="Granska igen",
                           completed_date="2026-01-01",
                           source_refs=[SourceRef("source_1", "primary"), SourceRef("source_1", "secondary")])
        )
        service.add_research_action(
            ResearchAction(id="", research_case_id=about.id, title="Kontrollera sidnumrering",
                           source_refs=[SourceRef("source_1", "primary")])
        )
        return service

    def test_direct_cases_and_action_usage(self, source_data) -> None:
        data = source_data.data
        index = ResearchIndex(data)
        assert [r.title for r in build_source_case_rows(index, "source_1")] == ["Om källan"]
        usage = build_action_usage_rows(data, index, "source_1")
        # Every citing action, including those of a case not linked to the source,
        # each listed once even when it cites the source twice.
        assert sorted(r.title for r in usage) == ["Granska", "Granska igen", "Kontrollera sidnumrering"]
        done = next(r for r in usage if r.title == "Granska igen")
        assert (done.state_label, done.completed_date) == ("Genomförd", "2026-01-01")
        assert {r.case_title for r in usage} == {"Annat ärende", "Om källan"}

    def test_unique_case_count(self, source_data) -> None:
        data = source_data.data
        index = ResearchIndex(data)
        cases = build_source_case_rows(index, "source_1")
        usage = build_action_usage_rows(data, index, "source_1")
        assert distinct_case_count(cases, usage) == 2

    def test_section_navigation(self, qapp, source_data, gateway) -> None:
        section = SourceResearchSection(source_data.data, lambda: "source_1")
        research_gateway.connect_source_research(section)
        assert section._actions_tree.topLevelItemCount() == 3

        section._actions_tree.topLevelItem(0).setSelected(True)
        section._open_action_button.click()
        section._open_action_case_button.click()
        assert gateway.calls[0][0] == "open_action"
        assert gateway.calls[1][0] == "open"
        assert gateway.calls[1][1] == gateway.calls[0][1]

        section._new_button.click()
        assert gateway.calls[-1] == ("create", "source", "source_1")


class TestNavigationKeepsUnsavedEdits:
    def test_research_actions_do_not_touch_an_open_person_editor(
        self, qapp, service, gateway
    ) -> None:
        from slaktbusken.ui.editors.person_editor import PersonEditor

        person = service.data.persons[0]
        editor = PersonEditor(service.data, person)
        names = editor._ui.names_table
        names.item(0, 1).setText("Ändrat förnamn")

        editor._forskning_tab._new_button.click()

        # The case was created through the gateway; the editor's unsaved edit
        # is still in the form and the person itself is unchanged until saved.
        assert len(service.data.research_cases) == 1
        assert names.item(0, 1).text() == "Ändrat förnamn"
        assert person.names[0].given == "Anna"

    def test_person_editor_has_a_forskning_tab(self, qapp, service, gateway) -> None:
        from slaktbusken.ui.editors.person_editor import PersonEditor

        editor = PersonEditor(service.data, service.data.persons[0])
        tabs = editor._ui.tab_widget
        texts = [tabs.tabText(i) for i in range(tabs.count())]
        assert "Forskning" in texts
