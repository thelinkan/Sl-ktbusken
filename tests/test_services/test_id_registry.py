"""Property 3 (candidate, comment and history id prefixes): ids are never reissued.

The retired-person part of Property 3 lives in test_retired_ids.py.
"""

from __future__ import annotations

import re

from hypothesis import given, strategies as st

from slaktbusken.model.merge_candidate import (
    MergeCandidate,
    MergeCandidateComment,
    MergeHistoryEntry,
)
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.serialization import deserialize, serialize
from slaktbusken.services.id_registry import (
    ProtectedIdGenerator,
    live_protected_ids,
    protected_id_prefix,
)

_TYPES = ("merge_candidate", "merge_candidate_comment", "merge_history")
_PREFIXES = {
    "merge_candidate": "mergecand_",
    "merge_candidate_comment": "mergecomment_",
    "merge_history": "merge_",
}

_op = st.one_of(
    st.tuples(st.just("create"), st.sampled_from(_TYPES)),
    st.tuples(st.just("delete"), st.sampled_from(_TYPES), st.integers(0, 50)),
    st.tuples(st.just("reopen"), st.booleans()),
)


def _suffix(value: str, prefix: str) -> int | None:
    match = re.fullmatch(re.escape(prefix) + r"(\d+)", value)
    return int(match.group(1)) if match else None


def _add(data: ProjectData, entity_type: str, new_id: str) -> None:
    if entity_type == "merge_candidate":
        data.merge_candidates.append(MergeCandidate(new_id, "person_1", "person_2"))
    elif entity_type == "merge_candidate_comment":
        if not data.merge_candidates:
            data.merge_candidates.append(
                MergeCandidate("mergecand_0", "person_1", "person_2")
            )
        data.merge_candidates[0].comments.append(
            MergeCandidateComment(new_id, "2024-01-01", "x")
        )
    else:
        data.merge_history.append(
            MergeHistoryEntry(new_id, "person_1", "person_2", "n", "", "2024-01-01")
        )


def _delete(data: ProjectData, entity_type: str, index: int) -> None:
    if entity_type == "merge_candidate" and data.merge_candidates:
        data.merge_candidates.pop(index % len(data.merge_candidates))
    elif entity_type == "merge_candidate_comment":
        holders = [c for c in data.merge_candidates if c.comments]
        if holders:
            holder = holders[index % len(holders)]
            holder.comments.pop(index % len(holder.comments))
    elif entity_type == "merge_history" and data.merge_history:
        data.merge_history.pop(index % len(data.merge_history))


@given(ops=st.lists(_op, max_size=40), add_to_project=st.booleans())
def test_property_3_protected_prefix_ids_never_reissued(
    ops: list, add_to_project: bool
) -> None:
    """**Validates: Requirements 1.4, 22.2, 22.6, 22.13, 22.14, 27.4, 28.2, 29.12, 30.12**"""
    data = ProjectData()
    generator = ProtectedIdGenerator(data)
    highest: dict[str, int] = {t: 0 for t in _TYPES}

    for op in ops:
        if op[0] == "create":
            entity_type = op[1]
            prefix = _PREFIXES[entity_type]
            new_id = generator.generate(entity_type)
            number = _suffix(new_id, prefix)
            assert number is not None
            assert number > highest[entity_type]
            assert new_id not in live_protected_ids(data)[prefix]
            highest[entity_type] = number
            if add_to_project:
                _add(data, entity_type, new_id)
        elif op[0] == "delete":
            _delete(data, op[1], op[2])
        else:
            if op[1]:
                data = deserialize(serialize(data))
            generator = ProtectedIdGenerator(data)


@given(
    entity_type=st.sampled_from(_TYPES),
    suffixes=st.lists(st.integers(1, 500), min_size=1, max_size=8, unique=True),
)
def test_highest_deleted_id_not_reissued_after_reopen(
    entity_type: str, suffixes: list[int]
) -> None:
    """**Validates: Requirements 1.4, 22.2, 28.2**"""
    data = ProjectData()
    generator = ProtectedIdGenerator(data)
    prefix = protected_id_prefix(entity_type)
    top = 0
    for number in suffixes:
        top = max(top, number)
        data.id_high_water_marks[prefix] = top
    assert top > 0
    reopened = ProtectedIdGenerator(deserialize(serialize(data)))
    assert _suffix(reopened.generate(entity_type), prefix) > top
    assert generator is not None
