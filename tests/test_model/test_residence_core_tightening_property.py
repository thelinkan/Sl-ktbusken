# Feature: residence-periods, Property 31: Observations tighten the documented core and never touch the outer bounds
"""Property-based test for core tightening.

Feature: residence-periods, Property 31: Observations tighten the documented core and never touch the outer bounds

After attaching observations, `start.latest` equals min(observed_from) when the stored
value was absent or later, `end.earliest` equals max(observed_to) when absent or earlier,
and `start.earliest`/`end.latest` are NEVER touched.

**Validates: Requirements 9.5, 16.3, 16.4, 16.5, 16.6, 16.9, 16.11**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.residence import Observation, ResidenceFact, core_aggregate
from slaktbusken.services.residence_edit_ops import attach_observations
from tests.test_model.residence_strategies import observations, residence_facts


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


def _parse_year(value: str | None) -> int | None:
    """Parse a four-digit year from a value, returning None if absent/malformed."""
    if value is None:
        return None
    trimmed = value.strip()
    if len(trimmed) != 4 or not trimmed.isdigit():
        return None
    return int(trimmed)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestCoreTighteningProperty:
    """Property 31: Observations tighten the documented core and never touch the outer bounds.

    After attaching observations, `start.latest` equals min(observed_from) when the stored
    value was absent or later, `end.earliest` equals max(observed_to) when absent or earlier,
    and `start.earliest`/`end.latest` are NEVER touched.

    **Validates: Requirements 9.5, 16.3, 16.4, 16.5, 16.6, 16.9, 16.11**
    """

    @given(
        fact=residence_facts(
            include_many_observations=False,
            max_observations=4,
            include_blank_references=False,
            shape="ordered",
        ),
        new_obs=st.lists(
            observations(shape="ordered"),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_observations_tighten_core_and_never_touch_outer_bounds(
        self,
        fact: ResidenceFact,
        new_obs: list[Observation],
    ) -> None:
        """Attaching observations tightens the documented core and never modifies outer bounds.

        Feature: residence-periods, Property 31: Observations tighten the documented core and never touch the outer bounds

        **Validates: Requirements 9.5, 16.3, 16.4, 16.5, 16.6, 16.9, 16.11**
        """
        # Record original outer bounds before attaching.
        original_start_earliest = fact.start.earliest
        original_end_latest = fact.end.latest

        # Attach observations.
        result = attach_observations(fact, new_obs)

        # --- Assertion 1: start.earliest and end.latest are NEVER touched (Req 16.3) ---
        assert result.start.earliest == original_start_earliest, (
            f"start.earliest was modified: {original_start_earliest!r} -> {result.start.earliest!r}"
        )
        assert result.end.latest == original_end_latest, (
            f"end.latest was modified: {original_end_latest!r} -> {result.end.latest!r}"
        )

        # --- Assertion 2: start.latest equals min(observed_from) when stored was absent or later (Req 16.4) ---
        # Compute the aggregate over ALL observations (existing + new).
        all_obs = list(fact.observations) + list(new_obs)
        agg_from, agg_to = core_aggregate(all_obs)

        # For start.latest: the tighter value should be the earlier (lower) year.
        stored_start_latest = fact.start.latest
        stored_start_latest_year = _parse_year(stored_start_latest)
        agg_from_year = _parse_year(agg_from)

        if agg_from_year is not None:
            if stored_start_latest is None or stored_start_latest.strip() == "":
                # Stored was absent → result should equal the aggregate.
                assert result.start.latest == agg_from, (
                    f"start.latest should be {agg_from!r} when stored was absent, "
                    f"got {result.start.latest!r}"
                )
            elif stored_start_latest_year is not None:
                # Both are plain years — the result should be the minimum (earliest).
                if stored_start_latest_year <= agg_from_year:
                    assert result.start.latest == stored_start_latest, (
                        f"start.latest should stay {stored_start_latest!r} (already tighter), "
                        f"got {result.start.latest!r}"
                    )
                else:
                    assert result.start.latest == agg_from, (
                        f"start.latest should become {agg_from!r} (tighter), "
                        f"got {result.start.latest!r}"
                    )

        # --- Assertion 3: end.earliest equals max(observed_to) when stored was absent or earlier (Req 16.4) ---
        stored_end_earliest = fact.end.earliest
        stored_end_earliest_year = _parse_year(stored_end_earliest)
        agg_to_year = _parse_year(agg_to)

        if agg_to_year is not None:
            if stored_end_earliest is None or stored_end_earliest.strip() == "":
                # Stored was absent → result should equal the aggregate.
                assert result.end.earliest == agg_to, (
                    f"end.earliest should be {agg_to!r} when stored was absent, "
                    f"got {result.end.earliest!r}"
                )
            elif stored_end_earliest_year is not None:
                # Both are plain years — the result should be the maximum (latest).
                if stored_end_earliest_year >= agg_to_year:
                    assert result.end.earliest == stored_end_earliest, (
                        f"end.earliest should stay {stored_end_earliest!r} (already tighter), "
                        f"got {result.end.earliest!r}"
                    )
                else:
                    assert result.end.earliest == agg_to, (
                        f"end.earliest should become {agg_to!r} (tighter), "
                        f"got {result.end.earliest!r}"
                    )
