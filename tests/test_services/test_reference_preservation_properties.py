"""Preservation property tests for non-ArkivDigital reference behavior.

These tests capture the EXISTING correct behavior of parse_reference() and
map_gedcom_source() on the unfixed code. They MUST PASS on both unfixed and
fixed code — any failure after fixes are applied indicates a regression.

Observation-first methodology: each test observes what the code actually
does for non-buggy inputs and asserts that behavior is preserved.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from slaktbusken.gedcom.translation.models import GedcomSource
from slaktbusken.gedcom.translation.source_translation import map_gedcom_source
from slaktbusken.model.source import ArkivReferens, Kalltyp, Leverantor
from slaktbusken.parsing.reference_parser import parse_reference


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate strings that do NOT match any ArkivDigital, SDB, or census pattern.
# Excludes characters/patterns that would trigger any known parser.
_non_ad_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "Zs"),
        blacklist_characters="()",
    ),
    min_size=1,
    max_size=120,
).filter(
    lambda s: (
        "arkivdigital" not in s.lower()
        and "AID:" not in s.upper()
        and "SDB" not in s.upper()
        and "sveriges dödbok" not in s.lower()
        and not (s.strip().startswith("r") and ".p" in s)
        # Exclude strings that could match the church book Bild: N pattern
        and "Bild:" not in s
        and "Bild " not in s
    )
)

# Generate GedcomSource objects that are NOT ArkivDigital and NOT SDB.
_safe_titles = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    min_size=1,
    max_size=60,
).filter(
    lambda s: (
        "arkivdigital" not in s.lower()
        and "SDB" not in s.upper()
        and "sveriges dödbok" not in s.lower()
    )
)

_safe_text = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs", "P")),
        min_size=1,
        max_size=100,
    ).filter(
        lambda s: (
            "arkivdigital" not in s.lower()
            and "SDB" not in s.upper()
            and "sveriges dödbok" not in s.lower()
            and "Bild:" not in s
            and "Bild " not in s
            and not (s.strip().startswith("r") and ".p" in s)
        )
    ),
)


def _non_ad_gedcom_source_strategy():
    """Strategy for GedcomSource objects that won't match ArkivDigital or SDB."""
    return st.builds(
        GedcomSource,
        xref_id=st.from_regex(r"@S[0-9]{1,4}@", fullmatch=True),
        title=_safe_titles,
        text=_safe_text,
        author=st.one_of(st.none(), _safe_titles),
        publication=st.one_of(st.none(), _safe_titles),
    )


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_rotter_providers() -> tuple[list[Leverantor], list[Kalltyp]]:
    """Create Leverantör and Källtyp entities for Rötter.se/SDB testing."""
    lev = Leverantor(id="lev_rotter", name="Rötter.se")
    kalltyper = [
        Kalltyp(id="kt_sdb", leverantor_id="lev_rotter", name="Sveriges Dödbok Webb"),
    ]
    return [lev], kalltyper


def _make_arkiv_digital_providers() -> tuple[list[Leverantor], list[Kalltyp]]:
    """Create Leverantör and Källtyp entities for Arkiv Digital testing."""
    lev = Leverantor(id="lev_ad", name="Arkiv Digital")
    kalltyper = [
        Kalltyp(id="kt_hfl", leverantor_id="lev_ad", name="Husförhörslängd"),
        Kalltyp(id="kt_fb", leverantor_id="lev_ad", name="Församlingsbok"),
        Kalltyp(id="kt_folk", leverantor_id="lev_ad", name="Folkräkning"),
    ]
    return [lev], kalltyper


# ---------------------------------------------------------------------------
# Property 2a: Non-ArkivDigital strings return None from parse_reference()
# Validates: Requirements 3.6
# ---------------------------------------------------------------------------


class TestNonArkivDigitalParseReferencePreservation:
    """**Validates: Requirements 3.6**

    Property: For any string that does not match any known pattern,
    parse_reference() returns None. This behavior must be preserved.

    Observed on UNFIXED code:
    - Random strings without ArkivDigital, SDB, or census patterns → None
    - Strings with partial keywords but not full patterns → None
    """

    @given(text=_non_ad_strategy)
    @settings(max_examples=50, deadline=None)
    def test_non_matching_strings_return_none(self, text: str) -> None:
        """Non-matching generated strings return None from parse_reference."""
        result = parse_reference(text)
        assert result is None, (
            f"Expected None for non-matching string, got {result!r} "
            f"for input: {text!r}"
        )

    def test_plain_text_returns_none(self) -> None:
        """Plain descriptive text without pattern markers returns None."""
        texts = [
            "Min farmors födelsebevis",
            "Kyrkobok från 1800-talet",
            "Dokument utan referens",
            "Some English document title",
            "123456789",
        ]
        for text in texts:
            result = parse_reference(text)
            assert result is None, (
                f"Expected None for plain text '{text}', got {result!r}"
            )


# ---------------------------------------------------------------------------
# Property 2b: Non-ArkivDigital GEDCOM sources get no Leverantör/Källtyp
# Validates: Requirements 3.1
# ---------------------------------------------------------------------------


class TestNonArkivDigitalGedcomPreservation:
    """**Validates: Requirements 3.1**

    Property: For any GEDCOM source without ArkivDigital markers and not
    matching SDB patterns, map_gedcom_source() produces a Source with
    empty leverantor_id and empty kalltyp_id.

    Observed on UNFIXED code:
    - GedcomSource(title="My family tree", text="Random notes") →
      leverantor_id == "", kalltyp_id == ""
    - No Leverantör or Källtyp assignment for generic sources
    """

    @given(gs=_non_ad_gedcom_source_strategy())
    @settings(max_examples=50, deadline=None)
    def test_non_ad_sources_have_no_leverantor_or_kalltyp(self, gs: GedcomSource) -> None:
        """Non-ArkivDigital, non-SDB GEDCOM sources get no Leverantör/Källtyp assigned."""
        leverantorer, kalltyper = _make_rotter_providers()
        ad_leverantorer, ad_kalltyper = _make_arkiv_digital_providers()
        all_lev = leverantorer + ad_leverantorer
        all_kt = kalltyper + ad_kalltyper

        result = map_gedcom_source(gs, [], [], leverantorer=all_lev, kalltyper=all_kt)

        assert result.leverantor_id == "", (
            f"Expected empty leverantor_id for non-AD source with title='{gs.title}', "
            f"text='{gs.text}', got '{result.leverantor_id}'"
        )
        assert result.kalltyp_id == "", (
            f"Expected empty kalltyp_id for non-AD source with title='{gs.title}', "
            f"text='{gs.text}', got '{result.kalltyp_id}'"
        )

    def test_generic_source_no_leverantor(self) -> None:
        """A generic GEDCOM source (no patterns) gets no leverantor_id."""
        gs = GedcomSource(
            xref_id="@S99@",
            title="Min egen anteckning",
            text="Noteringar om familjen",
        )
        result = map_gedcom_source(gs, [], [])
        assert result.leverantor_id == ""
        assert result.kalltyp_id == ""


# ---------------------------------------------------------------------------
# Property 2c: SDB pattern correctly assigns Rötter.se / Sveriges Dödbok Webb
# Validates: Requirements 3.5
# ---------------------------------------------------------------------------


class TestSdbDetectionPreservation:
    """**Validates: Requirements 3.5**

    Property: GEDCOM sources matching the SDB pattern (SDB{digit}_{digits}
    or "Sveriges dödbok webb") get Leverantör "Rötter.se" and Källtyp
    "Sveriges Dödbok Webb" assigned.

    Observed on UNFIXED code:
    - GedcomSource with text containing "SDB7_12345" →
      leverantor_id = "lev_rotter", kalltyp_id = "kt_sdb"
    - GedcomSource with title "Sveriges dödbok webb" →
      leverantor_id = "lev_rotter", kalltyp_id = "kt_sdb"
    """

    def test_sdb_pattern_assigns_leverantor_rotter(self) -> None:
        """SDB pattern in text assigns Leverantör 'Rötter.se'."""
        leverantorer, kalltyper = _make_rotter_providers()
        gs = GedcomSource(
            xref_id="@S10@",
            title="SDB dödsnotis",
            text="SDB7_98765",
        )
        result = map_gedcom_source(gs, [], [], leverantorer=leverantorer, kalltyper=kalltyper)
        assert result.leverantor_id == "lev_rotter", (
            f"Expected 'lev_rotter', got '{result.leverantor_id}'"
        )

    def test_sdb_pattern_assigns_kalltyp_sdb(self) -> None:
        """SDB pattern in text assigns Källtyp 'Sveriges Dödbok Webb'."""
        leverantorer, kalltyper = _make_rotter_providers()
        gs = GedcomSource(
            xref_id="@S11@",
            title="SDB dödsnotis",
            text="SDB7_98765",
        )
        result = map_gedcom_source(gs, [], [], leverantorer=leverantorer, kalltyper=kalltyper)
        assert result.kalltyp_id == "kt_sdb", (
            f"Expected 'kt_sdb', got '{result.kalltyp_id}'"
        )

    def test_sveriges_dodbok_text_assigns_leverantor(self) -> None:
        """'Sveriges dödbok webb' in title assigns Leverantör 'Rötter.se'."""
        leverantorer, kalltyper = _make_rotter_providers()
        gs = GedcomSource(
            xref_id="@S12@",
            title="Sveriges dödbok webb - 12345",
        )
        result = map_gedcom_source(gs, [], [], leverantorer=leverantorer, kalltyper=kalltyper)
        assert result.leverantor_id == "lev_rotter", (
            f"Expected 'lev_rotter', got '{result.leverantor_id}'"
        )
        assert result.kalltyp_id == "kt_sdb", (
            f"Expected 'kt_sdb', got '{result.kalltyp_id}'"
        )

    def test_sdb_extracts_arkivreferens_identifier(self) -> None:
        """SDB pattern extracts the SDB identifier as arkivreferens."""
        leverantorer, kalltyper = _make_rotter_providers()
        gs = GedcomSource(
            xref_id="@S13@",
            title="Dödsnotis",
            text="SDB3_54321",
        )
        result = map_gedcom_source(gs, [], [], leverantorer=leverantorer, kalltyper=kalltyper)
        assert result.arkivreferens == "SDB3_54321", (
            f"Expected 'SDB3_54321', got '{result.arkivreferens}'"
        )

    def test_parse_reference_sdb_pattern(self) -> None:
        """parse_reference() with SDB pattern returns Rötter.se / Sveriges Dödbok Webb."""
        result = parse_reference("SDB7_12345")
        assert result is not None
        assert result.leverantor_name == "Rötter.se"
        assert result.kalltyp_name == "Sveriges Dödbok Webb"


# ---------------------------------------------------------------------------
# Property 2d: Census pattern correctly assigns Arkiv Digital / Folkräkning
# Validates: Requirements 3.4
# ---------------------------------------------------------------------------


class TestCensusPatternPreservation:
    """**Validates: Requirements 3.4**

    Property: Census pattern rX.pXXXXX correctly produces Leverantör
    "Arkiv Digital" and Källtyp "Folkräkning".

    Observed on UNFIXED code:
    - "r5.p12345" → leverantor_name = "Arkiv Digital", kalltyp_name = "Folkräkning"
    - "r1.p99999" → leverantor_name = "Arkiv Digital", kalltyp_name = "Folkräkning"
    - arkivreferenser contains one entry for "Arkiv Digital" with the full rX.pXXXXX value
    """

    def test_census_basic_pattern(self) -> None:
        """r5.p12345 parses as Arkiv Digital / Folkräkning."""
        result = parse_reference("r5.p12345")
        assert result is not None
        assert result.leverantor_name == "Arkiv Digital"
        assert result.kalltyp_name == "Folkräkning"

    def test_census_single_digit_r(self) -> None:
        """r1.p99999 parses as Arkiv Digital / Folkräkning."""
        result = parse_reference("r1.p99999")
        assert result is not None
        assert result.leverantor_name == "Arkiv Digital"
        assert result.kalltyp_name == "Folkräkning"

    def test_census_multi_digit_r(self) -> None:
        """r12.p456789 parses as Arkiv Digital / Folkräkning."""
        result = parse_reference("r12.p456789")
        assert result is not None
        assert result.leverantor_name == "Arkiv Digital"
        assert result.kalltyp_name == "Folkräkning"

    def test_census_arkivreferenser_populated(self) -> None:
        """Census pattern populates arkivreferenser with the full value."""
        result = parse_reference("r5.p12345")
        assert result is not None
        assert len(result.arkivreferenser) == 1
        assert result.arkivreferenser[0].leverantor_name == "Arkiv Digital"
        assert result.arkivreferenser[0].reference_value == "r5.p12345"

    @given(
        r_digits=st.integers(min_value=1, max_value=99),
        p_digits=st.integers(min_value=10000, max_value=999999),
    )
    @settings(max_examples=50, deadline=None)
    def test_census_pattern_property(self, r_digits: int, p_digits: int) -> None:
        """For any valid rX.pXXXXX census pattern, parse produces Folkräkning."""
        text = f"r{r_digits}.p{p_digits}"
        result = parse_reference(text)
        assert result is not None, f"Census pattern '{text}' should parse"
        assert result.leverantor_name == "Arkiv Digital"
        assert result.kalltyp_name == "Folkräkning"
        assert result.arkivreferens == text


# ---------------------------------------------------------------------------
# Property 2e: Existing full pattern (slash variant) extracts arkivreferenser
# Validates: Requirements 3.2
# ---------------------------------------------------------------------------


class TestFullPatternArkivreferenserPreservation:
    """**Validates: Requirements 3.2**

    Property: The existing full pattern (slash variant) with AID and NAD
    correctly extracts aid_ref and nad_ref into arkivreferenser list with
    2 entries: one for "Arkiv Digital", one for "Nationell Arkivdatabas".

    Observed on UNFIXED code:
    - "Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)"
      → arkivreferenser = [
          ArkivReferens("Arkiv Digital", "v10726.b58.s51"),
          ArkivReferens("Nationell Arkivdatabas", "SE/VA/13090"),
        ]
    - leverantor_name = "Arkiv Digital"
    - kalltyp_name = "Husförhörslängd" (from series "AI")
    """

    def test_full_pattern_extracts_two_arkivreferenser(self) -> None:
        """Full slash pattern produces 2 arkivreferenser entries."""
        text = "Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)"
        result = parse_reference(text)

        assert result is not None, "Full pattern should parse"
        assert len(result.arkivreferenser) == 2

    def test_full_pattern_aid_entry(self) -> None:
        """Full pattern has arkivreferens for 'Arkiv Digital' with AID value."""
        text = "Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)"
        result = parse_reference(text)

        assert result is not None
        aid_entries = [ar for ar in result.arkivreferenser if ar.leverantor_name == "Arkiv Digital"]
        assert len(aid_entries) == 1
        assert aid_entries[0].reference_value == "v10726.b58.s51"

    def test_full_pattern_nad_entry(self) -> None:
        """Full pattern has arkivreferens for 'Nationell Arkivdatabas' with NAD value."""
        text = "Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)"
        result = parse_reference(text)

        assert result is not None
        nad_entries = [ar for ar in result.arkivreferenser if ar.leverantor_name == "Nationell Arkivdatabas"]
        assert len(nad_entries) == 1
        assert nad_entries[0].reference_value == "SE/VA/13090"

    def test_full_pattern_leverantor_and_kalltyp(self) -> None:
        """Full slash pattern assigns leverantor 'Arkiv Digital' and series-derived kalltyp."""
        text = "Ed (S) AI:16 (1866-1870) Bild 58 / sid 51 (AID: v10726.b58.s51, NAD: SE/VA/13090)"
        result = parse_reference(text)

        assert result is not None
        assert result.leverantor_name == "Arkiv Digital"
        assert result.kalltyp_name == "Husförhörslängd"

    def test_full_pattern_different_series(self) -> None:
        """Full pattern with series 'CI' assigns kalltyp 'Födelse- och dopbok'."""
        text = "Sundsvall (Y) CI:5 (1801-1810) Bild 100 / sid 50 (AID: v999.b100.s50, NAD: SE/HA/44444)"
        result = parse_reference(text)

        assert result is not None
        assert result.leverantor_name == "Arkiv Digital"
        assert result.kalltyp_name == "Födelse- och dopbok"
        assert len(result.arkivreferenser) == 2


# ---------------------------------------------------------------------------
# Property 2f: Existing short pattern (AID only) correctly parses
# Validates: Requirements 3.3
# ---------------------------------------------------------------------------


class TestShortPatternPreservation:
    """**Validates: Requirements 3.3**

    Property: The existing short pattern (AID only, no NAD) correctly
    parses with a single arkivreferens entry for "Arkiv Digital".

    Observed on UNFIXED code:
    - "Karlstad (1920) Bild 15 / sid 8 (AID: v5555.b15.s8)"
      → arkivreferenser = [ArkivReferens("Arkiv Digital", "v5555.b15.s8")]
    - leverantor_name = "Arkiv Digital"
    - kalltyp_name = "Övrigt" (no series code in short pattern)
    """

    def test_short_pattern_single_arkivreferens(self) -> None:
        """Short AID-only pattern produces 1 arkivreferens entry."""
        text = "Karlstad (1920) Bild 15 / sid 8 (AID: v5555.b15.s8)"
        result = parse_reference(text)

        assert result is not None, "Short pattern should parse"
        assert len(result.arkivreferenser) == 1
        assert result.arkivreferenser[0].leverantor_name == "Arkiv Digital"
        assert result.arkivreferenser[0].reference_value == "v5555.b15.s8"

    def test_short_pattern_leverantor(self) -> None:
        """Short pattern assigns leverantor 'Arkiv Digital'."""
        text = "Karlstad (1920) Bild 15 / sid 8 (AID: v5555.b15.s8)"
        result = parse_reference(text)

        assert result is not None
        assert result.leverantor_name == "Arkiv Digital"

    def test_short_pattern_kalltyp_ovrigt(self) -> None:
        """Short pattern (no series code) assigns kalltyp 'Övrigt'."""
        text = "Karlstad (1920) Bild 15 / sid 8 (AID: v5555.b15.s8)"
        result = parse_reference(text)

        assert result is not None
        assert result.kalltyp_name == "Övrigt"

    def test_short_pattern_different_description(self) -> None:
        """Short pattern with different description still produces correct arkivreferens."""
        text = "Folkräkning Stockholm (1910) Bild 200 / sid 45 (AID: v1234.b200.s45)"
        result = parse_reference(text)

        assert result is not None
        assert result.leverantor_name == "Arkiv Digital"
        assert result.kalltyp_name == "Övrigt"
        assert len(result.arkivreferenser) == 1
        assert result.arkivreferenser[0].reference_value == "v1234.b200.s45"
