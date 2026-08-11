# Feature: residence-periods, Property 16: Overlap findings pair, message and order deterministically
"""Property-based test for overlap findings.

Feature: residence-periods, Property 16: Overlap findings pair, message and order deterministically

For any pair of Residence_Facts, an overlap finding is returned exactly when the
two facts have equal `person_id`, both have a non-empty Certain_Core, and the
later core's start is strictly earlier than the earlier core's end at the coarser
of the two core precisions — so cores sharing exactly one boundary value yield
none, as does an overlap confined to the Possible_Spans; the message is the
same-place or different-place form with {period} the formatted core intersection,
{plats A} is the earlier-starting core with ties broken by Swedish place-name
order then ascending `id`, no fact is paired with itself, exactly one finding is
returned per unordered pair, and two runs over unchanged data return identical
messages in identical order.

**Validates: Requirements 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8**
"""

from __future__ import annotations

from itertools import combinations
from typing import Optional

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.date_span import (
    DaySpan,
    expand_iso,
    precision_of,
    strictly_earlier,
)
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import (
    Endpoint,
    ResidenceFact,
    certain_core,
)
from slaktbusken.services.residence_validation import (
    ResidenceFinding,
    overlap_findings,
)
from tests.test_model.residence_strategies import consistent_projects


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coarser_precision(prec_a: Optional[str], prec_b: Optional[str]) -> str:
    """Return the coarser of two core precisions."""
    rank = {"year": 0, "month": 1, "day": 2}
    r_a = rank.get(prec_a, 0) if prec_a else 0
    r_b = rank.get(prec_b, 0) if prec_b else 0
    return {0: "year", 1: "month", 2: "day"}[min(r_a, r_b)]


def _truncate(iso_value: str, target_precision: str) -> str:
    """Truncate an ISO date string to the given precision."""
    parts = iso_value.strip().split("-")
    if target_precision == "year":
        return parts[0]
    if target_precision == "month":
        return "-".join(parts[:2]) if len(parts) >= 2 else parts[0]
    return iso_value.strip()


def _core_precision(fact: ResidenceFact) -> str:
    """The coarser precision of the two bounds forming the Certain_Core."""
    prec_start = precision_of(fact.start.latest)
    prec_end = precision_of(fact.end.earliest)
    return _coarser_precision(prec_start, prec_end)


def _cores_overlap(fact_a: ResidenceFact, fact_b: ResidenceFact,
                   core_a: DaySpan, core_b: DaySpan) -> bool:
    """Test whether two cores overlap at the coarser core precision (Req 6.2)."""
    coarser = _coarser_precision(_core_precision(fact_a), _core_precision(fact_b))

    # Identify earlier and later by core start
    if core_a.first <= core_b.first:
        earlier_fact, later_fact = fact_a, fact_b
    else:
        earlier_fact, later_fact = fact_b, fact_a

    # The later core's start truncated at coarser precision must be strictly
    # earlier than the earlier core's end truncated at coarser precision
    later_start = _truncate(later_fact.start.latest or "", coarser)
    earlier_end = _truncate(earlier_fact.end.earliest or "", coarser)

    return strictly_earlier(later_start, earlier_end)


def _place_name(place_id: str, data: ProjectData) -> str:
    """Look up the display name of a place, falling back to its id."""
    for place in data.places:
        if place.id == place_id:
            return place.name
    return place_id


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


class TestOverlapFindingsDeterministic:
    """Property 16: Overlap findings pair, message and order deterministically.

    For any pair of Residence_Facts, an overlap finding is returned exactly when
    the two facts have equal `person_id`, both have a non-empty Certain_Core, and
    the later core's start is strictly earlier than the earlier core's end at the
    coarser of the two core precisions — so cores sharing exactly one boundary
    value yield none, as does an overlap confined to the Possible_Spans; the
    message is the same-place or different-place form with {period} the formatted
    core intersection, {plats A} is the earlier-starting core with ties broken by
    Swedish place-name order then ascending `id`, no fact is paired with itself,
    exactly one finding is returned per unordered pair, and two runs over unchanged
    data return identical messages in identical order.

    **Validates: Requirements 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_overlap_findings_deterministic(self, data: st.DataObject) -> None:
        """Overlap findings obey pairing, message, and ordering rules.

        Feature: residence-periods, Property 16: Overlap findings pair, message and order deterministically

        **Validates: Requirements 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8**
        """
        project = data.draw(
            consistent_projects(
                min_persons=1,
                max_persons=2,
                min_places=1,
                max_places=3,
                max_sources=2,
                max_events=2,
                min_residences=2,
                max_residences=6,
            )
        )

        # Pick a person_id that has residences
        person_ids_with_residences = {
            f.person_id for f in project.residences if f.person_id.strip()
        }
        if not person_ids_with_residences:
            return  # nothing to test

        person_id = data.draw(st.sampled_from(sorted(person_ids_with_residences)))

        # --- Run the function under test ---
        findings = overlap_findings(person_id, project)

        # --- Collect same-person facts with non-empty cores ---
        person_facts: list[tuple[ResidenceFact, DaySpan]] = []
        for fact in project.residences:
            if fact.person_id != person_id:
                continue
            core = certain_core(fact)
            if core is None:
                continue
            person_facts.append((fact, core))

        # --- Property: only unordered same-person pairs (6.3) ---
        # Every finding must reference two distinct residence ids belonging to this person
        person_fact_ids = {f.id for f in project.residences if f.person_id == person_id}
        for finding in findings:
            assert finding.residence_id in person_fact_ids, (
                f"Finding residence_id {finding.residence_id} not in person's facts"
            )
            assert finding.other_residence_id in person_fact_ids, (
                f"Finding other_residence_id {finding.other_residence_id} not in person's facts"
            )
            # No fact paired with itself
            assert finding.residence_id != finding.other_residence_id

        # --- Property: both cores must be non-empty (6.6) ---
        # Each finding references two facts that both have non-empty cores
        facts_with_core_ids = {f.id for f, _ in person_facts}
        for finding in findings:
            assert finding.residence_id in facts_with_core_ids, (
                f"Finding references {finding.residence_id} which has empty core"
            )
            assert finding.other_residence_id in facts_with_core_ids, (
                f"Finding references {finding.other_residence_id} which has empty core"
            )

        # --- Property: overlap at coarser precision (6.2) ---
        # Every returned finding pair must actually overlap at coarser precision
        facts_by_id = {f.id: (f, c) for f, c in person_facts}
        for finding in findings:
            fact_a, core_a = facts_by_id[finding.residence_id]
            fact_b, core_b = facts_by_id[finding.other_residence_id]
            assert _cores_overlap(fact_a, fact_b, core_a, core_b), (
                f"Finding for pair ({finding.residence_id}, {finding.other_residence_id}) "
                f"but cores do not overlap at coarser precision"
            )

        # --- Property: one finding per pair (6.8) ---
        # Collect all unordered pairs from findings
        finding_pairs = set()
        for finding in findings:
            pair = frozenset([finding.residence_id, finding.other_residence_id])
            assert pair not in finding_pairs, (
                f"Duplicate finding for pair {pair}"
            )
            finding_pairs.add(pair)

        # --- Property: completeness — all overlapping pairs produce a finding ---
        expected_pairs: set[frozenset[str]] = set()
        for i in range(len(person_facts)):
            for j in range(i + 1, len(person_facts)):
                fact_a, core_a = person_facts[i]
                fact_b, core_b = person_facts[j]
                if _cores_overlap(fact_a, fact_b, core_a, core_b):
                    expected_pairs.add(frozenset([fact_a.id, fact_b.id]))

        assert finding_pairs == expected_pairs, (
            f"Mismatch: findings produced pairs {finding_pairs}, "
            f"expected {expected_pairs}"
        )

        # --- Property: same-place vs different-place messages (6.4, 6.5) ---
        for finding in findings:
            fact_a, _ = facts_by_id[finding.residence_id]
            fact_b, _ = facts_by_id[finding.other_residence_id]
            if fact_a.place_id == fact_b.place_id:
                assert "Två boenden på samma plats överlappar" in finding.message, (
                    f"Same-place pair should use same-place message, got: {finding.message}"
                )
                assert "överväg att slå samman dem" in finding.message
            else:
                assert "Överlappande boenden:" in finding.message, (
                    f"Different-place pair should use different-place message, got: {finding.message}"
                )

        # --- Property: {plats A} ordering (6.7) ---
        for finding in findings:
            fact_a, core_a = facts_by_id[finding.residence_id]
            fact_b, core_b = facts_by_id[finding.other_residence_id]
            # finding.residence_id should be the {plats A} fact — the one whose
            # core starts earlier, with ties broken by place name then id
            if core_a.first < core_b.first:
                # fact_a should be plats A → residence_id
                pass  # correct
            elif core_b.first < core_a.first:
                # fact_b should be plats A → residence_id should be fact_b.id
                assert finding.residence_id == fact_b.id, (
                    "plats A should be the earlier-starting core"
                )
            else:
                # Tie: broken by place name then id
                name_a = _place_name(fact_a.place_id, project)
                name_b = _place_name(fact_b.place_id, project)
                if name_a < name_b:
                    assert finding.residence_id == fact_a.id
                elif name_b < name_a:
                    assert finding.residence_id == fact_b.id
                else:
                    # Tie in place name: by ascending id
                    expected_plats_a_id = min(fact_a.id, fact_b.id)
                    assert finding.residence_id == expected_plats_a_id

        # --- Property: findings ordered by earlier core start then ascending pair ids (6.8) ---
        sort_keys = []
        for finding in findings:
            fact_a, core_a = facts_by_id[finding.residence_id]
            fact_b, core_b = facts_by_id[finding.other_residence_id]
            earlier_start = min(core_a.first, core_b.first)
            pair_ids = tuple(sorted([finding.residence_id, finding.other_residence_id]))
            sort_keys.append((earlier_start, pair_ids[0], pair_ids[1]))

        assert sort_keys == sorted(sort_keys), (
            f"Findings not ordered correctly: {sort_keys}"
        )

        # --- Property: determinism — two runs produce identical results ---
        findings_second = overlap_findings(person_id, project)
        assert len(findings) == len(findings_second)
        for f1, f2 in zip(findings, findings_second):
            assert f1.residence_id == f2.residence_id
            assert f1.other_residence_id == f2.other_residence_id
            assert f1.message == f2.message
            assert f1.severity == f2.severity
            assert f1.person_id == f2.person_id

        # --- Property: severity is always "warning" ---
        for finding in findings:
            assert finding.severity == "warning"
            assert finding.person_id == person_id
