# Feature: residence-periods, Property 3: Endpoint classification is total, absence-driven and precision-independent
"""Property-based test for Endpoint classification.

Feature: residence-periods, Property 3: Endpoint classification is total, absence-driven and precision-independent

For any Endpoint, classification returns exactly one of exact date, open (only
`latest`), open (only `earliest`), transition window, or unknown, determined
solely by which bounds are present — treating an empty or whitespace-only value
as absent — and by whether the two present values denote the same day interval;
varying `precision` over its four permitted values changes neither the
classification, nor the error list, nor any derived interval.

**Validates: Requirements 2.1, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8**
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.date_span import expand_iso
from slaktbusken.model.residence import (
    Endpoint,
    EndpointKind,
    ResidenceFact,
    certain_core,
    classify_endpoint,
    possible_span,
)
from tests.test_model.residence_strategies import (
    ABSENT_ISO_VALUES,
    PRECISION_VALUES,
    endpoints,
    iso_values,
    residence_facts,
)

#: The four `precision` values Requirement 2.3 permits. Requirement 2.3 makes the
#: field descriptive only, so none of them may alter any outcome.
PERMITTED_PRECISIONS: tuple[str, ...] = ("day", "month", "year", "approximate")

#: `validate_residence` arrives with task 3.1. Until then the error-list clause of
#: this property has nothing to assert against.
try:  # pragma: no cover - import guard, not logic
    from slaktbusken.model.validators import validate_residence  # type: ignore

    _HAS_VALIDATOR = True
except ImportError:  # pragma: no cover
    _HAS_VALIDATOR = False


@st.composite
def _raw_endpoints(draw: DrawFn) -> Endpoint:
    """Build an Endpoint from two independently drawn bound values.

    `endpoints()` samples the five classifications; this samples the raw bound
    space instead, so absent, padded and malformed values meet each other in
    every combination.
    """
    return Endpoint(
        earliest=draw(iso_values()),
        latest=draw(iso_values()),
        precision=draw(st.sampled_from(PRECISION_VALUES)),
        event_id=draw(st.none() | st.just("event_1")),
        note=draw(st.none() | st.just("anteckning")),
    )


def _any_endpoints() -> st.SearchStrategy[Endpoint]:
    """The whole Endpoint space: the five shaped classifications plus raw pairs."""
    return st.one_of(endpoints(), _raw_endpoints())


def _present(value: Optional[str]) -> bool:
    """Requirement 2.1: empty and whitespace-only values count as absent."""
    return value is not None and bool(value.strip())


class TestEndpointClassification:
    """Property 3: Endpoint classification is total, absence-driven and precision-independent.

    For any Endpoint, classification returns exactly one of exact date, open
    (only `latest`), open (only `earliest`), transition window, or unknown,
    determined solely by which bounds are present — treating an empty or
    whitespace-only value as absent — and by whether the two present values
    denote the same day interval; varying `precision` over its four permitted
    values changes neither the classification, nor the error list, nor any
    derived interval.

    **Validates: Requirements 2.1, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8**
    """

    @given(endpoint=_any_endpoints())
    @settings(max_examples=100, deadline=None)
    def test_classification_is_total(self, endpoint: Endpoint) -> None:
        """Every Endpoint classifies as exactly one EndpointKind.

        Feature: residence-periods, Property 3: Endpoint classification is total, absence-driven and precision-independent

        **Validates: Requirements 2.4, 2.5, 2.6, 2.7, 2.8**
        """
        kind = classify_endpoint(endpoint)

        assert isinstance(kind, EndpointKind)
        assert kind in set(EndpointKind)
        # Exactly one: the five kinds are distinct enum members, so membership in
        # one excludes the other four.
        assert sum(1 for candidate in EndpointKind if candidate is kind) == 1

    @given(endpoint=_any_endpoints())
    @settings(max_examples=100, deadline=None)
    def test_classification_is_absence_driven(self, endpoint: Endpoint) -> None:
        """The kind follows only from bound presence and day-interval equality.

        Feature: residence-periods, Property 3: Endpoint classification is total, absence-driven and precision-independent

        **Validates: Requirements 2.1, 2.4, 2.5, 2.6, 2.7, 2.8**
        """
        kind = classify_endpoint(endpoint)
        has_earliest = _present(endpoint.earliest)
        has_latest = _present(endpoint.latest)
        earliest_span = expand_iso(endpoint.earliest)
        latest_span = expand_iso(endpoint.latest)
        same_day_interval = (
            earliest_span is not None and earliest_span == latest_span
        )

        # Requirement 2.8: both absent → unknown.
        assert (kind is EndpointKind.UNKNOWN) == (not has_earliest and not has_latest)
        # Requirement 2.5: only latest present → open.
        assert (kind is EndpointKind.OPEN_LATEST) == (not has_earliest and has_latest)
        # Requirement 2.6: only earliest present → open.
        assert (kind is EndpointKind.OPEN_EARLIEST) == (has_earliest and not has_latest)
        # Requirement 2.4: both present, same day interval → exact date.
        assert (kind is EndpointKind.EXACT) == (
            has_earliest and has_latest and same_day_interval
        )
        # Requirement 2.7: both present, different day intervals → transition window.
        assert (kind is EndpointKind.WINDOW) == (
            has_earliest and has_latest and not same_day_interval
        )

    @given(
        endpoint=_any_endpoints(),
        earliest_absent=st.sampled_from(ABSENT_ISO_VALUES),
        latest_absent=st.sampled_from(ABSENT_ISO_VALUES),
    )
    @settings(max_examples=100, deadline=None)
    def test_absent_values_are_interchangeable(
        self,
        endpoint: Endpoint,
        earliest_absent: Optional[str],
        latest_absent: Optional[str],
    ) -> None:
        """Replacing an absent bound with any other absent form keeps the kind.

        Feature: residence-periods, Property 3: Endpoint classification is total, absence-driven and precision-independent

        **Validates: Requirements 2.1**
        """
        rewritten = replace(
            endpoint,
            earliest=endpoint.earliest if _present(endpoint.earliest) else earliest_absent,
            latest=endpoint.latest if _present(endpoint.latest) else latest_absent,
        )

        assert classify_endpoint(rewritten) is classify_endpoint(endpoint)

    @given(endpoint=_any_endpoints())
    @settings(max_examples=100, deadline=None)
    def test_precision_does_not_change_the_classification(
        self, endpoint: Endpoint
    ) -> None:
        """All four permitted `precision` values classify identically.

        Feature: residence-periods, Property 3: Endpoint classification is total, absence-driven and precision-independent

        **Validates: Requirements 2.3**
        """
        kinds = {
            classify_endpoint(replace(endpoint, precision=precision))
            for precision in PERMITTED_PRECISIONS
        }

        assert kinds == {classify_endpoint(endpoint)}

    @given(fact=residence_facts())
    @settings(max_examples=100, deadline=None)
    def test_precision_does_not_change_any_derived_interval(
        self, fact: ResidenceFact
    ) -> None:
        """Certain_Core and Possible_Span are the same for every `precision`.

        Feature: residence-periods, Property 3: Endpoint classification is total, absence-driven and precision-independent

        **Validates: Requirements 2.3**
        """
        expected_core = certain_core(fact)
        expected_span = possible_span(fact)

        for start_precision in PERMITTED_PRECISIONS:
            for end_precision in PERMITTED_PRECISIONS:
                varied = replace(
                    fact,
                    start=replace(fact.start, precision=start_precision),
                    end=replace(fact.end, precision=end_precision),
                )

                assert certain_core(varied) == expected_core
                assert possible_span(varied) == expected_span

    @pytest.mark.skipif(
        not _HAS_VALIDATOR,
        reason="validate_residence is introduced by task 3.1",
    )
    @given(fact=residence_facts())
    @settings(max_examples=100, deadline=None)
    def test_precision_does_not_change_the_error_list(self, fact: ResidenceFact) -> None:
        """The validator returns the same errors for every `precision`.

        Feature: residence-periods, Property 3: Endpoint classification is total, absence-driven and precision-independent

        **Validates: Requirements 2.3**
        """
        expected = validate_residence(fact)

        for start_precision in PERMITTED_PRECISIONS:
            for end_precision in PERMITTED_PRECISIONS:
                varied = replace(
                    fact,
                    start=replace(fact.start, precision=start_precision),
                    end=replace(fact.end, precision=end_precision),
                )

                assert validate_residence(varied) == expected
