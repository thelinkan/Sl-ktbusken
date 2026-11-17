"""Exporter side of citations (task 7.1): QUAY, _SLK_QUAL, _SLK_CTX, NOTE, _SLK_ASP."""

from __future__ import annotations

from pathlib import Path

import pytest

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.gedcom.slk_tags import SLK_TAG_REGISTRY as SLK_TAGS
from slaktbusken.model.event import (
    DateValue, Event, Participant, PlaceRef, SourceRef,
)
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import Observation, ResidenceFact
from slaktbusken.model.source import Source


def _export(event: Event | None, tmp_path: Path, residences=None) -> list[str]:
    data = ProjectData(
        format="släktbuske-file",
        version="0.2",
        project=ProjectMetadata(title="T"),
        persons=[Person(
            id="person_1",
            names=[Name(type="birth", given="Anders", surname="Svensson")],
            sex="M",
        )],
        families=[],
        events=[event] if event else [],
        residences=residences or [],
        places=[
            Place(id="place_1", name="Ljusdal", type="socken"),
            Place(id="place_2", name="Delsbo", type="socken"),
        ],
        sources=[Source(id="source_1", provider="p", source_type="t", title="Kyrkbok")],
    )
    GEDCOMExporter().export(data, tmp_path / "t.ged")
    return (tmp_path / "t.ged").read_text(encoding="utf-8").splitlines()


def _event(event_type: str = "birth", **kw) -> Event:
    return Event(
        id="event_1",
        type=event_type,
        participants=[Participant(person_id="person_1", role="primary")],
        **kw,
    )


def _sour_block(lines: list[str], start: int = 0) -> list[str]:
    idx = next(i for i in range(start, len(lines)) if lines[i] == "2 SOUR @S1@")
    block = []
    for line in lines[idx + 1:]:
        if int(line.split(" ", 1)[0]) <= 2:
            break
        block.append(line)
    return block


@pytest.mark.parametrize(
    "quality,quay", [("primary", "3"), ("secondary", "2"), ("tertiary", "1")]
)
def test_quay_mapping(tmp_path: Path, quality: str, quay: str) -> None:
    ev = _event(source_refs=[SourceRef("source_1", quality)])
    block = _sour_block(_export(ev, tmp_path))
    assert f"3 QUAY {quay}" in block
    assert not any("_SLK_QUAL" in l for l in block)


def test_other_quality_goes_to_slk_qual_without_quay(tmp_path: Path) -> None:
    ev = _event(source_refs=[SourceRef("source_1", "original")])
    block = _sour_block(_export(ev, tmp_path))
    assert "3 _SLK_QUAL original" in block
    assert not any(" QUAY" in l for l in block)


def test_empty_quality_writes_nothing_and_never_quay_0(tmp_path: Path) -> None:
    ev = _event(source_refs=[SourceRef("source_1", "")])
    lines = _export(ev, tmp_path)
    block = _sour_block(lines)
    assert not any("QUAY" in l or "_SLK_QUAL" in l for l in block)
    assert "3 QUAY 0" not in lines


def test_contexts_note_aspects_and_text(tmp_path: Path) -> None:
    ref = SourceRef("source_1", "primary", note="Sida 4\nrad 2", aspects=["a", "b"])
    ev = _event(
        date=DateValue(value="1870", precision="year", source_refs=[ref]),
        place=PlaceRef("place_1", source_refs=[SourceRef("source_1", "secondary")]),
        source_refs=[SourceRef("source_1", "tertiary")],
    )
    lines = _export(ev, tmp_path)
    ctxs = [l for l in lines if "_SLK_CTX" in l]
    assert ctxs == ["3 _SLK_CTX date", "3 _SLK_CTX place"]
    date_block = _sour_block(lines, lines.index("1 BIRT"))
    # the event-level citation comes first and has no _SLK_CTX
    assert "3 QUAY 1" in date_block and not any("_SLK_CTX" in l for l in date_block)
    idx = lines.index("3 _SLK_CTX date")
    tail = lines[idx - 1: idx + 8]
    assert tail[:2] == ["3 QUAY 3", "3 _SLK_CTX date"]
    assert tail[2:6] == ["3 NOTE Sida 4", "4 CONT rad 2", "3 _SLK_ASP a", "3 _SLK_ASP b"]
    assert tail[6].startswith("3 TEXT ")


def test_flytt_from_place_citation_is_written(tmp_path: Path) -> None:
    ev = _event(
        "flytt",
        place=PlaceRef("place_1"),
        from_place=PlaceRef("place_2", source_refs=[SourceRef("source_1", "primary")]),
    )
    lines = _export(ev, tmp_path)
    assert "3 _SLK_CTX from_place" in lines
    assert "3 QUAY 3" in lines


def test_observation_citation_keeps_observation_note(tmp_path: Path) -> None:
    obs = Observation(
        SourceRef("source_1", "secondary", note="n", aspects=["x"]),
        observed_from="1840", observed_to="1845",
    )
    resi = ResidenceFact(id="r1", person_id="person_1", place_id="place_1",
                         observations=[obs])
    lines = _export(None, tmp_path, [resi])
    i = lines.index("2 SOUR @S1@")
    assert lines[i + 1] == "3 NOTE Observation: 1840-1845"
    assert lines[i + 2:i + 5] == ["3 QUAY 2", "3 _SLK_NOTE n", "3 _SLK_ASP x"]
    assert not any("_SLK_CTX" in l or "TEXT" in l for l in lines[i:i + 6])


def test_written_tags_are_registered() -> None:
    for tag in ("_SLK_QUAL", "_SLK_CTX", "_SLK_ASP", "_SLK_NOTE"):
        assert tag in SLK_TAGS


def test_mergetest_reexport_imported_twice_creates_nothing_second_time(
    tmp_path: Path,
) -> None:
    """The hash profile ignores QUAY, NOTE and _SLK_* below SOUR (Requirement 12)."""
    import copy
    import json

    from slaktbusken.persistence.serialization import serialize
    from slaktbusken.services.import_service import ImportService
    from slaktbusken.services.project_service import ProjectService
    from slaktbusken.services.report_service import ReportService
    from slaktbusken.services.validation_service import ValidationService
    from tests.test_gedcom_roundtrip import fixtures

    ged = tmp_path / "out.ged"
    GEDCOMExporter().export(fixtures.load_mergetest(), ged)
    text = ged.read_text(encoding="utf-8")
    assert "_SLK_CTX" in text and "QUAY" in text

    data = ProjectData(project=ProjectMetadata(title="T"))
    ps = ProjectService()
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    def run():
        ps._project_data = data
        service = ImportService(ValidationService(), ReportService())
        return service.run(data, ged, project_dir, ps)

    def snapshot() -> str:
        raw = json.loads(serialize(copy.deepcopy(data)))
        return json.dumps(
            {k: raw.get(k) for k in ("persons", "events", "residences", "sources")},
            sort_keys=True,
        )

    run()
    before = snapshot()
    result = run()
    assert snapshot() == before
    assert result.events_added == 0
