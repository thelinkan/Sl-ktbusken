"""Property 2: Migration to 0.4 is additive and idempotent.

**Validates: Requirements 2.1, 4.6, 7.1, 7.4, 28.11**
"""

from __future__ import annotations

import copy

from hypothesis import given, strategies as st

from slaktbusken.persistence.migration import MigrationManager

NEW_KEYS = ("merge_candidates", "merge_history")

_json_leaf = st.one_of(
    st.none(), st.booleans(), st.integers(), st.text(max_size=10)
)
_json = st.recursive(
    _json_leaf,
    lambda c: st.one_of(
        st.lists(c, max_size=3), st.dictionaries(st.text(max_size=6), c, max_size=3)
    ),
    max_leaves=8,
)


@st.composite
def documents_03(draw):
    doc = draw(
        st.dictionaries(
            st.text(max_size=8).filter(lambda k: k not in NEW_KEYS + ("version", "format_version")),
            _json,
            max_size=6,
        )
    )
    for key in NEW_KEYS:
        if draw(st.booleans()):
            doc[key] = draw(st.lists(_json, max_size=3))
    doc["version"] = "0.3"
    doc["format_version"] = "0.3"
    return doc


@given(documents_03())
def test_property_02_migration_additive_and_idempotent(doc):
    original = copy.deepcopy(doc)
    once = MigrationManager.migrate(copy.deepcopy(doc), "0.3")

    # Version fields set; missing collections added empty; existing kept.
    assert once["version"] == "0.4"
    assert once["format_version"] == "0.4"
    for key in NEW_KEYS:
        assert once[key] == original.get(key, [])

    # No other key changed.
    skip = set(NEW_KEYS) | {"version", "format_version"}
    assert {k: v for k, v in once.items() if k not in skip} == {
        k: v for k, v in original.items() if k not in skip
    }

    # Idempotent: applying the 0.3 -> 0.4 step again gives the same result.
    _, step = MigrationManager._migrations["0.3"]
    twice = step(copy.deepcopy(once))
    assert twice == once
