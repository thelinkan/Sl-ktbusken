"""Property 16: Shared persons and candidate relations depend on ids only.

A Shared_Person marker is produced exactly for ids present in both visible
sets; a candidate relation is shown between two different ids exactly when a
candidate exists for that unordered pair. Names, dates, sex, places and family
position never matter.

**Validates: Requirements 12.1, 12.3, 12.5, 12.6, 12.7, 33.3**
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from slaktbusken.model.merge_candidate import MergeCandidate
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.candidate_index import CandidateIndex
from slaktbusken.services.comparison_session import ComparisonSession

_IDS = [f"P{i}" for i in range(8)]
_id = st.sampled_from(_IDS)
_id_sets = st.lists(_id, max_size=8)
_pairs = st.lists(st.tuples(_id, _id), max_size=10)


def _data(pairs, name: str, sex: str) -> ProjectData:
    data = ProjectData()
    data.persons = [
        Person(id=i, sex=sex, names=[Name(type="birth", given=name, surname=name)])
        for i in _IDS
    ]
    for n, (a, b) in enumerate(pairs):
        data.merge_candidates.append(
            MergeCandidate(id=f"c{n}", person_1_id=a, person_2_id=b)
        )
    return data


@given(_id_sets, _id_sets)
def test_shared_only_for_identical_ids(left, right):
    shared = ComparisonSession.shared_person_ids(left, right)
    assert shared == {i for i in set(left) if i in set(right)}
    assert shared == ComparisonSession.shared_person_ids(right, left)


@given(st.lists(_id, min_size=2, max_size=8, unique=True))
def test_same_named_siblings_with_different_ids_not_shared(ids):
    # Persons with identical names/sex in both views, but disjoint ids.
    half = len(ids) // 2
    assert ComparisonSession.shared_person_ids(ids[:half], ids[half:]) == set()


@given(_pairs, _id, _id, st.sampled_from(["Anna", "Anna", "Bo"]), st.sampled_from(["F", "M"]))
def test_candidate_relation_depends_on_unordered_ids_only(pairs, a, b, name, sex):
    index = CandidateIndex.build(_data(pairs, name, sex))
    other = CandidateIndex.build(_data(pairs, "Zed", "U"))
    rel = ComparisonSession.candidate_relation(a, b, index)
    assert rel is not None or a == b or all(
        {a, b} != {x, y} for x, y in pairs
    )
    expected = None
    if a != b:
        expected = next(
            (f"c{n}" for n, (x, y) in enumerate(pairs) if {x, y} == {a, b}), None
        )
    assert (rel.id if rel else None) == expected
    rev = ComparisonSession.candidate_relation(b, a, index)
    assert (rev.id if rev else None) == expected
    alt = ComparisonSession.candidate_relation(a, b, other)
    assert (alt.id if alt else None) == expected


@given(_pairs, _id)
def test_no_relation_for_same_id_or_empty_slot(pairs, a):
    index = CandidateIndex.build(_data(pairs, "Anna", "F"))
    assert ComparisonSession.candidate_relation(a, a, index) is None
    assert ComparisonSession.candidate_relation(a, None, index) is None
    assert ComparisonSession.candidate_relation(None, a, index) is None
    assert ComparisonSession.candidate_relation(None, None, index) is None


@given(_id, _id)
def test_equal_persons_without_candidate_have_no_relation(a, b):
    # Identical names and sex but no candidate: nothing is inferred.
    index = CandidateIndex.build(_data([], "Anna", "F"))
    assert ComparisonSession.candidate_relation(a, b, index) is None
