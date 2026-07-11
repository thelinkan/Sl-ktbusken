"""Usage statistics calculation for sources."""

from __future__ import annotations

from dataclasses import dataclass

from slaktbusken.model.event import Event


@dataclass
class UsageStats:
    """Usage statistics for a single source."""

    event_count: int
    person_count: int


def compute_usage_stats(source_id: str, events: list[Event]) -> UsageStats:
    """Compute usage statistics for a source across all events.

    Args:
        source_id: The ID of the source to check.
        events: All events in the project.

    Returns:
        UsageStats with event_count (number of events referencing this source)
        and person_count (number of distinct person_ids from participants of
        those events).
    """
    event_count = 0
    person_ids: set[str] = set()

    for event in events:
        references_source = False

        if event.date is not None:
            for ref in event.date.source_refs:
                if ref.source_id == source_id:
                    references_source = True
                    break

        if not references_source and event.place is not None:
            for ref in event.place.source_refs:
                if ref.source_id == source_id:
                    references_source = True
                    break

        if references_source:
            event_count += 1
            for participant in event.participants:
                person_ids.add(participant.person_id)

    return UsageStats(event_count=event_count, person_count=len(person_ids))
