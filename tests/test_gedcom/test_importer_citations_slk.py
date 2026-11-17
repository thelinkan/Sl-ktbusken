"""Importer side of citations: quality, note, aspects and carrier (task 7.2)."""

from __future__ import annotations

from pathlib import Path

from slaktbusken.model.project import ProjectData
from tests.test_gedcom.test_importer_events_slk import HEAD, _import

SOURCE = "0 @S1@ SOUR\n1 TITL Kyrkbok\n"


def _birt(*cits: str) -> str:
    body = "".join(cits)
    return (
        "0 @I1@ INDI\n1 NAME Anna /X/\n1 BIRT\n2 DATE 1900\n2 PLAC Ljusdal\n"
        + body
    )


def _sour(*children: str) -> str:
    return "2 SOUR @S1@\n" + "".join(f"3 {c}\n" for c in children)


def _birth(data: ProjectData):
    (event,) = [e for e in data.events if e.type == "birth"]
    return event


def test_quay_maps_and_defaults(tmp_path: Path):
    text = HEAD + SOURCE + _birt(
        _sour("QUAY 3"), _sour("QUAY 0"), _sour("QUAY 9"), _sour()
    ) + "0 TRLR\n"
    data, _ = _import(text, tmp_path)
    assert [r.quality for r in _birth(data).source_refs] == [
        "primary", "tertiary", "secondary", "secondary",
    ]


def test_slk_qual_before_quay_note_and_aspects(tmp_path: Path):
    text = HEAD + SOURCE + _birt(
        _sour("QUAY 3", "_SLK_QUAL custom", "NOTE en not", "_SLK_ASP a", "_SLK_ASP b")
    ) + "0 TRLR\n"
    data, _ = _import(text, tmp_path)
    (ref,) = _birth(data).source_refs
    assert (ref.quality, ref.note, ref.aspects) == ("custom", "en not", ["a", "b"])


def test_context_places_citation_in_carrier(tmp_path: Path):
    text = HEAD + SOURCE + _birt(
        _sour("_SLK_CTX date"),
        _sour("_SLK_CTX place"),
        _sour("_SLK_CTX from_place"),
        _sour("_SLK_CTX bogus"),
        _sour(),
    ) + "0 TRLR\n"
    data, _ = _import(text, tmp_path)
    ev = _birth(data)
    assert len(ev.date.source_refs) == 1
    assert len(ev.place.source_refs) == 1
    # no from_place on a birth: falls back to the event, with the invalid and plain ones
    assert len(ev.source_refs) == 3


def test_reimport_creates_nothing(tmp_path: Path):
    text = HEAD + SOURCE + _birt(_sour("_SLK_CTX date", "QUAY 3")) + "0 TRLR\n"
    data, _ = _import(text, tmp_path)
    before = len(data.events)
    data, _ = _import(text, tmp_path, data)
    assert len(data.events) == before
