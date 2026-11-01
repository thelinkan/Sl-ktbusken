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


# ---------------------------------------------------------------------------
# Property 29: no stale reference to the retired person
# ---------------------------------------------------------------------------

from slaktbusken.model.dna import DnaCluster as _P29Cluster  # noqa: E402
from slaktbusken.model.dna import DnaProfile as _P29Profile  # noqa: E402
from slaktbusken.model.event import Event as _P29Event  # noqa: E402
from slaktbusken.model.event import Participant as _P29Participant  # noqa: E402
from slaktbusken.model.family import Family as _P29Family  # noqa: E402
from slaktbusken.model.family import FamilyPartner as _P29Partner  # noqa: E402
from slaktbusken.model.media import Annotation as _P29Annotation  # noqa: E402
from slaktbusken.model.media import MediaItem as _P29Media  # noqa: E402
from slaktbusken.model.merge_candidate import MergeCandidate as _P29Candidate  # noqa: E402
from slaktbusken.model.project import ProjectMetadata as _P29Meta  # noqa: E402
from slaktbusken.model.research_case import (  # noqa: E402
    ResearchCase as _P29Case,
    ResearchEntityLink as _P29Link,
    ResearchHypothesis as _P29Hypothesis,
)
from slaktbusken.model.research_note import ResearchNote as _P29Note  # noqa: E402
from slaktbusken.model.residence import ResidenceFact as _P29Residence  # noqa: E402
from slaktbusken.persistence.translation_io import (  # noqa: E402
    IdentityAlias as _P29Alias,
    PersonMapping as _P29Mapping,
    TranslationData as _P29Translation,
)
from slaktbusken.services import person_reference_index as _p29_pri  # noqa: E402
from slaktbusken.services.merge_engine import MergeEngine as _P29Engine  # noqa: E402
from slaktbusken.services.merge_planner import apply_change_set as _p29_apply  # noqa: E402

_P29_SURVIVOR = "person_1"
_P29_RETIRED = "person_2"
# Ids that merely contain the retired id as a substring; never to be touched.
_P29_DECOYS = ["person_22", "xperson_2", "person_2b"]
_P29_REFS = st.sampled_from([_P29_RETIRED, _P29_SURVIVOR, "person_3", *_P29_DECOYS])
_P29_REF_OR_RETIRED = st.sampled_from([_P29_RETIRED, _P29_RETIRED, _P29_SURVIVOR, "person_3"])
_P29_CHILD_IDS = st.sampled_from(["child_a", "child_b", _P29_RETIRED, _P29_SURVIVOR])
_P29_ROLES = st.sampled_from(["", "vittne", "fotograf"])


@st.composite
def _p29_projects(draw):
    """A project with references to the retired person in every location."""
    persons = [
        Person(id=pid, sex="F", names=[Name("birth", "Anna", "Berg")])
        for pid in (_P29_SURVIVOR, _P29_RETIRED, "person_3", "child_a", "child_b", *_P29_DECOYS)
    ]
    # Families: retired or survivor as partner (never both in one family), with
    # links whose parents are never children, so no cycle can be formed.
    families = []
    for i in range(draw(st.integers(0, 3))):
        partner = draw(st.sampled_from([_P29_RETIRED, _P29_SURVIVOR, "person_3"]))
        other = draw(st.sampled_from(["person_3", *_P29_DECOYS]))
        children = draw(st.lists(st.sampled_from(["child_a", "child_b"]), max_size=2, unique=True))
        links = []
        for c in children:
            parent = draw(st.sampled_from([partner, other, None]))
            links.append(ParentChildLink(
                c, parent, "unknown_donor" if parent is None else "biological"))
        families.append(_P29Family(f"fam_{i}", [_P29Partner(partner, "partner"),
                                                 _P29Partner(other, "partner")], children, links))
    # The retired person as a child of a family whose parents are neither of the pair.
    if draw(st.booleans()):
        kids = draw(st.permutations([_P29_RETIRED, _P29_SURVIVOR, "child_a"]))[: draw(st.integers(1, 3))]
        families.append(_P29Family(
            "fam_kids", [_P29Partner("person_3", "partner"), _P29Partner(_P29_DECOYS[0], "partner")],
            list(kids),
            [ParentChildLink(k, "person_3", draw(st.sampled_from(["biological", "adoptive", "foster"])))
             for k in kids],
        ))
    events = []
    for i in range(draw(st.integers(0, 3))):
        role = draw(_P29_ROLES)  # one role per event: differing roles need a user choice
        events.append(_P29Event(
            f"ev_{i}", "birth",
            [_P29Participant(draw(_P29_REFS), role) for _ in range(draw(st.integers(1, 3)))]))
    # Every event needs the pair to be consistent; a retired person always takes part once.
    events.append(_P29Event("ev_ret", "birth", [_P29Participant(_P29_RETIRED, "child")]))
    residences = [
        _P29Residence(f"res_{i}", draw(_P29_REF_OR_RETIRED), "place_1")
        for i in range(draw(st.integers(1, 3)))
    ]
    media = [
        _P29Media(
            f"m_{i}", "image", f"m_{i}.jpg", f"titel {_P29_RETIRED}",
            linked_entities=[LinkedEntity(draw(st.sampled_from(["person", "place"])),
                                          draw(_P29_REFS), draw(_P29_ROLES))
                             for _ in range(draw(st.integers(0, 3)))],
            mentioned_person_ids=draw(st.lists(_P29_REFS, max_size=3)),
            annotations=[_P29Annotation(0.1 * k, 0, 0.1, 0.1, "person", draw(_P29_REFS))
                         for k in range(draw(st.integers(0, 2)))],
            notes=f"se {_P29_RETIRED} och person_22",
        )
        for i in range(draw(st.integers(1, 2)))
    ]
    notes = [
        _P29Note(f"n_{i}", "Anteckning", f"text om {_P29_RETIRED}",
                 [LinkedEntity("person", draw(_P29_REFS), "") for _ in range(draw(st.integers(1, 3)))])
        for i in range(draw(st.integers(0, 2)))
    ]
    profiles = [
        _P29Profile(f"dna_{i}", draw(_P29_REF_OR_RETIRED), "c1", "autosomal",
                    admin_person_id=draw(st.one_of(st.none(), _P29_REF_OR_RETIRED)))
        for i in range(draw(st.integers(1, 3)))
    ]
    clusters = [_P29Cluster("cl_1", "Grupp", person_ids=draw(st.lists(_P29_REFS, min_size=1, max_size=5)))]
    cases = [_P29Case(
        "case_1", primary_entity_ref=draw(st.one_of(
            st.none(), st.builds(_P29Link, st.just("person"), _P29_REFS))),
        linked_entities=draw(st.lists(st.builds(_P29Link, st.just("person"), _P29_REFS), max_size=3)),
    )]
    hypotheses = [_P29Hypothesis(
        "hyp_1", "case_1",
        linked_entities=draw(st.lists(st.builds(_P29Link, st.just("person"), _P29_REFS), max_size=3)),
    )]
    candidates = []
    for i, other in enumerate(draw(st.lists(
            st.sampled_from(["person_3", _P29_SURVIVOR, _P29_DECOYS[0]]), max_size=3, unique=True))):
        pair = [_P29_RETIRED, other]
        if draw(st.booleans()):
            pair.reverse()
        candidates.append(_P29Candidate(f"cand_{i}", pair[0], pair[1]))
    overrides = {}
    if draw(st.booleans()):
        overrides[_P29_RETIRED] = "ovr"
    main = draw(st.sampled_from([None, _P29_RETIRED, _P29_SURVIVOR, "person_3"]))
    data = ProjectData(
        project=_P29Meta("T", main_person_id=main), persons=persons, families=families,
        events=events, residences=residences, media=media, research_notes=notes,
        dna_profiles=profiles, dna_clusters=clusters, research_cases=cases,
        research_hypotheses=hypotheses, merge_candidates=candidates,
        connection_overrides=overrides,
    )
    translation = _P29Translation(
        persons=[_P29Mapping("@I2@", _P29_RETIRED, "fp2"), _P29Mapping("@I3@", "person_3", "fp3")],
        person_aliases=[_P29Alias("@I9@", "fp9", _P29_RETIRED, "m0")],
    )
    return data, translation


@given(_p29_projects())
def test_property_29_no_stale_reference(project):
    """**Validates: Requirements 1.4, 22.2, 22.6, 22.13, 22.14, 27.4, 28.2, 29.12, 30.12**"""
    data, translation = project
    survivor, retired = _P29_SURVIVOR, _P29_RETIRED

    before_decoys = _decoy_snapshot(data)
    decisions = MergeDecisions(
        _P29_SURVIVOR, _P29_RETIRED, survivor_id=survivor, survivor_confirmed=True
    )
    plan = build_plan(data, translation, decisions)
    assert plan.can_execute, [c for c in plan.conflicts if c.is_blocking] + list(plan.unresolved)

    merged = _p29_apply(data, plan.change_set)
    merged_translation = _P29Engine._merged_translation(plan, translation, retired, survivor)

    # The retired person is no longer an active person anywhere.
    assert all(p.id != retired for p in merged.persons)
    assert any(p.id == survivor for p in merged.persons)

    # No reference with rule rewire, merge-and-deduplicate, explicit or special remains.
    index = _p29_pri.PersonReferenceIndex.build(merged, [retired], merged_translation)
    stale = {
        loc.key: index.count(loc.key, retired)
        for loc in _p29_pri.PERSON_REFERENCE_INVENTORY
        if loc.requires_handler and index.count(loc.key, retired)
    }
    assert not stale, stale

    # Unrelated text and ids that contain the retired id as a substring are unchanged.
    assert _decoy_snapshot(merged) == before_decoys

    # The input data is not modified by planning and applying.
    assert any(p.id == retired for p in data.persons)


def _decoy_snapshot(data: ProjectData):
    """Everything that mentions the retired id only as a substring."""
    return (
        [p.id for p in data.persons if p.id in _P29_DECOYS],
        [(m.id, m.title, m.notes) for m in data.media],
        [(n.id, n.text) for n in data.research_notes],
        [[pc for pc in f.partners if pc.person_id in _P29_DECOYS] for f in data.families],
        [[x for x in c.person_ids if x in _P29_DECOYS] for c in data.dna_clusters],
        [[x for x in m.mentioned_person_ids if x in _P29_DECOYS] for m in data.media],
        [[pp.person_id for pp in e.participants if pp.person_id in _P29_DECOYS] for e in data.events],
    )
