"""Property-based tests for usage statistics calculation.

Feature: source-management, Property 8: Usage statistics calculation

Validates: Requirements 6.1
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.services.source_stats import UsageStats, compute_usage_stats


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_QUALITY_VALUES = ["primary", "secondary", "questionable"]

source_id_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
    min_size=1,
    max_size=20,
)

source_ref_strategy = st.builds(
    SourceRef,
    source_id=source_id_strategy,
    quality=st.sampled_from(_QUALITY_VALUES),
    note=st.text(min_size=0, max_size=30),
    aspects=st.lists(st.text(min_size=1, max_size=10), max_size=3),
)


def source_ref_for(sid: str) -> st.SearchStrategy[SourceRef]:
    """Generate a SourceRef that references the given source_id."""
    return st.builds(
        SourceRef,
        source_id=st.just(sid),
        quality=st.sampled_from(_QUALITY_VALUES),
        note=st.text(min_size=0, max_size=30),
        aspects=st.lists(st.text(min_size=1, max_size=10), max_size=3),
    )


participant_strategy = st.builds(
    Participant,
    person_id=source_id_strategy,
    role=st.sampled_from(["principal", "witness", "parent", "spouse"]),
)

date_value_strategy = st.builds(
    DateValue,
    value=st.text(min_size=1, max_size=10),
    precision=st.sampled_from(["exact", "about", "before", "after"]),
    source_refs=st.lists(source_ref_strategy, max_size=3),
)

place_ref_strategy = st.builds(
    PlaceRef,
    place_id=source_id_strategy,
    source_refs=st.lists(source_ref_strategy, max_size=3),
)

event_strategy = st.builds(
    Event,
    id=source_id_strategy,
    type=st.sampled_from(["birth", "death", "marriage", "immigration", "census"]),
    participants=st.lists(participant_strategy, min_size=0, max_size=4),
    date=st.one_of(st.none(), date_value_strategy),
    place=st.one_of(st.none(), place_ref_strategy),
    media_ids=st.just([]),
    custom_type_name=st.none(),
    cause_of_death=st.none(),
)


# ---------------------------------------------------------------------------
# Property 8: Usage statistics calculation
# ---------------------------------------------------------------------------


class TestUsageStatsProperty:
    """Feature: source-management, Property 8: Usage statistics calculation

    For any project data with events containing source_refs (in date and/or
    place), the usage count function for a given source SHALL return an event
    count equal to the number of events referencing that source, and a person
    count equal to the number of distinct participant person_ids across those
    events.

    **Validates: Requirements 6.1**
    """

    @given(
        target_source_id=source_id_strategy,
        events=st.lists(event_strategy, min_size=0, max_size=10),
    )
    @settings(max_examples=100, deadline=None)
    def test_event_count_equals_referencing_events(
        self, target_source_id: str, events: list[Event]
    ) -> None:
        """event_count equals the number of events that reference the target
        source_id (in either date.source_refs or place.source_refs).

        Feature: source-management, Property 8: Usage statistics calculation
        **Validates: Requirements 6.1**
        """
        result = compute_usage_stats(target_source_id, events)

        # Independently compute expected event count
        expected_event_count = 0
        for event in events:
            refs_in_date = (
                any(r.source_id == target_source_id for r in event.date.source_refs)
                if event.date is not None
                else False
            )
            refs_in_place = (
                any(r.source_id == target_source_id for r in event.place.source_refs)
                if event.place is not None
                else False
            )
            if refs_in_date or refs_in_place:
                expected_event_count += 1

        assert result.event_count == expected_event_count

    @given(
        target_source_id=source_id_strategy,
        events=st.lists(event_strategy, min_size=0, max_size=10),
    )
    @settings(max_examples=100, deadline=None)
    def test_person_count_equals_distinct_participants(
        self, target_source_id: str, events: list[Event]
    ) -> None:
        """person_count equals the number of distinct participant person_ids
        across referencing events.

        Feature: source-management, Property 8: Usage statistics calculation
        **Validates: Requirements 6.1**
        """
        result = compute_usage_stats(target_source_id, events)

        # Independently compute expected person count
        expected_person_ids: set[str] = set()
        for event in events:
            refs_in_date = (
                any(r.source_id == target_source_id for r in event.date.source_refs)
                if event.date is not None
                else False
            )
            refs_in_place = (
                any(r.source_id == target_source_id for r in event.place.source_refs)
                if event.place is not None
                else False
            )
            if refs_in_date or refs_in_place:
                for p in event.participants:
                    expected_person_ids.add(p.person_id)

        assert result.person_count == len(expected_person_ids)

    @given(
        target_source_id=source_id_strategy,
        data=st.data(),
    )
    @settings(max_examples=100, deadline=None)
    def test_event_referenced_only_in_date_still_counts(
        self, target_source_id: str, data: st.DataObject
    ) -> None:
        """An event referenced only in date.source_refs still counts.

        Feature: source-management, Property 8: Usage statistics calculation
        **Validates: Requirements 6.1**
        """
        # Build an event with target ref only in date, not in place
        target_ref = data.draw(source_ref_for(target_source_id))
        other_refs = data.draw(st.lists(source_ref_strategy, max_size=2))
        date = DateValue(
            value="2020-01-01",
            precision="exact",
            source_refs=[target_ref] + other_refs,
        )
        # Place without target source
        place_refs = [
            r for r in data.draw(st.lists(source_ref_strategy, max_size=2))
            if r.source_id != target_source_id
        ]
        place = PlaceRef(place_id="p1", source_refs=place_refs)
        participants = data.draw(st.lists(participant_strategy, min_size=1, max_size=3))
        event = Event(
            id="evt1", type="birth", participants=participants, date=date, place=place
        )

        result = compute_usage_stats(target_source_id, [event])
        assert result.event_count == 1

    @given(
        target_source_id=source_id_strategy,
        data=st.data(),
    )
    @settings(max_examples=100, deadline=None)
    def test_event_referenced_only_in_place_still_counts(
        self, target_source_id: str, data: st.DataObject
    ) -> None:
        """An event referenced only in place.source_refs still counts.

        Feature: source-management, Property 8: Usage statistics calculation
        **Validates: Requirements 6.1**
        """
        # Build an event with target ref only in place, not in date
        target_ref = data.draw(source_ref_for(target_source_id))
        # Date without target source
        date_refs = [
            r for r in data.draw(st.lists(source_ref_strategy, max_size=2))
            if r.source_id != target_source_id
        ]
        date = DateValue(value="2020-01-01", precision="exact", source_refs=date_refs)
        other_refs = data.draw(st.lists(source_ref_strategy, max_size=2))
        place = PlaceRef(
            place_id="p1", source_refs=[target_ref] + other_refs
        )
        participants = data.draw(st.lists(participant_strategy, min_size=1, max_size=3))
        event = Event(
            id="evt1", type="birth", participants=participants, date=date, place=place
        )

        result = compute_usage_stats(target_source_id, [event])
        assert result.event_count == 1

    @given(
        target_source_id=source_id_strategy,
        data=st.data(),
    )
    @settings(max_examples=100, deadline=None)
    def test_event_referenced_in_both_counts_once(
        self, target_source_id: str, data: st.DataObject
    ) -> None:
        """An event referenced in both date and place only counts once
        (event_count).

        Feature: source-management, Property 8: Usage statistics calculation
        **Validates: Requirements 6.1**
        """
        target_ref_date = data.draw(source_ref_for(target_source_id))
        target_ref_place = data.draw(source_ref_for(target_source_id))
        date = DateValue(
            value="2020-01-01", precision="exact", source_refs=[target_ref_date]
        )
        place = PlaceRef(place_id="p1", source_refs=[target_ref_place])
        participants = data.draw(st.lists(participant_strategy, min_size=1, max_size=3))
        event = Event(
            id="evt1", type="birth", participants=participants, date=date, place=place
        )

        result = compute_usage_stats(target_source_id, [event])
        assert result.event_count == 1

    @given(
        target_source_id=source_id_strategy,
        events=st.lists(event_strategy, min_size=1, max_size=10),
    )
    @settings(max_examples=100, deadline=None)
    def test_non_referencing_events_contribute_nothing(
        self, target_source_id: str, events: list[Event]
    ) -> None:
        """Non-referencing events contribute nothing to counts.

        Feature: source-management, Property 8: Usage statistics calculation
        **Validates: Requirements 6.1**
        """
        # Remove target source from all events
        cleaned_events: list[Event] = []
        for event in events:
            new_date = None
            if event.date is not None:
                new_date = DateValue(
                    value=event.date.value,
                    precision=event.date.precision,
                    source_refs=[
                        r
                        for r in event.date.source_refs
                        if r.source_id != target_source_id
                    ],
                )
            new_place = None
            if event.place is not None:
                new_place = PlaceRef(
                    place_id=event.place.place_id,
                    source_refs=[
                        r
                        for r in event.place.source_refs
                        if r.source_id != target_source_id
                    ],
                )
            cleaned_events.append(
                Event(
                    id=event.id,
                    type=event.type,
                    participants=event.participants,
                    date=new_date,
                    place=new_place,
                    media_ids=event.media_ids,
                )
            )

        result = compute_usage_stats(target_source_id, cleaned_events)
        assert result.event_count == 0
        assert result.person_count == 0

    @given(target_source_id=source_id_strategy)
    @settings(max_examples=100, deadline=None)
    def test_empty_events_list_returns_zero_stats(
        self, target_source_id: str
    ) -> None:
        """Empty events list returns UsageStats(0, 0).

        Feature: source-management, Property 8: Usage statistics calculation
        **Validates: Requirements 6.1**
        """
        result = compute_usage_stats(target_source_id, [])
        assert result == UsageStats(event_count=0, person_count=0)
