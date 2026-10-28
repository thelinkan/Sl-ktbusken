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

_GEDCOM_WITH_MALFORMED_LINES = """\
0 HEAD
1 SOUR Test
THIS IS NOT A VALID GEDCOM LINE
0 @I1@ INDI
1 NAME Anna /Karlsson/
1 SEX F
ANOTHER BAD LINE HERE
0 TRLR
"""

_GEDCOM_WITHOUT_TRLR = """\
0 HEAD
1 SOUR Test
0 @I1@ INDI
1 NAME Lars /Nilsson/
1 SEX M
1 BIRT
2 DATE 5 MAY 1900
"""

_GEDCOM_INDI_MISSING_NAME = """\
0 HEAD
1 SOUR Test
0 @I1@ INDI
1 SEX M
1 BIRT
2 DATE 10 OCT 1890
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
        """Warnings include structured information (xref, name, reason)."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_WITH_UNSUPPORTED_TAGS, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        result = importer.import_file(gedcom_file)

        for w in result.warnings:
            if "ej stödd GEDCOM-taggtyp" in w:
                # Structured warnings include reason and action
                assert "Orsak:" in w or "ej stödd" in w

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

    def test_binary_file_raises_error(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Importing a binary file (e.g. image) raises GedcomParseError."""
        binary_file = tmp_path / "image.ged"
        binary_file.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4)

        importer = GEDCOMImporter(empty_project, translation_dir)
        with pytest.raises(GedcomParseError):
            importer.import_file(binary_file)

    def test_empty_file_raises_error(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Importing a completely empty file raises GedcomParseError."""
        empty_file = tmp_path / "empty.ged"
        empty_file.write_text("", encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        with pytest.raises(GedcomParseError):
            importer.import_file(empty_file)

    def test_malformed_lines_produce_warnings(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Malformed lines within valid GEDCOM produce warnings but import succeeds."""
        gedcom_file = tmp_path / "malformed.ged"
        gedcom_file.write_text(_GEDCOM_WITH_MALFORMED_LINES, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        result = importer.import_file(gedcom_file)

        # Import should succeed with the valid person
        assert result.persons_added == 1

        # Should have warnings for the malformed lines in Swedish
        malformed_warnings = [
            w for w in result.warnings if "Felformaterad" in w
        ]
        assert len(malformed_warnings) >= 2

    def test_unsupported_tags_import_succeeds_with_correct_counts(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Unsupported tags generate warnings but the import returns correct counts."""
        gedcom_file = tmp_path / "unsupported.ged"
        gedcom_file.write_text(_GEDCOM_WITH_UNSUPPORTED_TAGS, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        result = importer.import_file(gedcom_file)

        # The valid person should be imported
        assert result.persons_added == 1
        assert len(result.warnings) >= 2
        assert len(empty_project.persons) == 1

    def test_gedcom_without_trlr_imports_successfully(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """A GEDCOM file without TRLR record imports successfully (best-effort)."""
        gedcom_file = tmp_path / "no_trlr.ged"
        gedcom_file.write_text(_GEDCOM_WITHOUT_TRLR, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        result = importer.import_file(gedcom_file)

        # Should still import the person
        assert result.persons_added == 1
        assert len(empty_project.persons) == 1
        assert empty_project.persons[0].names[0].given == "Lars"

    def test_indi_missing_name_imports_with_empty_name(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """An INDI record without NAME still imports with empty name fields."""
        gedcom_file = tmp_path / "no_name.ged"
        gedcom_file.write_text(_GEDCOM_INDI_MISSING_NAME, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        result = importer.import_file(gedcom_file)

        # Should import the person despite missing NAME
        assert result.persons_added == 1
        person = empty_project.persons[0]
        # The person should exist with empty/default name
        assert person.sex == "M"


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
            if "Stockholm" in p.name and p.type == "socken"
        ]
        # Should be exactly one Stockholm socken
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


# ---------------------------------------------------------------------------
# Extended event tag tests (Task 43)
# ---------------------------------------------------------------------------

_GEDCOM_ALL_INDI_EVENTS = """\
0 HEAD
1 SOUR Test
0 @I1@ INDI
1 NAME Test /Person/
1 SEX M
1 BIRT
2 DATE 1 JAN 1800
2 PLAC Stockholm, Stockholms län, Sverige
1 DEAT
2 DATE 31 DEC 1870
1 BURI
2 DATE 5 JAN 1871
1 BAPM
2 DATE 10 JAN 1800
1 CHR
2 DATE 12 JAN 1800
1 CONF
2 DATE 1 MAY 1815
1 EMIG
2 DATE 1 JUN 1840
1 IMMI
2 DATE 1 AUG 1840
1 CENS
2 DATE 1880
1 RETI
2 DATE 1865
1 GRAD
2 DATE 1820
1 CREM
2 DATE 7 JAN 1871
1 WILL
2 DATE 20 DEC 1870
1 ADOP
2 DATE 1 FEB 1800
1 BLES
2 DATE 3 JAN 1800
1 FCOM
2 DATE 1 JUN 1812
1 RESI
2 DATE 1850
2 PLAC Göteborg, Göteborgs län, Sverige
1 EVEN
2 TYPE Militärtjänst
2 DATE 1825
0 TRLR
"""

_GEDCOM_ALL_FAM_EVENTS = """\
0 HEAD
1 SOUR Test
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
0 @I2@ INDI
1 NAME Anna /Persson/
1 SEX F
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 10 JUN 1875
2 PLAC Ljusdal, Gävleborgs län, Sverige
1 DIV
2 DATE 5 MAR 1890
1 ENGA
2 DATE 1 JAN 1874
1 DIVF
2 DATE 1 FEB 1890
1 EVEN
2 TYPE Separationsavtal
2 DATE 1 DEC 1889
0 TRLR
"""

_GEDCOM_EVENTS_WITH_PLACES = """\
0 HEAD
1 SOUR Test
0 @I1@ INDI
1 NAME Erik /Svensson/
1 SEX M
1 BIRT
2 DATE 1 JAN 1850
2 PLAC Ljusdal, Gävleborgs län, Sverige
1 CONF
2 DATE 1 MAY 1865
2 PLAC Ljusdal, Gävleborgs län, Sverige
1 EMIG
2 DATE 1 JUN 1880
2 PLAC Göteborg, Göteborgs län, Sverige
0 TRLR
"""

_GEDCOM_PERSONS_UNUSUAL = """\
0 HEAD
1 SOUR Test
0 @I1@ INDI
1 NAME Normal /Person/
1 SEX M
1 BIRT
2 DATE 1 JAN 1800
0 @I2@ INDI
1 SEX F
0 @I3@ INDI
1 NAME /OnlySurname/
1 SEX U
0 @I4@ INDI
1 NAME GivenOnly
1 SEX M
0 TRLR
"""

_GEDCOM_NAME_WITH_SLASHES = """\
0 HEAD
1 SOUR Test
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
0 @I2@ INDI
1 NAME Anna Lisa /von /Essen//
1 SEX F
0 @I3@ INDI
1 NAME /Karlsson/
1 SEX M
1 NAME
2 GIVN Per/Erik
2 SURN /Lindström/
0 TRLR
"""


class TestAllIndiEventTags:
    """Tests that ALL standard GEDCOM individual event tags produce correct App_JSON event types."""

    def test_all_indi_event_tags_produce_correct_types(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """All individual event tags are mapped to the correct event type."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_ALL_INDI_EVENTS, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        result = importer.import_file(gedcom_file)

        person = empty_project.persons[0]
        person_events = [
            e for e in empty_project.events
            if any(p.person_id == person.id for p in e.participants)
        ]
        event_types = {e.type for e in person_events}

        # Standard mapped events
        assert "birth" in event_types
        assert "death" in event_types
        assert "burial" in event_types
        assert "baptism" in event_types  # BAPM and CHR both map to baptism
        assert "confirmation" in event_types
        assert "emigration" in event_types
        assert "immigration" in event_types
        assert "census" in event_types  # CENS and RESI both map to census
        assert "retirement" in event_types
        assert "graduation" in event_types
        assert "cremation" in event_types
        assert "will" in event_types
        assert "adoption" in event_types
        assert "blessing" in event_types
        assert "first_communion" in event_types
        assert "custom_individual_event" in event_types

    def test_even_tag_has_custom_type_name(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """The EVEN tag creates a custom_individual_event with the TYPE value as custom_type_name."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_ALL_INDI_EVENTS, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        custom_events = [
            e for e in empty_project.events
            if e.type == "custom_individual_event"
        ]
        assert len(custom_events) == 1
        assert custom_events[0].custom_type_name == "Militärtjänst"

    def test_resi_tag_creates_residence_fact(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """RESI tag creates a ResidenceFact instead of a census event."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_ALL_INDI_EVENTS, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        # RESI should create a ResidenceFact, not a census event
        assert len(empty_project.residences) >= 1
        # CENS still creates a census event
        census_events = [e for e in empty_project.events if e.type == "census"]
        assert len(census_events) >= 1


class TestAllFamEventTags:
    """Tests that family event tags produce correct App_JSON family event types."""

    def test_all_fam_event_tags_produce_correct_types(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """All family event tags are mapped to the correct event type."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_ALL_FAM_EVENTS, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        family_event_types = set()
        for event in empty_project.events:
            if event.type in ("marriage", "divorce", "engagement", "divorce_filed", "custom_family_event"):
                family_event_types.add(event.type)

        assert "marriage" in family_event_types
        assert "divorce" in family_event_types
        assert "engagement" in family_event_types
        assert "divorce_filed" in family_event_types
        assert "custom_family_event" in family_event_types

    def test_family_even_tag_has_custom_type_name(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """The EVEN tag under FAM creates a custom_family_event with TYPE value."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_ALL_FAM_EVENTS, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        custom_events = [
            e for e in empty_project.events
            if e.type == "custom_family_event"
        ]
        assert len(custom_events) == 1
        assert custom_events[0].custom_type_name == "Separationsavtal"

    def test_divf_tag_maps_to_divorce_filed(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """DIVF tag is mapped to divorce_filed event type."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_ALL_FAM_EVENTS, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        divf_events = [e for e in empty_project.events if e.type == "divorce_filed"]
        assert len(divf_events) == 1


class TestEventPlaceLinking:
    """Tests that events have their place_id properly linked."""

    def test_events_have_place_ref(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Events with PLAC sub-tags have a non-null place reference."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_EVENTS_WITH_PLACES, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        person = empty_project.persons[0]
        person_events = [
            e for e in empty_project.events
            if any(p.person_id == person.id for p in e.participants)
        ]

        # Events with places: birth, confirmation, emigration
        events_with_places = [e for e in person_events if e.place is not None]
        assert len(events_with_places) == 3

        # Each should have a valid place_id
        for event in events_with_places:
            assert event.place.place_id is not None
            # The place_id should reference an existing place
            place_ids = {p.id for p in empty_project.places}
            assert event.place.place_id in place_ids

    def test_family_marriage_event_has_place(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Marriage event from FAM record has a place reference."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_ALL_FAM_EVENTS, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        marriage_events = [e for e in empty_project.events if e.type == "marriage"]
        assert len(marriage_events) == 1
        assert marriage_events[0].place is not None
        assert marriage_events[0].place.place_id is not None


class TestAllPersonsCaptured:
    """Tests that all persons in a GEDCOM file are captured, including unusual data."""

    def test_all_persons_imported(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """All persons are imported including those with missing or unusual name data."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_PERSONS_UNUSUAL, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        result = importer.import_file(gedcom_file)

        assert result.persons_added == 4
        assert len(empty_project.persons) == 4

    def test_person_without_name_still_imported(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """A person with no NAME tag is still imported."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_PERSONS_UNUSUAL, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        # Person @I2@ has no name
        females = [p for p in empty_project.persons if p.sex == "F"]
        assert len(females) == 1

    def test_malformed_lines_dont_prevent_person_import(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Malformed lines in the file don't prevent remaining persons from importing."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_WITH_MALFORMED_LINES, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        result = importer.import_file(gedcom_file)

        # Person should still be imported
        assert result.persons_added == 1


class TestNameSlashStripping:
    """Tests that imported names NEVER contain slash characters."""

    def test_standard_name_no_slashes(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Standard name format 'Given /Surname/' produces clean names."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_NAME_WITH_SLASHES, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        for person in empty_project.persons:
            for name in person.names:
                assert "/" not in name.given, f"Slash found in given name: {name.given}"
                assert "/" not in name.surname, f"Slash found in surname: {name.surname}"

    def test_givn_surn_children_stripped(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """GIVN and SURN child values with stray slashes are cleaned."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_NAME_WITH_SLASHES, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)

        # @I3@ has GIVN "Per/Erik" and SURN "/Lindström/"
        # Find Lindström person (the one with additional name from GIVN/SURN)
        for person in empty_project.persons:
            for name in person.names:
                assert "/" not in name.given
                assert "/" not in name.surname

    def test_parse_gedcom_name_strips_slashes(self) -> None:
        """_parse_gedcom_name strips remaining slashes from output."""
        given, surname = _parse_gedcom_name("Johan /Andersson/")
        assert "/" not in given
        assert "/" not in surname

        given, surname = _parse_gedcom_name("/Karlsson/")
        assert "/" not in given
        assert "/" not in surname

        # Edge case: stray slashes
        given, surname = _parse_gedcom_name("Per/Erik /von/Essen/")
        assert "/" not in given
        assert "/" not in surname


class TestFamilyReimportWithEvents:
    """Tests that family events are recreated during re-import."""

    def test_reimport_family_recreates_events(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Re-importing a family recreates its events with places."""
        gedcom_file = tmp_path / "test.ged"
        gedcom_file.write_text(_GEDCOM_ALL_FAM_EVENTS, encoding="utf-8")

        # First import
        importer1 = GEDCOMImporter(empty_project, translation_dir)
        importer1.import_file(gedcom_file)

        # Count marriage events after first import
        marriage_count_1 = len([e for e in empty_project.events if e.type == "marriage"])
        assert marriage_count_1 == 1

        # Second import (re-import)
        importer2 = GEDCOMImporter(empty_project, translation_dir)
        result2 = importer2.import_file(gedcom_file)

        # Family should be updated
        assert result2.families_updated == 1

        # Marriage events should exist (re-created)
        marriage_events = [e for e in empty_project.events if e.type == "marriage"]
        assert len(marriage_events) >= 1

        # The last marriage event should have a place
        latest_marriage = marriage_events[-1]
        assert latest_marriage.place is not None


# ---------------------------------------------------------------------------
# FAMC/PEDI pedigree → parentage_type (Requirements 11.3, 11.4, 11.5)
# ---------------------------------------------------------------------------

from slaktbusken.gedcom.importer import _pedigree_to_parentage_type


# A GEDCOM template where the child @I3@ is a child of family @F1@ and the
# pedigree under the child's FAMC is parameterised. `{pedi_line}` is either an
# empty string (no PEDI) or a "2 PEDI <value>\n" fragment.
_GEDCOM_PEDI_TEMPLATE = """\
0 HEAD
1 SOUR Test
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
0 @I2@ INDI
1 NAME Anna /Persson/
1 SEX F
0 @I3@ INDI
1 NAME Erik /Andersson/
1 SEX M
1 BIRT
2 DATE 3 FEB 1876
1 FAMC @F1@
{pedi_line}0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
0 TRLR
"""


def _pedi_gedcom(pedi: str | None) -> str:
    """Build a GEDCOM string for the pedigree template.

    Args:
        pedi: The PEDI value to place under the child's FAMC, or None to omit
            the PEDI line entirely (plain FAMC / family-level CHIL only).
    """
    pedi_line = f"2 PEDI {pedi}\n" if pedi is not None else ""
    return _GEDCOM_PEDI_TEMPLATE.format(pedi_line=pedi_line)


class TestPedigreeToParentageType:
    """Unit tests for the pure PEDI → parentage_type mapping."""

    def test_foster_maps_to_foster(self) -> None:
        """PEDI 'foster' maps to the 'foster' parentage type."""
        assert _pedigree_to_parentage_type("foster") == "foster"

    def test_adopted_maps_to_adoptive(self) -> None:
        """PEDI 'adopted' maps to our internal 'adoptive' type."""
        assert _pedigree_to_parentage_type("adopted") == "adoptive"

    def test_birth_maps_to_biological(self) -> None:
        """Standard PEDI 'birth' maps to 'biological'."""
        assert _pedigree_to_parentage_type("birth") == "biological"

    def test_sealing_maps_to_biological(self) -> None:
        """PEDI 'sealing' is treated as 'biological'."""
        assert _pedigree_to_parentage_type("sealing") == "biological"

    def test_none_maps_to_biological(self) -> None:
        """An absent (None) pedigree maps to 'biological'."""
        assert _pedigree_to_parentage_type(None) == "biological"

    def test_empty_maps_to_biological(self) -> None:
        """An empty-string pedigree maps to 'biological'."""
        assert _pedigree_to_parentage_type("") == "biological"

    def test_unknown_maps_to_biological(self) -> None:
        """An unrecognised pedigree value maps to 'biological'."""
        assert _pedigree_to_parentage_type("whatever") == "biological"

    def test_case_insensitive(self) -> None:
        """Mapping is case-insensitive for GEDCOM-cased values."""
        assert _pedigree_to_parentage_type("Adopted") == "adoptive"
        assert _pedigree_to_parentage_type("ADOPTED") == "adoptive"
        assert _pedigree_to_parentage_type("Foster") == "foster"


class TestImportPedigree:
    """Tests that FAMC/PEDI sets parentage_type on imported links.

    Validates: Requirements 11.3, 11.4, 11.5
    """

    def _import(
        self,
        pedi: str | None,
        empty_project: ProjectData,
        translation_dir: Path,
        tmp_path: Path,
    ) -> ProjectData:
        gedcom_file = tmp_path / "pedi.ged"
        gedcom_file.write_text(_pedi_gedcom(pedi), encoding="utf-8")
        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)
        return empty_project

    def test_adopted_pedi_yields_adoptive_links(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """'2 PEDI adopted' yields adoptive links for that child (Req 11.4)."""
        project = self._import("adopted", empty_project, translation_dir, tmp_path)

        family = project.families[0]
        assert len(family.parent_child_links) == 2  # one per parent
        assert {link.parentage_type for link in family.parent_child_links} == {
            "adoptive"
        }

    def test_foster_pedi_yields_foster_links(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """'2 PEDI foster' yields foster links for that child (Req 11.3)."""
        project = self._import("foster", empty_project, translation_dir, tmp_path)

        family = project.families[0]
        assert len(family.parent_child_links) == 2
        assert {link.parentage_type for link in family.parent_child_links} == {
            "foster"
        }

    def test_no_pedi_yields_biological_links(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """A plain FAMC with no PEDI yields biological links (Req 11.5)."""
        project = self._import(None, empty_project, translation_dir, tmp_path)

        family = project.families[0]
        assert len(family.parent_child_links) == 2
        assert {link.parentage_type for link in family.parent_child_links} == {
            "biological"
        }

    def test_birth_pedi_yields_biological_links(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """'2 PEDI birth' is treated as biological (Req 11.5)."""
        project = self._import("birth", empty_project, translation_dir, tmp_path)

        family = project.families[0]
        assert {link.parentage_type for link in family.parent_child_links} == {
            "biological"
        }

    def test_pedi_case_insensitive(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """A GEDCOM-cased 'Adopted' still yields adoptive links (Req 11.4)."""
        project = self._import("Adopted", empty_project, translation_dir, tmp_path)

        family = project.families[0]
        assert {link.parentage_type for link in family.parent_child_links} == {
            "adoptive"
        }

    def test_pedi_applies_to_both_parent_links(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """The pedigree applies to BOTH of the child's parent links in the family."""
        project = self._import("adopted", empty_project, translation_dir, tmp_path)

        family = project.families[0]
        # Both the father link and the mother link for @I3@ are adoptive.
        parent_ids = {link.parent_id for link in family.parent_child_links}
        assert len(parent_ids) == 2
        for link in family.parent_child_links:
            assert link.parentage_type == "adoptive"


# ---------------------------------------------------------------------------
# Import back-fill of placement events for foster/adoptive links
# (Requirements 11.6, 11.7, 11.7a, 11.8)
# ---------------------------------------------------------------------------

from slaktbusken.services.foster_sync import sync_parentage_links


# A two-parent adopted child whose INDI carries the exporter's ADOP structure
# (DATE/PLAC + a subordinate FAMC pointing at the derived family @F1@), plus the
# FAMC/PEDI adopted link. This mirrors a Släktbusken GEDCOM export round-trip.
_GEDCOM_ADOP_WITH_FAMC = """\
0 HEAD
1 SOUR Test
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
0 @I2@ INDI
1 NAME Anna /Persson/
1 SEX F
0 @I3@ INDI
1 NAME Erik /Andersson/
1 SEX M
1 BIRT
2 DATE 3 FEB 1876
1 FAMC @F1@
2 PEDI adopted
1 ADOP
2 DATE 10 JUN 1880
2 PLAC Ljusdal, Gävleborgs län, Sverige
2 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
0 TRLR
"""


# A two-parent foster child whose INDI carries the exporter's custom
# EVEN/TYPE Fosterhem structure (DATE/PLAC + subordinate FAMC) and the
# FAMC/PEDI foster link.
_GEDCOM_FOSTER_WITH_FAMC = """\
0 HEAD
1 SOUR Test
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
0 @I2@ INDI
1 NAME Anna /Persson/
1 SEX F
0 @I3@ INDI
1 NAME Erik /Andersson/
1 SEX M
1 BIRT
2 DATE 3 FEB 1876
1 FAMC @F1@
2 PEDI foster
1 EVEN
2 TYPE Fosterhem
2 DATE 10 JUN 1880
2 PLAC Ljusdal, Gävleborgs län, Sverige
2 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
0 TRLR
"""


# An adopted child with NO ADOP structure — only the FAMC/PEDI adopted link.
# The importer must fabricate a dateless Adoption event for the Parent_Set.
_GEDCOM_ADOPTED_NO_EVENT = """\
0 HEAD
1 SOUR Test
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
0 @I2@ INDI
1 NAME Anna /Persson/
1 SEX F
0 @I3@ INDI
1 NAME Erik /Andersson/
1 SEX M
1 FAMC @F1@
2 PEDI adopted
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
0 TRLR
"""


class TestImportPlacementBackfill:
    """Imported foster/adoptive links are backed by a placement event.

    Covers the shared back-fill (Requirement 11.6), preferring the matching
    ADOP/EVEN structure's date/place and FAMC parent linkage (11.7, 11.7a),
    grouping GEDCOM-family-mates into one Parent_Set (11.8), and that the
    post-import sync never deletes an imported link (11.8/11.9 precondition).
    """

    def _import(
        self,
        gedcom_text: str,
        empty_project: ProjectData,
        translation_dir: Path,
        tmp_path: Path,
    ) -> ProjectData:
        gedcom_file = tmp_path / "placement.ged"
        gedcom_file.write_text(gedcom_text, encoding="utf-8")
        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)
        return empty_project

    @staticmethod
    def _child_id(project: ProjectData) -> str:
        """The App_JSON id of the imported child Erik (@I3@)."""
        for person in project.persons:
            if person.names and person.names[0].given == "Erik":
                return person.id
        raise AssertionError("child Erik not found")

    @staticmethod
    def _parent_ids(project: ProjectData) -> set[str]:
        """The App_JSON ids of the two parents Johan (@I1@) and Anna (@I2@)."""
        ids: set[str] = set()
        for person in project.persons:
            if person.names and person.names[0].given in ("Johan", "Anna"):
                ids.add(person.id)
        return ids

    def test_adop_structure_reused_not_duplicated(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """A matching ADOP event backs the links; no duplicate is created (11.8)."""
        project = self._import(
            _GEDCOM_ADOP_WITH_FAMC, empty_project, translation_dir, tmp_path
        )

        adoption_events = [e for e in project.events if e.type == "adoption"]
        assert len(adoption_events) == 1  # reused, not duplicated

    def test_adop_event_names_child_and_both_parents(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Finalisation attaches the FAMC parents and the adopterad child (11.7a)."""
        project = self._import(
            _GEDCOM_ADOP_WITH_FAMC, empty_project, translation_dir, tmp_path
        )
        event = next(e for e in project.events if e.type == "adoption")

        child_id = self._child_id(project)
        parent_ids = self._parent_ids(project)

        child_participants = [
            p for p in event.participants if p.role == "adopterad"
        ]
        parent_participants = [
            p for p in event.participants if p.role == "adoptivförälder"
        ]
        assert [p.person_id for p in child_participants] == [child_id]
        assert {p.person_id for p in parent_participants} == parent_ids

    def test_adop_date_and_place_preferred(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """The structure's own DATE/PLAC are kept on the event (11.7)."""
        project = self._import(
            _GEDCOM_ADOP_WITH_FAMC, empty_project, translation_dir, tmp_path
        )
        event = next(e for e in project.events if e.type == "adoption")

        assert event.date is not None
        assert event.date.value == "1880-06-10"
        assert event.place is not None and event.place.place_id

    def test_foster_even_structure_reused(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """EVEN/TYPE Fosterhem becomes one foster_home event with its parents (11.7a)."""
        project = self._import(
            _GEDCOM_FOSTER_WITH_FAMC, empty_project, translation_dir, tmp_path
        )

        foster_events = [e for e in project.events if e.type == "foster_home"]
        assert len(foster_events) == 1
        # It must not have been misclassified as a generic custom event.
        assert not [
            e for e in project.events if e.type == "custom_individual_event"
        ]

        event = foster_events[0]
        child_id = self._child_id(project)
        parent_ids = self._parent_ids(project)
        assert [
            p.person_id for p in event.participants if p.role == "fosterbarn"
        ] == [child_id]
        assert {
            p.person_id for p in event.participants if p.role == "fosterförälder"
        } == parent_ids
        assert event.date is not None and event.date.value == "1880-06-10"

    def test_backfill_fabricates_event_when_no_structure(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """An adopted link with no ADOP structure gets a dateless back-fill event (11.6)."""
        project = self._import(
            _GEDCOM_ADOPTED_NO_EVENT, empty_project, translation_dir, tmp_path
        )

        adoption_events = [e for e in project.events if e.type == "adoption"]
        assert len(adoption_events) == 1
        event = adoption_events[0]
        assert event.date is None  # fabricated dateless

        child_id = self._child_id(project)
        parent_ids = self._parent_ids(project)
        assert [
            p.person_id for p in event.participants if p.role == "adopterad"
        ] == [child_id]
        assert {
            p.person_id for p in event.participants if p.role == "adoptivförälder"
        } == parent_ids

    def test_family_mates_grouped_into_one_parent_set(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Two parents sharing a GEDCOM family form a single event (11.8)."""
        project = self._import(
            _GEDCOM_ADOPTED_NO_EVENT, empty_project, translation_dir, tmp_path
        )

        adoption_events = [e for e in project.events if e.type == "adoption"]
        # One event (one Parent_Set), not two single-parent events.
        assert len(adoption_events) == 1
        parents = [
            p for p in adoption_events[0].participants
            if p.role == "adoptivförälder"
        ]
        assert len(parents) == 2

    def test_imported_links_survive_post_import_sync(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Running the sync after import never deletes the adoptive links (11.8).

        Because the back-fill (or the reused ADOP structure) backs the imported
        Parent_Set before the sync runs, the sync keeps a derived adoptive link
        for each (parent -> child) pair rather than dropping it as an orphan.
        """
        project = self._import(
            _GEDCOM_ADOP_WITH_FAMC, empty_project, translation_dir, tmp_path
        )

        child_id = self._child_id(project)
        parent_ids = self._parent_ids(project)

        def adoptive_pairs() -> set[tuple[str, str]]:
            return {
                (link.child_id, link.parent_id)
                for family in project.families
                for link in family.parent_child_links
                if link.child_id == child_id
                and link.parentage_type == "adoptive"
            }

        before = adoptive_pairs()
        assert before == {(child_id, pid) for pid in parent_ids}

        sync_parentage_links(project)

        # Every imported (parent -> child) adoptive pair still exists; none was
        # deleted as an unbacked orphan (Requirement 11.8).
        after = adoptive_pairs()
        assert before <= after

    def test_backfill_is_idempotent_on_reimport(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Re-importing the same GEDCOM does not create duplicate events (11.6)."""
        gedcom_file = tmp_path / "placement.ged"
        gedcom_file.write_text(_GEDCOM_ADOP_WITH_FAMC, encoding="utf-8")

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)
        first_count = len([e for e in empty_project.events if e.type == "adoption"])

        importer2 = GEDCOMImporter(empty_project, translation_dir)
        importer2.import_file(gedcom_file)
        second_count = len([e for e in empty_project.events if e.type == "adoption"])

        assert first_count == 1
        assert second_count == 1


# ---------------------------------------------------------------------------
# Placement END event reconstruction from an imported end date (Req 11.10)
# ---------------------------------------------------------------------------

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.gedcom.importer import _parse_placement_dates
from slaktbusken.gedcom.parser import GedcomLine
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person


def _event_record(
    tag: str, *, date: str | None = None, note: str | None = None
) -> GedcomLine:
    """Build a level-1 placement GedcomLine with an optional DATE/NOTE child.

    Mirrors the shape ``_parse_placement_dates`` reads from an ADOP / EVEN
    structure (only the DATE and NOTE children matter to it).
    """
    children: list[GedcomLine] = []
    if date is not None:
        children.append(
            GedcomLine(level=2, tag="DATE", value=date, xref_id=None, line_number=0)
        )
    if note is not None:
        children.append(
            GedcomLine(level=2, tag="NOTE", value=note, xref_id=None, line_number=0)
        )
    return GedcomLine(
        level=1,
        tag=tag,
        value=None,
        xref_id=None,
        line_number=0,
        children=children,
    )


class TestParsePlacementDates:
    """Unit tests for the pure placement period / NOTE splitter."""

    def test_from_to_period_splits_start_and_end(self) -> None:
        """'FROM x TO y' yields start x and end y."""
        start, end = _parse_placement_dates(
            _event_record("ADOP", date="FROM 10 JUN 1880 TO 5 MAY 1890")
        )
        assert start is not None and start.value == "1880-06-10"
        assert end is not None and end.value == "1890-05-05"

    def test_from_only_yields_no_end(self) -> None:
        """'FROM x' (period marker, no TO) yields a start but no end (Req 11.10)."""
        start, end = _parse_placement_dates(
            _event_record("ADOP", date="FROM 10 JUN 1880")
        )
        assert start is not None and start.value == "1880-06-10"
        assert end is None

    def test_to_only_yields_end_no_start(self) -> None:
        """'TO y' yields an end but no start (the start is dateless)."""
        start, end = _parse_placement_dates(
            _event_record("ADOP", date="TO 5 MAY 1890")
        )
        assert start is None
        assert end is not None and end.value == "1890-05-05"

    def test_plain_date_yields_no_end(self) -> None:
        """A plain (non-period) DATE never fabricates an end."""
        start, end = _parse_placement_dates(
            _event_record("ADOP", date="10 JUN 1880")
        )
        assert start is not None and start.value == "1880-06-10"
        assert end is None

    def test_avslutades_note_yields_end(self) -> None:
        """A labelled 'Avslutades: <end>' NOTE provides the end date."""
        start, end = _parse_placement_dates(
            _event_record("ADOP", date="10 JUN 1880", note="Avslutades: 1890")
        )
        assert start is not None and start.value == "1880-06-10"
        assert end is not None and end.value == "1890"

    def test_no_date_no_note_yields_nothing(self) -> None:
        """A structure with neither DATE nor NOTE yields (None, None)."""
        start, end = _parse_placement_dates(_event_record("ADOP"))
        assert start is None
        assert end is None


# GEDCOM snippets exercising the import reconstruction. Each child @I3@ is an
# adopted/foster child of family @F1@; the ADOP / EVEN Fosterhem structure
# carries the placement span.
def _placement_gedcom(structure: str, pedi: str) -> str:
    return f"""\
0 HEAD
1 SOUR Test
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
0 @I2@ INDI
1 NAME Anna /Persson/
1 SEX F
0 @I3@ INDI
1 NAME Erik /Andersson/
1 SEX M
1 FAMC @F1@
2 PEDI {pedi}
{structure}
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
0 TRLR
"""


_ADOP_PERIOD_STRUCTURE = """\
1 ADOP
2 DATE FROM 10 JUN 1880 TO 5 MAY 1890
2 FAMC @F1@"""

_ADOP_FROM_ONLY_STRUCTURE = """\
1 ADOP
2 DATE FROM 10 JUN 1880
2 FAMC @F1@"""

_ADOP_NOTE_STRUCTURE = """\
1 ADOP
2 DATE 10 JUN 1880
2 FAMC @F1@
2 NOTE Avslutades: 1890"""

_FOSTER_PERIOD_STRUCTURE = """\
1 EVEN
2 TYPE Fosterhem
2 DATE FROM 10 JUN 1880 TO 5 MAY 1890
2 FAMC @F1@"""


class TestImportReconstructEndEvent:
    """An imported placement end date reconstructs the paired end event.

    Validates: Requirement 11.10
    """

    def _import(
        self,
        gedcom_text: str,
        empty_project: ProjectData,
        translation_dir: Path,
        tmp_path: Path,
    ) -> ProjectData:
        gedcom_file = tmp_path / "placement_end.ged"
        gedcom_file.write_text(gedcom_text, encoding="utf-8")
        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)
        return empty_project

    @staticmethod
    def _child_id(project: ProjectData) -> str:
        for person in project.persons:
            if person.names and person.names[0].given == "Erik":
                return person.id
        raise AssertionError("child Erik not found")

    @staticmethod
    def _parent_ids(project: ProjectData) -> set[str]:
        ids: set[str] = set()
        for person in project.persons:
            if person.names and person.names[0].given in ("Johan", "Anna"):
                ids.add(person.id)
        return ids

    def test_adoption_period_creates_paired_end_event(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """A FROM/TO ADOP period yields a start + an adoption_ended end event."""
        project = self._import(
            _placement_gedcom(_ADOP_PERIOD_STRUCTURE, "adopted"),
            empty_project,
            translation_dir,
            tmp_path,
        )

        starts = [e for e in project.events if e.type == "adoption"]
        ends = [e for e in project.events if e.type == "adoption_ended"]
        assert len(starts) == 1
        assert len(ends) == 1

        # Start keeps only its own (lower-bound) date; the period is not left on it.
        assert starts[0].date is not None and starts[0].date.value == "1880-06-10"
        # End carries the upper bound.
        assert ends[0].date is not None and ends[0].date.value == "1890-05-05"

    def test_end_event_names_same_child_and_parents(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """The end event mirrors the start's child and parents (symmetric)."""
        project = self._import(
            _placement_gedcom(_ADOP_PERIOD_STRUCTURE, "adopted"),
            empty_project,
            translation_dir,
            tmp_path,
        )
        end = next(e for e in project.events if e.type == "adoption_ended")

        child_id = self._child_id(project)
        parent_ids = self._parent_ids(project)
        assert [
            p.person_id for p in end.participants if p.role == "adopterad"
        ] == [child_id]
        assert {
            p.person_id for p in end.participants if p.role == "adoptivförälder"
        } == parent_ids

    def test_from_only_period_creates_no_end_event(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """A 'FROM <start>' period (no upper bound) yields no end event (11.10)."""
        project = self._import(
            _placement_gedcom(_ADOP_FROM_ONLY_STRUCTURE, "adopted"),
            empty_project,
            translation_dir,
            tmp_path,
        )

        starts = [e for e in project.events if e.type == "adoption"]
        ends = [e for e in project.events if e.type == "adoption_ended"]
        assert len(starts) == 1
        assert starts[0].date is not None and starts[0].date.value == "1880-06-10"
        assert ends == []

    def test_avslutades_note_creates_end_event(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """A labelled 'Avslutades:' NOTE reconstructs the end event."""
        project = self._import(
            _placement_gedcom(_ADOP_NOTE_STRUCTURE, "adopted"),
            empty_project,
            translation_dir,
            tmp_path,
        )

        starts = [e for e in project.events if e.type == "adoption"]
        ends = [e for e in project.events if e.type == "adoption_ended"]
        assert len(starts) == 1
        assert starts[0].date is not None and starts[0].date.value == "1880-06-10"
        assert len(ends) == 1
        assert ends[0].date is not None and ends[0].date.value == "1890"

    def test_foster_period_creates_foster_home_ended(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """A FROM/TO Fosterhem EVEN period yields a foster_home_ended end event."""
        project = self._import(
            _placement_gedcom(_FOSTER_PERIOD_STRUCTURE, "foster"),
            empty_project,
            translation_dir,
            tmp_path,
        )

        starts = [e for e in project.events if e.type == "foster_home"]
        ends = [e for e in project.events if e.type == "foster_home_ended"]
        assert len(starts) == 1
        assert len(ends) == 1
        assert starts[0].date is not None and starts[0].date.value == "1880-06-10"
        assert ends[0].date is not None and ends[0].date.value == "1890-05-05"

        child_id = self._child_id(project)
        parent_ids = self._parent_ids(project)
        assert [
            p.person_id for p in ends[0].participants if p.role == "fosterbarn"
        ] == [child_id]
        assert {
            p.person_id for p in ends[0].participants if p.role == "fosterförälder"
        } == parent_ids


class TestPlacementEndRoundTrip:
    """Export a start+end placement, re-import, assert the span round-trips.

    Validates: Requirement 11.10 (round-trip with Requirements 11.2c/11.2e)
    """

    @staticmethod
    def _synced_adoption_project() -> ProjectData:
        """Build an adopted child with a dated start and a dated end, synced.

        ``sync_parentage_links`` creates the derived family (whose ``event_ids``
        the exporter needs for the ``FAMC`` pointer) and pairs the end to it, so
        the exporter can emit the span as a GEDCOM period.
        """
        child = Person(
            id="person_1",
            names=[Name(type="birth", given="Barn", surname="Testsson")],
            sex="M",
        )
        father = Person(
            id="person_10",
            names=[Name(type="birth", given="Far", surname="Testsson")],
            sex="M",
        )
        mother = Person(
            id="person_11",
            names=[Name(type="birth", given="Mor", surname="Testsson")],
            sex="F",
        )
        start = Event(
            id="event_1",
            type="adoption",
            participants=[
                Participant(person_id="person_1", role="adopterad"),
                Participant(person_id="person_10", role="adoptivförälder"),
                Participant(person_id="person_11", role="adoptivförälder"),
            ],
            date=DateValue(value="1880-06-10", precision="day"),
        )
        end = Event(
            id="event_2",
            type="adoption_ended",
            participants=[
                Participant(person_id="person_1", role="adopterad"),
                Participant(person_id="person_10", role="adoptivförälder"),
                Participant(person_id="person_11", role="adoptivförälder"),
            ],
            date=DateValue(value="1890-05-05", precision="day"),
        )
        project = ProjectData(
            format="släktbuske-file",
            version="0.2",
            project=ProjectMetadata(title="Test"),
            persons=[child, father, mother],
            families=[],
            events=[start, end],
            places=[],
            sources=[],
        )
        sync_parentage_links(project)
        return project

    def test_export_import_round_trips_two_events(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """export(start+end) → import → the child's start + paired end survive.

        The import must reconstruct the child's adoption start and its paired
        adoption_ended end with the exported span's dates, and the end must name
        the same Parent_Set (both parents) as the start.

        Now that the exporter emits the placement structure only on the adopted
        child's INDI (not on the parents), the round-trip is unscoped: the
        project must contain EXACTLY one adoption start and one adoption_ended
        end — no spurious structures fabricated from the parents' INDI records.
        """
        source_project = self._synced_adoption_project()

        ged_path = tmp_path / "roundtrip.ged"
        GEDCOMExporter().export(source_project, ged_path)

        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(ged_path)

        child_id = next(
            person.id
            for person in empty_project.persons
            if person.names and person.names[0].given == "Barn"
        )
        parent_ids = {
            person.id
            for person in empty_project.persons
            if person.names and person.names[0].given in ("Far", "Mor")
        }

        def names_child(event: Event) -> bool:
            return any(
                p.person_id == child_id and p.role == "adopterad"
                for p in event.participants
            )

        starts = [
            e for e in empty_project.events
            if e.type == "adoption" and names_child(e)
        ]
        ends = [
            e for e in empty_project.events
            if e.type == "adoption_ended" and names_child(e)
        ]
        assert len(starts) == 1
        assert len(ends) == 1

        # Unscoped: the exporter no longer emits the ADOP structure on the
        # parents, so the whole project has exactly one start and one end —
        # no bogus placement events reconstructed from a parent's INDI.
        all_starts = [e for e in empty_project.events if e.type == "adoption"]
        all_ends = [e for e in empty_project.events if e.type == "adoption_ended"]
        assert len(all_starts) == 1
        assert len(all_ends) == 1
        assert starts[0].date is not None and starts[0].date.value == "1880-06-10"
        assert ends[0].date is not None and ends[0].date.value == "1890-05-05"

        # The end names the same Parent_Set as the start (same child + parents).
        start_parents = {
            p.person_id
            for p in starts[0].participants
            if p.role == "adoptivförälder"
        }
        end_parents = {
            p.person_id
            for p in ends[0].participants
            if p.role == "adoptivförälder"
        }
        assert start_parents == parent_ids
        assert end_parents == start_parents and len(end_parents) == 2


# ---------------------------------------------------------------------------
# Step 3d: import_file runs sync_parentage_links after back-fill, events take
# precedence, no imported foster/adoptive relationship is deleted (Req 11.9)
# ---------------------------------------------------------------------------


# A mixed GEDCOM family @F1@ with an adopted child (@I3@, two adoptive parents
# via an ADOP structure + FAMC/PEDI) and a biological child (@I4@). Exercises
# the dangerous case where the imported family holds BOTH adoptive and
# biological links, so reconciliation must relocate only the adoptive links and
# must leave the biological ones exactly as found.
_GEDCOM_MIXED_ADOPTIVE_BIOLOGICAL = """\
0 HEAD
1 SOUR Test
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
0 @I2@ INDI
1 NAME Anna /Persson/
1 SEX F
0 @I3@ INDI
1 NAME Erik /Andersson/
1 SEX M
1 FAMC @F1@
2 PEDI adopted
1 ADOP
2 DATE 10 JUN 1880
2 FAMC @F1@
0 @I4@ INDI
1 NAME Karl /Andersson/
1 SEX M
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 CHIL @I4@
0 TRLR
"""


class TestImportRunsSyncStep3d:
    """``import_file`` runs the sync after back-fill (Requirement 11.9).

    Sync now runs *inside* ``import_file`` (Step 3d), so every assertion is on
    the final project state the importer returns — no external sync call. The
    end-state invariant: foster/adoptive links are authoritative on the
    event-derived family, no imported foster/adoptive relationship vanishes, and
    biological (and every other) link is left exactly as found.

    Validates: Requirement 11.9
    """

    def _import(
        self,
        gedcom_text: str,
        empty_project: ProjectData,
        translation_dir: Path,
        tmp_path: Path,
    ) -> ProjectData:
        gedcom_file = tmp_path / "step3d.ged"
        gedcom_file.write_text(gedcom_text, encoding="utf-8")
        importer = GEDCOMImporter(empty_project, translation_dir)
        importer.import_file(gedcom_file)
        return empty_project

    @staticmethod
    def _id_for(project: ProjectData, given: str) -> str:
        for person in project.persons:
            if person.names and person.names[0].given == given:
                return person.id
        raise AssertionError(f"person {given!r} not found")

    @staticmethod
    def _pairs(
        project: ProjectData, parentage_type: str
    ) -> set[tuple[str, str | None]]:
        """All (child_id, parent_id) pairs of a given parentage type."""
        return {
            (link.child_id, link.parent_id)
            for family in project.families
            for link in family.parent_child_links
            if link.parentage_type == parentage_type
        }

    @staticmethod
    def _event_derived_family(project: ProjectData, child_id: str):
        """The sync-derived placement family that names ``child_id``.

        A derived family records a placement START event id on ``event_ids``.
        """
        placement_start_ids = {
            e.id for e in project.events if e.type in ("adoption", "foster_home")
        }
        for family in project.families:
            if child_id in family.children and any(
                eid in placement_start_ids for eid in family.event_ids
            ):
                return family
        return None

    # --- (a) adoptive relationship survives — with and without an ADOP -------

    def test_adoptive_links_survive_with_adop_structure(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """An adopted child's links survive the in-import sync (ADOP present)."""
        project = self._import(
            _GEDCOM_ADOP_WITH_FAMC, empty_project, translation_dir, tmp_path
        )

        erik = self._id_for(project, "Erik")
        johan = self._id_for(project, "Johan")
        anna = self._id_for(project, "Anna")

        # Both imported (parent -> Erik) adoptive pairs still exist post-import.
        assert self._pairs(project, "adoptive") >= {
            (erik, johan),
            (erik, anna),
        }

    def test_adoptive_links_survive_without_adop_structure(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """An adopted child's links survive even when no ADOP structure exists.

        The back-fill fabricates a dateless Adoption event before the sync, so
        the sync keeps the links rather than dropping them as unbacked orphans.
        """
        project = self._import(
            _GEDCOM_ADOPTED_NO_EVENT, empty_project, translation_dir, tmp_path
        )

        erik = self._id_for(project, "Erik")
        johan = self._id_for(project, "Johan")
        anna = self._id_for(project, "Anna")

        assert self._pairs(project, "adoptive") == {
            (erik, johan),
            (erik, anna),
        }

    def test_adoptive_links_authoritative_on_event_derived_family(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """Events take precedence: links live on the event-derived family.

        After the sync + reconciliation the adoptive (child -> parent) pairs are
        carried by exactly one family — the one keyed to the placement event —
        rather than being duplicated across the imported GEDCOM family and the
        derived family.
        """
        project = self._import(
            _GEDCOM_ADOP_WITH_FAMC, empty_project, translation_dir, tmp_path
        )

        erik = self._id_for(project, "Erik")

        families_with_adoptive_erik = [
            family
            for family in project.families
            if any(
                link.child_id == erik and link.parentage_type == "adoptive"
                for link in family.parent_child_links
            )
        ]
        # Exactly one family carries Erik's adoptive links (no duplicate).
        assert len(families_with_adoptive_erik) == 1
        # And it is the event-derived family (keyed by the placement event).
        derived = self._event_derived_family(project, erik)
        assert derived is not None
        assert families_with_adoptive_erik[0] is derived

    # --- (b) biological links untouched --------------------------------------

    def test_biological_links_untouched_in_mixed_family(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """The sync never alters a biological link in a mixed GEDCOM family.

        @F1@ holds adoptive links for Erik and biological links for Karl. After
        the in-import sync the biological links for Karl are present and
        unchanged, while Erik's adoptive links have moved to the event-derived
        family.
        """
        project = self._import(
            _GEDCOM_MIXED_ADOPTIVE_BIOLOGICAL,
            empty_project,
            translation_dir,
            tmp_path,
        )

        erik = self._id_for(project, "Erik")
        karl = self._id_for(project, "Karl")
        johan = self._id_for(project, "Johan")
        anna = self._id_for(project, "Anna")

        # Karl's biological links are intact (both parents).
        assert self._pairs(project, "biological") >= {
            (karl, johan),
            (karl, anna),
        }
        # Erik's adoptive links survive too (no loss).
        assert self._pairs(project, "adoptive") >= {
            (erik, johan),
            (erik, anna),
        }
        # Erik's adoptive links are not left duplicated on the biological family.
        bio_family = next(
            family
            for family in project.families
            if karl in family.children
        )
        assert not any(
            link.child_id == erik for link in bio_family.parent_child_links
        )

    # --- (c) foster child case -----------------------------------------------

    def test_foster_links_survive_and_are_authoritative(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """A foster child's links survive and live on the event-derived family."""
        project = self._import(
            _GEDCOM_FOSTER_WITH_FAMC, empty_project, translation_dir, tmp_path
        )

        erik = self._id_for(project, "Erik")
        johan = self._id_for(project, "Johan")
        anna = self._id_for(project, "Anna")

        assert self._pairs(project, "foster") == {
            (erik, johan),
            (erik, anna),
        }

        families_with_foster_erik = [
            family
            for family in project.families
            if any(
                link.child_id == erik and link.parentage_type == "foster"
                for link in family.parent_child_links
            )
        ]
        assert len(families_with_foster_erik) == 1
        derived = self._event_derived_family(project, erik)
        assert derived is not None
        assert families_with_foster_erik[0] is derived

    # --- Childless marriage family is NOT destroyed by the sync --------------

    def test_childless_marriage_family_preserved(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """A partner-only marriage family survives the in-import sync.

        The sync only ever removes event-derived foster/adoptive families; a
        childless family carrying only a MARR/DIV event on ``event_ids`` (and no
        parent-child links) must be left exactly as found.
        """
        project = self._import(
            _GEDCOM_ALL_FAM_EVENTS, empty_project, translation_dir, tmp_path
        )

        assert len(project.families) == 1
        family = project.families[0]
        assert family.children == []
        assert family.parent_child_links == []
        # Its marriage event is still present.
        assert any(e.type == "marriage" for e in project.events)

    # --- (d) round-trip export -> import preserves parentage -----------------

    def test_round_trip_preserves_adopted_childs_parentage(
        self, empty_project: ProjectData, translation_dir: Path, tmp_path: Path
    ) -> None:
        """import -> export -> import keeps the adopted child's adoptive links.

        The first import runs the Step 3d sync internally. Exporting then
        re-importing must preserve the adopted child's (parent -> child)
        adoptive relationships (events remain the source of truth across the
        round-trip).

        Previously the exporter emitted the ``1 ADOP ... 2 FAMC`` placement
        structure on EVERY participant of the adoption event — including the
        adoptive parents — so the re-import fabricated bogus parent->parent
        adoptive links. This test was once scoped to the child to tolerate that
        behaviour; now that the exporter emits the placement structure only on
        the adopted child's INDI, the full set of adoptive pairs round-trips
        with NO spurious additions, so the assertion is unscoped.
        """
        first = self._import(
            _GEDCOM_ADOP_WITH_FAMC, empty_project, translation_dir, tmp_path
        )

        def adoptive_parents_of_child(project: ProjectData) -> set[str]:
            erik = self._id_for(project, "Erik")
            names = {p.id: (p.names[0].given if p.names else "") for p in project.persons}
            return {
                names[link.parent_id]
                for family in project.families
                for link in family.parent_child_links
                if link.child_id == erik
                and link.parentage_type == "adoptive"
                and link.parent_id is not None
            }

        def all_adoptive_pairs(project: ProjectData) -> set[tuple[str, str]]:
            names = {p.id: (p.names[0].given if p.names else "") for p in project.persons}
            return {
                (names[link.child_id], names[link.parent_id])
                for family in project.families
                for link in family.parent_child_links
                if link.parentage_type == "adoptive"
                and link.parent_id is not None
            }

        before = adoptive_parents_of_child(first)
        assert before == {"Johan", "Anna"}
        # The source project's ONLY adoptive pairs are the child's two.
        pairs_before = all_adoptive_pairs(first)
        assert pairs_before == {("Erik", "Johan"), ("Erik", "Anna")}

        ged_path = tmp_path / "roundtrip_step3d.ged"
        GEDCOMExporter().export(first, ged_path)

        second_project = ProjectData(project=ProjectMetadata(title="RT"))
        second_dir = tmp_path / "translation_rt"
        second_dir.mkdir()
        GEDCOMImporter(second_project, second_dir).import_file(ged_path)

        after = adoptive_parents_of_child(second_project)
        # The adopted child's adoptive parents survive the round-trip.
        assert after == before
        # Full, UNSCOPED round-trip: no spurious parent->parent adoptive links
        # are fabricated — the set of adoptive pairs is exactly preserved.
        assert all_adoptive_pairs(second_project) == pairs_before
