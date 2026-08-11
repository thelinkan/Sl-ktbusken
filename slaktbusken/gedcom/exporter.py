"""GEDCOM file exporter — produces GEDCOM 5.5.1 compliant output.

Exports App_JSON ProjectData to a GEDCOM 5.5.1 file with deterministic IDs,
place hierarchy resolution, and source citation handling. Data elements
without GEDCOM equivalents (DNA data, research notes, media items) are tracked
as omissions and reported to the user.

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from slaktbusken.gedcom.translation.citation_translation import build_citation_text
from slaktbusken.model.event import DateValue, Event
from slaktbusken.model.family import Family
from slaktbusken.model.person import Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import ResidenceFact
from slaktbusken.model.source import Source


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ExportResult:
    """Result of a GEDCOM export operation.

    Attributes:
        persons_exported: Number of person records written.
        families_exported: Number of family records written.
        sources_exported: Number of source records written.
        omitted_elements: Mapping of omitted element type to count.
        warnings: Swedish-language warnings for export issues.
    """

    persons_exported: int = 0
    families_exported: int = 0
    sources_exported: int = 0
    omitted_elements: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# GEDCOM month names (reverse of importer)
# ---------------------------------------------------------------------------

_ISO_MONTH_TO_GEDCOM: dict[str, str] = {
    "01": "JAN",
    "02": "FEB",
    "03": "MAR",
    "04": "APR",
    "05": "MAY",
    "06": "JUN",
    "07": "JUL",
    "08": "AUG",
    "09": "SEP",
    "10": "OCT",
    "11": "NOV",
    "12": "DEC",
}

# ---------------------------------------------------------------------------
# Event type to GEDCOM tag mapping (reverse of importer)
# ---------------------------------------------------------------------------

_EVENT_TYPE_TO_TAG: dict[str, str] = {
    "birth": "BIRT",
    "death": "DEAT",
    "burial": "BURI",
    "baptism": "BAPM",
    "emigration": "EMIG",
    "immigration": "IMMI",
    "census": "CENS",
    "retirement": "RETI",
    "graduation": "GRAD",
    "cremation": "CREM",
}

_FAMILY_EVENT_TYPE_TO_TAG: dict[str, str] = {
    "marriage": "MARR",
    "divorce": "DIV",
    "engagement": "ENGA",
}

# ---------------------------------------------------------------------------
# ID prefix mapping
# ---------------------------------------------------------------------------

_ID_PREFIX_MAP: dict[str, str] = {
    "person": "I",
    "family": "F",
    "source": "S",
}

# Regex to extract numeric suffix from App_JSON IDs like 'person_42'
_NUMERIC_SUFFIX_RE = re.compile(r"_(\d+)$")


# ---------------------------------------------------------------------------
# GEDCOMExporter
# ---------------------------------------------------------------------------


class GEDCOMExporter:
    """Exports App_JSON data to GEDCOM 5.5.1 format.

    Produces a UTF-8 encoded GEDCOM file with HEAD, INDI, FAM, SOUR,
    and TRLR records. Generates deterministic GEDCOM IDs from App_JSON
    IDs, resolves place hierarchies, and tracks omitted elements.
    """

    def __init__(self) -> None:
        """Initialise exporter state."""
        self._places: dict[str, Place] = {}
        self._sources: dict[str, Source] = {}
        self._events: dict[str, Event] = {}
        self._exported_source_ids: set[str] = set()
        self._resi_has_sour: bool = False
        self._flytt_from_place_loss: bool = False

    def export(self, data: ProjectData, output_path: Path) -> ExportResult:
        """Export ProjectData to a GEDCOM 5.5.1 file.

        Args:
            data: The complete project data to export.
            output_path: File path where the GEDCOM file will be written.

        Returns:
            ExportResult with counts and omitted element information.
        """
        # Build lookup tables
        self._places = {p.id: p for p in data.places}
        self._sources = {s.id: s for s in data.sources}
        self._events = {e.id: e for e in data.events}
        self._exported_source_ids = {s.id for s in data.sources}
        self._resi_has_sour = False
        self._flytt_from_place_loss = False

        # Build residence-by-person index
        residences_by_person: dict[str, list[ResidenceFact]] = {}
        for res in data.residences:
            residences_by_person.setdefault(res.person_id, []).append(res)

        lines: list[str] = []

        # HEAD record
        lines.extend(self._write_head())

        # INDI records
        for person in data.persons:
            lines.extend(self._write_person(person, data, residences_by_person))

        # FAM records
        for family in data.families:
            lines.extend(self._write_family(family, data))

        # SOUR records
        for source in data.sources:
            lines.extend(self._write_source(source))

        # TRLR record
        lines.append("0 TRLR")

        # Write file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Collect omissions
        omitted = self._collect_omissions(data)

        # Export log entry for observation notes (Requirement 12.10)
        warnings: list[str] = []
        if self._resi_has_sour:
            warnings.append(
                "Observationernas delperioder exporteras som anteckningar."
            )

        # Export log entry for Flytt from_place structure loss (Requirement 18.15)
        if self._flytt_from_place_loss:
            warnings.append(
                "Flyttens ursprungsplats exporteras som anteckning"
                " – GEDCOM 5.5.1 tillåter bara en PLAC per händelse."
            )

        return ExportResult(
            persons_exported=len(data.persons),
            families_exported=len(data.families),
            sources_exported=len(data.sources),
            omitted_elements=omitted,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Deterministic ID generation (subtask 12.2)
    # ------------------------------------------------------------------

    def _to_gedcom_id(self, app_id: str) -> str:
        """Generate a deterministic GEDCOM ID from an App_JSON ID.

        Extracts the numeric suffix and maps the prefix to the
        appropriate GEDCOM ID type character.

        Examples:
            'person_1' → '@I1@'
            'family_42' → '@F42@'
            'source_3' → '@S3@'

        Args:
            app_id: The App_JSON entity ID string.

        Returns:
            A GEDCOM-format ID string (e.g., '@I1@').
        """
        match = _NUMERIC_SUFFIX_RE.search(app_id)
        if not match:
            # Fallback: hash-based for non-standard IDs
            num = abs(hash(app_id)) % 99999
            prefix_char = "X"
            for prefix, char in _ID_PREFIX_MAP.items():
                if app_id.startswith(prefix):
                    prefix_char = char
                    break
            return f"@{prefix_char}{num}@"

        numeric = match.group(1)

        # Determine the GEDCOM prefix character
        prefix_char = "X"
        for prefix, char in _ID_PREFIX_MAP.items():
            if app_id.startswith(prefix):
                prefix_char = char
                break

        return f"@{prefix_char}{numeric}@"

    # ------------------------------------------------------------------
    # Place hierarchy resolution (subtask 12.3)
    # ------------------------------------------------------------------

    def _resolve_place_hierarchy(self, place_id: str) -> str:
        """Resolve a place hierarchy into a comma-separated string.

        Walks up the parent_place_id chain from the given place,
        producing a string ordered from most specific to least specific.

        Example:
            For a chain: church → parish → county → country
            Returns: "Ljusdals kyrka, Ljusdal, Gävleborgs län, Sverige"

        Args:
            place_id: The starting (most specific) place ID.

        Returns:
            Comma-separated place names from most to least specific.
            Returns empty string if place_id is not found.
        """
        parts: list[str] = []
        visited: set[str] = set()
        current_id: str | None = place_id

        while current_id and current_id not in visited:
            place = self._places.get(current_id)
            if place is None:
                break
            visited.add(current_id)
            parts.append(place.name)
            current_id = place.parent_place_id

        return ", ".join(parts)

    # ------------------------------------------------------------------
    # HEAD record
    # ------------------------------------------------------------------

    def _write_head(self) -> list[str]:
        """Write the GEDCOM HEAD record."""
        return [
            "0 HEAD",
            "1 SOUR Släktbusken",
            "1 GEDC",
            "2 VERS 5.5.1",
            "2 FORM LINEAGE-LINKED",
            "1 CHAR UTF-8",
        ]

    # ------------------------------------------------------------------
    # INDI record
    # ------------------------------------------------------------------

    def _write_person(
        self,
        person: Person,
        data: ProjectData,
        residences_by_person: dict[str, list[ResidenceFact]] | None = None,
    ) -> list[str]:
        """Write a GEDCOM INDI record for a person.

        Args:
            person: The person to export.
            data: Full project data for event lookups.
            residences_by_person: Pre-built index of residences keyed by person_id.

        Returns:
            List of GEDCOM lines for this person record.
        """
        gedcom_id = self._to_gedcom_id(person.id)
        lines: list[str] = [f"0 {gedcom_id} INDI"]

        # Names
        for name in person.names:
            given = name.given or ""
            surname = name.surname or ""
            lines.append(f"1 NAME {given} /{surname}/")

        # Sex
        if person.sex in ("M", "F"):
            lines.append(f"1 SEX {person.sex}")

        # Events for this person
        for event in data.events:
            if any(p.person_id == person.id for p in event.participants):
                if event.type == "flytt":
                    lines.extend(self._write_flytt_event(event))
                else:
                    tag = _EVENT_TYPE_TO_TAG.get(event.type)
                    if tag:
                        lines.extend(self._write_event_detail(tag, event))

        # Residence facts (RESI structures) for this person
        if residences_by_person:
            for residence in residences_by_person.get(person.id, []):
                lines.extend(self._write_residence(residence))

        return lines

    # ------------------------------------------------------------------
    # RESI record (Residence_Fact export)
    # ------------------------------------------------------------------

    def _iso_to_gedcom_date(
        self, iso_value: Optional[str], precision: Optional[str] = None
    ) -> str:
        """Convert an ISO date string to GEDCOM date form.

        YYYY-MM-DD → "DD MON YYYY", YYYY-MM → "MON YYYY", YYYY → "YYYY".
        Approximate precision adds "ABT " prefix.

        Args:
            iso_value: The ISO date string (YYYY, YYYY-MM, or YYYY-MM-DD).
            precision: The endpoint precision (adds "ABT " when "approximate").

        Returns:
            Formatted GEDCOM date string, or empty string if invalid/absent.
        """
        if not iso_value or not iso_value.strip():
            return ""

        value = iso_value.strip()
        result = ""

        # Try YYYY-MM-DD
        full_match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value)
        if full_match:
            year = full_match.group(1)
            month = full_match.group(2)
            day = int(full_match.group(3))
            month_name = _ISO_MONTH_TO_GEDCOM.get(month)
            if month_name:
                result = f"{day} {month_name} {year}"

        # Try YYYY-MM
        if not result:
            month_match = re.match(r"^(\d{4})-(\d{2})$", value)
            if month_match:
                year = month_match.group(1)
                month = month_match.group(2)
                month_name = _ISO_MONTH_TO_GEDCOM.get(month)
                if month_name:
                    result = f"{month_name} {year}"

        # Try YYYY
        if not result:
            year_match = re.match(r"^(\d{4})$", value)
            if year_match:
                result = value

        if not result:
            return ""

        # Apply approximate prefix (Requirement 12.11)
        if precision == "approximate":
            result = f"ABT {result}"

        return result

    def _write_residence(self, residence: ResidenceFact) -> list[str]:
        """Write a GEDCOM RESI structure for a Residence_Fact.

        Produces one level 1 RESI tag with optional DATE, PLAC, NOTE lines,
        and SOUR citations per Observation.

        Args:
            residence: The Residence_Fact to export.

        Returns:
            List of GEDCOM lines for the RESI structure.
        """
        lines: list[str] = ["1 RESI"]

        # DATE line (Requirement 12.2, 12.3, 12.4)
        # Use start.latest and end.earliest for the FROM/TO form
        start_latest = residence.start.latest
        end_earliest = residence.end.earliest
        has_start = bool(start_latest and start_latest.strip())
        has_end = bool(end_earliest and end_earliest.strip())

        if has_start and has_end:
            # FROM/TO form (non-empty Certain_Core)
            from_date = self._iso_to_gedcom_date(
                start_latest, residence.start.precision
            )
            to_date = self._iso_to_gedcom_date(
                end_earliest, residence.end.precision
            )
            if from_date and to_date:
                lines.append(f"2 DATE FROM {from_date} TO {to_date}")
        elif has_start:
            # FROM only
            from_date = self._iso_to_gedcom_date(
                start_latest, residence.start.precision
            )
            if from_date:
                lines.append(f"2 DATE FROM {from_date}")
        elif has_end:
            # TO only
            to_date = self._iso_to_gedcom_date(
                end_earliest, residence.end.precision
            )
            if to_date:
                lines.append(f"2 DATE TO {to_date}")
        # else: omit DATE entirely

        # PLAC line (Requirement 12.1)
        if residence.place_id:
            place_str = self._resolve_place_hierarchy(residence.place_id)
            if place_str:
                lines.append(f"2 PLAC {place_str}")

        # Labelled NOTE lines (Requirement 12.5)
        start_earliest = residence.start.earliest
        if start_earliest and start_earliest.strip():
            lines.append(f"2 NOTE Tidigast början: {start_earliest.strip()}")

        end_latest = residence.end.latest
        if end_latest and end_latest.strip():
            lines.append(f"2 NOTE Senast slut: {end_latest.strip()}")

        if residence.role_in_household:
            lines.append(f"2 NOTE Roll: {residence.role_in_household}")

        if residence.notes:
            lines.append(f"2 NOTE {residence.notes}")

        # SOUR lines (Requirement 12.6)
        for obs in residence.observations:
            source_id = obs.source_ref.source_id
            if source_id in self._exported_source_ids:
                source_gedcom_id = self._to_gedcom_id(source_id)
                lines.append(f"2 SOUR {source_gedcom_id}")
                # NOTE with observed_from/observed_to
                obs_from = obs.observed_from or ""
                obs_to = obs.observed_to or ""
                if obs_from or obs_to:
                    note_text = f"Observation: {obs_from}"
                    if obs_to and obs_to != obs_from:
                        note_text += f"-{obs_to}"
                    elif not obs_from and obs_to:
                        note_text = f"Observation: {obs_to}"
                    lines.append(f"3 NOTE {note_text}")
                else:
                    lines.append("3 NOTE Observation:")
                self._resi_has_sour = True

        return lines

    # ------------------------------------------------------------------
    # Flytt event (EVEN TYPE Flytt) export — Requirements 18.14, 18.15
    # ------------------------------------------------------------------

    def _write_flytt_event(self, event: Event) -> list[str]:
        """Write a GEDCOM EVEN structure for a Flytt event.

        Emits ``1 EVEN`` / ``2 TYPE Flytt`` / ``2 DATE`` (when present) /
        ``2 PLAC`` destination (when ``event.place`` is present) /
        ``2 NOTE Från: {from_place}`` (when ``event.from_place`` is present).
        Records the structure loss of ``from_place`` in the export log.

        Args:
            event: The flytt Event to export.

        Returns:
            List of GEDCOM lines for this flytt event.
        """
        lines: list[str] = ["1 EVEN", "2 TYPE Flytt"]

        # DATE line when event has a date (Requirement 18.14)
        if event.date:
            formatted = self._format_date(event.date)
            if formatted:
                lines.append(f"2 DATE {formatted}")

        # PLAC line — destination resolved from event.place (Requirement 18.14)
        if event.place and event.place.place_id:
            place_str = self._resolve_place_hierarchy(event.place.place_id)
            if place_str:
                lines.append(f"2 PLAC {place_str}")

        # NOTE for from_place — origin as labelled note (Requirement 18.15)
        if event.from_place and event.from_place.place_id:
            from_place_str = self._resolve_place_hierarchy(
                event.from_place.place_id
            )
            if from_place_str:
                lines.append(f"2 NOTE Från: {from_place_str}")
                self._flytt_from_place_loss = True

        return lines

    # ------------------------------------------------------------------
    # FAM record
    # ------------------------------------------------------------------

    def _write_family(self, family: Family, data: ProjectData) -> list[str]:
        """Write a GEDCOM FAM record for a family.

        Args:
            family: The family to export.
            data: Full project data for event lookups.

        Returns:
            List of GEDCOM lines for this family record.
        """
        gedcom_id = self._to_gedcom_id(family.id)
        lines: list[str] = [f"0 {gedcom_id} FAM"]

        # Partners
        for partner in family.partners:
            person_gedcom_id = self._to_gedcom_id(partner.person_id)
            if partner.role in ("husband", "father"):
                lines.append(f"1 HUSB {person_gedcom_id}")
            elif partner.role in ("wife", "mother"):
                lines.append(f"1 WIFE {person_gedcom_id}")

        # Children
        for child_id in family.children:
            child_gedcom_id = self._to_gedcom_id(child_id)
            lines.append(f"1 CHIL {child_gedcom_id}")

        # Family events
        for event_id in family.event_ids:
            event = self._events.get(event_id)
            if event:
                tag = _FAMILY_EVENT_TYPE_TO_TAG.get(event.type)
                if tag:
                    lines.extend(self._write_event_detail(tag, event))

        return lines

    # ------------------------------------------------------------------
    # SOUR record (subtask 12.4)
    # ------------------------------------------------------------------

    def _write_source(self, source: Source) -> list[str]:
        """Write a GEDCOM SOUR record for a source.

        Uses build_citation_text for citation resolution.

        Args:
            source: The source to export.

        Returns:
            List of GEDCOM lines for this source record.
        """
        gedcom_id = self._to_gedcom_id(source.id)
        lines: list[str] = [f"0 {gedcom_id} SOUR"]

        # Title
        if source.title:
            lines.append(f"1 TITL {source.title}")

        # Citation text (subtask 12.4)
        citation = build_citation_text(source)
        if citation and citation != source.title:
            lines.append(f"1 TEXT {citation}")

        return lines

    # ------------------------------------------------------------------
    # Event detail (date + place + source citations)
    # ------------------------------------------------------------------

    def _write_event_detail(self, tag: str, event: Event) -> list[str]:
        """Write event detail lines (tag, date, place, source citation).

        Args:
            tag: The GEDCOM event tag (e.g., 'BIRT', 'DEAT').
            event: The event to export.

        Returns:
            List of GEDCOM lines for the event detail.
        """
        lines: list[str] = [f"1 {tag}"]

        # Date
        if event.date:
            formatted = self._format_date(event.date)
            if formatted:
                lines.append(f"2 DATE {formatted}")

        # Place
        if event.place and event.place.place_id:
            place_str = self._resolve_place_hierarchy(event.place.place_id)
            if place_str:
                lines.append(f"2 PLAC {place_str}")
                # MAP coordinates (from the most specific place)
                place_obj = self._places.get(event.place.place_id)
                if place_obj and place_obj.latitude is not None and place_obj.longitude is not None:
                    lat_prefix = "N" if place_obj.latitude >= 0 else "S"
                    lon_prefix = "E" if place_obj.longitude >= 0 else "W"
                    lines.append("3 MAP")
                    lines.append(f"4 LATI {lat_prefix}{abs(place_obj.latitude)}")
                    lines.append(f"4 LONG {lon_prefix}{abs(place_obj.longitude)}")

        # Source citations on date
        if event.date and event.date.source_refs:
            for sref in event.date.source_refs:
                source = self._sources.get(sref.source_id)
                if source:
                    source_gedcom_id = self._to_gedcom_id(source.id)
                    lines.append(f"2 SOUR {source_gedcom_id}")
                    citation = build_citation_text(source)
                    if citation:
                        lines.append(f"3 TEXT {citation}")

        # Source citations on place
        if event.place and event.place.source_refs:
            for sref in event.place.source_refs:
                source = self._sources.get(sref.source_id)
                if source:
                    source_gedcom_id = self._to_gedcom_id(source.id)
                    lines.append(f"2 SOUR {source_gedcom_id}")
                    citation = build_citation_text(source)
                    if citation:
                        lines.append(f"3 TEXT {citation}")

        return lines

    # ------------------------------------------------------------------
    # Date formatting (ISO → GEDCOM)
    # ------------------------------------------------------------------

    def _format_date(self, date: DateValue) -> str:
        """Format a DateValue into GEDCOM date format.

        Converts ISO 8601 date strings to GEDCOM date format:
            - "1900-01-15" → "15 JAN 1900"
            - "1900-01" → "JAN 1900"
            - "1900" → "1900"
            - precision "approximate" → prefix with "ABT"

        Args:
            date: The DateValue to format.

        Returns:
            Formatted GEDCOM date string, or empty string if invalid.
        """
        if not date.value:
            return ""

        value = date.value.strip()
        result = ""

        # Try YYYY-MM-DD
        full_match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value)
        if full_match:
            year = full_match.group(1)
            month = full_match.group(2)
            day = int(full_match.group(3))
            month_name = _ISO_MONTH_TO_GEDCOM.get(month)
            if month_name:
                result = f"{day} {month_name} {year}"

        # Try YYYY-MM
        if not result:
            month_match = re.match(r"^(\d{4})-(\d{2})$", value)
            if month_match:
                year = month_match.group(1)
                month = month_match.group(2)
                month_name = _ISO_MONTH_TO_GEDCOM.get(month)
                if month_name:
                    result = f"{month_name} {year}"

        # Try YYYY
        if not result:
            year_match = re.match(r"^(\d{4})$", value)
            if year_match:
                result = value

        if not result:
            return ""

        # Apply approximate prefix
        if date.precision == "approximate":
            result = f"ABT {result}"

        return result

    # ------------------------------------------------------------------
    # Omission tracking (subtask 12.5)
    # ------------------------------------------------------------------

    def _collect_omissions(self, data: ProjectData) -> dict[str, int]:
        """Identify App_JSON elements with no GEDCOM equivalent.

        Tracks counts by type for: DNA data, research notes, media items,
        and other non-exportable elements.

        Args:
            data: The complete project data.

        Returns:
            Dictionary mapping element type to count of omitted elements.
        """
        omitted: dict[str, int] = {}

        if data.dna_companies:
            omitted["DNA-företag"] = len(data.dna_companies)

        if data.dna_profiles:
            omitted["DNA-profiler"] = len(data.dna_profiles)

        if data.dna_matches:
            omitted["DNA-matchningar"] = len(data.dna_matches)

        if data.dna_segments:
            omitted["DNA-segment"] = len(data.dna_segments)

        if data.dna_clusters:
            omitted["DNA-kluster"] = len(data.dna_clusters)

        if data.dna_triangulations:
            omitted["DNA-trianguleringar"] = len(data.dna_triangulations)

        if data.research_notes:
            omitted["Forskningsanteckningar"] = len(data.research_notes)

        if data.media:
            omitted["Medieobjekt"] = len(data.media)

        return omitted
