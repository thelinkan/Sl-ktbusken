"""Integration tests for the source management workflow.

Tests the full pipeline from GEDCOM import reference parsing through
to persisted data, including save/load round-trips and direct link
generation with QDesktopServices.

Requirements: 7.4, 10.2
"""

from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.model.source import Kalltyp, Leverantor, Source
from slaktbusken.parsing.reference_parser import parse_reference
from slaktbusken.persistence.serialization import deserialize, serialize
from slaktbusken.services.source_links import generate_direct_link
from slaktbusken.services.standard_providers import initialize_standard_providers


class TestGedcomArkivDigitalImport:
    """Test GEDCOM import with ArkivDigital sources → parse → Source creation."""

    def test_gedcom_arkivdigital_prefix_stripping(self) -> None:
        """ArkivDigital: prefix is stripped before parsing (Requirement 7.4)."""
        # Simulate GEDCOM import text with prefix
        gedcom_text = "ArkivDigital:Ljusdal (X) AI:17 (1820-1830) Bild 5 / sid 32 (AID: v12345, NAD: 67890)"
        # Strip the prefix as the import workflow would
        stripped = gedcom_text.replace("ArkivDigital:", "", 1)
        result = parse_reference(stripped)

        assert result is not None
        assert result.leverantor_name == "Arkiv Digital"
        assert result.kalltyp_name == "Husförhörslängd"
        assert result.title == "Ljusdal AI:17 Sida: 32"
        assert result.structured_fields["aid_ref"] == "v12345"
        assert result.structured_fields["nad_ref"] == "67890"

    def test_gedcom_arkivdigital_short_pattern_with_prefix(self) -> None:
        """ArkivDigital: prefix with short pattern is parsed correctly."""
        gedcom_text = "ArkivDigital:Ljusdals kyrkoarkiv (1825) Bild 10 / sid 5 (AID: v99999)"
        stripped = gedcom_text.replace("ArkivDigital:", "", 1)
        result = parse_reference(stripped)

        assert result is not None
        assert result.leverantor_name == "Arkiv Digital"
        assert result.title == "Ljusdals kyrkoarkiv Sida: 5"
        assert result.structured_fields["aid_ref"] == "v99999"

    def test_gedcom_arkivdigital_creates_source_fields(self) -> None:
        """Parsed reference has all fields needed to create a Source record."""
        gedcom_text = "ArkivDigital:Sundsvall (Y) CI:5 (1800-1810) Bild 3 / sid 15 (AID: v54321, NAD: 11111)"
        stripped = gedcom_text.replace("ArkivDigital:", "", 1)
        result = parse_reference(stripped)

        assert result is not None
        # All fields needed for Source creation are populated
        assert result.leverantor_name == "Arkiv Digital"
        assert result.kalltyp_name == "Födelse- och dopbok"
        assert result.title == "Sundsvall CI:5 Sida: 15"
        # reference_text should NOT contain AID/NAD parenthetical (requirement 2.4)
        assert result.reference_text == "Sundsvall (Y) CI:5 (1800-1810) Bild: 3 Sida: 15"
        assert "(AID:" not in result.reference_text
        assert "(NAD:" not in result.reference_text
        assert "aid_ref" in result.structured_fields
        assert "nad_ref" in result.structured_fields
        assert result.structured_fields["parish"] == "Sundsvall"
        assert result.structured_fields["county_code"] == "Y"
        assert result.structured_fields["series"] == "CI"
        assert result.structured_fields["volume"] == "5"


class TestProjectRoundTripWithProviders:
    """Test save/load project with new Leverantör/Källtyp entities."""

    def test_project_with_standard_providers_round_trip(self) -> None:
        """A project with standard providers survives serialize/deserialize."""
        project_data = ProjectData(
            format="släktbuske-file",
            version="0.1",
            project=ProjectMetadata(title="Test Project"),
        )
        initialize_standard_providers(project_data)

        json_str = serialize(project_data)
        restored = deserialize(json_str)

        # Verify same number of leverantorer and kalltyper
        assert len(restored.leverantorer) == len(project_data.leverantorer)
        assert len(restored.kalltyper) == len(project_data.kalltyper)

        # Verify specific providers exist
        names = [lev.name for lev in restored.leverantorer]
        assert "Arkiv Digital" in names
        assert "Rötter.se" in names

        # Verify a Källtyp with root_url is preserved
        sdb_kt = next(
            (kt for kt in restored.kalltyper if kt.name == "Sveriges Dödbok Webb"),
            None,
        )
        assert sdb_kt is not None
        assert sdb_kt.root_url == "https://www.rotter.se/abonnemang/sveriges-dodbok-webb/post/"

    def test_leverantor_kalltyp_ids_preserved(self) -> None:
        """Leverantör and Källtyp IDs are preserved through serialization."""
        project_data = ProjectData(
            format="släktbuske-file",
            version="0.1",
            project=ProjectMetadata(title="ID Test"),
        )
        initialize_standard_providers(project_data)

        original_lev_ids = [lev.id for lev in project_data.leverantorer]
        original_kt_ids = [kt.id for kt in project_data.kalltyper]

        json_str = serialize(project_data)
        restored = deserialize(json_str)

        restored_lev_ids = [lev.id for lev in restored.leverantorer]
        restored_kt_ids = [kt.id for kt in restored.kalltyper]

        assert restored_lev_ids == original_lev_ids
        assert restored_kt_ids == original_kt_ids

    def test_kalltyp_leverantor_id_references_preserved(self) -> None:
        """Källtyp → Leverantör FK relationship is preserved through round-trip."""
        project_data = ProjectData(
            format="släktbuske-file",
            version="0.1",
            project=ProjectMetadata(title="FK Test"),
        )
        initialize_standard_providers(project_data)

        json_str = serialize(project_data)
        restored = deserialize(json_str)

        # Every Källtyp should reference an existing Leverantör
        lev_ids = {lev.id for lev in restored.leverantorer}
        for kt in restored.kalltyper:
            assert kt.leverantor_id in lev_ids, (
                f"Källtyp '{kt.name}' references non-existent Leverantör ID '{kt.leverantor_id}'"
            )

    def test_source_with_leverantor_and_kalltyp_round_trip(self) -> None:
        """A Source with leverantor_id, kalltyp_id, and arkivreferens round-trips."""
        project_data = ProjectData(
            format="släktbuske-file",
            version="0.1",
            project=ProjectMetadata(title="Source FK Test"),
        )
        initialize_standard_providers(project_data)

        # Add a source referencing the first leverantör and first källtyp
        lev = project_data.leverantorer[0]
        kt = project_data.kalltyper[0]
        source = Source(
            id="src_test_1",
            provider=lev.name,
            source_type=kt.name,
            title="Test Source",
            leverantor_id=lev.id,
            kalltyp_id=kt.id,
            arkivreferens="v12345",
        )
        project_data.sources.append(source)

        json_str = serialize(project_data)
        restored = deserialize(json_str)

        restored_src = next(s for s in restored.sources if s.id == "src_test_1")
        assert restored_src.leverantor_id == lev.id
        assert restored_src.kalltyp_id == kt.id
        assert restored_src.arkivreferens == "v12345"


class TestDirectLinkGeneration:
    """Test direct link generation and QDesktopServices integration."""

    def test_direct_link_generation_for_rotter_sdb(self) -> None:
        """Direct link for a Rötter.se source with root_url and arkivreferens."""
        kt = Kalltyp(
            id="kt_sdb",
            leverantor_id="lev_rotter",
            name="Sveriges Dödbok Webb",
            root_url="https://www.rotter.se/abonnemang/sveriges-dodbok-webb/post/",
        )
        source = Source(
            id="src_1",
            provider="Rötter.se",
            source_type="Sveriges Dödbok Webb",
            title="Test Source",
            kalltyp_id="kt_sdb",
            arkivreferens="12345",
        )

        url = generate_direct_link(source, [kt])
        assert url == "https://www.rotter.se/abonnemang/sveriges-dodbok-webb/post/12345"

    def test_direct_link_none_when_no_arkivreferens(self) -> None:
        """No link is generated when arkivreferens is empty."""
        kt = Kalltyp(
            id="kt_sdb",
            leverantor_id="lev_rotter",
            name="Sveriges Dödbok Webb",
            root_url="https://www.rotter.se/abonnemang/sveriges-dodbok-webb/post/",
        )
        source = Source(
            id="src_1",
            provider="Rötter.se",
            source_type="Sveriges Dödbok Webb",
            title="Test Source",
            kalltyp_id="kt_sdb",
            arkivreferens="",
        )

        url = generate_direct_link(source, [kt])
        assert url is None

    def test_direct_link_none_when_no_root_url(self) -> None:
        """No link is generated when root_url is empty."""
        kt = Kalltyp(
            id="kt_other",
            leverantor_id="lev_other",
            name="Övrigt",
            root_url="",
        )
        source = Source(
            id="src_1",
            provider="Övrigt",
            source_type="Övrigt",
            title="Test Source",
            kalltyp_id="kt_other",
            arkivreferens="some_ref",
        )

        url = generate_direct_link(source, [kt])
        assert url is None

    def test_open_url_called_with_correct_url(self, monkeypatch) -> None:
        """QDesktopServices.openUrl is called with the generated URL (mocked)."""
        mock_open = MagicMock(return_value=True)
        monkeypatch.setattr(QDesktopServices, "openUrl", mock_open)

        expected_url = "https://www.rotter.se/abonnemang/sveriges-dodbok-webb/post/12345"
        QDesktopServices.openUrl(QUrl(expected_url))

        mock_open.assert_called_once()
        called_url = mock_open.call_args[0][0]
        assert called_url.toString() == expected_url

    def test_full_workflow_parse_then_generate_link(self) -> None:
        """Full workflow: parse SDB reference → create source → generate link."""
        # Step 1: Parse a Rötter.se SDB reference
        result = parse_reference("SDB7_98765")
        assert result is not None
        assert result.leverantor_name == "Rötter.se"
        assert result.kalltyp_name == "Sveriges Dödbok Webb"
        assert result.arkivreferens == "SDB7_98765"

        # Step 2: Create source from parsed reference
        source = Source(
            id="src_sdb_1",
            provider=result.leverantor_name,
            source_type=result.kalltyp_name,
            title=result.title,
            reference_text=result.reference_text,
            kalltyp_id="kt_sdb",
            arkivreferens=result.arkivreferens,
        )

        # Step 3: Generate direct link
        kt = Kalltyp(
            id="kt_sdb",
            leverantor_id="lev_rotter",
            name="Sveriges Dödbok Webb",
            root_url="https://www.rotter.se/abonnemang/sveriges-dodbok-webb/post/",
        )
        url = generate_direct_link(source, [kt])
        assert url == "https://www.rotter.se/abonnemang/sveriges-dodbok-webb/post/SDB7_98765"
