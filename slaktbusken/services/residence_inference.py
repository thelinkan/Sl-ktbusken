"""Inferred tightening of Residence_Fact endpoint bounds.

Computes derived endpoint bounds for a Residence_Fact from its person's other
Residence_Facts and birth/death Events, in a single pass over stored values
only. A derived bound is never an input to another derivation, and nothing is
mutated or persisted (Requirements 7.1, 7.2).

Candidates:
- *Neighbour candidate* for an absent ``start.earliest``: the latest stored
  ``end.earliest`` among facts at a different place whose value is earlier than
  this fact's ``start.latest`` (falling back to ``end.earliest`` when
  ``start.latest`` is absent) (Requirement 7.3).
- *Neighbour candidate* for an absent ``end.latest``: the earliest stored
  ``start.latest`` among facts at a different place whose value is later than
  this fact's ``end.earliest`` (falling back to ``start.latest`` when
  ``end.earliest`` is absent).
- *Birth candidate* for an absent ``start.earliest``: earliest birth date of the
  person (Requirement 7.4).
- *Death candidate* for an absent ``end.latest``: latest death date of the
  person (Requirement 7.5).

Competing candidates are resolved by widest-interval comparison: ``earliest``
bounds take the latest candidate (first day), ``latest`` bounds take the
earliest candidate (last day) — the winner is returned in its stored ISO form
(Requirement 7.6).

A candidate contradicting a stored bound of the same fact is dropped and
reported with the finding "Härlett värde motsäger inmatat värde."
(Requirement 7.12).

Because no candidate is formed for a bound that is already present, a second
invocation after a confirmed write is a no-op (Requirement 7.10).

Pure module: no Qt, no I/O, no mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from slaktbusken.model.date_span import expand_iso, strictly_earlier
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import ResidenceFact
from slaktbusken.services.residence_validation import ResidenceFinding


# ---------------------------------------------------------------------------
# Data records
# ---------------------------------------------------------------------------


@dataclass
class DerivedBound:
    """A single inferred bound value with its provenance."""

    residence_id: str
    endpoint: str       # "start" | "end"
    bound: str          # "earliest" | "latest"
    value: str          # ISO form as stored on the origin
    origin_kind: str    # "residence" | "event"
    origin_id: str
    origin_label: str   # neighbouring place name or Swedish event label


@dataclass
class InferenceResult:
    """The outcome of an inference pass over one Residence_Fact."""

    derived: list[DerivedBound] = field(default_factory=list)
    findings: list[ResidenceFinding] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Finding message
# ---------------------------------------------------------------------------

_MSG_CONTRADICTION = "Härlett värde motsäger inmatat värde."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BIRTH_TYPES = frozenset({"birth"})
_DEATH_TYPES = frozenset({"death"})


def _is_present(value: str | None) -> bool:
    """Whether a bound value counts as present (not None/empty/whitespace)."""
    return value is not None and bool(value.strip())


def _place_name(place_id: str, data: ProjectData) -> str:
    """Look up the display name of a place, falling back to its id."""
    for place in data.places:
        if place.id == place_id:
            return place.name
    return place_id


def _event_label(event_type: str) -> str:
    """Swedish label for a birth or death event type."""
    labels = {
        "birth": "Födelse",
        "death": "Död",
    }
    return labels.get(event_type, event_type)


def _candidate_contradicts_start_earliest(
    candidate_value: str, fact: ResidenceFact
) -> bool:
    """Whether a start.earliest candidate contradicts a stored bound.

    A start.earliest candidate contradicts if it is later than the stored
    start.latest or later than the stored end.latest (Requirement 7.12).
    """
    if _is_present(fact.start.latest):
        if strictly_earlier(fact.start.latest, candidate_value):
            return True
    if _is_present(fact.end.latest):
        if strictly_earlier(fact.end.latest, candidate_value):
            return True
    return False


def _candidate_contradicts_end_latest(
    candidate_value: str, fact: ResidenceFact
) -> bool:
    """Whether an end.latest candidate contradicts a stored bound.

    An end.latest candidate contradicts if it is earlier than the stored
    end.earliest or earlier than the stored start.earliest (Requirement 7.12).
    """
    if _is_present(fact.end.earliest):
        if strictly_earlier(candidate_value, fact.end.earliest):
            return True
    if _is_present(fact.start.earliest):
        if strictly_earlier(candidate_value, fact.start.earliest):
            return True
    return False


# ---------------------------------------------------------------------------
# Main inference function
# ---------------------------------------------------------------------------


def infer_bounds(fact: ResidenceFact, data: ProjectData) -> InferenceResult:
    """Compute derived endpoint bounds for *fact* without mutating anything.

    Returns an :class:`InferenceResult` holding the winning derived bounds and
    any contradiction findings. If a bound is already present on *fact*, no
    candidate is formed for it (Requirement 7.10).
    """
    result = InferenceResult()

    # Quick check: if all four bounds are present, nothing to derive.
    need_start_earliest = not _is_present(fact.start.earliest)
    need_end_latest = not _is_present(fact.end.latest)
    if not need_start_earliest and not need_end_latest:
        return result

    # -----------------------------------------------------------------------
    # Gather candidate values
    # -----------------------------------------------------------------------

    # Candidates are tuples: (iso_value, origin_kind, origin_id, origin_label)
    start_earliest_candidates: list[tuple[str, str, str, str]] = []
    end_latest_candidates: list[tuple[str, str, str, str]] = []

    # --- Neighbour candidates from other Residence_Facts of the same person ---
    # For start.earliest: latest stored end.earliest among facts at a different
    # place whose value is earlier than this fact's start.latest (or end.earliest
    # as fallback reference).
    # For end.latest: earliest stored start.latest among facts at a different
    # place whose value is later than this fact's end.earliest (or start.latest
    # as fallback reference).

    # Determine the reference value for neighbour comparison (start)
    if _is_present(fact.start.latest):
        start_ref = fact.start.latest
    elif _is_present(fact.end.earliest):
        start_ref = fact.end.earliest
    else:
        start_ref = None

    # Determine the reference value for neighbour comparison (end)
    if _is_present(fact.end.earliest):
        end_ref = fact.end.earliest
    elif _is_present(fact.start.latest):
        end_ref = fact.start.latest
    else:
        end_ref = None

    # Scan all residence facts for the same person
    for other in data.residences:
        if other.id == fact.id:
            continue
        if other.person_id != fact.person_id:
            continue
        if other.place_id == fact.place_id:
            continue

        # Neighbour candidate for start.earliest
        if need_start_earliest and start_ref is not None:
            end_earliest_val = other.end.earliest
            if _is_present(end_earliest_val):
                # Must be earlier than the reference
                if strictly_earlier(end_earliest_val, start_ref):
                    start_earliest_candidates.append((
                        end_earliest_val.strip(),  # type: ignore[union-attr]
                        "residence",
                        other.id,
                        _place_name(other.place_id, data),
                    ))

        # Neighbour candidate for end.latest
        if need_end_latest and end_ref is not None:
            start_latest_val = other.start.latest
            if _is_present(start_latest_val):
                # Must be later than the reference
                if strictly_earlier(end_ref, start_latest_val):
                    end_latest_candidates.append((
                        start_latest_val.strip(),  # type: ignore[union-attr]
                        "residence",
                        other.id,
                        _place_name(other.place_id, data),
                    ))

    # --- Birth candidate for start.earliest (Requirement 7.4) ---
    if need_start_earliest:
        birth_dates: list[tuple[str, str]] = []  # (iso_value, event_id)
        for event in data.events:
            if event.type not in _BIRTH_TYPES:
                continue
            if event.date is None or not _is_present(event.date.value):
                continue
            # Check if this person participates in the birth event
            for p in event.participants:
                if p.person_id == fact.person_id:
                    birth_dates.append((event.date.value.strip(), event.id))
                    break

        if birth_dates:
            # Take the earliest birth date (by first day comparison)
            best_birth = min(
                birth_dates,
                key=lambda bd: expand_iso(bd[0]).first  # type: ignore[union-attr]
            )
            start_earliest_candidates.append((
                best_birth[0],
                "event",
                best_birth[1],
                _event_label("birth"),
            ))

    # --- Death candidate for end.latest (Requirement 7.5) ---
    if need_end_latest:
        death_dates: list[tuple[str, str]] = []  # (iso_value, event_id)
        for event in data.events:
            if event.type not in _DEATH_TYPES:
                continue
            if event.date is None or not _is_present(event.date.value):
                continue
            for p in event.participants:
                if p.person_id == fact.person_id:
                    death_dates.append((event.date.value.strip(), event.id))
                    break

        if death_dates:
            # Take the latest death date (by last day comparison)
            best_death = max(
                death_dates,
                key=lambda dd: expand_iso(dd[0]).last  # type: ignore[union-attr]
            )
            end_latest_candidates.append((
                best_death[0],
                "event",
                best_death[1],
                _event_label("death"),
            ))

    # -----------------------------------------------------------------------
    # Resolve competing candidates (Requirement 7.6)
    # -----------------------------------------------------------------------

    # For start.earliest: take the *latest* candidate (widest interval ⇒
    # the one with the latest first day).
    if start_earliest_candidates:
        winner = max(
            start_earliest_candidates,
            key=lambda c: expand_iso(c[0]).first  # type: ignore[union-attr]
        )

        # Check contradiction (Requirement 7.12)
        if _candidate_contradicts_start_earliest(winner[0], fact):
            result.findings.append(ResidenceFinding(
                residence_id=fact.id,
                person_id=fact.person_id,
                severity="warning",
                message=_MSG_CONTRADICTION,
            ))
        else:
            result.derived.append(DerivedBound(
                residence_id=fact.id,
                endpoint="start",
                bound="earliest",
                value=winner[0],
                origin_kind=winner[1],
                origin_id=winner[2],
                origin_label=winner[3],
            ))

    # For end.latest: take the *earliest* candidate (widest interval ⇒
    # the one with the earliest last day).
    if end_latest_candidates:
        winner = min(
            end_latest_candidates,
            key=lambda c: expand_iso(c[0]).last  # type: ignore[union-attr]
        )

        # Check contradiction (Requirement 7.12)
        if _candidate_contradicts_end_latest(winner[0], fact):
            result.findings.append(ResidenceFinding(
                residence_id=fact.id,
                person_id=fact.person_id,
                severity="warning",
                message=_MSG_CONTRADICTION,
            ))
        else:
            result.derived.append(DerivedBound(
                residence_id=fact.id,
                endpoint="end",
                bound="latest",
                value=winner[0],
                origin_kind=winner[1],
                origin_id=winner[2],
                origin_label=winner[3],
            ))

    return result
