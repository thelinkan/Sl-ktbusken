"""Day-interval algebra for ISO 8601 date values.

Residence endpoints compare dates by the closed day interval each ISO value
denotes: a value A is earlier than a value B only when the last day of A
precedes the first day of B (Requirement 2.15). This differs from
``services/checks/date_utils.compare_dates``, which compares at the coarser
common precision, so this module is kept separate and is the single source of
truth for every bound comparison, core/span derivation and overlap test in the
residence feature.

A value that is absent, empty or whitespace-only counts as absent throughout
(Requirement 2.1); every reader funnels through :func:`expand_iso`, which trims
first.

Pure module: no Qt, no I/O, no model imports.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional


# ÅÅÅÅ, ÅÅÅÅ-MM or ÅÅÅÅ-MM-DD
_ISO_DATE_RE = re.compile(r"^\d{4}(?:-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?)?$")


@dataclass(frozen=True)
class DaySpan:
    """The closed day interval an ISO 8601 value denotes."""

    first: date
    last: date


@dataclass(frozen=True)
class OpenSpan:
    """A day interval whose absent bound means unbounded in that direction."""

    first: Optional[date] = None
    last: Optional[date] = None

    def contains_year(self, year: int) -> bool:
        """Whether every day of *year* falls inside this span."""
        span = year_span(year)
        if self.first is not None and self.first > span.first:
            return False
        if self.last is not None and self.last < span.last:
            return False
        return True

    def overlaps_year(self, year: int) -> bool:
        """Whether at least one day of *year* falls inside this span."""
        span = year_span(year)
        if self.first is not None and self.first > span.last:
            return False
        if self.last is not None and self.last < span.first:
            return False
        return True

    def is_unbounded_both(self) -> bool:
        """Whether the span is unbounded in both directions."""
        return self.first is None and self.last is None


def is_valid_iso(value: Optional[str]) -> bool:
    """Whether *value* is one of the forms ÅÅÅÅ, ÅÅÅÅ-MM or ÅÅÅÅ-MM-DD.

    Absent values (``None``, empty, whitespace-only) are not valid values; use
    :func:`expand_iso` to tell absent from malformed. A day that does not exist
    in its month, such as ``1840-02-30``, is not a valid ISO 8601 date and is
    rejected.
    """
    if value is None:
        return False
    trimmed = value.strip()
    if not trimmed:
        return False
    if not _ISO_DATE_RE.match(trimmed):
        return False
    parts = trimmed.split("-")
    if len(parts) == 3:
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        if day > calendar.monthrange(year, month)[1]:
            return False
    return True


def expand_iso(value: Optional[str]) -> Optional[DaySpan]:
    """Expand an ISO 8601 value to the closed day interval it denotes.

    ÅÅÅÅ spans 1 January through 31 December of that year, ÅÅÅÅ-MM spans the
    first through the last day of that month, and ÅÅÅÅ-MM-DD spans that single
    day. Returns ``None`` for absent (``None``, empty, whitespace-only) or
    malformed values.
    """
    if not is_valid_iso(value):
        return None

    trimmed = value.strip()  # type: ignore[union-attr]  # is_valid_iso rejects None
    parts = trimmed.split("-")
    year = int(parts[0])

    if len(parts) == 1:
        return DaySpan(date(year, 1, 1), date(year, 12, 31))

    month = int(parts[1])
    if len(parts) == 2:
        last_day = calendar.monthrange(year, month)[1]
        return DaySpan(date(year, month, 1), date(year, month, last_day))

    day = int(parts[2])
    single = date(year, month, day)
    return DaySpan(single, single)


def strictly_earlier(a: Optional[str], b: Optional[str]) -> bool:
    """Whether *a* is earlier than *b* under Requirement 2.15.

    True only when the last day of *a* precedes the first day of *b*, so
    "1840" is neither earlier nor later than "1840-06". An absent or malformed
    value on either side yields ``False``.
    """
    span_a = expand_iso(a)
    span_b = expand_iso(b)
    if span_a is None or span_b is None:
        return False
    return span_a.last < span_b.first


def year_of(value: Optional[str]) -> Optional[int]:
    """The year part of an ISO 8601 value, or ``None`` when absent or malformed."""
    span = expand_iso(value)
    if span is None:
        return None
    return span.first.year


def precision_of(value: Optional[str]) -> Optional[str]:
    """The precision an ISO 8601 value carries: "year", "month" or "day".

    Returns ``None`` for absent or malformed values.
    """
    if not is_valid_iso(value):
        return None
    trimmed = value.strip()  # type: ignore[union-attr]  # is_valid_iso rejects None
    return {1: "year", 2: "month", 3: "day"}[len(trimmed.split("-"))]


def overlaps(a: DaySpan, b: DaySpan) -> bool:
    """Whether two day intervals share at least one day."""
    return a.first <= b.last and b.first <= a.last


def intersect(a: DaySpan, b: DaySpan) -> Optional[DaySpan]:
    """The shared day interval of *a* and *b*, or ``None`` when they are disjoint."""
    if not overlaps(a, b):
        return None
    return DaySpan(max(a.first, b.first), min(a.last, b.last))


def year_span(year: int) -> DaySpan:
    """The day interval covering the whole calendar *year*."""
    return DaySpan(date(year, 1, 1), date(year, 12, 31))
