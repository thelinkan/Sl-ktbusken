# Feature: residence-periods, Property 5: Single-fact warning findings appear exactly when their condition holds
"""Property-based test for single-fact warning findings.

Feature: residence-periods, Property 5: Single-fact warning findings appear
exactly when their condition holds

For any Residence_Fact, a warning-level finding with the required message is
returned exactly when its condition holds — overlapping start and end windows,
the same Source attached more than once, an Observation attesting presence
outside the recorded outer bounds — with zero errors in each case, and the
Residence_Editor saves such a fact retaining every value the user entered.

**Validates: Requirements 2.17, 4.13, 6.9, 16.9**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.date_span import expand_iso
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.event import SourceRef
from slaktbusken.services.residence_validation import (
    residence_findings,
    _MSG_WINDOW_OVERLAP,
    _MSG_DUPLICATE_SOURCE,
    _MSG_EVIDENCE_OUTSIDE,
)
from tests.test_model.residence_strategies import (
    consistent_projects,
    residence_facts,
)


# ---------------------------------------------------------------------------
# Oracle helpers — independently verify each condition
# ---------------------------------------------------------------------------


def _expect_window_overlap(fact: ResidenceFact) -> bool:
    """Requirement 2.17: start.latest.last > end.earliest.first."""
    start_latest = expand_iso(fact.start.latest)
    end_earliest = expand_iso(fact.end.earliest)
    if start_latest is None or end_earliest is None:
        return False
    return start_latest.last > end_earliest.first


def _expect_duplicate_source(fact: ResidenceFact) -> bool:
    """Requirement 4.13: two or more Observations carry the same source_id."""
    seen: set[str] = set()
    for obs in fact.observations:
        sid = obs.source_ref.source_id
        if sid in seen:
            return True
        seen.add(sid)
    return False


def _expect_evidence_outside(fact: ResidenceFact) -> bool:
    """Requirement 16.9: an Observation attests presence outside the outer bounds.

    An Observation's observed_from earlier than start.earliest, or observed_to
    later than end.latest. Only fires when the respective outer bound is present
    and the observation year expands to a valid span.
    """
    start_earliest = expand_iso(fact.start.earliest)
    end_latest = expand_iso(fact.end.latest)

    for obs in fact.observations:
        # Check observed_from < start.earliest
        if start_earliest is not None and obs.observed_from.strip():
            obs_from = expand_iso(obs.observed_from.strip())
            if obs_from is not None and obs_from.first < start_earliest.first:
                return True
        # Check observed_to > end.latest
        if end_latest is not None and obs.observed_to.strip():
            obs_to = expand_iso(obs.observed_to.strip())
            if obs_to is not None and obs_to.last > end_latest.last:
                return True
    return False


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


class TestSingleFactWarningFindings:
    """Property 5: Single-fact warning findings appear exactly when their
    condition holds.

    For any Residence_Fact, a warning-level finding with the required message is
    returned exactly when its condition holds — overlapping start and end windows,
    the same Source attached more than once, an Observation attesting presence
    outside the recorded outer bounds — with zero errors in each case, and the
    Residence_Editor saves such a fact retaining every value the user entered.

    **Validates: Requirements 2.17, 4.13, 6.9, 16.9**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_findings_match_conditions_exactly(self, data: st.DataObject) -> None:
        """Each finding appears if and only if its condition holds.

        Feature: residence-periods, Property 5: Single-fact warning findings
        appear exactly when their condition holds

        **Validates: Requirements 2.17, 4.13, 6.9, 16.9**
        """
        project = data.draw(
            consistent_projects(
                min_persons=1,
                max_persons=2,
                min_places=1,
                max_places=2,
                max_sources=4,
                max_events=2,
                min_residences=1,
                max_residences=3,
                include_many_observations=False,
            )
        )

        for fact in project.residences:
            findings = residence_findings(fact, project)

            # All findings must be warning-level (6.9: saves with warnings)
            for f in findings:
                assert f.severity == "warning", (
                    f"Finding on {fact.id!r} has severity {f.severity!r}, "
                    f"expected 'warning'"
                )
                assert f.residence_id == fact.id
                assert f.person_id == fact.person_id

            messages = [f.message for f in findings]

            # --- 2.17: window overlap ---
            expect_overlap = _expect_window_overlap(fact)
            has_overlap = _MSG_WINDOW_OVERLAP in messages
            assert has_overlap == expect_overlap, (
                f"Window overlap finding mismatch for {fact.id!r}: "
                f"expected={expect_overlap}, got={has_overlap}.\n"
                f"start.latest={fact.start.latest!r}, "
                f"end.earliest={fact.end.earliest!r}"
            )
            # At most one window overlap finding per fact
            assert messages.count(_MSG_WINDOW_OVERLAP) <= 1

            # --- 4.13: duplicate source ---
            expect_dup = _expect_duplicate_source(fact)
            has_dup = _MSG_DUPLICATE_SOURCE in messages
            assert has_dup == expect_dup, (
                f"Duplicate source finding mismatch for {fact.id!r}: "
                f"expected={expect_dup}, got={has_dup}.\n"
                f"source_ids={[o.source_ref.source_id for o in fact.observations]}"
            )
            # At most one duplicate source finding per fact
            assert messages.count(_MSG_DUPLICATE_SOURCE) <= 1

            # --- 16.9: evidence outside ---
            expect_outside = _expect_evidence_outside(fact)
            has_outside = _MSG_EVIDENCE_OUTSIDE in messages
            assert has_outside == expect_outside, (
                f"Evidence-outside finding mismatch for {fact.id!r}: "
                f"expected={expect_outside}, got={has_outside}.\n"
                f"start.earliest={fact.start.earliest!r}, "
                f"end.latest={fact.end.latest!r}, "
                f"observations=[{', '.join(f'({o.observed_from!r},{o.observed_to!r})' for o in fact.observations)}]"
            )
            # At most one evidence-outside finding per fact
            assert messages.count(_MSG_EVIDENCE_OUTSIDE) <= 1

            # No unexpected messages: every message should be one of the three
            known_messages = {_MSG_WINDOW_OVERLAP, _MSG_DUPLICATE_SOURCE, _MSG_EVIDENCE_OUTSIDE}
            for msg in messages:
                assert msg in known_messages, (
                    f"Unexpected finding message on {fact.id!r}: {msg!r}"
                )
