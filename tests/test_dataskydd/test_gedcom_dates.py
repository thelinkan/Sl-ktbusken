"""GEDCOM date import and export tests (data-integrity-0-3-0, task 5.5).

Properties 7, 8 and 9 plus the named import and export examples for
``gedcom/dates.py``, the importer date paths and ``GEDCOMExporter._format_date``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from slaktbusken.gedcom.dates import (
    export_gedcom_date,
    format_gedcom_date,
    parse_gedcom_date,
)
from slaktbusken.gedcom.exporter import GEDCOMExporter
from slaktbusken.gedcom.importer import GEDCOMImporter, _parse_resi_date
from slaktbusken.model.date_semantics import (
    date_bounds,
    display_year,
    effective_qualifier,
    is_exact,
    validate_date_value,
)
from slaktbusken.model.event import DateValue
from slaktbusken.model.project import ProjectData, ProjectMetadata
from tests.test_dataskydd.strategies_dates import (
    date_like_texts,
    valid_date_values,
)

pytestmark = pytest.mark.mandatory_integrity

_KEYWORDS = {"BET", "FROM", "TO", "BEF", "AFT", "ABT", "EST", "CAL", "INT"}


def _parse(text: str) -> DateValue:
    parsed = parse_gedcom_date(text)
    assert parsed is not None
    return parsed.value


def _is_unparsed(dv: DateValue, text: str) -> bool:
    return dv.qualifier == "unparsed" and dv.value == "" and dv.original_text == " ".join(text.split())


def _export(dv: DateValue) -> str:
    return GEDCOMExporter()._format_date(dv)


# ---------------------------------------------------------------------------
# Property 7
# ---------------------------------------------------------------------------


@settings(max_examples=400, deadline=None)
@given(text=date_like_texts())
def test_dp_property_7_parsing_is_total_and_never_falsifies(text):
    """Property 7: every non-empty text yields a DateValue; unparsed keeps the text."""
    parsed = parse_gedcom_date(text)
    assert parsed is not None
    dv = parsed.value
    norm = " ".join(text.split())
    if dv.qualifier == "unparsed":
        assert dv.value == "" and dv.value_to in (None, "")
        assert dv.original_text == norm
        assert parsed.warnings
        return
    assert dv.value
    assert validate_date_value(dv) == []
    tokens = {t.upper() for t in norm.replace("(", " ").replace(")", " ").split()}
    if tokens & _KEYWORDS:
        assert dv.qualifier != "exact"
    if dv.qualifier == "exact":
        assert not (tokens & _KEYWORDS)
        assert dv.value_to in (None, "")


@settings(max_examples=200, deadline=None)
@given(dv=valid_date_values(qualifiers=("exact", "about", "between")))
def test_dp_property_7_julian_endpoints_stored_as_written(dv):
    """Property 7: a Julian input with real endpoints keeps its written endpoints."""
    if dv.calendar != "julian":
        return
    text = format_gedcom_date(dv)
    out = _parse(text)
    assert (out.value, out.value_to or None, out.calendar) == (dv.value, dv.value_to, "julian")


@settings(max_examples=200, deadline=None)
@given(year=st.sampled_from([1500, 1600, 1700, 1900]))
def test_dp_property_7_julian_only_day_without_escape_unparsed(year):
    text = f"29 FEB {year}"
    if year % 400 == 0:
        return
    assert _is_unparsed(_parse(text), text)
    out = _parse(f"@#DJULIAN@ {text}")
    assert (out.value, out.calendar, out.qualifier) == (f"{year}-02-29", "julian", "exact")


# ---------------------------------------------------------------------------
# Property 8
# ---------------------------------------------------------------------------


@settings(max_examples=400, deadline=None)
@given(dv=valid_date_values())
def test_dp_property_8_structured_dates_round_trip(dv):
    """Property 8: parse(export(dv)) keeps value, value_to, qualifier, calendar."""
    text, _ = export_gedcom_date(dv)
    out = _parse(text)
    assert out.value == dv.value
    assert (out.value_to or None) == (dv.value_to or None)
    assert out.qualifier == dv.qualifier
    assert out.calendar == dv.calendar


@settings(max_examples=200, deadline=None)
@given(
    dv=valid_date_values(qualifiers=("exact", "about", "before", "after", "between", "from_to")),
    style=st.sampled_from(["lower", "upper", "spaced"]),
)
def test_dp_property_8_consistent_original_text_is_exported_verbatim(dv, style):
    base = format_gedcom_date(dv)
    variant = {
        "lower": base.lower().replace("@#djulian@", "@#DJULIAN@"),
        "upper": base.upper(),
        "spaced": "  ".join(base.split(" ")),
    }[style]
    dv.original_text = variant
    text, warnings = export_gedcom_date(dv)
    assert text == variant
    assert warnings == []


@settings(max_examples=100, deadline=None)
@given(text=date_like_texts())
def test_dp_property_8_unparsed_exports_original_text(text):
    dv = _parse(text)
    assume(dv.qualifier == "unparsed")
    assert export_gedcom_date(dv) == (dv.original_text, [])


# ---------------------------------------------------------------------------
# Property 9
# ---------------------------------------------------------------------------


@settings(max_examples=300, deadline=None)
@given(
    dv=valid_date_values(qualifiers=("exact", "about", "before", "after", "between")),
    other=valid_date_values(qualifiers=("exact", "about", "before", "after", "between")),
)
def test_dp_property_9_stale_original_text_never_exported(dv, other):
    """Property 9: a stale original text gives the structured text and one warning."""
    other_text = format_gedcom_date(other)
    interpreted = _parse(other_text)
    same = (
        interpreted.value == dv.value
        and (interpreted.value_to or None) == (dv.value_to or None)
        and interpreted.qualifier == dv.qualifier
        and interpreted.calendar == dv.calendar
    )
    assume(not same)
    dv.original_text = other_text
    text, warnings = export_gedcom_date(dv)
    assert text == format_gedcom_date(dv)
    assert len(warnings) == 1


# ---------------------------------------------------------------------------
# Import examples
# ---------------------------------------------------------------------------


def test_import_between_and():
    dv = _parse("BET 1850 AND 1860")
    assert (dv.qualifier, dv.value, dv.value_to, dv.precision) == (
        "between", "1850", "1860", "approximate")
    dv = _parse("bet 3 may 1850 and 4 jun 1850")
    assert (dv.value, dv.value_to) == ("1850-05-03", "1850-06-04")


def test_import_from_to():
    dv = _parse("FROM 1850 TO 1860")
    assert (dv.qualifier, dv.value, dv.value_to) == ("from_to", "1850", "1860")


def test_import_from_only_and_to_only():
    dv = _parse("FROM 1850")
    assert (dv.qualifier, dv.value, dv.value_to) == ("from", "1850", None)
    dv = _parse("TO 1860")
    assert (dv.qualifier, dv.value, dv.value_to) == ("to", "1860", None)


def test_import_before_after_about_estimated_calculated():
    for kw, q in [("BEF", "before"), ("AFT", "after"), ("ABT", "about"),
                  ("EST", "estimated"), ("CAL", "calculated")]:
        dv = _parse(f"{kw} 3 MAY 1850")
        assert (dv.qualifier, dv.value, dv.precision) == (q, "1850-05-03", "approximate")
        assert not is_exact(dv)


def test_import_int_phrase():
    dv = _parse("INT 1850 (omkring jul)")
    assert (dv.qualifier, dv.value) == ("interpreted", "1850")
    assert dv.original_text == "INT 1850 (omkring jul)"
    assert not is_exact(dv)


def test_import_julian_as_written():
    dv = _parse("@#DJULIAN@ 15 MAR 1650")
    assert (dv.value, dv.calendar, dv.qualifier) == ("1650-03-15", "julian", "exact")


def test_import_julian_escape_per_endpoint():
    both = _parse("BET @#DJULIAN@ 1 JAN 1650 AND @#DJULIAN@ 5 JAN 1650")
    assert (both.qualifier, both.calendar, both.value, both.value_to) == (
        "between", "julian", "1650-01-01", "1650-01-05")
    lead = _parse("@#DJULIAN@ BET 1 JAN 1650 AND 5 JAN 1650")
    assert (lead.qualifier, lead.calendar, lead.value_to) == ("between", "julian", "1650-01-05")


def test_import_julian_swedish_window_kept_as_written():
    dv = _parse("@#DJULIAN@ 15 MAR 1705")
    assert (dv.value, dv.calendar, dv.qualifier) == ("1705-03-15", "julian", "exact")
    assert date_bounds(dv).known is False


def test_import_dual_year_becomes_unparsed():
    parsed = parse_gedcom_date("15 MAR 1750/51")
    assert parsed.dual_year is True
    assert _is_unparsed(parsed.value, "15 MAR 1750/51")
    assert parsed.warnings


def test_import_swedish_month_names():
    assert _parse("15 MAJ 1850").value == "1850-05-15"
    assert _parse("15 MARS 1850").value == "1850-03-15"
    assert _parse("15 JUNI 1850").value == "1850-06-15"
    assert _parse("15 JULI 1850").value == "1850-07-15"
    assert _parse("15 OKT 1850").value == "1850-10-15"
    assert _parse("MAJ 1850").value == "1850-05"


def test_import_iso_and_dotted_dates():
    assert _parse("1850-05-03").value == "1850-05-03"
    assert _parse("1850-05").value == "1850-05"
    dv = _parse("3.5.1850")
    assert (dv.value, dv.qualifier) == ("1850-05-03", "exact")
    assert _parse("5.1850").value == "1850-05"
    assert _parse("03.05.1850").value == "1850-05-03"


def test_import_invalid_dates_become_unparsed():
    for text in ["31 FEB 1850", "32 JAN 1850", "0 JAN 1850", "15 XXX 1850",
                 "BET 1860 AND 1850", "1850-13-01", "30 APR 1850 1"]:
        assert _is_unparsed(_parse(text), text), text


def test_import_exceptional_swedish_dates_become_unparsed():
    for text in ["30 FEB 1712", "@#DJULIAN@ 30 FEB 1712", "@#DGREGORIAN@ 30 FEB 1712",
                 "29 FEB 1700"]:
        assert _is_unparsed(_parse(text), text), text
    # 29 FEB 1700 is real only with the Julian escape.
    dv = _parse("@#DJULIAN@ 29 FEB 1700")
    assert (dv.value, dv.calendar, dv.qualifier) == ("1700-02-29", "julian", "exact")


def test_import_mixed_calendar_range_becomes_unparsed():
    for text in [
        "BET @#DJULIAN@ 1 JAN 1650 AND 5 JAN 1650",
        "BET @#DJULIAN@ 1 JAN 1650 AND @#DGREGORIAN@ 5 JAN 1650",
        "FROM 1 JAN 1650 TO @#DJULIAN@ 5 JAN 1650",
    ]:
        assert _is_unparsed(_parse(text), text), text


def test_import_unknown_phrase_becomes_unparsed_with_warning():
    parsed = parse_gedcom_date("omkring jul  1850")
    assert _is_unparsed(parsed.value, "omkring jul  1850")
    assert parsed.value.original_text == "omkring jul 1850"
    assert len(parsed.warnings) == 1
    parsed = parse_gedcom_date("@#DHEBREW@ 1 TSH 5600")
    assert parsed.value.qualifier == "unparsed"
    assert parse_gedcom_date("   ") is None


def test_import_residence_dates_use_same_interpretation():
    """RESI dates are interpretable exactly when ``parse_gedcom_date`` reads a Gregorian date."""
    texts = [
        "30 FEB 1712", "29 FEB 1700", "15 MAR 1850", "ABT 1850", "BEF 1850",
        "1850/51", "@#DJULIAN@ 1 JAN 1650", "xyz", "FROM 30 FEB 1712 TO 1720",
        "FROM 1850 TO 1860", "BET 1850 AND 1860", "BET 1860 AND 1850",
        "FROM 1850", "TO 1860", "EST 1850", "INT 1850 (x)",
    ]
    for text in texts:
        result = _parse_resi_date(text)
        dv = _parse(text)
        ok = dv.qualifier in (
            "exact", "about", "estimated", "calculated", "before", "after",
            "between", "from_to", "from", "to",
        ) and dv.calendar == "gregorian"
        assert result.interpretable is ok, text
    r = _parse_resi_date("FROM 1850 TO 1860")
    assert (r.start_latest, r.end_earliest) == ("1850", "1860")
    r = _parse_resi_date("ABT 1850")
    assert (r.start_latest, r.start_precision) == ("1850", "approximate")
    r = _parse_resi_date("30 FEB 1712")
    assert r.start_latest is None and r.end_earliest is None


_IMPORT_GEDCOM = """\
0 HEAD
1 CHAR UTF-8
0 @I1@ INDI
1 NAME Johan /Andersson/
1 SEX M
1 BIRT
2 DATE 30 FEB 1712
1 DEAT
2 DATE FROM 1850 TO 1860
1 BAPM
2 DATE omkring jul
1 BURI
2 DATE BET 1850 AND 1860
0 TRLR
"""


def _import_text(tmp_path: Path, text: str) -> ProjectData:
    tdir = tmp_path / "translation"
    tdir.mkdir()
    ged = tmp_path / "t.ged"
    ged.write_text(text, encoding="utf-8")
    data = ProjectData(project=ProjectMetadata(title="T"))
    GEDCOMImporter(data, tdir).import_file(ged)
    return data


def test_no_date_line_is_ever_dropped(tmp_path: Path):
    data = _import_text(tmp_path, _IMPORT_GEDCOM)
    by_type = {e.type: e for e in data.events}
    assert set(by_type) >= {"birth", "death", "baptism"}
    for event in by_type.values():
        assert event.date is not None
    assert by_type["birth"].date.original_text == "30 FEB 1712"
    assert by_type["baptism"].date.original_text == "omkring jul"
    assert all(e.date.qualifier == "unparsed" for e in (by_type["birth"], by_type["baptism"]))


def test_from_to_never_becomes_exact_year(tmp_path: Path):
    dv = _parse("FROM 1850 TO 1860")
    assert not is_exact(dv) and display_year(dv) is None
    data = _import_text(tmp_path, _IMPORT_GEDCOM)
    death = next(e for e in data.events if e.type == "death")
    assert death.date.qualifier == "from_to"
    assert (death.date.value, death.date.value_to) == ("1850", "1860")
    assert not is_exact(death.date)
    assert display_year(death.date) is None


# ---------------------------------------------------------------------------
# Export examples
# ---------------------------------------------------------------------------


def _d(value, qualifier="exact", value_to=None, calendar="gregorian", original_text=None):
    precision = ({4: "year", 7: "month"}.get(len(value), "day")
                 if qualifier == "exact" else "approximate")
    return DateValue(value=value, precision=precision, qualifier=qualifier,
                     value_to=value_to, calendar=calendar, original_text=original_text)


def test_export_qualifiers():
    assert _export(_d("1850-05-03")) == "3 MAY 1850"
    assert _export(_d("1850-05")) == "MAY 1850"
    assert _export(_d("1850")) == "1850"
    assert _export(_d("1850", "about")) == "ABT 1850"
    assert _export(_d("1850", "estimated")) == "EST 1850"
    assert _export(_d("1850", "calculated")) == "CAL 1850"
    assert _export(_d("1850", "before")) == "BEF 1850"
    assert _export(_d("1850", "after")) == "AFT 1850"
    assert _export(_d("1850", "interpreted")) == "INT 1850 (tolkat)"
    # Legacy 0.4 approximate date.
    assert _export(DateValue(value="1850", precision="approximate")) == "ABT 1850"


def test_export_ranges():
    assert _export(_d("1850", "between", "1860")) == "BET 1850 AND 1860"
    assert _export(_d("1850-05-03", "from_to", "1860-06-04")) == "FROM 3 MAY 1850 TO 4 JUN 1860"
    assert _export(_d("1850", "from")) == "FROM 1850"
    assert _export(_d("1860", "to")) == "TO 1860"


def test_export_julian_escape():
    assert _export(_d("1650-03-15", calendar="julian")) == "@#DJULIAN@ 15 MAR 1650"
    assert _export(_d("1650-01-01", "between", "1650-01-05", "julian")) == (
        "BET @#DJULIAN@ 1 JAN 1650 AND @#DJULIAN@ 5 JAN 1650")
    assert _export(_d("1650", "about", calendar="julian")) == "ABT @#DJULIAN@ 1650"


def test_export_original_text_verbatim():
    exporter = GEDCOMExporter()
    dv = _d("1850-05-03", original_text="3 may 1850")
    assert exporter._format_date(dv) == "3 may 1850"
    assert exporter._date_warnings == []
    dv = _d("1850-05-03", original_text="1850-05-03")
    assert exporter._format_date(dv) == "1850-05-03"


def test_export_unparsed_verbatim():
    dv = DateValue(value="", precision="approximate", qualifier="unparsed",
                   original_text="omkring jul 1850")
    exporter = GEDCOMExporter()
    assert exporter._format_date(dv) == "omkring jul 1850"
    assert exporter._date_warnings == []


def test_export_stale_original_text_uses_structured():
    exporter = GEDCOMExporter()
    dv = _d("1850-05-03", original_text="1 JAN 1900")
    assert exporter._format_date(dv) == "3 MAY 1850"
    assert len(exporter._date_warnings) == 1
    # The same warning is not repeated for a second stale date.
    exporter._format_date(_d("1851", original_text="1 JAN 1900"))
    assert len(exporter._date_warnings) == 1
    # A stale text with another qualifier is stale too.
    text, warnings = export_gedcom_date(_d("1850", "before", original_text="ABT 1850"))
    assert (text, len(warnings)) == ("BEF 1850", 1)


def test_export_before_never_abt():
    for qualifier, kw in [("before", "BEF"), ("after", "AFT")]:
        for calendar in ("gregorian", "julian"):
            text = _export(_d("1850-05-03", qualifier, calendar=calendar))
            assert text.startswith(kw), text
            assert "ABT" not in text
    for dv in (_d("1850", "between", "1860"), _d("1850", "from_to", "1860"),
               _d("1850", "from"), _d("1850", "to")):
        assert "ABT" not in _export(dv)
    # Even a before date carrying a stale ABT original text.
    assert _export(_d("1850", "before", original_text="ABT 1850")) == "BEF 1850"


@settings(max_examples=300, deadline=None)
@given(dv=valid_date_values())
def test_gedcom_date_round_trip_property(dv):
    text = _export(dv)
    out = _parse(text)
    assert (out.value, out.value_to or None, out.qualifier, out.calendar) == (
        dv.value, dv.value_to, dv.qualifier, dv.calendar)
    assert effective_qualifier(out) == dv.qualifier
