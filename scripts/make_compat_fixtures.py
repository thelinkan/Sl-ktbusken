"""Generate the golden format 0.3 compatibility fixtures.

Writes ``tests/fixtures/compat/v0_3_*.json`` from fixed projects built in code.
The files were produced once with the code before the person merge feature and
are committed; rerunning this script must reproduce them byte for byte (the
fixtures use the frozen 0.3 serialiser, never the production one, so a later
format change cannot alter them).

Usage (from the repository root):
    python scripts/make_compat_fixtures.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slaktbusken.model.dna import (  # noqa: E402
    DnaCluster,
    DnaCompany,
    DnaMatch,
    DnaProfile,
    DnaSegment,
)
from slaktbusken.model.event import (  # noqa: E402
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink  # noqa: E402
from slaktbusken.model.media import LinkedEntity, MediaItem  # noqa: E402
from slaktbusken.model.person import Name, Person  # noqa: E402
from slaktbusken.model.place import Place  # noqa: E402
from slaktbusken.model.project import ProjectData, ProjectMetadata  # noqa: E402
from slaktbusken.model.research_case import (  # noqa: E402
    HypothesisComment,
    ResearchAction,
    ResearchCase,
    ResearchEntityLink,
    ResearchHypothesis,
)
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact  # noqa: E402
from slaktbusken.model.source import Source  # noqa: E402
from tests.helpers.frozen_serialiser_v0_3 import serialize_v0_3  # noqa: E402

FIXTURE_DIR = ROOT / "tests" / "fixtures" / "compat"


def _person(pid: str, sex: str, given: str, surname: str) -> Person:
    return Person(id=pid, sex=sex, names=[Name(type="birth", given=given, surname=surname)])


def _places() -> list[Place]:
    return [
        Place(id="place_001", type="country", name="Sverige"),
        Place(id="place_002", type="city", name="Örebro", parent_place_id="place_001"),
        Place(id="place_003", type="parish", name="Ålem", parent_place_id="place_001"),
    ]


def _source() -> Source:
    return Source(id="source_001", provider="Riksarkivet", source_type="church_book", title="Husförhörslängd")


def build_empty() -> ProjectData:
    return ProjectData(project=ProjectMetadata(title="Tomt projekt"))


def build_research() -> ProjectData:
    data = ProjectData(project=ProjectMetadata(title="Forskning", main_person_id="person_001"))
    data.persons = [_person("person_001", "M", "Anders", "Svensson"), _person("person_002", "F", "Märta", "Ålund")]
    data.sources = [_source()]
    data.research_cases = [
        ResearchCase(
            id="case_001",
            title="Anders föräldrar",
            description="Vem var Anders far?",
            status="open",
            priority="high",
            primary_entity_ref=ResearchEntityLink(entity_type="person", entity_id="person_001", role="subject"),
            linked_entities=[ResearchEntityLink(entity_type="person", entity_id="person_002")],
        ),
        ResearchCase(id="case_002", title="Avslutat ärende", status="closed", conclusion="Klart."),
    ]
    data.research_hypotheses = [
        ResearchHypothesis(
            id="hyp_001",
            research_case_id="case_001",
            statement="Märta var mor",
            assessment="probable",
            linked_entities=[ResearchEntityLink(entity_type="person", entity_id="person_002")],
            comments=[HypothesisComment(id="cmt_001", date="1999-05-01", text="Stöds av längden")],
        )
    ]
    data.research_actions = [
        ResearchAction(
            id="act_001",
            research_case_id="case_001",
            title="Sök i husförhörslängd",
            completed_date="2020-02-03",
            sort_order=1,
            source_refs=[SourceRef(source_id="source_001", quality="primary")],
        ),
        ResearchAction(id="act_002", research_case_id="case_001", title="Kontakta arkivet", sort_order=2),
    ]
    data.id_high_water_marks = {"case_": 3, "hyp_": 1, "act_": 2, "cmt_": 1}
    return data


def build_residences() -> ProjectData:
    data = ProjectData(project=ProjectMetadata(title="Boenden", main_person_id="person_001"))
    data.persons = [_person("person_001", "M", "Erik", "Östberg")]
    data.places = _places()
    data.sources = [_source()]
    data.events = [
        Event(
            id="event_001",
            type="birth",
            participants=[Participant(person_id="person_001", role="child")],
            date=DateValue(value="1850-03-12", precision="day"),
            place=PlaceRef(place_id="place_003"),
        )
    ]
    data.residences = [
        ResidenceFact(
            id="res_001",
            person_id="person_001",
            place_id="place_002",
            start=Endpoint(earliest="1850", precision="year", event_id="event_001"),
            end=Endpoint(earliest="1880-05", latest="1880-06", precision="month"),
            role_in_household="Son",
            observations=[
                Observation(
                    source_ref=SourceRef(source_id="source_001", quality="primary", note="s. 12"),
                    observed_from="1860",
                    observed_to="1865",
                    page_note="Hushåll 4",
                )
            ],
            notes="Växte upp här.",
        ),
        ResidenceFact(id="res_002", person_id="person_001", place_id="place_003"),
    ]
    return data


def build_mixed() -> ProjectData:
    data = ProjectData(project=ProjectMetadata(title="Blandat projekt", main_person_id="person_003"))
    data.persons = [
        _person("person_001", "M", "Karl", "Lind"),
        _person("person_002", "F", "Greta", "Lind"),
        _person("person_003", "M", "Nils", "Ek"),
        _person("person_004", "F", "Hilda", "Berg"),
        _person("person_005", "M", "Olof", "Berg"),
    ]
    data.places = _places()
    data.sources = [_source()]
    data.families = [
        Family(
            id="family_001",
            partners=[FamilyPartner(person_id="person_001", role="father"), FamilyPartner(person_id="person_002", role="mother")],
            children=["person_003", "person_004"],
            parent_child_links=[
                ParentChildLink(child_id="person_003", parent_id="person_001", parentage_type="foster"),
                ParentChildLink(child_id="person_003", parent_id="person_002", parentage_type="foster"),
                ParentChildLink(child_id="person_004", parent_id="person_001", parentage_type="biological"),
                ParentChildLink(child_id="person_004", parent_id="person_002", parentage_type="biological"),
            ],
        ),
        Family(
            id="family_002",
            partners=[FamilyPartner(person_id="person_005", role="father")],
            children=["person_003"],
            parent_child_links=[ParentChildLink(child_id="person_003", parent_id="person_005", parentage_type="biological")],
        ),
    ]
    data.connection_overrides = {"person_003": "foster"}
    data.events = [
        Event(
            id="event_001",
            type="birth",
            participants=[Participant(person_id="person_003", role="child")],
            date=DateValue(value="1900", precision="year", source_refs=[SourceRef(source_id="source_001", quality="secondary")]),
            place=PlaceRef(place_id="place_002"),
        )
    ]
    data.media = [
        MediaItem(
            id="media_001",
            type="image",
            file="media/Östra_släkten.jpg",
            title="Släktbild",
            linked_entities=[LinkedEntity(entity_type="person", entity_id="person_003")],
            mentioned_person_ids=["person_003"],
        )
    ]
    data.dna_companies = [DnaCompany(id="dnacomp_001", name="FamilyTreeDNA")]
    data.dna_profiles = [
        DnaProfile(id="dnaprof_001", person_id="person_003", company_id="dnacomp_001", test_type="autosomal", kit_name="Nils"),
        DnaProfile(id="dnaprof_002", person_id="person_005", company_id="dnacomp_001", test_type="autosomal", kit_name="Olof"),
    ]
    data.dna_matches = [
        DnaMatch(id="dnamatch_001", profile1_id="dnaprof_001", profile2_id="dnaprof_002", shared_cm=1750.5, shared_percentage=25.8, segment_count=3, largest_segment_cm=120.25)
    ]
    data.dna_segments = [
        DnaSegment(id="dnaseg_001", match_id="dnamatch_001", chromosome="1", start_position=1000, end_position=90000000, cm=120.25, snp_count=15000)
    ]
    data.dna_clusters = [
        DnaCluster(id="dnacluster_001", name="Bergsläkten", company_ids=["dnacomp_001"], person_ids=["person_003"], dna_match_ids=["dnamatch_001"], color="#336699")
    ]
    return data


FIXTURES = {
    "v0_3_empty.json": build_empty,
    "v0_3_research.json": build_research,
    "v0_3_residences.json": build_residences,
    "v0_3_mixed.json": build_mixed,
}


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for name, builder in FIXTURES.items():
        text = serialize_v0_3(builder())
        (FIXTURE_DIR / name).write_text(text + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {FIXTURE_DIR / name}")


if __name__ == "__main__":
    main()
