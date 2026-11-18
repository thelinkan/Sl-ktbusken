"""Families and partner roles: Properties 1, 4, 5 and 6 and the examples of
Requirement 4 criterion 16.

Round trips go through ``GEDCOMExporter`` and ``ImportService.run`` into a real
empty project (``ProjectService.create_project``). Persons are given unique
labels (``P1``, ``P2`` ...) before the export, because the importer creates new
ids; the labels are the keys that match imported persons to original ones.
"""

from __future__ import annotations

import copy
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest
from hypothesis import given
from hypothesis import strategies as st

from slaktbusken.gedcom.exporter import ExportResult, GEDCOMExporter
from slaktbusken.gedcom.importer import ImportResult
from slaktbusken.gedcom.parser import GedcomLine, parse_gedcom
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.persistence.serialization import serialize
from slaktbusken.services.import_service import ImportService
from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.report_service import ReportService
from slaktbusken.services.validation_service import ValidationService
from tests.test_gedcom_roundtrip import synthetic as syn
from tests.test_gedcom_roundtrip.fixtures import load_mergetest
from tests.test_gedcom_roundtrip.strategies import (
    event_projects,
    parentage_projects,
    partner_projects,
)

pytestmark = pytest.mark.mandatory_integrity

FAMILY_EVENT_TAGS = {"MARR", "DIV", "ENGA", "DIVF", "EVEN"}
FAMILY_TYPES = ("marriage", "divorce", "engagement", "divorce_filed",
                "custom_family_event")
PLACEHOLDER_WARNING = "teknisk platshållare"
CLOSING_LINE = "Program som inte läser _SLK_PARTNER"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def label_persons(data: ProjectData) -> ProjectData:
    """Return a copy in which every person has the unique name ``P<n>``."""
    data = copy.deepcopy(data)
    for index, person in enumerate(data.persons, start=1):
        for name in person.names:
            name.given, name.surname = f"P{index}", "X"
    return data


def label_of(person: Person) -> str:
    return person.names[0].given


def export_text(data: ProjectData) -> tuple[str, ExportResult]:
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "out.ged"
        result = GEDCOMExporter().export(data, path)
        return path.read_text(encoding="utf-8"), result


def import_text(text: str) -> tuple[ProjectData, ImportResult]:
    """Import GEDCOM text into a new empty project and return its data."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        ps = ProjectService()
        ps.create_project("Mål", root / "proj")
        gedcom = root / "in.ged"
        gedcom.write_text(text, encoding="utf-8")
        service = ImportService(ValidationService(), ReportService())
        result = service.run(ps.data, gedcom, ps.project_path.parent, ps)
        return ps.data, result


def roundtrip(data: ProjectData) -> tuple[ProjectData, ImportResult, str, ExportResult]:
    text, export = export_text(data)
    imported, result = import_text(text)
    return imported, result, text, export


@dataclass
class FamilyView:
    """A family in label terms: ordered ``(label, role)`` pairs."""

    partners: list[tuple[str, str]]
    links: set[tuple[str, Optional[str], str]]


def family_views(data: ProjectData) -> dict[frozenset[str], FamilyView]:
    labels = {p.id: label_of(p) for p in data.persons}
    views: dict[frozenset[str], FamilyView] = {}
    for fam in data.families:
        partners = [(labels[p.person_id], p.role) for p in fam.partners]
        links = {
            (labels[link.child_id],
             labels[link.parent_id] if link.parent_id else None,
             link.parentage_type)
            for link in fam.parent_child_links
        }
        key = frozenset(label for label, _ in partners)
        if key in views:
            # The importer re-syncs foster and adoptive links onto a family
            # that is derived from the placement event (existing behaviour,
            # same parents). The first family keeps the partners; the links of
            # all families of one partner set are compared together.
            views[key].links |= links
        else:
            views[key] = FamilyView(partners, links)
    return views


def sex_by_label(data: ProjectData) -> dict[str, str]:
    return {label_of(p): p.sex for p in data.persons}


def fam_records(text: str) -> list[GedcomLine]:
    return [r for r in parse_gedcom(text).records if r.tag == "FAM"]


def indi_records(text: str) -> list[GedcomLine]:
    return [r for r in parse_gedcom(text).records if r.tag == "INDI"]


def _children(node: GedcomLine, tag: str) -> list[GedcomLine]:
    return [c for c in node.children if c.tag == tag]


def _walk(node: GedcomLine):
    yield node
    for child in node.children:
        yield from _walk(child)


def slot_xrefs(fam: GedcomLine) -> tuple[list[str], list[str]]:
    return ([c.value for c in _children(fam, "HUSB")],
            [c.value for c in _children(fam, "WIFE")])


def label_by_xref(text: str) -> dict[str, str]:
    """INDI cross-reference to the person label (the NAME given part)."""
    result = {}
    for indi in indi_records(text):
        name = _children(indi, "NAME")[0].value or ""
        result[indi.xref_id] = re.sub(r"/.*", "", name).strip().split(" ")[0]
    return result


def expected_conflicts(husb: Optional[str], wife: Optional[str],
                       sex: dict[str, str]) -> bool:
    """Placeholder_Conflict by definition (design glossary), on labels."""
    for slot, label in (("HUSB", husb), ("WIFE", wife)):
        if label is None:
            continue
        if (sex[label] == "M" and slot == "WIFE") or (
                sex[label] == "F" and slot == "HUSB") or sex[label] == "X":
            return True
    return False


def expected_slots(partners: list[str], sex: dict[str, str]
                   ) -> tuple[Optional[str], Optional[str]]:
    """The placeholder rule of Requirement 4 criteria 1 and 2 (one partner:
    the slot of a known sex, else HUSB)."""
    if len(partners) == 1:
        return (None, partners[0]) if sex[partners[0]] == "F" else (partners[0], None)
    first, second = partners
    if {sex[first], sex[second]} == {"M", "F"}:
        return (first, second) if sex[first] == "M" else (second, first)
    return first, second


def check_slots(data: ProjectData, text: str, export: ExportResult) -> None:
    """Assert the placeholder rule on the FAM records of ``text``."""
    sex = sex_by_label(data)
    labels = label_by_xref(text)
    persons_by_id = {p.id: label_of(p) for p in data.persons}
    records = fam_records(text)
    assert len(records) == len(data.families)
    conflicts = 0
    for family, record in zip(data.families, records):
        husb_x, wife_x = slot_xrefs(record)
        assert len(husb_x) <= 1 and len(wife_x) <= 1
        written = [x for x in husb_x + wife_x]
        assert len(written) == len(set(written)) == len(family.partners)
        partners = [persons_by_id[p.person_id] for p in family.partners]
        want_husb, want_wife = expected_slots(partners, sex)
        assert (labels[husb_x[0]] if husb_x else None) == want_husb
        assert (labels[wife_x[0]] if wife_x else None) == want_wife
        conflicts += expected_conflicts(want_husb, want_wife, sex)
    family_warnings = [w for w in export.warnings if PLACEHOLDER_WARNING in w]
    assert len(family_warnings) == conflicts
    closing = [w for w in export.warnings if w.startswith(CLOSING_LINE)]
    assert len(closing) == (1 if conflicts else 0)


# ---------------------------------------------------------------------------
# Property 1
# ---------------------------------------------------------------------------


def _expected_home(data: ProjectData) -> dict[str, Optional[str]]:
    """Event id to the family id that must hold it, or None for the fallback."""
    home: dict[str, Optional[str]] = {}
    for event in data.events:
        if event.type not in FAMILY_TYPES:
            continue
        listed = [f.id for f in data.families if event.id in f.event_ids]
        if listed:
            home[event.id] = listed[0]
            continue
        people = frozenset(p.person_id for p in event.participants)
        matches = [f.id for f in data.families
                   if people and frozenset(p.person_id for p in f.partners) == people]
        home[event.id] = matches[0] if len(matches) == 1 else None
    return home


def assert_family_events_once(data: ProjectData) -> None:
    before = serialize(data)
    text, export = export_text(data)
    assert serialize(data) == before  # the export leaves the project unchanged
    home = _expected_home(data)
    records = fam_records(text)
    assert len(records) == len(data.families)  # no family record is invented

    in_fam: dict[str, list[str]] = {}  # token -> family ids holding it
    for family, record in zip(data.families, records):
        for node in record.children:
            if node.tag not in FAMILY_EVENT_TAGS:
                continue
            for token in (c.value for c in _children(node, "_SLK_EID")):
                in_fam.setdefault(token, []).append(family.id)
    in_indi: dict[str, int] = {}  # token -> number of INDI structures
    for indi in indi_records(text):
        for node in indi.children:
            for token in (c.value for c in _children(node, "_SLK_EID")):
                in_indi[token] = in_indi.get(token, 0) + 1

    fallback = 0
    for event_id, family_id in home.items():
        if family_id is not None:
            assert in_fam.get(event_id) == [family_id], event_id
            assert event_id not in in_indi, event_id
        else:
            fallback += 1
            assert event_id not in in_fam, event_id
            assert in_indi.get(event_id, 0) >= 1, event_id
    notices = [w for w in export.warnings if "hör inte till någon enskild familj" in w]
    assert len(notices) == fallback


# Feature: gedcom-roundtrip-0-3-0, Property 1: Every family event is written exactly once, in the right family, without changing the project
# **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**
@given(event_projects(citations=False))
def test_every_family_event_is_written_exactly_once(data: ProjectData) -> None:
    assert_family_events_once(data)


@given(event_projects(citations=True))
def test_every_family_event_is_written_exactly_once_with_citations(
    data: ProjectData,
) -> None:
    assert_family_events_once(data)


def test_event_listed_in_two_families_goes_to_the_first() -> None:
    data = syn.build_synthetic_project()
    first, second = data.families[0], data.families[1]
    event_id = first.event_ids[0]
    second.event_ids.append(event_id)
    assert_family_events_once(data)


def test_orphan_matching_two_families_is_a_fallback() -> None:
    data = syn.build_synthetic_project()
    # Sara + Nils get a second family with the same partner set.
    sara_nils = next(f for f in data.families
                     if {p.person_id for p in f.partners} == {"person_12", "person_13"})
    data.families.append(
        Family(id="family_dup", partners=list(sara_nils.partners), children=[]))
    home = _expected_home(data)
    assert None in home.values()
    assert_family_events_once(data)


def test_synthetic_orphan_marriage_attaches_to_its_family() -> None:
    data = syn.build_synthetic_project()
    assert_family_events_once(data)


def test_mergetest_orphan_marriage_of_arne_and_siv_goes_into_their_family() -> None:
    data = load_mergetest()
    persons = {p.id: p for p in data.persons}
    orphan = next(
        e for e in data.events
        if e.type == "marriage" and e.date and e.date.value == "1977-11-22")
    names = {persons[p.person_id].names[0].given for p in orphan.participants}
    assert names == {"Siv", "Arne"}
    assert all(orphan.id not in f.event_ids for f in data.families)
    people = {p.person_id for p in orphan.participants}
    family = [f for f in data.families if {p.person_id for p in f.partners} == people]
    assert len(family) == 1

    text, export = export_text(data)
    records = {r.xref_id: r for r in fam_records(text)}
    holder = records[GEDCOMExporter()._to_gedcom_id(family[0].id)]
    marriages = [n for n in _children(holder, "MARR")
                 if any(c.tag == "DATE" and "22 NOV 1977" in (c.value or "")
                        for c in n.children)]
    assert len(marriages) == 1
    # Written exactly once in the whole file, and not as a fallback.
    assert text.count("22 NOV 1977") == 1
    assert not any("hör inte till någon enskild familj" in w and "1977-11-22" in w
                   for w in export.warnings)

    imported, _ = import_text(text)
    pmap = {p.id: p for p in imported.persons}
    marriage = [e for e in imported.events
                if e.type == "marriage" and e.date and e.date.value == "1977-11-22"]
    assert len(marriage) == 1
    assert {pmap[p.person_id].names[0].given for p in marriage[0].participants} == {
        "Siv", "Arne"}
    holder_family = [f for f in imported.families if marriage[0].id in f.event_ids]
    assert len(holder_family) == 1
    assert {p.person_id for p in holder_family[0].partners} == {
        p.person_id for p in marriage[0].participants}


# ---------------------------------------------------------------------------
# Property 4
# ---------------------------------------------------------------------------


# Feature: gedcom-roundtrip-0-3-0, Property 4: Placeholder slots follow the placeholder rule and never repeat
# **Validates: Requirements 4.1, 4.2, 4.3, 4.14**
@given(partner_projects())
def test_placeholder_slots_follow_the_rule(data: ProjectData) -> None:
    data = label_persons(data)
    text, export = export_text(data)
    check_slots(data, text, export)
    for record in fam_records(text):
        entries = _children(record, "_SLK_PARTNER")
        assert len(entries) == len(data.families[0].partners)


# ---------------------------------------------------------------------------
# Property 5
# ---------------------------------------------------------------------------


def assert_partners_roundtrip(data: ProjectData, imported: ProjectData) -> None:
    before, after = family_views(data), family_views(imported)
    assert before.keys() == after.keys()
    for key, view in before.items():
        assert after[key].partners == view.partners  # order and roles
    assert sex_by_label(imported) == sex_by_label(data)


def drop_slk_partner(text: str) -> str:
    """Remove every ``_SLK_PARTNER`` entry with its children."""
    out: list[str] = []
    skipping = False
    for line in text.split("\n"):
        level = line.split(" ", 1)[0]
        if line.startswith("1 _SLK_PARTNER"):
            skipping = True
            continue
        if skipping and level.isdigit() and int(level) > 1:
            continue
        skipping = False
        out.append(line)
    return "\n".join(out)


# Feature: gedcom-roundtrip-0-3-0, Property 5: Partners, roles, order and sex round-trip, and sex is never inferred
# **Validates: Requirements 4.4, 4.5, 4.8, 4.9, 4.11, 4.12, 4.13, 4.17, 4.18**
@given(partner_projects())
def test_partners_roles_order_and_sex_roundtrip(data: ProjectData) -> None:
    data = label_persons(data)
    imported, _result, text, _export = roundtrip(data)
    assert_partners_roundtrip(data, imported)
    # Without _SLK_PARTNER the slots give the roles, but no sex changes.
    stripped, _ = import_text(drop_slk_partner(text))
    assert sex_by_label(stripped) == sex_by_label(data)
    sex = sex_by_label(data)
    for key, view in family_views(data).items():
        husb, wife = expected_slots([label for label, _ in view.partners], sex)
        want = ([(husb, "husband")] if husb else []) + ([(wife, "wife")] if wife else [])
        assert family_views(stripped)[key].partners == want


# ---------------------------------------------------------------------------
# Property 6
# ---------------------------------------------------------------------------


# Feature: gedcom-roundtrip-0-3-0, Property 6: Parentage links round-trip
# **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
@given(parentage_projects())
def test_parentage_links_roundtrip(data: ProjectData) -> None:
    data = label_persons(data)
    imported, _result, _text, _export = roundtrip(data)
    before, after = family_views(data), family_views(imported)
    assert before.keys() == after.keys()
    for key in before:
        assert after[key].links == before[key].links


# ---------------------------------------------------------------------------
# Examples of Requirement 4 criterion 16
# ---------------------------------------------------------------------------


def couple(sexes: list[str], roles: list[str]) -> ProjectData:
    persons = [Person(id=f"person_{i}", sex=s, names=[Name("birth", f"P{i}", "X")])
               for i, s in enumerate(sexes, start=1)]
    partners = [FamilyPartner(p.id, r) for p, r in zip(persons, roles)]
    return ProjectData(persons=persons,
                       families=[Family(id="family_1", partners=partners, children=[])])


CASES = {
    "M+F": (["M", "F"], ["husband", "wife"], False),
    "M+M": (["M", "M"], ["husband", "husband"], True),
    "F+F": (["F", "F"], ["wife", "wife"], True),
    "M+U": (["M", "U"], ["partner", "partner"], False),
    "U+F": (["U", "F"], ["partner", "partner"], False),
    "X+M": (["X", "M"], ["partner", "husband"], True),
    "make/maka F,M": (["F", "M"], ["make/maka", "make/maka"], False),
    "partner both": (["M", "F"], ["partner", "partner"], False),
    "reversed order F,M": (["F", "M"], ["wife", "husband"], False),
    "one partner F": (["F"], ["mother"], False),
    "one partner M": (["M"], ["father"], False),
    "one partner X": (["X"], ["partner"], True),
    "one partner U": (["U"], ["partner"], False),
}


@pytest.mark.parametrize("case", sorted(CASES))
def test_partner_case_roundtrips(case: str) -> None:
    sexes, roles, _ = CASES[case]
    data = couple(sexes, roles)
    imported, _result, text, export = roundtrip(data)
    check_slots(data, text, export)
    assert_partners_roundtrip(data, imported)
    entries = _children(fam_records(text)[0], "_SLK_PARTNER")
    assert len(entries) == len(sexes)
    assert [_children(e, "_SLK_ROLE")[0].value for e in entries] == roles


@pytest.mark.parametrize("case", sorted(CASES))
def test_partner_case_warning_exactly_when_conflict(case: str) -> None:
    sexes, roles, expect = CASES[case]
    _text, export = export_text(couple(sexes, roles))
    has_warning = any(PLACEHOLDER_WARNING in w for w in export.warnings)
    assert has_warning is expect


def test_sex_x_survives_the_roundtrip() -> None:
    data = couple(["X", "U"], ["partner", "partner"])
    imported, _result, text, _export = roundtrip(data)
    assert "2 _SLK_SEX X" in text
    assert sex_by_label(imported) == {"P1": "X", "P2": "U"}


def test_make_maka_role_is_valid_and_kept() -> None:
    from slaktbusken.model.validators import validate_family
    data = couple(["F", "M"], ["make/maka", "make/maka"])
    assert validate_family(data.families[0], {p.id for p in data.persons}) == []
    imported, *_ = roundtrip(data)
    assert family_views(imported)[frozenset({"P1", "P2"})].partners == [
        ("P1", "make/maka"), ("P2", "make/maka")]


def test_two_warnings_for_two_conflict_families() -> None:
    persons = [Person(id=f"person_{i}", sex=s, names=[Name("birth", f"P{i}", "X")])
               for i, s in enumerate(["F", "F", "X", "U"], start=1)]
    data = ProjectData(persons=persons, families=[
        Family(id="family_1", children=[],
               partners=[FamilyPartner("person_1", "wife"),
                         FamilyPartner("person_2", "wife")]),
        Family(id="family_2", children=[],
               partners=[FamilyPartner("person_3", "partner"),
                         FamilyPartner("person_4", "partner")]),
    ])
    _text, export = export_text(data)
    assert sum(PLACEHOLDER_WARNING in w for w in export.warnings) == 2
    assert sum(w.startswith(CLOSING_LINE) for w in export.warnings) == 1


# ---------------------------------------------------------------------------
# Sex is never inferred (Requirement 4 criteria 12, 13, 18)
# ---------------------------------------------------------------------------

_FILE_HEAD = "0 HEAD\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n"


def _indi(xref: str, given: str, sex: Optional[str]) -> str:
    lines = [f"0 {xref} INDI", f"1 NAME {given} /Test/"]
    if sex is not None:
        lines.append(f"1 SEX {sex}")
    return "\n".join(lines) + "\n"


def test_importer_never_sets_sex_from_husb_or_wife() -> None:
    text = (
        _FILE_HEAD
        + _indi("@I1@", "Ada", "M") + _indi("@I2@", "Bo", None)
        + _indi("@I3@", "Cy", "F") + _indi("@I4@", "Di", "U")
        + "0 @F1@ FAM\n1 HUSB @I2@\n1 WIFE @I1@\n"      # M in WIFE, none in HUSB
        + "0 @F2@ FAM\n1 HUSB @I3@\n1 WIFE @I4@\n"      # F in HUSB, U in WIFE
        + "0 TRLR\n"
    )
    imported, _ = import_text(text)
    assert sex_by_label(imported) == {"Ada": "M", "Bo": "U", "Cy": "F", "Di": "U"}
    views = {frozenset(k): v for k, v in family_views(imported).items()}
    assert views[frozenset({"Ada", "Bo"})].partners == [("Bo", "husband"),
                                                        ("Ada", "wife")]


def test_slk_partner_keeps_roles_and_sex_of_a_male_wife() -> None:
    text = (
        _FILE_HEAD + "1 _SLK_VERS 1\n"
        + _indi("@I1@", "Ada", "M") + _indi("@I2@", "Bo", None)
        + "0 @F1@ FAM\n1 HUSB @I2@\n1 WIFE @I1@\n"
        + "1 _SLK_PARTNER @I1@\n2 _SLK_ROLE father\n"
        + "1 _SLK_PARTNER @I2@\n2 _SLK_ROLE make/maka\n"
        + "0 TRLR\n"
    )
    imported, _ = import_text(text)
    assert sex_by_label(imported) == {"Ada": "M", "Bo": "U"}
    view = family_views(imported)[frozenset({"Ada", "Bo"})]
    assert view.partners == [("Ada", "father"), ("Bo", "make/maka")]


# ---------------------------------------------------------------------------
# Old files, mismatch, foster families
# ---------------------------------------------------------------------------


def test_old_file_without_slk_partner_gets_husband_and_wife() -> None:
    text = (
        _FILE_HEAD + _indi("@I1@", "Ada", "F") + _indi("@I2@", "Bo", "M")
        + "0 @F1@ FAM\n1 HUSB @I2@\n1 WIFE @I1@\n0 TRLR\n"
    )
    imported, _ = import_text(text)
    assert family_views(imported)[frozenset({"Ada", "Bo"})].partners == [
        ("Bo", "husband"), ("Ada", "wife")]


def test_slk_partner_mismatch_is_ignored_with_a_warning() -> None:
    text = (
        _FILE_HEAD + "1 _SLK_VERS 1\n"
        + _indi("@I1@", "Ada", "F") + _indi("@I2@", "Bo", "M")
        + _indi("@I3@", "Cy", "M")
        + "0 @F1@ FAM\n1 HUSB @I2@\n1 WIFE @I1@\n"
        + "1 _SLK_PARTNER @I1@\n2 _SLK_ROLE mother\n"
        + "1 _SLK_PARTNER @I3@\n2 _SLK_ROLE father\n"
        + "0 TRLR\n"
    )
    imported, result = import_text(text)
    assert family_views(imported)[frozenset({"Ada", "Bo"})].partners == [
        ("Bo", "husband"), ("Ada", "wife")]
    assert any("_SLK_PARTNER" in w for w in result.warnings)


def test_foster_family_roundtrips_with_pedi_and_placement() -> None:
    data = label_persons(syn.build_synthetic_project())
    text, _export = export_text(data)
    foster = next(f for f in data.families if f.children
                  and any(l.parentage_type == "foster" for l in f.parent_child_links))
    assert "2 PEDI foster" in text
    assert "2 TYPE Fosterhem" in text
    imported, _result = import_text(text)
    key = frozenset(label_of(next(p for p in data.persons if p.id == x.person_id))
                    for x in foster.partners)
    before, after = family_views(data)[key], family_views(imported)[key]
    assert after.links == before.links
    assert {t for _, _, t in after.links} == {"foster"}


def test_foster_family_keeps_partner_roles_and_order() -> None:
    data = label_persons(syn.build_synthetic_project())
    imported, *_ = roundtrip(data)
    foster = next(f for f in data.families if any(
        l.parentage_type == "foster" for l in f.parent_child_links))
    labels = {p.id: label_of(p) for p in data.persons}
    key = frozenset(labels[x.person_id] for x in foster.partners)
    assert family_views(imported)[key].partners == family_views(data)[key].partners


def test_foster_child_does_not_remove_a_biological_sibling() -> None:
    data = couple(["M", "F"], ["husband", "wife"])
    data.persons += [Person(id=f"person_{i}", sex="U",
                            names=[Name("birth", f"P{i}", "X")]) for i in (3, 4)]
    family = data.families[0]
    family.children = ["person_3", "person_4"]
    family.parent_child_links = [
        ParentChildLink(c, p, t)
        for c, t in (("person_3", "biological"), ("person_4", "foster"))
        for p in ("person_1", "person_2")
    ]
    imported, *_ = roundtrip(data)
    key = frozenset({"P1", "P2"})
    assert family_views(imported)[key].links == family_views(data)[key].links


def test_old_file_foster_pedi_is_still_read() -> None:
    text = (
        _FILE_HEAD + _indi("@I1@", "Fa", "M") + _indi("@I2@", "Mo", "F")
        + _indi("@I3@", "Kid", "U")
        + "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n"
        + "0 TRLR\n"
    ).replace("1 NAME Kid /Test/\n", "1 NAME Kid /Test/\n1 FAMC @F1@\n2 PEDI foster\n")
    imported, _ = import_text(text)
    view = family_views(imported)[frozenset({"Fa", "Mo"})]
    assert {t for _, _, t in view.links} == {"foster"}


# ---------------------------------------------------------------------------
# One test per registry tag of the family module
# ---------------------------------------------------------------------------


def test_slk_tag_partner() -> None:
    data = couple(["F", "M"], ["wife", "make/maka"])
    text, _ = export_text(data)
    record = fam_records(text)[0]
    entries = _children(record, "_SLK_PARTNER")
    assert len(entries) == 2
    assert [_children(e, "_SLK_ROLE")[0].value for e in entries] == [
        "wife", "make/maka"]


def test_slk_tag_plink() -> None:
    data = couple(["M", "F"], ["husband", "wife"])
    data.persons.append(Person(id="person_3", sex="U",
                               names=[Name("birth", "P3", "X")]))
    family = data.families[0]
    family.children = ["person_3"]
    family.parent_child_links = [
        ParentChildLink("person_3", "person_1", "step"),
        ParentChildLink("person_3", None, "unknown_donor"),
        ParentChildLink("person_3", "person_2", "biological"),
    ]
    text, _ = export_text(data)
    child = next(i for i in indi_records(text) if _children(i, "FAMC"))
    plinks = _children(_children(child, "FAMC")[0], "_SLK_PLINK")
    assert [(p.value, _children(p, "TYPE")[0].value) for p in plinks] == [
        (next(x for x, l in label_by_xref(text).items() if l == "P1"), "step"),
        (None, "unknown_donor"),
    ]
    imported, _ = import_text(text)
    links = family_views(imported)[frozenset({"P1", "P2"})].links
    assert links == {("P3", "P1", "step"), ("P3", None, "unknown_donor"),
                     ("P3", "P2", "biological")}


def test_slk_tag_part() -> None:
    data = syn.build_synthetic_project()
    text, _ = export_text(data)
    imported, _ = import_text(text)
    # Participants and roles of a listed family event come from _SLK_PART.
    record = fam_records(text)[0]
    marr = _children(record, "MARR")[0]
    parts = _children(marr, "_SLK_PART")
    assert len(parts) == 2
    assert all(_children(p, "_SLK_ROLE")[0].value == "spouse" for p in parts)
    marriage = next(e for e in imported.events
                    if e.type == "marriage" and e.date and e.date.value == "1848-05-14")
    assert [p.role for p in marriage.participants] == ["spouse", "spouse"]
