"""Tests for the centralized Swedish locale module.

Validates: Requirements 21.1, 21.2, 21.3, 21.4
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from slaktbusken.ui.swedish_locale import (
    CHURCH_BOOK_SERIES_LABELS,
    EVENT_TYPE_LABELS,
    FAMILY_EVENT_TYPE_LABELS,
    INDIVIDUAL_EVENT_TYPE_LABELS,
    MEDIA_TYPE_LABELS,
    NAME_TYPE_LABELS,
    PARENTAGE_TYPE_LABELS,
    PARTNER_ROLE_LABELS,
    PLACE_TYPE_LABELS,
    RELATIONSHIP_LABELS,
    SOURCE_TYPE_LABELS,
    SEX_LABELS,
    DNA_TEST_TYPE_LABELS,
    SOURCE_QUALITY_LABELS,
    DATE_PRECISION_LABELS,
    event_type_from_label,
    format_cm,
    format_date,
    format_date_range,
    format_number,
    format_percentage,
    get_event_type_label,
    get_media_type_label,
    get_parentage_type_label,
    get_place_type_label,
    get_relationship_label,
    get_sex_label,
    get_source_type_label,
    place_type_from_label,
    source_type_from_label,
)


# ---------------------------------------------------------------------------
# 21.3 — Swedish genealogical terminology
# ---------------------------------------------------------------------------


class TestSourceTypeLabels:
    """Test Swedish source type terminology."""

    def test_church_book(self) -> None:
        assert SOURCE_TYPE_LABELS["church_book"] == "Kyrkobok"

    def test_database(self) -> None:
        assert SOURCE_TYPE_LABELS["database"] == "Databas"

    def test_all_source_types_have_labels(self) -> None:
        expected_types = {
            "church_book", "database", "death_notice",
            "newspaper", "photograph", "census", "other",
        }
        assert set(SOURCE_TYPE_LABELS.keys()) == expected_types

    def test_church_book_series_husforhorslangd(self) -> None:
        assert CHURCH_BOOK_SERIES_LABELS["AI"] == "Husförhörslängd"

    def test_church_book_series_fodelsebok(self) -> None:
        assert CHURCH_BOOK_SERIES_LABELS["CI"] == "Födelsebok"

    def test_church_book_series_vigselbok(self) -> None:
        assert CHURCH_BOOK_SERIES_LABELS["E"] == "Lysnings- och vigselbok"


class TestPlaceTypeLabels:
    """Test Swedish place type terminology."""

    def test_parish_is_socken(self) -> None:
        assert PLACE_TYPE_LABELS["parish"] == "Socken"

    def test_cemetery_is_kyrkogard(self) -> None:
        assert PLACE_TYPE_LABELS["cemetery"] == "Kyrkogård"

    def test_all_place_types_have_labels(self) -> None:
        expected_types = {"country", "county", "parish", "church", "cemetery"}
        assert set(PLACE_TYPE_LABELS.keys()) == expected_types


class TestEventTypeLabels:
    """Test Swedish event type terminology."""

    def test_baptism_is_dop(self) -> None:
        assert EVENT_TYPE_LABELS["baptism"] == "Dop"

    def test_burial_is_begravning(self) -> None:
        assert EVENT_TYPE_LABELS["burial"] == "Begravning"

    def test_marriage_is_vigsel(self) -> None:
        assert EVENT_TYPE_LABELS["marriage"] == "Vigsel"

    def test_individual_and_family_combined(self) -> None:
        # All individual + family events present
        assert "birth" in EVENT_TYPE_LABELS
        assert "death" in EVENT_TYPE_LABELS
        assert "divorce" in EVENT_TYPE_LABELS
        assert "marriage" in EVENT_TYPE_LABELS


class TestRelationshipLabels:
    """Test Swedish relationship terminology."""

    def test_father_is_far(self) -> None:
        assert RELATIONSHIP_LABELS["father"] == "Far"

    def test_mother_is_mor(self) -> None:
        assert RELATIONSHIP_LABELS["mother"] == "Mor"

    def test_husband_is_make(self) -> None:
        assert RELATIONSHIP_LABELS["husband"] == "Make"

    def test_wife_is_maka(self) -> None:
        assert RELATIONSHIP_LABELS["wife"] == "Maka"


class TestParentageTypeLabels:
    """Test Swedish parentage type terminology."""

    def test_biological(self) -> None:
        assert PARENTAGE_TYPE_LABELS["biological"] == "Biologisk"

    def test_adoptive(self) -> None:
        assert PARENTAGE_TYPE_LABELS["adoptive"] == "Adoptiv"

    def test_foster(self) -> None:
        assert PARENTAGE_TYPE_LABELS["foster"] == "Foster"


# ---------------------------------------------------------------------------
# 21.4 — Swedish date formatting
# ---------------------------------------------------------------------------


class TestDateFormatting:
    """Test Swedish date formatting (YYYY-MM-DD)."""

    def test_format_date_object(self) -> None:
        result = format_date(date(2024, 3, 15))
        assert result == "2024-03-15"

    def test_format_datetime_object(self) -> None:
        result = format_date(datetime(2024, 12, 25, 10, 30))
        assert result == "2024-12-25"

    def test_format_date_string_full(self) -> None:
        result = format_date("2024-03-15")
        assert result == "2024-03-15"

    def test_format_date_string_partial_month(self) -> None:
        result = format_date("2024-03")
        assert result == "2024-03"

    def test_format_date_string_year_only(self) -> None:
        result = format_date("2024")
        assert result == "2024"

    def test_format_date_none(self) -> None:
        result = format_date(None)
        assert result == ""

    def test_format_date_range(self) -> None:
        result = format_date_range("2020-01-01", "2024-12-31")
        assert "2020-01-01" in result
        assert "2024-12-31" in result
        assert "\u2013" in result  # en-dash


# ---------------------------------------------------------------------------
# 21.4 — Swedish number formatting
# ---------------------------------------------------------------------------


class TestNumberFormatting:
    """Test Swedish number formatting (comma decimal, space thousands)."""

    def test_integer_no_thousands(self) -> None:
        result = format_number(42)
        assert result == "42"

    def test_integer_with_thousands(self) -> None:
        result = format_number(1234567)
        assert result == "1\u00a0234\u00a0567"  # non-breaking spaces

    def test_integer_exactly_thousand(self) -> None:
        result = format_number(1000)
        assert result == "1\u00a0000"

    def test_decimal_with_comma(self) -> None:
        result = format_number(1234.5, decimals=2)
        assert "," in result
        assert "1\u00a0234,50" == result

    def test_small_decimal(self) -> None:
        result = format_number(0.5, decimals=1)
        assert result == "0,5"

    def test_million(self) -> None:
        result = format_number(1000000)
        assert result == "1\u00a0000\u00a0000"

    def test_negative_number(self) -> None:
        result = format_number(-1234)
        assert result == "-1\u00a0234"

    def test_format_percentage(self) -> None:
        result = format_percentage(75.5)
        assert "75,5" in result
        assert "%" in result

    def test_format_cm(self) -> None:
        result = format_cm(125.4)
        assert "125,4" in result
        assert "cM" in result


# ---------------------------------------------------------------------------
# Reverse lookups and utility functions
# ---------------------------------------------------------------------------


class TestReverseLookups:
    """Test reverse lookup functions (Swedish label -> internal key)."""

    def test_source_type_from_label(self) -> None:
        assert source_type_from_label("Kyrkobok") == "church_book"
        assert source_type_from_label("Folkräkning") == "census"
        assert source_type_from_label("Nonexistent") is None

    def test_place_type_from_label(self) -> None:
        assert place_type_from_label("Socken") == "parish"
        assert place_type_from_label("Kyrkogård") == "cemetery"
        assert place_type_from_label("Nonexistent") is None

    def test_event_type_from_label(self) -> None:
        assert event_type_from_label("Dop") == "baptism"
        assert event_type_from_label("Vigsel") == "marriage"
        assert event_type_from_label("Nonexistent") is None


class TestGetLabelFallback:
    """Test get_*_label functions with fallback behavior."""

    def test_get_event_type_label_known(self) -> None:
        assert get_event_type_label("birth") == "Födelse"

    def test_get_event_type_label_unknown_fallback(self) -> None:
        assert get_event_type_label("unknown_type") == "unknown_type"

    def test_get_source_type_label_known(self) -> None:
        assert get_source_type_label("church_book") == "Kyrkobok"

    def test_get_place_type_label_known(self) -> None:
        assert get_place_type_label("parish") == "Socken"

    def test_get_relationship_label_known(self) -> None:
        assert get_relationship_label("father") == "Far"

    def test_get_parentage_type_label_known(self) -> None:
        assert get_parentage_type_label("biological") == "Biologisk"

    def test_get_media_type_label_known(self) -> None:
        assert get_media_type_label("photo") == "Foto"

    def test_get_sex_label_known(self) -> None:
        assert get_sex_label("M") == "Man"
        assert get_sex_label("F") == "Kvinna"
