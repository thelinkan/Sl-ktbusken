"""Import service — orchestrates the full GEDCOM import pipeline.

Provides the ImportService class which coordinates parsing, translation,
validation, merging, and reporting for a GEDCOM file import. Acts as a
thin orchestration layer delegating to the GEDCOMImporter for the actual
translation work.

Validates: Requirements 4.1, 4.2, 4.3, 5.1, 5.6, 5.7
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from slaktbusken.gedcom.importer import GEDCOMImporter, ImportResult
from slaktbusken.gedcom.parser import GedcomParseError
from slaktbusken.model.project import ProjectData
from slaktbusken.services.validation_service import ValidationError, ValidationService

if TYPE_CHECKING:
    from slaktbusken.services.report_service import ReportService

logger = logging.getLogger(__name__)


class ImportError(Exception):
    """Raised when a GEDCOM import fails.

    Attributes:
        message: Swedish-language description of the failure.
    """

    def __init__(self, message: str) -> None:
        """Initialize with a descriptive error message."""
        super().__init__(message)
        self.message = message


class ImportService:
    """Orchestrates GEDCOM import: parse → translate → validate → merge.

    The service delegates the heavy lifting to GEDCOMImporter which handles
    parsing, translation, and merging internally. ImportService adds
    validation, error handling, and report generation around that core.

    Args:
        validation_service: Service for cross-entity referential integrity checks.
        report_service: Service for formatting import results (forward reference).
    """

    def __init__(
        self,
        validation_service: ValidationService,
        report_service: "ReportService | None" = None,
    ) -> None:
        """Initialize with validation and report services.

        Args:
            validation_service: Used to validate project data after import.
            report_service: Used to format the import result summary. Optional
                because it may not be implemented yet.
        """
        self._validation_service = validation_service
        self._report_service = report_service

    def run(
        self,
        project_data: ProjectData,
        gedcom_path: Path,
        project_path: Path,
    ) -> ImportResult:
        """Execute the full GEDCOM import pipeline.

        Orchestrates the following steps:
        1. Validate the GEDCOM file exists and is readable.
        2. Create a GEDCOMImporter with the project data and translation dir.
        3. Call import_file to parse, translate, and merge GEDCOM data.
        4. Validate the resulting project data for referential integrity.
        5. Append any validation warnings to the result.

        Args:
            project_data: The existing project data to import into. Modified
                in place during import.
            gedcom_path: Path to the GEDCOM file to import.
            project_path: Path to the project folder (translation dir is
                derived as project_path / "translation").

        Returns:
            An ImportResult with counts of created/updated entities, plus
            any warnings generated during import or validation.

        Raises:
            ImportError: If the file cannot be read or parsed.
            FileNotFoundError: If the GEDCOM file does not exist.
        """
        # Validate input file exists
        if not gedcom_path.exists():
            raise FileNotFoundError(
                f"GEDCOM-filen hittades inte: {gedcom_path}"
            )

        if not gedcom_path.is_file():
            raise ImportError(
                f"Sökvägen är inte en fil: {gedcom_path}"
            )

        # Determine translation directory
        translation_dir = project_path / "translation"

        # Create importer and run the import
        try:
            importer = GEDCOMImporter(project_data, translation_dir)
            result = importer.import_file(gedcom_path)
        except GedcomParseError as e:
            raise ImportError(
                f"Kunde inte tolka GEDCOM-filen: {e}"
            ) from e
        except UnicodeDecodeError as e:
            raise ImportError(
                f"Kunde inte läsa filen (teckenkodningsfel): {e}"
            ) from e

        # Post-import validation
        validation_errors = self._validation_service.validate_project(project_data)
        if validation_errors:
            for error in validation_errors:
                result.warnings.append(
                    f"Valideringsvarning ({error.entity_type} "
                    f"{error.entity_id}): {error.message}"
                )

        logger.info(
            "Import slutförd: %d personer tillagda, %d uppdaterade, "
            "%d familjer, %d händelser, %d källor, %d platser, %d varningar",
            result.persons_added,
            result.persons_updated,
            result.families_added,
            result.events_added,
            result.sources_added,
            result.places_added,
            len(result.warnings),
        )

        return result

    def format_result(self, result: ImportResult) -> str:
        """Format an import result as a human-readable Swedish summary.

        If a ReportService is available, delegates to it. Otherwise produces
        a basic summary string.

        Args:
            result: The ImportResult to format.

        Returns:
            A Swedish-language summary of the import operation.
        """
        if self._report_service is not None:
            return self._report_service.format_import_result(result)

        # Fallback formatting when ReportService is not available
        lines = ["Import slutförd:"]
        if result.persons_added:
            lines.append(f"  {result.persons_added} personer tillagda")
        if result.persons_updated:
            lines.append(f"  {result.persons_updated} personer uppdaterade")
        if result.families_added:
            lines.append(f"  {result.families_added} familjer tillagda")
        if result.families_updated:
            lines.append(f"  {result.families_updated} familjer uppdaterade")
        if result.events_added:
            lines.append(f"  {result.events_added} händelser tillagda")
        if result.sources_added:
            lines.append(f"  {result.sources_added} källor tillagda")
        if result.places_added:
            lines.append(f"  {result.places_added} platser tillagda")
        if result.warnings:
            lines.append(f"  {len(result.warnings)} varningar")
        return "\n".join(lines)
