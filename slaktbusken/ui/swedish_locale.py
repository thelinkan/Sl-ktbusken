"""Centralized Swedish locale and terminology module for Släktbusken.

Provides:
    1. Swedish translations for all enum values (source types, place types,
       event types, relationship labels).
    2. Date formatting function (YYYY-MM-DD, Swedish convention).
    3. Number formatting function (comma decimal separator, space thousands separator).

This module is the single source of truth for Swedish genealogical terminology
used throughout the UI layer, ensuring consistency across editors, dialogs,
views, and reports.

Validates: Requirements 21.1, 21.2, 21.3, 21.4
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Optional


# ---------------------------------------------------------------------------
# 21.3 — Swedish genealogical terminology
# ---------------------------------------------------------------------------

# Source types (källtyper)
SOURCE_TYPE_LABELS: dict[str, str] = {
    "church_book": "Kyrkobok",
    "database": "Databas",
    "death_notice": "Dödsannons",
    "newspaper": "Tidning",
    "photograph": "Fotografi",
    "census": "Folkräkning",
    "other": "Övrigt",
}

# More specific source type subtypes (church book series)
CHURCH_BOOK_SERIES_LABELS: dict[str, str] = {
    "AI": "Husförhörslängd",
    "CI": "Födelsebok",
    "FI": "Död- och begravningsbok",
    "E": "Lysnings- och vigselbok",
    "B": "Inflyttningslängd",
    "C": "Utflyttningslängd",
    "D": "Konfirmationsbok",
}

# Place types (platstyper)
PLACE_TYPE_LABELS: dict[str, str] = {
    "country": "Land",
    "county": "Län",
    "parish": "Socken",
    "church": "Kyrka",
    "cemetery": "Kyrkogård",
    "village": "By",
    "farm": "Gård",
    "school": "Skola",
}

# Event types — individual (individuella händelsetyper)
INDIVIDUAL_EVENT_TYPE_LABELS: dict[str, str] = {
    "adoption": "Adoption",
    "baptism": "Dop",
    "birth": "Födelse",
    "blessing": "Välsignelse",
    "burial": "Begravning",
    "census": "Folkräkning",
    "confirmation": "Konfirmation",
    "cremation": "Kremering",
    "death": "Död",
    "emigration": "Emigration",
    "first_communion": "Första nattvarden",
    "gender_correction": "Könskorrigering",
    "graduation": "Examen",
    "immigration": "Immigration",
    "name_change": "Namnbyte",
    "retirement": "Pension",
    "will": "Testamente",
    "custom_individual_event": "Anpassad individuell händelse",
}

# Event types — family (familjehändelsetyper)
FAMILY_EVENT_TYPE_LABELS: dict[str, str] = {
    "divorce": "Skilsmässa",
    "divorce_filed": "Skilsmässoansökan",
    "engagement": "Förlovning",
    "marriage": "Vigsel",
    "custom_family_event": "Anpassad familjehändelse",
}

# Combined event type labels
EVENT_TYPE_LABELS: dict[str, str] = {
    **INDIVIDUAL_EVENT_TYPE_LABELS,
    **FAMILY_EVENT_TYPE_LABELS,
}

# Relationship labels (släktskapsbenämningar)
RELATIONSHIP_LABELS: dict[str, str] = {
    "father": "Far",
    "mother": "Mor",
    "husband": "Make",
    "wife": "Maka",
    "partner": "Partner",
    "son": "Son",
    "daughter": "Dotter",
    "brother": "Bror",
    "sister": "Syster",
    "grandfather": "Farfar",
    "grandmother": "Farmor",
    "grandson": "Sonson",
    "granddaughter": "Sondotter",
    "uncle": "Farbror",
    "aunt": "Faster",
    "nephew": "Brorson",
    "niece": "Brordotter",
    "cousin": "Kusin",
    "spouse": "Make/Maka",
}

# Partner role labels (familjeroller)
PARTNER_ROLE_LABELS: dict[str, str] = {
    "father": "Far",
    "mother": "Mor",
    "husband": "Make",
    "wife": "Maka",
    "partner": "Partner",
}

# Parentage type labels (föräldratyper)
PARENTAGE_TYPE_LABELS: dict[str, str] = {
    "biological": "Biologisk",
    "legal": "Juridisk",
    "adoptive": "Adoptiv",
    "foster": "Foster",
    "step": "Styv",
    "unknown_donor": "Okänd donator",
}

# Sex labels
SEX_LABELS: dict[str, str] = {
    "M": "Man",
    "F": "Kvinna",
    "X": "Annat",
    "U": "Okänt",
}

# Media types (mediatyper)
MEDIA_TYPE_LABELS: dict[str, str] = {
    "photo": "Foto",
    "source_image": "Källbild",
    "death_notice": "Dödsannons",
    "obituary": "Minnesruna",
    "funeral_program": "Begravningsprogram",
    "grave_photo": "Gravfoto",
    "map": "Karta",
    "logo": "Logotyp",
    "document": "Dokument",
}

# DNA test types
DNA_TEST_TYPE_LABELS: dict[str, str] = {
    "autosomal": "Autosomal",
    "y-dna": "Y-DNA",
    "mtdna": "mtDNA",
}

# Repository types (arkivtyper)
REPOSITORY_TYPE_LABELS: dict[str, str] = {
    "archive": "Arkiv",
    "library": "Bibliotek",
    "digital_archive": "Digitalt arkiv",
    "private_collection": "Privat samling",
    "church_archive": "Kyrkoarkiv",
    "museum": "Museum",
}

# Date precision labels
DATE_PRECISION_LABELS: dict[str, str] = {
    "day": "Dag",
    "month": "Månad",
    "year": "År",
    "approximate": "Ungefärlig",
}

# Source quality labels
SOURCE_QUALITY_LABELS: dict[str, str] = {
    "primary": "Primär",
    "secondary": "Sekundär",
    "tertiary": "Tertiär",
}

# Name type labels
NAME_TYPE_LABELS: dict[str, str] = {
    "birth": "Födelsenamn",
    "married": "Giftasnamn",
    "adopted": "Adoptivnamn",
    "alias": "Alias",
    "other": "Övrigt",
}


# ---------------------------------------------------------------------------
# 21.4 — Swedish date formatting (YYYY-MM-DD)
# ---------------------------------------------------------------------------


def format_date(d: Optional[date | datetime | str]) -> str:
    """Format a date according to Swedish convention (YYYY-MM-DD).

    Accepts date objects, datetime objects, or ISO 8601 strings.
    Returns the date in YYYY-MM-DD format.

    Args:
        d: A date, datetime, or ISO string to format. None returns empty string.

    Returns:
        Formatted date string in YYYY-MM-DD format, or empty string if None.

    Examples:
        >>> format_date(date(2024, 3, 15))
        '2024-03-15'
        >>> format_date("2024-03-15")
        '2024-03-15'
        >>> format_date("2024-03")
        '2024-03'
        >>> format_date(None)
        ''
    """
    if d is None:
        return ""

    if isinstance(d, datetime):
        return d.strftime("%Y-%m-%d")
    elif isinstance(d, date):
        return d.strftime("%Y-%m-%d")
    elif isinstance(d, str):
        # Already in ISO format (YYYY, YYYY-MM, or YYYY-MM-DD), return as-is
        return d
    return str(d)


def format_date_range(start: Optional[str], end: Optional[str]) -> str:
    """Format a date range in Swedish style.

    Args:
        start: Start date string (YYYY-MM-DD or partial).
        end: End date string (YYYY-MM-DD or partial).

    Returns:
        Formatted range string, e.g. "2020-01-01 – 2024-12-31".
    """
    start_str = format_date(start) if start else "?"
    end_str = format_date(end) if end else "?"
    return f"{start_str} \u2013 {end_str}"


# ---------------------------------------------------------------------------
# 21.4 — Swedish number formatting
# ---------------------------------------------------------------------------


def format_number(value: int | float, decimals: int = 0) -> str:
    """Format a number using Swedish conventions.

    Swedish number formatting uses:
    - Comma (,) as decimal separator
    - Non-breaking space as thousands separator

    Args:
        value: The numeric value to format.
        decimals: Number of decimal places (0 for integers).

    Returns:
        Formatted number string following Swedish conventions.

    Examples:
        >>> format_number(1234567)
        '1 234 567'
        >>> format_number(1234.5, decimals=2)
        '1 234,50'
        >>> format_number(0.5, decimals=1)
        '0,5'
        >>> format_number(1000000)
        '1 000 000'
    """
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return str(value)

    if decimals > 0:
        # Format with decimals
        formatted = f"{value:.{decimals}f}"
        integer_part, decimal_part = formatted.split(".")
    else:
        integer_part = str(int(round(value)))
        decimal_part = ""

    # Handle negative numbers
    negative = integer_part.startswith("-")
    if negative:
        integer_part = integer_part[1:]

    # Add space as thousands separator
    groups: list[str] = []
    while len(integer_part) > 3:
        groups.insert(0, integer_part[-3:])
        integer_part = integer_part[:-3]
    groups.insert(0, integer_part)

    # Use non-breaking space (\u00a0) as thousands separator
    result = "\u00a0".join(groups)

    # Add decimal part with comma separator
    if decimal_part:
        result += "," + decimal_part

    if negative:
        result = "-" + result

    return result


def format_percentage(value: float, decimals: int = 1) -> str:
    """Format a percentage value using Swedish conventions.

    Args:
        value: The percentage value (e.g. 75.5 for 75.5%).
        decimals: Number of decimal places.

    Returns:
        Formatted percentage string (e.g. "75,5 %").
    """
    return f"{format_number(value, decimals)}\u00a0%"


def format_cm(value: float, decimals: int = 1) -> str:
    """Format a centiMorgan value using Swedish conventions.

    Args:
        value: The cM value.
        decimals: Number of decimal places.

    Returns:
        Formatted cM string (e.g. "125,4 cM").
    """
    return f"{format_number(value, decimals)}\u00a0cM"


# ---------------------------------------------------------------------------
# Reverse lookups (Swedish label → internal key)
# ---------------------------------------------------------------------------


def source_type_from_label(label: str) -> Optional[str]:
    """Get internal source type key from Swedish display label.

    Args:
        label: The Swedish display label.

    Returns:
        The internal key, or None if not found.
    """
    reverse = {v: k for k, v in SOURCE_TYPE_LABELS.items()}
    return reverse.get(label)


def place_type_from_label(label: str) -> Optional[str]:
    """Get internal place type key from Swedish display label.

    Args:
        label: The Swedish display label.

    Returns:
        The internal key, or None if not found.
    """
    reverse = {v: k for k, v in PLACE_TYPE_LABELS.items()}
    return reverse.get(label)


def event_type_from_label(label: str) -> Optional[str]:
    """Get internal event type key from Swedish display label.

    Args:
        label: The Swedish display label.

    Returns:
        The internal key, or None if not found.
    """
    reverse = {v: k for k, v in EVENT_TYPE_LABELS.items()}
    return reverse.get(label)


# ---------------------------------------------------------------------------
# Utility: get label with fallback
# ---------------------------------------------------------------------------


def get_event_type_label(event_type: str) -> str:
    """Get the Swedish label for an event type, with fallback to the key.

    Args:
        event_type: The internal event type key.

    Returns:
        Swedish display label, or the key itself if not mapped.
    """
    return EVENT_TYPE_LABELS.get(event_type, event_type)


def get_source_type_label(source_type: str) -> str:
    """Get the Swedish label for a source type, with fallback to the key.

    Args:
        source_type: The internal source type key.

    Returns:
        Swedish display label, or the key itself if not mapped.
    """
    return SOURCE_TYPE_LABELS.get(source_type, source_type)


def get_place_type_label(place_type: str) -> str:
    """Get the Swedish label for a place type, with fallback to the key.

    Args:
        place_type: The internal place type key.

    Returns:
        Swedish display label, or the key itself if not mapped.
    """
    return PLACE_TYPE_LABELS.get(place_type, place_type)


def get_relationship_label(role: str) -> str:
    """Get the Swedish label for a relationship role, with fallback to the key.

    Args:
        role: The internal relationship role key.

    Returns:
        Swedish display label, or the key itself if not mapped.
    """
    return RELATIONSHIP_LABELS.get(role, role)


def get_parentage_type_label(parentage_type: str) -> str:
    """Get the Swedish label for a parentage type, with fallback to the key.

    Args:
        parentage_type: The internal parentage type key.

    Returns:
        Swedish display label, or the key itself if not mapped.
    """
    return PARENTAGE_TYPE_LABELS.get(parentage_type, parentage_type)


def get_media_type_label(media_type: str) -> str:
    """Get the Swedish label for a media type, with fallback to the key.

    Args:
        media_type: The internal media type key.

    Returns:
        Swedish display label, or the key itself if not mapped.
    """
    return MEDIA_TYPE_LABELS.get(media_type, media_type)


def get_sex_label(sex: str) -> str:
    """Get the Swedish label for a sex value, with fallback to the key.

    Args:
        sex: The internal sex value (M, F, X, U).

    Returns:
        Swedish display label, or the key itself if not mapped.
    """
    return SEX_LABELS.get(sex, sex)
