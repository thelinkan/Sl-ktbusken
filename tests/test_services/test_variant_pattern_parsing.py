"""Example-based tests for variant pattern parsing of Arkiv Digital references.

Tests cover:
- Full pattern with C series (Födelse- och dopbok)
- Bild colon pattern with AIIa series (Församlingsbok)
- Title formatting for variant patterns
- GEDCOM import with ArkivDigital prefix and church book pattern

Validates: Requirements 15.1, 15.2, 15.3
"""

from __future__ import annotations

import pytest

from slaktbusken.gedcom.translation.models import GedcomSource
from slaktbusken.gedcom.translation.source_translation import (
    detect_arkiv_digital,
    map_gedcom_source,
    parse_church_book_citation,
)
from slaktbusken.parsing.reference_parser import (
    CHURCH_BOOK_SERIES_LABELS,
    parse_arkiv_digital,
    parse_reference,
)


class TestFullPatternCSeriesParsing:
    """Test existing full pattern still works with C series.

    Verifies that "Ed (S) C:6 (1861-1889) Bild 140 / sid 46 (AID: v5976.b140, NAD: SE/VA/13090)"
    is parsed as Arkiv Digital, Födelse- och dopbok.
    """

    REFERENCE = "Ed (S) C:6 (1861-1889) Bild 140 / sid 46 (AID: v5976.b140, NAD: SE/VA/13090)"

    def test_parses_as_arkiv_digital(self) -> None:
        result = parse_arkiv_digital(self.REFERENCE)
        assert result is not None
        assert result.leverantor_name == "Arkiv Digital"

    def test_c_series_maps_to_fodelse_och_dopbok(self) -> None:
        result = parse_arkiv_digital(self.REFERENCE)
        assert result is not None
        assert result.kalltyp_name == "Födelse- och dopbok"

    def test_title_is_formatted_correctly(self) -> None:
        result = parse_arkiv_digital(self.REFERENCE)
        assert result is not None
        assert result.title == "Ed C:6 Sida: 46"

    def test_structured_fields_are_extracted(self) -> None:
        result = parse_arkiv_digital(self.REFERENCE)
        assert result is not None
        assert result.structured_fields["parish"] == "Ed"
        assert result.structured_fields["county_code"] == "S"
        assert result.structured_fields["series"] == "C"
        assert result.structured_fields["volume"] == "6"
        assert result.structured_fields["years"] == "1861-1889"
        assert result.structured_fields["image"] == "140"
        assert result.structured_fields["page"] == "46"
        assert result.structured_fields["aid_ref"] == "v5976.b140"
        assert result.structured_fields["nad_ref"] == "SE/VA/13090"

    def test_parse_reference_also_matches(self) -> None:
        result = parse_reference(self.REFERENCE)
        assert result is not None
        assert result.leverantor_name == "Arkiv Digital"
        assert result.kalltyp_name == "Födelse- och dopbok"


class TestBildColonPatternAIIaSeries:
    """Test Bild colon pattern with AIIa series.

    Verifies that "Karlstads stadsförsamling (S) AIIa:7 (1906-1910) Bild: 350 Sida: 21"
    is parsed as Arkiv Digital, Församlingsbok.
    """

    REFERENCE = "Karlstads stadsförsamling (S) AIIa:7 (1906-1910) Bild: 350 Sida: 21"

    def test_parses_as_arkiv_digital(self) -> None:
        result = parse_arkiv_digital(self.REFERENCE)
        assert result is not None
        assert result.leverantor_name == "Arkiv Digital"

    def test_aiia_series_maps_to_forsamlingsbok(self) -> None:
        result = parse_arkiv_digital(self.REFERENCE)
        assert result is not None
        assert result.kalltyp_name == "Församlingsbok"

    def test_title_is_formatted_correctly(self) -> None:
        result = parse_arkiv_digital(self.REFERENCE)
        assert result is not None
        assert result.title == "Karlstads stadsförsamling AIIa:7 Sida: 21"

    def test_structured_fields_are_extracted(self) -> None:
        result = parse_arkiv_digital(self.REFERENCE)
        assert result is not None
        assert result.structured_fields["parish"] == "Karlstads stadsförsamling"
        assert result.structured_fields["county_code"] == "S"
        assert result.structured_fields["series"] == "AIIa"
        assert result.structured_fields["volume"] == "7"
        assert result.structured_fields["years"] == "1906-1910"
        assert result.structured_fields["image"] == "350"
        assert result.structured_fields["page"] == "21"

    def test_parse_reference_also_matches(self) -> None:
        result = parse_reference(self.REFERENCE)
        assert result is not None
        assert result.leverantor_name == "Arkiv Digital"
        assert result.kalltyp_name == "Församlingsbok"


class TestTitleFormattingForVariantPatterns:
    """Test title formatting produces correct output for variant patterns."""

    def test_bild_colon_pattern_title_format(self) -> None:
        """Title should be '{parish} {series}:{volume} Sida: {page}'."""
        ref = "Karlstads stadsförsamling (S) AIIa:7 (1906-1910) Bild: 350 Sida: 21"
        result = parse_arkiv_digital(ref)
        assert result is not None
        assert result.title == "Karlstads stadsförsamling AIIa:7 Sida: 21"

    def test_full_pattern_title_format(self) -> None:
        """Title from full pattern should use page from 'sid' part."""
        ref = "Ed (S) C:6 (1861-1889) Bild 140 / sid 46 (AID: v5976.b140, NAD: SE/VA/13090)"
        result = parse_arkiv_digital(ref)
        assert result is not None
        assert result.title == "Ed C:6 Sida: 46"

    def test_title_excludes_county_code_and_years(self) -> None:
        """Title should not include county code or year range."""
        ref = "Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915"
        result = parse_arkiv_digital(ref)
        assert result is not None
        assert "X" not in result.title or "Ljusdal" in result.title
        assert "1883-1887" not in result.title
        assert result.title == "Ljusdal AI:23d Sida: 915"


class TestGedcomImportWithArkivDigitalPrefix:
    """Test GEDCOM import with ArkivDigital prefix and church book pattern.

    Importing "ArkivDigital: Karlstads stadsförsamling (S) AIIa:7 (1906-1910) Bild: 350 Sida: 21"
    should produce a Source with correct title, reference_text, and provider_ref.
    """

    GEDCOM_TEXT = "ArkivDigital: Karlstads stadsförsamling (S) AIIa:7 (1906-1910) Bild: 350 Sida: 21"

    def test_detect_arkiv_digital_with_prefix(self) -> None:
        gs = GedcomSource(xref_id="@S99@", text=self.GEDCOM_TEXT)
        assert detect_arkiv_digital(gs) is True

    def test_source_title_is_formatted(self) -> None:
        gs = GedcomSource(xref_id="@S99@", text=self.GEDCOM_TEXT)
        source = map_gedcom_source(gs, [], [])
        assert source.title == "Karlstads stadsförsamling AIIa:7 Sida: 21"

    def test_reference_text_strips_prefix(self) -> None:
        gs = GedcomSource(xref_id="@S99@", text=self.GEDCOM_TEXT)
        source = map_gedcom_source(gs, [], [])
        expected_ref = "Karlstads stadsförsamling (S) AIIa:7 (1906-1910) Bild: 350 Sida: 21"
        assert source.reference_text == expected_ref

    def test_provider_ref_is_empty(self) -> None:
        gs = GedcomSource(xref_id="@S99@", text=self.GEDCOM_TEXT)
        source = map_gedcom_source(gs, [], [])
        assert source.provider_ref == ""

    def test_source_type_is_church_book(self) -> None:
        gs = GedcomSource(xref_id="@S99@", text=self.GEDCOM_TEXT)
        source = map_gedcom_source(gs, [], [])
        assert source.source_type == "church_book"

    def test_structured_reference_fields(self) -> None:
        gs = GedcomSource(xref_id="@S99@", text=self.GEDCOM_TEXT)
        source = map_gedcom_source(gs, [], [])
        fields = source.structured_reference.fields
        assert fields["parish"] == "Karlstads stadsförsamling"
        assert fields["county_code"] == "S"
        assert fields["series"] == "AIIa"
        assert fields["volume"] == "7"
        assert fields["years"] == "1906-1910"
        assert fields["image"] == 350
        assert fields["page"] == 21
