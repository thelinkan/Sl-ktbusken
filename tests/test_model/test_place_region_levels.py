"""Property-based tests for region level validation.

Tests Property 4 from the place-hierarchy-levels design document.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.place import RegionLevel
from slaktbusken.model.validators import validate_region_levels


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


@st.composite
def _valid_region_levels_strategy(draw: DrawFn) -> list[RegionLevel]:
    """Generate a valid list of RegionLevels with consecutive orders and unique keys."""
    count = draw(st.integers(min_value=1, max_value=10))
    keys = draw(st.lists(
        st.text(alphabet=st.characters(categories=("L", "N")), min_size=1, max_size=50),
        min_size=count, max_size=count, unique=True,
    ))
    levels = []
    for i, key in enumerate(keys):
        label = draw(st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=1, max_size=100,
        ))
        levels.append(RegionLevel(key=key, label=label, order=i + 1))
    return levels


# ---------------------------------------------------------------------------
# Feature: place-hierarchy-levels, Property 4: Region level validation
#
# For any list of RegionLevel entries on a country place, validation SHALL
# pass if and only if: all keys are 1-50 characters, all labels are 1-100
# characters, all keys are unique, order values are consecutive integers
# starting at 1, and there are at most 10 entries. Any violation SHALL
# produce a validation error.
# ---------------------------------------------------------------------------


class TestProperty4RegionLevelValidation:
    """Property 4: Region level validation.

    **Validates: Requirements 2.2, 2.3, 2.4, 2.6**
    """

    @given(levels=_valid_region_levels_strategy())
    @settings(max_examples=100)
    def test_valid_region_levels_produce_no_errors(self, levels: list[RegionLevel]) -> None:
        """**Validates: Requirements 2.2, 2.3, 2.4, 2.6**

        A valid list of region levels (keys 1-50, labels 1-100, unique keys,
        consecutive order from 1, at most 10 entries) produces no errors.
        """
        errors = validate_region_levels(levels)
        assert errors == [], f"Valid levels produced errors: {errors}"

    @given(
        label=st.text(alphabet=st.characters(categories=("L", "N", "Z")), min_size=1, max_size=100),
    )
    @settings(max_examples=100)
    def test_empty_key_rejected(self, label: str) -> None:
        """**Validates: Requirements 2.2**

        A region level with an empty key produces an error.
        """
        levels = [RegionLevel(key="", label=label, order=1)]
        errors = validate_region_levels(levels)
        assert "Regionnivåns nyckel måste vara 1–50 tecken." in errors

    @given(
        key=st.text(alphabet=st.characters(categories=("L", "N")), min_size=51, max_size=80),
        label=st.text(alphabet=st.characters(categories=("L", "N", "Z")), min_size=1, max_size=100),
    )
    @settings(max_examples=100)
    def test_key_too_long_rejected(self, key: str, label: str) -> None:
        """**Validates: Requirements 2.2**

        A region level with a key exceeding 50 characters produces an error.
        """
        levels = [RegionLevel(key=key, label=label, order=1)]
        errors = validate_region_levels(levels)
        assert "Regionnivåns nyckel måste vara 1–50 tecken." in errors

    @given(
        key=st.text(alphabet=st.characters(categories=("L", "N")), min_size=1, max_size=50),
    )
    @settings(max_examples=100)
    def test_empty_label_rejected(self, key: str) -> None:
        """**Validates: Requirements 2.6**

        A region level with an empty label produces an error.
        """
        levels = [RegionLevel(key=key, label="", order=1)]
        errors = validate_region_levels(levels)
        assert "Regionnivåns etikett måste vara 1–100 tecken." in errors

    @given(
        key=st.text(alphabet=st.characters(categories=("L", "N")), min_size=1, max_size=50),
        label=st.text(alphabet=st.characters(categories=("L", "N", "Z")), min_size=101, max_size=150),
    )
    @settings(max_examples=100)
    def test_label_too_long_rejected(self, key: str, label: str) -> None:
        """**Validates: Requirements 2.6**

        A region level with a label exceeding 100 characters produces an error.
        """
        levels = [RegionLevel(key=key, label=label, order=1)]
        errors = validate_region_levels(levels)
        assert "Regionnivåns etikett måste vara 1–100 tecken." in errors

    @given(
        key=st.text(alphabet=st.characters(categories=("L", "N")), min_size=1, max_size=50),
        label=st.text(alphabet=st.characters(categories=("L", "N", "Z")), min_size=1, max_size=100),
    )
    @settings(max_examples=100)
    def test_duplicate_keys_rejected(self, key: str, label: str) -> None:
        """**Validates: Requirements 2.3**

        Region levels with duplicate keys produce an error.
        """
        levels = [
            RegionLevel(key=key, label=label, order=1),
            RegionLevel(key=key, label=label, order=2),
        ]
        errors = validate_region_levels(levels)
        assert f"Regionnivåns nyckel '{key}' finns redan." in errors

    @given(
        keys=st.lists(
            st.text(alphabet=st.characters(categories=("L", "N")), min_size=1, max_size=50),
            min_size=2, max_size=5, unique=True,
        ),
    )
    @settings(max_examples=100)
    def test_non_consecutive_order_rejected(self, keys: list[str]) -> None:
        """**Validates: Requirements 2.4**

        Region levels with non-consecutive order values produce an error.
        """
        # Build levels with a gap in order (e.g., [1, 3] instead of [1, 2])
        levels = [
            RegionLevel(key=keys[i], label=f"Label {i}", order=(i + 1) * 2)
            for i in range(len(keys))
        ]
        errors = validate_region_levels(levels)
        assert "Regionnivåernas ordning måste vara löpande heltal från 1." in errors

    @given(
        keys=st.lists(
            st.text(alphabet=st.characters(categories=("L", "N")), min_size=1, max_size=50),
            min_size=11, max_size=15, unique=True,
        ),
    )
    @settings(max_examples=100)
    def test_more_than_10_entries_rejected(self, keys: list[str]) -> None:
        """**Validates: Requirements 2.2**

        More than 10 region level entries produce an error.
        """
        levels = [
            RegionLevel(key=keys[i], label=f"Label {i}", order=i + 1)
            for i in range(len(keys))
        ]
        errors = validate_region_levels(levels)
        assert "Högst 10 regionnivåer tillåtna." in errors

    @given(levels=_valid_region_levels_strategy())
    @settings(max_examples=100)
    def test_biconditional_passes_iff_all_constraints_satisfied(
        self, levels: list[RegionLevel]
    ) -> None:
        """**Validates: Requirements 2.2, 2.3, 2.4, 2.6**

        Validation passes (no errors) if and only if ALL constraints are met:
        keys 1-50 chars, labels 1-100 chars, unique keys, consecutive order, max 10 entries.
        """
        errors = validate_region_levels(levels)

        # All constraints are satisfied by _valid_region_levels_strategy
        all_keys_valid = all(1 <= len(rl.key) <= 50 for rl in levels)
        all_labels_valid = all(1 <= len(rl.label) <= 100 for rl in levels)
        keys_unique = len({rl.key for rl in levels}) == len(levels)
        orders_consecutive = [rl.order for rl in levels] == list(range(1, len(levels) + 1))
        at_most_10 = len(levels) <= 10

        all_valid = (
            all_keys_valid
            and all_labels_valid
            and keys_unique
            and orders_consecutive
            and at_most_10
        )

        if all_valid:
            assert errors == [], f"All constraints met but got errors: {errors}"
        else:
            assert errors != [], "Some constraint violated but no errors reported"
