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


# ---------------------------------------------------------------------------
# Property 25: attribute resolution
# ---------------------------------------------------------------------------

from slaktbusken.model.person import Name, Person  # noqa: E402
from slaktbusken.model.project import ProjectData  # noqa: E402
from slaktbusken.services.merge_planner import (  # noqa: E402
    MergeDecisions,
    build_plan,
)

_TEXT = st.sampled_from(["", "  ", "Smed", "Bonde", "Smed "])
_MEDIA = st.sampled_from(["", "m1", "m2"])
_SEX = st.sampled_from(["", "U", "M", "F"])
_OVERRIDE = st.sampled_from([None, "o1", "o2"])
_PICK = st.sampled_from([None, "first", "second"])


def _blank(v):
    return v is None or not v.strip()


def _attr_person(pid, sex, title, occupation, media):
    return Person(
        id=pid, sex=sex, title=title, occupation=occupation, profile_media_id=media,
        names=[Name("birth", "Anna", "Berg")],
    )


@given(
    st.tuples(_SEX, _TEXT, _TEXT, _MEDIA),
    st.tuples(_SEX, _TEXT, _TEXT, _MEDIA),
    _OVERRIDE, _OVERRIDE,
    _PICK, _PICK, _PICK, _PICK, _PICK,
    st.booleans(),
)
def test_property_25_attribute_resolution(
    a, b, ov_a, ov_b, pick_sex, pick_title, pick_occ, pick_media, pick_ov, survivor_is_first
):
    """**Validates: Requirements 1.3, 20.8, 21.2, 21.3, 21.4, 21.5, 21.7, 21.17,
    22.4, 22.5, 22.15, 22.16, 26.4**"""
    first = _attr_person("pa", *a)
    second = _attr_person("pb", *b)
    overrides = {}
    if ov_a:
        overrides["pa"] = ov_a
    if ov_b:
        overrides["pb"] = ov_b
    data = ProjectData(persons=[first, second], connection_overrides=dict(overrides))

    survivor, retired = (first, second) if survivor_is_first else (second, first)
    s_id, r_id = survivor.id, retired.id

    def person_of(which):
        return {"first": first, "second": second}[which] if which else None

    def pid(which):
        p = person_of(which)
        return p.id if p else None

    def media_choice(which):
        p = person_of(which)
        return p.profile_media_id if p else None

    # --- no survivor chosen: never defaulted, never executable ---------------
    undecided = build_plan(data, None, MergeDecisions("pa", "pb"))
    assert undecided.survivor_id is None and undecided.retired_id is None
    assert {u.key for u in undecided.unresolved} == {"survivor"}
    assert not undecided.can_execute

    # --- first pass: no attribute choices ------------------------------------
    plan = build_plan(
        data, None,
        MergeDecisions("pa", "pb", survivor_id=s_id, survivor_confirmed=True),
    )
    assert plan.survivor_id == s_id and plan.retired_id == r_id
    merged = plan.change_set.replaced["persons"][s_id]
    keys = {u.key for u in plan.unresolved}

    def check_single(field, s_val, r_val, key, merged_val, chosen_ok):
        if _blank(s_val) and _blank(r_val):
            assert key not in keys
        elif _blank(r_val):
            assert key not in keys and merged_val == s_val
        elif _blank(s_val):
            assert key not in keys and merged_val == r_val
        elif s_val.strip() == r_val.strip():
            assert key not in keys and merged_val.strip() == s_val.strip()
        else:
            assert key in keys, f"{field} conflict must be unresolved"
            assert not plan.can_execute
        if not _blank(s_val) or not _blank(r_val):
            assert not _blank(merged_val)  # never replaced by an empty value

    check_single("title", survivor.title, retired.title, "title", merged.title, True)
    check_single("occupation", survivor.occupation, retired.occupation,
                 "occupation", merged.occupation, True)
    check_single("profile_media_id", survivor.profile_media_id, retired.profile_media_id,
                 "profile_media_id", merged.profile_media_id, True)

    def known(sex):
        return None if _blank(sex) or sex.strip().upper() == "U" else sex.strip()

    ks, kr = known(survivor.sex), known(retired.sex)
    sex_conflict = ks is not None and kr is not None and ks != kr
    if sex_conflict:
        assert any(c.code == "sex_conflict" and c.is_blocking for c in plan.conflicts)
        assert "sex" in keys
    else:
        assert not any(c.code == "sex_conflict" for c in plan.conflicts)
        assert "sex" not in keys
        expected_sex = ks or kr
        if expected_sex:
            assert merged.sex == expected_sex

    # Connection override: only the retired person's value moves; the retired
    # key never survives; a difference needs a choice.
    new_overrides = plan.change_set.scalars.get("connection_overrides")
    s_ov, r_ov = overrides.get(s_id), overrides.get(r_id)
    if r_ov is None:
        assert "connection_override" not in keys
    else:
        assert new_overrides is not None and r_id not in new_overrides
        if s_ov is None:
            assert new_overrides[s_id] == r_ov
        elif s_ov == r_ov:
            assert new_overrides[s_id] == s_ov
        else:
            assert "connection_override" in keys

    # Unresolved choices or blocking conflicts disable execution; otherwise it is allowed.
    assert plan.can_execute == (not plan.blocking and not plan.unresolved)
    if keys or plan.blocking:
        assert not plan.can_execute

    # --- second pass: the user chooses where there is a conflict -------------
    decisions = MergeDecisions(
        "pa", "pb", survivor_id=s_id, survivor_confirmed=True,
        sex=(pid(pick_sex) and person_of(pick_sex).sex) or None,
        title_from=pid(pick_title), occupation_from=pid(pick_occ),
        profile_media_id=media_choice(pick_media),
        connection_override=overrides.get(pid(pick_ov)) if pick_ov else None,
    )
    plan2 = build_plan(data, None, decisions)
    merged2 = plan2.change_set.replaced["persons"][s_id]
    keys2 = {u.key for u in plan2.unresolved}

    def conflicting(s_val, r_val):
        return not _blank(s_val) and not _blank(r_val) and s_val.strip() != r_val.strip()

    for key, s_val, r_val, chosen_id, value in (
        ("title", survivor.title, retired.title, decisions.title_from, merged2.title),
        ("occupation", survivor.occupation, retired.occupation,
         decisions.occupation_from, merged2.occupation),
    ):
        if conflicting(s_val, r_val):
            if chosen_id in (s_id, r_id):
                assert key not in keys2
                assert value == (s_val if chosen_id == s_id else r_val)
            else:
                assert key in keys2
    if conflicting(survivor.profile_media_id, retired.profile_media_id):
        chosen = decisions.profile_media_id
        if chosen in (survivor.profile_media_id, retired.profile_media_id):
            assert "profile_media_id" not in keys2
            assert merged2.profile_media_id == chosen
        else:
            assert "profile_media_id" in keys2
    if sex_conflict:
        chosen_sex = decisions.sex.strip() if decisions.sex else None
        if chosen_sex in (ks, kr):
            assert "sex" not in keys2
            assert merged2.sex == chosen_sex
            assert not any(c.code == "sex_conflict" for c in plan2.conflicts)
        else:
            assert "sex" in keys2
            assert any(c.code == "sex_conflict" and c.is_blocking for c in plan2.conflicts)
    if s_ov is not None and r_ov is not None and s_ov != r_ov:
        if decisions.connection_override in (s_ov, r_ov):
            assert "connection_override" not in keys2
            assert plan2.change_set.scalars["connection_overrides"][s_id] == (
                decisions.connection_override
            )
        else:
            assert "connection_override" in keys2
    assert plan2.can_execute == (not plan2.blocking and not plan2.unresolved)

    # --- the planner never changes the inputs --------------------------------
    assert data.connection_overrides == overrides
    assert (first.title, first.occupation, first.sex) == (a[1], a[2], a[0])
