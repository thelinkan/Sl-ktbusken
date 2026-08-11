"""Unit tests for the Coverage_Analyzer gap computation.

Covers Requirements 5.1 and 5.2 (gaps as maximal runs between the lowest
`observed_from` and the highest `observed_to`, ordered by first uncovered year),
5.3 and 16.13 (zero gaps for zero or one Observation and for a complete union),
5.4 (nothing mutated) and 5.10 (`splittable`).
"""

from copy import deepcopy

from slaktbusken.model.event import SourceRef
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
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
