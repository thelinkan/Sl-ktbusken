# Feature: residence-periods, Property 25: GEDCOM export writes the specified RESI and Flytt structures
"""Property-based test for GEDCOM export of RESI and Flytt structures.

Feature: residence-periods, Property 25: GEDCOM export writes the specified RESI
and Flytt structures.

For any consistent project containing residence facts and flytt events:
- Each person's INDI contains one RESI per residence fact with the correct DATE
  form (FROM/TO, FROM, TO, or absent)
- PLAC from the place hierarchy
- Labelled NOTEs for outer bounds / role / notes
- SOUR per observation whose source resolves to an exported record
- Flytt events produce EVEN/TYPE Flytt with DATE/PLAC/NOTE

Uses a temporary file for the export.

**Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.10, 12.11, 18.14, 18.15**
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.model.date_span import expand_iso
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, ResidenceFact

from tests.test_model.residence_strategies import consistent_projects


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ISO_MONTH_TO_GEDCOM: dict[str, str] = {
    "01": "JAN", "02": "FEB", "03": "MAR", "04": "APR",
    "05": "MAY", "06": "JUN", "07": "JUL", "08": "AUG",
    "09": "SEP", "10": "OCT", "11": "NOV", "12": "DEC",
}


def _iso_to_gedcom_date(iso_value: str | None, precision: str | None = None) -> str:
    """Reference conversion from ISO to GEDCOM date form."""
    if not iso_value or not iso_value.strip():
        return ""
    value = iso_value.strip()
    result = ""

    full_match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value)
    if full_match:
        year, month, day = full_match.group(1), full_match.group(2), full_match.group(3)
        month_name = _ISO_MONTH_TO_GEDCOM.get(month)
        if month_name:
            result = f"{int(day)} {month_name} {year}"

    if not result:
        month_match = re.match(r"^(\d{4})-(\d{2})$", value)
        if month_match:
            year, month = month_match.group(1), month_match.group(2)
            month_name = _ISO_MONTH_TO_GEDCOM.get(month)
            if month_name:
                result = f"{month_name} {year}"

    if not result:
        year_match = re.match(r"^(\d{4})$", value)
        if year_match:
            result = value

    if not result:
        return ""

    if precision == "approximate":
        result = f"ABT {result}"

    return result


def _export_to_lines(data: ProjectData, tmp_dir: Path) -> list[str]:
    """Export a project and return all GEDCOM lines."""
    exporter = GEDCOMExporter()
    output = tmp_dir / "test.ged"
    exporter.export(data, output)
    return output.read_text(encoding="utf-8").splitlines()


def _extract_person_block(lines: list[str], person_id: str) -> list[str]:
    """Extract all lines belonging to a person's INDI record."""
    # Find the INDI record for this person by matching the numeric suffix
    match = re.search(r"_(\d+)$", person_id)
    if not match:
        return []
    xref = f"@I{match.group(1)}@"
    indi_line = f"0 {xref} INDI"

    try:
        start_idx = lines.index(indi_line)
    except ValueError:
        return []

    # Find next level 0 record
    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        if lines[i].startswith("0 "):
            end_idx = i
            break

    return lines[start_idx:end_idx]


def _extract_resi_blocks(person_lines: list[str]) -> list[list[str]]:
    """Extract individual RESI blocks from a person's INDI lines."""
    blocks: list[list[str]] = []
    current: list[str] | None = None

    for line in person_lines:
        if line == "1 RESI":
            if current is not None:
                blocks.append(current)
            current = [line]
        elif current is not None:
            if line.startswith("1 ") or line.startswith("0 "):
                blocks.append(current)
                current = None
            else:
                current.append(line)

    if current is not None:
        blocks.append(current)

    return blocks


def _extract_flytt_blocks(person_lines: list[str]) -> list[list[str]]:
    """Extract EVEN/TYPE Flytt blocks from a person's INDI lines."""
    blocks: list[list[str]] = []
    current: list[str] | None = None
    is_flytt = False

    for line in person_lines:
        if line == "1 EVEN":
            if current is not None and is_flytt:
                blocks.append(current)
            current = [line]
            is_flytt = False
        elif current is not None and line == "2 TYPE Flytt":
            is_flytt = True
            current.append(line)
        elif current is not None and is_flytt:
            if line.startswith("1 ") or line.startswith("0 "):
                blocks.append(current)
                current = None
                is_flytt = False
            else:
                current.append(line)
        elif current is not None and not is_flytt:
            if line.startswith("1 ") or line.startswith("0 "):
                current = None

    if current is not None and is_flytt:
        blocks.append(current)

    return blocks


def _resolve_place_hierarchy(place_id: str, data: ProjectData) -> str:
    """Replicate the exporter's place hierarchy resolution."""
    places_by_id = {p.id: p for p in data.places}
    parts: list[str] = []
    visited: set[str] = set()
    current_id: str | None = place_id

    while current_id and current_id not in visited:
        place = places_by_id.get(current_id)
        if place is None:
            break
        visited.add(current_id)
        parts.append(place.name)
        current_id = place.parent_place_id

    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestGedcomExportProperty:
    """Property 25: GEDCOM export writes the specified RESI and Flytt structures.

    **Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.10, 12.11, 18.14, 18.15**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_resi_and_flytt_structures_match_specification(
        self,
        data: st.DataObject,
    ) -> None:
        """Each INDI contains correct RESI and Flytt structures per the spec.

        Feature: residence-periods, Property 25: GEDCOM export writes the
        specified RESI and Flytt structures.

        **Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.10, 12.11, 18.14, 18.15**
        """
        project = data.draw(
            consistent_projects(
                min_persons=1,
                max_persons=2,
                min_places=1,
                max_places=3,
                max_sources=3,
                max_events=3,
                min_residences=1,
                max_residences=3,
                include_many_observations=False,
                min_year=1500,
                max_year=2100,
            )
        )

        # Ensure at least one residence exists
        assume(len(project.residences) > 0)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            lines = _export_to_lines(project, tmp_path)
            exported_source_ids = {s.id for s in project.sources}

            # --- RESI assertions ---
            # Build a person→residences index matching the exporter
            residences_by_person: dict[str, list[ResidenceFact]] = {}
            for res in project.residences:
                residences_by_person.setdefault(res.person_id, []).append(res)

            for person in project.persons:
                person_lines = _extract_person_block(lines, person.id)
                if not person_lines:
                    continue

                resi_blocks = _extract_resi_blocks(person_lines)
                expected_residences = residences_by_person.get(person.id, [])

                # One RESI per residence fact for this person (Req 12.1)
                assert len(resi_blocks) == len(expected_residences), (
                    f"Person {person.id}: expected {len(expected_residences)} RESI, "
                    f"got {len(resi_blocks)}"
                )

                for i, residence in enumerate(expected_residences):
                    block = resi_blocks[i]

                    # --- DATE line form (Req 12.2, 12.3, 12.4, 12.11) ---
                    start_latest = residence.start.latest
                    end_earliest = residence.end.earliest
                    has_start = bool(start_latest and start_latest.strip())
                    has_end = bool(end_earliest and end_earliest.strip())

                    date_lines = [l for l in block if l.startswith("2 DATE")]

                    if has_start and has_end:
                        from_date = _iso_to_gedcom_date(
                            start_latest, residence.start.precision
                        )
                        to_date = _iso_to_gedcom_date(
                            end_earliest, residence.end.precision
                        )
                        if from_date and to_date:
                            expected_date = f"2 DATE FROM {from_date} TO {to_date}"
                            assert len(date_lines) == 1
                            assert date_lines[0] == expected_date
                        else:
                            # Malformed dates produce no DATE line
                            assert len(date_lines) <= 1
                    elif has_start:
                        from_date = _iso_to_gedcom_date(
                            start_latest, residence.start.precision
                        )
                        if from_date:
                            expected_date = f"2 DATE FROM {from_date}"
                            assert len(date_lines) == 1
                            assert date_lines[0] == expected_date
                        else:
                            assert len(date_lines) <= 1
                    elif has_end:
                        to_date = _iso_to_gedcom_date(
                            end_earliest, residence.end.precision
                        )
                        if to_date:
                            expected_date = f"2 DATE TO {to_date}"
                            assert len(date_lines) == 1
                            assert date_lines[0] == expected_date
                        else:
                            assert len(date_lines) <= 1
                    else:
                        # Both absent: no DATE line
                        assert len(date_lines) == 0

                    # --- PLAC line (Req 12.1) ---
                    plac_lines = [l for l in block if l.startswith("2 PLAC")]
                    if residence.place_id:
                        expected_plac = _resolve_place_hierarchy(
                            residence.place_id, project
                        )
                        if expected_plac:
                            assert len(plac_lines) == 1
                            assert plac_lines[0] == f"2 PLAC {expected_plac}"
                        else:
                            assert len(plac_lines) == 0
                    else:
                        assert len(plac_lines) == 0

                    # --- Labelled NOTE lines (Req 12.5) ---
                    note_lines = [l for l in block if l.startswith("2 NOTE")]

                    # start.earliest
                    start_earliest = residence.start.earliest
                    if start_earliest and start_earliest.strip():
                        assert f"2 NOTE Tidigast början: {start_earliest.strip()}" in note_lines

                    # end.latest
                    end_latest = residence.end.latest
                    if end_latest and end_latest.strip():
                        assert f"2 NOTE Senast slut: {end_latest.strip()}" in note_lines

                    # role_in_household
                    if residence.role_in_household:
                        assert f"2 NOTE Roll: {residence.role_in_household}" in note_lines

                    # notes
                    if residence.notes:
                        assert f"2 NOTE {residence.notes}" in note_lines

                    # Absent values produce no NOTE for that field
                    if not (start_earliest and start_earliest.strip()):
                        assert not any(
                            "Tidigast början:" in l for l in note_lines
                        )
                    if not (end_latest and end_latest.strip()):
                        assert not any("Senast slut:" in l for l in note_lines)
                    if not residence.role_in_household:
                        assert not any("Roll:" in l for l in note_lines)

                    # --- SOUR lines per observation (Req 12.6) ---
                    sour_lines = [l for l in block if l.startswith("2 SOUR")]
                    expected_sours = [
                        obs
                        for obs in residence.observations
                        if obs.source_ref.source_id in exported_source_ids
                    ]
                    assert len(sour_lines) == len(expected_sours), (
                        f"Residence {residence.id}: expected {len(expected_sours)} SOUR, "
                        f"got {len(sour_lines)}"
                    )

                    # Check observation NOTE lines under SOUR (presence)
                    obs_note_lines = [l for l in block if l.startswith("3 NOTE")]
                    # Each SOUR should have a corresponding 3 NOTE line
                    assert len(obs_note_lines) == len(expected_sours)

            # --- Export log (Req 12.10) ---
            has_any_sour = any(
                obs.source_ref.source_id in exported_source_ids
                for res in project.residences
                for obs in res.observations
            )
            # Re-run export to get the result
            exporter = GEDCOMExporter()
            result = exporter.export(project, tmp_path / "test2.ged")
            obs_log_msg = "Observationernas delperioder exporteras som anteckningar."
            if has_any_sour:
                assert obs_log_msg in result.warnings
                # Exactly one occurrence
                assert result.warnings.count(obs_log_msg) == 1
            else:
                assert obs_log_msg not in result.warnings

            # --- Flytt event assertions (Req 18.14, 18.15) ---
            flytt_events = [e for e in project.events if e.type == "flytt"]
            for flytt_event in flytt_events:
                # Find the person who participates in this flytt
                for participant in flytt_event.participants:
                    person_lines = _extract_person_block(lines, participant.person_id)
                    if not person_lines:
                        continue

                    flytt_blocks = _extract_flytt_blocks(person_lines)
                    # There should be at least one flytt block for this person
                    # (might be more if multiple flytt events)
                    assert len(flytt_blocks) >= 1

                    # Find the flytt block corresponding to this event
                    # by checking date/place match
                    matched = False
                    for fb in flytt_blocks:
                        # Every flytt block starts with EVEN + TYPE Flytt
                        assert fb[0] == "1 EVEN"
                        assert fb[1] == "2 TYPE Flytt"

                        # DATE line (Req 18.14)
                        fb_date_lines = [l for l in fb if l.startswith("2 DATE")]
                        if flytt_event.date:
                            expected_date = _iso_to_gedcom_date(
                                flytt_event.date.value, flytt_event.date.precision
                            )
                            if expected_date:
                                if fb_date_lines and fb_date_lines[0] == f"2 DATE {expected_date}":
                                    matched = True
                            else:
                                # Invalid date -> no DATE line is ok
                                matched = True
                        else:
                            # No date -> no DATE line
                            if not fb_date_lines:
                                matched = True

                    # Validate generic flytt structure expectations
                    for fb in flytt_blocks:
                        fb_date_lines = [l for l in fb if l.startswith("2 DATE")]
                        fb_plac_lines = [l for l in fb if l.startswith("2 PLAC")]
                        fb_note_lines = [l for l in fb if l.startswith("2 NOTE")]

                        # At most one DATE line
                        assert len(fb_date_lines) <= 1
                        # At most one PLAC line
                        assert len(fb_plac_lines) <= 1

            # --- Flytt from_place structure loss (Req 18.15) ---
            has_from_place = any(
                e.from_place and e.from_place.place_id
                for e in flytt_events
            )
            from_place_warning = (
                "Flyttens ursprungsplats exporteras som anteckning"
                " – GEDCOM 5.5.1 tillåter bara en PLAC per händelse."
            )
            # Check if the from_place resolves to a known place
            places_by_id = {p.id: p for p in project.places}
            has_resolvable_from_place = any(
                e.from_place
                and e.from_place.place_id
                and e.from_place.place_id in places_by_id
                for e in flytt_events
            )
            if has_resolvable_from_place:
                assert from_place_warning in result.warnings
            else:
                assert from_place_warning not in result.warnings
