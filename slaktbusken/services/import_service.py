"""Import service — orchestrates the full GEDCOM import pipeline.

Provides the ImportService class which coordinates parsing, translation,
validation, merging, and reporting for a GEDCOM file import. Acts as a
thin orchestration layer delegating to the GEDCOMImporter for the actual
translation work.

Validates: Requirements 4.1, 4.2, 4.3, 5.1, 5.6, 5.7
"""

from __future__ import annotations

import copy
import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from slaktbusken.gedcom.errors import MSG_ABORT_PREFIX, ImportAborted
from slaktbusken.gedcom.importer import GEDCOMImporter, ImportResult
from slaktbusken.gedcom.parser import GedcomParseError
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.serialization import serialize
from slaktbusken.persistence.translation_io import (
    TranslationData,
    dumps_persons,
    dumps_places,
    dumps_sources,
    read_all as read_translations,
)
from slaktbusken.services.edit_session import (
    MSG_IMPORT_RUNNING,
    MSG_IMPORT_SAVE_UNFINISHED,
)
from slaktbusken.services.project_service import PendingTranslation, ProjectService
from slaktbusken.services.validation_service import ValidationError, ValidationService

if TYPE_CHECKING:
    from slaktbusken.services.report_service import ReportService

logger = logging.getLogger(__name__)

MSG_TRANSLATION_CHANGED = (
    "Översättningsfilerna ändrades under importen. Ingenting har ändrats."
)
MSG_BLOCKED_BY_EDITOR = 'Spara eller stäng "{title}" innan du importerar.'

#: Translation files in the order of the Translation_Base.
_TRANSLATION_FILES = ("persons.json", "places.json", "sources.json")


def _translation_base(translation_dir: Path) -> dict[str, str]:
    """SHA-256 of each translation file's bytes, or ``"absent"``."""
    base: dict[str, str] = {}
    for name in _TRANSLATION_FILES:
        path = translation_dir / name
        try:
            base[f"translation/{name}"] = hashlib.sha256(path.read_bytes()).hexdigest()
        except FileNotFoundError:
            base[f"translation/{name}"] = "absent"
    return base


def _dump_translation(data: TranslationData) -> tuple[bytes, bytes, bytes]:
    """Serialise all three translation files (pure, for comparison)."""
    return (
        dumps_persons(data.persons, data.families, data.person_aliases),
        dumps_places(data.places),
        dumps_sources(data.sources),
    )


_MAX_NAMED_FINDINGS = 5

_MSG_RESIDENCE_WITHOUT_PLACE = "Boendet måste ange både person och plats."
_MSG_PLACE_WITHOUT_PARENT_SUFFIX = "måste ha en överordnad plats."


# Findings about the *shape* of a place hierarchy (type and parent rules). The
# importer builds places from free text such as "Ljusdal, Hälsingland" and has
# to guess a type for each level, so real-world files regularly produce a
# country without a continent, a parish without a region-level parent and so
# on. Release 0.2.0 imported such files and showed these findings as warnings;
# aborting on them made ordinary GEDCOM files impossible to import. A parent
# that does not exist at all is a broken reference, not a shape problem, and
# still aborts.
_PLACE_SHAPE_MARKERS = (
    "måste ha en kontinent som överordnad plats",
    "måste vara av typen 'kontinent'",
    "måste ha en överordnad plats",
    "som överordnad plats.",  # "(ordning 1) måste ha ett land som överordnad plats"
    "måste ha en överordnad plats av typen",
)


def _is_place_shape_finding(error: ValidationError, work: ProjectData) -> bool:
    """True for a hierarchy-shape finding about a place of the working copy."""
    if error.entity_type != "Place":
        return False
    if "hittades inte" in error.message or "refererar inte" in error.message:
        return False
    if not any(marker in error.message for marker in _PLACE_SHAPE_MARKERS):
        return False
    return any(p.id == error.entity_id for p in work.places)


def _is_tolerated_import_finding(error: ValidationError, work: ProjectData) -> bool:
    """True for the findings the importer produces on purpose.

    Temporary exemption until the importer stops producing them:

    * a residence from a RESI without a usable PLAC (person set, place empty);
    * a place from a place string without a usable hierarchy (no parent);
    * a place whose guessed type does not fit its parent (hierarchy shape).

    These stay warnings; any other finding introduced by the import aborts.
    """
    if _is_place_shape_finding(error, work):
        return True
    if error.message == _MSG_RESIDENCE_WITHOUT_PLACE:
        residence = next(
            (r for r in work.residences if r.id == error.entity_id), None
        )
        return (
            residence is not None
            and bool(residence.person_id.strip())
            and not residence.place_id.strip()
        )
    if error.message.endswith(_MSG_PLACE_WITHOUT_PARENT_SUFFIX):
        place = next((p for p in work.places if p.id == error.entity_id), None)
        return place is not None and not place.parent_place_id
    return False


def _finding_key(error: ValidationError) -> tuple[str, str, str]:
    """Stable identity of a validation finding across two validation runs."""
    return (error.entity_type, error.entity_id, error.message)


def _validation_aborted(introduced: list[ValidationError]) -> ImportAborted:
    """Build the abort for findings that the import introduced."""
    named = "; ".join(
        f"{e.entity_type} {e.entity_id}: {e.message}"
        for e in introduced[:_MAX_NAMED_FINDINGS]
    )
    more = (
        f" (och {len(introduced) - _MAX_NAMED_FINDINGS} till)"
        if len(introduced) > _MAX_NAMED_FINDINGS
        else ""
    )
    details = "\n".join(
        f"{e.entity_type} {e.entity_id}: {e.message}" for e in introduced
    )
    return ImportAborted(
        f"{MSG_ABORT_PREFIX} Importen skulle ha gett ogiltiga data: "
        f"{len(introduced)} fel, t.ex. {named}{more}",
        phase="validation",
        traceback_text=f"Nya valideringsfel ({len(introduced)}):\n{details}",
    )


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
        project_service: ProjectService,
    ) -> ImportResult:
        """Execute the full GEDCOM import pipeline atomically.

        The importer runs on a deep copy of *project_data* in staging mode:
        it writes no translation file. The copy is adopted into
        *project_data* (one ``mark_changed``) only when it differs from the
        original or the staged translation differs from the effective one; the
        staged translation is kept as the service's Pending_Translation.

        Args:
            project_data: The project data of *project_service*. Changed only
                when the import succeeds and changes something.
            gedcom_path: Path to the GEDCOM file to import.
            project_path: Path to the project folder (translation dir is
                derived as project_path / "translation").
            project_service: Service that owns *project_data* and adopts the
                working copy.

        Returns:
            An ImportResult with counts of created/updated entities, plus
            any warnings generated during import or validation.

        Raises:
            ImportError: If the import is refused, the file cannot be read or
                parsed, or a translation file changed during the import.
            FileNotFoundError: If the GEDCOM file does not exist.
        """
        if project_service.data is not project_data:
            raise ValueError("project_data är inte projektet som tjänsten håller.")

        self._refuse_if_blocked(project_service)

        # Validate input file exists
        if not gedcom_path.exists():
            raise FileNotFoundError(
                f"GEDCOM-filen hittades inte: {gedcom_path}"
            )

        if not gedcom_path.is_file():
            raise ImportError(
                f"Sökvägen är inte en fil: {gedcom_path}"
            )

        translation_dir = project_path / "translation"
        project_service.set_import_in_progress(True)
        try:
            return self._run_staged(
                project_data, gedcom_path, translation_dir, project_service
            )
        finally:
            project_service.set_import_in_progress(False)

    @staticmethod
    def _refuse_if_blocked(project_service: ProjectService) -> None:
        """Raise ImportError when an import must not start (Requirement 20.13)."""
        session = project_service.active_edit_session
        if session is not None:
            raise ImportError(
                MSG_BLOCKED_BY_EDITOR.format(title=session.owner_title)
            )
        titles = project_service.unsaved_editor_titles()
        if titles:
            raise ImportError(
                "\n".join(MSG_BLOCKED_BY_EDITOR.format(title=t) for t in titles)
            )
        if project_service.import_save_unfinished:
            raise ImportError(MSG_IMPORT_SAVE_UNFINISHED)
        if project_service.import_in_progress:
            raise ImportError(MSG_IMPORT_RUNNING)

    def _run_staged(
        self,
        project_data: ProjectData,
        gedcom_path: Path,
        translation_dir: Path,
        project_service: ProjectService,
    ) -> ImportResult:
        """Run the importer on a working copy and adopt it when it changed."""
        pending = project_service.pending_translation
        overlay = pending.data if pending is not None else None
        base_before = (
            _translation_base(translation_dir) if pending is None else None
        )

        work = copy.deepcopy(project_data)

        # Create importer and run the import on the working copy
        try:
            importer = GEDCOMImporter(
                work, translation_dir, overlay=overlay, stage_only=True
            )
            result = importer.import_file(gedcom_path)
        except GedcomParseError as e:
            raise ImportError(
                f"Kunde inte tolka GEDCOM-filen: {e}"
            ) from e
        except UnicodeDecodeError as e:
            raise ImportError(
                f"Kunde inte läsa filen (teckenkodningsfel): {e}"
            ) from e
        staged = result.translation if result.translation is not None else TranslationData()

        # Ensure all countries have their region_levels presets applied
        # (needed for validation to recognize dynamic region-level types)
        from slaktbusken.data.country_presets import get_preset
        _COUNTRY_NAME_TO_PRESET = {
            "sverige": "Sverige", "norway": "Norge", "norge": "Norge",
            "finland": "Finland", "danmark": "Danmark", "denmark": "Danmark",
            "tyskland": "Tyskland", "germany": "Tyskland", "england": "England",
            "usa": "USA", "united states": "USA", "kanada": "USA", "canada": "USA",
        }
        for place in work.places:
            if place.type == "country" and not place.region_levels:
                preset_name = _COUNTRY_NAME_TO_PRESET.get(place.name.lower())
                if preset_name:
                    place.region_levels = get_preset(preset_name)

        # Post-import validation
        # Findings that the import introduced abort it; findings that were
        # already in the original data stay warnings.
        try:
            before_keys = {
                _finding_key(e)
                for e in self._validation_service.validate_project(project_data)
            }
            validation_errors = self._validation_service.validate_project(work)
        except Exception as e:  # noqa: BLE001 - any failure of the validator aborts
            raise ImportAborted.from_exception(e, phase="validation") from e
        introduced = [
            e
            for e in validation_errors
            if _finding_key(e) not in before_keys
            and not _is_tolerated_import_finding(e, work)
        ]
        if introduced:
            raise _validation_aborted(introduced)
        for error in validation_errors:
            result.warnings.append(
                f"Valideringsvarning ({error.entity_type} "
                f"{error.entity_id}): {error.message}"
            )

        # A translation file that changed during the import aborts it; the
        # working copy is discarded and nothing has been touched.
        if pending is None and _translation_base(translation_dir) != base_before:
            raise ImportError(MSG_TRANSLATION_CHANGED)

        effective = (
            pending.data if pending is not None else read_translations(translation_dir)
        )
        project_changed = serialize(work) != serialize(project_data)
        translation_changed = _dump_translation(staged) != _dump_translation(effective)

        if project_changed or translation_changed:
            new_pending = (
                PendingTranslation(staged, dict(base_before or {}))
                if translation_changed
                else None
            )
            project_service.adopt_working_copy(work, new_pending, "GEDCOM-import")

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
        if getattr(result, "residences_added", 0) or getattr(
            result, "residences_claimed", 0
        ):
            lines.append(
                f"  Boenden: {result.residences_added} nya, "
                f"{result.residences_claimed} kopplade till befintliga"
            )
        if result.sources_added:
            lines.append(f"  {result.sources_added} källor tillagda")
        if result.places_added:
            lines.append(f"  {result.places_added} platser tillagda")
        if result.warnings:
            lines.append(f"  {len(result.warnings)} varningar")
        return "\n".join(lines)
