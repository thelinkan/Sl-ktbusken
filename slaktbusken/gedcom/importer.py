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

import logging
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Optional, Sequence

from slaktbusken.gedcom.dates import parse_gedcom_date
from slaktbusken.gedcom.errors import ImportAborted
from slaktbusken.model.date_semantics import validate_date_value
from slaktbusken.gedcom import event_links
from slaktbusken.gedcom.parser import GedcomLine, GedcomParseError, parse_gedcom
from slaktbusken.gedcom.slk_tags import (
    EventTagData,
    SlkProblem,
    read_citation,
    read_endpoint,
    read_legacy_prose,
    read_residence_texts,
    read_source_fields,
    read_event_participants,
    read_event_tags,
    read_name_type,
    read_partners,
    read_plinks,
    read_repository,
)
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
from slaktbusken.gedcom.translation.record_identity import (
    IncomingRecord,
    MatchResult,
    Outcome,
    PoolEntry,
    build_origin_groups,
    event_fingerprint,
    match_records,
    residence_fingerprint,
    record_hash,
)
from slaktbusken.gedcom.translation.source_translation import detect_arkiv_digital
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.record_origin import RecordOrigin
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.id_generator import IDGenerator
from slaktbusken.services.id_registry import person_id_seed, retired_person_ids
from slaktbusken.services.redirect_resolution import RedirectResolver
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

logger = logging.getLogger(__name__)


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
        events_claimed: Number of legacy events (without origin) that were
            matched one to one and received an Event_Origin.
        residences_added: Number of new residences created from RESI records.
        residences_claimed: Number of legacy residences (without origins)
            matched one to one that received an origin.
        warnings: Swedish-language warnings for skipped/problematic records.
    """

    persons_added: int = 0
    persons_updated: int = 0
    families_added: int = 0
    families_updated: int = 0
    events_added: int = 0
    sources_added: int = 0
    places_added: int = 0
    events_claimed: int = 0
    residences_added: int = 0
    residences_claimed: int = 0
    warnings: list[str] = field(default_factory=list)
    merged_identity_matches: list["MergedIdentityMatch"] = field(default_factory=list)
    ambiguous_records: list["AmbiguousRecord"] = field(default_factory=list)
    translation: Optional[TranslationData] = None


@dataclass
class MergedIdentityMatch:
    """A GEDCOM record that matched the identity of a merged-away person.

    The record was not imported; the surviving person is left unchanged.

    Attributes:
        xref: The GEDCOM xref of the incoming record.
        person_id: The surviving person the record resolves to.
        matched_by: ``"xref"`` or ``"fingerprint"``.
        differing_fields: Names of person fields where the record differs
            from the survivor (for example ``"birth_date"``).
    """

    xref: str
    person_id: str
    matched_by: str
    differing_fields: list[str] = field(default_factory=list)


@dataclass
class AmbiguousRecord:
    """A GEDCOM record that could resolve to more than one active person.

    The record is assigned to no person and changes nothing.

    Attributes:
        xref: The GEDCOM xref of the incoming record.
        candidate_person_ids: The active persons the record could resolve to.
    """

    xref: str
    candidate_person_ids: list[str] = field(default_factory=list)


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



def _date_dedup_key(dv: Optional[DateValue]) -> Optional[str]:
    """Comparison key for a date: the ISO value for exact dates, else every
    structured field and the original text, so that two different qualified or
    unparsed dates are never treated as equal."""
    if dv is None:
        return None
    if dv.qualifier == "exact" and dv.precision != "approximate":
        return dv.value or None
    return "|".join(
        (dv.qualifier, dv.calendar, dv.value or "", dv.value_to or "", dv.original_text or "")
    )


def _event_tag_key(tag: str, custom_type_name: Optional[str]) -> str:
    """Tag key of an event record, consistent with ``tag_key_of``.

    The GEDCOM tag, except that ``CHR`` is keyed as ``BAPM`` (both map to the
    baptism type) and an ``EVEN`` record is ``EVEN:`` plus the normalised TYPE
    value (``EVEN`` alone without TYPE).
    """
    tag = tag.upper()
    if tag == "EVEN":
        name = (custom_type_name or "").strip().lower()
        return f"EVEN:{name}" if name else "EVEN"
    return "BAPM" if tag == "CHR" else tag


@dataclass
class _EventSpec:
    """An event-bearing child record of an INDI or FAM record."""

    record: GedcomLine
    event_type: str
    tag_key: str
    participants: list[tuple[str, str]]
    custom_type_name: Optional[str] = None
    placement: bool = False
    # Participant role of an INDI event (``_SLK_ROLE``; "subject" by default).
    role: str = "subject"
    # Event_Token of the structure (``_SLK_EID``), or None.
    token: Optional[str] = None
    # ``_SLK_FROMPLAC`` text of a flytt, or None.
    from_place: Optional[str] = None


class _EventIndex:
    """Lookup tables over the project's events for the identity matcher.

    Built once per import from the events present at that time and extended
    by the importer for events it creates or claims, so that matching an
    owner does not scan every event of the project.
    """

    def __init__(self, events: Sequence[Event]) -> None:
        self.by_id: dict[str, Event] = {}
        self.by_participant: dict[str, list[Event]] = {}
        self.by_origin_owner: dict[tuple[str, str], list[Event]] = {}
        self._seen: set[int] = set()
        for event in events:
            self.add(event)

    def add(self, event: Event) -> None:
        if id(event) in self._seen:
            return
        self._seen.add(id(event))
        self.by_id[event.id] = event
        listed: set[str] = set()
        for participant in event.participants:
            if participant.person_id not in listed:
                listed.add(participant.person_id)
                self.by_participant.setdefault(participant.person_id, []).append(event)
        self.note_origin(event)

    def note_origin(self, event: Event) -> None:
        for origin in _event_origins(event):
            bucket = self.by_origin_owner.setdefault(
                (origin.owner_kind, origin.owner_id), []
            )
            if not any(e is event for e in bucket):
                bucket.append(event)

    def note_participant(self, event: Event, person_id: str) -> None:
        bucket = self.by_participant.setdefault(person_id, [])
        if not any(e is event for e in bucket):
            bucket.append(event)

    def remove(self, event: Event) -> None:
        """Forget *event* (it was folded into another event)."""
        self._seen.discard(id(event))
        if self.by_id.get(event.id) is event:
            del self.by_id[event.id]
        for table in (self.by_participant, self.by_origin_owner):
            for bucket in table.values():
                bucket[:] = [e for e in bucket if e is not event]


def _event_origins(event: Event) -> list[RecordOrigin]:
    """All origins of *event*: ``origin`` first, then ``extra_origins``."""
    origins = [event.origin] if event.origin is not None else []
    origins.extend(event.extra_origins)
    return origins


class _ResidenceIndex:
    """Per-person lookup of residences for the identity matcher."""

    def __init__(self, residences: Sequence[ResidenceFact]) -> None:
        self.by_person: dict[str, list[ResidenceFact]] = {}
        self._seen: set[int] = set()
        for fact in residences:
            self.add(fact)

    def add(self, fact: ResidenceFact) -> None:
        if id(fact) in self._seen:
            return
        self._seen.add(id(fact))
        self.by_person.setdefault(fact.person_id, []).append(fact)


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


def _resi_fragment(text: str) -> Optional[tuple[str, str, DateValue]]:
    """Parse one RESI date fragment into (iso, precision, DateValue).

    Only a single Gregorian date, optionally qualified (ABT, EST, CAL, BEF,
    AFT), is usable; anything else (unparsed, Julian, a nested range) is not.
    """
    parsed = parse_gedcom_date(text)
    if parsed is None:
        return None
    dv = parsed.value
    if (
        dv.qualifier not in ("exact", "about", "estimated", "calculated", "before", "after")
        or dv.calendar != "gregorian"
        or not dv.value
    ):
        return None
    if dv.qualifier == "exact":
        precision = {4: "year", 7: "month"}.get(len(dv.value), "day")
    else:
        precision = "approximate"
    return dv.value, precision, dv


def _resi_range_ok(first: DateValue, last: DateValue, qualifier: str) -> bool:
    """Whether the two endpoints form a valid, non-reversed range."""
    return not validate_date_value(
        DateValue(
            value=first.value, precision="approximate", qualifier=qualifier,
            value_to=last.value,
        )
    )


def _parse_resi_date(raw_date: Optional[str]) -> _ResiDateResult:
    """Parse a RESI DATE line into endpoint data for a ResidenceFact.

    Tokenising and validation of every fragment are delegated to
    ``gedcom.dates``; this function only maps the structured fragments onto
    ``Endpoint`` bounds:

    - ``FROM x TO y`` -> start.latest = x, end.earliest = y (core bounds)
    - ``BET x AND y`` -> start.earliest = x, start.latest = y, end unknown
    - ``FROM x`` -> start.latest = x; ``TO x`` -> end.earliest = x
    - a single date (also ``ABT``, ``BEF`` ...) -> start.latest = end.earliest
      = the date (approximate precision when qualified)
    - unparsed, Julian, reversed and empty -> not interpretable, both
      endpoints unknown (an Endpoint has no calendar, so a Julian date is
      never stored as if it were Gregorian)
    """
    result = _ResiDateResult()
    if not raw_date or not raw_date.strip():
        return result

    stripped = raw_date.strip()
    lead = ""
    escape = re.match(r"^(@#D[^@]*@)\s*(.*)$", stripped)
    if escape:
        lead, stripped = escape.group(1) + " ", escape.group(2)

    m = _FROM_TO_RE.match(stripped)
    if m:
        a, b = _resi_fragment(lead + m.group(1)), _resi_fragment(lead + m.group(2))
        if a and b and _resi_range_ok(a[2], b[2], "from_to"):
            result.start_latest, result.start_precision = a[0], a[1]
            result.end_earliest, result.end_precision = b[0], b[1]
            result.interpretable = True
        return result

    m = _BET_AND_RE.match(stripped)
    if m:
        a, b = _resi_fragment(lead + m.group(1)), _resi_fragment(lead + m.group(2))
        if a and b and _resi_range_ok(a[2], b[2], "between"):
            result.start_earliest = a[0]
            result.start_latest, result.start_precision = b[0], b[1]
            result.interpretable = True
        return result

    m = _FROM_ONLY_RE.match(stripped)
    if m:
        a = _resi_fragment(lead + m.group(1))
        if a:
            result.start_latest, result.start_precision = a[0], a[1]
            result.interpretable = True
        return result

    m = _TO_ONLY_RE.match(stripped)
    if m:
        a = _resi_fragment(lead + m.group(1))
        if a:
            result.end_earliest, result.end_precision = a[0], a[1]
            result.interpretable = True
        return result

    a = _resi_fragment(lead + stripped)
    if a:
        result.start_latest = result.end_earliest = a[0]
        result.start_precision = result.end_precision = a[1]
        result.interpretable = True
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

    ``None`` only for a blank fragment; an unreadable fragment becomes an
    unparsed :class:`DateValue` that keeps its text.
    """
    parsed = parse_gedcom_date(raw or "")
    return parsed.value if parsed is not None else None


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

        # A leading calendar escape applies to every endpoint of the period.
        lead = ""
        escape = re.match(r"^(@#D[^@]*@)\s*(.*)$", stripped)
        if escape:
            lead, stripped = escape.group(1) + " ", escape.group(2)

        m = _FROM_TO_RE.match(stripped)
        if m:
            start_date = _date_value_from(lead + m.group(1))
            end_date = _date_value_from(lead + m.group(2))
            return start_date, end_date

        m = _FROM_ONLY_RE.match(stripped)
        if m:
            start_date = _date_value_from(lead + m.group(1))
            return start_date, None

        m = _TO_ONLY_RE.match(stripped)
        if m:
            end_date = _date_value_from(lead + m.group(1))
            return None, end_date

        # Plain date (no period marker): the start is this date; no end.
        start_date = _date_value_from(lead + stripped)

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
    name_types: list[Optional[str]] = []

    # Parse NAME tags
    name_records = _get_children(record, "NAME")
    for i, name_rec in enumerate(name_records):
        name_types.append(read_name_type(name_rec))
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
    # Sex X is written as ``SEX U`` with ``2 _SLK_SEX X`` (Requirement 4.8).
    sex_rec = _get_child(record, "SEX")
    if sex_rec is not None:
        slk_sex = _get_child_value(sex_rec, "_SLK_SEX")
        if slk_sex and slk_sex.strip().upper() == "X":
            sex = "X"

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
        name_types=name_types,
    )


def _build_names(
    gp: GedcomPerson, existing: Optional[Sequence[Name]] = None
) -> list[Name]:
    """Build the Name list of a person from an extracted INDI record.

    Requirement 3: a NAME with a TYPE gets the mapped type. When at least one
    NAME of the record has a TYPE, a NAME without TYPE becomes ``other`` and no
    type is inferred from the position. When no NAME has a TYPE, the existing
    name of the same given name and surname keeps its type (update only);
    otherwise the positional rule applies (first ``birth``, later ``other``).
    """
    entries: list[tuple[str, str, Optional[str], bool]] = []
    types = list(gp.name_types)
    if gp.given_name or gp.surname:
        entries.append(
            (gp.given_name, gp.surname, types[0] if types else None, True)
        )
    for i, (given, surname) in enumerate(gp.additional_names, start=1):
        entries.append(
            (given, surname, types[i] if i < len(types) else None, False)
        )

    any_type = any(t for t in types)
    available = list(existing or [])
    names: list[Name] = []
    for given, surname, name_type, is_primary in entries:
        event_id: Optional[str] = None
        if any_type:
            resolved = name_type or "other"
        else:
            match = next(
                (
                    n for n in available
                    if (n.given or "") == given and (n.surname or "") == surname
                ),
                None,
            )
            if match is not None:
                available.remove(match)
                resolved = match.type
                event_id = match.event_id
            else:
                resolved = "birth" if is_primary else "other"
        names.append(
            Name(type=resolved, given=given, surname=surname, event_id=event_id)
        )
    if not names:
        names.append(Name(type="birth", given="", surname=""))
    return names


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

        removed_links = [
            link for link in family.parent_child_links if link not in kept_links
        ]
        moved_children = {link.child_id for link in removed_links}
        moved_parents = {
            link.parent_id for link in removed_links if link.parent_id is not None
        }

        # The derived family of a moved child carries the partner roles and
        # order the file stated for the same parents (the derived family
        # itself only knows sex-based roles).
        for derived in derived_families:
            if not moved_children.intersection(derived.children):
                continue
            if {p.person_id for p in derived.partners} != {
                p.person_id for p in family.partners
            } or len(derived.partners) != len(family.partners):
                continue
            derived.partners = [
                FamilyPartner(person_id=p.person_id, role=p.role)
                for p in family.partners
            ]

        family.parent_child_links = kept_links

        # Only a child/parent that took part in a relocated link and has no
        # remaining link here is pruned, so the exporter does not emit a stray
        # FAMC/FAMS for a relationship that now lives solely on the derived
        # family. Children, partners and events the file stated stay.
        remaining_children = {link.child_id for link in kept_links}
        remaining_parents = {
            link.parent_id for link in kept_links if link.parent_id is not None
        }
        family.children = [
            child_id
            for child_id in family.children
            if child_id in remaining_children or child_id not in moved_children
        ]
        if not family.event_ids:
            family.partners = [
                partner
                for partner in family.partners
                if partner.person_id in remaining_parents
                or partner.person_id not in moved_parents
            ]

        # Drop a family emptied of all links, children and events; it holds no
        # data of its own.
        if (
            not family.parent_child_links
            and not family.children
            and not family.event_ids
        ):
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

    def __init__(
        self,
        project_data: ProjectData,
        translation_dir: Path,
        *,
        overlay: Optional[TranslationData] = None,
        stage_only: bool = False,
    ) -> None:
        """Initialize the importer with project data and translation directory.

        Args:
            overlay: Pending translation data used instead of the files on
                disk for every translation read.
            stage_only: When True the importer writes no translation file and
                returns the mutated data in ``ImportResult.translation``.
        """
        self._project_data = project_data
        self._translation_dir = translation_dir
        self._stage_only = stage_only
        self._translation_mgr = TranslationManager(translation_dir, overlay=overlay)
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

        # Retired person ids and the person high-water mark are never reissued.
        existing_ids |= person_id_seed(project_data)
        self._id_gen = IDGenerator(existing_ids)
        self._retired_ids: set[str] = retired_person_ids(project_data)
        self._merged_identity_matches: list[MergedIdentityMatch] = []
        self._ambiguous_records: list[AmbiguousRecord] = []

        # Mapping from GEDCOM xref → App_JSON ID (built during import)
        self._source_xref_map: dict[str, str] = {}
        # Hash_Profile of the file being imported ("legacy" or "slk1").
        self._hash_profile: str = "legacy"
        # True when HEAD has ``_SLK_VERS`` with any value (SLK_Marker).
        self._has_slk_marker: bool = False
        # Event_Token (``_SLK_EID``) → event id, for the file being imported.
        # Filled with every event created or matched that carries a token.
        self._event_token_map: dict[str, str] = {}
        # ``_SLK_EREF`` links found in the file, resolved after the events.
        self._event_link_requests: list[event_links.LinkRequest] = []
        # Ids of the events this run created (a fold may remove one of them).
        self._run_created_event_ids: set[str] = set()
        self._person_xref_map: dict[str, str] = {}
        self._family_xref_map: dict[str, str] = {}
        # REPO xref → Repository id, for the file being imported.
        self._repo_xref_map: dict[str, str] = {}

        # FAMC/PEDI pedigree lookup keyed by (child xref, family xref) →
        # lowercased PEDI value. Populated from INDI records before families
        # are processed so family-link creation can set parentage_type.
        self._famc_pedigree: dict[tuple[str, str], str] = {}
        # FAMC lines by (child xref, family xref), for _SLK_PLINK entries.
        self._famc_nodes: dict[tuple[str, str], GedcomLine] = {}

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

        # Event identity: lookup tables over the project's events, built on the
        # first matcher call of a run and kept current for events created in
        # the run (see _EventIndex).
        self._event_index: Optional[_EventIndex] = None
        self._events_missing_from_file = 0
        # Residence identity: per-person lookup built on first use per run.
        self._residence_index: Optional[_ResidenceIndex] = None
        self._residences_added = 0
        self._residences_claimed = 0

        # Counters
        self._persons_added = 0
        self._persons_updated = 0
        self._families_added = 0
        self._families_updated = 0
        self._events_added = 0
        self._events_claimed = 0
        self._residences_added = 0
        self._residences_claimed = 0
        self._residence_index = None
        self._sources_added = 0
        self._places_added = 0

        # Record context for ImportAborted (Requirement 20.26)
        self._ctx_xref: Optional[str] = None
        self._ctx_label: Optional[str] = None
        self._ctx_phase: Optional[str] = None

    @contextmanager
    def _record_context(
        self, xref: Optional[str], label: Optional[str], phase: str
    ) -> Iterator[None]:
        """Mark the record being processed.

        On normal exit the previous context is restored. When an exception
        leaves the block the context stays, so the outer handler in
        ``import_file`` can name the failed record.
        """
        previous = (self._ctx_xref, self._ctx_label, self._ctx_phase)
        self._ctx_xref, self._ctx_label, self._ctx_phase = xref, label, phase
        yield
        self._ctx_xref, self._ctx_label, self._ctx_phase = previous

    @staticmethod
    def _record_label(record: GedcomLine) -> str:
        """Name of an INDI record, else its tag."""
        name = _get_child_value(record, "NAME")
        if name:
            name = name.replace("/", " ")
            name = " ".join(name.split())
        return name or record.tag.upper()

    def import_file(self, gedcom_path: Path) -> ImportResult:
        """Import a GEDCOM file; any unexpected error aborts the import.

        Reading and parsing errors (``FileNotFoundError``,
        ``UnicodeDecodeError``, ``GedcomParseError``) keep their own types.
        Every other ``Exception`` raised while records are processed is
        wrapped in ``ImportAborted`` (cause kept, traceback written to the
        import log). ``BaseException`` is not touched. Nothing is converted
        into a warning (Requirements 20.23, 20.24).
        """
        self._ctx_xref = self._ctx_label = self._ctx_phase = None
        try:
            return self._import_file(gedcom_path)
        except (
            ImportAborted,
            GedcomParseError,
            UnicodeDecodeError,
            FileNotFoundError,
        ):
            raise
        except Exception as exc:
            aborted = ImportAborted.from_exception(
                exc,
                xref=self._ctx_xref,
                label=self._ctx_label,
                phase=self._ctx_phase,
            )
            logger.error("GEDCOM-importen avbröts:\n%s", aborted.traceback_text)
            self._write_abort_log(gedcom_path, aborted)
            raise aborted from exc

    def _write_abort_log(self, gedcom_path: Path, aborted: ImportAborted) -> None:
        """Append the abort message and traceback to the import log."""
        import datetime

        try:
            log_dir = Path(r"C:\Temp")
            log_dir.mkdir(parents=True, exist_ok=True)
            with open(log_dir / "gedcom_import.log", "w", encoding="utf-8") as f:
                f.write(
                    f"GEDCOM Import Log — {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n"
                )
                f.write(f"Source file: {gedcom_path}\n")
                f.write("IMPORT ABORTED\n")
                f.write(f"{aborted.message_sv}\n\n")
                f.write(aborted.traceback_text)
        except OSError:
            pass  # A missing diagnostic log must not hide the abort

    def _import_file(self, gedcom_path: Path) -> ImportResult:
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
        self._event_index = None
        self._event_token_map = {}
        self._event_link_requests = []
        self._run_created_event_ids = set()
        # ``families_added`` counts families that did not exist before this
        # import (Requirement 12.9), see the end of the import.
        families_before = {f.id for f in self._project_data.families}

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
        repo_records: list[GedcomLine] = []

        # Track last-seen INDI context for unsupported tag warnings
        _last_indi_xref: Optional[str] = None
        _last_indi_name: Optional[str] = None

        # SLK_Marker: HEAD ``_SLK_VERS 1`` selects Hash_Profile slk1. A missing
        # marker or any other value keeps ``legacy`` (other values warn once).
        self._hash_profile = "legacy"
        self._has_slk_marker = False
        for record in parse_result.records:
            if record.tag.upper() != "HEAD":
                continue
            for child in record.children:
                if child.tag.upper() != "_SLK_VERS":
                    continue
                self._has_slk_marker = True
                vers = (child.value or "").strip()
                if vers == "1":
                    self._hash_profile = "slk1"
                else:
                    self._warnings.append(WarningEntry(
                        gedcom_file=self._gedcom_filename,
                        raw_value=f"_SLK_VERS {vers}".strip(),
                        reason=f"okänt värde för _SLK_VERS '{vers}'",
                        action_taken="Äldre hashprofil användes",
                    ))
                break
            break

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
            elif tag == "REPO":
                repo_records.append(record)
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
        self._ctx_phase = "källor"
        self._process_sources(sour_records, translation_data, repo_records)

        # Step 2: Process persons (pass fam_records for fingerprint matching)
        self._ctx_phase = "personer"
        self._process_persons(indi_records, translation_data, fam_records)

        # Step 2b: Collect FAMC/PEDI pedigree so family-link creation can
        # set parentage_type (the pedigree lives under the child INDI's
        # FAMC, not under the family's CHIL).
        self._ctx_phase = "släktskap"
        self._collect_famc_pedigree(indi_records)

        # Step 3: Process families
        self._ctx_phase = "familjer"
        self._process_families(fam_records, translation_data)
        self._ctx_phase = "avslutande kontroller"

        # Step 3b: Finalise imported placement START events (ADOP / Fosterhem
        # EVEN). Now that the families exist, resolve each event's subordinate
        # FAMC to the Parent_Set it names and attach those parents in the
        # placement parent role, converting the child-only event into a real
        # backing placement event (Requirements 11.7, 11.7a).
        self._finalize_placement_events()

        # Step 3b2: Set Name.event_id / Endpoint.event_id from _SLK_EREF.
        self._resolve_event_links()

        # Step 3c: Back-fill a placement event for every imported foster/
        # adoptive link not already backed by an imported (or just-finalised)
        # placement event, so the post-import sync preserves it rather than
        # deleting it as an orphan (Requirements 11.6, 11.8). The same shared
        # helper is used by the on-load migration (task 3.2) so importer and
        # migration cannot diverge. Running the Parentage_Sync_Service itself is
        # task 10.4; the back-fill establishes the precondition it relies on.
        # ``attach_to_family=False``: an imported family is never recorded as
        # placement-derived, so the sync builds a separate derived family.
        backfill_orphan_placement_events(
            self._project_data, attach_to_family=False
        )

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

        # A family created during the import can be folded away again by the
        # reconciliation (an imported foster FAM), and a missing family with a
        # known translation is recreated under its old id. Neither is a new
        # family. Count what is in the project now and was not before; this
        # includes a derived foster family that stays separate.
        self._families_added = sum(
            1 for f in self._project_data.families if f.id not in families_before
        )

        # Summary notices for the event identity matcher (Requirements 10.7,
        # 19.7): events whose GEDCOM record is no longer in the file stay
        # untouched, and legacy events that received an Event_Origin are
        # counted.
        if self._events_missing_from_file:
            self._warnings.append(WarningEntry(
                gedcom_file=self._gedcom_filename,
                reason=(
                    f"{self._events_missing_from_file} befintliga händelser "
                    "hittades inte i GEDCOM-filen och lämnades oförändrade."
                ),
            ))
        if self._events_claimed:
            self._warnings.append(WarningEntry(
                gedcom_file=self._gedcom_filename,
                reason=(
                    f"{self._events_claimed} befintliga händelser kopplades "
                    "till GEDCOM-posterna och fick ursprungsmärkning."
                ),
            ))
        if self._residences_claimed:
            self._warnings.append(WarningEntry(
                gedcom_file=self._gedcom_filename,
                reason=(
                    f"{self._residences_claimed} befintliga boenden kopplades "
                    "till GEDCOM-posterna och fick ursprungsmärkning."
                ),
            ))

        # Save updated translation data (staged imports leave the files alone)
        if not self._stage_only:
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
            events_claimed=self._events_claimed,
            residences_added=self._residences_added,
            residences_claimed=self._residences_claimed,
            sources_added=self._sources_added,
            places_added=self._places_added,
            warnings=[str(w) for w in self._warnings],
            merged_identity_matches=list(self._merged_identity_matches),
            ambiguous_records=list(self._ambiguous_records),
            translation=translation_data if self._stage_only else None,
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
        repo_records: Sequence[GedcomLine] = (),
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
        self._process_repository_records(repo_records)
        for record in sour_records:
            self._ctx_xref = record.xref_id
            self._ctx_label = _get_child_value(record, "TITL") or "SOUR"
            gedcom_source = _extract_gedcom_source(record)

            problems: list[SlkProblem] = []
            extras = read_source_fields(record, problems)
            self._report_slk_problems(problems, record.xref_id, "Standardvärde användes")

            # Use translation manager to map (handles existing matching)
            source = self._translation_mgr.map_source(
                gedcom_source, self._project_data.sources,
                leverantorer=self._project_data.leverantorer,
                kalltyper=self._project_data.kalltyper,
                extras=extras,
            )

            # Check if this is a new source (not already in project)
            existing_source_ids = {s.id for s in self._project_data.sources}
            is_new = source.id not in existing_source_ids

            # Level-1 REPO references (Requirement 9.9, 9.10)
            self._attach_repository_refs(record, source)

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
        self._ctx_xref = self._ctx_label = None

    def _process_repository_records(self, repo_records: Sequence[GedcomLine]) -> None:
        """Import every level-0 REPO record: find a Repository or create one.

        Records no SOUR points at are imported too. Matching uses name, type
        and address, so a second import creates nothing. Files without
        SLK_Marker use only the standard tags.
        """
        self._repo_xref_map = {}
        for record in repo_records:
            name = (_get_child_value(record, "NAME") or "").strip()
            if not name:
                self._warnings.append(WarningEntry(
                    gedcom_file=self._gedcom_filename,
                    record_xref=record.xref_id or None,
                    raw_value="REPO",
                    reason="REPO-post utan NAME",
                    action_taken="Ignorerades",
                ))
                continue
            rtype = ""
            xids: list[str] = []
            if self._has_slk_marker:
                problems: list[SlkProblem] = []
                data = read_repository(record, problems)
                self._report_slk_problems(
                    problems, record.xref_id, "Standardvärde användes"
                )
                rtype = getattr(data, "type", "") or ""
                xids = list(getattr(data, "external_ids", []) or [])
            if not rtype and name == "ArkivDigital":
                rtype = "digital_archive"
            address = (_get_child_value(record, "ADDR") or "").strip() or None

            repo = self._find_repository(name, rtype, address)
            if repo is None:
                repo = Repository(
                    id=self._id_gen.generate("repository"),
                    name=name,
                    # The model requires a non-empty type; "archive" is the
                    # neutral default when the file gives none.
                    type=rtype or "archive",
                    address=address,
                    phone=[c.value.strip() for c in _get_children(record, "PHON") if c.value and c.value.strip()],
                    email=[c.value.strip() for c in _get_children(record, "EMAIL") if c.value and c.value.strip()],
                    web=[c.value.strip() for c in _get_children(record, "WWW") if c.value and c.value.strip()],
                    notes="\n".join(c.value for c in _get_children(record, "NOTE") if c.value),
                    external_ids=xids,
                )
                self._project_data.repositories.append(repo)
            if record.xref_id:
                self._repo_xref_map[record.xref_id] = repo.id

    def _find_repository(
        self, name: str, rtype: str, address: Optional[str]
    ) -> Optional[Repository]:
        """Find a Repository by name, type (empty matches any) and address."""
        for repo in self._project_data.repositories:
            if (repo.name or "").strip() != name:
                continue
            if rtype and repo.type != rtype:
                continue
            if ((repo.address or "").strip() or None) != address:
                continue
            return repo
        return None

    def _attach_repository_refs(self, record: GedcomLine, source: Source) -> None:
        """Add a RepositoryRef for each ``1 REPO @Rn@`` of a SOUR record."""
        for repo_line in _get_children(record, "REPO"):
            repo_id = self._repo_xref_map.get((repo_line.value or "").strip())
            if repo_id is None:
                self._warnings.append(WarningEntry(
                    gedcom_file=self._gedcom_filename,
                    record_xref=record.xref_id or None,
                    raw_value=f"REPO {repo_line.value or ''}".strip(),
                    reason="REPO-hänvisningen pekar inte på en REPO-post",
                    action_taken="Ignorerades",
                ))
                continue
            caln = _get_child(repo_line, "CALN")
            ref = RepositoryRef(
                repository_id=repo_id,
                call_number=((caln.value if caln else "") or "").strip(),
                media_type=(
                    ((_get_child_value(caln, "MEDI") or "").strip()) if caln else ""
                ),
                notes="\n".join(
                    c.value for c in _get_children(repo_line, "NOTE") if c.value
                ),
            )
            if self._has_slk_marker:
                problems: list[SlkProblem] = []
                extra = read_repository(repo_line, problems)
                self._report_slk_problems(
                    problems, record.xref_id, "Värdet ignorerades"
                )
                ref.source_type = extra.source_type
                ref.image_number = extra.image_number
                ref.page_number = extra.page_number
                ref.media_name = extra.media_name
            if ref not in source.repository_refs:
                source.repository_refs.append(ref)

    def _attach_arkiv_digital_repository(self, source: Source) -> None:
        """Find or create an ArkivDigital Repository and attach it to a Source.

        If an ArkivDigital repository already exists in the project, reuses it.
        Otherwise, creates a new Repository with name="ArkivDigital" and
        type="digital_archive". Adds a RepositoryRef to the source.

        Args:
            source: The Source to attach the repository reference to.
        """
        # Find existing ArkivDigital repository
        # A source that already points at an ArkivDigital repository (from a
        # REPO record of the file) needs nothing more: one repository, one ref.
        by_id = {r.id: r for r in self._project_data.repositories}
        for ref in source.repository_refs:
            held = by_id.get(ref.repository_id)
            if held is not None and held.name == "ArkivDigital":
                return

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
        # An extraction error is not a Recoverable_Input_Problem: it aborts
        # the import (Requirement 20.23).
        for record in indi_records:
            with self._record_context(
                record.xref_id, self._record_label(record), "personer"
            ):
                gp = _extract_gedcom_person(record)
            incoming_persons.append(gp)
            person_records_by_xref[gp.xref_id] = record

        families: list[GedcomFamily] = []
        for fam_rec in fam_records:
            with self._record_context(fam_rec.xref_id, "FAM", "familjer"):
                families.append(_extract_gedcom_family(fam_rec))

        # Resolve merged identities (aliases) before classification so a
        # record of a merged-away person never creates or updates a person.
        incoming_persons = self._resolve_merged_identities(
            incoming_persons, translation_data
        )

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
            record = person_records_by_xref.get(gedcom_person.xref_id)
            if record is None:
                continue

            with self._record_context(
                record.xref_id, self._record_label(record), "personer"
            ):
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
                    if not self._update_person(gedcom_person, mapping, record):
                        continue

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

    def _resolve_merged_identities(
        self,
        incoming_persons: list[GedcomPerson],
        translation_data: TranslationData,
    ) -> list[GedcomPerson]:
        """Split out records that resolve to a merged identity.

        A record whose xref (or, when the xref is unknown, fingerprint)
        matches an Identity_Alias resolves to the surviving person. Such a
        record is recorded in ``merged_identity_matches`` and changes
        nothing except ``_person_xref_map`` so families attach to the
        survivor. A record that could resolve to more than one active person
        is recorded in ``ambiguous_records`` and assigned to no person.

        Returns:
            The records that still go through ``classify_persons``.
        """
        aliases = translation_data.person_aliases
        if not aliases:
            return incoming_persons

        resolver = RedirectResolver(self._project_data.merge_history)
        persons_by_id = {p.id: p for p in self._project_data.persons}

        def alias_target(person_id: str) -> Optional[str]:
            """Resolved active person for an alias, or ``""`` if ambiguous."""
            resolved = resolver.resolve(person_id)
            if resolved is None:
                return ""
            return resolved if resolved in persons_by_id else None

        alias_by_xref: dict[str, set[str]] = {}
        alias_by_fp: dict[str, set[str]] = {}
        for alias in aliases:
            target = alias_target(alias.person_id)
            if target is None:
                continue
            alias_by_xref.setdefault(alias.gedcom_id, set()).add(target)
            if alias.fingerprint:
                alias_by_fp.setdefault(alias.fingerprint, set()).add(target)

        active_by_xref: dict[str, set[str]] = {}
        active_by_fp: dict[str, set[str]] = {}
        for mapping in translation_data.persons:
            if mapping.app_id in self._retired_ids:
                continue
            active_by_xref.setdefault(mapping.gedcom_id, set()).add(mapping.app_id)
            if mapping.fingerprint:
                active_by_fp.setdefault(mapping.fingerprint, set()).add(mapping.app_id)

        remaining: list[GedcomPerson] = []
        for gp in incoming_persons:
            fp_hash = compute_composite_key_hash(
                given_name=gp.given_name,
                surname=gp.surname,
                birth_date=gp.birth_date,
                birth_place=gp.birth_place,
            )
            matched_by: Optional[str] = None
            targets: set[str] = set()
            competing: set[str] = set()

            if gp.xref_id in alias_by_xref:
                matched_by = "xref"
                targets = set(alias_by_xref[gp.xref_id])
                competing = active_by_xref.get(gp.xref_id, set()) | active_by_fp.get(
                    fp_hash, set()
                )
            elif fp_hash in alias_by_fp and gp.xref_id not in active_by_xref:
                matched_by = "fingerprint"
                targets = set(alias_by_fp[fp_hash])
                competing = active_by_fp.get(fp_hash, set())

            if matched_by is None:
                remaining.append(gp)
                continue

            candidates = targets | competing
            candidates.discard("")
            if "" in targets or len(candidates) > 1:
                self._ambiguous_records.append(
                    AmbiguousRecord(
                        xref=gp.xref_id, candidate_person_ids=sorted(candidates)
                    )
                )
                self._warnings.append(WarningEntry(
                    gedcom_file=self._gedcom_filename,
                    record_xref=gp.xref_id,
                    person_or_family_name=f"{gp.given_name} {gp.surname}".strip() or None,
                    reason="Posten kan höra till flera personer och tilldelades ingen",
                    action_taken="Hoppades över, granska manuellt",
                ))
                continue

            survivor_id = next(iter(candidates))
            self._person_xref_map[gp.xref_id] = survivor_id
            differing = self._differing_fields(gp, persons_by_id[survivor_id])
            self._merged_identity_matches.append(
                MergedIdentityMatch(
                    xref=gp.xref_id,
                    person_id=survivor_id,
                    matched_by=matched_by,
                    differing_fields=differing,
                )
            )
            self._warnings.append(WarningEntry(
                gedcom_file=self._gedcom_filename,
                record_xref=gp.xref_id,
                person_or_family_name=f"{gp.given_name} {gp.surname}".strip() or None,
                reason=(
                    f"Posten tillhör en sammanslagen person ({survivor_id})"
                    + (f"; avvikande fält: {', '.join(differing)}" if differing else "")
                ),
                action_taken="Importerades inte, personen lämnades oförändrad",
            ))
        return remaining

    def _differing_fields(self, gp: GedcomPerson, person: Person) -> list[str]:
        """Names of fields where the GEDCOM record disagrees with ``person``.

        Only values the record actually asserts are compared; read-only.
        """
        differing: list[str] = []

        have_names = {(n.given or "", n.surname or "") for n in person.names}
        incoming_names = []
        if gp.given_name or gp.surname:
            incoming_names.append((gp.given_name, gp.surname))
        incoming_names.extend(gp.additional_names)
        if any(n not in have_names for n in incoming_names):
            differing.append("names")

        if gp.sex and gp.sex != "U" and gp.sex != person.sex:
            differing.append("sex")

        def event_values(event_type: str) -> tuple[set[str], set[str]]:
            dates: set[str] = set()
            places: set[str] = set()
            place_names = {pl.id: pl.name for pl in self._project_data.places}
            for evt in self._project_data.events:
                if evt.type != event_type:
                    continue
                if not any(pt.person_id == person.id for pt in evt.participants):
                    continue
                key = _date_dedup_key(evt.date)
                if key:
                    dates.add(key)
                if evt.place and evt.place.place_id in place_names:
                    places.add(place_names[evt.place.place_id])
            return dates, places

        for label, event_type, raw_date, raw_place in (
            ("birth", "birth", gp.birth_date, gp.birth_place),
            ("death", "death", gp.death_date, gp.death_place),
        ):
            dates, places = event_values(event_type)
            if raw_date and raw_date.strip():
                parsed = parse_gedcom_date(raw_date)
                if parsed is None or _date_dedup_key(parsed.value) not in dates:
                    differing.append(f"{label}_date")
            if raw_place and raw_place.strip():
                raw = raw_place.strip()
                leaf = raw.split(",")[0].strip()
                if raw not in places and leaf not in places:
                    differing.append(f"{label}_place")

        if gp.title and gp.title != (person.title or ""):
            differing.append("title")
        if gp.occupation and gp.occupation != (person.occupation or ""):
            differing.append("occupation")
        if gp.notes and gp.notes.strip() and gp.notes.strip() not in (person.notes or ""):
            differing.append("notes")
        return differing

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
        names = _build_names(gedcom_person)
        self._collect_name_links(names, gedcom_person, record)

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
    ) -> bool:
        """Update an existing Person with data from a GEDCOM re-import.

        Args:
            gedcom_person: The extracted GEDCOM person data.
            mapping: The existing PersonMapping with the App_JSON ID.
            record: The original GedcomLine record (for event extraction).

        Returns:
            False when the mapping names a retired person id (nothing is
            created or changed), True otherwise.
        """
        person_id = mapping.app_id
        if person_id in self._retired_ids:
            self._warnings.append(WarningEntry(
                gedcom_file=self._gedcom_filename,
                record_xref=gedcom_person.xref_id,
                reason="Posten pekar på en person som har slagits samman",
                action_taken="Hoppades över",
            ))
            return False
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
            names = _build_names(gedcom_person)
            self._collect_name_links(names, gedcom_person, record)

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
            return True

        # Update existing person fields
        existing_person.sex = gedcom_person.sex
        existing_person.names = _build_names(
            gedcom_person, existing_person.names
        )
        self._collect_name_links(existing_person.names, gedcom_person, record)
        existing_person.notes = gedcom_person.notes
        existing_person.title = gedcom_person.title
        existing_person.occupation = gedcom_person.occupation
        self._persons_updated += 1

        # Events are matched against the person's existing events by the
        # identity matcher inside _create_person_events (Requirement 10).
        self._create_person_events(person_id, record)
        return True

    def _create_person_events(self, person_id: str, record: GedcomLine) -> None:
        """Create events and residences for a person from GEDCOM event tags.

        The event-bearing children (BIRT, DEAT, BURI, BAPM, CHR, ADOP, EVEN
        and so on) are collected into incoming records and matched once
        against the person's existing events (Requirement 10, 19). Records
        that stand for an existing event leave it untouched; only new records
        create events, each with its Event_Origin. RESI children become
        ResidenceFact entities (not events) and are handled in file order.

        Args:
            person_id: The App_JSON person ID to use as participant.
            record: The INDI GedcomLine record with event children.
        """
        specs: list[_EventSpec] = []
        seen_tokens: set[str] = set()
        for child in record.children:
            spec = self._indi_event_spec(child, person_id)
            if spec is None:
                continue
            if spec.token:
                if spec.token in seen_tokens:
                    # Requirement 1.11: the first structure is used.
                    self._warnings.append(WarningEntry(
                        gedcom_file=self._gedcom_filename,
                        record_xref=record.xref_id or None,
                        raw_value=f"_SLK_EID {spec.token}",
                        reason=(
                            f"Samma _SLK_EID '{spec.token}' förekommer i flera "
                            "händelser på samma person. Den första händelsen "
                            "används och de övriga ignorerades."
                        ),
                        action_taken="Händelsen ignorerades",
                    ))
                    continue
                seen_tokens.add(spec.token)
            specs.append(spec)
        owner_xref = record.xref_id or ""
        results = self._match_owner_events("INDI", person_id, owner_xref, specs)
        result_for = {id(s.record): (s, r) for s, r in zip(specs, results)}
        resi_children = [c for c in record.children if c.tag.upper() == "RESI"]
        resi_results = self._match_person_residences(
            person_id, owner_xref, resi_children
        )
        resi_for = {id(c): r for c, r in zip(resi_children, resi_results)}
        claimed_legacy: list[ResidenceFact] = []

        for child in record.children:
            if child.tag.upper() == "RESI":
                # RESI → ResidenceFact (Requirement 12.7, 12.8, 12.12, 12.13, 22)
                self._apply_residence_result(
                    resi_for[id(child)], child, person_id, owner_xref, claimed_legacy
                )
                continue
            pair = result_for.get(id(child))
            if pair is None:
                continue
            spec, res = pair
            if self._join_event_by_token(spec, res, person_id, owner_xref):
                continue
            event_id = self._apply_event_result(
                res,
                spec,
                "INDI",
                person_id,
                owner_xref,
                [person_id],
                lambda origin, s=spec: self._create_event(
                    event_type=s.event_type,
                    event_record=s.record,
                    participant_id=person_id,
                    participant_role=s.role,
                    custom_type_name=s.custom_type_name,
                    origin=origin,
                    from_place=s.from_place,
                ),
            )
            self._register_event_token(spec, res, event_id)
            if event_id is not None and spec.placement:
                # ADOP and EVEN/TYPE Fosterhem are placement START events,
                # finalised once the families exist (Requirements 11.7, 11.7a).
                # Only newly created events take part.
                end_date = self._apply_placement_period(event_id, child)
                self._imported_placement_events.append(
                    (
                        event_id,
                        person_id,
                        _get_child_value(child, "FAMC"),
                        end_date,
                    )
                )
        self._report_legacy_residence_duplicates(
            person_id, owner_xref, claimed_legacy
        )

    # ------------------------------------------------------------------
    # Event identity (Requirements 10 and 19)
    # ------------------------------------------------------------------

    def _indi_event_spec(
        self, child: GedcomLine, person_id: str
    ) -> Optional["_EventSpec"]:
        """Classify an INDI child record as an event, or return None."""
        tag = child.tag.upper()
        if tag != "ADOP" and tag not in _INDI_EVENT_TAGS and tag != "EVEN":
            return None
        tags = self._event_tag_data(child, self._xref_for_person_id(person_id))
        spec = self._indi_event_spec_base(child, tag, tags, person_id)
        # Placement events derive their roles on import; _SLK_ROLE is ignored.
        role = "subject" if spec.placement else (tags.role or "subject")
        spec.role = role
        spec.participants = [(person_id, role)]
        spec.token = tags.token
        if spec.event_type == "flytt":
            spec.from_place = tags.from_place
        return spec

    def _event_tag_data(
        self, record: GedcomLine, owner_xref: Optional[str]
    ) -> EventTagData:
        """Read the ``_SLK_`` event tags of *record*; problems become warnings."""
        problems: list[SlkProblem] = []
        data = read_event_tags(record, problems)
        self._report_slk_problems(problems, owner_xref, "Taggen ignorerades")
        return data

    def _indi_event_spec_base(
        self,
        child: GedcomLine,
        tag: str,
        tags: EventTagData,
        person_id: str,
    ) -> "_EventSpec":
        """The type, tag key and custom name of an INDI event record."""
        participants = [(person_id, "subject")]
        if tag == "ADOP":
            return _EventSpec(
                record=child,
                event_type="adoption",
                tag_key=_event_tag_key(tag, None),
                participants=participants,
                placement=True,
            )
        if tag in _INDI_EVENT_TAGS:
            return _EventSpec(
                record=child,
                event_type=_INDI_EVENT_TAGS[tag],
                tag_key=_event_tag_key(tag, None),
                participants=participants,
            )
        custom_type_name = _get_child_value(child, "TYPE")
        normalized = custom_type_name.strip().lower() if custom_type_name else ""
        tag_key = _event_tag_key(tag, custom_type_name)
        if tags.evtype:
            if tags.evtype_known:
                event_type = tags.evtype
                return _EventSpec(
                    child,
                    event_type,
                    tag_key,
                    participants,
                    custom_type_name=(
                        custom_type_name if event_type.startswith("custom_") else None
                    ),
                    placement=event_type == "foster_home",
                )
            owner = self._xref_for_person_id(person_id)
            self._warnings.append(WarningEntry(
                gedcom_file=self._gedcom_filename,
                record_xref=owner,
                raw_value=f"_SLK_EVTYPE {tags.evtype}",
                reason=(
                    f'Okänd händelsetyp "{tags.evtype}" i _SLK_EVTYPE. '
                    "Händelsen skapades som en egen händelse."
                ),
                action_taken="Skapades som egen händelse",
            ))
            return _EventSpec(
                child,
                "custom_individual_event",
                tag_key,
                participants,
                custom_type_name=custom_type_name or tags.evtype,
            )
        if normalized == "flytt":
            return _EventSpec(child, "flytt", tag_key, participants)
        if normalized == "fosterhem":
            return _EventSpec(
                child, "foster_home", tag_key, participants, placement=True
            )
        return _EventSpec(
            child,
            "custom_individual_event",
            tag_key,
            participants,
            custom_type_name=custom_type_name,
        )

    def _fam_event_spec(
        self, child: GedcomLine, participants: list[tuple[str, str]]
    ) -> Optional["_EventSpec"]:
        """Classify a FAM child record as an event, or return None."""
        tag = child.tag.upper()
        spec: Optional[_EventSpec] = None
        if tag in _FAM_EVENT_TAGS:
            spec = _EventSpec(
                record=child,
                event_type=_FAM_EVENT_TAGS[tag],
                tag_key=_event_tag_key(tag, None),
                participants=participants,
            )
        elif tag == "EVEN":
            custom_type_name = _get_child_value(child, "TYPE")
            spec = _EventSpec(
                record=child,
                event_type="custom_family_event",
                tag_key=_event_tag_key(tag, custom_type_name),
                participants=participants,
                custom_type_name=custom_type_name,
            )
        if spec is not None:
            spec.token = self._event_tag_data(child, None).token
        return spec

    def _get_event_index(self) -> "_EventIndex":
        if self._event_index is None:
            self._event_index = _EventIndex(self._project_data.events)
        return self._event_index

    def _match_owner_events(
        self,
        owner_kind: str,
        owner_id: str,
        owner_xref: str,
        specs: list["_EventSpec"],
        legacy_event_ids: Sequence[str] = (),
    ) -> list[MatchResult]:
        """Match the event records of one owner against existing events.

        Builds the pool (events whose origin names this owner), the legacy
        pool (events of the owner without origin) and the foreign objects
        (events of the owner whose origin names another owner of the same
        kind), then calls the identity matcher once. Also counts the
        origin groups of the owner that no record claimed.

        Args:
            owner_kind: ``"INDI"`` or ``"FAM"``.
            owner_id: The app id the importer resolved for the owner record.
            owner_xref: The GEDCOM xref of the owner record (informational).
            specs: The event records of the owner in file order.
            legacy_event_ids: For ``FAM``, the ids in ``Family.event_ids``.
        """
        index = self._get_event_index()
        # One pool entry per origin that names this owner: an event merged from
        # several INDI records has one origin per record (Origin_Group rule).
        pool = [
            PoolEntry(e, o)
            for e in index.by_origin_owner.get((owner_kind, owner_id), [])
            for o in _event_origins(e)
            if (o.owner_kind, o.owner_id) == (owner_kind, owner_id)
        ]
        if owner_kind == "INDI":
            related = index.by_participant.get(owner_id, [])
        else:
            related = [index.by_id[i] for i in legacy_event_ids if i in index.by_id]
        legacy: list[Event] = []
        foreign: list[Event] = []
        for e in related:
            if e.origin is None:
                legacy.append(e)
            elif e.origin.owner_kind == owner_kind and e.origin.owner_id != owner_id:
                if not any(
                    (o.owner_kind, o.owner_id) == (owner_kind, owner_id)
                    for o in e.extra_origins
                ):
                    foreign.append(e)

        counters: dict[str, int] = {}
        incoming: list[IncomingRecord] = []
        for spec in specs:
            n = counters.get(spec.tag_key, 0)
            counters[spec.tag_key] = n + 1
            uid = (_get_child_value(spec.record, "_UID") or "").strip() or None
            incoming.append(
                IncomingRecord(
                    kind="event",
                    owner_kind=owner_kind,
                    owner_id=owner_id,
                    owner_xref=owner_xref,
                    tag_key=spec.tag_key,
                    index=n,
                    record_hash=record_hash(
                        spec.record, self._source_xref_map, self._hash_profile
                    ),
                    uid=uid,
                    fingerprint=lambda s=spec: self._incoming_event_fingerprint(s),
                )
            )

        results = match_records(incoming, pool, legacy, foreign)

        claimed = {id(m) for r in results for m in r.members}
        for group in build_origin_groups(pool):
            if not any(id(m) in claimed for m in group.members):
                self._events_missing_from_file += 1
        return results

    def _incoming_event_fingerprint(self, spec: "_EventSpec") -> str:
        """Content fingerprint of the event the importer would create."""
        date_str = _get_child_value(spec.record, "DATE")
        parsed = parse_gedcom_date(date_str or "")
        cause: Optional[str] = _get_child_value(spec.record, "CAUS") or None
        event = Event(
            id="",
            type=spec.event_type,
            participants=[Participant(person_id=p, role=r) for p, r in spec.participants],
            date=parsed.value if parsed is not None else None,
            place=self._event_place_ref(spec.record, apply_coordinates=False),
            cause_of_death=cause,
            custom_type_name=spec.custom_type_name,
        )
        return event_fingerprint(event)

    def _event_label(self, event_type: str, custom_type_name: Optional[str]) -> str:
        try:
            from slaktbusken.ui.swedish_locale import get_event_type_label
        except ImportError:  # label is cosmetic: UI module not available
            label = event_type
        else:
            label = get_event_type_label(event_type)
        if event_type.startswith("custom_") and custom_type_name:
            label = custom_type_name
        return label

    def _event_person_label(self, person_ids: list[str]) -> str:
        names = [
            n for n in (self._display_name_for_person_id(p) for p in person_ids) if n
        ]
        return " och ".join(names) if names else "okänd person"

    def _describe_event(self, event: Event) -> str:
        label = self._event_label(event.type, event.custom_type_name)
        date = event.date
        text = ""
        if date is not None:
            text = date.value or date.original_text or ""
        return f"{label} {text or 'utan datum'} ({event.id})"

    def _apply_event_result(
        self,
        res: MatchResult,
        spec: "_EventSpec",
        owner_kind: str,
        owner_id: str,
        owner_xref: str,
        person_ids: list[str],
        create: Callable[[RecordOrigin], Optional[str]],
    ) -> Optional[str]:
        """Act on one matcher result; return the id of a newly created event.

        ``UNCHANGED`` writes nothing. ``CHANGED_UID`` writes nothing and
        logs a notice. ``LEGACY_CLAIMED`` only sets ``origin`` on the claimed
        event. ``NEW`` and ``NEW_AMBIGUOUS`` create the event through
        *create* with its origin; the latter also logs a notice. The origin's
        ``index`` is informational and never rewritten.
        """
        outcome = res.outcome
        if outcome is Outcome.UNCHANGED:
            return None
        label = self._event_label(spec.event_type, spec.custom_type_name)
        person_label = self._event_person_label(person_ids)
        if outcome is Outcome.CHANGED_UID:
            self._warnings.append(WarningEntry(
                gedcom_file=self._gedcom_filename,
                record_xref=owner_xref or None,
                reason=(
                    f"GEDCOM-posten för händelsen {label} ({person_label}) har "
                    "ändrats sedan importen men har samma _UID. Den befintliga "
                    "händelsen lämnades oförändrad."
                ),
            ))
            return None

        rec = res.incoming
        origin = RecordOrigin(
            owner_kind=owner_kind,
            owner_id=owner_id,
            owner_xref=owner_xref,
            tag_key=rec.tag_key,
            index=rec.index,
            record_hash=rec.record_hash,
            uid=rec.uid,
            instance=res.instance or 0,
        )
        if outcome is Outcome.LEGACY_CLAIMED:
            event = res.members[0]
            event.origin = origin
            self._events_claimed += 1
            self._get_event_index().note_origin(event)
            return None

        event_id = create(origin)
        if event_id is not None and outcome is Outcome.NEW_AMBIGUOUS:
            shown = [self._describe_event(c) for c in res.candidates[:5]]
            listing = ", ".join(shown)
            if len(res.candidates) > 5:
                listing += f" och {len(res.candidates) - 5} till"
            self._warnings.append(WarningEntry(
                gedcom_file=self._gedcom_filename,
                record_xref=owner_xref or None,
                reason=(
                    f"En ny händelse {label} ({event_id}) skapades för "
                    f"{person_label} eftersom GEDCOM-posten inte kunde kopplas "
                    "till en befintlig händelse. Befintliga händelser som inte "
                    f"kopplades: {listing}. Granska och ta bort det som är "
                    "inaktuellt."
                ),
            ))
        return event_id

    # ------------------------------------------------------------------
    # Event_Token join (Requirements 1.8 to 1.14, 8.9)
    # ------------------------------------------------------------------

    def _join_event_by_token(
        self,
        spec: "_EventSpec",
        res: MatchResult,
        person_id: str,
        owner_xref: str,
    ) -> bool:
        """Add an INDI structure to the event of its token; True when joined.

        Joins only by equal Event_Token within this file, never by date,
        place, type or participants. Only a record that the matcher found
        no event for (``NEW`` or ``NEW_AMBIGUOUS``) joins: the participant is
        added to the event the token stands for, and one RecordOrigin of this
        INDI record is added to that event, so a second import of the file
        matches every contributing record and creates nothing. Returns False
        when the record must be handled as usual.
        """
        if not spec.token or spec.placement:
            return False
        if res.outcome not in (Outcome.NEW, Outcome.NEW_AMBIGUOUS):
            return False
        event_id = self._event_token_map.get(spec.token)
        event = self._get_event_index().by_id.get(event_id) if event_id else None
        if event is None:
            return False
        if not any(p.person_id == person_id for p in event.participants):
            event.participants.append(Participant(person_id=person_id, role=spec.role))
        rec = res.incoming
        origin = RecordOrigin(
            owner_kind="INDI",
            owner_id=person_id,
            owner_xref=owner_xref,
            tag_key=rec.tag_key,
            index=rec.index,
            record_hash=rec.record_hash,
            uid=rec.uid,
            instance=res.instance or 0,
        )
        # Every event in the token map was created here or matched through
        # its origin, so it has a first ``origin``; this record adds one more.
        event.extra_origins.append(origin)
        index = self._get_event_index()
        index.note_origin(event)
        index.note_participant(event, person_id)
        return True

    def _register_event_token(
        self, spec: "_EventSpec", res: MatchResult, new_event_id: Optional[str]
    ) -> None:
        """Remember the event of *spec* for its token (Requirement 8.9).

        The event is the one just created, or the existing event the record
        stands for. When a matched existing event arrives after the token
        already stands for an event created earlier in this run (the file
        lists the INDI of a new participant first), the new event is folded
        into the matched one so that no token ends up with two events.
        """
        if not spec.token:
            return
        target: Optional[str] = new_event_id
        if target is None and res.outcome in (
            Outcome.UNCHANGED, Outcome.CHANGED_UID, Outcome.LEGACY_CLAIMED
        ):
            members = [m for m in res.members if isinstance(m, Event)]
            target = members[0].id if members else None
        if target is None:
            return
        current = self._event_token_map.get(spec.token)
        if current is None:
            self._event_token_map[spec.token] = target
            return
        if (
            current != target
            and new_event_id is None
            and current in self._run_created_event_ids
            and not spec.placement
        ):
            self._fold_event(current, target)

    def _fold_event(self, source_id: str, target_id: str) -> None:
        """Move participants and origins of a run-created event into *target_id*."""
        index = self._get_event_index()
        source = index.by_id.get(source_id)
        target = index.by_id.get(target_id)
        if source is None or target is None or source is target:
            return
        for participant in source.participants:
            if not any(p.person_id == participant.person_id for p in target.participants):
                target.participants.append(participant)
                index.note_participant(target, participant.person_id)
        # The target is a matched event, so it has its own ``origin``; the
        # origins of the folded event become further origins of the target.
        target.extra_origins.extend(_event_origins(source))
        index.note_origin(target)
        for position, listed in enumerate(self._project_data.events):
            if listed is source:
                self._project_data.events.pop(position)
                break
        index.remove(source)
        self._run_created_event_ids.discard(source_id)
        self._events_added -= 1
        for token, event_id in list(self._event_token_map.items()):
            if event_id == source_id:
                self._event_token_map[token] = target_id

    def _process_family_events(
        self,
        gedcom_family: GedcomFamily,
        record: GedcomLine,
        family_id: str,
        existing_event_ids: Sequence[str] = (),
    ) -> list[str]:
        """Match the FAM event records and create the new ones.

        Returns the ids of newly created events only. Existing events are
        never removed or modified (Requirement 10.14).
        """
        participant_ids: list[tuple[str, str]] = []
        for xref in (gedcom_family.husb_xref, gedcom_family.wife_xref):
            if xref:
                pid = self._person_xref_map.get(xref)
                if pid:
                    participant_ids.append((pid, "spouse"))
        if not participant_ids:
            return []

        specs: list[_EventSpec] = []
        for child_node in record.children:
            spec = self._fam_event_spec(child_node, participant_ids)
            if spec is not None:
                spec.participants = self._slk_event_participants(
                    child_node, participant_ids, record.xref_id
                )
                specs.append(spec)
        owner_xref = record.xref_id or gedcom_family.xref_id or ""
        results = self._match_owner_events(
            "FAM", family_id, owner_xref, specs, existing_event_ids
        )
        new_ids: list[str] = []
        for spec, res in zip(specs, results):
            event_id = self._apply_event_result(
                res,
                spec,
                "FAM",
                family_id,
                owner_xref,
                [pid for pid, _role in participant_ids],
                lambda origin, s=spec: self._create_family_event(
                    event_type=s.event_type,
                    event_record=s.record,
                    participants=s.participants,
                    custom_type_name=s.custom_type_name,
                    origin=origin,
                ),
            )
            self._register_event_token(spec, res, event_id)
            if event_id:
                new_ids.append(event_id)
        return new_ids

    # ------------------------------------------------------------------
    # Residence identity (Requirement 22)
    # ------------------------------------------------------------------

    def _get_residence_index(self) -> "_ResidenceIndex":
        if self._residence_index is None:
            self._residence_index = _ResidenceIndex(self._project_data.residences)
        return self._residence_index

    def _match_person_residences(
        self, person_id: str, owner_xref: str, resi_children: list[GedcomLine]
    ) -> list[MatchResult]:
        """Match the RESI children of one person against existing residences.

        Pool: residences of the person with an origin naming this person.
        Legacy: residences of the person without origins. Foreign: residences
        of the person whose origins all name another INDI owner.
        """
        if not resi_children:
            return []
        owner = ("INDI", person_id)
        pool: list[PoolEntry] = []
        legacy: list[ResidenceFact] = []
        foreign: list[ResidenceFact] = []
        # Residences with an origin on this owner may belong to the person
        # only through the origin, so look at the person's list plus any
        # residence carrying one of the owner's origins.
        candidates = list(self._get_residence_index().by_person.get(person_id, []))
        for fact in candidates:
            if not fact.origins:
                legacy.append(fact)
                continue
            own = [o for o in fact.origins if (o.owner_kind, o.owner_id) == owner]
            if own:
                pool.extend(PoolEntry(fact, o) for o in own)
            elif any(
                o.owner_kind == "INDI" and o.owner_id != person_id
                for o in fact.origins
            ):
                foreign.append(fact)

        counters: dict[str, int] = {}
        incoming: list[IncomingRecord] = []
        for child in resi_children:
            n = counters.get("RESI", 0)
            counters["RESI"] = n + 1
            uid = (_get_child_value(child, "_UID") or "").strip() or None
            incoming.append(
                IncomingRecord(
                    kind="residence",
                    owner_kind="INDI",
                    owner_id=person_id,
                    owner_xref=owner_xref,
                    tag_key="RESI",
                    index=n,
                    record_hash=record_hash(
                        child, self._source_xref_map, self._hash_profile
                    ),
                    uid=uid,
                    fingerprint=lambda c=child: self._incoming_residence_fingerprint(
                        person_id, c
                    ),
                )
            )
        return match_records(incoming, pool, legacy, foreign)

    def _incoming_residence_fingerprint(
        self, person_id: str, resi_record: GedcomLine
    ) -> str:
        """Content fingerprint of the residence the importer would create."""
        place_id = self._lookup_residence_place_id(resi_record, apply_coordinates=False)[0]
        return residence_fingerprint(
            self._derive_residence(resi_record, person_id, place_id),
            ignore_links=True,
        )

    def _describe_residence(self, fact: ResidenceFact) -> str:
        place = fact.place_id or "utan plats"
        for p in self._project_data.places:
            if p.id == fact.place_id:
                place = getattr(p, "name", None) or place
                break
        start = fact.start.latest or fact.start.earliest or ""
        end = fact.end.earliest or fact.end.latest or ""
        period = f"{start}–{end}" if (start or end) else "utan datum"
        return f"{place} {period} ({fact.id})"

    def _apply_residence_result(
        self,
        res: MatchResult,
        resi_record: GedcomLine,
        person_id: str,
        owner_xref: str,
        claimed_legacy: list[ResidenceFact],
    ) -> None:
        """Act on one matcher result for a RESI record.

        ``UNCHANGED`` writes nothing at all (every member of a claimed
        Origin_Group stays as it is). ``CHANGED_UID`` writes a notice only.
        ``LEGACY_CLAIMED`` sets ``origins`` on the claimed residence.
        ``NEW`` and ``NEW_AMBIGUOUS`` create one residence.
        """
        outcome = res.outcome
        if outcome is Outcome.UNCHANGED:
            return
        person_label = self._display_name_for_person_id(person_id) or "okänd person"
        if outcome is Outcome.CHANGED_UID:
            self._warnings.append(WarningEntry(
                gedcom_file=self._gedcom_filename,
                record_xref=owner_xref or None,
                reason=(
                    f"GEDCOM-posten för ett boende ({person_label}) har ändrats "
                    "sedan importen men har samma _UID. Det befintliga boendet "
                    "lämnades oförändrat."
                ),
            ))
            return

        rec = res.incoming
        origin = RecordOrigin(
            owner_kind="INDI",
            owner_id=person_id,
            owner_xref=owner_xref,
            tag_key=rec.tag_key,
            index=rec.index,
            record_hash=rec.record_hash,
            uid=rec.uid,
            instance=res.instance or 0,
        )
        if outcome is Outcome.LEGACY_CLAIMED:
            fact = res.members[0]
            fact.origins = [origin]
            self._residences_claimed += 1
            claimed_legacy.append(fact)
            return

        place_id = self._resolve_residence_place(resi_record, person_id)
        problems: list[SlkProblem] = []
        residence = self._derive_residence(resi_record, person_id, place_id, problems)
        self._report_slk_problems(problems, owner_xref, "Värdet ignorerades")
        self._warn_residence_date(resi_record)
        residence_id = self._add_residence(residence, origin)
        event_links.collect_endpoint_links(
            self._event_link_requests, residence, resi_record, owner_xref
        )
        if outcome is Outcome.NEW_AMBIGUOUS:
            shown = [self._describe_residence(c) for c in res.candidates[:5]]
            listing = ", ".join(shown)
            if len(res.candidates) > 5:
                listing += f" och {len(res.candidates) - 5} till"
            self._warnings.append(WarningEntry(
                gedcom_file=self._gedcom_filename,
                record_xref=owner_xref or None,
                reason=(
                    f"Ett nytt boende ({residence_id}) skapades för {person_label} "
                    "eftersom GEDCOM-posten inte kunde kopplas till ett "
                    "befintligt boende. Befintliga boenden som inte kopplades: "
                    f"{listing}. Granska och ta bort det som är inaktuellt."
                ),
            ))

    def _report_legacy_residence_duplicates(
        self,
        person_id: str,
        owner_xref: str,
        claimed_legacy: list[ResidenceFact],
    ) -> None:
        """Notice for identical unclaimed legacy residences (Requirement 22.16)."""
        if not claimed_legacy:
            return
        remaining = [
            f
            for f in self._get_residence_index().by_person.get(person_id, [])
            if not f.origins
        ]
        person_label = self._display_name_for_person_id(person_id) or "okänd person"
        reported: set[str] = set()
        for fact in claimed_legacy:
            fp = residence_fingerprint(fact)
            if fp in reported:
                continue
            reported.add(fp)
            n = sum(1 for f in remaining if residence_fingerprint(f) == fp)
            if n:
                self._warnings.append(WarningEntry(
                    gedcom_file=self._gedcom_filename,
                    record_xref=owner_xref or None,
                    reason=(
                        f"{n} identiska boenden för {person_label} lämnades "
                        "orörda. De kan vara dubbletter från tidigare importer."
                    ),
                ))

    def _lookup_residence_place_id(
        self, resi_record: GedcomLine, apply_coordinates: bool
    ) -> tuple[str, Optional[GedcomLine]]:
        """Resolve the PLAC of a RESI record to a place id ("" when none)."""
        plac_rec = _get_child(resi_record, "PLAC")
        place_id = ""
        if plac_rec:
            resolved = self._resolve_place_from_adpl(plac_rec)
            if resolved is None and plac_rec.value:
                resolved = self._resolve_place(plac_rec.value)
            if resolved:
                place_id = resolved
                if apply_coordinates:
                    self._apply_coordinates(resolved, plac_rec)
        return place_id, plac_rec

    def _resolve_residence_place(
        self, resi_record: GedcomLine, person_id: str
    ) -> str:
        """Resolve the place of a RESI record to be created.

        Side effects (F27): places, place mappings, coordinates and the
        warning for a residence without usable place.
        """
        place_id, plac_rec = self._lookup_residence_place_id(
            resi_record, apply_coordinates=True
        )
        if not place_id:
            raw_place_value = plac_rec.value if plac_rec else None
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
        return place_id

    def _warn_residence_date(self, resi_record: GedcomLine) -> None:
        date_str = _get_child_value(resi_record, "DATE")
        if date_str and date_str.strip() and not _parse_resi_date(date_str).interpretable:
            self._warnings.append(WarningEntry(
                gedcom_file=self._gedcom_filename,
                record_xref=None,
                person_or_family_name=None,
                raw_value=date_str,
                reason="Kunde inte tolka datumraden för RESI – boendet importerades utan period.",
                action_taken="Importerades utan period",
            ))

    def _derive_residence(
        self,
        resi_record: GedcomLine,
        person_id: str,
        place_id: str,
        problems: Optional[list[SlkProblem]] = None,
    ) -> ResidenceFact:
        """Build the residence a RESI record stands for (pure, empty id).

        DATE mapping: FROM x TO y gives start.latest = x and end.earliest = y;
        BET x AND y gives start.earliest/latest; a plain date gives
        start.latest = end.earliest; anything else leaves both unknown.
        """
        # Pure: problems are only collected when the caller passes a list
        # (the fingerprint path calls this without one).
        date_result = _parse_resi_date(_get_child_value(resi_record, "DATE"))
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
        # Requirement 7.5: a usable _SLK_START/_SLK_END replaces the whole
        # endpoint built from DATE.
        slk_start = read_endpoint(_get_child(resi_record, "_SLK_START"), problems)
        if slk_start is not None:
            start = Endpoint(
                earliest=slk_start.earliest,
                latest=slk_start.latest,
                precision=slk_start.precision,
                note=slk_start.note,
            )
        slk_end = read_endpoint(_get_child(resi_record, "_SLK_END"), problems)
        if slk_end is not None:
            end = Endpoint(
                earliest=slk_end.earliest,
                latest=slk_end.latest,
                precision=slk_end.precision,
                note=slk_end.note,
            )

        role, notes = read_residence_texts(resi_record, problems)

        # Requirement 7.7: legacy prose, only for files without SLK_Marker.
        legacy = None
        if not self._has_slk_marker:
            legacy = read_legacy_prose(resi_record, problems)
            if slk_start is None and legacy.start_earliest:
                start.earliest = legacy.start_earliest
            if slk_end is None and legacy.end_latest:
                end.latest = legacy.end_latest
            if not role and legacy.role_in_household:
                role = legacy.role_in_household

        observations: list[Observation] = []
        for sour_child in _get_children(resi_record, "SOUR"):
            if sour_child.value:
                source_id = self._source_xref_map.get(sour_child.value)
                if source_id:
                    cit = read_citation(sour_child, problems)
                    observed_from, observed_to = cit.observed_from, cit.observed_to
                    if legacy is not None and not (observed_from or observed_to):
                        # Read this SOUR alone so the period cannot attach to
                        # another citation of the same source.
                        own = read_legacy_prose(
                            GedcomLine(
                                level=resi_record.level, tag=resi_record.tag,
                                value=None, xref_id=None,
                                line_number=resi_record.line_number,
                                children=[sour_child],
                            ),
                        )
                        if own.observations:
                            observed_from = own.observations[0].observed_from
                            observed_to = own.observations[0].observed_to
                    observations.append(
                        Observation(
                            source_ref=SourceRef(
                                source_id=source_id,
                                quality=cit.quality,
                                note=cit.note,
                                aspects=list(cit.aspects),
                            ),
                            observed_from=observed_from,
                            observed_to=observed_to,
                            page_note=cit.page,
                        )
                    )
        return ResidenceFact(
            id="",
            person_id=person_id,
            place_id=place_id,
            start=start,
            end=end,
            role_in_household=role,
            observations=observations,
            notes=notes,
        )

    def _add_residence(self, residence: ResidenceFact, origin: RecordOrigin) -> str:
        """Issue the id, set the single origin and append the residence."""
        residence.id = self._id_gen.generate("residence")
        residence.origins = [origin]
        self._project_data.residences.append(residence)
        self._get_residence_index().add(residence)
        self._residences_added += 1
        return residence.id
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
            for famc in _get_children(record, "FAMC"):
                if famc.value:
                    self._famc_nodes.setdefault((child_xref, famc.value), famc)

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
            with self._record_context(record.xref_id, "FAM", "familjer"):
                self._process_one_family(
                    record, translation_data, family_mapping_by_xref
                )

    def _process_one_family(
        self,
        record: GedcomLine,
        translation_data: TranslationData,
        family_mapping_by_xref: dict[str, FamilyMapping],
    ) -> None:
        """Create or update the family of one FAM record."""
        gedcom_family = _extract_gedcom_family(record)
        existing_mapping = family_mapping_by_xref.get(gedcom_family.xref_id)

        # Two merged records listed as husband and wife resolve to one
        # person: drop the second partner (no self-partner family).
        husb_id = self._person_xref_map.get(gedcom_family.husb_xref or "")
        wife_id = self._person_xref_map.get(gedcom_family.wife_xref or "")
        if husb_id and husb_id == wife_id:
            gedcom_family.wife_xref = None
            self._warnings.append(WarningEntry(
                gedcom_file=self._gedcom_filename,
                record_xref=gedcom_family.xref_id,
                reason=(
                    f"Båda partnerna i familjen {gedcom_family.xref_id} "
                    "pekar på samma person."
                ),
                action_taken="Den andra partnern ignorerades",
            ))

        if existing_mapping:
            self._update_family(gedcom_family, existing_mapping, record)
        else:
            self._create_family(gedcom_family, record, translation_data)

    def _collect_name_links(
        self, names: list[Name], gp: GedcomPerson, record: GedcomLine
    ) -> None:
        """Queue the ``_SLK_EREF`` of each NAME of an INDI record."""
        tokens = [
            event_links.read_eref(n) for n in _get_children(record, "NAME")
        ]
        # _build_names skips an empty primary name; its entries then start
        # at the second NAME.
        offset = 0 if (gp.given_name or gp.surname) else 1
        event_links.collect_name_links(
            self._event_link_requests, names, tokens, offset, gp.xref_id
        )

    def _resolve_event_links(self) -> None:
        """Set ``event_id`` of names and endpoints from the token map."""
        requests = self._event_link_requests
        self._event_link_requests = []

        def warn(request: event_links.LinkRequest) -> None:
            self._warnings.append(WarningEntry(
                gedcom_file=self._gedcom_filename,
                record_xref=request.xref or None,
                raw_value=f"_SLK_EREF {request.token}",
                reason=(
                    f"_SLK_EREF '{request.token}' pekar på en händelse som "
                    "inte finns i filen"
                    + (f" (rad {request.line_number})" if request.line_number else "")
                    + ". Länken till händelsen ignorerades."
                ),
                action_taken="Värdet ignorerades",
            ))

        event_links.resolve_event_links(
            requests,
            self._event_token_map,
            {e.id for e in self._project_data.events},
            warn,
        )

    def _report_slk_problems(
        self,
        problems: list[SlkProblem],
        record_xref: Optional[str],
        action: str,
    ) -> None:
        """Turn Recoverable_Input_Problems of the tolerant readers into warnings."""
        for problem in problems:
            self._warnings.append(WarningEntry(
                gedcom_file=self._gedcom_filename,
                record_xref=record_xref or None,
                raw_value=problem.tag or None,
                reason=(
                    f"{problem.message} (rad {problem.line_number})"
                    if problem.line_number
                    else problem.message
                ),
                action_taken=action,
            ))

    def _build_partners(
        self, gedcom_family: GedcomFamily, record: GedcomLine
    ) -> tuple[list[FamilyPartner], bool]:
        """Build the partner list of a FAM record.

        Returns ``(partners, from_slk)``. When ``_SLK_PARTNER`` names exactly
        the persons of HUSB and WIFE the partners get its order and roles
        (``from_slk`` is true); otherwise HUSB and WIFE give the roles
        ``husband`` and ``wife`` as before. Nothing here reads or sets
        ``Person.sex``.
        """
        problems: list[SlkProblem] = []
        slk = read_partners(record, None, problems)
        self._report_slk_problems(
            problems, gedcom_family.xref_id, "_SLK_PARTNER ignorerades"
        )
        partners: list[FamilyPartner] = []
        if slk is not None:
            seen: set[str] = set()
            for xref, role in slk:
                person_id = self._person_xref_map.get(xref)
                if person_id and person_id not in seen:
                    seen.add(person_id)
                    partners.append(FamilyPartner(person_id=person_id, role=role))
            return partners, True

        if gedcom_family.husb_xref:
            husb_id = self._person_xref_map.get(gedcom_family.husb_xref)
            if husb_id:
                partners.append(FamilyPartner(person_id=husb_id, role="husband"))
        if gedcom_family.wife_xref:
            wife_id = self._person_xref_map.get(gedcom_family.wife_xref)
            if wife_id:
                partners.append(FamilyPartner(person_id=wife_id, role="wife"))
        return partners, False

    def _build_parent_child_links(
        self, gedcom_family: GedcomFamily, partners: list[FamilyPartner]
    ) -> list[ParentChildLink]:
        """Build the ParentChildLinks of a family.

        The parentage type of a child comes from ``FAMC``/``PEDI`` and applies
        to both parents (PEDI qualifies the child's membership). Entries of
        ``_SLK_PLINK`` under the child's ``FAMC`` set the type per parent and
        replace the PEDI type for the parents they cover.
        """
        links: list[ParentChildLink] = []
        partner_ids = [p.person_id for p in partners]
        for child_xref in gedcom_family.child_xrefs:
            child_id = self._person_xref_map.get(child_xref)
            if not child_id:
                continue
            pedi_type = self._parentage_type_for(child_xref, gedcom_family.xref_id)
            famc = self._famc_nodes.get((child_xref, gedcom_family.xref_id))
            problems: list[SlkProblem] = []
            plinks = read_plinks(famc, self._person_xref_map.keys(), problems) if famc is not None else []
            if not plinks:
                self._report_slk_problems(
                    problems, child_xref, "PEDI användes"
                )
                for partner in partners:
                    links.append(ParentChildLink(
                        child_id=child_id,
                        parent_id=partner.person_id,
                        parentage_type=pedi_type,
                    ))
                continue

            by_parent: dict[str, str] = {}
            parentless: list[ParentChildLink] = []
            for plink in plinks:
                link_type = plink.parentage_type or pedi_type
                parent_id = (
                    self._person_xref_map.get(plink.parent_xref)
                    if plink.parent_xref
                    else None
                )
                if parent_id is None:
                    if link_type == "unknown_donor":
                        parentless.append(ParentChildLink(
                            child_id=child_id,
                            parent_id=None,
                            parentage_type=link_type,
                        ))
                    else:
                        problems.append(SlkProblem(
                            "plink_no_parent",
                            "_SLK_PLINK utan förälder har typen "
                            f"'{link_type}'; länken hoppades över.",
                            "_SLK_PLINK",
                        ))
                elif parent_id not in partner_ids or parent_id in by_parent:
                    problems.append(SlkProblem(
                        "plink_not_partner",
                        "_SLK_PLINK pekar på en person som inte är (ensam) "
                        "partner i familjen; länken hoppades över.",
                        "_SLK_PLINK",
                    ))
                else:
                    by_parent[parent_id] = link_type
            self._report_slk_problems(problems, child_xref, "PEDI användes")
            for parent_id in partner_ids:
                links.append(ParentChildLink(
                    child_id=child_id,
                    parent_id=parent_id,
                    parentage_type=by_parent.get(parent_id, pedi_type),
                ))
            links.extend(parentless)
        return links

    def _slk_event_participants(
        self,
        event_record: GedcomLine,
        default: list[tuple[str, str]],
        family_xref: Optional[str],
    ) -> list[tuple[str, str]]:
        """Participants of a family event: ``_SLK_PART`` entries, else *default*."""
        problems: list[SlkProblem] = []
        entries = read_event_participants(
            event_record, self._person_xref_map.keys(), problems
        )
        self._report_slk_problems(
            problems, family_xref, "Deltagare hoppades över"
        )
        if entries is None:
            return default
        participants: list[tuple[str, str]] = []
        for xref, role in entries:
            person_id = self._person_xref_map.get(xref)
            if person_id:
                participants.append((person_id, role))
        return participants or default

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

        # Build partners list (_SLK_PARTNER restores roles and order)
        partners, _slk_partners = self._build_partners(gedcom_family, record)

        # Build children list
        children: list[str] = []
        for child_xref in gedcom_family.child_xrefs:
            child_id = self._person_xref_map.get(child_xref)
            if child_id:
                children.append(child_id)

        # Create family events (matched by the identity matcher, which also
        # stores each new event's Event_Origin)
        event_ids: list[str] = self._process_family_events(
            gedcom_family, record, family_id
        )

        # Build ParentChildLinks. The parentage_type comes from the child's
        # FAMC/PEDI pedigree for THIS family and applies to both parent
        # links of the child in the family (PEDI qualifies the child's
        # membership in the family, not a single parent).
        parent_child_links = self._build_parent_child_links(
            gedcom_family, partners
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
            partners, _slk_partners = self._build_partners(gedcom_family, record)

            children_list: list[str] = []
            for child_xref in gedcom_family.child_xrefs:
                child_id = self._person_xref_map.get(child_xref)
                if child_id:
                    children_list.append(child_id)

            parent_child_links = self._build_parent_child_links(
                gedcom_family, partners
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
        partners, from_slk = self._build_partners(gedcom_family, record)
        # Requirement 4.10: an equal partner set keeps the existing roles and
        # order, unless _SLK_PARTNER restores them (Requirement 4.11).
        if not from_slk and {p.person_id for p in partners} == {
            p.person_id for p in existing_family.partners
        } and len(partners) == len(existing_family.partners):
            partners = existing_family.partners

        children_list = []
        for child_xref in gedcom_family.child_xrefs:
            child_id = self._person_xref_map.get(child_xref)
            if child_id:
                children_list.append(child_id)

        parent_child_links = self._build_parent_child_links(
            gedcom_family, partners
        )

        existing_family.partners = partners
        existing_family.children = children_list
        existing_family.parent_child_links = parent_child_links
        self._families_updated += 1

        # Family events are never removed (Requirement 10.14). The matcher
        # decides which records already have an event; every id of
        # ``event_ids`` is kept and the ids of new events are appended.
        for new_id in self._process_family_events(
            gedcom_family, record, family_id, existing_family.event_ids
        ):
            if new_id not in existing_family.event_ids:
                existing_family.event_ids.append(new_id)

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

    def _import_event_date(
        self,
        date_str: Optional[str],
        event_type: str,
        person_ids: list[str],
        custom_type_name: Optional[str] = None,
    ) -> Optional[DateValue]:
        """Parse an event DATE line; a non-blank line always yields a DateValue.

        A date that cannot be read reliably becomes an unparsed DateValue that
        keeps its original text, and a Swedish warning is added to the import
        log.
        """
        parsed = parse_gedcom_date(date_str or "")
        if parsed is None:
            return None
        date_value = parsed.value
        if date_value.qualifier == "unparsed":
            try:
                from slaktbusken.ui.swedish_locale import get_event_type_label
            except ImportError:  # label is cosmetic: UI module not available
                label = event_type
            else:
                label = get_event_type_label(event_type)
            if event_type.startswith("custom_") and custom_type_name:
                label = custom_type_name
            names = [
                n for n in (self._display_name_for_person_id(p) for p in person_ids) if n
            ]
            person_label = " och ".join(names) if names else "okänd person"
            text = date_value.original_text or ""
            if parsed.dual_year:
                reason = (
                    f'Dubbelt årtal i datumet "{text}" kan inte tolkas entydigt '
                    "och sparades som originaltext."
                )
            else:
                reason = (
                    f'Datumet "{text}" för {label} ({person_label}) kunde inte '
                    "tolkas och sparades som originaltext."
                )
            xref = self._xref_for_person_id(person_ids[0]) if person_ids else None
            self._warnings.append(WarningEntry(
                gedcom_file=self._gedcom_filename,
                record_xref=xref,
                person_or_family_name=person_label,
                event_type=label,
                raw_value=date_str,
                reason=reason,
                action_taken="Sparades som originaltext",
            ))
        return date_value

    def _read_event_citations(
        self, event_record: GedcomLine
    ) -> list[tuple[str, SourceRef]]:
        """Read the SOUR citations of an event as ``(context, SourceRef)``.

        Quality comes from ``_SLK_QUAL`` before ``QUAY``; the context from
        ``_SLK_CTX`` (``event`` when absent or invalid).
        """
        result: list[tuple[str, SourceRef]] = []
        for sour_child in _get_children(event_record, "SOUR"):
            if not sour_child.value:
                continue
            source_id = self._source_xref_map.get(sour_child.value)
            if not source_id:
                continue
            problems: list[SlkProblem] = []
            cit = read_citation(sour_child, problems)
            self._report_slk_problems(problems, None, "Standardvärde användes")
            result.append((
                cit.context,
                SourceRef(
                    source_id=source_id,
                    quality=cit.quality,
                    note=cit.note,
                    aspects=list(cit.aspects),
                ),
            ))
        return result

    @staticmethod
    def _place_citations(
        citations: list[tuple[str, SourceRef]],
        event_refs: list[SourceRef],
        date_value: Optional[DateValue],
        place_ref: Optional[PlaceRef],
        from_place_ref: Optional[PlaceRef] = None,
    ) -> None:
        """Put each citation in its carrier; event level when it is absent."""
        carriers = {
            "date": date_value,
            "place": place_ref,
            "from_place": from_place_ref,
        }
        # Only assigned, never read: citations are new, carriers start empty.
        grouped: dict[str, list[SourceRef]] = {k: [] for k in carriers}
        for context, ref in citations:
            if carriers.get(context) is None:
                event_refs.append(ref)
            else:
                grouped[context].append(ref)
        for context, carrier in carriers.items():
            if carrier is not None and grouped[context]:
                carrier.source_refs = grouped[context]

    def _create_event(
        self,
        event_type: str,
        event_record: GedcomLine,
        participant_id: str,
        participant_role: str,
        custom_type_name: Optional[str] = None,
        origin: Optional[RecordOrigin] = None,
        from_place: Optional[str] = None,
    ) -> Optional[str]:
        """Create an event from a GEDCOM event sub-record.

        Extracts date, place, and source citations from the event record
        and creates a new Event entity. Whether the record needs a new event
        at all is decided by the identity matcher before this is called.

        Args:
            event_type: The App_JSON event type string.
            event_record: The GedcomLine containing the event data.
            participant_id: The person ID to add as participant.
            participant_role: The role of the participant.
            custom_type_name: Optional custom type name for custom events.
            origin: The Event_Origin to store on the new event.
            from_place: ``_SLK_FROMPLAC`` text of a flytt; resolved like PLAC.

        Returns:
            The new event ID.
        """
        event_id = self._id_gen.generate("event")

        # Parse date
        date_str = _get_child_value(event_record, "DATE")
        date_value = self._import_event_date(
            date_str,
            event_type=event_type,
            person_ids=[participant_id],
            custom_type_name=custom_type_name,
        )

        # Parse place
        place_ref = self._event_place_ref(event_record)

        # Parse source citations on the event
        citations = self._read_event_citations(event_record)
        source_refs: list[SourceRef] = []

        # Cause (CAUS) of an event; most often the cause of death.
        cause_of_death: Optional[str] = _get_child_value(event_record, "CAUS") or None

        participants = [Participant(person_id=participant_id, role=participant_role)]

        from_place_ref: Optional[PlaceRef] = None
        if from_place:
            from_place_id = self._resolve_place(from_place)
            if from_place_id:
                from_place_ref = PlaceRef(place_id=from_place_id)

        self._place_citations(
            citations, source_refs, date_value, place_ref, from_place_ref
        )

        event = Event(
            id=event_id,
            type=event_type,
            participants=participants,
            date=date_value,
            place=place_ref,
            cause_of_death=cause_of_death,
            custom_type_name=custom_type_name,
            from_place=from_place_ref,
            source_refs=source_refs,
            origin=origin,
        )
        self._project_data.events.append(event)
        if self._event_index is not None:
            self._event_index.add(event)
        self._run_created_event_ids.add(event_id)
        self._events_added += 1
        return event_id

    def _create_family_event(
        self,
        event_type: str,
        event_record: GedcomLine,
        participants: list[tuple[str, str]],
        custom_type_name: Optional[str] = None,
        origin: Optional[RecordOrigin] = None,
    ) -> Optional[str]:
        """Create a family event (marriage, divorce, etc.) from GEDCOM data.

        Args:
            event_type: The App_JSON event type string.
            event_record: The GedcomLine containing the event data.
            participants: List of (person_id, role) tuples for participants.
            custom_type_name: Optional custom type name for custom events.
            origin: The Event_Origin to store on the new event.

        Returns:
            The new event ID, or None if no participants.
        """
        if not participants:
            return None

        event_id = self._id_gen.generate("event")

        # Parse date
        date_str = _get_child_value(event_record, "DATE")
        date_value = self._import_event_date(
            date_str,
            event_type=event_type,
            person_ids=[pid for pid, _role in participants],
            custom_type_name=custom_type_name,
        )

        # Parse place
        place_ref = self._event_place_ref(event_record)

        # Source citations
        source_refs: list[SourceRef] = []
        self._place_citations(
            self._read_event_citations(event_record),
            source_refs, date_value, place_ref,
        )

        event_participants = [
            Participant(person_id=pid, role=role) for pid, role in participants
        ]

        event = Event(
            id=event_id,
            type=event_type,
            participants=event_participants,
            date=date_value,
            place=place_ref,
            cause_of_death=_get_child_value(event_record, "CAUS") or None,
            custom_type_name=custom_type_name,
            source_refs=source_refs,
            origin=origin,
        )
        self._project_data.events.append(event)
        if self._event_index is not None:
            self._event_index.add(event)
        self._run_created_event_ids.add(event_id)
        self._events_added += 1
        return event_id

    def _event_place_ref(
        self, event_record: GedcomLine, apply_coordinates: bool = True
    ) -> Optional[PlaceRef]:
        """Resolve the PLAC of an event record to a PlaceRef (or None)."""
        plac_rec = _get_child(event_record, "PLAC")
        if not plac_rec:
            return None
        # Try structured _ADPL first, fall back to PLAC string parsing
        place_id = self._resolve_place_from_adpl(plac_rec)
        if place_id is None:
            place_str = plac_rec.value
            if place_str:
                place_id = self._resolve_place(place_str)
        if not place_id:
            return None
        if apply_coordinates:
            # Extract MAP/LATI/LONG coordinates if present
            self._apply_coordinates(place_id, plac_rec)
        return PlaceRef(place_id=place_id)

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
