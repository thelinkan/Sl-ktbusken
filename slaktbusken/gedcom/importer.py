"""GEDCOM file importer — main orchestration module.

Reads a GEDCOM file, parses it, and translates the records into App_JSON
entities (Person, Family, Event, Place, Source, Repository). Supports both
first-time import and re-import (updating existing records via translation
files).

The importer delegates to the parser for GEDCOM line parsing and to the
translation modules for mapping GEDCOM data to App_JSON format. It handles:

- Source extraction with ArkivDigital repository detection
- Place mapping on demand (when PLAC values are encountered)
- Person extraction with birth/death/burial/baptism events
- Family extraction with marriage/divorce events and ParentChildLinks
- Warning accumulation for unsupported or malformed records (Swedish)
- Translation file updates for re-import support

Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 11.7, 22.3
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from slaktbusken.gedcom.parser import GedcomLine, GedcomParseError, parse_gedcom
from slaktbusken.gedcom.translation import TranslationManager
from slaktbusken.gedcom.translation.models import (
    DiffCategory,
    GedcomFamily,
    GedcomPerson,
    GedcomSource,
    PersonDiffEntry,
)
from slaktbusken.gedcom.translation.person_mapping import (
    classify_persons,
    compute_composite_key_hash,
)
from slaktbusken.gedcom.translation.source_translation import detect_arkiv_digital
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.id_generator import IDGenerator
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.source import Repository, RepositoryRef, Source
from slaktbusken.services.foster_sync import (
    _DERIVED_PARENTAGE_TYPES,
    _PLACEMENT_END as _PLACEMENT_END_TYPES,
    _PLACEMENT_START as _PLACEMENT_START_ROLES,
    backfill_orphan_placement_events,
    sync_parentage_links,
)
from slaktbusken.persistence.translation_io import (
    FamilyMapping,
    PersonMapping,
    PlaceMapping,
    SourceMapping,
    TranslationData,
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ImportResult:
    """Result of a GEDCOM import operation.

    Attributes:
        persons_added: Number of new persons created.
        persons_updated: Number of existing persons updated during re-import.
        families_added: Number of new families created.
        events_added: Number of new events created.
        sources_added: Number of new sources created.
        places_added: Number of new places created.
        warnings: Swedish-language warnings for skipped/problematic records.
    """

    persons_added: int = 0
    persons_updated: int = 0
    families_added: int = 0
    families_updated: int = 0
    events_added: int = 0
    sources_added: int = 0
    places_added: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass
class WarningEntry:
    """Structured warning entry for GEDCOM import diagnostics.

    All fields except ``reason`` are optional. When formatted as a string,
    only non-None fields are included.

    Attributes:
        gedcom_file: Name of the GEDCOM file being imported.
        record_xref: The @I..@ or @F..@ xref of the related record.
        person_or_family_name: Person or family name if available.
        event_type: Event type if applicable.
        raw_value: The raw GEDCOM value/tag that triggered the warning.
        reason: The reason for the warning (Swedish).
        action_taken: What was done (e.g. "ignorerades").
    """

    gedcom_file: Optional[str] = None
    record_xref: Optional[str] = None
    person_or_family_name: Optional[str] = None
    event_type: Optional[str] = None
    raw_value: Optional[str] = None
    reason: str = ""
    action_taken: Optional[str] = None

    def __str__(self) -> str:
        """Format as a human-readable warning string with all available fields."""
        parts: list[str] = []

        if self.record_xref:
            parts.append(f"[{self.record_xref}]")

        if self.person_or_family_name:
            parts.append(self.person_or_family_name)

        if self.event_type:
            parts.append(self.event_type)

        if self.raw_value:
            parts.append(f"Råvärde: '{self.raw_value}'")

        if self.reason:
            parts.append(f"Orsak: {self.reason}")

        if self.action_taken:
            parts.append(f"Åtgärd: {self.action_taken}")

        if self.gedcom_file:
            parts.append(f"Fil: {self.gedcom_file}")

        return " | ".join(parts) if parts else self.reason


# ---------------------------------------------------------------------------
# GEDCOM month mapping
# ---------------------------------------------------------------------------

_GEDCOM_MONTHS: dict[str, str] = {
    "JAN": "01",
    "FEB": "02",
    "MAR": "03",
    "APR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AUG": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DEC": "12",
}

# Tags for individual events we recognize
_INDI_EVENT_TAGS: dict[str, str] = {
    "BIRT": "birth",
    "DEAT": "death",
    "BURI": "burial",
    "BAPM": "baptism",
    "CHR": "baptism",
    "EMIG": "emigration",
    "IMMI": "immigration",
    "CENS": "census",
    "RETI": "retirement",
    "GRAD": "graduation",
    "CREM": "cremation",
    "CONF": "confirmation",
    "WILL": "will",
    "ADOP": "adoption",
    "BLES": "blessing",
    "FCOM": "first_communion",
}

# Tags for family events
_FAM_EVENT_TAGS: dict[str, str] = {
    "MARR": "marriage",
    "DIV": "divorce",
    "ENGA": "engagement",
    "DIVF": "divorce_filed",
}

# Level-0 tags we recognize and do not warn about
_SUPPORTED_LEVEL0_TAGS = frozenset(
    {"HEAD", "INDI", "FAM", "SOUR", "TRLR", "SUBM", "NOTE", "REPO"}
)


# ---------------------------------------------------------------------------
# GEDCOM pedigree (PEDI) mapping
# ---------------------------------------------------------------------------

# Maps a GEDCOM 5.5.1 pedigree value (lowercased) to our internal
# ParentChildLink.parentage_type. Standard PEDI values are
# birth/adopted/foster/sealing; only "foster" and "adopted" denote a
# non-biological link in our model. Note the GEDCOM value is "adopted"
# while our internal type is "adoptive". Anything else (birth, sealing,
# an unrecognised value, or no PEDI at all) maps to "biological".
_PEDIGREE_TO_PARENTAGE_TYPE: dict[str, str] = {
    "foster": "foster",
    "adopted": "adoptive",
}


def _pedigree_to_parentage_type(pedigree: Optional[str]) -> str:
    """Map a GEDCOM PEDI value to an internal parentage_type.

    Args:
        pedigree: The raw PEDI value (any case), or None when absent.

    Returns:
        ``"foster"`` for ``foster``, ``"adoptive"`` for ``adopted`` (case
        insensitive), and ``"biological"`` for any other value or None.
    """
    if not pedigree:
        return "biological"
    return _PEDIGREE_TO_PARENTAGE_TYPE.get(pedigree.strip().lower(), "biological")


def _extract_famc_pedigree(record: GedcomLine) -> dict[str, str]:
    """Extract an INDI record's FAMC → PEDI pedigree map.

    In GEDCOM 5.5.1 the pedigree tag lives under the individual's ``FAMC``
    cross-reference, not under the family's ``CHIL``::

        0 @I1@ INDI
        1 FAMC @F1@
        2 PEDI adopted

    Args:
        record: A level-0 GedcomLine with tag "INDI".

    Returns:
        A dict mapping each family xref (e.g. ``"@F1@"``) to its lowercased
        PEDI value. Only FAMC links that carry a PEDI value are included.
    """
    pedigrees: dict[str, str] = {}
    for famc in _get_children(record, "FAMC"):
        family_xref = famc.value
        if not family_xref:
            continue
        pedi_val = _get_child_value(famc, "PEDI")
        if pedi_val and pedi_val.strip():
            pedigrees[family_xref] = pedi_val.strip().lower()
    return pedigrees


# ---------------------------------------------------------------------------
# GEDCOM date parsing
# ---------------------------------------------------------------------------

# Date pattern: optional prefix (ABT/BEF/AFT/EST/CAL) + date components
_DATE_PREFIX_RE = re.compile(
    r"^(ABT|BEF|AFT|EST|CAL|FROM|TO|BET)?\s*(.+)$", re.IGNORECASE
)
_DATE_FULL_RE = re.compile(
    r"^(\d{1,2})\s+([A-Z]{3})\s+(\d{4})$", re.IGNORECASE
)
_DATE_MONTH_YEAR_RE = re.compile(r"^([A-Z]{3})\s+(\d{4})$", re.IGNORECASE)
_DATE_YEAR_RE = re.compile(r"^(\d{4})$")


def parse_gedcom_date(raw_date: str) -> Optional[DateValue]:
    """Parse a GEDCOM date string into a DateValue.

    Handles formats:
        - "1 JAN 1900" → day precision
        - "JAN 1900" → month precision
        - "1900" → year precision
        - "ABT 1900", "BEF 1900", "AFT 1900" → approximate precision

    Args:
        raw_date: The raw GEDCOM DATE value string.

    Returns:
        A DateValue instance, or None if the date cannot be parsed.
    """
    if not raw_date or not raw_date.strip():
        return None

    stripped = raw_date.strip()

    # Extract prefix (ABT, BEF, AFT, etc.)
    prefix_match = _DATE_PREFIX_RE.match(stripped)
    if not prefix_match:
        return None

    prefix = prefix_match.group(1)
    date_part = prefix_match.group(2).strip()

    is_approximate = prefix is not None and prefix.upper() in (
        "ABT", "BEF", "AFT", "EST", "CAL",
    )

    # Try full date: "1 JAN 1900"
    full_match = _DATE_FULL_RE.match(date_part)
    if full_match:
        day = int(full_match.group(1))
        month_abbr = full_match.group(2).upper()
        year = full_match.group(3)
        month = _GEDCOM_MONTHS.get(month_abbr)
        if month:
            value = f"{year}-{month}-{day:02d}"
            precision = "approximate" if is_approximate else "day"
            return DateValue(value=value, precision=precision)

    # Try month-year: "JAN 1900"
    my_match = _DATE_MONTH_YEAR_RE.match(date_part)
    if my_match:
        month_abbr = my_match.group(1).upper()
        year = my_match.group(2)
        month = _GEDCOM_MONTHS.get(month_abbr)
        if month:
            value = f"{year}-{month}"
            precision = "approximate" if is_approximate else "month"
            return DateValue(value=value, precision=precision)

    # Try year only: "1900"
    year_match = _DATE_YEAR_RE.match(date_part)
    if year_match:
        value = year_match.group(1)
        precision = "approximate" if is_approximate else "year"
        return DateValue(value=value, precision=precision)

    return None


# ---------------------------------------------------------------------------
# GEDCOM RESI date range parsing
# ---------------------------------------------------------------------------

# Regex patterns for RESI date forms
_FROM_TO_RE = re.compile(
    r"^FROM\s+(.+?)\s+TO\s+(.+)$", re.IGNORECASE
)
_FROM_ONLY_RE = re.compile(r"^FROM\s+(.+)$", re.IGNORECASE)
_TO_ONLY_RE = re.compile(r"^TO\s+(.+)$", re.IGNORECASE)
_BET_AND_RE = re.compile(
    r"^BET\s+(.+?)\s+AND\s+(.+)$", re.IGNORECASE
)


def _parse_single_gedcom_date(raw: str) -> tuple[Optional[str], Optional[str]]:
    """Parse a single GEDCOM date component into (iso_value, precision).

    Returns (None, None) if the date cannot be interpreted.
    """
    stripped = raw.strip()
    if not stripped:
        return None, None

    # Check for approximate prefix
    approx_match = re.match(r"^(ABT|BEF|AFT|EST|CAL)\s+(.+)$", stripped, re.IGNORECASE)
    is_approximate = approx_match is not None
    date_part = approx_match.group(2).strip() if approx_match else stripped

    # Full date: "1 JAN 1900"
    full_match = _DATE_FULL_RE.match(date_part)
    if full_match:
        day = int(full_match.group(1))
        month_abbr = full_match.group(2).upper()
        year = full_match.group(3)
        month = _GEDCOM_MONTHS.get(month_abbr)
        if month:
            value = f"{year}-{month}-{day:02d}"
            precision = "approximate" if is_approximate else "day"
            return value, precision

    # Month-year: "JAN 1900"
    my_match = _DATE_MONTH_YEAR_RE.match(date_part)
    if my_match:
        month_abbr = my_match.group(1).upper()
        year = my_match.group(2)
        month = _GEDCOM_MONTHS.get(month_abbr)
        if month:
            value = f"{year}-{month}"
            precision = "approximate" if is_approximate else "month"
            return value, precision

    # Year only: "1900"
    year_match = _DATE_YEAR_RE.match(date_part)
    if year_match:
        value = year_match.group(1)
        precision = "approximate" if is_approximate else "year"
        return value, precision

    return None, None


@dataclass
class _ResiDateResult:
    """Result of parsing a RESI DATE line into endpoint data."""

    start_earliest: Optional[str] = None
    start_latest: Optional[str] = None
    start_precision: Optional[str] = None
    end_earliest: Optional[str] = None
    end_latest: Optional[str] = None
    end_precision: Optional[str] = None
    interpretable: bool = False


def _parse_resi_date(raw_date: Optional[str]) -> _ResiDateResult:
    """Parse a RESI DATE line into endpoint data for a ResidenceFact.

    Handles:
    - "FROM x TO y" → start.latest = x, end.earliest = y (core bounds)
    - "BET x AND y" → start.earliest = x, start.latest = y, end unknown
    - Plain date → start.latest = date, end.earliest = date (both core bounds)
    - Missing/uninterpretable → both endpoints unknown

    Returns a _ResiDateResult with the parsed values.
    """
    result = _ResiDateResult()

    if not raw_date or not raw_date.strip():
        return result

    stripped = raw_date.strip()

    # FROM x TO y → sets start.latest and end.earliest (core bounds)
    m = _FROM_TO_RE.match(stripped)
    if m:
        from_val, from_prec = _parse_single_gedcom_date(m.group(1))
        to_val, to_prec = _parse_single_gedcom_date(m.group(2))
        if from_val is not None and to_val is not None:
            result.start_latest = from_val
            result.start_precision = from_prec
            result.end_earliest = to_val
            result.end_precision = to_prec
            result.interpretable = True
            return result
        # One side failed → fall through to uninterpretable
        return result

    # BET x AND y → start window (earliest=x, latest=y), end unknown
    m = _BET_AND_RE.match(stripped)
    if m:
        bet_val, bet_prec = _parse_single_gedcom_date(m.group(1))
        and_val, and_prec = _parse_single_gedcom_date(m.group(2))
        if bet_val is not None and and_val is not None:
            result.start_earliest = bet_val
            result.start_latest = and_val
            result.start_precision = and_prec
            result.interpretable = True
            return result
        return result

    # FROM x only (without TO) → start.latest = x, end unknown
    m = _FROM_ONLY_RE.match(stripped)
    if m:
        val, prec = _parse_single_gedcom_date(m.group(1))
        if val is not None:
            result.start_latest = val
            result.start_precision = prec
            result.interpretable = True
            return result
        return result

    # TO x only (without FROM) → end.earliest = x, start unknown
    m = _TO_ONLY_RE.match(stripped)
    if m:
        val, prec = _parse_single_gedcom_date(m.group(1))
        if val is not None:
            result.end_earliest = val
            result.end_precision = prec
            result.interpretable = True
            return result
        return result

    # Plain date → both core bounds set to the same value
    val, prec = _parse_single_gedcom_date(stripped)
    if val is not None:
        result.start_latest = val
        result.start_precision = prec
        result.end_earliest = val
        result.end_precision = prec
        result.interpretable = True
        return result

    return result


# ---------------------------------------------------------------------------
# GEDCOM placement (ADOP / Fosterhem EVEN) period parsing
# ---------------------------------------------------------------------------

# Matches the labelled note the exporter writes when a placement's end date
# cannot be expressed as a GEDCOM period (``2 NOTE Avslutades: <raw end>``),
# mirroring ``_placement_date_lines`` in ``gedcom/exporter.py``. The captured
# group is the raw end-date string.
_AVSLUTADES_NOTE_RE = re.compile(r"^Avslutades:\s*(.+)$", re.IGNORECASE)


def _date_value_from(raw: Optional[str]) -> Optional[DateValue]:
    """Parse a single GEDCOM date fragment into a DateValue, or None.

    A thin wrapper over :func:`_parse_single_gedcom_date` that returns a
    :class:`DateValue` when the fragment is interpretable, mirroring the
    ``(value, precision)`` contract used by the RESI date parser.
    """
    if not raw or not raw.strip():
        return None
    value, precision = _parse_single_gedcom_date(raw)
    if value is None:
        return None
    return DateValue(value=value, precision=precision or "day")


def _parse_placement_dates(
    event_record: GedcomLine,
) -> tuple[Optional[DateValue], Optional[DateValue]]:
    """Split a placement structure's end date from its start date.

    A Släktbusken-exported ``ADOP`` / ``EVEN TYPE Fosterhem`` structure carries
    the span of a placement on a single ``DATE`` line as a GEDCOM period
    (``FROM <start> TO <end>``, degrading to ``FROM <start>`` or ``TO <end>``),
    or — when the end cannot be expressed as a period — on a labelled
    ``NOTE`` (``Avslutades: <end>``). This mirrors ``_placement_date_lines`` in
    ``gedcom/exporter.py`` (Requirements 11.2e, 11.10).

    Returns ``(start_date, end_date)``:

    - ``FROM x TO y`` → start ``x``, end ``y``.
    - ``FROM x`` (period marker but no ``TO``) → start ``x``, end ``None``.
    - ``TO y`` → start ``None``, end ``y``.
    - a plain (non-period) ``DATE`` → start = that date, end ``None`` (left to
      :func:`parse_gedcom_date` by the caller; returned here for completeness).
    - no ``DATE`` period but an ``Avslutades:`` note → start from a plain
      ``DATE`` if present, end from the note.

    Either element is ``None`` when the corresponding bound is absent or
    uninterpretable. The end is only ever produced from a period's upper bound
    or the labelled note — never from a plain single date — so a placement
    without an end never fabricates one.
    """
    date_str = _get_child_value(event_record, "DATE")
    start_date: Optional[DateValue] = None
    end_date: Optional[DateValue] = None

    if date_str and date_str.strip():
        stripped = date_str.strip()

        m = _FROM_TO_RE.match(stripped)
        if m:
            start_date = _date_value_from(m.group(1))
            end_date = _date_value_from(m.group(2))
            return start_date, end_date

        m = _FROM_ONLY_RE.match(stripped)
        if m:
            start_date = _date_value_from(m.group(1))
            return start_date, None

        m = _TO_ONLY_RE.match(stripped)
        if m:
            end_date = _date_value_from(m.group(1))
            return None, end_date

        # Plain date (no period marker): the start is this date; no end.
        start_date = parse_gedcom_date(stripped)

    # No period upper bound: fall back to a labelled "Avslutades:" NOTE.
    if end_date is None:
        for note in _get_children(event_record, "NOTE"):
            if not note.value:
                continue
            note_match = _AVSLUTADES_NOTE_RE.match(note.value.strip())
            if note_match:
                end_date = _date_value_from(note_match.group(1))
                if end_date is not None:
                    break

    return start_date, end_date


# ---------------------------------------------------------------------------
# GEDCOM record extraction helpers
# ---------------------------------------------------------------------------


def _get_child_value(record: GedcomLine, tag: str) -> Optional[str]:
    """Get the value of a direct child with the given tag.

    Args:
        record: The parent GedcomLine record.
        tag: The tag to search for among children.

    Returns:
        The value of the first matching child, or None.
    """
    for child in record.children:
        if child.tag == tag:
            return child.value
    return None


def _get_child(record: GedcomLine, tag: str) -> Optional[GedcomLine]:
    """Get the first direct child with the given tag.

    Args:
        record: The parent GedcomLine record.
        tag: The tag to search for among children.

    Returns:
        The first matching child GedcomLine, or None.
    """
    for child in record.children:
        if child.tag == tag:
            return child
    return None


def _get_children(record: GedcomLine, tag: str) -> list[GedcomLine]:
    """Get all direct children with the given tag.

    Args:
        record: The parent GedcomLine record.
        tag: The tag to search for among children.

    Returns:
        A list of matching child GedcomLine nodes.
    """
    return [child for child in record.children if child.tag == tag]


def _extract_source_citations(record: GedcomLine) -> list[str]:
    """Extract SOUR citation cross-references from a record's children.

    Args:
        record: A GedcomLine with potential SOUR children.

    Returns:
        A list of GEDCOM source cross-reference IDs (e.g., ["@S1@"]).
    """
    citations: list[str] = []
    for child in record.children:
        if child.tag == "SOUR" and child.value:
            citations.append(child.value)
    return citations


def _extract_gedcom_person(record: GedcomLine) -> GedcomPerson:
    """Extract a GedcomPerson from a level-0 INDI record.

    Parses the name, sex, birth/death date and place, title, occupation,
    notes, and source citations from the GEDCOM record tree.

    Args:
        record: A level-0 GedcomLine with tag "INDI".

    Returns:
        A populated GedcomPerson dataclass.
    """
    xref_id = record.xref_id or ""
    given_name = ""
    surname = ""
    additional_names: list[tuple[str, str]] = []

    # Parse NAME tags
    name_records = _get_children(record, "NAME")
    for i, name_rec in enumerate(name_records):
        name_val = name_rec.value or ""
        parsed_given, parsed_surname = _parse_gedcom_name(name_val)

        # Check for GIVN/SURN children that override
        givn_child = _get_child_value(name_rec, "GIVN")
        surn_child = _get_child_value(name_rec, "SURN")
        if givn_child:
            parsed_given = givn_child.replace("/", "")
        if surn_child:
            parsed_surname = surn_child.replace("/", "")

        if i == 0:
            given_name = parsed_given
            surname = parsed_surname
        else:
            additional_names.append((parsed_given, parsed_surname))

    # Sex
    sex_val = _get_child_value(record, "SEX")
    sex = sex_val.strip().upper() if sex_val else "U"
    if sex not in ("M", "F", "X", "U"):
        sex = "U"

    # Birth
    birth_date: Optional[str] = None
    birth_place: Optional[str] = None
    birt_rec = _get_child(record, "BIRT")
    if birt_rec:
        birth_date = _get_child_value(birt_rec, "DATE")
        birth_place = _get_child_value(birt_rec, "PLAC")

    # Death
    death_date: Optional[str] = None
    death_place: Optional[str] = None
    deat_rec = _get_child(record, "DEAT")
    if deat_rec:
        death_date = _get_child_value(deat_rec, "DATE")
        death_place = _get_child_value(deat_rec, "PLAC")

    # Title and Occupation
    title = _get_child_value(record, "TITL")
    occupation = _get_child_value(record, "OCCU")

    # Notes
    notes_parts: list[str] = []
    for note_child in _get_children(record, "NOTE"):
        if note_child.value:
            notes_parts.append(note_child.value)
    notes = "\n".join(notes_parts)

    # Source citations on the person level
    source_citations = _extract_source_citations(record)

    return GedcomPerson(
        xref_id=xref_id,
        given_name=given_name,
        surname=surname,
        sex=sex,
        birth_date=birth_date,
        birth_place=birth_place,
        death_date=death_date,
        death_place=death_place,
        additional_names=additional_names,
        title=title,
        occupation=occupation,
        notes=notes,
        source_citations=source_citations,
        line_number=record.line_number,
    )


def _extract_gedcom_family(record: GedcomLine) -> GedcomFamily:
    """Extract a GedcomFamily from a level-0 FAM record.

    Parses partner cross-references (HUSB, WIFE), child cross-references
    (CHIL), marriage/divorce dates and places, and source citations.

    Args:
        record: A level-0 GedcomLine with tag "FAM".

    Returns:
        A populated GedcomFamily dataclass.
    """
    xref_id = record.xref_id or ""
    husb_xref = _get_child_value(record, "HUSB")
    wife_xref = _get_child_value(record, "WIFE")

    child_xrefs: list[str] = []
    for child_rec in _get_children(record, "CHIL"):
        if child_rec.value:
            child_xrefs.append(child_rec.value)

    # Marriage
    marriage_date: Optional[str] = None
    marriage_place: Optional[str] = None
    marr_rec = _get_child(record, "MARR")
    if marr_rec:
        marriage_date = _get_child_value(marr_rec, "DATE")
        marriage_place = _get_child_value(marr_rec, "PLAC")

    # Divorce
    divorce_date: Optional[str] = None
    div_rec = _get_child(record, "DIV")
    if div_rec:
        divorce_date = _get_child_value(div_rec, "DATE")

    source_citations = _extract_source_citations(record)

    return GedcomFamily(
        xref_id=xref_id,
        husb_xref=husb_xref,
        wife_xref=wife_xref,
        child_xrefs=child_xrefs,
        marriage_date=marriage_date,
        marriage_place=marriage_place,
        divorce_date=divorce_date,
        source_citations=source_citations,
        line_number=record.line_number,
    )


def _extract_gedcom_source(record: GedcomLine) -> GedcomSource:
    """Extract a GedcomSource from a level-0 SOUR record.

    Parses source title, author, publication, text, abbreviation, notes,
    and repository cross-reference from the GEDCOM record tree.

    Args:
        record: A level-0 GedcomLine with tag "SOUR".

    Returns:
        A populated GedcomSource dataclass.
    """
    xref_id = record.xref_id or ""
    title = _get_child_value(record, "TITL") or ""
    author = _get_child_value(record, "AUTH")
    publication = _get_child_value(record, "PUBL")
    abbreviation = _get_child_value(record, "ABBR")

    # TEXT may be nested under DATA or directly under SOUR
    text: Optional[str] = None
    data_rec = _get_child(record, "DATA")
    if data_rec:
        text = _get_child_value(data_rec, "TEXT")
    if not text:
        text = _get_child_value(record, "TEXT")

    # Repository reference
    repository_xref: Optional[str] = None
    call_number: Optional[str] = None
    repo_rec = _get_child(record, "REPO")
    if repo_rec:
        repository_xref = repo_rec.value
        call_number = _get_child_value(repo_rec, "CALN")

    # Notes
    notes_parts: list[str] = []
    for note_child in _get_children(record, "NOTE"):
        if note_child.value:
            notes_parts.append(note_child.value)
    notes = "\n".join(notes_parts)

    return GedcomSource(
        xref_id=xref_id,
        title=title,
        author=author,
        publication=publication,
        repository_xref=repository_xref,
        call_number=call_number,
        text=text,
        abbreviation=abbreviation,
        notes=notes,
        line_number=record.line_number,
    )


def _parse_gedcom_name(name_value: str) -> tuple[str, str]:
    """Parse a GEDCOM NAME value into (given_name, surname).

    GEDCOM names use the format "Given /Surname/" where the surname is
    enclosed in slashes. If no slashes are present, the entire value is
    treated as the given name. Any remaining slash characters are stripped
    from the output as a safety measure.

    Args:
        name_value: The raw NAME tag value string.

    Returns:
        A tuple of (given_name, surname).
    """
    # Pattern: "Given Names /Surname/"
    match = re.match(r"^(.*?)\s*/(.+?)/\s*(.*)$", name_value)
    if match:
        given_parts = match.group(1).strip()
        surname = match.group(2).strip()
        suffix = match.group(3).strip()
        if suffix:
            given_parts = f"{given_parts} {suffix}".strip()
        # Strip any remaining slashes
        given_parts = given_parts.replace("/", "")
        surname = surname.replace("/", "")
        return given_parts, surname

    # No surname delimiters — strip slashes and treat all as given name
    return name_value.strip().replace("/", ""), ""


def _parse_gedcom_coordinate(
    value: str, positive_prefix: str, negative_prefix: str
) -> Optional[float]:
    """Parse a GEDCOM coordinate string (LATI or LONG) into a float.

    GEDCOM uses prefix notation: "N59.8392" means +59.8392 latitude,
    "W12.3153" means -12.3153 longitude.

    Args:
        value: The raw coordinate string (e.g., "N59.8392", "E12.3153").
        positive_prefix: The prefix character for positive values ("N" or "E").
        negative_prefix: The prefix character for negative values ("S" or "W").

    Returns:
        The coordinate as a float, or None if parsing fails.
    """
    if not value:
        return None

    value = value.strip()
    if not value:
        return None

    prefix = value[0].upper()
    num_str = value[1:]

    try:
        num = float(num_str)
    except ValueError:
        return None

    if prefix == positive_prefix:
        return num
    elif prefix == negative_prefix:
        return -num
    else:
        # No recognized prefix — try parsing the whole string as a number
        try:
            return float(value)
        except ValueError:
            return None


def _is_event_derived_family(
    family: Family, placement_start_ids: set[str]
) -> bool:
    """True when a family is an event-derived placement family.

    A derived family is one whose ``event_ids`` records a live placement START
    event id. The post-import sync (Step 3d) builds exactly these for each
    imported/back-filled placement event, and they are the authoritative home
    of foster/adoptive links.
    """
    return any(event_id in placement_start_ids for event_id in family.event_ids)


def _reconcile_imported_placement_families(project: ProjectData) -> None:
    """Drop foster/adoptive links made redundant by event-derived families.

    After :func:`sync_parentage_links` runs on an import, every imported
    foster/adoptive (child, parent) pair is also represented on an event-derived
    family keyed by the placement event. An imported GEDCOM ``FAM`` family that
    originally carried those foster/adoptive links (from FAMC/PEDI) is left
    holding a now-redundant duplicate, because the sync deliberately does not
    reconcile such a family in place (that would destroy any biological links it
    also carries for its other children).

    This reconciliation removes, from every *non* event-derived family, each
    foster/adoptive link whose exact ``(child_id, parent_id, parentage_type)`` is
    already present on some event-derived family — so the event-derived family
    is the single source of truth (Requirement 11.9 "giving precedence to
    Placement_Events"). It:

    - never removes a biological link or any link whose parentage this service
      does not own;
    - never removes a foster/adoptive link unless an event-derived family
      already carries the identical pair, so no imported relationship vanishes
      (Requirement 11.9 "SHALL NOT delete any imported foster or adoptive
      relationship for which a Placement_Event exists or was back-filled");
    - after stripping links, drops any child from ``children`` (and any partner
      from ``partners``) of the imported family that no longer participates in
      any remaining link there, so the exporter does not emit a stray
      pedigree-less ``FAMC`` for a child whose only tie to the family was the
      relocated foster/adoptive link;
    - removes an imported family entirely only when stripping leaves it with no
      links and no children, so it carries no information of its own.

    Mutates ``project`` in place. Idempotent: a second run finds the links
    already relocated and changes nothing.
    """
    placement_start_ids = {
        event.id
        for event in project.events
        if event.type in _PLACEMENT_START_ROLES
    }

    derived_families = [
        family
        for family in project.families
        if _is_event_derived_family(family, placement_start_ids)
    ]

    # Every (child, parent, type) pair authoritatively held by a derived family.
    derived_pairs: set[tuple[str, Optional[str], str]] = set()
    for family in derived_families:
        for link in family.parent_child_links:
            if link.parentage_type in _DERIVED_PARENTAGE_TYPES:
                derived_pairs.add(
                    (link.child_id, link.parent_id, link.parentage_type)
                )

    surviving: list[Family] = []
    for family in project.families:
        if _is_event_derived_family(family, placement_start_ids):
            surviving.append(family)
            continue

        # Keep every link except a foster/adoptive one already represented on a
        # derived family. Biological and other links are always kept.
        kept_links = [
            link
            for link in family.parent_child_links
            if not (
                link.parentage_type in _DERIVED_PARENTAGE_TYPES
                and (link.child_id, link.parent_id, link.parentage_type)
                in derived_pairs
            )
        ]

        if len(kept_links) == len(family.parent_child_links):
            # Nothing redundant here; leave the family exactly as found.
            surviving.append(family)
            continue

        family.parent_child_links = kept_links

        # A child/parent that no longer appears in any remaining link of this
        # family is pruned so the exporter will not emit a stray FAMC/FAMS for a
        # relationship that now lives solely on the derived family.
        remaining_children = {link.child_id for link in kept_links}
        remaining_parents = {
            link.parent_id for link in kept_links if link.parent_id is not None
        }
        family.children = [
            child_id
            for child_id in family.children
            if child_id in remaining_children
        ]
        family.partners = [
            partner
            for partner in family.partners
            if partner.person_id in remaining_parents
        ]

        # Drop a family emptied of all links and children; it holds no data.
        if not family.parent_child_links and not family.children:
            continue
        surviving.append(family)

    project.families = surviving


# ---------------------------------------------------------------------------
# GEDCOMImporter class
# ---------------------------------------------------------------------------


class GEDCOMImporter:
    """Orchestrates GEDCOM file import into the App_JSON data model.

    Reads and parses a GEDCOM file, translates records into App_JSON
    entities (Person, Family, Event, Place, Source, Repository), and
    updates translation files to support re-import.

    Args:
        project_data: The existing ProjectData to import into. Modified
            in place during import.
        translation_dir: Path to the directory where translation JSON
            files are stored.
    """

    def __init__(self, project_data: ProjectData, translation_dir: Path) -> None:
        """Initialize the importer with project data and translation directory."""
        self._project_data = project_data
        self._translation_dir = translation_dir
        self._translation_mgr = TranslationManager(translation_dir)
        self._warnings: list[WarningEntry] = []
        self._gedcom_filename: Optional[str] = None

        # Collect all existing IDs for the ID generator
        existing_ids: set[str] = set()
        for p in project_data.persons:
            existing_ids.add(p.id)
        for f in project_data.families:
            existing_ids.add(f.id)
        for e in project_data.events:
            existing_ids.add(e.id)
        for r_fact in project_data.residences:
            existing_ids.add(r_fact.id)
        for pl in project_data.places:
            existing_ids.add(pl.id)
        for s in project_data.sources:
            existing_ids.add(s.id)
        for r in project_data.repositories:
            existing_ids.add(r.id)

        self._id_gen = IDGenerator(existing_ids)

        # Mapping from GEDCOM xref → App_JSON ID (built during import)
        self._source_xref_map: dict[str, str] = {}
        self._person_xref_map: dict[str, str] = {}
        self._family_xref_map: dict[str, str] = {}

        # FAMC/PEDI pedigree lookup keyed by (child xref, family xref) →
        # lowercased PEDI value. Populated from INDI records before families
        # are processed so family-link creation can set parentage_type.
        self._famc_pedigree: dict[tuple[str, str], str] = {}

        # Imported placement START events (ADOP → "adoption",
        # EVEN/TYPE Fosterhem → "foster_home") awaiting finalisation after the
        # families are built. Each entry records the created event's id, the
        # child's App_JSON person id, the subordinate FAMC family xref (or
        # None) the structure pointed at, and the end date extracted from the
        # structure's period upper bound or labelled "Avslutades:" NOTE (or
        # None when the placement has no end). Finalisation (task 10.3) rewrites
        # the child participant to the placement child role and adds the FAMC
        # family's partners as parent-role participants so the back-fill and the
        # Parentage_Sync_Service recognise the event as backing its Parent_Set
        # (Requirements 11.7, 11.7a); task 10.3a then reconstructs the paired
        # Placement_End_Event from the recorded end date (Requirement 11.10).
        self._imported_placement_events: list[
            tuple[str, str, Optional[str], Optional[DateValue]]
        ] = []

        # Place cache: GEDCOM place string → App_JSON place_id
        self._place_cache: dict[str, str] = {}

        # Translation data reference (set during import_file)
        self._translation_data: Optional[TranslationData] = None

        # Event deduplication: set of keys for existing events when updating
        # a person. Used by _create_event to skip duplicates.
        # Key format: (event_type, date_value_str_or_none, place_id_or_none)
        self._existing_event_keys: Optional[set[tuple[str, Optional[str], Optional[str]]]] = None

        # Counters
        self._persons_added = 0
        self._persons_updated = 0
        self._families_added = 0
        self._families_updated = 0
        self._events_added = 0
        self._sources_added = 0
        self._places_added = 0

    def import_file(self, gedcom_path: Path) -> ImportResult:
        """Import a GEDCOM file into the project.

        Reads the file, parses it, and translates all records into App_JSON
        entities. Updates the project_data in place and persists translation
        mappings.

        The import processes records in this order:
        1. Sources (needed by person/family events for source refs)
        2. Persons (INDI records → Person + Events)
        3. Families (FAM records → Family + Events + ParentChildLinks)

        Places are resolved on demand when encountered during person/family
        processing.

        Args:
            gedcom_path: Path to the GEDCOM file to import.

        Returns:
            An ImportResult with counts of created/updated entities and
            any warnings generated during import.

        Raises:
            GedcomParseError: If the file is not a valid GEDCOM file.
            FileNotFoundError: If the gedcom_path does not exist.
            UnicodeDecodeError: If the file cannot be decoded as UTF-8.
        """
        # Read the file with BOM handling
        text = self._read_gedcom_file(gedcom_path)

        # Store filename for structured warnings
        self._gedcom_filename = gedcom_path.name

        # Parse into tree
        parse_result = parse_gedcom(text)

        # Collect parser warnings
        for pw in parse_result.warnings:
            self._warnings.append(WarningEntry(
                gedcom_file=self._gedcom_filename,
                raw_value=pw.message,
                reason=pw.message,
            ))

        # Load existing translation data
        translation_data = self._translation_mgr.load_translations()
        self._translation_data = translation_data

        # Separate records by tag type
        indi_records: list[GedcomLine] = []
        fam_records: list[GedcomLine] = []
        sour_records: list[GedcomLine] = []

        # Track last-seen INDI context for unsupported tag warnings
        _last_indi_xref: Optional[str] = None
        _last_indi_name: Optional[str] = None

        for record in parse_result.records:
            tag = record.tag.upper()
            if tag == "INDI":
                indi_records.append(record)
                _last_indi_xref = record.xref_id
                _last_indi_name = _get_child_value(record, "NAME")
            elif tag == "FAM":
                fam_records.append(record)
            elif tag == "SOUR":
                sour_records.append(record)
            elif tag not in _SUPPORTED_LEVEL0_TAGS:
                # Use the record's own xref if available, otherwise
                # fall back to the last-seen INDI record's xref as context
                context_xref = record.xref_id or _last_indi_xref
                context_name = _last_indi_name
                # Clean up NAME value (remove slashes around surname)
                if context_name:
                    context_name = context_name.replace("/", "").strip()
                self._warnings.append(WarningEntry(
                    gedcom_file=self._gedcom_filename,
                    record_xref=context_xref,
                    person_or_family_name=context_name or None,
                    raw_value=record.tag,
                    reason=f"ej stödd GEDCOM-taggtyp '{record.tag}'",
                    action_taken="Ignorerades",
                ))

        # Step 1: Process sources
        self._process_sources(sour_records, translation_data)

        # Step 2: Process persons (pass fam_records for fingerprint matching)
        self._process_persons(indi_records, translation_data, fam_records)

        # Step 2b: Collect FAMC/PEDI pedigree so family-link creation can
        # set parentage_type (the pedigree lives under the child INDI's
        # FAMC, not under the family's CHIL).
        self._collect_famc_pedigree(indi_records)

        # Step 3: Process families
        self._process_families(fam_records, translation_data)

        # Step 3b: Finalise imported placement START events (ADOP / Fosterhem
        # EVEN). Now that the families exist, resolve each event's subordinate
        # FAMC to the Parent_Set it names and attach those parents in the
        # placement parent role, converting the child-only event into a real
        # backing placement event (Requirements 11.7, 11.7a).
        self._finalize_placement_events()

        # Step 3c: Back-fill a placement event for every imported foster/
        # adoptive link not already backed by an imported (or just-finalised)
        # placement event, so the post-import sync preserves it rather than
        # deleting it as an orphan (Requirements 11.6, 11.8). The same shared
        # helper is used by the on-load migration (task 3.2) so importer and
        # migration cannot diverge. Running the Parentage_Sync_Service itself is
        # task 10.4; the back-fill establishes the precondition it relies on.
        backfill_orphan_placement_events(self._project_data)

        # Step 3d: Run the Parentage_Sync_Service so the imported foster/
        # adoptive links agree with the imported and back-filled placement
        # events, with the events as the source of truth (Requirement 11.9).
        # Because Step 3c backed every imported orphan Parent_Set with an event
        # BEFORE this runs, the sync preserves every imported foster/adoptive
        # relationship rather than dropping it as an unbacked orphan.
        #
        # The sync keys a derived family off a placement event id in
        # ``Family.event_ids``. An imported GEDCOM ``FAM`` whose foster/adoptive
        # links came from FAMC/PEDI does not record a placement event id, so the
        # sync builds a SEPARATE derived family for the event (rather than
        # reconciling the GEDCOM family in place — doing the latter would
        # destroy any biological links the GEDCOM family also carries for its
        # other children). After the sync the authoritative foster/adoptive
        # links therefore live on the event-derived family, while the imported
        # GEDCOM family may still carry the same foster/adoptive links as a now
        # redundant copy. Step 3d's reconciliation removes those redundant
        # copies from the imported families so the event-derived family is the
        # single source of truth, without ever touching biological or other
        # links (Requirement 11.9 "giving precedence to Placement_Events").
        sync_parentage_links(self._project_data)
        _reconcile_imported_placement_families(self._project_data)

        # Save updated translation data
        self._translation_mgr.save_translations(translation_data)

        # Write diagnostic log to C:\Temp
        self._write_import_log(
            gedcom_path, indi_records, fam_records, sour_records
        )

        return ImportResult(
            persons_added=self._persons_added,
            persons_updated=self._persons_updated,
            families_added=self._families_added,
            families_updated=self._families_updated,
            events_added=self._events_added,
            sources_added=self._sources_added,
            places_added=self._places_added,
            warnings=[str(w) for w in self._warnings],
        )

    # ------------------------------------------------------------------
    # File reading
    # ------------------------------------------------------------------

    def _read_gedcom_file(self, path: Path) -> str:
        """Read a GEDCOM file as UTF-8 text, handling BOM.

        Tries UTF-8 with BOM (utf-8-sig) first, which also handles plain
        UTF-8. Falls back to latin-1 if UTF-8 decoding fails.

        Args:
            path: Path to the GEDCOM file.

        Returns:
            The file content as a string.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            return path.read_text(encoding="latin-1")

    def _write_import_log(
        self,
        gedcom_path: Path,
        indi_records: list[GedcomLine],
        fam_records: list[GedcomLine],
        sour_records: list[GedcomLine],
    ) -> None:
        """Write a diagnostic log file to C:\\Temp\\gedcom_import.log.

        Logs a summary of the import, all warnings, and details about
        INDI records that were NOT successfully imported (i.e., their
        xref_id is not in _person_xref_map after processing).

        Args:
            gedcom_path: The source GEDCOM file path.
            indi_records: All parsed INDI records.
            fam_records: All parsed FAM records.
            sour_records: All parsed SOUR records.
        """
        import datetime

        log_dir = Path(r"C:\Temp")
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return  # Can't create log dir — skip silently

        log_path = log_dir / "gedcom_import.log"
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("=" * 72 + "\n")
                f.write(f"GEDCOM Import Log — {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")
                f.write(f"Source file: {gedcom_path}\n")
                f.write("=" * 72 + "\n\n")

                # Summary
                f.write("SUMMARY\n")
                f.write("-" * 40 + "\n")
                f.write(f"INDI records in GEDCOM:  {len(indi_records)}\n")
                f.write(f"FAM records in GEDCOM:   {len(fam_records)}\n")
                f.write(f"SOUR records in GEDCOM:  {len(sour_records)}\n")
                f.write(f"Persons added:           {self._persons_added}\n")
                f.write(f"Persons updated:         {self._persons_updated}\n")
                f.write(f"Families added:          {self._families_added}\n")
                f.write(f"Families updated:        {self._families_updated}\n")
                f.write(f"Events added:            {self._events_added}\n")
                f.write(f"Sources added:           {self._sources_added}\n")
                f.write(f"Places added:            {self._places_added}\n")
                f.write(f"Warnings:                {len(self._warnings)}\n")

                total_persons_processed = self._persons_added + self._persons_updated
                missing_count = len(indi_records) - total_persons_processed
                f.write(f"\nPersons NOT imported:    {missing_count}\n\n")

                # Find INDI records that were NOT imported
                if missing_count > 0:
                    f.write("=" * 72 + "\n")
                    f.write("INDI RECORDS NOT IMPORTED\n")
                    f.write("=" * 72 + "\n\n")
                    for record in indi_records:
                        xref = record.xref_id or "(no xref)"
                        if xref not in self._person_xref_map:
                            f.write(f"Line {record.line_number}: {xref}\n")
                            # Try to extract some info for diagnostics
                            name_val = _get_child_value(record, "NAME") or "(no NAME tag)"
                            sex_val = _get_child_value(record, "SEX") or "(no SEX)"
                            f.write(f"  NAME: {name_val}\n")
                            f.write(f"  SEX:  {sex_val}\n")
                            # Show all child tags for this record
                            child_tags = [
                                f"{c.tag}={c.value or ''}" for c in record.children[:20]
                            ]
                            f.write(f"  Tags: {', '.join(child_tags)}\n")
                            f.write("\n")

                # All warnings
                if self._warnings:
                    f.write("=" * 72 + "\n")
                    f.write("ALL WARNINGS\n")
                    f.write("=" * 72 + "\n\n")
                    for i, warning in enumerate(self._warnings, 1):
                        f.write(f"  {i}. {str(warning)}\n")
                    f.write("\n")

                # Family records with unresolved partner/child references
                f.write("=" * 72 + "\n")
                f.write("FAMILY LINKAGE ISSUES\n")
                f.write("=" * 72 + "\n\n")
                linkage_issues = 0
                for record in fam_records:
                    xref = record.xref_id or "(no xref)"
                    issues: list[str] = []

                    husb_val = _get_child_value(record, "HUSB")
                    wife_val = _get_child_value(record, "WIFE")
                    if husb_val and husb_val not in self._person_xref_map:
                        issues.append(f"HUSB {husb_val} not in person map")
                    if wife_val and wife_val not in self._person_xref_map:
                        issues.append(f"WIFE {wife_val} not in person map")

                    for child_rec in _get_children(record, "CHIL"):
                        if child_rec.value and child_rec.value not in self._person_xref_map:
                            issues.append(f"CHIL {child_rec.value} not in person map")

                    if issues:
                        linkage_issues += 1
                        f.write(f"Line {record.line_number}: {xref}\n")
                        for issue in issues:
                            f.write(f"  - {issue}\n")
                        f.write("\n")

                if linkage_issues == 0:
                    f.write("  (no linkage issues found)\n\n")

                f.write("=" * 72 + "\n")
                f.write("END OF LOG\n")
                f.write("=" * 72 + "\n")
        except OSError:
            pass  # If we can't write the log, don't crash the import

    # ------------------------------------------------------------------
    # Source processing
    # ------------------------------------------------------------------

    def _process_sources(
        self,
        sour_records: list[GedcomLine],
        translation_data: TranslationData,
    ) -> None:
        """Process all SOUR records from the GEDCOM file.

        For each source record:
        1. Extract into GedcomSource
        2. Map to an existing or new App_JSON Source
        3. Handle ArkivDigital repository detection
        4. Update translation mappings

        Args:
            sour_records: Level-0 SOUR GedcomLine records.
            translation_data: Translation data to update with new mappings.
        """
        for record in sour_records:
            gedcom_source = _extract_gedcom_source(record)

            # Use translation manager to map (handles existing matching)
            source = self._translation_mgr.map_source(
                gedcom_source, self._project_data.sources,
                leverantorer=self._project_data.leverantorer,
                kalltyper=self._project_data.kalltyper,
            )

            # Check if this is a new source (not already in project)
            existing_source_ids = {s.id for s in self._project_data.sources}
            is_new = source.id not in existing_source_ids

            # ArkivDigital detection
            if detect_arkiv_digital(gedcom_source):
                self._attach_arkiv_digital_repository(source)

            if is_new:
                self._project_data.sources.append(source)
                self._sources_added += 1

            # Track xref → app_id mapping
            self._source_xref_map[gedcom_source.xref_id] = source.id

            # Update translation mapping if not already present
            existing_mapping = next(
                (m for m in translation_data.sources
                 if m.gedcom_id == gedcom_source.xref_id),
                None,
            )
            if existing_mapping is None:
                translation_data.sources.append(
                    SourceMapping(
                        gedcom_id=gedcom_source.xref_id,
                        app_id=source.id,
                        title=source.title,
                    )
                )

    def _attach_arkiv_digital_repository(self, source: Source) -> None:
        """Find or create an ArkivDigital Repository and attach it to a Source.

        If an ArkivDigital repository already exists in the project, reuses it.
        Otherwise, creates a new Repository with name="ArkivDigital" and
        type="digital_archive". Adds a RepositoryRef to the source.

        Args:
            source: The Source to attach the repository reference to.
        """
        # Find existing ArkivDigital repository
        arkiv_repo: Optional[Repository] = None
        for repo in self._project_data.repositories:
            if repo.name == "ArkivDigital" and repo.type == "digital_archive":
                arkiv_repo = repo
                break

        if arkiv_repo is None:
            # Create new ArkivDigital repository
            repo_id = self._id_gen.generate("repository")
            arkiv_repo = Repository(
                id=repo_id,
                name="ArkivDigital",
                type="digital_archive",
                web=["https://www.arkivdigital.se"],
            )
            self._project_data.repositories.append(arkiv_repo)

        # Attach RepositoryRef if not already attached
        already_attached = any(
            ref.repository_id == arkiv_repo.id for ref in source.repository_refs
        )
        if not already_attached:
            source.repository_refs.append(
                RepositoryRef(repository_id=arkiv_repo.id)
            )

    # ------------------------------------------------------------------
    # Person processing
    # ------------------------------------------------------------------

    def _process_persons(
        self,
        indi_records: list[GedcomLine],
        translation_data: TranslationData,
        fam_records: list[GedcomLine],
    ) -> None:
        """Process all INDI records from the GEDCOM file.

        Uses fingerprint-based classification (via classify_persons) to
        correctly identify persons even when GEDCOM xrefs are renumbered
        between exports. This prevents the event isolation bug where a
        new person (with a reused xref) would incorrectly match an
        existing person.

        For each person record:
        1. Extract into GedcomPerson
        2. Classify using fingerprints (composite_key_hash matching)
        3. Create or update Person record based on classification
        4. Create events (birth, death, baptism, burial, etc.)
        5. Update translation mappings

        Args:
            indi_records: Level-0 INDI GedcomLine records.
            translation_data: Translation data to update with new mappings.
            fam_records: Level-0 FAM GedcomLine records (needed for
                fingerprint computation in classify_persons).
        """
        # Extract all GedcomPerson and GedcomFamily objects for classification
        incoming_persons: list[GedcomPerson] = []
        person_records_by_xref: dict[str, GedcomLine] = {}
        for record in indi_records:
            try:
                gp = _extract_gedcom_person(record)
                incoming_persons.append(gp)
                person_records_by_xref[gp.xref_id] = record
            except Exception as exc:
                line_num = record.line_number if record else "?"
                self._warnings.append(WarningEntry(
                    gedcom_file=self._gedcom_filename,
                    record_xref=record.xref_id or "?",
                    person_or_family_name=_get_child_value(record, "NAME") or None,
                    raw_value=f"Rad {line_num}",
                    reason=f"Kunde inte importera person: {exc}",
                    action_taken="Hoppades över",
                ))

        families: list[GedcomFamily] = []
        for fam_rec in fam_records:
            try:
                families.append(_extract_gedcom_family(fam_rec))
            except Exception:
                pass  # Family extraction failures handled in _process_families

        # Build existing_fingerprints: app_id → composite_key_hash
        # Use stored fingerprints from translation mappings (these were
        # computed from GEDCOM raw values during previous imports and will
        # match incoming GEDCOM data format)
        existing_fingerprints: dict[str, str] = {}
        for mapping in translation_data.persons:
            if mapping.fingerprint:
                existing_fingerprints[mapping.app_id] = mapping.fingerprint

        # If no stored fingerprints (first re-import after upgrading),
        # fall back to computing from project data. This won't match
        # perfectly due to format differences (ISO dates vs GEDCOM dates,
        # leaf place names vs full PLAC strings) but is better than nothing.
        if not existing_fingerprints:
            for person in self._project_data.persons:
                given_name = ""
                surname = ""
                if person.names:
                    given_name = person.names[0].given or ""
                    surname = person.names[0].surname or ""

                # Find birth event for this person to get date and place
                birth_date: Optional[str] = None
                birth_place: Optional[str] = None
                for evt in self._project_data.events:
                    if evt.type == "birth":
                        for participant in evt.participants:
                            if participant.person_id == person.id:
                                birth_date = evt.date.value if evt.date else None
                                if evt.place and evt.place.place_id:
                                    # Look up the place name
                                    for pl in self._project_data.places:
                                        if pl.id == evt.place.place_id:
                                            birth_place = pl.name
                                            break
                                break
                        if birth_date is not None or birth_place is not None:
                            break

                fp_hash = compute_composite_key_hash(
                    given_name=given_name,
                    surname=surname,
                    birth_date=birth_date,
                    birth_place=birth_place,
                )
                existing_fingerprints[person.id] = fp_hash

        # Classify persons using fingerprint-based matching
        # Build name lookup for fallback matching when fingerprints change
        existing_names: dict[str, tuple[str, str]] = {}
        for person in self._project_data.persons:
            given = person.names[0].given or "" if person.names else ""
            surname = person.names[0].surname or "" if person.names else ""
            existing_names[person.id] = (given, surname)

        diff_report = classify_persons(
            incoming=incoming_persons,
            families=families,
            existing_mappings=translation_data.persons,
            existing_fingerprints=existing_fingerprints,
            existing_names=existing_names,
        )

        # Build lookup: xref_id → PersonDiffEntry
        diff_by_xref: dict[str, PersonDiffEntry] = {
            entry.gedcom_xref: entry for entry in diff_report.entries
            if entry.category != DiffCategory.MISSING
        }

        # Process each person according to classification
        for gedcom_person in incoming_persons:
            # Reset event-related state at the start of each INDI record
            # to prevent leakage between persons (Bug 3 fix)
            self._existing_event_keys = None

            record = person_records_by_xref.get(gedcom_person.xref_id)
            if record is None:
                continue

            try:
                diff_entry = diff_by_xref.get(gedcom_person.xref_id)

                if diff_entry is None or diff_entry.category == DiffCategory.NEW:
                    # New person — no match found via fingerprint
                    self._create_person(gedcom_person, record, translation_data)

                elif diff_entry.category in (
                    DiffCategory.UPDATED,
                    DiffCategory.UNCHANGED,
                ):
                    # Matched an existing person via fingerprint
                    app_id = diff_entry.app_id
                    if app_id is None:
                        # Shouldn't happen for UPDATED/UNCHANGED, but treat as new
                        self._create_person(gedcom_person, record, translation_data)
                        continue

                    # Build a PersonMapping with the correct app_id
                    # (from fingerprint match, NOT from xref lookup)
                    mapping = PersonMapping(
                        gedcom_id=gedcom_person.xref_id,
                        app_id=app_id,
                    )
                    self._update_person(gedcom_person, mapping, record)

                    # Update translation mapping to reflect new xref for this
                    # person (xref may have changed between exports)
                    fp_hash = compute_composite_key_hash(
                        given_name=gedcom_person.given_name,
                        surname=gedcom_person.surname,
                        birth_date=gedcom_person.birth_date,
                        birth_place=gedcom_person.birth_place,
                    )
                    self._update_translation_xref(
                        translation_data, app_id, gedcom_person.xref_id, fp_hash
                    )

                elif diff_entry.category == DiffCategory.UNCERTAIN:
                    # Uncertain match — treat as new to be safe
                    self._create_person(gedcom_person, record, translation_data)

                else:
                    # Fallback: treat as new
                    self._create_person(gedcom_person, record, translation_data)

            except Exception as exc:
                line_num = record.line_number if record else "?"
                self._warnings.append(WarningEntry(
                    gedcom_file=self._gedcom_filename,
                    record_xref=record.xref_id or "?",
                    person_or_family_name=_get_child_value(record, "NAME") or None,
                    raw_value=f"Rad {line_num}",
                    reason=f"Kunde inte importera person: {exc}",
                    action_taken="Hoppades över",
                ))

    def _update_translation_xref(
        self,
        translation_data: TranslationData,
        app_id: str,
        new_xref: str,
        fingerprint_hash: Optional[str] = None,
    ) -> None:
        """Update or add a translation mapping for a person's xref.

        When a person is matched via fingerprint but their xref has changed
        (due to renumbering in MinSläkt), we update the translation mapping
        so subsequent imports use the new xref.

        Args:
            translation_data: Translation data containing person mappings.
            app_id: The App_JSON person ID.
            new_xref: The new GEDCOM cross-reference ID.
            fingerprint_hash: Optional composite_key_hash to store.
        """
        # Check if there's already a mapping for this app_id
        for mapping in translation_data.persons:
            if mapping.app_id == app_id:
                mapping.gedcom_id = new_xref
                if fingerprint_hash:
                    mapping.fingerprint = fingerprint_hash
                return

        # No existing mapping — create one
        translation_data.persons.append(
            PersonMapping(
                gedcom_id=new_xref,
                app_id=app_id,
                fingerprint=fingerprint_hash,
            )
        )

    def _create_person(
        self,
        gedcom_person: GedcomPerson,
        record: GedcomLine,
        translation_data: TranslationData,
    ) -> None:
        """Create a new Person and associated events from GEDCOM data.

        Args:
            gedcom_person: The extracted GEDCOM person data.
            record: The original GedcomLine record (for event extraction).
            translation_data: Translation data to update with new mapping.
        """
        person_id = self._id_gen.generate("person")
        self._person_xref_map[gedcom_person.xref_id] = person_id

        # Build names list
        names: list[Name] = []
        if gedcom_person.given_name or gedcom_person.surname:
            names.append(
                Name(type="birth", given=gedcom_person.given_name, surname=gedcom_person.surname)
            )
        for given, surname in gedcom_person.additional_names:
            names.append(Name(type="other", given=given, surname=surname))

        if not names:
            names.append(Name(type="birth", given="", surname=""))

        person = Person(
            id=person_id,
            sex=gedcom_person.sex,
            names=names,
            notes=gedcom_person.notes,
            title=gedcom_person.title,
            occupation=gedcom_person.occupation,
        )
        self._project_data.persons.append(person)
        self._persons_added += 1

        # Create events for this person
        self._create_person_events(person_id, record)

        # Update translation mapping with composite_key_hash fingerprint
        # so future re-imports can match this person even if xref changes
        fp_hash = compute_composite_key_hash(
            given_name=gedcom_person.given_name,
            surname=gedcom_person.surname,
            birth_date=gedcom_person.birth_date,
            birth_place=gedcom_person.birth_place,
        )
        translation_data.persons.append(
            PersonMapping(
                gedcom_id=gedcom_person.xref_id,
                app_id=person_id,
                fingerprint=fp_hash,
            )
        )

    def _update_person(
        self,
        gedcom_person: GedcomPerson,
        mapping: PersonMapping,
        record: GedcomLine,
    ) -> None:
        """Update an existing Person with data from a GEDCOM re-import.

        Args:
            gedcom_person: The extracted GEDCOM person data.
            mapping: The existing PersonMapping with the App_JSON ID.
            record: The original GedcomLine record (for event extraction).
        """
        person_id = mapping.app_id
        self._person_xref_map[gedcom_person.xref_id] = person_id

        # Find existing person in project
        existing_person: Optional[Person] = None
        for p in self._project_data.persons:
            if p.id == person_id:
                existing_person = p
                break

        if existing_person is None:
            # Person was deleted since last import — treat as new
            # but keep the same ID for consistency
            names: list[Name] = []
            if gedcom_person.given_name or gedcom_person.surname:
                names.append(
                    Name(type="birth", given=gedcom_person.given_name, surname=gedcom_person.surname)
                )
            for given, surname in gedcom_person.additional_names:
                names.append(Name(type="other", given=given, surname=surname))
            if not names:
                names.append(Name(type="birth", given="", surname=""))

            person = Person(
                id=person_id,
                sex=gedcom_person.sex,
                names=names,
                notes=gedcom_person.notes,
                title=gedcom_person.title,
                occupation=gedcom_person.occupation,
            )
            self._project_data.persons.append(person)
            self._persons_added += 1
            self._create_person_events(person_id, record)
            return

        # Update existing person fields
        existing_person.sex = gedcom_person.sex
        names = []
        if gedcom_person.given_name or gedcom_person.surname:
            names.append(
                Name(type="birth", given=gedcom_person.given_name, surname=gedcom_person.surname)
            )
        for given, surname in gedcom_person.additional_names:
            names.append(Name(type="other", given=given, surname=surname))
        if not names:
            names.append(Name(type="birth", given="", surname=""))
        existing_person.names = names
        existing_person.notes = gedcom_person.notes
        existing_person.title = gedcom_person.title
        existing_person.occupation = gedcom_person.occupation
        self._persons_updated += 1

        # Event deduplication: build set of existing event keys for this person
        # so _create_event can skip duplicates during re-import
        existing_keys: set[tuple[str, Optional[str], Optional[str]]] = set()
        for evt in self._project_data.events:
            for participant in evt.participants:
                if participant.person_id == person_id:
                    date_val = evt.date.value if evt.date else None
                    place_id = evt.place.place_id if evt.place else None
                    existing_keys.add((evt.type, date_val, place_id))
                    break

        self._existing_event_keys = existing_keys
        try:
            self._create_person_events(person_id, record)
        finally:
            self._existing_event_keys = None

    def _create_person_events(self, person_id: str, record: GedcomLine) -> None:
        """Create events and residences for a person from GEDCOM event tags.

        Scans the INDI record's children for known event tags (BIRT, DEAT,
        BURI, BAPM, CHR, etc.) and creates Event records for each.
        Handles RESI tags as ResidenceFact entities (not events).
        Handles EVEN with TYPE Flytt as a flytt Event.

        Args:
            person_id: The App_JSON person ID to use as participant.
            record: The INDI GedcomLine record with event children.
        """
        for child in record.children:
            tag = child.tag.upper()
            if tag == "RESI":
                # RESI → ResidenceFact (Requirement 12.7, 12.8, 12.12, 12.13)
                self._create_residence(person_id, child)
            elif tag == "ADOP":
                # ADOP → an "adoption" placement START event. It carries the
                # child in the "subject" role for now and (when exported by us)
                # a subordinate FAMC pointing at the derived family for its
                # Parent_Set. Record it for finalisation once the families exist
                # so the adoptive parents can be attached (Requirements 11.7,
                # 11.7a). The child's DATE/PLAC are read by _create_event, so a
                # matching ADOP's date/place is preferred over a dateless
                # back-fill.
                event_id = self._create_event(
                    event_type="adoption",
                    event_record=child,
                    participant_id=person_id,
                    participant_role="subject",
                )
                if event_id is not None:
                    end_date = self._apply_placement_period(event_id, child)
                    self._imported_placement_events.append(
                        (
                            event_id,
                            person_id,
                            _get_child_value(child, "FAMC"),
                            end_date,
                        )
                    )
            elif tag in _INDI_EVENT_TAGS:
                event_type = _INDI_EVENT_TAGS[tag]
                self._create_event(
                    event_type=event_type,
                    event_record=child,
                    participant_id=person_id,
                    participant_role="subject",
                )
            elif tag == "EVEN":
                custom_type_name = _get_child_value(child, "TYPE")
                normalized_type = (
                    custom_type_name.strip().lower() if custom_type_name else ""
                )
                if normalized_type == "flytt":
                    # Flytt event (Requirement 18.16)
                    self._create_event(
                        event_type="flytt",
                        event_record=child,
                        participant_id=person_id,
                        participant_role="subject",
                    )
                elif normalized_type == "fosterhem":
                    # EVEN / TYPE Fosterhem → a "foster_home" placement START
                    # event, mirroring the ADOP handling above (Requirements
                    # 11.7, 11.7a). The exporter emits this structure for a
                    # Fosterhem event; parsing it here lets the back-fill prefer
                    # its DATE/PLAC/FAMC over a dateless fabrication.
                    event_id = self._create_event(
                        event_type="foster_home",
                        event_record=child,
                        participant_id=person_id,
                        participant_role="subject",
                    )
                    if event_id is not None:
                        end_date = self._apply_placement_period(event_id, child)
                        self._imported_placement_events.append(
                            (
                                event_id,
                                person_id,
                                _get_child_value(child, "FAMC"),
                                end_date,
                            )
                        )
                else:
                    # Generic individual event → custom_individual_event
                    self._create_event(
                        event_type="custom_individual_event",
                        event_record=child,
                        participant_id=person_id,
                        participant_role="subject",
                        custom_type_name=custom_type_name,
                    )

    def _create_residence(self, person_id: str, resi_record: GedcomLine) -> None:
        """Create a ResidenceFact from a GEDCOM RESI structure.

        Maps the DATE line according to the requirements:
        - FROM x TO y → start.latest = x, end.earliest = y
        - BET x AND y → start.earliest = x, start.latest = y, end unknown
        - Plain DATE → start.latest = end.earliest = date
        - Missing/uninterpretable DATE → both endpoints unknown + warning

        Resolves the PLAC value and derives Observations from SOUR lines.

        Args:
            person_id: The App_JSON person ID for the residence.
            resi_record: The RESI GedcomLine sub-record.
        """
        residence_id = self._id_gen.generate("residence")

        # Parse the DATE line
        date_str = _get_child_value(resi_record, "DATE")
        date_result = _parse_resi_date(date_str)

        # Log warning if date is present but uninterpretable
        if date_str and date_str.strip() and not date_result.interpretable:
            self._warnings.append(WarningEntry(
                gedcom_file=self._gedcom_filename,
                record_xref=None,
                person_or_family_name=None,
                raw_value=date_str,
                reason="Kunde inte tolka datumraden för RESI – boendet importerades utan period.",
                action_taken="Importerades utan period",
            ))

        # Build endpoints
        start = Endpoint(
            earliest=date_result.start_earliest,
            latest=date_result.start_latest,
            precision=date_result.start_precision,
        )
        end = Endpoint(
            earliest=date_result.end_earliest,
            latest=date_result.end_latest,
            precision=date_result.end_precision,
        )

        # Resolve place from PLAC line
        place_id = ""
        raw_place_value: Optional[str] = None
        plac_rec = _get_child(resi_record, "PLAC")
        if plac_rec:
            raw_place_value = plac_rec.value
            resolved_place_id = self._resolve_place_from_adpl(plac_rec)
            if resolved_place_id is None:
                place_str = plac_rec.value
                if place_str:
                    resolved_place_id = self._resolve_place(place_str)
            if resolved_place_id:
                place_id = resolved_place_id
                self._apply_coordinates(resolved_place_id, plac_rec)

        # Warn specifically when the residence has no usable place, so the
        # user can locate the offending RESI record. The generic validation
        # warning ("Boendet måste ange både person och plats") does not say
        # which field is missing nor which GEDCOM record it came from.
        if not place_id:
            person_xref = self._xref_for_person_id(person_id)
            person_name = self._display_name_for_person_id(person_id)
            if raw_place_value and raw_place_value.strip():
                reason = (
                    "RESI-platsen kunde inte matchas mot eller skapas som en "
                    "plats – boendet importerades utan plats."
                )
            elif plac_rec is not None:
                reason = (
                    "RESI-raden har en tom PLAC-tagg – boendet importerades "
                    "utan plats."
                )
            else:
                reason = (
                    "RESI-raden saknar PLAC-tagg – boendet importerades utan "
                    "plats."
                )
            self._warnings.append(WarningEntry(
                gedcom_file=self._gedcom_filename,
                record_xref=person_xref,
                person_or_family_name=person_name,
                event_type="RESI (Boende)",
                raw_value=raw_place_value if raw_place_value else None,
                reason=reason,
                action_taken="Importerades utan plats",
            ))

        # Derive Observations from SOUR lines
        observations: list[Observation] = []
        for sour_child in _get_children(resi_record, "SOUR"):
            if sour_child.value:
                source_id = self._source_xref_map.get(sour_child.value)
                if source_id:
                    observations.append(
                        Observation(
                            source_ref=SourceRef(source_id=source_id, quality="secondary"),
                        )
                    )

        residence = ResidenceFact(
            id=residence_id,
            person_id=person_id,
            place_id=place_id,
            start=start,
            end=end,
            observations=observations,
        )
        self._project_data.residences.append(residence)

    def _xref_for_person_id(self, person_id: str) -> Optional[str]:
        """Return the GEDCOM xref that maps to this App_JSON person id.

        Reverse lookup over ``_person_xref_map`` (xref → app id). Used only
        for diagnostics, so a missing entry simply yields ``None``.
        """
        for xref, app_id in self._person_xref_map.items():
            if app_id == person_id:
                return xref
        return None

    def _display_name_for_person_id(self, person_id: str) -> Optional[str]:
        """Return a human-readable name for a person, for warning messages.

        Uses the person's first name entry ("Efternamn, Förnamn"). Returns
        ``None`` when the person or a usable name cannot be found.
        """
        for person in self._project_data.persons:
            if person.id != person_id:
                continue
            if not person.names:
                return None
            name = person.names[0]
            surname = (name.surname or "").strip()
            given = (name.given or "").strip()
            if surname and given:
                return f"{surname}, {given}"
            return surname or given or None
        return None

    # ------------------------------------------------------------------
    # Family processing
    # ------------------------------------------------------------------

    def _collect_famc_pedigree(self, indi_records: list[GedcomLine]) -> None:
        """Populate ``self._famc_pedigree`` from the INDI records.

        Reads each individual's ``FAMC`` cross-references and their
        subordinate ``PEDI`` values, keying the result by
        ``(child xref, family xref)`` so that family-link creation can look
        up the pedigree for a given (child, family) pair. Only FAMC links
        carrying a PEDI value are recorded.

        Args:
            indi_records: Level-0 INDI GedcomLine records.
        """
        for record in indi_records:
            child_xref = record.xref_id
            if not child_xref:
                continue
            for family_xref, pedi in _extract_famc_pedigree(record).items():
                self._famc_pedigree[(child_xref, family_xref)] = pedi

    def _parentage_type_for(
        self, child_xref: str, family_xref: str
    ) -> str:
        """Resolve the parentage_type for a (child, family) pair.

        Consults the FAMC/PEDI pedigree collected from the child INDI
        record. ``foster`` → ``"foster"``, ``adopted`` → ``"adoptive"``,
        and anything else or absent → ``"biological"``.

        Args:
            child_xref: The child's GEDCOM cross-reference (e.g. ``"@I1@"``).
            family_xref: The family's GEDCOM cross-reference (e.g. ``"@F1@"``).

        Returns:
            One of ``"foster"``, ``"adoptive"``, or ``"biological"``.
        """
        pedigree = self._famc_pedigree.get((child_xref, family_xref))
        return _pedigree_to_parentage_type(pedigree)

    def _process_families(
        self,
        fam_records: list[GedcomLine],
        translation_data: TranslationData,
    ) -> None:
        """Process all FAM records from the GEDCOM file.

        For each family record:
        1. Extract into GedcomFamily
        2. Check translation mappings for existing App_JSON ID (re-import)
        3. Create or update Family record with partners and children
        4. Create marriage/divorce events
        5. Create ParentChildLinks
        6. Update translation mappings

        Args:
            fam_records: Level-0 FAM GedcomLine records.
            translation_data: Translation data to update with new mappings.
        """
        # Build mapping from gedcom_id → FamilyMapping for re-import
        family_mapping_by_xref: dict[str, FamilyMapping] = {
            m.gedcom_id: m for m in translation_data.families
        }

        for record in fam_records:
            gedcom_family = _extract_gedcom_family(record)
            existing_mapping = family_mapping_by_xref.get(gedcom_family.xref_id)

            if existing_mapping:
                self._update_family(gedcom_family, existing_mapping, record)
            else:
                self._create_family(gedcom_family, record, translation_data)

    def _create_family(
        self,
        gedcom_family: GedcomFamily,
        record: GedcomLine,
        translation_data: TranslationData,
    ) -> None:
        """Create a new Family and associated events from GEDCOM data.

        Args:
            gedcom_family: The extracted GEDCOM family data.
            record: The original GedcomLine record (for event extraction).
            translation_data: Translation data to update with new mapping.
        """
        family_id = self._id_gen.generate("family")
        self._family_xref_map[gedcom_family.xref_id] = family_id

        # Build partners list
        partners: list[FamilyPartner] = []
        if gedcom_family.husb_xref:
            husb_id = self._person_xref_map.get(gedcom_family.husb_xref)
            if husb_id:
                partners.append(FamilyPartner(person_id=husb_id, role="husband"))
        if gedcom_family.wife_xref:
            wife_id = self._person_xref_map.get(gedcom_family.wife_xref)
            if wife_id:
                partners.append(FamilyPartner(person_id=wife_id, role="wife"))

        # Build children list
        children: list[str] = []
        for child_xref in gedcom_family.child_xrefs:
            child_id = self._person_xref_map.get(child_xref)
            if child_id:
                children.append(child_id)

        # Create family events
        event_ids: list[str] = []
        for child_node in record.children:
            tag = child_node.tag.upper()
            if tag in _FAM_EVENT_TAGS:
                event_type = _FAM_EVENT_TAGS[tag]
                # Determine participants for family events
                participant_ids: list[tuple[str, str]] = []
                if gedcom_family.husb_xref:
                    husb_id = self._person_xref_map.get(gedcom_family.husb_xref)
                    if husb_id:
                        participant_ids.append((husb_id, "spouse"))
                if gedcom_family.wife_xref:
                    wife_id = self._person_xref_map.get(gedcom_family.wife_xref)
                    if wife_id:
                        participant_ids.append((wife_id, "spouse"))

                event_id = self._create_family_event(
                    event_type=event_type,
                    event_record=child_node,
                    participants=participant_ids,
                )
                if event_id:
                    event_ids.append(event_id)
            elif tag == "EVEN":
                # Generic family event → custom_family_event
                custom_type_name = _get_child_value(child_node, "TYPE")
                participant_ids = []
                if gedcom_family.husb_xref:
                    husb_id = self._person_xref_map.get(gedcom_family.husb_xref)
                    if husb_id:
                        participant_ids.append((husb_id, "spouse"))
                if gedcom_family.wife_xref:
                    wife_id = self._person_xref_map.get(gedcom_family.wife_xref)
                    if wife_id:
                        participant_ids.append((wife_id, "spouse"))

                event_id = self._create_family_event(
                    event_type="custom_family_event",
                    event_record=child_node,
                    participants=participant_ids,
                    custom_type_name=custom_type_name,
                )
                if event_id:
                    event_ids.append(event_id)

        # Build ParentChildLinks. The parentage_type comes from the child's
        # FAMC/PEDI pedigree for THIS family and applies to both parent
        # links of the child in the family (PEDI qualifies the child's
        # membership in the family, not a single parent).
        parent_child_links: list[ParentChildLink] = []
        for child_xref in gedcom_family.child_xrefs:
            child_id = self._person_xref_map.get(child_xref)
            if not child_id:
                continue
            parentage_type = self._parentage_type_for(
                child_xref, gedcom_family.xref_id
            )
            for partner in partners:
                parent_child_links.append(
                    ParentChildLink(
                        child_id=child_id,
                        parent_id=partner.person_id,
                        parentage_type=parentage_type,
                    )
                )

        family = Family(
            id=family_id,
            partners=partners,
            children=children,
            parent_child_links=parent_child_links,
            event_ids=event_ids,
        )
        self._project_data.families.append(family)
        self._families_added += 1

        # Update translation mapping
        translation_data.families.append(
            FamilyMapping(
                gedcom_id=gedcom_family.xref_id,
                app_id=family_id,
            )
        )

    def _update_family(
        self,
        gedcom_family: GedcomFamily,
        mapping: FamilyMapping,
        record: GedcomLine,
    ) -> None:
        """Update an existing Family with data from a GEDCOM re-import.

        Args:
            gedcom_family: The extracted GEDCOM family data.
            mapping: The existing FamilyMapping with the App_JSON ID.
            record: The original GedcomLine record (for event extraction).
        """
        family_id = mapping.app_id
        self._family_xref_map[gedcom_family.xref_id] = family_id

        # Find existing family
        existing_family: Optional[Family] = None
        for f in self._project_data.families:
            if f.id == family_id:
                existing_family = f
                break

        if existing_family is None:
            # Family was deleted — recreate with same ID
            # Build partners and children, then create
            partners: list[FamilyPartner] = []
            if gedcom_family.husb_xref:
                husb_id = self._person_xref_map.get(gedcom_family.husb_xref)
                if husb_id:
                    partners.append(FamilyPartner(person_id=husb_id, role="husband"))
            if gedcom_family.wife_xref:
                wife_id = self._person_xref_map.get(gedcom_family.wife_xref)
                if wife_id:
                    partners.append(FamilyPartner(person_id=wife_id, role="wife"))

            children_list: list[str] = []
            for child_xref in gedcom_family.child_xrefs:
                child_id = self._person_xref_map.get(child_xref)
                if child_id:
                    children_list.append(child_id)

            parent_child_links: list[ParentChildLink] = []
            for child_xref in gedcom_family.child_xrefs:
                child_id = self._person_xref_map.get(child_xref)
                if not child_id:
                    continue
                parentage_type = self._parentage_type_for(
                    child_xref, gedcom_family.xref_id
                )
                for partner in partners:
                    parent_child_links.append(
                        ParentChildLink(
                            child_id=child_id,
                            parent_id=partner.person_id,
                            parentage_type=parentage_type,
                        )
                    )

            family = Family(
                id=family_id,
                partners=partners,
                children=children_list,
                parent_child_links=parent_child_links,
                event_ids=[],
            )
            self._project_data.families.append(family)
            self._families_added += 1
            return

        # Update existing family
        partners = []
        if gedcom_family.husb_xref:
            husb_id = self._person_xref_map.get(gedcom_family.husb_xref)
            if husb_id:
                partners.append(FamilyPartner(person_id=husb_id, role="husband"))
        if gedcom_family.wife_xref:
            wife_id = self._person_xref_map.get(gedcom_family.wife_xref)
            if wife_id:
                partners.append(FamilyPartner(person_id=wife_id, role="wife"))

        children_list = []
        for child_xref in gedcom_family.child_xrefs:
            child_id = self._person_xref_map.get(child_xref)
            if child_id:
                children_list.append(child_id)

        parent_child_links = []
        for child_xref in gedcom_family.child_xrefs:
            child_id = self._person_xref_map.get(child_xref)
            if not child_id:
                continue
            parentage_type = self._parentage_type_for(
                child_xref, gedcom_family.xref_id
            )
            for partner in partners:
                parent_child_links.append(
                    ParentChildLink(
                        child_id=child_id,
                        parent_id=partner.person_id,
                        parentage_type=parentage_type,
                    )
                )

        existing_family.partners = partners
        existing_family.children = children_list
        existing_family.parent_child_links = parent_child_links
        self._families_updated += 1

        # Remove old family events from project data before re-creating
        # to prevent duplicates on re-import
        old_event_ids = set(existing_family.event_ids) if existing_family.event_ids else set()
        if old_event_ids:
            self._project_data.events = [
                e for e in self._project_data.events if e.id not in old_event_ids
            ]

        # Re-create family events
        event_ids: list[str] = []
        for child_node in record.children:
            tag = child_node.tag.upper()
            if tag in _FAM_EVENT_TAGS:
                event_type = _FAM_EVENT_TAGS[tag]
                participant_ids: list[tuple[str, str]] = []
                if gedcom_family.husb_xref:
                    husb_id = self._person_xref_map.get(gedcom_family.husb_xref)
                    if husb_id:
                        participant_ids.append((husb_id, "spouse"))
                if gedcom_family.wife_xref:
                    wife_id = self._person_xref_map.get(gedcom_family.wife_xref)
                    if wife_id:
                        participant_ids.append((wife_id, "spouse"))

                event_id = self._create_family_event(
                    event_type=event_type,
                    event_record=child_node,
                    participants=participant_ids,
                )
                if event_id:
                    event_ids.append(event_id)
            elif tag == "EVEN":
                custom_type_name = _get_child_value(child_node, "TYPE")
                participant_ids = []
                if gedcom_family.husb_xref:
                    husb_id = self._person_xref_map.get(gedcom_family.husb_xref)
                    if husb_id:
                        participant_ids.append((husb_id, "spouse"))
                if gedcom_family.wife_xref:
                    wife_id = self._person_xref_map.get(gedcom_family.wife_xref)
                    if wife_id:
                        participant_ids.append((wife_id, "spouse"))

                event_id = self._create_family_event(
                    event_type="custom_family_event",
                    event_record=child_node,
                    participants=participant_ids,
                    custom_type_name=custom_type_name,
                )
                if event_id:
                    event_ids.append(event_id)
        existing_family.event_ids = event_ids

    # ------------------------------------------------------------------
    # Placement event finalisation (Requirements 11.7, 11.7a, 11.10)
    # ------------------------------------------------------------------

    def _apply_placement_period(
        self, event_id: str, event_record: GedcomLine
    ) -> Optional[DateValue]:
        """Normalise a placement start event's date and return its end date.

        A Släktbusken-exported ``ADOP`` / ``EVEN TYPE Fosterhem`` structure may
        carry its placement's span as a GEDCOM period on the ``DATE`` line
        (``FROM <start> TO <end>``) or as a labelled ``Avslutades: <end>``
        ``NOTE`` (Requirement 11.2e). ``_create_event`` already stored whatever
        :func:`parse_gedcom_date` could make of the raw ``DATE`` string, but it
        cannot interpret a period, so a ``FROM``/``TO`` placement would be left
        dateless. This method re-reads the structure, splits the span into its
        start and end bounds, sets the start event's date to the lower bound
        (so the start keeps only its own date, not the whole period), and
        returns the end bound for the paired Placement_End_Event reconstruction
        (Requirement 11.10).

        Returns the extracted end :class:`DateValue`, or ``None`` when the
        placement has no end bound.
        """
        start_date, end_date = _parse_placement_dates(event_record)

        # Only override the start date when we parsed a period's lower bound;
        # a plain DATE was already handled correctly by _create_event, and we
        # must not clobber its source refs with a fresh DateValue.
        if end_date is not None and start_date is not None:
            event = next(
                (e for e in self._project_data.events if e.id == event_id),
                None,
            )
            if event is not None:
                event.date = start_date
        elif end_date is not None and start_date is None:
            # ``TO <end>`` with no lower bound: the start is genuinely dateless.
            event = next(
                (e for e in self._project_data.events if e.id == event_id),
                None,
            )
            if event is not None:
                event.date = None

        return end_date

    def _finalize_placement_events(self) -> None:
        """Attach parents and the child role to imported placement events.

        An ``ADOP`` or ``EVEN``/``TYPE Fosterhem`` structure is parsed during
        person processing into a dateless-or-dated placement START event that,
        at that point, names only the child in the generic ``"subject"`` role
        (the families do not yet exist, so the parents are unknown). This method
        runs after the families are built and, for each such recorded event:

        - rewrites the child participant's role from ``"subject"`` to the
          placement child role (``"adopterad"`` / ``"fosterbarn"``); and
        - when the structure carried a subordinate ``FAMC`` that resolves to an
          imported family, adds that family's partners as parent-role
          participants (``"adoptivförälder"`` / ``"fosterförälder"``), so the
          event names the exact Parent_Set the GEDCOM structure described
          (Requirement 11.7a) rather than leaving the parents to be guessed.

        A structure with no (resolvable) FAMC keeps only its child participant,
        staying a descriptive placement event that backs no Parent_Set — exactly
        how a pre-feature descriptive adoption event behaves. Carrying the
        event's own ``DATE``/``PLAC`` is already done by ``_create_event`` when
        the structure is parsed, satisfying the "prefer the structure's
        date/place" half of Requirement 11.7.

        When the structure carried an end date (a period upper bound or a
        labelled ``Avslutades:`` NOTE, recorded by ``_apply_placement_period``),
        this method also reconstructs the paired Placement_End_Event — an
        ``adoption_ended`` / ``foster_home_ended`` event naming the same child
        and the same parents as the start, dated with the extracted end date —
        so the placement's span round-trips (Requirement 11.10).

        Idempotent per event: a participant is never duplicated.
        """
        # Start type -> its paired end type, inverted from foster_sync's
        # end -> start table so an imported start can spawn its end.
        start_to_end = {
            start_type: end_type
            for end_type, start_type in _PLACEMENT_END_TYPES.items()
        }

        events_by_id = {event.id: event for event in self._project_data.events}

        for (
            event_id,
            child_person_id,
            famc_xref,
            end_date,
        ) in self._imported_placement_events:
            event = events_by_id.get(event_id)
            if event is None:
                continue

            config = _PLACEMENT_START_ROLES.get(event.type)
            if config is None:
                continue
            child_role = config["child_role"]
            parent_role = config["parent_role"]

            # Rewrite the child's role from the generic "subject" to the
            # placement child role so the sync/back-fill recognise the child.
            for participant in event.participants:
                if (
                    participant.person_id == child_person_id
                    and participant.role == "subject"
                ):
                    participant.role = child_role

            # Resolve the FAMC family → attach its partners as parents.
            family = None
            if famc_xref:
                family_id = self._family_xref_map.get(famc_xref)
                if family_id is not None:
                    family = next(
                        (
                            f
                            for f in self._project_data.families
                            if f.id == family_id
                        ),
                        None,
                    )

            if family is not None:
                existing_ids = {p.person_id for p in event.participants}
                for partner in family.partners:
                    if partner.person_id in existing_ids:
                        continue
                    if partner.person_id == child_person_id:
                        continue
                    event.participants.append(
                        Participant(
                            person_id=partner.person_id, role=parent_role
                        )
                    )
                    existing_ids.add(partner.person_id)

            # Reconstruct the paired Placement_End_Event from the end date the
            # structure carried (Requirement 11.10). It names the same child
            # and the same parents (symmetric participants, Requirement 1.10),
            # using the end type's own roles (identical to the start's roles).
            if end_date is not None:
                end_type = start_to_end.get(event.type)
                if end_type is not None:
                    self._create_paired_end_event(
                        start_event=event,
                        end_type=end_type,
                        end_date=end_date,
                    )

    def _create_paired_end_event(
        self,
        start_event: Event,
        end_type: str,
        end_date: DateValue,
    ) -> None:
        """Create the Placement_End_Event paired to an imported start event.

        The end event mirrors the start's participants (same child in the child
        role, same parents in the parent role — the end and start types share
        the same roles) and carries the ``end_date`` extracted from the start
        structure's period/NOTE. Appended to ``project.events`` so the
        placement's span is represented internally as two separate events, the
        symmetric model ``foster_sync`` pairs by Parent_Set (Requirement 11.10).
        """
        end_event = Event(
            id=self._id_gen.generate("event"),
            type=end_type,
            participants=[
                Participant(person_id=p.person_id, role=p.role)
                for p in start_event.participants
            ],
            date=end_date,
        )
        self._project_data.events.append(end_event)
        self._events_added += 1

    # ------------------------------------------------------------------
    # Event creation helpers
    # ------------------------------------------------------------------

    def _create_event(
        self,
        event_type: str,
        event_record: GedcomLine,
        participant_id: str,
        participant_role: str,
        custom_type_name: Optional[str] = None,
    ) -> Optional[str]:
        """Create an event from a GEDCOM event sub-record.

        Extracts date, place, and source citations from the event record
        and creates a new Event entity.

        Args:
            event_type: The App_JSON event type string.
            event_record: The GedcomLine containing the event data.
            participant_id: The person ID to add as participant.
            participant_role: The role of the participant.
            custom_type_name: Optional custom type name for custom events.

        Returns:
            The new event ID, or None if the event could not be created.
        """
        event_id = self._id_gen.generate("event")

        # Parse date
        date_value: Optional[DateValue] = None
        date_str = _get_child_value(event_record, "DATE")
        if date_str:
            date_value = parse_gedcom_date(date_str)

        # Parse place
        place_ref: Optional[PlaceRef] = None
        plac_rec = _get_child(event_record, "PLAC")
        if plac_rec:
            # Try structured _ADPL first, fall back to PLAC string parsing
            place_id = self._resolve_place_from_adpl(plac_rec)
            if place_id is None:
                place_str = plac_rec.value
                if place_str:
                    place_id = self._resolve_place(place_str)
            if place_id:
                place_ref = PlaceRef(place_id=place_id)
                # Extract MAP/LATI/LONG coordinates if present
                self._apply_coordinates(place_id, plac_rec)

        # Event deduplication: skip if an identical event already exists
        if self._existing_event_keys is not None:
            date_val_str = date_value.value if date_value else None
            place_id_str = place_ref.place_id if place_ref else None
            key = (event_type, date_val_str, place_id_str)
            if key in self._existing_event_keys:
                return None

        # Parse source citations on the event
        source_refs: list[SourceRef] = []
        for sour_child in _get_children(event_record, "SOUR"):
            if sour_child.value:
                source_id = self._source_xref_map.get(sour_child.value)
                if source_id:
                    source_refs.append(
                        SourceRef(source_id=source_id, quality="secondary")
                    )

        # Attach source refs to date if present
        if date_value and source_refs:
            date_value.source_refs = list(source_refs)

        # Cause of death for DEAT events
        cause_of_death: Optional[str] = None
        if event_type == "death":
            cause_val = _get_child_value(event_record, "CAUS")
            if cause_val:
                cause_of_death = cause_val

        participants = [Participant(person_id=participant_id, role=participant_role)]

        event = Event(
            id=event_id,
            type=event_type,
            participants=participants,
            date=date_value,
            place=place_ref,
            cause_of_death=cause_of_death,
            custom_type_name=custom_type_name,
        )
        self._project_data.events.append(event)
        self._events_added += 1
        return event_id

    def _create_family_event(
        self,
        event_type: str,
        event_record: GedcomLine,
        participants: list[tuple[str, str]],
        custom_type_name: Optional[str] = None,
    ) -> Optional[str]:
        """Create a family event (marriage, divorce, etc.) from GEDCOM data.

        Args:
            event_type: The App_JSON event type string.
            event_record: The GedcomLine containing the event data.
            participants: List of (person_id, role) tuples for participants.
            custom_type_name: Optional custom type name for custom events.

        Returns:
            The new event ID, or None if no participants.
        """
        if not participants:
            return None

        event_id = self._id_gen.generate("event")

        # Parse date
        date_value: Optional[DateValue] = None
        date_str = _get_child_value(event_record, "DATE")
        if date_str:
            date_value = parse_gedcom_date(date_str)

        # Parse place
        place_ref: Optional[PlaceRef] = None
        plac_rec = _get_child(event_record, "PLAC")
        if plac_rec:
            # Try structured _ADPL first, fall back to PLAC string parsing
            place_id = self._resolve_place_from_adpl(plac_rec)
            if place_id is None:
                place_str = plac_rec.value
                if place_str:
                    place_id = self._resolve_place(place_str)
            if place_id:
                place_ref = PlaceRef(place_id=place_id)
                # Extract MAP/LATI/LONG coordinates if present
                self._apply_coordinates(place_id, plac_rec)

        # Source citations
        source_refs: list[SourceRef] = []
        for sour_child in _get_children(event_record, "SOUR"):
            if sour_child.value:
                source_id = self._source_xref_map.get(sour_child.value)
                if source_id:
                    source_refs.append(
                        SourceRef(source_id=source_id, quality="secondary")
                    )

        if date_value and source_refs:
            date_value.source_refs = list(source_refs)

        event_participants = [
            Participant(person_id=pid, role=role) for pid, role in participants
        ]

        event = Event(
            id=event_id,
            type=event_type,
            participants=event_participants,
            date=date_value,
            place=place_ref,
            custom_type_name=custom_type_name,
        )
        self._project_data.events.append(event)
        self._events_added += 1
        return event_id

    # ------------------------------------------------------------------
    # Place resolution
    # ------------------------------------------------------------------

    def _resolve_place_from_adpl(self, plac_rec: GedcomLine) -> Optional[str]:
        """Resolve a place from a structured _ADPL sub-record under PLAC.

        ArkivDigital exports include a custom _ADPL tag with structured place
        data. In the best case it contains _PARISH, _COUNTY, and _COUNTRY
        which can be used directly. Otherwise, if only _LOCALITY is present,
        that string is parsed as a regular place string.

        Args:
            plac_rec: The GedcomLine for the PLAC tag (with children).

        Returns:
            The App_JSON place ID, or None if no _ADPL data is usable.
        """
        adpl_rec = _get_child(plac_rec, "_ADPL")
        if not adpl_rec:
            return None

        parish = _get_child_value(adpl_rec, "_PARISH")
        county = _get_child_value(adpl_rec, "_COUNTY")
        country = _get_child_value(adpl_rec, "_COUNTRY")

        if parish and county and country:
            # Build a structured place string: "parish, county, country"
            place_string = f"{parish}, {county}, {country}"
            return self._resolve_place(place_string)

        # Fallback: use _LOCALITY as a place string
        locality = _get_child_value(adpl_rec, "_LOCALITY")
        if locality:
            return self._resolve_place(locality)

        return None

    def _resolve_place(self, place_string: str) -> Optional[str]:
        """Resolve a GEDCOM place string to an App_JSON place ID.

        Uses a cache to avoid re-processing the same place string. If the
        place has not been seen before, delegates to the TranslationManager
        to find or create the place hierarchy. Also updates the translation
        data with the new mapping for re-import support.

        Args:
            place_string: The verbatim GEDCOM place string.

        Returns:
            The App_JSON place ID for the most-specific place level,
            or None if the place string is empty.
        """
        if not place_string or not place_string.strip():
            return None

        normalized = place_string.strip()
        if normalized in self._place_cache:
            return self._place_cache[normalized]

        place_id, new_places = self._translation_mgr.map_place(
            normalized, self._project_data.places
        )

        # Add new places to project
        for new_place in new_places:
            self._project_data.places.append(new_place)
            self._places_added += 1

        # Fallback for single-word place values: if map_place returned None
        # and the place string has no commas (single word/name), try to find
        # an existing place by name or create a minimal record.
        if place_id is None and "," not in normalized:
            place_id = self._resolve_single_word_place(normalized)

        if place_id:
            self._place_cache[normalized] = place_id

            # Persist the place mapping in translation data for re-import
            if self._translation_data is not None:
                already_mapped = any(
                    m.gedcom_place == normalized
                    for m in self._translation_data.places
                )
                if not already_mapped:
                    # Extract the most-specific name for display
                    name_parts = normalized.split(",")
                    display_name = name_parts[0].strip() if name_parts else normalized
                    self._translation_data.places.append(
                        PlaceMapping(
                            gedcom_place=normalized,
                            app_id=place_id,
                            name=display_name,
                        )
                    )

        return place_id

    def _apply_coordinates(self, place_id: str, plac_rec: GedcomLine) -> None:
        """Extract MAP/LATI/LONG from a PLAC record and apply to the place.

        Parses the GEDCOM MAP sub-structure under PLAC to extract latitude
        and longitude. The GEDCOM format uses N/S prefix for latitude and
        E/W prefix for longitude (e.g., "N59.8392", "E12.3153").

        Only updates the place if it does not already have coordinates set.

        Args:
            place_id: The App_JSON place ID to update.
            plac_rec: The GedcomLine for the PLAC tag (with children).
        """
        map_rec = _get_child(plac_rec, "MAP")
        if not map_rec:
            return

        lati_str = _get_child_value(map_rec, "LATI")
        long_str = _get_child_value(map_rec, "LONG")
        if not lati_str or not long_str:
            return

        latitude = _parse_gedcom_coordinate(lati_str, positive_prefix="N", negative_prefix="S")
        longitude = _parse_gedcom_coordinate(long_str, positive_prefix="E", negative_prefix="W")

        if latitude is None or longitude is None:
            return

        # Find the place and update coordinates (only if not already set)
        for place in self._project_data.places:
            if place.id == place_id:
                if place.latitude is None and place.longitude is None:
                    place.latitude = latitude
                    place.longitude = longitude
                break

    def _resolve_single_word_place(self, place_name: str) -> Optional[str]:
        """Resolve a single-word PLAC value by name matching or creation.

        When the normal place mapping pipeline returns None for a single-word
        place string (no commas), this method provides a fallback:
        1. Search existing places for a case-insensitive name match.
        2. If found, reuse that place's ID.
        3. If not found, create a minimal Place record with type="unknown".

        A structured warning is always logged so the user is aware that
        a single-word place was resolved via fallback rather than the
        normal hierarchy-based mapping.

        Args:
            place_name: The single-word place string (already stripped).

        Returns:
            The place ID of the matched or newly created place.
        """
        name_lower = place_name.lower()

        # Search existing places by name (case-insensitive)
        for existing_place in self._project_data.places:
            if existing_place.name.lower() == name_lower:
                self._warnings.append(WarningEntry(
                    gedcom_file=self._gedcom_filename,
                    raw_value=place_name,
                    reason=f"Plats '{place_name}' (ett ord) matchades mot befintlig plats '{existing_place.name}' (id: {existing_place.id}, typ: {existing_place.type})",
                    action_taken="Använde befintlig plats",
                ))
                return existing_place.id

        # No existing match — create a minimal Place record
        new_id = self._id_gen.generate("place")
        new_place = Place(
            id=new_id,
            type="unknown",
            name=place_name,
            parent_place_id=None,
        )
        self._project_data.places.append(new_place)
        self._places_added += 1

        self._warnings.append(WarningEntry(
            gedcom_file=self._gedcom_filename,
            raw_value=place_name,
            reason=f"Plats '{place_name}' (ett ord) kunde inte matchas mot platshierarkin",
            action_taken=f"Skapade fristående platspost (id: {new_id}, typ: unknown)",
        ))
        return new_id
