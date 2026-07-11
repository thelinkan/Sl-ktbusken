"""Unit tests for source title formatting.

Tests format_source_title from the source_formatting module.
"""

from __future__ import annotations

from slaktbusken.services.source_formatting import format_source_title


class TestFormatSourceTitle:
    """Tests for format_source_title."""

    # --- Full combinations ---

    def test_all_fields_present(self) -> None:
        ref = {"parish": "Ljusdal", "series": "AI", "volume": "17", "page": "32"}
        assert format_source_title(ref) == "Ljusdal AI:17 Sida: 32"

    def test_all_fields_empty_page(self) -> None:
        ref = {"parish": "Ljusdal", "series": "AI", "volume": "17", "page": ""}
        assert format_source_title(ref) == "Ljusdal AI:17"

    def test_all_fields_missing_page(self) -> None:
        ref = {"parish": "Ljusdal", "series": "AI", "volume": "17"}
        assert format_source_title(ref) == "Ljusdal AI:17"

    def test_missing_parish(self) -> None:
        ref = {"series": "AI", "volume": "17", "page": "32"}
        assert format_source_title(ref) == "AI:17 Sida: 32"

    def test_empty_parish(self) -> None:
        ref = {"parish": "", "series": "AI", "volume": "17", "page": "32"}
        assert format_source_title(ref) == "AI:17 Sida: 32"

    # --- Series/volume partial ---

    def test_series_only_no_volume(self) -> None:
        ref = {"parish": "Ljusdal", "series": "AI", "page": "32"}
        assert format_source_title(ref) == "Ljusdal AI Sida: 32"

    def test_volume_only_no_series(self) -> None:
        ref = {"parish": "Ljusdal", "volume": "17", "page": "32"}
        assert format_source_title(ref) == "Ljusdal Sida: 32"

    def test_series_empty_volume_present(self) -> None:
        ref = {"parish": "Ljusdal", "series": "", "volume": "17", "page": "32"}
        assert format_source_title(ref) == "Ljusdal Sida: 32"

    def test_series_present_volume_empty(self) -> None:
        ref = {"parish": "Ljusdal", "series": "AI", "volume": "", "page": "32"}
        assert format_source_title(ref) == "Ljusdal AI Sida: 32"

    # --- Empty / minimal ---

    def test_empty_dict(self) -> None:
        assert format_source_title({}) == ""

    def test_all_empty_strings(self) -> None:
        ref = {"parish": "", "series": "", "volume": "", "page": ""}
        assert format_source_title(ref) == ""

    def test_only_page(self) -> None:
        ref = {"page": "32"}
        assert format_source_title(ref) == "Sida: 32"

    def test_only_parish(self) -> None:
        ref = {"parish": "Ljusdal"}
        assert format_source_title(ref) == "Ljusdal"

    # --- Whitespace handling ---

    def test_whitespace_in_values_trimmed(self) -> None:
        ref = {"parish": "  Ljusdal  ", "series": " AI ", "volume": " 17 ", "page": " 32 "}
        assert format_source_title(ref) == "Ljusdal AI:17 Sida: 32"

    def test_whitespace_only_values_treated_as_empty(self) -> None:
        ref = {"parish": "   ", "series": "AI", "volume": "17"}
        assert format_source_title(ref) == "AI:17"

    def test_no_leading_trailing_whitespace_in_result(self) -> None:
        ref = {"parish": "Ljusdal", "series": "AI", "volume": "17", "page": "32"}
        result = format_source_title(ref)
        assert result == result.strip()

    def test_no_consecutive_spaces_in_result(self) -> None:
        ref = {"parish": "Ljusdal", "series": "AI", "volume": "17", "page": "32"}
        result = format_source_title(ref)
        assert "  " not in result

    # --- Swedish characters ---

    def test_swedish_characters_in_parish(self) -> None:
        ref = {"parish": "Ångermanland", "series": "AI", "volume": "5", "page": "10"}
        assert format_source_title(ref) == "Ångermanland AI:5 Sida: 10"
