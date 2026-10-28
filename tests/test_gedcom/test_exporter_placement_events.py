"""Unit tests for Adoption (ADOP) and Fosterhem (EVEN/TYPE Fosterhem) export.

Tests verify that ``_write_person`` emits placement start events:

- An Adoption event exports as ``1 ADOP`` with its ``2 DATE``/``2 PLAC`` and a
  ``2 FAMC @Fxx@`` pointing at the derived family whose ``event_ids`` contains
  the event's id.
- A Fosterhem event exports as ``1 EVEN`` / ``2 TYPE Fosterhem`` /
  ``2 DATE`` / ``2 PLAC`` / ``2 FAMC @Fxx@``.
- A descriptive adoption event with no derived family emits ``1 ADOP`` with no
  ``2 FAMC`` (regression for pre-feature descriptive adoption, Requirement 1.9).
- Adoption events are no longer dropped (regression: ``ADOP`` was absent from
  the tag map before this task).
- Two Fosterhem events for the same child (two Parent_Sets) export as two
  separate EVEN/Fosterhem structures.

Validates: Requirements 11.2a, 11.2b, 11.2c, 11.2d
"""

from __future__ import annotations

from pathlib import Path

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _project(
    persons: list[Person],
    families: list[Family],
    events: list[Event],
    places: list[Place] | None = None,
) -> ProjectData:
    """Build a minimal ProjectData."""
    return ProjectData(
        format="släktbuske-file",
        version="0.2",
        project=ProjectMetadata(title="Test"),
        persons=persons,
        families=families,
        events=events,
        places=places or [],
        sources=[],
    )


def _export_lines(data: ProjectData, tmp_path: Path) -> list[str]:
    """Export and return all GEDCOM lines."""
    exporter = GEDCOMExporter()
    exporter.export(data, tmp_path / "test.ged")
    return (tmp_path / "test.ged").read_text(encoding="utf-8").splitlines()


def _child() -> Person:
    return Person(
        id="person_1",
        names=[Name(type="birth", given="Barn", surname="Testsson")],
        sex="M",
    )


def _default_places() -> list[Place]:
    return [Place(id="place_1", name="Ljusdal", type="socken")]


def _indi_block(lines: list[str], gedcom_id: str) -> list[str]:
    """Return the lines of the INDI record for gedcom_id (e.g. '@I1@')."""
    result: list[str] = []
    collecting = False
    for line in lines:
        if line.startswith("0 ") and line.endswith(" INDI"):
            collecting = line == f"0 {gedcom_id} INDI"
            if collecting:
                result.append(line)
            continue
        if line.startswith("0 "):
            collecting = False
            continue
        if collecting:
            result.append(line)
    return result


def _structure_after(block: list[str], header: str) -> list[str]:
    """Return the level-1 structure starting at `header` (level-1) and its
    following level-2+ lines, up to the next level-1 line."""
    out: list[str] = []
    collecting = False
    for line in block:
        if line == header and not collecting:
            collecting = True
            out.append(line)
            continue
        if collecting:
            if line.startswith("1 "):
                break
            out.append(line)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAdoptionExport:
    """ADOP export with derived-family FAMC linkage."""

    def test_adoption_exports_adop_with_date_place_and_famc(
        self, tmp_path: Path
    ) -> None:
        """An adoption event exports 1 ADOP with DATE/PLAC and a FAMC pointing
        at the derived family whose event_ids contains the event id."""
        child = _child()
        event = Event(
            id="event_1",
            type="adoption",
            participants=[Participant(person_id="person_1", role="adopterad")],
            date=DateValue(value="1950-06-15", precision="exact"),
            place=PlaceRef(place_id="place_1"),
        )
        # foster_sync keys the derived family to the start event via event_ids.
        family = Family(
            id="family_5",
            partners=[FamilyPartner(person_id="person_10", role="husband")],
            children=["person_1"],
            parent_child_links=[
                ParentChildLink(
                    child_id="person_1",
                    parent_id="person_10",
                    parentage_type="adoptive",
                ),
            ],
            event_ids=["event_1"],
        )
        lines = _export_lines(
            _project([child], [family], [event], _default_places()), tmp_path
        )
        block = _indi_block(lines, "@I1@")

        assert "1 ADOP" in block
        adop = _structure_after(block, "1 ADOP")
        assert "2 DATE 15 JUN 1950" in adop
        assert "2 PLAC Ljusdal" in adop
        assert "2 FAMC @F5@" in adop

    def test_descriptive_adoption_has_no_famc(self, tmp_path: Path) -> None:
        """A descriptive adoption event not referenced by any derived family
        exports 1 ADOP with no FAMC line (Requirement 1.9)."""
        child = _child()
        event = Event(
            id="event_1",
            type="adoption",
            participants=[Participant(person_id="person_1", role="adopterad")],
            date=DateValue(value="1950", precision="exact"),
        )
        lines = _export_lines(
            _project([child], [], [event], _default_places()), tmp_path
        )
        block = _indi_block(lines, "@I1@")

        assert "1 ADOP" in block
        adop = _structure_after(block, "1 ADOP")
        assert "2 DATE 1950" in adop
        assert not any(l.startswith("2 FAMC") for l in adop)

    def test_adoption_not_dropped(self, tmp_path: Path) -> None:
        """Regression: adoption events are emitted (ADOP was absent from the
        tag map before this task, so adoption events vanished)."""
        child = _child()
        event = Event(
            id="event_1",
            type="adoption",
            participants=[Participant(person_id="person_1", role="adopterad")],
        )
        lines = _export_lines(_project([child], [], [event]), tmp_path)
        block = _indi_block(lines, "@I1@")
        assert "1 ADOP" in block
        # No double emission.
        assert block.count("1 ADOP") == 1


class TestFosterExport:
    """Fosterhem export as EVEN/TYPE Fosterhem with FAMC linkage."""

    def test_foster_exports_even_type_date_place_famc(
        self, tmp_path: Path
    ) -> None:
        """A foster_home event exports 1 EVEN / 2 TYPE Fosterhem / DATE / PLAC
        / FAMC pointing at the derived family."""
        child = _child()
        event = Event(
            id="event_1",
            type="foster_home",
            participants=[Participant(person_id="person_1", role="fosterbarn")],
            date=DateValue(value="1940-03", precision="exact"),
            place=PlaceRef(place_id="place_1"),
        )
        family = Family(
            id="family_3",
            partners=[FamilyPartner(person_id="person_20", role="husband")],
            children=["person_1"],
            parent_child_links=[
                ParentChildLink(
                    child_id="person_1",
                    parent_id="person_20",
                    parentage_type="foster",
                ),
            ],
            event_ids=["event_1"],
        )
        lines = _export_lines(
            _project([child], [family], [event], _default_places()), tmp_path
        )
        block = _indi_block(lines, "@I1@")

        assert "1 EVEN" in block
        even = _structure_after(block, "1 EVEN")
        assert even[1] == "2 TYPE Fosterhem"
        assert "2 DATE MAR 1940" in even
        assert "2 PLAC Ljusdal" in even
        assert "2 FAMC @F3@" in even

    def test_two_foster_events_same_child_two_structures(
        self, tmp_path: Path
    ) -> None:
        """Two foster_home events (two Parent_Sets) for the same child export
        as two separate EVEN/Fosterhem structures with their own FAMC."""
        child = _child()
        event_a = Event(
            id="event_1",
            type="foster_home",
            participants=[Participant(person_id="person_1", role="fosterbarn")],
            date=DateValue(value="1940", precision="exact"),
        )
        event_b = Event(
            id="event_2",
            type="foster_home",
            participants=[Participant(person_id="person_1", role="fosterbarn")],
            date=DateValue(value="1945", precision="exact"),
        )
        family_a = Family(
            id="family_3",
            partners=[FamilyPartner(person_id="person_20", role="husband")],
            children=["person_1"],
            parent_child_links=[
                ParentChildLink(
                    child_id="person_1",
                    parent_id="person_20",
                    parentage_type="foster",
                ),
            ],
            event_ids=["event_1"],
        )
        family_b = Family(
            id="family_4",
            partners=[FamilyPartner(person_id="person_21", role="husband")],
            children=["person_1"],
            parent_child_links=[
                ParentChildLink(
                    child_id="person_1",
                    parent_id="person_21",
                    parentage_type="foster",
                ),
            ],
            event_ids=["event_2"],
        )
        lines = _export_lines(
            _project([child], [family_a, family_b], [event_a, event_b]),
            tmp_path,
        )
        block = _indi_block(lines, "@I1@")

        assert block.count("1 EVEN") == 2
        assert block.count("2 TYPE Fosterhem") == 2
        assert "2 FAMC @F3@" in block
        assert "2 FAMC @F4@" in block


# ---------------------------------------------------------------------------
# Task 10.1b — Placement_End_Event date carried on the paired start structure
# ---------------------------------------------------------------------------


def _foster_family_with_end(
    start_id: str = "event_1",
    end_id: str = "event_2",
    family_id: str = "family_3",
    parent_id: str = "person_20",
) -> Family:
    """A derived foster family whose event_ids holds the start AND paired end.

    foster_sync pairs an end to its start by appending the end id to the same
    derived family whose event_ids already holds the start id.
    """
    return Family(
        id=family_id,
        partners=[FamilyPartner(person_id=parent_id, role="husband")],
        children=["person_1"],
        parent_child_links=[
            ParentChildLink(
                child_id="person_1",
                parent_id=parent_id,
                parentage_type="foster",
            ),
        ],
        event_ids=[start_id, end_id],
    )


def _adoption_family_with_end(
    start_id: str = "event_1",
    end_id: str = "event_2",
    family_id: str = "family_5",
    parent_id: str = "person_10",
) -> Family:
    """A derived adoptive family whose event_ids holds the start AND paired end."""
    return Family(
        id=family_id,
        partners=[FamilyPartner(person_id=parent_id, role="husband")],
        children=["person_1"],
        parent_child_links=[
            ParentChildLink(
                child_id="person_1",
                parent_id=parent_id,
                parentage_type="adoptive",
            ),
        ],
        event_ids=[start_id, end_id],
    )


class TestFosterEndDatePeriod:
    """The foster end date rides on the paired EVEN structure's DATE line."""

    def test_both_dates_known_emits_period(self, tmp_path: Path) -> None:
        """Both start and end dated → 2 DATE FROM <start> TO <end>."""
        child = _child()
        start = Event(
            id="event_1",
            type="foster_home",
            participants=[Participant(person_id="person_1", role="fosterbarn")],
            date=DateValue(value="1950-01-01", precision="exact"),
        )
        end = Event(
            id="event_2",
            type="foster_home_ended",
            participants=[Participant(person_id="person_1", role="fosterbarn")],
            date=DateValue(value="1960-01-01", precision="exact"),
        )
        lines = _export_lines(
            _project([child], [_foster_family_with_end()], [start, end]),
            tmp_path,
        )
        block = _indi_block(lines, "@I1@")
        even = _structure_after(block, "1 EVEN")
        assert "2 DATE FROM 1 JAN 1950 TO 1 JAN 1960" in even
        # The end is never emitted as its own structure.
        assert block.count("1 EVEN") == 1
        assert block.count("2 TYPE Fosterhem") == 1

    def test_start_only_emits_from(self, tmp_path: Path) -> None:
        """End exists but is dateless → 2 DATE FROM <start>."""
        child = _child()
        start = Event(
            id="event_1",
            type="foster_home",
            participants=[Participant(person_id="person_1", role="fosterbarn")],
            date=DateValue(value="1950-01-01", precision="exact"),
        )
        end = Event(
            id="event_2",
            type="foster_home_ended",
            participants=[Participant(person_id="person_1", role="fosterbarn")],
            date=None,
        )
        lines = _export_lines(
            _project([child], [_foster_family_with_end()], [start, end]),
            tmp_path,
        )
        block = _indi_block(lines, "@I1@")
        even = _structure_after(block, "1 EVEN")
        assert "2 DATE FROM 1 JAN 1950" in even
        assert not any(l.startswith("2 DATE TO ") for l in even)

    def test_end_only_emits_to(self, tmp_path: Path) -> None:
        """Start dateless, end dated → 2 DATE TO <end>."""
        child = _child()
        start = Event(
            id="event_1",
            type="foster_home",
            participants=[Participant(person_id="person_1", role="fosterbarn")],
            date=None,
        )
        end = Event(
            id="event_2",
            type="foster_home_ended",
            participants=[Participant(person_id="person_1", role="fosterbarn")],
            date=DateValue(value="1960-01-01", precision="exact"),
        )
        lines = _export_lines(
            _project([child], [_foster_family_with_end()], [start, end]),
            tmp_path,
        )
        block = _indi_block(lines, "@I1@")
        even = _structure_after(block, "1 EVEN")
        assert "2 DATE TO 1 JAN 1960" in even

    def test_no_paired_end_keeps_plain_date(self, tmp_path: Path) -> None:
        """Regression (10.1a): with no paired end the plain 2 DATE remains."""
        child = _child()
        start = Event(
            id="event_1",
            type="foster_home",
            participants=[Participant(person_id="person_1", role="fosterbarn")],
            date=DateValue(value="1950-01-01", precision="exact"),
        )
        family = Family(
            id="family_3",
            partners=[FamilyPartner(person_id="person_20", role="husband")],
            children=["person_1"],
            parent_child_links=[
                ParentChildLink(
                    child_id="person_1",
                    parent_id="person_20",
                    parentage_type="foster",
                ),
            ],
            event_ids=["event_1"],
        )
        lines = _export_lines(
            _project([child], [family], [start]), tmp_path
        )
        block = _indi_block(lines, "@I1@")
        even = _structure_after(block, "1 EVEN")
        assert "2 DATE 1 JAN 1950" in even
        assert not any("FROM" in l or l.startswith("2 DATE TO") for l in even)

    def test_end_event_not_emitted_as_own_structure(
        self, tmp_path: Path
    ) -> None:
        """The end event produces no second EVEN/TYPE structure of its own."""
        child = _child()
        start = Event(
            id="event_1",
            type="foster_home",
            participants=[Participant(person_id="person_1", role="fosterbarn")],
            date=DateValue(value="1950-01-01", precision="exact"),
        )
        end = Event(
            id="event_2",
            type="foster_home_ended",
            participants=[Participant(person_id="person_1", role="fosterbarn")],
            date=DateValue(value="1960-01-01", precision="exact"),
        )
        lines = _export_lines(
            _project([child], [_foster_family_with_end()], [start, end]),
            tmp_path,
        )
        block = _indi_block(lines, "@I1@")
        # Exactly one Fosterhem structure; no orphan end structure.
        assert block.count("1 EVEN") == 1
        assert block.count("2 TYPE Fosterhem") == 1

    def test_unformattable_end_falls_back_to_note(
        self, tmp_path: Path
    ) -> None:
        """An end date _format_date cannot render → plain start DATE + labelled
        NOTE, and export() surfaces the Swedish structure-loss warning."""
        child = _child()
        start = Event(
            id="event_1",
            type="foster_home",
            participants=[Participant(person_id="person_1", role="fosterbarn")],
            date=DateValue(value="1950-01-01", precision="exact"),
        )
        # A free-text / non-ISO end value _format_date returns "" for.
        end = Event(
            id="event_2",
            type="foster_home_ended",
            participants=[Participant(person_id="person_1", role="fosterbarn")],
            date=DateValue(value="omkring påsk 1960", precision="approximate"),
        )
        data = _project([child], [_foster_family_with_end()], [start, end])
        exporter = GEDCOMExporter()
        result = exporter.export(data, tmp_path / "test.ged")
        lines = (tmp_path / "test.ged").read_text(encoding="utf-8").splitlines()
        block = _indi_block(lines, "@I1@")
        even = _structure_after(block, "1 EVEN")
        assert "2 DATE 1 JAN 1950" in even
        assert "2 NOTE Avslutades: omkring påsk 1960" in even
        assert any("Placeringens slutdatum" in w for w in result.warnings)


class TestAdoptionEndDatePeriod:
    """The adoption end date rides on the paired ADOP structure's DATE line."""

    def test_both_dates_known_emits_period(self, tmp_path: Path) -> None:
        """ADOP with paired end → 2 DATE FROM <start> TO <end>, PLAC + FAMC kept."""
        child = _child()
        start = Event(
            id="event_1",
            type="adoption",
            participants=[Participant(person_id="person_1", role="adopterad")],
            date=DateValue(value="1950-01-01", precision="exact"),
            place=PlaceRef(place_id="place_1"),
        )
        end = Event(
            id="event_2",
            type="adoption_ended",
            participants=[Participant(person_id="person_1", role="adopterad")],
            date=DateValue(value="1960-01-01", precision="exact"),
        )
        lines = _export_lines(
            _project(
                [child],
                [_adoption_family_with_end()],
                [start, end],
                _default_places(),
            ),
            tmp_path,
        )
        block = _indi_block(lines, "@I1@")
        adop = _structure_after(block, "1 ADOP")
        assert "2 DATE FROM 1 JAN 1950 TO 1 JAN 1960" in adop
        # PLAC and FAMC from 10.1a still present; no double DATE.
        assert "2 PLAC Ljusdal" in adop
        assert "2 FAMC @F5@" in adop
        assert sum(1 for l in adop if l.startswith("2 DATE")) == 1
        # End not emitted as its own structure.
        assert block.count("1 ADOP") == 1

    def test_start_only_emits_from(self, tmp_path: Path) -> None:
        """ADOP, end dateless → 2 DATE FROM <start>."""
        child = _child()
        start = Event(
            id="event_1",
            type="adoption",
            participants=[Participant(person_id="person_1", role="adopterad")],
            date=DateValue(value="1950-01-01", precision="exact"),
        )
        end = Event(
            id="event_2",
            type="adoption_ended",
            participants=[Participant(person_id="person_1", role="adopterad")],
            date=None,
        )
        lines = _export_lines(
            _project([child], [_adoption_family_with_end()], [start, end]),
            tmp_path,
        )
        block = _indi_block(lines, "@I1@")
        adop = _structure_after(block, "1 ADOP")
        assert "2 DATE FROM 1 JAN 1950" in adop
        assert not any(l.startswith("2 DATE TO ") for l in adop)

    def test_end_only_emits_to(self, tmp_path: Path) -> None:
        """ADOP start dateless, end dated → 2 DATE TO <end>."""
        child = _child()
        start = Event(
            id="event_1",
            type="adoption",
            participants=[Participant(person_id="person_1", role="adopterad")],
            date=None,
        )
        end = Event(
            id="event_2",
            type="adoption_ended",
            participants=[Participant(person_id="person_1", role="adopterad")],
            date=DateValue(value="1960-01-01", precision="exact"),
        )
        lines = _export_lines(
            _project([child], [_adoption_family_with_end()], [start, end]),
            tmp_path,
        )
        block = _indi_block(lines, "@I1@")
        adop = _structure_after(block, "1 ADOP")
        assert "2 DATE TO 1 JAN 1960" in adop

    def test_no_paired_end_keeps_plain_date(self, tmp_path: Path) -> None:
        """Regression (10.1a): with no paired end the plain 2 DATE remains."""
        child = _child()
        start = Event(
            id="event_1",
            type="adoption",
            participants=[Participant(person_id="person_1", role="adopterad")],
            date=DateValue(value="1950-01-01", precision="exact"),
        )
        family = Family(
            id="family_5",
            partners=[FamilyPartner(person_id="person_10", role="husband")],
            children=["person_1"],
            parent_child_links=[
                ParentChildLink(
                    child_id="person_1",
                    parent_id="person_10",
                    parentage_type="adoptive",
                ),
            ],
            event_ids=["event_1"],
        )
        lines = _export_lines(_project([child], [family], [start]), tmp_path)
        block = _indi_block(lines, "@I1@")
        adop = _structure_after(block, "1 ADOP")
        assert "2 DATE 1 JAN 1950" in adop
        assert not any("FROM" in l or l.startswith("2 DATE TO") for l in adop)
