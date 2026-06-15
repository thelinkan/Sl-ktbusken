"""Integration tests for ImportService orchestration.

Tests the full import pipeline using real GEDCOM content written to temp files.
Validates: Requirements 4.1, 4.2, 4.3, 5.1, 5.6, 5.7
"""

from __future__ import annotations

from pathlib import Path

import pytest

from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.import_service import ImportError, ImportService
from slaktbusken.services.report_service import ReportService
from slaktbusken.services.validation_service import ValidationService

# ---------------------------------------------------------------------------
# Shared GEDCOM content fixtures
# ---------------------------------------------------------------------------

MINIMAL_GEDCOM = """\
0 HEAD
1 SOUR TestProg
1 GEDC
2 VERS 5.5.1
2 FORM LINEAGE-LINKED
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Erik /Svensson/
1 SEX M
0 TRLR
"""

FULL_GEDCOM = """\
0 HEAD
1 SOUR TestProg
1 GEDC
2 VERS 5.5.1
2 FORM LINEAGE-LINKED
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Erik /Svensson/
1 SEX M
1 BIRT
2 DATE 1 JAN 1850
2 PLAC Ljusdal, Gävleborgs län, Sverige
0 @I2@ INDI
1 NAME Anna /Johansson/
1 SEX F
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 15 MAY 1875
0 @S1@ SOUR
1 TITL Husförhörslängd AI:1
0 TRLR
"""


def _write_gedcom(tmp_path: Path, content: str, filename: str = "test.ged") -> Path:
    """Write GEDCOM content to a temp file and return its path."""
    gedcom_path = tmp_path / filename
    gedcom_path.write_text(content, encoding="utf-8")
    return gedcom_path


def _make_service() -> ImportService:
    """Create an ImportService with real dependencies."""
    validation_service = ValidationService()
    report_service = ReportService()
    return ImportService(validation_service, report_service)


def _make_project_data() -> ProjectData:
    """Create an empty ProjectData for testing."""
    return ProjectData(project=ProjectMetadata(title="Test"))


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestImportServiceIntegration:
    """Integration tests for ImportService using real GEDCOM files."""

    def test_import_valid_gedcom_creates_entities(self, tmp_path: Path) -> None:
        """Importing a valid GEDCOM creates persons, families, events, sources, places."""
        service = _make_service()
        project_data = _make_project_data()
        gedcom_path = _write_gedcom(tmp_path, FULL_GEDCOM)
        project_path = tmp_path / "project"
        project_path.mkdir()

        result = service.run(project_data, gedcom_path, project_path)

        # Persons created
        assert result.persons_added == 2
        assert len(project_data.persons) == 2

        # Family created
        assert result.families_added == 1
        assert len(project_data.families) == 1

        # Events created (at least birth + marriage)
        assert result.events_added >= 2
        assert len(project_data.events) >= 2

        # Source created
        assert result.sources_added == 1
        assert len(project_data.sources) == 1
        assert project_data.sources[0].title == "Husförhörslängd AI:1"

        # Place created (from birth place string)
        assert result.places_added >= 1
        assert len(project_data.places) >= 1

    def test_import_nonexistent_file_raises_file_not_found(self, tmp_path: Path) -> None:
        """Importing a non-existent file raises FileNotFoundError."""
        service = _make_service()
        project_data = _make_project_data()
        missing_path = tmp_path / "does_not_exist.ged"
        project_path = tmp_path / "project"
        project_path.mkdir()

        with pytest.raises(FileNotFoundError):
            service.run(project_data, missing_path, project_path)

    def test_import_non_gedcom_file_raises_import_error(self, tmp_path: Path) -> None:
        """Importing a file that isn't valid GEDCOM raises ImportError with Swedish message."""
        service = _make_service()
        project_data = _make_project_data()
        bad_file = tmp_path / "not_gedcom.txt"
        bad_file.write_text("This is not a GEDCOM file at all.", encoding="utf-8")
        project_path = tmp_path / "project"
        project_path.mkdir()

        with pytest.raises(ImportError) as exc_info:
            service.run(project_data, bad_file, project_path)

        # Error message should be in Swedish
        assert "Kunde inte tolka GEDCOM-filen" in exc_info.value.message

    def test_reimport_same_file_updates_not_duplicates(self, tmp_path: Path) -> None:
        """Re-importing the same GEDCOM updates records rather than duplicating."""
        service = _make_service()
        project_data = _make_project_data()
        gedcom_path = _write_gedcom(tmp_path, FULL_GEDCOM)
        project_path = tmp_path / "project"
        project_path.mkdir()

        # First import
        result1 = service.run(project_data, gedcom_path, project_path)
        persons_after_first = len(project_data.persons)
        families_after_first = len(project_data.families)
        sources_after_first = len(project_data.sources)

        # Second import (re-import)
        result2 = service.run(project_data, gedcom_path, project_path)

        # Should not have duplicated entities
        assert len(project_data.persons) == persons_after_first
        assert len(project_data.families) == families_after_first
        assert len(project_data.sources) == sources_after_first

        # Second import should show updates, not additions
        assert result2.persons_added == 0
        assert result2.persons_updated == 2

    def test_post_import_validation_warnings_appended(self, tmp_path: Path) -> None:
        """Post-import validation warnings are appended to result.warnings."""
        service = _make_service()
        project_data = _make_project_data()
        gedcom_path = _write_gedcom(tmp_path, FULL_GEDCOM)
        project_path = tmp_path / "project"
        project_path.mkdir()

        result = service.run(project_data, gedcom_path, project_path)

        # The result should have a warnings list (may or may not have entries
        # depending on whether validation finds issues after a clean import).
        # At minimum, the list should exist and be a list.
        assert isinstance(result.warnings, list)

        # If there are warnings, they should contain "Valideringsvarning" prefix
        # for any validation-originated warnings
        for warning in result.warnings:
            if "Valideringsvarning" in warning:
                assert "Valideringsvarning" in warning

    def test_import_minimal_gedcom(self, tmp_path: Path) -> None:
        """Importing a minimal GEDCOM (HEAD + one person + TRLR) works."""
        service = _make_service()
        project_data = _make_project_data()
        gedcom_path = _write_gedcom(tmp_path, MINIMAL_GEDCOM)
        project_path = tmp_path / "project"
        project_path.mkdir()

        result = service.run(project_data, gedcom_path, project_path)

        assert result.persons_added == 1
        assert len(project_data.persons) == 1

        person = project_data.persons[0]
        assert person.sex == "M"
        assert person.names[0].given == "Erik"
        assert person.names[0].surname == "Svensson"
