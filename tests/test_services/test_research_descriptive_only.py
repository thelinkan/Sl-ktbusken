"""Research data is descriptive only (task 13.1).

Closing a case, rejecting a hypothesis, completing an action and writing a
conclusion must change no genealogical fact: no person, event, family, place,
source, media item or DNA record.
"""

from __future__ import annotations

import copy

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from slaktbusken.model.dna import DnaCluster, DnaMatch
from slaktbusken.model.event import DateValue, Event, Participant, SourceRef
from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.media import MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.model.research_case import (
    VALID_HYPOTHESIS_ASSESSMENTS,
    VALID_RESEARCH_STATUSES,
    HypothesisComment,
    ResearchAction,
    ResearchCase,
    ResearchEntityLink,
    ResearchHypothesis,
)
from slaktbusken.model.source import Source
from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.research_editing import set_action_completed
from slaktbusken.services.research_service import open_working_copy

#: Every genealogical collection that research must never change.
GENEALOGICAL = (
    "persons",
    "families",
    "events",
    "places",
    "sources",
    "repositories",
    "media",
    "residences",
    "dna_companies",
    "dna_profiles",
    "dna_matches",
    "dna_segments",
    "dna_clusters",
    "dna_triangulations",
)


def _snapshot(data: ProjectData) -> dict:
    return {name: copy.deepcopy(getattr(data, name)) for name in GENEALOGICAL}


@pytest.fixture
def service() -> ProjectService:
    svc = ProjectService()
    data = ProjectData()
    data.persons = [
        Person(id="person_1", sex="M", names=[Name(type="birth", given="Anders", surname="Ek")]),
        Person(id="person_2", sex="F", names=[Name(type="birth", given="Karin", surname="Lund")]),
    ]
    data.places = [Place(id="place_1", type="parish", name="Socken")]
    data.sources = [Source(id="source_1", provider="p", source_type="t", title="Kyrkbok")]
    data.events = [
        Event(
            id="event_1",
            type="birth",
            participants=[Participant("person_1", "principal")],
            date=DateValue("1850", "year", [SourceRef("source_1", "primary")]),
        )
    ]
    data.families = [
        Family(
            id="family_1",
            partners=[FamilyPartner("person_1", "partner"), FamilyPartner("person_2", "partner")],
            children=[],
        )
    ]
    data.media = [MediaItem(id="media_1", type="photo", file="a.jpg", title="Foto")]
    data.dna_matches = [DnaMatch(id="dnamatch_1", profile1_id="p1", profile2_id="p2")]
    data.dna_clusters = [DnaCluster(id="dnacluster_1", name="K", person_ids=["person_1"])]
    svc._project_data = data

    case = svc.add_research_case(
        ResearchCase(
            id="",
            title="Vem var fadern?",
            primary_entity_ref=ResearchEntityLink("person", "person_1"),
            linked_entities=[
                ResearchEntityLink(entity_type, entity_id)
                for entity_type, entity_id in [
                    ("family", "family_1"),
                    ("event", "event_1"),
                    ("place", "place_1"),
                    ("source", "source_1"),
                    ("media", "media_1"),
                    ("dna_match", "dnamatch_1"),
                    ("dna_cluster", "dnacluster_1"),
                ]
            ],
        )
    )
    svc.add_research_hypothesis(
        ResearchHypothesis(
            id="",
            research_case_id=case.id,
            statement="Karin är modern",
            assessment="strong_support",
            linked_entities=[ResearchEntityLink("person", "person_2")],
            comments=[HypothesisComment(id="", text="Fadder i dopet")],
        )
    )
    svc.add_research_action(
        ResearchAction(id="", research_case_id=case.id, title="Sök husförhör",
                       source_refs=[SourceRef("source_1", "primary", "s. 12", ["date"])])
    )
    return svc


def _commit(svc: ProjectService, change) -> None:
    case_id = svc.data.research_cases[0].id
    working_copy = open_working_copy(svc.data, case_id)
    change(working_copy)
    svc.commit_research_case_working_copy(working_copy)


class TestDescriptiveOnly:
    def test_closing_a_case(self, service: ProjectService) -> None:
        before = _snapshot(service.data)
        _commit(service, lambda wc: setattr(wc.case, "status", "closed"))
        assert service.data.research_cases[0].status == "closed"
        assert _snapshot(service.data) == before

    def test_rejecting_a_hypothesis(self, service: ProjectService) -> None:
        before = _snapshot(service.data)
        _commit(service, lambda wc: setattr(wc.hypotheses[0], "assessment", "rejected"))
        assert service.data.research_hypotheses[0].assessment == "rejected"
        assert _snapshot(service.data) == before

    def test_completing_an_action(self, service: ProjectService) -> None:
        before = _snapshot(service.data)
        _commit(service, lambda wc: set_action_completed(wc.actions[0], True, "2026-01-02"))
        assert service.data.research_actions[0].completed_date == "2026-01-02"
        # The examined source is untouched (Requirement 23.8).
        assert _snapshot(service.data) == before

    def test_setting_a_conclusion(self, service: ProjectService) -> None:
        before = _snapshot(service.data)
        _commit(service, lambda wc: setattr(wc.case, "conclusion", "Anders är fadern."))
        assert _snapshot(service.data) == before

    def test_deleting_the_case(self, service: ProjectService) -> None:
        before = _snapshot(service.data)
        service.delete_research_case(service.data.research_cases[0].id)
        assert _snapshot(service.data) == before

    @settings(max_examples=40, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        status=st.sampled_from(VALID_RESEARCH_STATUSES),
        assessment=st.sampled_from(VALID_HYPOTHESIS_ASSESSMENTS),
        completed=st.booleans(),
        conclusion=st.text(max_size=200),
    )
    def test_any_combination_of_research_changes(
        self, service: ProjectService, status, assessment, completed, conclusion
    ) -> None:
        before = _snapshot(service.data)

        def change(wc) -> None:
            wc.case.status = status
            wc.case.conclusion = conclusion
            wc.hypotheses[0].assessment = assessment
            set_action_completed(wc.actions[0], completed, "2026-01-02")

        _commit(service, change)
        assert _snapshot(service.data) == before
