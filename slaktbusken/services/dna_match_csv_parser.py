"""Parser for pasted MyHeritage match CSV data.

Handles CSV text with the MyHeritage match format header row:
Name,Match Name,Chromosome,Start Location,End Location,Start RSID,End RSID,Centimorgans,SNPs

Parses each data row into a MatchSegmentRecord, skipping rows with invalid
numeric values in Centimorgans or SNPs columns.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

EXPECTED_COLUMNS = [
    "Name",
    "Match Name",
    "Chromosome",
    "Start Location",
    "End Location",
    "Start RSID",
    "End RSID",
    "Centimorgans",
    "SNPs",
]

EXPECTED_HEADER_SET = {col.lower() for col in EXPECTED_COLUMNS}


@dataclass
class MatchSegmentRecord:
    """A single match segment parsed from CSV data."""

    chromosome: str
    start_position: int
    end_position: int
    start_rsid: str
    end_rsid: str
    centimorgans: float
    snp_count: int


@dataclass
class MatchCsvParseResult:
    """Result of parsing pasted CSV match data."""

    segments: list[MatchSegmentRecord]
    match_name: str
    skipped_rows: int


def parse_match_csv(text: str) -> MatchCsvParseResult:
    """Parse MyHeritage match CSV text.

    Expects a header row with the required columns followed by data rows.
    Rows with non-numeric Centimorgans or SNPs values are skipped.

    Args:
        text: The pasted CSV text content.

    Returns:
        MatchCsvParseResult with parsed segments, match name, and skipped count.

    Raises:
        ValueError: If the text cannot be parsed (missing required columns
            or no valid data rows after header).
    """
    text = text.strip()
    if not text:
        raise ValueError(
            "Formatet känns inte igen. Förväntade kolumner: "
            "Name, Match Name, Chromosome, Start Location, End Location, "
            "Start RSID, End RSID, Centimorgans, SNPs"
        )

    reader = csv.reader(io.StringIO(text))

    # Detect and validate header row
    header_row = _find_header(reader)
    if header_row is None:
        raise ValueError(
            "Formatet känns inte igen. Förväntade kolumner: "
            "Name, Match Name, Chromosome, Start Location, End Location, "
            "Start RSID, End RSID, Centimorgans, SNPs"
        )

    # Build column index mapping (case-insensitive)
    col_indices = {col.strip().lower(): i for i, col in enumerate(header_row)}

    segments: list[MatchSegmentRecord] = []
    match_name = ""
    skipped_rows = 0

    for row in reader:
        if not row or all(cell.strip() == "" for cell in row):
            continue

        # Ensure enough columns
        if len(row) < len(EXPECTED_COLUMNS):
            skipped_rows += 1
            continue

        try:
            chromosome = row[col_indices["chromosome"]].strip()
            start_loc = row[col_indices["start location"]].strip()
            end_loc = row[col_indices["end location"]].strip()
            start_rsid = row[col_indices["start rsid"]].strip()
            end_rsid = row[col_indices["end rsid"]].strip()
            cm_str = row[col_indices["centimorgans"]].strip()
            snps_str = row[col_indices["snps"]].strip()
            row_match_name = row[col_indices["match name"]].strip()

            # Validate numeric fields
            centimorgans = float(cm_str)
            snp_count = int(snps_str)
            start_position = int(start_loc)
            end_position = int(end_loc)

        except (ValueError, IndexError):
            skipped_rows += 1
            continue

        # Capture match_name from first valid data row
        if not match_name and row_match_name:
            match_name = row_match_name

        segments.append(
            MatchSegmentRecord(
                chromosome=chromosome,
                start_position=start_position,
                end_position=end_position,
                start_rsid=start_rsid,
                end_rsid=end_rsid,
                centimorgans=centimorgans,
                snp_count=snp_count,
            )
        )

    if not segments:
        raise ValueError(
            "Formatet känns inte igen. Förväntade kolumner: "
            "Name, Match Name, Chromosome, Start Location, End Location, "
            "Start RSID, End RSID, Centimorgans, SNPs"
        )

    return MatchCsvParseResult(
        segments=segments,
        match_name=match_name,
        skipped_rows=skipped_rows,
    )


def _find_header(reader: csv.reader) -> list[str] | None:
    """Find and validate the header row in the CSV reader.

    Iterates through rows looking for one that contains all expected
    column names (case-insensitive match).

    Returns:
        The header row if found, None otherwise.
    """
    for row in reader:
        if not row:
            continue
        # Check if this row contains all expected columns
        row_lower = {cell.strip().lower() for cell in row}
        if EXPECTED_HEADER_SET.issubset(row_lower):
            return row
    return None
