"""Timed performance budget tests for residence services.

Three time budgets are verified:
1. A check run over 10,000 Residence_Facts within 5 seconds (Requirement 5.9).
2. Inference for a person with 200 Residence_Facts within 1 second (Requirement 7.1).
3. A residents_of_place query over 50,000 facts / 20,000 persons / 5,000 places
   within 1 second (Requirement 8.11).

These tests generate synthetic projects at the required scale (year-precision bounds
only, no UI) and assert wall-clock time is within the budget.

Marked @pytest.mark.slow so they can be skipped in fast CI runs:
    pytest -m "not slow"
"""

from __future__ import annotations

import time

import pytest

from slaktbusken.model.event import SourceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.source import Source, StructuredReference
from slaktbusken.persistence.settings_io import PersonCheckConfig
from slaktbusken.services.person_check_engine import PersonCheckEngine
from slaktbusken.services.residence_inference import infer_bounds
from slaktbusken.services.residence_query import residents_of_place


# ---------------------------------------------------------------------------
# Helpers to generate synthetic projects
# ---------------------------------------------------------------------------


def _make_person(idx: int) -> Person:
    return Person(
        id=f"person_{idx}",
        sex="M" if idx % 2 == 0 else "F",
        names=[Name(type="birth", given=f"Given{idx}", surname=f"Surname{idx}")],
    )


def _make_place(idx: int, parent_id: str | None = None) -> Place:
    return Place(
        id=f"place_{idx}",
        type="farm",
        name=f"Gård {idx}",
        parent_place_id=parent_id,
    )


def _make_source(idx: int) -> Source:
    return Source(
        id=f"source_{idx}",
        provider="Arkiv Digital",
        source_type="church_book",
        title=f"AI:{idx}",
        structured_reference=StructuredReference(
            fields={"parish": "Ljusdal", "series": "AI", "years": f"{1800 + idx % 100}-{1805 + idx % 100}"}
        ),
    )


def _make_observation(source_idx: int, from_year: int, to_year: int) -> Observation:
    return Observation(
        source_ref=SourceRef(source_id=f"source_{source_idx}", quality="secondary"),
        observed_from=str(from_year),
        observed_to=str(to_year),
    )


def _make_residence_fact(
    idx: int,
    person_id: str,
    place_id: str,
    start_year: int,
    end_year: int,
    observations: list[Observation] | None = None,
) -> ResidenceFact:
    return ResidenceFact(
        id=f"residence_{idx}",
        person_id=person_id,
        place_id=place_id,
        start=Endpoint(earliest=str(start_year), latest=str(start_year)),
        end=Endpoint(earliest=str(end_year), latest=str(end_year)),
        observations=observations or [],
    )


# ---------------------------------------------------------------------------
# Test 1: Check engine run over 10,000 Residence_Facts within 5 seconds
# (Requirement 5.9)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_check_engine_10000_facts_within_5_seconds():
    """Person check engine completes a run over 10,000 Residence_Facts in ≤5s."""
    num_persons = 500
    facts_per_person = 20  # 500 * 20 = 10,000 facts
    num_places = 100
    num_sources = 200

    # Build persons
    persons = [_make_person(i) for i in range(num_persons)]
    # Build places
    places = [_make_place(i) for i in range(num_places)]
    # Build sources
    sources = [_make_source(i) for i in range(num_sources)]

    # Build 10,000 residence facts spread across persons
    residences: list[ResidenceFact] = []
    fact_idx = 0
    for person_idx in range(num_persons):
        person_id = f"person_{person_idx}"
        for j in range(facts_per_person):
            place_id = f"place_{(person_idx + j) % num_places}"
            start_year = 1800 + j * 5
            end_year = start_year + 4
            source_idx = (person_idx + j) % num_sources
            obs = _make_observation(source_idx, start_year, end_year)
            fact = _make_residence_fact(
                fact_idx, person_id, place_id, start_year, end_year, [obs]
            )
            residences.append(fact)
            fact_idx += 1

    data = ProjectData(
        project=ProjectMetadata(title="Perf test 10k"),
        persons=persons,
        places=places,
        sources=sources,
        residences=residences,
    )

    config = PersonCheckConfig()

    t0 = time.perf_counter()
    engine = PersonCheckEngine(data, config)
    engine.run_checks()
    elapsed = time.perf_counter() - t0

    assert elapsed <= 5.0, (
        f"Check engine took {elapsed:.2f}s for 10,000 facts; budget is 5s"
    )


# ---------------------------------------------------------------------------
# Test 2: Inference for a person with 200 Residence_Facts within 1 second
# (Requirement 7.1)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_inference_200_facts_within_1_second():
    """infer_bounds completes within 1s for a person having 200 Residence_Facts."""
    num_facts = 200
    target_person = "person_0"
    num_places = 50

    persons = [_make_person(0)]
    places = [_make_place(i) for i in range(num_places)]
    sources = [_make_source(i) for i in range(num_facts)]

    # Build 200 facts for a single person at various places,
    # each with year-precision bounds and one observation.
    # Leave some bounds absent to trigger inference candidates.
    residences: list[ResidenceFact] = []
    for i in range(num_facts):
        place_id = f"place_{i % num_places}"
        start_year = 1700 + i * 2
        end_year = start_year + 1
        obs = _make_observation(i, start_year, end_year)

        # Every 5th fact has absent start.earliest to trigger inference
        start_earliest = None if i % 5 == 0 else str(start_year)
        # Every 7th fact has absent end.latest to trigger inference
        end_latest = None if i % 7 == 0 else str(end_year)

        fact = ResidenceFact(
            id=f"residence_{i}",
            person_id=target_person,
            place_id=place_id,
            start=Endpoint(earliest=start_earliest, latest=str(start_year)),
            end=Endpoint(earliest=str(end_year), latest=end_latest),
            observations=[obs],
        )
        residences.append(fact)

    data = ProjectData(
        project=ProjectMetadata(title="Perf test inference"),
        persons=persons,
        places=places,
        sources=sources,
        residences=residences,
    )

    # Time inference for a single fact (with many neighbours to scan)
    # Run inference for every fact that needs it and check total time.
    t0 = time.perf_counter()
    for fact in residences:
        if fact.start.earliest is None or fact.end.latest is None:
            infer_bounds(fact, data)
    elapsed = time.perf_counter() - t0

    assert elapsed <= 1.0, (
        f"Inference over 200 facts took {elapsed:.2f}s; budget is 1s"
    )


# ---------------------------------------------------------------------------
# Test 3: residents_of_place on 50,000 facts within 1 second
# (Requirement 8.11)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_residents_query_50000_facts_within_1_second():
    """residents_of_place returns within 1s on a 50k-fact / 20k-person / 5k-place project."""
    num_persons = 20_000
    num_places = 5_000
    num_facts = 50_000

    # Build persons
    persons = [_make_person(i) for i in range(num_persons)]
    # Build places in a flat hierarchy (no children for max stress on index build)
    places = [_make_place(i) for i in range(num_places)]
    # No sources needed for the query itself
    sources: list[Source] = []

    # Build 50,000 residence facts distributed across persons and places.
    # Use year-precision bounds covering a realistic span around 1850.
    residences: list[ResidenceFact] = []
    for i in range(num_facts):
        person_id = f"person_{i % num_persons}"
        place_id = f"place_{i % num_places}"
        start_year = 1800 + (i % 100)
        end_year = start_year + 5
        fact = _make_residence_fact(i, person_id, place_id, start_year, end_year)
        residences.append(fact)

    data = ProjectData(
        project=ProjectMetadata(title="Perf test query 50k"),
        persons=persons,
        places=places,
        sources=sources,
        residences=residences,
    )

    # Query for a place that has many matching facts at the target year
    target_place = "place_0"  # ~50000/5000 = 10 facts at this place
    target_year = 1850

    t0 = time.perf_counter()
    residents_of_place(data, target_place, target_year)
    elapsed = time.perf_counter() - t0

    assert elapsed <= 1.0, (
        f"residents_of_place took {elapsed:.2f}s for 50k facts; budget is 1s"
    )
