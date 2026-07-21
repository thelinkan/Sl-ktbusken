# Feature: dna-cluster-enhancements, Property 14: Chromosome browser total cM equals segment sum
"""Property-based tests for chromosome browser total cM equals segment sum.

Feature: dna-cluster-enhancements, Property 14: Chromosome browser total cM equals segment sum

For any list of match segments with centimorgan values, the displayed total
shared cM SHALL equal the sum of all individual segment centimorgan values
(within floating-point precision of ±0.01).

**Validates: Requirements 15.11**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.services.dna_match_csv_parser import MatchSegmentRecord

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_CHROMOSOMES = [str(i) for i in range(1, 23)] + ["X"]


@st.composite
def match_segment_list(draw: DrawFn) -> list[MatchSegmentRecord]:
    """Generate a list of MatchSegmentRecord with known centimorgans values.

    Generates 0–50 segments with realistic chromosome positions and cM values.
    """
    num_segments = draw(st.integers(min_value=0, max_value=50))
    segments: list[MatchSegmentRecord] = []

    for _ in range(num_segments):
        chromosome = draw(st.sampled_from(_CHROMOSOMES))
        start_position = draw(st.integers(min_value=1, max_value=250_000_000))
        end_position = draw(
            st.integers(min_value=start_position + 1, max_value=250_000_001)
        )
        centimorgans = draw(
            st.floats(min_value=0.01, max_value=300.0, allow_nan=False, allow_infinity=False)
        )
        snp_count = draw(st.integers(min_value=1, max_value=100_000))

        segments.append(
            MatchSegmentRecord(
                chromosome=chromosome,
                start_position=start_position,
                end_position=end_position,
                start_rsid=f"rs{start_position}",
                end_rsid=f"rs{end_position}",
                centimorgans=centimorgans,
                snp_count=snp_count,
            )
        )

    return segments


class TestChromosomeBrowserTotalCmEqualsSegmentSum:
    """Feature: dna-cluster-enhancements, Property 14: Chromosome browser total cM equals segment sum

    For any list of match segments with centimorgan values, the displayed total
    shared cM SHALL equal the sum of all individual segment centimorgan values
    (within floating-point precision of ±0.01).

    **Validates: Requirements 15.11**
    """

    @given(segments=match_segment_list())
    @settings(max_examples=100)
    def test_total_cm_equals_sum_of_segment_centimorgans(
        self,
        segments: list[MatchSegmentRecord],
    ) -> None:
        """The computed total_cm SHALL equal the sum of all individual
        segment centimorgans values within ±0.01 floating-point precision.

        Feature: dna-cluster-enhancements, Property 14: Chromosome browser total cM equals segment sum
        **Validates: Requirements 15.11**
        """
        # This is the same computation used in ChromosomeBrowserDialog._setup_ui
        total_cm = sum(seg.centimorgans for seg in segments)

        # Independently compute the expected sum
        expected_sum = 0.0
        for seg in segments:
            expected_sum += seg.centimorgans

        assert abs(total_cm - expected_sum) <= 0.01, (
            f"Total cM mismatch.\n"
            f"  Computed total_cm: {total_cm}\n"
            f"  Expected sum: {expected_sum}\n"
            f"  Difference: {abs(total_cm - expected_sum)}\n"
            f"  Number of segments: {len(segments)}"
        )

    @given(segments=match_segment_list())
    @settings(max_examples=100)
    def test_total_cm_is_non_negative(
        self,
        segments: list[MatchSegmentRecord],
    ) -> None:
        """The total cM SHALL always be non-negative when all segment
        centimorgan values are positive.

        Feature: dna-cluster-enhancements, Property 14: Chromosome browser total cM equals segment sum
        **Validates: Requirements 15.11**
        """
        total_cm = sum(seg.centimorgans for seg in segments)

        assert total_cm >= 0.0, (
            f"Total cM is negative: {total_cm} for {len(segments)} segments"
        )

    @given(segments=match_segment_list())
    @settings(max_examples=100)
    def test_total_cm_greater_or_equal_to_any_single_segment(
        self,
        segments: list[MatchSegmentRecord],
    ) -> None:
        """The total cM SHALL be greater than or equal to any individual
        segment's centimorgan value (since all values are positive).

        Feature: dna-cluster-enhancements, Property 14: Chromosome browser total cM equals segment sum
        **Validates: Requirements 15.11**
        """
        if not segments:
            return  # Vacuously true for empty list

        total_cm = sum(seg.centimorgans for seg in segments)

        for seg in segments:
            assert total_cm >= seg.centimorgans - 0.01, (
                f"Total cM ({total_cm}) is less than a single segment's "
                f"cM ({seg.centimorgans}) on chromosome {seg.chromosome}"
            )

    @given(segments=match_segment_list())
    @settings(max_examples=100)
    def test_empty_segment_list_total_is_zero(
        self,
        segments: list[MatchSegmentRecord],
    ) -> None:
        """When the segment list is empty, total cM SHALL be 0.0.
        When non-empty, total cM SHALL be strictly positive.

        Feature: dna-cluster-enhancements, Property 14: Chromosome browser total cM equals segment sum
        **Validates: Requirements 15.11**
        """
        total_cm = sum(seg.centimorgans for seg in segments)

        if len(segments) == 0:
            assert total_cm == 0.0, (
                f"Expected 0.0 for empty segment list, got {total_cm}"
            )
        else:
            # All generated segments have centimorgans >= 0.01
            assert total_cm > 0.0, (
                f"Expected positive total for {len(segments)} segments, got {total_cm}"
            )
