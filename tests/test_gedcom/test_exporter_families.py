"""Exporter side of families (task 5.1): placeholders, partners, events, PLINK."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.gedcom.slk_tags import SLK_TAG_REGISTRY
from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from tests.test_gedcom_roundtrip.fixtures import load_mergetest


def _export(data: ProjectData, tmp_path: Path):
    out = tmp_path / "out.ged"
    result = GEDCOMExporter().export(data, out)
    return out.read_text(encoding="utf-8").split("\n"), result


def _records(lines: list[str]) -> dict[str, list[str]]:
    records: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in lines:
        if line.startswith("0 "):
            current = records.setdefault(line[2:], [])
        if current is not None:
            current.append(line)
    return records


def _fam(lines: list[str], family_xref: str) -> list[str]:
    for key, rec in _records(lines).items():
        if key == f"{family_xref} FAM":
            return rec
    raise AssertionError(f"no FAM {family_xref}")


def _person(pid: str, sex: str, given: str) -> Person:
    return Person(id=pid, names=[Name(type="birth", given=given, surname="X")], sex=sex)


def _project(persons, families, events=()) -> ProjectData:
    data = ProjectData()
    data.persons = list(persons)
    data.families = list(families)
    data.events = list(events)
    return data


def _marriage(eid: str, pids: list[str]) -> Event:
    return Event(
        id=eid,
        type="marriage",
        participants=[Participant(p, "make/maka") for p in pids],
        date=DateValue(value="1977-11-22", precision="day"),
    )


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


def test_fixture_exports_six_marriages_in_the_right_families(tmp_path):
    lines, _ = _export(load_mergetest(), tmp_path)
    assert sum(1 for ln in lines if ln == "1 MARR") == 6
    # The orphan marriage of person_52 and person_53 goes into family_22.
    fam22 = _fam(lines, "@F22@")
    assert "1 MARR" in fam22
    assert "2 DATE 22 NOV 1977" in fam22
    assert "2 _SLK_PART @I52@" in fam22 and "2 _SLK_PART @I53@" in fam22


def test_fixture_anna_jan_family(tmp_path):
    data = load_mergetest()
    family = next(f for f in data.families if [p.person_id for p in f.partners] == ["person_21", "person_19"])
    exporter = GEDCOMExporter()
    exporter.export(data, tmp_path / "out.ged")
    lines = (tmp_path / "out.ged").read_text(encoding="utf-8").split("\n")
    fam = _fam(lines, exporter._to_gedcom_id(family.id))
    assert fam[1:3] == ["1 HUSB @I19@", "1 WIFE @I21@"]  # Jan (M), Anna (F)
    i = fam.index("1 _SLK_PARTNER @I21@")
    assert fam[i : i + 4] == [
        "1 _SLK_PARTNER @I21@",
        "2 _SLK_ROLE make/maka",
        "1 _SLK_PARTNER @I19@",
        "2 _SLK_ROLE make/maka",
    ]


def test_fixture_writes_only_registered_slk_tags_and_each_slot_once(tmp_path):
    lines, result = _export(load_mergetest(), tmp_path)
    used = {m.group(1) for ln in lines if (m := re.match(r"^\d+ (_SLK_\w+)", ln))}
    assert used <= set(SLK_TAG_REGISTRY)
    for key, rec in _records(lines).items():
        if key.endswith(" FAM"):
            assert sum(1 for ln in rec if ln.startswith("1 HUSB")) <= 1
            assert sum(1 for ln in rec if ln.startswith("1 WIFE")) <= 1


# ---------------------------------------------------------------------------
# Slots and warnings
# ---------------------------------------------------------------------------

_CASES = [
    # (sex1, sex2, expected HUSB, expected WIFE, conflict)
    ("M", "F", "P1", "P2", False),
    ("F", "M", "P2", "P1", False),
    ("M", "M", "P1", "P2", True),
    ("F", "F", "P1", "P2", True),
    ("U", "F", "P1", "P2", False),
    ("F", "U", "P1", "P2", True),
    ("M", "U", "P1", "P2", False),
    ("X", "M", "P1", "P2", True),
]


@pytest.mark.parametrize("sex1,sex2,husb,wife,conflict", _CASES)
def test_two_partner_slots_and_warning(tmp_path, sex1, sex2, husb, wife, conflict):
    p1, p2 = _person("person_1", sex1, "Ann"), _person("person_2", sex2, "Bo")
    fam = Family(
        id="family_1",
        partners=[FamilyPartner("person_1", "make/maka"), FamilyPartner("person_2", "partner")],
        children=[],
    )
    lines, result = _export(_project([p1, p2], [fam]), tmp_path)
    rec = _fam(lines, "@F1@")
    ids = {"P1": "@I1@", "P2": "@I2@"}
    assert f"1 HUSB {ids[husb]}" in rec and f"1 WIFE {ids[wife]}" in rec
    # roles and list order are kept exactly
    assert rec[rec.index("1 _SLK_PARTNER @I1@") + 1] == "2 _SLK_ROLE make/maka"
    assert rec[rec.index("1 _SLK_PARTNER @I2@") + 1] == "2 _SLK_ROLE partner"
    assert rec.index("1 _SLK_PARTNER @I1@") < rec.index("1 _SLK_PARTNER @I2@")
    placeholder = [w for w in result.warnings if "platshållare" in w]
    assert bool(placeholder) == conflict
    if conflict:
        assert len(placeholder) == 1 and placeholder[0].startswith("Familj F1 (Ann X, Bo X)")
        assert any("visar platshållarna" in w for w in result.warnings)
    else:
        assert not any("visar platshållarna" in w for w in result.warnings)


def test_one_warning_per_conflicting_family(tmp_path):
    persons = [_person(f"person_{i}", "M", f"N{i}") for i in range(1, 5)]
    fams = [
        Family("family_1", [FamilyPartner("person_1", "partner"), FamilyPartner("person_2", "partner")], []),
        Family("family_2", [FamilyPartner("person_3", "partner"), FamilyPartner("person_4", "partner")], []),
    ]
    _, result = _export(_project(persons, fams), tmp_path)
    assert len([w for w in result.warnings if w.startswith("Familj F")]) == 2
    assert len([w for w in result.warnings if "visar platshållarna" in w]) == 1


@pytest.mark.parametrize(
    "sex,slot,conflict",
    [("M", "HUSB", False), ("F", "WIFE", False), ("U", "HUSB", False), ("X", "HUSB", True)],
)
def test_single_partner_slot(tmp_path, sex, slot, conflict):
    fam = Family("family_1", [FamilyPartner("person_1", "mother")], [])
    lines, result = _export(_project([_person("person_1", sex, "Ann")], [fam]), tmp_path)
    rec = _fam(lines, "@F1@")
    assert f"1 {slot} @I1@" in rec
    assert sum(1 for ln in rec if ln.startswith(("1 HUSB", "1 WIFE"))) == 1
    assert "1 _SLK_PARTNER @I1@" in rec and "2 _SLK_ROLE mother" in rec
    assert bool([w for w in result.warnings if "platshållare" in w]) == conflict


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def test_event_listed_in_two_families_is_written_once(tmp_path):
    persons = [_person("person_1", "M", "A"), _person("person_2", "F", "B")]
    marriage = _marriage("event_1", ["person_1", "person_2"])
    partners = [FamilyPartner("person_1", "husband"), FamilyPartner("person_2", "wife")]
    fams = [
        Family("family_1", list(partners), [], event_ids=["event_1"]),
        Family("family_2", list(partners), [], event_ids=["event_1"]),
    ]
    lines, _ = _export(_project(persons, fams, [marriage]), tmp_path)
    assert lines.count("1 MARR") == 1
    assert "1 MARR" in _fam(lines, "@F1@")


def test_ambiguous_orphan_is_not_forced_into_a_family(tmp_path):
    persons = [_person("person_1", "M", "A"), _person("person_2", "F", "B")]
    partners = [FamilyPartner("person_1", "husband"), FamilyPartner("person_2", "wife")]
    fams = [Family("family_1", list(partners), []), Family("family_2", list(partners), [])]
    exporter = GEDCOMExporter()
    out = tmp_path / "o.ged"
    exporter.export(_project(persons, fams, [_marriage("event_1", ["person_1", "person_2"])]), out)
    assert "1 MARR" not in out.read_text(encoding="utf-8")
    assert [e.id for e in exporter._fallback_family_events] == ["event_1"]


def test_divorce_filed_and_custom_family_event(tmp_path):
    persons = [_person("person_1", "M", "A"), _person("person_2", "F", "B")]
    partners = [FamilyPartner("person_1", "husband"), FamilyPartner("person_2", "wife")]
    divf = Event("event_1", "divorce_filed", [Participant("person_1", "make/maka")])
    custom = Event(
        "event_2", "custom_family_event",
        [Participant("person_1", "deltagare"), Participant("person_2", "deltagare")],
        custom_type_name="Samboende",
    )
    fam = Family("family_1", partners, [], event_ids=["event_1", "event_2"])
    lines, _ = _export(_project(persons, [fam], [divf, custom]), tmp_path)
    rec = _fam(lines, "@F1@")
    assert "1 DIVF" in rec
    assert rec[rec.index("1 EVEN") + 1] == "2 TYPE Samboende"
    assert "2 _SLK_PART @I2@" in rec and "3 _SLK_ROLE deltagare" in rec


def test_export_does_not_change_project(tmp_path):
    data = load_mergetest()
    before = repr(data)
    _export(data, tmp_path)
    assert repr(data) == before


# ---------------------------------------------------------------------------
# Parentage
# ---------------------------------------------------------------------------


def test_plink_for_non_biological_links_keeps_pedi(tmp_path):
    persons = [_person("person_1", "M", "A"), _person("person_2", "F", "B"), _person("person_3", "U", "C")]
    fam = Family(
        "family_1",
        [FamilyPartner("person_1", "father"), FamilyPartner("person_2", "mother")],
        ["person_3"],
        parent_child_links=[
            ParentChildLink("person_3", "person_1", "foster"),
            ParentChildLink("person_3", None, "step"),
        ],
    )
    lines, _ = _export(_project(persons, [fam]), tmp_path)
    indi = _records(lines)["@I3@ INDI"]
    i = indi.index("1 FAMC @F1@")
    assert indi[i : i + 6] == [
        "1 FAMC @F1@",
        "2 PEDI foster",
        "2 _SLK_PLINK @I1@",
        "3 TYPE foster",
        "2 _SLK_PLINK",
        "3 TYPE step",
    ]


def test_biological_link_writes_no_plink(tmp_path):
    persons = [_person("person_1", "M", "A"), _person("person_3", "U", "C")]
    fam = Family(
        "family_1", [FamilyPartner("person_1", "father")], ["person_3"],
        parent_child_links=[ParentChildLink("person_3", "person_1", "biological")],
    )
    lines, _ = _export(_project(persons, [fam]), tmp_path)
    assert not any("_SLK_PLINK" in ln for ln in lines)
