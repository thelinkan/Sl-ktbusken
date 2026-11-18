"""Source metadata: Property 11 (source part) and the examples of Requirement 9.

Round trips go through ``GEDCOMExporter`` and ``ImportService.run`` into a real
empty project. Leverantör and Källtyp resolve by name to entities that already
exist in the target project, so the target is seeded with the names of the
source project (a new project normally has the default list; ids differ).

Sources are compared by title: source type, provider, the structured reference
fields with their exact value types, and the Leverantör and Källtyp names.
Repositories and repository references (task 11.6) are compared by content,
because their ids differ between the two projects.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from hypothesis import assume, given
from hypothesis import strategies as st

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.gedcom.importer import ImportResult
from slaktbusken.gedcom.parser import parse_gedcom
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.model.source import (
    Kalltyp,
    Leverantor,
    Repository,
    RepositoryRef,
    Source,
    StructuredReference,
)
from slaktbusken.persistence.serialization import serialize
from slaktbusken.services.project_service import ProjectService
from tests.test_gedcom_roundtrip import synthetic as syn
from tests.test_gedcom_roundtrip.fixtures import load_mergetest
from tests.test_gedcom_roundtrip.strategies import source_projects
from tests.test_gedcom_roundtrip.test_events_roundtrip import World
from tests.test_gedcom_roundtrip.test_families_roundtrip import (
    _children,
    export_text,
    label_persons,
)
import pytest

pytestmark = pytest.mark.mandatory_integrity

_HEAD = "0 HEAD\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n"
_MARKED_HEAD = _HEAD + "1 _SLK_VERS 1\n"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def seed_names(ps: ProjectService, data: ProjectData) -> None:
    """Add the Leverantör and Källtyp names of ``data`` that the target lacks.

    New ids are generated, so that only the names can link the two projects.
    """
    target = ps.data
    lev_names = {l.id: l.name for l in data.leverantorer}
    for lev in data.leverantorer:
        if not any(t.name == lev.name for t in target.leverantorer):
            lev_copy = type(lev)(id=str(uuid.uuid4()), name=lev.name, comment="")
            target.leverantorer.append(lev_copy)
    for kt in data.kalltyper:
        lev = next(t for t in target.leverantorer if t.name == lev_names[kt.leverantor_id])
        if not any(k.leverantor_id == lev.id and k.name == kt.name
                   for k in target.kalltyper):
            target.kalltyper.append(type(kt)(
                id=str(uuid.uuid4()), leverantor_id=lev.id, name=kt.name))


def import_with_names(text: str, data: ProjectData) -> tuple[ProjectData, ImportResult]:
    with tempfile.TemporaryDirectory() as folder:
        world = World(Path(folder))
        seed_names(world.ps, data)
        result = world.run(text)
        return world.data, result


def _typed(value) -> tuple[str, object]:
    return type(value).__name__, value


def source_view(data: ProjectData, source: Source) -> tuple:
    """Everything of the source part, with exact value types."""
    levs = {l.id: l.name for l in data.leverantorer}
    kts = {k.id: k.name for k in data.kalltyper}
    fields = tuple(sorted(
        (k, _typed(v)) for k, v in source.structured_reference.fields.items()))
    return (source.title, source.source_type, source.provider, fields,
            levs.get(source.leverantor_id), kts.get(source.kalltyp_id))


def source_views(data: ProjectData) -> dict[str, tuple]:
    views = {s.title: source_view(data, s) for s in data.sources}
    assert len(views) == len(data.sources), "titles must be unique"
    return views


def sour_nodes(text: str) -> dict[str, object]:
    """SOUR records by title."""
    return {_children(r, "TITL")[0].value: r
            for r in parse_gedcom(text).records if r.tag == "SOUR"}


def one_source(**kw) -> ProjectData:
    person = Person(id="person_1", sex="U", names=[Name("birth", "P1", "X")])
    kw.setdefault("provider", "")
    kw.setdefault("source_type", "other")
    source = Source(id="source_1", title="Testkälla", **kw)
    return ProjectData(
        persons=[person], sources=[source],
        leverantorer=[Leverantor(id="lev_1", name="Arkiv Digital", comment="")],
        kalltyper=[Kalltyp(id="kalltyp_1", leverantor_id="lev_1",
                           name="Husförhörslängd")])


def _roundtrip_one(**kw) -> tuple[str, ProjectData]:
    data = one_source(**kw)
    text, _ = export_text(data)
    imported, _ = import_with_names(text, data)
    return text, imported


# ---------------------------------------------------------------------------
# Property 11 (source part)
# ---------------------------------------------------------------------------


# Feature: gedcom-roundtrip-0-3-0, Property 11: Sources and repositories round-trip
# **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6**
@given(source_projects())
def test_source_metadata_roundtrip(data: ProjectData) -> None:
    data = label_persons(data)
    text, _ = export_text(data)
    imported, _ = import_with_names(text, data)
    assert source_views(imported) == source_views(data)


def test_mergetest_sources_roundtrip_with_provider_type_and_string_values() -> None:
    data = label_persons(load_mergetest())
    text, _ = export_text(data)
    imported, _ = import_with_names(text, data)
    views = source_views(imported)
    assert views == source_views(data)

    by_title = {s.title: s for s in imported.sources}
    notice = by_title["Dödsannons Janne Karsson d. 1994"]
    assert notice.source_type == "other"          # never "death_notice"
    assert notice.provider == "Övrigt"
    church = by_title["Våmhus AII:2c Sida: 272"]
    assert church.provider == "Arkiv Digital"
    fields = church.structured_reference.fields
    assert fields["image"] == "70" and isinstance(fields["image"], str)
    assert fields["page"] == "272" and isinstance(fields["page"], str)
    assert {s.provider for s in imported.sources} == {"Arkiv Digital", "Övrigt"}


def test_integer_string_and_null_values_keep_their_type() -> None:
    _, imported = _roundtrip_one(
        source_type="newspaper", provider="Tidning",
        structured_reference=StructuredReference(fields={
            "newspaper": "Ljusdals Tidning", "date": "12", "page": 12,
            "article_title": None}))
    (source,) = imported.sources
    fields = source.structured_reference.fields
    assert fields == {"newspaper": "Ljusdals Tidning", "date": "12", "page": 12,
                      "article_title": None}
    assert type(fields["date"]) is str and type(fields["page"]) is int
    assert fields["article_title"] is None


def test_leverantor_and_kalltyp_resolve_by_name_not_id() -> None:
    _, imported = _roundtrip_one(
        source_type="church_book", leverantor_id="lev_1", kalltyp_id="kalltyp_1")
    (source,) = imported.sources
    lev = next(l for l in imported.leverantorer if l.id == source.leverantor_id)
    kt = next(k for k in imported.kalltyper if k.id == source.kalltyp_id)
    assert (lev.name, kt.name, kt.leverantor_id) == (
        "Arkiv Digital", "Husförhörslängd", lev.id)
    assert source.leverantor_id != "lev_1"


def test_unknown_leverantor_name_leaves_ids_empty() -> None:
    text, _ = export_text(one_source(
        source_type="other", leverantor_id="lev_1", kalltyp_id="kalltyp_1"))
    text = text.replace("_SLK_LEV Arkiv Digital", "_SLK_LEV Finns inte")
    with tempfile.TemporaryDirectory() as folder:
        world = World(Path(folder))
        world.run(text)
        (source,) = world.data.sources
        assert (source.leverantor_id, source.kalltyp_id) == ("", "")


# ---------------------------------------------------------------------------
# Old files keep their old mapping (Requirement 9.14)
# ---------------------------------------------------------------------------


def _old_file(sour_lines: str, head: str = _HEAD) -> str:
    return head + "0 @S1@ SOUR\n" + sour_lines + "0 TRLR\n"


def _import_plain(text: str) -> ProjectData:
    with tempfile.TemporaryDirectory() as folder:
        world = World(Path(folder))
        world.run(text)
        return world.data


def test_old_file_source_without_slk_tags_is_detected_as_before() -> None:
    data = _import_plain(_old_file(
        "1 TITL Dödsannons Janne Karsson d. 1994\n"))
    (source,) = data.sources
    from slaktbusken.gedcom.translation.source_translation import detect_source_type
    assert source.source_type == detect_source_type(
        _gedcom_source("Dödsannons Janne Karsson d. 1994"))
    assert source.provider == ""


def _gedcom_source(title: str):
    from slaktbusken.gedcom.importer import _extract_gedcom_source
    record = next(r for r in parse_gedcom(
        _old_file(f"1 TITL {title}\n")).records if r.tag == "SOUR")
    return _extract_gedcom_source(record)


def test_old_file_reference_text_is_parsed_as_before_without_sref() -> None:
    plain = _import_plain(_old_file(
        "1 TITL Våmhus AII:2c Sida: 272\n1 TEXT Våmhus AII:2c (1910-1923) Bild: 70 Sida: 272\n"))
    marked = _import_plain(_old_file(
        "1 TITL Våmhus AII:2c Sida: 272\n1 TEXT Våmhus AII:2c (1910-1923) Bild: 70 Sida: 272\n",
        head=_MARKED_HEAD))
    assert serialize_source(plain.sources[0]) == serialize_source(marked.sources[0])


def serialize_source(source: Source) -> tuple:
    return (source.source_type, source.provider,
            tuple(sorted(source.structured_reference.fields.items())),
            source.reference_text)


def test_stype_skips_the_keyword_detection() -> None:
    title = "Dödsannons Janne Karsson d. 1994"
    plain = _import_plain(_old_file(f"1 TITL {title}\n"))
    forced = _import_plain(_old_file(
        f"1 TITL {title}\n1 _SLK_STYPE census\n", head=_MARKED_HEAD))
    assert forced.sources[0].source_type == "census"
    assert plain.sources[0].source_type != "census"


def test_unknown_stype_falls_back_to_detection_with_a_warning() -> None:
    title = "Dödsannons Janne Karsson d. 1994"
    plain = _import_plain(_old_file(f"1 TITL {title}\n"))
    with tempfile.TemporaryDirectory() as folder:
        world = World(Path(folder))
        result = world.run(_old_file(
            f"1 TITL {title}\n1 _SLK_STYPE death_notice_x\n", head=_MARKED_HEAD))
        assert world.data.sources[0].source_type == plain.sources[0].source_type
        assert any("death_notice_x" in str(w) for w in result.warnings)


# ---------------------------------------------------------------------------
# One test per registry tag
# ---------------------------------------------------------------------------


def _full_source() -> ProjectData:
    return one_source(
        source_type="church_book", provider="Arkiv Digital",
        structured_reference=StructuredReference(fields={
            "parish": "Ljusdal", "image": 12, "page": "17", "volume": None}),
        leverantor_id="lev_1", kalltyp_id="kalltyp_1")


def _sour(data: ProjectData):
    text, _ = export_text(data)
    return text, sour_nodes(text)["Testkälla"]


def _values(node, tag: str) -> list[str]:
    return [c.value for c in _children(node, tag)]


def test_slk_tag_stype() -> None:
    _, sour = _sour(_full_source())
    assert _values(sour, "_SLK_STYPE") == ["church_book"]
    _, sour = _sour(one_source(source_type="other"))
    assert _values(sour, "_SLK_STYPE") == ["other"]
    imported = _import_plain(_old_file(
        "1 TITL Testkälla\n1 _SLK_STYPE photograph\n", head=_MARKED_HEAD))
    assert imported.sources[0].source_type == "photograph"


def test_slk_tag_prov() -> None:
    _, sour = _sour(_full_source())
    assert _values(sour, "_SLK_PROV") == ["Arkiv Digital"]
    _, sour = _sour(one_source(source_type="other", provider=""))
    assert _children(sour, "_SLK_PROV") == []
    imported = _import_plain(_old_file(
        "1 TITL Testkälla\n1 _SLK_PROV Egen leverantör\n", head=_MARKED_HEAD))
    assert imported.sources[0].provider == "Egen leverantör"


def test_slk_tag_lev_and_slk_tag_ktyp() -> None:
    _, sour = _sour(_full_source())
    assert _values(sour, "_SLK_LEV") == ["Arkiv Digital"]
    assert _values(sour, "_SLK_KTYP") == ["Husförhörslängd"]
    _, sour = _sour(one_source(source_type="other"))
    assert _children(sour, "_SLK_LEV") == [] and _children(sour, "_SLK_KTYP") == []
    imported = _import_plain(_old_file(
        "1 TITL Testkälla\n1 _SLK_LEV Arkiv Digital\n1 _SLK_KTYP Folkräkning\n",
        head=_MARKED_HEAD))
    source = imported.sources[0]
    assert {l.id: l.name for l in imported.leverantorer}[source.leverantor_id] \
        == "Arkiv Digital"
    assert {k.id: k.name for k in imported.kalltyper}[source.kalltyp_id] \
        == "Folkräkning"


def test_slk_tag_sref_and_slk_tag_fld() -> None:
    _, sour = _sour(_full_source())
    (sref,) = _children(sour, "_SLK_SREF")
    assert all(c.tag == "_SLK_FLD" and c.level == 2 for c in sref.children)
    assert sorted(c.value for c in sref.children) == [
        'image 12', 'page "17"', 'parish "Ljusdal"', 'volume null']
    _, sour = _sour(one_source(source_type="other"))
    assert _children(sour, "_SLK_SREF") == []


def test_slk_fld_bad_json_and_unknown_values_are_skipped_with_a_warning() -> None:
    text = _old_file(
        "1 TITL Testkälla\n1 _SLK_SREF\n2 _SLK_FLD parish \"Ljusdal\"\n"
        "2 _SLK_FLD image {bad\n2 _SLK_FLD page 1.5\n2 _SLK_FLD volume true\n",
        head=_MARKED_HEAD)
    with tempfile.TemporaryDirectory() as folder:
        world = World(Path(folder))
        result = world.run(text)
        assert world.data.sources[0].structured_reference.fields == {
            "parish": "Ljusdal"}
        assert len(result.warnings) >= 3


def test_sref_wins_over_the_reference_text() -> None:
    imported = _import_plain(_old_file(
        "1 TITL Testkälla\n1 TEXT Våmhus AII:2c (1910-1923) Bild: 70 Sida: 272\n"
        "1 _SLK_STYPE church_book\n1 _SLK_SREF\n2 _SLK_FLD parish \"Annan\"\n"
        "2 _SLK_FLD image 5\n", head=_MARKED_HEAD))
    assert imported.sources[0].structured_reference.fields == {
        "parish": "Annan", "image": 5}


def test_a_second_import_does_not_change_source_metadata() -> None:
    data = _full_source()
    text, _ = export_text(data)
    with tempfile.TemporaryDirectory() as folder:
        world = World(Path(folder))
        seed_names(world.ps, data)
        world.run(text)
        before = (source_views(world.data), len(world.data.sources))
        world.run(text)
        assert (source_views(world.data), len(world.data.sources)) == before
        assert serialize(world.data)


# ---------------------------------------------------------------------------
# Repositories (Requirements 9.7 to 9.13)
# ---------------------------------------------------------------------------


def repo_view(repo: Repository) -> tuple:
    """A Repository without its id."""
    # The importer trims the address; a blank one means no address.
    return (repo.name, repo.type, (repo.address or "").strip() or None,
            tuple(repo.phone),
            tuple(repo.email), tuple(repo.web), repo.notes,
            tuple(repo.external_ids))


def ref_view(data: ProjectData, ref: RepositoryRef) -> tuple:
    repo = next(r for r in data.repositories if r.id == ref.repository_id)
    # GEDCOM lines do not keep outer blanks of a value; the importer trims it.
    return (repo_view(repo), ref.call_number.strip(), ref.source_type, ref.image_number,
            ref.page_number, ref.media_type, ref.media_name, ref.notes)


def source_ref_views(data: ProjectData) -> dict[str, list[tuple]]:
    """Per source title the reference views; identical references collapse,
    as the importer adds a reference only once."""
    return {s.title: list(dict.fromkeys(ref_view(data, r) for r in s.repository_refs))
            for s in data.sources}


def repo_nodes(text: str) -> dict[str, object]:
    """Level-0 REPO records by NAME."""
    return {_children(r, "NAME")[0].value: r
            for r in parse_gedcom(text).records if r.tag == "REPO"}


def two_repo_project() -> ProjectData:
    data = one_source()
    data.sources.append(Source(id="source_2", title="Andra källan",
                               provider="", source_type="other"))
    data.repositories = [
        Repository(id="repo_1", name="Landsarkivet", type="archive",
                   address="Box 1, Härnösand", phone=["060-1"],
                   email=["a@b.se"], web=["https://x.se"], notes="Anm",
                   external_ids=["X1", "X2"]),
        Repository(id="repo_2", name="Oanvänt", type="library"),
    ]
    for source in data.sources:
        source.repository_refs.append(RepositoryRef(
            repository_id="repo_1", call_number=f"C {source.id}",
            media_type="Microfiche", source_type="church_book",
            image_number=3, page_number=0, media_name="Rulle 7", notes="n"))
    return data


# Feature: gedcom-roundtrip-0-3-0, Property 11: Sources and repositories round-trip
# **Validates: Requirements 9.7, 9.8, 9.9, 9.10**
@given(source_projects())
def test_repository_roundtrip(data: ProjectData) -> None:
    data = label_persons(data)
    assume(len({r.name for r in data.repositories}) == len(data.repositories))
    text, _ = export_text(data)
    imported, _ = import_with_names(text, data)
    assert source_ref_views(imported) == source_ref_views(data)
    # Unreferenced repositories are written and imported too.
    assert sorted(repo_view(r) for r in imported.repositories) == \
        sorted(repo_view(r) for r in data.repositories)


def test_two_sources_share_one_repo_record() -> None:
    data = two_repo_project()
    text, _ = export_text(data)
    records = repo_nodes(text)
    assert list(records) == ["Landsarkivet", "Oanvänt"]   # used first, then unused
    xref = next(r for r in parse_gedcom(text).records
                if r.tag == "REPO" and _children(r, "NAME")[0].value == "Landsarkivet").xref_id
    for sour in sour_nodes(text).values():
        assert [c.value for c in _children(sour, "REPO")] == [xref]

    imported, _ = import_with_names(text, data)
    assert len(imported.repositories) == 2
    ids = {r.repository_id for s in imported.sources for r in s.repository_refs}
    assert len(ids) == 1
    assert source_ref_views(imported) == source_ref_views(data)


def test_unused_repositories_follow_the_used_ones_in_project_order() -> None:
    data = two_repo_project()
    data.repositories.insert(0, Repository(id="repo_0", name="Först", type="museum"))
    data.repositories.append(Repository(id="repo_3", name="Sist", type="museum"))
    text, _ = export_text(data)
    assert list(repo_nodes(text)) == ["Landsarkivet", "Först", "Oanvänt", "Sist"]
    assert not any(n.tag == "OBJE" for n in parse_gedcom(text).records)


def test_repeated_import_creates_no_repository_and_no_reference() -> None:
    data = two_repo_project()
    text, _ = export_text(data)
    with tempfile.TemporaryDirectory() as folder:
        world = World(Path(folder))
        seed_names(world.ps, data)
        world.run(text)
        repos = [repo_view(r) for r in world.data.repositories]
        refs = source_ref_views(world.data)
        n_refs = sum(len(s.repository_refs) for s in world.data.sources)
        world.run(text)
        assert [repo_view(r) for r in world.data.repositories] == repos
        assert source_ref_views(world.data) == refs
        assert sum(len(s.repository_refs) for s in world.data.sources) == n_refs


_FOREIGN = (
    _HEAD
    + "0 @R1@ REPO\n1 NAME Riksarkivet\n1 ADDR Fyrverkarbacken 13\n2 CONT Stockholm\n"
    "1 PHON 08-1\n1 EMAIL r@ra.se\n1 WWW https://riksarkivet.se\n1 NOTE Öppet\n"
    "0 @S1@ SOUR\n1 TITL Foreign\n1 REPO @R1@\n2 CALN SE/RA/1\n3 MEDI Book\n"
    "2 NOTE hyllan\n"
    "0 @S2@ SOUR\n1 TITL Other\n1 REPO @R1@\n2 CALN SE/RA/2\n"
    "0 TRLR\n"
)


def test_file_without_marker_uses_the_standard_tags_only() -> None:
    # SLK lines in a file without the marker must be ignored.
    text = _FOREIGN.replace("1 NOTE Öppet\n", "1 NOTE Öppet\n1 _SLK_RTYPE library\n"
                            "1 _SLK_XID Z\n")
    text = text.replace("2 CALN SE/RA/1\n", "2 _SLK_RIMG 4\n2 CALN SE/RA/1\n")
    data = _import_plain(text)
    (repo,) = data.repositories
    assert (repo.name, repo.type, repo.address) == (
        "Riksarkivet", "archive", "Fyrverkarbacken 13\nStockholm")
    assert (repo.phone, repo.email, repo.web, repo.notes) == (
        ["08-1"], ["r@ra.se"], ["https://riksarkivet.se"], "Öppet")
    assert repo.external_ids == []
    refs = {s.title: s.repository_refs for s in data.sources}
    first, = refs["Foreign"]
    assert (first.repository_id, first.call_number, first.media_type, first.notes) == (
        repo.id, "SE/RA/1", "Book", "hyllan")
    assert first.image_number is None and first.source_type == ""
    assert [r.call_number for r in refs["Other"]] == ["SE/RA/2"]


def test_new_repository_without_type_gets_archive_or_digital_archive() -> None:
    text = _HEAD + "0 @R1@ REPO\n1 NAME Någon\n0 @R2@ REPO\n1 NAME ArkivDigital\n0 TRLR\n"
    data = _import_plain(text)
    assert {r.name: r.type for r in data.repositories} == {
        "Någon": "archive", "ArkivDigital": "digital_archive"}


def test_arkiv_digital_is_not_attached_twice() -> None:
    text = (_HEAD + "0 @R1@ REPO\n1 NAME ArkivDigital\n"
            "0 @S1@ SOUR\n1 TITL Våmhus AII:2c Sida: 272\n"
            "1 TEXT Våmhus AII:2c (1910-1923) Bild: 70 Sida: 272\n"
            "1 REPO @R1@\n2 CALN K1\n0 TRLR\n")
    data = _import_plain(text)
    assert [r.name for r in data.repositories] == ["ArkivDigital"]
    (source,) = data.sources
    assert len(source.repository_refs) == 1
    assert source.repository_refs[0].call_number == "K1"


def test_program_ignoring_slk_tags_sees_name_address_contacts_call_number_and_media() -> None:
    data = two_repo_project()
    text, _ = export_text(data)
    plain = "\n".join(line for line in text.split("\n") if "_SLK_" not in line)
    repo = repo_nodes(plain)["Landsarkivet"]
    assert [c.value for c in _children(repo, "ADDR")] == ["Box 1, Härnösand"]
    assert [c.value for c in _children(repo, "PHON")] == ["060-1"]
    assert [c.value for c in _children(repo, "EMAIL")] == ["a@b.se"]
    assert [c.value for c in _children(repo, "WWW")] == ["https://x.se"]
    assert [c.value for c in _children(repo, "NOTE")] == ["Anm"]
    for sour in sour_nodes(plain).values():
        (ref,) = _children(sour, "REPO")
        (caln,) = _children(ref, "CALN")
        assert caln.value == f"C {sour_id(sour, data)}"
        assert [c.value for c in _children(caln, "MEDI")] == ["Microfiche"]
    # Without the SLK lines the import still yields a usable repository.
    imported = _import_plain(plain)
    assert {r.name for r in imported.repositories} == {"Landsarkivet", "Oanvänt"}


def sour_id(sour, data: ProjectData) -> str:
    title = _children(sour, "TITL")[0].value
    return next(s.id for s in data.sources if s.title == title)


def test_slk_tag_rtype_and_slk_tag_xid() -> None:
    text, _ = export_text(two_repo_project())
    repo = repo_nodes(text)["Landsarkivet"]
    assert [c.value for c in _children(repo, "_SLK_RTYPE")] == ["archive"]
    assert [c.value for c in _children(repo, "_SLK_XID")] == ["X1", "X2"]
    imported = _import_plain(
        _HEAD + "1 _SLK_VERS 1\n0 @R1@ REPO\n1 NAME A\n1 _SLK_RTYPE museum\n"
        "1 _SLK_XID P1\n1 _SLK_XID \n1 _SLK_XID P2\n0 TRLR\n")
    (repo,) = imported.repositories
    assert repo.type == "museum" and repo.external_ids == ["P1", "P2"]


def _marked_with_ref(ref_lines: str) -> ProjectData:
    return _import_plain(
        _MARKED_HEAD + "0 @R1@ REPO\n1 NAME A\n0 @S1@ SOUR\n1 TITL T\n"
        "1 REPO @R1@\n" + ref_lines + "0 TRLR\n")


def _ref(data: ProjectData) -> RepositoryRef:
    (ref,) = data.sources[0].repository_refs
    return ref


def test_slk_tag_rstype() -> None:
    text, _ = export_text(two_repo_project())
    (ref,) = _children(sour_nodes(text)["Testkälla"], "REPO")
    assert [c.value for c in _children(ref, "_SLK_RSTYPE")] == ["church_book"]
    assert _ref(_marked_with_ref("2 _SLK_RSTYPE census\n")).source_type == "census"


def test_slk_tag_rimg_and_slk_tag_rpage() -> None:
    text, _ = export_text(two_repo_project())
    (ref,) = _children(sour_nodes(text)["Testkälla"], "REPO")
    assert [c.value for c in _children(ref, "_SLK_RIMG")] == ["3"]
    assert [c.value for c in _children(ref, "_SLK_RPAGE")] == ["0"]    # zero is kept
    got = _ref(_marked_with_ref("2 _SLK_RIMG 12\n2 _SLK_RPAGE 0\n"))
    assert (got.image_number, got.page_number) == (12, 0)
    bad = _ref(_marked_with_ref("2 _SLK_RIMG abc\n2 _SLK_RPAGE -1\n"))
    assert (bad.image_number, bad.page_number) == (None, None)


def test_slk_tag_rmedname() -> None:
    text, _ = export_text(two_repo_project())
    (ref,) = _children(sour_nodes(text)["Testkälla"], "REPO")
    assert [c.value for c in _children(ref, "_SLK_RMEDNAME")] == ["Rulle 7"]
    assert _ref(_marked_with_ref("2 _SLK_RMEDNAME Rulle 9\n")).media_name == "Rulle 9"
    assert _ref(_marked_with_ref("2 _SLK_RMEDNAME \n")).media_name == ""
