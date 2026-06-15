"""Export orchestration service: resolve IDs → build GEDCOM → report omissions.

ExportService is a thin coordination layer that delegates the actual GEDCOM
generation to GEDCOMExporter and result formatting to ReportService. It ties
together the full export pipeline: create exporter, call export, format the
user-facing summary in Swedish, and return the result.

Validates: Requirements 4.1, 4.2, 4.3, 5.1, 5.6, 5.7
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from slaktbusken.gedcom.exporter import ExportResult, GEDCOMExporter
from slaktbusken.model.project import ProjectData

if TYPE_CHECKING:
    from slaktbusken.services.report_service import ReportService

logger = logging.getLogger(__name__)


class ExportService:
    """Orchestrates GEDCOM export: resolve IDs → build output → report omissions.

    This service delegates heavy lifting to GEDCOMExporter (ID resolution,
    place hierarchy, source citations, GEDCOM output) and uses ReportService
    to format the result summary in Swedish for the user.
    """

    def __init__(self, report_service: ReportService) -> None:
        """Initialise the export service.

        Args:
            report_service: Service for formatting export results as
                Swedish-language summaries.
        """
        self._report_service = report_service

    def run(
        self,
        project_data: ProjectData,
        output_path: Path,
        project_path: Path,
    ) -> ExportResult:
        """Run the full GEDCOM export pipeline.

        Orchestrates the export by creating a GEDCOMExporter, invoking the
        export, and using the report service to produce a user-facing summary.

        Args:
            project_data: The complete project data to export.
            output_path: File path where the GEDCOM file will be written.
            project_path: Path to the project folder (used for context in
                report generation).

        Returns:
            ExportResult containing counts of exported entities, any omitted
            elements, and warnings.
        """
        logger.info("Starting GEDCOM export to %s", output_path)

        # Create exporter and run the export pipeline
        exporter = GEDCOMExporter()
        result = exporter.export(project_data, output_path)

        # Format the summary via report service
        summary = self._report_service.format_export_result(result)
        logger.info("Export complete: %s", summary)

        return result
