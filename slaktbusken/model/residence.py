"""Residence facts ("Boende") and their pure derivations.

A :class:`ResidenceFact` states that one person was resident at one place over
one interval whose endpoints are *ranges* rather than points. Evidence attaches
as :class:`Observation` entries — one per church book volume/page — each keeping
its own attested sub-period.

Every derivation in this module is a pure function: it returns a new value and
leaves the Residence_Fact, its Endpoints and its Observations unchanged
(Requirements 2.13, 2.16, 5.4). All date comparison goes through
:mod:`slaktbusken.model.date_span`, which is the single source of truth for the
day-interval algebra; nothing here re-implements it.

``Endpoint.precision`` is descriptive only. It never takes part in
classification, validation or any bound derivation (Requirement 2.3).

Pure module: no Qt, no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Sequence

from slaktbusken.model.date_span import DaySpan, OpenSpan, expand_iso
from slaktbusken.model.event import SourceRef


# An Observation year is a bare four-digit year (ÅÅÅÅ).
_OBSERVATION_YEAR_RE = re.compile(r"^\d{4}$")


@dataclass
class Endpoint:
    """One boundary of a residence interval, expressed as a range.

    An absent bound means the transition happened at an unknown time in that
    direction. `precision` is descriptive only and never affects classification,
    validation, or derivation.
    """

    earliest: Optional[str] = None      # ÅÅÅÅ | ÅÅÅÅ-MM | ÅÅÅÅ-MM-DD
    latest: Optional[str] = None
    precision: Optional[str] = None     # day | month | year | approximate
    event_id: Optional[str] = None
    note: Optional[str] = None          # max 1000 characters


@dataclass
class Observation:
    """One evidence entry: the period a Source attests for this person.

    `observed_from`/`observed_to` may be narrower than the volume's coverage
    period, which stays on the Source as structured_reference["years"].
    """

    source_ref: SourceRef
    observed_from: str = ""             # "" or ÅÅÅÅ in 1500..2100
    observed_to: str = ""
    page_note: str = ""                 # max 1000 characters


@dataclass
class ResidenceFact:
    """One person, resident at one place, over one interval ("Boende")."""

    id: str
    person_id: str
    place_id: str
    start: Endpoint = field(default_factory=Endpoint)
    end: Endpoint = field(default_factory=Endpoint)
    role_in_household: str = ""         # free text, max 100 chars after trim
    observations: list[Observation] = field(default_factory=list)
    notes: str = ""                     # max 5000 chars


class EndpointKind(Enum):
    """How an Endpoint reads, determined by which of its bounds are present."""

    EXACT = auto()          # earliest and latest present, same day interval
    OPEN_LATEST = auto()    # only latest  → "present by …, arrived unknown earlier"
    OPEN_EARLIEST = auto()  # only earliest → "present on …, left unknown later"
    WINDOW = auto()         # both present, different day intervals
    UNKNOWN = auto()        # both absent


def _is_present(value: Optional[str]) -> bool:
    """Whether a bound counts as present: not ``None`` and not whitespace-only."""
    return value is not None and bool(value.strip())


def classify_endpoint(endpoint: Endpoint) -> EndpointKind:
    """Classify *endpoint* by bound presence and day-interval equality.

    Exactly one :class:`EndpointKind` is returned for every Endpoint. A value
    that is ``None``, empty or whitespace-only counts as absent
    (Requirement 2.1). Two present values are the same date only when they
    expand to the same closed day interval, so "1840" together with "1840-06" is
    a transition window rather than an exact date (Requirements 2.4, 2.7). A
    present but malformed value denotes no day interval, so it can never be
    equal to the other bound and yields ``WINDOW``; the malformed value itself
    is reported by the validator. `precision` is ignored (Requirement 2.3).
    """
    has_earliest = _is_present(endpoint.earliest)
    has_latest = _is_present(endpoint.latest)

    if not has_earliest and not has_latest:
        return EndpointKind.UNKNOWN
    if not has_earliest:
        return EndpointKind.OPEN_LATEST
    if not has_latest:
        return EndpointKind.OPEN_EARLIEST

    span_earliest = expand_iso(endpoint.earliest)
    span_latest = expand_iso(endpoint.latest)
    if span_earliest is not None and span_earliest == span_latest:
        return EndpointKind.EXACT
    return EndpointKind.WINDOW


def certain_core(fact: ResidenceFact) -> Optional[DaySpan]:
    """The Certain_Core of *fact*, or ``None`` when it is empty.

    The core runs from the last day of `start.latest` through the first day of
    `end.earliest`. It is empty when either bound is absent or malformed, or
    when the last day of `start.latest` falls after the first day of
    `end.earliest` (Requirement 2.13). *fact* is left unchanged.
    """
    start_latest = expand_iso(fact.start.latest)
    end_earliest = expand_iso(fact.end.earliest)
    if start_latest is None or end_earliest is None:
        return None
    if start_latest.last > end_earliest.first:
        return None
    return DaySpan(start_latest.last, end_earliest.first)


def possible_span(fact: ResidenceFact) -> OpenSpan:
    """The Possible_Span of *fact*.

    The span runs from the first day of `start.earliest` through the last day of
    `end.latest`, unbounded in a direction whose bound is absent or malformed
    (Requirement 2.16). *fact* is left unchanged.
    """
    start_earliest = expand_iso(fact.start.earliest)
    end_latest = expand_iso(fact.end.latest)
    return OpenSpan(
        first=None if start_earliest is None else start_earliest.first,
        last=None if end_latest is None else end_latest.last,
    )


def _observation_year(value: Optional[str]) -> Optional[int]:
    """The year an Observation bound holds, or ``None`` when absent or malformed.

    Only the bare four-digit form ÅÅÅÅ is a year; surrounding whitespace is
    trimmed and an empty or whitespace-only value counts as absent. The
    1500–2100 range is a validation rule (Requirement 4.12), not part of the
    derivation, so a four-digit year outside it still yields its year part.
    """
    if value is None:
        return None
    trimmed = value.strip()
    if not _OBSERVATION_YEAR_RE.match(trimmed):
        return None
    return int(trimmed)


def observation_span_years(observation: Observation) -> Optional[tuple[int, int]]:
    """The inclusive year range *observation* attests, or ``None`` when it has none.

    Both bounds present yields their two year parts as stored, so an inverted
    pair is returned inverted and the validator reports it. Exactly one bound
    present yields that single year twice (Requirement 4.6). Both absent or
    malformed yields ``None``. *observation* is left unchanged.
    """
    first = _observation_year(observation.observed_from)
    last = _observation_year(observation.observed_to)
    if first is None and last is None:
        return None
    if first is None:
        return (last, last)  # type: ignore[return-value]  # last is not None here
    if last is None:
        return (first, first)
    return (first, last)


def coverage_union(fact: ResidenceFact) -> set[int]:
    """The set of whole calendar years the Observations of *fact* cover.

    Each Observation contributes every year from its `observed_from` year part
    through its `observed_to` year part inclusive, so identical, overlapping and
    adjacent Observations contribute each year exactly once (Requirement 5.1).
    An Observation holding only one bound covers that single year
    (Requirement 4.6); one holding an inverted pair contributes nothing.
    *fact* is left unchanged.
    """
    years: set[int] = set()
    for observation in fact.observations:
        span = observation_span_years(observation)
        if span is None:
            continue
        first, last = span
        years.update(range(first, last + 1))
    return years


def core_aggregate(
    observations: Sequence[Observation],
) -> tuple[Optional[str], Optional[str]]:
    """The documented core the given *observations* aggregate to.

    Returns ``(lowest observed_from, highest observed_to)`` in ISO form, each
    ``None`` when no Observation holds that bound. This is the single definition
    of the observation-derived core used by attach, removal, split and merge.
    The given sequence and its Observations are left unchanged.
    """
    from_years = [
        year
        for year in (_observation_year(obs.observed_from) for obs in observations)
        if year is not None
    ]
    to_years = [
        year
        for year in (_observation_year(obs.observed_to) for obs in observations)
        if year is not None
    ]
    lowest_from = f"{min(from_years):04d}" if from_years else None
    highest_to = f"{max(to_years):04d}" if to_years else None
    return (lowest_from, highest_to)
