"""Warning-level findings for Residence_Facts.

This module mirrors ``source_validation.py`` in the service layer: errors stay in
``model/validators.py`` (as ``list[str]``), while this module returns
:class:`ResidenceFinding` records carrying severity. It covers:

- Single-fact warnings: start/end window overlap (2.17), duplicate source on one
  fact (4.13), evidence outside the recorded period (16.9).
- Cross-fact overlap analysis: same-person unordered pairs whose Certain_Cores
  overlap at the coarser core precision (6.2–6.8).
- Flytt link consistency: a Flytt_Event linked to two Residence_Facts whose
  places don't match (18.10).

Pure module: no Qt, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from slaktbusken.model.date_span import (
    DaySpan,
    expand_iso,
    precision_of,
    strictly_earlier,
)
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import (
    Endpoint,
    ResidenceFact,
    certain_core,
)
from slaktbusken.ui.swedish_locale import (
    RESIDENCE_INTERVAL_DASH,
    format_residence_endpoint,
)


# ---------------------------------------------------------------------------
# Data record
# ---------------------------------------------------------------------------


@dataclass
class ResidenceFinding:
    """A warning-level finding about one or two Residence_Facts."""

    residence_id: str
    person_id: str
    severity: str  # "warning"
    message: str
    other_residence_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Messages (exact Swedish wording from requirements)
# ---------------------------------------------------------------------------

_MSG_WINDOW_OVERLAP = (
    "Boendets start- och slutfönster överlappar "
    "\u2013 ingen dokumenterad kärnperiod."
)

_MSG_DUPLICATE_SOURCE = "Samma källa är kopplad till boendet mer än en gång."

_MSG_EVIDENCE_OUTSIDE = (
    "Källan styrker närvaro utanför den angivna perioden "
    "\u2013 utöka perioden om du vill."
)

_MSG_FLYTT_LINK_MISMATCH = (
    "Flyttens platser stämmer inte med de kopplade boendena."
)


# ---------------------------------------------------------------------------
# Single-fact findings
# ---------------------------------------------------------------------------


def residence_findings(
    fact: ResidenceFact, data: ProjectData
) -> list[ResidenceFinding]:
    """Return warning-level findings for a single Residence_Fact.

    Checks:
    - Start/end window overlap (Requirement 2.17): ``start.latest`` and
      ``end.earliest`` are both present but the core is empty because
      ``start.latest.last > end.earliest.first``.
    - Duplicate source on one fact (Requirement 4.13): two or more Observations
      carry the same ``source_ref.source_id``.
    - Evidence outside the recorded period (Requirement 16.9): an Observation's
      ``observed_from`` is earlier than ``start.earliest``, or ``observed_to``
      is later than ``end.latest``.
    """
    findings: list[ResidenceFinding] = []

    # --- 2.17: start/end window overlap ---
    start_latest = expand_iso(fact.start.latest)
    end_earliest = expand_iso(fact.end.earliest)
    if (
        start_latest is not None
        and end_earliest is not None
        and start_latest.last > end_earliest.first
    ):
        findings.append(
            ResidenceFinding(
                residence_id=fact.id,
                person_id=fact.person_id,
                severity="warning",
                message=_MSG_WINDOW_OVERLAP,
            )
        )

    # --- 4.13: duplicate source ---
    seen_sources: set[str] = set()
    has_duplicate = False
    for obs in fact.observations:
        sid = obs.source_ref.source_id
        if sid in seen_sources:
            has_duplicate = True
            break
        seen_sources.add(sid)
    if has_duplicate:
        findings.append(
            ResidenceFinding(
                residence_id=fact.id,
                person_id=fact.person_id,
                severity="warning",
                message=_MSG_DUPLICATE_SOURCE,
            )
        )

    # --- 16.9: evidence outside the recorded period ---
    start_earliest = expand_iso(fact.start.earliest)
    end_latest_span = expand_iso(fact.end.latest)

    for obs in fact.observations:
        outside = False
        # Check observed_from earlier than start.earliest
        if start_earliest is not None and obs.observed_from.strip():
            obs_from = expand_iso(obs.observed_from.strip())
            if obs_from is not None and obs_from.first < start_earliest.first:
                outside = True
        # Check observed_to later than end.latest
        if end_latest_span is not None and obs.observed_to.strip():
            obs_to = expand_iso(obs.observed_to.strip())
            if obs_to is not None and obs_to.last > end_latest_span.last:
                outside = True
        if outside:
            findings.append(
                ResidenceFinding(
                    residence_id=fact.id,
                    person_id=fact.person_id,
                    severity="warning",
                    message=_MSG_EVIDENCE_OUTSIDE,
                )
            )
            break  # One finding per fact, not per observation

    return findings


# ---------------------------------------------------------------------------
# Overlap findings
# ---------------------------------------------------------------------------


def _fact_core_precision(fact: ResidenceFact) -> str:
    """The coarser precision of the two bounds forming the Certain_Core.

    Returns "year", "month" or "day". When one bound is absent or malformed
    the core is empty and this helper should not be called.
    """
    prec_start = precision_of(fact.start.latest)
    prec_end = precision_of(fact.end.earliest)

    # Map to a rank for coarsest comparison
    rank = {"year": 0, "month": 1, "day": 2}
    r_start = rank.get(prec_start, 0) if prec_start else 0
    r_end = rank.get(prec_end, 0) if prec_end else 0
    min_rank = min(r_start, r_end)
    return {0: "year", 1: "month", 2: "day"}[min_rank]


def _truncate_to_precision(iso_value: str, target_precision: str) -> str:
    """Truncate an ISO date string to the given precision.

    "1840-06-15" at year precision → "1840"
    "1840-06-15" at month precision → "1840-06"
    At day precision, return unchanged.
    """
    parts = iso_value.strip().split("-")
    if target_precision == "year":
        return parts[0]
    if target_precision == "month":
        return "-".join(parts[:2]) if len(parts) >= 2 else parts[0]
    return iso_value.strip()


def _cores_overlap_at_coarser(
    fact_a: ResidenceFact,
    fact_b: ResidenceFact,
    core_a: DaySpan,
    core_b: DaySpan,
) -> bool:
    """Whether two cores overlap at the coarser of the two core precisions.

    The overlap check from Requirement 6.2: the later core's start is strictly
    earlier than the earlier core's end, compared at the coarser precision.
    "Strictly earlier" means expand_iso(a).last < expand_iso(b).first per
    Requirement 2.15.

    Two cores sharing exactly one boundary value at the coarser precision are
    touching, not overlapping (Requirement 6.2, worked example 14.4).
    """
    prec_a = _fact_core_precision(fact_a)
    prec_b = _fact_core_precision(fact_b)
    rank = {"year": 0, "month": 1, "day": 2}
    coarser = {0: "year", 1: "month", 2: "day"}[
        min(rank.get(prec_a, 0), rank.get(prec_b, 0))
    ]

    # Determine which core starts earlier to identify the "later" and "earlier"
    if core_a.first <= core_b.first:
        earlier_fact, later_fact = fact_a, fact_b
    else:
        earlier_fact, later_fact = fact_b, fact_a

    # The later core's start is start.latest of the later fact
    # The earlier core's end is end.earliest of the earlier fact
    # Both truncated to the coarser precision and then compared via
    # strictly_earlier (expand_iso(a).last < expand_iso(b).first)
    later_start = _truncate_to_precision(later_fact.start.latest or "", coarser)
    earlier_end = _truncate_to_precision(earlier_fact.end.earliest or "", coarser)

    # Overlap: the later core's start is strictly earlier than the earlier core's end
    return strictly_earlier(later_start, earlier_end)


def _render_intersection_period(
    fact_a: ResidenceFact, fact_b: ResidenceFact
) -> str:
    """Render the intersection of two Certain_Cores as a period string.

    Uses the ISO values from the endpoints to build synthetic Endpoints and
    render them with the Residence_Formatter. The intersection start is the
    later of the two core starts (start.latest values), the intersection end
    is the earlier of the two core ends (end.earliest values).
    """
    # Determine which fact's core starts later and which ends earlier
    sl_a = expand_iso(fact_a.start.latest)
    sl_b = expand_iso(fact_b.start.latest)
    ee_a = expand_iso(fact_a.end.earliest)
    ee_b = expand_iso(fact_b.end.earliest)

    # Intersection start = later of the two start.latest values (by .last day)
    if sl_a is not None and sl_b is not None:
        if sl_a.last >= sl_b.last:
            inter_start_iso = fact_a.start.latest
        else:
            inter_start_iso = fact_b.start.latest
    elif sl_a is not None:
        inter_start_iso = fact_a.start.latest
    else:
        inter_start_iso = fact_b.start.latest

    # Intersection end = earlier of the two end.earliest values (by .first day)
    if ee_a is not None and ee_b is not None:
        if ee_a.first <= ee_b.first:
            inter_end_iso = fact_a.end.earliest
        else:
            inter_end_iso = fact_b.end.earliest
    elif ee_a is not None:
        inter_end_iso = fact_a.end.earliest
    else:
        inter_end_iso = fact_b.end.earliest

    # Build exact Endpoints and render with the standard formatter
    start_ep = Endpoint(earliest=inter_start_iso, latest=inter_start_iso)
    end_ep = Endpoint(earliest=inter_end_iso, latest=inter_end_iso)
    start_str = format_residence_endpoint(start_ep)
    end_str = format_residence_endpoint(end_ep)
    return f"{start_str}{RESIDENCE_INTERVAL_DASH}{end_str}"


def _place_name(place_id: str, data: ProjectData) -> str:
    """Look up the display name of a place, falling back to its id."""
    for place in data.places:
        if place.id == place_id:
            return place.name
    return place_id


def overlap_findings(person_id: str, data: ProjectData) -> list[ResidenceFinding]:
    """Return overlap findings for all Residence_Facts of one person.

    Evaluates only unordered pairs with equal ``person_id`` and never pairs a
    fact with itself (Requirement 6.3). Two Certain_Cores overlap only when
    the later core's start is strictly earlier than the earlier core's end,
    compared at the coarser of the two core precisions (Requirement 6.2). A
    pair where either core is empty yields nothing (Requirement 6.6).

    Findings are ordered by earlier core start, then by the pair's ascending
    ids, one per pair (Requirement 6.8).
    """
    # Collect this person's facts that have non-empty cores
    person_facts: list[tuple[ResidenceFact, DaySpan]] = []
    for fact in data.residences:
        if fact.person_id != person_id:
            continue
        core = certain_core(fact)
        if core is None:
            continue
        person_facts.append((fact, core))

    if len(person_facts) < 2:
        return []

    # Generate all unordered pairs
    raw_findings: list[tuple[DaySpan, str, str, ResidenceFinding]] = []

    for i in range(len(person_facts)):
        for j in range(i + 1, len(person_facts)):
            fact_a, core_a = person_facts[i]
            fact_b, core_b = person_facts[j]

            if not _cores_overlap_at_coarser(fact_a, fact_b, core_a, core_b):
                continue

            # Determine {plats A} = earlier-starting core (Requirement 6.7)
            # Ties broken by Swedish place-name order, then ascending id
            if core_a.first < core_b.first:
                plats_a_fact, plats_b_fact = fact_a, fact_b
            elif core_b.first < core_a.first:
                plats_a_fact, plats_b_fact = fact_b, fact_a
            else:
                # Tie: by place name then by id
                name_a = _place_name(fact_a.place_id, data)
                name_b = _place_name(fact_b.place_id, data)
                if name_a < name_b:
                    plats_a_fact, plats_b_fact = fact_a, fact_b
                elif name_b < name_a:
                    plats_a_fact, plats_b_fact = fact_b, fact_a
                elif fact_a.id < fact_b.id:
                    plats_a_fact, plats_b_fact = fact_a, fact_b
                else:
                    plats_a_fact, plats_b_fact = fact_b, fact_a

            period = _render_intersection_period(plats_a_fact, plats_b_fact)
            plats_a_name = _place_name(plats_a_fact.place_id, data)
            plats_b_name = _place_name(plats_b_fact.place_id, data)

            if plats_a_fact.place_id == plats_b_fact.place_id:
                message = (
                    f"Två boenden på samma plats överlappar {period}"
                    f" \u2013 överväg att slå samman dem."
                )
            else:
                message = (
                    f"Överlappande boenden: {plats_a_name} och"
                    f" {plats_b_name} överlappar {period}."
                )

            # Determine the earlier core start for sorting
            earlier_core_start = min(core_a.first, core_b.first)
            pair_ids = tuple(sorted([fact_a.id, fact_b.id]))

            finding = ResidenceFinding(
                residence_id=plats_a_fact.id,
                person_id=person_id,
                severity="warning",
                message=message,
                other_residence_id=plats_b_fact.id,
            )
            raw_findings.append(
                (earlier_core_start, pair_ids[0], pair_ids[1], finding)
            )

    # Sort by earlier core start then by ascending pair ids (6.8)
    raw_findings.sort(key=lambda x: (x[0], x[1], x[2]))
    return [f[3] for f in raw_findings]


# ---------------------------------------------------------------------------
# Flytt link findings
# ---------------------------------------------------------------------------


def flytt_link_findings(data: ProjectData) -> list[ResidenceFinding]:
    """Return findings for Flytt_Events whose places don't match linked residences.

    Requirement 18.10: WHERE a Flytt_Event is linked to the end Endpoint of one
    Residence_Fact and to the start Endpoint of another, IF the ``place_id`` of
    the Residence_Fact whose end Endpoint is linked differs from a present
    ``from_place``, or the ``place_id`` of the Residence_Fact whose start
    Endpoint is linked differs from a present ``place``, report the finding.
    """
    findings: list[ResidenceFinding] = []

    # Collect flytt events
    flytt_events = [e for e in data.events if e.type == "flytt"]
    if not flytt_events:
        return findings

    # Build index: event_id → (end-linked residences, start-linked residences)
    end_linked: dict[str, list[ResidenceFact]] = {}
    start_linked: dict[str, list[ResidenceFact]] = {}
    for fact in data.residences:
        if fact.end.event_id:
            end_linked.setdefault(fact.end.event_id, []).append(fact)
        if fact.start.event_id:
            start_linked.setdefault(fact.start.event_id, []).append(fact)

    for event in flytt_events:
        end_facts = end_linked.get(event.id, [])
        start_facts = start_linked.get(event.id, [])

        for end_fact in end_facts:
            # from_place present and differs from end-linked residence's place
            if event.from_place is not None:
                if end_fact.place_id != event.from_place.place_id:
                    findings.append(
                        ResidenceFinding(
                            residence_id=end_fact.id,
                            person_id=end_fact.person_id,
                            severity="warning",
                            message=_MSG_FLYTT_LINK_MISMATCH,
                        )
                    )

        for start_fact in start_facts:
            # place present and differs from start-linked residence's place
            if event.place is not None:
                if start_fact.place_id != event.place.place_id:
                    findings.append(
                        ResidenceFinding(
                            residence_id=start_fact.id,
                            person_id=start_fact.person_id,
                            severity="warning",
                            message=_MSG_FLYTT_LINK_MISMATCH,
                        )
                    )

    return findings
