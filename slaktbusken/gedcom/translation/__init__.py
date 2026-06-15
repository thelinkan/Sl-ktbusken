"""GEDCOM translation package — unified facade and public type exports.

This package handles all translation logic between GEDCOM data and App_JSON
format. The :class:`TranslationManager` provides a single entry point for
import/export services to interact with person fingerprinting, place mapping,
source mapping, citation building, and fuzzy/exact entity matching.

Validates: Requirements 4.1, 4.2, 4.4, 4.5, 4.6
"""

from __future__ import annotations

from pathlib import Path

from slaktbusken.gedcom.translation.citation_translation import build_citation_text
from slaktbusken.gedcom.translation.models import (
    DiffCategory,
    GedcomFamily,
    GedcomPerson,
    GedcomPlace,
    GedcomSource,
    ImportDiffReport,
    PersonDiffEntry,
    PersonFingerprint,
)
from slaktbusken.gedcom.translation.person_mapping import (
    classify_persons as _classify_persons,
    compute_fingerprint as _compute_fingerprint,
)
from slaktbusken.gedcom.translation.place_translation import (
    find_matching_place,
    map_place_to_hierarchy,
    parse_place_string,
)
from slaktbusken.gedcom.translation.source_translation import (
    detect_arkiv_digital,
    map_gedcom_source,
)
from slaktbusken.model.id_generator import IDGenerator
from slaktbusken.model.place import Place
from slaktbusken.model.source import Source
from slaktbusken.persistence.translation_io import (
    TranslationData,
    read_all as _read_all,
    write_all as _write_all,
)

__all__ = [
    "TranslationManager",
    # Models re-exported for consumers
    "GedcomPerson",
    "GedcomFamily",
    "GedcomSource",
    "GedcomPlace",
    "ImportDiffReport",
    "DiffCategory",
    "PersonDiffEntry",
    "PersonFingerprint",
]


class TranslationManager:
    """Facade coordinating all GEDCOM translation modules.

    Provides a unified interface for importing GEDCOM data into App_JSON
    format. Used by ImportService and ExportService to perform the actual
    translation work without needing direct knowledge of individual
    translation modules.

    Args:
        translation_dir: Path to the project's ``translation/`` directory
            where mapping JSON files are stored.
    """

    def __init__(self, translation_dir: Path) -> None:
        """Initialize with path to the project's translation directory."""
        self._translation_dir = translation_dir

    # ------------------------------------------------------------------
    # Translation data I/O
    # ------------------------------------------------------------------

    def load_translations(self) -> TranslationData:
        """Load all translation files from the translation directory.

        Reads sources.json, places.json, and persons.json from the
        configured translation directory.

        Returns:
            A TranslationData container with all persisted mappings.
            Missing files result in empty lists for those mapping types.
        """
        return _read_all(self._translation_dir)

    def save_translations(self, data: TranslationData) -> None:
        """Save all translation data back to the translation directory.

        Writes sources.json, places.json, and persons.json to the
        configured translation directory, creating it if necessary.

        Args:
            data: The TranslationData container with all mappings to persist.
        """
        _write_all(data, self._translation_dir)

    # ------------------------------------------------------------------
    # Person classification
    # ------------------------------------------------------------------

    def classify_persons(
        self,
        incoming: list[GedcomPerson],
        families: list[GedcomFamily],
        existing_fingerprints: dict[str, str],
    ) -> ImportDiffReport:
        """Classify incoming persons against existing data.

        Uses fingerprints and translation mappings to determine whether
        each incoming person is new, updated, unchanged, missing, or
        uncertain relative to the current project state.

        Args:
            incoming: Persons extracted from the incoming GEDCOM file.
            families: Families extracted from the incoming GEDCOM file.
            existing_fingerprints: Maps App_JSON person IDs to their
                stored composite_key_hash values.

        Returns:
            An ImportDiffReport summarizing all classification results.
        """
        translation_data = self.load_translations()
        return _classify_persons(
            incoming=incoming,
            families=families,
            existing_mappings=translation_data.persons,
            existing_fingerprints=existing_fingerprints,
        )

    # ------------------------------------------------------------------
    # Place mapping
    # ------------------------------------------------------------------

    def map_place(
        self,
        gedcom_place_string: str,
        existing_places: list[Place],
    ) -> tuple[str | None, list[Place]]:
        """Map a GEDCOM place string to an App_JSON place ID.

        First checks translation mappings for a known mapping. If none is
        found, parses the place hierarchy and creates new Place records as
        needed.

        Args:
            gedcom_place_string: The verbatim GEDCOM place string
                (e.g. "Ljusdal, Gävleborgs län, Sverige").
            existing_places: All Place records currently in the project.

        Returns:
            A tuple of (matched_or_most_specific_place_id, new_places).
            The first element is the ID of the most-specific place (either
            an existing match or the newly created most-specific place).
            The second element is a list of newly created Place records
            (empty if all levels already existed).
        """
        translation_data = self.load_translations()
        gedcom_place = parse_place_string(gedcom_place_string)

        # Try to find an existing match via translation mappings
        matched_id = find_matching_place(
            gedcom_place, existing_places, translation_data.places
        )
        if matched_id is not None:
            return matched_id, []

        # No existing match — create the hierarchy
        existing_ids = {p.id for p in existing_places}
        id_generator = IDGenerator(existing_ids)

        new_places = map_place_to_hierarchy(
            gedcom_place=gedcom_place,
            existing_places=existing_places,
            place_mappings=translation_data.places,
            id_generator=id_generator,
        )

        # The most-specific place is the last one created (ordered from
        # least specific to most specific)
        most_specific_id: str | None = None
        if new_places:
            most_specific_id = new_places[-1].id
        else:
            # All levels matched existing places; find the most-specific one
            # by re-checking the hierarchy
            matched_id = find_matching_place(
                gedcom_place, existing_places, translation_data.places
            )
            most_specific_id = matched_id

        return most_specific_id, new_places

    # ------------------------------------------------------------------
    # Source mapping
    # ------------------------------------------------------------------

    def map_source(
        self,
        gedcom_source: GedcomSource,
        existing_sources: list[Source],
    ) -> Source:
        """Map a GEDCOM source to an App_JSON Source entity.

        Attempts to find an existing match via translation mappings or
        content-based matching. If no match is found, creates a new Source
        with auto-detected type and parsed structured reference.

        Args:
            gedcom_source: The GEDCOM source record to translate.
            existing_sources: All Source records currently in the project.

        Returns:
            The matched existing Source, or a newly created Source entity.
        """
        translation_data = self.load_translations()
        return map_gedcom_source(
            gedcom_source=gedcom_source,
            existing_sources=existing_sources,
            source_mappings=translation_data.sources,
        )

    # ------------------------------------------------------------------
    # Citation building
    # ------------------------------------------------------------------

    def build_citation(self, source: Source) -> str:
        """Build citation text from a source's structured reference.

        Dispatches to the appropriate type-specific builder based on
        source_type. Falls back to reference_text or title for types
        without dedicated builders.

        Args:
            source: The Source record to generate a citation for.

        Returns:
            A human-readable citation string.
        """
        return build_citation_text(source)

    # ------------------------------------------------------------------
    # Fingerprinting
    # ------------------------------------------------------------------

    def compute_person_fingerprint(
        self,
        person: GedcomPerson,
        families: list[GedcomFamily],
    ) -> PersonFingerprint:
        """Compute fingerprint for a single person.

        Calculates composite_key_hash (identity), record_hash (content),
        and relationship_hash (structure) for the given person.

        Args:
            person: The GEDCOM person to fingerprint.
            families: All families from the GEDCOM file (needed for
                relationship hash computation).

        Returns:
            A PersonFingerprint containing all three hashes.
        """
        return _compute_fingerprint(person, families)

    # ------------------------------------------------------------------
    # ArkivDigital detection
    # ------------------------------------------------------------------

    def is_arkiv_digital(self, gedcom_source: GedcomSource) -> bool:
        """Check if a GEDCOM source is from ArkivDigital.

        A source is considered from ArkivDigital if its text or title
        begins with "ArkivDigital:" or if it matches the structured
        church book pattern with an ArkivDigital author/publication.

        Args:
            gedcom_source: The GEDCOM source record to check.

        Returns:
            True if the source is identified as ArkivDigital, False otherwise.
        """
        return detect_arkiv_digital(gedcom_source)
