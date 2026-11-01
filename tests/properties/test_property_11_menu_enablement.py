"""Property 11: Menu enablement and selection order.

**Validates: Requirements 8.4, 8.5, 8.6, 8.7, 9.1**
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from slaktbusken.services.comparison_session import (
    menu_state,
    order_by_person_list,
    slots_for_selection,
)


@given(st.integers(min_value=0, max_value=10_000))
def test_property_11_menu_enablement(count):
    state = menu_state(count)
    assert state.compare_enabled == (count in (1, 2))
    assert state.mark_candidates_enabled == (count == 2)


@st.composite
def _list_and_selection(draw):
    ids = draw(st.lists(st.text(min_size=1, max_size=6), min_size=0, max_size=15, unique=True))
    selected = draw(st.lists(st.sampled_from(ids), unique=True, max_size=2)) if ids else []
    return ids, selected


@given(_list_and_selection(), st.randoms(use_true_random=False))
def test_property_11_selection_order(data, rnd):
    list_order, selected = data
    shuffled = list(selected)
    rnd.shuffle(shuffled)

    expected = [p for p in list_order if p in set(selected)]
    assert order_by_person_list(shuffled, list_order) == expected

    slots = slots_for_selection(shuffled, list_order)
    assert slots == slots_for_selection(selected, list_order)
    padded = tuple(expected) + (None,) * (2 - len(expected))
    assert slots == padded
