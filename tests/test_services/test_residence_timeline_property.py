# Feature: residence-periods, Property 20: The person residence timeline is a total, stable order
"""Property-based test for the person residence timeline.

Feature: residence-periods, Property 20: The person residence timeline is a total, stable order

For any consistent Project and any person in it, `residence_timeline` returns
the person's Residence_Facts in a total order that is stable across multiple
runs over unchanged data. The order is determined by start.earliest,
start.latest, end.earliest, end.latest (absent sorting before any present
value), then place display name in Swedish alphabetical order, then ascending
Residence_Fact id.

**Validates: Requirements 8.7**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.services.residence_query import (
    residence_timeline,
    swedish_sort_key,
)
from tests.test_model.residence_strategies import consistent_projects


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _absent_first_key(value: str | None) -> tuple[int, str]:
    """Absent (None/empty/whitespace-only) sorts before any present value."""
    if value is None or not value.strip():
        return (0, "")
    return (1, value.strip())


def _place_display(place_id: str, places_by_id: dict) -> str:
    """The display name for a place, falling back to its id."""
    place = places_by_id.get(place_id)
    if place is not None:
        return place.name
    return place_id


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


class TestResidenceTimeline:
    """Property 20: The person residence timeline is a total, stable order.

    The timeline is a total order (every pair compares deterministically),
    stable across multiple runs over unchanged data, and orders by
    start.earliest, start.latest, end.earliest, end.latest (absent first),
    then place name (Swedish), then id.

    **Validates: Requirements 8.7**
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=None)
    def test_residence_timeline_total_stable_order(self, data: st.DataObject) -> None:
        """The person residence timeline is a total, stable order.

        Feature: residence-periods, Property 20: The person residence timeline is a total, stable order

        **Validates: Requirements 8.7**
        """
        project = data.draw(
            consistent_projects(
                min_persons=1,
                max_persons=3,
                min_places=2,
                max_places=5,
                max_sources=2,
                max_events=2,
                min_residences=2,
                max_residences=8,
                include_many_observations=False,
            )
        )

        # Pick a person who has at least one residence
        person_ids_with_residences = list(
            {fact.person_id for fact in project.residences}
            & {p.id for p in project.persons}
        )
        if not person_ids_with_residences:
            return

        person_id = data.draw(st.sampled_from(person_ids_with_residences))

        # --- Run the timeline query ---
        timeline = residence_timeline(project, person_id)

        # --- ASSERTION 1: Only facts for the requested person ---
        for fact in timeline:
            assert fact.person_id == person_id

        # --- ASSERTION 2: All of the person's facts are present ---
        expected_ids = sorted(
            fact.id for fact in project.residences if fact.person_id == person_id
        )
        actual_ids = sorted(fact.id for fact in timeline)
        assert actual_ids == expected_ids, (
            f"Timeline ids {actual_ids} != expected {expected_ids}"
        )

        # --- ASSERTION 3: Total order — every consecutive pair is in the correct order ---
        places_by_id = {place.id: place for place in project.places}

        def _timeline_sort_key(fact):
            place_name = _place_display(fact.place_id, places_by_id)
            return (
                _absent_first_key(fact.start.earliest),
                _absent_first_key(fact.start.latest),
                _absent_first_key(fact.end.earliest),
                _absent_first_key(fact.end.latest),
                swedish_sort_key(place_name),
                fact.id,
            )

        for i in range(len(timeline) - 1):
            key_a = _timeline_sort_key(timeline[i])
            key_b = _timeline_sort_key(timeline[i + 1])
            assert key_a <= key_b, (
                f"Ordering violated at positions {i},{i+1}: "
                f"key[{i}]={key_a} > key[{i+1}]={key_b}"
            )

        # --- ASSERTION 4: Total order — the id tie-breaker guarantees no ties ---
        # Since ids are unique, no two facts can have the same sort key.
        keys = [_timeline_sort_key(fact) for fact in timeline]
        assert len(keys) == len(set(keys)), "Duplicate sort keys found — order is not total"

        # --- ASSERTION 5: Stability — running the query again yields identical order ---
        timeline_second_run = residence_timeline(project, person_id)
        assert [f.id for f in timeline] == [f.id for f in timeline_second_run], (
            "Timeline order is not stable across repeated runs"
        )

        # --- ASSERTION 6: Absent bounds sort before present bounds ---
        for i in range(len(timeline) - 1):
            a, b = timeline[i], timeline[i + 1]
            # If a has an absent start.earliest and b has a present one,
            # a must come first (unless an earlier key already decided).
            key_a = _timeline_sort_key(a)
            key_b = _timeline_sort_key(b)
            # Already verified in assertion 3, but this reinforces the absent-first rule.
            # Check first key component specifically:
            a_earliest = _absent_first_key(a.start.earliest)
            b_earliest = _absent_first_key(b.start.earliest)
            if a_earliest > b_earliest:
                # Then a later sort key must have overridden — but that's impossible
                # since start.earliest is the first key. This should never happen.
                assert key_a <= key_b, (
                    f"Absent-first rule violated: fact {a.id} has start.earliest="
                    f"{a.start.earliest!r}, fact {b.id} has start.earliest="
                    f"{b.start.earliest!r}"
                )
