"""Property-based tests for source title formatting from structured reference.

Feature: source-management, Property 7: Source title formatting from structured reference

Validates: Requirements 5.1, 5.2, 5.3, 5.4
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from slaktbusken.services.source_formatting import format_source_title


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Non-empty, non-whitespace-only strings for field values (typical parish/series/volume/page)
_nonempty_field = st.text(
    min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))
).filter(lambda s: s.strip() != "")

# A field that is either present (non-empty) or absent (empty string)
_optional_field = st.one_of(st.just(""), _nonempty_field)


def _build_ref(parish: str, series: str, volume: str, page: str) -> dict:
    """Build a structured reference dict from field values.

    Empty strings represent absent/missing fields.
    """
    ref: dict = {}
    if parish:
        ref["parish"] = parish
    if series:
        ref["series"] = series
    if volume:
        ref["volume"] = volume
    if page:
        ref["page"] = page
    return ref


# ---------------------------------------------------------------------------
# Property 7: Source title formatting from structured reference
# ---------------------------------------------------------------------------


class TestSourceTitleFormattingProperty:
    """Feature: source-management, Property 7: Source title formatting from structured reference

    For any combination of parish, series, volume, and page values (each optionally
    empty), the title formatting function SHALL produce a title that: includes
    "{parish} {series}:{volume} Sida: {page}" when all are present; omits
    "Sida: {page}" when page is empty; omits any missing segment and its separator;
    and the final string has no leading/trailing whitespace and no consecutive spaces.

    **Validates: Requirements 5.1, 5.2, 5.3, 5.4**
    """

    @given(
        parish=_nonempty_field,
        series=_nonempty_field,
        volume=_nonempty_field,
        page=_nonempty_field,
    )
    @settings(max_examples=100, deadline=None)
    def test_all_fields_present_produces_full_format(
        self, parish: str, series: str, volume: str, page: str
    ) -> None:
        """When all fields are non-empty, result contains all segments in expected format.

        Feature: source-management, Property 7: Source title formatting from structured reference
        **Validates: Requirements 5.1**
        """
        ref = {"parish": parish, "series": series, "volume": volume, "page": page}
        result = format_source_title(ref)

        expected = f"{parish.strip()} {series.strip()}:{volume.strip()} Sida: {page.strip()}"
        assert result == expected, (
            f"Expected '{expected}', got '{result}' for ref={ref}"
        )

    @given(
        parish=_nonempty_field,
        series=_nonempty_field,
        volume=_nonempty_field,
    )
    @settings(max_examples=100, deadline=None)
    def test_empty_page_omits_sida(
        self, parish: str, series: str, volume: str
    ) -> None:
        """When page is empty, "Sida:" does not appear in result.

        Feature: source-management, Property 7: Source title formatting from structured reference
        **Validates: Requirements 5.2**
        """
        ref = {"parish": parish, "series": series, "volume": volume, "page": ""}
        result = format_source_title(ref)

        assert "Sida:" not in result, (
            f"'Sida:' should not appear when page is empty, got '{result}'"
        )

    @given(
        series=_optional_field,
        volume=_optional_field,
        page=_optional_field,
    )
    @settings(max_examples=100, deadline=None)
    def test_empty_parish_no_leading_space(
        self, series: str, volume: str, page: str
    ) -> None:
        """When parish is empty, result does not start with a space.

        Feature: source-management, Property 7: Source title formatting from structured reference
        **Validates: Requirements 5.3**
        """
        ref = {"parish": "", "series": series, "volume": volume, "page": page}
        result = format_source_title(ref)

        assert not result.startswith(" "), (
            f"Result should not start with space when parish is empty, got '{result}'"
        )

    @given(
        parish=_optional_field,
        series=_optional_field,
        volume=_optional_field,
        page=_optional_field,
    )
    @settings(max_examples=100, deadline=None)
    def test_no_leading_trailing_whitespace(
        self, parish: str, series: str, volume: str, page: str
    ) -> None:
        """Result never has leading/trailing whitespace.

        Feature: source-management, Property 7: Source title formatting from structured reference
        **Validates: Requirements 5.4**
        """
        ref = {"parish": parish, "series": series, "volume": volume, "page": page}
        result = format_source_title(ref)

        assert result == result.strip(), (
            f"Result has leading/trailing whitespace: '{result}'"
        )

    @given(
        parish=_optional_field,
        series=_optional_field,
        volume=_optional_field,
        page=_optional_field,
    )
    @settings(max_examples=100, deadline=None)
    def test_no_consecutive_spaces(
        self, parish: str, series: str, volume: str, page: str
    ) -> None:
        """Result never has consecutive spaces.

        Feature: source-management, Property 7: Source title formatting from structured reference
        **Validates: Requirements 5.4**
        """
        ref = {"parish": parish, "series": series, "volume": volume, "page": page}
        result = format_source_title(ref)

        assert "  " not in result, (
            f"Result contains consecutive spaces: '{result}'"
        )

    @settings(max_examples=1, deadline=None)
    @given(st.just(None))
    def test_all_fields_empty_returns_empty_string(self, _: None) -> None:
        """When all fields are empty, result is empty string.

        Feature: source-management, Property 7: Source title formatting from structured reference
        **Validates: Requirements 5.3**
        """
        ref = {"parish": "", "series": "", "volume": "", "page": ""}
        result = format_source_title(ref)

        assert result == "", f"Expected empty string when all fields empty, got '{result}'"

    @given(series=_nonempty_field)
    @settings(max_examples=100, deadline=None)
    def test_series_without_volume_no_colon(self, series: str) -> None:
        """When only series is present (no volume), result contains series without colon.

        Feature: source-management, Property 7: Source title formatting from structured reference
        **Validates: Requirements 5.3**
        """
        ref = {"parish": "", "series": series, "volume": "", "page": ""}
        result = format_source_title(ref)

        assert ":" not in result, (
            f"Colon should not appear when volume is empty, got '{result}'"
        )
        assert series.strip() in result, (
            f"Series '{series.strip()}' should be in result '{result}'"
        )
