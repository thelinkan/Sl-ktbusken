"""Parsers for raw DNA genotype data files (AncestryDNA, MyHeritage).

Supports two formats:
- AncestryDNA: Tab-delimited TXT with # comment lines
- MyHeritage: CSV with quoted fields and ## header lines

Each parser validates individual rows and skips invalid ones, reporting
the count of skipped rows in the result.
"""

from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass, field
from pathlib import Path

VALID_CHROMOSOMES = {
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
    "21", "22", "X", "Y", "MT",
}

MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB


@dataclass
class RawSnpRecord:
    """A single SNP genotype record."""

    rsid: str
    chromosome: str
    position: int
    alleles: str  # e.g., "AG", "CC", "--"


@dataclass
class ParseResult:
    """Result of parsing a raw DNA file."""

    records: list[RawSnpRecord] = field(default_factory=list)
    skipped_rows: int = 0
    format_detected: str = ""  # "ancestrydna" or "myheritage"


def _check_file_size(file_path: Path) -> None:
    """Raise ValueError if the file exceeds the 100 MB size limit."""
    file_size = os.path.getsize(file_path)
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            "Filen är för stor. Maximal filstorlek är 100 MB."
        )


def detect_format(file_path: Path) -> str | None:
    """Detect the raw DNA file format by inspecting initial lines.

    Returns:
        "ancestrydna" or "myheritage" if recognized, None otherwise.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            # Read first 50 lines to look for format indicators
            lines: list[str] = []
            for _ in range(50):
                line = f.readline()
                if not line:
                    break
                lines.append(line)
    except OSError:
        return None

    if not lines:
        return None

    # Check for MyHeritage format: lines starting with ## or CSV with quoted RSID header
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("##"):
            # MyHeritage uses ## for metadata headers
            if "myheritage" in stripped.lower():
                return "myheritage"
            # Continue checking more lines
            continue
        if stripped.startswith("#"):
            # AncestryDNA uses # for comments
            continue
        # First non-comment line — check if it's a header
        if stripped:
            # MyHeritage: quoted fields like "RSID","CHROMOSOME","POSITION","RESULT"
            if '"RSID"' in stripped or '"rsid"' in stripped.lower():
                return "myheritage"
            # AncestryDNA: tab-delimited header like "rsid\tchromosome\tposition\tallele1\tallele2"
            if "\t" in stripped:
                parts = stripped.split("\t")
                if len(parts) >= 5 and parts[0].lower() == "rsid":
                    return "ancestrydna"
            break

    # Second pass: if we saw ## headers but no explicit myheritage identifier,
    # check if the data looks like MyHeritage CSV
    has_double_hash = any(line.strip().startswith("##") for line in lines)
    if has_double_hash:
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if stripped:
                # Check for CSV with quoted fields
                if '"RSID"' in stripped.upper():
                    return "myheritage"
                break

    # Check if we have AncestryDNA style with # comments and tab-delimited data
    has_hash_comments = any(
        line.strip().startswith("#") and not line.strip().startswith("##")
        for line in lines
    )
    if has_hash_comments:
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if stripped:
                parts = stripped.split("\t")
                if len(parts) >= 5 and parts[0].lower() == "rsid":
                    return "ancestrydna"
                break

    return None


def _is_valid_record(rsid: str, chromosome: str, position: int, alleles: str) -> bool:
    """Validate a parsed SNP record."""
    if not rsid:
        return False
    if chromosome not in VALID_CHROMOSOMES:
        return False
    if position < 0:
        return False
    if not alleles:
        return False
    return True


def parse_ancestrydna(file_path: Path) -> ParseResult:
    """Parse an AncestryDNA tab-delimited raw data file.

    Format:
        # Comment lines start with #
        rsid\tchromosome\tposition\tallele1\tallele2
        rs4477212\t1\t82154\tA\tA

    Returns:
        ParseResult with records and skipped row count.
    """
    _check_file_size(file_path)

    records: list[RawSnpRecord] = []
    skipped_rows = 0
    header_seen = False

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            stripped = line.strip()

            # Skip empty lines and comment lines
            if not stripped or stripped.startswith("#"):
                continue

            # Skip the column header line
            if not header_seen:
                parts = stripped.split("\t")
                if len(parts) >= 4 and parts[0].lower() == "rsid":
                    header_seen = True
                    continue
                # If first non-comment line doesn't look like a header,
                # treat it as data
                header_seen = True

            # Parse data row
            parts = stripped.split("\t")
            if len(parts) < 5:
                skipped_rows += 1
                continue

            rsid = parts[0].strip()
            chromosome = parts[1].strip().upper()
            position_str = parts[2].strip()
            allele1 = parts[3].strip()
            allele2 = parts[4].strip()

            # Normalize chromosome
            if chromosome == "MT" or chromosome == "M":
                chromosome = "MT"

            try:
                position = int(position_str)
            except (ValueError, TypeError):
                skipped_rows += 1
                continue

            alleles = allele1 + allele2

            if _is_valid_record(rsid, chromosome, position, alleles):
                records.append(
                    RawSnpRecord(
                        rsid=rsid,
                        chromosome=chromosome,
                        position=position,
                        alleles=alleles,
                    )
                )
            else:
                skipped_rows += 1

    return ParseResult(
        records=records,
        skipped_rows=skipped_rows,
        format_detected="ancestrydna",
    )


def parse_myheritage(file_path: Path) -> ParseResult:
    """Parse a MyHeritage CSV raw data file.

    Format:
        ##fileformat=MyHeritage
        ##...
        "RSID","CHROMOSOME","POSITION","RESULT"
        "rs3094315","1","752566","AG"

    Returns:
        ParseResult with records and skipped row count.
    """
    _check_file_size(file_path)

    records: list[RawSnpRecord] = []
    skipped_rows = 0
    header_seen = False

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        # Collect non-comment lines for CSV parsing
        data_lines: list[str] = []
        for line in f:
            stripped = line.strip()
            # Skip ## comment/metadata lines and # comment lines
            if stripped.startswith("#"):
                continue
            if not stripped:
                continue
            data_lines.append(line)

    if not data_lines:
        return ParseResult(
            records=records,
            skipped_rows=skipped_rows,
            format_detected="myheritage",
        )

    # Parse the CSV data (first line should be the header)
    reader = csv.reader(io.StringIO("".join(data_lines)))

    for row in reader:
        if not row:
            continue

        # Detect and skip header row
        if not header_seen:
            # Check if this looks like a header row
            if row[0].strip().upper() == "RSID":
                header_seen = True
                continue
            # If first row doesn't look like a header, treat as data
            header_seen = True

        # Parse data row — expect at least 4 columns: RSID, CHROMOSOME, POSITION, RESULT
        if len(row) < 4:
            skipped_rows += 1
            continue

        rsid = row[0].strip()
        chromosome = row[1].strip().upper()
        position_str = row[2].strip()
        alleles = row[3].strip()

        # Normalize chromosome
        if chromosome == "MT" or chromosome == "M":
            chromosome = "MT"

        try:
            position = int(position_str)
        except (ValueError, TypeError):
            skipped_rows += 1
            continue

        if _is_valid_record(rsid, chromosome, position, alleles):
            records.append(
                RawSnpRecord(
                    rsid=rsid,
                    chromosome=chromosome,
                    position=position,
                    alleles=alleles,
                )
            )
        else:
            skipped_rows += 1

    return ParseResult(
        records=records,
        skipped_rows=skipped_rows,
        format_detected="myheritage",
    )


def parse_raw_dna_file(file_path: Path) -> ParseResult:
    """Auto-detect format and parse a raw DNA file.

    Args:
        file_path: Path to the raw DNA data file.

    Returns:
        ParseResult with parsed records, skipped count, and detected format.

    Raises:
        ValueError: If the file format is not recognized or the file is too large.
    """
    _check_file_size(file_path)

    detected = detect_format(file_path)
    if detected is None:
        raise ValueError(
            "Filformatet känns inte igen. Stödda format: "
            "AncestryDNA (tabbseparerad TXT), MyHeritage (CSV)."
        )

    if detected == "ancestrydna":
        return parse_ancestrydna(file_path)
    elif detected == "myheritage":
        return parse_myheritage(file_path)
    else:
        raise ValueError(
            "Filformatet känns inte igen. Stödda format: "
            "AncestryDNA (tabbseparerad TXT), MyHeritage (CSV)."
        )
