"""Event-level citations are seen by every consumer of the citation helper."""

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.model.event import Event, Participant, SourceRef
from slaktbusken.model.project import ProjectData
from slaktbusken.model.source import Source
from slaktbusken.services.merge_planner import _count_instances
from slaktbusken.services.source_stats import compute_usage_stats, event_cited_sources
from slaktbusken.ui.dialogs.usage_detail_dialog import build_usage_groups


def _event() -> Event:
    return Event(
        id="e1",
        type="birth",
        participants=[Participant(person_id="p1", role="subject")],
        source_refs=[SourceRef(source_id="s1", quality="secondary")],
    )


def test_stats_and_usage_groups_count_event_level_refs() -> None:
    event = _event()
    stats = compute_usage_stats("s1", [event])
    assert stats.event_count == 1
    assert stats.person_ids == ["p1"]
    assert event_cited_sources(event, {"s1": "Källa"}) == [("s1", "Källa")]
    assert build_usage_groups("s1", [event], []) == {"p1": [event]}


def test_merge_planner_counts_event_source_refs() -> None:
    assert _count_instances([_event()], SourceRef) == 1


def test_exporter_writes_event_level_sour_under_event() -> None:
    source = Source(id="s1", title="T", provider="", source_type="")
    exporter = GEDCOMExporter()
    exporter._sources = {"s1": source}
    lines = exporter._write_event_detail("BIRT", _event())
    assert lines[0] == "1 BIRT"
    assert any(line.startswith("2 SOUR ") for line in lines)