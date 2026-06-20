"""Property-based tests for match edit and same-company filtering.

Feature: dna-tab-enhancements, Properties 3–8

Validates: Requirements 4.1, 4.2, 4.4, 4.6, 4.7, 5.1, 5.2, 5.3
"""

from __future__ import annotations

import copy

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from PySide6.QtWidgets import QApplication

from slaktbusken.model.dna import DnaCompany, DnaMatch, DnaProfile
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.dialogs.dna_match_dialog import DnaMatchDialog
from slaktbusken.ui.editors.person_editor import PersonEditor
from tests.conftest import dna_company_strategy, dna_match_strategy, dna_profile_strategy


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# Local strategies
# ---------------------------------------------------------------------------

_person_id_strategy = st.integers(min_value=1, max_value=9999).map(
    lambda n: f"person_{n}"
)

_shared_cm_strategy = st.floats(min_value=0.01, max_value=10000.00, allow_nan=False)

_shared_pct_strategy = st.floats(min_value=0.00, max_value=100.00, allow_nan=False)

_segment_count_strategy = st.integers(min_value=0, max_value=100000)

_largest_segment_strategy = st.floats(min_value=0.00, max_value=10000.00, allow_nan=False)

_match_source_strategy = st.text(
    alphabet=st.characters(categories=("L", "N")),
    min_size=0,
    max_size=200,
)

_notes_strategy = st.text(
    alphabet=st.characters(
        categories=("L", "N", "P"),
        exclude_characters="\x00",
    ),
    min_size=0,
    max_size=200,
)


# ---------------------------------------------------------------------------
# Property 3: Edit button enabled state tracks selection
# ---------------------------------------------------------------------------


class TestMatchEditButtonEnabledStateTracksSelection:
    """Feature: dna-tab-enhancements, Property 3: Edit button enabled state tracks selection

    For any DNA matches list state, the "Redigera" button's enabled state SHALL
    equal True if and only if the list has a current selected item.

    **Validates: Requirements 4.1**
    """

    @given(
        person_id=_person_id_strategy,
        other_person_id=st.integers(min_value=10000, max_value=19999).map(
            lambda n: f"person_{n}"
        ),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_edit_match_button_enabled_tracks_selection(
        self, qtbot, person_id: str, other_person_id: str
    ) -> None:
        """The match edit button SHALL be enabled iff a match is selected in the list.

        Feature: dna-tab-enhancements, Property 3: Edit button enabled state tracks selection
        **Validates: Requirements 4.1**
        """
        company = DnaCompany(id="company_1", name="TestDNA")
        profile1 = DnaProfile(
            id="profile_1",
            person_id=person_id,
            company_id="company_1",
            test_type="autosomal",
            kit_name="Kit1",
        )
        profile2 = DnaProfile(
            id="profile_2",
            person_id=other_person_id,
            company_id="company_1",
            test_type="autosomal",
            kit_name="Kit2",
        )
        match = DnaMatch(
            id="match_1",
            profile1_id="profile_1",
            profile2_id="profile_2",
            shared_cm=100.0,
            segment_count=5,
        )

        person = Person(
            id=person_id,
            sex="M",
            names=[Name(type="birth", given="Test", surname="Person")],
        )

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            persons=[person],
            dna_companies=[company],
            dna_profiles=[profile1, profile2],
            dna_matches=[match],
        )

        editor = PersonEditor(project_data, person=person)
        qtbot.addWidget(editor)

        # Initially no selection => button disabled
        assert not editor._edit_dna_match_button.isEnabled()

        # Select first item in matches list
        matches_list = editor._ui.dna_matches_list
        if matches_list.count() > 0:
            matches_list.setCurrentRow(0)
            editor._update_dna_button_states()
            assert editor._edit_dna_match_button.isEnabled()

            # Deselect
            matches_list.setCurrentRow(-1)
            editor._update_dna_button_states()
            assert not editor._edit_dna_match_button.isEnabled()


# ---------------------------------------------------------------------------
# Property 4: Cancel preserves original data
# ---------------------------------------------------------------------------


class TestCancelEditPreservesOriginalData:
    """Feature: dna-tab-enhancements, Property 4: Cancel preserves original data

    For any DnaMatch opened in edit mode, if the user cancels the dialog, the
    match in ProjectData SHALL remain unchanged.

    **Validates: Requirements 4.6**
    """

    @given(
        shared_cm=_shared_cm_strategy,
        shared_pct=_shared_pct_strategy,
        segment_count=_segment_count_strategy,
        largest_segment=_largest_segment_strategy,
        match_source=_match_source_strategy,
        notes=_notes_strategy,
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_cancel_edit_preserves_match(
        self,
        qtbot,
        shared_cm: float,
        shared_pct: float,
        segment_count: int,
        largest_segment: float,
        match_source: str,
        notes: str,
    ) -> None:
        """Canceling the match edit dialog SHALL NOT modify the original match.

        Feature: dna-tab-enhancements, Property 4: Cancel preserves original data
        **Validates: Requirements 4.6**
        """
        person_id = "person_1"
        other_person_id = "person_2"
        company = DnaCompany(id="company_1", name="TestDNA")
        profile1 = DnaProfile(
            id="profile_1",
            person_id=person_id,
            company_id="company_1",
            test_type="autosomal",
            kit_name="Kit1",
        )
        profile2 = DnaProfile(
            id="profile_2",
            person_id=other_person_id,
            company_id="company_1",
            test_type="autosomal",
            kit_name="Kit2",
        )

        existing_match = DnaMatch(
            id="match_edit_1",
            profile1_id="profile_1",
            profile2_id="profile_2",
            shared_cm=shared_cm,
            shared_percentage=shared_pct,
            segment_count=segment_count,
            largest_segment_cm=largest_segment,
            match_source=match_source,
            notes=notes,
        )

        original_match = copy.deepcopy(existing_match)

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=[company],
            dna_profiles=[profile1, profile2],
            dna_matches=[existing_match],
        )

        dialog = DnaMatchDialog(
            project_data, person_id, existing_match=existing_match
        )
        qtbot.addWidget(dialog)

        # Cancel the dialog
        dialog.reject()

        # Verify edited_match is None
        assert dialog.edited_match is None

        # Verify original match in project_data is unchanged
        assert existing_match.id == original_match.id
        assert existing_match.profile1_id == original_match.profile1_id
        assert existing_match.profile2_id == original_match.profile2_id
        assert existing_match.shared_cm == original_match.shared_cm
        assert existing_match.shared_percentage == original_match.shared_percentage
        assert existing_match.segment_count == original_match.segment_count
        assert existing_match.largest_segment_cm == original_match.largest_segment_cm
        assert existing_match.match_source == original_match.match_source
        assert existing_match.notes == original_match.notes


# ---------------------------------------------------------------------------
# Property 5: Edit preserves identity and updates fields
# ---------------------------------------------------------------------------


class TestEditPreservesIdentityAndUpdatesFields:
    """Feature: dna-tab-enhancements, Property 5: Edit preserves identity and updates fields

    For any DnaMatch and valid field modifications, saving an edit SHALL preserve
    the match's id while updating other fields to match the dialog's values.

    **Validates: Requirements 4.4**
    """

    @given(
        new_shared_cm=st.floats(min_value=0.01, max_value=10000.00, allow_nan=False),
        new_shared_pct=_shared_pct_strategy,
        new_segment_count=_segment_count_strategy,
        new_largest_segment=_largest_segment_strategy,
        new_match_source=_match_source_strategy,
        new_notes=_notes_strategy,
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_edit_preserves_id_updates_fields(
        self,
        qtbot,
        new_shared_cm: float,
        new_shared_pct: float,
        new_segment_count: int,
        new_largest_segment: float,
        new_match_source: str,
        new_notes: str,
    ) -> None:
        """Saving an edit SHALL preserve match.id and update all other fields.

        Feature: dna-tab-enhancements, Property 5: Edit preserves identity and updates fields
        **Validates: Requirements 4.4**
        """
        person_id = "person_1"
        other_person_id = "person_2"
        company = DnaCompany(id="company_1", name="TestDNA")
        profile1 = DnaProfile(
            id="profile_1",
            person_id=person_id,
            company_id="company_1",
            test_type="autosomal",
            kit_name="Kit1",
        )
        profile2 = DnaProfile(
            id="profile_2",
            person_id=other_person_id,
            company_id="company_1",
            test_type="autosomal",
            kit_name="Kit2",
        )

        original_id = "match_original_id_123"
        existing_match = DnaMatch(
            id=original_id,
            profile1_id="profile_1",
            profile2_id="profile_2",
            shared_cm=50.0,
            shared_percentage=1.0,
            segment_count=3,
            largest_segment_cm=20.0,
            match_source="internal",
            notes="original notes",
        )

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=[company],
            dna_profiles=[profile1, profile2],
            dna_matches=[existing_match],
        )

        dialog = DnaMatchDialog(
            project_data, person_id, existing_match=existing_match
        )
        qtbot.addWidget(dialog)

        # Modify fields
        dialog._spin_shared_cm.setValue(new_shared_cm)
        dialog._spin_shared_pct.setValue(new_shared_pct)
        dialog._spin_segment_count.setValue(new_segment_count)
        dialog._spin_largest_segment.setValue(new_largest_segment)
        dialog._edit_match_source.setText(new_match_source)
        dialog._edit_notes.setPlainText(new_notes)

        # Accept the dialog
        dialog._on_accept()

        # Verify
        edited = dialog.edited_match
        assert edited is not None, "Expected edited_match to be set after accept"
        assert edited.id == original_id, "ID must be preserved on edit"
        assert edited.profile1_id == "profile_1"
        assert edited.profile2_id == "profile_2"
        assert edited.shared_cm == pytest.approx(
            dialog._spin_shared_cm.value(), abs=0.01
        )
        assert edited.shared_percentage == pytest.approx(
            dialog._spin_shared_pct.value(), abs=0.01
        )
        assert edited.segment_count == dialog._spin_segment_count.value()
        assert edited.largest_segment_cm == pytest.approx(
            dialog._spin_largest_segment.value(), abs=0.01
        )
        assert edited.match_source == new_match_source.strip()
        assert edited.notes == new_notes.strip()


# ---------------------------------------------------------------------------
# Property 6: Edit dialog pre-population matches entity data
# ---------------------------------------------------------------------------


class TestEditDialogPrePopulationMatchesEntityData:
    """Feature: dna-tab-enhancements, Property 6: Edit dialog pre-population matches entity data

    For any DnaMatch opened in edit mode, every field in the dialog SHALL display
    the exact current value of the corresponding entity attribute.

    **Validates: Requirements 4.2**
    """

    @given(
        shared_cm=st.floats(min_value=0.01, max_value=10000.00, allow_nan=False),
        shared_pct=_shared_pct_strategy,
        segment_count=_segment_count_strategy,
        largest_segment=_largest_segment_strategy,
        match_source=_match_source_strategy,
        notes=_notes_strategy,
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_edit_dialog_fields_match_entity(
        self,
        qtbot,
        shared_cm: float,
        shared_pct: float,
        segment_count: int,
        largest_segment: float,
        match_source: str,
        notes: str,
    ) -> None:
        """All dialog fields SHALL match the existing_match attributes when opened in edit mode.

        Feature: dna-tab-enhancements, Property 6: Edit dialog pre-population matches entity data
        **Validates: Requirements 4.2**
        """
        person_id = "person_1"
        other_person_id = "person_2"
        company = DnaCompany(id="company_1", name="TestDNA")
        profile1 = DnaProfile(
            id="profile_1",
            person_id=person_id,
            company_id="company_1",
            test_type="autosomal",
            kit_name="Kit1",
        )
        profile2 = DnaProfile(
            id="profile_2",
            person_id=other_person_id,
            company_id="company_1",
            test_type="autosomal",
            kit_name="Kit2",
        )

        existing_match = DnaMatch(
            id="match_prepop_1",
            profile1_id="profile_1",
            profile2_id="profile_2",
            shared_cm=shared_cm,
            shared_percentage=shared_pct,
            segment_count=segment_count,
            largest_segment_cm=largest_segment,
            match_source=match_source,
            notes=notes,
        )

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=[company],
            dna_profiles=[profile1, profile2],
            dna_matches=[existing_match],
        )

        dialog = DnaMatchDialog(
            project_data, person_id, existing_match=existing_match
        )
        qtbot.addWidget(dialog)

        # Verify all fields are pre-populated correctly
        assert dialog._combo_profile1.currentData() == "profile_1"
        assert dialog._combo_profile2.currentData() == "profile_2"
        assert dialog._spin_shared_cm.value() == pytest.approx(shared_cm, abs=0.01)
        assert dialog._spin_shared_pct.value() == pytest.approx(shared_pct, abs=0.01)
        assert dialog._spin_segment_count.value() == segment_count
        assert dialog._spin_largest_segment.value() == pytest.approx(
            largest_segment, abs=0.01
        )
        assert dialog._edit_match_source.text() == match_source
        assert dialog._edit_notes.toPlainText() == notes


# ---------------------------------------------------------------------------
# Property 7: Invalid edits are rejected without data modification
# ---------------------------------------------------------------------------


class TestInvalidEditsRejectedWithoutDataModification:
    """Feature: dna-tab-enhancements, Property 7: Invalid edits are rejected without data modification

    For any edit operation where validation fails, the dialog SHALL remain open
    and the original entity data SHALL be unchanged.

    **Validates: Requirements 4.7**
    """

    @given(
        invalid_notes=st.text(
            alphabet=st.characters(categories=("L", "N", "P"), exclude_characters="\x00"),
            min_size=2001,
            max_size=2100,
        ),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_notes_too_long_rejects_edit(
        self,
        qtbot,
        invalid_notes: str,
    ) -> None:
        """Notes exceeding 2000 characters SHALL cause rejection without data modification.

        Feature: dna-tab-enhancements, Property 7: Invalid edits are rejected without data modification
        **Validates: Requirements 4.7**
        """
        person_id = "person_1"
        other_person_id = "person_2"
        company = DnaCompany(id="company_1", name="TestDNA")
        profile1 = DnaProfile(
            id="profile_1",
            person_id=person_id,
            company_id="company_1",
            test_type="autosomal",
            kit_name="Kit1",
        )
        profile2 = DnaProfile(
            id="profile_2",
            person_id=other_person_id,
            company_id="company_1",
            test_type="autosomal",
            kit_name="Kit2",
        )

        existing_match = DnaMatch(
            id="match_invalid_1",
            profile1_id="profile_1",
            profile2_id="profile_2",
            shared_cm=100.0,
            shared_percentage=5.0,
            segment_count=3,
            largest_segment_cm=30.0,
            match_source="internal",
            notes="original",
        )

        original_match = copy.deepcopy(existing_match)

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=[company],
            dna_profiles=[profile1, profile2],
            dna_matches=[existing_match],
        )

        dialog = DnaMatchDialog(
            project_data, person_id, existing_match=existing_match
        )
        qtbot.addWidget(dialog)

        # Set invalid notes (too long)
        dialog._edit_notes.setPlainText(invalid_notes)

        # Attempt accept
        dialog._on_accept()

        # Verify rejection
        assert dialog.edited_match is None
        # Verify original data is unchanged
        assert existing_match.id == original_match.id
        assert existing_match.shared_cm == original_match.shared_cm
        assert existing_match.notes == original_match.notes

    @given(
        scenario=st.sampled_from(["missing_profile1", "missing_profile2"]),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_missing_profile_rejects_edit(
        self,
        qtbot,
        scenario: str,
    ) -> None:
        """Missing profile selection SHALL cause rejection without data modification.

        Feature: dna-tab-enhancements, Property 7: Invalid edits are rejected without data modification
        **Validates: Requirements 4.7**
        """
        person_id = "person_1"
        other_person_id = "person_2"
        company = DnaCompany(id="company_1", name="TestDNA")
        profile1 = DnaProfile(
            id="profile_1",
            person_id=person_id,
            company_id="company_1",
            test_type="autosomal",
            kit_name="Kit1",
        )
        # Add a second profile for the same person to avoid auto-select
        profile1b = DnaProfile(
            id="profile_1b",
            person_id=person_id,
            company_id="company_1",
            test_type="y-dna",
            kit_name="Kit1b",
        )
        profile2 = DnaProfile(
            id="profile_2",
            person_id=other_person_id,
            company_id="company_1",
            test_type="autosomal",
            kit_name="Kit2",
        )

        existing_match = DnaMatch(
            id="match_missing_prof",
            profile1_id="profile_1",
            profile2_id="profile_2",
            shared_cm=100.0,
            shared_percentage=5.0,
            segment_count=3,
            largest_segment_cm=30.0,
            match_source="internal",
            notes="original",
        )

        original_match = copy.deepcopy(existing_match)

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=[company],
            dna_profiles=[profile1, profile1b, profile2],
            dna_matches=[existing_match],
        )

        dialog = DnaMatchDialog(
            project_data, person_id, existing_match=existing_match
        )
        qtbot.addWidget(dialog)

        # Clear profile selections based on scenario
        if scenario == "missing_profile1":
            dialog._combo_profile1.setCurrentIndex(0)  # placeholder
        elif scenario == "missing_profile2":
            dialog._combo_profile2.setCurrentIndex(0)  # placeholder

        # Attempt accept
        dialog._on_accept()

        # Verify rejection
        assert dialog.edited_match is None
        # Verify original data preserved
        assert existing_match.id == original_match.id
        assert existing_match.shared_cm == original_match.shared_cm


# ---------------------------------------------------------------------------
# Property 8: Same-company profile filtering invariant
# ---------------------------------------------------------------------------


class TestSameCompanyProfileFilteringInvariant:
    """Feature: dna-tab-enhancements, Property 8: Same-company profile filtering invariant

    For any Profile 1 selection in the Match_Dialog, every item in the Profile 2
    dropdown SHALL have a company_id equal to Profile 1's company_id, and Profile 1
    itself SHALL not appear in the Profile 2 dropdown.

    **Validates: Requirements 5.1, 5.2, 5.3**
    """

    @given(
        num_companies=st.integers(min_value=2, max_value=4),
        profiles_per_company=st.integers(min_value=2, max_value=5),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_profile2_filtered_by_same_company(
        self,
        qtbot,
        num_companies: int,
        profiles_per_company: int,
    ) -> None:
        """Every profile2 dropdown item SHALL have same company_id as profile1;
        profile1 itself SHALL NOT appear in profile2 list.

        Feature: dna-tab-enhancements, Property 8: Same-company profile filtering invariant
        **Validates: Requirements 5.1, 5.2, 5.3**
        """
        person_id = "person_1"

        # Create companies
        companies = [
            DnaCompany(id=f"company_{i}", name=f"Company {i}")
            for i in range(num_companies)
        ]

        # Create profiles: person_1 gets profiles in different companies,
        # other persons also get profiles.
        profiles = []
        profile_idx = 0
        for ci, company in enumerate(companies):
            # person_1 gets one profile per company
            profiles.append(
                DnaProfile(
                    id=f"profile_{profile_idx}",
                    person_id=person_id,
                    company_id=company.id,
                    test_type="autosomal",
                    kit_name=f"Kit_{profile_idx}",
                )
            )
            profile_idx += 1
            # Other persons get profiles in this company
            for pi in range(1, profiles_per_company):
                profiles.append(
                    DnaProfile(
                        id=f"profile_{profile_idx}",
                        person_id=f"person_{pi + 100}",
                        company_id=company.id,
                        test_type="autosomal",
                        kit_name=f"Kit_{profile_idx}",
                    )
                )
                profile_idx += 1

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=companies,
            dna_profiles=profiles,
        )

        dialog = DnaMatchDialog(project_data, person_id)
        qtbot.addWidget(dialog)

        # For each person_1 profile (in combo_profile1), verify filtering
        for idx1 in range(1, dialog._combo_profile1.count()):
            dialog._combo_profile1.setCurrentIndex(idx1)
            profile1_id = dialog._combo_profile1.currentData()

            # Get profile1's company_id
            profile1_company_id = None
            for p in profiles:
                if p.id == profile1_id:
                    profile1_company_id = p.company_id
                    break

            assert profile1_company_id is not None

            # Check every item in profile2 dropdown (skip placeholder at 0)
            for idx2 in range(1, dialog._combo_profile2.count()):
                p2_id = dialog._combo_profile2.itemData(idx2)

                # profile1 must not appear in profile2
                assert p2_id != profile1_id, (
                    f"Profile1 ({profile1_id}) should not appear in profile2 dropdown"
                )

                # Find this profile's company_id
                p2_company_id = None
                for p in profiles:
                    if p.id == p2_id:
                        p2_company_id = p.company_id
                        break

                assert p2_company_id == profile1_company_id, (
                    f"Profile2 ({p2_id}) has company {p2_company_id}, "
                    f"expected {profile1_company_id}"
                )
