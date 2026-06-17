"""Example-based unit tests for the name_parser module.

Complements the property-based tests with specific, readable examples
that document expected behaviour for common and edge-case inputs.

Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.7
"""

from __future__ import annotations

import pytest

from slaktbusken.model.name_parser import (
    ParsedGivenName,
    parse_given_name,
)


class TestMarkedName:
    """Examples where a tilltalsnamn marker is present.

    Validates: Requirements 1.1, 1.3, 1.5
    """

    def test_kent_torbjorn_marked(self) -> None:
        """'Kent Torbjörn*' → tilltalsnamn='Torbjörn', index=1.

        Validates: Requirements 1.1, 1.3
        """
        result = parse_given_name("Kent Torbjörn*")

        assert result.parts == ["Kent", "Torbjörn"]
        assert result.tilltalsnamn_index == 1
        assert result.display_string == "Kent Torbjörn"
        assert result.raw == "Kent Torbjörn*"

    def test_anna_marked(self) -> None:
        """'Anna*' → tilltalsnamn='Anna', index=0.

        Validates: Requirements 1.1, 1.3
        """
        result = parse_given_name("Anna*")

        assert result.parts == ["Anna"]
        assert result.tilltalsnamn_index == 0
        assert result.display_string == "Anna"
        assert result.raw == "Anna*"

    def test_display_string_never_contains_asterisk(self) -> None:
        """The display_string should never contain trailing asterisks.

        Validates: Requirements 1.5
        """
        result = parse_given_name("Kent Torbjörn*")

        assert "*" not in result.display_string


class TestNoMarker:
    """Examples where no tilltalsnamn marker is present.

    Validates: Requirements 1.2
    """

    def test_erik_johan_no_marker(self) -> None:
        """'Erik Johan' → tilltalsnamn=None, parts preserved.

        Validates: Requirements 1.2
        """
        result = parse_given_name("Erik Johan")

        assert result.parts == ["Erik", "Johan"]
        assert result.tilltalsnamn_index is None
        assert result.display_string == "Erik Johan"
        assert result.raw == "Erik Johan"


class TestEmptyInput:
    """Examples for empty or whitespace-only input.

    Validates: Requirements 1.2
    """

    def test_empty_string(self) -> None:
        """Empty string → empty parts, None index.

        Validates: Requirements 1.2
        """
        result = parse_given_name("")

        assert result.parts == []
        assert result.tilltalsnamn_index is None
        assert result.display_string == ""
        assert result.raw == ""


class TestMultipleMarkers:
    """Examples where multiple markers should be rejected.

    Validates: Requirements 1.7
    """

    def test_multiple_markers_raises(self) -> None:
        """'Karl* Erik*' → raises ValueError.

        Validates: Requirements 1.7
        """
        with pytest.raises(ValueError, match="Only one tilltalsnamn marker"):
            parse_given_name("Karl* Erik*")


class TestEmbeddedAsterisks:
    """Examples where * appears mid-part and should be treated as literal.

    Validates: Requirements 1.4
    """

    def test_obrien_embedded_asterisk(self) -> None:
        """'O*Brien' should be treated as literal (not a marker).

        Validates: Requirements 1.4
        """
        result = parse_given_name("O*Brien")

        assert result.parts == ["O*Brien"]
        assert result.tilltalsnamn_index is None
        assert result.display_string == "O*Brien"
        assert result.raw == "O*Brien"
