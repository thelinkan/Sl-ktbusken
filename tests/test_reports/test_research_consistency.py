"""Consistency report tests for research data (task 12.4)."""

from __future__ import annotations

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
from slaktbusken.reports.research_consistency import (
    SEVERITY_ERROR,
    SEVERITY_INFO,
    check_research_consistency,
    generate_research_consistency_report,
)


def _base() -> ProjectData:
    data = ProjectData()
    data.persons = [
        Person(id="person_1", sex="M", names=[Name(type="birth", given="A", surname="B")])
    ]
    data.sources = [Source(id="source_1", provider="p", source_type="t", title="K")]
    return data


def _healthy_case(case_id: str = "case_1") -> ResearchCase:
    return ResearchCase(
        id=case_id,
        title="Frisk",
        primary_entity_ref=ResearchEntityLink("person", "person_1"),
    )


def _by_type(issues, check_type):
    return [i for i in issues if i.check_type == check_type]


class TestErrorChecks:
    def test_clean_project_has_no_errors(self) -> None:
        data = _base()
        data.research_cases = [_healthy_case()]
        data.research_actions = [ResearchAction(id="action_1", research_case_id="case_1")]
        assert [i for i in check_research_consistency(data) if i.severity == SEVERITY_ERROR] == []

    def test_missing_entity_link_identifies_the_reference(self) -> None:
        data = _base()
        case = _healthy_case()
        case.linked_entities = [ResearchEntityLink("place", "place_404")]
        data.research_cases = [case]
        (issue,) = _by_type(check_research_consistency(data), "missing_entity")
        assert issue.severity == SEVERITY_ERROR
        assert issue.case_id == "case_1"
        assert (issue.ref_entity_type, issue.ref_entity_id) == ("place", "place_404")
        assert "Frisk" in issue.message

    def test_unknown_entity_type(self) -> None:
        data = _base()
        case = _healthy_case()
        case.linked_entities = [ResearchEntityLink("spaceship", "x_1")]
        data.research_cases = [case]
        (issue,) = _by_type(check_research_consistency(data), "unknown_entity_type")
        assert issue.ref_entity_type == "spaceship"

    def test_duplicate_link_in_case(self) -> None:
        data = _base()
        case = _healthy_case()
        case.linked_entities = [ResearchEntityLink("person", "person_1")]
        data.research_cases = [case]
        (issue,) = _by_type(check_research_consistency(data), "duplicate_link")
        assert issue.case_id == "case_1"

    def test_invalid_status_priority_and_assessment(self) -> None:
        data = _base()
        case = _healthy_case()
        case.status = "weird"
        case.priority = "urgent"
        data.research_cases = [case]
        data.research_hypotheses = [
            ResearchHypothesis(id="hypothesis_1", research_case_id="case_1", assessment="maybe")
        ]
        issues = check_research_consistency(data)
        assert _by_type(issues, "invalid_status")[0].case_id == "case_1"
        assert _by_type(issues, "invalid_priority")[0].case_id == "case_1"
        hypothesis_issue = _by_type(issues, "invalid_assessment")[0]
        assert hypothesis_issue.hypothesis_id == "hypothesis_1"

    def test_orphan_hypothesis_and_action(self) -> None:
        data = _base()
        data.research_hypotheses = [
            ResearchHypothesis(id="hypothesis_1", research_case_id="case_404")
        ]
        data.research_actions = [ResearchAction(id="action_1", research_case_id="case_404")]
        issues = check_research_consistency(data)
        assert _by_type(issues, "orphan_hypothesis")[0].hypothesis_id == "hypothesis_1"
        assert _by_type(issues, "orphan_action")[0].action_id == "action_1"

    def test_missing_source_on_action(self) -> None:
        data = _base()
        data.research_cases = [_healthy_case()]
        data.research_actions = [
            ResearchAction(
                id="action_1",
                research_case_id="case_1",
                source_refs=[SourceRef("source_404", "primary"), SourceRef("source_1", "primary")],
            )
        ]
        (issue,) = _by_type(check_research_consistency(data), "missing_source")
        assert issue.action_id == "action_1"
        assert (issue.ref_entity_type, issue.ref_entity_id) == ("source", "source_404")

    def test_invalid_dates(self) -> None:
        data = _base()
        data.research_cases = [_healthy_case()]
        action = ResearchAction(id="action_1", research_case_id="case_1")
        action.completed_date = "2026-02-30"
        data.research_actions = [action]
        data.research_hypotheses = [
            ResearchHypothesis(
                id="hypothesis_1",
                research_case_id="case_1",
                comments=[HypothesisComment(id="hypcomment_1", date="not a date")],
            )
        ]
        issues = check_research_consistency(data)
        assert _by_type(issues, "invalid_completed_date")[0].action_id == "action_1"
        comment_issue = _by_type(issues, "invalid_comment_date")[0]
        assert (comment_issue.hypothesis_id, comment_issue.comment_id) == (
            "hypothesis_1",
            "hypcomment_1",
        )


class TestInformationalChecks:
    def test_closed_case_with_pending_actions(self) -> None:
        data = _base()
        case = _healthy_case()
        case.status = "closed"
        data.research_cases = [case]
        data.research_actions = [ResearchAction(id="action_1", research_case_id="case_1")]
        (issue,) = _by_type(check_research_consistency(data), "closed_with_pending_actions")
        assert issue.severity == SEVERITY_INFO and issue.case_id == "case_1"

    def test_case_without_entity_and_without_actions_is_info_only(self) -> None:
        data = _base()
        data.research_cases = [ResearchCase(id="case_1", title="Tom")]
        issues = check_research_consistency(data)
        assert {i.check_type for i in issues} == {"no_linked_entity", "no_actions"}
        assert all(i.severity == SEVERITY_INFO for i in issues)
        # Reporting never deletes anything.
        assert [c.id for c in data.research_cases] == ["case_1"]

    def test_broken_state_is_not_modified_by_the_check(self) -> None:
        data = _base()
        case = _healthy_case()
        case.linked_entities = [ResearchEntityLink("place", "place_404")]
        data.research_cases = [case]
        before = repr(data.research_cases)
        check_research_consistency(data)
        generate_research_consistency_report(data)
        assert repr(data.research_cases) == before


class TestReport:
    def test_report_for_project_without_research(self) -> None:
        report = generate_research_consistency_report(_base())
        texts = " ".join(getattr(block, "text", "") for block in report.blocks)
        assert "Det finns inga forskningsärenden att kontrollera." in texts

    def test_report_lists_findings_under_headings(self) -> None:
        data = _base()
        case = _healthy_case()
        case.linked_entities = [ResearchEntityLink("place", "place_404")]
        data.research_cases = [case]
        report = generate_research_consistency_report(data)
        flat: list[str] = []
        for block in report.blocks:
            flat.append(getattr(block, "text", "") or "")
            flat.extend(getattr(block, "items", []) or [])
        joined = "\n".join(str(x) for x in flat)
        assert "Länkar till objekt som inte finns" in joined
        assert "place_404" in joined
