# Feature: dna-cluster-enhancements, Property 9: DNA viewer combined filter correctness
"""Property-based tests for DNA viewer combined filter correctness.

Feature: dna-cluster-enhancements, Property 9: DNA viewer combined filter correctness

For any set of SNP records, search text, and chromosome filter selection, every
record in the filtered result SHALL satisfy both: (a) the rsID, chromosome, or
position contains the search text as a case-insensitive substring, AND (b) the
chromosome matches the selected filter (or filter is "Alla").

Also verifies completeness: no records that SHOULD match are excluded.

**Validates: Requirements 12.3, 12.5**
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.services.dna_raw_parser import RawSnpRecord
from slaktbusken.ui.dialogs.dna_viewer_dialog import DnaSnpTableModel


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_VALID_CHROMOSOMES = [
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
    "21", "22", "X", "Y", "MT",
]

# Generate realistic rsID strings (e.g., "rs12345")
_rsid_strategy = st.integers(min_value=1, max_value=9999999).map(
    lambda n: f"rs{n}"
)

_chromosome_strategy = st.sampled_from(_VALID_CHROMOSOMES)

_position_strategy = st.integers(min_value=1, max_value=250_000_000)

_alleles_strategy = st.sampled_from(["AA", "AG", "CC", "TT", "CT", "GG", "--"])


@st.composite
def raw_snp_record_strategy(draw: DrawFn) -> RawSnpRecord:
    """Generate a valid RawSnpRecord."""
    return RawSnpRecord(
        rsid=draw(_rsid_strategy),
        chromosome=draw(_chromosome_strategy),
        position=draw(_position_strategy),
        alleles=draw(_alleles_strategy),
    )


# Short search text — constrain to alphanumeric characters typical of searches
_search_text_strategy = st.text(
    alphabet=st.characters(categories=("L", "N")),
    min_size=0,
    max_size=8,
)


@st.composite
def filter_scenario(
    draw: DrawFn,
) -> tuple[list[RawSnpRecord], str, str]:
    """Generate a filter scenario: records, search text, chromosome filter.

    The chromosome filter is either "Alla" or a chromosome present in the records.

    Returns:
        (records, search_text, chromosome_filter)
    """
    records = draw(st.lists(raw_snp_record_strategy(), min_size=0, max_size=30))
    search_text = draw(_search_text_strategy)

    # Chromosome filter: either "Alla" or one of the chromosomes in the data
    if records:
        unique_chroms = list({r.chromosome for r in records})
        chromosome_filter = draw(
            st.sampled_from(["Alla"] + unique_chroms)
        )
    else:
        chromosome_filter = "Alla"

    return (records, search_text, chromosome_filter)


def _record_matches_filter(record: RawSnpRecord, search_text: str, chromosome: str) -> bool:
    """Reference implementation: check if a record satisfies both filter conditions."""
    # Condition (b): chromosome filter
    if chromosome != "Alla" and record.chromosome != chromosome:
        return False

    # Condition (a): text search (if non-empty)
    search_lower = search_text.strip().lower()
    if search_lower:
        if (
            search_lower not in record.rsid.lower()
            and search_lower not in record.chromosome.lower()
            and search_lower not in str(record.position).lower()
        ):
            return False

    return True


def _get_model_filtered_records(model: DnaSnpTableModel) -> list[tuple[str, str, str, str]]:
    """Extract all visible rows from the model as tuples of (rsid, chrom, pos, alleles)."""
    rows = []
    for row_idx in range(model.rowCount()):
        from PySide6.QtCore import QModelIndex
        rsid = model.data(model.index(row_idx, 0))
        chrom = model.data(model.index(row_idx, 1))
        pos = model.data(model.index(row_idx, 2))
        alleles = model.data(model.index(row_idx, 3))
        rows.append((rsid, chrom, pos, alleles))
    return rows


class TestDnaViewerCombinedFilterCorrectness:
    """Feature: dna-cluster-enhancements, Property 9: DNA viewer combined filter correctness

    For any set of SNP records, search text, and chromosome filter selection,
    every record in the filtered result SHALL satisfy both: (a) the rsID,
    chromosome, or position contains the search text as a case-insensitive
    substring, AND (b) the chromosome matches the selected filter (or filter
    is "Alla").

    **Validates: Requirements 12.3, 12.5**
    """

    @given(data=filter_scenario())
    @settings(max_examples=100)
    def test_all_filtered_records_satisfy_both_conditions(
        self,
        data: tuple[list[RawSnpRecord], str, str],
    ) -> None:
        """Every record in the filtered result satisfies both the text search
        AND the chromosome filter condition.

        Feature: dna-cluster-enhancements, Property 9: DNA viewer combined filter correctness
        **Validates: Requirements 12.3, 12.5**
        """
        records, search_text, chromosome_filter = data

        model = DnaSnpTableModel(records)
        model.set_filter(search_text, chromosome_filter)

        search_lower = search_text.strip().lower()

        for row_idx in range(model.rowCount()):
            rsid = model.data(model.index(row_idx, 0))
            chrom = model.data(model.index(row_idx, 1))
            pos = model.data(model.index(row_idx, 2))

            # Condition (b): chromosome filter
            if chromosome_filter != "Alla":
                assert chrom == chromosome_filter, (
                    f"Row {row_idx}: chromosome '{chrom}' does not match "
                    f"filter '{chromosome_filter}'"
                )

            # Condition (a): text search
            if search_lower:
                text_match = (
                    search_lower in rsid.lower()
                    or search_lower in chrom.lower()
                    or search_lower in pos.lower()
                )
                assert text_match, (
                    f"Row {row_idx}: none of rsid='{rsid}', chrom='{chrom}', "
                    f"pos='{pos}' contain search text '{search_lower}'"
                )

    @given(data=filter_scenario())
    @settings(max_examples=100)
    def test_no_matching_records_are_excluded(
        self,
        data: tuple[list[RawSnpRecord], str, str],
    ) -> None:
        """No records that SHOULD match both conditions are excluded from
        the filtered result (completeness).

        Feature: dna-cluster-enhancements, Property 9: DNA viewer combined filter correctness
        **Validates: Requirements 12.3, 12.5**
        """
        records, search_text, chromosome_filter = data

        model = DnaSnpTableModel(records)
        model.set_filter(search_text, chromosome_filter)

        # Compute expected matching records using reference implementation
        expected_records = [
            r for r in records
            if _record_matches_filter(r, search_text, chromosome_filter)
        ]

        # The model should contain exactly as many rows as expected
        assert model.rowCount() == len(expected_records), (
            f"Expected {len(expected_records)} rows but model has "
            f"{model.rowCount()} rows.\n"
            f"  search_text='{search_text}', chromosome_filter='{chromosome_filter}'\n"
            f"  total_records={len(records)}"
        )

        # Verify each expected record appears in the model output
        model_rows = _get_model_filtered_records(model)
        expected_tuples = [
            (r.rsid, r.chromosome, str(r.position), r.alleles)
            for r in expected_records
        ]

        assert model_rows == expected_tuples, (
            f"Filtered rows do not match expected.\n"
            f"  search_text='{search_text}', chromosome_filter='{chromosome_filter}'\n"
            f"  Expected: {expected_tuples[:5]}...\n"
            f"  Got: {model_rows[:5]}..."
        )

    @given(data=filter_scenario())
    @settings(max_examples=100)
    def test_no_filter_returns_all_records(
        self,
        data: tuple[list[RawSnpRecord], str, str],
    ) -> None:
        """When search_text is empty and chromosome filter is "Alla", all
        records SHALL be returned.

        Feature: dna-cluster-enhancements, Property 9: DNA viewer combined filter correctness
        **Validates: Requirements 12.3, 12.5**
        """
        records, _, _ = data

        model = DnaSnpTableModel(records)
        model.set_filter("", "Alla")

        assert model.rowCount() == len(records), (
            f"No-filter case: expected {len(records)} rows but got "
            f"{model.rowCount()}"
        )
