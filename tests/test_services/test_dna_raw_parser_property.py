"""Property-based tests for raw DNA file parsing.

# Feature: dna-cluster-enhancements, Property 7: Raw DNA parsing produces valid records
# Feature: dna-cluster-enhancements, Property 8: Raw DNA parse completeness

Validates: Requirements 11.2, 11.3, 11.5
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.services.dna_raw_parser import (
    VALID_CHROMOSOMES,
    parse_ancestrydna,
    parse_myheritage,
)

# ---------------------------------------------------------------------------
# Strategies for generating valid raw DNA file content
# ---------------------------------------------------------------------------

# rsid strategy: "rs" followed by digits
_rsid_strategy = st.integers(min_value=1, max_value=99999999).map(lambda n: f"rs{n}")

# chromosome strategy: one of the valid chromosomes
_chromosome_strategy = st.sampled_from(list(VALID_CHROMOSOMES))

# position strategy: non-negative integer
_position_strategy = st.integers(min_value=0, max_value=250_000_000)

# allele strategy: single nucleotide letters
_ALLELES = ["A", "C", "G", "T", "0", "-"]
_allele_strategy = st.sampled_from(_ALLELES)


# ---------------------------------------------------------------------------
# AncestryDNA file content generation
# ---------------------------------------------------------------------------


@st.composite
def ancestrydna_data_row(draw: DrawFn) -> str:
    """Generate a single valid AncestryDNA data row (tab-delimited)."""
    rsid = draw(_rsid_strategy)
    chrom = draw(_chromosome_strategy)
    position = draw(_position_strategy)
    allele1 = draw(_allele_strategy)
    allele2 = draw(_allele_strategy)
    return f"{rsid}\t{chrom}\t{position}\t{allele1}\t{allele2}"


@st.composite
def ancestrydna_file_content(draw: DrawFn) -> tuple[str, int]:
    """Generate valid AncestryDNA file content and the number of data rows.

    Returns:
        Tuple of (file content string, number of data rows).
    """
    # Optional comment lines (1-3)
    num_comments = draw(st.integers(min_value=1, max_value=3))
    comment_lines = [f"# AncestryDNA comment line {i}" for i in range(num_comments)]

    # Header line
    header = "rsid\tchromosome\tposition\tallele1\tallele2"

    # Data rows (1-20)
    data_rows = draw(st.lists(ancestrydna_data_row(), min_size=1, max_size=20))

    content = "\n".join(comment_lines + [header] + data_rows) + "\n"
    return content, len(data_rows)


# ---------------------------------------------------------------------------
# MyHeritage file content generation
# ---------------------------------------------------------------------------


@st.composite
def myheritage_data_row(draw: DrawFn) -> str:
    """Generate a single valid MyHeritage data row (quoted CSV)."""
    rsid = draw(_rsid_strategy)
    chrom = draw(_chromosome_strategy)
    position = draw(_position_strategy)
    allele1 = draw(_allele_strategy)
    allele2 = draw(_allele_strategy)
    alleles = allele1 + allele2
    return f'"{rsid}","{chrom}","{position}","{alleles}"'


@st.composite
def myheritage_file_content(draw: DrawFn) -> tuple[str, int]:
    """Generate valid MyHeritage file content and the number of data rows.

    Returns:
        Tuple of (file content string, number of data rows).
    """
    # ## header lines
    header_lines = [
        "##fileformat=MyHeritage",
        "##reference=GRCh37",
    ]

    # CSV header
    csv_header = '"RSID","CHROMOSOME","POSITION","RESULT"'

    # Data rows (1-20)
    data_rows = draw(st.lists(myheritage_data_row(), min_size=1, max_size=20))

    content = "\n".join(header_lines + [csv_header] + data_rows) + "\n"
    return content, len(data_rows)


# ---------------------------------------------------------------------------
# Property 7: Raw DNA parsing produces valid records
# ---------------------------------------------------------------------------


class TestRawDnaParsingProducesValidRecords:
    """Property 7: For any valid raw DNA file content, parsing SHALL produce
    a ParseResult where every record has a non-empty rsid, a chromosome value
    in the valid set, a non-negative position integer, and a non-empty alleles
    string.

    **Validates: Requirements 11.2, 11.3**
    """

    @settings(max_examples=100)
    @given(data=ancestrydna_file_content())
    def test_ancestrydna_produces_valid_records(
        self, data: tuple[str, int]
    ) -> None:
        """AncestryDNA parsing produces records with valid fields."""
        content, _row_count = data

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", encoding="utf-8", delete=False
        ) as f:
            f.write(content)
            file_path = Path(f.name)

        try:
            result = parse_ancestrydna(file_path)

            for record in result.records:
                assert record.rsid, "rsid must be non-empty"
                assert record.chromosome in VALID_CHROMOSOMES, (
                    f"chromosome '{record.chromosome}' not in valid set"
                )
                assert record.position >= 0, "position must be non-negative"
                assert record.alleles, "alleles must be non-empty"
        finally:
            file_path.unlink(missing_ok=True)

    @settings(max_examples=100)
    @given(data=myheritage_file_content())
    def test_myheritage_produces_valid_records(
        self, data: tuple[str, int]
    ) -> None:
        """MyHeritage parsing produces records with valid fields."""
        content, _row_count = data

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", encoding="utf-8", delete=False
        ) as f:
            f.write(content)
            file_path = Path(f.name)

        try:
            result = parse_myheritage(file_path)

            for record in result.records:
                assert record.rsid, "rsid must be non-empty"
                assert record.chromosome in VALID_CHROMOSOMES, (
                    f"chromosome '{record.chromosome}' not in valid set"
                )
                assert record.position >= 0, "position must be non-negative"
                assert record.alleles, "alleles must be non-empty"
        finally:
            file_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Property 8: Raw DNA parse completeness
# ---------------------------------------------------------------------------


class TestRawDnaParseCompleteness:
    """Property 8: For any raw DNA file content with N data rows, the number
    of successfully parsed records plus the number of skipped rows SHALL
    equal N.

    **Validates: Requirements 11.5**
    """

    @settings(max_examples=100)
    @given(data=ancestrydna_file_content())
    def test_ancestrydna_completeness(
        self, data: tuple[str, int]
    ) -> None:
        """AncestryDNA: records + skipped_rows == data row count."""
        content, row_count = data

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", encoding="utf-8", delete=False
        ) as f:
            f.write(content)
            file_path = Path(f.name)

        try:
            result = parse_ancestrydna(file_path)

            assert len(result.records) + result.skipped_rows == row_count, (
                f"Expected {row_count} total, got {len(result.records)} records + "
                f"{result.skipped_rows} skipped = "
                f"{len(result.records) + result.skipped_rows}"
            )
        finally:
            file_path.unlink(missing_ok=True)

    @settings(max_examples=100)
    @given(data=myheritage_file_content())
    def test_myheritage_completeness(
        self, data: tuple[str, int]
    ) -> None:
        """MyHeritage: records + skipped_rows == data row count."""
        content, row_count = data

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", encoding="utf-8", delete=False
        ) as f:
            f.write(content)
            file_path = Path(f.name)

        try:
            result = parse_myheritage(file_path)

            assert len(result.records) + result.skipped_rows == row_count, (
                f"Expected {row_count} total, got {len(result.records)} records + "
                f"{result.skipped_rows} skipped = "
                f"{len(result.records) + result.skipped_rows}"
            )
        finally:
            file_path.unlink(missing_ok=True)
