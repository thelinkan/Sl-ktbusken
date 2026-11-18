"""Exporter side of persons (task 3.1): NAME TYPE, SEX, TITL, OCCU, NOTE, _SLK_VERS."""

from __future__ import annotations

from pathlib import Path

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData


def _export(persons: list[Person], tmp_path: Path) -> list[str]:
    data = ProjectData()
    data.persons = persons
    out = tmp_path / "out.ged"
    GEDCOMExporter().export(data, out)
    return out.read_text(encoding="utf-8").split("\n")


def _indi(lines: list[str], xref: str) -> list[str]:
    start = lines.index(f"0 {xref} INDI")
    end = start + 1
    while not lines[end].startswith("0 "):
        end += 1
    return lines[start:end]


def test_head_has_slk_vers(tmp_path: Path) -> None:
    lines = _export([], tmp_path)
    assert "1 _SLK_VERS 1" in lines[: lines.index("0 TRLR")]
    assert lines.index("1 _SLK_VERS 1") < lines.index("0 TRLR")


def test_name_types_mapped(tmp_path: Path) -> None:
    names = [
        Name(type=t, given="A", surname="B")
        for t in ("birth", "married", "alias", "adopted", "other")
    ]
    lines = _indi(_export([Person(id="person_1", sex="M", names=names)], tmp_path), "@I1@")
    assert [l for l in lines if " TYPE " in l] == [
        "2 TYPE birth",
        "2 TYPE married",
        "2 TYPE aka",
        "2 TYPE adopted",
        "2 TYPE other",
    ]
    assert lines[1:3] == ["1 NAME A /B/", "2 TYPE birth"]


def test_sex_values(tmp_path: Path) -> None:
    persons = [
        Person(id=f"person_{i}", sex=s, names=[Name(type="birth", given="A", surname="B")])
        for i, s in enumerate(["M", "F", "U", "X"], start=1)
    ]
    lines = _export(persons, tmp_path)
    assert _indi(lines, "@I1@")[3:] == ["1 SEX M"]
    assert _indi(lines, "@I2@")[3:] == ["1 SEX F"]
    assert _indi(lines, "@I3@")[3:] == ["1 SEX U"]
    assert _indi(lines, "@I4@")[3:] == ["1 SEX U", "2 _SLK_SEX X"]


def test_title_occupation_note_order_and_text(tmp_path: Path) -> None:
    person = Person(
        id="person_1",
        sex="M",
        names=[Name(type="birth", given="A", surname="B")],
        notes="rad ett\n@rad två",
        title="Fil.Dr",
        occupation="Lektor",
    )
    lines = _indi(_export([person], tmp_path), "@I1@")
    assert lines[3:] == [
        "1 SEX M",
        "1 TITL Fil.Dr",
        "1 OCCU Lektor",
        "1 NOTE rad ett",
        "2 CONT @@rad två",
    ]


def test_empty_values_write_nothing(tmp_path: Path) -> None:
    person = Person(
        id="person_1",
        sex="M",
        names=[Name(type="birth", given="A", surname="B")],
        notes="",
        title=None,
        occupation="",
    )
    lines = _indi(_export([person], tmp_path), "@I1@")
    assert lines[3:] == ["1 SEX M"]
