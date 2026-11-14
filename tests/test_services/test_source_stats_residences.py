"""Usage statistics for a source including residence observations."""

from __future__ import annotations

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.residence import Observation, ResidenceFact
from slaktbusken.services.source_stats import compute_usage_stats


def _event(event_id: str, person_id: str, *, date_src: str = "", place_src: str = "") -> Event:
    return Event(
        id=event_id,
        type="birth",
        participants=[Participant(person_id=person_id, role="child")],
        date=DateValue(
            value="1850", precision="year",
            source_refs=[SourceRef(source_id=date_src, quality="high")] if date_src else [],
        ),
        place=PlaceRef(
            place_id="pl", source_refs=[SourceRef(source_id=place_src, quality="high")] if place_src else []
        ),
    )


def _residence(fact_id: str, person_id: str, *source_ids: str) -> ResidenceFact:
    return ResidenceFact(
        id=fact_id,
        person_id=person_id,
        place_id="pl",
        observations=[Observation(source_ref=SourceRef(source_id=s, quality="high")) for s in source_ids],
    )


def test_person_from_event_date_source() -> None:
    stats = compute_usage_stats("s", [_event("e", "p1", date_src="s")], [])
    assert (stats.event_count, stats.residence_count, stats.person_ids) == (1, 0, ["p1"])


def test_person_from_event_place_source() -> None:
    stats = compute_usage_stats("s", [_event("e", "p1", place_src="s")], [])
    assert stats.person_ids == ["p1"] and stats.person_count == 1


def test_person_from_residence_observation_only() -> None:
    stats = compute_usage_stats("s", [], [_residence("r", "p2", "s")])
    assert (stats.event_count, stats.residence_count, stats.person_count) == (0, 1, 1)
    assert stats.person_ids == ["p2"]


def test_mixed_and_deduplicated_sorted() -> None:
    events = [_event("e1", "p3", date_src="s"), _event("e2", "p1", place_src="s")]
    residences = [_residence("r1", "p3", "s"), _residence("r2", "p2", "s")]
    stats = compute_usage_stats("s", events, residences)
    assert stats.person_ids == ["p1", "p2", "p3"]
    assert stats.person_count == 3
    assert stats.event_count == 2
    assert stats.residence_count == 2


def test_residence_count_counts_facts_not_observations() -> None:
    stats = compute_usage_stats("s", [], [_residence("r", "p1", "s", "s", "other")])
    assert stats.residence_count == 1


def test_other_source_and_empty_give_zero() -> None:
    stats = compute_usage_stats("s", [_event("e", "p1", date_src="x")], [_residence("r", "p2", "x")])
    assert (stats.event_count, stats.residence_count, stats.person_count, stats.person_ids) == (0, 0, 0, [])
    assert compute_usage_stats("s", []).person_count == 0
