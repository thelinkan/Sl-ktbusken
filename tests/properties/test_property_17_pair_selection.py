"""Property 17: Pair selection.

**Validates: Requirements 13.1, 13.3, 13.4, 13.5**
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from slaktbusken.services.comparison_session import (
    SAME_PAIR_MESSAGE,
    ComparisonSession,
    PushResult,
)

_IDS = st.sampled_from(["p1", "p2", "p3", "p4"])
_CLICKS = st.lists(st.tuples(st.sampled_from([0, 1]), _IDS), max_size=30)


def test_same_pair_message_text():
    assert SAME_PAIR_MESSAGE == "Samma registrerade person kan inte vara kandidat till sig själv."


@given(_CLICKS)
def test_property_17_pair_selection(clicks):
    session = ComparisonSession()
    expected = [None, None]

    # Nothing is selected or inferred before the first click (13.5).
    assert session.selections() == (None, None)
    assert session.pair_action_state().enabled is False

    for view, pid in clicks:
        session.select(view, pid)
        expected[view] = pid  # a new selection replaces the old (13.1)

        assert session.selections() == tuple(expected)
        assert session.selection(view) == pid

        state = session.pair_action_state()
        both = expected[0] is not None and expected[1] is not None
        if not both:
            assert state.enabled is False
            assert state.reason == ""
        elif expected[0] == expected[1]:
            assert state.enabled is False
            assert state.reason == SAME_PAIR_MESSAGE
            assert session.compare_selected() is PushResult.NOT_ALLOWED
            assert session.depth == 0
        else:
            assert state.enabled is True
            assert (state.left_id, state.right_id) == tuple(expected)

    # A pair exists only if both persons were selected by clicks.
    if expected[0] is not None and expected[1] is not None and expected[0] != expected[1]:
        assert session.compare_selected() is PushResult.PUSHED
        assert session.slot_persons() == tuple(expected)
    else:
        assert session.compare_selected() is PushResult.NOT_ALLOWED


@given(st.lists(_IDS, max_size=2, unique=True), st.lists(_IDS, max_size=4, unique=True))
def test_property_17_no_preselected_pair(selected, order):
    for session in (
        ComparisonSession.from_selection(selected, order),
        ComparisonSession.from_pair(*(selected + [None, None])[:2]),
    ):
        assert session.selections() == (None, None)
        state = session.pair_action_state()
        assert state.enabled is False
        assert session.compare_selected() is PushResult.NOT_ALLOWED


@given(_IDS)
def test_property_17_same_id_disables_both(pid):
    session = ComparisonSession()
    session.select(0, pid)
    session.select(1, pid)
    state = session.pair_action_state()
    assert state.enabled is False
    assert state.reason == SAME_PAIR_MESSAGE
