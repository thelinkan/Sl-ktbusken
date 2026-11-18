"""Unit tests for residence places in the Geographic report and map_data_service.

Tests that residence places are included, labelled with the formatter's
interval string, in the timeline order of Requirement 11.10.

Requirements: 11.7, 11.10
"""

from __future__ import annotations

from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import Endpoint, ResidenceFact
from slaktbusken.reports.geographic import (
    ResidencePlaceEntry,
    residence_places_for_person,
)
from slaktbusken.services.map_data_service import build_markers_for_person


def _make_person(pid: str = "p1") -> Person:
    return Person(id=pid, sex="M", names=[Name(type="birth", given="Erik", surname="Svensson")])


def _make_place(pid: str = "pl1", name: str = "Ekeby", lat=57.0, lng=12.0) -> Place:
    return Place(id=pid, type="farm", name=name, latitude=lat, longitude=lng)


# ---------------------------------------------------------------------------
# residence_places_for_person tests
# ---------------------------------------------------------------------------


class TestResidencePlacesForPerson:
    """Tests for residence_places_for_person in geographic.py."""

    def test_no_residences_returns_empty(self):
        data = ProjectData(persons=[_make_person()])
        entries = residence_places_for_person(data, "p1")
        assert entries == []

    def test_single_residence_returns_one_entry(self):
        place = _make_place()
        fact = ResidenceFact(
            id="r1",
            person_id="p1",
            place_id="pl1",
            start=Endpoint(earliest="1840", latest="1840"),
            end=Endpoint(earliest="1870", latest="1870"),
        )
        data = ProjectData(
            persons=[_make_person()],
            places=[place],
            residences=[fact],
        )
        entries = residence_places_for_person(data, "p1")
        assert len(entries) == 1
        assert entries[0].place_id == "pl1"
        assert entries[0].place_name == "Ekeby"
        assert entries[0].interval_display == "1840\u20131870"
        assert entries[0].residence_id == "r1"

    def test_interval_uses_formatter(self):
        """The interval string comes from format_residence_interval (Req 11.7)."""
        place = _make_place()
        fact = ResidenceFact(
            id="r1",
            person_id="p1",
            place_id="pl1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1870"),
        )
        data = ProjectData(
            persons=[_make_person()],
            places=[place],
            residences=[fact],
        )
        entries = residence_places_for_person(data, "p1")
        # format_residence_interval for latest-only start + earliest-only end
        assert entries[0].interval_display == "senast 1840\u2013tidigast 1870"

    def test_timeline_order_by_start_earliest(self):
        """Entries are ordered by start.earliest ascending (Req 11.10)."""
        place = _make_place()
        facts = [
            ResidenceFact(
                id="r1", person_id="p1", place_id="pl1",
                start=Endpoint(earliest="1860", latest="1860"),
                end=Endpoint(earliest="1870", latest="1870"),
            ),
            ResidenceFact(
                id="r2", person_id="p1", place_id="pl1",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1850", latest="1850"),
            ),
        ]
        data = ProjectData(
            persons=[_make_person()],
            places=[place],
            residences=facts,
        )
        entries = residence_places_for_person(data, "p1")
        assert len(entries) == 2
        # r2 (1840) before r1 (1860)
        assert entries[0].residence_id == "r2"
        assert entries[1].residence_id == "r1"

    def test_absent_earliest_sorts_before_present(self):
        """An absent start.earliest sorts earlier than any present value."""
        place = _make_place()
        facts = [
            ResidenceFact(
                id="r1", person_id="p1", place_id="pl1",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1850", latest="1850"),
            ),
            ResidenceFact(
                id="r2", person_id="p1", place_id="pl1",
                start=Endpoint(earliest=None, latest="1835"),
                end=Endpoint(earliest="1840", latest="1840"),
            ),
        ]
        data = ProjectData(
            persons=[_make_person()],
            places=[place],
            residences=facts,
        )
        entries = residence_places_for_person(data, "p1")
        # r2 (absent earliest) sorts before r1 (1840)
        assert entries[0].residence_id == "r2"
        assert entries[1].residence_id == "r1"

    def test_tie_breaks_on_place_name_swedish_order(self):
        """When dates tie, place name in Swedish order breaks the tie."""
        places = [
            _make_place("pl1", "Östra"),
            _make_place("pl2", "Åkern"),
        ]
        facts = [
            ResidenceFact(
                id="r1", person_id="p1", place_id="pl1",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1850", latest="1850"),
            ),
            ResidenceFact(
                id="r2", person_id="p1", place_id="pl2",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1850", latest="1850"),
            ),
        ]
        data = ProjectData(
            persons=[_make_person()],
            places=places,
            residences=facts,
        )
        entries = residence_places_for_person(data, "p1")
        # Swedish order: Å < Ö, so Åkern before Östra
        assert entries[0].place_name == "Åkern"
        assert entries[1].place_name == "Östra"

    def test_other_person_excluded(self):
        """Only the target person's residences appear."""
        place = _make_place()
        facts = [
            ResidenceFact(
                id="r1", person_id="p1", place_id="pl1",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1850", latest="1850"),
            ),
            ResidenceFact(
                id="r2", person_id="p2", place_id="pl1",
                start=Endpoint(earliest="1830", latest="1830"),
                end=Endpoint(earliest="1840", latest="1840"),
            ),
        ]
        data = ProjectData(
            persons=[_make_person()],
            places=[place],
            residences=facts,
        )
        entries = residence_places_for_person(data, "p1")
        assert len(entries) == 1
        assert entries[0].residence_id == "r1"

    def test_unresolved_place_uses_place_id(self):
        """When the place doesn't exist, the place_id is used as display name."""
        fact = ResidenceFact(
            id="r1", person_id="p1", place_id="missing_place",
            start=Endpoint(earliest="1840", latest="1840"),
            end=Endpoint(earliest="1850", latest="1850"),
        )
        data = ProjectData(
            persons=[_make_person()],
            residences=[fact],
        )
        entries = residence_places_for_person(data, "p1")
        assert entries[0].place_name == "missing_place"
        assert entries[0].latitude is None
        assert entries[0].longitude is None

    def test_coordinates_included(self):
        """Entry carries place coordinates."""
        place = _make_place("pl1", "Ekeby", lat=57.5, lng=12.3)
        fact = ResidenceFact(
            id="r1", person_id="p1", place_id="pl1",
            start=Endpoint(earliest="1840", latest="1840"),
            end=Endpoint(earliest="1850", latest="1850"),
        )
        data = ProjectData(
            persons=[_make_person()],
            places=[place],
            residences=[fact],
        )
        entries = residence_places_for_person(data, "p1")
        assert entries[0].latitude == 57.5
        assert entries[0].longitude == 12.3


# ---------------------------------------------------------------------------
# build_markers_for_person residence integration tests
# ---------------------------------------------------------------------------


class TestMapDataServiceResidences:
    """Tests for residence places in build_markers_for_person."""

    def test_residence_places_included_as_markers(self):
        """A residence with a coordinated place appears as a marker."""
        person = _make_person()
        place = _make_place("pl1", "Ekeby", lat=57.0, lng=12.0)
        fact = ResidenceFact(
            id="r1", person_id="p1", place_id="pl1",
            start=Endpoint(earliest="1840", latest="1840"),
            end=Endpoint(earliest="1870", latest="1870"),
        )
        data = ProjectData(
            persons=[person],
            places=[place],
            residences=[fact],
        )
        markers = build_markers_for_person(data, "p1")
        assert len(markers) == 1
        assert markers[0].place_id == "pl1"
        assert markers[0].place_name == "Ekeby"
        assert len(markers[0].events) == 1
        ev = markers[0].events[0]
        assert ev.event_id == "r1"
        assert ev.event_type == "residence"
        assert ev.event_type_display == "Boende"
        assert ev.date_display == "1840\u20131870"
        assert ev.participants[0].person_id == "p1"

    def test_residence_with_no_coords_excluded(self):
        """A residence at a place without coordinates is not shown on the map."""
        person = _make_person()
        place = Place(id="pl1", type="farm", name="Ekeby", latitude=None, longitude=None)
        fact = ResidenceFact(
            id="r1", person_id="p1", place_id="pl1",
            start=Endpoint(earliest="1840", latest="1840"),
            end=Endpoint(earliest="1870", latest="1870"),
        )
        data = ProjectData(
            persons=[person],
            places=[place],
            residences=[fact],
        )
        markers = build_markers_for_person(data, "p1")
        assert markers == []

    def test_residence_interval_from_formatter(self):
        """The interval label is the formatter's interval string (Req 11.7)."""
        person = _make_person()
        place = _make_place()
        fact = ResidenceFact(
            id="r1", person_id="p1", place_id="pl1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1870"),
        )
        data = ProjectData(
            persons=[person],
            places=[place],
            residences=[fact],
        )
        markers = build_markers_for_person(data, "p1")
        ev = markers[0].events[0]
        assert ev.date_display == "senast 1840\u2013tidigast 1870"

    def test_residence_and_event_share_marker(self):
        """A residence and an event at the same place share one marker."""
        from slaktbusken.model.event import Event, Participant, PlaceRef

        person = _make_person()
        place = _make_place()
        event = Event(
            id="evt1", type="birth",
            participants=[Participant(person_id="p1", role="primary")],
            place=PlaceRef(place_id="pl1"),
        )
        fact = ResidenceFact(
            id="r1", person_id="p1", place_id="pl1",
            start=Endpoint(earliest="1840", latest="1840"),
            end=Endpoint(earliest="1870", latest="1870"),
        )
        data = ProjectData(
            persons=[person],
            places=[place],
            events=[event],
            residences=[fact],
        )
        markers = build_markers_for_person(data, "p1")
        assert len(markers) == 1
        assert len(markers[0].events) == 2
        event_types = {ev.event_type for ev in markers[0].events}
        assert "birth" in event_types
        assert "residence" in event_types

    def test_residence_timeline_order_in_markers(self):
        """Multiple residences at the same place appear in timeline order."""
        person = _make_person()
        place = _make_place()
        facts = [
            ResidenceFact(
                id="r2", person_id="p1", place_id="pl1",
                start=Endpoint(earliest="1860", latest="1860"),
                end=Endpoint(earliest="1870", latest="1870"),
            ),
            ResidenceFact(
                id="r1", person_id="p1", place_id="pl1",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1850", latest="1850"),
            ),
        ]
        data = ProjectData(
            persons=[person],
            places=[place],
            residences=facts,
        )
        markers = build_markers_for_person(data, "p1")
        assert len(markers) == 1
        residence_events = [ev for ev in markers[0].events if ev.event_type == "residence"]
        # After sort, r1 (1840) should come before r2 (1860)
        assert residence_events[0].event_id == "r1"
        assert residence_events[1].event_id == "r2"

    def test_other_person_residences_excluded(self):
        """Only the target person's residences produce markers."""
        person = _make_person()
        other = _make_person("p2")
        place = _make_place()
        facts = [
            ResidenceFact(
                id="r1", person_id="p1", place_id="pl1",
                start=Endpoint(earliest="1840", latest="1840"),
                end=Endpoint(earliest="1850", latest="1850"),
            ),
            ResidenceFact(
                id="r2", person_id="p2", place_id="pl1",
                start=Endpoint(earliest="1830", latest="1830"),
                end=Endpoint(earliest="1840", latest="1840"),
            ),
        ]
        data = ProjectData(
            persons=[person, other],
            places=[place],
            residences=facts,
        )
        markers = build_markers_for_person(data, "p1")
        assert len(markers) == 1
        # Only one residence event for p1
        residence_events = [ev for ev in markers[0].events if ev.event_type == "residence"]
        assert len(residence_events) == 1
        assert residence_events[0].event_id == "r1"

    def test_unknown_period_renders_correctly(self):
        """A residence with both endpoints unknown renders 'okänd period'."""
        person = _make_person()
        place = _make_place()
        fact = ResidenceFact(
            id="r1", person_id="p1", place_id="pl1",
            start=Endpoint(),
            end=Endpoint(),
        )
        data = ProjectData(
            persons=[person],
            places=[place],
            residences=[fact],
        )
        markers = build_markers_for_person(data, "p1")
        ev = markers[0].events[0]
        assert ev.date_display == "okänd period"
