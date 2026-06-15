"""Shared dataclasses for GEDCOM translation logic.

This module defines intermediate/working data structures used by the
translation pipeline modules (person_mapping, place_translation,
source_translation, matcher). These are **not** persistence models—they
represent GEDCOM data extracted from the parse tree *before* it is converted
to App_JSON entities, plus supporting structures for fingerprinting and
diff classification during re-import.

The persistence-layer dataclasses (SourceMapping, PlaceMapping,
PersonMapping, FamilyMapping, TranslationData) live in
``slaktbusken.persistence.translation_io`` and handle file I/O concerns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# GEDCOM extraction models
# ---------------------------------------------------------------------------


@dataclass
class GedcomPerson:
    """A person extracted from a GEDCOM INDI record before App_JSON translation.

    Holds the raw data parsed from GEDCOM tags in a structured form that
    is convenient for fingerprinting, matching, and eventual conversion
    to the App_JSON Person/Event model.

    Attributes:
        xref_id: The GEDCOM cross-reference identifier (e.g. ``"@I1@"``).
        given_name: Given name(s) extracted from the NAME tag.
        surname: Surname extracted from the NAME tag.
        sex: Sex value from the SEX tag (``"M"``, ``"F"``, ``"X"``, or ``"U"``).
        birth_date: Raw date string from the BIRT.DATE tag, if present.
        birth_place: Raw place string from the BIRT.PLAC tag, if present.
        death_date: Raw date string from the DEAT.DATE tag, if present.
        death_place: Raw place string from the DEAT.PLAC tag, if present.
        additional_names: Any additional NAME entries beyond the primary name.
        title: Title from the TITL tag, if present.
        occupation: Occupation from the OCCU tag, if present.
        notes: Notes from NOTE tags concatenated together.
        source_citations: GEDCOM source cross-references cited on this person.
        line_number: The GEDCOM file line number where this record starts.
    """

    xref_id: str
    given_name: str = ""
    surname: str = ""
    sex: str = "U"
    birth_date: Optional[str] = None
    birth_place: Optional[str] = None
    death_date: Optional[str] = None
    death_place: Optional[str] = None
    additional_names: list[tuple[str, str]] = field(default_factory=list)
    title: Optional[str] = None
    occupation: Optional[str] = None
    notes: str = ""
    source_citations: list[str] = field(default_factory=list)
    line_number: int = 0


@dataclass
class GedcomFamily:
    """A family extracted from a GEDCOM FAM record before App_JSON translation.

    Represents the GEDCOM family structure with cross-reference IDs for
    partners and children. These xrefs are resolved to App_JSON IDs
    during the translation step.

    Attributes:
        xref_id: The GEDCOM family cross-reference identifier (e.g. ``"@F1@"``).
        husb_xref: Cross-reference to the husband/partner1 INDI, if present.
        wife_xref: Cross-reference to the wife/partner2 INDI, if present.
        child_xrefs: Ordered list of cross-references to child INDIs.
        marriage_date: Raw date string from the MARR.DATE tag, if present.
        marriage_place: Raw place string from the MARR.PLAC tag, if present.
        divorce_date: Raw date string from the DIV.DATE tag, if present.
        source_citations: GEDCOM source cross-references cited on this family.
        line_number: The GEDCOM file line number where this record starts.
    """

    xref_id: str
    husb_xref: Optional[str] = None
    wife_xref: Optional[str] = None
    child_xrefs: list[str] = field(default_factory=list)
    marriage_date: Optional[str] = None
    marriage_place: Optional[str] = None
    divorce_date: Optional[str] = None
    source_citations: list[str] = field(default_factory=list)
    line_number: int = 0


@dataclass
class GedcomSource:
    """A source extracted from a GEDCOM SOUR record before App_JSON translation.

    Contains the raw data from GEDCOM source tags that will be mapped to
    the App_JSON structured source format.

    Attributes:
        xref_id: The GEDCOM source cross-reference identifier (e.g. ``"@S1@"``).
        title: Title from the TITL tag.
        author: Author from the AUTH tag, if present.
        publication: Publication info from the PUBL tag, if present.
        repository_xref: Cross-reference to a REPO record, if present.
        call_number: Call number from the REPO.CALN tag, if present.
        text: Text content from the TEXT tag, if present.
        abbreviation: Abbreviation from the ABBR tag, if present.
        notes: Notes from NOTE tags concatenated together.
        line_number: The GEDCOM file line number where this record starts.
    """

    xref_id: str
    title: str = ""
    author: Optional[str] = None
    publication: Optional[str] = None
    repository_xref: Optional[str] = None
    call_number: Optional[str] = None
    text: Optional[str] = None
    abbreviation: Optional[str] = None
    notes: str = ""
    line_number: int = 0


@dataclass
class GedcomPlace:
    """A place string extracted from a GEDCOM PLAC value.

    GEDCOM represents places as comma-separated hierarchical strings
    (most specific to least specific). This dataclass holds both the
    original string and the parsed hierarchy levels for translation
    into the App_JSON hierarchical Place model.

    Attributes:
        original: The verbatim place string from the GEDCOM file
            (e.g. ``"Ljusdal, Gävleborgs län, Sverige"``).
        levels: The place hierarchy split into individual levels, ordered
            from most specific to least specific.
        source_line_number: The GEDCOM line number where this place was found.
    """

    original: str
    levels: list[str] = field(default_factory=list)
    source_line_number: int = 0

    def __post_init__(self) -> None:
        """Parse the original string into hierarchy levels if not provided."""
        if not self.levels and self.original:
            self.levels = [part.strip() for part in self.original.split(",")]


# ---------------------------------------------------------------------------
# Fingerprint and hashing models
# ---------------------------------------------------------------------------


@dataclass
class PersonFingerprint:
    """Computed fingerprint data for a person used in re-import matching.

    Contains three distinct hashes that serve different purposes during
    the diff/matching process:

    - **composite_key_hash**: Identifies *who* the person is (stable identity).
      Based on primary name + birth date + birth place.
    - **record_hash**: Detects *content changes* in the full person record.
      Based on all person fields (names, dates, places, notes, etc.).
    - **relationship_hash**: Detects *structural changes* in family context.
      Based on the person's family connections (partner and child xrefs).

    Attributes:
        xref_id: The GEDCOM cross-reference for the person this fingerprint
            belongs to.
        composite_key_hash: SHA-256 hex digest of the identity composite key
            (given name + surname + birth date + birth place).
        record_hash: SHA-256 hex digest of all person fields concatenated
            in a deterministic order.
        relationship_hash: SHA-256 hex digest of the person's family
            structure (partner xrefs + child xrefs in sorted order).
    """

    xref_id: str
    composite_key_hash: str
    record_hash: str
    relationship_hash: str


# ---------------------------------------------------------------------------
# Diff classification models
# ---------------------------------------------------------------------------


class DiffCategory(Enum):
    """Classification categories for person diff during re-import.

    Each person from an incoming GEDCOM file is classified into one of
    these categories by comparing against existing App_JSON data via
    translation files and fingerprints.

    Attributes:
        NEW: No match found in existing data. The person will be added.
        UPDATED: Matched an existing person but the record hash differs.
            The existing record should be updated with new data.
        UNCHANGED: Matched an existing person and the record hash is
            identical. No action needed.
        MISSING: Present in existing App_JSON (via translation file) but
            absent from the incoming GEDCOM. May indicate deletion.
        UNCERTAIN: Fingerprint similarity is above threshold but below
            exact match. Requires user verification to confirm identity.
    """

    NEW = "new"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    MISSING = "missing"
    UNCERTAIN = "uncertain"


@dataclass
class PersonDiffEntry:
    """One person's diff classification result during re-import.

    Represents the outcome of comparing a single person between the
    incoming GEDCOM data and the existing App_JSON project data.

    Attributes:
        gedcom_xref: The GEDCOM cross-reference identifier for the person.
        app_id: The App_JSON person ID if matched, or ``None`` for new persons.
        category: The diff classification result.
        fingerprint: The computed fingerprint for this person.
        similarity_score: For UNCERTAIN matches, the similarity score
            (0.0–1.0) indicating how close the match is. ``None`` for
            definite classifications.
        matched_app_id: For UNCERTAIN matches, the candidate App_JSON ID
            that was partially matched. Same as ``app_id`` for definite matches.
    """

    gedcom_xref: str
    app_id: Optional[str]
    category: DiffCategory
    fingerprint: PersonFingerprint
    similarity_score: Optional[float] = None
    matched_app_id: Optional[str] = None


@dataclass
class ImportDiffReport:
    """Structured report summarizing the diff results for a GEDCOM re-import.

    Provides counts and detailed entries for each diff category, giving
    both a quick overview and drill-down capability for the import service
    and user interface.

    Attributes:
        new_count: Number of persons classified as NEW.
        updated_count: Number of persons classified as UPDATED.
        unchanged_count: Number of persons classified as UNCHANGED.
        missing_count: Number of persons classified as MISSING.
        uncertain_count: Number of persons classified as UNCERTAIN.
        entries: Full list of individual diff classification entries.
    """

    new_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    missing_count: int = 0
    uncertain_count: int = 0
    entries: list[PersonDiffEntry] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        """Total number of persons processed in this diff report."""
        return (
            self.new_count
            + self.updated_count
            + self.unchanged_count
            + self.missing_count
            + self.uncertain_count
        )

    @property
    def has_uncertain(self) -> bool:
        """Whether there are any uncertain matches requiring user review."""
        return self.uncertain_count > 0

    @property
    def has_changes(self) -> bool:
        """Whether the import would produce any changes (new, updated, or missing)."""
        return self.new_count > 0 or self.updated_count > 0 or self.missing_count > 0
