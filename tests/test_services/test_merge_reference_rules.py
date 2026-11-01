"""Reference rewrite and collapse rules (Mandatory group a: reference preservation).

Requirements 22.3, 22.9, 22.13, 23.2 to 23.4, 35.1.
"""

from __future__ import annotations

import copy

import pytest
from hypothesis import given, strategies as st

from slaktbusken.model.family import ParentChildLink
from slaktbusken.model.media import LinkedEntity
from slaktbusken.services.merge_rules import (
    collapse_id_list,
    collapse_linked_entities,
    collapse_parent_child_links,
)

pytestmark = pytest.mark.mandatory_integrity

RETIRED = "P_RETIRED"
SURVIVOR = "P_SURVIVOR"
_OTHERS = ["P1", "P2", "P3"]
_PERSON_IDS = st.sampled_from([RETIRED, SURVIVOR, *_OTHERS])
_ROLES = st.sampled_from(["", "  ", "vittne", "fotograf", "gudfar"])
_TYPES = st.sampled_from(["biological", "adopted", "foster"])


@st.composite
def _links(draw):
    entity_type = draw(st.sampled_from(["person", "person", "place"]))
    return LinkedEntity(entity_type, draw(_PERSON_IDS), draw(_ROLES))


@st.composite
def _pc_links(draw):
    return ParentChildLink(
        draw(_PERSON_IDS), draw(st.one_of(st.none(), _PERSON_IDS)), draw(_TYPES)
    )


@given(
    st.lists(_links(), max_size=12),
    st.lists(_PERSON_IDS, max_size=12),
    st.lists(_pc_links(), max_size=12),
)
def test_property_30_link_collapse(links, ids, pc_links):
    """**Validates: Requirements 22.3, 22.9, 22.13, 23.2, 23.3, 23.4**"""
    links_before = copy.deepcopy(links)
    ids_before = list(ids)
    pc_before = copy.deepcopy(pc_links)

    # --- media / research note person links -------------------------------
    result = collapse_linked_entities(links, RETIRED, SURVIVOR)
    assert links == links_before
    assert not any(
        l.entity_type == "person" and l.entity_id == RETIRED for l in result
    )
    to_survivor = [
        l for l in links
        if l.entity_type == "person" and l.entity_id in (RETIRED, SURVIVOR)
    ]
    survivor_links = [
        l for l in result if l.entity_type == "person" and l.entity_id == SURVIVOR
    ]
    if to_survivor:
        assert len(survivor_links) == 1
        expected_role = next((l.role for l in to_survivor if l.role.strip()), "")
        assert survivor_links[0].role == expected_role
        first_pos = next(
            i for i, l in enumerate(links)
            if l.entity_type == "person" and l.entity_id in (RETIRED, SURVIVOR)
        )
        # Position of the first such link is kept; the links before it are unchanged.
        assert result[first_pos] is survivor_links[0]
        assert result[:first_pos] == links[:first_pos]
    else:
        assert survivor_links == []
    # Everything else is untouched and keeps its order.
    others_in = [
        l for l in links
        if not (l.entity_type == "person" and l.entity_id in (RETIRED, SURVIVOR))
    ]
    others_out = [l for l in result if l.entity_id != SURVIVOR or l.entity_type != "person"]
    assert others_out == others_in

    # --- id lists (mentioned_person_ids, cluster person_ids) --------------
    id_result = collapse_id_list(ids, RETIRED, SURVIVOR)
    assert ids == ids_before
    assert RETIRED not in id_result
    assert id_result.count(SURVIVOR) == (1 if (RETIRED in ids or SURVIVOR in ids) else 0)
    assert [i for i in id_result if i != SURVIVOR] == [
        i for i in ids if i not in (RETIRED, SURVIVOR)
    ]
    if SURVIVOR in id_result:
        first = next(k for k, i in enumerate(ids) if i in (RETIRED, SURVIVOR))
        assert id_result.index(SURVIVOR) == len(
            [i for i in ids[:first] if i not in (RETIRED, SURVIVOR)]
        )

    # --- parent-child links ----------------------------------------------
    outcome = collapse_parent_child_links(pc_links, RETIRED, SURVIVOR)
    assert pc_links == pc_before
    assert all(
        RETIRED not in (l.child_id, l.parent_id) for l in outcome.links
    )

    def swap(value):
        return SURVIVOR if value == RETIRED else value

    rewritten = [(swap(l.child_id), swap(l.parent_id), l.parentage_type) for l in pc_links]
    expected_unique = list(dict.fromkeys(rewritten))
    assert [(l.child_id, l.parent_id, l.parentage_type) for l in outcome.links] == expected_unique
    assert outcome.collapsed == len(rewritten) - len(expected_unique)

    types_by_pair: dict[tuple, list[str]] = {}
    for child, parent, ptype in expected_unique:
        types_by_pair.setdefault((child, parent), []).append(ptype)
    expected_conflicts = [
        (c, p, tuple(t)) for (c, p), t in types_by_pair.items() if len(t) > 1
    ]
    assert outcome.type_conflicts == expected_conflicts
    # One warning per pair, never more.
    pairs = [(c, p) for c, p, _ in outcome.type_conflicts]
    assert len(pairs) == len(set(pairs))
    # Different-type links for a pair are all kept (no blocking conflict).
    for (child, parent), types in types_by_pair.items():
        kept = [l.parentage_type for l in outcome.links
                if (l.child_id, l.parent_id) == (child, parent)]
        assert kept == types
