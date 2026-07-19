"""Property-based tests for Arkiv Digital reference parsing.

Feature: source-management, Property 9: Arkiv Digital church book reference parsing round-trip

Validates: Requirements 7.1, 7.2
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from slaktbusken.parsing.reference_parser import (
    CHURCH_BOOK_SERIES_LABELS,
    ParsedReference,
    parse_arkiv_digital,
    parse_reference,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Parish names: non-empty text without parentheses that doesn't look like a year
# Must not end with whitespace (since parser strips), and must not contain
# characters that would break the regex pattern.
parish_strategy = (
    st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "Zs"),
            whitelist_characters="-",
        ),
        min_size=1,
        max_size=30,
    )
    .map(lambda s: s.strip())
    .filter(lambda s: len(s) > 0)
)

# County codes: short uppercase letters
county_code_strategy = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    min_size=1,
    max_size=3,
)

# Series: from known CHURCH_BOOK_SERIES_LABELS keys
series_strategy = st.sampled_from(list(CHURCH_BOOK_SERIES_LABELS.keys()))

# Volume: positive integers as strings
volume_strategy = st.integers(min_value=1, max_value=999).map(str)

# Years: year ranges like "1780-1820"
years_strategy = st.tuples(
    st.integers(1600, 1900), st.integers(0, 50)
).map(lambda t: f"{t[0]}-{t[0] + t[1]}")

# Image number
image_strategy = st.integers(min_value=1, max_value=9999).map(str)

# Page number
page_strategy = st.integers(min_value=1, max_value=9999).map(str)

# AID reference: alphanumeric, no commas or parentheses
aid_ref_strategy = (
    st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
        min_size=1,
        max_size=20,
    )
    .filter(lambda s: s.strip() and "," not in s and ")" not in s)
)

# NAD reference: alphanumeric, no parentheses
nad_ref_strategy = (
    st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz0123456789",
        min_size=1,
        max_size=20,
    )
    .filter(lambda s: s.strip() and ")" not in s)
)

# Description for short pattern: non-empty, no parentheses
# Must not end with a 4-digit year pattern (to avoid ambiguity)
description_strategy = (
    st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "Zs"),
            whitelist_characters="-",
        ),
        min_size=1,
        max_size=30,
    )
    .map(lambda s: s.strip())
    .filter(lambda s: len(s) > 0)
)

# Year for short pattern: 4-digit year
year_strategy = st.integers(min_value=1600, max_value=2023).map(str)


# ---------------------------------------------------------------------------
# Property 9: Arkiv Digital church book reference parsing round-trip
# ---------------------------------------------------------------------------


class TestArkivDigitalChurchBookRoundTrip:
    """Property 9: Arkiv Digital church book reference parsing round-trip.

    **Validates: Requirements 7.1, 7.2**

    For any valid parish name, county code, series, volume, years range,
    image number, page number, AID reference, and optional NAD reference,
    formatting them into the Arkiv Digital pattern and then parsing the result
    SHALL extract the same field values, set leverantor_name to "Arkiv Digital",
    derive källtyp_name from the series via CHURCH_BOOK_SERIES_LABELS, and set
    the title to "{parish} {series}:{volume} Sida: {page}".
    """

    @given(
        parish=parish_strategy,
        county_code=county_code_strategy,
        series=series_strategy,
        volume=volume_strategy,
        years=years_strategy,
        image=image_strategy,
        page=page_strategy,
        aid_ref=aid_ref_strategy,
        nad_ref=nad_ref_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_full_pattern_round_trip(
        self,
        parish: str,
        county_code: str,
        series: str,
        volume: str,
        years: str,
        image: str,
        page: str,
        aid_ref: str,
        nad_ref: str,
    ) -> None:
        """Full pattern formatted string parses back to original fields."""
        # Format the full Arkiv Digital reference string
        reference = (
            f"{parish} ({county_code}) {series}:{volume} ({years}) "
            f"Bild {image} / sid {page} (AID: {aid_ref}, NAD: {nad_ref})"
        )

        # Parse it
        result = parse_arkiv_digital(reference)

        # Round-trip assertions
        assert result is not None, f"Failed to parse: {reference}"
        assert result.leverantor_name == "Arkiv Digital"
        assert result.kalltyp_name == CHURCH_BOOK_SERIES_LABELS[series]
        assert result.title == f"{parish} {series}:{volume} Sida: {page}"
        # reference_text should be normalized to colon format without AID/NAD (requirement 2.4)
        expected_ref_text = (
            f"{parish} ({county_code}) {series}:{volume} ({years}) "
            f"Bild: {image} Sida: {page}"
        )
        assert result.reference_text == expected_ref_text
        assert "(AID:" not in result.reference_text
        assert result.structured_fields["parish"] == parish
        assert result.structured_fields["county_code"] == county_code
        assert result.structured_fields["series"] == series
        assert result.structured_fields["volume"] == volume
        assert result.structured_fields["years"] == years
        assert result.structured_fields["image"] == image
        assert result.structured_fields["page"] == page
        assert result.structured_fields["aid_ref"] == aid_ref
        assert result.structured_fields["nad_ref"] == nad_ref

    @given(
        description=description_strategy,
        year=year_strategy,
        image=image_strategy,
        page=page_strategy,
        aid_ref=aid_ref_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_short_pattern_round_trip(
        self,
        description: str,
        year: str,
        image: str,
        page: str,
        aid_ref: str,
    ) -> None:
        """Short pattern formatted string parses back to original fields."""
        # Format the short Arkiv Digital reference string
        reference = (
            f"{description} ({year}) Bild {image} / sid {page} (AID: {aid_ref})"
        )

        # Parse it
        result = parse_arkiv_digital(reference)

        # Round-trip assertions
        assert result is not None, f"Failed to parse: {reference}"
        assert result.leverantor_name == "Arkiv Digital"
        assert result.kalltyp_name == "Övrigt"
        assert result.title == f"{description} Sida: {page}"
        # reference_text should be normalized to colon format without AID (requirement 2.4)
        expected_ref_text = (
            f"{description} ({year}) Bild: {image} Sida: {page}"
        )
        assert result.reference_text == expected_ref_text
        assert "(AID:" not in result.reference_text
        assert result.structured_fields["description"] == description
        assert result.structured_fields["year"] == year
        assert result.structured_fields["image"] == image
        assert result.structured_fields["page"] == page
        assert result.structured_fields["aid_ref"] == aid_ref
