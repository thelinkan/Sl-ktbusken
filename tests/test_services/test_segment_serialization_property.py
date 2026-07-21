"""Property-based tests for match segment serialization round-trip.

# Feature: dna-cluster-enhancements, Property 12: Match segment serialization round-trip

Validates: Requirements 14.3, 14.4
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.services.dna_match_csv_parser import MatchSegmentRecord
from slaktbusken.services.match_segment_storage import (
    deserialize_segments,
    serialize_segments,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies for generating MatchSegmentRecord instances
# ---------------------------------------------------------------------------

_CHROMOSOMES = [str(i) for i in range(1, 23)] + ["X"]

_rsid = st.integers(min_value=1, max_value=99999999).map(lambda n: f"rs{n}")


@st.composite
def match_segment_record_strategy(draw: DrawFn) -> MatchSegmentRecord:
    """Generate a valid MatchSegmentRecord with constrained field values."""
    chromosome = draw(st.sampled_from(_CHROMOSOMES))
    start_position = draw(st.integers(min_value=1, max_value=250_000_000))
    end_position = draw(st.integers(min_value=start_position + 1, max_value=250_000_001))
    start_rsid = draw(_rsid)
    end_rsid = draw(_rsid)
    centimorgans = draw(
        st.floats(min_value=0.01, max_value=300.0, allow_nan=False, allow_infinity=False)
    )
    snp_count = draw(st.integers(min_value=0, max_value=100_000))
    return MatchSegmentRecord(
        chromosome=chromosome,
        start_position=start_position,
        end_position=end_position,
        start_rsid=start_rsid,
        end_rsid=end_rsid,
        centimorgans=centimorgans,
        snp_count=snp_count,
    )


# ---------------------------------------------------------------------------
# Property 12: Match segment serialization round-trip
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(segments=st.lists(match_segment_record_strategy(), min_size=1, max_size=20))
def test_segment_serialization_round_trip(segments: list[MatchSegmentRecord]) -> None:
    """**Validates: Requirements 14.3, 14.4**

    For any list of MatchSegmentRecords, serializing to JSON format and
    deserializing back SHALL produce an equivalent list with identical field
    values for all records.
    """
    serialized = serialize_segments(segments)
    restored = deserialize_segments(serialized)

    assert len(restored) == len(segments), (
        f"Expected {len(segments)} segments after round-trip, got {len(restored)}"
    )

    for i, (original, roundtripped) in enumerate(zip(segments, restored)):
        assert roundtripped.chromosome == original.chromosome, (
            f"Segment {i}: chromosome mismatch: "
            f"{roundtripped.chromosome!r} != {original.chromosome!r}"
        )
        assert roundtripped.start_position == original.start_position, (
            f"Segment {i}: start_position mismatch: "
            f"{roundtripped.start_position} != {original.start_position}"
        )
        assert roundtripped.end_position == original.end_position, (
            f"Segment {i}: end_position mismatch: "
            f"{roundtripped.end_position} != {original.end_position}"
        )
        assert roundtripped.start_rsid == original.start_rsid, (
            f"Segment {i}: start_rsid mismatch: "
            f"{roundtripped.start_rsid!r} != {original.start_rsid!r}"
        )
        assert roundtripped.end_rsid == original.end_rsid, (
            f"Segment {i}: end_rsid mismatch: "
            f"{roundtripped.end_rsid!r} != {original.end_rsid!r}"
        )
        assert roundtripped.centimorgans == original.centimorgans, (
            f"Segment {i}: centimorgans mismatch: "
            f"{roundtripped.centimorgans} != {original.centimorgans}"
        )
        assert roundtripped.snp_count == original.snp_count, (
            f"Segment {i}: snp_count mismatch: "
            f"{roundtripped.snp_count} != {original.snp_count}"
        )


@settings(max_examples=1)
@given(st.just([]))
def test_segment_serialization_empty_list(segments: list[MatchSegmentRecord]) -> None:
    """**Validates: Requirements 14.3, 14.4**

    Serializing an empty list and deserializing back SHALL produce an empty list.
    """
    serialized = serialize_segments(segments)
    restored = deserialize_segments(serialized)

    assert restored == [], (
        f"Expected empty list after round-trip of empty input, got {restored}"
    )
