"""Unit tests for residence interval rendering in the person list.

Validates that the person list renders residence intervals through
format_residence_interval with no channel-local wording, abbreviation
or truncation (Requirement 11.7).
"""

from __future__ import annotations

from slaktbusken.model.person import Name, Person
from slaktbusken.model.place import Place
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.ui.person_list_panel import build_person_display_list
from slaktbusken.ui.swedish_locale import format_residence_interval


class TestPersonListResidenceIntervals:
    """Residence interval rendering in the person list."""

    def _make_person(self, person_id: str = "person_1") -> Person:
        return Person(
            id=person_id,
            sex="M",
            names=[Name(type="birth", given="Anders", surname="Andersson")],
        )

    def test_single_exact_interval(self) -> None:
        """A single residence with exact bounds renders its interval."""
        person = self._make_person()
        place = Place(id="pl1", type="farm", name="Ekeby")
        fact = ResidenceFact(
            id="r1",
            person_id="person_1",
            place_id="pl1",
            start=Endpoint(earliest="1840", latest="1840"),
            end=Endpoint(earliest="1846", latest="1846"),
        )

        result = build_person_display_list(
            persons=[person],
            events=[],
            places=[place],
            residences=[fact],
        )

        assert len(result) == 1
        expected = format_residence_interval(fact.start, fact.end)
        assert result[0].residence_intervals == expected
        assert result[0].residence_intervals == "1840\u20131846"

    def test_open_endpoint_interval(self) -> None:
        """Open endpoints render through the formatter without abbreviation."""
        person = self._make_person()
        place = Place(id="pl1", type="farm", name="Ekeby")
        fact = ResidenceFact(
            id="r1",
            person_id="person_1",
            place_id="pl1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1870"),
        )

        result = build_person_display_list(
            persons=[person],
            events=[],
            places=[place],
            residences=[fact],
        )

        expected = format_residence_interval(fact.start, fact.end)
        assert result[0].residence_intervals == expected
        assert result[0].residence_intervals == "senast 1840\u2013tidigast 1870"

    def test_unknown_period(self) -> None:
        """Both endpoints unknown renders as 'okänd period'."""
        person = self._make_person()
        place = Place(id="pl1", type="farm", name="Ekeby")
        fact = ResidenceFact(
            id="r1",
            person_id="person_1",
            place_id="pl1",
            start=Endpoint(),
            end=Endpoint(),
        )

        result = build_person_display_list(
            persons=[person],
            events=[],
            places=[place],
            residences=[fact],
        )

        assert result[0].residence_intervals == "okänd period"

    def test_multiple_residences_joined_with_semicolons(self) -> None:
        """Multiple residence facts are joined with semicolons."""
        person = self._make_person()
        place = Place(id="pl1", type="farm", name="Ekeby")
        fact1 = ResidenceFact(
            id="r1",
            person_id="person_1",
            place_id="pl1",
            start=Endpoint(earliest="1840", latest="1840"),
            end=Endpoint(earliest="1846", latest="1846"),
        )
        fact2 = ResidenceFact(
            id="r2",
            person_id="person_1",
            place_id="pl1",
            start=Endpoint(earliest="1850", latest="1850"),
            end=Endpoint(earliest="1860", latest="1860"),
        )

        result = build_person_display_list(
            persons=[person],
            events=[],
            places=[place],
            residences=[fact1, fact2],
        )

        expected = (
            f"{format_residence_interval(fact1.start, fact1.end)}; "
            f"{format_residence_interval(fact2.start, fact2.end)}"
        )
        assert result[0].residence_intervals == expected

    def test_no_residences_gives_empty_string(self) -> None:
        """A person with no residence facts gets an empty intervals string."""
        person = self._make_person()

        result = build_person_display_list(
            persons=[person],
            events=[],
            places=[],
            residences=[],
        )

        assert result[0].residence_intervals == ""

    def test_intervals_ordered_by_start_earliest_absent_first(self) -> None:
        """Residences are ordered by start.earliest with absent sorting first."""
        person = self._make_person()
        place = Place(id="pl1", type="farm", name="Ekeby")
        # fact_later has start.earliest = "1860", fact_earlier has no start.earliest
        fact_later = ResidenceFact(
            id="r1",
            person_id="person_1",
            place_id="pl1",
            start=Endpoint(earliest="1860", latest="1860"),
            end=Endpoint(earliest="1870", latest="1870"),
        )
        fact_no_earliest = ResidenceFact(
            id="r2",
            person_id="person_1",
            place_id="pl1",
            start=Endpoint(latest="1840"),
            end=Endpoint(earliest="1850"),
        )

        result = build_person_display_list(
            persons=[person],
            events=[],
            places=[place],
            residences=[fact_later, fact_no_earliest],
        )

        # fact_no_earliest (absent start.earliest) should sort before fact_later
        intervals = result[0].residence_intervals.split("; ")
        assert intervals[0] == format_residence_interval(fact_no_earliest.start, fact_no_earliest.end)
        assert intervals[1] == format_residence_interval(fact_later.start, fact_later.end)

    def test_interval_string_matches_formatter_exactly(self) -> None:
        """The rendered string matches format_residence_interval with no modification."""
        person = self._make_person()
        place = Place(id="pl1", type="farm", name="Ekeby")
        # Window endpoint
        fact = ResidenceFact(
            id="r1",
            person_id="person_1",
            place_id="pl1",
            start=Endpoint(earliest="1838", latest="1840"),
            end=Endpoint(earliest="1870", latest="1870"),
        )

        result = build_person_display_list(
            persons=[person],
            events=[],
            places=[place],
            residences=[fact],
        )

        # Must be byte-identical to what the formatter produces
        assert result[0].residence_intervals == format_residence_interval(fact.start, fact.end)

    def test_month_precision_not_truncated(self) -> None:
        """Month-precision dates are not truncated to year (Requirement 11.13)."""
        person = self._make_person()
        place = Place(id="pl1", type="farm", name="Ekeby")
        fact = ResidenceFact(
            id="r1",
            person_id="person_1",
            place_id="pl1",
            start=Endpoint(earliest="1840-06", latest="1840-06"),
            end=Endpoint(earliest="1846-12", latest="1846-12"),
        )

        result = build_person_display_list(
            persons=[person],
            events=[],
            places=[place],
            residences=[fact],
        )

        assert result[0].residence_intervals == "1840-06\u20131846-12"

    def test_residences_for_other_persons_not_included(self) -> None:
        """A residence belonging to a different person is not shown."""
        person = self._make_person("person_1")
        other_person = Person(
            id="person_2",
            sex="F",
            names=[Name(type="birth", given="Lisa", surname="Bengtsson")],
        )
        place = Place(id="pl1", type="farm", name="Ekeby")
        fact = ResidenceFact(
            id="r1",
            person_id="person_2",
            place_id="pl1",
            start=Endpoint(earliest="1840", latest="1840"),
            end=Endpoint(earliest="1846", latest="1846"),
        )

        result = build_person_display_list(
            persons=[person, other_person],
            events=[],
            places=[place],
            residences=[fact],
        )

        person_1_info = next(r for r in result if r.person_id == "person_1")
        person_2_info = next(r for r in result if r.person_id == "person_2")
        assert person_1_info.residence_intervals == ""
        assert person_2_info.residence_intervals == "1840\u20131846"
