"""Bug condition exploration tests for ArkivDigital reference format equivalence.

These tests encode the EXPECTED (correct) behavior for the bugfix. They are
designed to FAIL on unfixed code, demonstrating that the bugs exist.

When the fix is implemented, these same tests should PASS.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4**

Bug Condition:
    isBugCondition(input) =
        (has_prefix AND leverantor_id NOT assigned)
        OR (has_aid_nad AND aid_nad_text IN reference_text)
        OR (colon/slash variants produce different Source records)
"""

from __future__ import annotations

import pytest

from slaktbusken.gedcom.translation.models import GedcomSource
from slaktbusken.gedcom.translation.source_translation import map_gedcom_source
from slaktbusken.model.source import Kalltyp, Leverantor
from slaktbusken.parsing.reference_parser import parse_reference
from slaktbusken.persistence.translation_io import SourceMapping
from slaktbusken.services.source_formatting import format_source_title


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_arkiv_digital_providers() -> tuple[list[Leverantor], list[Kalltyp]]:
    """Create Leverantör and Källtyp entities for ArkivDigital testing."""
    lev = Leverantor(id="lev_ad", name="Arkiv Digital")
    kalltyper = [
        Kalltyp(id="kt_hfl", leverantor_id="lev_ad", name="Husförhörslängd"),
        Kalltyp(id="kt_fb", leverantor_id="lev_ad", name="Församlingsbok"),
        Kalltyp(id="kt_fdb", leverantor_id="lev_ad", name="Födelse- och dopbok"),
        Kalltyp(id="kt_ovr", leverantor_id="lev_ad", name="Övrigt"),
    ]
    return [lev], kalltyper


# ---------------------------------------------------------------------------
# Test 1: Prefix Leverantör/Källtyp assignment via GEDCOM import
# Bug: map_gedcom_source() does not assign leverantor_id/kalltyp_id for
#      ArkivDigital-prefixed sources
# ---------------------------------------------------------------------------


class TestPrefixLeverantorKalltypAssignment:
    """Test that ArkivDigital-prefixed GEDCOM sources get Leverantör and Källtyp assigned.

    **Validates: Requirements 1.1**

    Expected behavior: When a GEDCOM source has text starting with "ArkivDigital:",
    the system shall strip the prefix, assign Leverantör ID for "Arkiv Digital",
    and assign Källtyp ID derived from the series code (AIIa → Församlingsbok).
    """

    def test_prefixed_source_assigns_leverantor_id(self) -> None:
        """A prefixed ArkivDigital GEDCOM source gets leverantor_id = 'Arkiv Digital'."""
        leverantorer, kalltyper = _make_arkiv_digital_providers()
        gs = GedcomSource(
            xref_id="@S1@",
            title="ArkivDigital: Karlstads stadsförsamling",
            text="ArkivDigital: Karlstads stadsförsamling (S) AIIa:7 (1906-1910) Bild: 300 Sida: 16",
        )
        result = map_gedcom_source(gs, [], [], leverantorer=leverantorer, kalltyper=kalltyper)

        # Expected: leverantor_id should be "lev_ad" (the ID for "Arkiv Digital")
        assert result.leverantor_id == "lev_ad", (
            f"Bug confirmed: leverantor_id is '{result.leverantor_id}' "
            f"(expected 'lev_ad' for 'Arkiv Digital')"
        )

    def test_prefixed_source_assigns_kalltyp_id(self) -> None:
        """A prefixed ArkivDigital GEDCOM source gets kalltyp_id derived from series 'AIIa' → 'Församlingsbok'."""
        leverantorer, kalltyper = _make_arkiv_digital_providers()
        gs = GedcomSource(
            xref_id="@S2@",
            title="ArkivDigital: Karlstads stadsförsamling",
            text="ArkivDigital: Karlstads stadsförsamling (S) AIIa:7 (1906-1910) Bild: 300 Sida: 16",
        )
        result = map_gedcom_source(gs, [], [], leverantorer=leverantorer, kalltyper=kalltyper)

        # Expected: kalltyp_id should be "kt_fb" (the ID for "Församlingsbok", from AIIa)
        assert result.kalltyp_id == "kt_fb", (
            f"Bug confirmed: kalltyp_id is '{result.kalltyp_id}' "
            f"(expected 'kt_fb' for 'Församlingsbok' derived from series 'AIIa')"
        )


# ---------------------------------------------------------------------------
# Test 2: AID/NAD should NOT appear in reference_text
# Bug: reference_text stores the full string including (AID: ..., NAD: ...)
# ---------------------------------------------------------------------------


class TestAidNadNotInReferenceText:
    """Test that reference_text does NOT contain AID/NAD parenthetical.

    **Validates: Requirements 1.3**

    Expected behavior: When a reference string contains (AID: ..., NAD: ...),
    the reference_text field should contain only the text preceding that
    parenthesis (trimmed).
    """

    def test_parse_reference_strips_aid_nad_from_reference_text(self) -> None:
        """parse_reference() should NOT include (AID: ..., NAD: ...) in reference_text."""
        text = "Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)"
        result = parse_reference(text)

        assert result is not None, "parse_reference should match this full pattern"

        # Expected: reference_text should NOT contain the AID/NAD parenthetical
        assert "(AID:" not in result.reference_text, (
            f"Bug confirmed: reference_text contains '(AID:' — "
            f"got: '{result.reference_text}'"
        )
        assert "(NAD:" not in result.reference_text, (
            f"Bug confirmed: reference_text contains '(NAD:' — "
            f"got: '{result.reference_text}'"
        )

    def test_reference_text_is_human_readable_portion_only(self) -> None:
        """reference_text should be only the human-readable part before (AID: ...)."""
        text = "Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)"
        result = parse_reference(text)

        assert result is not None
        expected_ref_text = "Ed (S) AI:16 (1866-1870) Bild 58 / sid 51"
        assert result.reference_text == expected_ref_text, (
            f"Bug confirmed: reference_text is '{result.reference_text}' "
            f"(expected '{expected_ref_text}')"
        )

    def test_gedcom_import_strips_aid_nad_from_reference_text(self) -> None:
        """map_gedcom_source() should strip AID/NAD from reference_text in GEDCOM import."""
        gs = GedcomSource(
            xref_id="@S3@",
            title="Ed AI:16",
            text="Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)",
        )
        result = map_gedcom_source(gs, [], [])

        assert "(AID:" not in result.reference_text, (
            f"Bug confirmed: GEDCOM reference_text contains '(AID:' — "
            f"got: '{result.reference_text}'"
        )
        assert "(NAD:" not in result.reference_text, (
            f"Bug confirmed: GEDCOM reference_text contains '(NAD:' — "
            f"got: '{result.reference_text}'"
        )


# ---------------------------------------------------------------------------
# Test 3: Prefixed GEDCOM import populates arkivreferenser
# Bug: map_gedcom_source() does not populate arkivreferenser for ArkivDigital
# ---------------------------------------------------------------------------


class TestPrefixedImportPopulatesArkivreferenser:
    """Test that GEDCOM import populates arkivreferenser when AID/NAD can be derived.

    **Validates: Requirements 1.2**

    Expected behavior: When a GEDCOM source with ArkivDigital prefix contains
    AID/NAD values (derivable from the reference text pattern), the system
    shall populate arkivreferenser entries on the Source.
    """

    def test_prefixed_source_with_aid_nad_populates_arkivreferenser(self) -> None:
        """GEDCOM import of a slash-variant ArkivDigital source populates arkivreferenser."""
        leverantorer, kalltyper = _make_arkiv_digital_providers()
        gs = GedcomSource(
            xref_id="@S4@",
            title="ArkivDigital: Ed",
            text="ArkivDigital: Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)",
        )
        result = map_gedcom_source(gs, [], [], leverantorer=leverantorer, kalltyper=kalltyper)

        # Expected: arkivreferenser should have entries for AID and NAD
        assert len(result.arkivreferenser) >= 1, (
            f"Bug confirmed: arkivreferenser is empty "
            f"(expected at least 1 entry for AID/NAD values)"
        )

    def test_arkivreferenser_contains_aid_entry(self) -> None:
        """arkivreferenser should contain an entry for 'Arkiv Digital' with AID value."""
        leverantorer, kalltyper = _make_arkiv_digital_providers()
        gs = GedcomSource(
            xref_id="@S5@",
            title="ArkivDigital: Ed",
            text="ArkivDigital: Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)",
        )
        result = map_gedcom_source(gs, [], [], leverantorer=leverantorer, kalltyper=kalltyper)

        aid_entries = [
            ar for ar in result.arkivreferenser
            if ar.leverantor_name == "Arkiv Digital"
        ]
        assert len(aid_entries) >= 1, (
            f"Bug confirmed: no arkivreferens entry for 'Arkiv Digital' "
            f"(expected entry with value 'v10726.b58.s51')"
        )
        if aid_entries:
            assert aid_entries[0].reference_value == "v10726.b58.s51", (
                f"arkivreferens value mismatch: got '{aid_entries[0].reference_value}'"
            )


# ---------------------------------------------------------------------------
# Test 4: Format equivalence between colon and slash variants
# Bug: The two format variants produce Source records with different
#      Leverantör, Källtyp, and/or title values
# ---------------------------------------------------------------------------


class TestFormatEquivalence:
    """Test that colon and slash variants produce equivalent Source records.

    **Validates: Requirements 1.4**

    Expected behavior: Both colon variant and slash variant of the same source
    produce Source records with equivalent Leverantör, Källtyp, and formatted title.
    The only permitted difference is that the slash variant may additionally
    include arkivreferenser entries.
    """

    def test_both_variants_produce_same_leverantor_name(self) -> None:
        """Both format variants should produce leverantor_name = 'Arkiv Digital'."""
        colon_text = "Ed (S) AI:16 (1866-1870) Bild: 58 Sida: 51"
        slash_text = "Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)"

        colon_result = parse_reference(colon_text)
        slash_result = parse_reference(slash_text)

        assert colon_result is not None, "Colon variant should parse"
        assert slash_result is not None, "Slash variant should parse"

        assert colon_result.leverantor_name == slash_result.leverantor_name, (
            f"Bug confirmed: leverantor_name differs — "
            f"colon='{colon_result.leverantor_name}', slash='{slash_result.leverantor_name}'"
        )
        assert colon_result.leverantor_name == "Arkiv Digital"

    def test_both_variants_produce_same_kalltyp_name(self) -> None:
        """Both format variants should produce kalltyp_name = 'Husförhörslängd' (from AI)."""
        colon_text = "Ed (S) AI:16 (1866-1870) Bild: 58 Sida: 51"
        slash_text = "Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)"

        colon_result = parse_reference(colon_text)
        slash_result = parse_reference(slash_text)

        assert colon_result is not None
        assert slash_result is not None

        assert colon_result.kalltyp_name == slash_result.kalltyp_name, (
            f"Bug confirmed: kalltyp_name differs — "
            f"colon='{colon_result.kalltyp_name}', slash='{slash_result.kalltyp_name}'"
        )
        assert colon_result.kalltyp_name == "Husförhörslängd"

    def test_both_variants_produce_same_title(self) -> None:
        """Both format variants should produce the same formatted title."""
        colon_text = "Ed (S) AI:16 (1866-1870) Bild: 58 Sida: 51"
        slash_text = "Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)"

        colon_result = parse_reference(colon_text)
        slash_result = parse_reference(slash_text)

        assert colon_result is not None
        assert slash_result is not None

        assert colon_result.title == slash_result.title, (
            f"Bug confirmed: title differs — "
            f"colon='{colon_result.title}', slash='{slash_result.title}'"
        )
        # Both should produce "Ed AI:16 Sida: 51"
        assert colon_result.title == "Ed AI:16 Sida: 51"

    def test_prefix_stripped_before_parsing(self) -> None:
        """parse_reference() with 'ArkivDigital:' prefix should still parse correctly."""
        prefixed_text = "ArkivDigital: Ed (S) AI:16 (1866-1870) Bild: 58 Sida: 51"
        result = parse_reference(prefixed_text)

        # Expected: prefix is stripped and text is parsed as normal ArkivDigital reference
        assert result is not None, (
            "Bug confirmed: parse_reference() returns None for prefixed text "
            f"'{prefixed_text}' — prefix is not being stripped before pattern matching"
        )
        if result is not None:
            assert result.leverantor_name == "Arkiv Digital"
            assert result.kalltyp_name == "Husförhörslängd"
