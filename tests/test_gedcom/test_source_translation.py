"""Unit tests for GEDCOM source ID to structured Source mapping.

Validates: Requirements 4.4, 11.7, 14.1, 14.2
"""

from __future__ import annotations

import pytest

from slaktbusken.gedcom.translation.models import GedcomSource
from slaktbusken.gedcom.translation.source_translation import (
    detect_arkiv_digital,
    detect_source_type,
    find_matching_source,
    map_gedcom_source,
    parse_church_book_citation,
)
from slaktbusken.model.source import Kalltyp, Leverantor, Source, StructuredReference
from slaktbusken.persistence.translation_io import SourceMapping


# ---------------------------------------------------------------------------
# parse_church_book_citation tests
# ---------------------------------------------------------------------------


class TestParseChurchBookCitation:
    """Tests for parse_church_book_citation function."""

    def test_full_citation_with_page(self) -> None:
        """A complete citation with Bild and Sida is parsed correctly."""
        ref = parse_church_book_citation(
            "Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915"
        )
        assert ref is not None
        assert ref.fields["parish"] == "Ljusdal"
        assert ref.fields["county_code"] == "X"
        assert ref.fields["series"] == "AI"
        assert ref.fields["volume"] == "23d"
        assert ref.fields["years"] == "1883-1887"
        assert ref.fields["image"] == 23
        assert ref.fields["page"] == 915

    def test_citation_without_page(self) -> None:
        """A citation with only Bild (no Sida) is parsed with page=None."""
        ref = parse_church_book_citation(
            "Sundsvall (Y) FI:2 (1790-1800) Bild: 5"
        )
        assert ref is not None
        assert ref.fields["parish"] == "Sundsvall"
        assert ref.fields["county_code"] == "Y"
        assert ref.fields["series"] == "FI"
        assert ref.fields["volume"] == "2"
        assert ref.fields["years"] == "1790-1800"
        assert ref.fields["image"] == 5
        assert ref.fields["page"] is None

    def test_citation_with_multi_char_county(self) -> None:
        """A citation with a multi-character county code is parsed."""
        ref = parse_church_book_citation(
            "Stockholm (AB) CI:10 (1850-1860) Bild: 44 Sida: 100"
        )
        assert ref is not None
        assert ref.fields["parish"] == "Stockholm"
        assert ref.fields["county_code"] == "AB"

    def test_non_matching_text_returns_none(self) -> None:
        """Text that doesn't match the citation pattern returns None."""
        assert parse_church_book_citation("Just a random note") is None

    def test_empty_string_returns_none(self) -> None:
        """An empty string returns None."""
        assert parse_church_book_citation("") is None

    def test_partial_match_missing_bild_returns_none(self) -> None:
        """A string with parish and years but no Bild returns None."""
        assert parse_church_book_citation("Ljusdal (X) AI:23d (1883-1887)") is None

    def test_different_series_codes(self) -> None:
        """Various Swedish church book series codes are parsed correctly."""
        ref = parse_church_book_citation(
            "Mora (W) B:3 (1800-1820) Bild: 10 Sida: 25"
        )
        assert ref is not None
        assert ref.fields["series"] == "B"
        assert ref.fields["volume"] == "3"


# ---------------------------------------------------------------------------
# detect_source_type tests
# ---------------------------------------------------------------------------


class TestDetectSourceType:
    """Tests for detect_source_type function."""

    def test_church_book_from_text(self) -> None:
        """A source with church book citation pattern in text is detected."""
        gs = GedcomSource(
            xref_id="@S1@",
            text="Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915",
        )
        assert detect_source_type(gs) == "church_book"

    def test_church_book_from_title(self) -> None:
        """A source with church book citation in title is detected."""
        gs = GedcomSource(
            xref_id="@S1@",
            title="Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915",
        )
        assert detect_source_type(gs) == "church_book"

    def test_census_detection(self) -> None:
        """A source with census keyword is detected as census."""
        gs = GedcomSource(xref_id="@S2@", title="Folkräkning 1900")
        assert detect_source_type(gs) == "census"

    def test_death_notice_detection(self) -> None:
        """A source with death notice keyword is detected."""
        gs = GedcomSource(xref_id="@S3@", title="Dödsannons i DN 1945")
        assert detect_source_type(gs) == "death_notice"

    def test_newspaper_detection(self) -> None:
        """A source with newspaper keyword is detected."""
        gs = GedcomSource(xref_id="@S4@", title="Artikel i tidning")
        assert detect_source_type(gs) == "newspaper"

    def test_photograph_detection(self) -> None:
        """A source referencing a photograph is detected."""
        gs = GedcomSource(xref_id="@S5@", title="Fotografi av familjen")
        assert detect_source_type(gs) == "photograph"

    def test_database_detection(self) -> None:
        """A source referencing a database is detected."""
        gs = GedcomSource(xref_id="@S6@", title="Online databas")
        assert detect_source_type(gs) == "database"

    def test_other_fallback(self) -> None:
        """A source with no matching keywords falls back to 'other'."""
        gs = GedcomSource(xref_id="@S7@", title="Min forskning")
        assert detect_source_type(gs) == "other"

    def test_empty_source(self) -> None:
        """A source with no text content defaults to 'other'."""
        gs = GedcomSource(xref_id="@S8@")
        assert detect_source_type(gs) == "other"


# ---------------------------------------------------------------------------
# detect_arkiv_digital tests
# ---------------------------------------------------------------------------


class TestDetectArkivDigital:
    """Tests for detect_arkiv_digital function."""

    def test_text_prefix(self) -> None:
        """A source with 'ArkivDigital:' prefix in text is detected."""
        gs = GedcomSource(
            xref_id="@S1@",
            text="ArkivDigital: Ljusdal (X) AI:23d (1883-1887) Bild: 23",
        )
        assert detect_arkiv_digital(gs) is True

    def test_title_prefix(self) -> None:
        """A source with 'ArkivDigital:' prefix in title is detected."""
        gs = GedcomSource(xref_id="@S2@", title="ArkivDigital: Some source ref")
        assert detect_arkiv_digital(gs) is True

    def test_case_insensitive_prefix(self) -> None:
        """The ArkivDigital prefix check is case-insensitive."""
        gs = GedcomSource(xref_id="@S3@", text="arkivdigital: test")
        assert detect_arkiv_digital(gs) is True

    def test_structured_pattern_with_author(self) -> None:
        """A structured citation with ArkivDigital in author is detected."""
        gs = GedcomSource(
            xref_id="@S4@",
            text="Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915",
            author="ArkivDigital AB",
        )
        assert detect_arkiv_digital(gs) is True

    def test_structured_pattern_with_publication(self) -> None:
        """A structured citation with ArkivDigital in publication is detected."""
        gs = GedcomSource(
            xref_id="@S5@",
            text="Ljusdal (X) AI:23d (1883-1887) Bild: 23",
            publication="ArkivDigital Online",
        )
        assert detect_arkiv_digital(gs) is True

    def test_non_arkiv_digital_source(self) -> None:
        """A regular source without ArkivDigital markers is not detected."""
        gs = GedcomSource(xref_id="@S6@", title="My family tree")
        assert detect_arkiv_digital(gs) is False

    def test_structured_pattern_without_arkivdigital_metadata(self) -> None:
        """A church book citation without ArkivDigital in metadata is not detected."""
        gs = GedcomSource(
            xref_id="@S7@",
            text="Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915",
            author="Riksarkivet",
        )
        assert detect_arkiv_digital(gs) is False


# ---------------------------------------------------------------------------
# find_matching_source tests
# ---------------------------------------------------------------------------


class TestFindMatchingSource:
    """Tests for find_matching_source function."""

    def test_match_by_mapping(self) -> None:
        """A GEDCOM source with a known mapping returns the mapped ID."""
        mapping = SourceMapping(gedcom_id="@S1@", app_id="source_1", title="Test")
        source = Source(
            id="source_1", provider="", source_type="other", title="Test"
        )
        gs = GedcomSource(xref_id="@S1@", title="Test")
        assert find_matching_source(gs, [source], [mapping]) == "source_1"

    def test_match_by_title(self) -> None:
        """A GEDCOM source is matched by title when no mapping exists."""
        source = Source(
            id="source_2", provider="", source_type="other", title="Unique Title"
        )
        gs = GedcomSource(xref_id="@S99@", title="Unique Title")
        assert find_matching_source(gs, [source], []) == "source_2"

    def test_title_match_case_insensitive(self) -> None:
        """Title matching is case-insensitive."""
        source = Source(
            id="source_3", provider="", source_type="other", title="My Source"
        )
        gs = GedcomSource(xref_id="@S99@", title="my source")
        assert find_matching_source(gs, [source], []) == "source_3"

    def test_no_match_returns_none(self) -> None:
        """When no mapping or title matches, returns None."""
        source = Source(
            id="source_2", provider="", source_type="other", title="Existing"
        )
        gs = GedcomSource(xref_id="@S100@", title="No Match Here")
        assert find_matching_source(gs, [source], []) is None

    def test_mapping_to_deleted_source_returns_none(self) -> None:
        """A mapping to a non-existent source ID returns None."""
        mapping = SourceMapping(
            gedcom_id="@S1@", app_id="source_deleted", title="Gone"
        )
        gs = GedcomSource(xref_id="@S1@", title="Gone")
        assert find_matching_source(gs, [], [mapping]) is None

    def test_mapping_preferred_over_title(self) -> None:
        """Mapping match takes precedence over title match."""
        source_mapped = Source(
            id="source_1", provider="", source_type="other", title="Other Title"
        )
        source_titled = Source(
            id="source_2", provider="", source_type="other", title="Same Title"
        )
        mapping = SourceMapping(
            gedcom_id="@S1@", app_id="source_1", title="Same Title"
        )
        gs = GedcomSource(xref_id="@S1@", title="Same Title")
        result = find_matching_source(gs, [source_mapped, source_titled], [mapping])
        assert result == "source_1"


# ---------------------------------------------------------------------------
# map_gedcom_source tests
# ---------------------------------------------------------------------------


class TestMapGedcomSource:
    """Tests for map_gedcom_source function."""

    def test_new_church_book_source(self) -> None:
        """A new church book source is created with structured reference."""
        gs = GedcomSource(
            xref_id="@S10@",
            title="Ljusdal husförhör",
            text="Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915",
        )
        result = map_gedcom_source(gs, [], [])
        assert result.source_type == "church_book"
        assert result.structured_reference.fields["parish"] == "Ljusdal"
        assert result.structured_reference.fields["county_code"] == "X"
        assert result.structured_reference.fields["series"] == "AI"
        assert result.structured_reference.fields["volume"] == "23d"
        assert result.structured_reference.fields["years"] == "1883-1887"
        assert result.structured_reference.fields["image"] == 23
        assert result.structured_reference.fields["page"] == 915
        assert result.id.startswith("source_")

    def test_new_source_gets_unique_id(self) -> None:
        """A new source is assigned a unique ID that doesn't clash with existing."""
        existing = Source(
            id="source_1", provider="", source_type="other", title="Existing"
        )
        gs = GedcomSource(xref_id="@S99@", title="Brand New Source")
        result = map_gedcom_source(gs, [existing], [])
        assert result.id != "source_1"
        assert result.id.startswith("source_")

    def test_existing_source_returned(self) -> None:
        """An existing matched source is returned without creating a new one."""
        existing = Source(
            id="source_5",
            provider="ArkivDigital",
            source_type="church_book",
            title="Ljusdal AI",
        )
        mapping = SourceMapping(
            gedcom_id="@S20@", app_id="source_5", title="Ljusdal AI"
        )
        gs = GedcomSource(xref_id="@S20@", title="Ljusdal AI")
        result = map_gedcom_source(gs, [existing], [mapping])
        assert result.id == "source_5"

    def test_arkivdigital_provider_set(self) -> None:
        """ArkivDigital sources get provider='ArkivDigital'."""
        gs = GedcomSource(
            xref_id="@S30@",
            title="Some Church",
            text="ArkivDigital: Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915",
        )
        result = map_gedcom_source(gs, [], [])
        assert result.provider == "ArkivDigital"

    def test_arkivdigital_strips_prefix_in_reference_text(self) -> None:
        """ArkivDigital prefix is stripped from reference_text."""
        gs = GedcomSource(
            xref_id="@S31@",
            title="Source",
            text="ArkivDigital: Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915",
        )
        result = map_gedcom_source(gs, [], [])
        assert not result.reference_text.lower().startswith("arkivdigital:")
        assert "Ljusdal" in result.reference_text

    def test_notes_preserved(self) -> None:
        """GEDCOM source notes are preserved in free_note."""
        gs = GedcomSource(
            xref_id="@S40@", title="Test", notes="Important research note"
        )
        result = map_gedcom_source(gs, [], [])
        assert result.free_note == "Important research note"

    def test_abbreviation_used_as_provider_ref(self) -> None:
        """GEDCOM abbreviation is mapped to provider_ref."""
        gs = GedcomSource(
            xref_id="@S41@", title="Test", abbreviation="v136004.b88"
        )
        result = map_gedcom_source(gs, [], [])
        assert result.provider_ref == "v136004.b88"

    def test_title_fallback_to_abbreviation(self) -> None:
        """When title is empty, abbreviation is used as title."""
        gs = GedcomSource(xref_id="@S42@", abbreviation="Short Name")
        result = map_gedcom_source(gs, [], [])
        assert result.title == "Short Name"

    def test_title_fallback_to_text(self) -> None:
        """When title and abbreviation are empty, text is used as title."""
        gs = GedcomSource(xref_id="@S43@", text="Some descriptive text")
        result = map_gedcom_source(gs, [], [])
        assert result.title == "Some descriptive text"

    def test_author_used_as_provider(self) -> None:
        """Non-ArkivDigital sources use author as provider."""
        gs = GedcomSource(
            xref_id="@S50@", title="A source", author="Riksarkivet"
        )
        result = map_gedcom_source(gs, [], [])
        assert result.provider == "Riksarkivet"

    def test_arkivdigital_church_book_title_formatted(self) -> None:
        """ArkivDigital church_book sources get title from format_source_title."""
        gs = GedcomSource(
            xref_id="@S60@",
            title="ArkivDigital: Karlstads stadsförsamling",
            text="ArkivDigital: Karlstads stadsförsamling (S) AIIa:7 (1870-1880) Bild: 50 Sida: 21",
        )
        result = map_gedcom_source(gs, [], [])
        # Title should be formatted from structured reference fields
        assert result.title == "Karlstads stadsförsamling AIIa:7 Sida: 21"
        # reference_text should be the full original text with prefix stripped
        assert result.reference_text == "Karlstads stadsförsamling (S) AIIa:7 (1870-1880) Bild: 50 Sida: 21"
        # provider_ref should be empty (not the abbreviation)
        assert result.provider_ref == ""

    def test_arkivdigital_church_book_provider_ref_empty(self) -> None:
        """ArkivDigital church_book sources have provider_ref set to empty string."""
        gs = GedcomSource(
            xref_id="@S61@",
            title="Some title",
            text="ArkivDigital: Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915",
            abbreviation="v136004.b88",
        )
        result = map_gedcom_source(gs, [], [])
        # Even though abbreviation is set, provider_ref should be empty for ArkivDigital
        assert result.provider_ref == ""


# ---------------------------------------------------------------------------
# SDB detection in GEDCOM import tests
# ---------------------------------------------------------------------------


def _make_sdb_providers() -> tuple[list[Leverantor], list[Kalltyp]]:
    """Helper to create standard leverantorer/kalltyper for SDB testing."""
    lev = Leverantor(id="lev_rotter", name="Rötter.se")
    kt = Kalltyp(
        id="kt_sdb_webb",
        leverantor_id="lev_rotter",
        name="Sveriges Dödbok Webb",
        root_url="https://www.rotter.se/abonnemang/sveriges-dodbok-webb/post/",
    )
    return [lev], [kt]


class TestSdbDetection:
    """Tests for SDB pattern detection in GEDCOM import.

    Validates: Requirements 14.1, 14.2
    """

    def test_sdb_pattern_in_text_assigns_leverantor_and_kalltyp(self) -> None:
        """A GEDCOM source with 'SDB7_12345' in text gets leverantor_id and kalltyp_id."""
        leverantorer, kalltyper = _make_sdb_providers()
        gs = GedcomSource(xref_id="@S100@", title="Dödbok", text="SDB7_12345")
        result = map_gedcom_source(gs, [], [], leverantorer=leverantorer, kalltyper=kalltyper)
        assert result.leverantor_id == "lev_rotter"
        assert result.kalltyp_id == "kt_sdb_webb"

    def test_sdb_pattern_extracts_arkivreferens(self) -> None:
        """The SDB identifier 'SDB7_12345' is stored as arkivreferens."""
        leverantorer, kalltyper = _make_sdb_providers()
        gs = GedcomSource(xref_id="@S101@", title="Dödbok", text="SDB7_12345")
        result = map_gedcom_source(gs, [], [], leverantorer=leverantorer, kalltyper=kalltyper)
        assert result.arkivreferens == "SDB7_12345"

    def test_sveriges_dodbok_webb_text_assigns_leverantor_and_kalltyp(self) -> None:
        """A GEDCOM source with 'Sveriges dödbok webb' in text is correctly recognized."""
        leverantorer, kalltyper = _make_sdb_providers()
        gs = GedcomSource(
            xref_id="@S102@",
            title="Dödspost",
            text="Sveriges dödbok webb - record123",
        )
        result = map_gedcom_source(gs, [], [], leverantorer=leverantorer, kalltyper=kalltyper)
        assert result.leverantor_id == "lev_rotter"
        assert result.kalltyp_id == "kt_sdb_webb"

    def test_sdb_detection_without_leverantorer_graceful(self) -> None:
        """When no leverantorer/kalltyper are provided, source is still created without IDs."""
        gs = GedcomSource(xref_id="@S103@", title="Dödbok", text="SDB7_12345")
        result = map_gedcom_source(gs, [], [])
        # Source is created but without leverantor_id/kalltyp_id set
        assert result.leverantor_id == ""
        assert result.kalltyp_id == ""
        # arkivreferens is still extracted
        assert result.arkivreferens == "SDB7_12345"

    def test_non_sdb_source_not_affected(self) -> None:
        """A normal source without SDB patterns doesn't get leverantor_id/kalltyp_id set."""
        leverantorer, kalltyper = _make_sdb_providers()
        gs = GedcomSource(xref_id="@S104@", title="Min forskning", text="Some notes")
        result = map_gedcom_source(gs, [], [], leverantorer=leverantorer, kalltyper=kalltyper)
        assert result.leverantor_id == ""
        assert result.kalltyp_id == ""
        assert result.arkivreferens == ""
