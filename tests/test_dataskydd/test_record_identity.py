"""Properties 14 and 15 plus the named examples for the record identity matcher.

Covers ``gedcom/translation/record_identity.py`` (record hash and
``match_records``) and the importer paths that set and respect
``Event.origin`` and ``ResidenceFact.origins`` (Requirements 10.1, 19.2 to
19.8, 19.12, 19.13, 22.2 to 22.9, 22.27, 22.28, 22.30, 22.31).
"""

from __future__ import annotations

import copy
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.gedcom.importer import GEDCOMImporter
from slaktbusken.gedcom.parser import parse_gedcom
from slaktbusken.gedcom.translation.record_identity import (
    IncomingRecord,
    Outcome,
    PoolEntry,
    build_origin_groups,
    event_fingerprint,
    match_records,
    record_hash,
    residence_fingerprint,
    tag_key_of,
)
from slaktbusken.gedcom.translation.record_identity_golden import (
    GOLDEN_VECTORS,
    build_record,
)
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.record_origin import RecordOrigin, origin_key
from slaktbusken.model.residence import Endpoint, ResidenceFact
from tests.test_dataskydd.strategies_gedcom import (
    DEFAULT_SOURCE_IDS,
    MatcherScenario,
    add_whitespace_noise,
    change_date,
    change_note,
    change_place,
    change_tag,
    change_tracking_noise,
    first_source_xref,
    gedcom_records,
    matcher_scenarios,
    renumber_sources,
    reorder_distinct_tags,
    swap_first_two,
)

pytestmark = pytest.mark.mandatory_integrity

U = Outcome

# ---------------------------------------------------------------------------
# Property 15: the record hash
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(rec_ids=gedcom_records(), rnd=st.randoms(use_true_random=False))
def test_dp_property_15_hash_ignores_harmless_differences(rec_ids, rnd) -> None:
    """**Validates: Requirements 19.3, 22.3**"""
    record, ids = rec_ids
    base = record_hash(record, ids)
    assert record_hash(add_whitespace_noise(record, rnd), ids) == base
    assert record_hash(change_tracking_noise(record, rnd), ids) == base
    assert record_hash(reorder_distinct_tags(record, rnd), ids) == base
    renumbered, new_ids = renumber_sources(record, ids, rnd)
    assert record_hash(renumbered, new_ids) == base
    combined, combined_ids = renumber_sources(record, ids, rnd)
    combined = change_tracking_noise(
        reorder_distinct_tags(add_whitespace_noise(combined, rnd), rnd), rnd
    )
    assert record_hash(combined, combined_ids) == base


@settings(max_examples=200, deadline=None)
@given(rec_ids=gedcom_records(min_sources=1))
def test_dp_property_15_hash_sensitive_to_meaningful_differences(rec_ids) -> None:
    """**Validates: Requirements 19.3, 22.3**"""
    record, ids = rec_ids
    base = record_hash(record, ids)
    assert record_hash(change_tag(record), ids) != base
    assert record_hash(change_date(record), ids) != base
    assert record_hash(change_place(record), ids) != base
    assert record_hash(change_note(record), ids) != base
    # A resolved source id changes while the xref stays.
    xref = first_source_xref(record)
    assert xref is not None
    assert record_hash(record, {**ids, xref: "src-other"}) != base
    # A different source pointer resolves to a different id.
    other = copy.deepcopy(record)
    sour = next(c for c in other.children if c.tag == "SOUR")
    sour.value = next(x for x in ids if x != sour.value)
    assert record_hash(other, ids) != base


@settings(max_examples=200, deadline=None)
@given(rec_ids=gedcom_records(min_notes=2))
def test_dp_property_15_hash_sensitive_to_order_of_repeated_notes(rec_ids) -> None:
    """**Validates: Requirements 19.3, 22.3**"""
    record, ids = rec_ids
    assert record_hash(swap_first_two(record, "NOTE"), ids) != record_hash(record, ids)


@settings(max_examples=200, deadline=None)
@given(rec_ids=gedcom_records(min_sources=2))
def test_dp_property_15_hash_sensitive_to_order_of_repeated_sources(rec_ids) -> None:
    """**Validates: Requirements 19.3, 22.3**"""
    record, ids = rec_ids
    assert record_hash(swap_first_two(record, "SOUR"), ids) != record_hash(record, ids)


def _rec(*lines: str):
    return build_record(tuple(lines))


_IDS = {"@S1@": "src-0001", "@S2@": "src-0002"}


def test_record_hash_ignores_change_tracking_tags() -> None:
    base = _rec("1 BIRT", "2 DATE 1850", "2 PLAC Stockholm")
    noisy = _rec(
        "1 BIRT",
        "2 CHAN",
        "3 DATE 1 JAN 2020",
        "2 DATE 1850",
        "2 _UPD 5 MAY 2021",
        "2 PLAC Stockholm",
        "2 _CRE 1 JAN 2000",
        "2 _UID ABC",
    )
    assert record_hash(noisy, {}) == record_hash(base, {})


def test_record_hash_ignores_order_of_distinct_tags() -> None:
    a = _rec("1 BIRT", "2 DATE 1850", "2 PLAC Stockholm", "2 NOTE x", "3 CONT y")
    b = _rec("1 BIRT", "2 NOTE x", "3 CONT y", "2 PLAC Stockholm", "2 DATE 1850")
    assert record_hash(a, {}) == record_hash(b, {})
    # at depth
    c = _rec("1 BIRT", "2 SOUR @S1@", "3 PAGE 1", "3 DATA", "2 PLAC X")
    d = _rec("1 BIRT", "2 PLAC X", "2 SOUR @S1@", "3 DATA", "3 PAGE 1")
    assert record_hash(c, _IDS) == record_hash(d, _IDS)


def test_record_hash_keeps_order_of_repeated_tags() -> None:
    a = _rec("1 BIRT", "2 NOTE first", "2 DATE 1850", "2 NOTE second")
    b = _rec("1 BIRT", "2 NOTE second", "2 DATE 1850", "2 NOTE first")
    assert record_hash(a, {}) != record_hash(b, {})
    c = _rec("1 BIRT", "2 SOUR @S1@", "2 SOUR @S2@")
    d = _rec("1 BIRT", "2 SOUR @S2@", "2 SOUR @S1@")
    assert record_hash(c, _IDS) != record_hash(d, _IDS)


def test_record_hash_stable_under_source_renumbering() -> None:
    a = _rec("1 BIRT", "2 SOUR @S1@", "3 PAGE 4", "2 SOUR @S2@")
    b = _rec("1 BIRT", "2 SOUR @S17@", "3 PAGE 4", "2 SOUR @S3@")
    assert record_hash(a, _IDS) == record_hash(b, {"@S17@": "src-0001", "@S3@": "src-0002"})
    assert record_hash(b, {"@S17@": "src-0002", "@S3@": "src-0001"}) != record_hash(a, _IDS)


def test_record_hash_golden_vectors() -> None:
    assert len(GOLDEN_VECTORS) == 4
    for vector in GOLDEN_VECTORS:
        assert record_hash(build_record(vector.lines), vector.source_ids) == vector.expected, (
            vector.name
        )


def test_residence_record_hash_ignores_change_tracking_tags() -> None:
    base = _rec("1 RESI", "2 DATE 1870", "2 PLAC Uppsala")
    noisy = _rec(
        "1 RESI", "2 PLAC Uppsala", "2 _UID U1", "2 CHAN", "3 DATE 1 JAN 2020", "2 DATE 1870",
        "2 _UPD 1 JAN 2020",
    )
    assert record_hash(noisy, {}) == record_hash(base, {})


def test_residence_record_hash_resolves_source_pointers() -> None:
    a = _rec("1 RESI", "2 PLAC Uppsala", "2 SOUR @S1@")
    b = _rec("1 RESI", "2 PLAC Uppsala", "2 SOUR @S9@")
    assert record_hash(a, _IDS) == record_hash(b, {"@S9@": "src-0001"})
    assert record_hash(a, _IDS) != record_hash(b, {"@S9@": "src-0002"})


def test_residence_record_hash_sensitive_to_date_place_and_sources() -> None:
    base = _rec("1 RESI", "2 DATE 1870", "2 PLAC Uppsala", "2 SOUR @S1@")
    h = record_hash(base, _IDS)
    assert record_hash(_rec("1 RESI", "2 DATE 1871", "2 PLAC Uppsala", "2 SOUR @S1@"), _IDS) != h
    assert record_hash(_rec("1 RESI", "2 DATE 1870", "2 PLAC Malmö", "2 SOUR @S1@"), _IDS) != h
    assert record_hash(_rec("1 RESI", "2 DATE 1870", "2 PLAC Uppsala", "2 SOUR @S2@"), _IDS) != h
    assert record_hash(_rec("1 RESI", "2 DATE 1870", "2 PLAC Uppsala"), _IDS) != h
    assert record_hash(_rec("1 RESI", "2 DATE 1870", "2 PLAC Uppsala", "2 SOUR @S1@",
                            "2 NOTE n"), _IDS) != h


# ---------------------------------------------------------------------------
# Helpers for hand-written matcher cases
# ---------------------------------------------------------------------------


def incoming(tag="BIRT", h="h1", uid=None, index=0, fp="fp", owner="P1", kind="event",
             owner_kind="INDI"):
    return IncomingRecord(
        kind=kind, owner_kind=owner_kind, owner_id=owner, owner_xref="@I1@", tag_key=tag,
        index=index, record_hash=h, uid=uid, fingerprint=lambda: fp,
    )


def origin(tag="BIRT", h="h1", uid=None, instance=0, owner="P1", index=0, xref="@I1@",
           owner_kind="INDI"):
    return RecordOrigin(owner_kind, owner, xref, tag, index, h, uid, instance)


def event(eid, ev_origin=None, etype="birth", date="1850", place="pl1"):
    return Event(
        id=eid, type=etype, participants=[Participant("P1", "subject")],
        date=DateValue(value=date, precision="year"), place=PlaceRef(place_id=place),
        origin=ev_origin,
    )


def residence(rid, *origins, place="pl1", start="1850"):
    return ResidenceFact(
        id=rid, person_id="P1", place_id=place,
        start=Endpoint(earliest=start, latest=start), origins=list(origins),
    )


def entries(*objs):
    out = []
    for o in objs:
        for og in ([o.origin] if isinstance(o, Event) else o.origins):
            out.append(PoolEntry(o, og))
    return out


def ids_of(members):
    return [m.id for m in members]


# ---------------------------------------------------------------------------
# Property 14: the matcher
# ---------------------------------------------------------------------------


def _obj_tag(obj) -> str:
    return "RESI" if isinstance(obj, ResidenceFact) else tag_key_of(obj)


def _obj_fp(obj) -> str:
    return residence_fingerprint(obj) if isinstance(obj, ResidenceFact) else event_fingerprint(obj)


def _eligible(res, group) -> bool:
    rec = res.incoming
    if {id(m) for m in group.members} != {id(m) for m in res.members}:
        return False
    uid_hit = bool(rec.uid) and group.key[5] == rec.uid
    hash_hit = group.key[2] == rec.tag_key and group.key[3] == rec.record_hash
    if res.outcome is U.UNCHANGED:
        return (uid_hit and group.key[3] == rec.record_hash) or hash_hit
    return uid_hit and group.key[3] != rec.record_hash


def _assign_distinct_groups(claims, groups) -> bool:
    """Whether every group claim can be given its own group of valid evidence."""
    taken: set[int] = set()

    def go(i: int) -> bool:
        if i == len(claims):
            return True
        for gi, g in enumerate(groups):
            if gi not in taken and _eligible(claims[i], g):
                taken.add(gi)
                if go(i + 1):
                    return True
                taken.discard(gi)
        return False

    return go(0)


def check_matcher_properties(scn: MatcherScenario, built, results, snapshot) -> None:
    """Compare ``match_records`` output with a simple reference model."""
    assert len(results) == len(built.incoming)
    assert all(r.incoming is i for r, i in zip(results, built.incoming))
    assert snapshot == (built.pool, built.legacy, built.foreign)  # nothing altered
    if not built.legacy:
        assert built.fingerprint_calls == []

    groups = build_origin_groups(built.pool)
    foreign_ids = {id(o) for o in built.foreign}
    legacy_ids = {id(o) for o in built.legacy}
    claimed_legacy: set[int] = set()
    claims = []
    for r in results:
        member_ids = {id(m) for m in r.members}
        assert not member_ids & foreign_ids
        if r.outcome in (U.UNCHANGED, U.CHANGED_UID):
            assert r.members and not member_ids & legacy_ids
            claims.append(r)
        elif r.outcome is U.LEGACY_CLAIMED:
            (obj,) = r.members
            assert id(obj) in legacy_ids and id(obj) not in claimed_legacy
            claimed_legacy.add(id(obj))
            assert r.incoming.fingerprint() == _obj_fp(obj)
        else:
            assert r.members == []
    assert _assign_distinct_groups(claims, groups)

    # k identical records and m groups pair min(k, m); a group counts once.
    if all(r.incoming.uid is None for r in results):
        k = Counter((r.incoming.tag_key, r.incoming.record_hash) for r in results)
        m = Counter((g.key[2], g.key[3]) for g in groups)
        unchanged = Counter(
            (r.incoming.tag_key, r.incoming.record_hash)
            for r in results
            if r.outcome is U.UNCHANGED
        )
        for key, count in k.items():
            assert unchanged[key] == min(count, m[key])

    # Candidates of unclaimed same-tag objects.
    everything: dict[int, object] = {}
    for obj in [e.obj for e in built.pool] + built.legacy + built.foreign:
        everything[id(obj)] = obj
    claimed_ids = {id(m) for r in results for m in r.members}
    for r in results:
        same_tag = {i for i, o in everything.items() if _obj_tag(o) == r.incoming.tag_key}
        lower = same_tag - claimed_ids
        if r.outcome is U.NEW:
            assert not lower
        if r.outcome in (U.NEW, U.NEW_AMBIGUOUS, U.LEGACY_CLAIMED):
            assert r.instance is not None
        if r.outcome is U.NEW_AMBIGUOUS:
            cand = {id(c) for c in r.candidates}
            assert cand and lower <= cand <= same_tag - claimed_legacy
        else:
            assert r.candidates == []

    # Instances: smallest unused value, distinct within one call.
    used: dict[tuple, set[int]] = defaultdict(set)
    for g in groups:
        used[(g.key[2], g.key[3])].add(g.key[4])
    for r in results:
        if r.outcome in (U.NEW, U.NEW_AMBIGUOUS, U.LEGACY_CLAIMED):
            key = (r.incoming.tag_key, r.incoming.record_hash)
            expected = next(n for n in range(100) if n not in used[key])
            assert r.instance == expected
            used[key].add(expected)


def _run(scn: MatcherScenario, **order):
    built = scn.build(**order)
    snapshot = copy.deepcopy((built.pool, built.legacy, built.foreign))
    results = match_records(built.incoming, built.pool, built.legacy, built.foreign)
    return built, snapshot, results


@settings(max_examples=300, deadline=None)
@given(scn=matcher_scenarios())
def test_dp_property_14_matcher_claims_at_most_once_on_identity_evidence(scn) -> None:
    """**Validates: Requirements 10.1, 19.4, 19.5, 19.6, 19.7, 19.12, 19.13, 22.4, 22.5, 22.9, 22.27, 22.28, 22.30, 22.31**"""
    built, snapshot, results = _run(scn)
    check_matcher_properties(scn, built, results, snapshot)


@settings(max_examples=300, deadline=None)
@given(scn=matcher_scenarios(kind="event"))
def test_dp_property_14_event_pools(scn) -> None:
    """**Validates: Requirements 19.5, 19.6, 19.13**"""
    built, snapshot, results = _run(scn)
    check_matcher_properties(scn, built, results, snapshot)


@settings(max_examples=300, deadline=None)
@given(scn=matcher_scenarios(kind="residence"))
def test_dp_property_14_residence_pools(scn) -> None:
    """**Validates: Requirements 22.5, 22.27, 22.28, 22.31**"""
    built, snapshot, results = _run(scn)
    check_matcher_properties(scn, built, results, snapshot)


@settings(max_examples=200, deadline=None)
@given(scn=matcher_scenarios(unique_uids=True), data=st.data())
def test_dp_property_14_reordering_keeps_results(scn, data) -> None:
    """**Validates: Requirements 19.5, 22.5**"""
    _, _, base = _run(scn)
    pool_n = len(scn.build().pool)
    pool_order = data.draw(st.permutations(range(pool_n)))
    in_order = data.draw(st.permutations(range(len(scn.incoming))))
    for order in ({"pool_order": list(pool_order)}, {"incoming_order": list(in_order)}):
        _, _, other = _run(scn, **order)
        assert Counter(r.outcome for r in other) == Counter(r.outcome for r in base)


@settings(max_examples=200, deadline=None)
@given(scn=matcher_scenarios(kind="event", with_uids=False))
def test_matcher_property_no_duplicates_no_merges(scn) -> None:
    """**Validates: Requirements 19.5, 19.6**"""
    built, _, results = _run(scn)
    seen: set[int] = set()
    for r in results:
        for m in r.members:
            assert id(m) not in seen  # no object answers for two records
            seen.add(id(m))
    groups = build_origin_groups(built.pool)
    k = Counter((r.incoming.tag_key, r.incoming.record_hash) for r in results)
    m = Counter((g.key[2], g.key[3]) for g in groups)
    created = sum(1 for r in results if r.outcome in (U.NEW, U.NEW_AMBIGUOUS))
    claimed = sum(1 for r in results if r.outcome in (U.UNCHANGED, U.LEGACY_CLAIMED))
    assert created + claimed == len(results)
    assert sum(1 for r in results if r.outcome is U.UNCHANGED) == sum(
        min(c, m[key]) for key, c in k.items()
    )


# ---------------------------------------------------------------------------
# Matcher examples (events)
# ---------------------------------------------------------------------------


def test_matcher_order_uid_hash_legacy() -> None:
    g_uid = event("e1", origin(h="old", uid="U1"))
    g_hash = event("e2", origin(h="h2", instance=0))
    legacy = event("e3", None, date="1900")
    recs = [
        incoming(h="new", uid="U1"),                  # step 1: uid, hash differs
        incoming(h="h2"),                             # step 2: tag key and hash
        incoming(h="h3", fp=event_fingerprint(legacy)),   # step 3: legacy fingerprint
        incoming(h="h4", fp="unknown"),                # nothing
    ]
    res = match_records(recs, entries(g_uid, g_hash), [legacy], [])
    assert [r.outcome for r in res] == [
        U.CHANGED_UID, U.UNCHANGED, U.LEGACY_CLAIMED, U.NEW,
    ]
    assert res[0].members == [g_uid] and res[1].members == [g_hash]
    assert res[2].members == [legacy]
    # The uid claim wins over a hash match on another group.
    other = event("e4", origin(h="h1", uid="U9"))
    target = event("e5", origin(h="zzz", uid="U7"))
    res = match_records([incoming(h="h1", uid="U7")], entries(other, target), [], [])
    assert res[0].outcome is U.CHANGED_UID and res[0].members == [target]


def test_matcher_claims_once() -> None:
    e = event("e1", origin(h="h1"))
    res = match_records([incoming(), incoming()], entries(e), [], [])
    assert [r.outcome for r in res] == [U.UNCHANGED, U.NEW_AMBIGUOUS] or [
        r.outcome for r in res
    ] == [U.UNCHANGED, U.NEW]
    assert res[1].members == []
    legacy = event("e2", None)
    fp = event_fingerprint(legacy)
    res = match_records([incoming(h="a", fp=fp), incoming(h="b", fp=fp)], [], [legacy], [])
    assert [r.outcome for r in res] == [U.LEGACY_CLAIMED, U.NEW]


def test_matcher_never_claims_by_tag_and_index() -> None:
    e = event("e1", origin(h="old", index=0))
    res = match_records([incoming(h="new", index=0)], entries(e), [], [])
    assert res[0].outcome is U.NEW_AMBIGUOUS and res[0].members == []
    assert res[0].candidates == [e]


def test_matcher_legacy_fingerprint_one_to_one() -> None:
    a, b = event("e1", None), event("e2", None)
    fp = event_fingerprint(a)
    assert fp == event_fingerprint(b)
    res = match_records([incoming(h=f"h{i}", fp=fp) for i in range(3)], [], [a, b], [])
    assert [r.outcome for r in res] == [U.LEGACY_CLAIMED, U.LEGACY_CLAIMED, U.NEW]
    assert {id(res[0].members[0]), id(res[1].members[0])} == {id(a), id(b)}
    # Equal legacy objects are never grouped: each claim returns one object.
    assert all(len(r.members) <= 1 for r in res)


def test_matcher_never_matches_on_type_and_place_alone() -> None:
    legacy = event("e1", None, etype="birth", date="1850", place="pl1")
    template = event("t", None, etype="birth", date="1851", place="pl1")
    res = match_records(
        [incoming(h="h", fp=event_fingerprint(template))], [], [legacy], []
    )
    assert res[0].outcome is U.NEW_AMBIGUOUS and res[0].candidates == [legacy]
    assert res[0].members == []


def test_matcher_owner_id_survives_xref_renumbering() -> None:
    e = event("e1", origin(h="h1", xref="@I1@"))
    renumbered = IncomingRecord(
        kind="event", owner_kind="INDI", owner_id="P1", owner_xref="@I500@", tag_key="BIRT",
        index=9, record_hash="h1", uid=None, fingerprint=lambda: "fp",
    )
    res = match_records([renumbered], entries(e), [], [])
    assert res[0].outcome is U.UNCHANGED and res[0].members == [e]
    # Same xref but another owner id claims nothing, even with the pool object.
    other = IncomingRecord(
        kind="event", owner_kind="INDI", owner_id="P2", owner_xref="@I1@", tag_key="BIRT",
        index=0, record_hash="h1", uid=None, fingerprint=lambda: "fp",
    )
    res = match_records([other], entries(e), [], [])
    assert res[0].outcome is U.NEW and res[0].members == []


def test_origin_instance_assigned_smallest_unused() -> None:
    a = event("e1", origin(h="h", instance=0))
    b = event("e2", origin(h="h", instance=2))
    res = match_records([incoming(h="h") for _ in range(5)], entries(a, b), [], [])
    assert [r.outcome for r in res[:2]] == [U.UNCHANGED, U.UNCHANGED]
    assert [r.instance for r in res[2:]] == [1, 3, 4]
    # Different hash or tag key do not use up instances.
    res = match_records([incoming(h="x"), incoming(h="x"), incoming(tag="DEAT", h="h")], entries(a, b), [], [])
    assert [r.instance for r in res] == [0, 1, 0]


def test_matcher_origin_group_claimed_once_as_a_whole() -> None:
    a = event("e1", origin(h="h"))
    b = event("e2", copy.deepcopy(a.origin))
    res = match_records([incoming(h="h"), incoming(h="h")], entries(a, b), [], [])
    assert res[0].outcome is U.UNCHANGED and ids_of(res[0].members) == ["e1", "e2"]
    assert res[1].outcome is not U.UNCHANGED and res[1].members == []


def test_matcher_distinguishes_origin_group_from_ambiguity() -> None:
    a = event("e1", origin(h="h"))
    b = event("e2", copy.deepcopy(a.origin))
    # One group of two members: a record for it is unchanged, never ambiguous.
    res = match_records([incoming(h="h")], entries(a, b), [], [])
    assert res[0].outcome is U.UNCHANGED and res[0].candidates == []
    # A different record only lists both members as candidates.
    res = match_records([incoming(h="other")], entries(a, b), [], [])
    assert res[0].outcome is U.NEW_AMBIGUOUS and ids_of(res[0].candidates) == ["e1", "e2"]
    # Two groups (different instance) and one record: one is claimed, one stays.
    c = event("e3", origin(h="h", instance=1))
    res = match_records([incoming(h="h")], entries(a, c), [], [])
    assert res[0].outcome is U.UNCHANGED and ids_of(res[0].members) == ["e1"]
    assert len(build_origin_groups(entries(a, b, c))) == 2


def test_origin_group_split_counts_as_one_record() -> None:
    whole = residence("r1", origin(tag="RESI", h="h"))
    first = copy.deepcopy(whole)
    second = copy.deepcopy(whole)
    second.id = "r2"
    res = match_records([incoming(tag="RESI", h="h", kind="residence")], entries(first, second), [], [])
    assert res[0].outcome is U.UNCHANGED and ids_of(res[0].members) == ["r1", "r2"]
    assert len(build_origin_groups(entries(first, second))) == 1
    # Two identical imports with different instances stay two groups after a split.
    third = residence("r3", origin(tag="RESI", h="h", instance=1))
    fourth = copy.deepcopy(third)
    fourth.id = "r4"
    pool = entries(first, second, third, fourth)
    assert len(build_origin_groups(pool)) == 2
    res = match_records(
        [incoming(tag="RESI", h="h", kind="residence") for _ in range(3)], pool, [], []
    )
    assert [r.outcome for r in res[:2]] == [U.UNCHANGED, U.UNCHANGED]
    assert res[2].outcome is U.NEW and res[2].instance == 2


# ---------------------------------------------------------------------------
# Matcher examples (residences)
# ---------------------------------------------------------------------------


def rincoming(h="h1", uid=None, index=0, fp="fp", owner="P1"):
    return incoming(tag="RESI", h=h, uid=uid, index=index, fp=fp, owner=owner, kind="residence")


def rorigin(h="h1", uid=None, instance=0, owner="P1", index=0, xref="@I1@"):
    return origin(tag="RESI", h=h, uid=uid, instance=instance, owner=owner, index=index, xref=xref)


def test_residence_matcher_claims_pair_once() -> None:
    r = residence("r1", rorigin())
    res = match_records([rincoming(), rincoming()], entries(r), [], [])
    assert res[0].outcome is U.UNCHANGED and res[0].members == [r]
    assert res[1].outcome is not U.UNCHANGED and res[1].members == []
    # A residence with two origins answers for two records, once each.
    both = residence("r2", rorigin(h="a"), rorigin(h="b"))
    res = match_records([rincoming(h="a"), rincoming(h="b"), rincoming(h="a")], entries(both), [], [])
    assert [r_.outcome for r_ in res[:2]] == [U.UNCHANGED, U.UNCHANGED]
    assert res[2].outcome is not U.UNCHANGED


def test_residence_matcher_never_matches_on_date_and_place_alone() -> None:
    legacy = residence("r1", place="pl1", start="1850")
    template = residence("t", place="pl1", start="1850")
    template.notes = "annan anteckning"
    res = match_records(
        [rincoming(h="n", fp=residence_fingerprint(template))], [], [legacy], []
    )
    assert res[0].outcome is U.NEW_AMBIGUOUS and res[0].members == []
    same = residence("t2", place="pl1", start="1850")
    res = match_records([rincoming(h="n", fp=residence_fingerprint(same))], [], [legacy], [])
    assert res[0].outcome is U.LEGACY_CLAIMED and res[0].members == [legacy]


def test_residence_matcher_never_claims_by_tag_and_index() -> None:
    r = residence("r1", rorigin(h="old", index=0))
    res = match_records([rincoming(h="new", index=0)], entries(r), [], [])
    assert res[0].outcome is U.NEW_AMBIGUOUS and res[0].members == []


def test_residence_matcher_owner_id_survives_xref_renumbering() -> None:
    r = residence("r1", rorigin(xref="@I1@"))
    rec = rincoming()
    rec = IncomingRecord(**{**rec.__dict__, "owner_xref": "@I321@", "index": 7})
    assert match_records([rec], entries(r), [], [])[0].outcome is U.UNCHANGED
    other_owner = rincoming(owner="P2")
    assert match_records([other_owner], entries(r), [], [])[0].outcome is U.NEW


# ---------------------------------------------------------------------------
# Importer examples
# ---------------------------------------------------------------------------

_BASE = """0 HEAD
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Anna /Svensson/
1 SEX F
1 BIRT
2 DATE 12 MAR 1850
2 PLAC Stockholm
2 _UID UID-BIRT
1 DEAT
2 DATE 1920
1 EVEN
2 TYPE Flytt
2 DATE 1875
2 PLAC Uppsala
1 RESI
2 DATE FROM 1870 TO 1880
2 PLAC Uppsala
2 _UID UID-RESI
1 RESI
2 DATE 1890
2 PLAC Malmö
0 @I2@ INDI
1 NAME Erik /Svensson/
1 SEX M
0 @F1@ FAM
1 HUSB @I2@
1 WIFE @I1@
1 MARR
2 DATE 1875
2 PLAC Stockholm
0 TRLR
"""


class _Project:
    def __init__(self, tmp_path: Path) -> None:
        self.tdir = tmp_path / "translation"
        self.tdir.mkdir()
        self.dir = tmp_path
        self.data = ProjectData(project=ProjectMetadata(title="T"))
        self.n = 0

    def import_text(self, text: str):
        self.n += 1
        path = self.dir / f"f{self.n}.ged"
        path.write_text(text, encoding="utf-8")
        return GEDCOMImporter(self.data, self.tdir).import_file(path)

    def person_id(self, given: str) -> str:
        return next(p.id for p in self.data.persons if p.names[0].given == given)


def _records_by_tag(text: str) -> dict[str, list]:
    out: dict[str, list] = defaultdict(list)
    for top in parse_gedcom(text).records:
        for child in top.children:
            out[(top.xref_id, child.tag.upper())].append(child)
    return out


def test_origin_set_on_import(tmp_path: Path) -> None:
    proj = _Project(tmp_path)
    proj.import_text(_BASE)
    anna = proj.person_id("Anna")
    records = _records_by_tag(_BASE)
    by_type = {e.type: e for e in proj.data.events}
    birth = by_type["birth"]
    assert birth.origin == RecordOrigin(
        "INDI", anna, "@I1@", "BIRT", 0, record_hash(records[("@I1@", "BIRT")][0], {}),
        "UID-BIRT", 0,
    )
    assert by_type["death"].origin.tag_key == "DEAT" and by_type["death"].origin.uid is None
    assert by_type["flytt"].origin.tag_key == "EVEN:flytt"
    family = proj.data.families[0]
    marriage = by_type["marriage"]
    assert marriage.origin.owner_kind == "FAM" and marriage.origin.owner_id == family.id
    assert marriage.origin.owner_xref == "@F1@" and marriage.origin.tag_key == "MARR"
    assert marriage.origin.record_hash == record_hash(records[("@F1@", "MARR")][0], {})
    # Two separately imported identical records get different instances (19.12).
    twin = _BASE.replace("1 DEAT\n2 DATE 1920\n", "1 DEAT\n2 DATE 1920\n1 DEAT\n2 DATE 1920\n")
    (tmp_path / "twin").mkdir()
    twin_proj = _Project(tmp_path / "twin")
    twin_proj.import_text(twin)
    deaths = [e for e in twin_proj.data.events if e.type == "death"]
    assert sorted(e.origin.instance for e in deaths) == [0, 1]
    assert sorted(e.origin.index for e in deaths) == [0, 1]
    assert len({origin_key(e.origin) for e in deaths}) == 2


def test_residence_origin_set_on_import(tmp_path: Path) -> None:
    proj = _Project(tmp_path)
    result = proj.import_text(_BASE)
    anna = proj.person_id("Anna")
    resis = _records_by_tag(_BASE)[("@I1@", "RESI")]
    assert len(proj.data.residences) == 2 and result.residences_added == 2
    first, second = proj.data.residences
    assert first.origins == [
        RecordOrigin("INDI", anna, "@I1@", "RESI", 0, record_hash(resis[0], {}), "UID-RESI", 0)
    ]
    assert second.origins == [
        RecordOrigin("INDI", anna, "@I1@", "RESI", 1, record_hash(resis[1], {}), None, 0)
    ]
    # Identical RESI records get distinct instances.
    twin_text = _BASE.replace("1 RESI\n2 DATE 1890\n2 PLAC Malmö\n",
                              "1 RESI\n2 DATE 1890\n2 PLAC Malmö\n1 RESI\n2 DATE 1890\n2 PLAC Malmö\n")
    (tmp_path / "twin").mkdir()
    twin = _Project(tmp_path / "twin")
    twin.import_text(twin_text)
    instances = sorted(
        r.origins[0].instance for r in twin.data.residences if r.origins[0].uid is None
    )
    assert instances == [0, 1]


def _snapshot(data: ProjectData):
    return copy.deepcopy((data.events, data.residences))


def test_edited_imported_event_not_modified_by_reimport(tmp_path: Path) -> None:
    proj = _Project(tmp_path)
    proj.import_text(_BASE)
    birth = next(e for e in proj.data.events if e.type == "birth")
    birth.date = DateValue(value="1851-01-02", precision="day")
    birth.place = PlaceRef(place_id="user-place")
    birth.origin.index = 5  # the occurrence index is informational and never rewritten
    before = _snapshot(proj.data)
    result = proj.import_text(_BASE)
    assert result.events_added == 0 and result.residences_added == 0
    assert _snapshot(proj.data) == before
    # Renumbered xrefs: the owner id, not the xref, identifies the owner.
    renumbered = _BASE.replace("@I1@", "@I77@")
    proj.import_text(renumbered)
    assert len(proj.data.events) == len(before[0]) and len(proj.data.residences) == len(before[1])
    assert [e for e in proj.data.events if e.type == "birth"][0].date.value == "1851-01-02"


def test_event_origin_duplicate_on_two_events_is_one_group(tmp_path: Path) -> None:
    proj = _Project(tmp_path)
    proj.import_text(_BASE)
    birth = next(e for e in proj.data.events if e.type == "birth")
    twin = copy.deepcopy(birth)
    twin.id = "event_manual_copy"
    proj.data.events.append(twin)
    assert len(build_origin_groups(entries(birth, twin))) == 1
    before = _snapshot(proj.data)
    result = proj.import_text(_BASE)
    assert result.events_added == 0
    assert _snapshot(proj.data) == before
    # Matcher level: the record claims both and nothing else.
    res = match_records(
        [incoming(h=birth.origin.record_hash, owner=birth.origin.owner_id)],
        entries(birth, twin), [], [],
    )
    assert res[0].outcome is U.UNCHANGED and len(res[0].members) == 2


def test_residence_changed_uid_with_group_leaves_all_members_unchanged(tmp_path: Path) -> None:
    proj = _Project(tmp_path)
    proj.import_text(_BASE)
    keyed = next(r for r in proj.data.residences if r.origins[0].uid == "UID-RESI")
    half = copy.deepcopy(keyed)  # what a split leaves behind
    half.id = "residence_half"
    proj.data.residences.append(half)
    before = _snapshot(proj.data)
    changed = _BASE.replace("2 DATE FROM 1870 TO 1880", "2 DATE FROM 1871 TO 1881")
    result = proj.import_text(changed)
    assert result.residences_added == 0
    assert _snapshot(proj.data) == before
    assert any("_UID" in w for w in result.warnings)
    # Matcher level: both members, outcome CHANGED_UID.
    res = match_records(
        [rincoming(h="changed", uid="UID-RESI", owner=keyed.origins[0].owner_id)],
        entries(keyed, half), [], [],
    )
    assert res[0].outcome is U.CHANGED_UID and len(res[0].members) == 2


_EVENT_ORIGIN_ALLOWED = {
    "slaktbusken/gedcom/importer.py",
    "slaktbusken/gedcom/translation/record_identity.py",
    "slaktbusken/persistence/serialization.py",
    "slaktbusken/model/event.py",
    "slaktbusken/model/validators.py",
    "slaktbusken/model/record_origin.py",
}


def test_event_origin_is_not_copied_by_any_event_operation() -> None:
    root = Path(__file__).resolve().parents[2]
    pattern = re.compile(r"\.origin\s*=(?!=)|\borigin=(?!=)")
    offenders = []
    for path in (root / "slaktbusken").rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if rel in _EVENT_ORIGIN_ALLOWED:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            # residence_edit_ops copy residence ``origins`` only; they say ``origins=``.
            if pattern.search(code) and "origins" not in code:
                offenders.append(f"{rel}:{n}: {line.strip()}")
    assert offenders == []

    # The importer sets an event origin only on a created event or a claimed legacy event.
    source = (root / "slaktbusken/gedcom/importer.py").read_text(encoding="utf-8")
    assert len(re.findall(r"event\.origin\s*=", source)) == 1
    assert len(re.findall(r"\borigin=origin\b", source)) >= 2

    # Editing keeps the one origin on the edited event; a new event gets none.
    from slaktbusken.ui.editors.event_assembler import assemble_event
    from tests.test_dataskydd.strategies_events import form_from_event

    base = event("e1", origin(h="h"))
    saved = assemble_event(base, form_from_event(base), {})
    assert saved.id == base.id and saved.origin == base.origin and saved.origin is not base.origin
    fresh = assemble_event(None, form_from_event(base), {})
    assert fresh.origin is None and fresh.id != base.id
