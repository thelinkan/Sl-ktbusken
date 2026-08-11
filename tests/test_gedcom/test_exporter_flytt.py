"""Unit tests for Flytt event export in the GEDCOM exporter.

Tests verify that Flytt events are exported as GEDCOM 5.5.1 EVEN structures
with TYPE Flytt, a DATE line when present, PLAC as destination when place is
present, and from_place as a labelled NOTE with structure loss in the export log.

Validates: Requirements 18.14, 18.15
"""

from __future__ import annotations

from pathlib import Path

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _project_with_flytt(
    event: Event,
    places: list[Place] | None = None,
) -> ProjectData:
    """Build a minimal ProjectData containing one Flytt event."""
    person = Person(
        id="person_1",
        names=[Name(type="birth", given="Anders", surname="Svensson")],
        sex="M",
    )
    default_places = [
        Place(id="place_1", name="Ljusdal", type="socken"),
        Place(id="place_2", name="Delsbo", type="socken"),
    ]
    return ProjectData(
        format="släktbuske-file",
        version="0.2",
        project=ProjectMetadata(title="Test"),
        persons=[person],
        families=[],
        events=[event],
        places=places or default_places,
        sources=[],
    )


def _export_lines(data: ProjectData, tmp_path: Path) -> list[str]:
    """Export and return all GEDCOM lines."""
    exporter = GEDCOMExporter()
    exporter.export(data, tmp_path / "test.ged")
    return (tmp_path / "test.ged").read_text(encoding="utf-8").splitlines()


def _flytt_lines(all_lines: list[str]) -> list[str]:
    """Extract lines belonging to the EVEN/TYPE Flytt structure."""
    result: list[str] = []
    in_flytt = False
    for line in all_lines:
        if line == "1 EVEN":
            in_flytt = False
            result_candidate: list[str] = [line]
        elif line == "2 TYPE Flytt" and result_candidate:
            in_flytt = True
            result_candidate.append(line)
        elif in_flytt and line.startswith("2 "):
            result_candidate.append(line)
        elif in_flytt and not line.startswith("2 "):
            result.extend(result_candidate)
            in_flytt = False
            result_candidate = []
    if in_flytt:
        result.extend(result_candidate)
    return result


# ---------------------------------------------------------------------------
# Unit tests: Flytt event EVEN structure (Requirement 18.14)
# ---------------------------------------------------------------------------


class TestFlyttEvenStructure:
    """Tests for the EVEN / TYPE Flytt GEDCOM structure."""

    def test_flytt_produces_even_with_type(self, tmp_path: Path) -> None:
        """A Flytt event produces 1 EVEN followed by 2 TYPE Flytt."""
        event = Event(
            id="event_1",
            type="flytt",
            participants=[Participant(person_id="person_1", role="primary")],
            date=DateValue(value="1870", precision="year"),
            place=PlaceRef(place_id="place_1"),
            from_place=PlaceRef(place_id="place_2"),
        )
        data = _project_with_flytt(event)
        lines = _export_lines(data, tmp_path)

        assert "1 EVEN" in lines
        even_idx = lines.index("1 EVEN")
        assert lines[even_idx + 1] == "2 TYPE Flytt"

    def test_flytt_with_date_writes_date_line(self, tmp_path: Path) -> None:
        """A Flytt with a date produces a 2 DATE line in GEDCOM form."""
        event = Event(
            id="event_1",
            type="flytt",
            participants=[Participant(person_id="person_1", role="primary")],
            date=DateValue(value="1870-06-15", precision="day"),
            place=PlaceRef(place_id="place_1"),
        )
        data = _project_with_flytt(event)
        lines = _export_lines(data, tmp_path)
        flytt = _flytt_lines(lines)

        assert "2 DATE 15 JUN 1870" in flytt

    def test_flytt_without_date_omits_date_line(self, tmp_path: Path) -> None:
        """A Flytt without a date produces no DATE line."""
        event = Event(
            id="event_1",
            type="flytt",
            participants=[Participant(person_id="person_1", role="primary")],
            place=PlaceRef(place_id="place_1"),
        )
        data = _project_with_flytt(event)
        lines = _export_lines(data, tmp_path)
        flytt = _flytt_lines(lines)

        assert not any(l.startswith("2 DATE") for l in flytt)

    def test_flytt_with_place_writes_plac_line(self, tmp_path: Path) -> None:
        """A Flytt with place writes destination as 2 PLAC."""
        event = Event(
            id="event_1",
            type="flytt",
            participants=[Participant(person_id="person_1", role="primary")],
            date=DateValue(value="1870", precision="year"),
            place=PlaceRef(place_id="place_1"),
        )
        data = _project_with_flytt(event)
        lines = _export_lines(data, tmp_path)
        flytt = _flytt_lines(lines)

        assert "2 PLAC Ljusdal" in flytt

    def test_flytt_without_place_omits_plac_line(self, tmp_path: Path) -> None:
        """A Flytt without place produces no PLAC line."""
        event = Event(
            id="event_1",
            type="flytt",
            participants=[Participant(person_id="person_1", role="primary")],
            date=DateValue(value="1870", precision="year"),
        )
        data = _project_with_flytt(event)
        lines = _export_lines(data, tmp_path)
        flytt = _flytt_lines(lines)

        assert not any(l.startswith("2 PLAC") for l in flytt)

    def test_flytt_with_approximate_date(self, tmp_path: Path) -> None:
        """A Flytt with approximate precision adds ABT prefix."""
        event = Event(
            id="event_1",
            type="flytt",
            participants=[Participant(person_id="person_1", role="primary")],
            date=DateValue(value="1870", precision="approximate"),
            place=PlaceRef(place_id="place_1"),
        )
        data = _project_with_flytt(event)
        lines = _export_lines(data, tmp_path)
        flytt = _flytt_lines(lines)

        assert "2 DATE ABT 1870" in flytt

    def test_flytt_with_month_date(self, tmp_path: Path) -> None:
        """A Flytt with month precision date formats correctly."""
        event = Event(
            id="event_1",
            type="flytt",
            participants=[Participant(person_id="person_1", role="primary")],
            date=DateValue(value="1870-03", precision="month"),
            place=PlaceRef(place_id="place_1"),
        )
        data = _project_with_flytt(event)
        lines = _export_lines(data, tmp_path)
        flytt = _flytt_lines(lines)

        assert "2 DATE MAR 1870" in flytt


# ---------------------------------------------------------------------------
# Unit tests: from_place as labelled NOTE (Requirement 18.15)
# ---------------------------------------------------------------------------


class TestFlyttFromPlaceNote:
    """Tests for the from_place NOTE and structure loss logging."""

    def test_from_place_written_as_note(self, tmp_path: Path) -> None:
        """A Flytt with from_place writes it as a labelled NOTE."""
        event = Event(
            id="event_1",
            type="flytt",
            participants=[Participant(person_id="person_1", role="primary")],
            date=DateValue(value="1870", precision="year"),
            place=PlaceRef(place_id="place_1"),
            from_place=PlaceRef(place_id="place_2"),
        )
        data = _project_with_flytt(event)
        lines = _export_lines(data, tmp_path)
        flytt = _flytt_lines(lines)

        assert "2 NOTE Från: Delsbo" in flytt

    def test_from_place_absent_no_note(self, tmp_path: Path) -> None:
        """A Flytt without from_place writes no NOTE."""
        event = Event(
            id="event_1",
            type="flytt",
            participants=[Participant(person_id="person_1", role="primary")],
            date=DateValue(value="1870", precision="year"),
            place=PlaceRef(place_id="place_1"),
        )
        data = _project_with_flytt(event)
        lines = _export_lines(data, tmp_path)
        flytt = _flytt_lines(lines)

        assert not any(l.startswith("2 NOTE") for l in flytt)

    def test_structure_loss_in_export_log(self, tmp_path: Path) -> None:
        """When from_place is exported as NOTE, the export log records the loss."""
        event = Event(
            id="event_1",
            type="flytt",
            participants=[Participant(person_id="person_1", role="primary")],
            date=DateValue(value="1870", precision="year"),
            place=PlaceRef(place_id="place_1"),
            from_place=PlaceRef(place_id="place_2"),
        )
        data = _project_with_flytt(event)
        exporter = GEDCOMExporter()
        result = exporter.export(data, tmp_path / "test.ged")

        assert any(
            "ursprungsplats" in w and "anteckning" in w
            for w in result.warnings
        )

    def test_no_structure_loss_without_from_place(self, tmp_path: Path) -> None:
        """When from_place is absent, no structure loss warning is produced."""
        event = Event(
            id="event_1",
            type="flytt",
            participants=[Participant(person_id="person_1", role="primary")],
            date=DateValue(value="1870", precision="year"),
            place=PlaceRef(place_id="place_1"),
        )
        data = _project_with_flytt(event)
        exporter = GEDCOMExporter()
        result = exporter.export(data, tmp_path / "test.ged")

        assert not any("ursprungsplats" in w for w in result.warnings)

    def test_from_place_with_hierarchy(self, tmp_path: Path) -> None:
        """from_place resolves the full place hierarchy in the NOTE."""
        places = [
            Place(
                id="place_1", name="Ljusdal", type="socken",
                parent_place_id="place_3",
            ),
            Place(
                id="place_2", name="Delsbo", type="socken",
                parent_place_id="place_3",
            ),
            Place(id="place_3", name="Gävleborgs län", type="county"),
        ]
        event = Event(
            id="event_1",
            type="flytt",
            participants=[Participant(person_id="person_1", role="primary")],
            date=DateValue(value="1870", precision="year"),
            place=PlaceRef(place_id="place_1"),
            from_place=PlaceRef(place_id="place_2"),
        )
        data = _project_with_flytt(event, places=places)
        lines = _export_lines(data, tmp_path)
        flytt = _flytt_lines(lines)

        assert "2 NOTE Från: Delsbo, Gävleborgs län" in flytt

    def test_flytt_both_absent_minimal(self, tmp_path: Path) -> None:
        """A Flytt with neither place nor from_place writes only EVEN + TYPE."""
        event = Event(
            id="event_1",
            type="flytt",
            participants=[Participant(person_id="person_1", role="primary")],
            date=DateValue(value="1870", precision="year"),
        )
        data = _project_with_flytt(event)
        lines = _export_lines(data, tmp_path)
        flytt = _flytt_lines(lines)

        assert flytt == ["1 EVEN", "2 TYPE Flytt", "2 DATE 1870"]

    def test_flytt_no_date_no_place_no_from_place(self, tmp_path: Path) -> None:
        """A bare Flytt produces only 1 EVEN / 2 TYPE Flytt."""
        event = Event(
            id="event_1",
            type="flytt",
            participants=[Participant(person_id="person_1", role="primary")],
        )
        data = _project_with_flytt(event)
        lines = _export_lines(data, tmp_path)
        flytt = _flytt_lines(lines)

        assert flytt == ["1 EVEN", "2 TYPE Flytt"]
