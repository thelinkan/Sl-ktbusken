"""Name rows of the comparison table: one row per name type."""

from __future__ import annotations

from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.comparison_session import (
    STATUS_EQUAL,
    STATUS_DIFFERS,
    STATUS_MISSING_RIGHT,
    STATUS_NONE,
    build_rows,
)


def _rows(left_names, right_names, right_id="b"):
    persons = [Person(id="a", sex="", names=left_names)]
    if right_id:
        persons.append(Person(id="b", sex="", names=right_names))
    return build_rows(ProjectData(persons=persons), "a", right_id)


def _name_rows(rows):
    return [r for r in rows if r.key.startswith("name:")]


def test_reported_case_birth_missing_and_married_equal():
    rows = _rows(
        [Name("birth", "Siv", "Jansson"), Name("married", "Siv", "Svensson")],
        [Name("married", "Siv", "Svensson")],
    )
    by_key = {r.key: r for r in rows}
    birth = by_key["name:birth"]
    assert birth.label == "Födelsenamn"
    assert birth.left == ("Siv Jansson",) and birth.right == ()
    assert birth.status == STATUS_MISSING_RIGHT and birth.status_label == "Saknas"
    married = by_key["name:married"]
    assert married.label == "Gift namn"
    assert married.left == married.right == ("Siv Svensson",)
    assert married.status == STATUS_EQUAL and married.status_label == ""


def test_name_rows_come_first_in_fixed_order_with_labels():
    rows = _rows(
        [Name("other", "A", "B"), Name("adopted", "C", "D"), Name("birth", "E", "F")],
        [Name("married", "G", "H")],
    )
    assert [r.key for r in rows[:4]] == [
        "name:birth",
        "name:married",
        "name:adopted",
        "name:other",
    ]
    assert [r.label for r in rows[:4]] == [
        "Födelsenamn",
        "Gift namn",
        "Adoptivnamn",
        "Annat",
    ]
    assert rows[4].key == "sex"


def test_only_used_types_appear():
    rows = _rows([Name("birth", "A", "B")], [Name("birth", "A", "B")])
    assert [r.key for r in _name_rows(rows)] == ["name:birth"]
    # Empty text does not count as a used type.
    rows = _rows([Name("birth", "A", "B"), Name("adopted", " ", " ")], [])
    assert [r.key for r in _name_rows(rows)] == ["name:birth"]


def test_empty_slot_shows_only_that_persons_types_without_marks():
    rows = _rows([Name("birth", "A", "B"), Name("married", "A", "C")], [], right_id=None)
    name_rows = _name_rows(rows)
    assert [r.key for r in name_rows] == ["name:birth", "name:married"]
    assert all(r.status == STATUS_NONE for r in name_rows)


def test_several_names_of_one_type_shown_together_and_compared_as_set():
    left = [Name("other", "Anna", "X"), Name("other", "Bo", "Y"), Name("other", "anna", "x")]
    right = [Name("other", "Bo", "Y"), Name("other", "Anna", "X")]
    row = _name_rows(_rows(left, right))[0]
    assert row.key == "name:other"
    assert row.left == ("Anna X", "Bo Y", "anna x")
    assert row.right == ("Bo Y", "Anna X")
    assert row.status == STATUS_EQUAL
    differing = _name_rows(_rows(left, [Name("other", "Bo", "Y")]))[0]
    assert differing.status == STATUS_DIFFERS


def test_untyped_or_unknown_type_lands_in_annat():
    rows = _rows([Name("", "A", "B")], [Name("alias", "A", "B")])
    name_rows = _name_rows(rows)
    assert [r.key for r in name_rows] == ["name:other"]
    assert name_rows[0].label == "Annat"
    assert name_rows[0].status == STATUS_EQUAL


def test_equal_names_of_a_type_have_no_mark_and_differing_show_avviker():
    equal = _name_rows(_rows([Name("birth", "Siv", "Jansson")], [Name("birth", " SIV ", "jansson")]))[0]
    assert equal.status == STATUS_EQUAL and equal.status_label == ""
    differ = _name_rows(_rows([Name("birth", "Siv", "Jansson")], [Name("birth", "Siv", "Berg")]))[0]
    assert differ.status == STATUS_DIFFERS and differ.status_label == "Avviker"
