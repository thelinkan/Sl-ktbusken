"""Property-based tests for DNA icon resolution public API.

Feature: dna-tab-enhancements

Tests correctness properties for resolve_profile_logo_icon and
resolve_company_logo_icon — the public API functions that map
DnaProfile/DnaMatch entities to QIcon results.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5**
"""

from __future__ import annotations

import uuid
from pathlib import Path

from hypothesis import assume, given, settings, HealthCheck
from hypothesis import strategies as st
from PySide6.QtGui import QIcon, QPixmap

from slaktbusken.model.dna import DnaCompany, DnaMatch, DnaProfile
from slaktbusken.model.media import MediaItem
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.editors.dna_editor import (
    LOGO_ICON_SIZE,
    resolve_company_logo_icon,
    resolve_profile_logo_icon,
)

from tests.conftest import (
    dna_company_strategy,
    dna_match_strategy,
    dna_profile_strategy,
    media_item_strategy,
    project_data_strategy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_project_data() -> ProjectData:
    """Return a minimal empty ProjectData."""
    return ProjectData(
        format="släktbuske-file",
        version="0.1",
        project=ProjectMetadata(
            title="Test", main_person_id=None, created_by="test", language="sv-SE"
        ),
        persons=[],
        families=[],
        events=[],
        places=[],
        sources=[],
        media=[],
        repositories=[],
        dna_companies=[],
        dna_profiles=[],
        dna_matches=[],
        dna_segments=[],
        dna_clusters=[],
        dna_triangulations=[],
        research_notes=[],
    )


def _make_logo_media_item(rel_path: str) -> MediaItem:
    """Create a MediaItem with a specific relative file path."""
    return MediaItem(
        id=str(uuid.uuid4()),
        type="logo",
        file=rel_path,
        title="Logo",
    )


# ---------------------------------------------------------------------------
# Property 1: Profile icon resolution correctness
# ---------------------------------------------------------------------------


class TestProfileIconResolution:
    """Feature: dna-tab-enhancements, Property 1: Profile icon resolution correctness"""

    @given(profile=dna_profile_strategy(), project_data=project_data_strategy())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_never_raises_and_returns_qicon(
        self, profile: DnaProfile, project_data: ProjectData, tmp_path: Path
    ) -> None:
        """For any DnaProfile and project data, resolve_profile_logo_icon
        never raises an exception and always returns a QIcon.

        Feature: dna-tab-enhancements, Property 1: Profile icon resolution correctness
        **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
        """
        result = resolve_profile_logo_icon(profile, project_data, tmp_path)
        assert isinstance(result, QIcon)

    @given(profile=dna_profile_strategy(), project_data=project_data_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_none_project_folder_returns_empty_icon(
        self, profile: DnaProfile, project_data: ProjectData
    ) -> None:
        """When project_folder is None, returns an empty (null) QIcon.

        Feature: dna-tab-enhancements, Property 1: Profile icon resolution correctness
        **Validates: Requirements 1.2**
        """
        result = resolve_profile_logo_icon(profile, project_data, None)
        assert isinstance(result, QIcon)
        assert result.isNull()

    @given(profile=dna_profile_strategy())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_company_not_in_project_returns_empty_icon(
        self, profile: DnaProfile, tmp_path: Path
    ) -> None:
        """When the company_id doesn't match any DnaCompany in project_data,
        returns an empty (null) QIcon.

        Feature: dna-tab-enhancements, Property 1: Profile icon resolution correctness
        **Validates: Requirements 1.2**
        """
        # Empty project data — no companies
        project_data = _empty_project_data()
        result = resolve_profile_logo_icon(profile, project_data, tmp_path)
        assert isinstance(result, QIcon)
        assert result.isNull()

    @given(company=dna_company_strategy())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_company_no_logo_media_id_returns_empty_icon(
        self, company: DnaCompany, tmp_path: Path
    ) -> None:
        """When the company has no logo_media_id (None), returns empty QIcon.

        Feature: dna-tab-enhancements, Property 1: Profile icon resolution correctness
        **Validates: Requirements 1.2**
        """
        # Force no logo
        company.logo_media_id = None

        profile = DnaProfile(
            id="dnaprofile_1",
            person_id="person_1",
            company_id=company.id,
            test_type="autosomal",
            kit_name="",
            kit_id="",
            admin_person_id=None,
            admin_status="",
            notes="",
        )

        project_data = _empty_project_data()
        project_data.dna_companies = [company]

        result = resolve_profile_logo_icon(profile, project_data, tmp_path)
        assert isinstance(result, QIcon)
        assert result.isNull()

    @given(company=dna_company_strategy())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_media_item_not_found_returns_empty_icon(
        self, company: DnaCompany, tmp_path: Path
    ) -> None:
        """When company has a logo_media_id but the MediaItem is not in project,
        returns empty QIcon.

        Feature: dna-tab-enhancements, Property 1: Profile icon resolution correctness
        **Validates: Requirements 1.2**
        """
        # Ensure logo_media_id is set but no matching MediaItem exists
        company.logo_media_id = "media_9999"

        profile = DnaProfile(
            id="dnaprofile_1",
            person_id="person_1",
            company_id=company.id,
            test_type="autosomal",
            kit_name="",
            kit_id="",
            admin_person_id=None,
            admin_status="",
            notes="",
        )

        project_data = _empty_project_data()
        project_data.dna_companies = [company]
        # No media items at all
        project_data.media = []

        result = resolve_profile_logo_icon(profile, project_data, tmp_path)
        assert isinstance(result, QIcon)
        assert result.isNull()

    def test_file_path_resolves_but_missing_returns_missing_icon(
        self, tmp_path: Path, qapp
    ) -> None:
        """When file path resolves but file doesn't exist on disk,
        returns a non-null QIcon (the missing-file indicator).

        Feature: dna-tab-enhancements, Property 1: Profile icon resolution correctness
        **Validates: Requirements 1.3**
        """
        media_item = _make_logo_media_item("logos/nonexistent.png")
        company = DnaCompany(
            id="dnacompany_1",
            name="TestCo",
            logo_media_id=media_item.id,
            description="",
        )
        profile = DnaProfile(
            id="dnaprofile_1",
            person_id="person_1",
            company_id=company.id,
            test_type="autosomal",
            kit_name="",
            kit_id="",
            admin_person_id=None,
            admin_status="",
            notes="",
        )

        project_data = _empty_project_data()
        project_data.dna_companies = [company]
        project_data.media = [media_item]

        # tmp_path exists but logos/nonexistent.png does NOT exist
        result = resolve_profile_logo_icon(profile, project_data, tmp_path)
        assert isinstance(result, QIcon)
        # The missing-file icon is NOT null — it has a red X pixmap
        assert not result.isNull()

    def test_valid_file_on_disk_returns_scaled_icon(self, tmp_path: Path, qapp) -> None:
        """When logo file exists on disk, returns a non-null scaled QIcon.

        Feature: dna-tab-enhancements, Property 1: Profile icon resolution correctness
        **Validates: Requirements 1.1, 1.4**
        """
        # Create an actual image file on disk
        logos_dir = tmp_path / "logos"
        logos_dir.mkdir()
        logo_file = logos_dir / "company_logo.png"
        # Create a minimal valid PNG-like image via QPixmap
        pixmap = QPixmap(48, 48)
        pixmap.fill()
        pixmap.save(str(logo_file), "PNG")

        media_item = _make_logo_media_item("logos/company_logo.png")
        company = DnaCompany(
            id="dnacompany_1",
            name="TestCo",
            logo_media_id=media_item.id,
            description="",
        )
        profile = DnaProfile(
            id="dnaprofile_1",
            person_id="person_1",
            company_id=company.id,
            test_type="autosomal",
            kit_name="",
            kit_id="",
            admin_person_id=None,
            admin_status="",
            notes="",
        )

        project_data = _empty_project_data()
        project_data.dna_companies = [company]
        project_data.media = [media_item]

        result = resolve_profile_logo_icon(profile, project_data, tmp_path)
        assert isinstance(result, QIcon)
        assert not result.isNull()


# ---------------------------------------------------------------------------
# Property 2: Match icon resolution correctness
# ---------------------------------------------------------------------------


class TestMatchIconResolution:
    """Feature: dna-tab-enhancements, Property 2: Match icon resolution correctness"""

    @given(match=dna_match_strategy(), project_data=project_data_strategy())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_never_raises_and_returns_qicon(
        self, match: DnaMatch, project_data: ProjectData, tmp_path: Path
    ) -> None:
        """For any DnaMatch and project data, resolve_company_logo_icon
        never raises an exception and always returns a QIcon.

        Feature: dna-tab-enhancements, Property 2: Match icon resolution correctness
        **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**
        """
        result = resolve_company_logo_icon(match, project_data, tmp_path)
        assert isinstance(result, QIcon)

    @given(match=dna_match_strategy(), project_data=project_data_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_none_project_folder_returns_empty_icon(
        self, match: DnaMatch, project_data: ProjectData
    ) -> None:
        """When project_folder is None, returns an empty (null) QIcon.

        Feature: dna-tab-enhancements, Property 2: Match icon resolution correctness
        **Validates: Requirements 2.3**
        """
        result = resolve_company_logo_icon(match, project_data, None)
        assert isinstance(result, QIcon)
        assert result.isNull()

    @given(match=dna_match_strategy())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_profile2_not_found_returns_empty_icon(
        self, match: DnaMatch, tmp_path: Path
    ) -> None:
        """When profile2_id doesn't reference a real profile in project_data,
        returns an empty (null) QIcon.

        Feature: dna-tab-enhancements, Property 2: Match icon resolution correctness
        **Validates: Requirements 2.3**
        """
        # Empty project data — no profiles
        project_data = _empty_project_data()
        result = resolve_company_logo_icon(match, project_data, tmp_path)
        assert isinstance(result, QIcon)
        assert result.isNull()

    @given(match=dna_match_strategy(), company=dna_company_strategy())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    )
    def test_company_no_logo_returns_empty_icon(
        self, match: DnaMatch, company: DnaCompany, tmp_path: Path
    ) -> None:
        """When the profile2 → company chain resolves but company has no
        logo_media_id, returns empty QIcon.

        Feature: dna-tab-enhancements, Property 2: Match icon resolution correctness
        **Validates: Requirements 2.3**
        """
        company.logo_media_id = None

        # Create a profile2 that the match references
        profile2 = DnaProfile(
            id=match.profile2_id,
            person_id="person_1",
            company_id=company.id,
            test_type="autosomal",
            kit_name="",
            kit_id="",
            admin_person_id=None,
            admin_status="",
            notes="",
        )

        project_data = _empty_project_data()
        project_data.dna_profiles = [profile2]
        project_data.dna_companies = [company]

        result = resolve_company_logo_icon(match, project_data, tmp_path)
        assert isinstance(result, QIcon)
        assert result.isNull()

    def test_file_path_resolves_but_missing_returns_missing_icon(
        self, tmp_path: Path, qapp
    ) -> None:
        """When the full chain resolves but the file doesn't exist on disk,
        returns a non-null QIcon (the missing-file indicator).

        Feature: dna-tab-enhancements, Property 2: Match icon resolution correctness
        **Validates: Requirements 2.4**
        """
        media_item = _make_logo_media_item("logos/missing.png")
        company = DnaCompany(
            id="dnacompany_1",
            name="TestCo",
            logo_media_id=media_item.id,
            description="",
        )
        profile2 = DnaProfile(
            id="dnaprofile_2",
            person_id="person_2",
            company_id=company.id,
            test_type="autosomal",
            kit_name="",
            kit_id="",
            admin_person_id=None,
            admin_status="",
            notes="",
        )
        match = DnaMatch(
            id="dnamatch_1",
            profile1_id="dnaprofile_1",
            profile2_id=profile2.id,
            shared_cm=50.0,
            shared_percentage=1.0,
            segment_count=3,
            largest_segment_cm=20.0,
            match_source="internal",
            notes="",
        )

        project_data = _empty_project_data()
        project_data.dna_companies = [company]
        project_data.dna_profiles = [profile2]
        project_data.media = [media_item]

        # tmp_path exists but logos/missing.png does NOT exist
        result = resolve_company_logo_icon(match, project_data, tmp_path)
        assert isinstance(result, QIcon)
        assert not result.isNull()

    def test_valid_file_on_disk_returns_scaled_icon(self, tmp_path: Path, qapp) -> None:
        """When the full chain resolves and the file exists on disk,
        returns a non-null scaled QIcon.

        Feature: dna-tab-enhancements, Property 2: Match icon resolution correctness
        **Validates: Requirements 2.1, 2.2**
        """
        # Create an actual image file on disk
        logos_dir = tmp_path / "logos"
        logos_dir.mkdir()
        logo_file = logos_dir / "match_logo.png"
        pixmap = QPixmap(48, 48)
        pixmap.fill()
        pixmap.save(str(logo_file), "PNG")

        media_item = _make_logo_media_item("logos/match_logo.png")
        company = DnaCompany(
            id="dnacompany_1",
            name="TestCo",
            logo_media_id=media_item.id,
            description="",
        )
        profile2 = DnaProfile(
            id="dnaprofile_2",
            person_id="person_2",
            company_id=company.id,
            test_type="autosomal",
            kit_name="",
            kit_id="",
            admin_person_id=None,
            admin_status="",
            notes="",
        )
        match = DnaMatch(
            id="dnamatch_1",
            profile1_id="dnaprofile_1",
            profile2_id=profile2.id,
            shared_cm=50.0,
            shared_percentage=1.0,
            segment_count=3,
            largest_segment_cm=20.0,
            match_source="internal",
            notes="",
        )

        project_data = _empty_project_data()
        project_data.dna_companies = [company]
        project_data.dna_profiles = [profile2]
        project_data.media = [media_item]

        result = resolve_company_logo_icon(match, project_data, tmp_path)
        assert isinstance(result, QIcon)
        assert not result.isNull()

    def test_corrupt_image_returns_empty_icon(self, tmp_path: Path, qapp) -> None:
        """When the logo file exists but cannot be loaded (corrupt),
        returns an empty (null) QIcon.

        Feature: dna-tab-enhancements, Property 2: Match icon resolution correctness
        **Validates: Requirements 2.5**
        """
        # Create a corrupt file that's not a valid image
        logos_dir = tmp_path / "logos"
        logos_dir.mkdir()
        logo_file = logos_dir / "corrupt.png"
        logo_file.write_bytes(b"not a valid image file content")

        media_item = _make_logo_media_item("logos/corrupt.png")
        company = DnaCompany(
            id="dnacompany_1",
            name="TestCo",
            logo_media_id=media_item.id,
            description="",
        )
        profile2 = DnaProfile(
            id="dnaprofile_2",
            person_id="person_2",
            company_id=company.id,
            test_type="autosomal",
            kit_name="",
            kit_id="",
            admin_person_id=None,
            admin_status="",
            notes="",
        )
        match = DnaMatch(
            id="dnamatch_1",
            profile1_id="dnaprofile_1",
            profile2_id=profile2.id,
            shared_cm=50.0,
            shared_percentage=1.0,
            segment_count=3,
            largest_segment_cm=20.0,
            match_source="internal",
            notes="",
        )

        project_data = _empty_project_data()
        project_data.dna_companies = [company]
        project_data.dna_profiles = [profile2]
        project_data.media = [media_item]

        result = resolve_company_logo_icon(match, project_data, tmp_path)
        assert isinstance(result, QIcon)
        assert result.isNull()
