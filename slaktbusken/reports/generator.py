"""Report generator service.

Orchestrates report generation by delegating to per-report modules.
Provides a single entry point for the UI layer to generate any
implemented report type.
"""

from __future__ import annotations

from pathlib import Path

from slaktbusken.model.project import ProjectData
from slaktbusken.reports.ansedel import generate_ansedel
from slaktbusken.reports.content import ReportContent
from slaktbusken.reports.geographic import generate_geographic_report
from slaktbusken.reports.kallrapport import generate_kallrapport
from slaktbusken.reports.media_consistency import generate_media_report


class ReportGeneratorService:
    """Service that dispatches report generation to per-report modules.

    Each method accepts the required data and returns a ReportContent
    instance ready for pagination and rendering.
    """

    def generate_ansedel(
        self,
        data: ProjectData,
        person_id: str,
        project_folder: Path | None,
    ) -> ReportContent:
        """Generate an Ansedel report for the specified person.

        Args:
            data: The full project data.
            person_id: ID of the person to report on.
            project_folder: Path to the project folder for resolving media.

        Returns:
            ReportContent with the person's details, events, and relationships.
        """
        return generate_ansedel(data, person_id, project_folder)

    def generate_geographic_consistency(
        self,
        data: ProjectData,
    ) -> ReportContent:
        """Generate a geographic consistency report for all places.

        Args:
            data: The full project data containing place records.

        Returns:
            ReportContent with hierarchy and coordinate check results.
        """
        return generate_geographic_report(data)

    def generate_media_consistency(
        self,
        data: ProjectData,
        project_folder: Path,
    ) -> ReportContent:
        """Generate a media consistency report for the project.

        Args:
            data: The full project data containing media records.
            project_folder: Path to the project folder for scanning media files.

        Returns:
            ReportContent with orphaned, unlinked, missing, and duplicate checks.
        """
        return generate_media_report(data, project_folder)

    def generate_kallrapport(
        self,
        data: ProjectData,
    ) -> ReportContent:
        """Generate a Källrapport (Source Report) for the project.

        Lists all sources organized by Leverantör → Källtyp → Title,
        with special grouping for Arkiv Digital (Volym → Sida/Bild).

        Args:
            data: The full project data containing sources.

        Returns:
            ReportContent with the hierarchical source listing.
        """
        return generate_kallrapport(data)
