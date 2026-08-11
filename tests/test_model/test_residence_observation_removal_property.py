# Feature: residence-periods, Property 32: Removal preserves survivors and hand-entered bounds
"""Property-based test for observation removal.

Feature: residence-periods, Property 32: Removal preserves survivors and hand-entered bounds

After removing an Observation, survivors keep their original relative order and are
byte-identical; a core bound that equals the pre-removal aggregate is recomputed from
survivors; a hand-entered bound (one differing from the aggregate) survives unchanged;
start.earliest and end.latest are never touched.

**Validates: Requirements 16.7, 16.8**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.residence import (
    Endpoint,
    Observation,
    ResidenceFact,
    core_aggregate,
)
from slaktbusken.services.residence_edit_ops import remove_observation
from tests.test_model.residence_strategies import observations, residence_facts


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def _fact_with_removal_scenario(draw: DrawFn) -> tuple[ResidenceFact, int, bool]:
    """Generate a ResidenceFact with at least 2 observations and a removal index.

    Returns (fact, removal_index, has_hand_entered_bound).

    To test both code paths (observation-derived vs hand-entered), we sometimes
    set a core bound to the pre-removal aggregate (observation-derived) and
    sometimes to a different value (hand-entered).
    """
    # Generate a fact with 2-6 ordered observations so core_aggregate is meaningful.
    fact = draw(residence_facts(
        include_many_observations=False,
        max_observations=6,
        include_blank_references=False,
        shape="ordered",
        observation_count=draw(st.integers(min_value=2, max_value=6)),
    ))

    index = draw(st.integers(min_value=0, max_value=len(fact.observations) - 1))

    # Determine whether to make the core bounds match the aggregate (observation-derived)
    # or differ from it (hand-entered).
    hand_entered = draw(st.booleans())

    agg_from, agg_to = core_aggregate(fact.observations)

    if hand_entered:
        # Make start.latest and/or end.earliest differ from the aggregate.
        # This simulates a hand-entered bound.
        hand_start_latest = draw(st.sampled_from(["1799", "1600", "1500", None]))
        hand_end_earliest = draw(st.sampled_from(["2050", "2090", "2100", None]))
        new_start = Endpoint(
            earliest=fact.start.earliest,
            latest=hand_start_latest,
            precision=fact.start.precision,
            event_id=fact.start.event_id,
            note=fact.start.note,
        )
        new_end = Endpoint(
            earliest=hand_end_earliest,
            latest=fact.end.latest,
            precision=fact.end.precision,
            event_id=fact.end.event_id,
            note=fact.end.note,
        )
    else:
        # Make core bounds equal the aggregate (observation-derived).
        new_start = Endpoint(
            earliest=fact.start.earliest,
            latest=agg_from,
            precision=fact.start.precision,
            event_id=fact.start.event_id,
            note=fact.start.note,
        )
        new_end = Endpoint(
            earliest=agg_to,
            latest=fact.end.latest,
            precision=fact.end.precision,
            event_id=fact.end.event_id,
            note=fact.end.note,
        )

    fact = ResidenceFact(
        id=fact.id,
        person_id=fact.person_id,
        place_id=fact.place_id,
        start=new_start,
        end=new_end,
        role_in_household=fact.role_in_household,
        observations=fact.observations,
        notes=fact.notes,
    )

    return fact, index, hand_entered


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestObservationRemovalProperty:
    """Property 32: Removal preserves survivors and hand-entered bounds.

    After removing an Observation, survivors keep their original relative order and are
    byte-identical; a core bound that equals the pre-removal aggregate is recomputed from
    survivors; a hand-entered bound (one differing from the aggregate) survives unchanged;
    start.earliest and end.latest are never touched.

    **Validates: Requirements 16.7, 16.8**
    """

    @given(scenario=_fact_with_removal_scenario())
    @settings(max_examples=100, deadline=None)
    def test_removal_preserves_survivors_and_hand_entered_bounds(
        self,
        scenario: tuple[ResidenceFact, int, bool],
    ) -> None:
        """Removal preserves survivors byte-identical, recomputes derived bounds, keeps hand-entered ones.

        Feature: residence-periods, Property 32: Removal preserves survivors and hand-entered bounds

        **Validates: Requirements 16.7, 16.8**
        """
        fact, index, hand_entered = scenario

        # Record pre-removal state.
        original_start_earliest = fact.start.earliest
        original_end_latest = fact.end.latest
        original_start_latest = fact.start.latest
        original_end_earliest = fact.end.earliest
        original_observations = list(fact.observations)
        pre_agg_from, pre_agg_to = core_aggregate(original_observations)

        # Compute expected survivors.
        expected_survivors = [
            obs for i, obs in enumerate(original_observations) if i != index
        ]

        # Perform removal.
        result = remove_observation(fact, index)

        # --- Assertion 1: Survivors keep their original relative order and are byte-identical ---
        assert len(result.observations) == len(expected_survivors)
        for result_obs, expected_obs in zip(result.observations, expected_survivors):
            assert result_obs.source_ref.source_id == expected_obs.source_ref.source_id
            assert result_obs.source_ref.quality == expected_obs.source_ref.quality
            assert result_obs.source_ref.note == expected_obs.source_ref.note
            assert result_obs.source_ref.aspects == expected_obs.source_ref.aspects
            assert result_obs.observed_from == expected_obs.observed_from
            assert result_obs.observed_to == expected_obs.observed_to
            assert result_obs.page_note == expected_obs.page_note

        # --- Assertion 2: Core bound recomputation vs hand-entered preservation ---
        post_agg_from, post_agg_to = core_aggregate(expected_survivors)

        # For start.latest:
        if _values_equal(original_start_latest, pre_agg_from):
            # Observation-derived → recomputed from survivors.
            assert result.start.latest == post_agg_from, (
                f"start.latest should be recomputed to {post_agg_from!r} "
                f"(was observation-derived {original_start_latest!r}), "
                f"got {result.start.latest!r}"
            )
        else:
            # Hand-entered → preserved unchanged.
            assert result.start.latest == original_start_latest, (
                f"start.latest should stay {original_start_latest!r} (hand-entered), "
                f"got {result.start.latest!r}"
            )

        # For end.earliest:
        if _values_equal(original_end_earliest, pre_agg_to):
            # Observation-derived → recomputed from survivors.
            assert result.end.earliest == post_agg_to, (
                f"end.earliest should be recomputed to {post_agg_to!r} "
                f"(was observation-derived {original_end_earliest!r}), "
                f"got {result.end.earliest!r}"
            )
        else:
            # Hand-entered → preserved unchanged.
            assert result.end.earliest == original_end_earliest, (
                f"end.earliest should stay {original_end_earliest!r} (hand-entered), "
                f"got {result.end.earliest!r}"
            )

        # --- Assertion 3: start.earliest and end.latest are NEVER touched ---
        assert result.start.earliest == original_start_earliest, (
            f"start.earliest was modified: {original_start_earliest!r} -> {result.start.earliest!r}"
        )
        assert result.end.latest == original_end_latest, (
            f"end.latest was modified: {original_end_latest!r} -> {result.end.latest!r}"
        )


# ---------------------------------------------------------------------------
# Helper (mirrors the implementation's comparison logic)
# ---------------------------------------------------------------------------


def _values_equal(stored: str | None, aggregate: str | None) -> bool:
    """Whether the stored value equals the aggregate (both as trimmed strings).

    Mirrors the implementation's comparison: both None → equal; one None → not equal;
    otherwise trimmed string comparison.
    """
    if stored is None and aggregate is None:
        return True
    if stored is None or aggregate is None:
        return False
    return stored.strip() == aggregate.strip()
