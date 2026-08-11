"""Unit tests for the Coverage_Analyzer gap computation.

Covers Requirements 5.1 and 5.2 (gaps as maximal runs between the lowest
`observed_from` and the highest `observed_to`, ordered by first uncovered year),
5.3 and 16.13 (zero gaps for zero or one Observation and for a complete union),
5.4 (nothing mutated), 5.5 and 5.14 (suggestion phrasing), 5.6 (candidate
volumes) and 5.10 (`splittable`).
"""

from copy import deepcopy

from slaktbusken.model.event import SourceRef
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.source import Source, StructuredReference
from slaktbusken.services.residence_coverage import (
    CoverageGap,
    OpenEndpointSuggestion,
    TimelineGap,
    coverage_gaps,
)


def _observation(observed_from="", observed_to="", source_id="source_1"):
    return Observation(
        source_ref=SourceRef(source_id=source_id, quality="secondary"),
        observed_from=observed_from,
        observed_to=observed_to,
    )


def _fact(observations, residence_id="residence_1"):
    return ResidenceFact(
        id=residence_id,
        person_id="person_1",
        place_id="place_1",
        observations=list(observations),
    )


# --- record shapes ---


def test_coverage_gap_carries_the_gap_years_suggestion_and_splittable():
    gap = CoverageGap(
        residence_id="residence_1",
        first_year=1876,
        last_year=1880,
        suggestion="",
        splittable=True,
    )
    assert (gap.residence_id, gap.first_year, gap.last_year) == ("residence_1", 1876, 1880)
    assert gap.suggestion == ""
    assert gap.splittable is True


def test_open_endpoint_suggestion_carries_side_and_text():
    suggestion = OpenEndpointSuggestion(
        residence_id="residence_1", side="start", suggestion="början"
    )
    assert (suggestion.residence_id, suggestion.side) == ("residence_1", "start")
    assert suggestion.suggestion == "början"


def test_timeline_gap_carries_person_and_gap_years():
    gap = TimelineGap(person_id="person_1", first_year=1848, last_year=1852)
    assert (gap.person_id, gap.first_year, gap.last_year) == ("person_1", 1848, 1852)


# --- gaps as maximal runs (Requirements 5.1, 5.2) ---


def test_single_gap_between_two_volumes_reports_its_first_and_last_year():
    fact = _fact([_observation("1866", "1870"), _observation("1881", "1885")])

    gaps = coverage_gaps(fact, ProjectData())

    assert [(gap.first_year, gap.last_year) for gap in gaps] == [(1871, 1880)]
    assert gaps[0].residence_id == "residence_1"


def test_the_user_story_volumes_leave_only_the_undocumented_run():
    fact = _fact(
        [
            _observation("1866", "1870"),
            _observation("1871", "1875"),
            _observation("1881", "1885"),
        ]
    )

    gaps = coverage_gaps(fact, ProjectData())

    assert [(gap.first_year, gap.last_year) for gap in gaps] == [(1876, 1880)]


def test_two_holes_are_reported_separately_ordered_by_first_uncovered_year():
    fact = _fact(
        [
            _observation("1890", "1892"),
            _observation("1860", "1861"),
            _observation("1870", "1871"),
        ]
    )

    gaps = coverage_gaps(fact, ProjectData())

    assert [(gap.first_year, gap.last_year) for gap in gaps] == [
        (1862, 1869),
        (1872, 1889),
    ]


def test_a_one_year_hole_is_reported_as_a_single_year_run():
    fact = _fact([_observation("1866", "1870"), _observation("1872", "1875")])

    gaps = coverage_gaps(fact, ProjectData())

    assert [(gap.first_year, gap.last_year) for gap in gaps] == [(1871, 1871)]


def test_single_bound_observations_cover_their_one_year_and_bound_the_range():
    fact = _fact([_observation(observed_from="1860"), _observation(observed_to="1863")])

    gaps = coverage_gaps(fact, ProjectData())

    assert [(gap.first_year, gap.last_year) for gap in gaps] == [(1861, 1862)]


def test_years_outside_the_observed_range_are_never_reported():
    fact = _fact([_observation("1866", "1870"), _observation("1875", "1880")])

    gaps = coverage_gaps(fact, ProjectData())

    assert [(gap.first_year, gap.last_year) for gap in gaps] == [(1871, 1874)]


# --- no gaps (Requirements 5.3, 16.13) ---


def test_no_observations_yields_no_gap():
    assert coverage_gaps(_fact([]), ProjectData()) == []


def test_one_observation_yields_no_gap_however_wide_its_span():
    assert coverage_gaps(_fact([_observation("1850", "1899")]), ProjectData()) == []


def test_a_complete_union_yields_no_gap():
    fact = _fact([_observation("1866", "1870"), _observation("1871", "1875")])

    assert coverage_gaps(fact, ProjectData()) == []


def test_overlapping_and_identical_observations_yield_no_gap():
    fact = _fact(
        [
            _observation("1866", "1872"),
            _observation("1866", "1872"),
            _observation("1870", "1875"),
        ]
    )

    assert coverage_gaps(fact, ProjectData()) == []


def test_observations_without_usable_years_yield_no_gap():
    fact = _fact([_observation("", ""), _observation("skräp", "1880")])

    assert coverage_gaps(fact, ProjectData()) == []


def test_an_inverted_observation_range_yields_no_gap():
    fact = _fact([_observation(observed_from="1880"), _observation(observed_to="1870")])

    assert coverage_gaps(fact, ProjectData()) == []


# --- splittable (Requirement 5.10) ---


def test_a_gap_with_evidence_on_both_sides_is_splittable():
    fact = _fact([_observation("1835", "1846"), _observation("1853", "1857")])

    gaps = coverage_gaps(fact, ProjectData())

    assert [(gap.first_year, gap.last_year) for gap in gaps] == [(1847, 1852)]
    assert gaps[0].splittable is True


def test_an_observation_bracketing_the_hole_leaves_no_gap_to_split():
    fact = _fact(
        [
            _observation("1866", "1870"),
            _observation("1866", "1885", source_id="source_2"),
            _observation("1881", "1885", source_id="source_3"),
        ]
    )

    assert coverage_gaps(fact, ProjectData()) == []


def test_every_gap_of_a_many_volume_fact_is_splittable():
    # A reported gap always has an Observation ending on the year before it and
    # one beginning on the year after it, so each side carries evidence.
    fact = _fact(
        [
            _observation("1860", "1868"),
            _observation("1876", "1885", source_id="source_2"),
            _observation("1890", "1892", source_id="source_3"),
        ]
    )

    gaps = coverage_gaps(fact, ProjectData())

    assert [(gap.first_year, gap.last_year) for gap in gaps] == [
        (1869, 1875),
        (1886, 1889),
    ]
    assert [gap.splittable for gap in gaps] == [True, True]


# --- purity (Requirement 5.4) ---


def test_computing_gaps_mutates_neither_the_fact_nor_the_project():
    fact = ResidenceFact(
        id="residence_1",
        person_id="person_1",
        place_id="place_1",
        start=Endpoint(earliest="1865", latest="1866"),
        end=Endpoint(earliest="1885", latest="1886"),
        role_in_household="dräng",
        observations=[_observation("1866", "1870"), _observation("1881", "1885")],
        notes="anteckning",
    )
    data = ProjectData()
    fact_before = deepcopy(fact)
    data_before = deepcopy(data)

    coverage_gaps(fact, data)

    assert fact == fact_before
    assert data == data_before


# --- helpers for suggestion tests ---


def _church_book_source(
    source_id: str,
    parish: str = "Ljusdal",
    series: str = "AI",
    volume: str = "17",
    years: str = "1866-1870",
) -> Source:
    return Source(
        id=source_id,
        provider="Arkiv Digital",
        source_type="church_book",
        title=f"{parish} {series}:{volume}",
        structured_reference=StructuredReference(
            fields={
                "parish": parish,
                "series": series,
                "volume": volume,
                "years": years,
            }
        ),
    )


# --- suggestion phrasing (Requirements 5.5, 5.14) ---


def test_multi_year_gap_uses_period_form_with_en_dash():
    """Requirement 5.5: multi-year form uses 'period 1876–1880 saknar källa'."""
    source = _church_book_source("source_1", parish="Ljusdal", series="AI", years="1871-1875")
    fact = _fact([
        _observation("1871", "1875", source_id="source_1"),
        _observation("1881", "1885", source_id="source_2"),
    ])
    data = ProjectData(sources=[source])

    gaps = coverage_gaps(fact, data)

    assert len(gaps) == 1
    assert "Ljusdal AI: period 1876\u20131880 saknar källa" in gaps[0].suggestion


def test_single_year_gap_uses_year_form():
    """Requirement 5.14: single-year form uses 'år 1876 saknar källa'."""
    source = _church_book_source("source_1", parish="Ljusdal", series="AI", years="1875")
    fact = _fact([
        _observation("1875", "1875", source_id="source_1"),
        _observation("1877", "1880", source_id="source_2"),
    ])
    data = ProjectData(sources=[source])

    gaps = coverage_gaps(fact, data)

    assert len(gaps) == 1
    assert gaps[0].suggestion.startswith("Ljusdal AI: år 1876 saknar källa")


def test_parish_and_series_from_preceding_observation_source():
    """Parish and series come from the Source of the Observation ending before the gap."""
    source_before = _church_book_source(
        "source_1", parish="Delsbo", series="AII", years="1860-1870"
    )
    source_after = _church_book_source(
        "source_2", parish="Ljusdal", series="AI", years="1880-1885"
    )
    fact = _fact([
        _observation("1860", "1870", source_id="source_1"),
        _observation("1880", "1885", source_id="source_2"),
    ])
    data = ProjectData(sources=[source_before, source_after])

    gaps = coverage_gaps(fact, data)

    # Should use Delsbo AII (the source of the preceding observation)
    assert gaps[0].suggestion.startswith("Delsbo AII: period 1871\u20131879 saknar källa")


def test_absent_parish_is_omitted_with_its_space():
    """An absent parish is omitted together with its separating space."""
    source = _church_book_source("source_1", parish="", series="AI", years="1866-1870")
    fact = _fact([
        _observation("1866", "1870", source_id="source_1"),
        _observation("1876", "1880", source_id="source_2"),
    ])
    data = ProjectData(sources=[source])

    gaps = coverage_gaps(fact, data)

    assert gaps[0].suggestion.startswith("AI: period 1871\u20131875 saknar källa")


def test_absent_series_is_omitted_with_its_space():
    """An absent series is omitted together with its separating space."""
    source = _church_book_source("source_1", parish="Ljusdal", series="", years="1866-1870")
    fact = _fact([
        _observation("1866", "1870", source_id="source_1"),
        _observation("1876", "1880", source_id="source_2"),
    ])
    data = ProjectData(sources=[source])

    gaps = coverage_gaps(fact, data)

    assert gaps[0].suggestion.startswith("Ljusdal: period 1871\u20131875 saknar källa")


def test_both_parish_and_series_absent_yields_bare_period_clause():
    """When both parish and series are absent, only the period clause remains."""
    source = _church_book_source("source_1", parish="", series="", years="1866-1870")
    fact = _fact([
        _observation("1866", "1870", source_id="source_1"),
        _observation("1876", "1880", source_id="source_2"),
    ])
    data = ProjectData(sources=[source])

    gaps = coverage_gaps(fact, data)

    assert gaps[0].suggestion.startswith("period 1871\u20131875 saknar källa")


def test_non_church_book_source_yields_no_parish_series():
    """A non-church_book Source yields no parish or series in the suggestion."""
    source = Source(
        id="source_1", provider="test", source_type="database", title="DB"
    )
    fact = _fact([
        _observation("1866", "1870", source_id="source_1"),
        _observation("1876", "1880", source_id="source_2"),
    ])
    data = ProjectData(sources=[source])

    gaps = coverage_gaps(fact, data)

    # No parish/series prefix
    assert gaps[0].suggestion.startswith("period 1871\u20131875 saknar källa")


def test_source_not_in_project_yields_no_parish_series():
    """A Source not found in the Project yields no parish or series."""
    fact = _fact([
        _observation("1866", "1870", source_id="missing_source"),
        _observation("1876", "1880", source_id="source_2"),
    ])
    data = ProjectData()

    gaps = coverage_gaps(fact, data)

    assert gaps[0].suggestion.startswith("period 1871\u20131875 saknar källa")


# --- candidate volumes (Requirement 5.6) ---


def test_candidates_appended_with_series_and_volume():
    """Matching candidate Sources are appended as 'kontrollera AI:18'."""
    source_before = _church_book_source(
        "source_1", parish="Ljusdal", series="AI", volume="17", years="1871-1875"
    )
    candidate = _church_book_source(
        "source_cand", parish="Ljusdal", series="AI", volume="18", years="1876-1880"
    )
    fact = _fact([
        _observation("1871", "1875", source_id="source_1"),
        _observation("1881", "1885", source_id="source_2"),
    ])
    data = ProjectData(sources=[source_before, candidate])

    gaps = coverage_gaps(fact, data)

    assert "kontrollera AI:18" in gaps[0].suggestion


def test_candidates_ordered_by_first_year_ascending():
    """Candidate Sources are ordered by first year ascending."""
    source_before = _church_book_source(
        "source_1", parish="Ljusdal", series="AI", volume="15", years="1860-1870"
    )
    cand_later = _church_book_source(
        "cand_2", parish="Ljusdal", series="AI", volume="18", years="1879-1885"
    )
    cand_earlier = _church_book_source(
        "cand_1", parish="Ljusdal", series="AI", volume="17", years="1871-1878"
    )
    fact = _fact([
        _observation("1860", "1870", source_id="source_1"),
        _observation("1886", "1890", source_id="source_2"),
    ])
    data = ProjectData(sources=[source_before, cand_later, cand_earlier])

    gaps = coverage_gaps(fact, data)

    assert "kontrollera AI:17, AI:18" in gaps[0].suggestion


def test_at_most_five_candidates_are_appended():
    """At most five matching candidate Sources are appended."""
    source_before = _church_book_source(
        "source_1", parish="Ljusdal", series="AI", volume="10", years="1850-1855"
    )
    candidates = [
        _church_book_source(
            f"cand_{i}", parish="Ljusdal", series="AI",
            volume=str(11 + i), years=f"{1856 + i * 5}-{1860 + i * 5}"
        )
        for i in range(7)  # 7 candidates, only 5 should appear
    ]
    fact = _fact([
        _observation("1850", "1855", source_id="source_1"),
        _observation("1900", "1905", source_id="source_2"),
    ])
    data = ProjectData(sources=[source_before] + candidates)

    gaps = coverage_gaps(fact, data)

    # Count the number of candidates in the suggestion
    suggestion = gaps[0].suggestion
    assert "kontrollera" in suggestion
    candidate_part = suggestion.split("kontrollera ")[1]
    assert len(candidate_part.split(", ")) == 5


def test_no_candidates_when_no_matching_sources():
    """No candidates appended when no Sources match parish/series."""
    source_before = _church_book_source(
        "source_1", parish="Ljusdal", series="AI", volume="17", years="1871-1875"
    )
    non_matching = _church_book_source(
        "other", parish="Delsbo", series="AI", volume="5", years="1876-1880"
    )
    fact = _fact([
        _observation("1871", "1875", source_id="source_1"),
        _observation("1881", "1885", source_id="source_2"),
    ])
    data = ProjectData(sources=[source_before, non_matching])

    gaps = coverage_gaps(fact, data)

    assert "kontrollera" not in gaps[0].suggestion


def test_candidate_must_cover_uncovered_year():
    """A Source with same parish/series but no uncovered year is excluded."""
    source_before = _church_book_source(
        "source_1", parish="Ljusdal", series="AI", volume="17", years="1871-1875"
    )
    # This source covers 1860-1870, which does NOT overlap the gap 1876-1880
    non_overlapping = _church_book_source(
        "other", parish="Ljusdal", series="AI", volume="16", years="1860-1870"
    )
    fact = _fact([
        _observation("1871", "1875", source_id="source_1"),
        _observation("1881", "1885", source_id="source_2"),
    ])
    data = ProjectData(sources=[source_before, non_overlapping])

    gaps = coverage_gaps(fact, data)

    assert "kontrollera" not in gaps[0].suggestion


def test_whitespace_only_parish_treated_as_absent():
    """A whitespace-only parish value is treated as absent."""
    source = _church_book_source("source_1", parish="   ", series="AI", years="1866-1870")
    fact = _fact([
        _observation("1866", "1870", source_id="source_1"),
        _observation("1876", "1880", source_id="source_2"),
    ])
    data = ProjectData(sources=[source])

    gaps = coverage_gaps(fact, data)

    # Parish is absent, so only series appears in prefix
    assert gaps[0].suggestion.startswith("AI: period 1871\u20131875 saknar källa")


def test_purity_with_suggestion_computation():
    """Computing gaps with sources mutates neither the fact nor the project."""
    source = _church_book_source("source_1", parish="Ljusdal", series="AI", years="1866-1870")
    candidate = _church_book_source(
        "cand_1", parish="Ljusdal", series="AI", volume="18", years="1876-1880"
    )
    fact = _fact([
        _observation("1866", "1870", source_id="source_1"),
        _observation("1881", "1885", source_id="source_2"),
    ])
    data = ProjectData(sources=[source, candidate])
    fact_before = deepcopy(fact)
    data_before = deepcopy(data)

    coverage_gaps(fact, data)

    assert fact == fact_before
    assert data == data_before


# ---------------------------------------------------------------------------
# Tests for open_endpoint_suggestions (Requirement 5.7)
# ---------------------------------------------------------------------------

from slaktbusken.model.residence import EndpointKind, classify_endpoint
from slaktbusken.services.residence_coverage import (
    PersonCoverageResult,
    analyze_person,
    open_endpoint_suggestions,
    timeline_gaps,
)
from slaktbusken.model.event import DateValue, Event, Participant


def test_open_start_suggests_borjan():
    """A start with absent earliest yields a suggestion naming 'början'."""
    fact = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest=None, latest="1840"),
        end=Endpoint(earliest="1885", latest="1890"),
    )
    suggestions = open_endpoint_suggestions(fact)
    assert len(suggestions) == 1
    assert suggestions[0].side == "start"
    assert "början" in suggestions[0].suggestion
    assert suggestions[0].residence_id == "r1"


def test_open_end_suggests_slutet():
    """An end with absent latest yields a suggestion naming 'slutet'."""
    fact = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest="1835", latest="1840"),
        end=Endpoint(earliest="1885", latest=None),
    )
    suggestions = open_endpoint_suggestions(fact)
    assert len(suggestions) == 1
    assert suggestions[0].side == "end"
    assert "slutet" in suggestions[0].suggestion


def test_both_open_yields_at_most_two_suggestions():
    """A fact with both start.earliest and end.latest absent yields two suggestions."""
    fact = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest=None, latest="1840"),
        end=Endpoint(earliest="1885", latest=None),
    )
    suggestions = open_endpoint_suggestions(fact)
    assert len(suggestions) == 2
    sides = {s.side for s in suggestions}
    assert sides == {"start", "end"}


def test_completely_unknown_endpoints_yield_two_suggestions():
    """Both endpoints unknown (earliest and latest both absent) yields two suggestions."""
    fact = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(),
        end=Endpoint(),
    )
    suggestions = open_endpoint_suggestions(fact)
    assert len(suggestions) == 2


def test_fully_specified_endpoints_yield_no_suggestions():
    """A fact with both endpoints having their required bounds yields no suggestions."""
    fact = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest="1835", latest="1840"),
        end=Endpoint(earliest="1885", latest="1890"),
    )
    suggestions = open_endpoint_suggestions(fact)
    assert suggestions == []


def test_exact_endpoints_yield_no_suggestions():
    """Exact endpoints (earliest == latest) yield no suggestions."""
    fact = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest="1840", latest="1840"),
        end=Endpoint(earliest="1890", latest="1890"),
    )
    suggestions = open_endpoint_suggestions(fact)
    assert suggestions == []


def test_open_start_with_only_earliest_no_latest_yields_no_start_suggestion():
    """A start with earliest present and latest absent is OPEN_EARLIEST, not OPEN_LATEST."""
    fact = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest="1835", latest=None),
        end=Endpoint(earliest="1885", latest="1890"),
    )
    suggestions = open_endpoint_suggestions(fact)
    # start is OPEN_EARLIEST (only earliest present) — this means we have the earliest
    # but not the latest; start.earliest is present so we do NOT report "beginning is open"
    assert suggestions == []


# ---------------------------------------------------------------------------
# Tests for timeline_gaps (Requirements 5.8, 5.15)
# ---------------------------------------------------------------------------


def test_single_fact_yields_no_timeline_gap():
    """A person with one fact produces no timeline gap."""
    fact = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest="1840"),
        end=Endpoint(latest="1870"),
    )
    data = ProjectData(residences=[fact])
    gaps = timeline_gaps("p1", data)
    assert gaps == []


def test_no_facts_yields_no_timeline_gap():
    """A person with no facts produces no timeline gap."""
    data = ProjectData()
    gaps = timeline_gaps("p1", data)
    assert gaps == []


def test_two_facts_with_gap_between_possible_spans():
    """Two facts with a year gap between their Possible_Spans yield one timeline gap."""
    fact1 = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest="1840"),
        end=Endpoint(latest="1850"),
    )
    fact2 = ResidenceFact(
        id="r2",
        person_id="p1",
        place_id="pl2",
        start=Endpoint(earliest="1855"),
        end=Endpoint(latest="1870"),
    )
    data = ProjectData(residences=[fact1, fact2])
    gaps = timeline_gaps("p1", data)
    assert len(gaps) == 1
    assert gaps[0].first_year == 1851
    assert gaps[0].last_year == 1854
    assert gaps[0].person_id == "p1"


def test_touching_possible_spans_leave_no_gap():
    """Facts touching at a boundary year leave no gap (Requirement 14.3)."""
    fact1 = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest="1840"),
        end=Endpoint(latest="1850"),
    )
    fact2 = ResidenceFact(
        id="r2",
        person_id="p1",
        place_id="pl2",
        start=Endpoint(earliest="1850"),
        end=Endpoint(latest="1870"),
    )
    data = ProjectData(residences=[fact1, fact2])
    gaps = timeline_gaps("p1", data)
    # 1850 is covered by both spans (they overlap at 1850)
    assert gaps == []


def test_unbounded_span_covers_everything_in_that_direction():
    """A span unbounded in a direction contains every year in that direction."""
    # fact1 has no end.latest → unbounded right → covers every year after start
    fact1 = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest="1840"),
        end=Endpoint(latest=None),
    )
    # fact2 has bounded end
    fact2 = ResidenceFact(
        id="r2",
        person_id="p1",
        place_id="pl2",
        start=Endpoint(earliest="1870"),
        end=Endpoint(latest="1880"),
    )
    data = ProjectData(residences=[fact1, fact2])
    gaps = timeline_gaps("p1", data)
    # fact1 is unbounded to the right so it covers everything from 1840 onwards,
    # so there's no gap between the two facts
    assert gaps == []


def test_birth_year_excludes_years_before():
    """Years before a dated birth are excluded from timeline gap reporting (5.15)."""
    fact1 = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest="1820"),
        end=Endpoint(latest="1830"),
    )
    fact2 = ResidenceFact(
        id="r2",
        person_id="p1",
        place_id="pl2",
        start=Endpoint(earliest="1850"),
        end=Endpoint(latest="1870"),
    )
    birth_event = Event(
        id="e1",
        type="birth",
        participants=[Participant(person_id="p1", role="child")],
        date=DateValue(value="1840", precision="year"),
    )
    data = ProjectData(residences=[fact1, fact2], events=[birth_event])
    gaps = timeline_gaps("p1", data)
    # Gap between 1831 and 1849, but years before 1840 (birth) are excluded
    # So the gap should be 1840–1849
    assert len(gaps) == 1
    assert gaps[0].first_year == 1840
    assert gaps[0].last_year == 1849


def test_death_year_excludes_years_after():
    """Years after a dated death are excluded from timeline gap reporting (5.15)."""
    fact1 = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest="1840"),
        end=Endpoint(latest="1850"),
    )
    fact2 = ResidenceFact(
        id="r2",
        person_id="p1",
        place_id="pl2",
        start=Endpoint(earliest="1870"),
        end=Endpoint(latest="1900"),
    )
    death_event = Event(
        id="e1",
        type="death",
        participants=[Participant(person_id="p1", role="deceased")],
        date=DateValue(value="1860", precision="year"),
    )
    data = ProjectData(residences=[fact1, fact2], events=[death_event])
    gaps = timeline_gaps("p1", data)
    # Gap between 1851 and 1869, but years after 1860 (death) are excluded
    # So the gap should be 1851–1860
    assert len(gaps) == 1
    assert gaps[0].first_year == 1851
    assert gaps[0].last_year == 1860


def test_both_birth_and_death_exclude_years_outside():
    """Both birth and death clamp the timeline gap range."""
    fact1 = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest="1800"),
        end=Endpoint(latest="1820"),
    )
    fact2 = ResidenceFact(
        id="r2",
        person_id="p1",
        place_id="pl2",
        start=Endpoint(earliest="1880"),
        end=Endpoint(latest="1920"),
    )
    birth_event = Event(
        id="e_birth",
        type="birth",
        participants=[Participant(person_id="p1", role="child")],
        date=DateValue(value="1840", precision="year"),
    )
    death_event = Event(
        id="e_death",
        type="death",
        participants=[Participant(person_id="p1", role="deceased")],
        date=DateValue(value="1900", precision="year"),
    )
    data = ProjectData(
        residences=[fact1, fact2],
        events=[birth_event, death_event],
    )
    gaps = timeline_gaps("p1", data)
    # The full range is 1800–1920. With birth at 1840 and death at 1900,
    # we only check 1840–1900. fact1 end at 1820 is before birth, so not relevant.
    # fact2 start at 1880. Years 1840–1879 are not covered by any span.
    # fact1's span is 1800–1820 (doesn't cover 1840+), fact2's span is 1880–1920
    assert len(gaps) == 1
    assert gaps[0].first_year == 1840
    assert gaps[0].last_year == 1879


def test_all_spans_unbounded_both_sides_yields_no_gap():
    """If all spans are unbounded on both sides, no bounded years exist."""
    fact1 = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest=None),
        end=Endpoint(latest=None),
    )
    fact2 = ResidenceFact(
        id="r2",
        person_id="p1",
        place_id="pl2",
        start=Endpoint(earliest=None),
        end=Endpoint(latest=None),
    )
    data = ProjectData(residences=[fact1, fact2])
    gaps = timeline_gaps("p1", data)
    assert gaps == []


def test_multiple_timeline_gaps_are_reported_separately():
    """Multiple timeline gaps are reported as separate maximal runs."""
    fact1 = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest="1840"),
        end=Endpoint(latest="1845"),
    )
    fact2 = ResidenceFact(
        id="r2",
        person_id="p1",
        place_id="pl2",
        start=Endpoint(earliest="1850"),
        end=Endpoint(latest="1855"),
    )
    fact3 = ResidenceFact(
        id="r3",
        person_id="p1",
        place_id="pl3",
        start=Endpoint(earliest="1860"),
        end=Endpoint(latest="1870"),
    )
    data = ProjectData(residences=[fact1, fact2, fact3])
    gaps = timeline_gaps("p1", data)
    assert len(gaps) == 2
    assert (gaps[0].first_year, gaps[0].last_year) == (1846, 1849)
    assert (gaps[1].first_year, gaps[1].last_year) == (1856, 1859)


# ---------------------------------------------------------------------------
# Tests for analyze_person
# ---------------------------------------------------------------------------


def test_analyze_person_combines_all_analyses():
    """analyze_person returns coverage gaps, open suggestions, and timeline gaps."""
    fact1 = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest=None, latest="1840"),
        end=Endpoint(earliest="1850", latest="1855"),
        observations=[
            _observation("1840", "1845", source_id="s1"),
            _observation("1848", "1850", source_id="s2"),
        ],
    )
    fact2 = ResidenceFact(
        id="r2",
        person_id="p1",
        place_id="pl2",
        start=Endpoint(earliest="1860", latest="1865"),
        end=Endpoint(earliest="1880", latest=None),
        observations=[
            _observation("1865", "1870", source_id="s3"),
            _observation("1875", "1880", source_id="s4"),
        ],
    )
    data = ProjectData(residences=[fact1, fact2])
    result = analyze_person("p1", data)

    assert isinstance(result, PersonCoverageResult)
    # fact1 has a gap at 1846–1847, fact2 has a gap at 1871–1874
    assert len(result.coverage_gaps) == 2
    # fact1 has open start (no earliest), fact2 has open end (no latest)
    assert len(result.open_endpoint_suggestions) == 2
    # Timeline gap between 1856 and 1859 (between fact1 end.latest=1855 and fact2 start.earliest=1860)
    assert len(result.timeline_gaps) == 1
    assert result.timeline_gaps[0].first_year == 1856
    assert result.timeline_gaps[0].last_year == 1859


def test_analyze_person_no_facts():
    """analyze_person for a person with no facts yields empty results."""
    data = ProjectData()
    result = analyze_person("p_unknown", data)
    assert result.coverage_gaps == []
    assert result.open_endpoint_suggestions == []
    assert result.timeline_gaps == []


def test_analyze_person_only_considers_that_person():
    """analyze_person ignores facts belonging to other persons."""
    fact_p1 = ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest="1840"),
        end=Endpoint(latest="1870"),
    )
    fact_p2 = ResidenceFact(
        id="r2",
        person_id="p2",
        place_id="pl2",
        start=Endpoint(earliest="1840"),
        end=Endpoint(latest="1870"),
    )
    data = ProjectData(residences=[fact_p1, fact_p2])
    result = analyze_person("p1", data)
    # Only one fact for p1 → no timeline gaps, no coverage gaps (needs 2+ obs)
    assert result.timeline_gaps == []
    assert result.coverage_gaps == []
