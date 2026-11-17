"""Regression: a PLAC that matches an already created place must resolve to it.

A place created as a parent in the hierarchy of another place (the church's
parish "Ljusdal") used to resolve to ``None`` when an event named it directly,
so the event lost its place on import.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.gedcom.importer import GEDCOMImporter
from slaktbusken.model.project import ProjectData, ProjectMetadata
from tests.test_gedcom_roundtrip.fixtures import load_mergetest

CHURCH = "Ljusdals kyrka, Ljusdal, Gävleborgs län, Sverige"
PARISH = "Ljusdal, Gävleborgs län, Sverige"


def _gedcom(indi_places: list[tuple[str, str]], fam_places: list[tuple[str, str]] = ()) -> str:
    lines = ["0 HEAD", "1 CHAR UTF-8", "0 @I1@ INDI", "1 NAME Anna /Test/", "1 SEX F"]
    for tag, place in indi_places:
        lines += [f"1 {tag}", "2 DATE 1 JAN 1900", f"2 PLAC {place}"]
    lines += ["0 @I2@ INDI", "1 NAME Erik /Test/", "1 SEX M"]
    if fam_places:
        lines += ["0 @F1@ FAM", "1 HUSB @I2@", "1 WIFE @I1@"]
        for tag, place in fam_places:
            lines += [f"1 {tag}", "2 DATE 1 JAN 1920", f"2 PLAC {place}"]
    lines.append("0 TRLR")
    return "\n".join(lines) + "\n"


def _import(project: ProjectData, tmp: Path, text: str) -> None:
    tdir = tmp / "translation"
    tdir.mkdir(exist_ok=True)
    path = tmp / "t.ged"
    path.write_text(text, encoding="utf-8")
    GEDCOMImporter(project, tdir).import_file(path)


def _new_project() -> ProjectData:
    return ProjectData(project=ProjectMetadata(title="T"))


def _place_names(project: ProjectData, event_type: str) -> list[str | None]:
    out = []
    for e in project.events:
        if e.type == event_type:
            if e.place is None:
                out.append(None)
            else:
                out.append(next(p.name for p in project.places if p.id == e.place.place_id))
    return out


@pytest.mark.parametrize(
    "first,second",
    [(CHURCH, PARISH), (PARISH, CHURCH)],
    ids=["child_first", "parent_first"],
)
def test_indi_events_keep_places_in_both_orders(tmp_path: Path, first: str, second: str) -> None:
    project = _new_project()
    _import(project, tmp_path, _gedcom([("BIRT", first), ("DEAT", second)]))
    names = {first.split(",")[0], second.split(",")[0]}
    assert _place_names(project, "birth") == [first.split(",")[0]]
    assert _place_names(project, "death") == [second.split(",")[0]]
    assert names == {"Ljusdals kyrka", "Ljusdal"}
    # No duplicate places.
    keys = [(p.name, p.parent_place_id) for p in project.places]
    assert len(keys) == len(set(keys))
    assert sum(1 for p in project.places if p.name == "Ljusdal") == 1


@pytest.mark.parametrize(
    "first,second",
    [(CHURCH, PARISH), (PARISH, CHURCH)],
    ids=["child_first", "parent_first"],
)
def test_family_events_keep_places(tmp_path: Path, first: str, second: str) -> None:
    project = _new_project()
    _import(
        project,
        tmp_path,
        _gedcom([("BIRT", first)], [("MARR", second)]),
    )
    assert _place_names(project, "birth") == [first.split(",")[0]]
    assert _place_names(project, "marriage") == [second.split(",")[0]]
    assert sum(1 for p in project.places if p.name == "Ljusdal") == 1


def test_reimport_is_idempotent_and_keeps_all_places(tmp_path: Path) -> None:
    project = _new_project()
    text = _gedcom([("BIRT", CHURCH), ("DEAT", PARISH)], [("MARR", PARISH)])
    _import(project, tmp_path, text)
    place_ids = sorted(p.id for p in project.places)
    events = sorted((e.id, e.type, e.place.place_id if e.place else None) for e in project.events)
    assert all(e[2] for e in events)

    _import(project, tmp_path, text)
    assert sorted(p.id for p in project.places) == place_ids
    assert sorted(
        (e.id, e.type, e.place.place_id if e.place else None) for e in project.events
    ) == events


def test_mergetest_event_places_survive_export_and_import(tmp_path: Path) -> None:
    original = load_mergetest()

    def place_name(data: ProjectData, ref) -> str | None:
        if ref is None:
            return None
        return next(p.name for p in data.places if p.id == ref.place_id)

    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder) / "out.ged"
        GEDCOMExporter().export(original, out)
        text = out.read_text(encoding="utf-8")

    imported = _new_project()
    _import(imported, tmp_path, text)

    def multiset(data: ProjectData) -> list[tuple[str, str | None]]:
        return sorted(
            (e.type, place_name(data, e.place)) for e in data.events if e.place is not None
        )

    imported_with_place = multiset(imported)
    for item in multiset(original):
        assert item in imported_with_place, item
    assert len(imported_with_place) == len(multiset(original))
