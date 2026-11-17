"""Importer side of source metadata (task 11.2, Requirement 9.3 to 9.6, 9.14)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from slaktbusken.services.import_service import ImportService
from slaktbusken.model.project import ProjectData
from slaktbusken.model.source import Kalltyp, Leverantor
from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.report_service import ReportService
from slaktbusken.services.validation_service import ValidationService

_HEAD = "0 HEAD\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n"
_MARKED = _HEAD + "1 _SLK_VERS 1\n"


def _run(ps: ProjectService, folder: Path, text: str, name: str = "in.ged") -> None:
    gedcom = folder / name
    gedcom.write_text(text, encoding="utf-8")
    ImportService(ValidationService(), ReportService()).run(
        ps.data, gedcom, ps.project_path.parent, ps
    )


def _import(text: str, providers: bool = False) -> ProjectData:
    with tempfile.TemporaryDirectory() as folder:
        ps = ProjectService()
        ps.create_project("Mål", Path(folder) / "proj")
        if providers:
            ps.data.leverantorer.append(Leverantor(id="lev_x", name="Testleverantör"))
            ps.data.kalltyper.append(
                Kalltyp(id="kt_x", leverantor_id="lev_x", name="Testtyp")
            )
        _run(ps, Path(folder), text)
        return ps.data


def _sour(body: str, head: str = _MARKED) -> str:
    return head + "0 @S1@ SOUR\n" + body + "0 TRLR\n"


def test_slk_stype_other_beats_keyword_detection() -> None:
    data = _import(_sour("1 TITL Dödsannons Ljusdal\n1 _SLK_STYPE other\n"))
    (src,) = data.sources
    assert src.source_type == "other"


def test_without_stype_keywords_still_decide() -> None:
    data = _import(_sour("1 TITL Dödsannons Ljusdal\n"))
    assert data.sources[0].source_type == "death_notice"


def test_invalid_stype_falls_back_to_keywords() -> None:
    data = _import(_sour("1 TITL Dödsannons\n1 _SLK_STYPE bogus\n"))
    assert data.sources[0].source_type == "death_notice"


def test_slk_prov_sets_provider() -> None:
    data = _import(_sour("1 TITL Källa\n1 _SLK_PROV Rötter\n"))
    assert data.sources[0].provider == "Rötter"


def test_leverantor_and_kalltyp_resolve_by_name() -> None:
    body = "1 TITL Källa\n1 _SLK_LEV Testleverantör\n1 _SLK_KTYP Testtyp\n"
    src = _import(_sour(body), providers=True).sources[0]
    assert (src.leverantor_id, src.kalltyp_id) == ("lev_x", "kt_x")


def test_unknown_leverantor_leaves_ids_empty() -> None:
    body = "1 TITL Källa\n1 _SLK_LEV Okänd\n1 _SLK_KTYP Något\n"
    src = _import(_sour(body), providers=True).sources[0]
    assert (src.leverantor_id, src.kalltyp_id) == ("", "")


def test_sref_keeps_exact_value_types() -> None:
    body = (
        "1 TITL Källa\n1 _SLK_STYPE church_book\n1 _SLK_SREF\n"
        '2 _SLK_FLD parish "Ljusdal"\n2 _SLK_FLD volume "70"\n'
        "2 _SLK_FLD image 12\n2 _SLK_FLD page null\n"
    )
    fields = _import(_sour(body)).sources[0].structured_reference.fields
    assert fields == {"parish": "Ljusdal", "volume": "70", "image": 12, "page": None}
    assert isinstance(fields["volume"], str)


def test_without_sref_reference_text_is_parsed_as_before() -> None:
    text = "Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915"
    src = _import(_sour(f"1 TITL Ljusdal\n1 TEXT {text}\n1 _SLK_STYPE church_book\n")).sources[0]
    assert src.structured_reference.fields["parish"] == "Ljusdal"
    assert src.structured_reference.fields["image"] == 23


def test_file_without_marker_maps_as_before() -> None:
    src = _import(_sour("1 TITL Dödsannons Ljusdal\n", head=_HEAD)).sources[0]
    assert (src.source_type, src.provider) == ("death_notice", "")


def test_reimport_creates_no_duplicate_sources() -> None:
    body = (
        "1 TITL Källa\n1 _SLK_STYPE database\n1 _SLK_PROV P\n1 _SLK_SREF\n"
        '2 _SLK_FLD database_name "DB"\n2 _SLK_FLD record_id "7"\n'
    )
    text = _sour(body)
    with tempfile.TemporaryDirectory() as folder:
        ps = ProjectService()
        ps.create_project("Mål", Path(folder) / "proj")
        _run(ps, Path(folder), text)
        first = [(s.id, s.source_type, s.provider) for s in ps.data.sources]
        _run(ps, Path(folder), text, "again.ged")
        assert [(s.id, s.source_type, s.provider) for s in ps.data.sources] == first
        assert len(first) == 1
