"""Persistence of ``MergeHistoryEntry.summary_lines`` (Requirement 36.1)."""

from __future__ import annotations

import json

from slaktbusken.model.merge_candidate import MergeHistoryEntry
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.serialization import deserialize, serialize


def _data(*entries: MergeHistoryEntry) -> ProjectData:
    data = ProjectData(project=ProjectMetadata(title="T"))
    data.merge_history = list(entries)
    return data


def _entry(eid: str = "merge_1", **kw) -> MergeHistoryEntry:
    return MergeHistoryEntry(eid, "p1", "p2", "Åsa Öberg", "1900-1970", "2024-01-02", **kw)


def test_round_trip_swedish_lines_and_order():
    lines = ["2 namn flyttades.", "Åke, Ärlig och Öst: 3 händelser", "0 beslut"]
    other = _entry("merge_2", summary_lines=["Sist"])
    loaded = deserialize(serialize(_data(_entry(summary_lines=lines), other)))
    assert [e.id for e in loaded.merge_history] == ["merge_1", "merge_2"]
    assert loaded.merge_history[0].summary_lines == lines
    assert loaded.merge_history[1].summary_lines == ["Sist"]
    assert not loaded.merge_load_findings


def test_empty_list_is_omitted():
    doc = json.loads(serialize(_data(_entry())))
    assert "summary_lines" not in doc["merge_history"][0]


def test_old_entry_without_key_loads_empty():
    doc = json.loads(serialize(_data(_entry(summary_lines=["x"]))))
    del doc["merge_history"][0]["summary_lines"]
    loaded = deserialize(json.dumps(doc))
    assert loaded.merge_history[0].summary_lines == []
    assert not loaded.merge_load_findings


def test_wrong_typed_summary_lines_kept_and_reported():
    for bad in ("text", 5, ["ok", 3]):
        doc = json.loads(serialize(_data(_entry())))
        doc["merge_history"][0]["summary_lines"] = bad
        loaded = deserialize(json.dumps(doc))
        assert loaded.merge_history[0].summary_lines == bad
        assert any(
            f.kind == "wrong_type" and "summary_lines" in f.fields and f.entry_id == "merge_1"
            for f in loaded.merge_load_findings
        )
