"""Property 15: Comparison row classification.

**Validates: Requirements 11.2, 11.3, 11.4, 11.5, 11.9**
"""

from __future__ import annotations

from hypothesis import given, strategies as st

from slaktbusken.model.event import DateValue, Event, Participant
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services.comparison_session import (
    STATUS_DIFFERS,
    STATUS_EQUAL,
    STATUS_MISSING_LEFT,
    STATUS_MISSING_RIGHT,
    STATUS_NONE,
    build_rows,
)

_text = st.text(
    alphabet=st.sampled_from(list("abcdeABCDEåäöÅÄÖ12 ")), min_size=0, max_size=8
)
_filled = _text.filter(lambda s: s.strip() != "")
_blank = st.sampled_from(["", " ", "   ", "\t", " \n "])
_pad = st.sampled_from(["", " ", "  ", "\t"])
_precision = st.sampled_from(["exact", "year", "about", "before", "after"])
_date_value = st.sampled_from(["1900", "1900-05-01", "1850", "1901-02"])


def _row(rows, key):
    return next(r for r in rows if r.key == key)


def _data(left: Person, right: Person, events=()) -> ProjectData:
    return ProjectData(persons=[left, right], events=list(events))


def _person(pid, **kw) -> Person:
    kw.setdefault("sex", "")
    kw.setdefault("names", [])
    return Person(id=pid, **kw)


def _birth(eid, pid, value, precision) -> Event:
    return Event(
        id=eid,
        type="birth",
        participants=[Participant(person_id=pid, role="child")],
        date=DateValue(value=value, precision=precision),
    )


@given(_filled, _pad, _pad, st.booleans())
def test_equal_after_trim_and_casefold(text, pad_l, pad_r, upper):
    other = text.upper() if upper else text.lower()
    rows = build_rows(
        _data(
            _person("a", occupation=pad_l + text + pad_l),
            _person("b", occupation=pad_r + other + pad_r),
        ),
        "a",
        "b",
    )
    row = _row(rows, "occupation")
    if text.strip().casefold() == other.strip().casefold():
        assert row.status == STATUS_EQUAL
        assert row.status_label == ""


@given(_filled, _filled)
def test_both_filled_and_different_is_avviker(a, b):
    rows = build_rows(
        _data(_person("a", occupation=a), _person("b", occupation=b)), "a", "b"
    )
    row = _row(rows, "occupation")
    if a.strip().casefold() == b.strip().casefold():
        assert row.status == STATUS_EQUAL
    else:
        assert row.status == STATUS_DIFFERS
        assert row.status_label == "Avviker"


@given(_filled, _blank, st.booleans())
def test_one_side_filled_is_saknas_on_empty_side(text, blank, filled_left):
    left, right = (text, blank) if filled_left else (blank, text)
    for value in (blank, None):
        left_v, right_v = (text, value) if filled_left else (value, text)
        rows = build_rows(
            _data(_person("a", occupation=left_v), _person("b", occupation=right_v)),
            "a",
            "b",
        )
        row = _row(rows, "occupation")
        expected = STATUS_MISSING_RIGHT if filled_left else STATUS_MISSING_LEFT
        assert row.status == expected
        assert row.status_label == "Saknas"
        assert row.status_label != "Avviker"
    # unused pair kept for readability of the whitespace-only case
    assert left.strip() == "" or right.strip() == ""


@given(_blank, _blank)
def test_both_blank_is_unmarked(a, b):
    rows = build_rows(
        _data(_person("a", occupation=a), _person("b", occupation=b)), "a", "b"
    )
    row = _row(rows, "occupation")
    assert row.status == STATUS_EQUAL
    assert row.status_label == ""


@given(_date_value, _precision, _date_value, _precision)
def test_dates_equal_only_with_same_precision_and_value(v1, p1, v2, p2):
    rows = build_rows(
        _data(
            _person("a"),
            _person("b"),
            [_birth("e1", "a", v1, p1), _birth("e2", "b", v2, p2)],
        ),
        "a",
        "b",
    )
    row = _row(rows, "birth")
    if v1 == v2 and p1 == p2:
        assert row.status == STATUS_EQUAL
    else:
        assert row.status == STATUS_DIFFERS


@given(
    st.lists(_filled, min_size=1, max_size=5, unique_by=lambda s: s.strip().casefold()),
    st.randoms(use_true_random=False),
    st.booleans(),
)
def test_multi_valued_rows_compare_as_sets(values, rnd, drop_one):
    shuffled = list(values)
    rnd.shuffle(shuffled)
    left_vals = list(values)
    right_vals = shuffled[:-1] if drop_one and len(shuffled) > 1 else shuffled

    def names(vals):
        return [Name(type="birth", given="Prim", surname="X")] + [
            Name(type="alias", given=v, surname="") for v in vals
        ]

    rows = build_rows(
        _data(_person("a", names=names(left_vals)), _person("b", names=names(right_vals))),
        "a",
        "b",
    )
    row = _row(rows, "alt_names")
    if drop_one and len(shuffled) > 1:
        assert row.status == STATUS_DIFFERS
    else:
        assert row.status == STATUS_EQUAL


@given(_filled, st.booleans(), st.booleans())
def test_empty_slot_yields_no_marks(text, left_has, right_slot_empty):
    persons = [_person("a", occupation=text, sex="F", names=[Name("birth", text, text)])]
    data = ProjectData(persons=persons)
    left_id, right_id = ("a", None) if not right_slot_empty else (None, "a")
    if left_has:
        left_id, right_id = left_id, right_id
    for rows in (
        build_rows(data, left_id, right_id),
        build_rows(data, None, None),
        build_rows(data, "a", "missing"),
    ):
        assert all(r.status == STATUS_NONE for r in rows)
        assert all(r.status_label == "" for r in rows)
