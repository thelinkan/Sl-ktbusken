"""Unit tests for ValidationService.

Tests cover:
- validate_entity for individual entities with valid/invalid references
- validate_project for full project validation
- Cross-entity referential integrity failures:
  - person_id references in families, event participants, DNA profiles
  - place_id references in events
  - source_id references in source_refs
  - media_id references
  - profile_id references in DNA clusters and matches

Requirements: 8.5, 13.6, 14.6
"""

from __future__ import annotations

import pytest

from slaktbusken.model.dna import (
    DnaCluster,
    DnaCompany,
    DnaMatch,
    DnaProfile,
    DnaSegment,
    DnaTriangulation,
)
from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.media import MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place, RegionLevel
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.research_note import ResearchNote
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.source import Repository, RepositoryRef, Source
from slaktbusken.services.validation_service import ValidationError, ValidationService


@pytest.fixture
def service() -> ValidationService:
    """Create a fresh ValidationService instance."""
    return ValidationService()


@pytest.fixture
def empty_project() -> ProjectData:
    """Create an empty ProjectData instance."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
    )


@pytest.fixture
def populated_project() -> ProjectData:
    """Create a ProjectData with a basic set of entities for reference checks."""
    return ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=[
            Person(id="p1", sex="M", names=[Name(type="birth", given="Erik", surname="S")]),
            Person(id="p2", sex="F", names=[Name(type="birth", given="Anna", surname="J")]),
        ],
        families=[
            Family(id="f1", partners=[FamilyPartner(person_id="p1", role="father")], children=["p2"]),
        ],
        events=[
            Event(id="e1", type="birth", participants=[Participant(person_id="p1", role="subject")]),
        ],
        places=[
            Place(id="pl0", type="continent", name="Europa"),
            Place(id="pl1", type="country", name="Sverige", parent_place_id="pl0",
                  region_levels=[
                      RegionLevel(key="lan", label="Län", order=1),
                      RegionLevel(key="socken", label="Socken", order=2),
                  ]),
            Place(id="pl2", type="lan", name="Stockholms län", parent_place_id="pl1"),
        ],
        sources=[
            Source(id="s1", provider="ArkivDigital", source_type="church_book", title="Födelseboken"),
        ],
        media=[
            MediaItem(id="m1", type="photo", file="photos/img.jpg", title="Foto"),
        ],
        repositories=[
            Repository(id="r1", name="Riksarkivet", type="archive"),
        ],
        dna_companies=[
            DnaCompany(id="dc1", name="MyHeritage"),
        ],
        dna_profiles=[
            DnaProfile(id="dp1", person_id="p1", company_id="dc1", test_type="autosomal"),
            DnaProfile(id="dp2", person_id="p2", company_id="dc1", test_type="autosomal"),
        ],
        dna_matches=[
            DnaMatch(id="dm1", profile1_id="dp1", profile2_id="dp2", shared_cm=50.0),
        ],
        dna_segments=[
            DnaSegment(id="ds1", match_id="dm1", chromosome="1", start_position=100, end_position=5000, cm=10.5),
            DnaSegment(id="ds2", match_id="dm1", chromosome="2", start_position=200, end_position=6000, cm=8.0),
        ],
        dna_clusters=[
            DnaCluster(id="dcl1", name="Norrland cluster"),
        ],
    )


# ---------------------------------------------------------------------------
# Valid entity tests – no errors expected
# ---------------------------------------------------------------------------


class TestValidEntityNoErrors:
    """Tests that valid entities produce no validation errors."""

    def test_valid_person(self, service: ValidationService, populated_project: ProjectData) -> None:
        """A person with valid references returns no errors."""
        person = populated_project.persons[0]
        errors = service.validate_entity(person, populated_project)
        assert errors == []

    def test_valid_family(self, service: ValidationService, populated_project: ProjectData) -> None:
        """A family with valid person references returns no errors."""
        family = populated_project.families[0]
        errors = service.validate_entity(family, populated_project)
        assert errors == []

    def test_valid_event(self, service: ValidationService, populated_project: ProjectData) -> None:
        """An event with valid participant references returns no errors."""
        event = populated_project.events[0]
        errors = service.validate_entity(event, populated_project)
        assert errors == []

    def test_valid_place(self, service: ValidationService, populated_project: ProjectData) -> None:
        """A place with valid parent_place_id returns no errors."""
        county = populated_project.places[2]  # pl2 (lan) with parent pl1 (country)
        errors = service.validate_entity(county, populated_project)
        assert errors == []

    def test_valid_source(self, service: ValidationService, populated_project: ProjectData) -> None:
        """A valid source returns no errors."""
        source = populated_project.sources[0]
        errors = service.validate_entity(source, populated_project)
        assert errors == []

    def test_valid_media(self, service: ValidationService, populated_project: ProjectData) -> None:
        """A valid media item returns no errors."""
        media = populated_project.media[0]
        errors = service.validate_entity(media, populated_project)
        assert errors == []

    def test_valid_dna_profile(self, service: ValidationService, populated_project: ProjectData) -> None:
        """A DNA profile with valid person_id and company_id returns no errors."""
        profile = populated_project.dna_profiles[0]
        errors = service.validate_entity(profile, populated_project)
        assert errors == []

    def test_valid_dna_match(self, service: ValidationService, populated_project: ProjectData) -> None:
        """A DNA match with valid profile references returns no errors."""
        match = populated_project.dna_matches[0]
        errors = service.validate_entity(match, populated_project)
        assert errors == []

    def test_valid_project(self, service: ValidationService, populated_project: ProjectData) -> None:
        """A fully populated valid project returns no errors."""
        errors = service.validate_project(populated_project)
        assert errors == []


# ---------------------------------------------------------------------------
# Referential integrity: person_id references
# ---------------------------------------------------------------------------


class TestPersonIdReferences:
    """Tests for invalid person_id references across entities.

    Requirements: 8.5, 8.6
    """

    def test_family_invalid_partner_person_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A family with a non-existent partner person_id produces an error."""
        family = Family(
            id="f_bad",
            partners=[FamilyPartner(person_id="nonexistent_p", role="father")],
            children=[],
        )
        errors = service.validate_entity(family, populated_project)
        assert any("nonexistent_p" in e.message and "person" in e.message.lower() for e in errors)

    def test_family_invalid_child_person_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A family with a non-existent child person_id produces an error."""
        family = Family(
            id="f_bad",
            partners=[FamilyPartner(person_id="p1", role="father")],
            children=["nonexistent_child"],
        )
        errors = service.validate_entity(family, populated_project)
        assert any("nonexistent_child" in e.message for e in errors)

    def test_event_invalid_participant_person_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """An event with a non-existent participant person_id produces an error."""
        event = Event(
            id="e_bad",
            type="birth",
            participants=[Participant(person_id="ghost_person", role="subject")],
        )
        errors = service.validate_entity(event, populated_project)
        assert any("ghost_person" in e.message for e in errors)

    def test_dna_profile_invalid_person_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A DnaProfile with invalid person_id produces an error.

        Requirement: 13.6
        """
        profile = DnaProfile(
            id="dp_bad", person_id="no_such_person", company_id="dc1", test_type="autosomal",
        )
        errors = service.validate_entity(profile, populated_project)
        assert any("no_such_person" in e.message for e in errors)

    def test_dna_profile_invalid_admin_person_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A DnaProfile with invalid admin_person_id produces an error."""
        profile = DnaProfile(
            id="dp_bad", person_id="p1", company_id="dc1", test_type="autosomal",
            admin_person_id="ghost_admin",
        )
        errors = service.validate_entity(profile, populated_project)
        assert any("ghost_admin" in e.message for e in errors)

    def test_dna_cluster_invalid_person_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A DnaCluster with invalid person_ids produces errors.

        Requirement: 14.6
        """
        cluster = DnaCluster(
            id="dcl_bad", name="Bad cluster", person_ids=["no_person_1", "no_person_2"],
        )
        errors = service.validate_entity(cluster, populated_project)
        person_errors = [e for e in errors if "person_id" in e.message]
        assert len(person_errors) == 2

    def test_media_item_invalid_mentioned_person_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A MediaItem with invalid mentioned_person_ids produces an error."""
        media = MediaItem(
            id="m_bad", type="photo", file="photos/x.jpg", title="X",
            mentioned_person_ids=["ghost_person"],
        )
        errors = service.validate_entity(media, populated_project)
        assert any("ghost_person" in e.message for e in errors)

    def test_person_invalid_profile_media_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A Person with invalid profile_media_id produces an error."""
        person = Person(
            id="p_bad", sex="M",
            names=[Name(type="birth", given="Test", surname="P")],
            profile_media_id="nonexistent_media",
        )
        errors = service.validate_entity(person, populated_project)
        assert any("nonexistent_media" in e.message for e in errors)


# ---------------------------------------------------------------------------
# Referential integrity: place_id references
# ---------------------------------------------------------------------------


class TestPlaceIdReferences:
    """Tests for invalid place_id references."""

    def test_event_invalid_place_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """An event referencing a non-existent place produces an error."""
        event = Event(
            id="e_bad", type="birth",
            participants=[Participant(person_id="p1", role="subject")],
            place=PlaceRef(place_id="no_such_place"),
        )
        errors = service.validate_entity(event, populated_project)
        assert any("no_such_place" in e.message for e in errors)

    def test_place_invalid_parent_place_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A place referencing a non-existent parent_place_id produces an error."""
        place = Place(id="pl_bad", type="county", name="Bad County", parent_place_id="ghost_place")
        errors = service.validate_entity(place, populated_project)
        assert any("ghost_place" in e.message for e in errors)


# ---------------------------------------------------------------------------
# Referential integrity: source_id references
# ---------------------------------------------------------------------------


class TestSourceIdReferences:
    """Tests for invalid source_id references."""

    def test_event_date_invalid_source_ref(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """An event date with invalid source_ref produces an error."""
        event = Event(
            id="e_bad", type="birth",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(
                value="1900-01-01", precision="day",
                source_refs=[SourceRef(source_id="ghost_source", quality="primary")],
            ),
        )
        errors = service.validate_entity(event, populated_project)
        assert any("ghost_source" in e.message for e in errors)

    def test_event_place_invalid_source_ref(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """An event place with invalid source_ref produces an error."""
        event = Event(
            id="e_bad", type="birth",
            participants=[Participant(person_id="p1", role="subject")],
            place=PlaceRef(
                place_id="pl1",
                source_refs=[SourceRef(source_id="no_source", quality="primary")],
            ),
        )
        errors = service.validate_entity(event, populated_project)
        assert any("no_source" in e.message for e in errors)

    def test_source_invalid_repository_ref(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A source with invalid repository_id produces an error."""
        source = Source(
            id="s_bad", provider="Test", source_type="church_book", title="Test",
            repository_refs=[RepositoryRef(repository_id="ghost_repo")],
        )
        errors = service.validate_entity(source, populated_project)
        assert any("ghost_repo" in e.message for e in errors)


# ---------------------------------------------------------------------------
# Referential integrity: media_id references
# ---------------------------------------------------------------------------


class TestMediaIdReferences:
    """Tests for invalid media_id references."""

    def test_event_invalid_media_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """An event with invalid media_id produces an error."""
        event = Event(
            id="e_bad", type="birth",
            participants=[Participant(person_id="p1", role="subject")],
            media_ids=["no_media"],
        )
        errors = service.validate_entity(event, populated_project)
        assert any("no_media" in e.message for e in errors)

    def test_source_invalid_media_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A source with invalid media_id produces an error."""
        source = Source(
            id="s_bad", provider="Test", source_type="church_book", title="Test",
            media_ids=["ghost_media"],
        )
        errors = service.validate_entity(source, populated_project)
        assert any("ghost_media" in e.message for e in errors)


# ---------------------------------------------------------------------------
# Referential integrity: DNA-specific references
# ---------------------------------------------------------------------------


class TestDnaReferences:
    """Tests for invalid DNA entity references.

    Requirements: 13.6, 14.6
    """

    def test_dna_profile_invalid_company_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A DnaProfile with invalid company_id produces an error.

        Requirement: 13.6
        """
        profile = DnaProfile(
            id="dp_bad", person_id="p1", company_id="ghost_company", test_type="autosomal",
        )
        errors = service.validate_entity(profile, populated_project)
        assert any("ghost_company" in e.message for e in errors)

    def test_dna_match_invalid_profile_ids(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A DnaMatch with invalid profile IDs produces errors."""
        match = DnaMatch(
            id="dm_bad", profile1_id="ghost_p1", profile2_id="ghost_p2", shared_cm=50.0,
        )
        errors = service.validate_entity(match, populated_project)
        profile_errors = [e for e in errors if "profile" in e.message.lower()]
        assert len(profile_errors) == 2

    def test_dna_segment_invalid_match_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A DnaSegment with invalid match_id produces an error."""
        segment = DnaSegment(
            id="ds_bad", match_id="ghost_match", chromosome="1",
            start_position=100, end_position=5000, cm=10.5,
        )
        errors = service.validate_entity(segment, populated_project)
        assert any("ghost_match" in e.message for e in errors)

    def test_dna_cluster_invalid_company_ids(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A DnaCluster with invalid company_ids produces errors."""
        cluster = DnaCluster(
            id="dcl_bad", name="Bad cluster", company_ids=["ghost_co"],
        )
        errors = service.validate_entity(cluster, populated_project)
        assert any("ghost_co" in e.message for e in errors)

    def test_dna_cluster_invalid_match_ids(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A DnaCluster with invalid dna_match_ids produces errors.

        Requirement: 14.6
        """
        cluster = DnaCluster(
            id="dcl_bad", name="Bad cluster", dna_match_ids=["no_match"],
        )
        errors = service.validate_entity(cluster, populated_project)
        assert any("no_match" in e.message for e in errors)

    def test_dna_triangulation_invalid_company_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A DnaTriangulation with invalid company_id produces an error."""
        tri = DnaTriangulation(
            id="dt_bad", company_id="ghost_co",
            profile_ids=["dp1", "dp2", "ghost_dp"],
            shared_cm=45.5,
        )
        errors = service.validate_entity(tri, populated_project)
        assert any("ghost_co" in e.message for e in errors)

    def test_dna_triangulation_invalid_profile_ids(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A DnaTriangulation with invalid profile_ids produces errors."""
        tri = DnaTriangulation(
            id="dt_bad", company_id="dc1",
            profile_ids=["dp1", "ghost_dp2", "ghost_dp3"],
            shared_cm=45.5,
        )
        errors = service.validate_entity(tri, populated_project)
        profile_errors = [e for e in errors if "profile_id" in e.message]
        assert len(profile_errors) == 2

    def test_dna_triangulation_invalid_cluster_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A DnaTriangulation with invalid cluster_id produces an error."""
        tri = DnaTriangulation(
            id="dt_bad", company_id="dc1",
            profile_ids=["dp1", "dp2", "dp2"],
            shared_cm=45.5,
            cluster_id="ghost_cluster",
        )
        errors = service.validate_entity(tri, populated_project)
        assert any("ghost_cluster" in e.message for e in errors)


# ---------------------------------------------------------------------------
# validate_project – full project validation
# ---------------------------------------------------------------------------


class TestValidateProject:
    """Tests for validate_project across the entire project."""

    def test_empty_project_valid(self, service: ValidationService, empty_project: ProjectData) -> None:
        """An empty project has no validation errors."""
        errors = service.validate_project(empty_project)
        assert errors == []

    def test_project_with_broken_family_reference(
        self, service: ValidationService
    ) -> None:
        """A project where a family references a non-existent person produces errors."""
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            families=[
                Family(
                    id="f1",
                    partners=[FamilyPartner(person_id="missing_p", role="father")],
                    children=[],
                ),
            ],
        )
        errors = service.validate_project(project)
        assert len(errors) > 0
        assert any(e.entity_type == "Family" and "missing_p" in e.message for e in errors)

    def test_project_with_broken_event_references(
        self, service: ValidationService
    ) -> None:
        """A project where an event references non-existent persons/places produces errors."""
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            events=[
                Event(
                    id="e1", type="birth",
                    participants=[Participant(person_id="ghost_p", role="subject")],
                    place=PlaceRef(place_id="ghost_place"),
                ),
            ],
        )
        errors = service.validate_project(project)
        assert any(e.entity_type == "Event" and "ghost_p" in e.message for e in errors)
        assert any(e.entity_type == "Event" and "ghost_place" in e.message for e in errors)

    def test_project_with_broken_dna_profile_references(
        self, service: ValidationService
    ) -> None:
        """A project where a DnaProfile references non-existent person/company.

        Requirement: 13.6
        """
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_profiles=[
                DnaProfile(
                    id="dp1", person_id="no_person", company_id="no_company",
                    test_type="autosomal",
                ),
            ],
        )
        errors = service.validate_project(project)
        assert any("no_person" in e.message for e in errors)
        assert any("no_company" in e.message for e in errors)

    def test_project_reports_multiple_entity_errors(
        self, service: ValidationService
    ) -> None:
        """validate_project reports errors across multiple entities."""
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            families=[
                Family(
                    id="f1",
                    partners=[FamilyPartner(person_id="bad_p", role="father")],
                    children=[],
                ),
            ],
            dna_profiles=[
                DnaProfile(
                    id="dp1", person_id="bad_p2", company_id="bad_co",
                    test_type="autosomal",
                ),
            ],
        )
        errors = service.validate_project(project)
        family_errors = [e for e in errors if e.entity_type == "Family"]
        profile_errors = [e for e in errors if e.entity_type == "DnaProfile"]
        assert len(family_errors) > 0
        assert len(profile_errors) > 0


# ---------------------------------------------------------------------------
# ValidationError dataclass tests
# ---------------------------------------------------------------------------


class TestValidationErrorDataclass:
    """Tests for the ValidationError dataclass."""

    def test_fields(self) -> None:
        """ValidationError stores entity_type, entity_id, and message."""
        err = ValidationError(entity_type="Person", entity_id="p1", message="Bad ref")
        assert err.entity_type == "Person"
        assert err.entity_id == "p1"
        assert err.message == "Bad ref"

    def test_equality(self) -> None:
        """Two ValidationError instances with same fields are equal."""
        err1 = ValidationError("Family", "f1", "Error A")
        err2 = ValidationError("Family", "f1", "Error A")
        assert err1 == err2


# ---------------------------------------------------------------------------
# Edge cases: missing reference scenarios
# ---------------------------------------------------------------------------


class TestMissingReferenceEdgeCases:
    """Edge-case tests for missing reference error reporting.

    Requirements: 3.4, 22.6
    """

    def test_family_parent_child_link_invalid_parent_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A ParentChildLink with a parent_id not among the family's partners produces an error."""
        family = Family(
            id="f_edge",
            partners=[FamilyPartner(person_id="p1", role="father")],
            children=["p2"],
            parent_child_links=[
                ParentChildLink(child_id="p2", parent_id="nonexistent_partner", parentage_type="biological"),
            ],
        )
        errors = service.validate_entity(family, populated_project)
        assert any("nonexistent_partner" in e.message for e in errors)

    def test_family_parent_child_link_invalid_child_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A ParentChildLink with a child_id not in the family's children list produces an error."""
        family = Family(
            id="f_edge",
            partners=[FamilyPartner(person_id="p1", role="father")],
            children=["p2"],
            parent_child_links=[
                ParentChildLink(child_id="not_a_child", parent_id="p1", parentage_type="biological"),
            ],
        )
        errors = service.validate_entity(family, populated_project)
        assert any("not_a_child" in e.message for e in errors)

    def test_event_multiple_invalid_references(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """An event with both an invalid participant and invalid place reports multiple errors."""
        event = Event(
            id="e_multi",
            type="birth",
            participants=[Participant(person_id="ghost_person", role="subject")],
            place=PlaceRef(place_id="ghost_place"),
        )
        errors = service.validate_entity(event, populated_project)
        person_errors = [e for e in errors if "ghost_person" in e.message]
        place_errors = [e for e in errors if "ghost_place" in e.message]
        assert len(person_errors) >= 1
        assert len(place_errors) >= 1

    def test_source_ref_with_empty_source_id(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A SourceRef with an empty string source_id produces an error."""
        event = Event(
            id="e_empty_src",
            type="birth",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(
                value="1900-01-01", precision="day",
                source_refs=[SourceRef(source_id="", quality="primary")],
            ),
        )
        errors = service.validate_entity(event, populated_project)
        assert len(errors) > 0
        assert any("source_id" in e.message for e in errors)

    def test_family_with_multiple_invalid_children(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A family with multiple non-existent children produces an error for each."""
        family = Family(
            id="f_multi",
            partners=[FamilyPartner(person_id="p1", role="father")],
            children=["bad_child_1", "bad_child_2", "bad_child_3"],
        )
        errors = service.validate_entity(family, populated_project)
        child_errors = [e for e in errors if "bad_child" in e.message]
        assert len(child_errors) == 3

    def test_validate_project_reports_all_missing_references(
        self, service: ValidationService
    ) -> None:
        """A project with multiple entities having broken references reports ALL errors."""
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=[
                Person(id="p1", sex="M", names=[Name(type="birth", given="A", surname="B")]),
            ],
            families=[
                Family(
                    id="f1",
                    partners=[FamilyPartner(person_id="missing_partner", role="father")],
                    children=["missing_child"],
                ),
            ],
            events=[
                Event(
                    id="e1", type="birth",
                    participants=[Participant(person_id="missing_person", role="subject")],
                    place=PlaceRef(place_id="missing_place"),
                ),
            ],
            sources=[
                Source(
                    id="s1", provider="X", source_type="church_book", title="X",
                    repository_refs=[RepositoryRef(repository_id="missing_repo")],
                ),
            ],
        )
        errors = service.validate_project(project)
        # Errors from different entities should all be reported
        family_errors = [e for e in errors if e.entity_type == "Family"]
        event_errors = [e for e in errors if e.entity_type == "Event"]
        source_errors = [e for e in errors if e.entity_type == "Source"]
        assert len(family_errors) >= 2  # invalid partner + invalid child
        assert len(event_errors) >= 2  # invalid participant + invalid place
        assert len(source_errors) >= 1  # invalid repository


# ---------------------------------------------------------------------------
# Residence_Fact ("Boende") validation wiring
# ---------------------------------------------------------------------------


class TestResidenceValidation:
    """Tests that ValidationService wraps residence errors as "Boende" records.

    Requirements: 1.3, 1.4, 1.10, 1.13, 16.1
    """

    def test_well_formed_residence_has_no_errors(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A fact with known person and place and valid bounds validates clean.

        Requirement: 1.13
        """
        residence = ResidenceFact(
            id="residence_1",
            person_id="p1",
            place_id="pl2",
            start=Endpoint(earliest="1840", latest="1845"),
            end=Endpoint(earliest="1850", latest="1855"),
            observations=[
                Observation(
                    source_ref=SourceRef(source_id="s1", quality="primary"),
                    observed_from="1845",
                    observed_to="1850",
                ),
            ],
        )
        assert service.validate_entity(residence, populated_project) == []

    def test_period_without_observations_has_no_errors(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A hand-entered period with zero Observations validates clean.

        Requirement: 16.1
        """
        residence = ResidenceFact(
            id="residence_1",
            person_id="p1",
            place_id="pl2",
            start=Endpoint(latest="1845"),
            end=Endpoint(earliest="1850"),
        )
        assert service.validate_entity(residence, populated_project) == []

    def test_place_of_any_type_has_no_errors(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """A region-level place is as acceptable as a farm.

        Requirement: 1.3
        """
        for place_id in ("pl0", "pl1", "pl2"):
            residence = ResidenceFact(id="residence_1", person_id="p1", place_id=place_id)
            assert service.validate_entity(residence, populated_project) == []

    def test_duplicate_person_place_combination_has_no_errors(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """Two facts sharing person, place and interval both validate clean.

        Requirement: 1.4
        """
        populated_project.residences = [
            ResidenceFact(
                id="residence_1", person_id="p1", place_id="pl2",
                start=Endpoint(earliest="1840"), end=Endpoint(latest="1850"),
            ),
            ResidenceFact(
                id="residence_2", person_id="p1", place_id="pl2",
                start=Endpoint(earliest="1840"), end=Endpoint(latest="1850"),
            ),
        ]
        errors = service.validate_project(populated_project)
        assert [e for e in errors if e.entity_type == "Boende"] == []

    def test_notes_up_to_5000_characters_accepted(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """5000 characters of notes are accepted, 5001 are not.

        Requirement: 1.10
        """
        at_limit = ResidenceFact(
            id="residence_1", person_id="p1", place_id="pl2", notes="a" * 5000
        )
        assert service.validate_entity(at_limit, populated_project) == []

        over_limit = ResidenceFact(
            id="residence_2", person_id="p1", place_id="pl2", notes="a" * 5001
        )
        errors = service.validate_entity(over_limit, populated_project)
        assert errors == [
            ValidationError("Boende", "residence_2", "Anteckningen får vara högst 5000 tecken.")
        ]

    def test_broken_references_reported_as_boende_records(
        self, service: ValidationService, populated_project: ProjectData
    ) -> None:
        """Every message is wrapped with entity_type "Boende" and the fact's id."""
        residence = ResidenceFact(
            id="residence_bad",
            person_id="ghost_person",
            place_id="ghost_place",
            start=Endpoint(event_id="ghost_event"),
            observations=[
                Observation(
                    source_ref=SourceRef(source_id="ghost_source", quality="primary"),
                    observed_from="1845",
                    observed_to="1850",
                ),
            ],
        )
        errors = service.validate_entity(residence, populated_project)
        assert all(e.entity_type == "Boende" for e in errors)
        assert all(e.entity_id == "residence_bad" for e in errors)
        messages = [e.message for e in errors]
        assert messages == [
            "Boendet refererar till en person som inte finns.",
            "Boendet refererar till en plats som inte finns.",
            "Endpunkten refererar till en händelse som inte finns.",
            "Observationen refererar till en källa som inte finns.",
        ]

    def test_validate_project_iterates_residences(
        self, service: ValidationService
    ) -> None:
        """validate_project walks project_data.residences in stored order."""
        project = ProjectData(
            project=ProjectMetadata(title="Test"),
            residences=[
                ResidenceFact(id="residence_1", person_id="ghost_a", place_id=""),
                ResidenceFact(id="residence_2", person_id="", place_id="ghost_b"),
            ],
        )
        errors = service.validate_project(project)
        assert [(e.entity_type, e.entity_id, e.message) for e in errors] == [
            ("Boende", "residence_1", "Boendet måste ange både person och plats."),
            ("Boende", "residence_1", "Boendet refererar till en person som inte finns."),
            ("Boende", "residence_2", "Boendet måste ange både person och plats."),
            ("Boende", "residence_2", "Boendet refererar till en plats som inte finns."),
        ]

    def test_empty_project_has_no_residence_errors(
        self, service: ValidationService, empty_project: ProjectData
    ) -> None:
        """A new project holds zero residences and therefore zero residence errors."""
        assert empty_project.residences == []
        assert service.validate_project(empty_project) == []
