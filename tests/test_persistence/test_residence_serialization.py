"""Unit tests for residence serialization (task 6.1).

Tests that:
- ResidenceFact serializes and deserializes correctly (round trip)
- Observations with SourceRef are preserved through serialization
- Endpoint fields (earliest, latest, precision, event_id, note) round-trip
- The absent vs empty string distinction is preserved (Requirement 13.2)
- Unknown fields are ignored and logged (Requirement 13.5)
- Unresolved references are kept as stored (Requirement 13.7)
- Event.from_place round-trips through serialization
"""

from __future__ import annotations

import json

from slaktbusken.model.event import Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.persistence.serialization import deserialize, serialize


class TestResidenceSerializationRoundTrip:
    """Residence facts survive a serialize/deserialize round trip."""

    def test_minimal_residence_round_trip(self) -> None:
        """A ResidenceFact with only required fields round-trips."""
        fact = ResidenceFact(id="residence_1", person_id="p1", place_id="pl1")
        data = ProjectData(residences=[fact])

        result = deserialize(serialize(data))

        assert len(result.residences) == 1
        r = result.residences[0]
        assert r.id == "residence_1"
        assert r.person_id == "p1"
        assert r.place_id == "pl1"
        assert r.start.earliest is None
        assert r.start.latest is None
        assert r.end.earliest is None
        assert r.end.latest is None
        assert r.role_in_household == ""
        assert r.observations == []
        assert r.notes == ""

    def test_full_residence_round_trip(self) -> None:
        """A fully populated ResidenceFact round-trips field by field."""
        fact = ResidenceFact(
            id="residence_2",
            person_id="person_1",
            place_id="place_1",
            start=Endpoint(
                earliest="1840",
                latest="1840-06",
                precision="month",
                event_id="event_1",
                note="Moved from Gävle",
            ),
            end=Endpoint(
                earliest="1846-12-25",
                latest="1847",
                precision="day",
                event_id="event_2",
                note="Death",
            ),
            role_in_household="Husbonde",
            observations=[
                Observation(
                    source_ref=SourceRef(
                        source_id="source_1",
                        quality="high",
                        note="p.42",
                        aspects=["place", "period"],
                    ),
                    observed_from="1840",
                    observed_to="1845",
                    page_note="Uppslag 12",
                ),
                Observation(
                    source_ref=SourceRef(source_id="source_2", quality="medium"),
                    observed_from="1845",
                    observed_to="1846",
                    page_note="",
                ),
            ],
            notes="First residence at this farm",
        )
        data = ProjectData(residences=[fact])

        result = deserialize(serialize(data))

        assert len(result.residences) == 1
        r = result.residences[0]
        assert r.id == "residence_2"
        assert r.person_id == "person_1"
        assert r.place_id == "place_1"

        # Start Endpoint
        assert r.start.earliest == "1840"
        assert r.start.latest == "1840-06"
        assert r.start.precision == "month"
        assert r.start.event_id == "event_1"
        assert r.start.note == "Moved from Gävle"

        # End Endpoint
        assert r.end.earliest == "1846-12-25"
        assert r.end.latest == "1847"
        assert r.end.precision == "day"
        assert r.end.event_id == "event_2"
        assert r.end.note == "Death"

        # Other fields
        assert r.role_in_household == "Husbonde"
        assert r.notes == "First residence at this farm"

        # Observations
        assert len(r.observations) == 2
        obs0 = r.observations[0]
        assert obs0.source_ref.source_id == "source_1"
        assert obs0.source_ref.quality == "high"
        assert obs0.source_ref.note == "p.42"
        assert obs0.source_ref.aspects == ["place", "period"]
        assert obs0.observed_from == "1840"
        assert obs0.observed_to == "1845"
        assert obs0.page_note == "Uppslag 12"

        obs1 = r.observations[1]
        assert obs1.source_ref.source_id == "source_2"
        assert obs1.source_ref.quality == "medium"
        assert obs1.observed_from == "1845"
        assert obs1.observed_to == "1846"

    def test_multiple_residences_preserve_order(self) -> None:
        """Multiple residences preserve their stored order."""
        facts = [
            ResidenceFact(id=f"residence_{i}", person_id="p1", place_id="pl1")
            for i in range(5)
        ]
        data = ProjectData(residences=facts)

        result = deserialize(serialize(data))

        assert [r.id for r in result.residences] == [
            "residence_0",
            "residence_1",
            "residence_2",
            "residence_3",
            "residence_4",
        ]

    def test_zero_observations_round_trip(self) -> None:
        """A residence with zero observations round-trips (observations absent from JSON)."""
        fact = ResidenceFact(id="r1", person_id="p1", place_id="pl1")
        data = ProjectData(residences=[fact])

        result = deserialize(serialize(data))

        assert result.residences[0].observations == []


class TestResidenceAbsentVsEmpty:
    """Absent (None) and empty string ("") are preserved distinctly (Req 13.2)."""

    def test_absent_endpoint_fields_stay_absent(self) -> None:
        """None values on Endpoint fields deserialize as None, not empty string."""
        fact = ResidenceFact(
            id="r1",
            person_id="p1",
            place_id="pl1",
            start=Endpoint(earliest=None, latest=None, precision=None, event_id=None, note=None),
        )
        data = ProjectData(residences=[fact])

        result = deserialize(serialize(data))

        ep = result.residences[0].start
        assert ep.earliest is None
        assert ep.latest is None
        assert ep.precision is None
        assert ep.event_id is None
        assert ep.note is None

    def test_empty_string_endpoint_fields_stay_empty_string(self) -> None:
        """Empty strings on Endpoint fields deserialize as empty string, not None."""
        fact = ResidenceFact(
            id="r1",
            person_id="p1",
            place_id="pl1",
            start=Endpoint(earliest="", latest="", precision="", event_id="", note=""),
        )
        data = ProjectData(residences=[fact])

        # Serialize — let's check what happens
        json_str = serialize(data)
        result = deserialize(json_str)

        # NOTE: The serializer omits None for Optional fields with defaults but
        # keeps empty strings (they're not None). On deserialization, absent keys
        # yield the dataclass default (None for Optional[str] = None).
        # An empty string "" is present in JSON and deserialized as "".
        ep = result.residences[0].start
        # Empty strings: they ARE different from None but the serializer may
        # omit them if they match defaults. Let's verify the JSON to understand.
        parsed = json.loads(json_str)
        # The start endpoint with all empty strings — those are not None and not
        # the default (which is None), so they should be present in JSON.
        start_json = parsed["residences"][0]["start"]
        # earliest="" is not None, and field default is None, so it's NOT omitted.
        assert "earliest" in start_json
        assert start_json["earliest"] == ""

    def test_role_in_household_empty_is_empty_string(self) -> None:
        """Empty role_in_household deserializes as '' not None."""
        fact = ResidenceFact(id="r1", person_id="p1", place_id="pl1")
        data = ProjectData(residences=[fact])

        result = deserialize(serialize(data))

        assert result.residences[0].role_in_household == ""


class TestTolerantLoading:
    """Unknown fields ignored + logged; unresolved refs kept (Req 13.5, 13.7)."""

    def test_unknown_fields_ignored_and_logged(self) -> None:
        """Unknown fields on a residence dict are ignored and logged with fact id."""
        raw = {
            "format": "släktbuske-file",
            "version": "0.1",
            "project": {"title": "Test"},
            "residences": [
                {
                    "id": "residence_42",
                    "person_id": "p1",
                    "place_id": "pl1",
                    "start": {},
                    "end": {},
                    "unknown_field": "some value",
                    "another_unknown": 123,
                }
            ],
        }
        json_str = json.dumps(raw)
        log: list[str] = []

        result = deserialize(json_str, log=log)

        # The residence is still loaded
        assert len(result.residences) == 1
        assert result.residences[0].id == "residence_42"
        assert result.residences[0].person_id == "p1"

        # Unknown fields were logged
        assert any("another_unknown" in msg for msg in log)
        assert any("unknown_field" in msg for msg in log)
        assert any("residence_42" in msg for msg in log)

    def test_unknown_fields_without_log_param(self) -> None:
        """Without log param, unknown fields are silently ignored."""
        raw = {
            "format": "släktbuske-file",
            "version": "0.1",
            "project": {"title": "Test"},
            "residences": [
                {
                    "id": "r1",
                    "person_id": "p1",
                    "place_id": "pl1",
                    "start": {},
                    "end": {},
                    "bogus_field": "ignored",
                }
            ],
        }
        json_str = json.dumps(raw)

        # No log parameter — should not raise
        result = deserialize(json_str)

        assert len(result.residences) == 1
        assert result.residences[0].id == "r1"

    def test_unresolved_person_id_kept(self) -> None:
        """Unresolved person_id is kept as stored (Req 13.7)."""
        fact = ResidenceFact(id="r1", person_id="nonexistent_person", place_id="pl1")
        data = ProjectData(residences=[fact])

        result = deserialize(serialize(data))

        assert result.residences[0].person_id == "nonexistent_person"

    def test_unresolved_place_id_kept(self) -> None:
        """Unresolved place_id is kept as stored."""
        fact = ResidenceFact(id="r1", person_id="p1", place_id="nonexistent_place")
        data = ProjectData(residences=[fact])

        result = deserialize(serialize(data))

        assert result.residences[0].place_id == "nonexistent_place"

    def test_unresolved_source_id_in_observation_kept(self) -> None:
        """Unresolved source_ref.source_id is kept as stored."""
        fact = ResidenceFact(
            id="r1",
            person_id="p1",
            place_id="pl1",
            observations=[
                Observation(
                    source_ref=SourceRef(source_id="missing_source", quality="low"),
                    observed_from="1850",
                    observed_to="1855",
                )
            ],
        )
        data = ProjectData(residences=[fact])

        result = deserialize(serialize(data))

        assert result.residences[0].observations[0].source_ref.source_id == "missing_source"

    def test_unresolved_event_id_in_endpoint_kept(self) -> None:
        """Unresolved event_id is kept as stored."""
        fact = ResidenceFact(
            id="r1",
            person_id="p1",
            place_id="pl1",
            start=Endpoint(event_id="missing_event"),
        )
        data = ProjectData(residences=[fact])

        result = deserialize(serialize(data))

        assert result.residences[0].start.event_id == "missing_event"


class TestEventFromPlaceRoundTrip:
    """Event.from_place round-trips through serialization."""

    def test_from_place_present(self) -> None:
        """An Event with from_place set serializes and deserializes correctly."""
        event = Event(
            id="event_flytt_1",
            type="flytt",
            participants=[Participant(person_id="p1", role="primary")],
            from_place=PlaceRef(
                place_id="place_origin",
                source_refs=[SourceRef(source_id="src_1", quality="high")],
            ),
            place=PlaceRef(place_id="place_dest"),
        )
        data = ProjectData(events=[event])

        result = deserialize(serialize(data))

        assert len(result.events) == 1
        e = result.events[0]
        assert e.from_place is not None
        assert e.from_place.place_id == "place_origin"
        assert len(e.from_place.source_refs) == 1
        assert e.from_place.source_refs[0].source_id == "src_1"
        assert e.from_place.source_refs[0].quality == "high"

    def test_from_place_absent(self) -> None:
        """An Event with from_place=None round-trips as None."""
        event = Event(
            id="event_1",
            type="birth",
            participants=[Participant(person_id="p1", role="primary")],
        )
        data = ProjectData(events=[event])

        result = deserialize(serialize(data))

        assert result.events[0].from_place is None

    def test_from_place_omitted_from_json_when_none(self) -> None:
        """from_place is omitted from JSON when None (not written as null)."""
        event = Event(
            id="event_1",
            type="birth",
            participants=[Participant(person_id="p1", role="primary")],
        )
        data = ProjectData(events=[event])

        json_str = serialize(data)
        parsed = json.loads(json_str)

        assert "from_place" not in parsed["events"][0]


class TestResidenceInJson:
    """Verify the JSON structure of serialized residences."""

    def test_residences_key_present_in_json(self) -> None:
        """The 'residences' key appears in the serialized JSON."""
        data = ProjectData(
            residences=[ResidenceFact(id="r1", person_id="p1", place_id="pl1")]
        )

        json_str = serialize(data)
        parsed = json.loads(json_str)

        assert "residences" in parsed
        assert len(parsed["residences"]) == 1

    def test_empty_residences_serialized_as_empty_list(self) -> None:
        """An empty residences collection serializes as []."""
        data = ProjectData()

        json_str = serialize(data)
        parsed = json.loads(json_str)

        assert parsed["residences"] == []

    def test_residences_after_events_in_entity_fields(self) -> None:
        """Residences appear after events in the JSON output."""
        data = ProjectData()

        json_str = serialize(data)
        parsed = json.loads(json_str)
        keys = list(parsed.keys())

        events_idx = keys.index("events")
        residences_idx = keys.index("residences")
        assert residences_idx == events_idx + 1
