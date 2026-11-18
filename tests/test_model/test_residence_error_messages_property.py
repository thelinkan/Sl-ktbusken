# Feature: residence-periods, Property 2: Every violation yields its exact Swedish message with the required multiplicity
"""Property-based test for error messages and multiplicity.

Feature: residence-periods, Property 2: Every violation yields its exact Swedish message with the required multiplicity

For any Residence_Fact violating one or more stated rules, the Residence_Validator
returns for each violation exactly the specified Swedish message, once per offending
value where the requirement says so, and returns no missing-reference message for a
`person_id` or `place_id` that is blank.

**Validates: Requirements 1.5, 1.6, 1.7, 1.11, 2.9, 2.10, 2.11, 2.12, 2.14, 4.2, 4.4, 4.5, 4.12, 10.6**
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.date_span import is_valid_iso, strictly_earlier
from slaktbusken.model.event import SourceRef
from slaktbusken.model.residence import Endpoint, Observation, ResidenceFact
from slaktbusken.model.validators import validate_residence
from tests.test_model.residence_strategies import (
    MALFORMED_ISO_VALUES,
    MALFORMED_YEAR_VALUES,
    OUT_OF_RANGE_YEARS,
    endpoints,
    observations,
    residence_facts,
)

# ---------------------------------------------------------------------------
# The exact Swedish error messages, copied for test-side oracle computation.
# ---------------------------------------------------------------------------

_MSG_PERSON_AND_PLACE_REQUIRED = "Boendet måste ange både person och plats."
_MSG_UNKNOWN_PERSON = "Boendet refererar till en person som inte finns."
_MSG_UNKNOWN_PLACE = "Boendet refererar till en plats som inte finns."
_MSG_NOTES_TOO_LONG = "Anteckningen får vara högst 5000 tecken."
_MSG_ROLE_TOO_LONG = "Roll i hushållet får vara högst 100 tecken."
_MSG_MALFORMED_ISO = (
    "Datumvärdet är inte ett giltigt ISO 8601-datum "
    "(förväntat ÅÅÅÅ, ÅÅÅÅ-MM eller ÅÅÅÅ-MM-DD)."
)
_MSG_INVERTED_ENDPOINT = "Tidigaste datum får inte vara senare än senaste datum."
_MSG_END_BEFORE_START = "Boendets slut kan inte ligga före dess början."
_MSG_ENDPOINT_NOTE_TOO_LONG = "Endpunktens anteckning får vara högst 1000 tecken."
_MSG_UNKNOWN_EVENT = "Endpunkten refererar till en händelse som inte finns."
_MSG_TOO_MANY_OBSERVATIONS = "Ett boende får ha högst 100 observationer."
_MSG_BAD_OBSERVATION_YEAR = (
    "Observationens årtal måste anges som fyra siffror (ÅÅÅÅ) mellan 1500 och 2100."
)
_MSG_INVERTED_OBSERVATION = "Observationens startår får inte vara senare än dess slutår."
_MSG_UNKNOWN_OBSERVATION_SOURCE = "Observationen refererar till en källa som inte finns."

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

_NOTES_MAX = 5000
_ROLE_MAX = 100
_ENDPOINT_NOTE_MAX = 1000
_MAX_OBSERVATIONS = 100
_MIN_YEAR = 1500
_MAX_YEAR = 2100
_YEAR_RE = re.compile(r"^\d{4}$")

# ---------------------------------------------------------------------------
# Reference sets for the test – a small, known universe.
# ---------------------------------------------------------------------------

_PERSONS = {"person_1", "person_2", "person_3"}
_PLACES = {"place_1", "place_2", "place_3"}
_SOURCES = {"source_1", "source_2", "source_3"}
_EVENTS = {"event_1", "event_2", "event_3"}


# ---------------------------------------------------------------------------
# Test-side oracle: independently compute expected errors.
# ---------------------------------------------------------------------------


def _value_present(value: Optional[str]) -> bool:
    """Matches the validator's `_residence_value_present`."""
    return value is not None and bool(value.strip())


def _observation_year(value: Optional[str]) -> Optional[int]:
    """Parse a bare four-digit year, or None."""
    if value is None:
        return None
    trimmed = value.strip()
    if not _YEAR_RE.match(trimmed):
        return None
    return int(trimmed)


def _expected_endpoint_errors(
    endpoint: Endpoint,
    valid_event_ids: set[str],
) -> list[str]:
    """Compute the expected errors for one Endpoint."""
    errors: list[str] = []

    for bound in (endpoint.earliest, endpoint.latest):
        if _value_present(bound) and not is_valid_iso(bound):
            errors.append(_MSG_MALFORMED_ISO)

    if strictly_earlier(endpoint.latest, endpoint.earliest):
        errors.append(_MSG_INVERTED_ENDPOINT)

    if endpoint.note is not None and len(endpoint.note) > _ENDPOINT_NOTE_MAX:
        errors.append(_MSG_ENDPOINT_NOTE_TOO_LONG)

    if _value_present(endpoint.event_id):
        if endpoint.event_id not in valid_event_ids:
            errors.append(_MSG_UNKNOWN_EVENT)

    return errors


def _expected_observation_errors(
    obs: Observation,
    valid_source_ids: set[str],
) -> list[str]:
    """Compute the expected errors for one Observation."""
    errors: list[str] = []

    for bound in (obs.observed_from, obs.observed_to):
        if not _value_present(bound):
            continue
        year = _observation_year(bound)
        if year is None or not (_MIN_YEAR <= year <= _MAX_YEAR):
            errors.append(_MSG_BAD_OBSERVATION_YEAR)

    first = _observation_year(obs.observed_from)
    last = _observation_year(obs.observed_to)
    if first is not None and last is not None and first > last:
        errors.append(_MSG_INVERTED_OBSERVATION)

    if obs.source_ref.source_id not in valid_source_ids:
        errors.append(_MSG_UNKNOWN_OBSERVATION_SOURCE)

    return errors


def _expected_errors(fact: ResidenceFact) -> list[str]:
    """Full oracle: compute the expected error list for any fact."""
    errors: list[str] = []

    person_present = _value_present(fact.person_id)
    place_present = _value_present(fact.place_id)

    if not person_present or not place_present:
        errors.append(_MSG_PERSON_AND_PLACE_REQUIRED)

    if person_present and fact.person_id not in _PERSONS:
        errors.append(_MSG_UNKNOWN_PERSON)

    if place_present and fact.place_id not in _PLACES:
        errors.append(_MSG_UNKNOWN_PLACE)

    if len(fact.notes) > _NOTES_MAX:
        errors.append(_MSG_NOTES_TOO_LONG)

    if len(fact.role_in_household.strip()) > _ROLE_MAX:
        errors.append(_MSG_ROLE_TOO_LONG)

    errors.extend(_expected_endpoint_errors(fact.start, _EVENTS))
    errors.extend(_expected_endpoint_errors(fact.end, _EVENTS))

    if strictly_earlier(fact.end.latest, fact.start.earliest):
        errors.append(_MSG_END_BEFORE_START)

    if len(fact.observations) > _MAX_OBSERVATIONS:
        errors.append(_MSG_TOO_MANY_OBSERVATIONS)

    for obs in fact.observations:
        errors.extend(_expected_observation_errors(obs, _SOURCES))

    return errors


# ---------------------------------------------------------------------------
# Strategy: Residence facts with violations injected against the known sets.
# ---------------------------------------------------------------------------


@st.composite
def _violating_residence_facts(draw: DrawFn) -> ResidenceFact:
    """Generate a Residence_Fact that may have one or more violations.

    Uses the shared strategy with person/place/source/event pools drawn from
    our fixed test sets. The strategy's `include_blank_references=True` (default)
    ensures blank person_id/place_id are generated. Malformed bounds, inverted
    spans, excessive lengths, and unknown references all occur naturally through
    the strategy's shape selectors.
    """
    return draw(
        residence_facts(
            person_ids=list(_PERSONS) + ["person_99", ""],
            place_ids=list(_PLACES) + ["place_99", "", "   "],
            source_ids=list(_SOURCES) + ["source_99", ""],
            event_ids=list(_EVENTS) + ["event_99"],
            include_blank_references=True,
            include_many_observations=True,
        )
    )


# ---------------------------------------------------------------------------
# The property test
# ---------------------------------------------------------------------------


class TestErrorMessagesAndMultiplicity:
    """Property 2: Every violation yields its exact Swedish message with the required multiplicity.

    For any Residence_Fact violating one or more stated rules, the
    Residence_Validator returns for each violation exactly the specified Swedish
    message, once per offending value where the requirement says so, and returns
    no missing-reference message for a `person_id` or `place_id` that is blank.

    **Validates: Requirements 1.5, 1.6, 1.7, 1.11, 2.9, 2.10, 2.11, 2.12, 2.14, 4.2, 4.4, 4.5, 4.12, 10.6**
    """

    @given(fact=_violating_residence_facts())
    @settings(max_examples=100, deadline=None)
    def test_error_messages_match_multiplicity(self, fact: ResidenceFact) -> None:
        """The validator produces exactly the expected messages with correct counts.

        Feature: residence-periods, Property 2: Every violation yields its exact Swedish message with the required multiplicity

        **Validates: Requirements 1.5, 1.6, 1.7, 1.11, 2.9, 2.10, 2.11, 2.12, 2.14, 4.2, 4.4, 4.5, 4.12, 10.6**
        """
        actual = validate_residence(fact, _PERSONS, _PLACES, _SOURCES, _EVENTS)
        expected = _expected_errors(fact)

        # Both the multiset of messages and the order must match.
        assert Counter(actual) == Counter(expected), (
            f"Message multiplicity mismatch.\n"
            f"  actual:   {Counter(actual)}\n"
            f"  expected: {Counter(expected)}\n"
            f"  fact.person_id={fact.person_id!r}, fact.place_id={fact.place_id!r}\n"
        )
        assert actual == expected, (
            f"Message order mismatch.\n"
            f"  actual:   {actual}\n"
            f"  expected: {expected}\n"
        )

    @given(fact=_violating_residence_facts())
    @settings(max_examples=100, deadline=None)
    def test_blank_ids_suppress_missing_reference(self, fact: ResidenceFact) -> None:
        """Blank person_id/place_id never triggers the missing-reference message.

        Feature: residence-periods, Property 2: Every violation yields its exact Swedish message with the required multiplicity

        **Validates: Requirements 1.7**
        """
        actual = validate_residence(fact, _PERSONS, _PLACES, _SOURCES, _EVENTS)

        person_blank = not _value_present(fact.person_id)
        place_blank = not _value_present(fact.place_id)

        if person_blank:
            assert _MSG_UNKNOWN_PERSON not in actual, (
                f"Blank person_id={fact.person_id!r} triggered unknown-person"
            )
        if place_blank:
            assert _MSG_UNKNOWN_PLACE not in actual, (
                f"Blank place_id={fact.place_id!r} triggered unknown-place"
            )

    @given(fact=_violating_residence_facts())
    @settings(max_examples=100, deadline=None)
    def test_blank_ids_yield_at_most_one_required_message(
        self, fact: ResidenceFact
    ) -> None:
        """However many fields are blank, there is exactly one "required" message.

        Feature: residence-periods, Property 2: Every violation yields its exact Swedish message with the required multiplicity

        **Validates: Requirements 1.7**
        """
        actual = validate_residence(fact, _PERSONS, _PLACES, _SOURCES, _EVENTS)

        person_blank = not _value_present(fact.person_id)
        place_blank = not _value_present(fact.place_id)

        required_count = actual.count(_MSG_PERSON_AND_PLACE_REQUIRED)

        if person_blank or place_blank:
            assert required_count == 1, (
                f"Expected exactly 1 'required' message, got {required_count}"
            )
        else:
            assert required_count == 0

    @given(fact=_violating_residence_facts())
    @settings(max_examples=100, deadline=None)
    def test_malformed_iso_one_per_offending_value(self, fact: ResidenceFact) -> None:
        """Each present but malformed ISO bound yields exactly one message.

        Feature: residence-periods, Property 2: Every violation yields its exact Swedish message with the required multiplicity

        **Validates: Requirements 2.11**
        """
        actual = validate_residence(fact, _PERSONS, _PLACES, _SOURCES, _EVENTS)

        # Count malformed bounds across both endpoints.
        expected_count = 0
        for ep in (fact.start, fact.end):
            for bound in (ep.earliest, ep.latest):
                if _value_present(bound) and not is_valid_iso(bound):
                    expected_count += 1

        actual_count = actual.count(_MSG_MALFORMED_ISO)
        assert actual_count == expected_count, (
            f"Expected {expected_count} malformed-ISO messages, got {actual_count}"
        )
