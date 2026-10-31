"""Overview and case editor logic tests (task 8.5).

The pure rules are tested directly; the editor widget is exercised through its
public methods with the confirmation dialogs replaced.
"""

from __future__ import annotations

import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from slaktbusken.model.event import SourceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import (
    HypothesisComment,
    ResearchAction,
    ResearchCase,
    ResearchEntityLink,
    ResearchHypothesis,
)
from slaktbusken.model.source import Source
from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.research_editing import (
    WorkingCopyIdAllocator,
    add_action,
    add_comment,
    add_link,
    closing_warning_count,
    closing_warning_text,
    completed_actions,
    demote_primary,
    new_case_working_copy,
    pending_actions,
    remove_link,
    reorder_pending,
    set_action_completed,
    set_action_completed_date,
    set_primary,
)
from slaktbusken.services.research_service import open_working_copy
from slaktbusken.ui.dialogs.delete_research_case_dialog import (
    confirm_and_delete_case,
    delete_case_message,
)
from slaktbusken.ui.research_overview import (
    CaseFilter,
    build_overview_case_rows,
    build_overview_hypothesis_rows,
    build_todo_rows,
)


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def service() -> ProjectService:
    svc = ProjectService()
    data = ProjectData()
    data.persons = [
        Person(id="person_1", sex="M", names=[Name(type="birth", given="A", surname="B")]),
        Person(id="person_2", sex="F", names=[Name(type="birth", given="C", surname="D")]),
    ]
    data.sources = [Source(id="source_1", provider="p", source_type="t", title="K")]
    svc._project_data = data
    return svc


# ---------------------------------------------------------------------------
# Overview: to-do and hypothesis modes, case filters
# ---------------------------------------------------------------------------


class TestOverviewLogic:
    @pytest.fixture
    def data(self) -> ProjectData:
        data = ProjectData()
        data.research_cases = [
            ResearchCase(id="case_1", title="Öppet", status="open",
                         primary_entity_ref=ResearchEntityLink("person", "person_1")),
            ResearchCase(id="case_2", title="Stängt", status="closed",
                         priority="high"),
        ]
        data.research_actions = [
            ResearchAction(id="action_1", research_case_id="case_1", title="Sök A"),
            ResearchAction(id="action_2", research_case_id="case_2", title="Sök B"),
            ResearchAction(id="action_3", research_case_id="case_1", title="Klar",
                           completed_date="2026-01-01"),
        ]
        data.research_hypotheses = [
            ResearchHypothesis(id="hypothesis_1", research_case_id="case_1", statement="H1",
                               assessment="possible"),
            ResearchHypothesis(id="hypothesis_2", research_case_id="case_1", statement="H2"),
            ResearchHypothesis(id="hypothesis_3", research_case_id="case_404", statement="H3"),
        ]
        return data

    def test_default_todo_excludes_closed_cases(self, data: ProjectData) -> None:
        assert [r.action_id for r in build_todo_rows(data)] == ["action_1"]

    def test_include_toggle_adds_closed_cases_and_completed_never_listed(
        self, data: ProjectData
    ) -> None:
        rows = build_todo_rows(data, include_closed=True)
        assert [r.action_id for r in rows] == ["action_1", "action_2"]
        assert rows[1].case_title == "Stängt" and rows[1].case_id == "case_2"

    def test_todo_search(self, data: ProjectData) -> None:
        assert [r.action_id for r in build_todo_rows(data, True, "stängt")] == ["action_2"]

    def test_hypothesis_mode_has_one_row_per_hypothesis(self, data: ProjectData) -> None:
        rows = build_overview_hypothesis_rows(data)
        # Two hypotheses of one case give two rows; the orphan has no case to show.
        assert [r.hypothesis_id for r in rows] == ["hypothesis_1", "hypothesis_2"]
        assert rows[0].assessment_label == "Möjlig"
        assert rows[0].case_title == "Öppet"
        assert [r.hypothesis_id for r in build_overview_hypothesis_rows(data, "h2")] == [
            "hypothesis_2"
        ]

    def test_case_table_hides_closed_until_asked(self, data: ProjectData) -> None:
        assert [r.case_id for r in build_overview_case_rows(data)] == ["case_1"]
        shown = build_overview_case_rows(data, CaseFilter(include_closed=True))
        assert [r.case_id for r in shown] == ["case_1", "case_2"]

    def test_case_row_values_resolved_at_render_time(self, data: ProjectData) -> None:
        data.persons = [
            Person(id="person_1", sex="M", names=[Name(type="birth", given="A", surname="B")])
        ]
        row = build_overview_case_rows(data)[0]
        assert row.primary_label == "A B"
        assert (row.hypothesis_count, row.pending_count, row.action_count) == (2, 1, 2)
        data.persons = []
        assert build_overview_case_rows(data)[0].primary_label == "(saknat objekt)"

    def test_case_filters(self, data: ProjectData) -> None:
        everything = CaseFilter(include_closed=True)
        assert [r.case_id for r in build_overview_case_rows(data, CaseFilter(status="closed"))] == ["case_2"]
        assert [r.case_id for r in build_overview_case_rows(data, CaseFilter(priority="high", include_closed=True))] == ["case_2"]
        assert [r.case_id for r in build_overview_case_rows(data, CaseFilter(entity_type="person", include_closed=True))] == ["case_1"]
        assert [r.case_id for r in build_overview_case_rows(data, CaseFilter(entity_type="person", entity_id="person_9", include_closed=True))] == []
        assert [r.case_id for r in build_overview_case_rows(data, CaseFilter(pending="none", include_closed=True))] == []
        assert [r.case_id for r in build_overview_case_rows(data, CaseFilter(hypotheses="none", include_closed=True))] == ["case_2"]
        assert [r.case_id for r in build_overview_case_rows(data, CaseFilter(text="stäng", include_closed=True))] == ["case_2"]
        assert len(build_overview_case_rows(data, everything)) == 2


# ---------------------------------------------------------------------------
# Editing rules
# ---------------------------------------------------------------------------


def _action(action_id: str, order: int = 0, done: str | None = None) -> ResearchAction:
    return ResearchAction(id=action_id, research_case_id="case_1", sort_order=order,
                          completed_date=done)


class TestCompletion:
    def test_round_trip_preserves_everything_else(self) -> None:
        action = _action("action_1", 4)
        action.title, action.text = "T", "X"
        action.source_refs = [SourceRef("source_1", "primary", "n", ["date"])]
        before = copy.deepcopy(action)

        set_action_completed(action, True, today="2026-03-04")
        assert action.completed_date == "2026-03-04"
        set_action_completed(action, False)
        assert action == before

    def test_completing_keeps_an_existing_date(self) -> None:
        action = _action("action_1", done="2020-05")
        set_action_completed(action, True, today="2026-03-04")
        assert action.completed_date == "2020-05"

    def test_clearing_the_date_never_stores_an_empty_string(self) -> None:
        action = _action("action_1", done="2020-05-05")
        assert set_action_completed_date(action, "   ") is False
        assert action.completed_date is None
        assert set_action_completed_date(action, "2021") is True
        assert action.completed_date == "2021"


class TestOrdering:
    def test_pending_ordered_by_sort_order_then_id(self) -> None:
        actions = [_action("action_10", 1), _action("action_2", 1), _action("action_3", 0)]
        assert [a.id for a in pending_actions(actions)] == ["action_3", "action_2", "action_10"]

    def test_completed_newest_first_coarse_dates_use_first_day(self) -> None:
        actions = [
            _action("action_1", done="2020"),
            _action("action_2", done="2020-06"),
            _action("action_3", done="2020-06-15"),
            _action("action_4", done="2020-06-15"),
        ]
        assert [a.id for a in completed_actions(actions)] == [
            "action_3", "action_4", "action_2", "action_1",
        ]

    def test_reorder_assigns_sort_order_and_reopen_keeps_it(self, service: ProjectService) -> None:
        wc = new_case_working_copy(service.data)
        alloc = WorkingCopyIdAllocator(service.data, wc)
        a, b, c = (add_action(wc, alloc, t) for t in "abc")
        reorder_pending(wc, [c.id, a.id, b.id])
        assert [x.title for x in pending_actions(wc.actions)] == ["c", "a", "b"]
        assert sorted(x.sort_order for x in wc.actions) == [0, 1, 2]

        # Completing and reopening does not change sort_order (Requirement 8.4).
        order_before = a.sort_order
        set_action_completed(a, True)
        assert a.sort_order == order_before
        set_action_completed(a, False)
        assert [x.title for x in pending_actions(wc.actions)] == ["c", "a", "b"]

    def test_order_persists_through_commit(self, service: ProjectService) -> None:
        wc = new_case_working_copy(service.data)
        wc.case.title = "X"
        alloc = WorkingCopyIdAllocator(service.data, wc)
        a, b = add_action(wc, alloc, "a"), add_action(wc, alloc, "b")
        reorder_pending(wc, [b.id, a.id])
        service.commit_research_case_working_copy(wc)
        reopened = open_working_copy(service.data, wc.case.id)
        assert [x.title for x in pending_actions(reopened.actions)] == ["b", "a"]


class TestClosingWarning:
    def test_only_on_transition_into_closed_with_pending(self) -> None:
        pending = [_action("action_1"), _action("action_2"), _action("action_3", done="2020")]
        assert closing_warning_count("open", "closed", pending) == 2
        assert closing_warning_count("closed", "closed", pending) == 0
        assert closing_warning_count("open", "on_hold", pending) == 0
        assert closing_warning_count("open", "closed", [_action("action_3", done="2020")]) == 0
        assert "2 forskningsåtgärder utan färdigdatum" in closing_warning_text(2)


# ---------------------------------------------------------------------------
# Linked entities
# ---------------------------------------------------------------------------


class TestLinks:
    def _case(self) -> ResearchCase:
        return ResearchCase(
            id="case_1",
            primary_entity_ref=ResearchEntityLink("person", "person_1"),
            linked_entities=[ResearchEntityLink("person", "person_2"),
                             ResearchEntityLink("place", "place_1")],
        )

    def test_no_duplicate_links(self) -> None:
        case = self._case()
        assert add_link(case, "person", "person_1") is False
        assert add_link(case, "person", "person_2") is False
        assert add_link(case, "source", "source_1") is True

    def test_set_primary_keeps_the_set_of_links(self) -> None:
        case = self._case()
        before = {(l.entity_type, l.entity_id) for l in [case.primary_entity_ref, *case.linked_entities]}
        set_primary(case, "place", "place_1")
        after = {(l.entity_type, l.entity_id) for l in [case.primary_entity_ref, *case.linked_entities]}
        assert after == before
        assert (case.primary_entity_ref.entity_type, case.primary_entity_ref.entity_id) == ("place", "place_1")
        # The old primary is now an ordinary link.
        assert any(l.entity_id == "person_1" for l in case.linked_entities)

    def test_demote_primary(self) -> None:
        case = self._case()
        demote_primary(case)
        assert case.primary_entity_ref is None
        assert any(l.entity_id == "person_1" for l in case.linked_entities)

    def test_removing_the_primary_promotes_nobody(self) -> None:
        case = self._case()
        remove_link(case, "person", "person_1")
        assert case.primary_entity_ref is None
        assert len(case.linked_entities) == 2


class TestIdAllocator:
    def test_ids_do_not_touch_the_project_marks(self, service: ProjectService) -> None:
        wc = new_case_working_copy(service.data)
        alloc = WorkingCopyIdAllocator(service.data, wc)
        first = alloc.generate("research_action")
        second = alloc.generate("research_action")
        assert first != second
        assert service.data.id_high_water_marks == {}

    def test_ids_skip_every_id_ever_issued(self, service: ProjectService) -> None:
        case = service.add_research_case(ResearchCase(id="", title="x"))
        service.delete_research_case(case.id)
        assert new_case_working_copy(service.data).case.id == "case_2"

    def test_comment_defaults_to_today_and_leaves_assessment(self, service: ProjectService) -> None:
        wc = new_case_working_copy(service.data)
        alloc = WorkingCopyIdAllocator(service.data, wc)
        hypothesis = ResearchHypothesis(id="hypothesis_1", research_case_id=wc.case.id,
                                        assessment="strong_support")
        comment = add_comment(hypothesis, alloc, today="2026-05-06")
        assert comment.date == "2026-05-06" and comment.id.startswith("hypcomment_")
        assert hypothesis.assessment == "strong_support"


# ---------------------------------------------------------------------------
# Editor widget
# ---------------------------------------------------------------------------


class TestEditorWidget:
    def _saved_case(self, service: ProjectService) -> ResearchCase:
        case = service.add_research_case(ResearchCase(id="", title="Fråga"))
        service.add_research_action(ResearchAction(id="", research_case_id=case.id, title="a"))
        service.add_research_action(ResearchAction(id="", research_case_id=case.id, title="b"))
        return case

    def test_mandatory_title_blocks_save_and_writes_nothing(self, qapp, service) -> None:
        from slaktbusken.ui.editors.research_case_editor import ResearchCaseEditor

        editor = ResearchCaseEditor(service)
        editor._title_edit.setText("   ")
        editor.add_pending_action("x")
        assert editor.try_save() is False
        assert "Forskningsärendet måste ha en rubrik." in editor._error_label.text()
        assert service.data.research_cases == [] and service.data.research_actions == []

    def test_validation_error_leaves_project_unchanged_and_keeps_edits(self, qapp, service) -> None:
        from slaktbusken.ui.editors.research_case_editor import ResearchCaseEditor

        case = self._saved_case(service)
        before = copy.deepcopy(
            (service.data.research_cases, service.data.research_actions)
        )
        editor = ResearchCaseEditor(service, case.id)
        editor._title_edit.setText("Ny rubrik")
        editor.working_copy.actions[0].completed_date = "2026-02-30"
        assert editor.try_save() is False
        assert (service.data.research_cases, service.data.research_actions) == before
        assert editor.working_copy.case.title == "Ny rubrik"

    def test_close_with_pending_confirm_and_cancel(self, qapp, service) -> None:
        from slaktbusken.ui.editors.research_case_editor import ResearchCaseEditor

        case = self._saved_case(service)
        editor = ResearchCaseEditor(service, case.id)
        asked: list[int] = []

        editor._confirm_close_with_pending = lambda n: (asked.append(n) or False)
        assert editor.set_status("closed") is False
        assert editor.working_copy.case.status == "open"
        assert editor._status_combo.currentData() == "open"

        editor._confirm_close_with_pending = lambda n: (asked.append(n) or True)
        assert editor.set_status("closed") is True
        assert asked == [2, 2]
        assert all(a.completed_date is None for a in editor.working_copy.actions)

        # Saving an already closed case does not ask again.
        assert editor.try_save() is True
        reopened = ResearchCaseEditor(service, case.id)
        reopened._confirm_close_with_pending = lambda n: pytest.fail("must not ask")
        assert reopened.working_copy.case.status == "closed"
        assert reopened.try_save() is True

    def test_reopening_keeps_hypotheses_actions_and_conclusion(self, qapp, service) -> None:
        from slaktbusken.ui.editors.research_case_editor import ResearchCaseEditor

        case = self._saved_case(service)
        case.status, case.conclusion = "closed", "Klart"
        service.update_research_case(case)
        service.add_research_hypothesis(
            ResearchHypothesis(id="", research_case_id=case.id, statement="H",
                               comments=[HypothesisComment(id="", text="t")])
        )
        before = copy.deepcopy(
            (service.data.research_actions, service.data.research_hypotheses)
        )
        editor = ResearchCaseEditor(service, case.id)
        editor.set_status("open")
        assert editor.try_save()
        assert (service.data.research_actions, service.data.research_hypotheses) == before
        assert service.data.research_cases[0].conclusion == "Klart"

    def test_adding_pending_action_to_closed_case_informs_and_keeps_status(
        self, qapp, service
    ) -> None:
        from slaktbusken.ui.editors.research_case_editor import ResearchCaseEditor

        case = service.add_research_case(ResearchCase(id="", title="x", status="closed"))
        editor = ResearchCaseEditor(service, case.id)
        shown: list[int] = []
        editor._show_closed_case_info = lambda: shown.append(1)
        editor.add_pending_action("ny")
        assert shown == [1]
        assert editor.working_copy.case.status == "closed"
        assert len(editor.working_copy.actions) == 1

    def test_completion_checkbox_moves_action_between_lists(self, qapp, service) -> None:
        from slaktbusken.ui.editors.research_case_editor import ResearchCaseEditor

        case = self._saved_case(service)
        editor = ResearchCaseEditor(service, case.id)
        assert (editor._pending_list.count(), editor._done_list.count()) == (2, 0)
        editor._pending_list.setCurrentRow(0)
        editor._action_done.click()
        assert (editor._pending_list.count(), editor._done_list.count()) == (1, 1)
        editor._action_done.click()
        assert (editor._pending_list.count(), editor._done_list.count()) == (2, 0)

    def test_delete_confirmation_cancel_and_confirm(self, qapp, service) -> None:
        from slaktbusken.ui.editors.research_case_editor import ResearchCaseEditor

        case = self._saved_case(service)
        editor = ResearchCaseEditor(service, case.id)
        deleted: list[str] = []
        editor.deleted.connect(deleted.append)

        assert editor.delete_case(ask=lambda message: False) is False
        assert deleted == [] and len(service.data.research_cases) == 1

        assert editor.delete_case(ask=lambda message: True) is True
        assert deleted == [case.id]
        assert service.data.research_cases == [] and service.data.research_actions == []


class TestDeleteConfirmation:
    def test_message_names_the_counts(self, service: ProjectService) -> None:
        case = service.add_research_case(ResearchCase(id="", title="x"))
        service.add_research_hypothesis(
            ResearchHypothesis(id="", research_case_id=case.id,
                               comments=[HypothesisComment(id=""), HypothesisComment(id="")])
        )
        service.add_research_action(ResearchAction(id="", research_case_id=case.id))
        seen: list[str] = []
        assert confirm_and_delete_case(None, service, case.id,
                                       ask=lambda m: (seen.append(m) or False)) is False
        assert seen == [
            "Att ta bort forskningsärendet tar även bort 1 hypoteser, 2 hypoteskommentarer "
            "och 1 forskningsåtgärder. Detta kan inte ångras."
        ]
        assert len(service.data.research_cases) == 1  # cancel changed nothing

    def test_other_cases_survive(self, service: ProjectService) -> None:
        keep = service.add_research_case(ResearchCase(id="", title="behåll"))
        drop = service.add_research_case(ResearchCase(id="", title="släng"))
        assert confirm_and_delete_case(None, service, drop.id, ask=lambda m: True)
        assert [c.id for c in service.data.research_cases] == [keep.id]

    def test_wording_is_distinct_from_removing_a_link(self) -> None:
        from slaktbusken.services.research_service import ResearchChildCounts

        text = delete_case_message(ResearchChildCounts(0, 0, 0))
        assert "forskningsärendet" in text and "kopplingen" not in text
