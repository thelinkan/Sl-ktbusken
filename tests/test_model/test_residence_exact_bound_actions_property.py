# Feature: residence-periods, Property 33: The exact-bound actions are the only route from an Observation to an outer bound
"""Property-based test for exact-bound actions.

Feature: residence-periods, Property 33: The exact-bound actions are the only route from an Observation to an outer bound

`use_as_exact_start` sets both start bounds to obs.observed_from;
`use_as_exact_end` sets both end bounds to obs.observed_to;
`attach_observations` never touches the outer bounds (start.earliest, end.latest);
both exact-bound functions leave all other fields unchanged;
the functions are the only route from an Observation to an outer bound.

**Validates: Requirements 16.10**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.residence import Observation, ResidenceFact
from slaktbusken.services.residence_edit_ops import (
    attach_observations,
    use_as_exact_end,
    use_as_exact_start,
)
from tests.test_model.residence_strategies import observations, residence_facts


class TestExactBoundActionsProperty:
    """Property 33: The exact-bound actions are the only route from an Observation to an outer bound.

    `use_as_exact_start` sets both start bounds to obs.observed_from;
    `use_as_exact_end` sets both end bounds to obs.observed_to;
    `attach_observations` never touches the outer bounds;
    both exact-bound functions leave all other fields unchanged.

    **Validates: Requirements 16.10**
    """

    @given(
        fact=residence_facts(
            include_many_observations=False,
            max_observations=4,
            include_blank_references=False,
        ),
        obs=observations(shape="ordered"),
    )
    @settings(max_examples=100, deadline=None)
    def test_exact_bound_actions_are_only_route_to_outer_bounds(
        self,
        fact: ResidenceFact,
        obs: Observation,
    ) -> None:
        """The exact-bound actions set outer bounds from an Observation; attach_observations never does.

        Feature: residence-periods, Property 33: The exact-bound actions are the only route from an Observation to an outer bound

        **Validates: Requirements 16.10**
        """
        # --- use_as_exact_start: sets both start bounds to obs.observed_from ---
        result_start = use_as_exact_start(fact, obs)

        assert result_start.start.earliest == obs.observed_from, (
            f"use_as_exact_start should set start.earliest to {obs.observed_from!r}, "
            f"got {result_start.start.earliest!r}"
        )
        assert result_start.start.latest == obs.observed_from, (
            f"use_as_exact_start should set start.latest to {obs.observed_from!r}, "
            f"got {result_start.start.latest!r}"
        )

        # --- use_as_exact_start: leaves all other fields unchanged ---
        assert result_start.end.earliest == fact.end.earliest
        assert result_start.end.latest == fact.end.latest
        assert result_start.end.precision == fact.end.precision
        assert result_start.end.event_id == fact.end.event_id
        assert result_start.end.note == fact.end.note
        assert result_start.start.precision == fact.start.precision
        assert result_start.start.event_id == fact.start.event_id
        assert result_start.start.note == fact.start.note
        assert result_start.id == fact.id
        assert result_start.person_id == fact.person_id
        assert result_start.place_id == fact.place_id
        assert result_start.role_in_household == fact.role_in_household
        assert result_start.notes == fact.notes
        assert len(result_start.observations) == len(fact.observations)

        # --- use_as_exact_end: sets both end bounds to obs.observed_to ---
        result_end = use_as_exact_end(fact, obs)

        assert result_end.end.earliest == obs.observed_to, (
            f"use_as_exact_end should set end.earliest to {obs.observed_to!r}, "
            f"got {result_end.end.earliest!r}"
        )
        assert result_end.end.latest == obs.observed_to, (
            f"use_as_exact_end should set end.latest to {obs.observed_to!r}, "
            f"got {result_end.end.latest!r}"
        )

        # --- use_as_exact_end: leaves all other fields unchanged ---
        assert result_end.start.earliest == fact.start.earliest
        assert result_end.start.latest == fact.start.latest
        assert result_end.start.precision == fact.start.precision
        assert result_end.start.event_id == fact.start.event_id
        assert result_end.start.note == fact.start.note
        assert result_end.end.precision == fact.end.precision
        assert result_end.end.event_id == fact.end.event_id
        assert result_end.end.note == fact.end.note
        assert result_end.id == fact.id
        assert result_end.person_id == fact.person_id
        assert result_end.place_id == fact.place_id
        assert result_end.role_in_household == fact.role_in_household
        assert result_end.notes == fact.notes
        assert len(result_end.observations) == len(fact.observations)

        # --- attach_observations: never touches outer bounds (start.earliest, end.latest) ---
        # This proves the exact-bound functions are the ONLY route to outer bounds.
        result_attach = attach_observations(fact, [obs])

        assert result_attach.start.earliest == fact.start.earliest, (
            f"attach_observations must not touch start.earliest: "
            f"{fact.start.earliest!r} -> {result_attach.start.earliest!r}"
        )
        assert result_attach.end.latest == fact.end.latest, (
            f"attach_observations must not touch end.latest: "
            f"{fact.end.latest!r} -> {result_attach.end.latest!r}"
        )
