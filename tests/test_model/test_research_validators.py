"""Tests for the research validators.

Covers ``validate_research_case``, ``validate_research_hypothesis``,
``validate_hypothesis_comment``, ``validate_research_action`` and the
duplicate-link warning ``research_case_findings``.

**Validates: Requirements 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 3.2, 3.4, 3.5, 3.7, 4.4, 4.6, 4.7,
4.10, 5.5, 6.5, 6.6, 6.7, 6.8, 9.2, 9.4, 9.5**
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings

from slaktbusken.model.event import SourceRef
from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import (
    VALID_HYPOTHESIS_ASSESSMENTS,
    VALID_RESEARCH_PRIORITIES,
    VALID_RESEARCH_STATUSES,
    HypothesisComment,
    ResearchAction,
    ResearchCase,
    ResearchEntityLink,
    ResearchHypothesis,
    case_entity_links,
)
from slaktbusken.model.validators import (
    research_case_findings,
    validate_hypothesis_comment,
    validate_research_action,
    validate_research_case,
    validate_research_hypothesis,
)
from tests.test_model.research_strategies import (
    IMPOSSIBLE_DATES,
    MALFORMED_DATES,
    actions,
    consistent_projects,
    hypotheses,
    research_cases,
)

BAD_STATUS = "Ogiltig status för forskningsärendet."
BAD_PRIORITY = "Ogiltig prioritet för forskningsärendet."
TITLE_TOO_LONG = "Rubriken får vara högst 200 tecken."
DESCRIPTION_TOO_LONG = "Frågeställningen får vara högst 10000 tecken."
CONCLUSION_TOO_LONG = "Slutsatsen får vara högst 10000 tecken."
UNKNOWN_TYPE = "Forskningslänken har en okänd objekttyp."
UNKNOWN_ENTITY = "Forskningsärendet refererar till ett objekt som inte finns."
DUPLICATE_LINK = "Forskningsärendet länkar till samma objekt mer än en gång."
BAD_ASSESSMENT = "Ogiltig bedömning för hypotesen."
HYPOTHESIS_UNKNOWN_CASE = "Hypotesen refererar till ett forskningsärende som inte finns."
STATEMENT_TOO_LONG = "Hypotesens påstående får vara högst 1000 tecken."
REASONING_TOO_LONG = "Hypotesens motivering får vara högst 10000 tecken."
COMMENT_BAD_DATE = (
    "Hypoteskommentarens datum är inte ett giltigt datum "
    "(förväntat ÅÅÅÅ, ÅÅÅÅ-MM eller ÅÅÅÅ-MM-DD)."
)
COMMENT_TEXT_TOO_LONG = "Hypoteskommentarens text får vara högst 10000 tecken."
ACTION_UNKNOWN_CASE = "Forskningsåtgärden refererar till ett forskningsärende som inte finns."
ACTION_BAD_DATE = (
    "Forskningsåtgärdens färdigdatum är inte ett giltigt datum "
    "(förväntat ÅÅÅÅ, ÅÅÅÅ-MM eller ÅÅÅÅ-MM-DD)."
)
ACTION_TITLE_TOO_LONG = "Forskningsåtgärdens rubrik får vara högst 200 tecken."
ACTION_TEXT_TOO_LONG = "Forskningsåtgärdens text får vara högst 10000 tecken."
ACTION_UNKNOWN_SOURCE = "Forskningsåtgärden refererar till en källa som inte finns."


def _entity_ids(project: ProjectData) -> dict[str, set[str]]:
    return {
        "person": {x.id for x in project.persons},
        "family": {x.id for x in project.families},
        "event": {x.id for x in project.events},
        "place": {x.id for x in project.places},
        "source": {x.id for x in project.sources},
        "media": {x.id for x in project.media},
        "dna_match": {x.id for x in project.dna_matches},
        "dna_cluster": {x.id for x in project.dna_clusters},
    }


# ---------------------------------------------------------------------------
# ResearchCase
# ---------------------------------------------------------------------------


class TestValidateResearchCase:
    def test_an_empty_case_is_valid(self) -> None:
        """No title, no links, no text: the model tolerates it. **Validates: Requirements 1.6, 3.2**"""
        assert validate_research_case(ResearchCase(id="case_1")) == []

    @pytest.mark.parametrize("status", VALID_RESEARCH_STATUSES)
    def test_every_valid_status_is_accepted(self, status: str) -> None:
        assert validate_research_case(ResearchCase(id="case_1", status=status)) == []

    @pytest.mark.parametrize("status", ["", "Open", "done", "avslutad"])
    def test_an_invalid_status_gives_exactly_one_message(self, status: str) -> None:
        """**Validates: Requirements 1.4**"""
        assert validate_research_case(ResearchCase(id="case_1", status=status)) == [BAD_STATUS]

    @pytest.mark.parametrize("priority", VALID_RESEARCH_PRIORITIES)
    def test_every_valid_priority_is_accepted(self, priority: str) -> None:
        assert validate_research_case(ResearchCase(id="case_1", priority=priority)) == []

    @pytest.mark.parametrize("priority", ["", "urgent", "Hög"])
    def test_an_invalid_priority_gives_exactly_one_message(self, priority: str) -> None:
        """**Validates: Requirements 1.5**"""
        assert validate_research_case(ResearchCase(id="case_1", priority=priority)) == [BAD_PRIORITY]

    @pytest.mark.parametrize(
        ("field", "limit", "message"),
        [
            ("title", 200, TITLE_TOO_LONG),
            ("description", 10000, DESCRIPTION_TOO_LONG),
            ("conclusion", 10000, CONCLUSION_TOO_LONG),
        ],
    )
    def test_text_limits_are_inclusive(self, field: str, limit: int, message: str) -> None:
        """The limit itself is allowed; one more character is not. **Validates: Requirements 1.7**"""
        at_limit = ResearchCase(id="case_1", **{field: "x" * limit})
        over_limit = ResearchCase(id="case_1", **{field: "x" * (limit + 1)})
        assert validate_research_case(at_limit) == []
        assert validate_research_case(over_limit) == [message]

    def test_length_counts_characters_not_bytes(self) -> None:
        """Swedish letters take two bytes in UTF-8 but count as one character."""
        assert validate_research_case(ResearchCase(id="case_1", title="å" * 200)) == []
        assert validate_research_case(ResearchCase(id="case_1", title="å" * 201)) == [TITLE_TOO_LONG]

    @pytest.mark.parametrize(
        ("status", "conclusion"),
        [("closed", ""), ("closed", "Slutsats"), ("open", ""), ("open", "Preliminär slutsats")],
    )
    def test_conclusion_is_independent_of_status(self, status: str, conclusion: str) -> None:
        """**Validates: Requirements 1.8**"""
        case = ResearchCase(id="case_1", status=status, conclusion=conclusion)
        assert validate_research_case(case) == []

    def test_several_problems_give_several_messages(self) -> None:
        case = ResearchCase(id="case_1", status="x", priority="y", title="t" * 201)
        assert validate_research_case(case) == [BAD_STATUS, BAD_PRIORITY, TITLE_TOO_LONG]

    @given(case=research_cases(include_over_limit=False))
    @settings(max_examples=100, deadline=None)
    def test_a_well_formed_case_validates_clean(self, case: ResearchCase) -> None:
        """Feature: research-cases, Property: well-formed cases have no errors

        **Validates: Requirements 1.9**
        """
        assert validate_research_case(case) == []

    @given(case=research_cases(include_invalid_values=True))
    @settings(max_examples=100, deadline=None)
    def test_each_rule_violation_gives_exactly_one_message(self, case: ResearchCase) -> None:
        """Feature: research-cases, Property: one message per violated rule

        **Validates: Requirements 1.4, 1.5, 1.7**
        """
        expected = (
            (case.status not in VALID_RESEARCH_STATUSES)
            + (case.priority not in VALID_RESEARCH_PRIORITIES)
            + (len(case.title) > 200)
            + (len(case.description) > 10000)
            + (len(case.conclusion) > 10000)
        )
        assert len(validate_research_case(case)) == expected


class TestEntityLinks:
    """Link rules, checked through a case (a hypothesis applies the same ones)."""

    def test_a_case_may_have_no_links_at_all(self) -> None:
        assert validate_research_case(ResearchCase(id="case_1")) == []

    @pytest.mark.parametrize("entity_type", ["residence", "repository", "", "Person"])
    def test_an_unsupported_type_gives_one_message_per_link(self, entity_type: str) -> None:
        """**Validates: Requirements 3.4**"""
        case = ResearchCase(
            id="case_1",
            primary_entity_ref=ResearchEntityLink(entity_type, "x_1"),
            linked_entities=[ResearchEntityLink(entity_type, "x_2")],
        )
        assert validate_research_case(case) == [UNKNOWN_TYPE, UNKNOWN_TYPE]

    def test_an_unsupported_type_is_not_also_reported_as_missing(self) -> None:
        case = ResearchCase(id="case_1", linked_entities=[ResearchEntityLink("residence", "r_1")])
        assert validate_research_case(case, {"person": set()}) == [UNKNOWN_TYPE]

    def test_a_link_that_does_not_resolve_is_reported_once(self) -> None:
        """**Validates: Requirements 3.5**"""
        case = ResearchCase(id="case_1", linked_entities=[ResearchEntityLink("person", "person_9")])
        assert validate_research_case(case, {"person": {"person_1"}}) == [UNKNOWN_ENTITY]

    def test_a_link_that_resolves_is_fine(self) -> None:
        case = ResearchCase(id="case_1", linked_entities=[ResearchEntityLink("person", "person_1")])
        assert validate_research_case(case, {"person": {"person_1"}}) == []

    def test_the_primary_link_is_checked_too(self) -> None:
        case = ResearchCase(id="case_1", primary_entity_ref=ResearchEntityLink("place", "place_9"))
        assert validate_research_case(case, {"place": {"place_1"}}) == [UNKNOWN_ENTITY]

    def test_existence_is_not_checked_without_id_sets(self) -> None:
        case = ResearchCase(id="case_1", linked_entities=[ResearchEntityLink("person", "person_999")])
        assert validate_research_case(case) == []
        assert validate_research_case(case, None) == []

    def test_a_blank_id_is_not_reported_as_missing(self) -> None:
        case = ResearchCase(id="case_1", linked_entities=[ResearchEntityLink("person", ""), ResearchEntityLink("person", "  ")])
        assert validate_research_case(case, {"person": {"person_1"}}) == []

    def test_a_type_missing_from_the_id_sets_is_not_checked(self) -> None:
        """A caller may supply id sets for just the types it knows."""
        case = ResearchCase(id="case_1", linked_entities=[ResearchEntityLink("media", "media_9")])
        assert validate_research_case(case, {"person": {"person_1"}}) == []

    def test_an_empty_id_set_means_nothing_of_that_type_exists(self) -> None:
        case = ResearchCase(id="case_1", linked_entities=[ResearchEntityLink("source", "source_1")])
        assert validate_research_case(case, {"source": set()}) == [UNKNOWN_ENTITY]

    def test_all_eight_supported_types_resolve(self) -> None:
        links = [
            ResearchEntityLink(t, f"{t}_1")
            for t in ("person", "family", "event", "place", "source", "media", "dna_match", "dna_cluster")
        ]
        ids = {link.entity_type: {link.entity_id} for link in links}
        assert validate_research_case(ResearchCase(id="case_1", linked_entities=links), ids) == []

    @given(project=consistent_projects())
    @settings(max_examples=100, deadline=None)
    def test_every_link_in_a_consistent_project_resolves(self, project: ProjectData) -> None:
        """Feature: research-cases, Property: consistent projects validate clean

        **Validates: Requirements 3.5, 4.9**
        """
        ids = _entity_ids(project)
        case_ids = {c.id for c in project.research_cases}
        for case in project.research_cases:
            assert validate_research_case(case, ids) == []
        for hypothesis in project.research_hypotheses:
            assert validate_research_hypothesis(hypothesis, case_ids, ids) == []
        for action in project.research_actions:
            assert validate_research_action(action, case_ids, ids["source"]) == []


class TestDuplicateLinkWarning:
    """Linking the same entity twice is a warning, never an error."""

    def test_primary_repeated_in_linked_entities_warns(self) -> None:
        """**Validates: Requirements 3.7**"""
        case = ResearchCase(
            id="case_1",
            primary_entity_ref=ResearchEntityLink("person", "person_1"),
            linked_entities=[ResearchEntityLink("person", "person_1", "candidate")],
        )
        findings = research_case_findings(case)
        assert [f.message for f in findings] == [DUPLICATE_LINK]
        assert findings[0].case_id == "case_1"
        assert findings[0].severity == "warning"

    def test_the_same_entity_twice_in_linked_entities_warns(self) -> None:
        link = ResearchEntityLink("event", "event_1")
        case = ResearchCase(id="case_1", linked_entities=[link, ResearchEntityLink("event", "event_1", "x")])
        assert [f.message for f in research_case_findings(case)] == [DUPLICATE_LINK]

    def test_many_duplicates_still_give_exactly_one_finding(self) -> None:
        link = ResearchEntityLink("person", "person_1")
        case = ResearchCase(id="case_1", primary_entity_ref=link, linked_entities=[link, link, link])
        assert len(research_case_findings(case)) == 1

    def test_a_duplicate_is_not_a_validation_error(self) -> None:
        link = ResearchEntityLink("person", "person_1")
        case = ResearchCase(id="case_1", primary_entity_ref=link, linked_entities=[link])
        assert validate_research_case(case) == []

    def test_distinct_entities_do_not_warn(self) -> None:
        case = ResearchCase(
            id="case_1",
            primary_entity_ref=ResearchEntityLink("person", "person_1"),
            linked_entities=[
                ResearchEntityLink("person", "person_2"),
                ResearchEntityLink("event", "person_1"),  # same id, different type
            ],
        )
        assert research_case_findings(case) == []

    def test_blank_ids_are_ignored(self) -> None:
        case = ResearchCase(id="case_1", linked_entities=[ResearchEntityLink("person", ""), ResearchEntityLink("person", "")])
        assert research_case_findings(case) == []

    def test_a_case_without_links_does_not_warn(self) -> None:
        assert research_case_findings(ResearchCase(id="case_1")) == []

    @given(case=research_cases())
    @settings(max_examples=100, deadline=None)
    def test_warns_exactly_when_a_pair_repeats(self, case: ResearchCase) -> None:
        """Feature: research-cases, Property: the warning matches repeated links

        **Validates: Requirements 3.7**
        """
        pairs = [
            (link.entity_type, link.entity_id)
            for link in case_entity_links(case)
            if link.entity_id.strip()
        ]
        assert bool(research_case_findings(case)) == (len(pairs) != len(set(pairs)))


# ---------------------------------------------------------------------------
# Comments, hypotheses
# ---------------------------------------------------------------------------


class TestValidateHypothesisComment:
    @pytest.mark.parametrize("date", ["", "2026", "2026-10", "2026-10-30", "2024-02-29"])
    def test_empty_and_real_dates_are_accepted(self, date: str) -> None:
        """Year and month precision are fine. **Validates: Requirements 5.5**"""
        assert validate_hypothesis_comment(HypothesisComment(id="hypcomment_1", date=date)) == []

    @pytest.mark.parametrize("date", [*IMPOSSIBLE_DATES, *MALFORMED_DATES])
    def test_impossible_and_malformed_dates_give_one_message(self, date: str) -> None:
        """"2026-02-30" has the right shape but is not a date. **Validates: Requirements 5.5**"""
        assert validate_hypothesis_comment(HypothesisComment(id="hypcomment_1", date=date)) == [COMMENT_BAD_DATE]

    def test_whitespace_only_date_counts_as_empty(self) -> None:
        assert validate_hypothesis_comment(HypothesisComment(id="hypcomment_1", date="  ")) == []

    def test_text_limit_is_inclusive(self) -> None:
        assert validate_hypothesis_comment(HypothesisComment(id="hypcomment_1", text="x" * 10000)) == []
        assert validate_hypothesis_comment(HypothesisComment(id="hypcomment_1", text="x" * 10001)) == [COMMENT_TEXT_TOO_LONG]


class TestValidateResearchHypothesis:
    def _hypothesis(self, **overrides: object) -> ResearchHypothesis:
        return ResearchHypothesis(id="hypothesis_1", research_case_id="case_1", **overrides)  # type: ignore[arg-type]

    def test_a_default_hypothesis_is_valid(self) -> None:
        assert validate_research_hypothesis(self._hypothesis()) == []

    @pytest.mark.parametrize("assessment", VALID_HYPOTHESIS_ASSESSMENTS)
    def test_every_valid_assessment_is_accepted(self, assessment: str) -> None:
        assert validate_research_hypothesis(self._hypothesis(assessment=assessment)) == []

    @pytest.mark.parametrize("assessment", ["", "likely", "Möjlig", "proven"])
    def test_an_invalid_assessment_gives_one_message(self, assessment: str) -> None:
        """**Validates: Requirements 4.4**"""
        assert validate_research_hypothesis(self._hypothesis(assessment=assessment)) == [BAD_ASSESSMENT]

    def test_conflicting_hypotheses_on_one_case_are_valid(self) -> None:
        """One confirmed and one rejected. **Validates: Requirements 4.6**"""
        confirmed = ResearchHypothesis(id="hypothesis_1", research_case_id="case_1", assessment="confirmed")
        rejected = ResearchHypothesis(id="hypothesis_2", research_case_id="case_1", assessment="rejected")
        for hypothesis in (confirmed, rejected):
            assert validate_research_hypothesis(hypothesis, {"case_1"}) == []

    def test_missing_case_is_reported_only_when_case_ids_are_given(self) -> None:
        """**Validates: Requirements 4.7**"""
        hypothesis = self._hypothesis()
        assert validate_research_hypothesis(hypothesis) == []
        assert validate_research_hypothesis(hypothesis, {"case_1"}) == []
        assert validate_research_hypothesis(hypothesis, {"case_2"}) == [HYPOTHESIS_UNKNOWN_CASE]
        assert validate_research_hypothesis(hypothesis, set()) == [HYPOTHESIS_UNKNOWN_CASE]

    @pytest.mark.parametrize(
        ("field", "limit", "message"),
        [("statement", 1000, STATEMENT_TOO_LONG), ("reasoning", 10000, REASONING_TOO_LONG)],
    )
    def test_text_limits_are_inclusive(self, field: str, limit: int, message: str) -> None:
        """**Validates: Requirements 4.10**"""
        assert validate_research_hypothesis(self._hypothesis(**{field: "x" * limit})) == []
        assert validate_research_hypothesis(self._hypothesis(**{field: "x" * (limit + 1)})) == [message]

    def test_links_follow_the_same_rules_as_a_case(self) -> None:
        """**Validates: Requirements 4.9**"""
        hypothesis = self._hypothesis(
            linked_entities=[
                ResearchEntityLink("residence", "r_1"),
                ResearchEntityLink("person", "person_9"),
                ResearchEntityLink("person", "person_1"),
            ]
        )
        assert validate_research_hypothesis(hypothesis, None, {"person": {"person_1"}}) == [UNKNOWN_TYPE, UNKNOWN_ENTITY]

    def test_nested_comments_are_validated_too(self) -> None:
        hypothesis = self._hypothesis(
            comments=[
                HypothesisComment("hypcomment_1", "2026-02-30", "x"),
                HypothesisComment("hypcomment_2", "", "ok"),
                HypothesisComment("hypcomment_3", "2026-10", "ok"),
                HypothesisComment("hypcomment_4", "", "y" * 10001),
            ]
        )
        assert validate_research_hypothesis(hypothesis) == [COMMENT_BAD_DATE, COMMENT_TEXT_TOO_LONG]

    def test_a_hypothesis_without_comments_is_valid(self) -> None:
        assert validate_research_hypothesis(self._hypothesis(comments=[])) == []

    @given(hypothesis=hypotheses(include_over_limit=False))
    @settings(max_examples=100, deadline=None)
    def test_a_well_formed_hypothesis_validates_clean(self, hypothesis: ResearchHypothesis) -> None:
        """Feature: research-cases, Property: well-formed hypotheses have no errors

        **Validates: Requirements 4.4, 4.6, 5.5**
        """
        assert validate_research_hypothesis(hypothesis) == []

    @given(hypothesis=hypotheses(include_invalid_values=True))
    @settings(max_examples=100, deadline=None)
    def test_each_rule_violation_gives_exactly_one_message(self, hypothesis: ResearchHypothesis) -> None:
        """Feature: research-cases, Property: one message per violated rule

        **Validates: Requirements 4.4, 4.10, 5.5**
        """
        from slaktbusken.model.research_case import is_valid_calendar_date

        expected = (
            (hypothesis.assessment not in VALID_HYPOTHESIS_ASSESSMENTS)
            + (len(hypothesis.statement) > 1000)
            + (len(hypothesis.reasoning) > 10000)
            + sum(
                (bool(c.date.strip()) and not is_valid_calendar_date(c.date))
                + (len(c.text) > 10000)
                for c in hypothesis.comments
            )
        )
        assert len(validate_research_hypothesis(hypothesis)) == expected


# ---------------------------------------------------------------------------
# ResearchAction
# ---------------------------------------------------------------------------


class TestValidateResearchAction:
    def _action(self, **overrides: object) -> ResearchAction:
        return ResearchAction(id="action_1", research_case_id="case_1", **overrides)  # type: ignore[arg-type]

    def test_a_default_action_is_valid(self) -> None:
        assert validate_research_action(self._action()) == []

    def test_several_pending_actions_on_one_case_are_valid(self) -> None:
        """**Validates: Requirements 6.6**"""
        for index in range(5):
            action = ResearchAction(id=f"action_{index}", research_case_id="case_1")
            assert validate_research_action(action, {"case_1"}, set()) == []

    def test_missing_case_is_reported_only_when_case_ids_are_given(self) -> None:
        """**Validates: Requirements 6.5**"""
        action = self._action()
        assert validate_research_action(action) == []
        assert validate_research_action(action, {"case_1"}) == []
        assert validate_research_action(action, {"case_2"}) == [ACTION_UNKNOWN_CASE]

    @pytest.mark.parametrize("completed", ["2026", "2026-10", "2026-10-30", "2024-02-29"])
    def test_a_real_completion_date_of_any_precision_is_accepted(self, completed: str) -> None:
        """**Validates: Requirements 6.7, 6.9**"""
        assert validate_research_action(self._action(completed_date=completed)) == []

    @pytest.mark.parametrize("completed", [*IMPOSSIBLE_DATES, *MALFORMED_DATES])
    def test_an_impossible_or_malformed_completion_date_gives_one_message(self, completed: str) -> None:
        """**Validates: Requirements 6.7**"""
        assert validate_research_action(self._action(completed_date=completed)) == [ACTION_BAD_DATE]

    def test_a_blank_completion_date_on_construction_means_pending_and_is_valid(self) -> None:
        """Normalization turns "" and whitespace into None. **Validates: Requirements 6.1**"""
        assert validate_research_action(self._action(completed_date="")) == []
        assert validate_research_action(self._action(completed_date="   ")) == []

    def test_an_empty_string_assigned_after_construction_is_reported(self) -> None:
        """Assignment bypasses normalization; the validator must not let it through."""
        action = self._action(completed_date="2026-10-30")
        action.completed_date = ""
        assert validate_research_action(action) == [ACTION_BAD_DATE]

    @pytest.mark.parametrize(
        ("field", "limit", "message"),
        [("title", 200, ACTION_TITLE_TOO_LONG), ("text", 10000, ACTION_TEXT_TOO_LONG)],
    )
    def test_text_limits_are_inclusive(self, field: str, limit: int, message: str) -> None:
        """**Validates: Requirements 6.8**"""
        assert validate_research_action(self._action(**{field: "x" * limit})) == []
        assert validate_research_action(self._action(**{field: "x" * (limit + 1)})) == [message]

    def test_an_action_may_cite_no_source_at_all(self) -> None:
        """Research can be documented before any source is registered. **Validates: Requirements 9.2**"""
        assert validate_research_action(self._action(source_refs=[]), {"case_1"}, {"source_1"}) == []

    def test_an_action_may_cite_several_sources(self) -> None:
        refs = [SourceRef("source_1", "primary"), SourceRef("source_2", "secondary")]
        assert validate_research_action(self._action(source_refs=refs), {"case_1"}, {"source_1", "source_2"}) == []

    def test_each_unresolved_source_is_reported(self) -> None:
        """**Validates: Requirements 9.4**"""
        refs = [SourceRef("source_1", "primary"), SourceRef("gone_1", "primary"), SourceRef("gone_2", "primary")]
        errors = validate_research_action(self._action(source_refs=refs), None, {"source_1"})
        assert errors == [ACTION_UNKNOWN_SOURCE, ACTION_UNKNOWN_SOURCE]

    def test_sources_are_not_checked_without_a_source_id_set(self) -> None:
        refs = [SourceRef("anything", "primary")]
        assert validate_research_action(self._action(source_refs=refs)) == []

    def test_a_negative_result_may_still_cite_the_examined_source(self) -> None:
        """"Personen återfanns inte." with the volume that was checked. **Validates: Requirements 9.5**"""
        action = self._action(
            title="Kontrollera Ljusdal AI:17",
            text="Personen återfanns inte.",
            completed_date="2026-10-30",
            source_refs=[SourceRef("source_1", "primary")],
        )
        assert validate_research_action(action, {"case_1"}, {"source_1"}) == []

    @given(action=actions(include_over_limit=False))
    @settings(max_examples=100, deadline=None)
    def test_a_well_formed_action_validates_clean(self, action: ResearchAction) -> None:
        """Feature: research-cases, Property: well-formed actions have no errors

        **Validates: Requirements 6.6, 6.7, 6.9**
        """
        assert validate_research_action(action) == []

    @given(action=actions(pending=False, include_invalid_values=True))
    @settings(max_examples=100, deadline=None)
    def test_each_rule_violation_gives_exactly_one_message(self, action: ResearchAction) -> None:
        """Feature: research-cases, Property: one message per violated rule

        **Validates: Requirements 6.7, 6.8**
        """
        from slaktbusken.model.research_case import is_valid_calendar_date

        expected = (
            (action.completed_date is not None and not is_valid_calendar_date(action.completed_date))
            + (len(action.title) > 200)
            + (len(action.text) > 10000)
        )
        assert len(validate_research_action(action)) == expected
