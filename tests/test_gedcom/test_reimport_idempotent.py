"""Regression: re-importing an identical GEDCOM file must be idempotent.

Root cause was ``foster_sync._reattach_end_events`` stripping family-level
event ids (MARR, DIV, ...) from ``Family.event_ids``, so the importer could not
delete the old family events on the next import and created copies.
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
        # Event ids are regenerated on each re-import (old family events are
        # deleted and recreated), so compare events by content.
        "events": sorted((e.type, str(e.date)) for e in project.events),
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


def test_reimport_still_applies_genuine_edit(setup) -> None:
    project, tdir, path = setup
    _import(project, tdir, path)
    count = len(project.events)

    path.write_text(_GEDCOM.replace("10 JUN 1875", "11 JUN 1875"), encoding="utf-8")
    _import(project, tdir, path)

    assert len(project.events) == count
    family = project.families[0]
    marriages = [
        e for e in project.events if e.id in family.event_ids and e.type == "marriage"
    ]
    assert len(marriages) == 1
    assert "11" in str(marriages[0].date)
