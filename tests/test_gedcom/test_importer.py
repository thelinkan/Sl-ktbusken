"""Unit tests for the GEDCOM importer module.

Tests verify correct entity creation and field mappings during GEDCOM import,
including ArkivDigital repository detection, re-import support, and warning
generation.

Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 11.7, 22.3
"""

from __future__ import annotations

from pathlib import Path

import pytest

from slaktbusken.gedcom.importer import (
    GEDCOMImporter,
    ImportResult,
    parse_gedcom_date,
    _extract_gedcom_person,
    _extract_gedcom_family,
    _extract_gedcom_source,
    _parse_gedcom_name,
)
from slaktbusken.gedcom.parser import GedcomParseError, parse_gedcom
from slaktbusken.model.project import ProjectData, ProjectMetadata


# ---------------------------------------------------------------------------
# Sample GEDCOM content helpers
# ---------------------------------------------------------------------------

_MINIMAL_GEDCOM = """\
0 HEAD
1 SOUR Test
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
1 BIRT
2 DATE 15 MAR 1850
2 PLAC Ljusdal, Gävleborgs län, Sverige
1 DEAT
2 DATE 2 JAN 1920
2 PLAC Sundsvall, Västernorrlands län, Sverige
0 @I2@ INDI
1 NAME Anna /Persson/
1 SEX F
1 BIRT
2 DATE 22 JUL 1855
2 PLAC Ljusdal, Gävleborgs län, Sverige
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 MARR
2 DATE 10 JUN 1875
2 PLAC Ljusdal, Gävleborgs län, Sverige
0 @I3@ INDI
1 NAME Erik /Andersson/
1 SEX M
1 BIRT
2 DATE 3 FEB 1876
0 TRLR
"""

_GEDCOM_WITH_SOURCE = """\
0 HEAD
1 SOUR Test
1 CHAR UTF-8
0 @S1@ SOUR
1 TITL Ljusdal husförhör
1 AUTH Riksarkivet
1 DATA
2 TEXT Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
1 BIRT
2 DATE 15 MAR 1850
2 PLAC Ljusdal, Gävleborgs län, Sverige
2 SOUR @S1@
0 TRLR
"""

_GEDCOM_WITH_ARKIVDIGITAL = """\
0 HEAD
1 SOUR Test
1 CHAR UTF-8
0 @S1@ SOUR
1 TITL ArkivDigital: Ljusdal AI:23d
1 DATA
2 TEXT ArkivDigital: Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915
0 @I1@ INDI
1 NAME Anna /Persson/
1 SEX F
0 TRLR
"""

_GEDCOM_WITH_UNSUPPORTED_TAGS = """\
0 HEAD
1 SOUR Test
0 @I1@ INDI
1 NAME Test /Person/
1 SEX M
0 _CUSTOM Custom data
0 OBJE Multimedia
0 TRLR
"""

_GEDCOM_MULTIPLE_EVENTS = """\
0 HEAD
1 SOUR Test
0 @I1@ INDI
1 NAME Karl /Svensson/
1 SEX M
1 BIRT
2 DATE 1 JAN 1800
2 PLAC Stockholm, Stockholms län, Sverige
1 BAPM
2 DATE 15 JAN 1800
2 PLAC Stockholm, Stockholms län, Sverige
1 DEAT
2 DATE 30 DEC 1870
1 BURI
2 DATE 5 JAN 1871
2 PLAC Stockholm, Stockholms län, Sverige
0 TRLR
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_project() -> ProjectData:
    """An empty project data container."""
    return ProjectData(
        project=ProjectMetadata(title="Test Project"),
    )


@pytest.fixture
def translation_dir(tmp_path: Path) -> Path:
    """A temporary directory for translation files."""
    d = tmp_path / "translation"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# parse_gedcom_date tests
# ---------------------------------------------------------------------------


class TestParseGedcomDate:
    """Tests for GEDCOM date parsing."""

    def test_full_date(self) -> None:
        """Full date '1 JAN 1900' is parsed to day precision."""
        result = parse_gedcom_date("1 JAN 1900")
        assert result is not None
        assert result.value == "1900-01-01"
        assert result.precision == "day"

    def test_month_year_date(self) -> None:
        """Month-year date 'MAR 1850' is parsed to month precision."""
        result = parse_gedcom_date("MAR 1850")
        assert result is not None
        assert result.value == "1850-03"
        assert result.precision == "month"

    def test_year_only(self) -> None:
        """Year-only date '1900' is parsed to year precision."""
        result = parse_gedcom_date("1900")
        assert result is not None
        assert result.value == "1900"
        assert result.precision == "year"

    def test_approximate_date(self) -> None:
        """ABT prefix produces approximate precision."""
        result = parse_gedcom_date("ABT 1900")
        assert result is not None
        assert result.value == "1900"
        assert result.precision == "approximate"

    def test_before_date(self) -> None:
        """BEF prefix produces approximate precision."""
        result = parse_gedcom_date("BEF 15 MAR 1900")
        assert result is not None
        assert result.value == "1900-03-15"
        assert result.precision == "approximate"

    def test_after_date(self) -> None:
        """AFT prefix produces approximate precision."""
        result = parse_gedcom_date("AFT JAN 1900")
        assert result is not None
        assert result.value == "1900-01"
        assert result.precision == "approximate"

    def test_empty_date_returns_none(self) -> None:
        """An empty string returns None."""
        assert parse_gedcom_date("") is None

    def test_none_returns_none(self) -> None:
        """None-like empty string returns None."""
        assert parse_gedcom_date("   ") is None

    def test_two_digit_day(self) -> None:
        """Two-digit day is handled correctly."""
        result = parse_gedcom_date("15 MAR 1850")
        assert result is not None
        assert result.value == "1850-03-15"
        assert result.precision == "day"


# ---------------------------------------------------------------------------
# Name parsing tests
# ---------------------------------------------------------------------------


class TestParseGedcomName:
    """Tests for GEDCOM NAME value parsing."""

    def test_standard_name(self) -> None:
        """Standard 'Given /Surname/' format is parsed correctly."""
        given, surname = _parse_gedcom_name("Johan /Andersson/")
        assert given == "Johan"
        assert surname == "Andersson"

    def test_multiple_given_names(self) -> None:
        """Multiple given names are preserved."""
        given, surname = _parse_gedcom_name("Johan Erik /Andersson/")
        assert given == "Johan Erik"
        assert surname == "Andersson"

    def test_no_surname(self) -> None:
        """Name without slashes treats all as given name."""
        given, surname = _parse_gedcom_name("Johan")
        assert given == "Johan"
        assert surname == ""

    def test_empty_given_name(self) -> None:
        """Name with only surname has empty given name."""
        given, surname = _parse_gedcom_name("/Andersson/")
        assert given == ""
        assert surname == "Andersson"

    def test_empty_string(self) -> None:
        """Empty string returns empty given and surname."""
        given, surname = _parse_gedcom_name("")
        assert given == ""
        assert surname == ""


# ---------------------------------------------------------------------------
# GEDCOMImporter tests — basic import
# ---------------------------------------------------------------------------


class TestGEDCOMImporterBasicImport:
    """Tests for basic GEDCOM file import."""

    def test_import_minimal_gedcom(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """A minimal GEDCOM file creates persons, family, and events."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_MINIMAL_GEDCOM, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        result = importer.import_file(gedcom_file)

        assert result.persons_added == 3
        assert result.families_added == 1
        assert result.events_added > 0
        assert len(empty_project.persons) == 3
        assert len(empty_project.families) == 1

    def test_person_field_mapping(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Person fields (name, sex) are correctly mapped from GEDCOM."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_MINIMAL_GEDCOM, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        # Find Johan Andersson
        johan = next(
            (p for p in empty_project.persons
             if p.names and p.names[0].given == "Johan"
             and p.names[0].surname == "Andersson"),
            None,
        )
        assert johan is not None
        assert johan.sex == "M"
        assert johan.names[0].type == "birth"

    def test_birth_event_created(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """A birth event is created with correct date and place."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_MINIMAL_GEDCOM, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        # Find Johan's person ID
        johan = next(
            p for p in empty_project.persons
            if p.names and p.names[0].given == "Johan"
        )

        # Find birth event for Johan
        birth_events = [
            e for e in empty_project.events
            if e.type == "birth"
            and any(part.person_id == johan.id for part in e.participants)
        ]
        assert len(birth_events) == 1
        birth_event = birth_events[0]
        assert birth_event.date is not None
        assert birth_event.date.value == "1850-03-15"
        assert birth_event.date.precision == "day"

    def test_death_event_created(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """A death event is created with correct date."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_MINIMAL_GEDCOM, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        johan = next(
            p for p in empty_project.persons
            if p.names and p.names[0].given == "Johan"
        )
        death_events = [
            e for e in empty_project.events
            if e.type == "death"
            and any(part.person_id == johan.id for part in e.participants)
        ]
        assert len(death_events) == 1
        assert death_events[0].date is not None
        assert death_events[0].date.value == "1920-01-02"

    def test_family_creation_with_partners_and_children(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Family is created with correct partners and children."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_MINIMAL_GEDCOM, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        assert len(empty_project.families) == 1
        family = empty_project.families[0]

        # Should have 2 partners (husband and wife)
        assert len(family.partners) == 2
        roles = {p.role for p in family.partners}
        assert "husband" in roles
        assert "wife" in roles

        # Should have 1 child
        assert len(family.children) == 1

    def test_marriage_event_created(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Marriage event is created for the family with correct date."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_MINIMAL_GEDCOM, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        marriage_events = [e for e in empty_project.events if e.type == "marriage"]
        assert len(marriage_events) == 1
        assert marriage_events[0].date is not None
        assert marriage_events[0].date.value == "1875-06-10"

    def test_parent_child_links_created(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """ParentChildLinks default to biological parentage_type."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_MINIMAL_GEDCOM, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        family = empty_project.families[0]
        assert len(family.parent_child_links) == 2  # One per parent
        for link in family.parent_child_links:
            assert link.parentage_type == "biological"

    def test_places_created(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Places are created with hierarchical structure."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_MINIMAL_GEDCOM, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        result = importer.import_file(gedcom_file)

        # Should have created places for the hierarchy
        assert result.places_added > 0
        assert len(empty_project.places) > 0

        # Check that "Sverige" exists as a country
        sverige = next(
            (p for p in empty_project.places if p.name == "Sverige"),
            None,
        )
        assert sverige is not None
        assert sverige.type == "country"


# ---------------------------------------------------------------------------
# Source import tests
# ---------------------------------------------------------------------------


class TestGEDCOMImporterSources:
    """Tests for GEDCOM source import and mapping."""

    def test_source_import(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """A GEDCOM SOUR record creates a Source entity."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_WITH_SOURCE, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        result = importer.import_file(gedcom_file)

        assert result.sources_added == 1
        assert len(empty_project.sources) == 1
        source = empty_project.sources[0]
        assert source.title == "Ljusdal husförhör"
        assert source.source_type == "church_book"

    def test_source_citation_on_event(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Source citations on events are preserved as SourceRefs."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_WITH_SOURCE, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        # Find birth event
        birth_events = [e for e in empty_project.events if e.type == "birth"]
        assert len(birth_events) == 1
        birth = birth_events[0]

        # Source ref should be attached to the date
        assert birth.date is not None
        assert len(birth.date.source_refs) == 1
        assert birth.date.source_refs[0].source_id == empty_project.sources[0].id


# ---------------------------------------------------------------------------
# ArkivDigital detection tests
# ---------------------------------------------------------------------------


class TestGEDCOMImporterArkivDigital:
    """Tests for ArkivDigital repository detection during import."""

    def test_arkivdigital_repository_created(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """ArkivDigital sources create an ArkivDigital Repository."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_WITH_ARKIVDIGITAL, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        # Should have created a repository
        assert len(empty_project.repositories) == 1
        repo = empty_project.repositories[0]
        assert repo.name == "ArkivDigital"
        assert repo.type == "digital_archive"

    def test_arkivdigital_repository_ref_on_source(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """ArkivDigital sources have a RepositoryRef attached."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_WITH_ARKIVDIGITAL, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        source = empty_project.sources[0]
        assert len(source.repository_refs) == 1
        assert source.repository_refs[0].repository_id == empty_project.repositories[0].id

    def test_arkivdigital_repository_reused(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Multiple ArkivDigital sources reuse the same Repository."""
        gedcom_content = """\
0 HEAD
1 SOUR Test
0 @S1@ SOUR
1 TITL ArkivDigital: Source 1
1 DATA
2 TEXT ArkivDigital: Ljusdal (X) AI:23d (1883-1887) Bild: 23
0 @S2@ SOUR
1 TITL ArkivDigital: Source 2
1 DATA
2 TEXT ArkivDigital: Sundsvall (Y) FI:2 (1790-1800) Bild: 5
0 TRLR
"""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(gedcom_content, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        # Only one repository should exist
        assert len(empty_project.repositories) == 1
        # Both sources should reference it
        for source in empty_project.sources:
            assert len(source.repository_refs) == 1
            assert (
                source.repository_refs[0].repository_id
                == empty_project.repositories[0].id
            )


# ---------------------------------------------------------------------------
# Re-import tests
# ---------------------------------------------------------------------------


class TestGEDCOMImporterReImport:
    """Tests for re-import: updating existing records and adding new ones."""

    def test_reimport_updates_existing_person(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Re-importing updates existing persons rather than duplicating."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_MINIMAL_GEDCOM, encoding="utf-8")

        # First import
        importer1 = GEDCOMImporter(empty_project, translation_dir)
        result1 = importer1.import_file(gedcom_file)
        assert result1.persons_added == 3

        initial_person_count = len(empty_project.persons)

        # Second import (re-import)
        importer2 = GEDCOMImporter(empty_project, translation_dir)
        result2 = importer2.import_file(gedcom_file)

        # Should update existing, not add new
        assert result2.persons_updated == 3
        assert result2.persons_added == 0
        # Person count should remain the same
        assert len(empty_project.persons) == initial_person_count

    def test_reimport_adds_new_persons(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Re-import adds new persons that weren't in previous import."""
        # First import with minimal data
        gedcom_first = """\
0 HEAD
1 SOUR Test
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
0 TRLR
"""
        gedcom_file = tmp_path / "first.ged"
        gedcom_file.write_text(gedcom_first, encoding="utf-8")

        importer1 = GEDCOMImporter(empty_project, translation_dir)
        importer1.import_file(gedcom_file)
        assert len(empty_project.persons) == 1

        # Second import with additional person
        gedcom_second = """\
0 HEAD
1 SOUR Test
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
0 @I2@ INDI
1 NAME Anna /Persson/
1 SEX F
0 TRLR
"""
        gedcom_file2 = tmp_path / "second.ged"
        gedcom_file2.write_text(gedcom_second, encoding="utf-8")

        importer2 = GEDCOMImporter(empty_project, translation_dir)
        result2 = importer2.import_file(gedcom_file2)

        assert result2.persons_updated == 1  # Johan updated
        assert result2.persons_added == 1  # Anna added
        assert len(empty_project.persons) == 2

    def test_reimport_preserves_person_id(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Re-import preserves the App_JSON person ID from translation file."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_content = """\
0 HEAD
1 SOUR Test
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
0 TRLR
"""
        gedcom_file.write_text(gedcom_content, encoding="utf-8")

        # First import
        importer1 = GEDCOMImporter(empty_project, translation_dir)
        importer1.import_file(gedcom_file)
        original_id = empty_project.persons[0].id

        # Re-import
        importer2 = GEDCOMImporter(empty_project, translation_dir)
        importer2.import_file(gedcom_file)

        # ID should be preserved
        assert empty_project.persons[0].id == original_id


# ---------------------------------------------------------------------------
# Warning tests
# ---------------------------------------------------------------------------


class TestGEDCOMImporterWarnings:
    """Tests for warning generation during import."""

    def test_unsupported_tag_warning(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Unsupported level-0 tags generate Swedish-language warnings."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_WITH_UNSUPPORTED_TAGS, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        result = importer.import_file(gedcom_file)

        # Should have warnings for _CUSTOM and OBJE
        unsupported_warnings = [
            w for w in result.warnings
            if "ej stödd GEDCOM-taggtyp" in w
        ]
        assert len(unsupported_warnings) >= 2

    def test_warning_includes_line_number(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Warnings include the GEDCOM line number."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_WITH_UNSUPPORTED_TAGS, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        result = importer.import_file(gedcom_file)

        for w in result.warnings:
            if "ej stödd GEDCOM-taggtyp" in w:
                assert "Rad " in w

    def test_warning_includes_tag(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Warnings include the unsupported tag name."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_WITH_UNSUPPORTED_TAGS, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        result = importer.import_file(gedcom_file)

        tags_in_warnings = []
        for w in result.warnings:
            if "_CUSTOM" in w:
                tags_in_warnings.append("_CUSTOM")
            if "OBJE" in w:
                tags_in_warnings.append("OBJE")

        assert "_CUSTOM" in tags_in_warnings
        assert "OBJE" in tags_in_warnings


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------


class TestGEDCOMImporterErrors:
    """Tests for error handling during import."""

    def test_non_gedcom_file_raises_error(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Importing a non-GEDCOM file raises GedcomParseError."""
        non_gedcom = tmp_path / "not_gedcom.txt"
        non_gedcom.write_text("This is not a GEDCOM file.", encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        with pytest.raises(GedcomParseError):
            importer.import_file(non_gedcom)

    def test_nonexistent_file_raises_error(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Importing a nonexistent file raises FileNotFoundError."""
        missing = tmp_path / "missing.ged"

        importer = GEDCOMImporter(empty_project, translation_dir)
        with pytest.raises(FileNotFoundError):
            importer.import_file(missing)


# ---------------------------------------------------------------------------
# Multiple events per person tests
# ---------------------------------------------------------------------------


class TestGEDCOMImporterMultipleEvents:
    """Tests for handling multiple events per person."""

    def test_multiple_events_per_person(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """A person with multiple event tags creates multiple events."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_MULTIPLE_EVENTS, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        result = importer.import_file(gedcom_file)

        # Should have birth, baptism, death, burial = 4 events
        assert result.events_added == 4

        karl = empty_project.persons[0]

        # Verify event types
        event_types = set()
        for event in empty_project.events:
            if any(p.person_id == karl.id for p in event.participants):
                event_types.add(event.type)

        assert "birth" in event_types
        assert "baptism" in event_types
        assert "death" in event_types
        assert "burial" in event_types

    def test_event_place_shared(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Multiple events at the same place share a single Place entity."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_MULTIPLE_EVENTS, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        # Stockholm should appear only once in places
        stockholm_places = [
            p for p in empty_project.places
            if "Stockholm" in p.name and p.type == "parish"
        ]
        # Should be exactly one Stockholm parish
        assert len(stockholm_places) == 1


# ---------------------------------------------------------------------------
# Translation file persistence tests
# ---------------------------------------------------------------------------


class TestGEDCOMImporterTranslationPersistence:
    """Tests for translation file persistence after import."""

    def test_translation_files_created(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Translation files are created after import."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_MINIMAL_GEDCOM, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        assert (translation_dir / "sources.json").exists()
        assert (translation_dir / "persons.json").exists()
        assert (translation_dir / "places.json").exists()

    def test_person_mappings_saved(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Person translation mappings are persisted after import."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_MINIMAL_GEDCOM, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        from slaktbusken.persistence.translation_io import read_all

        data = read_all(translation_dir)
        assert len(data.persons) == 3
        # Verify GEDCOM IDs are stored
        gedcom_ids = {m.gedcom_id for m in data.persons}
        assert "@I1@" in gedcom_ids
        assert "@I2@" in gedcom_ids
        assert "@I3@" in gedcom_ids
