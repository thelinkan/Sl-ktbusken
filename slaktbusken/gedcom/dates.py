"""GEDCOM date parsing and formatting.

Pure module (no Qt, no I/O). ``parse_gedcom_date`` turns the text of a GEDCOM
``DATE`` line into a :class:`DateValue` and never loses or falsifies a date: a
date that cannot be read reliably becomes an *unparsed* ``DateValue`` that keeps
the original text. ``format_gedcom_date`` writes the structured fields back as
GEDCOM text and ``export_gedcom_date`` applies the ``original_text`` rules of
the export.

Grammar (case-insensitive, whitespace collapsed)::

    date_expr := [calendar] ( range | period | approx | interp | simple )
    range     := "BET" endpoint "AND" endpoint
    period    := "FROM" endpoint ["TO" endpoint] | "TO" endpoint
    approx    := ("ABT"|"EST"|"CAL"|"BEF"|"AFT") endpoint
    interp    := "INT" endpoint "(" text ")"
    endpoint  := [calendar] simple
    calendar  := "@#DJULIAN@" | "@#DGREGORIAN@"
    simple    := [day] [month] year | iso | dotted

Dates are stored as written; nothing is converted between calendars and the
Swedish calendar of 1700-1712 is not modelled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from slaktbusken.model.date_semantics import (
    effective_qualifier,
    is_real_date,
    validate_date_value,
)
from slaktbusken.model.event import DateValue

_MONTHS: dict[str, int] = {
    "JAN": 1, "FEB": 2, "MAR": 3, "MARS": 3, "APR": 4, "MAY": 5, "MAJ": 5,
    "JUN": 6, "JUNI": 6, "JUL": 7, "JULI": 7, "AUG": 8, "SEP": 9,
    "OKT": 10, "OCT": 10, "NOV": 11, "DEC": 12,
}
_MONTH_NAMES = (
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)

_ESCAPE_RE = re.compile(r"^(@#D[^@]*@)\s*(.*)$", re.DOTALL)
_BET_RE = re.compile(r"^BET\s+(.+?)\s+AND\s+(.+)$", re.IGNORECASE)
_FROM_TO_RE = re.compile(r"^FROM\s+(.+?)\s+TO\s+(.+)$", re.IGNORECASE)
_FROM_RE = re.compile(r"^FROM\s+(.+)$", re.IGNORECASE)
_TO_RE = re.compile(r"^TO\s+(.+)$", re.IGNORECASE)
_APPROX_RE = re.compile(r"^(ABT|EST|CAL|BEF|AFT)\s+(.+)$", re.IGNORECASE)
_INT_RE = re.compile(r"^INT\s+(.+?)\s*\((.*)\)$", re.IGNORECASE)
_DUAL_YEAR_RE = re.compile(r"\b\d{3,4}\s*/\s*\d{1,4}\b")
_ISO_RE = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")
_DOTTED_RE = re.compile(r"^(?:(\d{1,2})\.)?(\d{1,2})\.(\d{4})$")
_WORDS_RE = re.compile(r"^(?:(\d{1,2})\s+)?(?:([^\W\d_]+)\s+)?(\d{4})$")

_APPROX_QUALIFIER = {
    "ABT": "about", "EST": "estimated", "CAL": "calculated",
    "BEF": "before", "AFT": "after",
}
_QUALIFIER_KEYWORD = {v: k for k, v in _APPROX_QUALIFIER.items()}

_STALE_ORIGINAL_WARNING = "Originaltexten stämmer inte med datumet och användes inte"


@dataclass
class ParsedGedcomDate:
    """Result of parsing one GEDCOM DATE value."""

    value: DateValue
    warnings: list[str] = field(default_factory=list)  # Swedish, for the import log
    dual_year: bool = False


class _Unparsable(Exception):
    def __init__(self, dual_year: bool = False) -> None:
        super().__init__()
        self.dual_year = dual_year


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _normalise(text: str) -> str:
    return _collapse(text).upper()


def _precision_of_iso(iso: str) -> str:
    return {4: "year", 7: "month", 10: "day"}.get(len(iso), "day")


def _calendar_of_escape(escape: str) -> str:
    name = escape[3:-1].strip().upper()
    if name == "JULIAN":
        return "julian"
    if name == "GREGORIAN":
        return "gregorian"
    raise _Unparsable()


def _parse_simple(text: str, calendar: str) -> str:
    """Parse one simple date to ISO, validated in *calendar*."""
    t = text.strip()
    if _DUAL_YEAR_RE.search(t):
        raise _Unparsable(dual_year=True)
    year: str
    month: Optional[int] = None
    day: Optional[int] = None

    m = _ISO_RE.match(t)
    if m:
        year = m.group(1)
        month = int(m.group(2)) if m.group(2) else None
        day = int(m.group(3)) if m.group(3) else None
    else:
        m = _DOTTED_RE.match(t)
        if m:
            day = int(m.group(1)) if m.group(1) else None
            month = int(m.group(2))
            year = m.group(3)
        else:
            m = _WORDS_RE.match(t)
            if not m:
                raise _Unparsable()
            year = m.group(3)
            if m.group(2):
                month = _MONTHS.get(m.group(2).upper())
                if month is None:
                    raise _Unparsable()
            if m.group(1):
                if month is None:
                    raise _Unparsable()
                day = int(m.group(1))

    if int(year) == 0 or (day is not None and month is None):
        raise _Unparsable()
    if month is None:
        iso = year
    elif day is None:
        iso = f"{year}-{month:02d}"
    else:
        iso = f"{year}-{month:02d}-{day:02d}"
    if not is_real_date(iso, calendar):
        raise _Unparsable()
    return iso


def _split_escape(text: str) -> tuple[Optional[str], str]:
    m = _ESCAPE_RE.match(text.strip())
    if not m:
        return None, text.strip()
    return _calendar_of_escape(m.group(1)), m.group(2).strip()


def _parse_endpoint(text: str, lead: Optional[str]) -> tuple[str, Optional[str]]:
    """Parse ``[calendar] simple``; return (iso, calendar written or None)."""
    own, rest = _split_escape(text)
    if own is not None and lead is not None and own != lead:
        raise _Unparsable()
    cal = own or lead
    return _parse_simple(rest, cal or "gregorian"), cal


def _interpret(norm: str) -> DateValue:
    """Interpret a whitespace-collapsed non-empty date; raise _Unparsable."""
    lead, rest = _split_escape(norm)
    qualifier = "exact"
    texts: list[str]

    m = _BET_RE.match(rest)
    if m:
        qualifier, texts = "between", [m.group(1), m.group(2)]
    elif (m := _FROM_TO_RE.match(rest)):
        qualifier, texts = "from_to", [m.group(1), m.group(2)]
    elif (m := _FROM_RE.match(rest)):
        qualifier, texts = "from", [m.group(1)]
    elif (m := _TO_RE.match(rest)):
        qualifier, texts = "to", [m.group(1)]
    elif (m := _APPROX_RE.match(rest)):
        qualifier, texts = _APPROX_QUALIFIER[m.group(1).upper()], [m.group(2)]
    elif (m := _INT_RE.match(rest)):
        qualifier, texts = "interpreted", [m.group(1)]
    else:
        texts = [rest]

    isos: list[str] = []
    cals: set[str] = set()
    for text in texts:
        iso, cal = _parse_endpoint(text, lead)
        isos.append(iso)
        cals.add(cal or "gregorian")
    if len(cals) != 1:
        raise _Unparsable()
    calendar = cals.pop()

    precision = _precision_of_iso(isos[0]) if qualifier == "exact" else "approximate"
    dv = DateValue(
        value=isos[0],
        precision=precision,
        qualifier=qualifier,
        value_to=isos[1] if len(isos) > 1 else None,
        calendar=calendar,
        original_text=norm if qualifier == "interpreted" else None,
    )
    if validate_date_value(dv):  # e.g. reversed range
        raise _Unparsable()
    return dv


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_gedcom_date(text: str) -> Optional[ParsedGedcomDate]:
    """Parse a GEDCOM DATE value.

    Returns ``None`` only for blank text. Every other text yields a
    :class:`DateValue`: ``unparsed`` (empty ``value``, whitespace-normalised
    ``original_text``) when it cannot be read reliably.
    """
    if text is None or not text.strip():
        return None
    norm = _collapse(text)
    try:
        dv = _interpret(norm)
    except _Unparsable as exc:
        dv = DateValue(
            value="", precision="approximate", qualifier="unparsed",
            calendar="gregorian", original_text=norm,
        )
        if exc.dual_year:
            msg = (
                f'Dubbelt årtal i datumet "{norm}" kan inte tolkas entydigt '
                "och sparades som originaltext."
            )
        else:
            msg = f'Datumet "{norm}" kunde inte tolkas och sparades som originaltext.'
        return ParsedGedcomDate(value=dv, warnings=[msg], dual_year=exc.dual_year)
    if dv.qualifier != "interpreted" and _normalise(norm) != _normalise(format_gedcom_date(dv)):
        dv.original_text = norm
    return ParsedGedcomDate(value=dv)


def _format_iso(iso: str, calendar: str) -> str:
    m = _ISO_RE.match(iso or "")
    if not m:
        text = iso or ""
    else:
        year, month, day = m.group(1), m.group(2), m.group(3)
        parts = []
        if day:
            parts.append(str(int(day)))
        if month:
            parts.append(_MONTH_NAMES[int(month) - 1])
        parts.append(year)
        text = " ".join(parts)
    if calendar == "julian" and text:
        return f"@#DJULIAN@ {text}"
    return text


def _phrase_of(dv: DateValue) -> str:
    m = _INT_RE.match(_collapse(dv.original_text or ""))
    return m.group(2) if m else "tolkat"


def format_gedcom_date(dv: DateValue) -> str:
    """GEDCOM text built from the structured fields only."""
    q = effective_qualifier(dv)
    if q == "unparsed":
        return dv.original_text or ""
    if not dv.value:
        return ""
    cal = dv.calendar
    first = _format_iso(dv.value, cal)
    if q == "exact":
        return first
    if q in _QUALIFIER_KEYWORD:
        return f"{_QUALIFIER_KEYWORD[q]} {first}"
    second = _format_iso(dv.value_to or "", cal)
    if q == "between":
        return f"BET {first} AND {second}"
    if q == "from_to":
        return f"FROM {first} TO {second}"
    if q == "from":
        return f"FROM {first}"
    if q == "to":
        return f"TO {first}"
    if q == "interpreted":
        return f"INT {first} ({_phrase_of(dv)})"
    return first


def export_gedcom_date(dv: DateValue) -> tuple[str, list[str]]:
    """GEDCOM text and Swedish warnings for exporting *dv*.

    ``original_text`` is used verbatim when it still interprets to the stored
    fields; unparsed dates always export their original text.
    """
    if effective_qualifier(dv) == "unparsed":
        return dv.original_text or "", []
    warnings: list[str] = []
    if dv.original_text:
        parsed = parse_gedcom_date(dv.original_text)
        if (
            parsed is not None
            and parsed.value.value == dv.value
            and (parsed.value.value_to or None) == (dv.value_to or None)
            and parsed.value.qualifier == effective_qualifier(dv)
            and parsed.value.calendar == dv.calendar
        ):
            return dv.original_text, []
        warnings.append(_STALE_ORIGINAL_WARNING)
    return format_gedcom_date(dv), warnings
