"""Tests for ExportService orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from slaktbusken.gedcom.exporter import ExportResult
from slaktbusken.model.dna import DnaProfile
from slaktbusken.model.media import MediaItem
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.export_service import ExportService
from slaktbusken.services.import_service import ImportService
from slaktbusken.services.report_service import ReportService
from slaktbusken.services.validation_service import ValidationService


class TestExportServiceRun:
    """Tests for ExportService.run orchestration."""

    def setup_method(self) -> None:
        self.report_service = ReportService()
        self.service = ExportService(self.report_service)

    def test_run_exports_to_gedcom_file(self, tmp_path: Path) -> None:
        """run() produces a GEDCOM file at output_path."""
        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
        )
        output_path = tmp_path / "export.ged"
        project_path = tmp_path / "project"
        project_path.mkdir()

        result = self.service.run(project_data, output_path, project_path)

        assert output_path.exists()
        content = output_path.read_text(encoding="utf-8")
        assert "0 HEAD" in content
        assert "0 TRLR" in content

    def test_run_returns_export_result(self, tmp_path: Path) -> None:
        """run() returns an ExportResult with correct counts."""
        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
        )
        output_path = tmp_path / "export.ged"
        project_path = tmp_path / "project"
        project_path.mkdir()

        result = self.service.run(project_data, output_path, project_path)

        assert isinstance(result, ExportResult)
        assert result.persons_exported == 0
        assert result.families_exported == 0
        assert result.sources_exported == 0

    def test_run_returns_counts_for_populated_data(self, tmp_path: Path) -> None:
        """run() returns correct counts when data has entities."""
        from slaktbusken.model.person import Name, Person

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=[
                Person(
                    id="person_1",
                    sex="M",
                    names=[Name(type="birth", given="Erik", surname="Svensson")],
                ),
                Person(
                    id="person_2",
                    sex="F",
                    names=[Name(type="birth", given="Anna", surname="Johansson")],
                ),
            ],
        )
        output_path = tmp_path / "export.ged"
        project_path = tmp_path / "project"
        project_path.mkdir()

        result = self.service.run(project_data, output_path, project_path)

        assert result.persons_exported == 2
        assert result.families_exported == 0

    def test_run_delegates_to_gedcom_exporter(self, tmp_path: Path) -> None:
        """run() creates a GEDCOMExporter and calls its export method."""
        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
        )
        output_path = tmp_path / "export.ged"
        project_path = tmp_path / "project"
        project_path.mkdir()

        mock_result = ExportResult(
            persons_exported=10,
            families_exported=5,
            sources_exported=3,
            omitted_elements={"DNA-data": 2},
            warnings=[],
        )

        with patch(
            "slaktbusken.services.export_service.GEDCOMExporter"
        ) as mock_exporter_cls:
            mock_exporter_cls.return_value.export.return_value = mock_result
            result = self.service.run(project_data, output_path, project_path)

        mock_exporter_cls.return_value.export.assert_called_once_with(
            project_data, output_path
        )
        assert result.persons_exported == 10
        assert result.families_exported == 5
        assert result.sources_exported == 3
        assert result.omitted_elements == {"DNA-data": 2}

    def test_run_calls_report_service_format(self, tmp_path: Path) -> None:
        """run() uses report_service.format_export_result on the result."""
        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
        )
        output_path = tmp_path / "export.ged"
        project_path = tmp_path / "project"
        project_path.mkdir()

        mock_result = ExportResult(
            persons_exported=1,
            families_exported=0,
            sources_exported=0,
        )

        with patch(
            "slaktbusken.services.export_service.GEDCOMExporter"
        ) as mock_exporter_cls:
            mock_exporter_cls.return_value.export.return_value = mock_result
            with patch.object(
                self.report_service, "format_export_result", return_value="Export OK"
            ) as mock_format:
                result = self.service.run(project_data, output_path, project_path)

        mock_format.assert_called_once_with(mock_result)


# ---------------------------------------------------------------------------
# Integration tests — full import→export pipeline
# ---------------------------------------------------------------------------

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


class TestExportServiceIntegration:
    """Integration tests: import GEDCOM then export, verifying round-trip."""

    def test_import_then_export_produces_valid_gedcom(self, tmp_path: Path) -> None:
        """Import a GEDCOM file then export — the export produces valid GEDCOM."""
        # Setup
        report_service = ReportService()
        validation_service = ValidationService()
        import_service = ImportService(validation_service, report_service)
        export_service = ExportService(report_service)

        project_data = ProjectData(project=ProjectMetadata(title="RoundTrip"))
        gedcom_path = tmp_path / "input.ged"
        gedcom_path.write_text(FULL_GEDCOM, encoding="utf-8")
        project_path = tmp_path / "project"
        project_path.mkdir()

        # Import
        import_result = import_service.run(project_data, gedcom_path, project_path)
        assert import_result.persons_added == 2

        # Export
        output_path = tmp_path / "export.ged"
        export_result = export_service.run(project_data, output_path, project_path)

        # Verify export file
        assert output_path.exists()
        content = output_path.read_text(encoding="utf-8")

        # Valid GEDCOM structure
        assert content.startswith("0 HEAD")
        assert "0 TRLR" in content

        # Person data preserved
        assert "Erik" in content
        assert "Svensson" in content
        assert "Anna" in content
        assert "Johansson" in content

        # Counts match
        assert export_result.persons_exported == 2
        assert export_result.families_exported == 1
        assert export_result.sources_exported >= 1

    def test_data_with_dna_media_produces_omitted_elements(self, tmp_path: Path) -> None:
        """Data with DNA/media items produces omitted_elements in the result."""
        report_service = ReportService()
        export_service = ExportService(report_service)

        from slaktbusken.model.person import Name, Person

        project_data = ProjectData(
            project=ProjectMetadata(title="DNA Test"),
            persons=[
                Person(
                    id="person_1",
                    sex="M",
                    names=[Name(type="birth", given="Test", surname="Person")],
                ),
            ],
            dna_profiles=[
                DnaProfile(
                    id="dna_profile_1",
                    person_id="person_1",
                    company_id="dna_company_1",
                    test_type="autosomal",
                ),
            ],
            media=[
                MediaItem(
                    id="media_1",
                    type="photo",
                    file="photo.jpg",
                    title="Test Photo",
                ),
            ],
        )

        output_path = tmp_path / "export.ged"
        project_path = tmp_path / "project"
        project_path.mkdir()

        result = export_service.run(project_data, output_path, project_path)

        # DNA and media should be reported as omitted
        assert result.omitted_elements is not None
        assert "DNA-profiler" in result.omitted_elements
        assert result.omitted_elements["DNA-profiler"] == 1
        assert "Medieobjekt" in result.omitted_elements
        assert result.omitted_elements["Medieobjekt"] == 1
