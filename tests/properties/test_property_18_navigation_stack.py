"""Property 18: Navigation stack.

**Validates: Requirements 14.1, 14.2, 14.3, 14.4, 14.9, 14.10**
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from slaktbusken.services.comparison_session import (
    MAX_DEPTH,
    ComparisonSession,
    PushResult,
)

_IDS = st.sampled_from(["p1", "p2", "p3", "p4", "p5"])
_OPT_IDS = st.one_of(st.none(), _IDS)
_VIEW = st.sampled_from([0, 1])
_ZOOMS = st.sampled_from([0.25, 0.5, 1.0, 1.5, 2.0])

_OP = st.one_of(
    st.tuples(st.just("select"), _VIEW, _OPT_IDS),
    st.tuples(st.just("focus"), _VIEW, _OPT_IDS),
    st.tuples(st.just("expand"), _VIEW, st.frozensets(_IDS, max_size=4)),
    st.tuples(st.just("zoom"), _VIEW, _ZOOMS),
    st.tuples(st.just("slot"), _VIEW, _OPT_IDS),
    st.tuples(st.just("swap")),
    st.tuples(st.just("sub"), _IDS, _IDS),
    st.tuples(st.just("sub"), _IDS, _IDS),
    st.tuples(st.just("sub"), _IDS, _IDS),
    st.tuples(st.just("back")),
)


def _apply(session, op):
    kind = op[0]
    if kind == "select":
        session.select(op[1], op[2])
    elif kind == "focus":
        session.set_focus(op[1], op[2])
    elif kind == "expand":
        session.set_expansion(op[1], op[2])
    elif kind == "zoom":
        session.set_zoom(op[1], op[2])
    elif kind == "slot":
        session.set_slot(op[1], op[2])
    elif kind == "swap":
        session.swap()


@given(st.lists(_OP, max_size=120))
def test_property_18_navigation_stack(ops):
    session = ComparisonSession()
    model: list = []  # independent expected stack of exact previous contexts

    for op in ops:
        if op[0] == "back":
            before = session.context()
            had = bool(model)
            assert session.can_go_back() is had
            result = session.back()
            assert result is had
            if had:
                expected = model.pop()
                assert session.context() == expected
                assert session.slot_persons() == expected.slot_persons
                assert session.selections() == expected.selection
                for v in (0, 1):
                    assert session.focus(v) == expected.focus[v]
                    assert session.expansion(v) == expected.expansion[v]
                    assert session.zoom(v) == expected.zoom[v]
            else:
                assert session.context() == before  # empty stack: no-op
        elif op[0] == "sub":
            session.select(0, op[1])
            session.select(1, op[2])
            before = session.context()
            result = session.compare_selected()
            if op[1] == op[2]:
                assert result is PushResult.NOT_ALLOWED
                assert session.context() == before
            elif len(model) >= MAX_DEPTH:
                assert result is PushResult.DEPTH_REACHED
                assert session.context() == before  # nothing changes (14.10)
            else:
                assert result is PushResult.PUSHED
                model.append(before)  # exact previous context (14.1)
                assert session.slot_persons() == (op[1], op[2])
            assert session.depth == len(model)
        else:
            _apply(session, op)

        assert session.depth == len(model) <= MAX_DEPTH
        assert session.can_go_back() is bool(model)

    # Unwind: exactly one level per back, in reverse order.
    while model:
        expected = model.pop()
        depth = session.depth
        assert session.back() is True
        assert session.depth == depth - 1
        assert session.context() == expected
    assert session.back() is False


@given(st.lists(st.tuples(_IDS, _IDS).filter(lambda t: t[0] != t[1]), min_size=1, max_size=30))
def test_property_18_repeated_sub_comparisons_return_one_level_each(pairs):
    session = ComparisonSession.from_pair("p1", "p2")
    contexts = []
    for left, right in pairs:
        session.select(0, left)
        session.select(1, right)
        ctx = session.context()
        result = session.compare_selected()
        if len(contexts) >= MAX_DEPTH:
            assert result is PushResult.DEPTH_REACHED
            assert session.context() == ctx
        else:
            assert result is PushResult.PUSHED
            contexts.append(ctx)
    assert session.depth == min(len(pairs), MAX_DEPTH)
    for expected in reversed(contexts):
        assert session.back() is True
        assert session.context() == expected
    assert session.depth == 0
    assert session.back() is False
