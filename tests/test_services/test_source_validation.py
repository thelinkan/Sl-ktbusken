"""Unit tests for source validation functions.

Tests validate_name, validate_comment, and validate_root_url from the
source_validation module.
"""

from __future__ import annotations

from slaktbusken.services.source_validation import (
    validate_comment,
    validate_name,
    validate_root_url,
)


# ---------------------------------------------------------------------------
# validate_name
# ---------------------------------------------------------------------------


class TestValidateName:
    """Tests for validate_name."""

    def test_valid_simple_name(self) -> None:
        assert validate_name("Arkiv Digital") == (True, "")

    def test_valid_single_character(self) -> None:
        assert validate_name("A") == (True, "")

    def test_valid_at_max_length(self) -> None:
        name = "A" * 100
        assert validate_name(name) == (True, "")

    def test_strips_whitespace_before_check(self) -> None:
        assert validate_name("  Rötter.se  ") == (True, "")

    def test_rejects_empty_string(self) -> None:
        valid, msg = validate_name("")
        assert valid is False
        assert msg == "Namn krävs."

    def test_rejects_whitespace_only(self) -> None:
        valid, msg = validate_name("   ")
        assert valid is False
        assert msg == "Namn krävs."

    def test_rejects_tabs_only(self) -> None:
        valid, msg = validate_name("\t\t")
        assert valid is False
        assert msg == "Namn krävs."

    def test_rejects_over_max_length(self) -> None:
        name = "A" * 101
        valid, msg = validate_name(name)
        assert valid is False
        assert msg == "Namn får vara högst 100 tecken."

    def test_custom_max_length(self) -> None:
        assert validate_name("ABCDE", max_length=5) == (True, "")
        valid, msg = validate_name("ABCDEF", max_length=5)
        assert valid is False
        assert msg == "Namn får vara högst 5 tecken."

    def test_stripped_length_used_for_max_check(self) -> None:
        # "  ABC  " stripped is "ABC" (3 chars), should pass with max_length=3
        assert validate_name("  ABC  ", max_length=3) == (True, "")

    def test_swedish_characters(self) -> None:
        assert validate_name("Övrigt") == (True, "")
        assert validate_name("Källöversättningar") == (True, "")


# ---------------------------------------------------------------------------
# validate_comment
# ---------------------------------------------------------------------------


class TestValidateComment:
    """Tests for validate_comment."""

    def test_valid_empty(self) -> None:
        assert validate_comment("") == (True, "")

    def test_valid_with_text(self) -> None:
        assert validate_comment("En kommentar om leverantören.") == (True, "")

    def test_valid_at_max_length(self) -> None:
        comment = "X" * 500
        assert validate_comment(comment) == (True, "")

    def test_rejects_over_max_length(self) -> None:
        comment = "X" * 501
        valid, msg = validate_comment(comment)
        assert valid is False
        assert msg == "Kommentar får vara högst 500 tecken."

    def test_custom_max_length(self) -> None:
        assert validate_comment("ABC", max_length=3) == (True, "")
        valid, msg = validate_comment("ABCD", max_length=3)
        assert valid is False
        assert msg == "Kommentar får vara högst 3 tecken."


# ---------------------------------------------------------------------------
# validate_root_url
# ---------------------------------------------------------------------------


class TestValidateRootUrl:
    """Tests for validate_root_url."""

    def test_valid_empty(self) -> None:
        assert validate_root_url("") == (True, "")

    def test_valid_url(self) -> None:
        url = "https://www.rotter.se/abonnemang/sveriges-dodbok-webb/post/"
        assert validate_root_url(url) == (True, "")

    def test_valid_at_max_length(self) -> None:
        url = "h" * 2048
        assert validate_root_url(url) == (True, "")

    def test_rejects_over_max_length(self) -> None:
        url = "h" * 2049
        valid, msg = validate_root_url(url)
        assert valid is False
        assert msg == "URL får vara högst 2048 tecken."

    def test_custom_max_length(self) -> None:
        assert validate_root_url("http://x", max_length=10) == (True, "")
        valid, msg = validate_root_url("http://example.com", max_length=10)
        assert valid is False
        assert msg == "URL får vara högst 10 tecken."


# ---------------------------------------------------------------------------
# is_kalltyp_name_unique
# ---------------------------------------------------------------------------

from slaktbusken.model.source import Kalltyp
from slaktbusken.services.source_validation import is_kalltyp_name_unique


class TestIsKalltypNameUnique:
    """Tests for is_kalltyp_name_unique."""

    def _make_kalltyp(self, id: str, leverantor_id: str, name: str) -> Kalltyp:
        return Kalltyp(id=id, leverantor_id=leverantor_id, name=name)

    def test_unique_name_empty_list(self) -> None:
        assert is_kalltyp_name_unique("lev1", "Husförhörslängd", []) is True

    def test_unique_name_no_conflict(self) -> None:
        kalltyper = [
            self._make_kalltyp("kt1", "lev1", "Folkräkning"),
            self._make_kalltyp("kt2", "lev1", "Mantalslängd"),
        ]
        assert is_kalltyp_name_unique("lev1", "Husförhörslängd", kalltyper) is True

    def test_conflict_same_leverantor(self) -> None:
        kalltyper = [
            self._make_kalltyp("kt1", "lev1", "Folkräkning"),
            self._make_kalltyp("kt2", "lev1", "Husförhörslängd"),
        ]
        assert is_kalltyp_name_unique("lev1", "Husförhörslängd", kalltyper) is False

    def test_no_conflict_different_leverantor(self) -> None:
        kalltyper = [
            self._make_kalltyp("kt1", "lev2", "Husförhörslängd"),
        ]
        assert is_kalltyp_name_unique("lev1", "Husförhörslängd", kalltyper) is True

    def test_case_sensitive_comparison(self) -> None:
        kalltyper = [
            self._make_kalltyp("kt1", "lev1", "husförhörslängd"),
        ]
        # Different case -> should be unique
        assert is_kalltyp_name_unique("lev1", "Husförhörslängd", kalltyper) is True

    def test_exclude_id_allows_self_rename(self) -> None:
        kalltyper = [
            self._make_kalltyp("kt1", "lev1", "Husförhörslängd"),
            self._make_kalltyp("kt2", "lev1", "Folkräkning"),
        ]
        # Excluding kt1 means "Husförhörslängd" is available (renaming kt1 to same name)
        assert is_kalltyp_name_unique("lev1", "Husförhörslängd", kalltyper, exclude_id="kt1") is True

    def test_exclude_id_still_detects_other_conflict(self) -> None:
        kalltyper = [
            self._make_kalltyp("kt1", "lev1", "Husförhörslängd"),
            self._make_kalltyp("kt2", "lev1", "Folkräkning"),
        ]
        # Excluding kt2, but kt1 still has "Husförhörslängd"
        assert is_kalltyp_name_unique("lev1", "Husförhörslängd", kalltyper, exclude_id="kt2") is False

    def test_exclude_id_empty_string_does_not_exclude(self) -> None:
        kalltyper = [
            self._make_kalltyp("kt1", "lev1", "Husförhörslängd"),
        ]
        assert is_kalltyp_name_unique("lev1", "Husförhörslängd", kalltyper, exclude_id="") is False


# ---------------------------------------------------------------------------
# is_leverantor_referenced
# ---------------------------------------------------------------------------

from slaktbusken.model.source import Leverantor, Source
from slaktbusken.services.source_validation import (
    delete_kalltyp,
    delete_leverantor,
    is_kalltyp_referenced,
    is_leverantor_referenced,
)


def _make_source(id: str, leverantor_id: str = "", kalltyp_id: str = "") -> Source:
    return Source(
        id=id,
        provider="",
        source_type="",
        title="Test",
        leverantor_id=leverantor_id,
        kalltyp_id=kalltyp_id,
    )


class TestIsLeverantorReferenced:
    """Tests for is_leverantor_referenced."""

    def test_no_sources(self) -> None:
        assert is_leverantor_referenced("lev1", []) is False

    def test_not_referenced(self) -> None:
        sources = [_make_source("s1", leverantor_id="lev2")]
        assert is_leverantor_referenced("lev1", sources) is False

    def test_referenced_by_one_source(self) -> None:
        sources = [_make_source("s1", leverantor_id="lev1")]
        assert is_leverantor_referenced("lev1", sources) is True

    def test_referenced_by_multiple_sources(self) -> None:
        sources = [
            _make_source("s1", leverantor_id="lev1"),
            _make_source("s2", leverantor_id="lev1"),
        ]
        assert is_leverantor_referenced("lev1", sources) is True


# ---------------------------------------------------------------------------
# is_kalltyp_referenced
# ---------------------------------------------------------------------------


class TestIsKalltypReferenced:
    """Tests for is_kalltyp_referenced."""

    def test_no_sources(self) -> None:
        assert is_kalltyp_referenced("kt1", []) is False

    def test_not_referenced(self) -> None:
        sources = [_make_source("s1", kalltyp_id="kt2")]
        assert is_kalltyp_referenced("kt1", sources) is False

    def test_referenced_by_one_source(self) -> None:
        sources = [_make_source("s1", kalltyp_id="kt1")]
        assert is_kalltyp_referenced("kt1", sources) is True

    def test_referenced_by_multiple_sources(self) -> None:
        sources = [
            _make_source("s1", kalltyp_id="kt1"),
            _make_source("s2", kalltyp_id="kt1"),
        ]
        assert is_kalltyp_referenced("kt1", sources) is True


# ---------------------------------------------------------------------------
# delete_leverantor
# ---------------------------------------------------------------------------


class TestDeleteLeverantor:
    """Tests for delete_leverantor."""

    def test_successful_delete_no_kalltyper(self) -> None:
        leverantorer = [Leverantor(id="lev1", name="Arkiv Digital")]
        kalltyper: list[Kalltyp] = []
        sources: list[Source] = []

        ok, msg = delete_leverantor("lev1", leverantorer, kalltyper, sources)
        assert ok is True
        assert msg == ""
        assert len(leverantorer) == 0

    def test_successful_delete_cascades_kalltyper(self) -> None:
        leverantorer = [Leverantor(id="lev1", name="Arkiv Digital")]
        kalltyper = [
            Kalltyp(id="kt1", leverantor_id="lev1", name="Husförhörslängd"),
            Kalltyp(id="kt2", leverantor_id="lev1", name="Folkräkning"),
            Kalltyp(id="kt3", leverantor_id="lev2", name="Övrigt"),
        ]
        sources: list[Source] = []

        ok, msg = delete_leverantor("lev1", leverantorer, kalltyper, sources)
        assert ok is True
        assert msg == ""
        assert len(leverantorer) == 0
        # Only kt3 (belonging to lev2) should remain
        assert len(kalltyper) == 1
        assert kalltyper[0].id == "kt3"

    def test_fails_when_leverantor_referenced(self) -> None:
        leverantorer = [Leverantor(id="lev1", name="Arkiv Digital")]
        kalltyper = [Kalltyp(id="kt1", leverantor_id="lev1", name="Husförhörslängd")]
        sources = [_make_source("s1", leverantor_id="lev1")]

        ok, msg = delete_leverantor("lev1", leverantorer, kalltyper, sources)
        assert ok is False
        assert "leverantören används" in msg
        # Nothing should be removed
        assert len(leverantorer) == 1
        assert len(kalltyper) == 1

    def test_fails_when_kalltyp_referenced(self) -> None:
        leverantorer = [Leverantor(id="lev1", name="Arkiv Digital")]
        kalltyper = [Kalltyp(id="kt1", leverantor_id="lev1", name="Husförhörslängd")]
        sources = [_make_source("s1", kalltyp_id="kt1")]

        ok, msg = delete_leverantor("lev1", leverantorer, kalltyper, sources)
        assert ok is False
        assert "källtyper används" in msg
        # Nothing should be removed
        assert len(leverantorer) == 1
        assert len(kalltyper) == 1

    def test_does_not_remove_other_leverantorer(self) -> None:
        leverantorer = [
            Leverantor(id="lev1", name="Arkiv Digital"),
            Leverantor(id="lev2", name="Rötter.se"),
        ]
        kalltyper: list[Kalltyp] = []
        sources: list[Source] = []

        ok, msg = delete_leverantor("lev1", leverantorer, kalltyper, sources)
        assert ok is True
        assert len(leverantorer) == 1
        assert leverantorer[0].id == "lev2"


# ---------------------------------------------------------------------------
# delete_kalltyp
# ---------------------------------------------------------------------------


class TestDeleteKalltyp:
    """Tests for delete_kalltyp."""

    def test_successful_delete(self) -> None:
        kalltyper = [
            Kalltyp(id="kt1", leverantor_id="lev1", name="Husförhörslängd"),
            Kalltyp(id="kt2", leverantor_id="lev1", name="Folkräkning"),
        ]
        sources: list[Source] = []

        ok, msg = delete_kalltyp("kt1", kalltyper, sources)
        assert ok is True
        assert msg == ""
        assert len(kalltyper) == 1
        assert kalltyper[0].id == "kt2"

    def test_fails_when_referenced(self) -> None:
        kalltyper = [Kalltyp(id="kt1", leverantor_id="lev1", name="Husförhörslängd")]
        sources = [_make_source("s1", kalltyp_id="kt1")]

        ok, msg = delete_kalltyp("kt1", kalltyper, sources)
        assert ok is False
        assert "källtypen används" in msg
        assert len(kalltyper) == 1

    def test_does_not_remove_other_kalltyper(self) -> None:
        kalltyper = [
            Kalltyp(id="kt1", leverantor_id="lev1", name="Husförhörslängd"),
            Kalltyp(id="kt2", leverantor_id="lev1", name="Folkräkning"),
        ]
        sources: list[Source] = []

        ok, msg = delete_kalltyp("kt2", kalltyper, sources)
        assert ok is True
        assert len(kalltyper) == 1
        assert kalltyper[0].id == "kt1"
