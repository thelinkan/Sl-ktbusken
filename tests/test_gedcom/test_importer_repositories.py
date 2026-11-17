"""Importer side of repositories (task 11.5, Requirement 9.9 to 9.11)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from slaktbusken.model.project import ProjectData
from slaktbusken.services.import_service import ImportService
from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.report_service import ReportService
from slaktbusken.services.validation_service import ValidationService

_HEAD = "0 HEAD\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n"
_MARKED = _HEAD + "1 _SLK_VERS 1\n"

_REPO = (
    "0 @R1@ REPO\n1 NAME Riksarkivet\n1 ADDR Box 1\n1 PHON 08-1\n1 PHON 08-2\n"
    "1 EMAIL a@b.se\n1 WWW https://ra.se\n1 NOTE En anteckning\n"
)
_MARK_REPO = "1 _SLK_RTYPE archive\n1 _SLK_XID x1\n1 _SLK_XID x2\n"
_REF = (
    "1 REPO @R1@\n2 CALN SE/1\n3 MEDI microfilm\n2 NOTE refnot\n"
    "2 _SLK_RSTYPE church_book\n2 _SLK_RIMG 7\n2 _SLK_RPAGE 3\n2 _SLK_RMEDNAME Rulle\n"
)


def _run(ps: ProjectService, folder: Path, text: str) -> None:
    gedcom = folder / "in.ged"
    gedcom.write_text(text, encoding="utf-8")
    ImportService(ValidationService(), ReportService()).run(
        ps.data, gedcom, ps.project_path.parent, ps
    )


def _import(text: str, times: int = 1) -> ProjectData:
    with tempfile.TemporaryDirectory() as folder:
        ps = ProjectService()
        ps.create_project("Mål", Path(folder) / "proj")
        for _ in range(times):
            _run(ps, Path(folder), text)
        return ps.data


def _file(head: str, repo_extra: str, sources: int = 2) -> str:
    text = head + _REPO + repo_extra
    for n in range(1, sources + 1):
        text += f"0 @S{n}@ SOUR\n1 TITL Källa {n}\n" + _REF
    return text + "0 TRLR\n"


def test_two_sources_share_one_repository_with_full_ref() -> None:
    data = _import(_file(_MARKED, _MARK_REPO))
    (repo,) = data.repositories
    assert (repo.name, repo.type, repo.address) == ("Riksarkivet", "archive", "Box 1")
    assert repo.phone == ["08-1", "08-2"]
    assert repo.email == ["a@b.se"] and repo.web == ["https://ra.se"]
    assert repo.notes == "En anteckning" and repo.external_ids == ["x1", "x2"]
    assert len(data.sources) == 2
    for src in data.sources:
        (ref,) = src.repository_refs
        assert ref.repository_id == repo.id
        assert (ref.call_number, ref.media_type, ref.notes) == ("SE/1", "microfilm", "refnot")
        assert (ref.source_type, ref.image_number, ref.page_number, ref.media_name) == (
            "church_book", 7, 3, "Rulle",
        )


def test_second_import_creates_nothing_new() -> None:
    data = _import(_file(_MARKED, _MARK_REPO), times=2)
    assert len(data.repositories) == 1
    assert len(data.sources) == 2
    assert all(len(s.repository_refs) == 1 for s in data.sources)


def test_unreferenced_repo_record_is_imported_once() -> None:
    text = _MARKED + "0 @R9@ REPO\n1 NAME ArkivDigital\n1 _SLK_RTYPE digital_archive\n0 TRLR\n"
    data = _import(text, times=2)
    assert [(r.name, r.type) for r in data.repositories] == [("ArkivDigital", "digital_archive")]


def test_without_marker_only_standard_tags() -> None:
    data = _import(_file(_HEAD, _MARK_REPO))
    (repo,) = data.repositories
    assert repo.type == "archive" and repo.external_ids == []
    ref = data.sources[0].repository_refs[0]
    assert (ref.call_number, ref.media_type) == ("SE/1", "microfilm")
    assert (ref.source_type, ref.image_number, ref.page_number, ref.media_name) == ("", None, None, "")


def test_arkivdigital_repo_record_and_detection_give_one_repo_one_ref() -> None:
    for head in (_MARKED, _HEAD):
        text = (
            head + "0 @R1@ REPO\n1 NAME ArkivDigital\n"
            "0 @S1@ SOUR\n1 TITL ArkivDigital Ljusdal C:1\n1 REPO @R1@\n2 CALN C:1\n"
            "0 TRLR\n"
        )
        data = _import(text, times=2)
        assert [r.name for r in data.repositories] == ["ArkivDigital"]
        assert len(data.sources[0].repository_refs) == 1


def test_dangling_repo_reference_is_skipped_with_warning() -> None:
    text = _MARKED + "0 @S1@ SOUR\n1 TITL Källa\n1 REPO @R404@\n0 TRLR\n"
    data = _import(text)
    assert data.repositories == [] and data.sources[0].repository_refs == []
