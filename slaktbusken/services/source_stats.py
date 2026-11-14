"""Usage statistics calculation for sources."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from slaktbusken.model.event import Event
from slaktbusken.model.residence import ResidenceFact


def _cited_ids_event(event: Event) -> list[str]:
    ids: list[str] = []
    if event.date is not None:
        ids.extend(ref.source_id for ref in event.date.source_refs)
    if event.place is not None:
        ids.extend(ref.source_id for ref in event.place.source_refs)
    return ids


def _distinct_sources(
    ids: Iterable[str], titles: Mapping[str, str] | None
) -> list[tuple[str, str]]:
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for source_id in ids:
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        title = ((titles or {}).get(source_id) or "").strip()
        result.append((source_id, title or source_id))
    return result


def event_cited_sources(
    event: Event, titles: Mapping[str, str] | None = None
) -> list[tuple[str, str]]:
    """Distinct ``(source_id, title)`` cited by an event's date or place refs.

    Date refs come first, then place refs, in order of first appearance. The
    title falls back to the id when unknown or empty.
    """
    return _distinct_sources(_cited_ids_event(event), titles)


def residence_cited_sources(
    fact: ResidenceFact, titles: Mapping[str, str] | None = None
) -> list[tuple[str, str]]:
    """Distinct ``(source_id, title)`` cited by a residence fact's observations."""
    return _distinct_sources(
        (obs.source_ref.source_id for obs in fact.observations), titles
    )


def residence_usage_text(fact: ResidenceFact, place_names: Mapping[str, str]) -> str:
    """Plain Swedish text for a residence, e.g. ``Boende: Ljusdal (från 1880 till 1890)``."""

    def span(endpoint) -> str:
        parts = [p for p in (endpoint.earliest, endpoint.latest) if p]
        return "\u2013".join(dict.fromkeys(parts))

    place = place_names.get(fact.place_id) or fact.place_id or ""
    start, end = span(fact.start), span(fact.end)
    period = " ".join(
        part for part in (f"från {start}" if start else "", f"till {end}" if end else "") if part
    )
    text = f"Boende: {place}" if place else "Boende"
    if period:
        text += f" ({period})"
    return text


@dataclass
class UsageStats:
    """Usage statistics for a single source.

    ``person_ids`` is excluded from equality so that ``UsageStats(1, 2)``
    style comparisons keep working; ``person_count == len(person_ids)``
    whenever the stats come from :func:`compute_usage_stats`.
    """

    event_count: int
    person_count: int
    residence_count: int = 0
    person_ids: list[str] = field(default_factory=list, compare=False)


def compute_usage_stats(
    source_id: str,
    events: list[Event],
    residences: Iterable[ResidenceFact] | None = None,
) -> UsageStats:
    """Compute usage statistics for a source.

    A person is "on" the source when an event they participate in cites it in
    ``date.source_refs`` or ``place.source_refs``, or when one of their
    residence facts has an observation citing it.

    Args:
        source_id: The ID of the source to check.
        events: All events in the project.
        residences: Optional residence facts (``data.residences``).

    Returns:
        UsageStats with event_count (events citing the source), residence_count
        (residence facts citing it at least once), person_ids (sorted distinct
        ids from events and residences) and person_count (``len(person_ids)``).
    """
    event_count = 0
    residence_count = 0
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

    for fact in residences or ():
        if any(obs.source_ref.source_id == source_id for obs in fact.observations):
            residence_count += 1
            person_ids.add(fact.person_id)

    ordered = sorted(person_ids)
    return UsageStats(
        event_count=event_count,
        person_count=len(ordered),
        residence_count=residence_count,
        person_ids=ordered,
    )
