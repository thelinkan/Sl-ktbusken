"""Report service for formatting operation results in Swedish.

Provides human-readable Swedish-language summaries for import results,
export results, and validation errors. Used by the UI layer to present
operation outcomes to the user.

Validates: Requirements 4.1, 4.2, 4.3, 5.1, 5.6, 5.7
"""

from __future__ import annotations

from slaktbusken.gedcom.exporter import ExportResult
from slaktbusken.gedcom.importer import ImportResult
from slaktbusken.services.validation_service import ValidationError


class ReportService:
    """Formats operation results into Swedish-language summary messages.

    Provides methods to produce user-facing text summaries for GEDCOM import,
    GEDCOM export, and validation operations.
    """

    def format_import_result(self, result: ImportResult) -> str:
        """Format an import result as a Swedish-language summary.

        Produces a multi-line summary listing counts of added/updated entities,
        followed by any warnings encountered during the import.

        Args:
            result: The import operation result to format.

        Returns:
            A Swedish-language summary string.
        """
        parts: list[str] = []

        if result.persons_added:
            parts.append(f"{result.persons_added} personer tillagda")
        if result.persons_updated:
            parts.append(f"{result.persons_updated} personer uppdaterade")
        if result.families_added:
            parts.append(f"{result.families_added} familjer tillagda")
        if result.families_updated:
            parts.append(f"{result.families_updated} familjer uppdaterade")
        if result.events_added:
            parts.append(f"{result.events_added} händelser tillagda")
        if result.sources_added:
            parts.append(f"{result.sources_added} källor tillagda")
        if result.places_added:
            parts.append(f"{result.places_added} platser tillagda")

        if parts:
            summary = "Import slutförd: " + ", ".join(parts) + "."
        else:
            summary = "Import slutförd: inga ändringar."

        if result.warnings:
            summary += "\n\nVarningar:\n" + "\n".join(
                f"  - {w}" for w in result.warnings
            )

        return summary

    def format_export_result(self, result: ExportResult) -> str:
        """Format an export result as a Swedish-language summary.

        Produces a confirmation line with entity counts, optionally followed
        by a section listing omitted element types and their counts.

        Args:
            result: The export operation result to format.

        Returns:
            A Swedish-language summary string.
        """
        summary = (
            f"Export slutförd: {result.persons_exported} personer, "
            f"{result.families_exported} familjer och "
            f"{result.sources_exported} källor exporterade."
        )

        if result.omitted_elements:
            lines = [
                f"  - {element_type}: {count}"
                for element_type, count in result.omitted_elements.items()
            ]
            summary += (
                "\n\nUtelämnade element:\n" + "\n".join(lines)
            )

        if result.warnings:
            summary += "\n\nVarningar:\n" + "\n".join(
                f"  - {w}" for w in result.warnings
            )

        return summary

    def format_validation_errors(self, errors: list[ValidationError]) -> str:
        """Format validation errors as a Swedish-language report grouped by entity type.

        Groups errors by their entity_type and presents each group with its
        entity IDs and error messages.

        Args:
            errors: List of validation errors to format.

        Returns:
            A Swedish-language error report, or a success message if the list
            is empty.
        """
        if not errors:
            return "Ingen valideringsfel hittades."

        grouped: dict[str, list[ValidationError]] = {}
        for error in errors:
            grouped.setdefault(error.entity_type, []).append(error)

        sections: list[str] = []
        total = len(errors)
        sections.append(f"Valideringsfel: {total} fel hittades.\n")

        for entity_type, type_errors in grouped.items():
            sections.append(f"{entity_type} ({len(type_errors)} fel):")
            for err in type_errors:
                sections.append(f"  - [{err.entity_id}] {err.message}")

        return "\n".join(sections)
