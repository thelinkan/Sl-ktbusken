"""Service and integrity tests for research cases (task 6.5).

Covers the ProjectService research operations, the transactional working copy
commit, reference integrity on delete / merge / association removal, the
cascading case delete, and the research-changed notification.
"""

from __future__ import annotations

import copy

import pytest

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
from slaktbusken.services.delete_service import DeleteService
from slaktbusken.services.project_service import ProjectService, ValidationError
from slaktbusken.services.research_service import (
    count_case_children,
    delete_case_cascade,
    open_working_copy,
    remove_entity_association,
)


def _person(person_id: str) -> Person:
    return Person(id=person_id, sex="M", names=[Name(type="birth", given="A", surname="B")])


@pytest.fixture
def service() -> ProjectService:
    svc = ProjectService()
    data = ProjectData()
    data.persons = [_person("person_1"), _person("person_2"), _person("person_3")]
    data.sources = [
        Source(id="source_1", provider="p", source_type="t", title="K1"),
        Source(id="source_2", provider="p", source_type="t", title="K2"),
    ]
    svc._project_data = data
    return svc


def _make_case(svc: ProjectService, title: str = "Fråga") -> ResearchCase:
    return svc.add_research_case(
        ResearchCase(
            id="",
            title=title,
            primary_entity_ref=ResearchEntityLink("person", "person_1", "candidate"),
            linked_entities=[ResearchEntityLink("person", "person_2")],
        )
    )


class TestDirtyAndNotification:
    def test_every_mutation_sets_dirty_and_notifies(self, service: ProjectService) -> None:
        calls: list[int] = []
        service.add_research_listener(lambda: calls.append(1))

        def clean() -> None:
            service._dirty = False

        case = _make_case(service)
        assert service._dirty and len(calls) == 1
        clean()
        hypothesis = service.add_research_hypothesis(
            ResearchHypothesis(id="", research_case_id=case.id, statement="H")
        )
        assert service._dirty and len(calls) == 2
        clean()
        action = service.add_research_action(ResearchAction(id="", research_case_id=case.id))
        assert service._dirty and len(calls) == 3
        clean()
        action.title = "Ny"
        service.update_research_action(action)
        hypothesis.statement = "H2"
        service.update_research_hypothesis(hypothesis)
        case.title = "Ny rubrik"
        service.update_research_case(case)
        assert service._dirty and len(calls) == 6
        clean()
        assert service.delete_research_action(action.id)
        assert service.delete_research_hypothesis(hypothesis.id)
        assert service.delete_research_case(case.id)
        assert service._dirty and len(calls) == 9

    def test_noop_delete_does_not_dirty_or_notify(self, service: ProjectService) -> None:
        calls: list[int] = []
        service.add_research_listener(lambda: calls.append(1))
        assert service.delete_research_case("case_404") is False
        assert service.delete_research_hypothesis("hypothesis_404") is False
        assert service.delete_research_action("action_404") is False
        assert not service._dirty and calls == []

    def test_broken_listener_does_not_stop_others(self, service: ProjectService) -> None:
        calls: list[int] = []

        def boom() -> None:
            raise RuntimeError("fel")

        service.add_research_listener(boom)
        service.add_research_listener(lambda: calls.append(1))
        _make_case(service)
        assert calls == [1]

    def test_removed_listener_is_not_called(self, service: ProjectService) -> None:
        calls: list[int] = []
        remove = service.add_research_listener(lambda: calls.append(1))
        remove()
        remove()  # harmless twice
        _make_case(service)
        assert calls == []


class TestTransactionalCommit:
    def _two_cases(self, svc: ProjectService) -> tuple[ResearchCase, ResearchCase]:
        first = _make_case(svc, "Ett")
        second = _make_case(svc, "Två")
        svc.add_research_action(ResearchAction(id="", research_case_id=first.id, title="a"))
        svc.add_research_action(ResearchAction(id="", research_case_id=second.id, title="b"))
        return first, second

    def test_invalid_child_writes_nothing(self, service: ProjectService) -> None:
        first, _ = self._two_cases(service)
        before = copy.deepcopy(service.data)
        calls: list[int] = []
        service.add_research_listener(lambda: calls.append(1))
        service._dirty = False

        wc = open_working_copy(service.data, first.id)
        wc.case.title = "Ändrad"
        wc.actions[0].completed_date = "2026-02-30"
        with pytest.raises(ValidationError):
            service.commit_research_case_working_copy(wc)

        assert service.data.research_cases == before.research_cases
        assert service.data.research_actions == before.research_actions
        assert service.data.research_hypotheses == before.research_hypotheses
        assert service.data.id_high_water_marks == before.id_high_water_marks
        assert not service._dirty and calls == []

    def test_all_errors_are_reported_together(self, service: ProjectService) -> None:
        first, _ = self._two_cases(service)
        wc = open_working_copy(service.data, first.id)
        wc.case.title = " "
        wc.actions[0].completed_date = "nonsense"
        with pytest.raises(ValidationError) as excinfo:
            service.commit_research_case_working_copy(wc)
        assert "Forskningsärendet måste ha en rubrik." in excinfo.value.errors
        assert len(excinfo.value.errors) >= 2

    def test_child_of_another_case_is_rejected(self, service: ProjectService) -> None:
        first, second = self._two_cases(service)
        wc = open_working_copy(service.data, first.id)
        wc.actions.append(ResearchAction(id="action_99", research_case_id=second.id))
        with pytest.raises(ValidationError):
            service.commit_research_case_working_copy(wc)
        assert len(service.data.research_actions) == 2

    def test_id_collision_with_another_case_is_rejected(self, service: ProjectService) -> None:
        first, second = self._two_cases(service)
        other_action_id = next(
            a.id for a in service.data.research_actions if a.research_case_id == second.id
        )
        wc = open_working_copy(service.data, first.id)
        wc.actions.append(ResearchAction(id=other_action_id, research_case_id=first.id))
        with pytest.raises(ValidationError):
            service.commit_research_case_working_copy(wc)

    def test_cancelled_working_copy_changes_nothing(self, service: ProjectService) -> None:
        first, _ = self._two_cases(service)
        before = copy.deepcopy(service.data)
        wc = open_working_copy(service.data, first.id)
        wc.case.title = "Kasseras"
        wc.hypotheses.append(ResearchHypothesis(id="hypothesis_9", research_case_id=first.id))
        wc.actions.clear()
        # The editor was cancelled: the working copy is simply dropped.
        assert service.data.research_cases == before.research_cases
        assert service.data.research_actions == before.research_actions
        assert service.data.research_hypotheses == before.research_hypotheses

    def test_valid_commit_is_atomic_and_notifies_once(self, service: ProjectService) -> None:
        first, second = self._two_cases(service)
        calls: list[int] = []
        service.add_research_listener(lambda: calls.append(1))
        service._dirty = False
        wc = open_working_copy(service.data, first.id)
        wc.case.title = "Ändrad"
        wc.hypotheses.append(
            ResearchHypothesis(
                id="hypothesis_5",
                research_case_id=first.id,
                comments=[HypothesisComment(id="hypcomment_5", date="2026-01-01", text="t")],
            )
        )
        wc.actions.append(ResearchAction(id="action_5", research_case_id=first.id))
        diff = service.commit_research_case_working_copy(wc)
        assert diff.case_updated and diff.hypotheses_created == ["hypothesis_5"]
        assert diff.actions_created == ["action_5"]
        assert service._dirty and calls == [1]
        # The other case is untouched.
        assert [a.title for a in service.data.research_actions if a.research_case_id == second.id] == ["b"]
        # Marks reflect the committed ids so they are never issued again.
        assert service.data.id_high_water_marks["hypothesis_"] == 5
        assert service.data.id_high_water_marks["hypcomment_"] == 5

    def test_unchanged_copy_is_a_noop(self, service: ProjectService) -> None:
        first, _ = self._two_cases(service)
        calls: list[int] = []
        service.add_research_listener(lambda: calls.append(1))
        service._dirty = False
        diff = service.commit_research_case_working_copy(open_working_copy(service.data, first.id))
        assert diff.is_empty and not service._dirty and calls == []

    def test_new_case_commit_and_blank_date_normalized(self, service: ProjectService) -> None:
        wc = open_working_copy(service.data, _make_case(service).id)
        wc.case = ResearchCase(id="case_7", title="Ny")
        wc.hypotheses.clear()
        wc.actions = [ResearchAction(id="action_7", research_case_id="case_7")]
        wc.actions[0].completed_date = "  "
        service.commit_research_case_working_copy(wc)
        stored = next(a for a in service.data.research_actions if a.id == "action_7")
        assert stored.completed_date is None


class TestReferenceIntegrity:
    def test_deleting_a_referenced_person_keeps_research(self, service: ProjectService) -> None:
        case = _make_case(service)
        service.add_research_hypothesis(
            ResearchHypothesis(
                id="",
                research_case_id=case.id,
                linked_entities=[ResearchEntityLink("person", "person_1")],
            )
        )
        before = copy.deepcopy(
            (service.data.research_cases, service.data.research_hypotheses)
        )
        calls: list[int] = []
        service.add_research_listener(lambda: calls.append(1))

        consequences = DeleteService(service).compute_consequences("person_1")
        assert consequences.research_case_count == 1
        assert consequences.research_hypothesis_count == 1
        DeleteService(service).execute_deletion("person_1")

        assert [p.id for p in service.data.persons] == ["person_2", "person_3"]
        # Everything is kept, including the now stale references.
        assert (service.data.research_cases, service.data.research_hypotheses) == before
        assert calls == [1]

    def test_deleting_an_unreferenced_person_does_not_notify(
        self, service: ProjectService
    ) -> None:
        _make_case(service)
        calls: list[int] = []
        service.add_research_listener(lambda: calls.append(1))
        DeleteService(service).execute_deletion("person_3")
        assert calls == []

    def test_merge_rewires_collapses_and_preserves_details(self, service: ProjectService) -> None:
        case = service.add_research_case(
            ResearchCase(
                id="",
                title="Sammanslagning",
                primary_entity_ref=ResearchEntityLink("person", "person_2", "candidate"),
                linked_entities=[
                    ResearchEntityLink("person", "person_3", ""),
                    ResearchEntityLink("person", "person_2", "identified_person"),
                ],
            )
        )
        action = service.add_research_action(
            ResearchAction(
                id="",
                research_case_id=case.id,
                source_refs=[
                    SourceRef(
                        source_id="source_1",
                        quality="secondary",
                        note="s. 12",
                        aspects=["date"],
                    )
                ],
            )
        )
        calls: list[int] = []
        service.add_research_listener(lambda: calls.append(1))

        person_result = service.merge_research_references("person", "person_2", "person_3")
        assert person_result.links_rewired >= 1
        links = [service.data.research_cases[0].primary_entity_ref] + list(
            service.data.research_cases[0].linked_entities
        )
        assert all(link.entity_id == "person_3" for link in links if link is not None)
        # Duplicates collapsed to one link to the survivor, role preserved.
        survivors = [link for link in links if link is not None and link.entity_id == "person_3"]
        assert len(survivors) == 1
        assert survivors[0].role == "candidate"

        source_result = service.merge_research_references("source", "source_1", "source_2")
        assert source_result.source_refs_rewired == 1
        ref = service.data.research_actions[0].source_refs[0]
        assert (ref.source_id, ref.quality, ref.note, ref.aspects) == (
            "source_2", "secondary", "s. 12", ["date"],
        )
        assert action.id == service.data.research_actions[0].id
        assert len(calls) == 2

    def test_merge_without_references_is_a_noop(self, service: ProjectService) -> None:
        _make_case(service)
        service._dirty = False
        calls: list[int] = []
        service.add_research_listener(lambda: calls.append(1))
        result = service.merge_research_references("person", "person_404", "person_3")
        assert result.links_rewired == 0
        assert not service._dirty and calls == []

    def test_remove_association_keeps_case_and_does_not_promote(self) -> None:
        case = ResearchCase(
            id="case_1",
            title="x",
            primary_entity_ref=ResearchEntityLink("person", "person_1"),
            linked_entities=[
                ResearchEntityLink("person", "person_2"),
                ResearchEntityLink("place", "place_1"),
            ],
        )
        remove_entity_association(case, "person", "person_1")
        assert case.primary_entity_ref is None
        assert [(l.entity_type, l.entity_id) for l in case.linked_entities] == [
            ("person", "person_2"),
            ("place", "place_1"),
        ]
        remove_entity_association(case, "place", "place_1")
        assert [l.entity_id for l in case.linked_entities] == ["person_2"]


class TestCascadeDelete:
    def test_counts_and_only_own_children_removed(self, service: ProjectService) -> None:
        first = _make_case(service, "Ett")
        second = _make_case(service, "Två")
        service.add_research_hypothesis(
            ResearchHypothesis(
                id="",
                research_case_id=first.id,
                comments=[HypothesisComment(id="", text="a"), HypothesisComment(id="", text="b")],
            )
        )
        service.add_research_hypothesis(
            ResearchHypothesis(
                id="",
                research_case_id=second.id,
                comments=[HypothesisComment(id="", text="c")],
            )
        )
        service.add_research_action(ResearchAction(id="", research_case_id=first.id))
        service.add_research_action(ResearchAction(id="", research_case_id=first.id))
        service.add_research_action(ResearchAction(id="", research_case_id=second.id))

        counts = count_case_children(service.data, first.id)
        assert (counts.hypotheses, counts.comments, counts.actions) == (1, 2, 2)

        removed = delete_case_cascade(service.data, first.id)
        assert (removed.hypotheses, removed.comments, removed.actions) == (1, 2, 2)
        assert [c.id for c in service.data.research_cases] == [second.id]
        assert [h.research_case_id for h in service.data.research_hypotheses] == [second.id]
        assert [a.research_case_id for a in service.data.research_actions] == [second.id]

    def test_unknown_case_raises_and_changes_nothing(self, service: ProjectService) -> None:
        _make_case(service)
        with pytest.raises(KeyError):
            delete_case_cascade(service.data, "case_404")
        assert len(service.data.research_cases) == 1

    def test_deleted_ids_are_not_reused(self, service: ProjectService) -> None:
        case = _make_case(service)
        assert service.delete_research_case(case.id)
        assert service.new_research_id("research_case") == "case_2"

    def test_deleted_case_disappears_from_a_registered_view(
        self, service: ProjectService
    ) -> None:
        from slaktbusken.ui.research_overview import build_overview_case_rows

        case = _make_case(service)
        shown: list[list[str]] = []

        def refresh_view() -> None:
            shown.append([r.case_id for r in build_overview_case_rows(service.data)])

        service.add_research_listener(refresh_view)
        service.update_research_case(case)
        assert shown[-1] == [case.id]
        service.delete_research_case(case.id)
        assert shown[-1] == []
