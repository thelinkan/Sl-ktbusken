"""Property-based tests for Rötter.se reference parsing.

Feature: source-management, Property 12: Rötter.se Sveriges Dödbok reference parsing
Feature: source-management, Property 13: Rötter.se SDB identifier parsing

Validates: Requirements 8.1, 8.2, 8.3
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from slaktbusken.parsing.reference_parser import (
    ParsedReference,
    parse_reference,
    parse_rotter,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

record_id_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "Nd"),
        whitelist_characters="-_",
    ),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip())

case_variant_prefix = st.sampled_from(
    [
        "Sveriges dödbok webb",
        "SVERIGES DÖDBOK WEBB",
        "Sveriges Dödbok Webb",
        "sveriges dödbok webb",
    ]
)


# ---------------------------------------------------------------------------
# Property 12: Rötter.se Sveriges Dödbok reference parsing
# ---------------------------------------------------------------------------


class TestRotterSverigesDodbokProperty:
    """Property 12: Rötter.se Sveriges Dödbok reference parsing.

    *For any* string matching "Sveriges dödbok webb - {record_id}"
    (case-insensitive on the prefix), the parser SHALL produce a source with
    leverantor_name "Rötter.se", kalltyp_name "Sveriges Dödbok Webb", and
    arkivreferens set to the trimmed record_id portion.

    **Validates: Requirements 8.1, 8.2**
    """

    @given(
        prefix=case_variant_prefix,
        record_id=record_id_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_record_id_extraction_is_trimmed(self, prefix: str, record_id: str) -> None:
        """Arkivreferens equals the trimmed record_id portion."""
        text = f"{prefix} - {record_id}"
        result = parse_rotter(text)

        assert result is not None
        assert result.arkivreferens == record_id.strip()

    @given(
        prefix=case_variant_prefix,
        record_id=record_id_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_leverantor_is_rotter(self, prefix: str, record_id: str) -> None:
        """Leverantör name is always 'Rötter.se'."""
        text = f"{prefix} - {record_id}"
        result = parse_rotter(text)

        assert result is not None
        assert result.leverantor_name == "Rötter.se"

    @given(
        prefix=case_variant_prefix,
        record_id=record_id_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_kalltyp_is_sveriges_dodbok_webb(self, prefix: str, record_id: str) -> None:
        """Källtyp name is always 'Sveriges Dödbok Webb'."""
        text = f"{prefix} - {record_id}"
        result = parse_rotter(text)

        assert result is not None
        assert result.kalltyp_name == "Sveriges Dödbok Webb"

    @given(
        prefix=case_variant_prefix,
        record_id=record_id_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_case_insensitive_prefix(self, prefix: str, record_id: str) -> None:
        """All case variants of the prefix produce a valid ParsedReference."""
        text = f"{prefix} - {record_id}"
        result = parse_rotter(text)

        assert result is not None
        assert isinstance(result, ParsedReference)

    @given(prefix=case_variant_prefix)
    @settings(max_examples=100, deadline=None)
    def test_general_contains_pattern(self, prefix: str) -> None:
        """Text containing 'Sveriges dödbok webb' without ' - record_id' format
        still matches with Rötter.se and Sveriges Dödbok Webb."""
        # Text that contains the prefix but not in the " - record_id" format
        text = f"Referens från {prefix} källa"
        result = parse_rotter(text)

        assert result is not None
        assert result.leverantor_name == "Rötter.se"
        assert result.kalltyp_name == "Sveriges Dödbok Webb"
