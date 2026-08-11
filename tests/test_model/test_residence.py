"""Unit tests for the residence entity and its pure derivations.

Covers Requirements 1.1 and 4.1 (dataclass shape and defaults), 2.1 and 2.3–2.8
(Endpoint classification), 2.13 (Certain_Core), 2.16 (Possible_Span), 4.6 and
5.1 (observation spans and the coverage union) and the shared core aggregate.
"""

from dataclasses import replace
from datetime import date

import pytest

from slaktbusken.model.date_span import DaySpan, OpenSpan
from slaktbusken.model.event import SourceRef
from slaktbusken.model.residence import (
    Endpoint,
    EndpointKind,
    Observation,
    ResidenceFact,
    certain_core,
    classify_endpoint,
    core_aggregate,
    coverage_union,
    observation_span_years,
    possible_span,
)


def _observation(observed_from="", observed_to="", source_id="source_1"):
    return Observation(
        source_ref=SourceRef(source_id=source_id, quality="secondary"),
        observed_from=observed_from,
        observed_to=observed_to,
    )


def _fact(start=None, end=None, observations=None):
    return ResidenceFact(
        id="residence_1",
        person_id="person_1",
        place_id="place_1",
        start=start or Endpoint(),
        end=end or Endpoint(),
        observations=list(observations or []),
    )


# --- dataclass shape and defaults (Requirements 1.1, 4.1) ---


def test_endpoint_defaults_are_all_absent():
    endpoint = Endpoint()
    assert endpoint.earliest is None
    assert endpoint.latest is None
    assert endpoint.precision is None
    assert endpoint.event_id is None
    assert endpoint.note is None


def test_observation_defaults_are_empty_text():
    observation = Observation(source_ref=SourceRef(source_id="source_1", quality="primary"))
    assert observation.observed_from == ""
    assert observation.observed_to == ""
    assert observation.page_note == ""


def test_residence_fact_defaults_hold_two_unknown_endpoints_and_empty_text():
    fact = ResidenceFact(id="residence_1", person_id="person_1", place_id="place_1")
    assert classify_endpoint(fact.start) is EndpointKind.UNKNOWN
    assert classify_endpoint(fact.end) is EndpointKind.UNKNOWN
    assert fact.role_in_household == ""
    assert fact.observations == []
    assert fact.notes == ""


def test_residence_fact_endpoints_are_not_shared_between_instances():
    first = ResidenceFact(id="residence_1", person_id="person_1", place_id="place_1")
    second = ResidenceFact(id="residence_2", person_id="person_1", place_id="place_1")
    first.start.earliest = "1840"
    first.observations.append(_observation("1840", "1845"))
    assert second.start.earliest is None
    assert second.observations == []


# --- classify_endpoint (Requirements 2.4-2.8) ---


@pytest.mark.parametrize(
    ("earliest", "latest", "expected"),
    [
        (None, None, EndpointKind.UNKNOWN),
        ("", "   ", EndpointKind.UNKNOWN),
        (None, "1840", EndpointKind.OPEN_LATEST),
        ("  ", "1840-06", EndpointKind.OPEN_LATEST),
        ("1840", None, EndpointKind.OPEN_EARLIEST),
        ("1840-06-15", "", EndpointKind.OPEN_EARLIEST),
        ("1840", "1840", EndpointKind.EXACT),
        ("1840-06-15", " 1840-06-15 ", EndpointKind.EXACT),
        ("1840", "1840-06", EndpointKind.WINDOW),
        ("1840", "1845", EndpointKind.WINDOW),
        ("1845", "1840", EndpointKind.WINDOW),
    ],
)
def test_classify_endpoint_follows_bound_presence_and_day_intervals(earliest, latest, expected):
    assert classify_endpoint(Endpoint(earliest=earliest, latest=latest)) is expected


@pytest.mark.parametrize("precision", ["day", "month", "year", "approximate", None, "nonsense"])
def test_classify_endpoint_ignores_precision(precision):
    endpoint = Endpoint(earliest="1840", latest="1840", precision=precision)
    assert classify_endpoint(endpoint) is EndpointKind.EXACT


def test_classify_endpoint_treats_a_malformed_present_bound_as_a_window():
    assert classify_endpoint(Endpoint(earliest="1840", latest="18xx")) is EndpointKind.WINDOW


def test_classify_endpoint_leaves_the_endpoint_unchanged():
    endpoint = Endpoint(earliest=" 1840 ", latest="1845", precision="year", note="n")
    before = replace(endpoint)
    classify_endpoint(endpoint)
    assert endpoint == before


# --- certain_core (Requirement 2.13) ---


def test_certain_core_runs_from_start_latest_last_day_to_end_earliest_first_day():
    fact = _fact(start=Endpoint(latest="1840-06"), end=Endpoint(earliest="1845"))
    assert certain_core(fact) == DaySpan(date(1840, 6, 30), date(1845, 1, 1))


def test_certain_core_of_a_single_shared_day_is_that_day():
    fact = _fact(start=Endpoint(latest="1840-06-15"), end=Endpoint(earliest="1840-06-15"))
    assert certain_core(fact) == DaySpan(date(1840, 6, 15), date(1840, 6, 15))


@pytest.mark.parametrize(
    ("start_latest", "end_earliest"),
    [
        (None, "1845"),
        ("1840", None),
        (None, None),
        ("   ", "1845"),
        ("18xx", "1845"),
        ("1845", "1840"),  # inverted: the core is empty
        ("1840-07", "1840-06"),
    ],
)
def test_certain_core_is_empty_when_a_bound_is_absent_or_the_interval_inverts(
    start_latest, end_earliest
):
    fact = _fact(start=Endpoint(latest=start_latest), end=Endpoint(earliest=end_earliest))
    assert certain_core(fact) is None


def test_certain_core_leaves_the_fact_unchanged():
    fact = _fact(
        start=Endpoint(earliest="1838", latest="1840"),
        end=Endpoint(earliest="1845", latest="1848"),
        observations=[_observation("1840", "1845")],
    )
    before = repr(fact)
    certain_core(fact)
    assert repr(fact) == before


# --- possible_span (Requirement 2.16) ---


def test_possible_span_runs_from_start_earliest_first_day_to_end_latest_last_day():
    fact = _fact(start=Endpoint(earliest="1838-05"), end=Endpoint(latest="1848"))
    assert possible_span(fact) == OpenSpan(date(1838, 5, 1), date(1848, 12, 31))


@pytest.mark.parametrize(
    ("start_earliest", "end_latest", "expected"),
    [
        (None, "1848", OpenSpan(None, date(1848, 12, 31))),
        ("1838", None, OpenSpan(date(1838, 1, 1), None)),
        (None, None, OpenSpan(None, None)),
        ("  ", "18xx", OpenSpan(None, None)),
    ],
)
def test_possible_span_is_unbounded_where_a_bound_is_absent(
    start_earliest, end_latest, expected
):
    fact = _fact(start=Endpoint(earliest=start_earliest), end=Endpoint(latest=end_latest))
    span = possible_span(fact)
    assert span == expected


def test_possible_span_unbounded_in_both_directions_is_reported_as_such():
    assert possible_span(_fact()).is_unbounded_both() is True


def test_possible_span_leaves_the_fact_unchanged():
    fact = _fact(start=Endpoint(earliest="1838"), end=Endpoint(latest="1848"))
    before = repr(fact)
    possible_span(fact)
    assert repr(fact) == before


# --- observation_span_years (Requirement 4.6) ---


@pytest.mark.parametrize(
    ("observed_from", "observed_to", "expected"),
    [
        ("1866", "1870", (1866, 1870)),
        ("1866", "", (1866, 1866)),
        ("", "1870", (1870, 1870)),
        (" 1866 ", " 1870 ", (1866, 1870)),
        ("", "", None),
        ("18xx", "", None),
        ("1866-06", "1870", (1870, 1870)),  # only ÅÅÅÅ is a year
        ("1870", "1866", (1870, 1866)),  # inverted, reported by the validator
    ],
)
def test_observation_span_years(observed_from, observed_to, expected):
    assert observation_span_years(_observation(observed_from, observed_to)) == expected


# --- coverage_union (Requirement 5.1) ---


def test_coverage_union_counts_each_year_once_across_overlapping_observations():
    fact = _fact(
        observations=[
            _observation("1866", "1870"),
            _observation("1866", "1870"),
            _observation("1869", "1872"),
            _observation("1873", "1873"),
        ]
    )
    assert coverage_union(fact) == set(range(1866, 1874))


def test_coverage_union_of_zero_observations_is_empty():
    assert coverage_union(_fact()) == set()


def test_coverage_union_skips_undated_and_inverted_observations():
    fact = _fact(
        observations=[
            _observation("", ""),
            _observation("1870", "1866"),
            _observation("1880", ""),
        ]
    )
    assert coverage_union(fact) == {1880}


def test_coverage_union_leaves_the_fact_unchanged():
    fact = _fact(observations=[_observation("1866", "1870")])
    before = repr(fact)
    coverage_union(fact)
    assert repr(fact) == before


# --- core_aggregate ---


def test_core_aggregate_is_the_lowest_from_and_the_highest_to():
    observations = [
        _observation("1871", "1875"),
        _observation("1866", "1870"),
        _observation("1876", "1880"),
    ]
    assert core_aggregate(observations) == ("1866", "1880")


def test_core_aggregate_ignores_absent_and_malformed_bounds():
    observations = [_observation("", "1870"), _observation("18xx", "1875"), _observation("1866", "")]
    assert core_aggregate(observations) == ("1866", "1875")


def test_core_aggregate_of_no_observations_is_two_absent_bounds():
    assert core_aggregate([]) == (None, None)


def test_core_aggregate_leaves_the_observations_unchanged():
    observations = [_observation(" 1866 ", "1870")]
    before = repr(observations)
    assert core_aggregate(observations) == ("1866", "1870")
    assert repr(observations) == before
