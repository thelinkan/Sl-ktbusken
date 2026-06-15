"""Unit tests for the serialization module."""

from __future__ import annotations

import json

from slaktbusken.model.dna import (
    DnaCluster,
    DnaCompany,
    DnaMatch,
    DnaProfile,
    DnaSegment,
    DnaTriangulation,
)
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.media import LinkedEntity, MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.research_note import ResearchNote
from slaktbusken.model.source import Repository, RepositoryRef, Source, StructuredReference
from slaktbusken.persistence.serialization import deserialize, serialize


def _make_full_project_data() -> ProjectData:
    """Create a ProjectData instance with all entity types populated."""
    return ProjectData(
        format="släktbuske-file",
        version="0.1",
        project=ProjectMetadata(
            title="Test Project",
            main_person_id="person_1",
            created_by="Tester",
            language="sv-SE",
        ),
        persons=[
            Person(
                id="person_1",
                sex="M",
                names=[
                    Name(type="birth", given="Erik", surname="Andersson"),
                    Name(type="married", given="Erik", surname="Svensson", event_id="event_2"),
                ],
                profile_media_id="media_1",
                notes="A note",
                title="Fil.Dr",
                occupation="Lektor",
            ),
        ],
        families=[
            Family(
                id="family_1",
                partners=[
                    FamilyPartner(person_id="person_1", role="husband"),
                    FamilyPartner(person_id="person_2", role="wife"),
                ],
                children=["person_3", "person_4"],
                parent_child_links=[
                    ParentChildLink(
                        child_id="person_3",
                        parent_id="person_1",
                        parentage_type="biological",
                    ),
                    ParentChildLink(
                        child_id="person_3",
                        parent_id=None,
                        parentage_type="unknown_donor",
                    ),
                ],
                event_ids=["event_1"],
            ),
        ],
        events=[
            Event(
                id="event_1",
                type="birth",
                participants=[Participant(person_id="person_3", role="primary")],
                date=DateValue(
                    value="1920-05-15",
                    precision="exact",
                    source_refs=[
                        SourceRef(source_id="source_1", quality="high", note="p.42")
                    ],
                ),
                place=PlaceRef(
                    place_id="place_1",
                    source_refs=[SourceRef(source_id="source_1", quality="medium")],
                ),
                media_ids=["media_1"],
                custom_type_name=None,
                cause_of_death=None,
            ),
            Event(
                id="event_death",
                type="death",
                participants=[Participant(person_id="person_1", role="primary")],
                cause_of_death="Hjärtinfarkt",
            ),
        ],
        places=[
            Place(
                id="place_1",
                type="parish",
                name="Ljusdal",
                parent_place_id="place_2",
                latitude=61.83,
                longitude=15.89,
                notes="Hälsingland",
            ),
        ],
        sources=[
            Source(
                id="source_1",
                provider="ArkivDigital",
                source_type="church_record",
                title="Ljusdal C:5",
                reference_text="Ljusdal (X) CI:5 (1800-1850) Bild: 42",
                provider_ref="ad_12345",
                short_note="C:5 p.42",
                free_note="Dopbok",
                structured_reference=StructuredReference(
                    fields={"parish": "Ljusdal", "volume": "CI:5", "page": 42}
                ),
                media_ids=["media_2"],
                repository_refs=[
                    RepositoryRef(
                        repository_id="repo_1",
                        call_number="SE/HLA/13010",
                        source_type="church_record",
                        image_number=42,
                        page_number=21,
                        media_type="digital_image",
                        media_name="Image 42",
                        notes="First entry",
                    )
                ],
            ),
        ],
        media=[
            MediaItem(
                id="media_1",
                type="image",
                file="images/photo.jpg",
                title="Portrait",
                linked_entities=[
                    LinkedEntity(entity_type="person", entity_id="person_1", role="subject")
                ],
                publication={"date": "1920", "publisher": "Studio AB"},
                transcription="Erik Andersson, 1920",
                mentioned_person_ids=["person_1"],
            ),
        ],
        repositories=[
            Repository(
                id="repo_1",
                name="ArkivDigital",
                type="digital_archive",
                address="Norra Hamngatan 14, Göteborg",
                phone=["+46 31 778 77 70"],
                email=["info@arkivdigital.se"],
                web=["https://www.arkivdigital.se"],
                notes="Swedish digital archive",
                external_ids=["ad_001"],
            ),
        ],
        dna_companies=[
            DnaCompany(
                id="dna_co_1",
                name="MyHeritage",
                logo_media_id="media_3",
                description="DNA testing company",
            ),
        ],
        dna_profiles=[
            DnaProfile(
                id="dna_prof_1",
                person_id="person_1",
                company_id="dna_co_1",
                test_type="autosomal",
                kit_name="Erik's Kit",
                kit_id="KIT001",
                admin_person_id="person_2",
                admin_status="active",
                notes="Primary kit",
            ),
        ],
        dna_matches=[
            DnaMatch(
                id="dna_match_1",
                profile1_id="dna_prof_1",
                profile2_id="dna_prof_2",
                shared_cm=150.5,
                shared_percentage=2.1,
                segment_count=8,
                largest_segment_cm=45.2,
                match_source="internal",
                notes="Strong match",
            ),
        ],
        dna_segments=[
            DnaSegment(
                id="dna_seg_1",
                match_id="dna_match_1",
                chromosome="7",
                start_position=1000000,
                end_position=5000000,
                cm=45.2,
                snp_count=3500,
            ),
        ],
        dna_clusters=[
            DnaCluster(
                id="dna_cluster_1",
                name="Andersson cluster",
                notes="Maternal side",
                company_ids=["dna_co_1"],
                person_ids=["person_1", "person_5"],
                dna_match_ids=["dna_match_1"],
                color="#FF5733",
            ),
        ],
        dna_triangulations=[
            DnaTriangulation(
                id="dna_tri_1",
                company_id="dna_co_1",
                chromosome="7",
                overlap_start=1500000,
                overlap_end=4000000,
                segment_ids=["dna_seg_1", "dna_seg_2"],
                profile_ids=["dna_prof_1", "dna_prof_2", "dna_prof_3"],
                cluster_id="dna_cluster_1",
                notes="Triangulated overlap",
            ),
        ],
        research_notes=[
            ResearchNote(
                id="note_1",
                title="Research on Andersson family",
                text="Found new records in Ljusdal parish.",
                linked_entities=[
                    LinkedEntity(entity_type="person", entity_id="person_1", role="subject"),
                    LinkedEntity(entity_type="source", entity_id="source_1"),
                ],
            ),
        ],
    )


class TestSerializeFormatVersion:
    """Tests that format and version appear as the first keys in output JSON."""

    def test_format_and_version_are_first_keys(self) -> None:
        """format and version must be the first two keys in the JSON output."""
        data = ProjectData()
        result = serialize(data)
        parsed = json.loads(result)
        keys = list(parsed.keys())
        assert keys[0] == "format"
        assert keys[1] == "version"

    def test_format_value_preserved(self) -> None:
        """The format field value is preserved through serialization."""
        data = ProjectData(format="släktbuske-file")
        result = serialize(data)
        parsed = json.loads(result)
        assert parsed["format"] == "släktbuske-file"

    def test_version_value_preserved(self) -> None:
        """The version field value is preserved through serialization."""
        data = ProjectData(version="0.1")
        result = serialize(data)
        parsed = json.loads(result)
        assert parsed["version"] == "0.1"


class TestRoundTrip:
    """Tests that serialization and deserialization are inverse operations."""

    def test_empty_project_round_trip(self) -> None:
        """An empty ProjectData round-trips correctly."""
        data = ProjectData()
        result = deserialize(serialize(data))
        assert result.format == data.format
        assert result.version == data.version
        assert result.project.title == data.project.title
        assert result.persons == []
        assert result.families == []
        assert result.events == []

    def test_full_project_round_trip(self) -> None:
        """A fully populated ProjectData round-trips correctly."""
        data = _make_full_project_data()
        result = deserialize(serialize(data))

        # Check top-level
        assert result.format == data.format
        assert result.version == data.version
        assert result.project.title == data.project.title
        assert result.project.main_person_id == data.project.main_person_id
        assert result.project.created_by == data.project.created_by
        assert result.project.language == data.project.language

        # Persons
        assert len(result.persons) == 1
        p = result.persons[0]
        assert p.id == "person_1"
        assert p.sex == "M"
        assert len(p.names) == 2
        assert p.names[0].type == "birth"
        assert p.names[0].given == "Erik"
        assert p.names[0].surname == "Andersson"
        assert p.names[0].event_id is None
        assert p.names[1].event_id == "event_2"
        assert p.profile_media_id == "media_1"
        assert p.notes == "A note"
        assert p.title == "Fil.Dr"
        assert p.occupation == "Lektor"

        # Families
        assert len(result.families) == 1
        f = result.families[0]
        assert f.id == "family_1"
        assert len(f.partners) == 2
        assert f.partners[0].person_id == "person_1"
        assert f.partners[0].role == "husband"
        assert f.children == ["person_3", "person_4"]
        assert len(f.parent_child_links) == 2
        assert f.parent_child_links[1].parent_id is None
        assert f.parent_child_links[1].parentage_type == "unknown_donor"
        assert f.event_ids == ["event_1"]

        # Events
        assert len(result.events) == 2
        e = result.events[0]
        assert e.id == "event_1"
        assert e.type == "birth"
        assert len(e.participants) == 1
        assert e.participants[0].person_id == "person_3"
        assert e.date is not None
        assert e.date.value == "1920-05-15"
        assert e.date.precision == "exact"
        assert len(e.date.source_refs) == 1
        assert e.date.source_refs[0].note == "p.42"
        assert e.place is not None
        assert e.place.place_id == "place_1"
        assert e.media_ids == ["media_1"]
        # Death event with cause
        e_death = result.events[1]
        assert e_death.cause_of_death == "Hjärtinfarkt"

        # Places
        assert len(result.places) == 1
        pl = result.places[0]
        assert pl.id == "place_1"
        assert pl.parent_place_id == "place_2"
        assert pl.latitude == 61.83
        assert pl.longitude == 15.89

        # Sources
        assert len(result.sources) == 1
        s = result.sources[0]
        assert s.id == "source_1"
        assert s.structured_reference.fields["parish"] == "Ljusdal"
        assert s.structured_reference.fields["page"] == 42
        assert len(s.repository_refs) == 1
        assert s.repository_refs[0].image_number == 42

        # Media
        assert len(result.media) == 1
        m = result.media[0]
        assert m.id == "media_1"
        assert m.publication == {"date": "1920", "publisher": "Studio AB"}
        assert m.transcription == "Erik Andersson, 1920"
        assert m.mentioned_person_ids == ["person_1"]
        assert len(m.linked_entities) == 1

        # Repositories
        assert len(result.repositories) == 1
        r = result.repositories[0]
        assert r.id == "repo_1"
        assert r.phone == ["+46 31 778 77 70"]
        assert r.external_ids == ["ad_001"]

        # DNA entities
        assert len(result.dna_companies) == 1
        assert result.dna_companies[0].name == "MyHeritage"
        assert result.dna_companies[0].logo_media_id == "media_3"

        assert len(result.dna_profiles) == 1
        assert result.dna_profiles[0].admin_person_id == "person_2"

        assert len(result.dna_matches) == 1
        assert result.dna_matches[0].shared_cm == 150.5

        assert len(result.dna_segments) == 1
        assert result.dna_segments[0].snp_count == 3500

        assert len(result.dna_clusters) == 1
        assert result.dna_clusters[0].color == "#FF5733"
        assert result.dna_clusters[0].dna_match_ids == ["dna_match_1"]

        assert len(result.dna_triangulations) == 1
        tri = result.dna_triangulations[0]
        assert tri.cluster_id == "dna_cluster_1"
        assert len(tri.segment_ids) == 2
        assert len(tri.profile_ids) == 3

        # Research notes
        assert len(result.research_notes) == 1
        rn = result.research_notes[0]
        assert rn.title == "Research on Andersson family"
        assert len(rn.linked_entities) == 2


class TestSerializeOutputFormat:
    """Tests for specific output format requirements."""

    def test_output_is_valid_utf8_json(self) -> None:
        """Output is valid JSON with UTF-8 characters preserved."""
        data = ProjectData(
            project=ProjectMetadata(title="Släktträd med åäö")
        )
        result = serialize(data)
        # Should not raise
        parsed = json.loads(result)
        assert parsed["project"]["title"] == "Släktträd med åäö"

    def test_non_ascii_characters_not_escaped(self) -> None:
        """Swedish characters are not escaped to \\uXXXX."""
        data = ProjectData(
            project=ProjectMetadata(title="Släktträd")
        )
        result = serialize(data)
        assert "Släktträd" in result
        assert "\\u" not in result

    def test_optional_none_fields_omitted(self) -> None:
        """Optional fields with None values are not included in output."""
        data = ProjectData(
            persons=[
                Person(id="p1", sex="M", names=[Name(type="birth", given="A", surname="B")])
            ]
        )
        result = serialize(data)
        parsed = json.loads(result)
        person = parsed["persons"][0]
        assert "profile_media_id" not in person
        assert "title" not in person
        assert "occupation" not in person


class TestDeserializeDefaults:
    """Tests that deserialization applies sensible defaults for missing fields."""

    def test_missing_optional_fields_get_defaults(self) -> None:
        """Missing optional fields in JSON get default values."""
        minimal_json = json.dumps({
            "format": "släktbuske-file",
            "version": "0.1",
            "project": {"title": "Minimal"},
            "persons": [{"id": "p1", "sex": "F", "names": []}],
        })
        result = deserialize(minimal_json)
        assert result.persons[0].profile_media_id is None
        assert result.persons[0].notes == ""
        assert result.persons[0].title is None
        assert result.families == []
        assert result.dna_companies == []

    def test_missing_format_version_gets_defaults(self) -> None:
        """Missing format and version fields default to expected values."""
        minimal_json = json.dumps({"project": {"title": "No version"}})
        result = deserialize(minimal_json)
        assert result.format == "släktbuske-file"
        assert result.version == "0.1"
