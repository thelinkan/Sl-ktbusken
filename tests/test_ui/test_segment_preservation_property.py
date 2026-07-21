"""Property-based test for segment data preservation round-trip.

Feature: dna-cluster-enhancements, Property 4: Segment data preservation round-trip

For any list of DnaSegment records stored in ProjectData.dna_segments,
serializing the project to JSON and deserializing it back SHALL preserve
all segment records with identical field values.

**Validates: Requirements 5.3, 5.4**
"""

from __future__ import annotations

from dataclasses import asdict

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.model.dna import DnaSegment
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.persistence.serialization import deserialize, serialize

from tests.conftest import dna_segment_strategy, project_data_strategy


# ---------------------------------------------------------------------------
# Strategy: ProjectData with guaranteed non-empty dna_segments
# ---------------------------------------------------------------------------


@st.composite
def project_with_segments_strategy(draw: st.DrawFn) -> ProjectData:
    """Generate a ProjectData with at least one DnaSegment record."""
    project = draw(project_data_strategy())
    # Ensure at least 1 segment exists (override if empty)
    if not project.dna_segments:
        segments = draw(st.lists(dna_segment_strategy(), min_size=1, max_size=5))
        project.dna_segments = segments
    return project


# ---------------------------------------------------------------------------
# Property 4: Segment data preservation round-trip
# ---------------------------------------------------------------------------


class TestSegmentPreservationRoundTrip:
    """Property 4: Segment data preservation round-trip.

    For any list of DnaSegment records stored in ProjectData.dna_segments,
    serializing the project to JSON and deserializing it back SHALL preserve
    all segment records with identical field values.

    **Validates: Requirements 5.3, 5.4**
    """

    @given(project=project_with_segments_strategy())
    @settings(max_examples=100, deadline=None)
    def test_segment_count_preserved(self, project: ProjectData) -> None:
        """The number of DnaSegment records is preserved through round-trip.

        **Validates: Requirements 5.3, 5.4**
        """
        json_str = serialize(project)
        restored = deserialize(json_str)

        assert len(restored.dna_segments) == len(project.dna_segments), (
            f"Expected {len(project.dna_segments)} segments, "
            f"got {len(restored.dna_segments)}"
        )

    @given(project=project_with_segments_strategy())
    @settings(max_examples=100, deadline=None)
    def test_segment_fields_preserved(self, project: ProjectData) -> None:
        """All DnaSegment field values are preserved through round-trip.

        **Validates: Requirements 5.3, 5.4**
        """
        json_str = serialize(project)
        restored = deserialize(json_str)

        for i, (original, deserialized) in enumerate(
            zip(project.dna_segments, restored.dna_segments)
        ):
            assert original.id == deserialized.id, (
                f"Segment {i}: id mismatch: {original.id!r} != {deserialized.id!r}"
            )
            assert original.match_id == deserialized.match_id, (
                f"Segment {i}: match_id mismatch: "
                f"{original.match_id!r} != {deserialized.match_id!r}"
            )
            assert original.chromosome == deserialized.chromosome, (
                f"Segment {i}: chromosome mismatch: "
                f"{original.chromosome!r} != {deserialized.chromosome!r}"
            )
            assert original.start_position == deserialized.start_position, (
                f"Segment {i}: start_position mismatch: "
                f"{original.start_position} != {deserialized.start_position}"
            )
            assert original.end_position == deserialized.end_position, (
                f"Segment {i}: end_position mismatch: "
                f"{original.end_position} != {deserialized.end_position}"
            )
            assert original.cm == deserialized.cm, (
                f"Segment {i}: cm mismatch: {original.cm} != {deserialized.cm}"
            )
            assert original.snp_count == deserialized.snp_count, (
                f"Segment {i}: snp_count mismatch: "
                f"{original.snp_count} != {deserialized.snp_count}"
            )

    @given(project=project_with_segments_strategy())
    @settings(max_examples=100, deadline=None)
    def test_segment_dataclass_equality(self, project: ProjectData) -> None:
        """DnaSegment records are equal as dicts after round-trip (structural equality).

        **Validates: Requirements 5.3, 5.4**
        """
        json_str = serialize(project)
        restored = deserialize(json_str)

        original_dicts = [asdict(seg) for seg in project.dna_segments]
        restored_dicts = [asdict(seg) for seg in restored.dna_segments]

        assert original_dicts == restored_dicts, (
            "Segment data not preserved through serialize/deserialize round-trip"
        )
