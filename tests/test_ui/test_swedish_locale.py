"""Tests for the centralized Swedish locale module.

Validates: Requirements 21.1, 21.2, 21.3, 21.4
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from slaktbusken.model.residence import Endpoint
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
    format_observation_span,
    format_percentage,
    format_residence_endpoint,
    format_residence_interval,
    format_residence_line,
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
        expected_types = {"country", "county", "parish", "church", "cemetery", "village", "farm", "school"}
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

# ---------------------------------------------------------------------------
# Residence_Formatter
#
# Validates: Requirements 10.8, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.11,
#            11.12, 11.13
# ---------------------------------------------------------------------------


EN_DASH = "\u2013"


class TestFormatResidenceEndpoint:
    """The five endpoint wordings, used alike at the start and end position."""

    def test_exact_renders_bare_value(self) -> None:
        # 11.1
        assert format_residence_endpoint(Endpoint(earliest="1840", latest="1840")) == "1840"

    def test_only_latest_renders_senast(self) -> None:
        # 11.2
        assert format_residence_endpoint(Endpoint(latest="1840")) == "senast 1840"

    def test_only_earliest_renders_tidigast(self) -> None:
        # 11.3
        assert format_residence_endpoint(Endpoint(earliest="1846")) == "tidigast 1846"

    def test_window_renders_mellan_och(self) -> None:
        # 11.4
        endpoint = Endpoint(earliest="1838", latest="1840")
        assert format_residence_endpoint(endpoint) == "mellan 1838 och 1840"

    def test_unknown_renders_okant(self) -> None:
        # 11.5
        assert format_residence_endpoint(Endpoint()) == "okänt"

    def test_whitespace_only_bounds_count_as_unknown(self) -> None:
        # 11.5 — a whitespace-only bound is absent
        assert format_residence_endpoint(Endpoint(earliest="  ", latest="\t")) == "okänt"

    def test_same_wording_at_start_and_end_position(self) -> None:
        # 11.2, 11.3 — the function has no notion of position
        endpoint = Endpoint(latest="1840")
        assert format_residence_endpoint(endpoint) == format_residence_endpoint(endpoint)

    def test_month_precision_is_not_truncated(self) -> None:
        # 11.13
        assert format_residence_endpoint(Endpoint(latest="1840-06")) == "senast 1840-06"

    def test_day_precision_is_not_truncated(self) -> None:
        # 11.13
        endpoint = Endpoint(earliest="1840-06-15")
        assert format_residence_endpoint(endpoint) == "tidigast 1840-06-15"

    def test_mixed_precision_window_keeps_both_stored_forms(self) -> None:
        # 11.4, 11.13 — "1840" and "1840-06" denote different day intervals
        endpoint = Endpoint(earliest="1840", latest="1840-06")
        assert format_residence_endpoint(endpoint) == "mellan 1840 och 1840-06"

    def test_precision_field_does_not_affect_wording(self) -> None:
        # 11.1 — precision is descriptive only
        plain = Endpoint(earliest="1840", latest="1840")
        approximate = Endpoint(earliest="1840", latest="1840", precision="approximate")
        assert format_residence_endpoint(plain) == format_residence_endpoint(approximate)


class TestFormatResidenceInterval:
    """Interval joining, the unknown period and pairwise distinguishability."""

    def test_two_exact_dates(self) -> None:
        # 11.1
        rendered = format_residence_interval(
            Endpoint(earliest="1840", latest="1840"),
            Endpoint(earliest="1846", latest="1846"),
        )
        assert rendered == "1840\u20131846"

    def test_two_open_endpoints(self) -> None:
        # 11.2, 11.3, 11.11
        rendered = format_residence_interval(
            Endpoint(latest="1840"), Endpoint(earliest="1846")
        )
        assert rendered == "senast 1840\u2013tidigast 1846"

    def test_worked_example_place_a(self) -> None:
        # 14.6 — "senast 1837–1840"
        rendered = format_residence_interval(
            Endpoint(latest="1837"),
            Endpoint(earliest="1840", latest="1840"),
        )
        assert rendered == "senast 1837\u20131840"

    def test_both_unknown_renders_unknown_period(self) -> None:
        # 11.12
        assert format_residence_interval(Endpoint(), Endpoint()) == "okänd period"

    def test_unknown_period_carries_no_separator(self) -> None:
        # 11.12
        assert EN_DASH not in format_residence_interval(Endpoint(), Endpoint())

    def test_one_unknown_side_still_renders_okant(self) -> None:
        # 11.5, 11.11 — no "?" placeholder, unlike format_date_range
        rendered = format_residence_interval(
            Endpoint(earliest="1840", latest="1840"), Endpoint()
        )
        assert rendered == "1840\u2013okänt"
        assert "?" not in rendered

    def test_dash_is_exactly_one_unspaced_en_dash(self) -> None:
        # 11.11
        rendered = format_residence_interval(
            Endpoint(latest="1840"), Endpoint(earliest="1846")
        )
        assert rendered.count(EN_DASH) == 1
        index = rendered.index(EN_DASH)
        assert rendered[index - 1] != " "
        assert rendered[index + 1] != " "

    def test_differs_from_format_date_range(self) -> None:
        # 11.11
        rendered = format_residence_interval(
            Endpoint(earliest="1840", latest="1840"),
            Endpoint(earliest="1846", latest="1846"),
        )
        assert rendered != format_date_range("1840", "1846")

    def test_every_ordered_classification_pair_is_distinguishable(self) -> None:
        # 11.6, 11.12
        representatives = {
            "exact": Endpoint(earliest="1840", latest="1840"),
            "open_latest": Endpoint(latest="1840"),
            "open_earliest": Endpoint(earliest="1840"),
            "window": Endpoint(earliest="1838", latest="1840"),
            "unknown": Endpoint(),
        }
        rendered = {
            (start_kind, end_kind): format_residence_interval(start, end)
            for start_kind, start in representatives.items()
            for end_kind, end in representatives.items()
        }
        assert len(rendered) == 25
        assert len(set(rendered.values())) == 25


class TestFormatResidenceLine:
    """Place, interval and household role on one line."""

    def test_non_empty_role_is_appended_with_comma_and_space(self) -> None:
        # 10.8
        line = format_residence_line(
            "Ekeby", Endpoint(latest="1840"), Endpoint(), "piga"
        )
        assert line == "Ekeby, senast 1840\u2013okänt, piga"

    def test_role_is_rendered_unchanged(self) -> None:
        # 10.8 — stored text, including internal spacing and case
        line = format_residence_line(
            "Ekeby",
            Endpoint(earliest="1840", latest="1840"),
            Endpoint(earliest="1846", latest="1846"),
            "Piga  hos  Anders",
        )
        assert line.endswith(", Piga  hos  Anders")

    def test_empty_role_adds_no_separator_and_no_trailing_whitespace(self) -> None:
        # 10.8
        line = format_residence_line(
            "Ekeby",
            Endpoint(earliest="1840", latest="1840"),
            Endpoint(earliest="1846", latest="1846"),
            "",
        )
        assert line == "Ekeby, 1840\u20131846"
        assert line == line.rstrip()

    def test_unknown_period_line(self) -> None:
        # 11.12
        assert format_residence_line("Ekeby", Endpoint(), Endpoint(), "") == "Ekeby, okänd period"

    def test_missing_place_display_adds_no_leading_separator(self) -> None:
        line = format_residence_line("", Endpoint(latest="1840"), Endpoint(), "")
        assert line == "senast 1840\u2013okänt"


class TestFormatObservationSpan:
    """Observation spans as "1866–1870" or "1866"."""

    def test_differing_years(self) -> None:
        # 11.9
        assert format_observation_span("1866", "1870") == "1866\u20131870"

    def test_equal_years(self) -> None:
        # 11.9
        assert format_observation_span("1866", "1866") == "1866"

    def test_only_from_year(self) -> None:
        assert format_observation_span("1866", "") == "1866"

    def test_only_to_year(self) -> None:
        assert format_observation_span("", "1870") == "1870"

    def test_both_absent(self) -> None:
        assert format_observation_span("", "") == ""

    def test_span_dash_is_unspaced(self) -> None:
        # 11.11
        rendered = format_observation_span("1866", "1870")
        assert rendered.count(EN_DASH) == 1
        assert " " not in rendered
