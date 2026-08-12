# Feature: residence-periods, Property 36: Merge offers appear and are suppressed by documented absence
"""Property-based test for merge-offer detection and suppression.

Feature: residence-periods, Property 36: Merge offers appear and are suppressed by documented absence

For any Residence_Fact pair of the same person at the same place, the merge offer appears when an
attached Observation covers every year separating their Possible_Spans and declining it leaves both
facts unchanged apart from the new Observation; the offer is withheld and the separating years are
reported as no gap when a Flytt_Event of that person is dated inside the separation or another
Residence_Fact of that person at a different place overlaps it.

**Validates: Requirements 17.13, 17.14**
"""

from __future__ import annotations

import copy

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.event import DateValue, Event, Participant, PlaceRef
from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.residence import (
    Endpoint,
    Observation,
    ResidenceFact,
)
from slaktbusken.model.source import Source, StructuredReference
from slaktbusken.services.residence_edit_ops import (
    should_offer_merge,
    is_merge_suppressed,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(source_id: str) -> Source:
    """Create a minimal Source for observations."""
    return Source(
        id=source_id,
        provider="Test",
        source_type="church_book",
        title="Test Source",
        structured_reference=StructuredReference(
            fields={"parish": "Test", "series": "AI", "volume": "1", "years": "1800-1900"}
        ),
    )


def _make_observation(source_id: str, from_year: int, to_year: int) -> Observation:
    """Create an Observation covering the given year range."""
    from slaktbusken.model.event import SourceRef

    return Observation(
        source_ref=SourceRef(source_id=source_id, quality="primary", note="", aspects=[]),
        observed_from=f"{from_year:04d}",
        observed_to=f"{to_year:04d}",
        page_note="",
    )


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def _separated_pair_with_bridging_obs(draw: DrawFn):
    """Generate two same-person same-place facts separated by a gap, plus an observation
    that covers every separating year.

    The observation is meant to bridge the gap, triggering a merge offer.
    """
    person_id = "person_1"
    place_id = "place_1"

    # First fact ends at year A, second starts at year B, with A < B creating a gap.
    first_end_year = draw(st.integers(min_value=1600, max_value=1850))
    gap_size = draw(st.integers(min_value=1, max_value=15))
    second_start_year = first_end_year + gap_size + 1

    # First fact: spans from some earlier year to first_end_year
    first_start_year = draw(st.integers(min_value=1550, max_value=first_end_year - 1))
    first_obs = _make_observation("source_1", first_start_year, first_end_year)

    fact_a = ResidenceFact(
        id="residence_1",
        person_id=person_id,
        place_id=place_id,
        start=Endpoint(earliest=f"{first_start_year:04d}", latest=f"{first_start_year:04d}"),
        end=Endpoint(earliest=f"{first_end_year:04d}", latest=f"{first_end_year:04d}"),
        role_in_household="",
        observations=[first_obs],
        notes="",
    )

    # Second fact: spans from second_start_year to some later year
    second_end_year = draw(st.integers(min_value=second_start_year + 1, max_value=2050))
    second_obs = _make_observation("source_2", second_start_year, second_end_year)

    fact_b = ResidenceFact(
        id="residence_2",
        person_id=person_id,
        place_id=place_id,
        start=Endpoint(earliest=f"{second_start_year:04d}", latest=f"{second_start_year:04d}"),
        end=Endpoint(earliest=f"{second_end_year:04d}", latest=f"{second_end_year:04d}"),
        role_in_household="",
        observations=[second_obs],
        notes="",
    )

    # Bridging observation covers every separating year (first_end_year+1 to second_start_year-1)
    bridge_from = first_end_year + 1
    bridge_to = second_start_year - 1
    bridge_obs = _make_observation("source_3", bridge_from, bridge_to)

    # Build project with persons, places, sources
    person = Person(
        id=person_id,
        sex="M",
        names=[Name(type="birth", given="Anders", surname="Andersson")],
    )
    place = Place(id=place_id, type="farm", name="Norrgården")
    sources = [_make_source("source_1"), _make_source("source_2"), _make_source("source_3")]

    data = ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=[person],
        places=[place],
        sources=sources,
        residences=[fact_a, fact_b],
        events=[],
    )

    return fact_a, fact_b, bridge_obs, data


@st.composite
def _separated_pair_with_flytt_suppression(draw: DrawFn):
    """Generate two same-person same-place facts with a Flytt_Event inside the gap.

    The Flytt_Event is dated inside the separating years, which should suppress
    the merge offer per Requirement 17.14.
    """
    person_id = "person_1"
    place_id = "place_1"

    # Create a gap
    first_end_year = draw(st.integers(min_value=1600, max_value=1850))
    gap_size = draw(st.integers(min_value=2, max_value=15))
    second_start_year = first_end_year + gap_size + 1

    first_start_year = draw(st.integers(min_value=1550, max_value=first_end_year - 1))
    first_obs = _make_observation("source_1", first_start_year, first_end_year)

    fact_a = ResidenceFact(
        id="residence_1",
        person_id=person_id,
        place_id=place_id,
        start=Endpoint(earliest=f"{first_start_year:04d}", latest=f"{first_start_year:04d}"),
        end=Endpoint(earliest=f"{first_end_year:04d}", latest=f"{first_end_year:04d}"),
        role_in_household="",
        observations=[first_obs],
        notes="",
    )

    second_end_year = draw(st.integers(min_value=second_start_year + 1, max_value=2050))
    second_obs = _make_observation("source_2", second_start_year, second_end_year)

    fact_b = ResidenceFact(
        id="residence_2",
        person_id=person_id,
        place_id=place_id,
        start=Endpoint(earliest=f"{second_start_year:04d}", latest=f"{second_start_year:04d}"),
        end=Endpoint(earliest=f"{second_end_year:04d}", latest=f"{second_end_year:04d}"),
        role_in_household="",
        observations=[second_obs],
        notes="",
    )

    # Flytt event dated inside the gap
    flytt_year = draw(st.integers(min_value=first_end_year + 1, max_value=second_start_year - 1))
    flytt_event = Event(
        id="event_1",
        type="flytt",
        participants=[Participant(person_id=person_id, role="primary")],
        date=DateValue(value=f"{flytt_year:04d}", precision="year"),
        place=PlaceRef(place_id="place_2"),
    )

    # Bridging observation that covers the gap
    bridge_obs = _make_observation("source_3", first_end_year + 1, second_start_year - 1)

    person = Person(
        id=person_id,
        sex="M",
        names=[Name(type="birth", given="Anders", surname="Andersson")],
    )
    place_a = Place(id=place_id, type="farm", name="Norrgården")
    place_b = Place(id="place_2", type="farm", name="Södergården")
    sources = [_make_source("source_1"), _make_source("source_2"), _make_source("source_3")]

    data = ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=[person],
        places=[place_a, place_b],
        sources=sources,
        residences=[fact_a, fact_b],
        events=[flytt_event],
    )

    return fact_a, fact_b, bridge_obs, data


@st.composite
def _separated_pair_with_other_place_suppression(draw: DrawFn):
    """Generate two same-person same-place facts with another fact at a different place
    whose Possible_Span overlaps the separating years.

    This should suppress the merge offer per Requirement 17.14.
    """
    person_id = "person_1"
    place_id = "place_1"

    # Create a gap — need at least 2 separating years so the other fact can overlap.
    first_end_year = draw(st.integers(min_value=1600, max_value=1850))
    gap_size = draw(st.integers(min_value=2, max_value=15))
    second_start_year = first_end_year + gap_size + 1
    # Separating years are first_end_year+1 through second_start_year-1.

    first_start_year = draw(st.integers(min_value=1550, max_value=first_end_year - 1))
    first_obs = _make_observation("source_1", first_start_year, first_end_year)

    fact_a = ResidenceFact(
        id="residence_1",
        person_id=person_id,
        place_id=place_id,
        start=Endpoint(earliest=f"{first_start_year:04d}", latest=f"{first_start_year:04d}"),
        end=Endpoint(earliest=f"{first_end_year:04d}", latest=f"{first_end_year:04d}"),
        role_in_household="",
        observations=[first_obs],
        notes="",
    )

    second_end_year = draw(st.integers(min_value=second_start_year + 1, max_value=2050))
    second_obs = _make_observation("source_2", second_start_year, second_end_year)

    fact_b = ResidenceFact(
        id="residence_2",
        person_id=person_id,
        place_id=place_id,
        start=Endpoint(earliest=f"{second_start_year:04d}", latest=f"{second_start_year:04d}"),
        end=Endpoint(earliest=f"{second_end_year:04d}", latest=f"{second_end_year:04d}"),
        role_in_household="",
        observations=[second_obs],
        notes="",
    )

    # Another fact at a different place whose Possible_Span overlaps the separating years.
    # The separating years are first_end_year+1 to second_start_year-1.
    # The other fact's Possible_Span (start.earliest to end.latest) must overlap that range.
    # To guarantee overlap, the other fact must start at or before the last separating year
    # and end at or after the first separating year.
    first_sep_year = first_end_year + 1
    last_sep_year = second_start_year - 1
    # Pick a start for the other fact that is at most the last separating year.
    other_start = draw(st.integers(min_value=first_sep_year, max_value=last_sep_year))
    # Pick an end that is at least the other_start (and at least first_sep_year).
    other_end = draw(st.integers(min_value=other_start, max_value=last_sep_year + 5))
    other_obs = _make_observation("source_4", other_start, other_end)

    other_fact = ResidenceFact(
        id="residence_3",
        person_id=person_id,
        place_id="place_2",  # Different place
        start=Endpoint(earliest=f"{other_start:04d}", latest=f"{other_start:04d}"),
        end=Endpoint(earliest=f"{other_end:04d}", latest=f"{other_end:04d}"),
        role_in_household="",
        observations=[other_obs],
        notes="",
    )

    # Bridging observation that covers the gap
    bridge_obs = _make_observation("source_3", first_end_year + 1, second_start_year - 1)

    person = Person(
        id=person_id,
        sex="M",
        names=[Name(type="birth", given="Anders", surname="Andersson")],
    )
    place_a = Place(id=place_id, type="farm", name="Norrgården")
    place_b = Place(id="place_2", type="farm", name="Södergården")
    sources = [
        _make_source("source_1"),
        _make_source("source_2"),
        _make_source("source_3"),
        _make_source("source_4"),
    ]

    data = ProjectData(
        project=ProjectMetadata(title="Test"),
        persons=[person],
        places=[place_a, place_b],
        sources=sources,
        residences=[fact_a, fact_b, other_fact],
        events=[],
    )

    return fact_a, fact_b, bridge_obs, data


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestMergeOfferSuppressionProperty:
    """Property 36: Merge offers appear and are suppressed by documented absence.

    **Validates: Requirements 17.13, 17.14**
    """

    @given(data=_separated_pair_with_bridging_obs())
    @settings(max_examples=100, deadline=None)
    def test_merge_offer_appears_when_observation_bridges_gap(
        self,
        data: tuple[ResidenceFact, ResidenceFact, Observation, ProjectData],
    ) -> None:
        """A merge is offered when an attached observation covers every separating year.

        Feature: residence-periods, Property 36

        **Validates: Requirements 17.13, 17.14**
        """
        fact_a, fact_b, bridge_obs, project_data = data

        # Deep copy facts to verify they are not mutated on decline.
        fact_a_before = copy.deepcopy(fact_a)
        fact_b_before = copy.deepcopy(fact_b)

        # The merge should be offered because the bridge_obs covers every
        # separating year between the two facts' Possible_Spans.
        result = should_offer_merge(fact_a, fact_b, bridge_obs, project_data)
        assert result is True, (
            f"Expected merge offer for facts separated by gap "
            f"with bridging obs {bridge_obs.observed_from}–{bridge_obs.observed_to}"
        )

        # Verify it is NOT suppressed (no flytt or other-place fact in the gap).
        suppressed = is_merge_suppressed(fact_a, fact_b, project_data)
        assert suppressed is False, "Merge should not be suppressed when no flytt or other-place fact exists"

        # Declining the offer leaves both facts unchanged apart from the new observation.
        # The original facts should still be identical to their deep copies.
        assert fact_a.id == fact_a_before.id
        assert fact_a.person_id == fact_a_before.person_id
        assert fact_a.place_id == fact_a_before.place_id
        assert fact_a.start.earliest == fact_a_before.start.earliest
        assert fact_a.start.latest == fact_a_before.start.latest
        assert fact_a.end.earliest == fact_a_before.end.earliest
        assert fact_a.end.latest == fact_a_before.end.latest
        assert fact_a.role_in_household == fact_a_before.role_in_household
        assert fact_a.notes == fact_a_before.notes
        assert len(fact_a.observations) == len(fact_a_before.observations)

        assert fact_b.id == fact_b_before.id
        assert fact_b.person_id == fact_b_before.person_id
        assert fact_b.place_id == fact_b_before.place_id
        assert fact_b.start.earliest == fact_b_before.start.earliest
        assert fact_b.start.latest == fact_b_before.start.latest
        assert fact_b.end.earliest == fact_b_before.end.earliest
        assert fact_b.end.latest == fact_b_before.end.latest
        assert fact_b.role_in_household == fact_b_before.role_in_household
        assert fact_b.notes == fact_b_before.notes
        assert len(fact_b.observations) == len(fact_b_before.observations)

    @given(data=_separated_pair_with_flytt_suppression())
    @settings(max_examples=100, deadline=None)
    def test_merge_suppressed_by_flytt_event_inside_separation(
        self,
        data: tuple[ResidenceFact, ResidenceFact, Observation, ProjectData],
    ) -> None:
        """The merge offer is withheld when a Flytt_Event is dated inside the separation.

        Feature: residence-periods, Property 36

        **Validates: Requirements 17.13, 17.14**
        """
        fact_a, fact_b, bridge_obs, project_data = data

        # The merge should be suppressed because a flytt event of the same person
        # is dated inside the separating years.
        suppressed = is_merge_suppressed(fact_a, fact_b, project_data)
        assert suppressed is True, (
            "Merge should be suppressed when a Flytt_Event of the same person "
            "is dated inside the separating years"
        )

        # should_offer_merge should return False because suppression applies.
        result = should_offer_merge(fact_a, fact_b, bridge_obs, project_data)
        assert result is False, (
            "Merge should not be offered when suppressed by a Flytt_Event"
        )

    @given(data=_separated_pair_with_other_place_suppression())
    @settings(max_examples=100, deadline=None)
    def test_merge_suppressed_by_other_place_fact_overlapping_separation(
        self,
        data: tuple[ResidenceFact, ResidenceFact, Observation, ProjectData],
    ) -> None:
        """The merge offer is withheld when another fact at a different place overlaps the separation.

        Feature: residence-periods, Property 36

        **Validates: Requirements 17.13, 17.14**
        """
        fact_a, fact_b, bridge_obs, project_data = data

        # The merge should be suppressed because another Residence_Fact of the same
        # person at a different place has a Possible_Span overlapping the separation.
        suppressed = is_merge_suppressed(fact_a, fact_b, project_data)
        assert suppressed is True, (
            "Merge should be suppressed when another fact at a different place "
            "overlaps the separating years"
        )

        # should_offer_merge should return False because suppression applies.
        result = should_offer_merge(fact_a, fact_b, bridge_obs, project_data)
        assert result is False, (
            "Merge should not be offered when suppressed by other-place fact"
        )
