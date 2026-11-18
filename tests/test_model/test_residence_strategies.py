"""Smoke tests for the shared residence Hypothesis strategies.

These assert that the strategy module draws well-formed values and that every
edge case the design asks for is actually reachable: whitespace-only bounds, the
100/1000/5000-character length boundaries, 100 Observations, inverted bounds,
empty cores, unbounded spans, one-sided Observation spans, years outside
1500-2100, and circular place parents.

Covers Requirements 2.1, 4.1, 10.1 (the input space the residence property tests
draw from).
"""

from hypothesis import find, given, settings
from hypothesis import strategies as st

from slaktbusken.model.date_span import expand_iso
from slaktbusken.model.place import Place
from slaktbusken.model.residence import (
    Endpoint,
    EndpointKind,
    Observation,
    ResidenceFact,
    certain_core,
    classify_endpoint,
    observation_span_years,
    possible_span,
)
from tests.test_model.residence_strategies import (
    FACT_NOTES_MAX_LENGTH,
    MANY_OBSERVATIONS,
    MAX_PLAUSIBLE_YEAR,
    MIN_PLAUSIBLE_YEAR,
    NOTE_MAX_LENGTH,
    ROLE_MAX_LENGTH,
    consistent_projects,
    endpoints,
    iso_values,
    observations,
    residence_facts,
)


_SEARCH = settings(max_examples=500, deadline=None)
_DRAW = settings(max_examples=50, deadline=None)


# --- iso_values ---


@given(iso_values())
@_DRAW
def test_iso_values_draws_absent_or_string_values(value):
    assert value is None or isinstance(value, str)


def test_iso_values_reaches_whitespace_only_bounds():
    # Requirement 2.1: a whitespace-only bound counts as absent.
    value = find(
        iso_values(),
        lambda v: v is not None and v != "" and v.strip() == "",
        settings=_SEARCH,
    )
    assert expand_iso(value) is None


def test_iso_values_reaches_every_precision():
    for expected, predicate in (
        ("year", lambda v: isinstance(v, str) and len(v.strip()) == 4),
        ("month", lambda v: isinstance(v, str) and len(v.strip()) == 7),
        ("day", lambda v: isinstance(v, str) and len(v.strip()) == 10),
    ):
        value = find(
            iso_values(include_absent=False, include_malformed=False),
            predicate,
            settings=_SEARCH,
        )
        assert expand_iso(value) is not None, expected


def test_iso_values_can_exclude_absent_and_malformed():
    strategy = iso_values(include_absent=False, include_malformed=False)

    @given(strategy)
    @_DRAW
    def check(value):
        assert expand_iso(value) is not None

    check()


# --- endpoints ---


@given(endpoints())
@_DRAW
def test_endpoints_are_endpoints_with_a_classification(endpoint):
    assert isinstance(endpoint, Endpoint)
    assert isinstance(classify_endpoint(endpoint), EndpointKind)
    if endpoint.note is not None:
        assert len(endpoint.note) <= NOTE_MAX_LENGTH + 1


@given(st.data())
@_DRAW
def test_endpoints_honour_the_requested_kind(data):
    kind = data.draw(st.sampled_from(list(EndpointKind)))
    endpoint = data.draw(endpoints(kind=kind))
    assert classify_endpoint(endpoint) is kind


def test_endpoints_reach_inverted_bounds():
    endpoint = find(
        endpoints(shape="inverted_window"),
        lambda ep: expand_iso(ep.earliest).first > expand_iso(ep.latest).last,
        settings=_SEARCH,
    )
    assert classify_endpoint(endpoint) is EndpointKind.WINDOW


def test_endpoints_reach_the_note_length_boundary():
    endpoint = find(
        endpoints(),
        lambda ep: ep.note is not None and len(ep.note) == NOTE_MAX_LENGTH,
        settings=_SEARCH,
    )
    assert len(endpoint.note) == NOTE_MAX_LENGTH


# --- observations ---


@given(observations())
@_DRAW
def test_observations_have_string_bounds(observation):
    assert isinstance(observation, Observation)
    assert isinstance(observation.observed_from, str)
    assert isinstance(observation.observed_to, str)
    assert isinstance(observation.page_note, str)


def test_observations_reach_one_sided_spans():
    only_from = find(
        observations(shape="one_sided_from"),
        lambda obs: not obs.observed_to.strip(),
        settings=_SEARCH,
    )
    span = observation_span_years(only_from)
    assert span is not None and span[0] == span[1]

    only_to = find(
        observations(shape="one_sided_to"),
        lambda obs: not obs.observed_from.strip(),
        settings=_SEARCH,
    )
    span = observation_span_years(only_to)
    assert span is not None and span[0] == span[1]


def test_observations_reach_years_outside_the_plausible_range():
    observation = find(
        observations(shape="out_of_range"),
        lambda obs: obs.observed_from.isdigit()
        and not (MIN_PLAUSIBLE_YEAR <= int(obs.observed_from) <= MAX_PLAUSIBLE_YEAR),
        settings=_SEARCH,
    )
    assert len(observation.observed_from) == 4


def test_observations_reach_inverted_spans():
    observation = find(
        observations(shape="inverted"),
        lambda obs: obs.observed_from > obs.observed_to,
        settings=_SEARCH,
    )
    span = observation_span_years(observation)
    assert span is not None and span[0] > span[1]


# --- residence_facts ---


@given(residence_facts(include_many_observations=False))
@_DRAW
def test_residence_facts_are_well_formed(fact):
    assert isinstance(fact, ResidenceFact)
    assert fact.id.startswith("residence_")
    assert isinstance(fact.person_id, str)
    assert isinstance(fact.place_id, str)
    assert all(isinstance(obs, Observation) for obs in fact.observations)
    assert len(fact.role_in_household) <= ROLE_MAX_LENGTH + 1
    assert len(fact.notes) <= FACT_NOTES_MAX_LENGTH + 1


@given(residence_facts(shape="ordered", observation_count=0))
@_DRAW
def test_ordered_shape_has_a_non_empty_core(fact):
    assert certain_core(fact) is not None


@given(residence_facts(shape="empty_core", observation_count=0))
@_DRAW
def test_empty_core_shape_has_no_core(fact):
    assert certain_core(fact) is None


@given(residence_facts(shape="unbounded", observation_count=0))
@_DRAW
def test_unbounded_shape_spans_everything(fact):
    assert possible_span(fact).is_unbounded_both() is True


@given(residence_facts(observation_count=MANY_OBSERVATIONS, include_blank_references=False))
@settings(max_examples=5, deadline=None)
def test_facts_can_carry_a_hundred_observations(fact):
    assert len(fact.observations) == MANY_OBSERVATIONS


def test_residence_facts_reach_the_role_length_boundary():
    fact = find(
        residence_facts(include_many_observations=False, observation_count=0),
        lambda f: len(f.role_in_household) == ROLE_MAX_LENGTH,
        settings=_SEARCH,
    )
    assert len(fact.role_in_household) == ROLE_MAX_LENGTH


def test_residence_facts_reach_the_notes_length_boundary():
    fact = find(
        residence_facts(include_many_observations=False, observation_count=0),
        lambda f: len(f.notes) == FACT_NOTES_MAX_LENGTH,
        settings=_SEARCH,
    )
    assert len(fact.notes) == FACT_NOTES_MAX_LENGTH


def test_residence_facts_reach_blank_references():
    fact = find(
        residence_facts(observation_count=0),
        lambda f: not f.person_id.strip() or not f.place_id.strip(),
        settings=_SEARCH,
    )
    assert not fact.person_id.strip() or not fact.place_id.strip()


# --- consistent_projects ---


@given(consistent_projects(min_residences=1))
@_DRAW
def test_consistent_projects_resolve_every_residence_reference(data):
    person_ids = {person.id for person in data.persons}
    place_ids = {place.id for place in data.places}
    source_ids = {source.id for source in data.sources}
    event_ids = {event.id for event in data.events}

    assert data.residences  # min_residences=1
    for fact in data.residences:
        assert fact.person_id in person_ids
        assert fact.place_id in place_ids
        for endpoint in (fact.start, fact.end):
            assert endpoint.event_id is None or endpoint.event_id in event_ids
        for observation in fact.observations:
            assert observation.source_ref.source_id in source_ids


@given(consistent_projects())
@_DRAW
def test_consistent_projects_place_parents_stay_inside_the_project(data):
    place_ids = {place.id for place in data.places}
    for place in data.places:
        assert isinstance(place, Place)
        assert place.parent_place_id is None or place.parent_place_id in place_ids


def _has_place_cycle(data) -> bool:
    by_id = {place.id: place for place in data.places}
    for place in data.places:
        seen = set()
        current = place.id
        while current is not None and current not in seen:
            seen.add(current)
            current = by_id[current].parent_place_id if current in by_id else None
        if current is not None:
            return True
    return False


def test_consistent_projects_reach_circular_place_parents():
    data = find(consistent_projects(min_places=2), _has_place_cycle, settings=_SEARCH)
    assert _has_place_cycle(data) is True
