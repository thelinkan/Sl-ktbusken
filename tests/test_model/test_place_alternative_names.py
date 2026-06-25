"""Property-based tests for Place Alternative Name validation logic.

Tests Property 6 (round-trip with trimming), Property 7 (duplicate rejection),
and Property 8 (invalid input rejection) from the design document.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**
"""

from __future__ import annotations

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from slaktbusken.model.place import Place
from slaktbusken.model.validators import (
    validate_alternative_name,
    validate_place_alternative_names,
)
from tests.conftest import place_strategy


# ===========================================================================
# Feature: place-editor-enhancements, Property 6: Alternative Name round-trip with trimming
#
# For any string of 1–200 characters that contains at least one non-whitespace
# character, adding it as an Alternative_Name and reading back SHALL yield the
# trimmed version of the input.
# **Validates: Requirements 3.1, 3.2**
# ===========================================================================


class TestProperty6AlternativeNameRoundTrip:
    """Property 6: valid alternative names pass validation and round-trip with trimming."""

    @given(name=st.text(min_size=1, max_size=200))
    @settings(max_examples=100)
    def test_valid_name_passes_validation_and_stores_trimmed(self, name: str) -> None:
        """**Validates: Requirements 3.1, 3.2**

        For any string of 1–200 characters containing at least one non-whitespace
        character, the validator accepts it, and storing the trimmed version on a
        Place yields the expected value in alternative_names.
        """
        # Only consider names that have at least one non-whitespace character
        assume(name.strip())

        # The validator should accept this name (no errors)
        errors = validate_alternative_name(name)
        assert errors == [], f"Valid name '{name!r}' was rejected: {errors}"

        # Create a place and store the trimmed version
        trimmed = name.strip()
        place = Place(
            id="place_1",
            type="parish",
            name="TestPlace",
            alternative_names=[trimmed],
        )

        # The stored value should equal the trimmed input
        assert place.alternative_names[0] == trimmed

        # The place-level validator should also pass (no duplicates, valid entry)
        place_errors = validate_place_alternative_names(place)
        assert place_errors == [], f"Place validation failed for trimmed name: {place_errors}"


# ===========================================================================
# Feature: place-editor-enhancements, Property 7: Alternative Name duplicate rejection
#
# For any place with an existing Alternative_Name S, attempting to add the same
# string S again SHALL be rejected (validator returns errors), and the list
# SHALL remain unchanged.
# **Validates: Requirements 3.3**
# ===========================================================================


class TestProperty7AlternativeNameDuplicateRejection:
    """Property 7: duplicate alternative names are rejected by the validator."""

    @given(name=st.text(min_size=1, max_size=200))
    @settings(max_examples=100)
    def test_duplicate_name_is_rejected(self, name: str) -> None:
        """**Validates: Requirements 3.3**

        For any place with an existing alternative name S, adding the same
        string S again causes validate_place_alternative_names to return errors.
        """
        # Only consider valid names (non-whitespace-only)
        assume(name.strip())

        # Create a place with the name already in alternative_names (duplicated)
        place = Place(
            id="place_1",
            type="parish",
            name="TestPlace",
            alternative_names=[name, name],  # duplicate
        )

        # The place-level validator should detect the duplicate
        errors = validate_place_alternative_names(place)
        assert len(errors) > 0, (
            f"Duplicate name '{name!r}' was not rejected by validate_place_alternative_names"
        )
        assert any("redan" in e for e in errors), (
            f"Expected duplicate error message containing 'redan', got: {errors}"
        )

    @given(
        name=st.text(min_size=1, max_size=200),
        other_names=st.lists(
            st.text(min_size=1, max_size=200),
            min_size=0,
            max_size=3,
            unique=True,
        ),
    )
    @settings(max_examples=100)
    def test_duplicate_does_not_change_valid_portion(self, name: str, other_names: list[str]) -> None:
        """**Validates: Requirements 3.3**

        For any place with existing alternative names, adding a duplicate
        should be caught by validation. The list with distinct entries passes.
        """
        assume(name.strip())
        # Filter other_names to be valid and distinct from `name`
        valid_others = [n for n in other_names if n.strip() and n != name]

        # A place with unique names should pass validation
        place_valid = Place(
            id="place_1",
            type="parish",
            name="TestPlace",
            alternative_names=[name] + valid_others,
        )
        errors_valid = validate_place_alternative_names(place_valid)
        assert errors_valid == [], f"Unique names were rejected: {errors_valid}"

        # A place with the duplicate should fail validation
        place_dup = Place(
            id="place_1",
            type="parish",
            name="TestPlace",
            alternative_names=[name] + valid_others + [name],
        )
        errors_dup = validate_place_alternative_names(place_dup)
        assert len(errors_dup) > 0, "Duplicate was not detected"


# ===========================================================================
# Feature: place-editor-enhancements, Property 8: Alternative Name invalid input rejection
#
# For any string that is empty, contains only whitespace, or exceeds 200
# characters, attempting to add it as an Alternative_Name SHALL be rejected
# (validator returns errors).
# **Validates: Requirements 3.4**
# ===========================================================================


class TestProperty8AlternativeNameInvalidInputRejection:
    """Property 8: invalid alternative names (empty, whitespace-only, >200 chars) are rejected."""

    @given(name=st.text(
        alphabet=st.sampled_from([" ", "\t", "\n", "\r", "\x0b", "\x0c", "\u00a0", "\u2003"]),
        min_size=0,
        max_size=200,
    ))
    @settings(max_examples=100)
    def test_whitespace_only_or_empty_name_is_rejected(self, name: str) -> None:
        """**Validates: Requirements 3.4**

        For any string that is empty or contains only whitespace characters,
        validate_alternative_name returns errors.
        """
        # This strategy generates strings made entirely of whitespace chars
        assume(not name.strip())

        errors = validate_alternative_name(name)
        assert len(errors) > 0, (
            f"Whitespace-only/empty name {name!r} was not rejected"
        )

    @given(name=st.text(min_size=201, max_size=400))
    @settings(max_examples=100)
    def test_name_exceeding_200_chars_is_rejected(self, name: str) -> None:
        """**Validates: Requirements 3.4**

        For any string exceeding 200 characters, validate_alternative_name
        returns errors.
        """
        errors = validate_alternative_name(name)
        assert len(errors) > 0, (
            f"Name of length {len(name)} was not rejected"
        )
        assert any("200" in e for e in errors), (
            f"Expected error about 200 char limit, got: {errors}"
        )

    @settings(max_examples=100)
    @given(name=st.just(""))
    def test_empty_string_is_rejected(self, name: str) -> None:
        """**Validates: Requirements 3.4**

        The empty string must be rejected by validate_alternative_name.
        """
        errors = validate_alternative_name(name)
        assert len(errors) > 0, "Empty string was not rejected"


# ===========================================================================
# Feature: place-editor-enhancements, Property 9: Alternative Name removal preserves order
#
# For any place with N Alternative_Names (N ≥ 2) and any valid index I to
# remove, removing the entry at index I SHALL result in N-1 entries remaining
# in the same relative order as the original list (with only the removed entry
# absent).
# **Validates: Requirements 3.5, 4.4**
# ===========================================================================


class TestProperty9AlternativeNameRemovalPreservesOrder:
    """Property 9: removing an alternative name preserves the order of remaining entries."""

    @given(
        names=st.lists(
            st.text(
                alphabet=st.characters(blacklist_categories=("Cs",)),
                min_size=1,
                max_size=200,
            ),
            min_size=2,
            max_size=10,
            unique=True,
        ),
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_removal_preserves_order(self, names: list[str], data: st.DataObject) -> None:
        """**Validates: Requirements 3.5, 4.4**

        For any place with N Alternative_Names (N ≥ 2) and any valid index I
        to remove, removing the entry at index I results in N-1 entries remaining
        in the same relative order as the original list (with only the removed
        entry absent).
        """
        from slaktbusken.model.place import remove_alternative_name

        # Filter to valid alternative names (non-whitespace-only, 1-200 chars)
        valid_names = [n for n in names if n.strip() and 1 <= len(n) <= 200]
        assume(len(valid_names) >= 2)

        # Pick a random valid index to remove
        index_to_remove = data.draw(
            st.integers(min_value=0, max_value=len(valid_names) - 1),
            label="index_to_remove",
        )

        # Create a place with the alternative names
        place = Place(
            id="place_1",
            type="parish",
            name="TestPlace",
            alternative_names=list(valid_names),  # copy to avoid mutation issues
        )

        original_names = list(place.alternative_names)
        removed_name = original_names[index_to_remove]

        # Perform the removal
        remove_alternative_name(place, index_to_remove)

        # Verify N-1 entries remain
        assert len(place.alternative_names) == len(original_names) - 1

        # Verify the remaining entries are in the same relative order
        expected = original_names[:index_to_remove] + original_names[index_to_remove + 1:]
        assert place.alternative_names == expected

        # Verify the removed name is no longer present (since names were unique)
        assert removed_name not in place.alternative_names
