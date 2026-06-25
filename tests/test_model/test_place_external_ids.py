"""Property-based tests for External ID model validation logic.

Tests Properties 1, 2, and 3 from the place-editor-enhancements design document.
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from slaktbusken.model.place import ExternalId, Place
from slaktbusken.model.validators import (
    validate_external_id,
    validate_place_external_ids,
)
from tests.conftest import place_strategy


# ===========================================================================
# Feature: place-editor-enhancements, Property 1: External ID round-trip preservation
#
# For any valid key (1–100 non-whitespace-only chars) and valid value
# (1–500 non-whitespace-only chars), adding an External_ID to a place and
# then reading back SHALL yield the exact same key and value.
# **Validates: Requirements 1.2, 1.3**
# ===========================================================================


class TestProperty1ExternalIdRoundTrip:
    """Property 1: External ID round-trip preservation."""

    @given(
        place=place_strategy(),
        key=st.text(min_size=1, max_size=100),
        value=st.text(min_size=1, max_size=500),
    )
    @settings(max_examples=100)
    def test_valid_external_id_round_trip(
        self, place: Place, key: str, value: str
    ) -> None:
        """**Validates: Requirements 1.2, 1.3**

        Adding a valid ExternalId to a place and reading it back yields
        the exact same key and value.
        """
        # Filter: key and value must contain at least one non-whitespace char
        assume(key.strip())
        assume(value.strip())

        ext_id = ExternalId(key=key, value=value)

        # Validate the entry is accepted
        errors = validate_external_id(ext_id)
        assert errors == [], f"Valid external ID rejected: {errors}"

        # Add to place and read back
        place.external_ids = []  # Start fresh to avoid key conflicts
        place.external_ids.append(ext_id)

        # Validate the place's external IDs pass validation
        place_errors = validate_place_external_ids(place)
        assert place_errors == [], f"Place external ID validation failed: {place_errors}"

        # Read back and verify round-trip
        assert len(place.external_ids) == 1
        stored = place.external_ids[0]
        assert stored.key == key
        assert stored.value == value


# ===========================================================================
# Feature: place-editor-enhancements, Property 2: External ID duplicate key rejection
#
# For any place with an existing External_ID with key K, attempting to add
# another External_ID with the same key K SHALL be rejected (validator
# returns errors), and the list SHALL remain unchanged.
# **Validates: Requirements 1.4**
# ===========================================================================


class TestProperty2ExternalIdDuplicateKeyRejection:
    """Property 2: External ID duplicate key rejection."""

    @given(
        place=place_strategy(),
        key=st.text(min_size=1, max_size=100),
        value1=st.text(min_size=1, max_size=500),
        value2=st.text(min_size=1, max_size=500),
    )
    @settings(max_examples=100)
    def test_duplicate_key_rejected(
        self, place: Place, key: str, value1: str, value2: str
    ) -> None:
        """**Validates: Requirements 1.4**

        Adding two ExternalId entries with the same key results in a
        validation error from validate_place_external_ids.
        """
        # Filter: key and values must contain at least one non-whitespace char
        assume(key.strip())
        assume(value1.strip())
        assume(value2.strip())

        # Set up place with one existing entry
        ext_id1 = ExternalId(key=key, value=value1)
        place.external_ids = [ext_id1]

        # Verify single entry is valid
        errors_before = validate_place_external_ids(place)
        assert errors_before == [], f"Single entry should be valid: {errors_before}"

        # Attempt to add a second entry with the same key
        ext_id2 = ExternalId(key=key, value=value2)
        place.external_ids.append(ext_id2)

        # Validate — should report duplicate key error
        errors_after = validate_place_external_ids(place)
        assert len(errors_after) > 0, (
            "Duplicate key should be rejected by validator"
        )
        assert any(key in err for err in errors_after), (
            f"Error should mention the duplicate key '{key}': {errors_after}"
        )


# ===========================================================================
# Feature: place-editor-enhancements, Property 3: External ID whitespace-only rejection
#
# For any string composed entirely of whitespace (or empty), attempting to
# add an External_ID using that string as either key or value SHALL be
# rejected (validator returns errors).
# **Validates: Requirements 1.5**
# ===========================================================================


class TestProperty3ExternalIdWhitespaceOnlyRejection:
    """Property 3: External ID whitespace-only rejection."""

    @given(
        whitespace_key=st.text(
            alphabet=st.characters(whitelist_categories=("Zs", "Cc")),
            min_size=0,
            max_size=100,
        ),
        valid_value=st.text(min_size=1, max_size=500),
    )
    @settings(max_examples=100)
    def test_whitespace_only_key_rejected(
        self, whitespace_key: str, valid_value: str
    ) -> None:
        """**Validates: Requirements 1.5**

        An ExternalId with a whitespace-only (or empty) key is rejected
        by validate_external_id.
        """
        assume(valid_value.strip())
        # Ensure key is actually whitespace-only or empty
        assume(not whitespace_key.strip())

        ext_id = ExternalId(key=whitespace_key, value=valid_value)
        errors = validate_external_id(ext_id)
        assert len(errors) > 0, (
            "Whitespace-only key should be rejected by validator"
        )

    @given(
        valid_key=st.text(min_size=1, max_size=100),
        whitespace_value=st.text(
            alphabet=st.characters(whitelist_categories=("Zs", "Cc")),
            min_size=0,
            max_size=500,
        ),
    )
    @settings(max_examples=100)
    def test_whitespace_only_value_rejected(
        self, valid_key: str, whitespace_value: str
    ) -> None:
        """**Validates: Requirements 1.5**

        An ExternalId with a whitespace-only (or empty) value is rejected
        by validate_external_id.
        """
        assume(valid_key.strip())
        # Ensure value is actually whitespace-only or empty
        assume(not whitespace_value.strip())

        ext_id = ExternalId(key=valid_key, value=whitespace_value)
        errors = validate_external_id(ext_id)
        assert len(errors) > 0, (
            "Whitespace-only value should be rejected by validator"
        )

    @given(
        whitespace_key=st.from_regex(r"\A[\s]*\Z", fullmatch=True),
        whitespace_value=st.from_regex(r"\A[\s]*\Z", fullmatch=True),
    )
    @settings(max_examples=100)
    def test_whitespace_only_key_and_value_both_rejected(
        self, whitespace_key: str, whitespace_value: str
    ) -> None:
        """**Validates: Requirements 1.5**

        An ExternalId with both key and value as whitespace-only (or empty)
        is rejected by validate_external_id.
        """
        ext_id = ExternalId(key=whitespace_key, value=whitespace_value)
        errors = validate_external_id(ext_id)
        assert len(errors) > 0, (
            "Whitespace-only key and value should both be rejected"
        )


# ===========================================================================
# Feature: place-editor-enhancements, Property 4: External ID removal preserves remaining entries
#
# For any place with N External_ID entries (N ≥ 1), removing one entry by key
# SHALL result in exactly N-1 entries remaining, and all non-removed entries
# SHALL be preserved with their original key and value.
# **Validates: Requirements 1.6, 2.4**
# ===========================================================================


class TestProperty4ExternalIdRemovalPreservesRemaining:
    """Property 4: External ID removal preserves remaining entries."""

    @given(
        place=place_strategy(),
        entries=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=100),
                st.text(min_size=1, max_size=500),
            ),
            min_size=1,
            max_size=10,
            unique_by=lambda t: t[0],
        ),
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_removal_preserves_remaining_entries(
        self, place: Place, entries: list[tuple[str, str]], data: st.DataObject
    ) -> None:
        """**Validates: Requirements 1.6, 2.4**

        Removing one External_ID entry by key results in exactly N-1 entries
        remaining, and all non-removed entries are preserved with their
        original key and value.
        """
        from slaktbusken.model.place import remove_external_id

        # Filter: all keys and values must have at least one non-whitespace char
        assume(all(k.strip() and v.strip() for k, v in entries))

        # Set up place with N entries
        place.external_ids = [ExternalId(key=k, value=v) for k, v in entries]
        n = len(place.external_ids)

        # Choose one entry to remove
        index_to_remove = data.draw(st.integers(min_value=0, max_value=n - 1))
        key_to_remove = place.external_ids[index_to_remove].key

        # Snapshot all entries that should remain
        expected_remaining = [
            (eid.key, eid.value)
            for eid in place.external_ids
            if eid.key != key_to_remove
        ]

        # Perform removal
        remove_external_id(place, key_to_remove)

        # Verify exactly N-1 entries remain
        assert len(place.external_ids) == n - 1

        # Verify all non-removed entries are preserved with original key and value
        actual_remaining = [(eid.key, eid.value) for eid in place.external_ids]
        assert actual_remaining == expected_remaining


# ===========================================================================
# Feature: place-editor-enhancements, Property 5: External ID edit updates entry
#
# For any existing External_ID entry on a place, editing it with a new valid
# key and value SHALL result in the entry being updated to the new values,
# with all other entries remaining unchanged.
# **Validates: Requirements 2.4, 2.7**
# ===========================================================================


class TestProperty5ExternalIdEditUpdatesEntry:
    """Property 5: External ID edit updates entry."""

    @given(
        place=place_strategy(),
        entries=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=100),
                st.text(min_size=1, max_size=500),
            ),
            min_size=1,
            max_size=10,
            unique_by=lambda t: t[0],
        ),
        new_key=st.text(min_size=1, max_size=100),
        new_value=st.text(min_size=1, max_size=500),
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_edit_updates_entry_and_preserves_others(
        self,
        place: Place,
        entries: list[tuple[str, str]],
        new_key: str,
        new_value: str,
        data: st.DataObject,
    ) -> None:
        """**Validates: Requirements 2.4, 2.7**

        Editing an existing External_ID entry with a new valid key and value
        updates the entry to the new values, with all other entries unchanged.
        """
        from slaktbusken.model.place import edit_external_id

        # Filter: all keys and values must have at least one non-whitespace char
        assume(all(k.strip() and v.strip() for k, v in entries))
        assume(new_key.strip())
        assume(new_value.strip())

        # Set up place with entries
        place.external_ids = [ExternalId(key=k, value=v) for k, v in entries]

        # Choose one entry to edit
        index_to_edit = data.draw(
            st.integers(min_value=0, max_value=len(entries) - 1)
        )
        old_key = place.external_ids[index_to_edit].key

        # Ensure new key doesn't conflict with other existing keys
        other_keys = {eid.key for eid in place.external_ids if eid.key != old_key}
        assume(new_key not in other_keys)

        # Snapshot entries that should remain unchanged
        expected_others = [
            (eid.key, eid.value)
            for i, eid in enumerate(place.external_ids)
            if i != index_to_edit
        ]

        # Perform edit
        new_ext_id = ExternalId(key=new_key, value=new_value)
        errors = edit_external_id(place, old_key, new_ext_id)

        # Edit should succeed (no errors)
        assert errors == [], f"Edit should succeed but got errors: {errors}"

        # Verify the edited entry has the new key and value
        edited_entry = place.external_ids[index_to_edit]
        assert edited_entry.key == new_key
        assert edited_entry.value == new_value

        # Verify all other entries remain unchanged
        actual_others = [
            (eid.key, eid.value)
            for i, eid in enumerate(place.external_ids)
            if i != index_to_edit
        ]
        assert actual_others == expected_others
