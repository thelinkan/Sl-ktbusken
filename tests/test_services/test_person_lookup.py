"""Retired-id lookup and search by retired id (Requirements 36.13, 36.14)."""

from __future__ import annotations

from slaktbusken.model.merge_candidate import MergeHistoryEntry
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.person_lookup import resolve_person_request
from slaktbusken.services.person_search import PersonSearchIndex


def _entry(n: int, survivor: str, retired: str, name="Anna Berg", span="1829–1890"):
    return MergeHistoryEntry(
        id=f"merge_{n}",
        surviving_person_id=survivor,
        merged_person_id=retired,
        merged_person_name=name,
        merged_person_lifespan=span,
        merge_date="2024-01-0%d" % n,
    )


def _data(history, person_ids=("person_1", "person_3")) -> ProjectData:
    data = ProjectData()
    for pid in person_ids:
        data.persons.append(
            Person(id=pid, sex="F", names=[Name("birth", "Karin", "Svensson")])
        )
    data.merge_history = list(history)
    return data


def test_active_id_unchanged():
    result = resolve_person_request(_data([_entry(1, "person_1", "person_2")]), "person_1")
    assert (result.person_id, result.redirected_from) == ("person_1", None)


def test_retired_id_redirects_through_chain():
    data = _data([_entry(1, "person_1", "person_2"), _entry(2, "person_3", "person_1")],
                 person_ids=("person_3",))
    result = resolve_person_request(data, "person_2")
    assert result.person_id == "person_3"
    assert result.redirected_from == "person_2"
    assert result.retired_name == "Anna Berg"


def test_cycle_and_ambiguity_resolve_nothing():
    cyc = _data([_entry(1, "person_b", "person_a"), _entry(2, "person_a", "person_b")])
    assert resolve_person_request(cyc, "person_a").person_id is None
    assert resolve_person_request(cyc, "person_b").person_id is None
    amb = _data([_entry(1, "person_1", "person_9"), _entry(2, "person_3", "person_9")])
    assert resolve_person_request(amb, "person_9").person_id is None
    assert resolve_person_request(amb, "person_unknown").person_id is None


def test_search_by_retired_id_returns_survivor_with_label():
    index = PersonSearchIndex.build(_data([_entry(1, "person_1", "person_2")]))
    results = index.search("PERSON_2")
    assert results[0].person_id == "person_1"
    assert results[0].retired_label == "Sammanslagen med Anna Berg (1829–1890)"
    assert "Sammanslagen med Anna Berg (1829–1890)" in results[0].display_text


def test_search_unchanged_without_match_and_for_cycles():
    plain = PersonSearchIndex.build(_data([]))
    with_hist = PersonSearchIndex.build(_data([_entry(1, "person_1", "person_2")]))
    assert plain.search("karin") == with_hist.search("karin")
    cyc = PersonSearchIndex.build(
        _data([_entry(1, "person_b", "person_a"), _entry(2, "person_a", "person_b")])
    )
    assert cyc.search("person_a") == []
