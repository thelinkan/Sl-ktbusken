"""Date semantics: validation, bounds, formatting and exactness of DateValue.

Pure module: no Qt, no I/O. It imports only ``DateValue`` and nothing from
``validators``. It does not model the Swedish calendar of 1700-1712 or the
1753 switch (that stays in ``is_valid_swedish_calendar``). Dates inside the
Swedish calendar window are never converted or shifted; their bounds are
unknown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from slaktbusken.model.event import DateValue

QUALIFIERS = (
    "exact", "about", "estimated", "calculated", "before", "after",
    "between", "from_to", "from", "to", "interpreted", "unparsed",
)
CALENDARS = ("gregorian", "julian")

_VALID_PRECISIONS = {"day", "month", "year", "approximate"}
_RANGE_QUALIFIERS = {"between", "from_to"}
_SINGLE_APPROX_QUALIFIERS = {
    "about", "estimated", "calculated", "before", "after", "from", "to",
    "interpreted",
}
_ISO_RE = re.compile(r"^(\d{4})(?:-(0[1-9]|1[0-2])(?:-(0[1-9]|[12]\d|3[01]))?)?$")
_ISO_VALUE_ERROR = "(förväntat ÅÅÅÅ, ÅÅÅÅ-MM eller ÅÅÅÅ-MM-DD)."

_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

_WINDOW_FIRST = (1700, 2)
_WINDOW_LAST = (1712, 2)

_FORMAT_PREFIX = {
    "about": "ca ",
    "estimated": "uppskattat ",
    "calculated": "beräknat ",
    "interpreted": "tolkat ",
    "before": "före ",
    "after": "efter ",
    "from": "från ",
    "to": "till ",
}


@dataclass(frozen=True)
class DateBounds:
    """Earliest and latest day a date can denote; ``None`` means open."""

    earliest: Optional[date]
    latest: Optional[date]
    known: bool


_UNKNOWN = DateBounds(None, None, False)


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------


def _is_leap(year: int, calendar: str) -> bool:
    if calendar == "julian":
        return year % 4 == 0
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _month_len(year: int, month: int, calendar: str) -> int:
    if month == 2 and _is_leap(year, calendar):
        return 29
    return _MONTH_DAYS[month - 1]


def _parse_iso(iso: Optional[str]) -> Optional[tuple[int, Optional[int], Optional[int]]]:
    if not isinstance(iso, str):
        return None
    m = _ISO_RE.match(iso.strip())
    if not m:
        return None
    y = int(m.group(1))
    mo = int(m.group(2)) if m.group(2) else None
    d = int(m.group(3)) if m.group(3) else None
    return y, mo, d


def is_real_date(iso: str, calendar: str) -> bool:
    """Whether *iso* (ÅÅÅÅ, ÅÅÅÅ-MM or ÅÅÅÅ-MM-DD) is a real date in *calendar*."""
    if calendar not in CALENDARS:
        return False
    parsed = _parse_iso(iso)
    if parsed is None:
        return False
    y, mo, d = parsed
    if mo is not None and d is not None:
        return d <= _month_len(y, mo, calendar)
    return True


def _jdn_from_julian(y: int, m: int, d: int) -> int:
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - 32083


def _gregorian_from_jdn(jdn: int) -> tuple[int, int, int]:
    a = jdn + 32044
    b = (4 * a + 3) // 146097
    c = a - 146097 * b // 4
    d = (4 * c + 3) // 1461
    e = c - 1461 * d // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d - 4800 + m // 10
    return year, month, day


def julian_to_gregorian(y: int, m: int, d: int) -> date:
    """Convert a Julian calendar day to the proleptic Gregorian calendar.

    For comparison bounds only; stored values are never changed.
    """
    return date(*_gregorian_from_jdn(_jdn_from_julian(y, m, d)))


def in_swedish_window(iso: str) -> bool:
    """Whether *iso* lies in 1700-02 to 1712-02 (a year-only value counts when
    its year overlaps the window)."""
    parsed = _parse_iso(iso)
    if parsed is None:
        return False
    y, mo, _ = parsed
    if mo is None:
        return _WINDOW_FIRST[0] <= y <= _WINDOW_LAST[0]
    return _WINDOW_FIRST <= (y, mo) <= _WINDOW_LAST


# ---------------------------------------------------------------------------
# Qualifier and exactness
# ---------------------------------------------------------------------------


def effective_qualifier(dv: DateValue) -> str:
    """``about`` only for legacy ``exact`` + ``approximate``; else the qualifier."""
    if dv.qualifier == "exact" and dv.precision == "approximate":
        return "about"
    return dv.qualifier


def is_exact(dv: Optional[DateValue]) -> bool:
    return dv is not None and effective_qualifier(dv) == "exact"


def display_year(dv: Optional[DateValue]) -> Optional[str]:
    """Four-digit year to show for an exact date or a legacy ``about`` date.

    ``None`` for before/after/ranges/estimated/unparsed and for unusable
    values, so those never appear as a plain year.
    """
    if dv is None or effective_qualifier(dv) not in ("exact", "about"):
        return None
    parsed = _parse_iso(dv.value) if dv.value else None
    return f"{parsed[0]:04d}" if parsed else None


def exact_value(dv: Optional[DateValue]) -> Optional[str]:
    """The ISO value of an exact Gregorian-labelled date, else ``None``."""
    if dv is None or not is_exact(dv) or dv.calendar != "gregorian":
        return None
    if not dv.value or _parse_iso(dv.value) is None:
        return None
    return dv.value.strip()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _local_span(iso: str, calendar: str):
    """Span of *iso* as ((y, m, d) first, (y, m, d) last) in its own calendar."""
    y, mo, d = _parse_iso(iso)  # type: ignore[misc]
    if mo is None:
        return (y, 1, 1), (y, 12, 31)
    if d is None:
        return (y, mo, 1), (y, mo, _month_len(y, mo, calendar))
    return (y, mo, d), (y, mo, d)


def validate_date_value(dv: DateValue) -> list[str]:
    """Swedish error messages for a DateValue; an empty list means valid."""
    errors: list[str] = []
    qualifier = dv.qualifier
    value = dv.value
    value_to = dv.value_to
    calendar_ok = dv.calendar in CALENDARS

    if dv.precision not in _VALID_PRECISIONS:
        errors.append(
            f"Datumprecision '{dv.precision}' är ogiltig; "
            f"måste vara en av {sorted(_VALID_PRECISIONS)}."
        )
    if qualifier not in QUALIFIERS:
        errors.append(
            f"Datumkvalificerare '{qualifier}' är ogiltig; "
            f"måste vara en av {sorted(QUALIFIERS)}."
        )
    if not calendar_ok:
        errors.append(
            f"Kalender '{dv.calendar}' är ogiltig; måste vara en av {sorted(CALENDARS)}."
        )

    def check_iso(text: str, label: str) -> bool:
        """Report a malformed or non-existent date; True when it is a real date."""
        if _parse_iso(text) is None:
            errors.append(f"{label} '{text}' är inte ett giltigt ISO 8601-datum {_ISO_VALUE_ERROR}")
            return False
        if calendar_ok and not is_real_date(text, dv.calendar):
            cal_sv = "julianska" if dv.calendar == "julian" else "gregorianska"
            errors.append(f"{label} '{text}' är inte ett riktigt datum i den {cal_sv} kalendern.")
            return False
        return True

    value_ok = True
    if value:
        value_ok = check_iso(value, "Datumvärde")

    if qualifier == "unparsed":
        if value:
            errors.append("Ett otolkat datum får inte ha något datumvärde.")
        if value_to:
            errors.append("Ett otolkat datum får inte ha något slutdatum.")
        if not (dv.original_text and dv.original_text.strip()):
            errors.append("Ett otolkat datum måste ha originaltext.")
        return errors

    if qualifier == "exact":
        # An empty exact value is tolerated: 0.4 files may hold one.
        if value_to:
            errors.append("Ett exakt datum får inte ha något slutdatum.")
        return errors

    if qualifier in _SINGLE_APPROX_QUALIFIERS or qualifier in _RANGE_QUALIFIERS:
        if not value:
            errors.append(f"Datum med kvalificerare '{qualifier}' måste ha ett datumvärde.")
        if dv.precision != "approximate":
            errors.append(
                f"Datum med kvalificerare '{qualifier}' måste ha precision 'approximate'."
            )
    if qualifier == "interpreted" and not (dv.original_text and dv.original_text.strip()):
        errors.append("Ett tolkat datum måste ha originaltext.")
    if qualifier in _SINGLE_APPROX_QUALIFIERS and value_to:
        errors.append(f"Datum med kvalificerare '{qualifier}' får inte ha något slutdatum.")
    if qualifier in _RANGE_QUALIFIERS:
        if not value_to:
            errors.append(f"Datum med kvalificerare '{qualifier}' måste ha ett slutdatum.")
        else:
            to_ok = check_iso(value_to, "Slutdatum")
            if to_ok and value and value_ok:
                cal = dv.calendar if calendar_ok else "gregorian"
                if _local_span(value_to, cal)[1] < _local_span(value, cal)[0]:
                    errors.append("Slutdatumet får inte vara tidigare än startdatumet.")
    return errors


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------


def _clamped(y: int, m: int, d: int) -> date:
    """Gregorian date for as-written numbers, clamping a Julian-only day."""
    last = _month_len(y, m, "gregorian")
    return date(y, m, min(d, last))


def _endpoint_span(iso: str, calendar: str) -> tuple[date, date]:
    """Earliest and latest day of one endpoint (may raise ValueError)."""
    first, last = _local_span(iso, calendar)
    if calendar != "julian":
        return date(*first), date(*last)
    w_first, w_last = _clamped(*first), _clamped(*last)
    c_first, c_last = julian_to_gregorian(*first), julian_to_gregorian(*last)
    return min(w_first, c_first), max(w_last, c_last)


def date_bounds(dv: Optional[DateValue]) -> DateBounds:
    """Earliest and latest day *dv* can denote, with open bounds where the
    qualifier leaves them open. Unknown for unparsed dates, unusable values
    and Julian endpoints in the Swedish calendar window."""
    if dv is None:
        return _UNKNOWN
    q = effective_qualifier(dv)
    if q == "unparsed" or q not in QUALIFIERS or dv.calendar not in CALENDARS:
        return _UNKNOWN
    if not dv.value or not is_real_date(dv.value, dv.calendar):
        return _UNKNOWN
    endpoints = [dv.value]
    if q in _RANGE_QUALIFIERS:
        if not dv.value_to or not is_real_date(dv.value_to, dv.calendar):
            return _UNKNOWN
        endpoints.append(dv.value_to)
    if dv.calendar == "julian" and any(in_swedish_window(e) for e in endpoints):
        return _UNKNOWN
    try:
        start = _endpoint_span(dv.value, dv.calendar)
        end = _endpoint_span(dv.value_to, dv.calendar) if q in _RANGE_QUALIFIERS else start
    except (ValueError, OverflowError):
        return _UNKNOWN
    try:
        if q == "before":
            return DateBounds(None, start[0] - timedelta(days=1), True)
        if q == "after":
            return DateBounds(start[1] + timedelta(days=1), None, True)
    except OverflowError:
        return _UNKNOWN
    if q == "from":
        return DateBounds(start[0], None, True)
    if q == "to":
        return DateBounds(None, start[1], True)
    if q in _RANGE_QUALIFIERS:
        return DateBounds(start[0], end[1], True)
    return DateBounds(start[0], start[1], True)


# ---------------------------------------------------------------------------
# Formatting and sorting
# ---------------------------------------------------------------------------


def format_date_sv(dv: Optional[DateValue]) -> str:
    """Swedish text for a date, e.g. ``ca 1850`` or ``1700-02-15 (julianskt)``."""
    if dv is None:
        return ""
    q = effective_qualifier(dv)
    if q == "unparsed":
        return (dv.original_text or "").strip()
    if q in _RANGE_QUALIFIERS:
        if q == "between":
            text = f"mellan {dv.value} och {dv.value_to}"
        else:
            text = f"från {dv.value} till {dv.value_to}"
    else:
        text = _FORMAT_PREFIX.get(q, "") + (dv.value or "")
    text = text.strip()
    if dv.calendar == "julian" and text:
        text += " (julianskt)"
    return text


def sort_key(dv: Optional[DateValue]) -> tuple:
    """Sort key: known dates by start day (exact before non-exact on ties),
    open start first; unknown dates last."""
    b = date_bounds(dv)
    if not b.known:
        return (1, 0, 0, 0)
    start = (b.earliest or date.min).toordinal()
    end = (b.latest or date.max).toordinal()
    return (0, start, 0 if is_exact(dv) else 1, end)
