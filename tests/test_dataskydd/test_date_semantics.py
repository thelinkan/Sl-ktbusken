"""Date semantics tests (data-integrity-0-3-0, task 5.5).

Properties 10, 11 and 22 plus the named examples for
``model/date_semantics.py`` and its consumers.
"""

from __future__ import annotations

import calendar as _stdlib_calendar
from datetime import date
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.gedcom.dates import export_gedcom_date, parse_gedcom_date
from slaktbusken.model import date_semantics as ds
from slaktbusken.model.date_semantics import (
    date_bounds,
    display_year,
    effective_qualifier,
    exact_value,
    format_date_sv,
    in_swedish_window,
    is_exact,
    is_real_date,
    julian_to_gregorian,
    sort_key,
    validate_date_value,
)
from slaktbusken.model.event import DateValue, Event, Participant
from tests.test_dataskydd.strategies_dates import (
    MONTH_NAMES,
    NON_EXACT_QUALIFIERS,
    calendars,
    valid_date_values,
)

pytestmark = pytest.mark.mandatory_integrity


def _dv(value, qualifier="exact", precision=None, value_to=None, calendar="gregorian",
        original_text=None) -> DateValue:
    if precision is None:
        if qualifier == "exact":
            precision = {4: "year", 7: "month"}.get(len(value), "day")
        else:
            precision = "approximate"
    return DateValue(value=value, precision=precision, qualifier=qualifier,
                     value_to=value_to, calendar=calendar, original_text=original_text)


def _gregorian_leap(y: int) -> bool:
    return _stdlib_calendar.isleap(y)


def _julian_leap(y: int) -> bool:
    return y % 4 == 0


def _jdn_to_julian(jdn: int) -> tuple[int, int, int]:
    c = jdn + 32082
    d = (4 * c + 3) // 1461
    e = c - 1461 * d // 4
    m = (5 * e + 2) // 153
    return d - 4800 + m // 10, m + 3 - 12 * (m // 10), e - (153 * m + 2) // 5 + 1


# ---------------------------------------------------------------------------
# Property 10
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    year=st.integers(1, 9999),
    month=st.integers(1, 12),
    day=st.integers(1, 31),
    cal=calendars,
)
def test_dp_property_10_day_accepted_exactly_when_real_in_calendar(year, month, day, cal):
    """Property 10: is_real_date, the GEDCOM parser and validation agree."""
    leap = _julian_leap(year) if cal == "julian" else _gregorian_leap(year)
    lengths = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    expected = day <= lengths[month - 1]
    iso = f"{year:04d}-{month:02d}-{day:02d}"

    assert is_real_date(iso, cal) is expected

    dv = _dv(iso, calendar=cal)
    assert (validate_date_value(dv) == []) is expected

    escape = "@#DJULIAN@ " if cal == "julian" else ""
    parsed = parse_gedcom_date(f"{escape}{day} {MONTH_NAMES[month - 1]} {year:04d}")
    assert parsed is not None
    assert (parsed.value.qualifier != "unparsed") is expected
    if expected:
        assert parsed.value.value == iso and parsed.value.calendar == cal


# Feature: data-integrity-0-3-0, Property 10 (month and year granularity)
@settings(max_examples=100, deadline=None)
@given(year=st.integers(1, 9999), month=st.integers(1, 12), cal=calendars)
def test_dp_property_10_month_and_year_values_always_real(year, month, cal):
    assert is_real_date(f"{year:04d}", cal)
    assert is_real_date(f"{year:04d}-{month:02d}", cal)


# ---------------------------------------------------------------------------
# Property 11
# ---------------------------------------------------------------------------


def _written_span(dv: DateValue) -> tuple[date, date]:
    """As-written span (numbers read as Gregorian, a Julian-only day clamped)."""
    def span(iso: str):
        parts = [int(p) for p in iso.split("-")]
        y = parts[0]
        if len(parts) == 1:
            return date(y, 1, 1), date(y, 12, 31)
        m = parts[1]
        last_day = _stdlib_calendar.monthrange(y, m)[1]
        if len(parts) == 2:
            return date(y, m, 1), date(y, m, last_day)
        d = min(parts[2], last_day)
        return date(y, m, d), date(y, m, d)

    first = span(dv.value)
    last = span(dv.value_to) if dv.value_to else first
    return first[0], last[1]


def _converted_span(dv: DateValue) -> tuple[date, date]:
    def span(iso: str):
        parts = [int(p) for p in iso.split("-")]
        y = parts[0]
        if len(parts) == 1:
            return (y, 1, 1), (y, 12, 31)
        m = parts[1]
        n = 29 if (m == 2 and _julian_leap(y)) else [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
        if len(parts) == 2:
            return (y, m, 1), (y, m, n)
        return (y, m, parts[2]), (y, m, parts[2])

    first = span(dv.value)
    last = span(dv.value_to) if dv.value_to else first
    return julian_to_gregorian(*first[0]), julian_to_gregorian(*last[1])


@settings(max_examples=300, deadline=None)
@given(dv=valid_date_values(years=st.integers(1000, 2100)))
def test_dp_property_11_bounds_consistent_conservative_and_unknown_in_window(dv):
    """Property 11."""
    before = (dv.value, dv.value_to, dv.calendar, dv.qualifier, dv.precision)
    b = date_bounds(dv)
    assert (dv.value, dv.value_to, dv.calendar, dv.qualifier, dv.precision) == before

    endpoints = [e for e in (dv.value, dv.value_to) if e]
    if dv.calendar == "julian" and any(in_swedish_window(e) for e in endpoints):
        assert b.known is False
        assert b.earliest is None and b.latest is None
        return

    assert b.known is True
    if b.earliest is not None and b.latest is not None:
        assert b.earliest <= b.latest

    if dv.calendar == "julian":
        w_first, w_last = _written_span(dv)
        c_first, c_last = _converted_span(dv)
        lo, hi = min(w_first, c_first), max(w_last, c_last)
        q = dv.qualifier
        if q in ("before",):
            assert b.earliest is None and b.latest is not None and b.latest < lo
        elif q == "after":
            assert b.latest is None and b.earliest is not None and b.earliest > hi
        elif q == "from":
            assert b.latest is None and b.earliest <= lo
        elif q == "to":
            assert b.earliest is None and b.latest >= hi
        else:
            assert b.earliest <= lo and b.latest >= hi


@settings(max_examples=300, deadline=None)
@given(
    y=st.integers(1000, 2100),
    m=st.integers(1, 12),
    d=st.integers(1, 28),
)
def test_dp_property_11_julian_to_gregorian_round_trip(y, m, d):
    g = julian_to_gregorian(y, m, d)
    jdn = g.toordinal() + 1721425
    assert _jdn_to_julian(jdn) == (y, m, d)


# ---------------------------------------------------------------------------
# Property 22
# ---------------------------------------------------------------------------

_ANY_QUALIFIER = st.sampled_from(
    ["exact", "about", "estimated", "calculated", "before", "after", "between",
     "from_to", "from", "to", "interpreted", "unparsed"]
)


@settings(max_examples=300, deadline=None)
@given(
    qualifier=_ANY_QUALIFIER,
    precision=st.sampled_from(["day", "month", "year", "approximate"]),
    value=st.sampled_from(["1850", "1850-05", "1850-05-03", ""]),
)
def test_dp_property_22_qualifier_semantics_never_exact_when_qualified(
    qualifier, precision, value
):
    dv = DateValue(value=value, precision=precision, qualifier=qualifier,
                   value_to="1860" if qualifier in ("between", "from_to") else None,
                   original_text="x" if qualifier in ("unparsed", "interpreted") else None)
    legacy = qualifier == "exact" and precision == "approximate"
    expected = "about" if legacy else qualifier
    assert effective_qualifier(dv) == expected
    assert is_exact(dv) is (expected == "exact")
    if expected != "exact":
        assert exact_value(dv) is None
    if expected not in ("exact", "about"):
        assert display_year(dv) is None


@settings(max_examples=200, deadline=None)
@given(dv=valid_date_values(qualifiers=("before", "after", "between", "from_to", "from", "to")))
def test_dp_property_22_non_about_qualifiers_never_exported_as_abt(dv):
    text, _ = export_gedcom_date(dv)
    assert not text.upper().startswith("ABT")
    assert not text.upper().startswith("@#DJULIAN@ ABT")
    expected_start = {"before": "BEF", "after": "AFT", "between": "BET",
                      "from_to": "FROM", "from": "FROM", "to": "TO"}[dv.qualifier]
    assert text.startswith(expected_start)


# ---------------------------------------------------------------------------
# Examples
# ---------------------------------------------------------------------------


def test_leap_year_rules_gregorian():
    assert is_real_date("2024-02-29", "gregorian")
    assert is_real_date("2000-02-29", "gregorian")
    assert not is_real_date("1900-02-29", "gregorian")
    assert not is_real_date("1700-02-29", "gregorian")
    assert not is_real_date("2023-02-29", "gregorian")


def test_leap_year_rules_julian():
    assert is_real_date("1900-02-29", "julian")
    assert is_real_date("1700-02-29", "julian")
    assert is_real_date("1600-02-29", "julian")
    assert not is_real_date("1701-02-29", "julian")
    assert not is_real_date("1700-02-30", "julian")


def test_julian_to_gregorian_conversion_round_trip():
    assert julian_to_gregorian(1582, 10, 5) == date(1582, 10, 15)
    assert julian_to_gregorian(1752, 9, 2) == date(1752, 9, 13)
    assert julian_to_gregorian(1900, 1, 1) == date(1900, 1, 13)
    for y, m, d in [(1582, 10, 5), (1650, 3, 15), (1752, 9, 2), (1900, 1, 1), (1066, 10, 14)]:
        g = julian_to_gregorian(y, m, d)
        assert _jdn_to_julian(g.toordinal() + 1721425) == (y, m, d)


def test_legacy_exact_approximate_is_about():
    dv = DateValue(value="1850", precision="approximate")  # qualifier defaults to exact
    assert effective_qualifier(dv) == "about"
    assert not is_exact(dv)
    assert exact_value(dv) is None
    assert display_year(dv) == "1850"
    assert format_date_sv(dv) == "ca 1850"


def test_explicit_before_never_about():
    dv = _dv("1850", "before")
    assert effective_qualifier(dv) == "before"
    # Even with a legacy-looking precision the qualifier stays before.
    assert effective_qualifier(DateValue(value="1850", precision="year", qualifier="before")) == "before"
    assert display_year(dv) is None
    assert format_date_sv(dv) == "före 1850"
    text, _ = export_gedcom_date(dv)
    assert text == "BEF 1850"


def test_date_bounds_per_qualifier():
    d = date
    b = date_bounds(_dv("1850-05-03"))
    assert (b.earliest, b.latest, b.known) == (d(1850, 5, 3), d(1850, 5, 3), True)
    b = date_bounds(_dv("1850-05"))
    assert (b.earliest, b.latest) == (d(1850, 5, 1), d(1850, 5, 31))
    b = date_bounds(_dv("1850"))
    assert (b.earliest, b.latest) == (d(1850, 1, 1), d(1850, 12, 31))
    for q in ("about", "estimated", "calculated", "interpreted"):
        b = date_bounds(_dv("1850", q, original_text="INT 1850 (x)" if q == "interpreted" else None))
        assert (b.earliest, b.latest, b.known) == (d(1850, 1, 1), d(1850, 12, 31), True)
    b = date_bounds(_dv("1850", "before"))
    assert (b.earliest, b.latest, b.known) == (None, d(1849, 12, 31), True)
    b = date_bounds(_dv("1850", "after"))
    assert (b.earliest, b.latest, b.known) == (d(1851, 1, 1), None, True)
    b = date_bounds(_dv("1850", "between", value_to="1860"))
    assert (b.earliest, b.latest) == (d(1850, 1, 1), d(1860, 12, 31))
    b = date_bounds(_dv("1850", "from_to", value_to="1860"))
    assert (b.earliest, b.latest) == (d(1850, 1, 1), d(1860, 12, 31))
    b = date_bounds(_dv("1850", "from"))
    assert (b.earliest, b.latest, b.known) == (d(1850, 1, 1), None, True)
    b = date_bounds(_dv("1850", "to"))
    assert (b.earliest, b.latest, b.known) == (None, d(1850, 12, 31), True)
    assert date_bounds(_dv("", "unparsed", original_text="x")).known is False
    assert date_bounds(None).known is False
    # Legacy exact+approximate reads as about.
    b = date_bounds(DateValue(value="1850", precision="approximate"))
    assert (b.earliest, b.latest) == (d(1850, 1, 1), d(1850, 12, 31))


def test_julian_bounds_conservative():
    dv = _dv("1650-03-15", calendar="julian")
    b = date_bounds(dv)
    assert b.known
    assert b.earliest == date(1650, 3, 15)  # as written
    assert b.latest == julian_to_gregorian(1650, 3, 15)  # converted, later
    assert b.latest > b.earliest
    assert dv.value == "1650-03-15"  # value untouched
    # A Julian-only day (29 FEB 1700 is in the window; use 1500) is clamped, not an error.
    b = date_bounds(_dv("1500-02-29", calendar="julian"))
    assert b.known and b.earliest <= b.latest


def test_swedish_window_bounds_unknown():
    assert date_bounds(_dv("1705-03-15", calendar="julian")).known is False
    assert date_bounds(_dv("1705", calendar="julian")).known is False
    assert date_bounds(_dv("1700-02-01", calendar="julian")).known is False
    assert date_bounds(_dv("1712-02-29", calendar="julian")).known is False
    assert date_bounds(_dv("1650", "between", value_to="1705", calendar="julian")).known is False
    # Outside the window and Gregorian dates in the window stay known.
    assert date_bounds(_dv("1700-01-31", calendar="julian")).known is True
    assert date_bounds(_dv("1712-03-01", calendar="julian")).known is True
    assert date_bounds(_dv("1705-03-15", calendar="gregorian")).known is True


def test_swedish_date_formatting():
    assert format_date_sv(_dv("1850", "about")) == "ca 1850"
    assert format_date_sv(_dv("1850", "estimated")) == "uppskattat 1850"
    assert format_date_sv(_dv("1850", "calculated")) == "beräknat 1850"
    assert format_date_sv(_dv("1850", "before")) == "före 1850"
    assert format_date_sv(_dv("1850", "after")) == "efter 1850"
    assert format_date_sv(_dv("1850", "from")) == "från 1850"
    assert format_date_sv(_dv("1850", "to")) == "till 1850"
    assert format_date_sv(_dv("1850", "between", value_to="1860")) == "mellan 1850 och 1860"
    assert format_date_sv(_dv("1850", "from_to", value_to="1860")) == "från 1850 till 1860"
    assert format_date_sv(_dv("1700-02-15", calendar="julian")) == "1700-02-15 (julianskt)"
    assert format_date_sv(_dv("", "unparsed", original_text="  omkring jul ")) == "omkring jul"
    assert format_date_sv(None) == ""


def test_consumers_treat_qualified_dates_as_not_exact():
    from slaktbusken.persistence.settings_io import PersonCheckConfig
    from slaktbusken.model.person import Person
    from slaktbusken.model.project import ProjectData, ProjectMetadata
    from slaktbusken.model.residence import ResidenceFact
    from slaktbusken.services import comparison_session
    from slaktbusken.services.checks.calendar_checks import check_valid_swedish_calendar
    from slaktbusken.services.checks.date_utils import (
        age_in_years,
        days_between,
        parse_date_value,
    )
    from slaktbusken.services.merge_rules import _date_value
    from slaktbusken.services.person_check_engine import CheckContext
    from slaktbusken.services.person_summary import _year_of
    from slaktbusken.services.residence_coverage import _get_birth_death_years
    from slaktbusken.services.residence_inference import infer_bounds

    exact = _dv("1850-05-03")
    qualified = [
        _dv("1850-05-03", q, original_text="INT 1850-05-03 (x)" if q == "interpreted" else None,
            value_to="1860-05-03" if q in ("between", "from_to") else None)
        for q in NON_EXACT_QUALIFIERS
    ] + [_dv("", "unparsed", original_text="omkring 1850"),
         DateValue(value="1850-05-03", precision="approximate")]

    # date_utils: precision is the effective qualifier; age and interval need exact dates.
    pe = parse_date_value(exact)
    assert pe is not None and pe.precision == "exact"
    assert parse_date_value(_dv("", "unparsed", original_text="x")) is None
    later = parse_date_value(_dv("1900-05-03"))
    assert age_in_years(pe, later) == 50
    assert days_between(pe, later) is not None
    for q in qualified:
        pq = parse_date_value(q)
        if pq is None:
            continue
        assert pq.precision == effective_qualifier(q) != "exact"
        assert age_in_years(pq, later) is None and age_in_years(pe, pq) is None
        assert days_between(pq, later) is None and days_between(pe, pq) is None

    # person_summary: a year only for exact and legacy about dates.
    assert _year_of(exact) == "1850"
    for q in qualified:
        expected = "1850" if effective_qualifier(q) == "about" else ""
        assert _year_of(q) == expected, q

    # merge_rules: only exact dates take part in matching.
    def event(dv):
        return Event(id="e", type="birth", participants=[Participant("p", "child")], date=dv)

    assert _date_value(event(exact)) == "1850-05-03"
    for q in qualified:
        assert _date_value(event(q)) is None, q

    # calendar_checks: the 1753 check ignores qualified dates.
    bad = "1753-02-20"
    person = Person(id="p", sex="M", names=[])
    config = PersonCheckConfig()
    ctx = CheckContext()
    ev_exact = Event(id="e1", type="birth", participants=[Participant("p", "child")],
                     date=_dv(bad))
    ev_about = Event(id="e2", type="birth", participants=[Participant("p", "child")],
                     date=_dv(bad, "about"))
    assert len(check_valid_swedish_calendar(person, [ev_exact], config, ctx)) == 1
    assert check_valid_swedish_calendar(person, [ev_about], config, ctx) == []

    # residence_coverage and residence_inference: birth/death bounds need exact dates.
    data = ProjectData(project=ProjectMetadata(title="T"))
    data.persons.append(person)
    fact = ResidenceFact(id="r", person_id="p", place_id="pl")
    for q in qualified:
        data.events[:] = [
            Event(id="b", type="birth", participants=[Participant("p", "child")], date=q),
            Event(id="d", type="death", participants=[Participant("p", "deceased")], date=q),
        ]
        by, dy = _get_birth_death_years(person.id, data)
        # exact_value is None for every qualified date, legacy about included.
        assert (by, dy) == (None, None), q
        assert infer_bounds(fact, data).derived == [], q
    data.events[:] = [Event(id="b", type="birth", participants=[Participant("p", "child")], date=exact)]
    assert _get_birth_death_years(person.id, data) == (1850, None)
    assert [d.value for d in infer_bounds(fact, data).derived] == ["1850-05-03"]

    # foster_sync and comparison_session: qualified dates sort and compare apart from exact.
    assert sort_key(exact) < sort_key(_dv("1850-05-03", "about"))
    assert sort_key(_dv("", "unparsed", original_text="x")) > sort_key(exact)
    item = lambda dv: comparison_session._date_place_item(dv, None, {})  # noqa: E731
    base = item(exact)
    for q in qualified:
        assert item(q).key != base.key, q
    assert exact_value(exact) == "1850-05-03"
    assert exact_value(_dv("1850-05-03", calendar="julian")) is None


def test_invalid_day_unparsed_in_import(tmp_path: Path):
    from slaktbusken.gedcom.importer import GEDCOMImporter
    from slaktbusken.model.project import ProjectData, ProjectMetadata

    ged = tmp_path / "t.ged"
    ged.write_text(
        "0 HEAD\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME Johan /Andersson/\n1 SEX M\n"
        "1 BIRT\n2 DATE 31 FEB 1850\n0 TRLR\n",
        encoding="utf-8",
    )
    tdir = tmp_path / "translation"
    tdir.mkdir()
    data = ProjectData(project=ProjectMetadata(title="T"))
    GEDCOMImporter(data, tdir).import_file(ged)
    birth = next(e for e in data.events if e.type == "birth")
    assert birth.date is not None
    assert birth.date.qualifier == "unparsed"
    assert birth.date.value == ""
    assert birth.date.original_text == "31 FEB 1850"


@settings(max_examples=200, deadline=None)
@given(dv=valid_date_values())
def test_date_validity_property(dv):
    """Every generated date is valid, and breaking a day makes it invalid."""
    assert validate_date_value(dv) == []
    if dv.qualifier == "exact" and len(dv.value) == 10:
        y, m = int(dv.value[:4]), int(dv.value[5:7])
        bad = _dv(f"{y:04d}-{m:02d}-32", calendar=dv.calendar)
        assert validate_date_value(bad)


def test_swedish_calendar_not_modelled_by_date_semantics():
    from slaktbusken.services.checks.date_utils import (
        is_valid_swedish_calendar,
        parse_date_value,
    )

    # 1753-02-20 never existed in Sweden, but is real in both calendars here.
    assert is_real_date("1753-02-20", "gregorian")
    assert validate_date_value(_dv("1753-02-20")) == []
    assert is_valid_swedish_calendar(parse_date_value(_dv("1753-02-20"))) is False
    # Dates in the 1700-1712 window are neither converted nor shifted.
    dv = _dv("1712-02-30", calendar="julian")
    assert validate_date_value(dv)  # still not a real day
    ok = _dv("1712-02-29", calendar="julian")
    assert validate_date_value(ok) == []
    assert ok.value == "1712-02-29" and date_bounds(ok).known is False
    source = Path(ds.__file__).read_text(encoding="utf-8")
    import_lines = [
        ln for ln in source.splitlines() if ln.startswith(("import ", "from "))
    ]
    assert not any("validators" in ln for ln in import_lines)
    assert "def is_valid_swedish_calendar" not in source
