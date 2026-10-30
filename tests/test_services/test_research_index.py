"""Tests for the research index.

**Validates: Requirements 3.8, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.8, 12.9, 22.3, 26.3**
"""

from __future__ import annotations

import copy
import time

import pytest
from hypothesis import given, settings

from slaktbusken.model.dna import DnaCluster, DnaMatch
from slaktbusken.model.event import Event, Participant, SourceRef
from slaktbusken.model.family import Family
from slaktbusken.model.media import MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.research_case import (
    ResearchAction,
    ResearchCase,
    ResearchEntityLink,
    ResearchHypothesis,
    case_entity_links,
    is_pending,
)
from slaktbusken.model.source import Source
from slaktbusken.services.research_index import ResearchCaseCounts, ResearchIndex
from tests.test_model.research_strategies import consistent_projects, research_cases

L = ResearchEntityLink


def _project() -> ProjectData:
    """A project with one entity of every linkable type."""
    data = ProjectData(project=ProjectMetadata(title="Test"))
    data.persons = [
        Person(id="person_1", sex="F", names=[Name("birth", "Anna", "A")]),
        Person(id="person_2", sex="M", names=[Name("birth", "Per", "P")]),
    ]
    data.families = [Family(id="family_1", partners=[], children=[])]
    data.events = [Event(id="event_1", type="birth", participants=[Participant("person_1", "subject")])]
    data.places = [Place(id="place_1", type="parish", name="Ljusdal")]
    data.sources = [
        Source(id="source_1", provider="AD", source_type="church_book", title="Volym 1"),
        Source(id="source_2", provider="AD", source_type="church_book", title="Volym 2"),
    ]
    data.media = [MediaItem(id="media_1", type="photo", file="a.jpg", title="Foto")]
    data.dna_matches = [DnaMatch(id="dna_match_1", profile1_id="p1", profile2_id="p2")]
    data.dna_clusters = [DnaCluster(id="dna_cluster_1", name="Kluster")]
    return data


class TestCasesForEntity:
    def test_a_case_linking_an_entity_is_returned_for_it(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id="case_1", linked_entities=[L("person", "person_1")])]
        assert [c.id for c in ResearchIndex(data).cases_for_entity("person", "person_1")] == ["case_1"]

    def test_the_primary_link_counts(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id="case_1", primary_entity_ref=L("place", "place_1"))]
        assert [c.id for c in ResearchIndex(data).cases_for_entity("place", "place_1")] == ["case_1"]

    def test_a_case_linking_the_same_entity_twice_appears_once(self) -> None:
        """**Validates: Requirements 3.8, 12.2**"""
        data = _project()
        data.research_cases = [
            ResearchCase(
                id="case_1",
                primary_entity_ref=L("person", "person_1"),
                linked_entities=[L("person", "person_1", "candidate"), L("person", "person_1")],
            )
        ]
        index = ResearchIndex(data)
        assert len(index.cases_for_entity("person", "person_1")) == 1
        assert index.counts_for_entity("person", "person_1") == ResearchCaseCounts(1, 1)

    def test_cases_come_in_project_order(self) -> None:
        data = _project()
        data.research_cases = [
            ResearchCase(id=f"case_{n}", linked_entities=[L("person", "person_1")]) for n in (3, 1, 2)
        ]
        assert [c.id for c in ResearchIndex(data).cases_for_entity("person", "person_1")] == [
            "case_3", "case_1", "case_2"
        ]

    def test_an_entity_with_no_cases_gives_an_empty_list(self) -> None:
        assert ResearchIndex(_project()).cases_for_entity("person", "person_1") == []

    def test_type_and_id_must_both_match(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id="case_1", linked_entities=[L("person", "person_1")])]
        index = ResearchIndex(data)
        assert index.cases_for_entity("event", "person_1") == []
        assert index.cases_for_entity("person", "person_2") == []

    @pytest.mark.parametrize(
        "link",
        [
            L("person", "person_1"), L("family", "family_1"), L("event", "event_1"), L("place", "place_1"),
            L("source", "source_1"), L("media", "media_1"), L("dna_match", "dna_match_1"),
            L("dna_cluster", "dna_cluster_1"),
        ],
    )
    def test_every_supported_entity_type_is_indexed(self, link: ResearchEntityLink) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id="case_1", linked_entities=[link])]
        found = ResearchIndex(data).cases_for_entity(link.entity_type, link.entity_id)
        assert [c.id for c in found] == ["case_1"]

    def test_the_returned_list_is_a_copy(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id="case_1", linked_entities=[L("person", "person_1")])]
        index = ResearchIndex(data)
        index.cases_for_entity("person", "person_1").clear()
        assert len(index.cases_for_entity("person", "person_1")) == 1


class TestBrokenLinks:
    """A link kept after its target was deleted contributes to nothing."""

    def test_a_link_to_a_deleted_entity_is_not_returned(self) -> None:
        """**Validates: Requirements 26.3**"""
        data = _project()
        data.research_cases = [ResearchCase(id="case_1", linked_entities=[L("person", "person_deleted")])]
        index = ResearchIndex(data)
        assert index.cases_for_entity("person", "person_deleted") == []
        assert index.counts_for_entity("person", "person_deleted") == ResearchCaseCounts(0, 0)

    def test_deleting_the_entity_removes_it_from_a_fresh_index(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id="case_1", linked_entities=[L("person", "person_2")])]
        assert len(ResearchIndex(data).cases_for_entity("person", "person_2")) == 1
        data.persons = [p for p in data.persons if p.id != "person_2"]
        assert ResearchIndex(data).cases_for_entity("person", "person_2") == []
        assert len(data.research_cases[0].linked_entities) == 1  # the link itself is kept

    def test_a_link_of_an_unsupported_type_is_never_indexed(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id="case_1", linked_entities=[L("residence", "residence_1")])]
        assert ResearchIndex(data).cases_for_entity("residence", "residence_1") == []

    def test_a_broken_link_does_not_hide_a_working_one_in_the_same_case(self) -> None:
        data = _project()
        data.research_cases = [
            ResearchCase(id="case_1", linked_entities=[L("person", "gone"), L("place", "place_1")])
        ]
        index = ResearchIndex(data)
        assert [c.id for c in index.cases_for_entity("place", "place_1")] == ["case_1"]

    def test_a_blank_id_is_never_indexed(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id="case_1", linked_entities=[L("person", "")])]
        assert ResearchIndex(data).cases_for_entity("person", "") == []


class TestCounts:
    def test_counts_split_open_from_total(self) -> None:
        """**Validates: Requirements 12.3**"""
        data = _project()
        data.research_cases = [
            ResearchCase(id="case_1", status="open", linked_entities=[L("person", "person_1")]),
            ResearchCase(id="case_2", status="in_progress", linked_entities=[L("person", "person_1")]),
            ResearchCase(id="case_3", status="on_hold", linked_entities=[L("person", "person_1")]),
            ResearchCase(id="case_4", status="closed", linked_entities=[L("person", "person_1")]),
        ]
        assert ResearchIndex(data).counts_for_entity("person", "person_1") == ResearchCaseCounts(
            non_closed=3, total=4
        )

    def test_only_closed_cases_gives_zero_open(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id="case_1", status="closed", linked_entities=[L("person", "person_1")])]
        assert ResearchIndex(data).counts_for_entity("person", "person_1") == ResearchCaseCounts(0, 1)

    def test_no_cases_gives_zero_zero(self) -> None:
        assert ResearchIndex(_project()).counts_for_entity("person", "person_1") == ResearchCaseCounts(0, 0)

    def test_on_hold_counts_as_open(self) -> None:
        """"öppna" means not closed. **Validates: Requirements 14.5**"""
        data = _project()
        data.research_cases = [ResearchCase(id="case_1", status="on_hold", linked_entities=[L("person", "person_1")])]
        assert ResearchIndex(data).counts_for_entity("person", "person_1").non_closed == 1

    def test_counts_count_unique_cases_not_links(self) -> None:
        data = _project()
        link = L("person", "person_1")
        data.research_cases = [ResearchCase(id="case_1", primary_entity_ref=link, linked_entities=[link, link])]
        assert ResearchIndex(data).counts_for_entity("person", "person_1").total == 1

    def test_an_unknown_entity_gives_zero(self) -> None:
        assert ResearchIndex(_project()).counts_for_entity("residence", "x") == ResearchCaseCounts(0, 0)

    def test_the_counts_are_immutable(self) -> None:
        counts = ResearchCaseCounts(1, 2)
        with pytest.raises(Exception):
            counts.total = 5  # type: ignore[misc]


class TestFreshIndexReflectsChanges:
    """The index is rebuilt rather than invalidated. **Validates: Requirements 12.6**"""

    def _data(self) -> ProjectData:
        data = _project()
        data.research_cases = [ResearchCase(id="case_1", status="open", linked_entities=[L("person", "person_1")])]
        return data

    def test_closing_a_case(self) -> None:
        data = self._data()
        assert ResearchIndex(data).counts_for_entity("person", "person_1") == ResearchCaseCounts(1, 1)
        data.research_cases[0].status = "closed"
        assert ResearchIndex(data).counts_for_entity("person", "person_1") == ResearchCaseCounts(0, 1)

    def test_reopening_a_case(self) -> None:
        data = self._data()
        data.research_cases[0].status = "closed"
        data.research_cases[0].status = "open"
        assert ResearchIndex(data).counts_for_entity("person", "person_1") == ResearchCaseCounts(1, 1)

    def test_adding_and_removing_a_link(self) -> None:
        data = self._data()
        data.research_cases[0].linked_entities.append(L("place", "place_1"))
        assert len(ResearchIndex(data).cases_for_entity("place", "place_1")) == 1
        data.research_cases[0].linked_entities.pop()
        assert ResearchIndex(data).cases_for_entity("place", "place_1") == []

    def test_deleting_a_case(self) -> None:
        data = self._data()
        data.research_cases.clear()
        assert ResearchIndex(data).counts_for_entity("person", "person_1") == ResearchCaseCounts(0, 0)

    def test_an_index_already_built_does_not_follow_later_changes(self) -> None:
        """It is a snapshot: callers build a new one after a change."""
        data = self._data()
        index = ResearchIndex(data)
        data.research_cases[0].status = "closed"
        assert index.counts_for_entity("person", "person_1") == ResearchCaseCounts(1, 1)


class TestHypothesesForEntity:
    def _data(self) -> ProjectData:
        data = _project()
        data.research_cases = [
            ResearchCase(id="case_1", title="Far", linked_entities=[L("person", "person_1")]),
            ResearchCase(id="case_2", title="Mor"),
        ]
        data.research_hypotheses = [
            ResearchHypothesis(id="hypothesis_1", research_case_id="case_1", linked_entities=[L("person", "person_2")]),
            ResearchHypothesis(id="hypothesis_2", research_case_id="case_2", linked_entities=[L("person", "person_2")]),
            ResearchHypothesis(id="hypothesis_3", research_case_id="case_1"),
        ]
        return data

    def test_returns_each_hypothesis_with_its_owning_case(self) -> None:
        """**Validates: Requirements 12.9**"""
        found = ResearchIndex(self._data()).hypotheses_for_entity("person", "person_2")
        assert [(h.id, c.id) for h, c in found] == [("hypothesis_1", "case_1"), ("hypothesis_2", "case_2")]

    def test_a_hypothesis_naming_a_person_does_not_make_its_case_one_of_the_persons_cases(self) -> None:
        """**Validates: Requirements 22.3**"""
        index = ResearchIndex(self._data())
        assert index.cases_for_entity("person", "person_2") == []
        assert index.counts_for_entity("person", "person_2") == ResearchCaseCounts(0, 0)

    def test_and_does_not_affect_the_count_of_a_person_who_has_a_case(self) -> None:
        data = self._data()
        data.research_hypotheses[0].linked_entities.append(L("person", "person_1"))
        index = ResearchIndex(data)
        assert index.counts_for_entity("person", "person_1") == ResearchCaseCounts(1, 1)
        assert len(index.hypotheses_for_entity("person", "person_1")) == 1

    def test_a_hypothesis_naming_an_entity_twice_is_listed_once(self) -> None:
        data = self._data()
        data.research_hypotheses[0].linked_entities.append(L("person", "person_2", "candidate"))
        assert len(ResearchIndex(data).hypotheses_for_entity("person", "person_2")) == 2

    def test_a_hypothesis_whose_case_is_missing_has_nothing_to_pair_with(self) -> None:
        data = self._data()
        data.research_hypotheses.append(
            ResearchHypothesis(id="hypothesis_9", research_case_id="case_gone", linked_entities=[L("person", "person_2")])
        )
        ids = [h.id for h, _ in ResearchIndex(data).hypotheses_for_entity("person", "person_2")]
        assert "hypothesis_9" not in ids

    def test_a_link_to_a_deleted_entity_is_not_returned(self) -> None:
        data = self._data()
        data.persons = [p for p in data.persons if p.id != "person_2"]
        assert ResearchIndex(data).hypotheses_for_entity("person", "person_2") == []

    def test_no_hypotheses_gives_an_empty_list(self) -> None:
        assert ResearchIndex(_project()).hypotheses_for_entity("person", "person_1") == []


class TestHypothesesForCase:
    def test_returns_the_cases_hypotheses_in_project_order(self) -> None:
        data = _project()
        data.research_hypotheses = [
            ResearchHypothesis(id="hypothesis_2", research_case_id="case_1"),
            ResearchHypothesis(id="hypothesis_1", research_case_id="case_2"),
            ResearchHypothesis(id="hypothesis_3", research_case_id="case_1"),
        ]
        index = ResearchIndex(data)
        assert [h.id for h in index.hypotheses_for_case("case_1")] == ["hypothesis_2", "hypothesis_3"]
        assert [h.id for h in index.hypotheses_for_case("case_2")] == ["hypothesis_1"]
        assert index.hypotheses_for_case("case_none") == []


class TestActions:
    def _data(self) -> ProjectData:
        data = _project()
        data.research_cases = [ResearchCase(id="case_1"), ResearchCase(id="case_2")]
        data.research_actions = [
            ResearchAction(id="action_1", research_case_id="case_1", source_refs=[SourceRef("source_1", "primary")]),
            ResearchAction(id="action_2", research_case_id="case_1", completed_date="2026-05-01"),
            ResearchAction(id="action_3", research_case_id="case_2", source_refs=[SourceRef("source_1", "primary"), SourceRef("source_2", "primary")]),
        ]
        return data

    def test_actions_for_a_case(self) -> None:
        index = ResearchIndex(self._data())
        assert [a.id for a in index.actions_for_case("case_1")] == ["action_1", "action_2"]
        assert [a.id for a in index.actions_for_case("case_2")] == ["action_3"]
        assert index.actions_for_case("case_none") == []

    def test_actions_for_a_source_span_several_cases(self) -> None:
        """The cases need not link the source. **Validates: Requirements 12.4**"""
        index = ResearchIndex(self._data())
        found = index.actions_for_source("source_1")
        assert [a.id for a in found] == ["action_1", "action_3"]
        assert {a.research_case_id for a in found} == {"case_1", "case_2"}

    def test_an_action_citing_a_source_twice_is_listed_once(self) -> None:
        data = self._data()
        data.research_actions[0].source_refs.append(SourceRef("source_1", "secondary"))
        assert [a.id for a in ResearchIndex(data).actions_for_source("source_1")] == ["action_1", "action_3"]

    def test_several_actions_of_one_case_citing_a_source_are_all_listed(self) -> None:
        """**Validates: Requirements 23.5**"""
        data = self._data()
        data.research_actions.append(
            ResearchAction(id="action_4", research_case_id="case_1", source_refs=[SourceRef("source_1", "primary")])
        )
        found = ResearchIndex(data).actions_for_source("source_1")
        assert [a.id for a in found if a.research_case_id == "case_1"] == ["action_1", "action_4"]

    def test_a_source_nobody_cited_has_no_actions(self) -> None:
        assert ResearchIndex(self._data()).actions_for_source("source_x") == []

    def test_an_action_with_no_sources_is_in_no_source_list(self) -> None:
        index = ResearchIndex(self._data())
        assert all("action_2" != a.id for a in index.actions_for_source("source_1"))

    def test_pending_action_count(self) -> None:
        index = ResearchIndex(self._data())
        assert index.pending_action_count("case_1") == 1   # action_2 is completed
        assert index.pending_action_count("case_2") == 1
        assert index.pending_action_count("case_none") == 0

    def test_a_blank_completion_date_counts_as_pending(self) -> None:
        data = self._data()
        data.research_actions.append(ResearchAction(id="action_5", research_case_id="case_1", completed_date="  "))
        assert ResearchIndex(data).pending_action_count("case_1") == 2

    def test_a_case_with_only_completed_actions_has_none_pending(self) -> None:
        data = _project()
        data.research_actions = [ResearchAction(id="action_1", research_case_id="case_1", completed_date="2026")]
        assert ResearchIndex(data).pending_action_count("case_1") == 0

    def test_a_closed_case_still_reports_its_pending_actions(self) -> None:
        data = self._data()
        data.research_cases[0].status = "closed"
        assert ResearchIndex(data).pending_action_count("case_1") == 1


class TestCaseLookup:
    def test_case_by_id(self) -> None:
        data = _project()
        data.research_cases = [ResearchCase(id="case_1", title="Ett")]
        index = ResearchIndex(data)
        assert index.case("case_1").title == "Ett"
        assert index.case("case_9") is None


class TestReadOnly:
    @given(project=consistent_projects())
    @settings(max_examples=100, deadline=None)
    def test_building_and_querying_changes_nothing(self, project: ProjectData) -> None:
        """Feature: research-cases, Property: the index is read-only

        **Validates: Requirements 12.1**
        """
        before = copy.deepcopy(project)
        index = ResearchIndex(project)
        for person in project.persons:
            index.cases_for_entity("person", person.id)
            index.counts_for_entity("person", person.id)
            index.hypotheses_for_entity("person", person.id)
        for source in project.sources:
            index.actions_for_source(source.id)
        for case in project.research_cases:
            index.actions_for_case(case.id)
            index.hypotheses_for_case(case.id)
            index.pending_action_count(case.id)
        assert project == before


class TestAgainstBruteForce:
    """The index must agree with a plain scan of the data."""

    @given(project=consistent_projects())
    @settings(max_examples=100, deadline=None)
    def test_cases_and_counts_match_a_scan(self, project: ProjectData) -> None:
        """Feature: research-cases, Property: cases and counts equal a brute-force scan

        **Validates: Requirements 3.8, 12.2, 12.3**
        """
        index = ResearchIndex(project)
        entities = (
            [("person", x.id) for x in project.persons] + [("family", x.id) for x in project.families]
            + [("event", x.id) for x in project.events] + [("place", x.id) for x in project.places]
            + [("source", x.id) for x in project.sources] + [("media", x.id) for x in project.media]
            + [("dna_match", x.id) for x in project.dna_matches] + [("dna_cluster", x.id) for x in project.dna_clusters]
        )
        for entity_type, entity_id in entities:
            expected = [
                case for case in project.research_cases
                if any((l.entity_type, l.entity_id) == (entity_type, entity_id) for l in case_entity_links(case))
            ]
            assert [c.id for c in index.cases_for_entity(entity_type, entity_id)] == [c.id for c in expected]
            assert index.counts_for_entity(entity_type, entity_id) == ResearchCaseCounts(
                non_closed=sum(1 for c in expected if c.status != "closed"), total=len(expected)
            )

    @given(project=consistent_projects())
    @settings(max_examples=100, deadline=None)
    def test_hypotheses_and_actions_match_a_scan(self, project: ProjectData) -> None:
        """Feature: research-cases, Property: hypothesis and action lookups equal a scan

        **Validates: Requirements 12.4, 12.5, 12.9**
        """
        index = ResearchIndex(project)
        for case in project.research_cases:
            assert [h.id for h in index.hypotheses_for_case(case.id)] == [
                h.id for h in project.research_hypotheses if h.research_case_id == case.id
            ]
            assert [a.id for a in index.actions_for_case(case.id)] == [
                a.id for a in project.research_actions if a.research_case_id == case.id
            ]
            assert index.pending_action_count(case.id) == sum(
                1 for a in project.research_actions if a.research_case_id == case.id and is_pending(a)
            )
        for source in project.sources:
            assert [a.id for a in index.actions_for_source(source.id)] == [
                a.id for a in project.research_actions if any(r.source_id == source.id for r in a.source_refs)
            ]
        for person in project.persons:
            expected = [
                (h.id, h.research_case_id) for h in project.research_hypotheses
                if any((l.entity_type, l.entity_id) == ("person", person.id) for l in h.linked_entities)
            ]
            assert [(h.id, c.id) for h, c in index.hypotheses_for_entity("person", person.id)] == expected

    @given(case=research_cases())
    @settings(max_examples=100, deadline=None)
    def test_links_to_entities_that_do_not_exist_are_never_indexed(self, case: ResearchCase) -> None:
        """Feature: research-cases, Property: dangling links contribute nothing

        A project with no entities at all indexes no links.

        **Validates: Requirements 26.3**
        """
        data = ProjectData(project=ProjectMetadata(title="Tomt"))
        data.research_cases = [case]
        index = ResearchIndex(data)
        for link in case_entity_links(case):
            assert index.cases_for_entity(link.entity_type, link.entity_id) == []
            assert index.counts_for_entity(link.entity_type, link.entity_id) == ResearchCaseCounts(0, 0)


class TestScale:
    """The index stays fast on a large project. **Validates: Requirements 12.8**"""

    @staticmethod
    def _large() -> ProjectData:
        data = ProjectData(project=ProjectMetadata(title="Stort"))
        data.persons = [
            Person(id=f"person_{n}", sex="U", names=[Name("birth", "G", "S")]) for n in range(1, 20001)
        ]
        data.sources = [Source(id=f"source_{n}", provider="AD", source_type="church_book", title="V") for n in range(1, 501)]
        data.research_cases = [
            ResearchCase(
                id=f"case_{n}",
                status="closed" if n % 3 == 0 else "open",
                primary_entity_ref=L("person", f"person_{n}"),
                linked_entities=[L("person", f"person_{(n * 7) % 20000 + 1}")],
            )
            for n in range(1, 10001)
        ]
        data.research_hypotheses = [
            ResearchHypothesis(id=f"hypothesis_{n}", research_case_id=f"case_{n % 10000 + 1}",
                               linked_entities=[L("person", f"person_{n % 20000 + 1}")])
            for n in range(1, 10001)
        ]
        data.research_actions = [
            ResearchAction(
                id=f"action_{n}", research_case_id=f"case_{n % 10000 + 1}",
                completed_date="2026-01-01" if n % 2 else None,
                source_refs=[SourceRef(f"source_{n % 500 + 1}", "primary")],
            )
            for n in range(1, 20001)
        ]
        return data

    def test_building_takes_at_most_two_seconds(self) -> None:
        data = self._large()
        start = time.perf_counter()
        ResearchIndex(data)
        assert time.perf_counter() - start <= 2.0

    def test_lookups_after_the_build_are_fast(self) -> None:
        data = self._large()
        index = ResearchIndex(data)
        start = time.perf_counter()
        for n in range(1, 20001):
            index.counts_for_entity("person", f"person_{n}")
        for n in range(1, 10001):
            index.actions_for_case(f"case_{n}")
            index.pending_action_count(f"case_{n}")
            index.hypotheses_for_case(f"case_{n}")
        # 40,000 lookups in well under a second, not a scan each
        assert time.perf_counter() - start < 1.0

    def test_a_large_index_still_answers_correctly(self) -> None:
        data = self._large()
        index = ResearchIndex(data)
        # person_3 is primary of case_3 (closed) and also linked by case_n where (n*7) % 20000 + 1 == 3
        expected = [
            c for c in data.research_cases
            if any(l.entity_id == "person_3" for l in case_entity_links(c))
        ]
        counts = index.counts_for_entity("person", "person_3")
        assert counts.total == len(expected)
        assert counts.non_closed == sum(1 for c in expected if c.status != "closed")
