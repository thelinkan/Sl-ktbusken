"""Property-based tests for DNA match button enabled invariant.

Feature: dna-management-from-person-editor, Property 7: Match button enabled invariant

Validates: Requirements 3.4, 5.3
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from PySide6.QtWidgets import QApplication

from slaktbusken.model.dna import DnaProfile
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.editors.person_editor import PersonEditor
from tests.conftest import dna_profile_strategy, person_strategy


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


_DISABLED_TOOLTIP = "En DNA-profil krävs för att skapa matchningar"


class TestMatchButtonEnabledInvariant:
    """Feature: dna-management-from-person-editor, Property 7: Match button enabled invariant

    For any person loaded in the editor, the match button SHALL be enabled
    iff the person has at least one DnaProfile. When enabled, tooltip is empty;
    when disabled, tooltip is the Swedish message.

    **Validates: Requirements 3.4, 5.3**
    """

    @given(
        person=person_strategy(),
        profiles=st.lists(dna_profile_strategy(), min_size=0, max_size=5),
        has_own_profile=st.booleans(),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_match_button_enabled_iff_person_has_profile(
        self, qtbot, person, profiles, has_own_profile
    ):
        """Match button SHALL be enabled iff person has at least one DnaProfile.

        Feature: dna-management-from-person-editor, Property 7: Match button enabled invariant
        **Validates: Requirements 3.4, 5.3**
        """
        # Ensure no generated profiles belong to the person under test
        for p in profiles:
            if p.person_id == person.id:
                p.person_id = person.id + "_other"

        # Optionally add a profile belonging to the person
        if has_own_profile:
            own_profile = DnaProfile(
                id="own_profile_1",
                person_id=person.id,
                company_id="company_1",
                test_type="autosomal",
                kit_name="Test Kit",
                kit_id="KIT001",
            )
            profiles.append(own_profile)

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_profiles=profiles,
        )

        editor = PersonEditor(project_data=project_data, person=person)
        qtbot.addWidget(editor)

        # Check invariant: button enabled iff person has at least one profile
        expected_enabled = has_own_profile
        assert editor._add_dna_match_button.isEnabled() == expected_enabled

        # Check tooltip invariant
        if expected_enabled:
            assert editor._add_dna_match_button.toolTip() == ""
        else:
            assert editor._add_dna_match_button.toolTip() == _DISABLED_TOOLTIP
