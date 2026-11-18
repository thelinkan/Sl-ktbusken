"""Exporter side of repositories: REPO records and 1 REPO references (task 11.4).

Requirements 9.7, 9.8.
"""

from __future__ import annotations

import json
from pathlib import Path

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.gedcom.slk_tags import SLK_TAG_REGISTRY
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.source import Repository, RepositoryRef, Source


def _src(sid: str, *refs: RepositoryRef) -> Source:
    return Source(
        id=sid, provider="", source_type="other", title=sid,
        repository_refs=list(refs),
    )


def _export(
    sources: list[Source], repos: list[Repository], tmp_path: Path
) -> tuple[list[str], list[str]]:
    data = ProjectData(
        format="släktbuske-file",
        version="0.2",
        project=ProjectMetadata(title="T"),
        persons=[], families=[], events=[], places=[],
        sources=sources, repositories=repos,
    )
    result = GEDCOMExporter().export(data, tmp_path / "t.ged")
    lines = (tmp_path / "t.ged").read_text(encoding="utf-8").splitlines()
    return lines, result.warnings


def _block(lines: list[str], header: str) -> list[str]:
    start = lines.index(header)
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("0 ")),
        len(lines),
    )
    return lines[start:end]


def test_repo_record_and_reference_are_written(tmp_path: Path) -> None:
    repo = Repository(
        id="repo_3", name="Landsarkivet", type="archive",
        address="Box 1\nUppsala", phone=["018-1", "018-2"],
        email=["a@b.se"], web=["https://x.se"], notes="Öppet\nmån-fre",
        external_ids=["SE/ULA", "ID2"],
    )
    ref = RepositoryRef(
        repository_id="repo_3", call_number="AI:23", media_type="Microfilm",
        notes="Not", source_type="church_book", image_number=0,
        page_number=12, media_name="Rulle 4",
    )
    lines, _ = _export([_src("source_1", ref)], [repo], tmp_path)
    assert _block(lines, "0 @R3@ REPO") == [
        "0 @R3@ REPO", "1 NAME Landsarkivet",
        "1 ADDR Box 1", "2 CONT Uppsala",
        "1 PHON 018-1", "1 PHON 018-2", "1 EMAIL a@b.se",
        "1 WWW https://x.se", "1 NOTE Öppet", "2 CONT mån-fre",
        "1 _SLK_RTYPE archive", "1 _SLK_XID SE/ULA", "1 _SLK_XID ID2",
    ]
    sour = _block(lines, "0 @S1@ SOUR")
    assert sour[sour.index("1 REPO @R3@"):] == [
        "1 REPO @R3@", "2 CALN AI:23", "3 MEDI Microfilm", "2 NOTE Not",
        "2 _SLK_RSTYPE church_book", "2 _SLK_RIMG 0", "2 _SLK_RPAGE 12",
        "2 _SLK_RMEDNAME Rulle 4",
    ]


def test_used_repositories_come_first_in_first_use_order(
    tmp_path: Path,
) -> None:
    repos = [
        Repository(id="repo_1", name="A", type=""),
        Repository(id="repo_2", name="B", type=""),
        Repository(id="repo_3", name="C", type=""),
    ]
    sources = [
        _src("source_1", RepositoryRef("repo_3")),
        _src("source_2", RepositoryRef("repo_2"), RepositoryRef("repo_3")),
    ]
    lines, _ = _export(sources, repos, tmp_path)
    headers = [ln for ln in lines if ln.endswith(" REPO") and ln.startswith("0 ")]
    # Used ones in first-use order, then the unused one in project order.
    assert headers == ["0 @R3@ REPO", "0 @R2@ REPO", "0 @R1@ REPO"]
    assert lines.count("0 @R3@ REPO") == 1


def test_unused_repository_is_written(tmp_path: Path) -> None:
    """MergeTest case: repo_1 exists but no source references it."""
    repo = Repository(
        id="repo_1", name="ArkivDigital", type="digital_archive",
        web=["https://www.arkivdigital.se"],
    )
    lines, _ = _export([_src("source_1")], [repo], tmp_path)
    assert _block(lines, "0 @R1@ REPO") == [
        "0 @R1@ REPO", "1 NAME ArkivDigital",
        "1 WWW https://www.arkivdigital.se", "1 _SLK_RTYPE digital_archive",
    ]
    assert not any(ln.startswith("1 REPO") for ln in lines)


def test_non_numeric_ids_get_deterministic_r_xrefs(tmp_path: Path) -> None:
    repos = [Repository(id="uuid-b", name="B", type=""),
             Repository(id="uuid-a", name="A", type="")]
    sources = [_src("source_1", RepositoryRef("uuid-a"), RepositoryRef("uuid-b"))]
    first, _ = _export(sources, repos, tmp_path)
    second, _ = _export(sources, repos, tmp_path)
    assert first == second
    assert "1 REPO @R2@" in first and "1 REPO @R1@" in first
    assert "0 @R1@ REPO" in first and "0 @R2@ REPO" in first


def test_media_type_without_call_number_writes_bare_caln(tmp_path: Path) -> None:
    repo = Repository(id="repo_1", name="A", type="")
    ref = RepositoryRef("repo_1", media_type="Book")
    lines, _ = _export([_src("source_1", ref)], [repo], tmp_path)
    sour = _block(lines, "0 @S1@ SOUR")
    assert sour[sour.index("1 REPO @R1@"):] == [
        "1 REPO @R1@", "2 CALN", "3 MEDI Book"]
    assert not any("_SLK_R" in ln for ln in sour)
    assert "1 _SLK_RTYPE" not in "\n".join(_block(lines, "0 @R1@ REPO"))


def test_dangling_reference_is_dropped_with_warning(tmp_path: Path) -> None:
    lines, warnings = _export(
        [_src("source_1", RepositoryRef("repo_9"))], [], tmp_path)
    assert not any(" REPO" in ln for ln in lines)
    assert any("arkiv" in w for w in warnings)


def test_registry_covers_written_repository_tags() -> None:
    names = set(SLK_TAG_REGISTRY)
    for tag in ("_SLK_RTYPE", "_SLK_XID", "_SLK_RSTYPE", "_SLK_RIMG",
                "_SLK_RPAGE", "_SLK_RMEDNAME"):
        assert tag in names


def test_mergetest_fixture_repository_is_unreferenced(tmp_path: Path) -> None:
    path = (Path(__file__).parent.parent / "fixtures" / "gedcom_roundtrip"
            / "MergeTest.json")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert [r["id"] for r in doc["repositories"]] == ["repo_1"]
    assert all(not s.get("repository_refs") for s in doc["sources"])
