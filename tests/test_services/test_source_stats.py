"""Unit tests for source usage statistics calculation.

Feature: source-management

Validates: Requirements 6.1
"""

from __future__ import annotations

from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.services.source_stats import UsageStats, compute_usage_stats


class TestComputeUsageStats:
    """Unit tests for compute_usage_stats."""

    def test_no_events_returns_zero_counts(self) -> None:
        """No events means zero event and person counts."""
        result = compute_usage_stats("src-1", [])
        assert result == UsageStats(event_count=0, person_count=0)

    def test_source_referenced_in_date(self) -> None:
        """Source referenced in event.date.source_refs is counted."""
        event = Event(
            id="e1",
            type="birth",
            participants=[Participant(person_id="p1", role="child")],
            date=DateValue(
                value="1900-01-01",
                precision="exact",
                source_refs=[SourceRef(source_id="src-1", quality="high")],
            ),
        )
        result = compute_usage_stats("src-1", [event])
        assert result == UsageStats(event_count=1, person_count=1)

    def test_source_referenced_in_place(self) -> None:
        """Source referenced in event.place.source_refs is counted."""
        event = Event(
            id="e1",
            type="birth",
            participants=[Participant(person_id="p1", role="child")],
            place=PlaceRef(
                place_id="pl-1",
                source_refs=[SourceRef(source_id="src-1", quality="high")],
            ),
        )
        result = compute_usage_stats("src-1", [event])
        assert result == UsageStats(event_count=1, person_count=1)

    def test_source_referenced_in_both_date_and_place_counts_once(self) -> None:
        """Event referencing source in both date and place counts as 1 event."""
        event = Event(
            id="e1",
            type="birth",
            participants=[Participant(person_id="p1", role="child")],
            date=DateValue(
                value="1900-01-01",
                precision="exact",
                source_refs=[SourceRef(source_id="src-1", quality="high")],
            ),
            place=PlaceRef(
                place_id="pl-1",
                source_refs=[SourceRef(source_id="src-1", quality="high")],
            ),
        )
        result = compute_usage_stats("src-1", [event])
        assert result == UsageStats(event_count=1, person_count=1)

    def test_source_not_referenced_returns_zero(self) -> None:
        """Events not referencing this source produce zero counts."""
        event = Event(
            id="e1",
            type="birth",
            participants=[Participant(person_id="p1", role="child")],
            date=DateValue(
                value="1900-01-01",
                precision="exact",
                source_refs=[SourceRef(source_id="other-src", quality="high")],
            ),
        )
        result = compute_usage_stats("src-1", [event])
        assert result == UsageStats(event_count=0, person_count=0)

    def test_distinct_persons_across_events(self) -> None:
        """Person count is distinct person_ids across all matching events."""
        events = [
            Event(
                id="e1",
                type="birth",
                participants=[
                    Participant(person_id="p1", role="child"),
                    Participant(person_id="p2", role="mother"),
                ],
                date=DateValue(
                    value="1900-01-01",
                    precision="exact",
                    source_refs=[SourceRef(source_id="src-1", quality="high")],
                ),
            ),
            Event(
                id="e2",
                type="marriage",
                participants=[
                    Participant(person_id="p2", role="wife"),
                    Participant(person_id="p3", role="husband"),
                ],
                place=PlaceRef(
                    place_id="pl-1",
                    source_refs=[SourceRef(source_id="src-1", quality="high")],
                ),
            ),
        ]
        result = compute_usage_stats("src-1", events)
        assert result.event_count == 2
        # p1, p2, p3 are distinct
        assert result.person_count == 3

    def test_same_person_in_multiple_events_counted_once(self) -> None:
        """Same person_id in multiple events is counted only once."""
        events = [
            Event(
                id="e1",
                type="birth",
                participants=[Participant(person_id="p1", role="child")],
                date=DateValue(
                    value="1900-01-01",
                    precision="exact",
                    source_refs=[SourceRef(source_id="src-1", quality="high")],
                ),
            ),
            Event(
                id="e2",
                type="death",
                participants=[Participant(person_id="p1", role="deceased")],
                date=DateValue(
                    value="1950-06-15",
                    precision="exact",
                    source_refs=[SourceRef(source_id="src-1", quality="high")],
                ),
            ),
        ]
        result = compute_usage_stats("src-1", events)
        assert result.event_count == 2
        assert result.person_count == 1

    def test_event_with_no_date_and_no_place(self) -> None:
        """Event with neither date nor place cannot reference a source."""
        event = Event(
            id="e1",
            type="birth",
            participants=[Participant(person_id="p1", role="child")],
        )
        result = compute_usage_stats("src-1", [event])
        assert result == UsageStats(event_count=0, person_count=0)

    def test_event_with_empty_source_refs(self) -> None:
        """Event with date/place but empty source_refs lists."""
        event = Event(
            id="e1",
            type="birth",
            participants=[Participant(person_id="p1", role="child")],
            date=DateValue(value="1900-01-01", precision="exact", source_refs=[]),
            place=PlaceRef(place_id="pl-1", source_refs=[]),
        )
        result = compute_usage_stats("src-1", [event])
        assert result == UsageStats(event_count=0, person_count=0)
