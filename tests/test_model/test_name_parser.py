"""Property-based tests for the name_parser module.

Tests Properties 1–6 from the primary-name-asterisk design document.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.6, 1.7, 5.4, 5.5
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from hypothesis.strategies import DrawFn

from slaktbusken.model.name_parser import (
    ParsedGivenName,
    format_given_name,
    parse_given_name,
    validate_given_name_markers,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Characters valid for Swedish name parts (letters incl. Swedish chars, hyphens)
_swedish_name_chars = st.sampled_from(
    list("abcdefghijklmnopqrstuvwxyzåäöABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ-")
)

_name_part = st.text(alphabet=_swedish_name_chars, min_size=1, max_size=12)


@st.composite
def valid_given_name_with_marker(draw: DrawFn) -> str:
    """Generate a given-name string with exactly one trailing * marker.

    Produces 1–5 name parts (letters + common Swedish characters),
    then places a trailing * on one random part.
    """
    num_parts = draw(st.integers(min_value=1, max_value=5))
    parts = [draw(_name_part) for _ in range(num_parts)]
    # Ensure no part already ends with *
    parts = [p.rstrip("*") for p in parts]
    # Ensure all parts are non-empty after stripping
    parts = [p if p else "A" for p in parts]
    marker_index = draw(st.integers(min_value=0, max_value=num_parts - 1))
    parts[marker_index] = parts[marker_index] + "*"
    return " ".join(parts)


@st.composite
def valid_given_name_without_marker(draw: DrawFn) -> str:
    """Generate a given-name string with no trailing * on any part."""
    num_parts = draw(st.integers(min_value=1, max_value=5))
    parts = [draw(_name_part) for _ in range(num_parts)]
    # Ensure no part ends with * (strip any trailing *)
    parts = [p.rstrip("*") for p in parts]
    parts = [p if p else "A" for p in parts]
    return " ".join(parts)


@st.composite
def given_name_with_embedded_asterisks(draw: DrawFn) -> str:
    """Generate name parts where * appears mid-part (e.g., "O*Brien").

    The * is never at the trailing position of any part.
    """
    num_parts = draw(st.integers(min_value=1, max_value=5))
    parts: list[str] = []
    for _ in range(num_parts):
        # Build a part with an embedded * (not trailing)
        prefix = draw(st.text(alphabet=_swedish_name_chars, min_size=1, max_size=5))
        suffix = draw(st.text(alphabet=_swedish_name_chars, min_size=1, max_size=5))
        part = prefix + "*" + suffix
        parts.append(part)
    return " ".join(parts)


@st.composite
def given_name_with_multiple_markers(draw: DrawFn) -> str:
    """Generate a given-name string with 2+ parts ending in *."""
    num_parts = draw(st.integers(min_value=2, max_value=5))
    parts = [draw(_name_part) for _ in range(num_parts)]
    # Strip trailing * to control placement
    parts = [p.rstrip("*") for p in parts]
    parts = [p if p else "A" for p in parts]
    # Pick at least 2 distinct indices to mark
    num_markers = draw(st.integers(min_value=2, max_value=num_parts))
    indices = draw(
        st.lists(
            st.integers(min_value=0, max_value=num_parts - 1),
            min_size=num_markers,
            max_size=num_markers,
            unique=True,
        )
    )
    for idx in indices:
        parts[idx] = parts[idx] + "*"
    return " ".join(parts)


@st.composite
def malformed_marker_string(draw: DrawFn) -> str:
    """Generate strings with standalone *, leading *, or whitespace-preceded *.

    These represent invalid marker placements that should be rejected.
    """
    variant = draw(st.integers(min_value=0, max_value=2))
    base_parts = [draw(_name_part) for _ in range(draw(st.integers(min_value=1, max_value=3)))]
    # Ensure base parts don't end with *
    base_parts = [p.rstrip("*") for p in base_parts]
    base_parts = [p if p else "A" for p in base_parts]

    if variant == 0:
        # Standalone * as a token
        insert_pos = draw(st.integers(min_value=0, max_value=len(base_parts)))
        base_parts.insert(insert_pos, "*")
    elif variant == 1:
        # Leading * on a name part (e.g., "*Anna")
        target = draw(st.integers(min_value=0, max_value=len(base_parts) - 1))
        base_parts[target] = "*" + base_parts[target]
    else:
        # Standalone * (different position pattern)
        base_parts.append("*")

    return " ".join(base_parts)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


class TestProperty1CorrectTilltalsnamn:
    """Property 1: Correct Tilltalsnamn Identification.

    For any given-name string containing multiple whitespace-separated name parts
    with exactly one part ending in *, parse_given_name SHALL return that part
    (without the asterisk) as the tilltalsnamn and its correct zero-based index
    in the parts list.

    Validates: Requirements 1.1, 1.3
    """

    @given(name_str=valid_given_name_with_marker())
    @settings(max_examples=200)
    def test_correct_tilltalsnamn_identification(self, name_str: str) -> None:
        """**Validates: Requirements 1.1, 1.3**"""
        result = parse_given_name(name_str)

        # Determine expected marker index from the raw input
        raw_parts = name_str.split()
        expected_index = None
        expected_name = None
        for i, part in enumerate(raw_parts):
            if part.endswith("*"):
                expected_index = i
                expected_name = part[:-1]
                break

        assert result.tilltalsnamn_index == expected_index
        assert result.parts[expected_index] == expected_name
        # All parts should have asterisk stripped
        assert all("*" not in p or not p.endswith("*") for p in result.parts)


class TestProperty2NoMarkerReturnsNone:
    """Property 2: No-Marker Returns None.

    For any given-name string containing no * character at the end of any name part,
    parse_given_name SHALL return a result with tilltalsnamn_index equal to None
    and parts equal to the whitespace-split name parts.

    Validates: Requirements 1.2
    """

    @given(name_str=valid_given_name_without_marker())
    @settings(max_examples=200)
    def test_no_marker_returns_none(self, name_str: str) -> None:
        """**Validates: Requirements 1.2**"""
        result = parse_given_name(name_str)

        assert result.tilltalsnamn_index is None
        assert result.parts == name_str.split()


class TestProperty3EmbeddedAsterisksAreLiteral:
    """Property 3: Embedded Asterisks Are Literal.

    For any given-name string where * characters appear only within name parts
    (not at the trailing position of any part), parse_given_name SHALL treat them
    as literal characters, returning tilltalsnamn_index as None and preserving
    the * characters within the parts.

    Validates: Requirements 1.4
    """

    @given(name_str=given_name_with_embedded_asterisks())
    @settings(max_examples=200)
    def test_embedded_asterisks_are_literal(self, name_str: str) -> None:
        """**Validates: Requirements 1.4**"""
        result = parse_given_name(name_str)

        # Embedded * should not trigger marker detection
        assert result.tilltalsnamn_index is None
        # Parts should preserve the * characters
        assert result.parts == name_str.split()
        # Verify * is actually present in some parts
        assert any("*" in part for part in result.parts)


class TestProperty4ParseFormatRoundTrip:
    """Property 4: Parse-Format Round Trip.

    For any valid given-name string containing zero or one asterisk marker,
    parsing with parse_given_name then formatting with format_given_name SHALL
    produce a string equal to the original input.

    Validates: Requirements 1.6
    """

    @given(name_str=valid_given_name_with_marker())
    @settings(max_examples=200)
    def test_round_trip_with_marker(self, name_str: str) -> None:
        """**Validates: Requirements 1.6**"""
        parsed = parse_given_name(name_str)
        reconstructed = format_given_name(parsed)
        assert reconstructed == name_str

    @given(name_str=valid_given_name_without_marker())
    @settings(max_examples=200)
    def test_round_trip_without_marker(self, name_str: str) -> None:
        """**Validates: Requirements 1.6**"""
        parsed = parse_given_name(name_str)
        reconstructed = format_given_name(parsed)
        assert reconstructed == name_str


class TestProperty5MultipleMarkersRejected:
    """Property 5: Multiple Markers Rejected.

    For any given-name string containing two or more name parts each ending in *,
    parse_given_name SHALL raise a ValueError.

    Validates: Requirements 1.7, 5.4
    """

    @given(name_str=given_name_with_multiple_markers())
    @settings(max_examples=200)
    def test_multiple_markers_raises_value_error(self, name_str: str) -> None:
        """**Validates: Requirements 1.7, 5.4**"""
        with pytest.raises(ValueError):
            parse_given_name(name_str)


class TestProperty6MalformedMarkersRejected:
    """Property 6: Malformed Markers Rejected.

    For any given-name string where * appears as a standalone token, a leading
    character, or is preceded by whitespace, validate_given_name_markers SHALL
    return a non-empty error list.

    Validates: Requirements 5.5
    """

    @given(name_str=malformed_marker_string())
    @settings(max_examples=200)
    def test_malformed_markers_return_errors(self, name_str: str) -> None:
        """**Validates: Requirements 5.5**"""
        errors = validate_given_name_markers(name_str)
        assert len(errors) > 0, (
            f"Expected validation errors for malformed input: {name_str!r}"
        )
