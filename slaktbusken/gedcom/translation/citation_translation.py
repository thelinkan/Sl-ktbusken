"""Build human-readable citation strings from structured source references.

This module provides functions to construct citation text from the App_JSON
Source model's ``structured_reference`` fields. The resulting citation strings
are used both in the UI for display and during GEDCOM export (requirement 5.4,
5.5) where structured fields must be concatenated into a single citation.

Each source type has a dedicated builder that formats fields in the
conventional Swedish genealogical citation style. Missing fields are omitted
gracefully so the citation remains readable.

Supported source types and their citation patterns:

- **church_book**: ``"Parish (CountyCode) Series:Volume (Years) Bild: Image Sida: Page"``
- **database**: ``"DatabaseName, Record ID: RecordId"``
- **death_notice**: ``"Newspaper, PublicationDate, s. Page"``
- **newspaper**: ``"Newspaper, Date, s. Page - ArticleTitle"``
- **other/photograph/census**: Falls back to ``reference_text`` or ``title``.
"""

from __future__ import annotations

from slaktbusken.model.source import Source, StructuredReference


def build_citation_text(source: Source) -> str:
    """Build a full citation text from a Source's structured reference.

    Dispatches to the appropriate type-specific citation builder based on
    the source's ``source_type``. If no structured reference data is
    available for the type, falls back to ``build_generic_citation``.

    Args:
        source: The Source record to generate a citation for.

    Returns:
        A human-readable citation string. Never returns an empty string;
        at minimum the source title is returned.
    """
    ref = source.structured_reference

    builders = {
        "church_book": build_church_book_citation,
        "database": build_database_citation,
        "death_notice": build_death_notice_citation,
        "newspaper": build_newspaper_citation,
    }

    builder = builders.get(source.source_type)
    if builder is not None:
        result = builder(ref)
        if result:
            return result

    return build_generic_citation(source)


def build_church_book_citation(ref: StructuredReference) -> str:
    """Format a church book reference as a citation string.

    Produces the conventional Swedish church book citation format::

        Parish (CountyCode) Series:Volume (Years) Bild: Image Sida: Page

    Example::

        Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915

    Parts with missing fields are omitted gracefully. If no fields are
    present at all, returns an empty string (caller should fall back to
    generic citation).

    Args:
        ref: The StructuredReference containing church book fields.
            Expected keys: ``parish``, ``county_code``, ``series``,
            ``volume``, ``years``, ``image``, ``page``.

    Returns:
        The formatted citation string, or empty string if no relevant
        fields are present.
    """
    fields = ref.fields
    parts: list[str] = []

    parish = fields.get("parish")
    county_code = fields.get("county_code")

    if parish:
        parish_str = str(parish)
        if county_code:
            parish_str += f" ({county_code})"
        parts.append(parish_str)

    series = fields.get("series")
    volume = fields.get("volume")

    if series:
        series_str = str(series)
        if volume:
            series_str += f":{volume}"
        parts.append(series_str)
    elif volume:
        parts.append(str(volume))

    years = fields.get("years")
    if years:
        parts.append(f"({years})")

    image = fields.get("image")
    if image is not None:
        parts.append(f"Bild: {image}")

    page = fields.get("page")
    if page is not None:
        parts.append(f"Sida: {page}")

    return " ".join(parts)


def build_database_citation(ref: StructuredReference) -> str:
    """Format a database source reference as a citation string.

    Produces the format::

        DatabaseName, Record ID: RecordId

    Example::

        Sveriges Befolkning 1900, Record ID: 12345

    Args:
        ref: The StructuredReference containing database fields.
            Expected keys: ``database_name``, ``record_id``.

    Returns:
        The formatted citation string, or empty string if no relevant
        fields are present.
    """
    fields = ref.fields
    parts: list[str] = []

    database_name = fields.get("database_name")
    if database_name:
        parts.append(str(database_name))

    record_id = fields.get("record_id")
    if record_id:
        parts.append(f"Record ID: {record_id}")

    return ", ".join(parts)


def build_death_notice_citation(ref: StructuredReference) -> str:
    """Format a death notice reference as a citation string.

    Produces the format::

        Newspaper, PublicationDate, s. Page

    Example::

        Hudiksvalls Tidning, 2023-05-15, s. 12

    Args:
        ref: The StructuredReference containing death notice fields.
            Expected keys: ``newspaper``, ``publication_date``, ``page``.

    Returns:
        The formatted citation string, or empty string if no relevant
        fields are present.
    """
    fields = ref.fields
    parts: list[str] = []

    newspaper = fields.get("newspaper")
    if newspaper:
        parts.append(str(newspaper))

    publication_date = fields.get("publication_date")
    if publication_date:
        parts.append(str(publication_date))

    page = fields.get("page")
    if page is not None:
        parts.append(f"s. {page}")

    return ", ".join(parts)


def build_newspaper_citation(ref: StructuredReference) -> str:
    """Format a newspaper source reference as a citation string.

    Produces the format::

        Newspaper, Date, s. Page - ArticleTitle

    Example::

        Dagens Nyheter, 1950-03-01, s. 5 - Dödsannons

    The article title is appended with `` - `` separator after the page
    if present.

    Args:
        ref: The StructuredReference containing newspaper fields.
            Expected keys: ``newspaper``, ``date``, ``page``,
            ``article_title``.

    Returns:
        The formatted citation string, or empty string if no relevant
        fields are present.
    """
    fields = ref.fields
    parts: list[str] = []

    newspaper = fields.get("newspaper")
    if newspaper:
        parts.append(str(newspaper))

    date = fields.get("date")
    if date:
        parts.append(str(date))

    page = fields.get("page")
    if page is not None:
        parts.append(f"s. {page}")

    base = ", ".join(parts)

    article_title = fields.get("article_title")
    if article_title:
        if base:
            return f"{base} - {article_title}"
        return str(article_title)

    return base


def build_generic_citation(source: Source) -> str:
    """Build a fallback citation from reference_text or title.

    Used for source types that do not have dedicated structured citation
    builders (photograph, census, other) or when structured fields are
    empty.

    Args:
        source: The Source record to generate a citation for.

    Returns:
        The source's ``reference_text`` if non-empty, otherwise the
        source's ``title``. Guaranteed non-empty since Source requires
        a title.
    """
    if source.reference_text:
        return source.reference_text
    return source.title
