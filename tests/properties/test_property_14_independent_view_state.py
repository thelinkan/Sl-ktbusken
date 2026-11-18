"""Property 14: Independent view state.
**Validates: Requirements 10.7, 10.8, 10.9, 10.14**
"""
from __future__ import annotations

from hypothesis import given, strategies as st

from slaktbusken.services.comparison_session import ComparisonSession

IDS = st.sampled_from([f"p{i}" for i in range(6)])
OPT_IDS = st.one_of(st.none(), IDS)

# One operation on one view: (view, kind, value)
OPERATION = st.one_of(
    st.tuples(st.sampled_from([0, 1]), st.just("focus"), OPT_IDS),
    st.tuples(st.sampled_from([0, 1]), st.just("expansion"), st.frozensets(IDS)),
    st.tuples(
        st.sampled_from([0, 1]),
        st.just("zoom"),
        st.floats(min_value=0.1, max_value=8.0, allow_nan=False),
    ),
    st.tuples(st.sampled_from([0, 1]), st.just("select"), OPT_IDS),
)


@st.composite
def sessions(draw):
    left = draw(OPT_IDS)
    right = draw(OPT_IDS)
    return ComparisonSession.from_pair(left, right)


def _view_state(session: ComparisonSession, view: int):
    return (
        session.focus(view),
        session.expansion(view),
        session.zoom(view),
        session.selection(view),
    )


def _apply(session: ComparisonSession, view: int, kind: str, value) -> None:
    if kind == "focus":
        session.set_focus(view, value)
    elif kind == "expansion":
        session.set_expansion(view, value)
    elif kind == "zoom":
        session.set_zoom(view, value)
    else:
        session.select(view, value)


@given(session=sessions(), view=st.sampled_from([0, 1]), ops=st.lists(OPERATION))
def test_operations_in_one_view_leave_other_view_and_slots_unchanged(
    session, view, ops
):
    other = 1 - view
    slots_before = session.slot_persons()
    other_before = _view_state(session, other)

    for _, kind, value in ops:
        _apply(session, view, kind, value)
        assert session.slot_persons() == slots_before
        assert _view_state(session, other) == other_before


@given(session=sessions(), ops=st.lists(OPERATION))
def test_navigation_within_a_view_keeps_slot_persons(session, ops):
    slots_before = session.slot_persons()
    for view, kind, value in ops:
        _apply(session, view, kind, value)
    assert session.slot_persons() == slots_before


@given(
    session=sessions(),
    ops=st.lists(OPERATION),
    existing=st.frozensets(IDS),
)
def test_clear_missing_clears_only_the_deleted_persons_slot(session, ops, existing):
    for view, kind, value in ops:
        _apply(session, view, kind, value)

    slots_before = session.slot_persons()
    views_before = [_view_state(session, v) for v in (0, 1)]

    cleared = session.clear_missing(set(existing))

    for slot in (0, 1):
        pid = slots_before[slot]
        if pid is not None and pid not in existing:
            assert slot in cleared
            assert session.slot_persons()[slot] is None
        else:
            assert slot not in cleared
            assert session.slot_persons()[slot] == pid
            assert _view_state(session, slot) == views_before[slot]
