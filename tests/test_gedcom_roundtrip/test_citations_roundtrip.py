"""Citations: Property 8 and the examples of Requirement 6.

Round trips go through ``GEDCOMExporter`` and ``ImportService.run`` into a real
empty project. Persons are labelled ``P<n>`` before the export, because the
importer creates new ids. Sources get new ids too, so a source is identified by
its title (unique in every fixture used here).
"""

from __future__ import annotations

from collections import Counter

import pytest
from hypothesis import given

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef, SourceRef
from slaktbusken.model.event_citations import event_citations
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from tests.test_gedcom_roundtrip import synthetic as syn
from tests.test_gedcom_roundtrip.fixtures import load_mergetest
from tests.test_gedcom_roundtrip.strategies import citation_projects
from tests.test_gedcom_roundtrip.test_events_roundtrip import event_view
from tests.test_gedcom_roundtrip.test_families_roundtrip import (
    export_text,
    import_text,
    label_persons,
)

pytestmark = pytest.mark.mandatory_integrity

_HEAD = "0 HEAD\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def citation_view(data: ProjectData, event: Event) -> tuple:
    """The citations of an event per context, in order, with source titles."""
    titles = {s.id: s.title for s in data.sources}
    per_context: dict[str, list[tuple]] = {}
    for cit in event_citations(event):
        ref = cit.ref
        per_context.setdefault(cit.context.value, []).append(
            (titles[ref.source_id], ref.quality, ref.note, tuple(ref.aspects)))
    return tuple(sorted((c, tuple(v)) for c, v in per_context.items()))


def event_citation_counter(data: ProjectData) -> Counter:
    return Counter((event_view(data, e), citation_view(data, e)) for e in data.events)


def citation_total(data: ProjectData) -> int:
    return sum(len(event_citations(e)) for e in data.events)


def single_event_project(refs: list[SourceRef], with_date: bool = True,
                         with_place: bool = False) -> ProjectData:
    """One birth with ``refs`` at event level (and optionally on date or place)."""
    sources, leverantorer, kalltyper = syn.build_sources()
    event = Event(
        id="event_1", type="birth",
        participants=[Participant("person_1", "subject")],
        source_refs=list(refs),
        date=DateValue("1850-03-04", "day") if with_date else None,
        place=PlaceRef(syn.PLACE_LJUSDAL) if with_place else None)
    return ProjectData(
        persons=[Person(id="person_1", sex="U", names=[Name("birth", "P1", "X")])],
        events=[event], places=syn.build_places(), sources=sources,
        leverantorer=leverantorer, kalltyper=kalltyper)


def imported_refs(text: str) -> tuple[list[SourceRef], list]:
    imported, result = import_text(text)
    event = next(e for e in imported.events if e.type == "birth")
    return [c.ref for c in event_citations(event)], result.warnings


def foreign_file(sour_lines: str) -> str:
    """A file without the SLK marker: one source record, one cited birth."""
    return (_HEAD + "0 @S1@ SOUR\n1 TITL Kyrkbok\n"
            "0 @I1@ INDI\n1 NAME Ada /X/\n1 BIRT\n2 DATE 1 JAN 1900\n"
            "2 SOUR @S1@\n" + sour_lines + "0 TRLR\n")


# ---------------------------------------------------------------------------
# Property 8
# ---------------------------------------------------------------------------


# Feature: gedcom-roundtrip-0-3-0, Property 8: Citations round-trip with context, quality, note and aspects
# **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.12, 6.13, 6.15, 15.5**
@given(citation_projects())
def test_citations_roundtrip_with_context_quality_note_and_aspects(
        data: ProjectData) -> None:
    data = label_persons(data)
    text, _export = export_text(data)
    imported, _result = import_text(text)
    assert citation_total(imported) == citation_total(data)
    got, want = event_citation_counter(imported), event_citation_counter(data)
    assert got == want, (f"only imported: {list((got - want).items())}\n"
                         f"only original: {list((want - got).items())}")


def test_mergetest_date_citations_roundtrip() -> None:
    data = label_persons(load_mergetest())
    refs = [(e.id, c) for e in data.events for c in event_citations(e)]
    assert len(refs) == 5
    assert {c.context.value for _e, c in refs} == {"date"}
    assert {c.ref.quality for _e, c in refs} == {"primary"}
    assert any(c.ref.aspects for _e, c in refs)
    text, _ = export_text(data)
    imported, _ = import_text(text)
    assert citation_total(imported) == 5
    assert event_citation_counter(imported) == event_citation_counter(data)
    for event in imported.events:
        assert event.source_refs == []
        assert all(r.quality == "primary" for r in
                   (event.date.source_refs if event.date else []))


def test_every_quality_text_keeps_its_value() -> None:
    qualities = ["primary", "secondary", "tertiary", "osäker", "Primär källa",
                 "0", "3", "@x", "två\nrader"]
    refs = [SourceRef(syn.SOURCE_HFL if i % 2 else syn.SOURCE_DOP, q,
                      note=f"n{i}", aspects=[f"a{i}"])
            for i, q in enumerate(qualities)]
    text, _ = export_text(single_event_project(refs))
    got, warnings = imported_refs(text)
    assert [r.quality for r in got] == qualities


def test_citation_note_and_aspects_survive_with_source_identity() -> None:
    refs = [SourceRef(syn.SOURCE_DB, "primary", note="Rad 1\nRad 2",
                      aspects=["namn", "ålder"])]
    data = single_event_project(refs, with_place=True)
    data.events[0].date.source_refs = [SourceRef(syn.SOURCE_NEWS, "osäker", "dn", ["år"])]
    data.events[0].place.source_refs = [SourceRef(syn.SOURCE_HFL, "tertiary")]
    text, _ = export_text(data)
    imported, _ = import_text(text)
    assert event_citation_counter(imported) == event_citation_counter(data)


def test_date_citation_without_date_is_stored_at_event_level() -> None:
    text = (_HEAD + "0 @S1@ SOUR\n1 TITL Kyrkbok\n"
            "0 @I1@ INDI\n1 NAME Ada /X/\n1 BIRT\n2 PLAC Ljusdal\n"
            "2 SOUR @S1@\n3 QUAY 3\n3 _SLK_CTX date\n3 _SLK_ASP datum\n"
            "0 TRLR\n")
    imported, result = import_text(text)
    event = next(e for e in imported.events if e.type == "birth")
    assert event.date is None
    assert [(r.quality, r.aspects) for r in event.source_refs] == [
        ("primary", ["datum"])]
    assert not [w for w in result.warnings if "_SLK_CTX" in str(w)]


# ---------------------------------------------------------------------------
# QUAY mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("quality, quay", [
    ("primary", "3"), ("secondary", "2"), ("tertiary", "1")])
def test_quay_written_for_the_three_known_qualities(quality: str, quay: str) -> None:
    text, _ = export_text(single_event_project([SourceRef(syn.SOURCE_HFL, quality)]))
    assert f"3 QUAY {quay}\n" in text
    assert "_SLK_QUAL" not in text
    got, _ = imported_refs(text)
    assert [r.quality for r in got] == [quality]


def test_other_quality_goes_to_slk_qual_without_quay() -> None:
    text, _ = export_text(single_event_project([SourceRef(syn.SOURCE_HFL, "osäker")]))
    assert "3 _SLK_QUAL osäker\n" in text
    assert " QUAY " not in text
    got, _ = imported_refs(text)
    assert [r.quality for r in got] == ["osäker"]


def test_quay_zero_is_read_as_tertiary_and_never_written() -> None:
    text, _ = export_text(single_event_project([SourceRef(syn.SOURCE_HFL, "tertiary")]))
    assert "QUAY 0" not in text
    got, warnings = imported_refs(foreign_file("3 QUAY 0\n"))
    assert [r.quality for r in got] == ["tertiary"]
    assert not [w for w in warnings if "QUAY" in str(w)]


def test_absent_quay_reads_as_secondary_without_warning() -> None:
    got, warnings = imported_refs(foreign_file("3 PAGE s. 4\n"))
    assert [r.quality for r in got] == ["secondary"]
    assert not warnings or not [w for w in warnings if "QUAY" in str(w)]


@pytest.mark.parametrize("quay, quality", [
    ("3", "primary"), ("2", "secondary"), ("1", "tertiary"), ("0", "tertiary")])
def test_foreign_file_quay_maps_without_warning(quay: str, quality: str) -> None:
    got, warnings = imported_refs(foreign_file(f"3 QUAY {quay}\n"))
    assert [r.quality for r in got] == [quality]
    assert not [w for w in warnings if "QUAY" in str(w)]


def test_invalid_quay_gives_secondary_and_a_warning() -> None:
    got, warnings = imported_refs(foreign_file("3 QUAY 7\n"))
    assert [r.quality for r in got] == ["secondary"]
    assert [w for w in warnings if "QUAY" in str(w)]


def test_slk_qual_is_read_before_quay() -> None:
    got, warnings = imported_refs(foreign_file("3 QUAY 3\n3 _SLK_QUAL osäker\n"))
    assert [r.quality for r in got] == ["osäker"]
    assert not [w for w in warnings if "QUAY" in str(w)]


def test_empty_slk_qual_falls_back_to_quay() -> None:
    got, _ = imported_refs(foreign_file("3 QUAY 3\n3 _SLK_QUAL\n"))
    assert [r.quality for r in got] == ["primary"]


# ---------------------------------------------------------------------------
# One test per registry tag of the citation module
# ---------------------------------------------------------------------------


def test_slk_tag_qual() -> None:
    data = single_event_project([SourceRef(syn.SOURCE_HFL, "osäker")])
    text, _ = export_text(data)
    assert text.count("_SLK_QUAL") == 1
    imported, _ = import_text(text)
    assert event_citation_counter(imported) == event_citation_counter(data)


def test_slk_tag_ctx() -> None:
    data = single_event_project([SourceRef(syn.SOURCE_HFL, "primary")], with_place=True)
    data.events[0].date.source_refs = [SourceRef(syn.SOURCE_DOP, "primary")]
    data.events[0].place.source_refs = [SourceRef(syn.SOURCE_DB, "primary")]
    text, _ = export_text(data)
    assert text.count("_SLK_CTX date\n") == 1
    assert text.count("_SLK_CTX place\n") == 1
    assert "_SLK_CTX event" not in text
    imported, _ = import_text(text)
    assert event_citation_counter(imported) == event_citation_counter(data)


def test_slk_tag_ctx_from_place() -> None:
    data = single_event_project([], with_date=True)
    data.events[0].type = "flytt"
    data.events[0].place = PlaceRef(syn.PLACE_GAVLE)
    data.events[0].from_place = PlaceRef(
        syn.PLACE_LJUSDAL, [SourceRef(syn.SOURCE_DOP, "tertiary", "från")])
    text, _ = export_text(data)
    assert text.count("_SLK_CTX from_place\n") == 1
    imported, _ = import_text(text)
    flytt = next(e for e in imported.events if e.type == "flytt")
    assert [(c.context.value, c.ref.quality, c.ref.note)
            for c in event_citations(flytt)] == [("from_place", "tertiary", "från")]


def test_invalid_ctx_gives_event_level_and_a_warning() -> None:
    got, warnings = imported_refs(foreign_file("3 QUAY 3\n3 _SLK_CTX nowhere\n"))
    assert len(got) == 1
    assert [w for w in warnings if "_SLK_CTX" in str(w)]


def test_slk_tag_asp() -> None:
    aspects = ["namn", "ålder", "dag"]
    data = single_event_project([SourceRef(syn.SOURCE_HFL, "primary", "", aspects)])
    text, _ = export_text(data)
    assert text.count("_SLK_ASP ") == 3
    got, _ = imported_refs(text)
    assert [r.aspects for r in got] == [aspects]
