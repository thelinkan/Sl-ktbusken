# Feature: residence-periods, Property 34: Merging composes two facts and refuses or warns as specified
"""Property-based test for merge.

Feature: residence-periods, Property 34: Merging composes two facts and refuses or warns as specified

For any two Residence_Facts sharing the same person_id and place_id, merging takes the start
Endpoint of the timeline-earlier fact and the end Endpoint of the other, each carrying all five
fields unchanged; unions the Observations ordered by observed_from with none discarded; keeps
the earlier role_in_household while appending the other to notes when non-empty and differing;
retains both notes texts; assigns the given new id; re-derives core bounds from the combined
observations; and reports a >10-year separation warning when the gap between the earlier fact's
highest observed_to and the later fact's lowest observed_from exceeds 10 whole years. When
person_id or place_id differ, the merge is refused with the required Swedish error message and
both facts remain unchanged.

**Validates: Requirements 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.10, 17.11, 17.15**
"""

from __future__ import annotations

import copy

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from slaktbusken.model.residence import (
    Endpoint,
    Observation,
    ResidenceFact,
    core_aggregate,
)
from slaktbusken.services.residence_edit_ops import merge, ResidenceMergeError
from tests.test_model.residence_strategies import (
    observations,
    residence_facts,
    _identifiers,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def _mergeable_pair(draw):
    """Generate two ResidenceFacts sharing the same person_id and place_id.

    Each fact has ordered observations so that the merge behaviour (timeline order,
    observation union, core re-derivation) is exercisable.
    """
    person_id = draw(_identifiers("person"))
    place_id = draw(_identifiers("place"))

    # Generate two facts with the same person and place.
    fact_a = draw(
        residence_facts(
            person_ids=[person_id],
            place_ids=[place_id],
            include_blank_references=False,
            include_many_observations=False,
            max_observations=5,
        )
    )
    fact_b = draw(
        residence_facts(
            person_ids=[person_id],
            place_ids=[place_id],
            include_blank_references=False,
            include_many_observations=False,
            max_observations=5,
        )
    )

    # Ensure distinct ids.
    assume(fact_a.id != fact_b.id)

    new_id = draw(
        st.text(alphabet="abcdefghijk0123456789_", min_size=4, max_size=12).filter(
            lambda x: x != fact_a.id and x != fact_b.id
        )
    )

    return fact_a, fact_b, new_id


@st.composite
def _mergeable_pair_with_large_separation(draw):
    """Generate two facts at the same person/place whose observations are >10 years apart."""
    person_id = draw(_identifiers("person"))
    place_id = draw(_identifiers("place"))

    # Earlier fact: observations ending before a gap.
    earlier_to = draw(st.integers(min_value=1600, max_value=1800))
    earlier_from = draw(st.integers(min_value=1500, max_value=earlier_to))

    # Later fact: observations starting more than 10 years after earlier_to.
    later_from = draw(st.integers(min_value=earlier_to + 11, max_value=2050))
    later_to = draw(st.integers(min_value=later_from, max_value=2100))

    obs_a = Observation(
        source_ref=draw(observations(shape="ordered")).source_ref,
        observed_from=f"{earlier_from:04d}",
        observed_to=f"{earlier_to:04d}",
        page_note="",
    )
    obs_b = Observation(
        source_ref=draw(observations(shape="ordered")).source_ref,
        observed_from=f"{later_from:04d}",
        observed_to=f"{later_to:04d}",
        page_note="",
    )

    fact_a = ResidenceFact(
        id=draw(_identifiers("residence")),
        person_id=person_id,
        place_id=place_id,
        start=Endpoint(earliest=f"{earlier_from:04d}", latest=f"{earlier_from:04d}"),
        end=Endpoint(earliest=f"{earlier_to:04d}", latest=f"{earlier_to:04d}"),
        role_in_household="",
        observations=[obs_a],
        notes="",
    )
    fact_b_id = draw(_identifiers("residence"))
    assume(fact_b_id != fact_a.id)
    fact_b = ResidenceFact(
        id=fact_b_id,
        person_id=person_id,
        place_id=place_id,
        start=Endpoint(earliest=f"{later_from:04d}", latest=f"{later_from:04d}"),
        end=Endpoint(earliest=f"{later_to:04d}", latest=f"{later_to:04d}"),
        role_in_household="",
        observations=[obs_b],
        notes="",
    )

    new_id = draw(
        st.text(alphabet="abcdefghijk0123456789_", min_size=4, max_size=12).filter(
            lambda x: x != fact_a.id and x != fact_b.id
        )
    )

    return fact_a, fact_b, new_id, earlier_to, later_from


@st.composite
def _differing_person_pair(draw):
    """Generate two facts with different person_id values."""
    person_a = draw(_identifiers("person"))
    person_b = draw(_identifiers("person"))
    assume(person_a != person_b)
    place_id = draw(_identifiers("place"))

    fact_a = draw(
        residence_facts(
            person_ids=[person_a],
            place_ids=[place_id],
            include_blank_references=False,
            include_many_observations=False,
            max_observations=2,
        )
    )
    fact_b = draw(
        residence_facts(
            person_ids=[person_b],
            place_ids=[place_id],
            include_blank_references=False,
            include_many_observations=False,
            max_observations=2,
        )
    )

    return fact_a, fact_b


@st.composite
def _differing_place_pair(draw):
    """Generate two facts with different place_id values but same person_id."""
    person_id = draw(_identifiers("person"))
    place_a = draw(_identifiers("place"))
    place_b = draw(_identifiers("place"))
    assume(place_a != place_b)

    fact_a = draw(
        residence_facts(
            person_ids=[person_id],
            place_ids=[place_a],
            include_blank_references=False,
            include_many_observations=False,
            max_observations=2,
        )
    )
    fact_b = draw(
        residence_facts(
            person_ids=[person_id],
            place_ids=[place_b],
            include_blank_references=False,
            include_many_observations=False,
            max_observations=2,
        )
    )

    return fact_a, fact_b


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _absent_first_key(value: str | None) -> tuple[int, str]:
    """Sort key: absent before present, matching the implementation."""
    if value is None or not value.strip():
        return (0, "")
    return (1, value.strip())


def _timeline_key(fact: ResidenceFact) -> tuple:
    """The same timeline sort key the merge uses to determine earlier/later."""
    return (
        _absent_first_key(fact.start.earliest),
        _absent_first_key(fact.start.latest),
        _absent_first_key(fact.end.earliest),
        _absent_first_key(fact.end.latest),
        fact.id,
    )


def _obs_year(value: str) -> int | None:
    """Parse a four-digit year from an observation bound, returning None if invalid."""
    if not value or not value.strip():
        return None
    stripped = value.strip()
    if len(stripped) == 4 and stripped.isdigit():
        return int(stripped)
    return None


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestMergingProperty:
    """Property 34: Merging composes two facts and refuses or warns as specified.

    **Validates: Requirements 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.10, 17.11, 17.15**
    """

    @given(data=_mergeable_pair())
    @settings(max_examples=100, deadline=None)
    def test_merging_composes_two_facts(
        self,
        data: tuple[ResidenceFact, ResidenceFact, str],
    ) -> None:
        """Merging two same-person/same-place facts produces the correct merged result.

        Feature: residence-periods, Property 34: Merging composes two facts and refuses or warns as specified

        **Validates: Requirements 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.10, 17.11, 17.15**
        """
        fact_a, fact_b, new_id = data

        # Keep deep copies to verify originals are not mutated.
        orig_a = copy.deepcopy(fact_a)
        orig_b = copy.deepcopy(fact_b)

        merged, warning = merge(fact_a, fact_b, new_id)

        # Determine which is earlier under the timeline order.
        if _timeline_key(orig_a) <= _timeline_key(orig_b):
            earlier, later = orig_a, orig_b
        else:
            earlier, later = orig_b, orig_a

        # --- Assertion 1: New id is assigned (Req 17.6) ---
        assert merged.id == new_id

        # --- Assertion 2: Start from earlier, end from later, all 5 fields unchanged (Req 17.2) ---
        assert merged.start.earliest == earlier.start.earliest
        assert merged.start.latest is not None or earlier.start.latest is None
        # start.latest is re-derived; we check it under assertion 6
        assert merged.start.precision == earlier.start.precision
        assert merged.start.event_id == earlier.start.event_id
        assert merged.start.note == earlier.start.note

        assert merged.end.latest == later.end.latest
        # end.earliest is re-derived; we check it under assertion 6
        assert merged.end.precision == later.end.precision
        assert merged.end.event_id == later.end.event_id
        assert merged.end.note == later.end.note

        # start.earliest comes from earlier, end.latest comes from later (outer bounds unchanged)
        assert merged.start.earliest == earlier.start.earliest
        assert merged.end.latest == later.end.latest

        # --- Assertion 3: Observations are the union, ordered by observed_from (Req 17.3) ---
        total_obs_count = len(earlier.observations) + len(later.observations)
        assert len(merged.observations) == total_obs_count

        # None discarded: all source_ref.source_id + observed_from + observed_to combinations
        # from both originals appear in merged.
        original_obs_keys = sorted(
            [
                (o.source_ref.source_id, o.observed_from, o.observed_to, o.page_note)
                for o in earlier.observations
            ]
            + [
                (o.source_ref.source_id, o.observed_from, o.observed_to, o.page_note)
                for o in later.observations
            ]
        )
        merged_obs_keys = sorted(
            [
                (o.source_ref.source_id, o.observed_from, o.observed_to, o.page_note)
                for o in merged.observations
            ]
        )
        assert merged_obs_keys == original_obs_keys

        # Ordered by observed_from ascending.
        for i in range(len(merged.observations) - 1):
            key_i = _absent_first_key(merged.observations[i].observed_from)
            key_next = _absent_first_key(merged.observations[i + 1].observed_from)
            assert key_i <= key_next, (
                f"Observations not ordered by observed_from: "
                f"{merged.observations[i].observed_from!r} > "
                f"{merged.observations[i + 1].observed_from!r}"
            )

        # --- Assertion 4: Role handling (Req 17.4) ---
        assert merged.role_in_household == earlier.role_in_household

        if (
            later.role_in_household
            and later.role_in_household != earlier.role_in_household
        ):
            expected_role_note = (
                f"Tidigare roll i hushållet vid sammanslagning: "
                f"{later.role_in_household}"
            )
            assert expected_role_note in merged.notes

        # --- Assertion 5: Both notes retained (Req 17.5) ---
        if earlier.notes:
            assert earlier.notes in merged.notes
        if later.notes:
            assert later.notes in merged.notes

        # --- Assertion 6: Core bounds re-derived from combined observations (Req 17.11) ---
        agg_from, agg_to = core_aggregate(merged.observations)
        if agg_from is not None:
            assert merged.start.latest == agg_from, (
                f"start.latest should be re-derived to {agg_from!r}, "
                f"got {merged.start.latest!r}"
            )
        else:
            # When no observation has a valid from, keep earlier's start.latest
            assert merged.start.latest == earlier.start.latest

        if agg_to is not None:
            assert merged.end.earliest == agg_to, (
                f"end.earliest should be re-derived to {agg_to!r}, "
                f"got {merged.end.earliest!r}"
            )
        else:
            # When no observation has a valid to, keep later's end.earliest
            assert merged.end.earliest == later.end.earliest

        # --- Assertion 7: person_id and place_id preserved (Req 17.1) ---
        assert merged.person_id == earlier.person_id
        assert merged.place_id == earlier.place_id

        # --- Assertion 8: Originals are not mutated ---
        assert fact_a.id == orig_a.id
        assert fact_b.id == orig_b.id
        assert len(fact_a.observations) == len(orig_a.observations)
        assert len(fact_b.observations) == len(orig_b.observations)

    @given(data=_mergeable_pair_with_large_separation())
    @settings(max_examples=100, deadline=None)
    def test_merging_reports_large_separation_warning(
        self,
        data: tuple[ResidenceFact, ResidenceFact, str, int, int],
    ) -> None:
        """Merging reports a warning when the separation exceeds 10 whole years.

        Feature: residence-periods, Property 34: Merging composes two facts and refuses or warns as specified

        **Validates: Requirements 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.10, 17.11, 17.15**
        """
        fact_a, fact_b, new_id, earlier_to, later_from = data

        # Verify separation is > 10 years.
        assert later_from - earlier_to > 10

        merged, warning = merge(fact_a, fact_b, new_id)

        # --- Assertion: Warning present for >10-year separation (Req 17.10) ---
        assert warning is not None
        assert "Perioderna ligger långt ifrån varandra" in warning
        assert "kontrollera att det är samma boende" in warning

        # Merge still produces a valid result.
        assert merged.id == new_id
        assert merged.person_id == fact_a.person_id

    @given(data=_differing_person_pair())
    @settings(max_examples=100, deadline=None)
    def test_merging_refuses_different_person(
        self,
        data: tuple[ResidenceFact, ResidenceFact],
    ) -> None:
        """Merging refuses when person_id values differ.

        Feature: residence-periods, Property 34: Merging composes two facts and refuses or warns as specified

        **Validates: Requirements 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.10, 17.11, 17.15**
        """
        fact_a, fact_b = data

        with pytest.raises(ResidenceMergeError) as exc_info:
            merge(fact_a, fact_b, "new_id")

        assert str(exc_info.value) == "Endast boenden för samma person kan slås samman."

    @given(data=_differing_place_pair())
    @settings(max_examples=100, deadline=None)
    def test_merging_refuses_different_place(
        self,
        data: tuple[ResidenceFact, ResidenceFact],
    ) -> None:
        """Merging refuses when place_id values differ.

        Feature: residence-periods, Property 34: Merging composes two facts and refuses or warns as specified

        **Validates: Requirements 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.10, 17.11, 17.15**
        """
        fact_a, fact_b = data

        with pytest.raises(ResidenceMergeError) as exc_info:
            merge(fact_a, fact_b, "new_id")

        assert str(exc_info.value) == "Endast boenden på samma plats kan slås samman."
