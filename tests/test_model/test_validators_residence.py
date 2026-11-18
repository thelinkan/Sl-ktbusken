"""Unit tests for `validate_residence` (errors only).

One test per row of the error table in the residence-periods design, plus the
cases the design calls out as deliberately error-free.
"""

from __future__ import annotations

import pytest

from slaktbusken.model.event import SourceRef
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.validators import validate_residence


PERSONS = {"person_1"}
PLACES = {"place_1"}
SOURCES = {"source_1"}
EVENTS = {"event_1"}


def make_fact(**overrides: object) -> ResidenceFact:
    """A Residence_Fact that validates clean, with the given fields replaced."""
    fields: dict[str, object] = {
        "id": "residence_1",
        "person_id": "person_1",
        "place_id": "place_1",
        "start": Endpoint(earliest="1866", latest="1867"),
        "end": Endpoint(earliest="1870", latest="1871"),
        "role_in_household": "dräng",
        "observations": [],
        "notes": "",
    }
    fields.update(overrides)
    return ResidenceFact(**fields)  # type: ignore[arg-type]


def make_observation(
    observed_from: str = "1866",
    observed_to: str = "1870",
    source_id: str = "source_1",
) -> Observation:
    return Observation(
        source_ref=SourceRef(source_id=source_id, quality="primary"),
        observed_from=observed_from,
        observed_to=observed_to,
    )


def validate(fact: ResidenceFact) -> list[str]:
    """Validate against the fully populated reference sets."""
    return validate_residence(fact, PERSONS, PLACES, SOURCES, EVENTS)


# ---------------------------------------------------------------------------
# Clean facts (Requirement 1.13)
# ---------------------------------------------------------------------------


class TestCleanFacts:
    def test_well_formed_fact_has_no_errors(self) -> None:
        assert validate(make_fact()) == []

    def test_fact_with_observations_and_event_links_has_no_errors(self) -> None:
        fact = make_fact(
            start=Endpoint(earliest="1866", latest="1867", event_id="event_1"),
            observations=[make_observation(), make_observation("1868", "1870")],
        )
        assert validate(fact) == []

    def test_both_endpoints_unknown_has_no_errors(self) -> None:
        """Requirement 2.8, 4.11: an undated but sourced fact is valid."""
        fact = make_fact(
            start=Endpoint(),
            end=Endpoint(earliest="   ", latest=None),
            observations=[make_observation()],
        )
        assert validate(fact) == []

    def test_one_sided_observation_span_has_no_errors(self) -> None:
        """Requirement 4.6."""
        fact = make_fact(observations=[make_observation("1866", ""), make_observation("", "1870")])
        assert validate(fact) == []

    def test_reference_checks_are_skipped_when_no_sets_are_given(self) -> None:
        fact = make_fact(
            person_id="person_99",
            place_id="place_99",
            start=Endpoint(earliest="1866", latest="1867", event_id="event_99"),
            observations=[make_observation(source_id="source_99")],
        )
        assert validate_residence(fact) == []

    def test_unknown_precision_yields_no_error(self) -> None:
        """Requirement 2.3: `precision` is descriptive only."""
        for precision in ("day", "month", "year", "approximate", "cirka", None):
            fact = make_fact(
                start=Endpoint(earliest="1866", latest="1867", precision=precision),
                end=Endpoint(earliest="1870", latest="1871", precision=precision),
            )
            assert validate(fact) == [], f"precision {precision!r} produced errors"

    def test_year_and_month_bounds_on_one_endpoint_are_no_error(self) -> None:
        """Requirement 2.9/2.15: "1840" is neither earlier nor later than "1840-06"."""
        fact = make_fact(start=Endpoint(earliest="1866", latest="1866-06"))
        assert validate(fact) == []

    def test_duplicate_person_place_combination_yields_no_error(self) -> None:
        """Requirement 1.4."""
        first = make_fact(id="residence_1")
        second = make_fact(id="residence_2")
        assert validate(first) == []
        assert validate(second) == []

    def test_notes_at_the_limit_are_accepted(self) -> None:
        assert validate(make_fact(notes="x" * 5000)) == []

    def test_role_at_the_limit_after_trimming_is_accepted(self) -> None:
        assert validate(make_fact(role_in_household="  " + "x" * 100 + "  ")) == []

    def test_endpoint_note_at_the_limit_is_accepted(self) -> None:
        fact = make_fact(start=Endpoint(earliest="1866", latest="1867", note="x" * 1000))
        assert validate(fact) == []

    def test_one_hundred_observations_are_accepted(self) -> None:
        """Requirement 4.2: the limit itself is valid."""
        fact = make_fact(observations=[make_observation() for _ in range(100)])
        assert validate(fact) == []


# ---------------------------------------------------------------------------
# Person and place references (Requirements 1.5, 1.6, 1.7)
# ---------------------------------------------------------------------------


class TestPersonAndPlaceReferences:
    def test_unknown_person_is_reported_once(self) -> None:
        errors = validate(make_fact(person_id="person_99"))
        assert errors == ["Boendet refererar till en person som inte finns."]

    def test_unknown_place_is_reported_once(self) -> None:
        errors = validate(make_fact(place_id="place_99"))
        assert errors == ["Boendet refererar till en plats som inte finns."]

    @pytest.mark.parametrize("blank", ["", "   ", "\t"])
    def test_blank_person_suppresses_the_missing_person_message(self, blank: str) -> None:
        errors = validate(make_fact(person_id=blank))
        assert errors == ["Boendet måste ange både person och plats."]

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_place_suppresses_the_missing_place_message(self, blank: str) -> None:
        errors = validate(make_fact(place_id=blank))
        assert errors == ["Boendet måste ange både person och plats."]

    def test_both_blank_yields_exactly_one_message(self) -> None:
        errors = validate(make_fact(person_id="", place_id="  "))
        assert errors == ["Boendet måste ange både person och plats."]

    def test_blank_person_with_unknown_place_reports_both_conditions(self) -> None:
        errors = validate(make_fact(person_id="", place_id="place_99"))
        assert errors == [
            "Boendet måste ange både person och plats.",
            "Boendet refererar till en plats som inte finns.",
        ]


# ---------------------------------------------------------------------------
# Text lengths (Requirements 1.11, 2.14, 10.6)
# ---------------------------------------------------------------------------


class TestTextLengths:
    def test_notes_over_the_limit(self) -> None:
        errors = validate(make_fact(notes="x" * 5001))
        assert errors == ["Anteckningen får vara högst 5000 tecken."]

    def test_role_over_the_limit_after_trimming(self) -> None:
        errors = validate(make_fact(role_in_household=" " + "x" * 101 + " "))
        assert errors == ["Roll i hushållet får vara högst 100 tecken."]

    def test_endpoint_note_over_the_limit(self) -> None:
        fact = make_fact(start=Endpoint(earliest="1866", latest="1867", note="x" * 1001))
        assert validate(fact) == ["Endpunktens anteckning får vara högst 1000 tecken."]

    def test_both_endpoint_notes_over_the_limit_yield_two_messages(self) -> None:
        fact = make_fact(
            start=Endpoint(earliest="1866", latest="1867", note="x" * 1001),
            end=Endpoint(earliest="1870", latest="1871", note="y" * 1001),
        )
        assert validate(fact) == ["Endpunktens anteckning får vara högst 1000 tecken."] * 2


# ---------------------------------------------------------------------------
# Endpoint bounds (Requirements 2.9, 2.10, 2.11, 2.12)
# ---------------------------------------------------------------------------


MALFORMED_ISO_MESSAGE = (
    "Datumvärdet är inte ett giltigt ISO 8601-datum "
    "(förväntat ÅÅÅÅ, ÅÅÅÅ-MM eller ÅÅÅÅ-MM-DD)."
)


class TestEndpointBounds:
    @pytest.mark.parametrize(
        "value",
        ["184", "18400", "1840-13", "1840-6-1", "1841-02-29", "ca 1840", "okänt"],
    )
    def test_malformed_bound_is_reported_once(self, value: str) -> None:
        fact = make_fact(start=Endpoint(earliest=value, latest=None))
        assert validate(fact) == [MALFORMED_ISO_MESSAGE]

    def test_one_message_per_offending_value(self) -> None:
        fact = make_fact(
            start=Endpoint(earliest="184", latest="okänt"),
            end=Endpoint(earliest="1870", latest="1840-13"),
        )
        assert validate(fact) == [MALFORMED_ISO_MESSAGE] * 3

    def test_padded_bound_is_not_malformed(self) -> None:
        fact = make_fact(start=Endpoint(earliest="  1866 ", latest="\t1867\n"))
        assert validate(fact) == []

    def test_inverted_endpoint_bounds(self) -> None:
        fact = make_fact(start=Endpoint(earliest="1867", latest="1866"))
        assert validate(fact) == ["Tidigaste datum får inte vara senare än senaste datum."]

    def test_inverted_bounds_on_both_endpoints_yield_two_messages(self) -> None:
        fact = make_fact(
            start=Endpoint(earliest="1867", latest="1866"),
            end=Endpoint(earliest="1871", latest="1870"),
        )
        assert validate(fact) == ["Tidigaste datum får inte vara senare än senaste datum."] * 2

    def test_end_before_start(self) -> None:
        fact = make_fact(
            start=Endpoint(earliest="1880", latest="1881"),
            end=Endpoint(earliest="1870", latest="1871"),
        )
        assert validate(fact) == ["Boendets slut kan inte ligga före dess början."]

    def test_overlapping_start_and_end_windows_are_no_error(self) -> None:
        """Requirement 2.10/2.17: an empty core is a warning, not an error."""
        fact = make_fact(
            start=Endpoint(earliest="1866", latest="1875"),
            end=Endpoint(earliest="1870", latest="1880"),
        )
        assert validate(fact) == []

    def test_unknown_event_reference(self) -> None:
        fact = make_fact(start=Endpoint(earliest="1866", latest="1867", event_id="event_99"))
        assert validate(fact) == ["Endpunkten refererar till en händelse som inte finns."]

    def test_unknown_event_reference_on_both_endpoints(self) -> None:
        fact = make_fact(
            start=Endpoint(earliest="1866", latest="1867", event_id="event_98"),
            end=Endpoint(earliest="1870", latest="1871", event_id="event_99"),
        )
        assert validate(fact) == ["Endpunkten refererar till en händelse som inte finns."] * 2

    @pytest.mark.parametrize("event_id", [None, "", "   "])
    def test_absent_event_reference_is_no_error(self, event_id: object) -> None:
        fact = make_fact(
            start=Endpoint(earliest="1866", latest="1867", event_id=event_id)  # type: ignore[arg-type]
        )
        assert validate(fact) == []


# ---------------------------------------------------------------------------
# Observations (Requirements 4.2, 4.4, 4.5, 4.12)
# ---------------------------------------------------------------------------


BAD_YEAR_MESSAGE = (
    "Observationens årtal måste anges som fyra siffror (ÅÅÅÅ) mellan 1500 och 2100."
)


class TestObservations:
    def test_more_than_one_hundred_observations(self) -> None:
        fact = make_fact(observations=[make_observation() for _ in range(101)])
        assert validate(fact) == ["Ett boende får ha högst 100 observationer."]

    @pytest.mark.parametrize("value", ["18ab", "184", "1840-06", "ca 1840", "1499", "2101", "9999"])
    def test_malformed_or_out_of_range_year(self, value: str) -> None:
        fact = make_fact(observations=[make_observation(observed_from=value, observed_to="")])
        assert validate(fact) == [BAD_YEAR_MESSAGE]

    def test_one_message_per_offending_bound(self) -> None:
        fact = make_fact(observations=[make_observation("1499", "2101")])
        assert validate(fact) == [BAD_YEAR_MESSAGE] * 2

    def test_each_offending_observation_is_reported(self) -> None:
        fact = make_fact(
            observations=[make_observation("18ab", ""), make_observation("", "okänt")]
        )
        assert validate(fact) == [BAD_YEAR_MESSAGE] * 2

    def test_inverted_observation_span(self) -> None:
        fact = make_fact(observations=[make_observation("1870", "1866")])
        assert validate(fact) == ["Observationens startår får inte vara senare än dess slutår."]

    def test_equal_observation_bounds_are_no_error(self) -> None:
        fact = make_fact(observations=[make_observation("1866", "1866")])
        assert validate(fact) == []

    def test_unknown_observation_source(self) -> None:
        fact = make_fact(observations=[make_observation(source_id="source_99")])
        assert validate(fact) == ["Observationen refererar till en källa som inte finns."]

    def test_blank_observation_source(self) -> None:
        fact = make_fact(observations=[make_observation(source_id="")])
        assert validate(fact) == ["Observationen refererar till en källa som inte finns."]

    def test_duplicate_source_on_one_fact_is_no_error(self) -> None:
        """Requirement 4.13: reported as a warning-level finding instead."""
        fact = make_fact(observations=[make_observation(), make_observation()])
        assert validate(fact) == []
