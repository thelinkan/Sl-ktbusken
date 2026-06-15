"""GEDCOM source ID to structured App_JSON Source mapping.

This module provides logic for translating GEDCOM source records (SOUR) into
the App_JSON structured Source format. It handles:

- Source type detection from GEDCOM source content (church_book, database,
  death_notice, newspaper, photograph, census, other)
- Parsing Swedish church book citations into structured reference fields
- ArkivDigital source detection (prefix "ArkivDigital:" or matching the
  structured church book pattern with ArkivDigital provider)
- Finding existing Source records that match a given GEDCOM source
- Creating new Source records when no match exists

Swedish church book citation format:
    "Parish (CountyCode) Series:Volume (Years) Bild: N Sida: N"
    Example: "Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915"

Structured reference fields for church_book type:
    - parish: str (e.g., "Ljusdal")
    - county_code: str (e.g., "X" for Gävleborg)
    - series: str (free text, e.g., "AI" for Husförhörslängd)
    - volume: str (e.g., "23d")
    - years: str (e.g., "1883-1887")
    - image: int (image/bild number)
    - page: int (page/sida number)

Validates: Requirements 4.4, 11.7
"""

from __future__ import annotations

import re
from typing import Optional

from slaktbusken.gedcom.translation.models import GedcomSource
from slaktbusken.model.id_generator import IDGenerator
from slaktbusken.model.source import RepositoryRef, Source, StructuredReference
from slaktbusken.persistence.translation_io import SourceMapping


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_SOURCE_TYPES = frozenset(
    {"church_book", "database", "death_notice", "newspaper", "photograph", "census", "other"}
)

# Pattern: "Parish (CountyCode) Series:Volume (Years) Bild: N Sida: N"
# Examples:
#   "Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915"
#   "Sundsvall (Y) CI:5 (1801-1810) Bild: 100 Sida: 50"
# Groups: parish, county_code, series, volume, years, image, page
_CHURCH_BOOK_PATTERN = re.compile(
    r"^(?P<parish>[^(]+?)\s*"
    r"\((?P<county_code>[A-Za-zÅÄÖåäö]+)\)\s*"
    r"(?P<series>[A-Za-zÅÄÖåäö]+)\s*:\s*(?P<volume>[^\s(]+)\s*"
    r"\((?P<years>\d{4}\s*-\s*\d{4})\)\s*"
    r"Bild\s*:\s*(?P<image>\d+)"
    r"(?:\s+Sida\s*:\s*(?P<page>\d+))?",
    re.IGNORECASE,
)

# Looser pattern for ArkivDigital detection: matches the church book structure
# without requiring Bild/Sida (but still has parish, county_code, series, volume, years)
_ARKIV_DIGITAL_STRUCTURE_PATTERN = re.compile(
    r"^(?P<parish>[^(]+?)\s*"
    r"\((?P<county_code>[A-Za-zÅÄÖåäö]+)\)\s*"
    r"(?P<series>[A-Za-zÅÄÖåäö]+)\s*:\s*(?P<volume>[^\s(]+)\s*"
    r"\((?P<years>\d{4}\s*-\s*\d{4})\)",
    re.IGNORECASE,
)

_ARKIV_DIGITAL_PREFIX = "arkivdigital:"

# Keywords for source type detection
_DATABASE_KEYWORDS = ("database", "databas", "online", "register")
_DEATH_NOTICE_KEYWORDS = ("dödsannons", "death notice", "dödsnotis")
_NEWSPAPER_KEYWORDS = ("tidning", "newspaper", "journal", "tidskrift")
_PHOTOGRAPH_KEYWORDS = ("foto", "photo", "photograph", "fotografi", "bild")
_CENSUS_KEYWORDS = ("folkräkning", "mantalslängd", "census", "husförhör")


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def map_gedcom_source(
    gedcom_source: GedcomSource,
    existing_sources: list[Source],
    source_mappings: list[SourceMapping],
) -> Source:
    """Map a GEDCOM source record to an App_JSON Source entity.

    First attempts to find an existing App_JSON Source that matches the
    GEDCOM source (via translation mappings or content matching). If a
    match is found, returns the existing Source. If no match exists,
    creates a new Source with an auto-generated ID, detected source type,
    and parsed structured reference.

    Args:
        gedcom_source: The GEDCOM source record to translate.
        existing_sources: All Source records currently in the project.
        source_mappings: The current source translation mappings from
            the translation file.

    Returns:
        The matched existing Source, or a newly created Source entity with
        fields populated from the GEDCOM source data.

    Examples:
        >>> gs = GedcomSource(xref_id="@S1@", title="Ljusdal AI:23d",
        ...     text="Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915")
        >>> source = map_gedcom_source(gs, [], [])
        >>> source.source_type
        'church_book'
        >>> source.structured_reference.fields['parish']
        'Ljusdal'
    """
    # Try to find an existing match
    matched_id = find_matching_source(gedcom_source, existing_sources, source_mappings)
    if matched_id is not None:
        for source in existing_sources:
            if source.id == matched_id:
                return source

    # No match found — create a new Source
    existing_ids = {s.id for s in existing_sources}
    id_gen = IDGenerator(existing_ids)
    new_id = id_gen.generate("source")

    source_type = detect_source_type(gedcom_source)
    structured_ref = _build_structured_reference(gedcom_source, source_type)
    title = gedcom_source.title or _derive_title(gedcom_source)
    reference_text = _derive_reference_text(gedcom_source)
    provider = _derive_provider(gedcom_source)

    return Source(
        id=new_id,
        provider=provider,
        source_type=source_type,
        title=title,
        reference_text=reference_text,
        provider_ref=gedcom_source.abbreviation or "",
        short_note="",
        free_note=gedcom_source.notes,
        structured_reference=structured_ref,
        media_ids=[],
        repository_refs=[],
    )


def detect_source_type(gedcom_source: GedcomSource) -> str:
    """Infer the source_type from a GEDCOM source's content.

    Examines the source's title, text, and other fields to determine
    the most appropriate source type. Detection priority:

    1. If the text or title matches the church book citation pattern
       → "church_book"
    2. If the text or title contains database-related keywords
       → "database"
    3. If the text or title contains death notice keywords
       → "death_notice"
    4. If the text or title contains newspaper keywords
       → "newspaper"
    5. If the text or title contains photograph keywords
       → "photograph"
    6. If the text or title contains census/husförhör keywords
       → "census"
    7. Otherwise → "other"

    Args:
        gedcom_source: The GEDCOM source record to analyze.

    Returns:
        A source type string: one of "church_book", "database",
        "death_notice", "newspaper", "photograph", "census", or "other".

    Examples:
        >>> gs = GedcomSource(xref_id="@S1@",
        ...     text="Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915")
        >>> detect_source_type(gs)
        'church_book'
        >>> gs2 = GedcomSource(xref_id="@S2@", title="Folkräkning 1900")
        >>> detect_source_type(gs2)
        'census'
    """
    searchable_text = _get_searchable_text(gedcom_source)

    # Church book: check the structured citation pattern
    if _CHURCH_BOOK_PATTERN.search(searchable_text):
        return "church_book"

    searchable_lower = searchable_text.lower()

    # Database
    if any(kw in searchable_lower for kw in _DATABASE_KEYWORDS):
        return "database"

    # Death notice
    if any(kw in searchable_lower for kw in _DEATH_NOTICE_KEYWORDS):
        return "death_notice"

    # Newspaper
    if any(kw in searchable_lower for kw in _NEWSPAPER_KEYWORDS):
        return "newspaper"

    # Photograph
    if any(kw in searchable_lower for kw in _PHOTOGRAPH_KEYWORDS):
        return "photograph"

    # Census / husförhör
    if any(kw in searchable_lower for kw in _CENSUS_KEYWORDS):
        return "census"

    return "other"


def parse_church_book_citation(text: str) -> Optional[StructuredReference]:
    """Parse a Swedish church book citation string into structured fields.

    Expects the format:
        "Parish (CountyCode) Series:Volume (Years) Bild: N Sida: N"

    The "Sida: N" portion is optional. The "Bild: N" portion is required
    for a successful parse.

    Args:
        text: The citation text to parse. May be a full reference_text
            from a church book source.

    Returns:
        A StructuredReference with fields populated (parish, county_code,
        series, volume, years, image, page) if the text matches the
        expected pattern. Returns None if the text does not match.

    Examples:
        >>> ref = parse_church_book_citation(
        ...     "Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915"
        ... )
        >>> ref is not None
        True
        >>> ref.fields['parish']
        'Ljusdal'
        >>> ref.fields['county_code']
        'X'
        >>> ref.fields['series']
        'AI'
        >>> ref.fields['volume']
        '23d'
        >>> ref.fields['years']
        '1883-1887'
        >>> ref.fields['image']
        23
        >>> ref.fields['page']
        915
        >>> parse_church_book_citation("Some random text")
        >>> # Returns None
    """
    match = _CHURCH_BOOK_PATTERN.search(text)
    if match is None:
        return None

    fields: dict[str, Optional[str | int]] = {
        "parish": match.group("parish").strip(),
        "county_code": match.group("county_code").strip(),
        "series": match.group("series").strip(),
        "volume": match.group("volume").strip(),
        "years": match.group("years").replace(" ", ""),
        "image": int(match.group("image")),
    }

    page_str = match.group("page")
    if page_str is not None:
        fields["page"] = int(page_str)
    else:
        fields["page"] = None

    return StructuredReference(fields=fields)


def detect_arkiv_digital(gedcom_source: GedcomSource) -> bool:
    """Check if a GEDCOM source originates from ArkivDigital.

    A source is considered from ArkivDigital if:
    1. The source text begins with "ArkivDigital:" (case-insensitive), OR
    2. The source title begins with "ArkivDigital:" (case-insensitive), OR
    3. The source text or title matches the structured church book pattern
       (parish, county code, series, volume, years, image) AND the author
       or publication field references ArkivDigital.

    Args:
        gedcom_source: The GEDCOM source record to check.

    Returns:
        True if the source is identified as an ArkivDigital source,
        False otherwise.

    Examples:
        >>> gs = GedcomSource(xref_id="@S1@",
        ...     text="ArkivDigital: Ljusdal (X) AI:23d (1883-1887) Bild: 23")
        >>> detect_arkiv_digital(gs)
        True
        >>> gs2 = GedcomSource(xref_id="@S2@", title="My family tree")
        >>> detect_arkiv_digital(gs2)
        False
    """
    # Check text field
    if gedcom_source.text:
        text_stripped = gedcom_source.text.strip().lower()
        if text_stripped.startswith(_ARKIV_DIGITAL_PREFIX):
            return True

    # Check title field
    if gedcom_source.title:
        title_stripped = gedcom_source.title.strip().lower()
        if title_stripped.startswith(_ARKIV_DIGITAL_PREFIX):
            return True

    # Check if the structured pattern is present AND author/publication
    # mentions ArkivDigital
    searchable = _get_searchable_text(gedcom_source)
    if _ARKIV_DIGITAL_STRUCTURE_PATTERN.search(searchable):
        ad_lower = "arkivdigital"
        if gedcom_source.author and ad_lower in gedcom_source.author.lower():
            return True
        if gedcom_source.publication and ad_lower in gedcom_source.publication.lower():
            return True

    return False


def find_matching_source(
    gedcom_source: GedcomSource,
    existing_sources: list[Source],
    source_mappings: list[SourceMapping],
) -> Optional[str]:
    """Find an existing App_JSON source ID matching the GEDCOM source.

    Searches the source translation mappings for an exact match on the
    GEDCOM source cross-reference identifier. If found, validates that the
    target source still exists in the project.

    If no mapping match is found, performs content-based matching by
    comparing the GEDCOM source title against existing source titles
    (case-insensitive).

    Args:
        gedcom_source: The GEDCOM source to look up.
        existing_sources: All Source records currently in the project.
        source_mappings: The current source translation mappings from
            the translation file.

    Returns:
        The App_JSON source ID if a match is found and the target source
        still exists, or None if no match is found.

    Examples:
        >>> mapping = SourceMapping(
        ...     gedcom_id="@S1@", app_id="source_1", title="Test Source"
        ... )
        >>> source = Source(id="source_1", provider="", source_type="other",
        ...     title="Test Source")
        >>> gs = GedcomSource(xref_id="@S1@", title="Test Source")
        >>> find_matching_source(gs, [source], [mapping])
        'source_1'
    """
    existing_ids = {s.id for s in existing_sources}

    # First: check translation mappings by GEDCOM xref_id
    for mapping in source_mappings:
        if mapping.gedcom_id == gedcom_source.xref_id:
            if mapping.app_id in existing_ids:
                return mapping.app_id

    # Second: content-based matching by title (case-insensitive)
    if gedcom_source.title:
        gedcom_title_lower = gedcom_source.title.strip().lower()
        for source in existing_sources:
            if source.title.strip().lower() == gedcom_title_lower:
                return source.id

    return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _get_searchable_text(gedcom_source: GedcomSource) -> str:
    """Combine relevant GEDCOM source fields into a single searchable string.

    Concatenates title, text, publication, and abbreviation fields
    (if present) separated by spaces for pattern matching.

    Args:
        gedcom_source: The GEDCOM source to extract text from.

    Returns:
        A combined string of all relevant source text fields.
    """
    parts: list[str] = []
    if gedcom_source.title:
        parts.append(gedcom_source.title)
    if gedcom_source.text:
        parts.append(gedcom_source.text)
    if gedcom_source.publication:
        parts.append(gedcom_source.publication)
    if gedcom_source.abbreviation:
        parts.append(gedcom_source.abbreviation)
    return " ".join(parts)


def _build_structured_reference(
    gedcom_source: GedcomSource, source_type: str
) -> StructuredReference:
    """Build a StructuredReference from GEDCOM source data.

    For church_book sources, attempts to parse the citation from the
    text field first (most likely location for structured citations),
    then the title field. For other types, returns an empty structured
    reference.

    Args:
        gedcom_source: The GEDCOM source record.
        source_type: The detected source type.

    Returns:
        A StructuredReference with type-appropriate fields populated.
    """
    if source_type == "church_book":
        # Try text field first (most likely to contain the full citation)
        if gedcom_source.text:
            text = gedcom_source.text.strip()
            # Strip ArkivDigital prefix before parsing
            if text.lower().startswith(_ARKIV_DIGITAL_PREFIX):
                text = text[len(_ARKIV_DIGITAL_PREFIX) :].strip()
            ref = parse_church_book_citation(text)
            if ref is not None:
                return ref

        # Try title field
        if gedcom_source.title:
            ref = parse_church_book_citation(gedcom_source.title)
            if ref is not None:
                return ref

        # Fall back to publication or abbreviation
        if gedcom_source.publication:
            ref = parse_church_book_citation(gedcom_source.publication)
            if ref is not None:
                return ref

    return StructuredReference()


def _derive_title(gedcom_source: GedcomSource) -> str:
    """Derive a title for a Source when the GEDCOM title is empty.

    Falls back to abbreviation, then a truncated version of the text field,
    or finally the xref_id.

    Args:
        gedcom_source: The GEDCOM source record.

    Returns:
        A non-empty title string for the source.
    """
    if gedcom_source.abbreviation:
        return gedcom_source.abbreviation

    if gedcom_source.text:
        # Use first 80 characters of text as title
        text = gedcom_source.text.strip()
        if len(text) > 80:
            return text[:77] + "..."
        return text

    return f"Source {gedcom_source.xref_id}"


def _derive_reference_text(gedcom_source: GedcomSource) -> str:
    """Derive the reference_text field from GEDCOM source data.

    Uses the text field if available (stripping "ArkivDigital:" prefix
    if present), otherwise uses the title.

    Args:
        gedcom_source: The GEDCOM source record.

    Returns:
        A reference text string, possibly empty if no content is available.
    """
    if gedcom_source.text:
        text = gedcom_source.text.strip()
        # Strip ArkivDigital prefix for cleaner reference_text
        if text.lower().startswith(_ARKIV_DIGITAL_PREFIX):
            text = text[len(_ARKIV_DIGITAL_PREFIX) :].strip()
        return text

    return gedcom_source.title or ""


def _derive_provider(gedcom_source: GedcomSource) -> str:
    """Derive the provider field from GEDCOM source data.

    If the source is from ArkivDigital, returns "ArkivDigital".
    Otherwise uses the author field, or falls back to empty string.

    Args:
        gedcom_source: The GEDCOM source record.

    Returns:
        The provider name string.
    """
    if detect_arkiv_digital(gedcom_source):
        return "ArkivDigital"

    if gedcom_source.author:
        return gedcom_source.author

    return ""
