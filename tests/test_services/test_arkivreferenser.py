"""Unit tests for multi-provider arkivreferenser.

Tests cover parsing of reference strings that produce multiple ArkivReferens
entries and round-trip persistence through JSON serialization.

Requirements: 13.2, 13.3, 13.5
"""

from __future__ import annotations

from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.source import ArkivReferens, Source
from slaktbusken.parsing.reference_parser import parse_reference
from slaktbusken.persistence.serialization import deserialize, serialize


class TestFullPatternArkivreferenser:
    """Tests for full Arkiv Digital pattern producing multiple arkivreferenser."""

    def test_full_pattern_produces_two_arkivreferenser(self) -> None:
        """Full pattern with AID and NAD produces 2 arkivreferens entries."""
        text = "Ed (S) AI:16 (1866-1870) Bild 53 / sid 46 (AID: v10726.b53.s46, NAD: SE/VA/13090)"
        result = parse_reference(text)
        assert result is not None
        assert len(result.arkivreferenser) == 2
        assert result.arkivreferenser[0].leverantor_name == "Arkiv Digital"
        assert result.arkivreferenser[0].reference_value == "v10726.b53.s46"
        assert result.arkivreferenser[1].leverantor_name == "Nationell Arkivdatabas"
        assert result.arkivreferenser[1].reference_value == "SE/VA/13090"


class TestShortPatternArkivreferenser:
    """Tests for short Arkiv Digital pattern producing a single arkivreferens."""

    def test_short_pattern_produces_one_arkivreferens(self) -> None:
        """Short pattern with only AID produces 1 arkivreferens entry."""
        text = "Norra Vi kyrka (1871) Bild 15 / sid 12 (AID: v12345.b15.s12)"
        result = parse_reference(text)
        assert result is not None
        assert len(result.arkivreferenser) == 1
        assert result.arkivreferenser[0].leverantor_name == "Arkiv Digital"
        assert result.arkivreferenser[0].reference_value == "v12345.b15.s12"


class TestCensusPatternArkivreferenser:
    """Tests for census pattern producing a single arkivreferens."""

    def test_census_pattern_produces_one_arkivreferens(self) -> None:
        """Census pattern (rX.pXXXXX) produces 1 arkivreferens entry."""
        result = parse_reference("r5.p12345")
        assert result is not None
        assert len(result.arkivreferenser) == 1
        assert result.arkivreferenser[0].leverantor_name == "Arkiv Digital"
        assert result.arkivreferenser[0].reference_value == "r5.p12345"


class TestSdbPatternArkivreferenser:
    """Tests for Rötter.se SDB pattern producing a single arkivreferens."""

    def test_sdb_pattern_produces_one_arkivreferens(self) -> None:
        """SDB identifier produces 1 arkivreferens entry for Rötter.se."""
        result = parse_reference("SDB7_12345")
        assert result is not None
        assert len(result.arkivreferenser) == 1
        assert result.arkivreferenser[0].leverantor_name == "Rötter.se"
        assert result.arkivreferenser[0].reference_value == "SDB7_12345"


class TestBildColonNoArkivreferenser:
    """Tests for Bild colon pattern which has no AID/NAD."""

    def test_bild_colon_pattern_no_arkivreferenser(self) -> None:
        """Bild colon pattern without AID/NAD produces no arkivreferenser."""
        text = "Karlstads stadsförsamling (S) AIIa:7 (1906-1910) Bild: 350 Sida: 21"
        result = parse_reference(text)
        assert result is not None
        assert len(result.arkivreferenser) == 0


class TestArkivreferenserRoundTrip:
    """Tests for round-trip serialization/deserialization of arkivreferenser."""

    def test_arkivreferenser_round_trip_persistence(self) -> None:
        """Serialize Source with arkivreferenser, deserialize, and verify data intact."""
        source = Source(
            id="src-1",
            provider="Test",
            source_type="other",
            title="Test",
            arkivreferenser=[
                ArkivReferens(leverantor_name="Arkiv Digital", reference_value="v10726.b53.s46"),
                ArkivReferens(leverantor_name="Nationell Arkivdatabas", reference_value="SE/VA/13090"),
            ],
        )
        project = ProjectData(project=ProjectMetadata(title="Test"), sources=[source])
        json_str = serialize(project)
        loaded = deserialize(json_str)
        assert len(loaded.sources[0].arkivreferenser) == 2
        assert loaded.sources[0].arkivreferenser[0].leverantor_name == "Arkiv Digital"
        assert loaded.sources[0].arkivreferenser[0].reference_value == "v10726.b53.s46"
        assert loaded.sources[0].arkivreferenser[1].leverantor_name == "Nationell Arkivdatabas"
        assert loaded.sources[0].arkivreferenser[1].reference_value == "SE/VA/13090"
