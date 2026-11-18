"""Family lines in the detail view: partner sets are merged, children grouped by parentage."""

from __future__ import annotations

from slaktbusken.model.family import Family, FamilyPartner, ParentChildLink
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.ui.person_detail_panel import family_summary_lines


def _person(person_id: str, given: str, surname: str) -> Person:
    return Person(id=person_id, sex="U", names=[Name(type="birth", given=given, surname=surname)])


def _family(family_id: str, partner_ids: list[str], children: dict[str, str]) -> Family:
    """*children* maps child id to the parentage type of both partners' links."""
    return Family(
        id=family_id,
        partners=[FamilyPartner(pid, "partner") for pid in partner_ids],
        children=list(children),
        parent_child_links=[
            ParentChildLink(child_id=child, parent_id=parent, parentage_type=kind)
            for child, kind in children.items()
            for parent in partner_ids
        ],
    )


def _project() -> ProjectData:
    data = ProjectData()
    data.persons = [
        _person("arla", "Ärla", "Larsson"),
        _person("janne", "Janne", "Karlsson"),
        _person("rut", "Rut", "Karlsson"),
        _person("bertil", "Bertil", "Svensson"),
        _person("olle", "Olle", "Ek"),
        _person("stina", "Stina", "Ek"),
    ]
    return data


def test_biological_and_foster_families_of_one_couple_become_one_line() -> None:
    data = _project()
    families = [
        _family("family_5", ["janne", "arla"], {"rut": "biological"}),
        _family("family_10", ["arla", "janne"], {"bertil": "foster"}),
    ]
    assert family_summary_lines(data, "arla", families) == [
        "Partner: Janne Karlsson · Barn: Rut Karlsson · Fosterbarn: Bertil Svensson"
    ]


def test_different_partners_stay_separate() -> None:
    data = _project()
    families = [
        _family("family_1", ["arla", "janne"], {"rut": "biological"}),
        _family("family_2", ["arla", "olle"], {"stina": "adoptive"}),
    ]
    assert family_summary_lines(data, "arla", families) == [
        "Partner: Janne Karlsson · Barn: Rut Karlsson",
        "Partner: Olle Ek · Adoptivbarn: Stina Ek",
    ]


def test_child_without_explicit_link_counts_as_biological() -> None:
    data = _project()
    family = Family(id="family_1", partners=[FamilyPartner("arla", "partner")], children=["rut"])
    assert family_summary_lines(data, "arla", [family]) == ["Barn: Rut Karlsson"]


def test_child_listed_once_even_if_in_two_records() -> None:
    data = _project()
    families = [
        _family("family_1", ["arla", "janne"], {"rut": "biological"}),
        _family("family_2", ["arla", "janne"], {"rut": "biological"}),
    ]
    assert family_summary_lines(data, "arla", families) == [
        "Partner: Janne Karlsson · Barn: Rut Karlsson"
    ]


def test_grouping_follows_the_shown_persons_own_link() -> None:
    # Bertil is Janne's biological son and Ärla's foster son.
    data = _project()
    family = Family(
        id="family_1",
        partners=[FamilyPartner("arla", "partner"), FamilyPartner("janne", "partner")],
        children=["bertil"],
        parent_child_links=[
            ParentChildLink(child_id="bertil", parent_id="janne", parentage_type="biological"),
            ParentChildLink(child_id="bertil", parent_id="arla", parentage_type="foster"),
        ],
    )
    assert family_summary_lines(data, "arla", [family]) == [
        "Partner: Janne Karlsson · Fosterbarn: Bertil Svensson"
    ]
    assert family_summary_lines(data, "janne", [family]) == [
        "Partner: Ärla Larsson · Barn: Bertil Svensson"
    ]


def test_family_without_partner_or_children() -> None:
    data = _project()
    family = Family(id="family_1", partners=[FamilyPartner("arla", "partner")], children=[])
    assert family_summary_lines(data, "arla", [family]) == ["(inga detaljer)"]
