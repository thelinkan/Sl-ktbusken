"""Coverage_Analyzer: research gaps derived from residence evidence.

A Residence_Fact states a period; its Observations document parts of that
period. Where the documented years leave a hole, the genealogist has a volume
left to look up. This module finds those holes.

Every function here is pure: it reads the Residence_Fact and the Project and
returns new records, leaving every field of the fact, of its Observations and of
every other Project entity unchanged (Requirement 5.4). Year arithmetic goes
through :func:`slaktbusken.model.residence.coverage_union`,
:func:`observation_span_years` and :func:`core_aggregate`, which are the single
definitions of what an Observation covers; nothing here re-derives them.

Pure module: no Qt, no I/O, no mutation of the Project.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import (
    Observation,
    ResidenceFact,
    core_aggregate,
    coverage_union,
    observation_span_years,
)


@dataclass
class CoverageGap:
    """A maximal run of years a Residence_Fact's Observations do not document.

    `suggestion` is the research suggestion text phrased from the Source cited
    immediately before the gap; `splittable` says whether the fact has evidence
    on both sides of the gap and can therefore be split at it (Requirement 5.10).
    """

    residence_id: str
    first_year: int
    last_year: int
    suggestion: str
    splittable: bool


@dataclass
class OpenEndpointSuggestion:
    """A research suggestion for one open bound of a Residence_Fact.

    `side` is "start" for an absent `start.earliest` and "end" for an absent
    `end.latest`; `suggestion` names "början" or "slutet" accordingly
    (Requirement 5.7).
    """

    residence_id: str
    side: str        # "start" | "end"
    suggestion: str  # names "början" or "slutet"


@dataclass
class TimelineGap:
    """A maximal run of years contained in no Possible_Span of one person.

    Reported between the person's lowest and highest bounded Possible_Span year
    (Requirement 5.8).
    """

    person_id: str
    first_year: int
    last_year: int


def _observation_year_bounds(
    observations: list[Observation],
) -> Optional[tuple[int, int]]:
    """The lowest `observed_from` year and highest `observed_to` year, or ``None``.

    Both come from :func:`core_aggregate`, the shared definition of the
    observation-derived core, so a bound no Observation holds makes the whole
    range undefined. Absent, malformed and whitespace-only values are absent
    there, and the range is reported exactly as stored, so an inverted pair
    stays inverted and yields no years at all.
    """
    lowest_from, highest_to = core_aggregate(observations)
    if lowest_from is None or highest_to is None:
        return None
    return (int(lowest_from), int(highest_to))


def _maximal_runs(years: list[int]) -> list[tuple[int, int]]:
    """Group ascending, distinct *years* into maximal runs of consecutive years."""
    runs: list[tuple[int, int]] = []
    for year in years:
        if runs and year == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], year)
        else:
            runs.append((year, year))
    return runs


def _is_splittable(fact: ResidenceFact, first_year: int, last_year: int) -> bool:
    """Whether *fact* has an Observation ending before and one beginning after the gap.

    Requirement 5.10: the split action is offered only when at least one
    Observation's covered years end before the gap's first uncovered year and at
    least one Observation's covered years begin after its last uncovered year.
    """
    ends_before = False
    begins_after = False
    for observation in fact.observations:
        span = observation_span_years(observation)
        if span is None:
            continue
        span_first, span_last = span
        if span_last < first_year:
            ends_before = True
        if span_first > last_year:
            begins_after = True
    return ends_before and begins_after


def coverage_gaps(fact: ResidenceFact, data: ProjectData) -> list[CoverageGap]:
    """The coverage gaps of *fact*, ordered by first uncovered year ascending.

    A gap is a maximal run of consecutive whole years absent from the coverage
    union between the lowest `observed_from` year and the highest `observed_to`
    year of the fact's Observations (Requirement 5.2). A fact carrying zero or
    exactly one Observation, or whose union covers every year in that range,
    yields no gap at all (Requirements 5.3, 16.13). `splittable` follows
    Requirement 5.10.

    *fact*, its Observations and *data* are only read; nothing is mutated
    (Requirement 5.4).

    The `suggestion` text of each gap is phrased from the Project Sources in a
    later step and is empty here.
    """
    if len(fact.observations) < 2:
        return []

    bounds = _observation_year_bounds(fact.observations)
    if bounds is None:
        return []
    lowest_from, highest_to = bounds

    covered = coverage_union(fact)
    uncovered = [
        year for year in range(lowest_from, highest_to + 1) if year not in covered
    ]

    return [
        CoverageGap(
            residence_id=fact.id,
            first_year=first_year,
            last_year=last_year,
            suggestion="",
            splittable=_is_splittable(fact, first_year, last_year),
        )
        for first_year, last_year in _maximal_runs(uncovered)
    ]
