"""Property 23: Redirect resolution.

**Validates: Requirements 28.5, 28.6, 28.7, 28.8**
"""

from __future__ import annotations

import copy

from hypothesis import given, strategies as st

from slaktbusken.model.merge_candidate import MergeHistoryEntry
from slaktbusken.services.redirect_resolution import RedirectResolver


def _entry(seq: int, survivor: str, retired: str, date: str) -> MergeHistoryEntry:
    return MergeHistoryEntry(
        id=f"merge_{seq}",
        surviving_person_id=survivor,
        merged_person_id=retired,
        merged_person_name="N",
        merged_person_lifespan="",
        merge_date=date,
    )


DATES = st.sampled_from(["2024-01-01", "2024-01-02", "2024-02-01"])


@st.composite
def acyclic_histories(draw):
    n = draw(st.integers(min_value=1, max_value=12))
    ids = [f"p{i}" for i in range(n + 1)]
    parent: dict[str, str] = {}
    for i in range(n):
        if draw(st.booleans()):
            # Redirect only to a higher index: guarantees acyclicity.
            j = draw(st.integers(min_value=i + 1, max_value=n))
            parent[ids[i]] = ids[j]
    entries = [
        _entry(k, s, r, draw(DATES)) for k, (r, s) in enumerate(parent.items(), 1)
    ]
    entries = draw(st.permutations(entries))
    return ids, parent, list(entries)


def _final(parent: dict[str, str], x: str) -> str:
    while x in parent:
        x = parent[x]
    return x


@given(acyclic_histories())
def test_acyclic_resolves_to_final_survivor_and_entries_unchanged(data):
    ids, parent, entries = data
    before = copy.deepcopy(entries)
    resolver = RedirectResolver(entries)
    for pid in ids:
        assert resolver.resolve(pid) == _final(parent, pid)
        assert resolver.is_retired(pid) == (pid in parent)
    assert resolver.cycles() == []
    assert resolver.ambiguous_ids() == []
    assert entries == before


@given(acyclic_histories(), st.data())
def test_earlier_entries_unmodified_by_later_merges(data, draw):
    ids, parent, entries = data
    cut = draw.draw(st.integers(min_value=0, max_value=len(entries)))
    prefix = copy.deepcopy(entries[:cut])
    RedirectResolver(entries)
    assert entries[:cut] == prefix


@given(acyclic_histories())
def test_merged_into_ordered_by_date_then_sequence(data):
    ids, parent, entries = data
    resolver = RedirectResolver(entries)
    by_id = {e.id: e for e in entries}
    for pid in ids:
        got = resolver.merged_into(pid)
        expected = sorted(
            (e for e in entries if _final(parent, e.merged_person_id) == pid),
            key=lambda e: (e.merge_date, int(e.id.split("_")[1])),
        )
        assert [e.id for e in got] == [e.id for e in expected]
        assert all(by_id[e.id] is e for e in got)


@given(st.integers(min_value=1, max_value=60))
def test_many_entries_per_survivor(count):
    entries = [_entry(k, "S", f"r{k}", "2024-01-01") for k in range(1, count + 1)]
    resolver = RedirectResolver(entries)
    assert all(resolver.resolve(f"r{k}") == "S" for k in range(1, count + 1))
    assert [e.id for e in resolver.merged_into("S")] == [e.id for e in entries]


@st.composite
def cyclic_histories(draw):
    size = draw(st.integers(min_value=2, max_value=6))
    cyc = [f"c{i}" for i in range(size)]
    tails = draw(st.integers(min_value=0, max_value=4))
    entries = [
        _entry(i + 1, cyc[(i + 1) % size], cyc[i], draw(DATES)) for i in range(size)
    ]
    tail_ids = []
    prev = cyc[0]
    for t in range(tails):
        tid = f"t{t}"
        entries.append(_entry(size + t + 1, prev, tid, draw(DATES)))
        tail_ids.append(tid)
        prev = tid
    # An unrelated acyclic merge must stay resolvable.
    entries.append(_entry(size + tails + 1, "ok_survivor", "ok_retired", "2024-01-01"))
    entries = list(draw(st.permutations(entries)))
    return cyc, tail_ids, entries


@given(cyclic_histories())
def test_cycle_resolves_to_none_is_reported_and_entries_unchanged(data):
    cyc, tail_ids, entries = data
    before = copy.deepcopy(entries)
    resolver = RedirectResolver(entries)
    for pid in cyc + tail_ids:
        assert resolver.resolve(pid) is None
    assert resolver.resolve("ok_retired") == "ok_survivor"
    reported = resolver.cycles()
    assert len(reported) == 1
    assert set(reported[0]) == set(cyc)
    assert entries == before
