"""Property-based tests for Arkiv Digital census reference parsing.

Feature: source-management, Property 10: Arkiv Digital census reference parsing

Validates: Requirements 7.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.parsing.reference_parser import (
    ParsedReference,
    parse_arkiv_digital_census,
    parse_reference,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

census_digits_strategy = st.integers(min_value=1, max_value=99999).map(str)


# ---------------------------------------------------------------------------
# Property 10: Arkiv Digital census reference parsing
# ---------------------------------------------------------------------------


class TestArkivDigitalCensusParsingProperty:
    """Feature: source-management, Property 10: Arkiv Digital census reference parsing

    For any string matching the pattern "r{digits}.p{digits}" (where each digit
    group is 1+ characters), the parser SHALL produce a source with
    leverantor_name "Arkiv Digital", källtyp_name "Folkräkning", and store the
    full matched string as arkivreferens.

    **Validates: Requirements 7.3**
    """

    @given(r_digits=census_digits_strategy, p_digits=census_digits_strategy)
    @settings(max_examples=100, deadline=None)
    def test_census_pattern_produces_correct_leverantor(
        self, r_digits: str, p_digits: str
    ) -> None:
        """For any r_digits and p_digits, parsing "r{r_digits}.p{p_digits}"
        produces leverantor_name == "Arkiv Digital".

        Feature: source-management, Property 10: Arkiv Digital census reference parsing
        **Validates: Requirements 7.3**
        """
        ref_string = f"r{r_digits}.p{p_digits}"
        result = parse_arkiv_digital_census(ref_string)

        assert result is not None, (
            f"Expected a ParsedReference for '{ref_string}', got None"
        )
        assert result.leverantor_name == "Arkiv Digital", (
            f"Expected leverantor_name='Arkiv Digital' for '{ref_string}', "
            f"got '{result.leverantor_name}'"
        )

    @given(r_digits=census_digits_strategy, p_digits=census_digits_strategy)
    @settings(max_examples=100, deadline=None)
    def test_census_pattern_produces_folkrakning_kalltyp(
        self, r_digits: str, p_digits: str
    ) -> None:
        """For any r_digits and p_digits, parsing "r{r_digits}.p{p_digits}"
        produces kalltyp_name == "Folkräkning".

        Feature: source-management, Property 10: Arkiv Digital census reference parsing
        **Validates: Requirements 7.3**
        """
        ref_string = f"r{r_digits}.p{p_digits}"
        result = parse_arkiv_digital_census(ref_string)

        assert result is not None, (
            f"Expected a ParsedReference for '{ref_string}', got None"
        )
        assert result.kalltyp_name == "Folkräkning", (
            f"Expected kalltyp_name='Folkräkning' for '{ref_string}', "
            f"got '{result.kalltyp_name}'"
        )

    @given(r_digits=census_digits_strategy, p_digits=census_digits_strategy)
    @settings(max_examples=100, deadline=None)
    def test_census_pattern_stores_full_match_as_arkivreferens(
        self, r_digits: str, p_digits: str
    ) -> None:
        """For any r_digits and p_digits, parsing "r{r_digits}.p{p_digits}"
        stores the full matched string as arkivreferens.

        Feature: source-management, Property 10: Arkiv Digital census reference parsing
        **Validates: Requirements 7.3**
        """
        ref_string = f"r{r_digits}.p{p_digits}"
        result = parse_arkiv_digital_census(ref_string)

        assert result is not None, (
            f"Expected a ParsedReference for '{ref_string}', got None"
        )
        assert result.arkivreferens == ref_string, (
            f"Expected arkivreferens='{ref_string}', "
            f"got '{result.arkivreferens}'"
        )

    @given(r_digits=census_digits_strategy, p_digits=census_digits_strategy)
    @settings(max_examples=100, deadline=None)
    def test_census_pattern_sets_title_to_matched_string(
        self, r_digits: str, p_digits: str
    ) -> None:
        """For any r_digits and p_digits, parsing "r{r_digits}.p{p_digits}"
        sets title to the matched string.

        Feature: source-management, Property 10: Arkiv Digital census reference parsing
        **Validates: Requirements 7.3**
        """
        ref_string = f"r{r_digits}.p{p_digits}"
        result = parse_arkiv_digital_census(ref_string)

        assert result is not None, (
            f"Expected a ParsedReference for '{ref_string}', got None"
        )
        assert result.title == ref_string, (
            f"Expected title='{ref_string}', got '{result.title}'"
        )

    @given(r_digits=census_digits_strategy, p_digits=census_digits_strategy)
    @settings(max_examples=100, deadline=None)
    def test_census_via_parse_reference(
        self, r_digits: str, p_digits: str
    ) -> None:
        """For any r_digits and p_digits, parse_reference("r{r_digits}.p{p_digits}")
        also returns a result (not None) with the same properties.

        Feature: source-management, Property 10: Arkiv Digital census reference parsing
        **Validates: Requirements 7.3**
        """
        ref_string = f"r{r_digits}.p{p_digits}"
        result = parse_reference(ref_string)

        assert result is not None, (
            f"Expected parse_reference to return a ParsedReference for '{ref_string}', "
            f"got None"
        )
        assert result.leverantor_name == "Arkiv Digital", (
            f"Expected leverantor_name='Arkiv Digital' via parse_reference for "
            f"'{ref_string}', got '{result.leverantor_name}'"
        )
        assert result.kalltyp_name == "Folkräkning", (
            f"Expected kalltyp_name='Folkräkning' via parse_reference for "
            f"'{ref_string}', got '{result.kalltyp_name}'"
        )
        assert result.arkivreferens == ref_string, (
            f"Expected arkivreferens='{ref_string}' via parse_reference, "
            f"got '{result.arkivreferens}'"
        )
