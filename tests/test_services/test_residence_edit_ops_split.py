"""Unit tests for split_at_gap and ResidenceSplitError.

Covers partitioning Observations by a coverage gap, assigning new ids,
copying shared fields, keeping the original start/end on the correct sides,
setting core bounds from assigned Observations, leaving outward bounds absent,
and raising when one side has no Observation.

Requirements: 5.10, 5.11, 5.12, 5.13, 5.16.
"""

from __future__ import annotations

import copy

import pytest

from slaktbusken.model.event import SourceRef
from slaktbusken.model.residence import (
    Endpoint,
    Observation,
    ResidenceFact,
)
from slaktbusken.services.residence_coverage import CoverageGap
from slaktbusken.services.residence_edit_ops import (
    ResidenceSplitError,
    split_at_gap,
)


def _obs(from_year: str = "", to_year: str = "", source_id: str = "s1") -> Observation:
    """Helper to build a minimal Observation."""
    return Observation(
        source_ref=SourceRef(source_id=source_id, quality=""),
        observed_from=from_year,
        observed_to=to_year,
    )


def _gap(residence_id: str, first_year: int, last_year: int) -> CoverageGap:
    """Helper to build a CoverageGap."""
    return CoverageGap(
        residence_id=residence_id,
        first_year=first_year,
        last_year=last_year,
        suggestion="",
        splittable=True,
    )


def _fact(
    obs: list[Observation] | None = None,
    start_earliest: str | None = None,
    start_latest: str | None = None,
    end_earliest: str | None = None,
    end_latest: str | None = None,
    role: str = "",
    notes: str = "",
) -> ResidenceFact:
    """Helper to build a minimal ResidenceFact."""
    return ResidenceFact(
        id="r1",
        person_id="p1",
        place_id="pl1",
        start=Endpoint(earliest=start_earliest, latest=start_latest),
        end=Endpoint(earliest=end_earliest, latest=end_latest),
        role_in_household=role,
        observations=obs if obs is not None else [],
        notes=notes,
    )


# ===========================================================================
# Basic split behaviour (Requirement 5.11)
# ===========================================================================


class TestSplitPartitionsObservations:
    """Observations are partitioned by the gap: those ending before go to the
    first fact, those beginning after go to the second (Req 5.11)."""

    def test_simple_two_observations_split(self) -> None:
        obs_before = _obs("1866", "1870")
        obs_after = _obs("1876", "1880")
        fact = _fact(obs=[obs_before, obs_after])
        gap = _gap("r1", 1871, 1875)

        first, second = split_at_gap(fact, gap, ("new1", "new2"))

        assert len(first.observations) == 1
        assert first.observations[0].observed_from == "1866"
        assert first.observations[0].observed_to == "1870"
        assert len(second.observations) == 1
        assert second.observations[0].observed_from == "1876"
        assert second.observations[0].observed_to == "1880"

    def test_multiple_observations_per_side(self) -> None:
        obs1 = _obs("1860", "1865")
        obs2 = _obs("1866", "1870")
        obs3 = _obs("1876", "1880")
        obs4 = _obs("1881", "1885")
        fact = _fact(obs=[obs1, obs2, obs3, obs4])
        gap = _gap("r1", 1871, 1875)

        first, second = split_at_gap(fact, gap, ("new1", "new2"))

        assert len(first.observations) == 2
        assert first.observations[0].observed_from == "1860"
        assert first.observations[1].observed_from == "1866"
        assert len(second.observations) == 2
        assert second.observations[0].observed_from == "1876"
        assert second.observations[1].observed_from == "1881"

    def test_relative_order_preserved(self) -> None:
        """Observations keep their relative order within each side (Req 5.12)."""
        obs1 = _obs("1860", "1862")
        obs2 = _obs("1863", "1865")
        obs3 = _obs("1870", "1872")
        obs4 = _obs("1873", "1875")
        fact = _fact(obs=[obs1, obs2, obs3, obs4])
        gap = _gap("r1", 1866, 1869)

        first, second = split_at_gap(fact, gap, ("a", "b"))

        assert [o.observed_from for o in first.observations] == ["1860", "1863"]
        assert [o.observed_from for o in second.observations] == ["1870", "1873"]

    def test_observation_fields_unchanged(self) -> None:
        """Each Observation keeps source_ref, observed_from, observed_to, and
        page_note unchanged (Req 5.12)."""
        obs_before = Observation(
            source_ref=SourceRef(source_id="src1", quality="primary", note="a note"),
            observed_from="1866",
            observed_to="1870",
            page_note="sid 42",
        )
        obs_after = Observation(
            source_ref=SourceRef(source_id="src2", quality="secondary", note="b note"),
            observed_from="1876",
            observed_to="1880",
            page_note="sid 99",
        )
        fact = _fact(obs=[obs_before, obs_after])
        gap = _gap("r1", 1871, 1875)

        first, second = split_at_gap(fact, gap, ("a", "b"))

        f_obs = first.observations[0]
        assert f_obs.source_ref.source_id == "src1"
        assert f_obs.source_ref.quality == "primary"
        assert f_obs.source_ref.note == "a note"
        assert f_obs.observed_from == "1866"
        assert f_obs.observed_to == "1870"
        assert f_obs.page_note == "sid 42"

        s_obs = second.observations[0]
        assert s_obs.source_ref.source_id == "src2"
        assert s_obs.source_ref.quality == "secondary"
        assert s_obs.source_ref.note == "b note"
        assert s_obs.observed_from == "1876"
        assert s_obs.observed_to == "1880"
        assert s_obs.page_note == "sid 99"


# ===========================================================================
# New ids and copied fields (Requirement 5.12)
# ===========================================================================


class TestSplitNewIdsAndCopiedFields:
    """Both facts get new ids and copies of person_id, place_id,
    role_in_household, notes (Req 5.12)."""

    def test_new_ids_assigned(self) -> None:
        fact = _fact(obs=[_obs("1866", "1870"), _obs("1876", "1880")])
        gap = _gap("r1", 1871, 1875)

        first, second = split_at_gap(fact, gap, ("id_a", "id_b"))

        assert first.id == "id_a"
        assert second.id == "id_b"

    def test_person_id_copied(self) -> None:
        fact = _fact(obs=[_obs("1866", "1870"), _obs("1876", "1880")])
        fact.person_id = "person_42"
        gap = _gap("r1", 1871, 1875)

        first, second = split_at_gap(fact, gap, ("a", "b"))

        assert first.person_id == "person_42"
        assert second.person_id == "person_42"

    def test_place_id_copied(self) -> None:
        fact = _fact(obs=[_obs("1866", "1870"), _obs("1876", "1880")])
        fact.place_id = "place_99"
        gap = _gap("r1", 1871, 1875)

        first, second = split_at_gap(fact, gap, ("a", "b"))

        assert first.place_id == "place_99"
        assert second.place_id == "place_99"

    def test_role_in_household_copied(self) -> None:
        fact = _fact(
            obs=[_obs("1866", "1870"), _obs("1876", "1880")],
            role="Dräng",
        )
        gap = _gap("r1", 1871, 1875)

        first, second = split_at_gap(fact, gap, ("a", "b"))

        assert first.role_in_household == "Dräng"
        assert second.role_in_household == "Dräng"

    def test_notes_copied(self) -> None:
        fact = _fact(
            obs=[_obs("1866", "1870"), _obs("1876", "1880")],
            notes="En anteckning",
        )
        gap = _gap("r1", 1871, 1875)

        first, second = split_at_gap(fact, gap, ("a", "b"))

        assert first.notes == "En anteckning"
        assert second.notes == "En anteckning"


# ===========================================================================
# Endpoint handling (Requirements 5.12, 5.13)
# ===========================================================================


class TestSplitEndpoints:
    """Original start kept on first, original end on second; the new inner
    bounds are derived from observations with outward bounds absent."""

    def test_original_start_kept_on_first(self) -> None:
        """First fact keeps the original start endpoint (Req 5.12)."""
        fact = _fact(
            obs=[_obs("1866", "1870"), _obs("1876", "1880")],
            start_earliest="1860",
            start_latest="1865",
        )
        fact.start.precision = "year"
        fact.start.event_id = "evt1"
        fact.start.note = "Start note"
        gap = _gap("r1", 1871, 1875)

        first, _ = split_at_gap(fact, gap, ("a", "b"))

        assert first.start.earliest == "1860"
        assert first.start.latest == "1865"
        assert first.start.precision == "year"
        assert first.start.event_id == "evt1"
        assert first.start.note == "Start note"

    def test_original_end_kept_on_second(self) -> None:
        """Second fact keeps the original end endpoint (Req 5.12)."""
        fact = _fact(
            obs=[_obs("1866", "1870"), _obs("1876", "1880")],
            end_earliest="1882",
            end_latest="1885",
        )
        fact.end.precision = "month"
        fact.end.event_id = "evt2"
        fact.end.note = "End note"
        gap = _gap("r1", 1871, 1875)

        _, second = split_at_gap(fact, gap, ("a", "b"))

        assert second.end.earliest == "1882"
        assert second.end.latest == "1885"
        assert second.end.precision == "month"
        assert second.end.event_id == "evt2"
        assert second.end.note == "End note"

    def test_first_end_earliest_from_observations(self) -> None:
        """First fact's end.earliest = highest observed_to of its observations (Req 5.13)."""
        fact = _fact(obs=[_obs("1860", "1865"), _obs("1866", "1870"), _obs("1876", "1880")])
        gap = _gap("r1", 1871, 1875)

        first, _ = split_at_gap(fact, gap, ("a", "b"))

        # Highest observed_to among before-gap observations: 1870
        assert first.end.earliest == "1870"

    def test_second_start_latest_from_observations(self) -> None:
        """Second fact's start.latest = lowest observed_from of its observations (Req 5.13)."""
        fact = _fact(obs=[_obs("1866", "1870"), _obs("1876", "1880"), _obs("1881", "1885")])
        gap = _gap("r1", 1871, 1875)

        _, second = split_at_gap(fact, gap, ("a", "b"))

        # Lowest observed_from among after-gap observations: 1876
        assert second.start.latest == "1876"

    def test_first_end_latest_absent(self) -> None:
        """First fact's end.latest is left absent (Req 5.13)."""
        fact = _fact(
            obs=[_obs("1866", "1870"), _obs("1876", "1880")],
            end_latest="1885",
        )
        gap = _gap("r1", 1871, 1875)

        first, _ = split_at_gap(fact, gap, ("a", "b"))

        assert first.end.latest is None

    def test_second_start_earliest_absent(self) -> None:
        """Second fact's start.earliest is left absent (Req 5.13)."""
        fact = _fact(
            obs=[_obs("1866", "1870"), _obs("1876", "1880")],
            start_earliest="1860",
        )
        gap = _gap("r1", 1871, 1875)

        _, second = split_at_gap(fact, gap, ("a", "b"))

        assert second.start.earliest is None

    def test_new_inner_endpoints_have_no_precision_event_note(self) -> None:
        """The new inner endpoints have no precision, event_id or note."""
        fact = _fact(obs=[_obs("1866", "1870"), _obs("1876", "1880")])
        gap = _gap("r1", 1871, 1875)

        first, second = split_at_gap(fact, gap, ("a", "b"))

        # First fact's new end endpoint
        assert first.end.precision is None
        assert first.end.event_id is None
        assert first.end.note is None
        # Second fact's new start endpoint
        assert second.start.precision is None
        assert second.start.event_id is None
        assert second.start.note is None


# ===========================================================================
# Error case: one side has no Observation (Requirement 5.16)
# ===========================================================================


class TestSplitRaisesOnEmptySide:
    """ResidenceSplitError is raised when one side has no Observation (Req 5.16)."""

    def test_all_observations_before_gap(self) -> None:
        fact = _fact(obs=[_obs("1866", "1870"), _obs("1871", "1875")])
        gap = _gap("r1", 1876, 1880)

        with pytest.raises(ResidenceSplitError):
            split_at_gap(fact, gap, ("a", "b"))

    def test_all_observations_after_gap(self) -> None:
        fact = _fact(obs=[_obs("1876", "1880"), _obs("1881", "1885")])
        gap = _gap("r1", 1871, 1875)

        with pytest.raises(ResidenceSplitError):
            split_at_gap(fact, gap, ("a", "b"))

    def test_error_message_mentions_one_side(self) -> None:
        fact = _fact(obs=[_obs("1866", "1870")])
        gap = _gap("r1", 1871, 1875)

        with pytest.raises(ResidenceSplitError, match="en sida"):
            split_at_gap(fact, gap, ("a", "b"))

    def test_observations_with_no_years_only(self) -> None:
        """Observations with no parseable years cannot be classified and
        result in empty sides."""
        fact = _fact(obs=[_obs("", ""), _obs("", "")])
        gap = _gap("r1", 1871, 1875)

        with pytest.raises(ResidenceSplitError):
            split_at_gap(fact, gap, ("a", "b"))

    def test_single_observation_cannot_be_split(self) -> None:
        """A gap that leaves only one Observation means the other side is empty."""
        fact = _fact(obs=[_obs("1866", "1870")])
        gap = _gap("r1", 1871, 1875)

        with pytest.raises(ResidenceSplitError):
            split_at_gap(fact, gap, ("a", "b"))


# ===========================================================================
# Purity: original fact is not mutated
# ===========================================================================


class TestSplitIsPure:
    """split_at_gap does not mutate its inputs."""

    def test_original_fact_unchanged(self) -> None:
        obs1 = _obs("1866", "1870")
        obs2 = _obs("1876", "1880")
        fact = _fact(
            obs=[obs1, obs2],
            start_earliest="1860",
            start_latest="1865",
            end_earliest="1882",
            end_latest="1885",
            role="Bonde",
            notes="Original notes",
        )
        fact_copy = copy.deepcopy(fact)
        gap = _gap("r1", 1871, 1875)

        split_at_gap(fact, gap, ("a", "b"))

        # All fields on the original fact should be unchanged
        assert fact.id == fact_copy.id
        assert fact.person_id == fact_copy.person_id
        assert fact.place_id == fact_copy.place_id
        assert fact.start.earliest == fact_copy.start.earliest
        assert fact.start.latest == fact_copy.start.latest
        assert fact.end.earliest == fact_copy.end.earliest
        assert fact.end.latest == fact_copy.end.latest
        assert fact.role_in_household == fact_copy.role_in_household
        assert fact.notes == fact_copy.notes
        assert len(fact.observations) == len(fact_copy.observations)
        for orig, cp in zip(fact.observations, fact_copy.observations):
            assert orig.observed_from == cp.observed_from
            assert orig.observed_to == cp.observed_to

    def test_mutating_result_does_not_affect_original(self) -> None:
        fact = _fact(obs=[_obs("1866", "1870"), _obs("1876", "1880")])
        gap = _gap("r1", 1871, 1875)

        first, second = split_at_gap(fact, gap, ("a", "b"))

        # Mutate the results
        first.observations.append(_obs("1900", "1905"))
        second.person_id = "changed"

        # Original should be unaffected
        assert len(fact.observations) == 2
        assert fact.person_id == "p1"


# ===========================================================================
# Edge cases
# ===========================================================================


class TestSplitEdgeCases:
    """Edge cases for the split logic."""

    def test_single_year_gap(self) -> None:
        """A gap spanning a single year still splits correctly."""
        fact = _fact(obs=[_obs("1866", "1870"), _obs("1872", "1876")])
        gap = _gap("r1", 1871, 1871)

        first, second = split_at_gap(fact, gap, ("a", "b"))

        assert len(first.observations) == 1
        assert len(second.observations) == 1
        assert first.end.earliest == "1870"
        assert second.start.latest == "1872"

    def test_observation_with_only_observed_to_before_gap(self) -> None:
        """An observation with only observed_to that's before the gap
        goes to the first side (single year coverage per Req 4.6)."""
        fact = _fact(obs=[_obs("", "1870"), _obs("1876", "1880")])
        gap = _gap("r1", 1871, 1875)

        first, second = split_at_gap(fact, gap, ("a", "b"))

        assert len(first.observations) == 1
        assert first.observations[0].observed_to == "1870"
        assert len(second.observations) == 1

    def test_observation_with_only_observed_from_after_gap(self) -> None:
        """An observation with only observed_from that's after the gap
        goes to the second side (single year coverage per Req 4.6)."""
        fact = _fact(obs=[_obs("1866", "1870"), _obs("1876", "")])
        gap = _gap("r1", 1871, 1875)

        first, second = split_at_gap(fact, gap, ("a", "b"))

        assert len(first.observations) == 1
        assert len(second.observations) == 1
        assert second.observations[0].observed_from == "1876"

    def test_combined_observations_yield_all_present_on_both_sides(self) -> None:
        """The combined set of Observations across both sides equals
        the classifiable set from the original (Req 5.12 conservation)."""
        obs_list = [
            _obs("1860", "1862"),
            _obs("1863", "1865"),
            _obs("1866", "1870"),
            _obs("1876", "1878"),
            _obs("1879", "1880"),
            _obs("1881", "1885"),
        ]
        fact = _fact(obs=obs_list)
        gap = _gap("r1", 1871, 1875)

        first, second = split_at_gap(fact, gap, ("a", "b"))

        all_from_split = [
            (o.observed_from, o.observed_to) for o in first.observations
        ] + [
            (o.observed_from, o.observed_to) for o in second.observations
        ]
        all_original = [(o.observed_from, o.observed_to) for o in obs_list]
        assert all_from_split == all_original
