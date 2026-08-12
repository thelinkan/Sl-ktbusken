# Feature: residence-periods, Property 15: Splitting partitions, re-bounds and conserves
"""Property-based test for split_at_gap.

Feature: residence-periods, Property 15: Splitting partitions, re-bounds and conserves

For any Residence_Fact and any reported coverage gap having at least one Observation ending
before it and one beginning after it, splitting yields exactly two Residence_Facts with new
unique ids and copied person_id, place_id, role_in_household and notes; the original start
stays on the first and the original end on the second, the first end.earliest equals the
highest observed_to assigned to it and the second start.latest the lowest observed_from
assigned to it, the first end.latest and second start.earliest are absent, and the combined
Observation set equals the original with each Observation appearing once, unchanged, in its
original relative order within each side; the split action is offered exactly for gaps meeting
the two-sided condition and refused with an error otherwise, leaving the fact unchanged.

**Validates: Requirements 5.10, 5.11, 5.12, 5.13, 5.16**
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from slaktbusken.model.residence import (
    Endpoint,
    Observation,
    ResidenceFact,
    core_aggregate,
    observation_span_years,
)
from slaktbusken.services.residence_coverage import CoverageGap
from slaktbusken.services.residence_edit_ops import split_at_gap, ResidenceSplitError
from tests.test_model.residence_strategies import observations, residence_facts


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def _splittable_fact_and_gap(draw):
    """Generate a ResidenceFact with at least two observations separated by a gap.

    The strategy constructs observations in two groups: a "before" group whose
    observed_to is below the gap, and an "after" group whose observed_from is
    above the gap. This guarantees the gap is splittable.
    """
    # Pick a gap region somewhere in the middle of the plausible range.
    gap_start = draw(st.integers(min_value=1600, max_value=1900))
    gap_end = draw(st.integers(min_value=gap_start, max_value=gap_start + 20))

    # Generate 1-5 observations ending before the gap.
    before_count = draw(st.integers(min_value=1, max_value=5))
    before_obs: list[Observation] = []
    for _ in range(before_count):
        obs_from = draw(st.integers(min_value=1500, max_value=gap_start - 2))
        obs_to = draw(st.integers(min_value=obs_from, max_value=gap_start - 1))
        before_obs.append(
            draw(observations(shape="ordered", min_year=obs_from, max_year=obs_to))
        )
        # Override the years to ensure they are before the gap.
        before_obs[-1] = Observation(
            source_ref=before_obs[-1].source_ref,
            observed_from=f"{obs_from:04d}",
            observed_to=f"{obs_to:04d}",
            page_note=before_obs[-1].page_note,
        )

    # Generate 1-5 observations beginning after the gap.
    after_count = draw(st.integers(min_value=1, max_value=5))
    after_obs: list[Observation] = []
    for _ in range(after_count):
        obs_from = draw(st.integers(min_value=gap_end + 1, max_value=2050))
        obs_to = draw(st.integers(min_value=obs_from, max_value=2100))
        after_obs.append(
            draw(observations(shape="ordered", min_year=obs_from, max_year=obs_to))
        )
        # Override the years to ensure they are after the gap.
        after_obs[-1] = Observation(
            source_ref=after_obs[-1].source_ref,
            observed_from=f"{obs_from:04d}",
            observed_to=f"{obs_to:04d}",
            page_note=after_obs[-1].page_note,
        )

    all_obs = before_obs + after_obs

    # Build a fact with these observations and well-formed endpoints.
    fact = draw(
        residence_facts(
            observation_count=0,
            include_many_observations=False,
            include_blank_references=False,
            shape="ordered",
        )
    )
    fact = ResidenceFact(
        id=fact.id,
        person_id=fact.person_id,
        place_id=fact.place_id,
        start=fact.start,
        end=fact.end,
        role_in_household=fact.role_in_household,
        observations=all_obs,
        notes=fact.notes,
    )

    gap = CoverageGap(
        residence_id=fact.id,
        first_year=gap_start,
        last_year=gap_end,
        suggestion="",
        splittable=True,
    )

    new_id_1 = draw(st.text(alphabet="abcdefghijk0123456789_", min_size=4, max_size=12))
    new_id_2 = draw(
        st.text(alphabet="abcdefghijk0123456789_", min_size=4, max_size=12).filter(
            lambda x: x != new_id_1
        )
    )

    return fact, gap, (new_id_1, new_id_2)


@st.composite
def _one_sided_fact_and_gap(draw):
    """Generate a ResidenceFact where all observations are on one side of a gap.

    This is the case where split_at_gap should raise ResidenceSplitError.
    """
    gap_start = draw(st.integers(min_value=1700, max_value=1900))
    gap_end = draw(st.integers(min_value=gap_start, max_value=gap_start + 10))

    # Generate observations all on one side.
    side = draw(st.sampled_from(["before", "after"]))
    count = draw(st.integers(min_value=1, max_value=4))
    obs_list: list[Observation] = []
    for _ in range(count):
        if side == "before":
            obs_from = draw(st.integers(min_value=1500, max_value=gap_start - 2))
            obs_to = draw(st.integers(min_value=obs_from, max_value=gap_start - 1))
        else:
            obs_from = draw(st.integers(min_value=gap_end + 1, max_value=2050))
            obs_to = draw(st.integers(min_value=obs_from, max_value=2100))
        obs_list.append(
            Observation(
                source_ref=draw(observations(shape="ordered")).source_ref,
                observed_from=f"{obs_from:04d}",
                observed_to=f"{obs_to:04d}",
                page_note="",
            )
        )

    fact = draw(
        residence_facts(
            observation_count=0,
            include_many_observations=False,
            include_blank_references=False,
            shape="ordered",
        )
    )
    fact = ResidenceFact(
        id=fact.id,
        person_id=fact.person_id,
        place_id=fact.place_id,
        start=fact.start,
        end=fact.end,
        role_in_household=fact.role_in_household,
        observations=obs_list,
        notes=fact.notes,
    )

    gap = CoverageGap(
        residence_id=fact.id,
        first_year=gap_start,
        last_year=gap_end,
        suggestion="",
        splittable=False,
    )

    return fact, gap


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestSplittingProperty:
    """Property 15: Splitting partitions, re-bounds and conserves.

    **Validates: Requirements 5.10, 5.11, 5.12, 5.13, 5.16**
    """

    @given(data=_splittable_fact_and_gap())
    @settings(max_examples=100, deadline=None)
    def test_splitting_partitions_rebounds_and_conserves(
        self,
        data: tuple[ResidenceFact, CoverageGap, tuple[str, str]],
    ) -> None:
        """Splitting partitions observations by the gap, re-bounds and conserves metadata.

        Feature: residence-periods, Property 15: Splitting partitions, re-bounds and conserves

        **Validates: Requirements 5.10, 5.11, 5.12, 5.13, 5.16**
        """
        fact, gap, new_ids = data

        first, second = split_at_gap(fact, gap, new_ids)

        # --- Assertion 1: New unique ids are assigned (Req 5.12) ---
        assert first.id == new_ids[0]
        assert second.id == new_ids[1]
        assert first.id != second.id
        assert first.id != fact.id
        assert second.id != fact.id

        # --- Assertion 2: person_id, place_id, role_in_household, notes copied (Req 5.12) ---
        assert first.person_id == fact.person_id
        assert second.person_id == fact.person_id
        assert first.place_id == fact.place_id
        assert second.place_id == fact.place_id
        assert first.role_in_household == fact.role_in_household
        assert second.role_in_household == fact.role_in_household
        assert first.notes == fact.notes
        assert second.notes == fact.notes

        # --- Assertion 3: Original start on first, original end on second (Req 5.12) ---
        assert first.start.earliest == fact.start.earliest
        assert first.start.latest == fact.start.latest
        assert first.start.precision == fact.start.precision
        assert first.start.event_id == fact.start.event_id
        assert first.start.note == fact.start.note

        assert second.end.earliest == fact.end.earliest
        assert second.end.latest == fact.end.latest
        assert second.end.precision == fact.end.precision
        assert second.end.event_id == fact.end.event_id
        assert second.end.note == fact.end.note

        # --- Assertion 4: Core bounds from assigned observations (Req 5.12) ---
        _, first_highest_to = core_aggregate(first.observations)
        second_lowest_from, _ = core_aggregate(second.observations)

        assert first.end.earliest == first_highest_to, (
            f"First end.earliest should be {first_highest_to!r}, got {first.end.earliest!r}"
        )
        assert second.start.latest == second_lowest_from, (
            f"Second start.latest should be {second_lowest_from!r}, got {second.start.latest!r}"
        )

        # --- Assertion 5: Outward bounds absent on new inner endpoints (Req 5.13) ---
        assert first.end.latest is None, (
            f"First end.latest should be absent, got {first.end.latest!r}"
        )
        assert second.start.earliest is None, (
            f"Second start.earliest should be absent, got {second.start.earliest!r}"
        )

        # --- Assertion 6: Observations are partitioned by the gap (Req 5.11) ---
        # Every observation in first should end before the gap.
        for obs in first.observations:
            span = observation_span_years(obs)
            assert span is not None, "First-side obs must have a span"
            assert span[1] < gap.first_year, (
                f"First-side obs ends at {span[1]}, but gap starts at {gap.first_year}"
            )

        # Every observation in second should begin after the gap.
        for obs in second.observations:
            span = observation_span_years(obs)
            assert span is not None, "Second-side obs must have a span"
            assert span[0] > gap.last_year, (
                f"Second-side obs starts at {span[0]}, but gap ends at {gap.last_year}"
            )

        # --- Assertion 7: Combined set equals original classifiable obs (Req 5.13) ---
        # Collect classifiable observations from the original that clearly belong
        # to one side of the gap.
        original_before = []
        original_after = []
        for obs in fact.observations:
            span = observation_span_years(obs)
            if span is None:
                continue
            if span[1] < gap.first_year:
                original_before.append(obs)
            elif span[0] > gap.last_year:
                original_after.append(obs)

        # Each observation appears exactly once, unchanged.
        assert len(first.observations) == len(original_before)
        assert len(second.observations) == len(original_after)

        for orig, split_obs in zip(original_before, first.observations):
            assert split_obs.source_ref.source_id == orig.source_ref.source_id
            assert split_obs.observed_from == orig.observed_from
            assert split_obs.observed_to == orig.observed_to
            assert split_obs.page_note == orig.page_note

        for orig, split_obs in zip(original_after, second.observations):
            assert split_obs.source_ref.source_id == orig.source_ref.source_id
            assert split_obs.observed_from == orig.observed_from
            assert split_obs.observed_to == orig.observed_to
            assert split_obs.page_note == orig.page_note

    @given(data=_one_sided_fact_and_gap())
    @settings(max_examples=100, deadline=None)
    def test_splitting_raises_when_one_side_has_no_observation(
        self,
        data: tuple[ResidenceFact, CoverageGap],
    ) -> None:
        """Splitting raises ResidenceSplitError when one side has no observation.

        Feature: residence-periods, Property 15: Splitting partitions, re-bounds and conserves

        **Validates: Requirements 5.10, 5.11, 5.12, 5.13, 5.16**
        """
        fact, gap = data

        with pytest.raises(ResidenceSplitError):
            split_at_gap(fact, gap, ("new_id_1", "new_id_2"))
