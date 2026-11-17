"""Persons: Property 2 (person part), Property 3 (name types and order) and the
sex part of Property 5, plus the examples of Requirements 2, 3 and 4 criteria 8
and 9.

Round trips go through ``GEDCOMExporter`` and ``ImportService.run`` into a real
empty project (``ProjectService.create_project``). The importer creates new
person ids and the generated names are random, so persons are compared as a
sorted list of signatures, not by id.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

import pytest
from hypothesis import given
from hypothesis import strategies as st

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.gedcom.importer import ImportResult
from slaktbusken.gedcom.parser import GedcomLine, parse_gedcom
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.import_service import ImportService
from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.report_service import ReportService
from slaktbusken.services.validation_service import ValidationService
from tests.test_gedcom_roundtrip.fixtures import load_mergetest
from tests.test_gedcom_roundtrip.strategies import name_lists, person_projects

pytestmark = pytest.mark.mandatory_integrity

_FILE_HEAD = "0 HEAD\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def export_text(data: ProjectData) -> str:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "out.ged"
        GEDCOMExporter().export(data, path)
        return path.read_text(encoding="utf-8")


def _run_import(ps: ProjectService, root: Path, text: str, name: str) -> ImportResult:
    gedcom = root / name
    gedcom.write_text(text, encoding="utf-8")
    service = ImportService(ValidationService(), ReportService())
    return service.run(ps.data, gedcom, ps.project_path.parent, ps)


def import_text(text: str) -> tuple[ProjectData, ImportResult]:
    """Import GEDCOM text into a new empty project and return its data."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        ps = ProjectService()
        ps.create_project("Mål", root / "proj")
        result = _run_import(ps, root, text, "in.ged")
        return ps.data, result


def roundtrip(data: ProjectData) -> tuple[ProjectData, str]:
    text = export_text(data)
    imported, _ = import_text(text)
    return imported, text


def name_tuples(person: Person) -> list[tuple[str, str, str]]:
    return [(n.type, n.given, n.surname) for n in person.names]


def signature(person: Person) -> tuple:
    return (name_tuples(person), person.sex, person.notes,
            person.title, person.occupation)


def signatures(data: ProjectData) -> list[tuple]:
    # repr orders None and str together; None and "" stay distinct.
    return sorted((signature(p) for p in data.persons), key=repr)


def indi_records(text: str) -> list[GedcomLine]:
    return [r for r in parse_gedcom(text).records if r.tag == "INDI"]


def children(node: GedcomLine, tag: str) -> list[GedcomLine]:
    return [c for c in node.children if c.tag == tag]


def names_of(imported: ProjectData, given: str, surname: str) -> list[Person]:
    return [p for p in imported.persons
            if any(n.given == given and n.surname == surname for n in p.names)]


def indi_block(xref: str, names: list[tuple[str, Optional[str]]],
               extra: str = "") -> str:
    """An INDI record with ``(name, type_or_None)`` NAME lines."""
    lines = [f"0 {xref} INDI"]
    for value, type_ in names:
        lines.append(f"1 NAME {value}")
        if type_ is not None:
            lines.append(f"2 TYPE {type_}")
    return "\n".join(lines) + "\n" + extra


def gedcom_file(*blocks: str) -> str:
    return _FILE_HEAD + "".join(blocks) + "0 TRLR\n"


def person_types(data: ProjectData) -> list[str]:
    assert len(data.persons) == 1
    return [n.type for n in data.persons[0].names]


# ---------------------------------------------------------------------------
# Property 2 (person part): notes, titles and occupations
# ---------------------------------------------------------------------------


# Feature: gedcom-roundtrip-0-3-0, Property 2: Free text round-trips
# **Validates: Requirements 2.1, 2.2, 2.3, 2.5**
@given(person_projects())
def test_person_notes_title_and_occupation_roundtrip(data: ProjectData) -> None:
    imported, text = roundtrip(data)
    assert signatures(imported) == signatures(data)
    assert max(len(line) for line in text.split("\n")) <= 255


def test_person_text_with_multiline_at_and_special_characters() -> None:
    note = ("@Första raden med @ i mitten\n@@dubbel\n  inledande mellanslag \n"
            "\nÅÄÖ åäö é – ñ\nSista raden ")
    person = Person(id="person_1", sex="M", title="@Dr  ", occupation="@Lektor",
                    notes=note, names=[Name("birth", "Anna", "Test")])
    imported, text = roundtrip(ProjectData(persons=[person]))
    assert text.count("1 NOTE @@Första") == 1
    assert "1 TITL @@Dr" in text
    assert "1 OCCU @@Lektor" in text
    result = imported.persons[0]
    assert (result.notes, result.title, result.occupation) == (
        note, "@Dr  ", "@Lektor")


def test_long_person_note_is_split_with_conc_and_restored() -> None:
    note = ("Lång anteckning å ä ö @ " * 40).rstrip() + "\nSlut"
    person = Person(id="person_1", sex="F", notes=note,
                    names=[Name("birth", "Anna", "Test")])
    imported, text = roundtrip(ProjectData(persons=[person]))
    assert "CONC" in text and "CONT" in text
    assert imported.persons[0].notes == note


def test_empty_notes_title_and_occupation_write_no_lines() -> None:
    person = Person(id="person_1", sex="M", names=[Name("birth", "Anna", "Test")])
    imported, text = roundtrip(ProjectData(persons=[person]))
    indi = indi_records(text)[0]
    for tag in ("NOTE", "TITL", "OCCU"):
        assert children(indi, tag) == []
    result = imported.persons[0]
    assert (result.notes, result.title, result.occupation) == ("", None, None)


@pytest.fixture(scope="module")
def mergetest_roundtrip() -> tuple[ProjectData, ProjectData, str]:
    data = load_mergetest()
    imported, text = roundtrip(data)
    return data, imported, text


def _original(data: ProjectData, given: str, surname: str, **attrs) -> Person:
    found = [p for p in data.persons
             if any(n.given == given and n.surname == surname for n in p.names)
             and all(getattr(p, k) == v for k, v in attrs.items())]
    assert len(found) == 1
    return found[0]


@pytest.mark.parametrize("given,surname,field,value", [
    ("Janne", "Karlsson", "notes", "Janne Carlsson är en testperson."),
    ("Jan", "Karlsson", "notes", "Har inte hittat pappan ännu."),
    ("Sune", "Persson", "title", "Major"),
])
def test_mergetest_person_text_survives(mergetest_roundtrip, given, surname,
                                        field, value) -> None:
    data, imported, text = mergetest_roundtrip
    original = _original(data, given, surname, **{field: value})
    matches = [p for p in names_of(imported, given, surname)
               if signature(p) == signature(original)]
    assert len(matches) == 1
    assert getattr(matches[0], field) == value
    assert value in text


def test_mergetest_person_signatures_survive(mergetest_roundtrip) -> None:
    data, imported, _ = mergetest_roundtrip
    assert signatures(imported) == signatures(data)


def test_person_title_is_not_confused_with_source_title() -> None:
    text = gedcom_file(
        indi_block("@I1@", [("Sune /Persson/", "birth")],
                   "1 SEX M\n1 TITL Major\n1 SOUR @S1@\n"),
        "0 @S1@ SOUR\n1 TITL Kyrkbok för Testsocken\n",
    )
    imported, _ = import_text(text)
    assert imported.persons[0].title == "Major"
    titles = [s.title for s in imported.sources]
    assert titles == ["Kyrkbok för Testsocken"]
    # And on the way out: the source keeps its title, the person its own.
    out = export_text(imported)
    indi = indi_records(out)[0]
    assert [c.value for c in children(indi, "TITL")] == ["Major"]
    sour = next(r for r in parse_gedcom(out).records if r.tag == "SOUR")
    assert [c.value for c in children(sour, "TITL")] == ["Kyrkbok för Testsocken"]


def test_mergetest_source_titles_and_person_titles_stay_apart(
        mergetest_roundtrip) -> None:
    data, imported, _ = mergetest_roundtrip
    assert sorted(s.title for s in imported.sources) == sorted(
        s.title for s in data.sources)
    person_titles = {p.title for p in data.persons if p.title}
    assert person_titles
    assert not person_titles & {s.title for s in imported.sources}
    assert sorted(p.title for p in imported.persons if p.title) == sorted(
        p.title for p in data.persons if p.title)


# ---------------------------------------------------------------------------
# Property 3: name types and order
# ---------------------------------------------------------------------------


# Feature: gedcom-roundtrip-0-3-0, Property 3: Name types and order round-trip
# **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**
@given(name_lists(1, 5))
def test_name_types_and_order_roundtrip(names: list[Name]) -> None:
    person = Person(id="person_1", sex="U", names=names)
    text = export_text(ProjectData(persons=[person]))
    # Every NAME carries a TYPE (criterion 1).
    nodes = children(indi_records(text)[0], "NAME")
    assert len(nodes) == len(names)
    assert all(len(children(n, "TYPE")) == 1 for n in nodes)
    imported, _ = import_text(text)
    assert [name_tuples(p) for p in imported.persons] == [name_tuples(person)]


def test_name_type_mapping_is_written() -> None:
    names = [Name("birth", "A", "B"), Name("married", "A", "C"),
             Name("alias", "A", "D"), Name("adopted", "A", "E"),
             Name("other", "A", "F")]
    text = export_text(ProjectData(persons=[
        Person(id="person_1", sex="U", names=names)]))
    nodes = children(indi_records(text)[0], "NAME")
    assert [children(n, "TYPE")[0].value for n in nodes] == [
        "birth", "married", "aka", "adopted", "other"]


def test_stina_jansson_stays_married_as_stina_persson(mergetest_roundtrip) -> None:
    _, imported, _ = mergetest_roundtrip
    stina = [p for p in names_of(imported, "Stina", "Jansson")
             if any(n.surname == "Persson" for n in p.names)]
    assert len(stina) == 1
    assert name_tuples(stina[0]) == [("birth", "Stina", "Jansson"),
                                     ("married", "Stina", "Persson")]


def test_jan_jonsson_second_birth_name_stays_birth(mergetest_roundtrip) -> None:
    _, imported, _ = mergetest_roundtrip
    jan = names_of(imported, "Jan", "Jönsson")
    assert len(jan) == 1
    assert name_tuples(jan[0]) == [("birth", "Jan", "Jönsson"),
                                   ("birth", "Jan", "Jonsson")]


def test_married_name_first_in_the_list_is_not_inferred_as_birth() -> None:
    person = Person(id="person_1", sex="F", names=[
        Name("married", "Stina", "Persson"), Name("birth", "Stina", "Jansson")])
    imported, _ = roundtrip(ProjectData(persons=[person]))
    assert name_tuples(imported.persons[0]) == name_tuples(person)


def test_no_type_uses_the_positional_rule() -> None:
    text = gedcom_file(indi_block(
        "@I1@", [("A /X/", None), ("B /X/", None), ("C /X/", None)]))
    imported, _ = import_text(text)
    assert person_types(imported) == ["birth", "other", "other"]


@pytest.mark.parametrize("given_type,expected", [
    ("birth", "birth"), ("maiden", "birth"), ("married", "married"),
    ("aka", "alias"), ("adopted", "adopted"), ("other", "other"),
    ("immigrant", "other"), ("Birth", None),
])
def test_type_mapping_on_import(given_type: str, expected: Optional[str]) -> None:
    text = gedcom_file(indi_block("@I1@", [("A /X/", given_type)]))
    imported, _ = import_text(text)
    if expected is None:  # case rule is not specified: only require a valid type
        assert person_types(imported)[0] in {"birth", "other"}
    else:
        assert person_types(imported) == [expected]


def test_mixed_type_untyped_name_is_other_and_never_positional() -> None:
    text = gedcom_file(indi_block(
        "@I1@", [("Stina /Persson/", "married"), ("Stina /Jansson/", None),
                 ("Stina /Berg/", "birth"), ("Stina /Ek/", None)]))
    imported, _ = import_text(text)
    # The first name has a TYPE, the untyped first-after names are 'other'.
    assert person_types(imported) == ["married", "other", "birth", "other"]


def test_mixed_type_untyped_first_name_is_other_not_birth() -> None:
    text = gedcom_file(indi_block(
        "@I1@", [("Stina /Jansson/", None), ("Stina /Persson/", "married")]))
    imported, _ = import_text(text)
    assert person_types(imported) == ["other", "married"]


def test_update_without_types_keeps_existing_types() -> None:
    original = Person(id="person_1", sex="F", names=[
        Name("birth", "Stina", "Jansson"), Name("married", "Stina", "Persson"),
        Name("alias", "Stinnan", "Jansson")])
    text = export_text(ProjectData(persons=[original]))
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        ps = ProjectService()
        ps.create_project("Mål", root / "proj")
        _run_import(ps, root, text, "first.ged")
        assert len(ps.data.persons) == 1
        # Same person re-imported from a file in which no NAME has a TYPE,
        # with the names in a different order.
        untyped = gedcom_file(indi_block(
            "@I1@", [("Stina /Jansson/", None), ("Stinnan /Jansson/", None),
                     ("Stina /Persson/", None)], "1 SEX F\n"))
        _run_import(ps, root, untyped, "second.ged")
        assert len(ps.data.persons) == 1
        by_name = {(n.given, n.surname): n.type for n in ps.data.persons[0].names}
        assert by_name[("Stina", "Jansson")] == "birth"
        assert by_name[("Stina", "Persson")] == "married"
        assert by_name[("Stinnan", "Jansson")] == "alias"


# ---------------------------------------------------------------------------
# Property 5 (sex part): sex round-trips and is never inferred
# ---------------------------------------------------------------------------


# Feature: gedcom-roundtrip-0-3-0, Property 5: Partners, roles, order and sex round-trip, and sex is never inferred
# **Validates: Requirements 4.8, 4.9**
@given(person_projects())
def test_sex_roundtrips_for_every_person(data: ProjectData) -> None:
    imported, text = roundtrip(data)
    assert sorted(p.sex for p in imported.persons) == sorted(
        p.sex for p in data.persons)
    for person, indi in zip(data.persons, indi_records(text)):
        sex = children(indi, "SEX")
        assert len(sex) == 1
        assert sex[0].value == ("U" if person.sex == "X" else person.sex)
        tags = [c.value for c in children(sex[0], "_SLK_SEX")]
        assert tags == (["X"] if person.sex == "X" else [])


@pytest.mark.parametrize("sex", ["M", "F", "U", "X"])
def test_each_sex_value_roundtrips(sex: str) -> None:
    person = Person(id="person_1", sex=sex, names=[Name("birth", "Anna", "Test")])
    imported, _ = roundtrip(ProjectData(persons=[person]))
    assert imported.persons[0].sex == sex


def test_slk_tag_sex_x() -> None:
    person = Person(id="person_1", sex="X", names=[Name("birth", "Anna", "Test")])
    text = export_text(ProjectData(persons=[person]))
    assert "1 SEX U\n2 _SLK_SEX X\n" in text
    imported, _ = import_text(text)
    assert imported.persons[0].sex == "X"
    # A reader that does not know the tag sees SEX U: without the tag it is U.
    imported, _ = import_text(text.replace("2 _SLK_SEX X\n", ""))
    assert imported.persons[0].sex == "U"


def test_sex_u_is_written_as_sex_u_without_slk_tag() -> None:
    person = Person(id="person_1", sex="U", names=[Name("birth", "Anna", "Test")])
    text = export_text(ProjectData(persons=[person]))
    assert "1 SEX U\n" in text
    assert "_SLK_SEX" not in text


def test_missing_sex_line_imports_as_unknown() -> None:
    text = gedcom_file(indi_block("@I1@", [("Anna /Test/", "birth")]))
    imported, _ = import_text(text)
    assert imported.persons[0].sex == "U"
