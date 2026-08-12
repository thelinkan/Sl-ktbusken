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
    observation_span_years,
)
from slaktbusken.services.residence_coverage import CoverageGap

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


def use_as_exact_start(fact: ResidenceFact, obs: Observation) -> ResidenceFact:
    """Set the start Endpoint to an exact date from an Observation.

    Sets both ``start.earliest`` and ``start.latest`` to ``obs.observed_from``,
    making the start an exact date derived from the Observation. All other
    fields of the Residence_Fact — including ``end.earliest``, ``end.latest``,
    the start ``precision``, ``event_id``, ``note``, and the Observations
    list — stay unchanged.

    This is the only route by which an Observation value reaches an outer bound.
    It is never invoked automatically; the user must explicitly choose
    "Använd som exakt början" (Requirement 16.11).

    *fact* and *obs* are left unchanged. A new :class:`ResidenceFact` is
    returned.

    Requirements: 16.10, 16.11.
    """
    new_start = Endpoint(
        earliest=obs.observed_from,
        latest=obs.observed_from,
        precision=fact.start.precision,
        event_id=fact.start.event_id,
        note=fact.start.note,
    )

    return ResidenceFact(
        id=fact.id,
        person_id=fact.person_id,
        place_id=fact.place_id,
        start=new_start,
        end=Endpoint(
            earliest=fact.end.earliest,
            latest=fact.end.latest,
            precision=fact.end.precision,
            event_id=fact.end.event_id,
            note=fact.end.note,
        ),
        role_in_household=fact.role_in_household,
        observations=list(fact.observations),
        notes=fact.notes,
    )


def use_as_exact_end(fact: ResidenceFact, obs: Observation) -> ResidenceFact:
    """Set the end Endpoint to an exact date from an Observation.

    Sets both ``end.earliest`` and ``end.latest`` to ``obs.observed_to``,
    making the end an exact date derived from the Observation. All other
    fields of the Residence_Fact — including ``start.earliest``,
    ``start.latest``, the end ``precision``, ``event_id``, ``note``, and the
    Observations list — stay unchanged.

    This is the only route by which an Observation value reaches an outer bound.
    It is never invoked automatically; the user must explicitly choose
    "Använd som exakt slut" (Requirement 16.11).

    *fact* and *obs* are left unchanged. A new :class:`ResidenceFact` is
    returned.

    Requirements: 16.10, 16.11.
    """
    new_end = Endpoint(
        earliest=obs.observed_to,
        latest=obs.observed_to,
        precision=fact.end.precision,
        event_id=fact.end.event_id,
        note=fact.end.note,
    )

    return ResidenceFact(
        id=fact.id,
        person_id=fact.person_id,
        place_id=fact.place_id,
        start=Endpoint(
            earliest=fact.start.earliest,
            latest=fact.start.latest,
            precision=fact.start.precision,
            event_id=fact.start.event_id,
            note=fact.start.note,
        ),
        end=new_end,
        role_in_household=fact.role_in_household,
        observations=list(fact.observations),
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


class ResidenceSplitError(Exception):
    """Raised when a Residence_Fact cannot be split at a gap.

    The split requires at least one Observation on each side of the gap
    (Requirement 5.16). When one side has no Observation, the split is
    impossible and this error is raised with a message indicating that the
    boende cannot be split because observations exist on only one side of
    the period.
    """


class ResidenceMergeError(Exception):
    """Raised when two Residence_Facts cannot be merged.

    The merge requires equal ``person_id`` and equal ``place_id``
    (Requirements 17.7, 17.8). When they differ, this error is raised with
    the appropriate Swedish message.
    """


def split_at_gap(
    fact: ResidenceFact,
    gap: CoverageGap,
    new_ids: tuple[str, str],
) -> tuple[ResidenceFact, ResidenceFact]:
    """Split *fact* at a coverage *gap*, yielding two new Residence_Facts.

    Observations whose last covered year (``observed_to``) is earlier than the
    gap's first uncovered year are assigned to the first fact; those whose first
    covered year (``observed_from``) is later than the gap's last uncovered year
    are assigned to the second fact (Requirement 5.11). Observations that cannot
    be classified (both bounds absent or malformed) are dropped from the split
    result — the requirement only defines assignment for those ending before and
    beginning after the gap.

    Both resulting facts get new ``id`` values from *new_ids*. Both receive
    copies of ``person_id``, ``place_id``, ``role_in_household`` and ``notes``
    from the original fact (Requirement 5.12).

    The original ``start`` is kept on the first fact and the original ``end``
    on the second (Requirement 5.12). The first fact's ``end.earliest`` is set
    to its highest ``observed_to`` (from ``core_aggregate``), and the second
    fact's ``start.latest`` is set to its lowest ``observed_from`` (from
    ``core_aggregate``). The first fact's ``end.latest`` and the second fact's
    ``start.earliest`` are left absent (Requirement 5.13).

    Raises:
        ResidenceSplitError: when one side of the gap has no Observation
            (Requirement 5.16).

    *fact* and *gap* are left unchanged. Two new :class:`ResidenceFact` values
    are returned.

    Requirements: 5.10, 5.11, 5.12, 5.13, 5.16.
    """
    # Partition Observations by the gap.
    before_gap: list[Observation] = []
    after_gap: list[Observation] = []

    for obs in fact.observations:
        span = observation_span_years(obs)
        if span is None:
            # Cannot classify — skip (no years to compare against the gap)
            continue
        span_first, span_last = span
        if span_last < gap.first_year:
            before_gap.append(copy.deepcopy(obs))
        elif span_first > gap.last_year:
            after_gap.append(copy.deepcopy(obs))
        # Observations that overlap the gap boundary are not defined in the
        # requirement to go to either side; skip them.

    # Requirement 5.16: raise when one side has no Observation.
    if not before_gap or not after_gap:
        raise ResidenceSplitError(
            "Boendet kan inte delas eftersom observationer "
            "bara finns på en sida av perioden."
        )

    # Compute the core aggregates for each side.
    _, first_highest_to = core_aggregate(before_gap)
    second_lowest_from, _ = core_aggregate(after_gap)

    # Build the first fact: keeps original start, new end with end.earliest
    # from its observations and end.latest absent.
    first_end = Endpoint(
        earliest=first_highest_to,
        latest=None,
        precision=None,
        event_id=None,
        note=None,
    )
    first_fact = ResidenceFact(
        id=new_ids[0],
        person_id=fact.person_id,
        place_id=fact.place_id,
        start=Endpoint(
            earliest=fact.start.earliest,
            latest=fact.start.latest,
            precision=fact.start.precision,
            event_id=fact.start.event_id,
            note=fact.start.note,
        ),
        end=first_end,
        role_in_household=fact.role_in_household,
        observations=before_gap,
        notes=fact.notes,
    )

    # Build the second fact: keeps original end, new start with start.latest
    # from its observations and start.earliest absent.
    second_start = Endpoint(
        earliest=None,
        latest=second_lowest_from,
        precision=None,
        event_id=None,
        note=None,
    )
    second_fact = ResidenceFact(
        id=new_ids[1],
        person_id=fact.person_id,
        place_id=fact.place_id,
        start=second_start,
        end=Endpoint(
            earliest=fact.end.earliest,
            latest=fact.end.latest,
            precision=fact.end.precision,
            event_id=fact.end.event_id,
            note=fact.end.note,
        ),
        role_in_household=fact.role_in_household,
        observations=after_gap,
        notes=fact.notes,
    )

    return (first_fact, second_fact)


def merge(
    first: ResidenceFact,
    second: ResidenceFact,
    new_id: str,
) -> tuple[ResidenceFact, str | None]:
    """Merge two Residence_Facts into one, returning the merged fact and an optional warning.

    The two facts must share the same ``person_id`` and ``place_id``; otherwise
    :exc:`ResidenceMergeError` is raised (Requirements 17.7, 17.8).

    The fact that sorts first under the same total order as
    :func:`~slaktbusken.services.residence_query.residence_timeline` — that is,
    by ``start.earliest``, ``start.latest``, ``end.earliest``, ``end.latest``
    with absent sorting before any present value, then place name, then ``id``
    — provides the merged fact's ``start`` Endpoint; the other provides the
    ``end`` Endpoint. All five Endpoint fields (``earliest``, ``latest``,
    ``precision``, ``event_id``, ``note``) carry over unchanged
    (Requirement 17.2).

    Observations from both facts are unioned and sorted by ``observed_from``
    ascending, with none discarded (Requirement 17.3).

    The earlier fact's ``role_in_household`` becomes the merged fact's role. If
    the other fact's role is non-empty and differs, the text
    "Tidigare roll i hushållet vid sammanslagning: {other_role}" is appended to
    the merged fact's ``notes`` (Requirement 17.4).

    Both facts' ``notes`` texts are retained: the earlier fact's notes come
    first, the other's is appended separated by a newline when non-empty
    (Requirement 17.5).

    The merged fact receives *new_id* as its ``id`` (Requirement 17.6).

    ``start.latest`` and ``end.earliest`` are re-derived via
    :func:`~slaktbusken.model.residence.core_aggregate` over the combined
    observations (Requirement 17.11); ``start.earliest`` and ``end.latest``
    stay as carried over from the respective Endpoints.

    A warning string is returned when the gap between the earlier fact's last
    ``observed_to`` and the later fact's first ``observed_from`` exceeds 10
    whole years (Requirement 17.10); otherwise ``None``.

    *first*, *second* and their contents are left unchanged. A new
    :class:`ResidenceFact` is returned together with the optional warning.

    Returns:
        ``(merged_fact, warning)`` where *warning* is either a Swedish string
        or ``None``.

    Raises:
        ResidenceMergeError: when ``person_id`` or ``place_id`` differ.

    Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.10, 17.11, 17.15.
    """
    # --- Refuse on different person or place (17.7, 17.8) ---
    if first.person_id != second.person_id:
        raise ResidenceMergeError(
            "Endast boenden för samma person kan slås samman."
        )
    if first.place_id != second.place_id:
        raise ResidenceMergeError(
            "Endast boenden på samma plats kan slås samman."
        )

    # --- Determine timeline order (17.2) ---
    # Use the same sort key as residence_timeline: absent sorts before present.
    earlier, later = _timeline_order(first, second)

    # --- Union observations ordered by observed_from ascending (17.3) ---
    combined_obs = sorted(
        [copy.deepcopy(obs) for obs in earlier.observations]
        + [copy.deepcopy(obs) for obs in later.observations],
        key=lambda obs: _absent_first_obs_key(obs.observed_from),
    )

    # --- Role handling (17.4) ---
    merged_role = earlier.role_in_household
    role_note_addition = ""
    if (
        later.role_in_household
        and later.role_in_household != earlier.role_in_household
    ):
        role_note_addition = (
            f"Tidigare roll i hushållet vid sammanslagning: "
            f"{later.role_in_household}"
        )

    # --- Notes handling (17.5) ---
    notes_parts: list[str] = []
    if earlier.notes:
        notes_parts.append(earlier.notes)
    if later.notes:
        notes_parts.append(later.notes)
    if role_note_addition:
        notes_parts.append(role_note_addition)
    merged_notes = "\n".join(notes_parts)

    # --- Re-derive core bounds from combined observations (17.11) ---
    agg_from, agg_to = core_aggregate(combined_obs)

    # Build Endpoints: start from earlier, end from later, but with
    # start.latest and end.earliest re-derived from the observations.
    merged_start = Endpoint(
        earliest=earlier.start.earliest,
        latest=agg_from if agg_from is not None else earlier.start.latest,
        precision=earlier.start.precision,
        event_id=earlier.start.event_id,
        note=earlier.start.note,
    )
    merged_end = Endpoint(
        earliest=agg_to if agg_to is not None else later.end.earliest,
        latest=later.end.latest,
        precision=later.end.precision,
        event_id=later.end.event_id,
        note=later.end.note,
    )

    # --- Build merged fact (17.6) ---
    merged_fact = ResidenceFact(
        id=new_id,
        person_id=earlier.person_id,
        place_id=earlier.place_id,
        start=merged_start,
        end=merged_end,
        role_in_household=merged_role,
        observations=combined_obs,
        notes=merged_notes,
    )

    # --- Compute >10-year separation warning (17.10) ---
    warning = _separation_warning(earlier, later)

    return (merged_fact, warning)


def _timeline_order(
    a: ResidenceFact, b: ResidenceFact
) -> tuple[ResidenceFact, ResidenceFact]:
    """Return (earlier, later) under the residence_timeline sort order.

    The sort key mirrors residence_timeline: start.earliest, start.latest,
    end.earliest, end.latest — each with absent sorting before present — then
    id as the final tiebreaker (place name is not applicable here since both
    facts share the same place_id for a valid merge).
    """
    def _key(fact: ResidenceFact) -> tuple:
        return (
            _absent_first_key(fact.start.earliest),
            _absent_first_key(fact.start.latest),
            _absent_first_key(fact.end.earliest),
            _absent_first_key(fact.end.latest),
            fact.id,
        )

    if _key(a) <= _key(b):
        return (a, b)
    return (b, a)


def _absent_first_key(value: str | None) -> tuple[int, str]:
    """A sort key placing absent (None/empty/whitespace) before present."""
    if value is None or not value.strip():
        return (0, "")
    return (1, value.strip())


def _absent_first_obs_key(value: str) -> tuple[int, str]:
    """A sort key for observation years, with empty sorting first."""
    if not value or not value.strip():
        return (0, "")
    return (1, value.strip())


def _separation_warning(
    earlier: ResidenceFact, later: ResidenceFact
) -> str | None:
    """Return a warning when the gap between the two facts exceeds 10 years.

    The gap is measured from the earlier fact's highest ``observed_to`` to the
    later fact's lowest ``observed_from``. If both are present as valid years
    and the difference exceeds 10, a warning is returned.
    """
    # Find the earlier fact's last observed_to
    earlier_last_to: int | None = None
    for obs in earlier.observations:
        year = _obs_year(obs.observed_to)
        if year is not None:
            if earlier_last_to is None or year > earlier_last_to:
                earlier_last_to = year

    # Find the later fact's first observed_from
    later_first_from: int | None = None
    for obs in later.observations:
        year = _obs_year(obs.observed_from)
        if year is not None:
            if later_first_from is None or year < later_first_from:
                later_first_from = year

    if earlier_last_to is None or later_first_from is None:
        return None

    separation = later_first_from - earlier_last_to
    if separation > 10:
        return (
            "Perioderna ligger långt ifrån varandra "
            "– kontrollera att det är samma boende."
        )
    return None


def _obs_year(value: str) -> int | None:
    """Parse an observation year string to an int, or None if invalid/empty."""
    if not value or not value.strip():
        return None
    stripped = value.strip()
    if len(stripped) == 4 and stripped.isdigit():
        return int(stripped)
    return None


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
