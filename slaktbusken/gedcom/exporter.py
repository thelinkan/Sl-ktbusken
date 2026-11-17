"""GEDCOM file exporter — produces GEDCOM 5.5.1 compliant output.

Exports App_JSON ProjectData to a GEDCOM 5.5.1 file with deterministic IDs,
place hierarchy resolution, and source citation handling. Data elements
without GEDCOM equivalents (DNA data, research notes, media items) are tracked
as omissions and reported to the user.

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from slaktbusken.gedcom.translation.citation_translation import build_citation_text
from slaktbusken.gedcom.dates import export_gedcom_date
from slaktbusken.gedcom.event_links import export_endpoint_link, export_name_link
from slaktbusken.gedcom.text_lines import text_lines
from slaktbusken.model.date_semantics import effective_qualifier
from slaktbusken.model.event import DateValue, Event, SourceRef
from slaktbusken.model.event_citations import CitationContext, event_citations
from slaktbusken.model.family import Family
from slaktbusken.model.person import Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, ResidenceFact
from slaktbusken.model.source import Repository, RepositoryRef, Source

_ISO_VALUE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")

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


@dataclass
class SlotAssignment:
    """HUSB/WIFE placeholder slots of one family.

    ``husb`` and ``wife`` hold person ids (or ``None``). ``conflicts`` lists
    ``(person_id, slot)`` pairs where the slot contradicts a known sex
    (sex ``M`` in WIFE, ``F`` in HUSB, ``X`` in either slot).
    """

    husb: Optional[str] = None
    wife: Optional[str] = None
    conflicts: list[tuple[str, str]] = field(default_factory=list)


_FAMILY_EVENT_TYPES = frozenset(
    {"marriage", "divorce", "engagement", "divorce_filed", "custom_family_event"}
)

_SEX_WORD = {"M": "man", "F": "kvinna", "X": "kön X"}


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
    "adoption": "ADOP",
    "confirmation": "CONF",
    "will": "WILL",
    "blessing": "BLES",
    "first_communion": "FCOM",
}

# Placement events derive their roles on import: no _SLK_ROLE for them.
_PLACEMENT_EVENT_TYPES = frozenset({"foster_home", "adoption"})

# Swedish labels for the TYPE line of an Individual_Fallback.
_FALLBACK_TYPE_LABELS: dict[str, str] = {
    "marriage": "Vigsel",
    "divorce": "Skilsmässa",
    "engagement": "Förlovning",
    "divorce_filed": "Skilsmässoansökan",
    "custom_family_event": "Anpassad familjehändelse",
}

# Name.type -> GEDCOM NAME TYPE value (Requirement 3 criterion 1).
_NAME_TYPE_TO_GEDCOM: dict[str, str] = {
    "birth": "birth",
    "married": "married",
    "alias": "aka",
    "adopted": "adopted",
    "other": "other",
}

_FAMILY_EVENT_TYPE_TO_TAG: dict[str, str] = {
    "marriage": "MARR",
    "divorce": "DIV",
    "engagement": "ENGA",
    "divorce_filed": "DIVF",
    "custom_family_event": "EVEN",
}

# ---------------------------------------------------------------------------
# ID prefix mapping
# ---------------------------------------------------------------------------

_ID_PREFIX_MAP: dict[str, str] = {
    "person": "I",
    "family": "F",
    "source": "S",
    "repo": "R",
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
        self._leverantor_names: dict[str, str] = {}
        self._kalltyp_names: dict[str, str] = {}
        self._placement_end_note_loss: bool = False
        self._date_warnings: list[str] = []
        self._persons: dict[str, Person] = {}
        self._written_family_events: set[str] = set()
        self._orphan_by_family: Optional[dict[str, list[Event]]] = None
        # Orphan family events without a unique family. The event exporter
        # (task 6.1) writes them as Individual_Fallback.
        self._fallback_family_events: list[Event] = []
        self._placeholder_warnings: list[str] = []
        self._xref_map: dict[str, str] = {}
        self._xref_used: set[str] = set()
        self._xref_next: dict[str, int] = {}
        self._fallback_event_ids: set[str] = set()
        self._repositories: dict[str, Repository] = {}
        self._repo_warnings: list[str] = []

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
        self._repositories = {r.id: r for r in data.repositories}
        self._repo_warnings = []
        self._leverantor_names = {l.id: l.name for l in data.leverantorer}
        self._kalltyp_names = {k.id: k.name for k in data.kalltyper}
        self._placement_end_note_loss = False
        self._date_warnings = []
        self._persons = {p.id: p for p in data.persons}
        self._written_family_events = set()
        self._orphan_by_family = None
        self._fallback_family_events = []
        self._placeholder_warnings = []
        self._prepare_xrefs(data)
        # Sort the orphan family events before the INDI records are written,
        # so that each INDI knows which events it carries as fallback.
        self._orphan_index(data)
        self._fallback_event_ids = {e.id for e in self._fallback_family_events}

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

        # REPO records: repositories used by a SOUR, then the unused ones
        lines.extend(self._write_repositories(data))

        # TRLR record
        lines.append("0 TRLR")

        # Write file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Collect omissions
        omitted = self._collect_omissions(data)

        warnings: list[str] = []

        # Dangling RepositoryRefs (Requirement 9.7)
        warnings.extend(self._repo_warnings)

        # Placeholder conflicts of families (Requirement 4 criteria 14, 15)
        warnings.extend(self._placeholder_warnings)
        if self._placeholder_warnings:
            warnings.append(
                "Program som inte läser _SLK_PARTNER visar platshållarna HUSB"
                " och WIFE som make och maka."
            )

        # Orphan family events written as Individual_Fallback (Requirement 1.4)
        for event in self._fallback_family_events:
            warnings.append(self._fallback_warning(event))

        # Stale original text of dates (Requirement 11.6)
        for date_warning in self._date_warnings:
            if date_warning not in warnings:
                warnings.append(date_warning)

        # Export log entry for placement-end NOTE fallback (Requirement 11.2e)
        if self._placement_end_note_loss:
            warnings.append(
                "Placeringens slutdatum exporteras som anteckning"
                " – det kunde inte uttryckas som en GEDCOM-period på DATE-raden."
            )

        # Data without a GEDCOM form (Requirement 10 criteria 2, 3)
        if data.media:
            warnings.append(
                f"Media exporteras inte: {len(data.media)} medieobjekt"
                " (filer och länkar) ingår inte i GEDCOM-filen."
            )
        if any(place.type for place in data.places):
            warnings.append(
                "Platstyper exporteras inte (skjuts upp till en senare version)."
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
        numeric_xref = self._numeric_xref(app_id)
        if numeric_xref is not None:
            return numeric_xref
        known = self._xref_map.get(app_id)
        if known is not None:
            return known
        # Not seen by _prepare_xrefs (an id outside the three record lists):
        # numbered on first use, which is deterministic for a given call order.
        return self._allocate_xref(app_id, self._prefix_char(app_id))

    @staticmethod
    def _prefix_char(app_id: str) -> str:
        """GEDCOM prefix character chosen by the start of the App_JSON id."""
        for prefix, char in _ID_PREFIX_MAP.items():
            if app_id.startswith(prefix):
                return char
        return "X"

    def _numeric_xref(self, app_id: str) -> Optional[str]:
        """Xref of an id with a numeric suffix (``person_19`` -> ``@I19@``)."""
        match = _NUMERIC_SUFFIX_RE.search(app_id)
        if not match:
            return None
        return f"@{self._prefix_char(app_id)}{match.group(1)}@"

    def _allocate_xref(self, app_id: str, prefix_char: str) -> str:
        """Next free sequential xref of ``prefix_char`` for a non-numeric id."""
        number = self._xref_next.get(prefix_char, 1)
        while f"@{prefix_char}{number}@" in self._xref_used:
            number += 1
        self._xref_next[prefix_char] = number + 1
        xref = f"@{prefix_char}{number}@"
        self._xref_used.add(xref)
        self._xref_map[app_id] = xref
        return xref

    def _prepare_xrefs(self, data: ProjectData) -> None:
        """Fix the xrefs of ids without a numeric suffix for this export.

        Numeric-suffix xrefs stay as they are. The other ids of persons,
        families and sources get the next free number of their record kind in
        project order, skipping numbers that a numeric-suffix xref already
        uses, so the output does not depend on Python's hash seed.
        """
        self._xref_map = {}
        self._xref_next = {}
        records = (
            ("I", [p.id for p in data.persons]),
            ("F", [f.id for f in data.families]),
            ("S", [s.id for s in data.sources]),
            ("R", [r.id for r in data.repositories]),
        )
        self._xref_used = {
            xref
            for _, ids in records
            for app_id in ids
            if (xref := self._numeric_xref(app_id)) is not None
        }
        for prefix_char, ids in records:
            for app_id in ids:
                if self._numeric_xref(app_id) is None and app_id not in self._xref_map:
                    self._allocate_xref(app_id, prefix_char)

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
            "1 _SLK_VERS 1",
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
            lines.append(f"2 TYPE {_NAME_TYPE_TO_GEDCOM.get(name.type, 'other')}")
            lines.extend(export_name_link(name, self._events, self._event_token))

        # Sex (Requirement 4 criteria 8, 9)
        if person.sex in ("M", "F", "U"):
            lines.append(f"1 SEX {person.sex}")
        elif person.sex == "X":
            lines.append("1 SEX U")
            lines.append("2 _SLK_SEX X")

        # Title, occupation and notes (Requirement 2 criteria 1, 2)
        if person.title:
            lines.extend(text_lines(1, "TITL", person.title))
        if person.occupation:
            lines.extend(text_lines(1, "OCCU", person.occupation))
        if person.notes:
            lines.extend(text_lines(1, "NOTE", person.notes))

        # Family links (FAMC / FAMS) — Requirements 11.1, 11.2
        lines.extend(self._write_family_links(person, data))

        # Events for this person
        for event in data.events:
            if any(p.person_id == person.id for p in event.participants):
                if event.type == "flytt":
                    lines.extend(self._write_flytt_event(event, person.id))
                elif event.type == "foster_home":
                    # The Fosterhem placement structure belongs ONLY on the
                    # placed CHILD's INDI record, never on a foster parent's.
                    # Emitting it on a parent would give that parent a spurious
                    # ``1 EVEN TYPE Fosterhem ... 2 FAMC`` that the importer's
                    # _finalize_placement_events mis-reads as a placed child,
                    # fabricating bogus parent→parent links and breaking the
                    # round-trip. Guard by the placement child role.
                    if self._is_placement_child(person.id, event):
                        lines.extend(self._write_foster_event(event, data))
                elif event.type == "adoption":
                    # Same child-only guard for the Adoption placement
                    # structure (``1 ADOP ... 2 FAMC``): emit it only on the
                    # adoptee's INDI, never on an adoptive parent's.
                    if self._is_placement_child(person.id, event):
                        lines.extend(self._write_adoption_event(event, data))
                elif event.type in ("foster_home_ended", "adoption_ended"):
                    # Placement END events carry no structure of their own: their
                    # date rides on the paired START structure's DATE line (as a
                    # GEDCOM period) or a labelled NOTE, emitted by
                    # ``_write_foster_event``/``_write_adoption_event`` via
                    # ``_find_paired_end_event``. Skipping here ensures the end is
                    # never emitted as a separate orphan structure
                    # (Requirement 11.2e). (The generic branch would already drop
                    # these types — they have no ``_EVENT_TYPE_TO_TAG`` entry — but
                    # this explicit skip documents the intent.)
                    continue
                elif event.type in _FAMILY_EVENT_TYPES:
                    # Listed and matching orphan family events are written in
                    # their FAM record. Only the others are written here, as
                    # Individual_Fallback on the INDI of each participant.
                    if event.id in self._fallback_event_ids:
                        lines.extend(self._write_fallback_event(event, person.id))
                else:
                    lines.extend(self._write_individual_event(event, person.id))

        # Residence facts (RESI structures) for this person
        if residences_by_person:
            for residence in residences_by_person.get(person.id, []):
                lines.extend(self._write_residence(residence))

        return lines

    # ------------------------------------------------------------------
    # Family links (FAMC / FAMS) — Requirements 11.1, 11.2
    # ------------------------------------------------------------------

    def _write_family_links(
        self, person: Person, data: ProjectData
    ) -> list[str]:
        """Write the individual's ``FAMC``/``FAMS`` family-link structures.

        In GEDCOM 5.5.1 the pedigree tag ``PEDI`` is a subordinate of the
        child's ``FAMC`` link (not of the family's ``CHIL``), so foster and
        adoptive parentage is emitted here:

        - ``1 FAMC @Fxx@`` for each family in which the person is a child.
          The child's parentage type in that family is read from the
          family's ``parent_child_links`` (links where ``child_id`` equals the
          person). A foster link emits ``2 PEDI foster``; an adoptive link
          emits ``2 PEDI adopted`` (the GEDCOM value is ``adopted``, not
          ``adoptive``). Biological or any other parentage type emits no
          ``PEDI`` line. When a single family mixes link types for the same
          child, foster takes precedence over adoptive (any other type is
          ignored) so exactly one ``PEDI`` line is emitted at most.
        - ``1 FAMS @Fxx@`` for each family in which the person is a partner.

        Families are iterated in project order (``data.families``) and each
        family produces at most one ``FAMC``/``FAMS`` line, giving stable,
        deduplicated output.

        Args:
            person: The person whose family links are written.
            data: Full project data (iterated for its families).

        Returns:
            List of GEDCOM lines for this person's FAMC/FAMS structures.
        """
        lines: list[str] = []

        for family in data.families:
            family_gedcom_id = self._to_gedcom_id(family.id)

            # FAMC — person appears as a child of this family.
            if person.id in family.children:
                lines.append(f"1 FAMC {family_gedcom_id}")
                pedi = self._pedigree_for_child(family, person.id)
                if pedi:
                    lines.append(f"2 PEDI {pedi}")
                lines.extend(self._plink_lines(family, person.id))

            # FAMS — person appears as a partner of this family.
            if any(fp.person_id == person.id for fp in family.partners):
                lines.append(f"1 FAMS {family_gedcom_id}")

        return lines

    def _plink_lines(self, family: Family, child_id: str) -> list[str]:
        """``_SLK_PLINK`` lines for the non-biological links of a child.

        One entry per ParentChildLink of the child whose parentage type is not
        ``biological``, in link order. A link without parent gets no value.
        """
        lines: list[str] = []
        for link in family.parent_child_links:
            if link.child_id != child_id or link.parentage_type == "biological":
                continue
            if link.parent_id:
                lines.append(f"2 _SLK_PLINK {self._to_gedcom_id(link.parent_id)}")
            else:
                lines.append("2 _SLK_PLINK")
            lines.append(f"3 TYPE {link.parentage_type}")
        return lines

    @staticmethod
    def _pedigree_for_child(family: Family, child_id: str) -> str | None:
        """Resolve the GEDCOM ``PEDI`` value for a child in a family.

        Reads the family's ``parent_child_links`` for links whose
        ``child_id`` matches. Returns ``"foster"`` if any such link is a
        foster link, else ``"adopted"`` if any is an adoptive link, else
        ``None`` (biological and every other type carry no pedigree tag).
        Foster is preferred over adoptive when a family mixes types for the
        same child.

        Args:
            family: The family the child belongs to.
            child_id: The child's person id.

        Returns:
            ``"foster"``, ``"adopted"``, or ``None``.
        """
        types = {
            link.parentage_type
            for link in family.parent_child_links
            if link.child_id == child_id
        }
        if "foster" in types:
            return "foster"
        if "adoptive" in types:
            return "adopted"
        return None

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
            lines.extend(text_lines(2, "NOTE", f"Roll: {residence.role_in_household}"))

        if residence.notes:
            lines.extend(text_lines(2, "NOTE", residence.notes))

        # SLK tags (Requirement 7): endpoints, role, notes. They carry the
        # exact values; DATE and the prose NOTE lines above stay unchanged.
        lines.extend(self._slk_endpoint_lines("_SLK_START", residence.start))
        lines.extend(self._slk_endpoint_lines("_SLK_END", residence.end))
        if residence.role_in_household and residence.role_in_household.strip():
            lines.extend(text_lines(2, "_SLK_HHROLE", residence.role_in_household))
        if residence.notes and residence.notes.strip():
            lines.extend(text_lines(2, "_SLK_RNOTES", residence.notes))

        # SOUR lines (Requirement 12.6)
        for obs in residence.observations:
            source_id = obs.source_ref.source_id
            if source_id in self._exported_source_ids:
                # NOTE with observed_from/observed_to
                obs_from = obs.observed_from or ""
                obs_to = obs.observed_to or ""
                if obs_from or obs_to:
                    note_text = f"Observation: {obs_from}"
                    if obs_to and obs_to != obs_from:
                        note_text += f"-{obs_to}"
                    elif not obs_from and obs_to:
                        note_text = f"Observation: {obs_to}"
                    obs_note = f"3 NOTE {note_text}"
                else:
                    obs_note = "3 NOTE Observation:"
                citation = self._write_citation(
                    2, self._sources[source_id], obs.source_ref, None,
                    event_text=False,
                )
                # SOUR line, the unchanged Observation note, then the rest.
                lines.append(citation[0])
                lines.append(obs_note)
                lines.extend(citation[1:])
                # PAGE and the observation period; QUAY, _SLK_QUAL, _SLK_NOTE
                # and _SLK_ASP are already written by _write_citation.
                if obs.page_note and obs.page_note.strip():
                    lines.extend(text_lines(3, "PAGE", obs.page_note))
                if obs_from.strip():
                    lines.append(f"3 _SLK_OBSFROM {obs_from.strip()}")
                if obs_to.strip():
                    lines.append(f"3 _SLK_OBSTO {obs_to.strip()}")

        return lines

    def _slk_endpoint_lines(self, tag: str, endpoint: Endpoint) -> list[str]:
        """``2 _SLK_START`` / ``2 _SLK_END`` with its children, or nothing.

        Written whenever the endpoint has any value (including an event link).
        """
        children: list[str] = []
        if endpoint.earliest and endpoint.earliest.strip():
            children.append(f"3 _SLK_EARLIEST {endpoint.earliest.strip()}")
        if endpoint.latest and endpoint.latest.strip():
            children.append(f"3 _SLK_LATEST {endpoint.latest.strip()}")
        if endpoint.precision and endpoint.precision.strip():
            children.append(f"3 _SLK_PREC {endpoint.precision.strip()}")
        if endpoint.note and endpoint.note.strip():
            children.extend(text_lines(3, "_SLK_NOTE", endpoint.note))
        children.extend(export_endpoint_link(endpoint, self._events, self._event_token))
        return [f"2 {tag}", *children] if children else []

    # ------------------------------------------------------------------
    # Flytt event (EVEN TYPE Flytt) export — Requirements 18.14, 18.15
    # ------------------------------------------------------------------

    def _write_flytt_event(
        self, event: Event, person_id: Optional[str] = None
    ) -> list[str]:
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
                lines.extend(text_lines(2, "_SLK_FROMPLAC", from_place_str))

        # Citations of the event, its date and its place (Requirement 12.5).
        # The from-place citations carry _SLK_CTX from_place.
        lines.extend(self._event_citation_lines(event))
        if event.cause_of_death:
            lines.extend(text_lines(2, "CAUS", event.cause_of_death))
        lines.extend(self._slk_event_lines(event, person_id))
        return lines

    # ------------------------------------------------------------------
    # Placement events (Adoption / Fosterhem) export — Requirements 11.2a–11.2d
    # ------------------------------------------------------------------
    #
    # Routing note: both ``adoption`` and ``foster_home`` are handled by
    # dedicated branches in ``_write_person`` rather than the generic
    # ``_EVENT_TYPE_TO_TAG`` path, because each must carry a subordinate
    # ``FAMC`` pointing at the derived family for its Parent_Set. ``adoption``
    # is also present in ``_EVENT_TYPE_TO_TAG`` (so adoption events are no
    # longer dropped), but the explicit branch runs first and the generic
    # branch is only reached for event types *without* an explicit case, so
    # the ``ADOP`` structure is never emitted twice.
    #
    # GEDCOM levels: the event tag is level 1 (``1 ADOP`` / ``1 EVEN``); its
    # ``DATE``/``PLAC``/``TYPE`` are level 2; the derived-family ``FAMC`` is a
    # level-2 subordinate of the level-1 event (``2 FAMC @Fxx@``).

    def _derived_family_for_event(
        self, event: Event, data: ProjectData
    ) -> Family | None:
        """Return the derived :class:`Family` keyed to ``event``.

        ``foster_sync`` keys a derived family to its placement start event by
        appending the event id to the family's ``event_ids`` (a paired end
        event's id is also appended there). This returns the first family whose
        ``event_ids`` contains ``event.id``, or ``None`` when no family
        references the event (e.g. a pre-feature descriptive adoption event with
        no parents, which derives no family — Requirement 1.9).

        Args:
            event: The placement event (start or end).
            data: Full project data (iterated for its families).

        Returns:
            The matching :class:`Family`, or ``None``.
        """
        for family in data.families:
            if event.id in family.event_ids:
                return family
        return None

    def _derived_family_gedcom_id(
        self, event: Event, data: ProjectData
    ) -> str | None:
        """Find the GEDCOM id of the derived family keyed to ``event``.

        Thin wrapper over :meth:`_derived_family_for_event` returning the
        family's GEDCOM id, or ``None`` when no family references the event.

        Args:
            event: The placement start event.
            data: Full project data (iterated for its families).

        Returns:
            A GEDCOM family id string (e.g. ``@F3@``), or ``None``.
        """
        family = self._derived_family_for_event(event, data)
        return self._to_gedcom_id(family.id) if family is not None else None

    # Maps a placement START event type to the matching placement END event
    # type. Kept locally (rather than imported from ``foster_sync``'s private
    # ``_PLACEMENT_END``) so the exporter has no dependency on service
    # internals; it mirrors that table (foster_home → foster_home_ended,
    # adoption → adoption_ended).
    _PLACEMENT_START_TO_END: dict[str, str] = {
        "foster_home": "foster_home_ended",
        "adoption": "adoption_ended",
    }

    def _find_paired_end_event(
        self, start_event: Event, data: ProjectData
    ) -> Event | None:
        """Return the placement END event paired to ``start_event``, or ``None``.

        ``foster_sync`` pairs an end to its start by appending the end event's
        id to the *same* derived family whose ``event_ids`` already holds the
        start event id. The paired end is therefore the event — among that
        family's ``event_ids`` — whose type is the matching end type
        (``foster_home_ended`` for a ``foster_home`` start, ``adoption_ended``
        for an ``adoption`` start). Returns ``None`` when the start has no
        derived family or no such end is recorded.

        Args:
            start_event: The placement start event.
            data: Full project data (for the derived-family lookup).

        Returns:
            The paired placement END :class:`Event`, or ``None``.
        """
        end_type = self._PLACEMENT_START_TO_END.get(start_event.type)
        if end_type is None:
            return None
        family = self._derived_family_for_event(start_event, data)
        if family is None:
            return None
        for event_id in family.event_ids:
            candidate = self._events.get(event_id)
            if candidate is not None and candidate.type == end_type:
                return candidate
        return None

    def _placement_date_lines(
        self, start_event: Event, data: ProjectData
    ) -> list[str]:
        """Build the period-aware ``DATE`` (and fallback ``NOTE``) lines.

        Encodes a placement's span on a single ``2 DATE`` line as a GEDCOM
        period, following the paired end rules (Requirement 11.2e):

        - paired end + both dates formattable → ``2 DATE FROM <start> TO <end>``
        - paired end + start only → ``2 DATE FROM <start>``
        - paired end + end only (start dateless) → ``2 DATE TO <end>``
        - paired end whose date exists but is *unformattable* by
          :meth:`_format_date` → the plain start ``DATE`` (if any) plus a
          labelled ``2 NOTE Avslutades: <raw end>`` fallback, recording the
          structure loss via ``self._placement_end_note_loss`` (mirrors
          ``_write_flytt_event``'s ``from_place`` note loss).
        - no paired end → the existing 10.1a behaviour: a plain ``2 DATE
          <start>`` when the start has a formattable date (no regression).

        Args:
            start_event: The placement start event.
            data: Full project data (for the paired-end lookup).

        Returns:
            The ``DATE``/``NOTE`` lines for the structure (possibly empty).
        """
        start_formatted = (
            self._format_date(start_event.date) if start_event.date else ""
        )

        end_event = self._find_paired_end_event(start_event, data)
        if end_event is None:
            # No end at all: keep the 10.1a plain-DATE behaviour unchanged.
            if start_formatted:
                return [f"2 DATE {start_formatted}"]
            return []

        end_formatted = (
            self._format_date(end_event.date) if end_event.date else ""
        )

        # FROM/TO only take single exact dates. A qualified, ranged or
        # unparsed endpoint cannot be a period endpoint, so the start is
        # written as an ordinary DATE and a dated end becomes a labelled NOTE
        # (recording the structure loss).
        start_ok = (
            not start_formatted or self._is_period_endpoint(start_event.date)
        )
        end_ok = not end_formatted or self._is_period_endpoint(end_event.date)
        end_raw = (
            end_event.date.value.strip()
            if end_event.date is not None and end_event.date.value
            else ""
        )
        if (end_formatted or end_raw) and not (start_ok and end_ok and end_formatted):
            lines: list[str] = []
            if start_formatted:
                lines.append(f"2 DATE {start_formatted}")
            lines.append(f"2 NOTE Avslutades: {end_formatted or end_raw}")
            self._placement_end_note_loss = True
            return lines
        if not start_ok:
            # Start is qualified/ranged and there is no dated end.
            return [f"2 DATE {start_formatted}"]

        # Period encoding from the formattable endpoints.
        if start_formatted and end_formatted:
            return [f"2 DATE FROM {start_formatted} TO {end_formatted}"]
        if start_formatted:
            # End exists but has no (formattable) date: prefer FROM <start>.
            return [f"2 DATE FROM {start_formatted}"]
        if end_formatted:
            # Start is dateless, end is dated.
            return [f"2 DATE TO {end_formatted}"]
        # Neither endpoint has a date: emit no DATE line.
        return []

    def _is_placement_child(self, person_id: str, event: Event) -> bool:
        """Return True when ``person_id`` is the placed CHILD of ``event``.

        The placement structure (``1 ADOP`` / ``1 EVEN TYPE Fosterhem``) must be
        emitted only on the placed child's INDI record, never on a foster/
        adoptive parent's. The child role per placement type comes from the
        validators' ``_PLACEMENT_START`` table (``fosterbarn`` for ``foster_home``,
        ``adopterad`` for ``adoption``) rather than being hardcoded, so the
        exporter stays consistent with validation and sync. A non-placement
        event type returns ``False``.

        Args:
            person_id: The person whose INDI record is being written.
            event: The placement start event.

        Returns:
            ``True`` when the person participates in ``event`` with its child
            role; ``False`` otherwise.
        """
        from slaktbusken.model.validators import _PLACEMENT_START

        spec = _PLACEMENT_START.get(event.type)
        if spec is None:
            return False
        return any(
            p.person_id == person_id and p.role == spec.child_role
            for p in event.participants
        )

    def _write_adoption_event(
        self, event: Event, data: ProjectData
    ) -> list[str]:
        """Write a GEDCOM ``ADOP`` structure for an Adoption event.

        Emits the standard ``1 ADOP`` event detail (``DATE``/``PLAC``/source
        citations via :meth:`_write_event_detail`), then a subordinate
        ``2 FAMC @Fxx@`` pointing at the derived family for this event's
        Parent_Set when such a family exists (Requirements 11.2a, 11.2c, 11.2d).

        Args:
            event: The adoption Event to export.
            data: Full project data (for derived-family lookup).

        Returns:
            List of GEDCOM lines for this adoption event.

        DATE handling: ``_write_event_detail`` emits the plain ``2 DATE`` from
        10.1a, but for a placement with a paired end the DATE must become a
        GEDCOM period (``FROM <start> TO <end>`` etc.). We therefore delegate to
        ``_write_event_detail`` for the tag, ``PLAC`` and source citations, drop
        the plain ``DATE`` line(s) it produced, and splice in the period-aware
        ``DATE``/``NOTE`` lines from ``_placement_date_lines`` right after the
        ``1 ADOP`` header. This keeps PLAC/sources/FAMC working, produces the
        period DATE, and never double-emits ``DATE``.
        """
        detail = self._write_event_detail("ADOP", event)
        # Drop the plain top-level DATE line(s) emitted by _write_event_detail;
        # source-citation TEXT lines live at level 3 and are not affected.
        detail = [line for line in detail if not line.startswith("2 DATE ")]

        # detail[0] is "1 ADOP"; insert the period-aware DATE/NOTE right after.
        date_lines = self._placement_date_lines(event, data)
        lines = [detail[0], *date_lines, *detail[1:]]

        family_gedcom_id = self._derived_family_gedcom_id(event, data)
        if family_gedcom_id:
            lines.append(f"2 FAMC {family_gedcom_id}")

        return lines

    def _write_foster_event(
        self, event: Event, data: ProjectData
    ) -> list[str]:
        """Write a GEDCOM ``EVEN`` structure for a Fosterhem event.

        Fosterhem has no GEDCOM tag, so it is exported as a custom event like
        Flytt: ``1 EVEN`` / ``2 TYPE Fosterhem`` / a period-aware ``2 DATE``
        (``FROM <start> TO <end>`` etc. when a paired Placement_End_Event
        exists, else the plain start date — Requirement 11.2e) / ``2 PLAC``
        (when present), followed by a subordinate ``2 FAMC @Fxx@``
        pointing at the derived family for this event's Parent_Set when such a
        family exists (Requirements 11.2b, 11.2c, 11.2d).

        Args:
            event: The foster_home Event to export.
            data: Full project data (for derived-family lookup).

        Returns:
            List of GEDCOM lines for this foster event.
        """
        lines: list[str] = ["1 EVEN", "2 TYPE Fosterhem"]

        # DATE line(s) — period-aware when a paired end exists, else the plain
        # 10.1a DATE (Requirement 11.2e).
        lines.extend(self._placement_date_lines(event, data))

        # PLAC line resolved from event.place.
        if event.place and event.place.place_id:
            place_str = self._resolve_place_hierarchy(event.place.place_id)
            if place_str:
                lines.append(f"2 PLAC {place_str}")

        # Derived-family linkage.
        family_gedcom_id = self._derived_family_gedcom_id(event, data)
        if event.cause_of_death:
            lines.extend(text_lines(2, "CAUS", event.cause_of_death))
        lines.extend(self._slk_event_lines(event, None))

        if family_gedcom_id:
            lines.append(f"2 FAMC {family_gedcom_id}")

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

        # HUSB/WIFE are structural placeholders (Requirement 4). One line per
        # slot at most; the real roles and order go to _SLK_PARTNER.
        slots = self._assign_slots(family.partners, self._persons_for(data))
        if slots.husb is not None:
            lines.append(f"1 HUSB {self._to_gedcom_id(slots.husb)}")
        if slots.wife is not None:
            lines.append(f"1 WIFE {self._to_gedcom_id(slots.wife)}")
        if slots.conflicts:
            self._placeholder_warnings.append(
                self._placeholder_warning(family, slots, data)
            )

        # Partner list order and stored roles, tied to the individuals.
        for partner in family.partners:
            lines.append(f"1 _SLK_PARTNER {self._to_gedcom_id(partner.person_id)}")
            if partner.role:
                lines.extend(text_lines(2, "_SLK_ROLE", partner.role))

        # Children
        for child_id in family.children:
            child_gedcom_id = self._to_gedcom_id(child_id)
            lines.append(f"1 CHIL {child_gedcom_id}")

        # Family events
        for event in self._family_events_for(family, data):
            lines.extend(self._write_family_event(event))

        return lines

    # ------------------------------------------------------------------
    # Partner placeholders and family events (Requirements 1, 4)
    # ------------------------------------------------------------------

    def _persons_for(self, data: ProjectData) -> dict[str, Person]:
        """Person lookup of the current export (built on demand)."""
        if not self._persons and data.persons:
            self._persons = {p.id: p for p in data.persons}
        return self._persons

    @staticmethod
    def _assign_slots(
        partners: list, persons: dict[str, Person]
    ) -> SlotAssignment:
        """Place the partners in the HUSB and WIFE placeholder slots.

        Both sexes known (``M``/``F``) and different: the slot follows sex.
        Otherwise partner list order (HUSB, then WIFE). One partner: the slot
        of a known sex ``M`` or ``F``, else HUSB. Never two lines of a slot.
        """

        def sex_of(person_id: str) -> str:
            person = persons.get(person_id)
            return person.sex if person is not None else "U"

        ids = [p.person_id for p in partners]
        result = SlotAssignment()
        if not ids:
            return result
        if len(ids) == 1:
            if sex_of(ids[0]) == "F":
                result.wife = ids[0]
            else:
                result.husb = ids[0]
        else:
            first, second = ids[0], ids[1]
            if {sex_of(first), sex_of(second)} == {"M", "F"}:
                if sex_of(first) == "M":
                    result.husb, result.wife = first, second
                else:
                    result.husb, result.wife = second, first
            else:
                result.husb, result.wife = first, second
        for slot, person_id in (("HUSB", result.husb), ("WIFE", result.wife)):
            if person_id is None:
                continue
            sex = sex_of(person_id)
            if (
                (sex == "M" and slot == "WIFE")
                or (sex == "F" and slot == "HUSB")
                or sex == "X"
            ):
                result.conflicts.append((person_id, slot))
        return result

    def _person_label(self, person_id: str) -> str:
        """Display name of a person for export-log text."""
        person = self._persons.get(person_id)
        if person is not None and person.names:
            name = person.names[0]
            text = f"{name.given or ''} {name.surname or ''}".strip()
            if text:
                return text
        return person_id

    def _placeholder_warning(
        self, family: Family, slots: SlotAssignment, data: ProjectData
    ) -> str:
        """Swedish export-log warning for one family with a placeholder conflict."""
        family_label = self._to_gedcom_id(family.id).strip("@")
        names = ", ".join(self._person_label(p.person_id) for p in family.partners)
        parts: list[str] = []
        for person_id, slot in slots.conflicts:
            person = self._persons_for(data).get(person_id)
            sex_word = _SEX_WORD.get(person.sex if person else "", "okänt kön")
            parts.append(
                f"{self._person_label(person_id)} ({sex_word}) står som {slot}."
            )
        return (
            f"Familj {family_label} ({names}): {' '.join(parts)} "
            "HUSB/WIFE är en teknisk platshållare, inte ett påstående om kön "
            "eller roll. Rätt roller och ordning finns i _SLK_PARTNER."
        )

    def _orphan_index(self, data: ProjectData) -> dict[str, list[Event]]:
        """Map family id to the orphan family events that belong to it.

        An orphan is a family-type event listed in no ``Family.event_ids``. It
        belongs to a family when its participant person-id set equals the
        partner person-id set of exactly one family. Other orphans are kept in
        ``_fallback_family_events`` for the Individual_Fallback.
        """
        if self._orphan_by_family is not None:
            return self._orphan_by_family
        listed: set[str] = set()
        for family in data.families:
            listed.update(family.event_ids)
        partner_sets = [
            (family.id, frozenset(p.person_id for p in family.partners))
            for family in data.families
        ]
        index: dict[str, list[Event]] = {}
        for event in data.events:
            if event.type not in _FAMILY_EVENT_TYPES or event.id in listed:
                continue
            people = frozenset(p.person_id for p in event.participants)
            matches = [fid for fid, pset in partner_sets if people and pset == people]
            if len(matches) == 1:
                index.setdefault(matches[0], []).append(event)
            else:
                self._fallback_family_events.append(event)
        self._orphan_by_family = index
        return index

    def _family_events_for(
        self, family: Family, data: ProjectData
    ) -> list[Event]:
        """Family events to write in ``family``, each event at most once.

        The listed family-type events not yet written come first, then the
        orphan events that match this family alone.
        """
        events: list[Event] = []
        for event_id in family.event_ids:
            event = self._events.get(event_id)
            if event and event.type in _FAMILY_EVENT_TYPES:
                events.append(event)
        events.extend(self._orphan_index(data).get(family.id, []))
        result: list[Event] = []
        for event in events:
            if event.id in self._written_family_events:
                continue
            self._written_family_events.add(event.id)
            result.append(event)
        return result

    def _write_family_event(self, event: Event) -> list[str]:
        """Write one family event with its ``_SLK_PART`` participants."""
        tag = _FAMILY_EVENT_TYPE_TO_TAG[event.type]
        lines = self._write_event_detail(tag, event)
        if event.type == "custom_family_event" and event.custom_type_name:
            lines[1:1] = text_lines(2, "TYPE", event.custom_type_name)
        for participant in event.participants:
            if participant.person_id not in self._persons:
                continue
            lines.append(
                f"2 _SLK_PART {self._to_gedcom_id(participant.person_id)}"
            )
            if participant.role:
                lines.extend(text_lines(3, "_SLK_ROLE", participant.role))
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

        lines.extend(self._source_slk_lines(source))
        for ref in source.repository_refs:
            lines.extend(self._write_repository_ref(source, ref))
        return lines

    def _write_repository_ref(
        self, source: Source, ref: RepositoryRef
    ) -> list[str]:
        """``1 REPO`` reference of a SOUR record (Requirement 9.7, 9.8)."""
        if ref.repository_id not in self._repositories:
            warning = (
                f"Källan {source.title or source.id} pekar på ett arkiv som"
                " saknas och exporterades utan arkivhänvisning."
            )
            if warning not in self._repo_warnings:
                self._repo_warnings.append(warning)
            return []
        lines = [f"1 REPO {self._to_gedcom_id(ref.repository_id)}"]
        if ref.call_number or ref.media_type:
            lines.extend(text_lines(2, "CALN", ref.call_number))
            if ref.media_type:
                lines.extend(text_lines(3, "MEDI", ref.media_type))
        if ref.notes:
            lines.extend(text_lines(2, "NOTE", ref.notes))
        if ref.source_type:
            lines.extend(text_lines(2, "_SLK_RSTYPE", ref.source_type))
        if ref.image_number is not None:
            lines.append(f"2 _SLK_RIMG {ref.image_number}")
        if ref.page_number is not None:
            lines.append(f"2 _SLK_RPAGE {ref.page_number}")
        if ref.media_name:
            lines.extend(text_lines(2, "_SLK_RMEDNAME", ref.media_name))
        return lines

    def _write_repositories(self, data: ProjectData) -> list[str]:
        """REPO records: used ones first, then the unused (Requirement 9.7).

        A Repository that no Source references is not written.
        """
        lines: list[str] = []
        written: set[str] = set()
        for source in data.sources:
            for ref in source.repository_refs:
                repo = self._repositories.get(ref.repository_id)
                if repo is None or repo.id in written:
                    continue
                written.add(repo.id)
                lines.extend(self._write_repository(repo))
        # Repositories that no SOUR references, in project order.
        for repo in data.repositories:
            if repo.id in written:
                continue
            written.add(repo.id)
            lines.extend(self._write_repository(repo))
        return lines

    def _write_repository(self, repo: Repository) -> list[str]:
        """One level-0 REPO record."""
        lines = [f"0 {self._to_gedcom_id(repo.id)} REPO"]
        lines.extend(text_lines(1, "NAME", repo.name))
        if repo.address:
            lines.extend(text_lines(1, "ADDR", repo.address))
        for tag, values in (
            ("PHON", repo.phone),
            ("EMAIL", repo.email),
            ("WWW", repo.web),
        ):
            for value in values:
                lines.extend(text_lines(1, tag, value))
        if repo.notes:
            lines.extend(text_lines(1, "NOTE", repo.notes))
        if repo.type:
            lines.extend(text_lines(1, "_SLK_RTYPE", repo.type))
        for external_id in repo.external_ids:
            lines.extend(text_lines(1, "_SLK_XID", external_id))
        return lines

    def _source_slk_lines(self, source: Source) -> list[str]:
        """``_SLK_`` metadata lines of a SOUR record (Requirement 9.1, 9.2)."""
        lines: list[str] = []
        if source.source_type:
            lines.extend(text_lines(1, "_SLK_STYPE", source.source_type))
        if source.provider:
            lines.extend(text_lines(1, "_SLK_PROV", source.provider))
        lev_name = self._leverantor_names.get(source.leverantor_id, "")
        if lev_name:
            lines.extend(text_lines(1, "_SLK_LEV", lev_name))
        kt_name = self._kalltyp_names.get(source.kalltyp_id, "")
        if kt_name:
            lines.extend(text_lines(1, "_SLK_KTYP", kt_name))
        fields = source.structured_reference.fields
        entries = [
            (key, value)
            for key, value in fields.items()
            if key and not re.search(r"\s", key)
            and (value is None or isinstance(value, (str, int)))
        ]
        if entries:
            lines.append("1 _SLK_SREF")
            for key, value in entries:
                # ensure_ascii=False keeps å, ä, ö readable; json.dumps never
                # emits a raw line break, so one line per field is enough.
                encoded = json.dumps(value, ensure_ascii=False)
                lines.append(f"2 _SLK_FLD {key} {encoded}")
        return lines

    # ------------------------------------------------------------------
    # Event detail (date + place + source citations)
    # ------------------------------------------------------------------

    @staticmethod
    def _event_token(event: Event) -> str:
        """Event_Token of an event: its id, without whitespace."""
        return re.sub(r"\s+", "_", event.id.strip())

    def _slk_event_lines(
        self,
        event: Event,
        person_id: Optional[str],
        evtype: Optional[str] = None,
    ) -> list[str]:
        """``_SLK_EVTYPE``, ``_SLK_EID`` and ``_SLK_ROLE`` lines of an event.

        ``_SLK_ROLE`` is written for an INDI event (``person_id`` given) when
        the person's role is not ``subject`` and the event is not a placement
        event, because the importer derives the roles of those.
        """
        lines: list[str] = []
        if evtype:
            lines.extend(text_lines(2, "_SLK_EVTYPE", evtype))
        token = self._event_token(event)
        if token:
            lines.append(f"2 _SLK_EID {token}")
        if person_id is not None and event.type not in _PLACEMENT_EVENT_TYPES:
            role = next(
                (p.role for p in event.participants if p.person_id == person_id),
                "",
            )
            if role and role != "subject":
                lines.extend(text_lines(2, "_SLK_ROLE", role))
        return lines

    def _write_individual_event(self, event: Event, person_id: str) -> list[str]:
        """Write an INDI event: its own tag, or ``EVEN`` for types without one."""
        tag = _EVENT_TYPE_TO_TAG.get(event.type)
        if tag:
            return self._write_event_detail(tag, event, person_id)
        if event.type == "custom_individual_event":
            lines = self._write_event_detail("EVEN", event, person_id)
            if event.custom_type_name:
                lines[1:1] = text_lines(2, "TYPE", event.custom_type_name)
            return lines
        # Any other type: TYPE holds the type text, _SLK_EVTYPE the type.
        lines = self._write_event_detail("EVEN", event, person_id, evtype=event.type)
        lines[1:1] = text_lines(2, "TYPE", event.type)
        return lines

    def _write_fallback_event(self, event: Event, person_id: str) -> list[str]:
        """Write an orphan family event as Individual_Fallback on one INDI."""
        lines = self._write_event_detail(
            "EVEN", event, person_id, evtype=event.type
        )
        label = (
            event.custom_type_name
            if event.type == "custom_family_event" and event.custom_type_name
            else _FALLBACK_TYPE_LABELS.get(event.type, event.type)
        )
        lines[1:1] = text_lines(2, "TYPE", label)
        return lines

    def _fallback_warning(self, event: Event) -> str:
        """Swedish export-log warning for one Individual_Fallback event."""
        label = _FALLBACK_TYPE_LABELS.get(event.type, event.type)
        if event.type == "custom_family_event" and event.custom_type_name:
            label = event.custom_type_name
        date_text = self._format_date(event.date) if event.date else ""
        names = ", ".join(
            self._person_label(p.person_id) for p in event.participants
        )
        return (
            f"Händelsen {label} ({date_text or 'utan datum'}) med deltagarna "
            f"{names or 'inga'} hör inte till någon enskild familj och skrevs "
            "som en händelse på varje deltagares personpost (_SLK_EID). "
            "Ingen familj skapades."
        )

    def _write_event_detail(
        self,
        tag: str,
        event: Event,
        person_id: Optional[str] = None,
        evtype: Optional[str] = None,
    ) -> list[str]:
        """Write event detail lines (tag, date, place, source citation).

        Args:
            tag: The GEDCOM event tag (e.g., 'BIRT', 'DEAT').
            event: The event to export.
            person_id: The INDI the event is written on (for ``_SLK_ROLE``);
                ``None`` for a FAM event.
            evtype: Value for ``_SLK_EVTYPE`` when the event is an ``EVEN``
                that stands for a Släktbusken event type.

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

        # Source citations: event-level (directly under the event record),
        # then date and place citations as before.
        lines.extend(self._event_citation_lines(event))
        if event.cause_of_death:
            lines.extend(text_lines(2, "CAUS", event.cause_of_death))
        lines.extend(self._slk_event_lines(event, person_id, evtype))
        return lines

    # ------------------------------------------------------------------
    # Citations (shared by events and residence observations)
    # ------------------------------------------------------------------

    _QUALITY_TO_QUAY = {"primary": "3", "secondary": "2", "tertiary": "1"}

    def _event_citation_lines(self, event: Event) -> list[str]:
        """``2 SOUR`` structures for every citation of an event.

        Event, date, place and from_place citations all get a structure; the
        context is written as ``_SLK_CTX`` by :meth:`_write_citation`.
        """
        lines: list[str] = []
        for cit in event_citations(event):
            source = self._sources.get(cit.ref.source_id)
            if source:
                lines.extend(
                    self._write_citation(
                        2, source, cit.ref, cit.context, event_text=True
                    )
                )
        return lines

    def _write_citation(
        self,
        level: int,
        source: Source,
        ref: SourceRef,
        ctx: Optional[CitationContext],
        *,
        event_text: bool,
    ) -> list[str]:
        """Write one citation: ``level SOUR`` and its subordinate lines.

        Quality: ``QUAY`` 3/2/1 for primary/secondary/tertiary; any other
        non-empty text goes to ``_SLK_QUAL`` and no ``QUAY``; ``QUAY 0`` is
        never written. ``_SLK_CTX`` is written for date, place and
        from_place (events only). The note goes to ``NOTE`` for events and to
        ``_SLK_NOTE`` for observations. ``_SLK_ASP`` follows once per aspect,
        in order. Events keep ``TEXT`` with the citation text (hash stability).
        """
        sub = level + 1
        lines: list[str] = [f"{level} SOUR {self._to_gedcom_id(source.id)}"]

        quality = ref.quality or ""
        quay = self._QUALITY_TO_QUAY.get(quality)
        if quay is not None:
            lines.append(f"{sub} QUAY {quay}")
        elif quality.strip():
            lines.extend(text_lines(sub, "_SLK_QUAL", quality))

        if event_text and ctx is not None and ctx != CitationContext.EVENT:
            lines.append(f"{sub} _SLK_CTX {ctx.value}")

        if ref.note:
            tag = "NOTE" if event_text else "_SLK_NOTE"
            lines.extend(text_lines(sub, tag, ref.note))

        for aspect in ref.aspects:
            lines.extend(text_lines(sub, "_SLK_ASP", aspect))

        if event_text:
            citation = build_citation_text(source)
            if citation:
                lines.append(f"{sub} TEXT {citation}")
        return lines

    # ------------------------------------------------------------------
    # Date formatting (ISO → GEDCOM)
    # ------------------------------------------------------------------

    def _format_date(self, date: DateValue) -> str:
        """Format a DateValue into GEDCOM date text via ``export_gedcom_date``.

        Qualifiers, ranges, the Julian escape (before each endpoint), verbatim
        consistent original text and verbatim unparsed text are handled by
        :func:`slaktbusken.gedcom.dates.export_gedcom_date`. Swedish warnings
        for stale original text are collected for the export log.

        Returns:
            GEDCOM date text, or an empty string when there is nothing to write.
        """
        if effective_qualifier(date) != "unparsed" and not _ISO_VALUE_RE.match(
            (date.value or "").strip()
        ):
            # Structured value is not an ISO date: nothing GEDCOM can express.
            return ""
        text, warnings = export_gedcom_date(date)
        for warning in warnings:
            if warning not in self._date_warnings:
                self._date_warnings.append(warning)
        return text.strip()

    @staticmethod
    def _is_period_endpoint(date: Optional[DateValue]) -> bool:
        """True when *date* is a single exact date usable after FROM/TO."""
        return date is not None and effective_qualifier(date) == "exact"

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

        # Research cases, hypotheses and actions are native Släktbusken data
        # with no GEDCOM representation in this version.
        if data.research_cases:
            omitted["Forskningsärenden"] = len(data.research_cases)

        if data.research_hypotheses:
            omitted["Hypoteser"] = len(data.research_hypotheses)

        if data.research_actions:
            omitted["Forskningsåtgärder"] = len(data.research_actions)

        if data.media:
            omitted["Medieobjekt"] = len(data.media)

        # Merge candidates and history have no GEDCOM representation
        # (Requirement 30.12). Retired persons are not in data.persons.
        if data.merge_candidates:
            omitted["Sammanslagningskandidater"] = len(data.merge_candidates)

        if data.merge_history:
            omitted["Sammanslagningshistorik"] = len(data.merge_history)

        # Manual parentage overrides stay in the project file (class D).
        if data.connection_overrides:
            omitted["Anslutningsöverstyrningar"] = len(data.connection_overrides)

        return omitted
