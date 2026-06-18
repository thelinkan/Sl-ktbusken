"""Property-based tests for cancel preserving project data.

Feature: dna-management-from-person-editor, Property 5: Cancel preserves project data

Validates: Requirements 2.7, 4.9
"""

from __future__ import annotations

import copy

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from PySide6.QtWidgets import QApplication

from slaktbusken.model.dna import DnaCompany, DnaProfile
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.dialogs.dna_profile_dialog import DnaProfileDialog
from slaktbusken.ui.dialogs.dna_match_dialog import DnaMatchDialog
from tests.conftest import dna_company_strategy


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestCancelPreservesProjectData:
    """Feature: dna-management-from-person-editor, Property 5: Cancel preserves project data

    For any ProjectData state, opening and then canceling either the profile dialog
    or the match dialog SHALL result in ProjectData being unchanged (same number of
    profiles and matches, identical content).

    **Validates: Requirements 2.7, 4.9**
    """

    @given(
        company=dna_company_strategy(),
        person_id=st.integers(min_value=1, max_value=9999).map(lambda n: f"person_{n}"),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_cancel_profile_dialog_preserves_profiles(self, qtbot, company, person_id):
        """Canceling the profile dialog SHALL NOT modify ProjectData.dna_profiles.

        Feature: dna-management-from-person-editor, Property 5: Cancel preserves project data
        **Validates: Requirements 2.7**
        """
        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=[company],
        )
        original_profiles = list(project_data.dna_profiles)

        dialog = DnaProfileDialog(project_data, person_id)
        qtbot.addWidget(dialog)
        dialog.reject()

        assert project_data.dna_profiles == original_profiles
        assert dialog.created_profile is None

    @given(
        person_id=st.integers(min_value=1, max_value=9999).map(lambda n: f"person_{n}"),
        other_person_id=st.integers(min_value=10000, max_value=19999).map(lambda n: f"person_{n}"),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_cancel_match_dialog_preserves_matches(self, qtbot, person_id, other_person_id):
        """Canceling the match dialog SHALL NOT modify ProjectData.dna_matches.

        Feature: dna-management-from-person-editor, Property 5: Cancel preserves project data
        **Validates: Requirements 4.9**
        """
        # Create project data with profiles for both persons so the dialog is usable
        company = DnaCompany(id="company_1", name="TestDNA")
        profile1 = DnaProfile(
            id="profile_1",
            person_id=person_id,
            company_id="company_1",
            test_type="autosomal",
            kit_name="",
            kit_id="",
            notes="",
        )
        profile2 = DnaProfile(
            id="profile_2",
            person_id=other_person_id,
            company_id="company_1",
            test_type="autosomal",
            kit_name="",
            kit_id="",
            notes="",
        )

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=[company],
            dna_profiles=[profile1, profile2],
        )
        original_matches = list(project_data.dna_matches)

        dialog = DnaMatchDialog(project_data, person_id)
        qtbot.addWidget(dialog)
        dialog.reject()

        assert project_data.dna_matches == original_matches
        assert dialog.created_match is None
