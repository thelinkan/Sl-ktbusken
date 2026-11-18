"""Static guard for event citations (Requirement 13.8).

Consumers must obtain event citations through ``model.event_citations``
instead of reading ``.source_refs`` of an event, date or place themselves.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.mandatory_integrity

_PACKAGE = Path(__file__).resolve().parents[2] / "slaktbusken"

# Path prefixes (posix, relative to slaktbusken/) where reads are allowed.
_ALLOWED_PREFIXES = (
    "model/",  # includes model/event_citations.py, the helper itself
    "services/research_",  # ResearchAction.source_refs readers
)

# Exact modules where reads are allowed.
_ALLOWED_MODULES = {
    "persistence/serialization.py": "serialization of all source_refs fields",
    "reports/research_consistency.py": "reads ResearchAction.source_refs",
    "ui/editors/research_case_editor.py": "edits ResearchAction.source_refs",
}

# Temporary entries. Each must be removed by the named task.
_TEMPORARY_ALLOWED: dict[str, str] = {}


def _is_allowed(rel: str) -> bool:
    return (
        rel.startswith(_ALLOWED_PREFIXES)
        or rel in _ALLOWED_MODULES
        or rel in _TEMPORARY_ALLOWED
    )


def _reads_of_source_refs(tree: ast.AST) -> list[int]:
    """Line numbers of reads: Attribute in Load context, or getattr by name."""
    lines: list[int] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "source_refs"
            and isinstance(node.ctx, ast.Load)
        ):
            lines.append(node.lineno)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == "source_refs"
        ):
            lines.append(node.lineno)
    return lines


def test_guard_no_direct_source_refs_reads() -> None:
    violations: list[str] = []
    for path in sorted(_PACKAGE.rglob("*.py")):
        rel = path.relative_to(_PACKAGE).as_posix()
        if _is_allowed(rel):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for line in _reads_of_source_refs(tree):
            violations.append(f"{rel}:{line}")
    assert not violations, (
        "Direct reads of .source_refs outside the allowed modules; use "
        "model.event_citations instead: " + ", ".join(violations)
    )


def test_guard_detects_a_read_and_ignores_a_write() -> None:
    read = ast.parse("x = event.source_refs\ny = getattr(d, 'source_refs')")
    write = ast.parse("event.source_refs = []")
    assert _reads_of_source_refs(read) == [1, 2]
    assert _reads_of_source_refs(write) == []


# ---------------------------------------------------------------------------
# Helper and consumer tests (task 3.4)
# Validates: Requirements 12.4, 12.5, 12.7, 13.1 to 13.7, 13.9
# ---------------------------------------------------------------------------

import re
from types import SimpleNamespace

from hypothesis import given, settings

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.gedcom.importer import GEDCOMImporter
from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.event_citations import (
    CitationContext,
    cited_source_ids,
    event_citations,
    event_cites_source,
)
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.source import Source
from slaktbusken.reports.ansedel import _add_sources_section
from slaktbusken.reports.content import EmptyStateBlock, ListBlock, ReportContent
from slaktbusken.reports.kallrapport import _collect_source_usage
from slaktbusken.services.comparison_session import _event_items
from slaktbusken.services.merge_planner import _count_instances
from slaktbusken.services.source_stats import compute_usage_stats, event_cited_sources
from slaktbusken.services.validation_service import ValidationService, _IdSets
from slaktbusken.ui.dialogs.usage_detail_dialog import build_usage_groups
from slaktbusken.ui.editors.source_editor import SourceEditor
from tests.test_dataskydd.strategies import cited_event_lists, cited_events

_ALL_IDS = [f"source_{n}" for n in range(1, 51)] + ["source_999"]


def _event(
    *,
    event=(),
    date=(),
    place=(),
    from_place=(),
    with_date_value: bool = True,
) -> Event:
    """An event with the given SourceRefs in each location."""
    return Event(
        id="event_1",
        type="birth",
        participants=[Participant("person_1", "self")],
        date=DateValue("1900", "year", list(date)) if (with_date_value or date) else None,
        place=PlaceRef("place_1", list(place)),
        from_place=PlaceRef("place_2", list(from_place)),
        source_refs=list(event),
    )


def _ref(source_id: str = "source_1", quality: str = "primary", note: str = "") -> SourceRef:
    return SourceRef(source_id, quality, note)


def _four_context_event() -> Event:
    return _event(
        event=[_ref("source_1")],
        date=[_ref("source_2")],
        place=[_ref("source_3")],
        from_place=[_ref("source_4")],
    )


def _project(events: list[Event]) -> ProjectData:
    return ProjectData(project=ProjectMetadata(title="T"), events=events)


def _expected_ids(events: list[Event]) -> set[str]:
    ids: set[str] = set()
    for event in events:
        for ref in event.source_refs:
            ids.add(ref.source_id)
        for holder in (event.date, event.place, event.from_place):
            if holder is not None:
                ids.update(r.source_id for r in holder.source_refs)
    return ids


def _id_sets_without_sources() -> _IdSets:
    return _IdSets(
        person_ids={"person_1"},
        place_ids={f"place_{n}" for n in range(1, 51)},
    )


# --- Property 5 -------------------------------------------------------------


# Feature: data-integrity-0-3-0, Property 5: The citation helper returns every reference exactly once
@settings(max_examples=100, deadline=None)
@given(event=cited_events())
def test_dp_property_5_helper_returns_every_reference_exactly_once(event: Event) -> None:
    """**Validates: Requirements 13.1, 13.2**"""
    found = event_citations(event)
    holders = {
        CitationContext.EVENT: event.source_refs,
        CitationContext.DATE: event.date.source_refs if event.date else [],
        CitationContext.PLACE: event.place.source_refs if event.place else [],
        CitationContext.FROM_PLACE: event.from_place.source_refs if event.from_place else [],
    }
    assert len(found) == sum(len(refs) for refs in holders.values())
    for context, refs in holders.items():
        in_context = [c.ref for c in found if c.context == context]
        assert len(in_context) == len(refs)
        # The stored objects themselves, once each, in stored order.
        assert all(a is b for a, b in zip(in_context, refs))
    assert cited_source_ids(event) == _expected_ids([event])
    for source_id in _ALL_IDS:
        assert event_cites_source(event, source_id) == (source_id in cited_source_ids(event))


# --- Property 6 -------------------------------------------------------------


# Feature: data-integrity-0-3-0, Property 6: Consumers agree on cited sources and keep distinct citation contexts
@settings(max_examples=100, deadline=None)
@given(events=cited_event_lists())
def test_dp_property_6_consumers_agree_on_cited_sources(events: list[Event]) -> None:
    """**Validates: Requirements 13.3, 13.4, 13.5, 13.6**"""
    expected = _expected_ids(events)
    data = _project(events)

    # Source usage statistics.
    stats_ids = {s for s in _ALL_IDS if compute_usage_stats(s, events).event_count > 0}
    assert stats_ids == expected

    # Usage dialog grouping.
    dialog_ids = {s for s in _ALL_IDS if build_usage_groups(s, events, [])}
    assert dialog_ids == expected

    # Source deletion check.
    editor = SimpleNamespace(_project_data=data)
    delete_ids = {
        s for s in _ALL_IDS if SourceEditor._find_referencing_events(editor, s)
    }
    assert delete_ids == expected

    # Per-event cited sources.
    listed = {s for e in events for s, _title in event_cited_sources(e)}
    assert listed == expected

    # Kallrapport.
    assert set(_collect_source_usage(data)) == expected

    # Ansedel: sources are unknown here, so each id is listed as unknown.
    report = ReportContent(title="Ansedel")
    _add_sources_section(report, "person_1", data)
    block = report.blocks[-1]
    if expected:
        assert isinstance(block, ListBlock)
        assert set(block.items) == {f"[Okänd källa: {s}]" for s in expected}
    else:
        assert isinstance(block, EmptyStateBlock)

    # Validation: sources are missing, so every cited id is reported.
    service = ValidationService()
    reported: set[str] = set()
    for event in events:
        for err in service._validate_event(event, _id_sets_without_sources()):
            match = re.search(r"source_id '(source_\d+)' refererar", err.message)
            if match:
                reported.add(match.group(1))
    assert reported == expected

    # GEDCOM export: every context, from-place included, is written as SOUR
    # (the context travels in _SLK_CTX).
    exporter = GEDCOMExporter()
    exporter._sources = {
        s: Source(id=s, title=s, provider="", source_type="") for s in _ALL_IDS
    }
    exported: set[str] = set()
    exportable: set[str] = set()
    for event in events:
        lines = exporter._write_event_detail("BIRT", event)
        exported.update(ln[len("2 SOUR "):] for ln in lines if ln.startswith("2 SOUR "))
        exportable |= {c.ref.source_id for c in event_citations(event)}
    assert exported == {exporter._to_gedcom_id(s) for s in exportable}

    # Comparison: every item carries the event's cited ids.
    for event in events:
        if event.date is None:
            continue
        items = _event_items([event], {})
        assert len(items) == 1
        assert set(items[0].sources) == cited_source_ids(event)


# Feature: data-integrity-0-3-0, Property 6 (unique-source report part)
@settings(max_examples=100, deadline=None)
@given(events=cited_event_lists(max_size=1))
def test_dp_property_6_unique_source_report_lists_distinct_entries(
    events: list[Event],
) -> None:
    """**Validates: Requirement 13.7**"""
    usage = _collect_source_usage(_project(events))
    for source_id, entries in usage.items():
        distinct = {
            (
                c.context.value,
                c.ref.quality,
                c.ref.note,
                tuple(c.ref.aspects),
            )
            for e in events
            for c in event_citations(e)
            if c.ref.source_id == source_id
        }
        got = [
            (e["context"], e.get("quality", ""), e.get("note", ""), tuple(e.get("aspects", ())))
            for e in entries
        ]
        assert len(got) == len(set(got))
        assert set(got) == distinct


# --- Examples ---------------------------------------------------------------


def test_event_citations_returns_all_locations_once() -> None:
    event = _four_context_event()
    found = event_citations(event)
    assert [(c.context, c.ref.source_id) for c in found] == [
        (CitationContext.EVENT, "source_1"),
        (CitationContext.DATE, "source_2"),
        (CitationContext.PLACE, "source_3"),
        (CitationContext.FROM_PLACE, "source_4"),
    ]
    assert found[0].ref is event.source_refs[0]
    assert cited_source_ids(event) == {"source_1", "source_2", "source_3", "source_4"}
    assert event_citations(Event("e", "birth", [])) == []


def test_consumers_agree_on_cited_sources() -> None:
    event = _four_context_event()
    for source_id in ("source_1", "source_2", "source_3", "source_4"):
        assert compute_usage_stats(source_id, [event]).event_count == 1
        assert build_usage_groups(source_id, [event], []) == {"person_1": [event]}
    assert compute_usage_stats("source_9", [event]).event_count == 0
    assert [s for s, _ in event_cited_sources(event)] == [
        "source_1", "source_2", "source_3", "source_4",
    ]
    assert set(_collect_source_usage(_project([event]))) == cited_source_ids(event)


@pytest.mark.parametrize(
    "location", ["event", "date", "place", "from_place"]
)
def test_source_delete_refused_for_every_context(location: str) -> None:
    """The delete check finds the event whatever location holds the citation."""
    event = _event(**{location: [_ref("source_7")]})
    editor = SimpleNamespace(_project_data=_project([event]))
    assert SourceEditor._find_referencing_events(editor, "source_7") == [event]
    assert SourceEditor._find_referencing_events(editor, "source_8") == []


def test_unique_source_report_keeps_distinct_contexts() -> None:
    same = _ref("source_1", "primary", "n")
    event = _event(
        event=[same, SourceRef("source_1", "primary", "n")],  # identical, same context
        date=[SourceRef("source_1", "primary", "n")],  # other context
        place=[SourceRef("source_1", "secondary", "n")],  # other quality
    )
    entries = _collect_source_usage(_project([event]))["source_1"]
    assert len(entries) == 3
    assert {(e["context"], e["quality"]) for e in entries} == {
        ("event", "primary"), ("date", "primary"), ("place", "secondary"),
    }


def test_validation_reports_context() -> None:
    event = _event(event=[_ref("source_1")], from_place=[_ref("source_2")])
    errors = ValidationService()._validate_event(event, _id_sets_without_sources())
    messages = [e.message for e in errors if "source_id" in e.message]
    assert len(messages) == 2
    assert any("event.source_refs[0]" in m and "Händelse" in m for m in messages)
    assert any("from_place.source_refs[0]" in m and "Från plats" in m for m in messages)


def test_merge_counts_event_level_refs() -> None:
    event = _four_context_event()
    assert _count_instances([event], SourceRef) == 4
    assert _count_instances([_event(event=[_ref(), _ref("source_2")])], SourceRef) == 2


def test_comparison_uses_all_citation_contexts() -> None:
    event = _four_context_event()
    items = _event_items([event], {})
    assert len(items) == 1
    assert set(items[0].sources) == {"source_1", "source_2", "source_3", "source_4"}


_IMPORT_GEDCOM = """\
0 HEAD
1 CHAR UTF-8
0 @S1@ SOUR
1 TITL Husförhör
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
1 BIRT
2 PLAC Ljusdal
2 SOUR @S1@
1 DEAT
2 DATE 1 JAN 1900
2 SOUR @S1@
0 TRLR
"""


def test_importer_event_level_sour_without_date(tmp_path: Path) -> None:
    tdir = tmp_path / "translation"
    tdir.mkdir()
    ged = tmp_path / "t.ged"
    ged.write_text(_IMPORT_GEDCOM, encoding="utf-8")
    data = ProjectData(project=ProjectMetadata(title="T"))

    GEDCOMImporter(data, tdir).import_file(ged)

    source_id = data.sources[0].id
    birth = next(e for e in data.events if e.type == "birth")
    assert birth.date is None
    assert [r.source_id for r in birth.source_refs] == [source_id]
    death = next(e for e in data.events if e.type == "death")
    assert [r.source_id for r in death.source_refs] == [source_id]
    assert death.date is not None and death.date.source_refs == []


def test_exporter_event_level_sour() -> None:
    event = _event(event=[_ref("source_1")], with_date_value=False)
    event.date = None
    event.place = None
    exporter = GEDCOMExporter()
    exporter._sources = {"source_1": Source(id="source_1", title="T", provider="", source_type="")}
    lines = exporter._write_event_detail("BIRT", event)
    assert lines[0] == "1 BIRT"
    assert f"2 SOUR {exporter._to_gedcom_id('source_1')}" in lines
