"""Property-based tests for MyHeritage match CSV parsing.

# Feature: dna-cluster-enhancements, Property 10 & 11: Match CSV parsing

Validates: Requirements 13.2, 13.9
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.services.dna_match_csv_parser import parse_match_csv


# ---------------------------------------------------------------------------
# Hypothesis strategies for generating valid MyHeritage match CSV data
# ---------------------------------------------------------------------------

HEADER = "Name,Match Name,Chromosome,Start Location,End Location,Start RSID,End RSID,Centimorgans,SNPs"

_CHROMOSOMES = [str(i) for i in range(1, 23)] + ["X"]

_safe_name = st.text(
    alphabet=st.characters(categories=("L", "N", "Z"), exclude_characters=",\"\n\r"),
    min_size=1,
    max_size=30,
)

_rsid = st.integers(min_value=1, max_value=99999999).map(lambda n: f"rs{n}")


@st.composite
def valid_csv_row(draw: DrawFn) -> str:
    """Generate a single valid MyHeritage match CSV data row."""
    name = draw(_safe_name)
    match_name = draw(_safe_name)
    chromosome = draw(st.sampled_from(_CHROMOSOMES))
    start = draw(st.integers(min_value=1, max_value=250_000_000))
    end = draw(st.integers(min_value=start + 1, max_value=250_000_001))
    start_rsid = draw(_rsid)
    end_rsid = draw(_rsid)
    cm = draw(st.floats(min_value=0.01, max_value=300.0, allow_nan=False, allow_infinity=False))
    snp_count = draw(st.integers(min_value=0, max_value=100_000))
    return f"{name},{match_name},{chromosome},{start},{end},{start_rsid},{end_rsid},{cm},{snp_count}"


@st.composite
def invalid_csv_row(draw: DrawFn) -> str:
    """Generate a row with non-numeric cM value (will be skipped)."""
    name = draw(_safe_name)
    match_name = draw(_safe_name)
    chromosome = draw(st.sampled_from(_CHROMOSOMES))
    start = draw(st.integers(min_value=1, max_value=250_000_000))
    end = draw(st.integers(min_value=start + 1, max_value=250_000_001))
    start_rsid = draw(_rsid)
    end_rsid = draw(_rsid)
    # Non-numeric cM value - this will cause the row to be skipped
    cm_invalid = draw(st.sampled_from(["abc", "N/A", "", "---", "null"]))
    snp_count = draw(st.integers(min_value=0, max_value=100_000))
    return f"{name},{match_name},{chromosome},{start},{end},{start_rsid},{end_rsid},{cm_invalid},{snp_count}"


@st.composite
def valid_match_csv_text(draw: DrawFn) -> str:
    """Generate a valid MyHeritage match CSV text with header and data rows."""
    rows = draw(st.lists(valid_csv_row(), min_size=1, max_size=20))
    return HEADER + "\n" + "\n".join(rows)


@st.composite
def mixed_match_csv_text(draw: DrawFn) -> tuple[str, int, int]:
    """Generate CSV text with a mix of valid and invalid rows.

    Returns (csv_text, valid_count, invalid_count).
    """
    valid_rows = draw(st.lists(valid_csv_row(), min_size=1, max_size=10))
    invalid_rows = draw(st.lists(invalid_csv_row(), min_size=1, max_size=10))

    # Interleave valid and invalid rows
    all_rows = [(r, True) for r in valid_rows] + [(r, False) for r in invalid_rows]
    # Shuffle deterministically by drawing a permutation
    shuffled = draw(st.permutations(all_rows))

    csv_rows = [r for r, _ in shuffled]
    csv_text = HEADER + "\n" + "\n".join(csv_rows)
    return csv_text, len(valid_rows), len(invalid_rows)


# ---------------------------------------------------------------------------
# Property 10: Match CSV parsing produces valid segments
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(csv_text=valid_match_csv_text())
def test_match_csv_parsing_produces_valid_segments(csv_text: str) -> None:
    """**Validates: Requirements 13.2**

    For any valid MyHeritage match CSV text (with header row containing required
    columns), parsing SHALL produce MatchSegmentRecords where each record has a
    non-empty chromosome, start_position < end_position, centimorgans > 0,
    and snp_count >= 0.
    """
    result = parse_match_csv(csv_text)

    assert len(result.segments) > 0, "Expected at least one parsed segment"

    for segment in result.segments:
        assert segment.chromosome != "", (
            f"Expected non-empty chromosome, got empty string"
        )
        assert segment.start_position < segment.end_position, (
            f"Expected start_position ({segment.start_position}) < "
            f"end_position ({segment.end_position})"
        )
        assert segment.centimorgans > 0, (
            f"Expected centimorgans > 0, got {segment.centimorgans}"
        )
        assert segment.snp_count >= 0, (
            f"Expected snp_count >= 0, got {segment.snp_count}"
        )


# ---------------------------------------------------------------------------
# Property 11: Match CSV parse completeness
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(data=mixed_match_csv_text())
def test_match_csv_parse_completeness(data: tuple[str, int, int]) -> None:
    """**Validates: Requirements 13.9**

    For any match CSV text with N data rows (after header), the number of
    successfully parsed segments plus the number of skipped rows SHALL equal N.
    """
    csv_text, valid_count, invalid_count = data
    total_data_rows = valid_count + invalid_count

    result = parse_match_csv(csv_text)

    parsed_plus_skipped = len(result.segments) + result.skipped_rows
    assert parsed_plus_skipped == total_data_rows, (
        f"Expected parsed ({len(result.segments)}) + skipped ({result.skipped_rows}) "
        f"== total data rows ({total_data_rows}), "
        f"but got {parsed_plus_skipped}"
    )
