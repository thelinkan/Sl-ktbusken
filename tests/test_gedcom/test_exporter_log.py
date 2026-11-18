"""Export-log entries for data that GEDCOM does not carry (task 12.1).

Requirements 1.4, 10.1, 10.2, 10.3, 10.5.
"""

from __future__ import annotations

from pathlib import Path

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.model.media import MediaItem
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata


def _export(tmp_path: Path, **kwargs):
    data = ProjectData(
        format="släktbuske-file",
        version="0.2",
        project=ProjectMetadata(title="T"),
        persons=[], families=[], events=[], places=[], sources=[],
        **kwargs,
    )
    return GEDCOMExporter().export(data, tmp_path / "t.ged")


def test_media_count_and_warning(tmp_path: Path) -> None:
    media = [MediaItem(id=f"media_{i}", type="image", file=f"{i}.jpg", title="t")
             for i in (1, 2)]
    result = _export(tmp_path, media=media)
    assert result.omitted_elements["Medieobjekt"] == 2
    assert any("Media exporteras inte" in w and "2" in w for w in result.warnings)


def test_place_types_warning_only_with_places(tmp_path: Path) -> None:
    assert not any("Platstyper" in w for w in _export(tmp_path).warnings)
    data = ProjectData(
        format="släktbuske-file", version="0.2",
        project=ProjectMetadata(title="T"),
        persons=[], families=[], events=[], sources=[],
        places=[Place(id="place_1", name="Ljusdal", type="ort")],
    )
    result = GEDCOMExporter().export(data, tmp_path / "p.ged")
    assert sum("Platstyper exporteras inte" in w for w in result.warnings) == 1


def test_connection_overrides_are_counted(tmp_path: Path) -> None:
    result = _export(tmp_path, connection_overrides={"person_2": "foster"})
    assert result.omitted_elements["Anslutningsöverstyrningar"] == 1


def test_empty_project_has_no_omissions_or_warnings(tmp_path: Path) -> None:
    result = _export(tmp_path)
    assert result.omitted_elements == {}
    assert result.warnings == []
