"""Importer side of families: _SLK_PARTNER, _SLK_PLINK and _SLK_PART (task 5.2).

Focused tests; the full family test suite is task 5.3.
"""

from __future__ import annotations

from pathlib import Path

from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.services.import_service import ImportService
from slaktbusken.services.project_service import ProjectService
from slaktbusken.services.report_service import ReportService
from slaktbusken.services.validation_service import ValidationService
from tests.test_gedcom_roundtrip import fixtures

HEAD = "0 HEAD\n1 SOUR T\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n"


_SERVICES: dict[Path, ProjectService] = {}


def _import(text: str, tmp_path: Path, data: ProjectData | None = None):
    data = data or ProjectData(project=ProjectMetadata(title="T"))
    ps = _SERVICES.get(tmp_path)
    if ps is None:
        ps = _SERVICES[tmp_path] = ProjectService()
    ps._project_data = data
    ged = tmp_path / "in.ged"
    ged.write_text(text, encoding="utf-8")
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    service = ImportService(ValidationService(), ReportService())
    result = service.run(data, ged, project, ps)
    return data, result


def _name(data: ProjectData, person_id: str) -> str:
    person = next(p for p in data.persons if p.id == person_id)
    return f"{person.names[0].given} {person.names[0].surname}".strip()


def _sex(data: ProjectData, given: str) -> str:
    return next(p.sex for p in data.persons if p.names[0].given == given)


def _indi(xref: str, given: str, sex: str | None) -> str:
    sex_line = f"1 SEX {sex}\n" if sex else ""
    return f"0 {xref} INDI\n1 NAME {given} /X/\n{sex_line}"


# ---------------------------------------------------------------------------
# Fixture round trip
# ---------------------------------------------------------------------------


def test_mergetest_roundtrip_keeps_make_maka_roles_order_and_1977_marriage(tmp_path):
    source = fixtures.load_mergetest()
    ged = tmp_path / "merge.ged"
    GEDCOMExporter().export(source, ged)

    data, result = _import(ged.read_text(encoding="utf-8"), tmp_path)

    anna_jan = [
        f for f in data.families
        if [_name(data, p.person_id) for p in f.partners] == ["Anna Östlund", "Jan Karlsson"]
        and f.partners[0].role == "make/maka"
    ]
    assert len(anna_jan) == 1
    assert [p.role for p in anna_jan[0].partners] == ["make/maka", "make/maka"]

    marriages = [
        e for e in data.events
        if e.type == "marriage" and e.date and e.date.value == "1977-11-22"
    ]
    assert len(marriages) == 1
    siv_arne = [
        f for f in data.families
        if {_name(data, p.person_id) for p in f.partners} == {"Arne Svensson", "Siv Svensson"}
    ]
    assert len(siv_arne) == 1
    assert marriages[0].id in siv_arne[0].event_ids
    assert {p.role for p in marriages[0].participants} == {"make/maka"}

    # Sex is never changed by slots.
    def _sexes(project: ProjectData) -> list[tuple[str, str, str]]:
        return sorted((p.names[0].given, p.names[0].surname, p.sex) for p in project.persons)

    assert _sexes(data) == _sexes(source)
    assert not [w for w in result.warnings if "_SLK_PARTNER" in w]


# ---------------------------------------------------------------------------
# _SLK_PARTNER
# ---------------------------------------------------------------------------

_TWO = (
    HEAD
    + _indi("@I1@", "Aa", "F") + _indi("@I2@", "Bb", "M")
    + "0 @F1@ FAM\n1 HUSB @I2@\n1 WIFE @I1@\n"
)


def test_slk_partner_restores_order_and_roles(tmp_path):
    text = _TWO + (
        "1 _SLK_PARTNER @I1@\n2 _SLK_ROLE make/maka\n"
        "1 _SLK_PARTNER @I2@\n2 _SLK_ROLE make/maka\n0 TRLR\n"
    )
    data, result = _import(text, tmp_path)
    family = data.families[0]
    assert [_name(data, p.person_id) for p in family.partners] == ["Aa X", "Bb X"]
    assert [p.role for p in family.partners] == ["make/maka", "make/maka"]
    assert not [w for w in result.warnings if "_SLK_PARTNER" in w]


def test_file_without_slk_partner_gives_husband_wife(tmp_path):
    data, _ = _import(_TWO + "0 TRLR\n", tmp_path)
    family = data.families[0]
    assert [(_name(data, p.person_id), p.role) for p in family.partners] == [
        ("Bb X", "husband"), ("Aa X", "wife"),
    ]


def test_importer_never_infers_sex_from_slots(tmp_path):
    # SEX M person in WIFE keeps M; a person without SEX in HUSB stays U.
    text = (
        HEAD + _indi("@I1@", "Mm", "M") + _indi("@I2@", "Uu", None)
        + "0 @F1@ FAM\n1 HUSB @I2@\n1 WIFE @I1@\n0 TRLR\n"
    )
    data, _ = _import(text, tmp_path)
    assert _sex(data, "Mm") == "M"
    assert _sex(data, "Uu") == "U"


def test_slk_partner_keeps_roles_and_sex_for_male_in_wife_slot(tmp_path):
    text = (
        HEAD + _indi("@I1@", "Mm", "M") + _indi("@I2@", "Ff", "F")
        + "0 @F1@ FAM\n1 HUSB @I2@\n1 WIFE @I1@\n"
        "1 _SLK_PARTNER @I1@\n2 _SLK_ROLE father\n"
        "1 _SLK_PARTNER @I2@\n2 _SLK_ROLE mother\n0 TRLR\n"
    )
    data, _ = _import(text, tmp_path)
    assert [(_name(data, p.person_id), p.role) for p in data.families[0].partners] == [
        ("Mm X", "father"), ("Ff X", "mother"),
    ]
    assert _sex(data, "Mm") == "M" and _sex(data, "Ff") == "F"


def test_same_sex_and_unknown_sex_couples_stay_intact(tmp_path):
    text = (
        HEAD + _indi("@I1@", "A1", "M") + _indi("@I2@", "A2", "M")
        + _indi("@I3@", "B1", None) + _indi("@I4@", "B2", "F")
        + "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n"
        "1 _SLK_PARTNER @I1@\n2 _SLK_ROLE partner\n"
        "1 _SLK_PARTNER @I2@\n2 _SLK_ROLE partner\n"
        "0 @F2@ FAM\n1 HUSB @I3@\n1 WIFE @I4@\n"
        "1 _SLK_PARTNER @I4@\n2 _SLK_ROLE make/maka\n"
        "1 _SLK_PARTNER @I3@\n2 _SLK_ROLE make/maka\n0 TRLR\n"
    )
    data, _ = _import(text, tmp_path)
    first, second = data.families
    assert [p.role for p in first.partners] == ["partner", "partner"]
    assert [_name(data, p.person_id) for p in second.partners] == ["B2 X", "B1 X"]
    assert _sex(data, "A1") == "M" and _sex(data, "A2") == "M"
    assert _sex(data, "B1") == "U"


def test_slk_partner_mismatch_warns_and_uses_slots(tmp_path):
    text = _TWO + "1 _SLK_PARTNER @I1@\n2 _SLK_ROLE make/maka\n0 TRLR\n"
    data, result = _import(text, tmp_path)
    assert [p.role for p in data.families[0].partners] == ["husband", "wife"]
    assert any("_SLK_PARTNER" in w for w in result.warnings)


def test_invalid_partner_role_falls_back_to_slot_role_with_warning(tmp_path):
    text = _TWO + (
        "1 _SLK_PARTNER @I1@\n2 _SLK_ROLE bogus\n"
        "1 _SLK_PARTNER @I2@\n2 _SLK_ROLE make/maka\n0 TRLR\n"
    )
    data, result = _import(text, tmp_path)
    assert [p.role for p in data.families[0].partners] == ["wife", "make/maka"]
    assert any("bogus" in w for w in result.warnings)


def test_update_keeps_roles_of_equal_partner_set(tmp_path):
    data, _ = _import(_TWO + "0 TRLR\n", tmp_path)
    for partner in data.families[0].partners:
        partner.role = "make/maka"
    data, _ = _import(_TWO + "0 TRLR\n", tmp_path, data)
    assert len(data.families) == 1
    assert [p.role for p in data.families[0].partners] == ["make/maka", "make/maka"]


# ---------------------------------------------------------------------------
# _SLK_PLINK
# ---------------------------------------------------------------------------

_CHILD_FAM = (
    HEAD + _indi("@I1@", "Fa", "M") + _indi("@I2@", "Mo", "F")
    + "0 @I3@ INDI\n1 NAME Ch /X/\n1 FAMC @F1@\n{pedi}"
    "{plinks}"
    "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n0 TRLR\n"
)


def test_slk_plink_sets_type_per_parent_and_pedi_covers_the_rest(tmp_path):
    text = _CHILD_FAM.format(pedi="", plinks="2 _SLK_PLINK @I1@\n3 TYPE step\n")
    data, result = _import(text, tmp_path)
    types = {_name(data, link.parent_id): link.parentage_type
             for link in data.families[0].parent_child_links}
    assert types == {"Fa X": "step", "Mo X": "biological"}
    assert not result.warnings or not any("_SLK_PLINK" in w for w in result.warnings)


def test_without_slk_plink_pedi_applies_to_both_parents(tmp_path):
    data, _ = _import(_CHILD_FAM.format(pedi="2 PEDI foster\n", plinks=""), tmp_path)
    assert [l.parentage_type for l in data.families[0].parent_child_links] == ["foster", "foster"]


def test_slk_plink_unknown_parent_and_bad_type_warn_without_aborting(tmp_path):
    text = _CHILD_FAM.format(
        pedi="",
        plinks="2 _SLK_PLINK @I9@\n3 TYPE step\n2 _SLK_PLINK @I2@\n3 TYPE nonsense\n"
    )
    data, result = _import(text, tmp_path)
    types = {_name(data, link.parent_id): link.parentage_type
             for link in data.families[0].parent_child_links if link.parent_id}
    assert types == {"Fa X": "biological", "Mo X": "biological"}
    assert any("_SLK_PLINK" in w for w in result.warnings)


def test_slk_plink_without_parent_is_kept_for_unknown_donor(tmp_path):
    text = _CHILD_FAM.format(pedi="", plinks="2 _SLK_PLINK\n3 TYPE unknown_donor\n")
    data, _ = _import(text, tmp_path)
    links = data.families[0].parent_child_links
    assert [(l.parent_id is None, l.parentage_type) for l in links] == [
        (False, "biological"), (False, "biological"), (True, "unknown_donor"),
    ]


# ---------------------------------------------------------------------------
# _SLK_PART
# ---------------------------------------------------------------------------


def _fam_with_marriage(part_lines: str) -> str:
    return (
        HEAD + _indi("@I1@", "Aa", "F") + _indi("@I2@", "Bb", "M")
        + "0 @F1@ FAM\n1 HUSB @I2@\n1 WIFE @I1@\n1 MARR\n2 DATE 1 JAN 1900\n"
        + part_lines + "0 TRLR\n"
    )


def test_slk_part_gives_participants_and_roles(tmp_path):
    text = _fam_with_marriage(
        "2 _SLK_PART @I1@\n3 _SLK_ROLE make/maka\n2 _SLK_PART @I2@\n3 _SLK_ROLE make/maka\n"
    )
    data, _ = _import(text, tmp_path)
    marriage = next(e for e in data.events if e.type == "marriage")
    assert [(_name(data, p.person_id), p.role) for p in marriage.participants] == [
        ("Aa X", "make/maka"), ("Bb X", "make/maka"),
    ]


def test_family_event_without_slk_part_uses_spouse(tmp_path):
    data, _ = _import(_fam_with_marriage(""), tmp_path)
    marriage = next(e for e in data.events if e.type == "marriage")
    assert {p.role for p in marriage.participants} == {"spouse"}
    assert len(marriage.participants) == 2


def test_slk_part_unknown_pointer_is_skipped_with_warning(tmp_path):
    text = _fam_with_marriage("2 _SLK_PART @I9@\n2 _SLK_PART @I1@\n3 _SLK_ROLE witness\n")
    data, result = _import(text, tmp_path)
    marriage = next(e for e in data.events if e.type == "marriage")
    assert [(_name(data, p.person_id), p.role) for p in marriage.participants] == [
        ("Aa X", "witness"),
    ]
    assert any("_SLK_PART" in w for w in result.warnings)


def test_slk_part_with_only_bad_entries_falls_back_to_spouses(tmp_path):
    data, result = _import(_fam_with_marriage("2 _SLK_PART @I9@\n"), tmp_path)
    marriage = next(e for e in data.events if e.type == "marriage")
    assert {p.role for p in marriage.participants} == {"spouse"}
    assert any("_SLK_PART" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# make/maka is a valid partner role
# ---------------------------------------------------------------------------


def test_make_maka_is_a_valid_partner_role_with_swedish_label():
    from slaktbusken.model.family import Family, FamilyPartner
    from slaktbusken.model.validators import validate_family
    from slaktbusken.ui.swedish_locale import PARTNER_ROLE_LABELS, RELATIONSHIP_LABELS

    family = Family(
        id="f1",
        partners=[FamilyPartner(person_id="p1", role="make/maka")],
        children=[],
    )
    assert validate_family(family) == []
    assert PARTNER_ROLE_LABELS["make/maka"] == "Make/maka"
    assert RELATIONSHIP_LABELS["make/maka"] == "Make/maka"
