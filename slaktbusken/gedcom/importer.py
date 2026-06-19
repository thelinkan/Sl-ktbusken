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
from slaktbusken.model.source import Repository, RepositoryRef, Source
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
    "RESI": "census",
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
        self._warnings: list[str] = []

        # Collect all existing IDs for the ID generator
        existing_ids: set[str] = set()
        for p in project_data.persons:
            existing_ids.add(p.id)
        for f in project_data.families:
            existing_ids.add(f.id)
        for e in project_data.events:
            existing_ids.add(e.id)
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

        # Parse into tree
        parse_result = parse_gedcom(text)

        # Collect parser warnings
        for pw in parse_result.warnings:
            self._warnings.append(pw.message)

        # Load existing translation data
        translation_data = self._translation_mgr.load_translations()
        self._translation_data = translation_data

        # Separate records by tag type
        indi_records: list[GedcomLine] = []
        fam_records: list[GedcomLine] = []
        sour_records: list[GedcomLine] = []

        for record in parse_result.records:
            tag = record.tag.upper()
            if tag == "INDI":
                indi_records.append(record)
            elif tag == "FAM":
                fam_records.append(record)
            elif tag == "SOUR":
                sour_records.append(record)
            elif tag not in _SUPPORTED_LEVEL0_TAGS:
                self._warnings.append(
                    f"Rad {record.line_number}: Ignorerade post med tagg "
                    f"'{record.tag}' (ej stödd GEDCOM-taggtyp)"
                )

        # Step 1: Process sources
        self._process_sources(sour_records, translation_data)

        # Step 2: Process persons (pass fam_records for fingerprint matching)
        self._process_persons(indi_records, translation_data, fam_records)

        # Step 3: Process families
        self._process_families(fam_records, translation_data)

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
            warnings=self._warnings,
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
                        f.write(f"  {i}. {warning}\n")
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
                gedcom_source, self._project_data.sources
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
                self._warnings.append(
                    f"Rad {line_num}: Kunde inte importera person "
                    f"(xref={record.xref_id or '?'}): {exc}"
                )

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
        diff_report = classify_persons(
            incoming=incoming_persons,
            families=families,
            existing_mappings=translation_data.persons,
            existing_fingerprints=existing_fingerprints,
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
                self._warnings.append(
                    f"Rad {line_num}: Kunde inte importera person "
                    f"(xref={record.xref_id or '?'}): {exc}"
                )

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
        """Create events for a person from GEDCOM event tags.

        Scans the INDI record's children for known event tags (BIRT, DEAT,
        BURI, BAPM, CHR, etc.) and creates Event records for each. Also
        handles the generic EVEN tag as a custom_individual_event.

        Args:
            person_id: The App_JSON person ID to use as participant.
            record: The INDI GedcomLine record with event children.
        """
        for child in record.children:
            tag = child.tag.upper()
            if tag in _INDI_EVENT_TAGS:
                event_type = _INDI_EVENT_TAGS[tag]
                self._create_event(
                    event_type=event_type,
                    event_record=child,
                    participant_id=person_id,
                    participant_role="subject",
                )
            elif tag == "EVEN":
                # Generic individual event → custom_individual_event
                custom_type_name = _get_child_value(child, "TYPE")
                self._create_event(
                    event_type="custom_individual_event",
                    event_record=child,
                    participant_id=person_id,
                    participant_role="subject",
                    custom_type_name=custom_type_name,
                )

    # ------------------------------------------------------------------
    # Family processing
    # ------------------------------------------------------------------

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

        # Build ParentChildLinks
        parent_child_links: list[ParentChildLink] = []
        for child_id in children:
            for partner in partners:
                parent_child_links.append(
                    ParentChildLink(
                        child_id=child_id,
                        parent_id=partner.person_id,
                        parentage_type="biological",
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
            for child_id in children_list:
                for partner in partners:
                    parent_child_links.append(
                        ParentChildLink(
                            child_id=child_id,
                            parent_id=partner.person_id,
                            parentage_type="biological",
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
        for child_id in children_list:
            for partner in partners:
                parent_child_links.append(
                    ParentChildLink(
                        child_id=child_id,
                        parent_id=partner.person_id,
                        parentage_type="biological",
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
        place_str = _get_child_value(event_record, "PLAC")
        if place_str:
            place_id = self._resolve_place(place_str)
            if place_id:
                place_ref = PlaceRef(place_id=place_id)

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
        place_str = _get_child_value(event_record, "PLAC")
        if place_str:
            place_id = self._resolve_place(place_str)
            if place_id:
                place_ref = PlaceRef(place_id=place_id)

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
