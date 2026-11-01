"""Property 13: Slot operations.

**Validates: Requirements 9.6, 9.10, 9.12, 20.2, 20.3**
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from slaktbusken.model.merge_candidate import MergeCandidate
from slaktbusken.model.project import ProjectData
from slaktbusken.services.candidate_index import CandidateIndex
from slaktbusken.services.comparison_session import (
    SELF_COMPARE_MESSAGE,
    ComparisonSession,
)

_IDS = ["P0", "P1", "P2", "P3"]
_SLOT = st.one_of(st.none(), st.sampled_from(_IDS))


@st.composite
def sessions(draw):
    """A session with arbitrary (never equal) slot contents and view state."""
    left, right = draw(_SLOT), draw(_SLOT)
    session = ComparisonSession.from_pair(left, right)
    for view in (0, 1):
        session.set_focus(view, draw(_SLOT))
        session.set_expansion(view, draw(st.sets(st.sampled_from(_IDS))))
        session.set_zoom(view, draw(st.sampled_from([0.5, 1.0, 2.0])))
        session.select(view, draw(_SLOT))
    return session


def _index(pairs) -> CandidateIndex:
    data = ProjectData()
    for i, (a, b) in enumerate(pairs):
        data.merge_candidates.append(
            MergeCandidate(id=f"c{i}", person_1_id=a, person_2_id=b)
        )
    return CandidateIndex.build(data)


@given(sessions())
def test_swap_twice_restores_slots_and_swap_exchanges_contents(session):
    original = session.slot_persons()
    session.swap()
    assert session.slot_persons() == (original[1], original[0])
    assert session.focus(0) == original[1]
    assert session.focus(1) == original[0]
    session.swap()
    assert session.slot_persons() == original


def test_swap_with_empty_slot():
    session = ComparisonSession.from_pair("P0", None)
    session.swap()
    assert session.slot_persons() == (None, "P0")
    assert session.focus(0) is None
    assert session.focus(1) == "P0"


@given(sessions(), st.sampled_from([0, 1]))
def test_set_slot_rejects_other_slots_person_and_keeps_content(session, slot):
    other = session.slot_persons()[1 - slot]
    if other is None:
        return
    before_slots = session.slot_persons()
    before_ctx = session.context()
    result = session.set_slot(slot, other)
    assert result.ok is False
    assert result.message == SELF_COMPARE_MESSAGE
    assert session.slot_persons() == before_slots
    assert session.context() == before_ctx


@given(sessions(), st.sampled_from([0, 1]), _SLOT)
def test_replacing_a_person_resets_only_that_view(session, slot, new_id):
    if new_id is not None and new_id == session.slot_persons()[1 - slot]:
        return
    other = 1 - slot
    other_state = (
        session.focus(other),
        session.expansion(other),
        session.zoom(other),
        session.selection(other),
    )
    other_slot = session.slot_persons()[other]
    assert session.set_slot(slot, new_id).ok
    assert session.slot_persons()[slot] == new_id
    assert session.slot_persons()[other] == other_slot
    assert session.focus(slot) == new_id
    assert session.expansion(slot) == frozenset()
    assert session.selection(slot) is None
    assert (
        session.focus(other),
        session.expansion(other),
        session.zoom(other),
        session.selection(other),
    ) == other_state


@given(
    st.sets(
        st.tuples(st.sampled_from(_IDS), st.sampled_from(_IDS)).filter(
            lambda p: p[0] != p[1]
        ),
        max_size=6,
    ),
    sessions(),
    _SLOT,
    st.sampled_from([0, 1]),
)
def test_candidate_depends_only_on_current_pair(pairs, session, new_id, slot):
    index = _index(pairs)

    def expected():
        a, b = session.slot_persons()
        if a is None or b is None or a == b:
            return None
        return index.candidate_for_pair(a, b)

    assert session.current_candidate(index) is expected()
    session.set_slot(slot, new_id)
    assert session.current_candidate(index) is expected()
    session.swap()
    assert session.current_candidate(index) is expected()
    # Same pair in a fresh session yields the same candidate (no carry-over).
    fresh = ComparisonSession.from_pair(*session.slot_persons())
    assert fresh.current_candidate(index) is session.current_candidate(index)


@given(sessions(), st.sampled_from([0, 1]), _SLOT)
def test_continue_to_merge_only_for_two_different_persons(session, slot, new_id):
    def check():
        a, b = session.slot_persons()
        assert session.can_continue_to_merge() == (
            a is not None and b is not None and a != b
        )

    check()
    session.set_slot(slot, new_id)
    check()
    session.swap()
    check()
    session.set_slot(slot, None)
    check()
    assert not session.can_continue_to_merge()
