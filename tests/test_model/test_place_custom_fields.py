"""Property-based tests for custom field value length validation.

Tests Property 10 from the place-hierarchy-levels design document.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.place import Place
from slaktbusken.model.validators import validate_custom_field_values


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_safe_name = st.text(
    alphabet=st.characters(categories=("L", "N", "Z")),
    min_size=1,
    max_size=50,
)

_field_key = st.text(
    alphabet=st.characters(categories=("L", "N")),
    min_size=1,
    max_size=50,
)

_CUSTOM_FIELD_ERROR = "Anpassat fältvärde får vara högst 20 tecken."


@st.composite
def _place_with_valid_custom_fields(draw: DrawFn) -> Place:
    """Generate a place with custom_field_values where all values are 1-20 chars."""
    name = draw(_safe_name)
    values = draw(st.dictionaries(
        keys=_field_key,
        values=st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=1,
            max_size=20,
        ),
        min_size=1,
        max_size=5,
    ))
    return Place(
        id="p1",
        type="church",
        name=name,
        parent_place_id="parent_1",
        custom_field_values=values,
    )


@st.composite
def _place_with_empty_custom_field_value(draw: DrawFn) -> Place:
    """Generate a place with at least one empty custom field value."""
    name = draw(_safe_name)
    # At least one empty value, possibly mixed with valid values
    empty_key = draw(_field_key)
    other_values = draw(st.dictionaries(
        keys=_field_key,
        values=st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=0,
            max_size=20,
        ),
        min_size=0,
        max_size=4,
    ))
    values = {empty_key: "", **other_values}
    return Place(
        id="p1",
        type="church",
        name=name,
        parent_place_id="parent_1",
        custom_field_values=values,
    )


@st.composite
def _place_with_too_long_custom_field_value(draw: DrawFn) -> Place:
    """Generate a place with at least one custom field value exceeding 20 chars."""
    name = draw(_safe_name)
    # Generate one value that is too long (21-100 chars)
    long_value = draw(st.text(
        alphabet=st.characters(categories=("L", "N", "Z")),
        min_size=21,
        max_size=100,
    ))
    long_key = draw(_field_key)
    # Possibly other valid values
    other_values = draw(st.dictionaries(
        keys=_field_key,
        values=st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=1,
            max_size=20,
        ),
        min_size=0,
        max_size=4,
    ))
    # Place long value last so it cannot be overwritten by other_values
    values = {**other_values, long_key: long_value}
    return Place(
        id="p1",
        type="church",
        name=name,
        parent_place_id="parent_1",
        custom_field_values=values,
    )


@st.composite
def _place_with_arbitrary_custom_fields(draw: DrawFn) -> Place:
    """Generate a place with custom field values of arbitrary lengths (including >20)."""
    name = draw(_safe_name)
    values = draw(st.dictionaries(
        keys=_field_key,
        values=st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=0,
            max_size=100,
        ),
        min_size=1,
        max_size=5,
    ))
    return Place(
        id="p1",
        type="church",
        name=name,
        parent_place_id="parent_1",
        custom_field_values=values,
    )


# ---------------------------------------------------------------------------
# Feature: place-hierarchy-levels, Property 10: Custom field value length
# validation
#
# For any custom field value of 1 to 20 characters, validation SHALL accept.
# For any custom field value exceeding 20 characters, validation SHALL reject.
# Empty values SHALL be accepted (optional fields).
# ---------------------------------------------------------------------------


class TestProperty10CustomFieldValueLengthValidation:
    """Property 10: Custom field value length validation.

    **Validates: Requirements 8.5, 8.6**
    """

    @given(place=_place_with_valid_custom_fields())
    @settings(max_examples=100)
    def test_values_1_to_20_chars_accepted(self, place: Place) -> None:
        """**Validates: Requirements 8.5**

        Place with custom_field_values where all values are 1-20 chars
        produces no "Anpassat fältvärde" errors.
        """
        errors = validate_custom_field_values(place)

        assert _CUSTOM_FIELD_ERROR not in errors

    @given(place=_place_with_empty_custom_field_value())
    @settings(max_examples=100)
    def test_empty_value_accepted(self, place: Place) -> None:
        """**Validates: Requirements 8.6**

        Place with an empty custom field value ("") produces no
        "Anpassat fältvärde" errors — custom fields are optional.
        """
        errors = validate_custom_field_values(place)

        assert _CUSTOM_FIELD_ERROR not in errors

    @given(place=_place_with_too_long_custom_field_value())
    @settings(max_examples=100)
    def test_value_exceeding_20_chars_rejected(self, place: Place) -> None:
        """**Validates: Requirements 8.5**

        Place with a custom field value exceeding 20 characters produces the
        error: "Anpassat fältvärde får vara högst 20 tecken."
        """
        errors = validate_custom_field_values(place)

        assert _CUSTOM_FIELD_ERROR in errors

    @given(place=_place_with_arbitrary_custom_fields())
    @settings(max_examples=100)
    def test_error_iff_any_value_exceeds_20_chars(self, place: Place) -> None:
        """**Validates: Requirements 8.5, 8.6**

        Biconditional: the error is present if and only if at least one custom
        field value exceeds 20 characters.
        """
        errors = validate_custom_field_values(place)

        has_too_long = any(
            len(v) > 20 for v in place.custom_field_values.values() if v
        )
        has_error = _CUSTOM_FIELD_ERROR in errors

        if has_too_long:
            assert has_error, (
                "Expected error when at least one value exceeds 20 chars"
            )
        else:
            assert not has_error, (
                "Should not produce error when all values are ≤20 chars or empty"
            )
