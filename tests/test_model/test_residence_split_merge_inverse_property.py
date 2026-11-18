# Feature: residence-periods, Property 35: Splitting inverts merging
"""Property-based test for the split/merge inverse relation.

Feature: residence-periods, Property 35: Splitting inverts merging

For all pairs of Residence_Facts having equal person_id and equal place_id whose
Observations are separated by a coverage gap holding at least one Observation
ending before it and one beginning after it, merging the pair and then splitting
the result at that gap yields two Residence_Facts whose person_id, place_id and
Observation sets equal those of the two originals, and the merged fact's reported
coverage gap equals the separating years.

**Validates: Requirements 17.9, 17.12**
"""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from slaktbusken.model.residence import (
    Endpoint,
    Observation,
    ResidenceFact,
    coverage_union,
    observation_span_years,
)
from slaktbusken.services.residence_coverage import CoverageGap, coverage_gaps
from slaktbusken.services.residence_edit_ops import merge, split_at_gap
from slaktbusken.model.project import ProjectData, ProjectMetadata
from tests.test_model.residence_strategies import observations


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def _mergeable_pair_with_gap(draw):
    """Generate two Residence_Facts sharing person_id/place_id with a splittable gap between them.

    The first fact has observations forming contiguous coverage up to just before
    the gap, and the second has contiguous coverage starting just after the gap.
    This ensures that after merging, the merged fact has exactly one coverage gap
    at the specified position, and splitting at that gap recovers the originals.
    """
    # Shared identity.
    person_id = draw(st.text(alphabet="abcdefghijk0123456789_", min_size=4, max_size=10))
    place_id = draw(st.text(alphabet="abcdefghijk0123456789_", min_size=4, max_size=10))

    # Define the gap region.
    gap_start = draw(st.integers(min_value=1600, max_value=1880))
    gap_end = draw(st.integers(min_value=gap_start, max_value=gap_start + 15))

    # Generate 1-4 contiguous observations for the first fact (before the gap).
    # They must collectively cover exactly from some start year up to gap_start - 1.
    before_count = draw(st.integers(min_value=1, max_value=4))
    # Pick a starting year for the first observation.
    first_obs_start = draw(st.integers(min_value=1500, max_value=gap_start - before_count))
    # Divide the range [first_obs_start, gap_start - 1] into contiguous segments.
    total_before_years = gap_start - 1 - first_obs_start + 1
    before_obs: list[Observation] = []
    current_year = first_obs_start
    for i in range(before_count):
        if i == before_count - 1:
            # Last observation covers up to gap_start - 1.
            obs_from = current_year
            obs_to = gap_start - 1
        else:
            # Each intermediate observation covers at least 1 year.
            remaining = before_count - i
            max_end = gap_start - 1 - (remaining - 1)
            obs_from = current_year
            obs_to = draw(st.integers(min_value=current_year, max_value=max_end))
            current_year = obs_to + 1
        base_obs = draw(observations(shape="ordered", min_year=obs_from, max_year=obs_to))
        before_obs.append(
            Observation(
                source_ref=base_obs.source_ref,
                observed_from=f"{obs_from:04d}",
                observed_to=f"{obs_to:04d}",
                page_note=base_obs.page_note,
            )
        )

    # Generate 1-4 contiguous observations for the second fact (after the gap).
    after_count = draw(st.integers(min_value=1, max_value=4))
    last_obs_end = draw(st.integers(min_value=gap_end + after_count, max_value=2100))
    after_obs: list[Observation] = []
    current_year = gap_end + 1
    for i in range(after_count):
        if i == after_count - 1:
            obs_from = current_year
            obs_to = last_obs_end
        else:
            remaining = after_count - i
            max_end = last_obs_end - (remaining - 1)
            obs_from = current_year
            obs_to = draw(st.integers(min_value=current_year, max_value=max_end))
            current_year = obs_to + 1
        base_obs = draw(observations(shape="ordered", min_year=obs_from, max_year=obs_to))
        after_obs.append(
            Observation(
                source_ref=base_obs.source_ref,
                observed_from=f"{obs_from:04d}",
                observed_to=f"{obs_to:04d}",
                page_note=base_obs.page_note,
            )
        )

    # Build the first fact: endpoints that bracket the "before" observations.
    # Use start.earliest/latest from the earliest obs year and end from
    # the highest obs year on that side.
    first_start_earliest = before_obs[0].observed_from
    first_start_latest = before_obs[0].observed_from
    first_end_earliest = max(obs.observed_to for obs in before_obs)
    # end.latest is the user's conclusion — leave it absent so the split
    # can set it to absent as well (matching original).
    first_fact = ResidenceFact(
        id=draw(st.text(alphabet="abcdefghijk0123456789_", min_size=4, max_size=10)),
        person_id=person_id,
        place_id=place_id,
        start=Endpoint(
            earliest=first_start_earliest,
            latest=first_start_latest,
            precision=None,
            event_id=None,
            note=None,
        ),
        end=Endpoint(
            earliest=first_end_earliest,
            latest=None,
            precision=None,
            event_id=None,
            note=None,
        ),
        role_in_household="",
        observations=before_obs,
        notes="",
    )

    # Build the second fact: endpoints that bracket the "after" observations.
    second_start_latest = min(obs.observed_from for obs in after_obs)
    second_end_earliest = max(obs.observed_to for obs in after_obs)
    second_end_latest = max(obs.observed_to for obs in after_obs)
    second_fact = ResidenceFact(
        id=draw(
            st.text(alphabet="abcdefghijk0123456789_", min_size=4, max_size=10).filter(
                lambda x: x != first_fact.id
            )
        ),
        person_id=person_id,
        place_id=place_id,
        start=Endpoint(
            earliest=None,
            latest=second_start_latest,
            precision=None,
            event_id=None,
            note=None,
        ),
        end=Endpoint(
            earliest=second_end_earliest,
            latest=second_end_latest,
            precision=None,
            event_id=None,
            note=None,
        ),
        role_in_household="",
        observations=after_obs,
        notes="",
    )

    # The gap between them.
    gap = CoverageGap(
        residence_id="",  # will be set on the merged fact
        first_year=gap_start,
        last_year=gap_end,
        suggestion="",
        splittable=True,
    )

    # IDs for merge and split results.
    merge_id = draw(st.text(alphabet="abcdefghijk0123456789_", min_size=4, max_size=10))
    split_id_1 = draw(st.text(alphabet="abcdefghijk0123456789_", min_size=4, max_size=10))
    split_id_2 = draw(
        st.text(alphabet="abcdefghijk0123456789_", min_size=4, max_size=10).filter(
            lambda x: x != split_id_1
        )
    )

    return first_fact, second_fact, gap, merge_id, (split_id_1, split_id_2)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestSplitMergeInverseProperty:
    """Property 35: Splitting inverts merging.

    **Validates: Requirements 17.9, 17.12**
    """

    @given(data=_mergeable_pair_with_gap())
    @settings(max_examples=100, deadline=None)
    def test_splitting_inverts_merging(
        self,
        data: tuple[
            ResidenceFact,
            ResidenceFact,
            CoverageGap,
            str,
            tuple[str, str],
        ],
    ) -> None:
        """Merging then splitting at the gap recovers the original observation sets.

        Feature: residence-periods, Property 35: Splitting inverts merging

        **Validates: Requirements 17.9, 17.12**
        """
        first_fact, second_fact, gap, merge_id, split_ids = data

        # --- Step 1: Merge the two facts ---
        merged_fact, _warning = merge(first_fact, second_fact, merge_id)

        # --- Step 2: Verify the merged fact has a coverage gap at the expected position ---
        # Build a minimal ProjectData for coverage_gaps (it needs sources lookup but
        # for gap detection only the observations matter; absent sources just produce
        # empty suggestions).
        project = ProjectData(
            project=ProjectMetadata(title="test"),
            residences=[merged_fact],
        )
        reported_gaps = coverage_gaps(merged_fact, project)

        # The gap between the original pair's observations should appear.
        matching_gaps = [
            g
            for g in reported_gaps
            if g.first_year == gap.first_year and g.last_year == gap.last_year
        ]
        assert len(matching_gaps) == 1, (
            f"Expected exactly one coverage gap at {gap.first_year}-{gap.last_year}, "
            f"got {len(matching_gaps)} gaps. All gaps: "
            f"{[(g.first_year, g.last_year) for g in reported_gaps]}"
        )
        reported_gap = matching_gaps[0]

        # --- Step 3: Split the merged fact at the gap ---
        split_first, split_second = split_at_gap(merged_fact, reported_gap, split_ids)

        # --- Step 4: Verify person_id and place_id are preserved (Req 17.12) ---
        assert split_first.person_id == first_fact.person_id
        assert split_first.place_id == first_fact.place_id
        assert split_second.person_id == second_fact.person_id
        assert split_second.place_id == second_fact.place_id

        # --- Step 5: Verify observation sets equal those of the originals (Req 17.12) ---
        # Collect observation fingerprints (source_id, from, to, page_note) for comparison.
        def _obs_fingerprint(obs: Observation) -> tuple[str, str, str, str]:
            return (
                obs.source_ref.source_id,
                obs.observed_from,
                obs.observed_to,
                obs.page_note,
            )

        # The original first fact's observations should all end up in split_first,
        # and the second fact's in split_second.
        original_before_fps = sorted(
            _obs_fingerprint(obs) for obs in first_fact.observations
        )
        original_after_fps = sorted(
            _obs_fingerprint(obs) for obs in second_fact.observations
        )

        split_before_fps = sorted(
            _obs_fingerprint(obs) for obs in split_first.observations
        )
        split_after_fps = sorted(
            _obs_fingerprint(obs) for obs in split_second.observations
        )

        assert split_before_fps == original_before_fps, (
            f"Split first observations don't match original first.\n"
            f"Expected: {original_before_fps}\n"
            f"Got: {split_before_fps}"
        )
        assert split_after_fps == original_after_fps, (
            f"Split second observations don't match original second.\n"
            f"Expected: {original_after_fps}\n"
            f"Got: {split_after_fps}"
        )

        # --- Step 6: The observation content is conserved (superset or equal set) ---
        # Per the task: "splitting and then merging the two halves produces a fact
        # whose observations are a superset (or equal set) of the original"
        # Here we test the inverse: merge then split. The observation sets should
        # be exactly equal since all observations cleanly partition by the gap.
        combined_split_fps = sorted(split_before_fps + split_after_fps)
        combined_original_fps = sorted(original_before_fps + original_after_fps)
        assert combined_split_fps == combined_original_fps
