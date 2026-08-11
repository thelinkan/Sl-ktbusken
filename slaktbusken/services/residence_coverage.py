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

import re
from dataclasses import dataclass
from typing import Optional

from slaktbusken.model.date_span import OpenSpan, year_of
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import (
    EndpointKind,
    Observation,
    ResidenceFact,
    classify_endpoint,
    core_aggregate,
    coverage_union,
    observation_span_years,
    possible_span,
)
from slaktbusken.model.source import Source

# Regex for parsing a Source ``years`` value: one four-digit year, or two
# separated by a hyphen-minus or en dash (U+2013) with optional spaces.
_YEARS_RE = re.compile(r"^\s*(\d{4})(?:\s*[-\u2013]\s*(\d{4}))?\s*$")


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


def _parse_source_years(years_value: Optional[str]) -> Optional[tuple[int, int]]:
    """Parse a Source ``years`` field into (first_year, last_year) or ``None``.

    Accepts a single four-digit year (both bounds equal) or two four-digit years
    separated by a hyphen-minus or en dash with optional surrounding spaces.
    Returns ``None`` for absent, empty, malformed or descending values.
    """
    if years_value is None:
        return None
    match = _YEARS_RE.match(years_value)
    if match is None:
        return None
    first = int(match.group(1))
    second_text = match.group(2)
    last = int(second_text) if second_text is not None else first
    if first > last:
        return None
    return (first, last)


def _source_years_contain_any(source: Source, uncovered_years: set[int]) -> bool:
    """Whether the Source ``years`` value covers at least one of *uncovered_years*."""
    parsed = _parse_source_years(
        source.structured_reference.fields.get("years")
    )
    if parsed is None:
        return False
    first, last = parsed
    return any(y in uncovered_years for y in range(first, last + 1))


def _source_first_year(source: Source) -> int:
    """The first year of a Source ``years`` value; used as sort key."""
    parsed = _parse_source_years(
        source.structured_reference.fields.get("years")
    )
    # Caller guarantees this is called only on sources with parseable years.
    assert parsed is not None
    return parsed[0]


def _find_preceding_observation(
    fact: ResidenceFact, gap_first_year: int
) -> Optional[Observation]:
    """The Observation whose covered years end immediately before the gap.

    "Immediately before" means the Observation's last covered year is
    gap_first_year - 1. If multiple Observations match (overlapping spans), the
    first in list order is used.
    """
    target_year = gap_first_year - 1
    for observation in fact.observations:
        span = observation_span_years(observation)
        if span is None:
            continue
        _, span_last = span
        if span_last == target_year:
            return observation
    return None


def _get_source_church_book_fields(
    source_id: str, data: ProjectData
) -> tuple[Optional[str], Optional[str]]:
    """Return (parish, series) from the church_book structured_reference of the source.

    Returns (None, None) if the source is not found or not a church_book type.
    A whitespace-only or empty field counts as absent.
    """
    for source in data.sources:
        if source.id == source_id:
            if source.source_type != "church_book":
                return (None, None)
            fields = source.structured_reference.fields
            parish = fields.get("parish")
            series = fields.get("series")
            # Treat whitespace-only as absent
            if parish is not None and isinstance(parish, str):
                parish = parish.strip() or None
            else:
                parish = None
            if series is not None and isinstance(series, str):
                series = series.strip() or None
            else:
                series = None
            return (parish, series)
    return (None, None)


def _find_candidate_sources(
    parish: Optional[str],
    series: Optional[str],
    uncovered_years: set[int],
    data: ProjectData,
    max_candidates: int = 5,
) -> list[Source]:
    """Find Sources with matching parish/series whose years cover gap years.

    Returns at most *max_candidates* Sources ordered by first year ascending.
    Matching is case-sensitive on the stored parish/series values.
    """
    candidates: list[Source] = []
    for source in data.sources:
        if source.source_type != "church_book":
            continue
        fields = source.structured_reference.fields
        src_parish = fields.get("parish")
        src_series = fields.get("series")
        # Normalize: strip and treat empty as None
        if src_parish is not None and isinstance(src_parish, str):
            src_parish = src_parish.strip() or None
        else:
            src_parish = None
        if src_series is not None and isinstance(src_series, str):
            src_series = src_series.strip() or None
        else:
            src_series = None
        if src_parish != parish or src_series != series:
            continue
        if _source_years_contain_any(source, uncovered_years):
            candidates.append(source)
    # Sort by first year ascending
    candidates.sort(key=_source_first_year)
    return candidates[:max_candidates]


def _format_candidate_label(source: Source) -> str:
    """Format a candidate Source as "{series}:{volume}" for the suggestion.

    Absent series or volume parts are omitted with their separating colon.
    """
    fields = source.structured_reference.fields
    series_val = fields.get("series")
    volume_val = fields.get("volume")
    # Normalize to string
    series_str = str(series_val).strip() if series_val is not None else ""
    volume_str = str(volume_val).strip() if volume_val is not None else ""
    if series_str and volume_str:
        return f"{series_str}:{volume_str}"
    if series_str:
        return series_str
    if volume_str:
        return volume_str
    return ""


def _build_suggestion(
    gap_first_year: int,
    gap_last_year: int,
    parish: Optional[str],
    series: Optional[str],
    candidates: list[Source],
) -> str:
    """Compose the full suggestion text for a coverage gap.

    Multi-year form: "{parish} {series}: period 1876\u20131880 saknar källa"
    Single-year form: "{parish} {series}: år 1876 saknar källa"
    (Requirements 5.5, 5.14)

    Absent parish or series is omitted together with its separating space.
    Candidate volumes appended as " \u2013 kontrollera AI:18, AI:19" (Requirement 5.6).
    """
    # Build the prefix: parish and series with absent values omitted
    parts: list[str] = []
    if parish:
        parts.append(parish)
    if series:
        parts.append(series)
    prefix = " ".join(parts)

    # Build the period/year clause
    if gap_first_year == gap_last_year:
        period_clause = f"år {gap_first_year} saknar källa"
    else:
        period_clause = f"period {gap_first_year}\u2013{gap_last_year} saknar källa"

    # Combine prefix and clause
    if prefix:
        suggestion = f"{prefix}: {period_clause}"
    else:
        suggestion = period_clause

    # Append candidate volumes
    if candidates:
        labels = [_format_candidate_label(c) for c in candidates]
        # Filter out empty labels
        labels = [label for label in labels if label]
        if labels:
            suggestion += f" \u2013 kontrollera {', '.join(labels)}"

    return suggestion


def coverage_gaps(fact: ResidenceFact, data: ProjectData) -> list[CoverageGap]:
    """The coverage gaps of *fact*, ordered by first uncovered year ascending.

    A gap is a maximal run of consecutive whole years absent from the coverage
    union between the lowest `observed_from` year and the highest `observed_to`
    year of the fact's Observations (Requirement 5.2). A fact carrying zero or
    exactly one Observation, or whose union covers every year in that range,
    yields no gap at all (Requirements 5.3, 16.13). `splittable` follows
    Requirement 5.10.

    The `suggestion` text of each gap is phrased from the preceding Observation's
    Source: parish and series from the `church_book` structured_reference, in
    multi-year or single-year form (Requirements 5.5, 5.14), with at most five
    matching candidate Sources appended (Requirement 5.6).

    *fact*, its Observations and *data* are only read; nothing is mutated
    (Requirement 5.4).
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

    gaps: list[CoverageGap] = []
    for first_year, last_year in _maximal_runs(uncovered):
        # Find the Observation ending immediately before this gap
        preceding_obs = _find_preceding_observation(fact, first_year)

        # Extract parish and series from the preceding Observation's Source
        parish: Optional[str] = None
        series: Optional[str] = None
        if preceding_obs is not None:
            parish, series = _get_source_church_book_fields(
                preceding_obs.source_ref.source_id, data
            )

        # Find candidate volumes
        uncovered_years = set(range(first_year, last_year + 1))
        candidates = _find_candidate_sources(parish, series, uncovered_years, data)

        suggestion = _build_suggestion(
            first_year, last_year, parish, series, candidates
        )

        gaps.append(
            CoverageGap(
                residence_id=fact.id,
                first_year=first_year,
                last_year=last_year,
                suggestion=suggestion,
                splittable=_is_splittable(fact, first_year, last_year),
            )
        )

    return gaps


@dataclass
class PersonCoverageResult:
    """Combined coverage analysis for one person.

    Returned by :func:`analyze_person` to give the caller all coverage gaps,
    open-endpoint suggestions and timeline gaps in a single pass.
    """

    coverage_gaps: list[CoverageGap]
    open_endpoint_suggestions: list[OpenEndpointSuggestion]
    timeline_gaps: list[TimelineGap]


def open_endpoint_suggestions(fact: ResidenceFact) -> list[OpenEndpointSuggestion]:
    """Research suggestions for open bounds of *fact*.

    One suggestion per open bound: "början" for a start Endpoint whose
    `earliest` is absent, "slutet" for an end Endpoint whose `latest` is
    absent; at most two suggestions per fact (Requirement 5.7).

    *fact* is only read; nothing is mutated.
    """
    suggestions: list[OpenEndpointSuggestion] = []

    start_kind = classify_endpoint(fact.start)
    if start_kind in (EndpointKind.OPEN_LATEST, EndpointKind.UNKNOWN):
        # start.earliest is absent
        suggestions.append(
            OpenEndpointSuggestion(
                residence_id=fact.id,
                side="start",
                suggestion="Boendets början är öppen \u2013 ange tidigaste startdatum.",
            )
        )

    end_kind = classify_endpoint(fact.end)
    if end_kind in (EndpointKind.OPEN_EARLIEST, EndpointKind.UNKNOWN):
        # end.latest is absent
        suggestions.append(
            OpenEndpointSuggestion(
                residence_id=fact.id,
                side="end",
                suggestion="Boendets slutet är öppet \u2013 ange senaste slutdatum.",
            )
        )

    return suggestions


def _get_birth_death_years(
    person_id: str, data: ProjectData
) -> tuple[Optional[int], Optional[int]]:
    """Return (birth_year, death_year) for *person_id*, each ``None`` when undated.

    Examines all events of type "birth" or "death" where *person_id* participates.
    Uses the earliest birth date year and latest death date year (Requirement 5.15).
    """
    birth_year: Optional[int] = None
    death_year: Optional[int] = None

    for event in data.events:
        is_participant = any(
            p.person_id == person_id for p in event.participants
        )
        if not is_participant:
            continue
        if event.date is None:
            continue

        event_year = year_of(event.date.value)
        if event_year is None:
            continue

        if event.type == "birth":
            if birth_year is None or event_year < birth_year:
                birth_year = event_year
        elif event.type == "death":
            if death_year is None or event_year > death_year:
                death_year = event_year

    return (birth_year, death_year)


def timeline_gaps(person_id: str, data: ProjectData) -> list[TimelineGap]:
    """Timeline gaps for *person_id*: years in no Possible_Span.

    Returns the maximal runs of years, between the lowest and highest bounded
    Possible_Span year of the person, contained in no Possible_Span of that
    person's Residence_Facts (Requirement 5.8). A span unbounded in a direction
    contains every year in that direction. Years before a dated birth and after
    a dated death are excluded (Requirement 5.15). Facts touching at a boundary
    year leave no gap (Requirement 14.3).

    *data* is only read; nothing is mutated.
    """
    # Collect Possible_Spans for this person
    person_facts = [f for f in data.residences if f.person_id == person_id]
    if len(person_facts) < 2:
        # A single fact or no facts yields no timeline gap
        return []

    spans: list[OpenSpan] = [possible_span(f) for f in person_facts]

    # Find the lowest and highest bounded year across all Possible_Spans
    bounded_years: list[int] = []
    for span in spans:
        if span.first is not None:
            bounded_years.append(span.first.year)
        if span.last is not None:
            bounded_years.append(span.last.year)

    if not bounded_years:
        # All spans are unbounded on both sides — no gap can be defined
        return []

    lowest_year = min(bounded_years)
    highest_year = max(bounded_years)

    if lowest_year >= highest_year:
        return []

    # Exclude years before birth and after death (Requirement 5.15)
    birth_year, death_year = _get_birth_death_years(person_id, data)

    effective_start = lowest_year
    effective_end = highest_year
    if birth_year is not None:
        effective_start = max(effective_start, birth_year)
    if death_year is not None:
        effective_end = min(effective_end, death_year)

    if effective_start > effective_end:
        return []

    # Find years not contained in any Possible_Span
    # A span unbounded in a direction contains every year in that direction
    uncovered: list[int] = []
    for year in range(effective_start, effective_end + 1):
        # Exclude birth and death years themselves (5.15)
        if birth_year is not None and year < birth_year:
            continue
        if death_year is not None and year > death_year:
            continue
        # Check if this year is contained in any span
        covered = False
        for span in spans:
            if span.overlaps_year(year):
                covered = True
                break
        if not covered:
            uncovered.append(year)

    # Build maximal runs
    result: list[TimelineGap] = []
    for first_year, last_year in _maximal_runs(uncovered):
        result.append(
            TimelineGap(
                person_id=person_id,
                first_year=first_year,
                last_year=last_year,
            )
        )

    return result


def analyze_person(person_id: str, data: ProjectData) -> PersonCoverageResult:
    """Combined coverage analysis for *person_id*.

    A convenience function combining coverage gaps, open-endpoint suggestions
    and timeline gaps. Receives the full ProjectData so that prebuilt indexes
    can be passed through once per run for the 10 000-fact / 5-second budget
    (Requirement 5.9).

    *data* is only read; nothing is mutated.
    """
    person_facts = [f for f in data.residences if f.person_id == person_id]

    all_coverage_gaps: list[CoverageGap] = []
    all_open_suggestions: list[OpenEndpointSuggestion] = []

    for fact in person_facts:
        all_coverage_gaps.extend(coverage_gaps(fact, data))
        all_open_suggestions.extend(open_endpoint_suggestions(fact))

    all_timeline_gaps = timeline_gaps(person_id, data)

    return PersonCoverageResult(
        coverage_gaps=all_coverage_gaps,
        open_endpoint_suggestions=all_open_suggestions,
        timeline_gaps=all_timeline_gaps,
    )
