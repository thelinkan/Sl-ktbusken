"""Match segment serialization and file storage.

Provides functions to serialize/deserialize MatchSegmentRecord lists to/from
JSON format, and save/load them in the dna/ subfolder relative to the project file.

Filename convention: match_segments_{match_id}.json
"""

from __future__ import annotations

from pathlib import Path

from slaktbusken.services.dna_file_utils import read_dna_file, write_dna_file
from slaktbusken.services.dna_match_csv_parser import MatchSegmentRecord


def serialize_segments(segments: list[MatchSegmentRecord]) -> list[dict]:
    """Convert segment records to list of dicts suitable for JSON serialization.

    Args:
        segments: List of MatchSegmentRecord instances.

    Returns:
        List of dictionaries with keys: chromosome, start_position, end_position,
        start_rsid, end_rsid, centimorgans, snp_count.
    """
    return [
        {
            "chromosome": seg.chromosome,
            "start_position": seg.start_position,
            "end_position": seg.end_position,
            "start_rsid": seg.start_rsid,
            "end_rsid": seg.end_rsid,
            "centimorgans": seg.centimorgans,
            "snp_count": seg.snp_count,
        }
        for seg in segments
    ]


def deserialize_segments(data: list[dict]) -> list[MatchSegmentRecord]:
    """Parse list of dicts back to MatchSegmentRecord instances.

    Args:
        data: List of dictionaries (as read from JSON) with segment fields.

    Returns:
        List of MatchSegmentRecord instances.
    """
    return [
        MatchSegmentRecord(
            chromosome=item["chromosome"],
            start_position=int(item["start_position"]),
            end_position=int(item["end_position"]),
            start_rsid=item["start_rsid"],
            end_rsid=item["end_rsid"],
            centimorgans=float(item["centimorgans"]),
            snp_count=int(item["snp_count"]),
        )
        for item in data
    ]


def save_match_segments(
    project_path: Path, match_id: str, segments: list[MatchSegmentRecord]
) -> str:
    """Serialize and write match segments to the dna/ subfolder.

    Args:
        project_path: Path to the .json.gz project file.
        match_id: The DnaMatch ID used for filename generation.
        segments: List of MatchSegmentRecord instances to save.

    Returns:
        The filename written (e.g., 'match_segments_abc123.json').
    """
    filename = f"match_segments_{match_id}.json"
    data = serialize_segments(segments)
    write_dna_file(project_path, filename, data)
    return filename


def load_match_segments(
    project_path: Path, filename: str
) -> list[MatchSegmentRecord]:
    """Read and deserialize match segments from the dna/ subfolder.

    Args:
        project_path: Path to the .json.gz project file.
        filename: The segment file name within the dna/ subfolder.

    Returns:
        List of MatchSegmentRecord instances.

    Raises:
        FileNotFoundError: If the segment file doesn't exist.
        json.JSONDecodeError: If the file content is not valid JSON.
    """
    data = read_dna_file(project_path, filename)
    return deserialize_segments(data)
