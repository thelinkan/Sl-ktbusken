"""Similar_Event_Rule (Req 21.14, 21.15): duplicate-event warnings in the merge plan."""

from __future__ import annotations

from datetime import date, timedelta

from hypothesis import given, strategies as st

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData
from slaktbusken.services import merge_rules as rules
from slaktbusken.services.merge_planner import MergeDecisions, build_plan

_TYPES = [("birth", None), ("death", None), ("marriage", None), ("custom", "A"), ("custom", "B")]
_MALFORMED = ["abc", "1850-02-30", "18x0"]


def _full_dates():
    return st.dates(date(1849, 1, 1), date(1851, 12, 31))


@st.composite
def _date_strings(draw):
    """None, a year, a month, a full date or a malformed value."""
    kind = draw(st.sampled_from(["none", "year", "month", "day", "day", "bad"]))
    if kind == "none":
        return None
    if kind == "bad":
        return draw(st.sampled_from(_MALFORMED))
    iso = draw(_full_dates()).isoformat()
    return iso[:{"year": 4, "month": 7, "day": 10}[kind]]


def _parse(value):
    """Independent oracle parser: (precision, first_day) or None when malformed."""
    try:
        if len(value) == 4:
            return "year", date(int(value), 1, 1)
        if len(value) == 7 and value[4] == "-":
            return "month", date(int(value[:4]), int(value[5:]), 1)
        if len(value) == 10 and value[4] == "-" and value[7] == "-":
            return "day", date.fromisoformat(value)
    except ValueError:
        return None
    return None


def _oracle_dates_compatible(v1, v2):
    p1, p2 = _parse(v1), _parse(v2)
    if p1 is None or p2 is None:
        return False
    length = min(len(v1), len(v2))
    if v1[:length] == v2[:length]:
        return True
    return p1[0] == "day" and p2[0] == "day" and abs(p1[1] - p2[1]) <= timedelta(days=365)


def _oracle_similar(a, b):
    if (a.type, a.custom_type_name) != (b.type, b.custom_type_name):
        return False
    if a.date is None or b.date is None:
        return False
    if not _oracle_dates_compatible(a.date.value, b.date.value):
        return False
    pa = a.place.place_id if a.place else None
    pb = b.place.place_id if b.place else None
    return pa is None or pb is None or pa == pb


def _make_event(eid, spec, owners):
    (etype, custom), value, place = spec
    precision = {4: "year", 7: "month"}.get(len(value), "day") if value else None
    return Event(
        id=eid,
        type=etype,
        custom_type_name=custom,
        participants=[Participant(p, "self") for p in owners],
        date=DateValue(value, precision) if value else None,
        place=PlaceRef(place) if place else None,
    )


_SPEC = st.tuples(
    st.sampled_from(_TYPES),
    _date_strings(),
    st.sampled_from([None, "pl1", "pl2"]),
)
_OWNERS = st.sampled_from([("p1",), ("p2",), ("p1", "p2"), ("p3",)])


def _person(pid):
    return Person(id=pid, sex="U", names=[Name("birth", "Anna", "Berg")])


def _build(entries):
    events = [_make_event(f"e{i}", spec, owners) for i, (spec, owners) in enumerate(entries)]
    data = ProjectData(persons=[_person("p1"), _person("p2"), _person("p3")], events=events)
    return data, events


@given(st.lists(st.tuples(_SPEC, _OWNERS), max_size=8))
def test_property_28_duplicate_event_warnings(entries):
    # Feature: person-comparison-and-merge, Property 28: Duplicate-event warnings (Similar_Event_Rule)
    # **Validates: Requirements 21.14, 21.15**
    data, events = _build(entries)
    before_ids = [e.id for e in events]

    expected = set()
    for a in events:
        for b in events:
            a_ids = {p.person_id for p in a.participants}
            b_ids = {p.person_id for p in b.participants}
            if "p1" in a_ids and "p2" not in a_ids and "p2" in b_ids and "p1" not in b_ids:
                if _oracle_similar(a, b):
                    expected.add((a.id, b.id))

    # the pure rule agrees with the oracle
    ev1 = [e for e in events if any(p.person_id == "p1" for p in e.participants)]
    ev2 = [e for e in events if any(p.person_id == "p2" for p in e.participants)]
    assert set(rules.find_similar_event_pairs(ev1, ev2)) == expected

    # the plan warns exactly for those pairs, never blocking
    plan = build_plan(data, None, MergeDecisions("p1", "p2", survivor_id="p1", survivor_confirmed=True))
    similar = [c for c in plan.conflicts if c.code == "similar_event"]
    assert {tuple(c.subjects) for c in similar} == expected
    assert len(similar) == len(expected)
    assert all(not c.is_blocking for c in similar)
    for id_1, id_2 in expected:
        assert id_1 != id_2

    # both events of every warned pair are kept with unchanged ids, nothing merged or deleted
    kept = set(before_ids) - plan.change_set.removed.get("events", set())
    assert kept == set(before_ids)
    assert not plan.change_set.removed.get("events")
    assert not plan.change_set.added.get("events")
    replaced_ids = set(plan.change_set.replaced.get("events", {}))
    assert replaced_ids <= set(before_ids)
    assert plan.ledger_before["events"] == plan.ledger_after_expected["events"]


# ---------------------------------------------------------------------------
# Examples and edge cases (task 11.21, Req 21.14, 21.15)
# ---------------------------------------------------------------------------

import pytest


def _ev(eid, etype="birth", value=None, place=None, owners=("p1",), custom=None, precision=None):
    if value is not None and precision is None:
        precision = {4: "year", 7: "month"}.get(len(value), "day")
    return Event(
        id=eid,
        type=etype,
        custom_type_name=custom,
        participants=[Participant(p, "self") for p in owners],
        date=DateValue(value, precision) if value is not None else None,
        place=PlaceRef(place) if place else None,
    )


def _plan_pairs(events):
    """Run the planner; assert non-blocking and preservation; return warned pairs."""
    data = ProjectData(persons=[_person("p1"), _person("p2")], events=list(events))
    plan = build_plan(data, None, MergeDecisions("p1", "p2", survivor_id="p1", survivor_confirmed=True))
    similar = [c for c in plan.conflicts if c.code == "similar_event"]
    assert all(not c.is_blocking for c in similar)
    ids = [e.id for e in events]
    assert not plan.change_set.removed.get("events")
    assert not plan.change_set.added.get("events")
    assert set(plan.change_set.replaced.get("events", {})) <= set(ids)
    assert plan.ledger_before["events"] == plan.ledger_after_expected["events"]
    return {tuple(c.subjects) for c in similar}


def _check(e1, e2, expected):
    """Pure rule and planner path must agree on whether (e1, e2) is a warning."""
    assert rules.is_similar_event_pair(e1, e2) is expected
    ev1 = [e1] if "p1" in {p.person_id for p in e1.participants} else []
    ev2 = [e2]
    assert (rules.find_similar_event_pairs(ev1, ev2) == [(e1.id, e2.id)]) is expected
    pairs = _plan_pairs([e1, e2])
    assert (pairs == {(e1.id, e2.id)}) is expected
    if not expected:
        assert pairs == set()


def _pair(t1, d1, pl1, t2=None, d2=None, pl2=None, **kw):
    e1 = _ev("a", t1, d1, pl1, ("p1",), **kw.get("k1", {}))
    e2 = _ev("b", t2 or t1, d2, pl2, ("p2",), **kw.get("k2", {}))
    return e1, e2


_EXAMPLES = [
    # two Births, same parish, no dates
    (("birth", None, "pl1"), ("birth", None, "pl1"), False),
    # two Births, same parish, different years
    (("birth", "1850-03-12", "pl1"), ("birth", "1855-03-12", "pl1"), False),
    # equal full dates, same place / no place
    (("birth", "1850-03-12", "pl1"), ("birth", "1850-03-12", "pl1"), True),
    (("birth", "1850-03-12", None), ("birth", "1850-03-12", None), True),
    # equal full dates, different places
    (("birth", "1850-03-12", "pl1"), ("birth", "1850-03-12", "pl2"), False),
    # Marriages 10 years apart, same place
    (("marriage", "1850-03-12", "pl1"), ("marriage", "1860-03-12", "pl1"), False),
    # Marriages 100 days apart, no place
    (("marriage", "1850-01-01", None), ("marriage", "1850-04-11", None), True),
]


@pytest.mark.parametrize("left,right,expected", _EXAMPLES)
def test_requirement_21_14_examples(left, right, expected):
    _check(*_pair(left[0], left[1], left[2], right[0], right[1], right[2]), expected)


_PRECISION_CASES = [
    ("1850", "1850-03-12", True),          # year against full date
    ("1850-03-12", "1850", True),
    ("1850-03", "1850-03-12", True),       # month against full date
    ("1850-03", "1850-04-12", False),
    ("1850", "1851-03-12", False),         # year does not match other year
    ("1850-03-12", "1851-03-12", True),    # 365 days
    ("1850-03-12", "1851-03-13", False),   # 366 days
    ("1850", "1851", False),               # year-only a year apart
    ("1850-03", "1851-03", False),         # month-only a year apart
    ("1850-03", "1850-03", True),
]


@pytest.mark.parametrize("v1,v2,expected", _PRECISION_CASES)
def test_precision_cases(v1, v2, expected):
    _check(*_pair("birth", v1, None, d2=v2), expected)


def test_day_distance_boundaries_are_365_and_366():
    assert date(1851, 3, 12) - date(1850, 3, 12) == timedelta(days=365)
    assert date(1851, 3, 13) - date(1850, 3, 12) == timedelta(days=366)


def test_approximate_precision_compares_by_iso_value():
    e1 = _ev("a", "birth", "1850-03-12", None, ("p1",), precision="approximate")
    e2 = _ev("b", "birth", "1850-03-12", None, ("p2",), precision="approximate")
    _check(e1, e2, True)
    e3 = _ev("c", "birth", "1850-03-20", None, ("p2",), precision="approximate")
    _check(e1, e3, True)
    e4 = _ev("d", "birth", "1852-03-20", None, ("p2",), precision="approximate")
    _check(e1, e4, False)


@pytest.mark.parametrize("bad", _MALFORMED + ["", "ca 1850", "1850-13", "1850-03-12T00"])
def test_malformed_date_never_warns(bad):
    _check(*_pair("birth", bad, None, d2="1850-03-12"), False)
    _check(*_pair("birth", "1850-03-12", None, d2=bad), False)
    _check(*_pair("birth", bad, None, d2=bad), False)


def test_type_only_never_warns():
    _check(*_pair("birth", None, None), False)


def test_place_only_never_warns():
    _check(*_pair("birth", None, "pl1"), False)


def test_type_and_place_without_compatible_dates_never_warns():
    _check(*_pair("birth", "1850-03-12", "pl1", d2="1900-03-12", pl2="pl1"), False)
    _check(*_pair("birth", None, "pl1", d2="1900-03-12", pl2="pl1"), False)


@pytest.mark.parametrize("d1,d2", [(None, "1850-03-12"), ("1850-03-12", None), (None, None)])
def test_undated_event_never_warns(d1, d2):
    _check(*_pair("birth", d1, "pl1", d2=d2, pl2="pl1"), False)


def test_different_types_never_warn():
    _check(*_pair("birth", "1850-03-12", None, t2="death", d2="1850-03-12"), False)


def test_custom_types_with_different_names_never_warn():
    k1, k2 = {"custom": "Dop"}, {"custom": "Konfirmation"}
    _check(*_pair("custom", "1850-03-12", None, d2="1850-03-12", k1=k1, k2=k2), False)


def test_custom_types_with_same_name_warn():
    k = {"custom": "Dop"}
    _check(*_pair("custom", "1850-03-12", None, d2="1850-03-12", k1=k, k2=dict(k)), True)


def test_similar_events_of_one_person_are_never_compared():
    e1 = _ev("a", "birth", "1850-03-12", None, ("p1",))
    e2 = _ev("b", "birth", "1850-03-12", None, ("p1",))
    assert rules.find_similar_event_pairs([e1, e2], []) == []
    assert rules.find_similar_event_pairs([e1, e2], [e1, e2]) == []
    assert _plan_pairs([e1, e2]) == set()
    e3 = _ev("c", "birth", "1850-03-12", None, ("p2",))
    e4 = _ev("d", "birth", "1850-03-12", None, ("p2",))
    assert _plan_pairs([e3, e4]) == set()


def test_event_shared_by_both_persons_is_skipped():
    shared = _ev("s", "marriage", "1850-03-12", None, ("p1", "p2"))
    other = _ev("o", "marriage", "1850-03-12", None, ("p2",))
    assert rules.find_similar_event_pairs([shared], [shared, other]) == []
    assert _plan_pairs([shared]) == set()
    assert _plan_pairs([shared, other]) == set()


def test_planner_reports_each_pair_once_and_keeps_both_events():
    e1 = _ev("a", "birth", "1850-03-12", None, ("p1",))
    e2 = _ev("b", "birth", "1850-03-12", "pl1", ("p2",))
    e3 = _ev("c", "marriage", "1850-03-12", None, ("p2",))
    assert _plan_pairs([e1, e2, e3]) == {("a", "b")}
