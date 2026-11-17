"""Importer side of persons: NAME.TYPE, _SLK_SEX, notes, title (task 3.2)."""

from __future__ import annotations

from pathlib import Path

from slaktbusken.model.person import Name
from slaktbusken.model.project import ProjectData
from tests.test_gedcom.test_importer_events_slk import HEAD, _import

END = "0 TRLR\n"


def _person(data: ProjectData, given: str):
    return next(p for p in data.persons if p.names[0].given == given)


def _types(person) -> list[tuple[str, str, str]]:
    return [(n.type, n.given, n.surname) for n in person.names]


def test_types_are_read_from_name_type(tmp_path: Path) -> None:
    text = (
        HEAD + "0 @I1@ INDI\n1 NAME Anna /Lind/\n2 TYPE birth\n"
        "1 NAME Anna /Berg/\n2 TYPE married\n"
        "1 NAME Annie /Lind/\n2 TYPE aka\n"
        "1 NAME Ann /Ost/\n2 TYPE adopted\n"
        "1 NAME Ana /Lund/\n2 TYPE maiden\n"
        "1 NAME Anja /Z/\n2 TYPE nickname\n" + END
    )
    data, _ = _import(text, tmp_path)
    assert [n.type for n in _person(data, "Anna").names] == [
        "birth", "married", "alias", "adopted", "birth", "other"
    ]


def test_positional_fallback_without_any_type(tmp_path: Path) -> None:
    text = HEAD + "0 @I1@ INDI\n1 NAME Anna /A/\n1 NAME Bo /B/\n" + END
    data, _ = _import(text, tmp_path)
    assert [n.type for n in _person(data, "Anna").names] == ["birth", "other"]


def test_untyped_name_is_other_when_another_has_type(tmp_path: Path) -> None:
    text = (
        HEAD + "0 @I1@ INDI\n1 NAME Anna /A/\n1 NAME Bo /B/\n2 TYPE married\n"
        + END
    )
    data, _ = _import(text, tmp_path)
    assert [n.type for n in _person(data, "Anna").names] == ["other", "married"]


def test_update_keeps_existing_types_without_type(tmp_path: Path) -> None:
    first = (
        HEAD + "0 @I1@ INDI\n1 NAME Anna /A/\n2 TYPE married\n"
        "1 NAME Bo /B/\n2 TYPE aka\n" + END
    )
    data, _ = _import(first, tmp_path)
    second = HEAD + "0 @I1@ INDI\n1 NAME Anna /A/\n1 NAME Bo /B/\n1 NAME Cy /C/\n" + END
    data, _ = _import(second, tmp_path, data)
    person = _person(data, "Anna")
    assert [(n.type, n.given) for n in person.names] == [
        ("married", "Anna"), ("alias", "Bo"), ("other", "Cy")
    ]


def test_sex_x_from_slk_sex(tmp_path: Path) -> None:
    text = (
        HEAD + "0 @I1@ INDI\n1 NAME Ex /A/\n1 SEX U\n2 _SLK_SEX X\n"
        "0 @I2@ INDI\n1 NAME Un /B/\n1 SEX U\n"
        "0 @I3@ INDI\n1 NAME Em /C/\n1 SEX M\n" + END
    )
    data, _ = _import(text, tmp_path)
    assert _person(data, "Ex").sex == "X"
    assert _person(data, "Un").sex == "U"
    assert _person(data, "Em").sex == "M"


def test_notes_title_occupation_restored(tmp_path: Path) -> None:
    text = (
        HEAD + "0 @I1@ INDI\n1 NAME Anna /A/\n"
        "1 TITL Fil.Dr\n1 OCCU Lektor\n"
        "1 NOTE rad ett\n2 CONT rad två\n2 CONC  forts\n2 CONT @@alfa\n"
        "0 @S1@ SOUR\n1 TITL Källa\n" + END
    )
    data, _ = _import(text, tmp_path)
    person = _person(data, "Anna")
    assert person.title == "Fil.Dr"
    assert person.occupation == "Lektor"
    assert person.notes == "rad ett\nrad två forts\n@alfa"
    assert [s.title for s in data.sources] == ["Källa"]


def test_name_type_leaves_event_link_tag_alone(tmp_path: Path) -> None:
    text = (
        HEAD + "0 @I1@ INDI\n1 NAME Anna /A/\n2 TYPE married\n3 _SLK_EREF @E9@\n"
        + END
    )
    data, result = _import(text, tmp_path)
    assert _person(data, "Anna").names == [
        Name(type="married", given="Anna", surname="A", event_id=None)
    ]
