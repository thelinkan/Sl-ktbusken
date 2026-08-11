# Feature: residence-periods, Property 10: Observation order is preserved through every list operation
"""Property-based test for observation order.

Feature: residence-periods, Property 10: Observation order is preserved through every list operation

For any Residence_Fact and sequence of attach/remove operations, `attach_observations`
appends new Observations in order after existing ones; `remove_observation` keeps
survivors in their original relative order and byte-identical; and repeated
attach+remove cycles preserve the order contract throughout.

**Validates: Requirements 4.3, 16.12**
"""

from __future__ import annotations

import copy

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.residence import Observation, ResidenceFact
from slaktbusken.services.residence_edit_ops import attach_observations, remove_observation
from tests.test_model.residence_strategies import observations, residence_facts


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def _attach_remove_scenario(draw: DrawFn) -> tuple[
    ResidenceFact,
    list[tuple[str, list[Observation] | int]],
]:
    """Generate a Residence_Fact and a sequence of attach/remove operations.

    Each operation is either ("attach", [obs_list]) or ("remove", index). The
    sequence is generated so that removal indices are always valid for the
    current observation count at that point in the replay.
    """
    fact = draw(residence_facts(
        include_many_observations=False,
        max_observations=5,
        include_blank_references=False,
        shape="ordered",
    ))

    op_count = draw(st.integers(min_value=1, max_value=8))
    operations: list[tuple[str, list[Observation] | int]] = []
    current_count = len(fact.observations)

    for _ in range(op_count):
        if current_count == 0 or draw(st.integers(min_value=0, max_value=2)) > 0:
            # Attach 1–3 new observations.
            batch_size = draw(st.integers(min_value=1, max_value=3))
            batch = [
                draw(observations(shape="ordered"))
                for _ in range(batch_size)
            ]
            operations.append(("attach", batch))
            current_count += batch_size
        else:
            # Remove an observation at a valid index.
            index = draw(st.integers(min_value=0, max_value=current_count - 1))
            operations.append(("remove", index))
            current_count -= 1

    return fact, operations


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestObservationOrderProperty:
    """Property 10: Observation order is preserved through every list operation.

    `attach_observations` appends new Observations in order after existing ones;
    `remove_observation` keeps survivors in their original relative order and
    byte-identical; repeated attach+remove cycles preserve the order contract.

    **Validates: Requirements 4.3, 16.12**
    """

    @given(
        fact=residence_facts(
            include_many_observations=False,
            max_observations=4,
            include_blank_references=False,
            shape="ordered",
        ),
        new_obs=st.lists(observations(shape="ordered"), min_size=1, max_size=5),
    )
    @settings(max_examples=100, deadline=None)
    def test_attach_appends_in_order_after_existing(
        self,
        fact: ResidenceFact,
        new_obs: list[Observation],
    ) -> None:
        """attach_observations appends new observations in order after existing ones.

        Feature: residence-periods, Property 10: Observation order is preserved through every list operation

        **Validates: Requirements 4.3**
        """
        original_obs = list(fact.observations)
        result = attach_observations(fact, new_obs)

        # The result's observations start with the original ones in their
        # original order, followed by the new ones in the order given.
        assert len(result.observations) == len(original_obs) + len(new_obs)

        # Existing observations come first, unchanged.
        for i, obs in enumerate(original_obs):
            assert result.observations[i].source_ref == obs.source_ref
            assert result.observations[i].observed_from == obs.observed_from
            assert result.observations[i].observed_to == obs.observed_to
            assert result.observations[i].page_note == obs.page_note

        # New observations follow in the exact order given.
        for j, obs in enumerate(new_obs):
            result_obs = result.observations[len(original_obs) + j]
            assert result_obs.source_ref == obs.source_ref
            assert result_obs.observed_from == obs.observed_from
            assert result_obs.observed_to == obs.observed_to
            assert result_obs.page_note == obs.page_note

    @given(
        fact=residence_facts(
            include_many_observations=False,
            max_observations=6,
            include_blank_references=False,
            shape="ordered",
            observation_count=3,
        ),
        index=st.integers(min_value=0, max_value=2),
    )
    @settings(max_examples=100, deadline=None)
    def test_remove_keeps_survivors_in_relative_order_and_byte_identical(
        self,
        fact: ResidenceFact,
        index: int,
    ) -> None:
        """remove_observation keeps survivors in their original relative order and byte-identical.

        Feature: residence-periods, Property 10: Observation order is preserved through every list operation

        **Validates: Requirements 4.3**
        """
        original_obs = list(fact.observations)
        expected_survivors = [obs for i, obs in enumerate(original_obs) if i != index]

        result = remove_observation(fact, index)

        # Survivors are in the same relative order.
        assert len(result.observations) == len(expected_survivors)
        for result_obs, expected_obs in zip(result.observations, expected_survivors):
            # Byte-identical: every field matches.
            assert result_obs.source_ref.source_id == expected_obs.source_ref.source_id
            assert result_obs.source_ref.quality == expected_obs.source_ref.quality
            assert result_obs.source_ref.note == expected_obs.source_ref.note
            assert result_obs.source_ref.aspects == expected_obs.source_ref.aspects
            assert result_obs.observed_from == expected_obs.observed_from
            assert result_obs.observed_to == expected_obs.observed_to
            assert result_obs.page_note == expected_obs.page_note

    @given(scenario=_attach_remove_scenario())
    @settings(max_examples=100, deadline=None)
    def test_repeated_cycles_preserve_order_contract(
        self,
        scenario: tuple[ResidenceFact, list[tuple[str, list[Observation] | int]]],
    ) -> None:
        """Repeated attach+remove cycles preserve the order contract throughout.

        Feature: residence-periods, Property 10: Observation order is preserved through every list operation

        **Validates: Requirements 4.3, 16.12**
        """
        fact, operations = scenario

        # Track the expected observation order as a list of (source_id, from, to, page_note) tuples.
        # This is our oracle for what the observations should be at every step.
        expected_order: list[tuple[str, str, str, str]] = [
            (obs.source_ref.source_id, obs.observed_from, obs.observed_to, obs.page_note)
            for obs in fact.observations
        ]

        current_fact = copy.deepcopy(fact)

        for op, payload in operations:
            if op == "attach":
                batch = payload  # type: ignore[assignment]
                current_fact = attach_observations(current_fact, batch)
                # Extend the expected order with the new observations in order.
                for obs in batch:
                    expected_order.append(
                        (obs.source_ref.source_id, obs.observed_from, obs.observed_to, obs.page_note)
                    )
            else:
                index = payload  # type: ignore[assignment]
                current_fact = remove_observation(current_fact, index)
                # Remove from expected at the same index.
                del expected_order[index]

            # After every operation, the observation list must match expected order.
            actual_order = [
                (obs.source_ref.source_id, obs.observed_from, obs.observed_to, obs.page_note)
                for obs in current_fact.observations
            ]
            assert actual_order == expected_order, (
                f"Order mismatch after {op} operation:\n"
                f"  expected: {expected_order}\n"
                f"  got:      {actual_order}"
            )
