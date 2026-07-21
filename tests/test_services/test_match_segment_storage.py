"""Unit tests for match segment serialization/deserialization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slaktbusken.services.dna_match_csv_parser import MatchSegmentRecord
from slaktbusken.services.match_segment_storage import (
    deserialize_segments,
    load_match_segments,
    save_match_segments,
    serialize_segments,
)


# ---------------------------------------------------------------------------
# serialize_segments / deserialize_segments
# ---------------------------------------------------------------------------


def _sample_segments() -> list[MatchSegmentRecord]:
    """Create a list of sample MatchSegmentRecord instances for testing."""
    return [
        MatchSegmentRecord(
            chromosome="1",
            start_position=1000000,
            end_position=5000000,
            start_rsid="rs100",
            end_rsid="rs500",
            centimorgans=12.5,
            snp_count=1200,
        ),
        MatchSegmentRecord(
            chromosome="X",
            start_position=500000,
            end_position=2000000,
            start_rsid="rs200",
            end_rsid="rs800",
            centimorgans=8.3,
            snp_count=750,
        ),
    ]


def test_serialize_segments_produces_correct_dicts():
    """Serialize should produce list of dicts with expected keys/values."""
    segments = _sample_segments()
    result = serialize_segments(segments)

    assert len(result) == 2
    assert result[0] == {
        "chromosome": "1",
        "start_position": 1000000,
        "end_position": 5000000,
        "start_rsid": "rs100",
        "end_rsid": "rs500",
        "centimorgans": 12.5,
        "snp_count": 1200,
    }
    assert result[1]["chromosome"] == "X"
    assert result[1]["centimorgans"] == 8.3


def test_serialize_empty_list():
    """Serializing an empty list produces an empty list."""
    assert serialize_segments([]) == []


def test_deserialize_segments_produces_correct_records():
    """Deserialize should reconstruct MatchSegmentRecord instances."""
    data = [
        {
            "chromosome": "1",
            "start_position": 1000000,
            "end_position": 5000000,
            "start_rsid": "rs100",
            "end_rsid": "rs500",
            "centimorgans": 12.5,
            "snp_count": 1200,
        },
    ]
    result = deserialize_segments(data)

    assert len(result) == 1
    seg = result[0]
    assert seg.chromosome == "1"
    assert seg.start_position == 1000000
    assert seg.end_position == 5000000
    assert seg.start_rsid == "rs100"
    assert seg.end_rsid == "rs500"
    assert seg.centimorgans == 12.5
    assert seg.snp_count == 1200


def test_deserialize_empty_list():
    """Deserializing an empty list produces an empty list."""
    assert deserialize_segments([]) == []


def test_round_trip_preserves_data():
    """Serialize followed by deserialize should produce equivalent records."""
    segments = _sample_segments()
    data = serialize_segments(segments)
    restored = deserialize_segments(data)

    assert len(restored) == len(segments)
    for orig, rest in zip(segments, restored):
        assert orig.chromosome == rest.chromosome
        assert orig.start_position == rest.start_position
        assert orig.end_position == rest.end_position
        assert orig.start_rsid == rest.start_rsid
        assert orig.end_rsid == rest.end_rsid
        assert orig.centimorgans == rest.centimorgans
        assert orig.snp_count == rest.snp_count


# ---------------------------------------------------------------------------
# save_match_segments / load_match_segments (file I/O integration)
# ---------------------------------------------------------------------------


def test_save_and_load_match_segments(tmp_path: Path):
    """Save followed by load should produce equivalent segments."""
    project_path = tmp_path / "project.json.gz"
    project_path.touch()

    segments = _sample_segments()
    filename = save_match_segments(project_path, "match123", segments)

    assert filename == "match_segments_match123.json"

    # Verify the file exists in dna/ subfolder
    dna_folder = tmp_path / "dna"
    assert dna_folder.exists()
    assert (dna_folder / filename).exists()

    # Verify file content is valid JSON matching expected format
    content = json.loads((dna_folder / filename).read_text(encoding="utf-8"))
    assert isinstance(content, list)
    assert len(content) == 2
    assert content[0]["chromosome"] == "1"

    # Load and verify
    loaded = load_match_segments(project_path, filename)
    assert len(loaded) == 2
    assert loaded[0].chromosome == "1"
    assert loaded[0].centimorgans == 12.5
    assert loaded[1].chromosome == "X"


def test_save_creates_dna_folder(tmp_path: Path):
    """Saving segments should create the dna/ subfolder if it doesn't exist."""
    project_path = tmp_path / "project.json.gz"
    project_path.touch()

    dna_folder = tmp_path / "dna"
    assert not dna_folder.exists()

    save_match_segments(project_path, "abc", [])
    assert dna_folder.exists()


def test_load_nonexistent_file_raises(tmp_path: Path):
    """Loading a nonexistent file should raise FileNotFoundError."""
    project_path = tmp_path / "project.json.gz"
    project_path.touch()

    with pytest.raises(FileNotFoundError):
        load_match_segments(project_path, "nonexistent.json")


def test_filename_convention():
    """Saved filename should follow match_segments_{match_id}.json convention."""
    from unittest.mock import patch

    # We just test the filename generation part
    segments = []
    with patch(
        "slaktbusken.services.match_segment_storage.write_dna_file"
    ) as mock_write:
        from slaktbusken.services.match_segment_storage import save_match_segments as save_fn

        filename = save_fn(Path("/fake/project.json.gz"), "test-id-456", segments)
        assert filename == "match_segments_test-id-456.json"
        mock_write.assert_called_once()
