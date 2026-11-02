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


# Feature: person-comparison-and-merge, Property 30:
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


# Feature: person-comparison-and-merge, Property 25:
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


# Feature: person-comparison-and-merge, Property 29:
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


# ---------------------------------------------------------------------------
# Property 31: information is never lost
# ---------------------------------------------------------------------------

from slaktbusken.services.merge_planner import (  # noqa: E402
    LEDGER_KEYS as _P31_KEYS,
    compute_ledger as _p31_ledger,
)

#: Counters that may only fall through a documented deduplication, never rise.
_P31_DEDUP_KEYS = {
    "participants", "media_person_links", "parent_child_links", "names",
    "research_cases", "dna_clusters", "candidates", "candidate_comments",
    "families", "persons",
}


def _p31_independent_counts(data: ProjectData) -> dict[str, int]:
    """Counts taken straight from the data, not through the planner's ledger."""
    from slaktbusken.model.event import SourceRef

    def refs(obj):
        from dataclasses import fields, is_dataclass
        n = 1 if isinstance(obj, SourceRef) else 0
        if is_dataclass(obj) and not isinstance(obj, type):
            n += sum(refs(getattr(obj, f.name)) for f in fields(obj))
        elif isinstance(obj, (list, tuple)):
            n += sum(refs(x) for x in obj)
        return n

    return {
        "events": len(data.events),
        "residences": len(data.residences),
        "source_refs": refs(data.events) + refs(data.residences),
        "media_items": len(data.media),
        "annotations": sum(len(m.annotations) for m in data.media),
        "dna_profiles": len(data.dna_profiles),
        "research_hypotheses": len(data.research_hypotheses),
        "research_notes": len(data.research_notes),
        "observations": sum(len(r.observations) for r in data.residences),
        "participants": sum(len(e.participants) for e in data.events),
        "names": sum(len(p.names) for p in data.persons),
    }


# Feature: person-comparison-and-merge, Property 31:
@given(_p29_projects())
def test_property_31_information_never_lost(project):
    """**Validates: Requirements 21.11, 21.15, 21.16, 22.1, 22.7, 22.10, 23.8, 32.6**"""
    data, translation = project
    survivor, retired = _P29_SURVIVOR, _P29_RETIRED
    plan = build_plan(
        data, translation,
        MergeDecisions(survivor, retired, survivor_id=survivor, survivor_confirmed=True),
    )
    assert plan.can_execute

    before = _p31_independent_counts(data)
    ledger_before = _p31_ledger(data)
    event_ids_before = [e.id for e in data.events]
    residence_ids_before = [r.id for r in data.residences]
    media_ids_before = [m.id for m in data.media]
    participants_before = {e.id: len(e.participants) for e in data.events}
    sources_before = {
        e.id: len(getattr(e, "source_refs", []) or []) for e in data.events
    }
    retired_names = len(next(p for p in data.persons if p.id == retired).names)
    survivor_names = len(next(p for p in data.persons if p.id == survivor).names)

    merged = _p29_apply(data, plan.change_set)
    after = _p31_independent_counts(merged)
    ledger_after = _p31_ledger(merged)

    # The plan's own "before" ledger describes the real input.
    assert plan.ledger_before.differences(ledger_before) == {}
    assert _p31_ledger(data).differences(ledger_before) == {}  # input untouched

    # Records that carry information and have no documented dedup are all kept.
    for key in ("events", "residences", "source_refs", "media_items", "annotations",
                "dna_profiles", "research_hypotheses", "research_notes", "observations"):
        assert after[key] == before[key], key
    for key in ("dna_matches", "dna_segments", "research_actions", "hypothesis_comments"):
        assert ledger_after[key] == ledger_before[key], key

    # No event id is combined with another or invented; ids and order are unchanged.
    assert [e.id for e in merged.events] == event_ids_before
    assert [r.id for r in merged.residences] == residence_ids_before
    assert [m.id for m in merged.media] == media_ids_before

    # Each event keeps at least one participant; only exact duplicates of the
    # pair inside one event may disappear, never more than the original count - 1.
    for event in merged.events:
        assert 1 <= len(event.participants) <= participants_before[event.id]
    for event in data.events:  # input events are not mutated
        assert len(event.participants) == participants_before[event.id]

    # Names: the survivor keeps all of its names; at most the retired person's are deduplicated.
    survivor_after = next(p for p in merged.persons if p.id == survivor)
    assert len(survivor_after.names) >= survivor_names
    assert len(survivor_after.names) <= survivor_names + retired_names

    # Every counter: the actual result equals the plan's documented expectation,
    # and falls below the input only for counters with a documented deduplication.
    assert ledger_after.differences(plan.ledger_after_expected) == {}
    for key in _P31_KEYS:
        if key not in _P31_DEDUP_KEYS:
            assert ledger_after[key] == ledger_before[key], key
    assert ledger_after["persons"] == ledger_before["persons"] - 1
    for key in ("participants", "media_person_links", "parent_child_links"):
        assert ledger_after[key] <= ledger_before[key]
    # Families are not lost: a changed count must be explained by the plan.
    if ledger_after["families"] != ledger_before["families"]:
        assert plan.ledger_after_expected["families"] == ledger_after["families"]
    # Candidate comments leave the active list only together with their candidate.
    if ledger_after["candidate_comments"] < ledger_before["candidate_comments"]:
        assert ledger_after["candidates"] < ledger_before["candidates"]
    del sources_before


# ---------------------------------------------------------------------------
# Task 13.17: one example test per row of the Person_Reference_Inventory
#
# One project holds a reference to the retired person at every inventory
# location. It is merged once with the real engine (plan, commit to disk,
# adopt); each row test then checks its own Reference_Rule on the result.
# Conflicts that need a user choice are resolved by the decisions; the
# "no choice made" and "blocking" variants are planned separately.
# ---------------------------------------------------------------------------

import sys as _rr_sys  # noqa: E402
from collections import namedtuple as _rr_namedtuple  # noqa: E402
from dataclasses import fields as _rr_fields, is_dataclass as _rr_is_dc  # noqa: E402
from typing import get_args as _rr_get_args, get_type_hints as _rr_get_type_hints  # noqa: E402

from slaktbusken.model.dna import DnaMatch as _RRMatch  # noqa: E402
from slaktbusken.model.event import SourceRef as _RRSourceRef  # noqa: E402
from slaktbusken.model.merge_candidate import (  # noqa: E402
    ArchivedCandidate as _RRArchived,
    MergeCandidateComment as _RRComment,
    MergeHistoryEntry as _RRHistory,
)
from slaktbusken.model.research_case import ResearchAction as _RRAction  # noqa: E402
from slaktbusken.model.residence import Observation as _RRObservation  # noqa: E402
from slaktbusken.persistence import translation_io as _rr_tio  # noqa: E402
from slaktbusken.persistence.translation_io import FamilyMapping as _RRFamilyMapping  # noqa: E402
from slaktbusken.services.project_service import ProjectService as _RRService  # noqa: E402

_S = "person_1"  # survivor
_R = "person_2"  # retired
_RR_CONNECTION = "o_survivor"

_RRMerged = _rr_namedtuple(
    "_RRMerged",
    "before_data before_translation plan outcome after after_translation "
    "settings_before settings_after reloaded",
)


def _rr_project() -> ProjectData:
    ids = ["person_1", "person_2", "person_3", "person_4", "person_5", "person_6",
           "person_7", "person_8", "person_9", "child_a", "child_b", "child_c"]
    persons = [Person(id=i, sex="F", names=[Name("birth", i, "Berg")]) for i in ids]
    persons[0] = Person(
        id=_S, sex="F", names=[Name("birth", "Anna", "Berg")], notes="Överlevande",
        occupation="Lektor", profile_media_id="m_s",
    )
    persons[1] = Person(
        id=_R, sex="F", names=[Name("birth", "Anna", "Berg"), Name("alias", "Annika", "Lind")],
        notes="Avförd", title="Dr", occupation="Smed", profile_media_id="m_r",
    )

    def partner(pid):
        return _P29Partner(pid, "partner")

    def link(child, parent, kind="biological"):
        return ParentChildLink(child, parent, kind)

    families = [
        # retired as partner and as parent of a link
        _P29Family("fam_a", [partner(_R), partner("person_3")], ["child_a"],
                   [link("child_a", _R), link("child_a", "person_3")], ["ev_marr"]),
        # both persons are children of one family: children and child links collapse
        _P29Family("fam_b", [partner("person_4"), partner("person_5")], [_S, _R],
                   [link(_S, "person_4"), link(_S, "person_5"),
                    link(_R, "person_4"), link(_R, "person_5")]),
        # retired as a child only; the unknown-donor link (parent None) is left alone
        _P29Family("fam_d", [partner("person_7"), partner("person_8")], [_R, "child_c"],
                   [link(_R, "person_7"), link(_R, None, "unknown_donor"),
                    link("child_c", "person_7"), link("child_c", "person_8")]),
        # untouched family
        _P29Family("fam_z", [partner("person_6"), partner("person_9")], ["child_b"],
                   [link("child_b", "person_6"), link("child_b", "person_9")]),
    ]
    events = [
        _P29Event("ev_birth", "birth", [_P29Participant(_R, "child")]),
        _P29Event("ev_wit", "baptism", [
            _P29Participant(_S, "witness"), _P29Participant(_R, "witness"),
            _P29Participant("person_3", "child")]),
        _P29Event("ev_roles", "baptism", [
            _P29Participant(_S, "father"), _P29Participant(_R, "witness")]),
        _P29Event("ev_marr", "marriage", [_P29Participant("person_3", "groom"),
                                           _P29Participant("person_9", "bride")]),
    ]
    obs = _RRObservation(_RRSourceRef("s1", "A"), "1900", "1901")
    residences = [
        _P29Residence("res_1", _R, "place_1", observations=[obs], notes="lika"),
        _P29Residence("res_2", _S, "place_1", observations=[obs], notes="lika"),
    ]
    media = [
        _P29Media("m_s", "image", "m_s.jpg", "Profil"),
        _P29Media("m_r", "image", "m_r.jpg", "Profil"),
        _P29Media(
            "m_1", "image", "m_1.jpg", "Bild",
            linked_entities=[LinkedEntity("person", _S, ""), LinkedEntity("person", _R, "fotograf"),
                             LinkedEntity("place", "place_1", "")],
            mentioned_person_ids=[_R, "person_3", _S],
            mentioned_names=["Anna Berg"],
            annotations=[_P29Annotation(0.1, 0.1, 0.1, 0.1, "person", _R),
                         _P29Annotation(0.5, 0.5, 0.1, 0.1, "person", _S)],
            publication={"title": "Bok", "text": _R}, photo_date={"year": 1900},
        ),
    ]
    notes = [_P29Note("n_1", "Anteckning", f"om {_R}",
                      [LinkedEntity("person", _R, ""), LinkedEntity("person", _S, "")])]
    profiles = [
        _P29Profile("dna_r", _R, "c1", "autosomal", admin_person_id=_R),
        _P29Profile("dna_s", _S, "c1", "autosomal"),
        _P29Profile("dna_x", "person_3", "c1", "autosomal", admin_person_id=_R),
    ]
    clusters = [_P29Cluster("cl_1", "Grupp", person_ids=[_R, "person_3", _S, "person_4"])]
    matches = [_RRMatch("dm_1", "dna_r", "dna_s", 40.0)]
    cases = [_P29Case(
        "case_1", primary_entity_ref=_P29Link("person", _R),
        linked_entities=[_P29Link("person", _R), _P29Link("person", _S)])]
    hypotheses = [_P29Hypothesis(
        "hyp_1", "case_1", linked_entities=[_P29Link("person", _R), _P29Link("person", "person_3")])]
    actions = [_RRAction("act_1", "case_1", "Gör något")]
    candidates = [
        _P29Candidate("cand_1", _R, "person_3", comments=[_RRComment("cc_1", "2024-01-01", "x")]),
        _P29Candidate("cand_2", "person_3", _S),   # collides with cand_1 after the redirect
        _P29Candidate("cand_3", _S, _R),            # becomes a self pair
        _P29Candidate("cand_4", "person_4", _R),    # plain redirect
    ]
    history = [_RRHistory(
        "merge_old", _R, "person_8", "Gammal", "1800-1850", "2020-01-01",
        archived_candidates=[_RRArchived("cand_old", _R, "person_8", "possible", True)],
    )]
    return ProjectData(
        project=_P29Meta("T", main_person_id=_R), persons=persons, families=families,
        events=events, residences=residences, media=media, research_notes=notes,
        dna_profiles=profiles, dna_matches=matches, dna_clusters=clusters,
        research_cases=cases, research_hypotheses=hypotheses, research_actions=actions,
        merge_candidates=candidates, merge_history=history,
        connection_overrides={_S: _RR_CONNECTION, _R: "o_retired"},
    )


def _rr_translation() -> _P29Translation:
    return _P29Translation(
        persons=[_P29Mapping("@I2@", _R, "fp2"), _P29Mapping("@I3@", "person_3", "fp3")],
        families=[_RRFamilyMapping("@F1@", "fam_a")],
        person_aliases=[_P29Alias("@I9@", "fp9", _R, "merge_0")],
    )


def _rr_decisions(**overrides) -> MergeDecisions:
    choices = dict(
        survivor_id=_S, survivor_confirmed=True, occupation_from=_S, profile_media_id="m_s",
        primary_name=("Anna", "Berg", "birth", None),
        participant_roles={"ev_roles": "father"}, connection_override=_RR_CONNECTION,
    )
    choices.update(overrides)
    return MergeDecisions(_S, _R, **choices)


def _rr_settings_bytes(svc) -> bytes:
    return (svc.project_path.parent / "settings.json").read_bytes()


@pytest.fixture(scope="module")
def merged(tmp_path_factory) -> _RRMerged:
    svc = _RRService()
    svc.create_project("Test", tmp_path_factory.mktemp("rr"))
    svc.data.project.main_person_id = _R
    for name in ("persons", "families", "events", "residences", "media", "research_notes",
                 "dna_profiles", "dna_matches", "dna_clusters", "research_cases",
                 "research_hypotheses", "research_actions", "merge_candidates",
                 "merge_history"):
        setattr(svc.data, name, getattr(_rr_project(), name))
    svc.data.connection_overrides = dict(_rr_project().connection_overrides)
    translation = _rr_translation()
    _rr_tio.write_persons(
        translation.persons, translation.families,
        svc.project_path.parent / "translation" / "persons.json", translation.person_aliases,
    )
    svc._dirty = True
    svc.save_project()

    before = copy.deepcopy(svc.data)
    before_translation = _rr_tio.read_all(svc.project_path.parent / "translation")
    settings_before = _rr_settings_bytes(svc)
    plan = build_plan(svc.data, before_translation, _rr_decisions(), svc.content_revision)
    outcome = _P29Engine(svc, None).execute(plan)
    assert outcome.success, outcome.message
    from slaktbusken.persistence.file_io import FilePersistence as _FP

    return _RRMerged(
        before, before_translation, plan, outcome, svc.data,
        _rr_tio.read_all(svc.project_path.parent / "translation"),
        settings_before, _rr_settings_bytes(svc), _FP.load(svc.project_path),
    )


def _rr_by_id(items):
    return {x.id: x for x in items}


def _rr_plan_without_choices(merged: _RRMerged, **choices):
    return build_plan(
        merged.before_data, merged.before_translation,
        MergeDecisions(_S, _R, survivor_id=_S, survivor_confirmed=True, **choices),
    )


def _rr_unresolved(plan) -> set[str]:
    return {u.key for u in plan.unresolved}


def test_merge_of_the_reference_project_succeeds_and_persists(merged):
    assert merged.outcome.success
    assert [p.id for p in merged.after.persons if p.id == _R] == []
    assert [p.id for p in merged.reloaded.persons if p.id == _R] == []
    assert merged.reloaded.project.main_person_id == _S


# --- family rows ------------------------------------------------------------


def test_reference_rule_family_partners(merged):
    """R + block: rewritten to the survivor; both in one family is blocking."""
    after = _rr_by_id(merged.after.families)
    assert [p.person_id for p in after["fam_a"].partners] == [_S, "person_3"]
    assert [p.role for p in after["fam_a"].partners] == ["partner", "partner"]
    data = copy.deepcopy(merged.before_data)
    data.families.append(_P29Family("fam_both", [_P29Partner(_S, "partner"), _P29Partner(_R, "partner")], []))
    plan = build_plan(data, merged.before_translation,
                      MergeDecisions(_S, _R, survivor_id=_S, survivor_confirmed=True))
    assert any(c.code == "self_partner" and c.is_blocking for c in plan.conflicts)
    assert not plan.can_execute


def test_reference_rule_family_children(merged):
    """M + collapse: duplicate child entry collapses to the first position."""
    after = _rr_by_id(merged.after.families)
    assert after["fam_b"].children == [_S]
    assert after["fam_d"].children == [_S, "child_c"]
    assert any(c.code == "duplicate_child" and "fam_b" in c.message for c in merged.plan.warnings)


def test_reference_rule_family_parent_child_links_child(merged):
    """M + collapse: the child side is rewritten and equal links collapse."""
    links = [(l.child_id, l.parent_id, l.parentage_type)
             for l in _rr_by_id(merged.after.families)["fam_b"].parent_child_links]
    assert links == [(_S, "person_4", "biological"), (_S, "person_5", "biological")]
    d_links = _rr_by_id(merged.after.families)["fam_d"].parent_child_links
    assert (_S, "person_7", "biological") in [(l.child_id, l.parent_id, l.parentage_type) for l in d_links]
    # Different parentage types stay separate (one warning per pair).
    outcome = collapse_parent_child_links(
        [ParentChildLink(_S, "person_4", "biological"), ParentChildLink(_R, "person_4", "adopted")],
        _R, _S,
    )
    assert [l.parentage_type for l in outcome.links] == ["biological", "adopted"]
    assert outcome.type_conflicts == [(_S, "person_4", ("biological", "adopted"))]


def test_reference_rule_family_parent_child_links_parent(merged):
    """M + collapse: the parent side is rewritten; None (unknown donor) is left alone."""
    a_links = _rr_by_id(merged.after.families)["fam_a"].parent_child_links
    assert sorted((l.child_id, l.parent_id) for l in a_links) == [
        ("child_a", _S), ("child_a", "person_3")]
    d_links = _rr_by_id(merged.after.families)["fam_d"].parent_child_links
    donor = [l for l in d_links if l.parent_id is None]
    assert [(l.child_id, l.parentage_type) for l in donor] == [(_S, "unknown_donor")]
    # A child equal to its own parent after the rewrite is a Blocking_Conflict.
    data = copy.deepcopy(merged.before_data)
    data.families.append(_P29Family(
        "fam_self", [_P29Partner(_R, "partner"), _P29Partner("person_3", "partner")], [_S],
        [ParentChildLink(_S, _R, "biological")]))
    plan = build_plan(data, merged.before_translation,
                      MergeDecisions(_S, _R, survivor_id=_S, survivor_confirmed=True))
    assert any(c.code == "self_parent_child" and c.is_blocking for c in plan.conflicts)


def test_reference_rule_family_event_ids(merged):
    """S: event ids of a family are not person ids and stay unchanged."""
    before = _rr_by_id(merged.before_data.families)
    after = _rr_by_id(merged.after.families)
    assert after["fam_a"].event_ids == before["fam_a"].event_ids == ["ev_marr"]
    assert "ev_marr" in _rr_by_id(merged.after.events)


# --- events and residences --------------------------------------------------


def test_reference_rule_event_participants(merged):
    """M + collapse: same person and role collapse; different roles need a choice."""
    after = _rr_by_id(merged.after.events)
    assert [(p.person_id, p.role) for p in after["ev_birth"].participants] == [(_S, "child")]
    assert [(p.person_id, p.role) for p in after["ev_wit"].participants] == [
        (_S, "witness"), ("person_3", "child")]
    assert [(p.person_id, p.role) for p in after["ev_roles"].participants] == [(_S, "father")]
    # Without the role choice the plan is blocked and asks for the role.
    plan = _rr_plan_without_choices(merged)
    assert "participant_role:ev_roles" in _rr_unresolved(plan)
    assert any(c.code == "participant_role" and c.is_blocking for c in plan.conflicts)
    assert not plan.can_execute


def test_reference_rule_residence_person(merged):
    """R + none: reassigned, never collapsed, also when date and place are equal."""
    after = merged.after.residences
    assert [(r.id, r.person_id, r.place_id) for r in after] == [
        ("res_1", _S, "place_1"), ("res_2", _S, "place_1")]
    assert after[0].observations == after[1].observations == merged.before_data.residences[0].observations


def test_reference_rule_residence_refs(merged):
    """S: source references and observations are unchanged."""
    before = _rr_by_id(merged.before_data.residences)
    after = _rr_by_id(merged.after.residences)
    for rid in ("res_1", "res_2"):
        assert after[rid].observations == before[rid].observations
        assert after[rid].observations[0].source_ref.source_id == "s1"


# --- person attributes ------------------------------------------------------


def test_reference_rule_person_profile_media_id(merged):
    """E: both non-empty and different, the user chooses."""
    assert "profile_media_id" in _rr_unresolved(_rr_plan_without_choices(merged))
    survivor = _rr_by_id(merged.after.persons)[_S]
    assert survivor.profile_media_id == "m_s"
    other = merged.before_data.persons[1].profile_media_id
    plan = _rr_plan_without_choices(merged, profile_media_id=other)
    assert "profile_media_id" not in _rr_unresolved(plan)
    assert plan.change_set.replaced["persons"][_S].profile_media_id == other


def test_reference_rule_person_sex(merged):
    """E: two different known values need a choice; U counts as unknown."""
    data = copy.deepcopy(merged.before_data)
    next(p for p in data.persons if p.id == _R).sex = "M"
    plan = build_plan(data, merged.before_translation,
                      MergeDecisions(_S, _R, survivor_id=_S, survivor_confirmed=True))
    assert "sex" in _rr_unresolved(plan)
    assert any(c.code == "sex_conflict" and c.is_blocking for c in plan.conflicts)
    chosen = build_plan(data, merged.before_translation,
                        MergeDecisions(_S, _R, survivor_id=_S, survivor_confirmed=True, sex="M"))
    assert "sex" not in _rr_unresolved(chosen)
    assert chosen.change_set.replaced["persons"][_S].sex == "M"
    next(p for p in data.persons if p.id == _R).sex = "U"
    unknown = build_plan(data, merged.before_translation,
                         MergeDecisions(_S, _R, survivor_id=_S, survivor_confirmed=True))
    assert "sex" not in _rr_unresolved(unknown)
    assert unknown.change_set.replaced["persons"][_S].sex == "F"
    assert _rr_by_id(merged.after.persons)[_S].sex == "F"


def test_reference_rule_person_title_occupation(merged):
    """E: title moves when only one is set; differing occupations need a choice."""
    unresolved = _rr_unresolved(_rr_plan_without_choices(merged))
    assert "occupation" in unresolved and "title" not in unresolved
    survivor = _rr_by_id(merged.after.persons)[_S]
    assert survivor.title == "Dr"
    assert survivor.occupation == "Lektor"
    # The other person's value can be chosen as well.
    plan = _rr_plan_without_choices(merged, occupation_from=_R)
    assert plan.change_set.replaced["persons"][_S].occupation == "Smed"


def test_reference_rule_person_notes(merged):
    """M: keep survivor's, keep other's, or concatenate with a visible separator."""
    notes = _rr_by_id(merged.after.persons)[_S].notes
    assert "Överlevande" in notes and "Avförd" in notes and notes != "ÖverlevandeAvförd"
    for mode, expected in (("keep_survivor", "Överlevande"), ("keep_other", "Avförd")):
        plan = _rr_plan_without_choices(merged, notes_mode=mode)
        assert plan.change_set.replaced["persons"][_S].notes == expected


def test_reference_rule_person_names(merged):
    """M + collapse: exact duplicates collapse; other names stay."""
    survivor = _rr_by_id(merged.after.persons)[_S]
    assert [(n.type, n.given, n.surname) for n in survivor.names] == [
        ("birth", "Anna", "Berg"), ("alias", "Annika", "Lind")]
    # Same string with a different type stays.
    from slaktbusken.services.merge_rules import union_names

    kept = union_names([Name("birth", "Anna", "Berg")], [Name("alias", "Anna", "Berg")])
    assert len(kept) == 2


def test_reference_rule_person_names_event_id(merged):
    """S: the event id of a name is not a person id and is unchanged."""
    data = copy.deepcopy(merged.before_data)
    next(p for p in data.persons if p.id == _R).names.append(
        Name("married", "Anna", "Ek", event_id="ev_marr"))
    plan = build_plan(data, merged.before_translation, _rr_decisions())
    names = plan.change_set.replaced["persons"][_S].names
    assert [n.event_id for n in names if n.surname == "Ek"] == ["ev_marr"]


# --- media and research notes ------------------------------------------------


def test_reference_rule_media_linked_entities(merged):
    """M + collapse: duplicate person links collapse; the role is the first non-empty."""
    links = _rr_by_id(merged.after.media)["m_1"].linked_entities
    assert [(l.entity_type, l.entity_id, l.role) for l in links] == [
        ("person", _S, "fotograf"), ("place", "place_1", "")]


def test_reference_rule_media_mentioned_person_ids(merged):
    """M + collapse: duplicates collapse to the first position."""
    assert _rr_by_id(merged.after.media)["m_1"].mentioned_person_ids == [_S, "person_3"]


def test_reference_rule_media_annotations(merged):
    """R + none: kept as separate entries; a warning for two regions of one person."""
    annotations = _rr_by_id(merged.after.media)["m_1"].annotations
    assert [(a.entity_id, a.x) for a in annotations] == [(_S, 0.1), (_S, 0.5)]
    assert any(c.code == "annotation_same_person" for c in merged.plan.warnings)


def test_reference_rule_media_mentioned_names(merged):
    """S: free-text names are unchanged."""
    assert _rr_by_id(merged.after.media)["m_1"].mentioned_names == ["Anna Berg"]


def test_reference_rule_research_note_linked_entities(merged):
    """M + collapse: duplicates collapse to one per note."""
    links = _rr_by_id(merged.after.research_notes)["n_1"].linked_entities
    assert [(l.entity_type, l.entity_id) for l in links] == [("person", _S)]
    assert _rr_by_id(merged.after.research_notes)["n_1"].text == f"om {_R}"


# --- DNA --------------------------------------------------------------------


def test_reference_rule_dna_profile_person(merged):
    """R + none: profiles are never merged; the count is unchanged."""
    after = _rr_by_id(merged.after.dna_profiles)
    assert len(merged.after.dna_profiles) == len(merged.before_data.dna_profiles) == 3
    assert after["dna_r"].person_id == _S and after["dna_s"].person_id == _S


def test_reference_rule_dna_profile_admin_person(merged):
    """R: replaced when equal to the retired id; others unchanged."""
    after = _rr_by_id(merged.after.dna_profiles)
    assert after["dna_r"].admin_person_id == _S
    assert after["dna_x"].admin_person_id == _S
    assert after["dna_s"].admin_person_id is None


def test_reference_rule_dna_cluster_person_ids(merged):
    """M + collapse: duplicate collapses; the order of the others is preserved."""
    assert _rr_by_id(merged.after.dna_clusters)["cl_1"].person_ids == [_S, "person_3", "person_4"]


def test_reference_rule_dna_profile_match_refs(merged):
    """S: profile and match ids are unchanged; a match joining one person warns."""
    assert merged.after.dna_matches == merged.before_data.dna_matches
    match = merged.after.dna_matches[0]
    assert (match.profile1_id, match.profile2_id) == ("dna_r", "dna_s")
    assert any(c.code == "dna_match_same_person" for c in merged.plan.warnings)


# --- research ----------------------------------------------------------------


def test_reference_rule_research_case_entities(merged):
    """M + collapse: primary reference and links are rewritten; duplicates collapse."""
    case = _rr_by_id(merged.after.research_cases)["case_1"]
    assert (case.primary_entity_ref.entity_type, case.primary_entity_ref.entity_id) == ("person", _S)
    # Collapsed across primary and linked together: the primary holds the survivor once.
    assert case.linked_entities == []
    assert merged.plan.research.links_rewired + merged.plan.research.links_collapsed > 0


def test_reference_rule_research_hypothesis_entities(merged):
    """M + collapse: same helper as for cases."""
    hyp = _rr_by_id(merged.after.research_hypotheses)["hyp_1"]
    assert [(l.entity_type, l.entity_id) for l in hyp.linked_entities] == [
        ("person", _S), ("person", "person_3")]


def test_reference_rule_research_action_none(merged):
    """S: actions hold no person ids and are unchanged."""
    assert merged.after.research_actions == merged.before_data.research_actions
    assert not any("person" in f.name for f in _rr_fields(_RRAction))


# --- project-level ------------------------------------------------------------


def test_reference_rule_project_main_person_id(merged):
    """R: set to the survivor when equal to the retired id."""
    assert merged.before_data.project.main_person_id == _R
    assert merged.after.project.main_person_id == _S
    assert merged.reloaded.project.main_person_id == _S


def test_reference_rule_project_connection_overrides(merged):
    """E: both with different values, the user chooses; the retired key is removed."""
    assert "connection_override" in _rr_unresolved(_rr_plan_without_choices(merged))
    assert merged.after.connection_overrides == {_S: _RR_CONNECTION}
    plan = _rr_plan_without_choices(merged, connection_override="o_retired")
    assert plan.change_set.scalars["connection_overrides"] == {_S: "o_retired"}
    # Only the retired value: it moves to the survivor.
    data = copy.deepcopy(merged.before_data)
    data.connection_overrides = {_R: "o_retired"}
    moved = build_plan(data, merged.before_translation, _rr_decisions())
    assert moved.change_set.scalars["connection_overrides"] == {_S: "o_retired"}


# --- merge candidates and history ----------------------------------------------


def test_reference_rule_merge_candidate_persons(merged):
    """special: redirect, collision or archive; one candidate per unordered pair."""
    active = merged.after.merge_candidates
    assert all(_R not in (c.person_1_id, c.person_2_id) for c in active)
    pairs = [frozenset((c.person_1_id, c.person_2_id)) for c in active]
    assert len(pairs) == len(set(pairs))
    assert frozenset((_S, "person_3")) in pairs and frozenset((_S, "person_4")) in pairs
    assert all(_S != c.person_1_id or _S != c.person_2_id for c in active)  # no self pair
    entry = next(h for h in merged.after.merge_history if h.merged_person_id == _R)
    archived_ids = {a.id for a in entry.archived_candidates}
    assert "cand_3" in archived_ids  # the self pair
    assert len(active) + len(archived_ids) >= len(merged.before_data.merge_candidates)
    assert "cc_1" in {c.id for a in entry.archived_candidates for c in a.comments} | {
        c.id for cand in active for c in cand.comments}


def test_reference_rule_merge_history_persons(merged):
    """H: earlier entries are never rewritten; the new entry names the pair."""
    old = _rr_by_id(merged.after.merge_history)["merge_old"]
    assert old == merged.before_data.merge_history[0]
    assert (old.surviving_person_id, old.merged_person_id) == (_R, "person_8")
    new = next(h for h in merged.after.merge_history if h.merged_person_id == _R)
    assert new.surviving_person_id == _S


def test_reference_rule_merge_history_archived_candidates(merged):
    """H: archived candidates keep their original ids."""
    old = _rr_by_id(merged.after.merge_history)["merge_old"]
    assert [(a.id, a.person_1_id, a.person_2_id) for a in old.archived_candidates] == [
        ("cand_old", _R, "person_8")]
    new = next(h for h in merged.after.merge_history if h.merged_person_id == _R)
    originals = {c.id: (c.person_1_id, c.person_2_id) for c in merged.before_data.merge_candidates}
    for archived in new.archived_candidates:
        assert (archived.person_1_id, archived.person_2_id) == originals[archived.id]


# --- translation ----------------------------------------------------------------


def test_reference_rule_translation_person_mappings(merged):
    """special: mappings of the retired person move to identity_aliases."""
    assert [m.app_id for m in merged.after_translation.persons] == ["person_3"]
    moved = [a for a in merged.after_translation.person_aliases if a.gedcom_id == "@I2@"]
    assert [(a.person_id, a.fingerprint) for a in moved] == [(_S, "fp2")]
    entry = next(h for h in merged.after.merge_history if h.merged_person_id == _R)
    assert moved[0].merge_id == entry.id


def test_reference_rule_translation_identity_aliases(merged):
    """R: earlier aliases pointing at the retired person point at the survivor."""
    earlier = [a for a in merged.after_translation.person_aliases if a.gedcom_id == "@I9@"]
    assert [(a.person_id, a.merge_id) for a in earlier] == [(_S, "merge_0")]
    assert all(a.person_id != _R for a in merged.after_translation.person_aliases)


def test_reference_rule_translation_family_mappings(merged):
    """S: family ids; a merge does not combine families."""
    assert merged.after_translation.families == merged.before_translation.families
    assert [f.app_id for f in merged.after_translation.families] == ["fam_a"]


# --- settings and free-form dicts -------------------------------------------------


def _rr_person_reference_field_names(cls, seen=None) -> set[str]:
    seen = set() if seen is None else seen
    if cls in seen or not _rr_is_dc(cls):
        return set()
    seen.add(cls)
    names: set[str] = set()
    hints = _rr_get_type_hints(cls)
    for f in _rr_fields(cls):
        if "person_id" in f.name or f.name.endswith("_person_ref"):
            names.add(f.name)
        stack = [hints.get(f.name)]
        while stack:
            hint = stack.pop()
            if hint is None:
                continue
            names |= _rr_person_reference_field_names(hint, seen)
            stack.extend(_rr_get_args(hint))
    return names


def test_reference_rule_settings_none(merged):
    """S: neither settings file stores a person id, and the merge leaves them alone."""
    from slaktbusken.persistence.app_settings_io import AppSettings
    from slaktbusken.persistence.settings_io import ProjectSettings

    assert _rr_person_reference_field_names(ProjectSettings) == set()
    assert _rr_person_reference_field_names(AppSettings) == set()
    assert merged.settings_after == merged.settings_before
    assert _R.encode() not in merged.settings_after


def test_reference_rule_media_publication_dates(merged):
    """S: free-form dicts without person ids are unchanged."""
    before = _rr_by_id(merged.before_data.media)["m_1"]
    after = _rr_by_id(merged.after.media)["m_1"]
    assert after.publication == before.publication == {"title": "Bok", "text": _R}
    assert after.photo_date == before.photo_date == {"year": 1900}


# --- completeness --------------------------------------------------------------------


def _rr_test_name(key: str) -> str:
    return "test_reference_rule_" + key.replace(".", "_")


def test_every_inventory_row_has_a_rule_test():
    module = _rr_sys.modules[__name__]
    names = [_rr_test_name(loc.key) for loc in _p29_pri.PERSON_REFERENCE_INVENTORY]
    assert len(names) == len(set(names)), "two inventory keys map to one test name"
    missing = [
        loc.key for loc in _p29_pri.PERSON_REFERENCE_INVENTORY
        if not callable(getattr(module, _rr_test_name(loc.key), None))
    ]
    assert missing == [], f"Inventory rows without a rule test: {missing}"


def test_rewire_rows_leave_no_retired_reference(merged):
    rewire = [loc for loc in _p29_pri.PERSON_REFERENCE_INVENTORY if loc.rule == "R"]
    assert rewire
    before = _p29_pri.PersonReferenceIndex.build(
        merged.before_data, [_R], merged.before_translation)
    after = _p29_pri.PersonReferenceIndex.build(merged.after, [_R], merged.after_translation)
    reloaded = _p29_pri.PersonReferenceIndex.build(merged.reloaded, [_R], merged.after_translation)
    for loc in rewire:
        assert before.count(loc.key, _R) > 0, f"{loc.key}: the fixture has no reference"
        assert after.count(loc.key, _R) == 0, f"{loc.key} still refers to the retired person"
        assert reloaded.count(loc.key, _R) == 0, f"{loc.key} (reloaded)"
    # Every row that needs a handler is clean, not only the rewrite rows.
    for loc in _p29_pri.PERSON_REFERENCE_INVENTORY:
        if loc.requires_handler:
            assert after.count(loc.key, _R) == 0, loc.key
