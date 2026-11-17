"""Exporter side of source metadata: _SLK_STYPE/PROV/LEV/KTYP/SREF (task 11.1).

Requirements 9.1, 9.2. TITL and TEXT stay unchanged.
"""

from __future__ import annotations

from pathlib import Path

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.gedcom.parser import parse_gedcom
from slaktbusken.gedcom.slk_tags import SLK_TAG_REGISTRY, read_source_fields
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.source import Kalltyp, Leverantor, Source, StructuredReference


def _export(source: Source, tmp_path: Path, **kw) -> list[str]:
    data = ProjectData(
        format="släktbuske-file",
        version="0.2",
        project=ProjectMetadata(title="T"),
        persons=[], families=[], events=[], places=[],
        sources=[source], **kw,
    )
    GEDCOMExporter().export(data, tmp_path / "t.ged")
    return (tmp_path / "t.ged").read_text(encoding="utf-8").splitlines()


def _sour(lines: list[str]) -> list[str]:
    start = next(i for i, ln in enumerate(lines) if ln.endswith(" SOUR"))
    return lines[start:lines.index("0 TRLR")]


def test_all_metadata_is_written(tmp_path: Path) -> None:
    src = Source(
        id="source_1", provider="Arkiv Digital", source_type="other",
        title="Dödsannons", leverantor_id="lev_1", kalltyp_id="kt_1",
        structured_reference=StructuredReference(
            fields={"image": "70", "page": 272, "note": None}),
    )
    lines = _sour(_export(
        src, tmp_path,
        leverantorer=[Leverantor(id="lev_1", name="Arkiv Digital")],
        kalltyper=[Kalltyp(id="kt_1", leverantor_id="lev_1", name="Husförhör")],
    ))
    assert "1 TITL Dödsannons" in lines
    assert "1 _SLK_STYPE other" in lines
    assert "1 _SLK_PROV Arkiv Digital" in lines
    assert "1 _SLK_LEV Arkiv Digital" in lines
    assert "1 _SLK_KTYP Husförhör" in lines
    i = lines.index("1 _SLK_SREF")
    assert lines[i + 1:i + 4] == [
        '2 _SLK_FLD image "70"', "2 _SLK_FLD page 272", "2 _SLK_FLD note null",
    ]
    assert all(t in SLK_TAG_REGISTRY for t in
               (ln.split()[1] for ln in lines if " _SLK_" in ln[:12]))


def test_fields_read_back_with_types(tmp_path: Path) -> None:
    src = Source(
        id="source_1", provider="Övrigt", source_type="church_book", title="K",
        structured_reference=StructuredReference(
            fields={"image": "70", "page": 272, "volume": None}),
    )
    out = "\n".join(_export(src, tmp_path)) + "\n"
    sour = next(r for r in parse_gedcom(out).records if r.tag == "SOUR")
    extras = read_source_fields(sour)
    assert extras.provider == "Övrigt"
    assert extras.source_type == "church_book"
    assert extras.reference_fields == {"image": "70", "page": 272, "volume": None}
    assert extras.reference_fields["image"] == "70"


def test_empty_values_write_nothing(tmp_path: Path) -> None:
    src = Source(id="source_1", provider="", source_type="", title="K")
    lines = _sour(_export(src, tmp_path))
    assert not any("_SLK_" in ln for ln in lines)


def test_unknown_leverantor_id_is_skipped(tmp_path: Path) -> None:
    src = Source(id="source_1", provider="p", source_type="other", title="K",
                 leverantor_id="gone", kalltyp_id="gone")
    lines = _sour(_export(src, tmp_path))
    assert not any("_SLK_LEV" in ln or "_SLK_KTYP" in ln for ln in lines)
