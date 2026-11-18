"""Tests for the person list research filters (task 11.4)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import (
    ResearchAction,
    ResearchCase,
    ResearchEntityLink,
)
from slaktbusken.services.research_index import ResearchIndex
from slaktbusken.ui.person_list_panel import (
    FilterCriteria,
    build_person_display_list,
    filter_persons,
)


def _person(person_id: str, given: str, surname: str = "Test") -> Person:
    return Person(id=person_id, sex="M", names=[Name(type="birth", given=given, surname=surname)])


def _case(case_id: str, status: str, person_id: str) -> ResearchCase:
    return ResearchCase(
        id=case_id,
        title=case_id,
        status=status,
        primary_entity_ref=ResearchEntityLink("person", person_id),
    )


def _action(action_id: str, case_id: str, done: bool) -> ResearchAction:
    return ResearchAction(
        id=action_id,
        research_case_id=case_id,
        completed_date="2026-01-01" if done else None,
    )


@pytest.fixture
def project() -> ProjectData:
    """Five persons covering every research situation.

    anna  - no research at all
    bo    - one open case, a pending action
    cia   - one closed case with only completed actions
    dag   - one open case with no actions
    eva   - closed case with a pending action AND a separate open case with a
            completed action (the same-case combination rule)
    """
    data = ProjectData()
    data.persons = [
        _person("person_1", "Anna"),
        _person("person_2", "Bo"),
        _person("person_3", "Cia"),
        _person("person_4", "Dag"),
        _person("person_5", "Eva"),
    ]
    data.research_cases = [
        _case("case_bo", "open", "person_2"),
        _case("case_cia", "closed", "person_3"),
        _case("case_dag", "in_progress", "person_4"),
        _case("case_eva_closed", "closed", "person_5"),
        _case("case_eva_open", "open", "person_5"),
    ]
    data.research_actions = [
        _action("action_1", "case_bo", False),
        _action("action_2", "case_cia", True),
        _action("action_3", "case_eva_closed", False),
        _action("action_4", "case_eva_open", True),
    ]
    return data


def _run(data: ProjectData, **criteria: str) -> list[str]:
    index = ResearchIndex(data)
    display = build_person_display_list(
        data.persons, data.events, data.places, research_index=index
    )
    found = filter_persons(display, FilterCriteria(**criteria), None, index)
    return sorted(p.person_id for p in found)


ALL = ["person_1", "person_2", "person_3", "person_4", "person_5"]


class TestExistence:
    def test_all_is_no_filter(self, project: ProjectData) -> None:
        assert _run(project) == ALL

    def test_has(self, project: ProjectData) -> None:
        assert _run(project, research_existence="has") == [
            "person_2", "person_3", "person_4", "person_5",
        ]

    def test_none(self, project: ProjectData) -> None:
        assert _run(project, research_existence="none") == ["person_1"]

    def test_none_ignores_status_and_action(self, project: ProjectData) -> None:
        assert _run(
            project,
            research_existence="none",
            research_status="open",
            research_action="pending",
        ) == ["person_1"]


class TestStatus:
    def test_open_means_at_least_one_case_not_closed(self, project: ProjectData) -> None:
        assert _run(project, research_status="open") == ["person_2", "person_4", "person_5"]

    def test_closed_only_requires_cases_and_all_closed(self, project: ProjectData) -> None:
        # Eva has an open case too, so she is not "closed only". Anna has no cases.
        assert _run(project, research_status="closed_only") == ["person_3"]


class TestActions:
    def test_pending(self, project: ProjectData) -> None:
        assert _run(project, research_action="pending") == ["person_2", "person_5"]

    def test_completed(self, project: ProjectData) -> None:
        assert _run(project, research_action="completed") == ["person_3", "person_5"]

    def test_no_actions_means_a_case_without_any(self, project: ProjectData) -> None:
        assert _run(project, research_action="none") == ["person_4"]


class TestSameCaseRule:
    """Status and action conditions must hold for one and the same case."""

    def test_open_and_pending_needs_one_case_with_both(self, project: ProjectData) -> None:
        # Eva's pending action is on her closed case, her open case has none.
        assert _run(project, research_status="open", research_action="pending") == ["person_2"]

    def test_closed_only_with_pending(self, project: ProjectData) -> None:
        assert _run(project, research_status="closed_only", research_action="pending") == []

    def test_open_and_completed_matches_eva_through_her_open_case(
        self, project: ProjectData
    ) -> None:
        assert _run(project, research_status="open", research_action="completed") == ["person_5"]


class TestOtherFilters:
    def test_existing_filters_still_work_alongside_research(self, project: ProjectData) -> None:
        assert _run(project, given="bo") == ["person_2"]
        assert _run(project, given="a", research_existence="has") == ["person_3", "person_4", "person_5"]
        assert _run(project, given="anna", research_existence="has") == []

    def test_without_an_index_nobody_has_research(self, project: ProjectData) -> None:
        display = build_person_display_list(project.persons, project.events, project.places)
        assert filter_persons(display, FilterCriteria(research_existence="has")) == []
        assert len(filter_persons(display, FilterCriteria(research_existence="none"))) == 5

    def test_dangling_case_link_does_not_count(self, project: ProjectData) -> None:
        project.research_cases.append(_case("case_ghost", "open", "person_404"))
        assert "person_404" not in _run(project, research_existence="has")


class TestDialog:
    @pytest.fixture(scope="class")
    def qapp(self):
        return QApplication.instance() or QApplication([])

    def test_selection_reaches_criteria_and_clear_resets(self, qapp) -> None:
        from slaktbusken.ui.dialogs.filter_dialog import FilterDialog

        dialog = FilterDialog()
        received: list[FilterCriteria] = []
        dialog.filter_applied.connect(received.append)

        dialog._research_existence_combo.setCurrentIndex(
            dialog._research_existence_combo.findData("has")
        )
        dialog._research_status_combo.setCurrentIndex(
            dialog._research_status_combo.findData("open")
        )
        dialog._research_action_combo.setCurrentIndex(
            dialog._research_action_combo.findData("pending")
        )
        dialog._on_apply()
        assert (
            received[-1].research_existence,
            received[-1].research_status,
            received[-1].research_action,
        ) == ("has", "open", "pending")

        dialog._on_clear()
        dialog._on_apply()
        assert (
            received[-1].research_existence,
            received[-1].research_status,
            received[-1].research_action,
        ) == ("all", "all", "all")

    def test_none_disables_and_resets_the_dependent_filters(self, qapp) -> None:
        from slaktbusken.ui.dialogs.filter_dialog import FilterDialog

        dialog = FilterDialog()
        dialog._research_status_combo.setCurrentIndex(
            dialog._research_status_combo.findData("open")
        )
        dialog._research_existence_combo.setCurrentIndex(
            dialog._research_existence_combo.findData("none")
        )
        assert not dialog._research_status_combo.isEnabled()
        assert dialog._research_status_combo.currentData() == "all"
        assert not dialog._research_action_combo.isEnabled()
        dialog._on_clear()
        assert dialog._research_status_combo.isEnabled()
