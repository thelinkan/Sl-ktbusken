"""Unit tests for ProjectService.

Tests cover:
- Project creation (folder structure, empty data, settings, translations)
- Open/save/close lifecycle
- Entity addition with validation
- Dirty tracking

Requirements: 1.1, 1.2, 1.3, 1.4, 3.1, 3.2
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from slaktbusken.model.dna import (
    DnaCluster,
    DnaCompany,
    DnaMatch,
    DnaProfile,
    DnaSegment,
    DnaTriangulation,
)
from slaktbusken.model.event import Event, Participant
from slaktbusken.model.family import Family, FamilyPartner
from slaktbusken.model.media import MediaItem
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.research_note import ResearchNote
from slaktbusken.model.source import Repository, Source, StructuredReference
from slaktbusken.services.project_service import (
    ProjectNotOpenError,
    ProjectService,
    ValidationError,
)


@pytest.fixture
def service() -> ProjectService:
    """Create a fresh ProjectService instance."""
    return ProjectService()


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Return a temporary directory to use as project location."""
    return tmp_path


# ---------------------------------------------------------------------------
# 7.1 – Project Creation Tests
# ---------------------------------------------------------------------------


class TestCreateProject:
    """Tests for ProjectService.create_project."""

    def test_creates_project_folder(self, service: ProjectService, project_dir: Path) -> None:
        """Project folder is created at the given location."""
        service.create_project("TestProjekt", project_dir)
        assert (project_dir / "TestProjekt").is_dir()

    def test_creates_data_file(self, service: ProjectService, project_dir: Path) -> None:
        """A .json.gz data file is created inside the project folder."""
        service.create_project("TestProjekt", project_dir)
        data_file = project_dir / "TestProjekt" / "TestProjekt.json.gz"
        assert data_file.exists()

    def test_data_file_has_correct_metadata(
        self, service: ProjectService, project_dir: Path
    ) -> None:
        """The data file contains correct format, version, created_by, language."""
        service.create_project("MittProjekt", project_dir)
        data_file = project_dir / "MittProjekt" / "MittProjekt.json.gz"

        raw = gzip.decompress(data_file.read_bytes())
        data = json.loads(raw)

        assert data["format"] == "släktbuske-file"
        assert data["version"] == "0.1"
        assert data["project"]["title"] == "MittProjekt"
        assert data["project"]["created_by"] == "Släktbuske"
        assert data["project"]["language"] == "sv-SE"

    def test_data_file_has_empty_entity_arrays(
        self, service: ProjectService, project_dir: Path
    ) -> None:
        """All top-level entity arrays are present and empty."""
        service.create_project("TestProjekt", project_dir)
        data_file = project_dir / "TestProjekt" / "TestProjekt.json.gz"

        raw = gzip.decompress(data_file.read_bytes())
        data = json.loads(raw)

        entity_keys = [
            "persons", "families", "events", "places", "sources",
            "media", "repositories", "dna_companies", "dna_profiles",
            "dna_matches", "dna_segments", "dna_clusters",
            "dna_triangulations", "research_notes",
        ]
        for key in entity_keys:
            assert key in data, f"Missing key: {key}"
            assert data[key] == [], f"Expected empty list for {key}"

    def test_creates_settings_file(self, service: ProjectService, project_dir: Path) -> None:
        """A settings.json file is created with defaults."""
        service.create_project("TestProjekt", project_dir)
        settings_file = project_dir / "TestProjekt" / "settings.json"
        assert settings_file.exists()

        settings = json.loads(settings_file.read_text(encoding="utf-8"))
        assert "person_box_config" in settings
        assert "diagram_settings" in settings

    def test_creates_translation_subfolder(
        self, service: ProjectService, project_dir: Path
    ) -> None:
        """A translation subfolder with empty mapping files is created."""
        service.create_project("TestProjekt", project_dir)
        translation_dir = project_dir / "TestProjekt" / "translation"
        assert translation_dir.is_dir()
        assert (translation_dir / "sources.json").exists()
        assert (translation_dir / "places.json").exists()
        assert (translation_dir / "persons.json").exists()

    def test_creates_media_subfolders(
        self, service: ProjectService, project_dir: Path
    ) -> None:
        """All required media category subfolders are created."""
        service.create_project("TestProjekt", project_dir)
        media_dir = project_dir / "TestProjekt" / "media"

        expected = [
            "source-image", "photos", "death-notice", "obituary",
            "funeral-program", "grave-photo", "map", "logo", "document",
        ]
        for subfolder in expected:
            assert (media_dir / subfolder).is_dir(), f"Missing media folder: {subfolder}"

    def test_project_not_dirty_after_creation(
        self, service: ProjectService, project_dir: Path
    ) -> None:
        """A freshly created project is not dirty."""
        service.create_project("TestProjekt", project_dir)
        assert not service.is_dirty

    def test_returns_project_data(self, service: ProjectService, project_dir: Path) -> None:
        """create_project returns a ProjectData instance."""
        result = service.create_project("TestProjekt", project_dir)
        assert result.format == "släktbuske-file"
        assert result.project.title == "TestProjekt"


# ---------------------------------------------------------------------------
# 7.1 – Open / Save / Close Lifecycle Tests
# ---------------------------------------------------------------------------


class TestOpenSaveClose:
    """Tests for open_project, save_project, and close_project."""

    def test_open_project_loads_data(
        self, service: ProjectService, project_dir: Path
    ) -> None:
        """open_project loads a previously saved project."""
        service.create_project("TestProjekt", project_dir)
        data_file = project_dir / "TestProjekt" / "TestProjekt.json.gz"

        # Close and reopen.
        service.close_project()
        result = service.open_project(data_file)

        assert result.format == "släktbuske-file"
        assert result.project.title == "TestProjekt"

    def test_open_project_not_dirty(
        self, service: ProjectService, project_dir: Path
    ) -> None:
        """A freshly opened project is not dirty."""
        service.create_project("TestProjekt", project_dir)
        data_file = project_dir / "TestProjekt" / "TestProjekt.json.gz"

        service.close_project()
        service.open_project(data_file)
        assert not service.is_dirty

    def test_save_project_persists_changes(
        self, service: ProjectService, project_dir: Path
    ) -> None:
        """save_project persists in-memory changes to disk."""
        service.create_project("TestProjekt", project_dir)

        # Add a person and save.
        person = Person(id="person_1", sex="M", names=[Name(type="birth", given="Erik", surname="Svensson")])
        service.add_person(person)
        service.save_project()

        # Reopen and check.
        data_file = project_dir / "TestProjekt" / "TestProjekt.json.gz"
        service.close_project()
        result = service.open_project(data_file)

        assert len(result.persons) == 1
        assert result.persons[0].id == "person_1"

    def test_save_clears_dirty_flag(
        self, service: ProjectService, project_dir: Path
    ) -> None:
        """Saving the project clears the dirty flag."""
        service.create_project("TestProjekt", project_dir)
        person = Person(id="person_1", sex="M", names=[Name(type="birth", given="A", surname="B")])
        service.add_person(person)
        assert service.is_dirty

        service.save_project()
        assert not service.is_dirty

    def test_close_project_resets_state(
        self, service: ProjectService, project_dir: Path
    ) -> None:
        """Closing the project resets all internal state."""
        service.create_project("TestProjekt", project_dir)
        service.close_project()

        assert service.project_path is None
        assert service.settings is None
        assert not service.is_dirty

    def test_close_project_data_inaccessible(
        self, service: ProjectService, project_dir: Path
    ) -> None:
        """After close, accessing data raises ProjectNotOpenError."""
        service.create_project("TestProjekt", project_dir)
        service.close_project()

        with pytest.raises(ProjectNotOpenError):
            _ = service.data

    def test_save_without_open_raises(self, service: ProjectService) -> None:
        """save_project raises if no project is open."""
        with pytest.raises(ProjectNotOpenError):
            service.save_project()

    def test_open_nonexistent_file_raises(self, service: ProjectService, tmp_path: Path) -> None:
        """open_project raises FileNotFoundError for missing files."""
        with pytest.raises(FileNotFoundError):
            service.open_project(tmp_path / "nonexistent.json.gz")


# ---------------------------------------------------------------------------
# 7.2 – Entity Addition with Validation Tests
# ---------------------------------------------------------------------------


class TestAddEntities:
    """Tests for entity addition methods with validation."""

    @pytest.fixture(autouse=True)
    def _create_project(self, service: ProjectService, project_dir: Path) -> None:
        """Create a project before each test."""
        service.create_project("TestProjekt", project_dir)

    def test_add_valid_person(self, service: ProjectService) -> None:
        """Adding a valid person succeeds."""
        person = Person(id="p1", sex="M", names=[Name(type="birth", given="Erik", surname="A")])
        result = service.add_person(person)
        assert result.id == "p1"
        assert len(service.data.persons) == 1

    def test_add_invalid_person_raises(self, service: ProjectService) -> None:
        """Adding a person with no names raises ValidationError."""
        person = Person(id="p1", sex="M", names=[])
        with pytest.raises(ValidationError) as exc_info:
            service.add_person(person)
        assert "minst ett namnfält" in exc_info.value.errors[0]

    def test_add_valid_family(self, service: ProjectService) -> None:
        """Adding a valid family succeeds."""
        family = Family(
            id="f1",
            partners=[FamilyPartner(person_id="p1", role="father")],
            children=[],
        )
        result = service.add_family(family)
        assert result.id == "f1"
        assert len(service.data.families) == 1

    def test_add_invalid_family_raises(self, service: ProjectService) -> None:
        """Adding a family with invalid partner role raises ValidationError."""
        family = Family(
            id="f1",
            partners=[FamilyPartner(person_id="p1", role="invalid_role")],
            children=[],
        )
        with pytest.raises(ValidationError):
            service.add_family(family)

    def test_add_valid_event(self, service: ProjectService) -> None:
        """Adding a valid event succeeds."""
        event = Event(
            id="e1", type="birth",
            participants=[Participant(person_id="p1", role="subject")],
        )
        result = service.add_event(event)
        assert result.id == "e1"
        assert len(service.data.events) == 1

    def test_add_invalid_event_raises(self, service: ProjectService) -> None:
        """Adding an event without participants raises ValidationError."""
        event = Event(id="e1", type="birth", participants=[])
        with pytest.raises(ValidationError):
            service.add_event(event)

    def test_add_valid_place(self, service: ProjectService) -> None:
        """Adding a valid place succeeds."""
        place = Place(id="pl1", type="country", name="Sverige")
        result = service.add_place(place)
        assert result.id == "pl1"
        assert len(service.data.places) == 1

    def test_add_invalid_place_raises(self, service: ProjectService) -> None:
        """Adding a place with invalid type raises ValidationError."""
        place = Place(id="pl1", type="invalid", name="Test")
        with pytest.raises(ValidationError):
            service.add_place(place)

    def test_add_valid_source(self, service: ProjectService) -> None:
        """Adding a valid source succeeds."""
        source = Source(
            id="s1", provider="ArkivDigital", source_type="church_book",
            title="Födelseboken",
        )
        result = service.add_source(source)
        assert result.id == "s1"
        assert len(service.data.sources) == 1

    def test_add_invalid_source_raises(self, service: ProjectService) -> None:
        """Adding a source with invalid source_type raises ValidationError."""
        source = Source(
            id="s1", provider="Test", source_type="invalid_type", title="Test",
        )
        with pytest.raises(ValidationError):
            service.add_source(source)

    def test_add_valid_media(self, service: ProjectService) -> None:
        """Adding a valid media item succeeds."""
        media = MediaItem(id="m1", type="photo", file="photos/img.jpg", title="Foto")
        result = service.add_media(media)
        assert result.id == "m1"
        assert len(service.data.media) == 1

    def test_add_invalid_media_raises(self, service: ProjectService) -> None:
        """Adding a media item with invalid type raises ValidationError."""
        media = MediaItem(id="m1", type="invalid_type", file="x.jpg", title="Test")
        with pytest.raises(ValidationError):
            service.add_media(media)

    def test_add_valid_repository(self, service: ProjectService) -> None:
        """Adding a valid repository succeeds."""
        repo = Repository(id="r1", name="Riksarkivet", type="archive")
        result = service.add_repository(repo)
        assert result.id == "r1"
        assert len(service.data.repositories) == 1

    def test_add_invalid_repository_raises(self, service: ProjectService) -> None:
        """Adding a repository with empty type raises ValidationError."""
        repo = Repository(id="r1", name="Riksarkivet", type="")
        with pytest.raises(ValidationError):
            service.add_repository(repo)

    def test_add_dna_company(self, service: ProjectService) -> None:
        """Adding a DNA company succeeds."""
        company = DnaCompany(id="dc1", name="MyHeritage")
        result = service.add_dna_company(company)
        assert result.id == "dc1"
        assert len(service.data.dna_companies) == 1

    def test_add_valid_dna_profile(self, service: ProjectService) -> None:
        """Adding a valid DNA profile succeeds."""
        profile = DnaProfile(
            id="dp1", person_id="p1", company_id="dc1", test_type="autosomal",
        )
        result = service.add_dna_profile(profile)
        assert result.id == "dp1"
        assert len(service.data.dna_profiles) == 1

    def test_add_invalid_dna_profile_raises(self, service: ProjectService) -> None:
        """Adding a DNA profile with invalid test_type raises ValidationError."""
        profile = DnaProfile(
            id="dp1", person_id="p1", company_id="dc1", test_type="invalid",
        )
        with pytest.raises(ValidationError):
            service.add_dna_profile(profile)

    def test_add_valid_dna_match(self, service: ProjectService) -> None:
        """Adding a valid DNA match succeeds."""
        match = DnaMatch(
            id="dm1", profile1_id="dp1", profile2_id="dp2",
            shared_cm=50.0, shared_percentage=1.5, segment_count=3,
            largest_segment_cm=20.0,
        )
        result = service.add_dna_match(match)
        assert result.id == "dm1"
        assert len(service.data.dna_matches) == 1

    def test_add_invalid_dna_match_raises(self, service: ProjectService) -> None:
        """Adding a DNA match with out-of-range shared_cm raises ValidationError."""
        match = DnaMatch(
            id="dm1", profile1_id="dp1", profile2_id="dp2",
            shared_cm=8000.0, shared_percentage=1.5, segment_count=3,
            largest_segment_cm=20.0,
        )
        with pytest.raises(ValidationError):
            service.add_dna_match(match)

    def test_add_valid_dna_segment(self, service: ProjectService) -> None:
        """Adding a valid DNA segment succeeds."""
        segment = DnaSegment(
            id="ds1", match_id="dm1", chromosome="1",
            start_position=100, end_position=5000, cm=10.5, snp_count=500,
        )
        result = service.add_dna_segment(segment)
        assert result.id == "ds1"
        assert len(service.data.dna_segments) == 1

    def test_add_invalid_dna_segment_raises(self, service: ProjectService) -> None:
        """Adding a segment with start >= end raises ValidationError."""
        segment = DnaSegment(
            id="ds1", match_id="dm1", chromosome="1",
            start_position=5000, end_position=100, cm=10.5,
        )
        with pytest.raises(ValidationError):
            service.add_dna_segment(segment)

    def test_add_valid_dna_cluster(self, service: ProjectService) -> None:
        """Adding a valid DNA cluster succeeds."""
        cluster = DnaCluster(id="dcl1", name="Norrland cluster")
        result = service.add_dna_cluster(cluster)
        assert result.id == "dcl1"
        assert len(service.data.dna_clusters) == 1

    def test_add_invalid_dna_cluster_raises(self, service: ProjectService) -> None:
        """Adding a DNA cluster with empty name raises ValidationError."""
        cluster = DnaCluster(id="dcl1", name="")
        with pytest.raises(ValidationError):
            service.add_dna_cluster(cluster)

    def test_add_valid_dna_triangulation(self, service: ProjectService) -> None:
        """Adding a valid DNA triangulation succeeds."""
        tri = DnaTriangulation(
            id="dt1", company_id="dc1",
            profile_ids=["dp1", "dp2", "dp3"],
            shared_cm=45.5,
            segment_count=3,
            largest_segment_cm=22.1,
        )
        result = service.add_dna_triangulation(tri)
        assert result.id == "dt1"
        assert len(service.data.dna_triangulations) == 1

    def test_add_invalid_dna_triangulation_raises(self, service: ProjectService) -> None:
        """Adding a triangulation with < 3 profiles raises ValidationError."""
        tri = DnaTriangulation(
            id="dt1", company_id="dc1",
            profile_ids=["dp1", "dp2"],
            shared_cm=45.5,
            segment_count=3,
            largest_segment_cm=22.1,
        )
        with pytest.raises(ValidationError):
            service.add_dna_triangulation(tri)

    def test_add_research_note(self, service: ProjectService) -> None:
        """Adding a research note succeeds."""
        note = ResearchNote(id="rn1", title="Notering", text="Kontrollera källa.")
        result = service.add_research_note(note)
        assert result.id == "rn1"
        assert len(service.data.research_notes) == 1


# ---------------------------------------------------------------------------
# 7.3 – Dirty Tracking Tests
# ---------------------------------------------------------------------------


class TestDirtyTracking:
    """Tests for dirty state tracking."""

    @pytest.fixture(autouse=True)
    def _create_project(self, service: ProjectService, project_dir: Path) -> None:
        """Create a project before each test."""
        service.create_project("TestProjekt", project_dir)

    def test_not_dirty_after_create(self, service: ProjectService) -> None:
        """Project is not dirty immediately after creation."""
        assert not service.is_dirty

    def test_dirty_after_add_person(self, service: ProjectService) -> None:
        """Adding a person marks the project as dirty."""
        person = Person(id="p1", sex="F", names=[Name(type="birth", given="Anna", surname="B")])
        service.add_person(person)
        assert service.is_dirty

    def test_dirty_after_add_family(self, service: ProjectService) -> None:
        """Adding a family marks the project as dirty."""
        family = Family(id="f1", partners=[FamilyPartner(person_id="p1", role="mother")], children=[])
        service.add_family(family)
        assert service.is_dirty

    def test_dirty_after_add_event(self, service: ProjectService) -> None:
        """Adding an event marks the project as dirty."""
        event = Event(id="e1", type="birth", participants=[Participant(person_id="p1", role="subject")])
        service.add_event(event)
        assert service.is_dirty

    def test_dirty_after_add_dna_company(self, service: ProjectService) -> None:
        """Adding a DNA company marks the project as dirty."""
        company = DnaCompany(id="dc1", name="Test")
        service.add_dna_company(company)
        assert service.is_dirty

    def test_dirty_after_add_research_note(self, service: ProjectService) -> None:
        """Adding a research note marks the project as dirty."""
        note = ResearchNote(id="rn1", title="T", text="Text")
        service.add_research_note(note)
        assert service.is_dirty

    def test_save_clears_dirty(self, service: ProjectService) -> None:
        """Saving the project clears the dirty flag."""
        person = Person(id="p1", sex="M", names=[Name(type="birth", given="A", surname="B")])
        service.add_person(person)
        assert service.is_dirty

        service.save_project()
        assert not service.is_dirty

    def test_close_clears_dirty(self, service: ProjectService) -> None:
        """Closing the project resets dirty to False."""
        person = Person(id="p1", sex="M", names=[Name(type="birth", given="A", surname="B")])
        service.add_person(person)
        assert service.is_dirty

        service.close_project()
        assert not service.is_dirty

    def test_failed_validation_does_not_mark_dirty(self, service: ProjectService) -> None:
        """A failed add (validation error) does not mark the project dirty."""
        # Start clean
        assert not service.is_dirty

        # Try to add invalid person (no names)
        person = Person(id="p1", sex="M", names=[])
        with pytest.raises(ValidationError):
            service.add_person(person)

        # Still clean
        assert not service.is_dirty

    def test_open_project_not_dirty(
        self, service: ProjectService, project_dir: Path
    ) -> None:
        """Opening a project sets dirty to False regardless of prior state."""
        # Modify and save
        person = Person(id="p1", sex="M", names=[Name(type="birth", given="A", surname="B")])
        service.add_person(person)
        service.save_project()

        # Close and reopen
        data_file = project_dir / "TestProjekt" / "TestProjekt.json.gz"
        service.close_project()
        service.open_project(data_file)
        assert not service.is_dirty
