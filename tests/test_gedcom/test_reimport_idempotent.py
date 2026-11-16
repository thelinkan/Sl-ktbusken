"""Regression: re-importing an identical GEDCOM file must be idempotent.

An unchanged re-import creates, removes and modifies no event, and keeps every
id of ``Family.event_ids``. A changed record adds one new event (design 0.3.0,
Component 7 and 8).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from slaktbusken.gedcom.importer import GEDCOMImporter
from slaktbusken.model.project import ProjectData, ProjectMetadata

_GEDCOM = """\
0 HEAD
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
0 @I2@ INDI
1 NAME Anna /Persson/
1 SEX F
0 @I3@ INDI
1 NAME Erik /Andersson/
1 SEX M
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 MARR
2 DATE 10 JUN 1875
2 PLAC Ljusdal
1 DIV
2 DATE 1 JAN 1890
1 EVEN
2 TYPE Förlovning
2 DATE 1 JAN 1874
0 TRLR
"""


def _snapshot(project: ProjectData) -> dict:
    return {
        "persons": sorted(p.id for p in project.persons),
        "families": sorted(f.id for f in project.families),
        "events": sorted((e.id, e.type, str(e.date)) for e in project.events),
        "family_event_ids": {f.id: list(f.event_ids) for f in project.families},
        "family_event_counts": {f.id: len(f.event_ids) for f in project.families},
    }


def _import(project: ProjectData, tdir: Path, path: Path) -> None:
    GEDCOMImporter(project, tdir).import_file(path)


@pytest.fixture
def setup(tmp_path: Path):
    tdir = tmp_path / "translation"
    tdir.mkdir()
    path = tmp_path / "t.ged"
    path.write_text(_GEDCOM, encoding="utf-8")
    project = ProjectData(project=ProjectMetadata(title="T"))
    return project, tdir, path


def test_second_import_leaves_everything_unchanged(setup) -> None:
    project, tdir, path = setup
    _import(project, tdir, path)
    first = _snapshot(project)
    assert first["family_event_counts"][project.families[0].id] == 3

    _import(project, tdir, path)
    assert _snapshot(project) == first

    _import(project, tdir, path)
    assert _snapshot(project) == first


def test_reimport_changed_record_adds_event_and_keeps_old(setup) -> None:
    """A changed GEDCOM record creates one new event (with a notice) and the
    existing family event stays unchanged (Requirements 10.10, 10.14)."""
    project, tdir, path = setup
    _import(project, tdir, path)
    count = len(project.events)
    family = project.families[0]
    old_ids = list(family.event_ids)

    path.write_text(_GEDCOM.replace("10 JUN 1875", "11 JUN 1875"), encoding="utf-8")
    result = GEDCOMImporter(project, tdir).import_file(path)

    assert len(project.events) == count + 1
    assert family.event_ids[: len(old_ids)] == old_ids
    assert len(family.event_ids) == len(old_ids) + 1
    marriages = [
        e for e in project.events if e.id in family.event_ids and e.type == "marriage"
    ]
    assert len(marriages) == 2
    assert any("10" in str(e.date) for e in marriages)
    assert any("11" in str(e.date) for e in marriages)
    assert any("En ny händelse" in w for w in result.warnings)


_RESI_GEDCOM = """\
0 HEAD
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Johan /Andersson/
1 RESI
2 DATE FROM 1 JAN 1880 TO 1 JAN 1890
2 PLAC Ljusdal
1 RESI
2 DATE FROM 1 JAN 1880 TO 1 JAN 1890
2 PLAC Ljusdal
0 TRLR
"""


def test_reimport_residences_creates_none_and_counts(tmp_path: Path) -> None:
    """Identical RESI records pair by count; an unchanged re-import creates
    no residence and resolves no place (Requirement 22.10, 22.14)."""
    tdir = tmp_path / "translation"
    tdir.mkdir()
    path = tmp_path / "r.ged"
    path.write_text(_RESI_GEDCOM, encoding="utf-8")
    project = ProjectData(project=ProjectMetadata(title="T"))

    first = GEDCOMImporter(project, tdir).import_file(path)
    assert first.residences_added == 2
    assert len(project.residences) == 2
    assert sorted(r.origins[0].instance for r in project.residences) == [0, 1]
    before = [(r.id, r.place_id, len(r.origins)) for r in project.residences]
    places = len(project.places)

    second = GEDCOMImporter(project, tdir).import_file(path)
    assert second.residences_added == 0
    assert [(r.id, r.place_id, len(r.origins)) for r in project.residences] == before
    assert len(project.places) == places


def test_reimport_claims_legacy_residence(tmp_path: Path) -> None:
    tdir = tmp_path / "translation"
    tdir.mkdir()
    path = tmp_path / "r.ged"
    path.write_text(_RESI_GEDCOM, encoding="utf-8")
    project = ProjectData(project=ProjectMetadata(title="T"))
    GEDCOMImporter(project, tdir).import_file(path)
    for r in project.residences:
        r.origins = []  # simulate residences made by an older version

    result = GEDCOMImporter(project, tdir).import_file(path)
    assert result.residences_claimed == 2
    assert result.residences_added == 0
    assert len(project.residences) == 2
    assert all(len(r.origins) == 1 for r in project.residences)
