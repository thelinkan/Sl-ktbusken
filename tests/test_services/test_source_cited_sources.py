"""Tests for the cited-sources helpers in services.source_stats."""

from __future__ import annotations

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.services.source_stats import (
    event_cited_sources,
    residence_cited_sources,
    residence_usage_text,
)

TITLES = {"s1": "Husförhörslängd", "s2": "Dödbok", "s3": ""}


def _event(date_refs=(), place_refs=()) -> Event:
    return Event(
        id="e1",
        type="birth",
        participants=[Participant(person_id="p1", role="child")],
        date=DateValue(
            value="1850", precision="year", source_refs=[SourceRef(source_id=s, quality="high") for s in date_refs]
        ),
        place=PlaceRef(place_id="pl1", source_refs=[SourceRef(source_id=s, quality="high") for s in place_refs]),
    )


def test_event_with_date_source():
    assert event_cited_sources(_event(["s1"]), TITLES) == [("s1", "Husförhörslängd")]


def test_event_with_place_source():
    assert event_cited_sources(_event(place_refs=["s2"]), TITLES) == [("s2", "Dödbok")]


def test_event_with_both_distinct_in_order():
    result = event_cited_sources(_event(["s2", "s1"], ["s1"]), TITLES)
    assert result == [("s2", "Dödbok"), ("s1", "Husförhörslängd")]


def test_event_without_sources_is_empty():
    assert event_cited_sources(_event(), TITLES) == []


def test_empty_title_falls_back_to_id():
    assert event_cited_sources(_event(["s3", "unknown"]), TITLES) == [
        ("s3", "s3"),
        ("unknown", "unknown"),
    ]


def test_residence_distinct_sources():
    fact = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        observations=[
            Observation(source_ref=SourceRef(source_id="s1", quality="high")),
            Observation(source_ref=SourceRef(source_id="s2", quality="high")),
            Observation(source_ref=SourceRef(source_id="s1", quality="high")),
        ],
    )
    assert residence_cited_sources(fact, TITLES) == [("s1", "Husförhörslängd"), ("s2", "Dödbok")]


def test_residence_without_observations_is_empty():
    assert residence_cited_sources(ResidenceFact(id="r", person_id="p", place_id="x")) == []


def test_residence_usage_text():
    fact = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest="1880"),
        end=Endpoint(earliest="1890"),
    )
    assert residence_usage_text(fact, {"pl1": "Ljusdal"}) == "Boende: Ljusdal (från 1880 till 1890)"
    bare = ResidenceFact(id="r2", person_id="p1", place_id="pl9")
    assert residence_usage_text(bare, {}) == "Boende: pl9"
