"""Pure edit operations on Residence_Facts ("Boende").

Every function here is a pure function over its arguments: it reads the values
it is given, builds a new value, and mutates nothing. The Residence_Editor
collects input, calls one function from this module, and commits its result,
which keeps the edit semantics testable without a Qt event loop.

Pure module: no Qt, no I/O, no mutation.
"""

from __future__ import annotations

import copy
import re
from typing import Sequence

from slaktbusken.model.residence import (
    Endpoint,
    Observation,
    ResidenceFact,
    core_aggregate,
)

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


def attach_observations(
    fact: ResidenceFact,
    new_obs: Sequence[Observation],
) -> ResidenceFact:
    """Append *new_obs* to *fact* and tighten the documented core.

    The new Observations are appended in order after those already present
    (Requirement 4.3). The documented core is tightened only:

    - ``start.latest`` becomes the lowest ``observed_from`` among **all** the
      Observations (existing + new) when the stored value is absent or later
      (Requirement 16.4).
    - ``end.earliest`` becomes the highest ``observed_to`` among **all** the
      Observations (existing + new) when the stored value is absent or earlier
      (Requirement 16.4).
    - ``start.earliest`` and ``end.latest`` are **never** touched
      (Requirement 16.3).

    *fact* and every element of *new_obs* are left unchanged. A new
    :class:`ResidenceFact` is returned.

    Requirements: 4.3, 9.5, 16.3, 16.4.
    """
    # Build the combined Observations list (existing + new, in order).
    combined_obs = list(fact.observations) + list(new_obs)

    # Compute the aggregate over the combined set.
    agg_from, agg_to = core_aggregate(combined_obs)

    # Tighten start.latest: use aggregate when absent or looser (later year).
    new_start_latest = _tighten_start_latest(fact.start.latest, agg_from)

    # Tighten end.earliest: use aggregate when absent or looser (earlier year).
    new_end_earliest = _tighten_end_earliest(fact.end.earliest, agg_to)

    # Build the result — a fresh ResidenceFact that shares no mutable state.
    new_start = Endpoint(
        earliest=fact.start.earliest,
        latest=new_start_latest,
        precision=fact.start.precision,
        event_id=fact.start.event_id,
        note=fact.start.note,
    )
    new_end = Endpoint(
        earliest=new_end_earliest,
        latest=fact.end.latest,
        precision=fact.end.precision,
        event_id=fact.end.event_id,
        note=fact.end.note,
    )

    return ResidenceFact(
        id=fact.id,
        person_id=fact.person_id,
        place_id=fact.place_id,
        start=new_start,
        end=new_end,
        role_in_household=fact.role_in_household,
        observations=combined_obs,
        notes=fact.notes,
    )


def remove_observation(fact: ResidenceFact, index: int) -> ResidenceFact:
    """Remove the Observation at *index* from *fact*.

    Survivors keep their byte-identical values and relative order
    (Requirement 4.3). The documented core bounds are recomputed only when the
    stored value equals the aggregate over the **pre-removal** Observation set
    (design decision 3, Requirement 16.7). A hand-entered bound — one that
    differs from the pre-removal aggregate — survives unchanged
    (Requirement 16.8).

    ``start.earliest`` and ``end.latest`` are **never** touched
    (Requirement 16.3).

    *fact* is left unchanged. A new :class:`ResidenceFact` is returned.

    Raises:
        IndexError: when *index* is out of range.

    Requirements: 4.3, 16.3, 16.7, 16.8.
    """
    if index < 0 or index >= len(fact.observations):
        raise IndexError(f"Observation index {index} out of range")

    # The aggregate over the *pre-removal* set determines provenance.
    pre_agg_from, pre_agg_to = core_aggregate(fact.observations)

    # Build survivors in relative order, each a deep copy so they are
    # byte-identical but share no mutable state with the original.
    survivors = [
        copy.deepcopy(obs)
        for i, obs in enumerate(fact.observations)
        if i != index
    ]

    # Decide whether each core bound should be recomputed.
    # A bound counts as observation-derived when its stored value equals the
    # pre-removal aggregate; otherwise it is hand-entered and stays unchanged.
    stored_start_latest = fact.start.latest
    stored_end_earliest = fact.end.earliest

    if _values_equal(stored_start_latest, pre_agg_from):
        # Observation-derived → recompute from survivors.
        post_agg_from, _ = core_aggregate(survivors)
        new_start_latest = post_agg_from
    else:
        # Hand-entered → keep unchanged.
        new_start_latest = stored_start_latest

    if _values_equal(stored_end_earliest, pre_agg_to):
        # Observation-derived → recompute from survivors.
        _, post_agg_to = core_aggregate(survivors)
        new_end_earliest = post_agg_to
    else:
        # Hand-entered → keep unchanged.
        new_end_earliest = stored_end_earliest

    new_start = Endpoint(
        earliest=fact.start.earliest,
        latest=new_start_latest,
        precision=fact.start.precision,
        event_id=fact.start.event_id,
        note=fact.start.note,
    )
    new_end = Endpoint(
        earliest=new_end_earliest,
        latest=fact.end.latest,
        precision=fact.end.precision,
        event_id=fact.end.event_id,
        note=fact.end.note,
    )

    return ResidenceFact(
        id=fact.id,
        person_id=fact.person_id,
        place_id=fact.place_id,
        start=new_start,
        end=new_end,
        role_in_household=fact.role_in_household,
        observations=survivors,
        notes=fact.notes,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _tighten_start_latest(
    stored: str | None,
    aggregate_from: str | None,
) -> str | None:
    """Return the tighter value for ``start.latest``.

    The aggregate (lowest ``observed_from``) is used when the stored value is
    absent or *later* (a later year is looser for a start bound — we want the
    earliest documented start).
    """
    if aggregate_from is None:
        return stored
    if stored is None or stored.strip() == "":
        return aggregate_from
    # Both present — use the earlier (numerically lower) year.
    try:
        stored_year = int(stored.strip())
        agg_year = int(aggregate_from.strip())
    except ValueError:
        # Stored is not a plain year (could be ÅÅÅÅ-MM or ÅÅÅÅ-MM-DD).
        # Compare as strings; the aggregate is always a plain 4-digit year.
        # A stored ISO value of finer precision keeps its form when it is
        # earlier or equal; otherwise the aggregate replaces it.
        from slaktbusken.model.date_span import expand_iso

        stored_span = expand_iso(stored)
        agg_span = expand_iso(aggregate_from)
        if stored_span is None:
            return aggregate_from
        if agg_span is None:
            return stored
        # "Earlier" for start.latest means the first day is earlier or equal.
        if stored_span.first <= agg_span.first:
            return stored
        return aggregate_from

    if stored_year <= agg_year:
        return stored
    return aggregate_from


def _tighten_end_earliest(
    stored: str | None,
    aggregate_to: str | None,
) -> str | None:
    """Return the tighter value for ``end.earliest``.

    The aggregate (highest ``observed_to``) is used when the stored value is
    absent or *earlier* (an earlier year is looser for an end bound — we want
    the latest documented end).
    """
    if aggregate_to is None:
        return stored
    if stored is None or stored.strip() == "":
        return aggregate_to
    # Both present — use the later (numerically higher) year.
    try:
        stored_year = int(stored.strip())
        agg_year = int(aggregate_to.strip())
    except ValueError:
        from slaktbusken.model.date_span import expand_iso

        stored_span = expand_iso(stored)
        agg_span = expand_iso(aggregate_to)
        if stored_span is None:
            return aggregate_to
        if agg_span is None:
            return stored
        # "Later" for end.earliest means the last day is later or equal.
        if stored_span.last >= agg_span.last:
            return stored
        return aggregate_to

    if stored_year >= agg_year:
        return stored
    return aggregate_to


def _values_equal(stored: str | None, aggregate: str | None) -> bool:
    """Whether the stored value equals the aggregate (both as trimmed strings).

    Design decision 3: a bound is observation-derived exactly when its stored
    value equals the aggregate over the Observation set. The comparison is on
    the stored string form — a four-digit year — since ``core_aggregate``
    always returns four-digit years or ``None``.
    """
    if stored is None and aggregate is None:
        return True
    if stored is None or aggregate is None:
        return False
    return stored.strip() == aggregate.strip()
