"""Unit tests for attach_observations and remove_observation.

Covers the documented core tightening on attach (Requirements 4.3, 9.5,
16.3, 16.4) and the provenance-aware recomputation on removal
(Requirements 16.7, 16.8).
"""

from __future__ import annotations

import copy

import pytest

from slaktbusken.model.event import SourceRef
from slaktbusken.model.residence import (
    Endpoint,
    Observation,
    ResidenceFact,
    core_aggregate,
)
from slaktbusken.services.residence_edit_ops import (
    attach_observations,
    remove_observation,
)


def _obs(from_year: str = "", to_year: str = "", source_id: str = "s1") -> Observation:
    """Helper to build a minimal Observation."""
    return Observation(
        source_ref=SourceRef(source_id=source_id, quality=""),
        observed_from=from_year,
        observed_to=to_year,
    )


def _fact(
    obs: list[Observation] | None = None,
    start_earliest: str | None = None,
    start_latest: str | None = None,
    end_earliest: str | None = None,
    end_latest: str | None = None,
) -> ResidenceFact:
    """Helper to build a minimal ResidenceFact."""
    return ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest=start_earliest, latest=start_latest),
        end=Endpoint(earliest=end_earliest, latest=end_latest),
        observations=obs if obs is not None else [],
    )


# ===========================================================================
# attach_observations
# ===========================================================================


class TestAttachObservationsAppendOrder:
    """Observations are appended in order (Req 4.3)."""

    def test_appends_single_observation(self) -> None:
        fact = _fact()
        obs = _obs("1866", "1870")
        result = attach_observations(fact, [obs])
        assert len(result.observations) == 1
        assert result.observations[0].observed_from == "1866"
        assert result.observations[0].observed_to == "1870"

    def test_appends_multiple_observations_in_order(self) -> None:
        existing = _obs("1860", "1865")
        fact = _fact(obs=[existing])
        new_obs = [_obs("1866", "1870"), _obs("1871", "1875")]
        result = attach_observations(fact, new_obs)
        assert len(result.observations) == 3
        assert result.observations[0].observed_from == "1860"
        assert result.observations[1].observed_from == "1866"
        assert result.observations[2].observed_from == "1871"

    def test_appends_to_empty_list(self) -> None:
        fact = _fact()
        result = attach_observations(fact, [_obs("1866", "1870")])
        assert len(result.observations) == 1

    def test_appends_empty_list_is_noop(self) -> None:
        existing = _obs("1866", "1870")
        fact = _fact(obs=[existing])
        result = attach_observations(fact, [])
        assert len(result.observations) == 1
        assert result.observations[0].observed_from == "1866"


class TestAttachObservationsTightenCore:
    """Core tightening: start.latest and end.earliest (Req 16.4)."""

    def test_sets_start_latest_when_absent(self) -> None:
        fact = _fact(start_latest=None)
        result = attach_observations(fact, [_obs("1866", "1870")])
        assert result.start.latest == "1866"

    def test_sets_end_earliest_when_absent(self) -> None:
        fact = _fact(end_earliest=None)
        result = attach_observations(fact, [_obs("1866", "1870")])
        assert result.end.earliest == "1870"

    def test_tightens_start_latest_to_earlier(self) -> None:
        fact = _fact(start_latest="1870")
        result = attach_observations(fact, [_obs("1866", "1870")])
        assert result.start.latest == "1866"

    def test_keeps_start_latest_when_already_earlier(self) -> None:
        fact = _fact(start_latest="1860")
        result = attach_observations(fact, [_obs("1866", "1870")])
        assert result.start.latest == "1860"

    def test_tightens_end_earliest_to_later(self) -> None:
        fact = _fact(end_earliest="1865")
        result = attach_observations(fact, [_obs("1866", "1870")])
        assert result.end.earliest == "1870"

    def test_keeps_end_earliest_when_already_later(self) -> None:
        fact = _fact(end_earliest="1880")
        result = attach_observations(fact, [_obs("1866", "1870")])
        assert result.end.earliest == "1880"

    def test_multiple_new_obs_uses_min_from_max_to(self) -> None:
        fact = _fact()
        new_obs = [_obs("1866", "1870"), _obs("1860", "1875")]
        result = attach_observations(fact, new_obs)
        assert result.start.latest == "1860"
        assert result.end.earliest == "1875"

    def test_considers_existing_observations_for_aggregate(self) -> None:
        existing = _obs("1855", "1880")
        fact = _fact(obs=[existing], start_latest="1855", end_earliest="1880")
        new_obs = [_obs("1866", "1870")]
        result = attach_observations(fact, new_obs)
        # Aggregate is min(1855, 1866)=1855, max(1880, 1870)=1880
        assert result.start.latest == "1855"
        assert result.end.earliest == "1880"


class TestAttachObservationsNeverTouchOuterBounds:
    """start.earliest and end.latest are NEVER modified (Req 16.3)."""

    def test_start_earliest_unchanged(self) -> None:
        fact = _fact(start_earliest="1840")
        result = attach_observations(fact, [_obs("1830", "1870")])
        assert result.start.earliest == "1840"

    def test_end_latest_unchanged(self) -> None:
        fact = _fact(end_latest="1890")
        result = attach_observations(fact, [_obs("1866", "1900")])
        assert result.end.latest == "1890"

    def test_absent_outer_bounds_stay_absent(self) -> None:
        fact = _fact(start_earliest=None, end_latest=None)
        result = attach_observations(fact, [_obs("1866", "1870")])
        assert result.start.earliest is None
        assert result.end.latest is None


class TestAttachObservationsIsPure:
    """The input fact is never mutated."""

    def test_input_fact_unchanged(self) -> None:
        fact = _fact(start_latest="1870")
        original_start_latest = fact.start.latest
        original_obs_count = len(fact.observations)
        attach_observations(fact, [_obs("1866", "1870")])
        assert fact.start.latest == original_start_latest
        assert len(fact.observations) == original_obs_count

    def test_input_observations_unchanged(self) -> None:
        obs = _obs("1866", "1870")
        original_from = obs.observed_from
        fact = _fact()
        attach_observations(fact, [obs])
        assert obs.observed_from == original_from


# ===========================================================================
# remove_observation
# ===========================================================================


class TestRemoveObservationSurvivorOrder:
    """Survivors keep relative order and are byte-identical (Req 4.3)."""

    def test_removes_single_observation(self) -> None:
        fact = _fact(obs=[_obs("1866", "1870")])
        result = remove_observation(fact, 0)
        assert len(result.observations) == 0

    def test_removes_middle_observation(self) -> None:
        obs1 = _obs("1860", "1865", "s1")
        obs2 = _obs("1866", "1870", "s2")
        obs3 = _obs("1871", "1875", "s3")
        fact = _fact(obs=[obs1, obs2, obs3], start_latest="1860", end_earliest="1875")
        result = remove_observation(fact, 1)
        assert len(result.observations) == 2
        assert result.observations[0].observed_from == "1860"
        assert result.observations[0].source_ref.source_id == "s1"
        assert result.observations[1].observed_from == "1871"
        assert result.observations[1].source_ref.source_id == "s3"

    def test_removes_first_observation(self) -> None:
        obs1 = _obs("1860", "1865", "s1")
        obs2 = _obs("1866", "1870", "s2")
        fact = _fact(obs=[obs1, obs2], start_latest="1860", end_earliest="1870")
        result = remove_observation(fact, 0)
        assert len(result.observations) == 1
        assert result.observations[0].source_ref.source_id == "s2"

    def test_removes_last_observation(self) -> None:
        obs1 = _obs("1860", "1865", "s1")
        obs2 = _obs("1866", "1870", "s2")
        fact = _fact(obs=[obs1, obs2], start_latest="1860", end_earliest="1870")
        result = remove_observation(fact, 1)
        assert len(result.observations) == 1
        assert result.observations[0].source_ref.source_id == "s1"


class TestRemoveObservationRecomputesDerived:
    """Recomputes bounds when stored value equals pre-removal aggregate (Req 16.7)."""

    def test_recomputes_start_latest_when_derived(self) -> None:
        # Observations: 1860-1865, 1866-1870. Aggregate from = "1860".
        # Remove the first → survivors aggregate from = "1866".
        obs1 = _obs("1860", "1865", "s1")
        obs2 = _obs("1866", "1870", "s2")
        fact = _fact(obs=[obs1, obs2], start_latest="1860", end_earliest="1870")
        result = remove_observation(fact, 0)
        assert result.start.latest == "1866"

    def test_recomputes_end_earliest_when_derived(self) -> None:
        # Observations: 1860-1870, 1866-1875. Aggregate to = "1875".
        # Remove the second → survivors aggregate to = "1870".
        obs1 = _obs("1860", "1870", "s1")
        obs2 = _obs("1866", "1875", "s2")
        fact = _fact(obs=[obs1, obs2], start_latest="1860", end_earliest="1875")
        result = remove_observation(fact, 1)
        assert result.end.earliest == "1870"

    def test_sets_to_none_when_no_survivors(self) -> None:
        obs = _obs("1866", "1870")
        fact = _fact(obs=[obs], start_latest="1866", end_earliest="1870")
        result = remove_observation(fact, 0)
        # No survivors → aggregate is (None, None) → bounds become None.
        assert result.start.latest is None
        assert result.end.earliest is None


class TestRemoveObservationKeepsHandEntered:
    """Hand-entered bounds survive removal unchanged (Req 16.8)."""

    def test_keeps_start_latest_when_hand_entered(self) -> None:
        # Aggregate from = "1860", but stored start.latest = "1850" (hand-entered).
        obs1 = _obs("1860", "1865", "s1")
        obs2 = _obs("1866", "1870", "s2")
        fact = _fact(obs=[obs1, obs2], start_latest="1850", end_earliest="1870")
        result = remove_observation(fact, 0)
        assert result.start.latest == "1850"

    def test_keeps_end_earliest_when_hand_entered(self) -> None:
        # Aggregate to = "1870", but stored end.earliest = "1880" (hand-entered).
        obs1 = _obs("1860", "1865", "s1")
        obs2 = _obs("1866", "1870", "s2")
        fact = _fact(obs=[obs1, obs2], start_latest="1860", end_earliest="1880")
        result = remove_observation(fact, 0)
        assert result.end.earliest == "1880"

    def test_bound_equal_to_aggregate_is_treated_as_derived(self) -> None:
        """Design decision 3: coincidence is treated as derived (harmless direction)."""
        # Stored bound equals the aggregate, so it is treated as derived.
        obs1 = _obs("1866", "1870", "s1")
        obs2 = _obs("1866", "1875", "s2")
        fact = _fact(obs=[obs1, obs2], start_latest="1866", end_earliest="1875")
        # Remove obs2, survivors aggregate = ("1866", "1870").
        result = remove_observation(fact, 1)
        assert result.start.latest == "1866"  # Stays same (aggregate unchanged).
        assert result.end.earliest == "1870"  # Recomputed from survivors.


class TestRemoveObservationNeverTouchesOuterBounds:
    """start.earliest and end.latest are NEVER modified (Req 16.3)."""

    def test_start_earliest_unchanged(self) -> None:
        obs = _obs("1866", "1870")
        fact = _fact(
            obs=[obs], start_earliest="1840", start_latest="1866", end_earliest="1870"
        )
        result = remove_observation(fact, 0)
        assert result.start.earliest == "1840"

    def test_end_latest_unchanged(self) -> None:
        obs = _obs("1866", "1870")
        fact = _fact(
            obs=[obs], end_latest="1890", start_latest="1866", end_earliest="1870"
        )
        result = remove_observation(fact, 0)
        assert result.end.latest == "1890"


class TestRemoveObservationIsPure:
    """The input fact is never mutated."""

    def test_input_fact_unchanged(self) -> None:
        obs1 = _obs("1860", "1865", "s1")
        obs2 = _obs("1866", "1870", "s2")
        fact = _fact(obs=[obs1, obs2], start_latest="1860", end_earliest="1870")
        original_obs_count = len(fact.observations)
        original_start_latest = fact.start.latest
        remove_observation(fact, 0)
        assert len(fact.observations) == original_obs_count
        assert fact.start.latest == original_start_latest

    def test_raises_index_error_on_invalid_index(self) -> None:
        fact = _fact(obs=[_obs("1866", "1870")])
        with pytest.raises(IndexError):
            remove_observation(fact, 1)
        with pytest.raises(IndexError):
            remove_observation(fact, -1)


class TestRemoveObservationEdgeCases:
    """Edge cases for the removal logic."""

    def test_empty_observed_from_or_to(self) -> None:
        """Observations with empty year bounds don't contribute to aggregate."""
        obs1 = _obs("1866", "1870", "s1")
        obs2 = _obs("", "", "s2")  # no years
        fact = _fact(obs=[obs1, obs2], start_latest="1866", end_earliest="1870")
        # Remove obs2 (empty years). Aggregate is still (1866, 1870).
        result = remove_observation(fact, 1)
        assert result.start.latest == "1866"
        assert result.end.earliest == "1870"

    def test_whitespace_stored_bound_treated_as_absent(self) -> None:
        """A whitespace-only stored bound is treated as absent for tightening."""
        obs = _obs("1866", "1870")
        fact = _fact(obs=[obs])
        fact.start.latest = "   "  # whitespace-only
        fact.end.earliest = "   "
        result = attach_observations(fact, [_obs("1871", "1875")])
        # Aggregate from = 1866, to = 1875. Stored is whitespace → treated as absent.
        assert result.start.latest == "1866"
        assert result.end.earliest == "1875"
