"""Tests for ReportService Swedish-language formatting."""

from __future__ import annotations

from slaktbusken.gedcom.exporter import ExportResult
from slaktbusken.gedcom.importer import ImportResult
from slaktbusken.services.report_service import ReportService
from slaktbusken.services.validation_service import ValidationError


class TestFormatImportResult:
    """Tests for ReportService.format_import_result."""

    def setup_method(self) -> None:
        self.service = ReportService()

    def test_full_import_result(self) -> None:
        result = ImportResult(
            persons_added=42,
            persons_updated=3,
            families_added=15,
            families_updated=2,
            events_added=85,
            sources_added=12,
            places_added=8,
        )
        text = self.service.format_import_result(result)
        assert text.startswith("Import slutförd:")
        assert "42 personer tillagda" in text
        assert "3 personer uppdaterade" in text
        assert "15 familjer tillagda" in text
        assert "2 familjer uppdaterade" in text
        assert "85 händelser tillagda" in text
        assert "12 källor tillagda" in text
        assert "8 platser tillagda" in text
        assert text.endswith(".")

    def test_empty_import_result(self) -> None:
        result = ImportResult()
        text = self.service.format_import_result(result)
        assert text == "Import slutförd: inga ändringar."

    def test_partial_import_result(self) -> None:
        result = ImportResult(persons_added=5, events_added=10)
        text = self.service.format_import_result(result)
        assert "5 personer tillagda" in text
        assert "10 händelser tillagda" in text
        assert "uppdaterade" not in text
        assert "familjer" not in text

    def test_import_result_with_warnings(self) -> None:
        result = ImportResult(
            persons_added=1,
            warnings=["Rad 42: okänd tagg CUST", "Rad 99: felaktigt datum"],
        )
        text = self.service.format_import_result(result)
        assert "Varningar:" in text
        assert "Rad 42: okänd tagg CUST" in text
        assert "Rad 99: felaktigt datum" in text

    def test_import_result_no_warnings_section_when_empty(self) -> None:
        result = ImportResult(persons_added=1)
        text = self.service.format_import_result(result)
        assert "Varningar:" not in text


class TestFormatExportResult:
    """Tests for ReportService.format_export_result."""

    def setup_method(self) -> None:
        self.service = ReportService()

    def test_export_no_omissions(self) -> None:
        result = ExportResult(
            persons_exported=42,
            families_exported=15,
            sources_exported=12,
        )
        text = self.service.format_export_result(result)
        assert text == (
            "Export slutförd: 42 personer, 15 familjer och 12 källor exporterade."
        )

    def test_export_with_omissions(self) -> None:
        result = ExportResult(
            persons_exported=10,
            families_exported=5,
            sources_exported=3,
            omitted_elements={"DNA-profiler": 4, "Forskningsanteckningar": 2},
        )
        text = self.service.format_export_result(result)
        assert "Utelämnade element:" in text
        assert "DNA-profiler: 4" in text
        assert "Forskningsanteckningar: 2" in text

    def test_export_with_warnings(self) -> None:
        result = ExportResult(
            persons_exported=5,
            families_exported=2,
            sources_exported=1,
            warnings=["Källa utan referenstext utelämnad"],
        )
        text = self.service.format_export_result(result)
        assert "Varningar:" in text
        assert "Källa utan referenstext utelämnad" in text

    def test_export_zero_counts(self) -> None:
        result = ExportResult()
        text = self.service.format_export_result(result)
        assert "0 personer" in text
        assert "0 familjer" in text
        assert "0 källor" in text


class TestFormatValidationErrors:
    """Tests for ReportService.format_validation_errors."""

    def setup_method(self) -> None:
        self.service = ReportService()

    def test_no_errors(self) -> None:
        text = self.service.format_validation_errors([])
        assert text == "Ingen valideringsfel hittades."

    def test_single_error(self) -> None:
        errors = [
            ValidationError(
                entity_type="Person",
                entity_id="P001",
                message="Saknar namn",
            )
        ]
        text = self.service.format_validation_errors(errors)
        assert "Valideringsfel: 1 fel hittades." in text
        assert "Person (1 fel):" in text
        assert "[P001] Saknar namn" in text

    def test_multiple_errors_grouped_by_type(self) -> None:
        errors = [
            ValidationError("Person", "P001", "Saknar namn"),
            ValidationError("Person", "P002", "Ogiltigt kön"),
            ValidationError("Family", "F001", "Referens saknas"),
        ]
        text = self.service.format_validation_errors(errors)
        assert "Valideringsfel: 3 fel hittades." in text
        assert "Person (2 fel):" in text
        assert "Family (1 fel):" in text
        assert "[P001] Saknar namn" in text
        assert "[P002] Ogiltigt kön" in text
        assert "[F001] Referens saknas" in text

    def test_preserves_error_order_within_group(self) -> None:
        errors = [
            ValidationError("Event", "E001", "Första felet"),
            ValidationError("Event", "E002", "Andra felet"),
            ValidationError("Event", "E003", "Tredje felet"),
        ]
        text = self.service.format_validation_errors(errors)
        lines = text.split("\n")
        e001_idx = next(i for i, l in enumerate(lines) if "E001" in l)
        e002_idx = next(i for i, l in enumerate(lines) if "E002" in l)
        e003_idx = next(i for i, l in enumerate(lines) if "E003" in l)
        assert e001_idx < e002_idx < e003_idx
