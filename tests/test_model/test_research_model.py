"""Tests for the research data model: defaults, constants and pure helpers.

**Validates: Requirements 1.1, 3.1, 4.1, 5.1, 6.1, 6.4**
"""

from __future__ import annotations

import copy

import pytest
from hypothesis import given, settings

from slaktbusken.model.id_generator import IDGenerator
from slaktbusken.model.research_case import (
    SUPPORTED_ENTITY_TYPES,
    VALID_HYPOTHESIS_ASSESSMENTS,
    VALID_RESEARCH_PRIORITIES,
    VALID_RESEARCH_STATUSES,
    HypothesisComment,
    ResearchAction,
    ResearchCase,
    ResearchEntityLink,
    ResearchHypothesis,
    case_entity_links,
    count_links_for_entity,
    is_pending,
)
from tests.test_model.research_strategies import actions, research_cases


class TestDefaults:
    """A new entity starts in the documented state."""

    def test_case_defaults(self) -> None:
        """**Validates: Requirements 1.1**"""
        case = ResearchCase(id="case_1")
        assert case.title == ""
        assert case.description == ""
        assert case.status == "open"
        assert case.priority == "normal"
        assert case.conclusion == ""
        assert case.primary_entity_ref is None
        assert case.linked_entities == []

    def test_hypothesis_defaults(self) -> None:
        """**Validates: Requirements 4.1**"""
        hypothesis = ResearchHypothesis(id="hypothesis_1", research_case_id="case_1")
        assert hypothesis.statement == ""
        assert hypothesis.assessment == "unassessed"
        assert hypothesis.reasoning == ""
        assert hypothesis.linked_entities == []
        assert hypothesis.comments == []

    def test_comment_defaults(self) -> None:
        """**Validates: Requirements 5.1**"""
        comment = HypothesisComment(id="hypcomment_1")
        assert comment.date == ""
        assert comment.text == ""

    def test_action_defaults(self) -> None:
        """**Validates: Requirements 6.1**"""
        action = ResearchAction(id="action_1", research_case_id="case_1")
        assert action.title == ""
        assert action.text == ""
        assert action.completed_date is None
        assert action.sort_order == 0
        assert action.source_refs == []

    def test_link_defaults(self) -> None:
        """**Validates: Requirements 3.1**"""
        link = ResearchEntityLink(entity_type="person", entity_id="person_1")
        assert link.role == ""

    def test_mutable_defaults_are_not_shared_between_instances(self) -> None:
        first = ResearchCase(id="case_1")
        second = ResearchCase(id="case_2")
        first.linked_entities.append(ResearchEntityLink("person", "person_1"))
        assert second.linked_entities == []

        hypothesis_a = ResearchHypothesis(id="hypothesis_1", research_case_id="case_1")
        hypothesis_b = ResearchHypothesis(id="hypothesis_2", research_case_id="case_1")
        hypothesis_a.comments.append(HypothesisComment(id="hypcomment_1"))
        assert hypothesis_b.comments == []

        action_a = ResearchAction(id="action_1", research_case_id="case_1")
        action_b = ResearchAction(id="action_2", research_case_id="case_1")
        action_a.source_refs.append(object())  # type: ignore[arg-type]
        assert action_b.source_refs == []


class TestConstants:
    def test_supported_entity_types(self) -> None:
        """**Validates: Requirements 3.4**"""
        assert SUPPORTED_ENTITY_TYPES == {
            "person",
            "family",
            "event",
            "place",
            "source",
            "media",
            "dna_match",
            "dna_cluster",
        }

    def test_statuses_priorities_and_assessments(self) -> None:
        """**Validates: Requirements 1.4, 1.5, 4.4**"""
        assert VALID_RESEARCH_STATUSES == ("open", "in_progress", "on_hold", "closed")
        assert VALID_RESEARCH_PRIORITIES == ("low", "normal", "high")
        assert VALID_HYPOTHESIS_ASSESSMENTS == (
            "unassessed",
            "possible",
            "strong_support",
            "confirmed",
            "rejected",
        )

    def test_defaults_are_members_of_their_valid_sets(self) -> None:
        case = ResearchCase(id="case_1")
        hypothesis = ResearchHypothesis(id="hypothesis_1", research_case_id="case_1")
        assert case.status in VALID_RESEARCH_STATUSES
        assert case.priority in VALID_RESEARCH_PRIORITIES
        assert hypothesis.assessment in VALID_HYPOTHESIS_ASSESSMENTS


class TestIdPrefixes:
    """The four research entity types have their own readable id prefixes."""

    @pytest.mark.parametrize(
        ("entity_type", "expected"),
        [
            ("research_case", "case_1"),
            ("research_hypothesis", "hypothesis_1"),
            ("research_action", "action_1"),
            ("hypothesis_comment", "hypcomment_1"),
        ],
    )
    def test_first_id_for_each_type(self, entity_type: str, expected: str) -> None:
        """**Validates: Requirements 1.3, 4.3, 5.3, 6.3**"""
        assert IDGenerator(set()).generate(entity_type) == expected

    def test_prefixes_do_not_interfere_with_each_other(self) -> None:
        generator = IDGenerator({"case_5", "hypothesis_9", "action_2", "hypcomment_7"})
        assert generator.generate("research_case") == "case_6"
        assert generator.generate("research_hypothesis") == "hypothesis_10"
        assert generator.generate("research_action") == "action_3"
        assert generator.generate("hypothesis_comment") == "hypcomment_8"


class TestCaseEntityLinks:
    def test_primary_comes_first_then_linked_in_order(self) -> None:
        """**Validates: Requirements 3.3**"""
        primary = ResearchEntityLink("person", "person_1")
        first = ResearchEntityLink("event", "event_1", "research_context")
        second = ResearchEntityLink("person", "person_2", "candidate")
        case = ResearchCase(id="case_1", primary_entity_ref=primary, linked_entities=[first, second])
        assert case_entity_links(case) == [primary, first, second]

    def test_without_a_primary_only_linked_entities_are_returned(self) -> None:
        linked = [ResearchEntityLink("place", "place_1")]
        assert case_entity_links(ResearchCase(id="case_1", linked_entities=linked)) == linked

    def test_only_a_primary_is_returned_alone(self) -> None:
        primary = ResearchEntityLink("source", "source_1")
        assert case_entity_links(ResearchCase(id="case_1", primary_entity_ref=primary)) == [primary]

    def test_a_case_with_no_links_yields_nothing(self) -> None:
        """A research case need reference no entity at all. **Validates: Requirements 3.2**"""
        assert case_entity_links(ResearchCase(id="case_1")) == []

    def test_the_result_is_a_new_list(self) -> None:
        case = ResearchCase(
            id="case_1",
            primary_entity_ref=ResearchEntityLink("person", "person_1"),
            linked_entities=[ResearchEntityLink("event", "event_1")],
        )
        result = case_entity_links(case)
        result.clear()
        assert len(case.linked_entities) == 1
        assert case.primary_entity_ref is not None

    @given(case=research_cases())
    @settings(max_examples=100, deadline=None)
    def test_never_mutates_the_case(self, case: ResearchCase) -> None:
        """Feature: research-cases, Property: link helpers leave the case unchanged

        **Validates: Requirements 3.3**
        """
        before = copy.deepcopy(case)
        case_entity_links(case)
        for link in case_entity_links(case):
            count_links_for_entity(case, link.entity_type, link.entity_id)
        assert case == before

    @given(case=research_cases())
    @settings(max_examples=100, deadline=None)
    def test_length_is_primary_plus_linked(self, case: ResearchCase) -> None:
        """**Validates: Requirements 3.3**"""
        expected = len(case.linked_entities) + (1 if case.primary_entity_ref is not None else 0)
        links = case_entity_links(case)
        assert len(links) == expected
        if case.primary_entity_ref is not None:
            assert links[0] is case.primary_entity_ref


class TestCountLinksForEntity:
    def test_counts_every_link_to_the_same_entity(self) -> None:
        """**Validates: Requirements 3.7**"""
        link = ResearchEntityLink("person", "person_1")
        case = ResearchCase(
            id="case_1",
            primary_entity_ref=link,
            linked_entities=[ResearchEntityLink("person", "person_1", "candidate"), link],
        )
        assert count_links_for_entity(case, "person", "person_1") == 3

    def test_type_and_id_must_both_match(self) -> None:
        case = ResearchCase(id="case_1", linked_entities=[ResearchEntityLink("person", "x_1")])
        assert count_links_for_entity(case, "event", "x_1") == 0
        assert count_links_for_entity(case, "person", "x_2") == 0
        assert count_links_for_entity(case, "person", "x_1") == 1

    def test_a_case_without_links_counts_zero(self) -> None:
        assert count_links_for_entity(ResearchCase(id="case_1"), "person", "person_1") == 0

    @given(case=research_cases())
    @settings(max_examples=100, deadline=None)
    def test_matches_a_manual_count_for_every_linked_entity(self, case: ResearchCase) -> None:
        """Feature: research-cases, Property: link counts agree with the link list

        **Validates: Requirements 3.7**
        """
        links = case_entity_links(case)
        for link in links:
            manual = sum(
                1 for other in links
                if (other.entity_type, other.entity_id) == (link.entity_type, link.entity_id)
            )
            assert count_links_for_entity(case, link.entity_type, link.entity_id) == manual


class TestIsPending:
    @given(action=actions())
    @settings(max_examples=100, deadline=None)
    def test_pending_exactly_when_there_is_no_completion_date(self, action: ResearchAction) -> None:
        """Feature: research-cases, Property: pending means completed_date is None

        **Validates: Requirements 6.4**
        """
        assert is_pending(action) == (action.completed_date is None)

    def test_a_dated_action_is_not_pending(self) -> None:
        assert is_pending(ResearchAction(id="a", research_case_id="c", completed_date="2026-10-30")) is False

    def test_an_undated_action_is_pending(self) -> None:
        assert is_pending(ResearchAction(id="a", research_case_id="c")) is True
