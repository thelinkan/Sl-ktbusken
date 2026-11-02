"""Property 52: History rows equal the stored entries.

*For any* valid project and any person id, the rows of
``build_history_rows(data, person_id)`` equal ``RedirectResolver.merged_into``
in reverse order, each row shows exactly the stored name, lifespan, id and
date of its entry, and for ``None`` the rows contain every entry in descending
``(merge_date, id suffix)`` order. Cycles and ambiguity disable navigation and
the input is not modified.

**Validates: Requirements 36.2, 36.3, 36.4, 36.16**
"""

from __future__ import annotations

import copy
import re

from hypothesis import given, settings, strategies as st

from slaktbusken.model.merge_candidate import (
    ArchivedCandidate,
    MergeHistoryEntry,
)
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.merge_history_view import build_history_rows

NAMES = st.sampled_from(["Åsa Öberg", "Anna Berg", "Märta Ström", ""])
SPANS = st.sampled_from(["1829–1890", "", "(1901)", "1700–1760"])
DATES = st.sampled_from(["2023-12-31", "2024-01-01", "2024-02-01"])
SUMMARY = st.lists(st.sampled_from(["Namn: 2", "Händelser: 3 ändrade"]), max_size=3)


@st.composite
def histories(draw):
    """(active ids, retired ids, entries): chains, cycles, duplicates, ghosts."""
    active = [f"per_{i}" for i in range(draw(st.integers(1, 4)))]
    n_ret = draw(st.integers(1, 8))
    retired = [f"ret_{i}" for i in range(n_ret)]
    pairs: list[tuple[str, str]] = []
    for i, rid in enumerate(retired):
        kind = draw(st.sampled_from(["active", "later", "any", "ghost", "none"]))
        if kind == "none":
            continue
        if kind == "active":
            target = draw(st.sampled_from(active))
        elif kind == "later" and i + 1 < n_ret:
            target = retired[draw(st.integers(i + 1, n_ret - 1))]
        elif kind == "ghost":
            target = "ghost_x"  # survivor that is not in the project
        else:
            target = draw(st.sampled_from(retired))
        pairs.append((rid, target))
        if draw(st.integers(0, 6)) == 0:  # ambiguous: retired a second time
            pairs.append((rid, draw(st.sampled_from(active + retired))))
    pairs = draw(st.permutations(pairs))
    numbers = draw(
        st.lists(
            st.integers(1, 120),
            min_size=len(pairs),
            max_size=len(pairs),
            unique=True,
        )
    )
    entries = []
    for (rid, target), number in zip(pairs, numbers):
        archived = []
        for k in range(draw(st.integers(0, 2))):
            other = draw(st.sampled_from(active + ["ghost_y"]))
            ids = (rid, other) if draw(st.booleans()) else (other, rid)
            archived.append(
                ArchivedCandidate(
                    id=f"cand_{number}_{k}",
                    person_1_id=ids[0],
                    person_2_id=ids[1],
                    assessment=draw(st.sampled_from(["possible", "rejected"])),
                    enabled=True,
                )
            )
        entries.append(
            MergeHistoryEntry(
                id=f"merge_{number}",
                surviving_person_id=target,
                merged_person_id=rid,
                merged_person_name=draw(NAMES),
                merged_person_lifespan=draw(SPANS),
                merge_date=draw(DATES),
                archived_candidates=archived,
                summary_lines=draw(SUMMARY),
            )
        )
    return active, retired, entries


def _data(active, entries) -> ProjectData:
    data = ProjectData()
    for n, pid in enumerate(active):
        data.persons.append(
            Person(id=pid, sex="F", names=[Name("birth", f"Karin{n}", "Åkesson")])
        )
    data.merge_history = list(entries)
    return data


# --- independent oracle ----------------------------------------------------


def _order_key(entry):
    m = re.search(r"(\d+)$", entry.id)
    return (entry.merge_date, int(m.group(1)), entry.id)


class Oracle:
    def __init__(self, entries):
        self.entries = entries
        targets: dict[str, list[str]] = {}
        for e in entries:
            targets.setdefault(e.merged_person_id, []).append(e.surviving_person_id)
        self.ambiguous = {k for k, v in targets.items() if len(v) > 1}
        self.target = {k: v[0] for k, v in targets.items() if len(v) == 1}

    def final(self, start):
        x, seen = start, set()
        while True:
            if x in self.ambiguous:
                return None
            if x not in self.target:
                return x
            if x in seen:
                return None
            seen.add(x)
            x = self.target[x]

    def scoped(self, person_id):
        picked = [
            e
            for e in self.entries
            if e.merged_person_id not in self.ambiguous
            and self.final(e.merged_person_id) == person_id
            and self.final(e.surviving_person_id) == person_id
        ]
        return sorted(picked, key=_order_key, reverse=True)

    def navigable(self, entry, active):
        if entry.merged_person_id in self.ambiguous:
            return False
        return self.final(entry.surviving_person_id) in active


def _check_row(row, entry):
    assert row.entry_id == entry.id
    assert row.merged_name == entry.merged_person_name
    assert row.merged_lifespan == entry.merged_person_lifespan
    assert row.merged_id == entry.merged_person_id
    assert row.merge_date == entry.merge_date
    assert row.summary_lines == tuple(entry.summary_lines)
    assert [a.candidate_id for a in row.archived] == [
        a.id for a in entry.archived_candidates
    ]


# Feature: person-comparison-and-merge, Property 52: History rows equal the stored entries
@settings(max_examples=200, deadline=None)
@given(histories())
def test_property_52_history_rows(case):
    """Rows equal the stored entries (ordering, scope, navigation, purity).

    **Validates: Requirements 36.2, 36.3, 36.4, 36.16**
    """
    active, retired, entries = case
    data = _data(active, entries)
    before = copy.deepcopy((data.merge_history, data.persons))
    oracle = Oracle(entries)
    by_id = {e.id: e for e in entries}

    # Unscoped: every entry, newest first.
    rows = build_history_rows(data, None)
    want = sorted(entries, key=_order_key, reverse=True)
    assert [r.entry_id for r in rows] == [e.id for e in want]
    for row, entry in zip(rows, want):
        _check_row(row, entry)
        nav = oracle.navigable(entry, set(active))
        assert row.can_navigate is nav
        assert (row.survivor_id is not None) is nav
        if nav:
            assert row.survivor_id == oracle.final(entry.surviving_person_id)
            assert row.survivor_state == "resolved"
        elif entry.merged_person_id in oracle.ambiguous:
            assert row.survivor_state == "ambiguous"
        else:
            assert row.survivor_state != "resolved"

    # Scoped to one person: the entries merged into it, newest first.
    for pid in active + retired + ["ghost_x", "unknown"]:
        scoped = build_history_rows(data, pid)
        expected = oracle.scoped(pid)
        assert [r.entry_id for r in scoped] == [e.id for e in expected]
        for row in scoped:
            _check_row(row, by_id[row.entry_id])
            if pid in active:
                assert row.can_navigate and row.survivor_id == pid

    # Input is not modified.
    assert (data.merge_history, data.persons) == before


def test_property_52_empty_history():
    assert build_history_rows(ProjectData(), None) == []
    assert build_history_rows(ProjectData(), "per_0") == []
