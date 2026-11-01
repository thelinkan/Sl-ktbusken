"""Property 46: Benchmark data is deterministic.

Generating the benchmark project twice with the same arguments gives identical
serialised output, and the generated project contains the stated structures
(generations, multiple partnerships, shared ancestors, all four parentage types,
the stated candidate mix).

**Validates: Requirements 32.9**
"""

from __future__ import annotations

from collections import Counter

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.benchmarks.synthetic_project import (
    DEFAULT_CANDIDATES,
    DEFAULT_PERSONS,
    DEFAULT_SEED,
    couples_sharing_ancestors,
    generate_project,
    project_sha256,
    serialise_project,
)


@settings(settings.get_profile("sbk"), max_examples=15, deadline=None)
@given(
    seed=st.integers(min_value=0, max_value=2**31 - 1),
    persons=st.integers(min_value=100, max_value=400),
    candidates=st.integers(min_value=0, max_value=30),
)
def test_same_arguments_give_identical_serialised_output(seed, persons, candidates):
    first = generate_project(seed, persons, candidates)
    second = generate_project(seed, persons, candidates)
    assert serialise_project(first) == serialise_project(second)
    assert project_sha256(first) == project_sha256(second)
    assert len(first.persons) == persons
    assert len(first.merge_candidates) <= candidates


def test_different_seeds_give_different_output():
    a = generate_project(1, 300, 20)
    b = generate_project(2, 300, 20)
    assert project_sha256(a) != project_sha256(b)


def test_full_scale_runs_have_equal_digests_and_stated_structures():
    first = generate_project()
    second = generate_project(DEFAULT_SEED, DEFAULT_PERSONS, DEFAULT_CANDIDATES)
    assert project_sha256(first) == project_sha256(second)

    assert len(first.persons) == DEFAULT_PERSONS
    assert len(first.merge_candidates) == DEFAULT_CANDIDATES

    # Multiple partnerships: some person is a partner in more than one family.
    partner_families = Counter()
    for family in first.families:
        for partner in family.partners:
            if family.event_ids and len(family.partners) == 2:
                partner_families[partner.person_id] += 1
    assert any(n > 1 for n in partner_families.values())

    # Shared ancestors (pedigree collapse).
    assert couples_sharing_ancestors(first) > 0

    # All four parentage types.
    kinds = {
        link.parentage_type
        for family in first.families
        for link in family.parent_child_links
    }
    assert {"biological", "adoptive", "foster", "step"} <= kinds

    # Generations: birth years span several generations.
    years = [
        int(e.date.value[:4])
        for e in first.events
        if e.type == "birth" and e.date is not None
    ]
    assert max(years) - min(years) >= 100

    # Candidate mix.
    total = len(first.merge_candidates)
    disabled = sum(1 for c in first.merge_candidates if not c.enabled)
    enabled = [c for c in first.merge_candidates if c.enabled]
    mix = Counter(c.assessment for c in enabled)
    assert abs(disabled / total - 0.08) < 0.02
    assert abs(mix["confirmed"] / total - 0.10) < 0.02
    assert abs(mix["rejected"] / total - 0.12) < 0.02
    assert (mix["unreviewed"] + mix["possible"]) / total > 0.65
