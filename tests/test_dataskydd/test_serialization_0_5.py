"""Serialization of the 0.5 fields: event citations, origins, date fields.

**Validates: Requirements 12.1, 12.2, 14.1, 14.7, 16.5, 19.1, 22.1**
"""

from __future__ import annotations

import json

import pytest
from hypothesis import given, settings

from slaktbusken.model.date_semantics import validate_date_value
from slaktbusken.model.event import DateValue, Event, Participant, SourceRef
from slaktbusken.model.project import ProjectData
from slaktbusken.model.record_origin import RecordOrigin
from slaktbusken.model.residence import ResidenceFact
from slaktbusken.persistence.serialization import deserialize, serialize
from tests.test_dataskydd.strategies import (
    events,
    record_origins,
    residence_origins,
    residences,
    valid_date_values,
)

pytestmark = pytest.mark.mandatory_integrity

_HASH = "a" * 64


def _round_trip(**collections) -> tuple[ProjectData, dict]:
    data = ProjectData(**collections)
    text = serialize(data)
    return deserialize(text), json.loads(text)


def _event(**kwargs) -> Event:
    return Event("event_1", "birth", [Participant("person_1", "self")], **kwargs)


def _origin(**kwargs) -> RecordOrigin:
    values = dict(
        owner_kind="INDI", owner_id="person_1", owner_xref="@I1@",
        tag_key="BIRT", index=0, record_hash=_HASH,
    )
    values.update(kwargs)
    return RecordOrigin(**values)


def _residence(**kwargs) -> ResidenceFact:
    return ResidenceFact("residence_1", "person_1", "place_1", **kwargs)


# Feature: data-integrity-0-3-0, Property 12: Date, event and residence
# serialization round-trips and omits defaults
@settings(settings.get_profile("sbk"))
@given(evs=events(), res=residences())
def test_dp_property_12_round_trip_and_omitted_defaults(evs, res) -> None:
    """**Validates: Requirements 12.1, 12.2, 14.1, 14.7, 19.1, 22.1**"""
    loaded, raw = _round_trip(events=[evs], residences=[res])
    assert loaded.events == [evs]
    assert loaded.residences == [res]

    raw_event = raw["events"][0]
    assert ("source_refs" in raw_event) == bool(evs.source_refs)
    assert ("origin" in raw_event) == (evs.origin is not None)
    assert ("origins" in raw["residences"][0]) == bool(res.origins)

    if evs.date is not None:
        raw_date = raw_event["date"]
        assert ("qualifier" in raw_date) == (evs.date.qualifier != "exact")
        assert ("value_to" in raw_date) == (evs.date.value_to is not None)
        assert ("calendar" in raw_date) == (evs.date.calendar != "gregorian")
        assert ("original_text" in raw_date) == (evs.date.original_text is not None)


@settings(settings.get_profile("sbk"))
@given(valid_date_values())
def test_dp_property_12_valid_dates_validate_and_round_trip(date) -> None:
    """**Validates: Requirements 14.1, 14.7, 16.5**"""
    assert validate_date_value(date) == []
    loaded, _ = _round_trip(events=[_event(date=date)])
    assert loaded.events[0].date == date


def test_event_source_refs_serialize_only_when_non_empty() -> None:
    _, raw = _round_trip(events=[_event()])
    assert "source_refs" not in raw["events"][0]
    _, raw = _round_trip(events=[_event(source_refs=[SourceRef("source_1", "primary")])])
    assert raw["events"][0]["source_refs"][0]["source_id"] == "source_1"


def test_event_source_refs_round_trip() -> None:
    refs = [
        SourceRef("source_1", "primary", "s. 3", ["datum"]),
        SourceRef("source_2", "secondary"),
    ]
    date = DateValue("1850", "year", [SourceRef("source_3", "primary")])
    loaded, _ = _round_trip(events=[_event(source_refs=refs, date=date)])
    assert loaded.events[0].source_refs == refs
    assert loaded.events[0].date.source_refs == date.source_refs


def test_origin_serialization_round_trip() -> None:
    event = _event(origin=_origin(uid="UID-1", index=2))
    loaded, raw = _round_trip(events=[event])
    assert loaded.events[0].origin == event.origin
    assert "origin" not in json.loads(serialize(ProjectData(events=[_event()])))["events"][0]
    assert raw["events"][0]["origin"]["uid"] == "UID-1"
    # An absent uid is not written.
    _, raw = _round_trip(events=[_event(origin=_origin())])
    assert "uid" not in raw["events"][0]["origin"]


@settings(settings.get_profile("sbk"))
@given(record_origins)
def test_dp_property_12_origin_round_trip(origin) -> None:
    """**Validates: Requirements 19.1**"""
    loaded, _ = _round_trip(events=[_event(origin=origin)])
    assert loaded.events[0].origin == origin


def test_origin_instance_round_trip() -> None:
    event = _event(origin=_origin(instance=3))
    loaded, _ = _round_trip(events=[event])
    assert loaded.events[0].origin.instance == 3

    # A missing instance key is read as 0.
    text = serialize(ProjectData(events=[_event(origin=_origin(instance=3))]))
    raw = json.loads(text)
    del raw["events"][0]["origin"]["instance"]
    assert deserialize(json.dumps(raw)).events[0].origin.instance == 0

    # Equal origins on two residences are kept as two residences.
    origin = residence_origin = _origin(tag_key="RESI", instance=1)
    first = _residence(origins=[origin])
    second = ResidenceFact("residence_2", "person_1", "place_1", origins=[residence_origin])
    loaded, _ = _round_trip(residences=[first, second])
    assert [r.origins for r in loaded.residences] == [[origin], [origin]]
    assert loaded.residences[0].origins[0] == loaded.residences[1].origins[0]


def test_residence_origins_serialize_only_when_non_empty() -> None:
    _, raw = _round_trip(residences=[_residence()])
    assert "origins" not in raw["residences"][0]
    _, raw = _round_trip(residences=[_residence(origins=[_origin(tag_key="RESI")])])
    assert len(raw["residences"][0]["origins"]) == 1


def test_residence_origins_round_trip() -> None:
    origins = [_origin(tag_key="RESI", index=0), _origin(tag_key="RESI", index=1, uid="U")]
    loaded, _ = _round_trip(residences=[_residence(origins=origins)])
    assert loaded.residences[0].origins == origins


@settings(settings.get_profile("sbk"))
@given(residence_origins)
def test_dp_property_12_residence_origin_round_trip(origin) -> None:
    """**Validates: Requirements 22.1**"""
    loaded, _ = _round_trip(residences=[_residence(origins=[origin, origin])])
    assert loaded.residences[0].origins == [origin, origin]


def test_date_value_defaults_and_validation() -> None:
    date = DateValue("1850", "year")
    assert (date.qualifier, date.value_to, date.calendar, date.original_text) == (
        "exact", None, "gregorian", None,
    )
    assert validate_date_value(date) == []
    assert validate_date_value(DateValue("1850", "year", qualifier="bogus"))
    assert validate_date_value(DateValue("1850", "year", calendar="hebrew"))
    # Qualified dates need the approximate precision.
    assert validate_date_value(DateValue("1850", "year", qualifier="about"))
    assert validate_date_value(DateValue("1850", "approximate", qualifier="about")) == []
    # Ranges need an end that is not earlier than the start.
    assert validate_date_value(DateValue("1850", "approximate", qualifier="between"))
    assert validate_date_value(
        DateValue("1850-05", "approximate", qualifier="between", value_to="1850-04")
    )
    assert validate_date_value(
        DateValue("1850-05", "approximate", qualifier="between", value_to="1851")
    ) == []
    # A leap day exists in the Julian calendar of 1900 but not the Gregorian.
    assert validate_date_value(DateValue("1900-02-29", "day"))
    assert validate_date_value(DateValue("1900-02-29", "day", calendar="julian")) == []
    # An exact date has no range end.
    assert validate_date_value(DateValue("1850", "year", value_to="1851"))


def test_date_value_serialization_omits_defaults() -> None:
    _, raw = _round_trip(events=[_event(date=DateValue("1850", "year"))])
    assert set(raw["events"][0]["date"]) == {"value", "precision"}
    full = DateValue(
        "1850", "approximate", [], "between", "1852", "julian", "mellan 1850 och 1852"
    )
    _, raw = _round_trip(events=[_event(date=full)])
    assert raw["events"][0]["date"] == {
        "value": "1850", "precision": "approximate", "qualifier": "between",
        "value_to": "1852", "calendar": "julian", "original_text": "mellan 1850 och 1852",
    }


def test_unparsed_validation() -> None:
    assert validate_date_value(DateValue("", "year", qualifier="unparsed", original_text="i våras")) == []
    # Original text is required.
    assert validate_date_value(DateValue("", "year", qualifier="unparsed"))
    assert validate_date_value(DateValue("", "year", qualifier="unparsed", original_text="  "))
    # No value and no range end may be present.
    assert validate_date_value(
        DateValue("1850", "year", qualifier="unparsed", original_text="x")
    )
    assert validate_date_value(
        DateValue("", "year", qualifier="unparsed", value_to="1851", original_text="x")
    )
    loaded, _ = _round_trip(
        events=[_event(date=DateValue("", "year", qualifier="unparsed", original_text="i våras"))]
    )
    assert loaded.events[0].date.qualifier == "unparsed"
    assert loaded.events[0].date.original_text == "i våras"
