"""Property 54: Retired ids are redirected.

# Feature: person-comparison-and-merge, Property 54: Retired ids are redirected

*For any* acyclic history and any retired id, ``resolve_person_request``
returns the final surviving person and the retired name; for an id in a cycle
or ambiguous it returns no person; for an active id it returns that id
unchanged. The search index returns the survivor with the label
"Sammanslagen med <namn> (<år–år>)" for a retired id.

**Validates: Requirements 36.13, 36.14**
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from slaktbusken.model.merge_candidate import MergeHistoryEntry
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.person_lookup import resolve_person_request
from slaktbusken.services.person_search import PersonSearchIndex

NAMES = st.sampled_from(["Åsa Öberg", "Anna Berg", "Märta Ström", "Lars Ek"])
SPANS = st.sampled_from(["1829–1890", "", "1700–1760", "1901–"])


@st.composite
def histories(draw):
    """(active ids, history entries) mixing chains, cycles and duplicates."""
    n_active = draw(st.integers(min_value=1, max_value=4))
    active = [f"per_{i}" for i in range(n_active)]
    n_ret = draw(st.integers(min_value=1, max_value=8))
    retired = [f"ret_{i}" for i in range(n_ret)]
    pairs: list[tuple[str, str]] = []
    for i, rid in enumerate(retired):
        kind = draw(st.sampled_from(["active", "later", "any", "none"]))
        if kind == "none":
            continue
        if kind == "active":
            target = draw(st.sampled_from(active))
        elif kind == "later" and i + 1 < n_ret:
            target = retired[draw(st.integers(i + 1, n_ret - 1))]
        else:  # any retired id: may form cycles or self references
            target = draw(st.sampled_from(retired))
        pairs.append((rid, target))
        if draw(st.integers(0, 5)) == 0:  # ambiguous: retired a second time
            pairs.append((rid, draw(st.sampled_from(active + retired))))
    pairs = draw(st.permutations(pairs))
    entries = []
    for seq, (rid, target) in enumerate(pairs, 1):
        entries.append(
            MergeHistoryEntry(
                id=f"merge_{seq}",
                surviving_person_id=target,
                merged_person_id=rid,
                merged_person_name=draw(NAMES),
                merged_person_lifespan=draw(SPANS),
                merge_date=draw(st.sampled_from(["2024-01-01", "2024-02-01"])),
            )
        )
    return active, retired, entries


def _data(active: list[str], entries: list[MergeHistoryEntry]) -> ProjectData:
    data = ProjectData()
    for pid in active:
        data.persons.append(
            Person(id=pid, sex="F", names=[Name("birth", "Karin", "Svensson")])
        )
    data.merge_history = list(entries)
    return data


def _expected(active, entries, start):
    """Independent oracle: final active survivor id or None."""
    targets: dict[str, list[str]] = {}
    for e in entries:
        targets.setdefault(e.merged_person_id, []).append(e.surviving_person_id)
    x, seen = start, set()
    while True:
        if x in active:
            return x
        if x not in targets or len(targets[x]) != 1 or x in seen:
            return None
        seen.add(x)
        x = targets[x][0]


@settings(max_examples=200, deadline=None)
@given(histories())
def test_property_54_lookup(case):
    active, retired, entries = case
    data = _data(active, entries)
    names = {}
    for e in entries:
        names.setdefault(e.merged_person_id, e.merged_person_name)
    for pid in active:
        res = resolve_person_request(data, pid)
        assert (res.person_id, res.redirected_from) == (pid, None)
    for rid in retired:
        res = resolve_person_request(data, rid)
        want = _expected(set(active), entries, rid)
        assert res.person_id == want
        if want is not None and rid in names:
            assert res.redirected_from == rid
            assert res.retired_name == names[rid]
        else:
            assert res.redirected_from is None
    assert resolve_person_request(data, "unknown_id").person_id is None


@settings(max_examples=200, deadline=None)
@given(histories(), st.booleans())
def test_property_54_search_by_retired_id(case, upper):
    active, retired, entries = case
    data = _data(active, entries)
    index = PersonSearchIndex.build(data)
    for rid in retired:
        query = rid.upper() if upper else rid
        results = index.search(query)
        want = _expected(set(active), entries, rid)
        labelled = [r for r in results if r.retired_label]
        if want is None or not any(e.merged_person_id == rid for e in entries):
            assert labelled == []
            continue
        entry = next(e for e in entries if e.merged_person_id == rid)
        assert results[0].person_id == want
        label = f"Sammanslagen med {entry.merged_person_name}"
        if entry.merged_person_lifespan:
            label += f" ({entry.merged_person_lifespan})"
        assert results[0].retired_label == label
        assert [r.person_id for r in results].count(want) == 1
