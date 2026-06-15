"""Unit tests for citation text building from structured source references.

Validates: Requirements 5.4, 5.5
"""

from __future__ import annotations

from slaktbusken.gedcom.translation.citation_translation import (
    build_church_book_citation,
    build_citation_text,
    build_database_citation,
    build_death_notice_citation,
    build_generic_citation,
    build_newspaper_citation,
)
from slaktbusken.model.source import Source, StructuredReference


# ---------------------------------------------------------------------------
# build_church_book_citation tests
# ---------------------------------------------------------------------------


class TestBuildChurchBookCitation:
    """Tests for build_church_book_citation function."""

    def test_full_citation(self) -> None:
        """All fields present produces the canonical citation format."""
        ref = StructuredReference(
            fields={
                "parish": "Ljusdal",
                "county_code": "X",
                "series": "AI",
                "volume": "23d",
                "years": "1883-1887",
                "image": 23,
                "page": 915,
            }
        )
        result = build_church_book_citation(ref)
        assert result == "Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915"

    def test_missing_county_code(self) -> None:
        """Parish without county code omits parenthetical."""
        ref = StructuredReference(
            fields={
                "parish": "Ljusdal",
                "series": "AI",
                "volume": "23d",
                "years": "1883-1887",
                "image": 23,
                "page": 915,
            }
        )
        result = build_church_book_citation(ref)
        assert result == "Ljusdal AI:23d (1883-1887) Bild: 23 Sida: 915"

    def test_missing_volume(self) -> None:
        """Series without volume omits the colon separator."""
        ref = StructuredReference(
            fields={
                "parish": "Ljusdal",
                "county_code": "X",
                "series": "AI",
                "years": "1883-1887",
                "image": 23,
                "page": 915,
            }
        )
        result = build_church_book_citation(ref)
        assert result == "Ljusdal (X) AI (1883-1887) Bild: 23 Sida: 915"

    def test_missing_series(self) -> None:
        """Volume without series shows just the volume."""
        ref = StructuredReference(
            fields={
                "parish": "Ljusdal",
                "county_code": "X",
                "volume": "23d",
                "years": "1883-1887",
                "image": 23,
                "page": 915,
            }
        )
        result = build_church_book_citation(ref)
        assert result == "Ljusdal (X) 23d (1883-1887) Bild: 23 Sida: 915"

    def test_missing_years(self) -> None:
        """Citation without years omits the year parenthetical."""
        ref = StructuredReference(
            fields={
                "parish": "Ljusdal",
                "county_code": "X",
                "series": "AI",
                "volume": "23d",
                "image": 23,
                "page": 915,
            }
        )
        result = build_church_book_citation(ref)
        assert result == "Ljusdal (X) AI:23d Bild: 23 Sida: 915"

    def test_missing_image(self) -> None:
        """Citation without image omits Bild part."""
        ref = StructuredReference(
            fields={
                "parish": "Ljusdal",
                "county_code": "X",
                "series": "AI",
                "volume": "23d",
                "years": "1883-1887",
                "page": 915,
            }
        )
        result = build_church_book_citation(ref)
        assert result == "Ljusdal (X) AI:23d (1883-1887) Sida: 915"

    def test_missing_page(self) -> None:
        """Citation without page omits Sida part."""
        ref = StructuredReference(
            fields={
                "parish": "Ljusdal",
                "county_code": "X",
                "series": "AI",
                "volume": "23d",
                "years": "1883-1887",
                "image": 23,
            }
        )
        result = build_church_book_citation(ref)
        assert result == "Ljusdal (X) AI:23d (1883-1887) Bild: 23"

    def test_only_parish(self) -> None:
        """Minimal citation with just parish."""
        ref = StructuredReference(fields={"parish": "Ljusdal"})
        result = build_church_book_citation(ref)
        assert result == "Ljusdal"

    def test_empty_fields(self) -> None:
        """Empty fields returns empty string."""
        ref = StructuredReference(fields={})
        result = build_church_book_citation(ref)
        assert result == ""

    def test_image_as_string(self) -> None:
        """Image field as string (not int) is handled."""
        ref = StructuredReference(
            fields={"parish": "Ljusdal", "county_code": "X", "image": "23"}
        )
        result = build_church_book_citation(ref)
        assert result == "Ljusdal (X) Bild: 23"

    def test_page_zero(self) -> None:
        """Page value of 0 is still included (not falsy-skipped)."""
        ref = StructuredReference(
            fields={"parish": "Ljusdal", "page": 0}
        )
        result = build_church_book_citation(ref)
        assert result == "Ljusdal Sida: 0"


# ---------------------------------------------------------------------------
# build_database_citation tests
# ---------------------------------------------------------------------------


class TestBuildDatabaseCitation:
    """Tests for build_database_citation function."""

    def test_full_citation(self) -> None:
        """Both database_name and record_id present."""
        ref = StructuredReference(
            fields={"database_name": "Sveriges Befolkning 1900", "record_id": "12345"}
        )
        result = build_database_citation(ref)
        assert result == "Sveriges Befolkning 1900, Record ID: 12345"

    def test_only_database_name(self) -> None:
        """Only database_name produces just the name."""
        ref = StructuredReference(fields={"database_name": "Sveriges Befolkning 1900"})
        result = build_database_citation(ref)
        assert result == "Sveriges Befolkning 1900"

    def test_only_record_id(self) -> None:
        """Only record_id produces just the record ID part."""
        ref = StructuredReference(fields={"record_id": "12345"})
        result = build_database_citation(ref)
        assert result == "Record ID: 12345"

    def test_empty_fields(self) -> None:
        """Empty fields returns empty string."""
        ref = StructuredReference(fields={})
        result = build_database_citation(ref)
        assert result == ""


# ---------------------------------------------------------------------------
# build_death_notice_citation tests
# ---------------------------------------------------------------------------


class TestBuildDeathNoticeCitation:
    """Tests for build_death_notice_citation function."""

    def test_full_citation(self) -> None:
        """All fields present produces the canonical format."""
        ref = StructuredReference(
            fields={
                "newspaper": "Hudiksvalls Tidning",
                "publication_date": "2023-05-15",
                "page": 12,
            }
        )
        result = build_death_notice_citation(ref)
        assert result == "Hudiksvalls Tidning, 2023-05-15, s. 12"

    def test_missing_page(self) -> None:
        """Citation without page omits s. part."""
        ref = StructuredReference(
            fields={
                "newspaper": "Hudiksvalls Tidning",
                "publication_date": "2023-05-15",
            }
        )
        result = build_death_notice_citation(ref)
        assert result == "Hudiksvalls Tidning, 2023-05-15"

    def test_missing_date(self) -> None:
        """Citation without date omits date part."""
        ref = StructuredReference(
            fields={"newspaper": "Hudiksvalls Tidning", "page": 12}
        )
        result = build_death_notice_citation(ref)
        assert result == "Hudiksvalls Tidning, s. 12"

    def test_only_newspaper(self) -> None:
        """Only newspaper name."""
        ref = StructuredReference(fields={"newspaper": "Hudiksvalls Tidning"})
        result = build_death_notice_citation(ref)
        assert result == "Hudiksvalls Tidning"

    def test_empty_fields(self) -> None:
        """Empty fields returns empty string."""
        ref = StructuredReference(fields={})
        result = build_death_notice_citation(ref)
        assert result == ""


# ---------------------------------------------------------------------------
# build_newspaper_citation tests
# ---------------------------------------------------------------------------


class TestBuildNewspaperCitation:
    """Tests for build_newspaper_citation function."""

    def test_full_citation(self) -> None:
        """All fields present produces canonical format with article title."""
        ref = StructuredReference(
            fields={
                "newspaper": "Dagens Nyheter",
                "date": "1950-03-01",
                "page": 5,
                "article_title": "Dödsannons",
            }
        )
        result = build_newspaper_citation(ref)
        assert result == "Dagens Nyheter, 1950-03-01, s. 5 - Dödsannons"

    def test_without_article_title(self) -> None:
        """Citation without article title omits the dash separator."""
        ref = StructuredReference(
            fields={
                "newspaper": "Dagens Nyheter",
                "date": "1950-03-01",
                "page": 5,
            }
        )
        result = build_newspaper_citation(ref)
        assert result == "Dagens Nyheter, 1950-03-01, s. 5"

    def test_missing_page(self) -> None:
        """Citation without page omits s. part."""
        ref = StructuredReference(
            fields={
                "newspaper": "Dagens Nyheter",
                "date": "1950-03-01",
                "article_title": "Dödsannons",
            }
        )
        result = build_newspaper_citation(ref)
        assert result == "Dagens Nyheter, 1950-03-01 - Dödsannons"

    def test_only_article_title(self) -> None:
        """Only article title when no other fields present."""
        ref = StructuredReference(fields={"article_title": "Dödsannons"})
        result = build_newspaper_citation(ref)
        assert result == "Dödsannons"

    def test_only_newspaper(self) -> None:
        """Only newspaper name."""
        ref = StructuredReference(fields={"newspaper": "Dagens Nyheter"})
        result = build_newspaper_citation(ref)
        assert result == "Dagens Nyheter"

    def test_empty_fields(self) -> None:
        """Empty fields returns empty string."""
        ref = StructuredReference(fields={})
        result = build_newspaper_citation(ref)
        assert result == ""


# ---------------------------------------------------------------------------
# build_generic_citation tests
# ---------------------------------------------------------------------------


class TestBuildGenericCitation:
    """Tests for build_generic_citation function."""

    def test_uses_reference_text_when_present(self) -> None:
        """Falls back to reference_text when available."""
        source = Source(
            id="src_1",
            provider="ArkivDigital",
            source_type="other",
            title="Some Title",
            reference_text="Custom reference text",
        )
        result = build_generic_citation(source)
        assert result == "Custom reference text"

    def test_uses_title_when_no_reference_text(self) -> None:
        """Falls back to title when reference_text is empty."""
        source = Source(
            id="src_1",
            provider="ArkivDigital",
            source_type="photograph",
            title="Photo of gravsten",
        )
        result = build_generic_citation(source)
        assert result == "Photo of gravsten"


# ---------------------------------------------------------------------------
# build_citation_text tests (integration / dispatch)
# ---------------------------------------------------------------------------


class TestBuildCitationText:
    """Tests for build_citation_text dispatch function."""

    def test_dispatches_church_book(self) -> None:
        """Church book source dispatches to church book builder."""
        source = Source(
            id="src_1",
            provider="ArkivDigital",
            source_type="church_book",
            title="Ljusdal AI:23d",
            structured_reference=StructuredReference(
                fields={
                    "parish": "Ljusdal",
                    "county_code": "X",
                    "series": "AI",
                    "volume": "23d",
                    "years": "1883-1887",
                    "image": 23,
                    "page": 915,
                }
            ),
        )
        result = build_citation_text(source)
        assert result == "Ljusdal (X) AI:23d (1883-1887) Bild: 23 Sida: 915"

    def test_dispatches_database(self) -> None:
        """Database source dispatches to database builder."""
        source = Source(
            id="src_2",
            provider="Riksarkivet",
            source_type="database",
            title="Sveriges Befolkning",
            structured_reference=StructuredReference(
                fields={"database_name": "Sveriges Befolkning 1900", "record_id": "12345"}
            ),
        )
        result = build_citation_text(source)
        assert result == "Sveriges Befolkning 1900, Record ID: 12345"

    def test_dispatches_death_notice(self) -> None:
        """Death notice source dispatches to death notice builder."""
        source = Source(
            id="src_3",
            provider="Manual",
            source_type="death_notice",
            title="Dödsannons",
            structured_reference=StructuredReference(
                fields={
                    "newspaper": "Hudiksvalls Tidning",
                    "publication_date": "2023-05-15",
                    "page": 12,
                }
            ),
        )
        result = build_citation_text(source)
        assert result == "Hudiksvalls Tidning, 2023-05-15, s. 12"

    def test_dispatches_newspaper(self) -> None:
        """Newspaper source dispatches to newspaper builder."""
        source = Source(
            id="src_4",
            provider="KB",
            source_type="newspaper",
            title="Tidningsartikel",
            structured_reference=StructuredReference(
                fields={
                    "newspaper": "Dagens Nyheter",
                    "date": "1950-03-01",
                    "page": 5,
                    "article_title": "Dödsannons",
                }
            ),
        )
        result = build_citation_text(source)
        assert result == "Dagens Nyheter, 1950-03-01, s. 5 - Dödsannons"

    def test_photograph_uses_generic(self) -> None:
        """Photograph source falls back to generic citation."""
        source = Source(
            id="src_5",
            provider="Family",
            source_type="photograph",
            title="Photo of grandfather",
            reference_text="Family photo collection, 1945",
        )
        result = build_citation_text(source)
        assert result == "Family photo collection, 1945"

    def test_census_uses_generic(self) -> None:
        """Census source falls back to generic citation."""
        source = Source(
            id="src_6",
            provider="SCB",
            source_type="census",
            title="Folkräkning 1900",
        )
        result = build_citation_text(source)
        assert result == "Folkräkning 1900"

    def test_other_uses_generic(self) -> None:
        """Other source type falls back to generic citation."""
        source = Source(
            id="src_7",
            provider="Manual",
            source_type="other",
            title="Handwritten notes",
        )
        result = build_citation_text(source)
        assert result == "Handwritten notes"

    def test_church_book_empty_fields_falls_back(self) -> None:
        """Church book source with empty structured ref falls back to generic."""
        source = Source(
            id="src_8",
            provider="ArkivDigital",
            source_type="church_book",
            title="Okänd källa",
            structured_reference=StructuredReference(fields={}),
        )
        result = build_citation_text(source)
        assert result == "Okänd källa"

    def test_church_book_empty_fields_with_reference_text(self) -> None:
        """Church book with empty struct ref but reference_text uses reference_text."""
        source = Source(
            id="src_9",
            provider="ArkivDigital",
            source_type="church_book",
            title="Titel",
            reference_text="Ljusdal (X) AI:23d",
            structured_reference=StructuredReference(fields={}),
        )
        result = build_citation_text(source)
        assert result == "Ljusdal (X) AI:23d"
