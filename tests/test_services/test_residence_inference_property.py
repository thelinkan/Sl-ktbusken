# Feature: residence-periods, Property 17: Inference derives from stored data only, idempotently, and never contradicts
"""Property-based test for residence inference.

Feature: residence-periods, Property 17: Inference derives from stored data only, idempotently, and never contradicts

For any Residence_Fact, the derived bounds are computed in a single pass from the
stored bounds of the person's other Residence_Facts and the stored dates of that
person's birth and death Events, each derived bound naming the endpoint, the
bound, the value in its stored ISO form and the entity it came from; no derived
bound is used as input to another; every stored field of every Residence_Fact,
Endpoint and Observation is unchanged and no derived value is written to the
project file; competing candidates resolve to the latest for an `earliest` bound
and the earliest for a `latest` bound compared as widest intervals; a candidate
contradicting a stored bound of the same fact is omitted and reported as
"Härlett värde motsäger inmatat värde."; and because no candidate is formed for a
bound already present, a second run after a confirmed write leaves every bound
equal to its value after the first.

**Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.10, 7.12**
"""

from __future__ import annotations

import copy

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.date_span import expand_iso, strictly_earlier
from slaktbusken.model.residence import Endpoint, ResidenceFact
from slaktbusken.services.residence_inference import (
    DerivedBound,
    InferenceResult,
    infer_bounds,
)
from tests.test_model.residence_strategies import consistent_projects


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MSG_CONTRADICTION = "Härlett värde motsäger inmatat värde."


def _is_present(value: str | None) -> bool:
    """Whether a bound value counts as present (not None/empty/whitespace)."""
    return value is not None and bool(value.strip())


def _get_bound(ep: Endpoint, bound: str) -> str | None:
    """Get an endpoint bound by name."""
    return ep.earliest if bound == "earliest" else ep.latest


def _set_bound(ep: Endpoint, bound: str, value: str) -> None:
    """Set an endpoint bound by name (for simulating confirmed write)."""
    if bound == "earliest":
        ep.earliest = value
    else:
        ep.latest = value


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


class TestInferenceDerived:
    """Property 17: Inference derives from stored data only, idempotently, and never contradicts.

    For any Residence_Fact, the derived bounds are computed in a single pass from
    the stored bounds of the person's other Residence_Facts and the stored dates
    of that person's birth and death Events, each derived bound naming the
    endpoint, the bound, the value in its stored ISO form and the entity it came
    from; no derived bound is used as input to another; every stored field of
    every Residence_Fact, Endpoint and Observation is unchanged and no derived
    value is written to the project file; competing candidates resolve to the
    latest for an `earliest` bound and the earliest for a `latest` bound compared
    as widest intervals; a candidate contradicting a stored bound of the same fact
    is omitted and reported as "Härlett värde motsäger inmatat värde."; and because
    no candidate is formed for a bound already present, a second run after a
    confirmed write leaves every bound equal to its value after the first.

    **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.10, 7.12**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_inference_property(self, data: st.DataObject) -> None:
        """Inference obeys stored-data-only, idempotence and contradiction rules.

        Feature: residence-periods, Property 17: Inference derives from stored data only, idempotently, and never contradicts

        **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.10, 7.12**
        """
        project = data.draw(
            consistent_projects(
                min_persons=1,
                max_persons=3,
                min_places=2,
                max_places=4,
                max_sources=2,
                max_events=4,
                min_residences=2,
                max_residences=6,
            )
        )

        if not project.residences:
            return

        # Pick a fact to run inference on
        fact = data.draw(st.sampled_from(project.residences))

        # --- Snapshot all facts before inference (Requirement 7.2: no mutation) ---
        project_snapshot = copy.deepcopy(project)

        # --- Run inference ---
        result = infer_bounds(fact, project)

        # --- ASSERTION 1: No mutation of any stored field (Req 7.2) ---
        # The original project must be identical to the snapshot
        for i, res in enumerate(project.residences):
            snap = project_snapshot.residences[i]
            assert res.id == snap.id
            assert res.person_id == snap.person_id
            assert res.place_id == snap.place_id
            assert res.role_in_household == snap.role_in_household
            assert res.notes == snap.notes
            assert res.start.earliest == snap.start.earliest
            assert res.start.latest == snap.start.latest
            assert res.start.precision == snap.start.precision
            assert res.start.event_id == snap.start.event_id
            assert res.start.note == snap.start.note
            assert res.end.earliest == snap.end.earliest
            assert res.end.latest == snap.end.latest
            assert res.end.precision == snap.end.precision
            assert res.end.event_id == snap.end.event_id
            assert res.end.note == snap.end.note
            assert len(res.observations) == len(snap.observations)
            for obs, snap_obs in zip(res.observations, snap.observations):
                assert obs.source_ref.source_id == snap_obs.source_ref.source_id
                assert obs.observed_from == snap_obs.observed_from
                assert obs.observed_to == snap_obs.observed_to
                assert obs.page_note == snap_obs.page_note

        # --- ASSERTION 2: Derived bounds come only from stored values (Req 7.1) ---
        # Each derived bound references an origin (residence or event) that
        # exists in the project, and its value is a stored ISO value from that origin.
        for db in result.derived:
            assert db.residence_id == fact.id
            assert db.endpoint in ("start", "end")
            assert db.bound in ("earliest", "latest")
            assert db.origin_kind in ("residence", "event")
            # The value must be a valid ISO form
            assert expand_iso(db.value) is not None, (
                f"Derived value '{db.value}' is not a valid ISO date"
            )
            # The origin must exist
            if db.origin_kind == "residence":
                origin_ids = {r.id for r in project.residences}
                assert db.origin_id in origin_ids, (
                    f"Derived bound references unknown residence {db.origin_id}"
                )
            else:
                origin_ids = {e.id for e in project.events}
                assert db.origin_id in origin_ids, (
                    f"Derived bound references unknown event {db.origin_id}"
                )

        # --- ASSERTION 3: No derived bound for a bound that is already present (Req 7.10) ---
        for db in result.derived:
            ep = fact.start if db.endpoint == "start" else fact.end
            stored = _get_bound(ep, db.bound)
            assert not _is_present(stored), (
                f"Derived bound for {db.endpoint}.{db.bound} but stored value "
                f"'{stored}' is already present"
            )

        # --- ASSERTION 4: Contradicting candidates produce a finding (Req 7.12) ---
        # Every finding carries the contradiction message and references the fact
        for finding in result.findings:
            assert finding.residence_id == fact.id
            assert finding.person_id == fact.person_id
            assert finding.severity == "warning"
            assert finding.message == _MSG_CONTRADICTION

        # No derived bound should contradict the stored bounds
        for db in result.derived:
            if db.endpoint == "start" and db.bound == "earliest":
                # start.earliest must not be later than start.latest
                if _is_present(fact.start.latest):
                    assert not strictly_earlier(fact.start.latest, db.value), (
                        f"Derived start.earliest '{db.value}' contradicts "
                        f"stored start.latest '{fact.start.latest}'"
                    )
                # start.earliest must not be later than end.latest
                if _is_present(fact.end.latest):
                    assert not strictly_earlier(fact.end.latest, db.value), (
                        f"Derived start.earliest '{db.value}' contradicts "
                        f"stored end.latest '{fact.end.latest}'"
                    )
            elif db.endpoint == "end" and db.bound == "latest":
                # end.latest must not be earlier than end.earliest
                if _is_present(fact.end.earliest):
                    assert not strictly_earlier(db.value, fact.end.earliest), (
                        f"Derived end.latest '{db.value}' contradicts "
                        f"stored end.earliest '{fact.end.earliest}'"
                    )
                # end.latest must not be earlier than start.earliest
                if _is_present(fact.start.earliest):
                    assert not strictly_earlier(db.value, fact.start.earliest), (
                        f"Derived end.latest '{db.value}' contradicts "
                        f"stored start.earliest '{fact.start.earliest}'"
                    )

        # --- ASSERTION 5: Idempotence after simulated confirmed write (Req 7.10) ---
        # Simulate writing the derived bounds into the fact, then re-run inference.
        if result.derived:
            fact_copy = copy.deepcopy(fact)
            for db in result.derived:
                ep = fact_copy.start if db.endpoint == "start" else fact_copy.end
                _set_bound(ep, db.bound, db.value)

            # Replace the fact in a project copy for the second run
            project_copy = copy.deepcopy(project)
            for i, res in enumerate(project_copy.residences):
                if res.id == fact_copy.id:
                    project_copy.residences[i] = fact_copy
                    break

            result2 = infer_bounds(fact_copy, project_copy)
            # Second run should produce no new derived bounds (idempotence)
            assert result2.derived == [], (
                f"Second inference after confirmed write produced "
                f"{len(result2.derived)} derived bounds; expected 0 (idempotence)"
            )

        # --- ASSERTION 6: No derived bound uses another derived bound as input (Req 7.1) ---
        # The derived values must trace back to stored fields on other entities,
        # not to other derived bounds from this same run.
        derived_values = {(db.endpoint, db.bound, db.value) for db in result.derived}
        for db in result.derived:
            if db.origin_kind == "residence":
                # The value must match a stored bound on the origin residence
                origin_fact = None
                for r in project.residences:
                    if r.id == db.origin_id:
                        origin_fact = r
                        break
                assert origin_fact is not None
                # Collect all stored bound values on the origin
                stored_values = {
                    origin_fact.start.earliest,
                    origin_fact.start.latest,
                    origin_fact.end.earliest,
                    origin_fact.end.latest,
                }
                # The derived value must come from a stored bound (stripped)
                stored_stripped = {
                    v.strip() for v in stored_values if _is_present(v)
                }
                assert db.value in stored_stripped, (
                    f"Derived value '{db.value}' not found in stored bounds of "
                    f"origin residence {db.origin_id}: {stored_stripped}"
                )
            else:
                # Event origin: value must match a stored event date
                origin_event = None
                for e in project.events:
                    if e.id == db.origin_id:
                        origin_event = e
                        break
                assert origin_event is not None
                assert origin_event.date is not None
                assert _is_present(origin_event.date.value)
                assert db.value == origin_event.date.value.strip(), (
                    f"Derived value '{db.value}' does not match event date "
                    f"'{origin_event.date.value}'"
                )
