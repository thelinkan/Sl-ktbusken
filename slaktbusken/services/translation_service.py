"""Translation file lifecycle service: load, save, update mappings.

TranslationService orchestrates the *workflow* of translation—loading
translation files from disk, coordinating updates, and persisting changes.
The actual GEDCOM↔App_JSON mapping *logic* (how a GEDCOM place string maps
to a hierarchical Place, how a source ID maps to a structured Source, etc.)
lives in the ``gedcom/translation/`` package.

This service owns the file lifecycle (loading/saving) while the translation
package handles the actual mapping logic.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

from slaktbusken.persistence.translation_io import (
    FamilyMapping,
    PersonMapping,
    PlaceMapping,
    SourceMapping,
    TranslationData,
    TranslationIOError,
    read_all,
    write_all,
)

logger = logging.getLogger(__name__)

# Union type for any translation mapping entry that can be added via
# update_mappings. Corresponds to "TranslationEntry" in the design document.
TranslationEntry = Union[SourceMapping, PlaceMapping, PersonMapping, FamilyMapping]


class TranslationServiceError(Exception):
    """Raised when a translation service operation fails.

    Wraps lower-level I/O errors with additional context about the
    operation that was attempted.

    Attributes:
        message: Swedish-language user-facing error message.
        cause: The original exception that triggered this error.
    """

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.__cause__ = cause


class TranslationService:
    """Translation file lifecycle: load/save/update.

    This service orchestrates the *workflow* of translation—loading
    translation files from disk, coordinating updates, and persisting
    changes. The actual GEDCOM↔App_JSON mapping *logic* lives in the
    gedcom/translation/ package.
    """

    def load_translations(self, project_path: Path) -> TranslationData:
        """Load all translation files for the project.

        Reads sources.json, places.json, and persons.json from the
        project's ``translation/`` subdirectory.

        Args:
            project_path: Path to the project .json.gz file or the
                project folder. If a file is given, the translation
                directory is resolved as ``file.parent / "translation"``.

        Returns:
            A TranslationData container with all persisted mappings.
            Missing files result in empty lists for those mapping types.

        Raises:
            TranslationServiceError: If translation files cannot be read.
        """
        translation_dir = self._resolve_translation_dir(project_path)
        try:
            data = read_all(translation_dir)
            logger.info(
                "Översättningsfiler laddade från: %s "
                "(källor=%d, platser=%d, personer=%d, familjer=%d)",
                translation_dir,
                len(data.sources),
                len(data.places),
                len(data.persons),
                len(data.families),
            )
            return data
        except TranslationIOError as exc:
            msg = f"Kunde inte läsa översättningsfiler: {exc}"
            logger.error(msg)
            raise TranslationServiceError(msg, cause=exc) from exc

    def save_translations(
        self, data: TranslationData, project_path: Path
    ) -> None:
        """Persist updated translation data back to disk.

        Writes sources.json, places.json, and persons.json to the
        project's ``translation/`` subdirectory.

        Args:
            data: The TranslationData container with all mappings to persist.
            project_path: Path to the project .json.gz file or the
                project folder. If a file is given, the translation
                directory is resolved as ``file.parent / "translation"``.

        Raises:
            TranslationServiceError: If translation files cannot be saved.
                The error message is in Swedish for user-facing display
                (requirement 6.6). The unsaved data remains in memory.
        """
        translation_dir = self._resolve_translation_dir(project_path)
        try:
            write_all(data, translation_dir)
            logger.info("Översättningsfiler sparade till: %s", translation_dir)
        except TranslationIOError as exc:
            msg = (
                f"Kunde inte spara översättningsfiler: {exc}. "
                "Ändringarna finns kvar i minnet men kunde inte skrivas till disk."
            )
            logger.error(msg)
            raise TranslationServiceError(msg, cause=exc) from exc

    def update_mappings(
        self, data: TranslationData, new_mappings: list[TranslationEntry]
    ) -> TranslationData:
        """Register new GEDCOM↔App_JSON mappings discovered during import.

        Adds the provided mapping entries to the appropriate lists in the
        TranslationData container. Duplicate entries (same gedcom_id or
        gedcom_place) are updated in place rather than creating duplicates.

        Args:
            data: The current TranslationData to update.
            new_mappings: List of mapping entries to add or update. Each
                entry must be a SourceMapping, PlaceMapping, PersonMapping,
                or FamilyMapping instance.

        Returns:
            The updated TranslationData instance (same object, mutated).
        """
        for mapping in new_mappings:
            if isinstance(mapping, SourceMapping):
                self._upsert_source_mapping(data, mapping)
            elif isinstance(mapping, PlaceMapping):
                self._upsert_place_mapping(data, mapping)
            elif isinstance(mapping, PersonMapping):
                self._upsert_person_mapping(data, mapping)
            elif isinstance(mapping, FamilyMapping):
                self._upsert_family_mapping(data, mapping)
            else:
                logger.warning(
                    "Okänd mappningstyp ignorerad: %s", type(mapping).__name__
                )

        logger.debug(
            "Uppdaterade %d mappningar i översättningsdata.", len(new_mappings)
        )
        return data

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_translation_dir(self, project_path: Path) -> Path:
        """Resolve the translation directory from a project path.

        If project_path is a file (e.g. .json.gz), the translation
        directory is at ``project_path.parent / "translation"``.
        If it's a directory, it's at ``project_path / "translation"``.

        Args:
            project_path: The project file or folder path.

        Returns:
            The resolved path to the translation/ directory.
        """
        if project_path.is_file():
            return project_path.parent / "translation"
        return project_path / "translation"

    def _upsert_source_mapping(
        self, data: TranslationData, mapping: SourceMapping
    ) -> None:
        """Add or update a source mapping in the translation data."""
        for i, existing in enumerate(data.sources):
            if existing.gedcom_id == mapping.gedcom_id:
                data.sources[i] = mapping
                return
        data.sources.append(mapping)

    def _upsert_place_mapping(
        self, data: TranslationData, mapping: PlaceMapping
    ) -> None:
        """Add or update a place mapping in the translation data."""
        for i, existing in enumerate(data.places):
            if existing.gedcom_place == mapping.gedcom_place:
                data.places[i] = mapping
                return
        data.places.append(mapping)

    def _upsert_person_mapping(
        self, data: TranslationData, mapping: PersonMapping
    ) -> None:
        """Add or update a person mapping in the translation data."""
        for i, existing in enumerate(data.persons):
            if existing.gedcom_id == mapping.gedcom_id:
                data.persons[i] = mapping
                return
        data.persons.append(mapping)

    def _upsert_family_mapping(
        self, data: TranslationData, mapping: FamilyMapping
    ) -> None:
        """Add or update a family mapping in the translation data."""
        for i, existing in enumerate(data.families):
            if existing.gedcom_id == mapping.gedcom_id:
                data.families[i] = mapping
                return
        data.families.append(mapping)
