"""Property-based tests for relationship probability lookup.

# Feature: dna-cluster-enhancements, Property 6: Relationship probability consistency

Validates: Requirements 10.4, 10.6
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.services.relationship_lookup import get_relationship_probabilities


# ---------------------------------------------------------------------------
# Property 6: Relationship probability consistency
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(shared_cm=st.floats(min_value=1.0, max_value=3500.0, allow_nan=False))
def test_probability_consistency(shared_cm: float) -> None:
    """**Validates: Requirements 10.4, 10.6**

    For any shared_cm value in the range 1–3500, the get_relationship_probabilities
    function returns a list where all probabilities are > 0% and the sum of all
    probabilities is approximately 100% (within ±1% rounding tolerance).
    """
    result = get_relationship_probabilities(shared_cm)

    # Must return at least one relationship
    assert len(result) > 0, f"Expected non-empty result for shared_cm={shared_cm}"

    # All probabilities must be > 0
    for rp in result:
        assert rp.probability > 0, (
            f"Expected probability > 0 for relationship '{rp.relationship}', "
            f"got {rp.probability} at shared_cm={shared_cm}"
        )

    # Sum of probabilities must be approximately 100% (±1% tolerance)
    total = sum(rp.probability for rp in result)
    assert 99.0 <= total <= 101.0, (
        f"Expected sum of probabilities within 99.0–101.0, "
        f"got {total} at shared_cm={shared_cm}"
    )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_zero_cm_returns_empty() -> None:
    """shared_cm=0 returns empty list."""
    result = get_relationship_probabilities(0.0)
    assert result == []


def test_negative_cm_returns_empty() -> None:
    """shared_cm < 0 returns empty list."""
    result = get_relationship_probabilities(-5.0)
    assert result == []


def test_above_max_range_returns_empty() -> None:
    """shared_cm > 3720 returns empty list."""
    result = get_relationship_probabilities(3721.0)
    assert result == []
