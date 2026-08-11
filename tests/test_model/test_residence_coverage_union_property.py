# Feature: residence-periods, Property 12: Coverage union and coverage gaps are exact, maximal and non-mutating
"""Property-based test for coverage union and coverage gaps.

Feature: residence-periods, Property 12: Coverage union and coverage gaps are exact, maximal and non-mutating

For any Residence_Fact, the coverage union contains each whole year contributed
by its Observations exactly once regardless of identical, overlapping or adjacent
spans; the reported coverage gaps are exactly the maximal runs of years absent
from that union between the lowest `observed_from` year and the highest
`observed_to` year, pairwise disjoint and ordered by first uncovered year
ascending; zero gaps are reported when the fact carries zero or one Observation
or when the union is complete; and every field of the Project is unchanged after
the analysis.

**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 16.13**
"""

from __future__ import annotations

import copy

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.residence import (
    Observation,
    ResidenceFact,
    core_aggregate,
    coverage_union,
    observation_span_years,
)
from slaktbusken.services.residence_coverage import coverage_gaps
from tests.test_model.residence_strategies import (
    consistent_projects,
)


class TestCoverageUnionAndGaps:
    """Feature: residence-periods, Property 12: Coverage union and coverage gaps are exact, maximal and non-mutating

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 16.13**
    """

    @given(data=consistent_projects(min_residences=1, max_residences=3))
    @settings(max_examples=100, deadline=None)
    def test_coverage_union_counts_each_year_once(self, data) -> None:
        """The coverage union contains each year exactly once regardless of
        identical, overlapping or adjacent Observations.

        **Validates: Requirements 5.1**
        """
        for fact in data.residences:
            union = coverage_union(fact)
            # Recompute independently: each Observation contributes years from
            # observed_from to observed_to inclusive, and a year appears once.
            expected: set[int] = set()
            for obs in fact.observations:
                span = observation_span_years(obs)
                if span is None:
                    continue
                first, last = span
                # Inverted pairs contribute nothing (the implementation uses range)
                if first <= last:
                    expected.update(range(first, last + 1))

            assert union == expected, (
                f"coverage_union mismatch for fact {fact.id}: "
                f"got {sorted(union)[:10]}..., expected {sorted(expected)[:10]}..."
            )

    @given(data=consistent_projects(min_residences=1, max_residences=3))
    @settings(max_examples=100, deadline=None)
    def test_gaps_are_maximal_runs_between_observation_range(self, data) -> None:
        """Coverage gaps are exactly the maximal runs of years absent from the
        union between the lowest observed_from and highest observed_to.

        **Validates: Requirements 5.2**
        """
        for fact in data.residences:
            gaps = coverage_gaps(fact, data)
            union = coverage_union(fact)

            # Determine the observation range using core_aggregate, which is the
            # same definition the implementation uses: lowest observed_from and
            # highest observed_to, each taken independently across all observations.
            lowest_from_str, highest_to_str = core_aggregate(fact.observations)

            if (
                lowest_from_str is None
                or highest_to_str is None
                or len(fact.observations) < 2
            ):
                # No gaps expected (handled by the zero/one observation test)
                assert gaps == [], (
                    f"Expected no gaps for fact {fact.id} with insufficient bounds"
                )
                continue

            lowest_from = int(lowest_from_str)
            highest_to = int(highest_to_str)

            # Compute expected uncovered years
            all_years = set(range(lowest_from, highest_to + 1))
            uncovered = sorted(all_years - union)

            # Group into maximal runs
            expected_runs: list[tuple[int, int]] = []
            for year in uncovered:
                if expected_runs and year == expected_runs[-1][1] + 1:
                    expected_runs[-1] = (expected_runs[-1][0], year)
                else:
                    expected_runs.append((year, year))

            # Gaps should match the expected runs
            actual_runs = [(g.first_year, g.last_year) for g in gaps]
            assert actual_runs == expected_runs, (
                f"Gaps mismatch for fact {fact.id}: "
                f"got {actual_runs}, expected {expected_runs}"
            )

            # Gaps should be ordered by first uncovered year ascending
            for i in range(1, len(gaps)):
                assert gaps[i].first_year > gaps[i - 1].last_year, (
                    f"Gaps not ordered ascending for fact {fact.id}"
                )

            # Gaps should be pairwise disjoint
            for i in range(1, len(gaps)):
                assert gaps[i].first_year > gaps[i - 1].last_year, (
                    f"Gaps overlap for fact {fact.id}"
                )

    @given(data=consistent_projects(min_residences=1, max_residences=3))
    @settings(max_examples=100, deadline=None)
    def test_zero_or_one_observation_yields_no_gap(self, data) -> None:
        """Zero or one Observation yields no coverage gap.

        **Validates: Requirements 5.3, 16.13**
        """
        for fact in data.residences:
            if len(fact.observations) <= 1:
                gaps = coverage_gaps(fact, data)
                assert gaps == [], (
                    f"Expected no gaps for fact {fact.id} with "
                    f"{len(fact.observations)} observation(s), got {len(gaps)}"
                )

    @given(data=consistent_projects(min_residences=1, max_residences=3))
    @settings(max_examples=100, deadline=None)
    def test_complete_union_yields_no_gap(self, data) -> None:
        """A complete coverage union yields no coverage gap.

        **Validates: Requirements 5.3, 16.13**
        """
        for fact in data.residences:
            if len(fact.observations) < 2:
                continue

            union = coverage_union(fact)

            # Determine observation range
            lowest_from: int | None = None
            highest_to: int | None = None
            for obs in fact.observations:
                span = observation_span_years(obs)
                if span is None:
                    continue
                first, last = span
                if lowest_from is None or first < lowest_from:
                    lowest_from = first
                if highest_to is None or last > highest_to:
                    highest_to = last

            if lowest_from is None or highest_to is None:
                continue

            # If the union is complete (covers every year in the range)
            all_years = set(range(lowest_from, highest_to + 1))
            if union >= all_years:
                gaps = coverage_gaps(fact, data)
                assert gaps == [], (
                    f"Expected no gaps for fact {fact.id} with complete "
                    f"union, got {len(gaps)}"
                )

    @given(data=consistent_projects(min_residences=1, max_residences=3))
    @settings(max_examples=100, deadline=None)
    def test_nothing_is_mutated(self, data) -> None:
        """coverage_union and coverage_gaps leave every field of the Project
        unchanged.

        **Validates: Requirements 5.4**
        """
        data_before = copy.deepcopy(data)

        for fact in data.residences:
            coverage_union(fact)
            coverage_gaps(fact, data)

        # Every Residence_Fact, its Observations, and all Project entities unchanged
        assert data.residences == data_before.residences, (
            "residences were mutated by coverage analysis"
        )
        assert data.persons == data_before.persons, (
            "persons were mutated by coverage analysis"
        )
        assert data.places == data_before.places, (
            "places were mutated by coverage analysis"
        )
        assert data.sources == data_before.sources, (
            "sources were mutated by coverage analysis"
        )
        assert data.events == data_before.events, (
            "events were mutated by coverage analysis"
        )
