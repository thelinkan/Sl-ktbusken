"""Pure edit operations on Residence_Facts ("Boende").

Every function here is a pure function over its arguments: it reads the values
it is given, builds a new value, and mutates nothing. The Residence_Editor
collects input, calls one function from this module, and commits its result,
which keeps the edit semantics testable without a Qt event loop.

Pure module: no Qt, no I/O, no mutation.
"""

from __future__ import annotations

import re

# An Observation year is a bare four-digit year (ÅÅÅÅ) in this range
# (Requirements 4.1, 4.12).
MIN_OBSERVATION_YEAR = 1500
MAX_OBSERVATION_YEAR = 2100

# A Source ``years`` value we can read: one four-digit year, or two separated by
# a hyphen-minus or an en dash (U+2013) with any number of surrounding spaces
# (Requirements 4.7, 4.8). Any other separator — em dash, slash, the word
# "till" — is not a form we read.
_YEARS_RE = re.compile(r"^(\d{4})(?:\s*[-\u2013]\s*(\d{4}))?$")


def prefill_span_from_years(years: str | None) -> tuple[str, str] | None:
    """Read a Source ``years`` value as an Observation span suggestion.

    A single four-digit year in 1500–2100 yields that year for both bounds
    (Requirement 4.8); two such years separated by a hyphen or an en dash, with
    any surrounding spaces, yield the pair when they are in ascending order
    (Requirement 4.7). Equal years are read as that single year, matching the
    validator, which treats ``observed_from == observed_to`` as valid
    (Requirement 4.4).

    Everything else — absent, empty or whitespace-only, descending, out of
    range, more than two years, or any other text — yields ``None``, which is
    what drives the editor's "Kunde inte läsa årtal från källan – ange period
    manuellt." message (Requirement 4.9). The same reading serves the bulk
    paste candidates (Requirement 9.2).

    The suggestion is derived from the volume's coverage period and asserts
    nothing about the person's presence. Nothing is written back: the caller's
    ``years`` string is only read, so the Source keeps its own coverage period
    (Requirements 4.1, 4.10).

    Returns:
        ``(observed_from, observed_to)`` as four-digit year strings, or ``None``
        when the value holds no readable span.
    """
    if years is None:
        return None

    match = _YEARS_RE.match(years.strip())
    if match is None:
        return None

    first_text, second_text = match.group(1), match.group(2)
    if second_text is None:
        second_text = first_text

    first, second = int(first_text), int(second_text)
    if not _in_range(first) or not _in_range(second):
        return None
    if first > second:
        return None

    return first_text, second_text


def _in_range(year: int) -> bool:
    """True when the year falls inside the accepted Observation year range."""
    return MIN_OBSERVATION_YEAR <= year <= MAX_OBSERVATION_YEAR
