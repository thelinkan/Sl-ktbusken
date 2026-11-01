"""Self-test of the deterministic synthetic benchmark generator (Requirement 32.9)."""

from __future__ import annotations

import copy
from collections import Counter

import pytest

from slaktbusken.model.merge_candidate import pair_key
from slaktbusken.model.project import ProjectData
from slaktbusken.services.foster_sync import sync_parentage_links
from tests.benchmarks.synthetic_project import (
    DEFAULT_CANDIDATES,
    DEFAULT_PERSONS,
    couples_sharing_ancestors,
    generate_project,
    project_sha256,
    serialise_project,
)


@pytest.fixture(scope="module")
def full_project() -> ProjectData:
    return generate_project()


def _all_ids(project: ProjectData) -> list[str]:
    ids: list[str] = []
    for name in (
        "persons", "families", "events", "residences", "places", "sources", "media",
        "dna_companies", "dna_profiles", "dna_matches", "research_cases",
        "merge_candidates", "merge_history",
    ):
        ids.extend(item.id for item in getattr(project, name))
    ids.extend(c.id for candidate in project.merge_candidates for c in candidate.comments)
    return ids


def _assert_references_exist(project: ProjectData) -> None:
    persons = {p.id for p in project.persons}
    places = {p.id for p in project.places}
    events = {e.id for e in project.events}
    cases = {c.id for c in project.research_cases}
    for family in project.families:
        assert all(p.person_id in persons for p in family.partners)
        assert all(c in persons for c in family.children)
        assert all(e in events for e in family.event_ids)
        for link in family.parent_child_links:
            assert link.child_id in family.children
            assert link.parent_id in persons
    for event in project.events:
        assert all(p.person_id in persons for p in event.participants)
        for ref in (event.place, event.from_place):
            assert ref is None or ref.place_id in places
    for place in project.places:
        assert place.parent_place_id is None or place.parent_place_id in places
    for fact in project.residences:
        assert fact.person_id in persons and fact.place_id in places
    for candidate in project.merge_candidates:
        assert candidate.person_1_id in persons
        assert candidate.person_2_id in persons
        assert candidate.research_case_id is None or candidate.research_case_id in cases
    for entry in project.merge_history:
        assert entry.surviving_person_id in persons
        assert entry.merged_person_id not in persons


def test_same_seed_gives_identical_output_and_other_seed_differs() -> None:
    first = generate_project(seed=7, persons=1500, candidates=150)
    second = generate_project(seed=7, persons=1500, candidates=150)
    other = generate_project(seed=8, persons=1500, candidates=150)
    assert serialise_project(first) == serialise_project(second)
    assert project_sha256(first) == project_sha256(second)
    assert project_sha256(first) != project_sha256(other)


def test_default_scale(full_project: ProjectData) -> None:
    assert len(full_project.persons) == DEFAULT_PERSONS
    assert len(full_project.merge_candidates) == DEFAULT_CANDIDATES
    assert len(full_project.research_cases) == 200


def test_ids_are_unique_and_references_resolve(full_project: ProjectData) -> None:
    ids = _all_ids(full_project)
    assert len(ids) == len(set(ids))
    _assert_references_exist(full_project)


def test_ancestry_has_no_cycles(full_project: ProjectData) -> None:
    parents: dict[str, set[str]] = {p.id: set() for p in full_project.persons}
    for family in full_project.families:
        for link in family.parent_child_links:
            parents[link.child_id].add(link.parent_id)
    children_left = {pid: len(ps) for pid, ps in parents.items()}
    kids: dict[str, list[str]] = {}
    for child, ps in parents.items():
        for parent in ps:
            kids.setdefault(parent, []).append(child)
    # Kahn's algorithm from the persons that have no parents: every person must
    # be reached, which is only possible when the parent graph is acyclic.
    ready = [pid for pid, left in children_left.items() if left == 0]
    reached = 0
    depth = {pid: 0 for pid in ready}
    while ready:
        pid = ready.pop()
        reached += 1
        for child in kids.get(pid, ()):
            depth[child] = max(depth.get(child, 0), depth[pid] + 1)
            children_left[child] -= 1
            if children_left[child] == 0:
                ready.append(child)
    assert reached == len(parents)
    assert max(depth.values()) >= 3  # several generations (founders at depth 0)


def test_family_structures_are_present(full_project: ProjectData) -> None:
    parentage = Counter(
        link.parentage_type
        for family in full_project.families
        for link in family.parent_child_links
    )
    assert set(parentage) == {"biological", "adoptive", "foster", "step"}
    assert parentage["biological"] > 0.85 * sum(parentage.values())

    partnerships: Counter[str] = Counter()
    for family in full_project.families:
        if len(family.partners) == 2 and family.event_ids:
            for partner in family.partners:
                partnerships[partner.person_id] += 1
    assert sum(1 for n in partnerships.values() if n >= 2) > 500
    assert couples_sharing_ancestors(full_project) > 0

    event_types = {e.type for e in full_project.events}
    assert {"birth", "death", "baptism", "burial", "marriage", "flytt",
            "adoption", "foster_home", "foster_home_ended"} <= event_types
    assert full_project.residences and full_project.media
    assert full_project.dna_profiles and full_project.merge_history
    assert any(len(p.names) > 1 for p in full_project.persons)


def test_candidate_mix_and_pairs(full_project: ProjectData) -> None:
    candidates = full_project.merge_candidates
    keys = [pair_key(c.person_1_id, c.person_2_id) for c in candidates]
    assert len(keys) == len(set(keys))
    assert all(c.person_1_id != c.person_2_id for c in candidates)

    n = len(candidates)
    enabled = [c for c in candidates if c.enabled]
    assert abs((n - len(enabled)) - 0.08 * n) <= 2
    by_assessment = Counter(c.assessment for c in enabled)
    assert abs(by_assessment["confirmed"] - 0.10 * n) <= 2
    assert abs(by_assessment["rejected"] - 0.12 * n) <= 2
    assert sum(1 for c in candidates if c.research_case_id) == 150
    assert max(len(c.comments) for c in candidates) <= 6

    appearances = Counter(p for c in candidates for p in (c.person_1_id, c.person_2_id))
    assert max(appearances.values()) <= 5
    assert sum(1 for v in appearances.values() if v >= 2) > 0


def test_scale_parameter() -> None:
    project = generate_project(persons=600, candidates=40)
    assert len(project.persons) == 600
    assert len(project.merge_candidates) == 40
    ids = _all_ids(project)
    assert len(ids) == len(set(ids))
    _assert_references_exist(project)

    tiny = generate_project(persons=10, candidates=0)
    assert len(tiny.persons) == 10
    assert tiny.merge_candidates == []

    with pytest.raises(ValueError):
        generate_project(persons=3)


def test_placement_families_match_what_sync_derives() -> None:
    project = generate_project(persons=1500, candidates=0)
    before = {
        (link.child_id, link.parent_id, link.parentage_type)
        for family in project.families
        for link in family.parent_child_links
    }
    synced = copy.deepcopy(project)
    sync_parentage_links(synced)
    after = {
        (link.child_id, link.parent_id, link.parentage_type)
        for family in synced.families
        for link in family.parent_child_links
    }
    assert after == before
    assert len(synced.families) == len(project.families)
