"""Unit tests for RESI export in the GEDCOM exporter.

Tests verify that Residence_Facts are exported as GEDCOM 5.5.1 RESI structures
with correct DATE (FROM/TO), PLAC, labelled NOTE, and SOUR lines.

Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.10, 12.11
"""

from __future__ import annotations

from pathlib import Path

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.model.event import SourceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.source import Source


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _project_with_residence(
    residence: ResidenceFact,
    persons: list[Person] | None = None,
    places: list[Place] | None = None,
    sources: list[Source] | None = None,
) -> ProjectData:
    """Build a minimal ProjectData containing one residence fact."""
    default_person = Person(
        id="person_1", names=[Name(type="birth", given="Anders", surname="Svensson")], sex="M"
    )
    default_place = Place(id="place_1", name="Ljusdal", type="socken")
    return ProjectData(
        format="släktbuske-file",
        version="0.1",
        project=ProjectMetadata(title="Test"),
        persons=persons or [default_person],
        families=[],
        events=[],
        places=places or [default_place],
        sources=sources or [],
        residences=[residence],
    )


def _export_lines(data: ProjectData, tmp_path: Path) -> list[str]:
    """Export and return all GEDCOM lines."""
    exporter = GEDCOMExporter()
    exporter.export(data, tmp_path / "test.ged")
    return (tmp_path / "test.ged").read_text(encoding="utf-8").splitlines()


def _resi_lines(all_lines: list[str]) -> list[str]:
    """Extract lines belonging to RESI structures."""
    result: list[str] = []
    in_resi = False
    for line in all_lines:
        if line == "1 RESI":
            in_resi = True
            result.append(line)
        elif in_resi:
            if line.startswith("1 ") or line.startswith("0 "):
                in_resi = False
            else:
                result.append(line)
    return result


# ---------------------------------------------------------------------------
# Test: DATE line forms (Requirements 12.2, 12.3, 12.4)
# ---------------------------------------------------------------------------


class TestResiDateLine:
    """Tests for the RESI DATE line in FROM/TO, FROM-only, TO-only, and omitted forms."""

    def test_from_to_when_both_present(self, tmp_path: Path) -> None:
        """Req 12.2: Non-empty core writes FROM x TO y."""
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1846"),
        )
        lines = _resi_lines(_export_lines(_project_with_residence(res), tmp_path))
        assert "2 DATE FROM 1840 TO 1846" in lines

    def test_from_to_with_full_dates(self, tmp_path: Path) -> None:
        """Req 12.2, 12.11: Full ISO dates convert to DD MON YYYY."""
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1840-01-15"),
            end=Endpoint(earliest="1846-12-31"),
        )
        lines = _resi_lines(_export_lines(_project_with_residence(res), tmp_path))
        assert "2 DATE FROM 15 JAN 1840 TO 31 DEC 1846" in lines

    def test_from_to_with_month_dates(self, tmp_path: Path) -> None:
        """Req 12.2, 12.11: Month precision converts to MON YYYY."""
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1840-06"),
            end=Endpoint(earliest="1846-03"),
        )
        lines = _resi_lines(_export_lines(_project_with_residence(res), tmp_path))
        assert "2 DATE FROM JUN 1840 TO MAR 1846" in lines

    def test_from_only_when_end_absent(self, tmp_path: Path) -> None:
        """Req 12.3: Only start.latest present writes FROM only."""
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1840"),
            end=Endpoint(),
        )
        lines = _resi_lines(_export_lines(_project_with_residence(res), tmp_path))
        assert "2 DATE FROM 1840" in lines
        assert not any("TO" in line for line in lines if line.startswith("2 DATE"))

    def test_to_only_when_start_absent(self, tmp_path: Path) -> None:
        """Req 12.4: Only end.earliest present writes TO only."""
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(),
            end=Endpoint(earliest="1846"),
        )
        lines = _resi_lines(_export_lines(_project_with_residence(res), tmp_path))
        assert "2 DATE TO 1846" in lines
        assert not any("FROM" in line for line in lines if line.startswith("2 DATE"))

    def test_no_date_when_both_absent(self, tmp_path: Path) -> None:
        """Both start.latest and end.earliest absent: no DATE line."""
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(),
            end=Endpoint(),
        )
        lines = _resi_lines(_export_lines(_project_with_residence(res), tmp_path))
        assert not any(line.startswith("2 DATE") for line in lines)

    def test_approximate_precision_adds_abt_prefix(self, tmp_path: Path) -> None:
        """Req 12.11: Approximate precision adds 'ABT ' prefix."""
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1840", precision="approximate"),
            end=Endpoint(earliest="1846", precision="approximate"),
        )
        lines = _resi_lines(_export_lines(_project_with_residence(res), tmp_path))
        assert "2 DATE FROM ABT 1840 TO ABT 1846" in lines


# ---------------------------------------------------------------------------
# Test: PLAC line (Requirement 12.1)
# ---------------------------------------------------------------------------


class TestResiPlacLine:
    """Tests for the RESI PLAC line."""

    def test_plac_from_place_hierarchy(self, tmp_path: Path) -> None:
        """Req 12.1: PLAC holds comma-separated hierarchy, most specific first."""
        parish = Place(id="place_2", name="Gävleborgs län", type="county")
        place = Place(
            id="place_1", name="Ljusdal", type="socken", parent_place_id="place_2"
        )
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1846"),
        )
        data = _project_with_residence(
            res,
            places=[place, parish],
        )
        lines = _resi_lines(_export_lines(data, tmp_path))
        assert "2 PLAC Ljusdal, Gävleborgs län" in lines


# ---------------------------------------------------------------------------
# Test: NOTE lines (Requirement 12.5)
# ---------------------------------------------------------------------------


class TestResiNoteLines:
    """Tests for the labelled NOTE lines under RESI."""

    def test_start_earliest_note(self, tmp_path: Path) -> None:
        """Req 12.5: start.earliest written as labelled NOTE."""
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(earliest="1838", latest="1840"),
            end=Endpoint(earliest="1846"),
        )
        lines = _resi_lines(_export_lines(_project_with_residence(res), tmp_path))
        assert "2 NOTE Tidigast början: 1838" in lines

    def test_end_latest_note(self, tmp_path: Path) -> None:
        """Req 12.5: end.latest written as labelled NOTE."""
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1846", latest="1848"),
        )
        lines = _resi_lines(_export_lines(_project_with_residence(res), tmp_path))
        assert "2 NOTE Senast slut: 1848" in lines

    def test_role_note(self, tmp_path: Path) -> None:
        """Req 12.5: non-empty role_in_household as labelled NOTE."""
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1846"),
            role_in_household="husbonde",
        )
        lines = _resi_lines(_export_lines(_project_with_residence(res), tmp_path))
        assert "2 NOTE Roll: husbonde" in lines

    def test_notes_note(self, tmp_path: Path) -> None:
        """Req 12.5: non-empty notes value as NOTE."""
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1846"),
            notes="Familjen flyttade hit från Hälsingland.",
        )
        lines = _resi_lines(_export_lines(_project_with_residence(res), tmp_path))
        assert "2 NOTE Familjen flyttade hit från Hälsingland." in lines

    def test_no_note_for_absent_values(self, tmp_path: Path) -> None:
        """Req 12.5: Absent values produce no NOTE lines."""
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1846"),
        )
        lines = _resi_lines(_export_lines(_project_with_residence(res), tmp_path))
        note_lines = [l for l in lines if l.startswith("2 NOTE")]
        assert len(note_lines) == 0

    def test_no_note_for_empty_role(self, tmp_path: Path) -> None:
        """Empty role_in_household produces no NOTE."""
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1846"),
            role_in_household="",
        )
        lines = _resi_lines(_export_lines(_project_with_residence(res), tmp_path))
        assert not any("Roll:" in line for line in lines)


# ---------------------------------------------------------------------------
# Test: SOUR lines (Requirement 12.6)
# ---------------------------------------------------------------------------


class TestResiSourLines:
    """Tests for SOUR lines under RESI with observation NOTE."""

    def test_sour_with_observation_note(self, tmp_path: Path) -> None:
        """Req 12.6: SOUR line per Observation with observed_from/to NOTE."""
        source = Source(id="source_1", provider="ArkivDigital", source_type="church_book", title="HFL Ljusdal AI:15")
        obs = Observation(
            source_ref=SourceRef(source_id="source_1", quality="primary"),
            observed_from="1840",
            observed_to="1845",
        )
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1846"),
            observations=[obs],
        )
        data = _project_with_residence(res, sources=[source])
        lines = _resi_lines(_export_lines(data, tmp_path))
        assert "2 SOUR @S1@" in lines
        assert "3 NOTE Observation: 1840-1845" in lines

    def test_sour_not_written_for_unresolved_source(self, tmp_path: Path) -> None:
        """Req 12.6: Observation with source_id not in exported sources is skipped."""
        obs = Observation(
            source_ref=SourceRef(source_id="source_99", quality="primary"),
            observed_from="1840",
            observed_to="1845",
        )
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1846"),
            observations=[obs],
        )
        lines = _resi_lines(_export_lines(_project_with_residence(res), tmp_path))
        assert not any("SOUR" in line for line in lines)

    def test_multiple_observations_in_order(self, tmp_path: Path) -> None:
        """Req 12.6: SOUR lines ordered by Observation position."""
        source1 = Source(id="source_1", provider="ArkivDigital", source_type="church_book", title="HFL 1")
        source2 = Source(id="source_2", provider="ArkivDigital", source_type="church_book", title="HFL 2")
        obs1 = Observation(
            source_ref=SourceRef(source_id="source_1", quality="primary"),
            observed_from="1840",
            observed_to="1845",
        )
        obs2 = Observation(
            source_ref=SourceRef(source_id="source_2", quality="primary"),
            observed_from="1846",
            observed_to="1850",
        )
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1850"),
            observations=[obs1, obs2],
        )
        data = _project_with_residence(res, sources=[source1, source2])
        lines = _resi_lines(_export_lines(data, tmp_path))
        sour_lines = [l for l in lines if "SOUR" in l]
        assert sour_lines == ["2 SOUR @S1@", "2 SOUR @S2@"]

    def test_observation_same_from_to(self, tmp_path: Path) -> None:
        """Single-year observation: NOTE shows just the one year."""
        source = Source(id="source_1", provider="ArkivDigital", source_type="church_book", title="Mantalslängd")
        obs = Observation(
            source_ref=SourceRef(source_id="source_1", quality="primary"),
            observed_from="1866",
            observed_to="1866",
        )
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1866"),
            end=Endpoint(earliest="1866"),
            observations=[obs],
        )
        data = _project_with_residence(res, sources=[source])
        lines = _resi_lines(_export_lines(data, tmp_path))
        assert "3 NOTE Observation: 1866" in lines


# ---------------------------------------------------------------------------
# Test: Export log entry (Requirement 12.10)
# ---------------------------------------------------------------------------


class TestResiExportLog:
    """Tests for the observation-notes export log entry."""

    def test_log_entry_when_sour_written(self, tmp_path: Path) -> None:
        """Req 12.10: Exactly one log entry when at least one SOUR written."""
        source = Source(id="source_1", provider="ArkivDigital", source_type="church_book", title="HFL")
        obs = Observation(
            source_ref=SourceRef(source_id="source_1", quality="primary"),
            observed_from="1840",
            observed_to="1845",
        )
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1845"),
            observations=[obs],
        )
        data = _project_with_residence(res, sources=[source])
        exporter = GEDCOMExporter()
        result = exporter.export(data, tmp_path / "test.ged")
        assert (
            "Observationernas delperioder exporteras som anteckningar."
            in result.warnings
        )
        # Exactly one occurrence
        assert result.warnings.count(
            "Observationernas delperioder exporteras som anteckningar."
        ) == 1

    def test_no_log_entry_when_no_sour(self, tmp_path: Path) -> None:
        """Req 12.10: No log entry when no SOUR lines written."""
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1846"),
        )
        data = _project_with_residence(res)
        exporter = GEDCOMExporter()
        result = exporter.export(data, tmp_path / "test.ged")
        assert (
            "Observationernas delperioder exporteras som anteckningar."
            not in result.warnings
        )


# ---------------------------------------------------------------------------
# Test: ISO→GEDCOM date conversion (Requirement 12.11)
# ---------------------------------------------------------------------------


class TestIsoToGedcomDate:
    """Tests for the ISO→GEDCOM date conversion method."""

    def test_year_only(self) -> None:
        exporter = GEDCOMExporter()
        assert exporter._iso_to_gedcom_date("1875") == "1875"

    def test_month_year(self) -> None:
        exporter = GEDCOMExporter()
        assert exporter._iso_to_gedcom_date("1875-05") == "MAY 1875"

    def test_full_date(self) -> None:
        exporter = GEDCOMExporter()
        assert exporter._iso_to_gedcom_date("1875-05-15") == "15 MAY 1875"

    def test_approximate_year(self) -> None:
        exporter = GEDCOMExporter()
        assert exporter._iso_to_gedcom_date("1875", "approximate") == "ABT 1875"

    def test_approximate_full_date(self) -> None:
        exporter = GEDCOMExporter()
        assert (
            exporter._iso_to_gedcom_date("1875-05-15", "approximate")
            == "ABT 15 MAY 1875"
        )

    def test_none_value(self) -> None:
        exporter = GEDCOMExporter()
        assert exporter._iso_to_gedcom_date(None) == ""

    def test_empty_value(self) -> None:
        exporter = GEDCOMExporter()
        assert exporter._iso_to_gedcom_date("") == ""

    def test_whitespace_value(self) -> None:
        exporter = GEDCOMExporter()
        assert exporter._iso_to_gedcom_date("   ") == ""

    def test_non_approximate_precision_no_prefix(self) -> None:
        exporter = GEDCOMExporter()
        assert exporter._iso_to_gedcom_date("1875", "year") == "1875"
        assert exporter._iso_to_gedcom_date("1875-05", "month") == "MAY 1875"
        assert exporter._iso_to_gedcom_date("1875-05-15", "day") == "15 MAY 1875"


# ---------------------------------------------------------------------------
# Test: RESI structure placement (Requirement 12.1)
# ---------------------------------------------------------------------------


class TestResiPlacement:
    """Tests that RESI is placed under the correct INDI record."""

    def test_resi_under_correct_person(self, tmp_path: Path) -> None:
        """RESI appears under the INDI of the residence's person."""
        person = Person(id="person_1", names=[Name(type="birth", given="Anders", surname="S")], sex="M")
        place = Place(id="place_1", name="Ljusdal", type="socken")
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1846"),
        )
        data = ProjectData(
            format="släktbuske-file",
            version="0.1",
            project=ProjectMetadata(title="Test"),
            persons=[person],
            families=[],
            events=[],
            places=[place],
            sources=[],
            residences=[res],
        )
        lines = _export_lines(data, tmp_path)
        # Find INDI line and subsequent RESI
        indi_idx = lines.index("0 @I1@ INDI")
        # Find next 0-level record
        next_record = None
        for i in range(indi_idx + 1, len(lines)):
            if lines[i].startswith("0 "):
                next_record = i
                break
        person_lines = lines[indi_idx:next_record]
        assert "1 RESI" in person_lines

    def test_resi_not_under_other_person(self, tmp_path: Path) -> None:
        """RESI does not appear under a person it doesn't belong to."""
        person1 = Person(id="person_1", names=[Name(type="birth", given="Anders", surname="S")], sex="M")
        person2 = Person(id="person_2", names=[Name(type="birth", given="Brita", surname="L")], sex="F")
        place = Place(id="place_1", name="Ljusdal", type="socken")
        res = ResidenceFact(
            id="residence_1",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1846"),
        )
        data = ProjectData(
            format="släktbuske-file",
            version="0.1",
            project=ProjectMetadata(title="Test"),
            persons=[person1, person2],
            families=[],
            events=[],
            places=[place],
            sources=[],
            residences=[res],
        )
        lines = _export_lines(data, tmp_path)
        # Find person2's INDI and check no RESI there
        indi2_idx = lines.index("0 @I2@ INDI")
        next_record = None
        for i in range(indi2_idx + 1, len(lines)):
            if lines[i].startswith("0 "):
                next_record = i
                break
        person2_lines = lines[indi2_idx:next_record]
        assert "1 RESI" not in person2_lines
