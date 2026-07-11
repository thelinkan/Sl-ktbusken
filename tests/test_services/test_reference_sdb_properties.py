"""Property-based tests for Rötter.se SDB identifier parsing.

Feature: source-management, Property 13: Rötter.se SDB identifier parsing

Validates: Requirements 8.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.parsing.reference_parser import (
    ParsedReference,
    parse_reference,
    parse_rotter,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Single digit after SDB (0-9)
version_digit = st.integers(min_value=0, max_value=9)

# One or more digits after underscore
record_number = st.integers(min_value=1, max_value=99999)


# ---------------------------------------------------------------------------
# Property 13: Rötter.se SDB identifier parsing
# ---------------------------------------------------------------------------


class TestRotterSDBIdentifierProperty:
    """Property 13: Rötter.se SDB identifier parsing.

    **Validates: Requirements 8.3**

    For any string matching "SDB{single_digit}_{one_or_more_digits}", the parser
    SHALL produce a source with leverantor_name "Rötter.se", kalltyp_name
    "Sveriges Dödbok Webb", and arkivreferens set to the full matched identifier.
    """

    @given(digit=version_digit, record=record_number)
    @settings(max_examples=100, deadline=None)
    def test_sdb_leverantor_is_rotter(self, digit: int, record: int) -> None:
        """SDB identifier produces leverantor_name == 'Rötter.se'."""
        sdb_id = f"SDB{digit}_{record}"
        result = parse_rotter(sdb_id)

        assert result is not None, f"Failed to parse: {sdb_id}"
        assert result.leverantor_name == "Rötter.se"

    @given(digit=version_digit, record=record_number)
    @settings(max_examples=100, deadline=None)
    def test_sdb_kalltyp_is_sveriges_dodbok_webb(self, digit: int, record: int) -> None:
        """SDB identifier produces kalltyp_name == 'Sveriges Dödbok Webb'."""
        sdb_id = f"SDB{digit}_{record}"
        result = parse_rotter(sdb_id)

        assert result is not None, f"Failed to parse: {sdb_id}"
        assert result.kalltyp_name == "Sveriges Dödbok Webb"

    @given(digit=version_digit, record=record_number)
    @settings(max_examples=100, deadline=None)
    def test_sdb_arkivreferens_is_full_match(self, digit: int, record: int) -> None:
        """SDB identifier sets arkivreferens to the full matched identifier."""
        sdb_id = f"SDB{digit}_{record}"
        result = parse_rotter(sdb_id)

        assert result is not None, f"Failed to parse: {sdb_id}"
        assert result.arkivreferens == sdb_id

    @given(digit=version_digit, record=record_number)
    @settings(max_examples=100, deadline=None)
    def test_sdb_title_is_full_match(self, digit: int, record: int) -> None:
        """SDB identifier sets title to the full matched identifier."""
        sdb_id = f"SDB{digit}_{record}"
        result = parse_rotter(sdb_id)

        assert result is not None, f"Failed to parse: {sdb_id}"
        assert result.title == sdb_id

    @given(digit=version_digit, record=record_number)
    @settings(max_examples=100, deadline=None)
    def test_sdb_via_parse_reference(self, digit: int, record: int) -> None:
        """SDB identifier is also matched via the top-level parse_reference."""
        sdb_id = f"SDB{digit}_{record}"
        result = parse_reference(sdb_id)

        assert result is not None, f"parse_reference failed for: {sdb_id}"
        assert result.leverantor_name == "Rötter.se"
        assert result.kalltyp_name == "Sveriges Dödbok Webb"
        assert result.arkivreferens == sdb_id
        assert result.title == sdb_id

    @given(
        digit=version_digit,
        record=record_number,
        prefix=st.text(
            alphabet=st.characters(whitelist_categories=("L", "Zs")),
            min_size=1,
            max_size=10,
        ).map(lambda s: s.strip()).filter(lambda s: len(s) > 0),
        suffix=st.text(
            alphabet=st.characters(whitelist_categories=("L", "Zs")),
            min_size=1,
            max_size=10,
        ).map(lambda s: s.strip()).filter(lambda s: len(s) > 0),
    )
    @settings(max_examples=100, deadline=None)
    def test_sdb_embedded_in_text(
        self, digit: int, record: int, prefix: str, suffix: str
    ) -> None:
        """SDB pattern embedded in surrounding text still gets parsed."""
        sdb_id = f"SDB{digit}_{record}"
        text = f"{prefix} {sdb_id} {suffix}"
        result = parse_rotter(text)

        assert result is not None, f"Failed to parse embedded SDB: {text}"
        assert result.leverantor_name == "Rötter.se"
        assert result.kalltyp_name == "Sveriges Dödbok Webb"
        assert result.arkivreferens == sdb_id
