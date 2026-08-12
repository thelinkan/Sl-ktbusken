"""Unit tests for merge-offer detection and suppression.

Covers should_offer_merge, is_merge_suppressed, and _separating_years
(Requirements 17.13, 17.14).
"""

from __future__ import annotations

import pytest

from slaktbusken.model.event import (
    DateValue,
    Event,
    Participant,
    PlaceRef,
    SourceRef,
)
from slaktbusken.model.project import ProjectData
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.services.residence_edit_ops import (
    _separating_years,
    is_merge_suppressed,
    should_offer_merge,
)


def _make_source_ref(source_id: str = "src1") -> SourceRef:
    return SourceRef(source_id=source_id, quality="")


def _make_obs(from_year: str, to_year: str, source_id: str = "src1") -> Observation:
    return Observation(
        source_ref=_make_source_ref(source_id),
        observed_from=from_year,
        observed_to=to_year,
    )


def _make_fact(
    fact_id: str,
    person_id: str,
    place_id: str,
    start_earliest: str | None = None,
    start_latest: str | None = None,
    end_earliest: str | None = None,
    end_latest: str | None = None,
    observations: list[Observation] | None = None,
) -> ResidenceFact:
    return ResidenceFact(
        id=fact_id,
        person_id=person_id,
        place_id=place_id,
        start=Endpoint(earliest=start_earliest, latest=start_latest),
        end=Endpoint(earliest=end_earliest, latest=end_latest),
        observations=observations or [],
    )


def _make_project(
    residences: list[ResidenceFact] | None = None,
    events: list[Event] | None = None,
) -> ProjectData:
    data = ProjectData()
    data.residences = residences or []
    data.events = events or []
    return data


class TestSeparatingYears:
    """Test _separating_years computation."""

    def test_adjacent_spans_have_no_separation(self) -> None:
        """1835-1846 and 1847-1857 are adjacent (no gap year)."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1847", "1847", "1857", "1857")
        assert _separating_years(a, b) == set()

    def test_overlapping_spans_have_no_separation(self) -> None:
        """Overlapping Possible_Spans yield empty separation."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1850", "1850")
        b = _make_fact("b", "p1", "pl1", "1845", "1845", "1860", "1860")
        assert _separating_years(a, b) == set()

    def test_separated_spans(self) -> None:
        """1835-1846 and 1853-1857 yield 1847-1852 as separation."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1853", "1853", "1857", "1857")
        assert _separating_years(a, b) == {1847, 1848, 1849, 1850, 1851, 1852}

    def test_order_independent(self) -> None:
        """Separation is the same regardless of which fact is a and which is b."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1853", "1853", "1857", "1857")
        assert _separating_years(a, b) == _separating_years(b, a)

    def test_unbounded_end_has_no_separation(self) -> None:
        """A span unbounded at its end cannot be separated from another."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", None, None)
        b = _make_fact("b", "p1", "pl1", "1853", "1853", "1857", "1857")
        assert _separating_years(a, b) == set()

    def test_unbounded_start_has_no_separation(self) -> None:
        """A span unbounded at its start cannot be separated from another."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", None, None, "1857", "1857")
        assert _separating_years(a, b) == set()

    def test_one_year_gap(self) -> None:
        """1835-1846 and 1848-1857 yield exactly {1847}."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1848", "1848", "1857", "1857")
        assert _separating_years(a, b) == {1847}


class TestShouldOfferMerge:
    """Test should_offer_merge logic (Requirement 17.13)."""

    def test_offer_when_obs_covers_all_separating_years(self) -> None:
        """A new obs covering 1847-1852 bridges the gap between 1835-1846 and 1853-1857."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1853", "1853", "1857", "1857")
        new_obs = _make_obs("1847", "1852")
        data = _make_project(residences=[a, b])
        assert should_offer_merge(a, b, new_obs, data) is True

    def test_no_offer_when_obs_does_not_cover_all_years(self) -> None:
        """An obs covering 1847-1850 does NOT cover the full 1847-1852 gap."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1853", "1853", "1857", "1857")
        new_obs = _make_obs("1847", "1850")
        data = _make_project(residences=[a, b])
        assert should_offer_merge(a, b, new_obs, data) is False

    def test_no_offer_different_person(self) -> None:
        """Different person_id means no offer."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p2", "pl1", "1853", "1853", "1857", "1857")
        new_obs = _make_obs("1847", "1852")
        data = _make_project(residences=[a, b])
        assert should_offer_merge(a, b, new_obs, data) is False

    def test_no_offer_different_place(self) -> None:
        """Different place_id means no offer."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl2", "1853", "1853", "1857", "1857")
        new_obs = _make_obs("1847", "1852")
        data = _make_project(residences=[a, b])
        assert should_offer_merge(a, b, new_obs, data) is False

    def test_no_offer_when_no_separation(self) -> None:
        """Adjacent spans have no separating years; no offer needed."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1847", "1847", "1857", "1857")
        new_obs = _make_obs("1845", "1848")
        data = _make_project(residences=[a, b])
        assert should_offer_merge(a, b, new_obs, data) is False

    def test_no_offer_when_obs_has_no_years(self) -> None:
        """An obs with empty year bounds cannot cover the gap."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1853", "1853", "1857", "1857")
        new_obs = Observation(source_ref=_make_source_ref(), observed_from="", observed_to="")
        data = _make_project(residences=[a, b])
        assert should_offer_merge(a, b, new_obs, data) is False

    def test_offer_with_wider_obs(self) -> None:
        """An obs wider than the gap still qualifies (it just needs to cover all sep years)."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1853", "1853", "1857", "1857")
        new_obs = _make_obs("1840", "1860")
        data = _make_project(residences=[a, b])
        assert should_offer_merge(a, b, new_obs, data) is True

    def test_declining_leaves_facts_unchanged(self) -> None:
        """Calling should_offer_merge does not mutate fact_a, fact_b, or data."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846",
                       observations=[_make_obs("1835", "1846")])
        b = _make_fact("b", "p1", "pl1", "1853", "1853", "1857", "1857",
                       observations=[_make_obs("1853", "1857")])
        new_obs = _make_obs("1847", "1852")
        data = _make_project(residences=[a, b])

        # Snapshot before
        a_id, b_id = a.id, b.id
        a_obs_count = len(a.observations)
        b_obs_count = len(b.observations)

        should_offer_merge(a, b, new_obs, data)

        # Nothing changed
        assert a.id == a_id
        assert b.id == b_id
        assert len(a.observations) == a_obs_count
        assert len(b.observations) == b_obs_count


class TestIsMergeSuppressed:
    """Test is_merge_suppressed logic (Requirement 17.14)."""

    def test_suppressed_by_flytt_event_inside_separation(self) -> None:
        """A Flytt_Event dated inside the separating years suppresses the offer."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1853", "1853", "1857", "1857")
        flytt = Event(
            id="ev1",
            type="flytt",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value="1849", precision="year"),
            place=PlaceRef(place_id="pl2"),
        )
        data = _make_project(residences=[a, b], events=[flytt])
        assert is_merge_suppressed(a, b, data) is True

    def test_not_suppressed_when_flytt_outside_separation(self) -> None:
        """A Flytt_Event dated outside the separating years does not suppress."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1853", "1853", "1857", "1857")
        flytt = Event(
            id="ev1",
            type="flytt",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value="1860", precision="year"),
            place=PlaceRef(place_id="pl2"),
        )
        data = _make_project(residences=[a, b], events=[flytt])
        assert is_merge_suppressed(a, b, data) is False

    def test_not_suppressed_when_flytt_for_other_person(self) -> None:
        """A Flytt_Event for a different person does not suppress."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1853", "1853", "1857", "1857")
        flytt = Event(
            id="ev1",
            type="flytt",
            participants=[Participant(person_id="p2", role="subject")],
            date=DateValue(value="1849", precision="year"),
            place=PlaceRef(place_id="pl2"),
        )
        data = _make_project(residences=[a, b], events=[flytt])
        assert is_merge_suppressed(a, b, data) is False

    def test_suppressed_by_other_residence_at_different_place(self) -> None:
        """A Residence_Fact at a different place overlapping the gap suppresses."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1853", "1853", "1857", "1857")
        # Another fact at a different place whose Possible_Span overlaps 1847-1852
        other = _make_fact("c", "p1", "pl2", "1848", "1848", "1850", "1850")
        data = _make_project(residences=[a, b, other])
        assert is_merge_suppressed(a, b, data) is True

    def test_not_suppressed_by_residence_at_same_place(self) -> None:
        """A Residence_Fact at the SAME place does not suppress."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1853", "1853", "1857", "1857")
        other = _make_fact("c", "p1", "pl1", "1848", "1848", "1850", "1850")
        data = _make_project(residences=[a, b, other])
        assert is_merge_suppressed(a, b, data) is False

    def test_not_suppressed_by_residence_for_other_person(self) -> None:
        """A Residence_Fact for a different person does not suppress."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1853", "1853", "1857", "1857")
        other = _make_fact("c", "p2", "pl2", "1848", "1848", "1850", "1850")
        data = _make_project(residences=[a, b, other])
        assert is_merge_suppressed(a, b, data) is False

    def test_not_suppressed_when_other_residence_outside_gap(self) -> None:
        """A Residence_Fact at a different place but outside the gap does not suppress."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1853", "1853", "1857", "1857")
        other = _make_fact("c", "p1", "pl2", "1860", "1860", "1870", "1870")
        data = _make_project(residences=[a, b, other])
        assert is_merge_suppressed(a, b, data) is False

    def test_not_suppressed_when_no_separation(self) -> None:
        """Adjacent facts have no separating years, so nothing can suppress."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1847", "1847", "1857", "1857")
        data = _make_project(residences=[a, b])
        assert is_merge_suppressed(a, b, data) is False

    def test_suppressed_by_flytt_with_undated_does_not_suppress(self) -> None:
        """An undated Flytt_Event does not suppress (no date to check)."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1853", "1853", "1857", "1857")
        flytt = Event(
            id="ev1",
            type="flytt",
            participants=[Participant(person_id="p1", role="subject")],
            date=None,  # undated
            place=PlaceRef(place_id="pl2"),
        )
        data = _make_project(residences=[a, b], events=[flytt])
        assert is_merge_suppressed(a, b, data) is False

    def test_should_offer_merge_suppressed_by_flytt(self) -> None:
        """Integration: should_offer_merge returns False when suppressed by flytt."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1853", "1853", "1857", "1857")
        new_obs = _make_obs("1847", "1852")
        flytt = Event(
            id="ev1",
            type="flytt",
            participants=[Participant(person_id="p1", role="subject")],
            date=DateValue(value="1849", precision="year"),
            place=PlaceRef(place_id="pl2"),
        )
        data = _make_project(residences=[a, b], events=[flytt])
        assert should_offer_merge(a, b, new_obs, data) is False

    def test_should_offer_merge_suppressed_by_other_residence(self) -> None:
        """Integration: should_offer_merge returns False when suppressed by other residence."""
        a = _make_fact("a", "p1", "pl1", "1835", "1835", "1846", "1846")
        b = _make_fact("b", "p1", "pl1", "1853", "1853", "1857", "1857")
        new_obs = _make_obs("1847", "1852")
        other = _make_fact("c", "p1", "pl2", "1848", "1848", "1850", "1850")
        data = _make_project(residences=[a, b, other])
        assert should_offer_merge(a, b, new_obs, data) is False
