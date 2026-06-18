"""Property-based tests for UI list consistency after DNA creation.

Feature: dna-management-from-person-editor, Property 6: UI list consistency after creation

Validates: Requirements 2.5, 4.5, 5.1, 5.2
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from PySide6.QtWidgets import QApplication

from slaktbusken.model.dna import DnaMatch, DnaProfile
from slaktbusken.model.person import Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.editors.person_editor import PersonEditor
from tests.conftest import dna_match_strategy, dna_profile_strategy, person_strategy


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestUiListConsistencyAfterCreation:
    """Feature: dna-management-from-person-editor, Property 6: UI list consistency after creation

    After creation operations, the profiles list item count SHALL equal the number
    of DnaProfile entries for the current person, and the matches list item count
    SHALL equal the number of DnaMatch entries referencing any of the current
    person's profile IDs.

    **Validates: Requirements 2.5, 4.5, 5.1, 5.2**
    """

    @given(
        person=person_strategy(),
        new_profiles=st.lists(dna_profile_strategy(), min_size=1, max_size=5),
        existing_profiles=st.lists(dna_profile_strategy(), min_size=0, max_size=3),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_profiles_list_count_matches_data_after_creation(
        self, qtbot, person, new_profiles, existing_profiles
    ):
        """After creating profiles and calling refresh, profiles list count matches
        the number of DnaProfile entries for that person.

        Feature: dna-management-from-person-editor, Property 6: UI list consistency after creation
        **Validates: Requirements 2.5, 5.1**
        """
        # Ensure existing_profiles do NOT belong to the person under test
        for p in existing_profiles:
            if p.person_id == person.id:
                p.person_id = person.id + "_other"

        # Assign new_profiles to the person under test
        for p in new_profiles:
            p.person_id = person.id

        # Start with only existing profiles (none belong to person)
        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_profiles=list(existing_profiles),
        )

        editor = PersonEditor(project_data=project_data, person=person)
        qtbot.addWidget(editor)

        # Simulate creation: append each new profile and refresh
        for profile in new_profiles:
            project_data.dna_profiles.append(profile)
            editor._refresh_dna_profiles()

        # Count expected profiles for this person
        expected_count = sum(
            1 for p in project_data.dna_profiles if p.person_id == person.id
        )

        assert editor._ui.dna_profiles_list.count() == expected_count

    @given(
        person=person_strategy(),
        person_profile=dna_profile_strategy(),
        other_profile=dna_profile_strategy(),
        new_matches=st.lists(dna_match_strategy(), min_size=1, max_size=5),
        existing_matches=st.lists(dna_match_strategy(), min_size=0, max_size=3),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_matches_list_count_matches_data_after_creation(
        self, qtbot, person, person_profile, other_profile, new_matches, existing_matches
    ):
        """After creating matches and calling refresh, matches list count matches
        the number of DnaMatch entries referencing the person's profile IDs.

        Feature: dna-management-from-person-editor, Property 6: UI list consistency after creation
        **Validates: Requirements 4.5, 5.2**
        """
        # Set up person_profile to belong to the person
        person_profile.person_id = person.id
        person_profile.id = "person_profile_1"

        # Ensure other_profile does NOT belong to the person
        other_profile.person_id = person.id + "_other"
        other_profile.id = "other_profile_1"

        # Ensure existing_matches don't reference the person's profile
        for m in existing_matches:
            if m.profile1_id == person_profile.id or m.profile2_id == person_profile.id:
                m.profile1_id = "unrelated_profile_a"
                m.profile2_id = "unrelated_profile_b"

        # Make new_matches reference the person's profile (either as profile1 or profile2)
        for m in new_matches:
            m.profile1_id = person_profile.id
            m.profile2_id = other_profile.id

        # Set up project data with both profiles and only existing matches
        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_profiles=[person_profile, other_profile],
            dna_matches=list(existing_matches),
        )

        editor = PersonEditor(project_data=project_data, person=person)
        qtbot.addWidget(editor)

        # Simulate creation: append each new match and refresh
        for match in new_matches:
            project_data.dna_matches.append(match)
            editor._refresh_dna_matches()

        # Compute expected: all matches referencing any of the person's profile IDs
        person_profile_ids = {
            p.id for p in project_data.dna_profiles if p.person_id == person.id
        }
        expected_count = sum(
            1
            for m in project_data.dna_matches
            if m.profile1_id in person_profile_ids or m.profile2_id in person_profile_ids
        )

        assert editor._ui.dna_matches_list.count() == expected_count
