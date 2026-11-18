"""Property tests for merge candidate service.

Property 6: Unordered pair identity and uniqueness.
"""

from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.merge_candidate import pair_key
from slaktbusken.services import merge_candidate_service as svc

pytestmark = pytest.mark.mandatory_integrity


def _project(n: int) -> ProjectData:
    persons = [
        Person(id=f"p{i}", sex="U", names=[Name(type="birth", given="G", surname="S")])
        for i in range(n)
    ]
    return ProjectData(project=ProjectMetadata(title="T"), persons=persons)


@st.composite
def _scenarios(draw):
    n = draw(st.integers(min_value=2, max_value=6))
    ids = [f"p{i}" for i in range(n)]
    ops = draw(
        st.lists(
            st.tuples(
                st.sampled_from(ids),
                st.sampled_from(ids),
                st.booleans(),  # disable the candidate after the call
            ).filter(lambda t: t[0] != t[1]),
            min_size=1,
            max_size=25,
        )
    )
    return n, ops


class TestProperty6UnorderedPairIdentity:
    """**Validates: Requirements 2.9, 5.5, 5.6, 5.7**"""

    @given(_scenarios())
    def test_unordered_pair_identity_and_uniqueness(self, scenario) -> None:
        n, ops = scenario
        data = _project(n)
        seen: dict = {}
        for a, b, disable in ops:
            key = pair_key(a, b)
            before = len(data.merge_candidates)
            cand, created = svc.get_or_create_candidate(data, a, b)
            if key in seen:
                assert not created
                assert cand is seen[key]
                assert len(data.merge_candidates) == before
                # Reverse order returns the same stored object.
                again, created2 = svc.get_or_create_candidate(data, b, a)
                assert again is cand and not created2
            else:
                assert created
                assert len(data.merge_candidates) == before + 1
                seen[key] = cand
            snapshot = (cand.id, cand.person_1_id, cand.person_2_id, cand.enabled)
            if disable:
                svc.set_enabled(data, cand.id, False)
                seen[key] = svc.find_candidate_by_pair(data, b, a)
                snapshot = (cand.id, cand.person_1_id, cand.person_2_id, False)
            stored = svc.find_candidate_by_pair(data, a, b)
            assert (stored.id, stored.person_1_id, stored.person_2_id, stored.enabled) == snapshot

        keys = [pair_key(c.person_1_id, c.person_2_id) for c in data.merge_candidates]
        assert len(keys) == len(set(keys)) == len(seen)
        assert len({c.id for c in data.merge_candidates}) == len(data.merge_candidates)

    @given(st.integers(min_value=2, max_value=7))
    def test_person_in_many_pairs(self, n: int) -> None:
        data = _project(n)
        for i in range(1, n):
            svc.get_or_create_candidate(data, "p0", f"p{i}")
        assert len(data.merge_candidates) == n - 1
        assert all(
            "p0" in (c.person_1_id, c.person_2_id) for c in data.merge_candidates
        )
