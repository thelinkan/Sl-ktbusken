"""Property-based tests for chromosome segment position and width calculations.

# Feature: dna-cluster-enhancements, Property 13: Chromosome segment position and width calculation

Validates: Requirements 15.3, 15.5, 15.6
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.services.chromosome_data import (
    CHROMOSOME_LENGTHS,
    segment_relative_position,
    segment_relative_width,
)


# ---------------------------------------------------------------------------
# Helpers — strategy for valid chromosome segments
# ---------------------------------------------------------------------------


@st.composite
def valid_segment(draw: st.DrawFn) -> tuple[str, int, int]:
    """Generate a valid (chromosome, start, end) triple.

    Constraints:
      - chromosome sampled from CHROMOSOME_LENGTHS keys
      - 0 <= start < CHROMOSOME_LENGTHS[chrom]
      - start < end <= CHROMOSOME_LENGTHS[chrom]
    """
    chrom = draw(st.sampled_from(sorted(CHROMOSOME_LENGTHS.keys())))
    chrom_len = CHROMOSOME_LENGTHS[chrom]
    start = draw(st.integers(min_value=0, max_value=chrom_len - 1))
    end = draw(st.integers(min_value=start + 1, max_value=chrom_len))
    return (chrom, start, end)


# ---------------------------------------------------------------------------
# Property 13: Chromosome segment position and width calculation
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(seg=valid_segment())
def test_segment_relative_position_and_width(seg: tuple[str, int, int]) -> None:
    """**Validates: Requirements 15.3, 15.5, 15.6**

    For any valid segment where 0 <= start < end <= CHROMOSOME_LENGTHS[chrom]:
    - segment_relative_position(start, chrom) == start / CHROMOSOME_LENGTHS[chrom]
    - segment_relative_width(start, end, chrom) == (end - start) / CHROMOSOME_LENGTHS[chrom]
    - Both results are in range [0.0, 1.0]
    """
    chrom, start, end = seg
    chrom_len = CHROMOSOME_LENGTHS[chrom]

    position = segment_relative_position(start, chrom)
    width = segment_relative_width(start, end, chrom)

    # Correctness
    assert position == pytest.approx(start / chrom_len), (
        f"Expected position={start / chrom_len}, got {position} "
        f"for chrom={chrom}, start={start}"
    )
    assert width == pytest.approx((end - start) / chrom_len), (
        f"Expected width={(end - start) / chrom_len}, got {width} "
        f"for chrom={chrom}, start={start}, end={end}"
    )

    # Range bounds
    assert 0.0 <= position <= 1.0, f"Position {position} out of [0, 1] range"
    assert 0.0 <= width <= 1.0, f"Width {width} out of [0, 1] range"


# ---------------------------------------------------------------------------
# Boundary cases
# ---------------------------------------------------------------------------


def test_start_zero_gives_position_zero() -> None:
    """start=0 always gives relative position 0.0."""
    for chrom in CHROMOSOME_LENGTHS:
        pos = segment_relative_position(0, chrom)
        assert pos == 0.0, f"Expected 0.0 for chrom={chrom}, got {pos}"


def test_full_chromosome_span_gives_width_one() -> None:
    """Full chromosome span (start=0, end=length) gives width 1.0."""
    for chrom, length in CHROMOSOME_LENGTHS.items():
        w = segment_relative_width(0, length, chrom)
        assert w == pytest.approx(1.0), (
            f"Expected width=1.0 for full span of chrom={chrom}, got {w}"
        )
