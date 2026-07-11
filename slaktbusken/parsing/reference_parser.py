"""Reference parser for Swedish genealogy archive sources.

Parses pasted or imported reference strings from Arkiv Digital and Rötter.se
into structured source data (ParsedReference).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedReference:
    """Result of parsing a reference string."""

    leverantor_name: str
    kalltyp_name: str
    title: str
    reference_text: str
    structured_fields: dict[str, Optional[str | int]]
    arkivreferens: str = ""


# Mapping from church book series codes to Källtyp names.
CHURCH_BOOK_SERIES_LABELS: dict[str, str] = {
    "AI": "Husförhörslängd",
    "AII": "Husförhörslängd",
    "A": "Husförhörslängd",
    "CI": "Födelse- och dopbok",
    "CII": "Födelse- och dopbok",
    "C": "Födelse- och dopbok",
    "EI": "Lysnings- och vigselbok",
    "EII": "Lysnings- och vigselbok",
    "E": "Lysnings- och vigselbok",
    "FI": "Död- och begravningsbok",
    "FII": "Död- och begravningsbok",
    "F": "Död- och begravningsbok",
    "BI": "Inflyttningslängd",
    "BII": "Utflyttningslängd",
    "B": "In- och Utflyttningslängd",
    "HIIIa": "Mantalslängd",
    "D": "Konfirmationsbok",
}



# Full pattern regex:
# {parish} ({county_code}) {series}:{volume} ({years}) Bild {image} / sid {page} (AID: {aid_ref}, NAD: {nad_ref})
_AD_FULL_PATTERN = re.compile(
    r"^(?P<parish>.+?)\s+"
    r"\((?P<county_code>[^)]+)\)\s+"
    r"(?P<series>[A-Za-z]+)\:(?P<volume>[^\s]+)\s+"
    r"\((?P<years>[^)]+)\)\s+"
    r"Bild\s+(?P<image>\d+)\s*/\s*sid\s+(?P<page>\d+)\s+"
    r"\(AID:\s*(?P<aid_ref>[^,]+),\s*NAD:\s*(?P<nad_ref>[^)]+)\)$"
)

# Short pattern regex:
# {description} ({year}) Bild {image} / sid {page} (AID: {aid_ref})
_AD_SHORT_PATTERN = re.compile(
    r"^(?P<description>.+?)\s+"
    r"\((?P<year>\d{4})\)\s+"
    r"Bild\s+(?P<image>\d+)\s*/\s*sid\s+(?P<page>\d+)\s+"
    r"\(AID:\s*(?P<aid_ref>[^)]+)\)$"
)


def parse_arkiv_digital(text: str) -> Optional[ParsedReference]:
    """Parse Arkiv Digital reference patterns.

    Handles:
    1. Full pattern: {parish} ({county}) {series}:{volume} ({years}) Bild {image} / sid {page} (AID: {aid}, NAD: {nad})
    2. Short pattern: {description} ({year}) Bild {image} / sid {page} (AID: {aid})
    3. Census pattern: rX.pXXXXX

    Returns None if no pattern matches.
    """
    # Try full pattern first
    m = _AD_FULL_PATTERN.match(text)
    if m:
        parish = m.group("parish").strip()
        county_code = m.group("county_code").strip()
        series = m.group("series").strip()
        volume = m.group("volume").strip()
        years = m.group("years").strip()
        image = m.group("image").strip()
        page = m.group("page").strip()
        aid_ref = m.group("aid_ref").strip()
        nad_ref = m.group("nad_ref").strip()

        kalltyp_name = CHURCH_BOOK_SERIES_LABELS.get(series, "Övrigt")
        title = f"{parish} {series}:{volume} Sida: {page}"

        return ParsedReference(
            leverantor_name="Arkiv Digital",
            kalltyp_name=kalltyp_name,
            title=title,
            reference_text=text,
            structured_fields={
                "parish": parish,
                "county_code": county_code,
                "series": series,
                "volume": volume,
                "years": years,
                "image": image,
                "page": page,
                "aid_ref": aid_ref,
                "nad_ref": nad_ref,
            },
        )

    # Try short pattern
    m = _AD_SHORT_PATTERN.match(text)
    if m:
        description = m.group("description").strip()
        year = m.group("year").strip()
        image = m.group("image").strip()
        page = m.group("page").strip()
        aid_ref = m.group("aid_ref").strip()

        title = f"{description} Sida: {page}"

        return ParsedReference(
            leverantor_name="Arkiv Digital",
            kalltyp_name="Övrigt",
            title=title,
            reference_text=text,
            structured_fields={
                "description": description,
                "year": year,
                "image": image,
                "page": page,
                "aid_ref": aid_ref,
            },
        )

    # Try census pattern
    result = parse_arkiv_digital_census(text)
    if result is not None:
        return result

    return None


# Census pattern regex: rX.pXXXXX (r followed by digits, dot, p followed by digits)
_AD_CENSUS_PATTERN = re.compile(r"^r(\d+)\.p(\d+)$")


def parse_arkiv_digital_census(text: str) -> Optional[ParsedReference]:
    """Parse Arkiv Digital census pattern (rX.pXXXXX).

    Matches references like "r5.p12345" which represent Folkräkning (census) records.

    Returns None if the text does not match the census pattern.
    """
    stripped = text.strip()
    m = _AD_CENSUS_PATTERN.match(stripped)
    if not m:
        return None

    matched_string = m.group(0)

    return ParsedReference(
        leverantor_name="Arkiv Digital",
        kalltyp_name="Folkräkning",
        title=matched_string,
        reference_text=text,
        structured_fields={"aid_ref": matched_string},
        arkivreferens=matched_string,
    )


def parse_rotter(text: str) -> Optional[ParsedReference]:
    """Parse Rötter.se reference patterns.

    Handles (checked in priority order):
    1. SDB identifier: "SDB{single_digit}_{one_or_more_digits}"
    2. Sveriges dödbok webb with record_id: "Sveriges dödbok webb - {record_id}"
    3. General Sveriges dödbok webb: contains "Sveriges dödbok webb" (case-insensitive)

    Returns None if no pattern matches.
    """
    # Pattern 1: SDB identifier (e.g., "SDB7_12345")
    sdb_match = re.search(r"SDB\d_\d+", text)
    if sdb_match:
        sdb_id = sdb_match.group(0)
        return ParsedReference(
            leverantor_name="Rötter.se",
            kalltyp_name="Sveriges Dödbok Webb",
            title=sdb_id,
            reference_text=text,
            structured_fields={},
            arkivreferens=sdb_id,
        )

    # Pattern 2: "Sveriges dödbok webb - {record_id}" (case-insensitive prefix)
    record_match = re.match(r"(?i)sveriges dödbok webb - (.+)", text)
    if record_match:
        record_id = record_match.group(1).strip()
        return ParsedReference(
            leverantor_name="Rötter.se",
            kalltyp_name="Sveriges Dödbok Webb",
            title="Sveriges Dödbok Webb",
            reference_text=text,
            structured_fields={"record_id": record_id},
            arkivreferens=record_id,
        )

    # Pattern 3: Contains "Sveriges dödbok webb" (case-insensitive)
    if re.search(r"(?i)sveriges dödbok webb", text):
        return ParsedReference(
            leverantor_name="Rötter.se",
            kalltyp_name="Sveriges Dödbok Webb",
            title="Sveriges Dödbok Webb",
            reference_text=text,
            structured_fields={},
            arkivreferens="",
        )

    return None


def parse_reference(text: str) -> Optional[ParsedReference]:
    """Attempt to parse a reference string against all known patterns.

    Delegates to sub-parsers in order:
    1. Arkiv Digital patterns
    2. Rötter.se patterns

    Returns None if no pattern matches.
    """
    text = text.strip()
    if not text:
        return None

    # Try each sub-parser in order, return first match
    result = parse_arkiv_digital(text)
    if result is not None:
        return result

    result = parse_arkiv_digital_census(text)
    if result is not None:
        return result

    result = parse_rotter(text)
    if result is not None:
        return result

    return None


def parse_multi_line(text: str) -> list[ParsedReference]:
    """Parse a multi-line reference string, one reference per line.

    Splits the input on newline characters, attempts to parse each line
    individually, and returns all successfully parsed references.
    """
    results: list[ParsedReference] = []
    for line in text.splitlines():
        parsed = parse_reference(line)
        if parsed is not None:
            results.append(parsed)
    return results
