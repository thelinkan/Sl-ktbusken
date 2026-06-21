"""Property-based tests for DNA profile edit functionality.

Feature: dna-tab-enhancements, Properties 3–7 for profiles

Validates: Requirements 3.1, 3.2, 3.4, 3.5, 3.7
"""

from __future__ import annotations

import copy

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from PySide6.QtWidgets import QApplication

from slaktbusken.model.dna import DnaCompany, DnaProfile
from slaktbusken.model.person import Name, Person
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.dialogs.dna_profile_dialog import DnaProfileDialog
from slaktbusken.ui.editors.person_editor import PersonEditor
from tests.conftest import dna_company_strategy, dna_profile_strategy


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

_DNA_TEST_TYPES = ["autosomal", "y-dna", "mtdna"]

_person_id_strategy = st.integers(min_value=1, max_value=9999).map(
    lambda n: f"person_{n}"
)

_kit_name_strategy = st.text(
    alphabet=st.characters(categories=("L", "N"), max_codepoint=0xFFFF),
    min_size=0,
    max_size=100,
)

_kit_id_strategy = st.text(
    alphabet=st.characters(categories=("L", "N"), max_codepoint=0xFFFF),
    min_size=0,
    max_size=50,
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


class TestProfileEditButtonEnabledStateTracksSelection:
    """Feature: dna-tab-enhancements, Property 3: Edit button enabled state tracks selection

    For the DNA profiles list, the "Redigera" button's enabled state SHALL
    equal True if and only if the list has a current selected item.

    **Validates: Requirements 3.1**
    """

    @given(
        person_id=_person_id_strategy,
        company=dna_company_strategy(),
        test_type=st.sampled_from(_DNA_TEST_TYPES),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_edit_profile_button_enabled_tracks_selection(
        self, qtbot, person_id: str, company: DnaCompany, test_type: str
    ) -> None:
        """The profile edit button SHALL be enabled iff a profile is selected in the list.

        Feature: dna-tab-enhancements, Property 3: Edit button enabled state tracks selection
        **Validates: Requirements 3.1**
        """
        profile = DnaProfile(
            id="profile_1",
            person_id=person_id,
            company_id=company.id,
            test_type=test_type,
            kit_name="TestKit",
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
            dna_profiles=[profile],
        )

        editor = PersonEditor(project_data, person=person)
        qtbot.addWidget(editor)

        # Initially no selection => button disabled
        assert not editor._edit_dna_profile_button.isEnabled()

        # Select first item in profiles list
        profiles_list = editor._ui.dna_profiles_list
        if profiles_list.count() > 0:
            profiles_list.setCurrentRow(0)
            editor._update_dna_button_states()
            assert editor._edit_dna_profile_button.isEnabled()

            # Deselect
            profiles_list.setCurrentRow(-1)
            editor._update_dna_button_states()
            assert not editor._edit_dna_profile_button.isEnabled()


# ---------------------------------------------------------------------------
# Property 4: Cancel preserves original data
# ---------------------------------------------------------------------------


class TestCancelProfileEditPreservesOriginalData:
    """Feature: dna-tab-enhancements, Property 4: Cancel preserves original data

    For any DnaProfile opened in edit mode, if the user cancels the dialog, the
    profile in ProjectData SHALL remain unchanged.

    **Validates: Requirements 3.2**
    """

    @given(
        company=dna_company_strategy(),
        test_type=st.sampled_from(_DNA_TEST_TYPES),
        kit_name=_kit_name_strategy,
        kit_id=_kit_id_strategy,
        notes=_notes_strategy,
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_cancel_edit_preserves_profile(
        self,
        qtbot,
        company: DnaCompany,
        test_type: str,
        kit_name: str,
        kit_id: str,
        notes: str,
    ) -> None:
        """Canceling the profile edit dialog SHALL NOT modify the original profile.

        Feature: dna-tab-enhancements, Property 4: Cancel preserves original data
        **Validates: Requirements 3.2**
        """
        person_id = "person_1"

        existing_profile = DnaProfile(
            id="profile_cancel_1",
            person_id=person_id,
            company_id=company.id,
            test_type=test_type,
            kit_name=kit_name,
            kit_id=kit_id,
            notes=notes,
        )

        original_profile = copy.deepcopy(existing_profile)

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=[company],
            dna_profiles=[existing_profile],
        )

        dialog = DnaProfileDialog(
            project_data, person_id, existing_profile=existing_profile
        )
        qtbot.addWidget(dialog)

        # Cancel the dialog
        dialog.reject()

        # Verify edited_profile is None
        assert dialog.edited_profile is None

        # Verify original profile in project_data is unchanged
        assert existing_profile.id == original_profile.id
        assert existing_profile.person_id == original_profile.person_id
        assert existing_profile.company_id == original_profile.company_id
        assert existing_profile.test_type == original_profile.test_type
        assert existing_profile.kit_name == original_profile.kit_name
        assert existing_profile.kit_id == original_profile.kit_id
        assert existing_profile.notes == original_profile.notes


# ---------------------------------------------------------------------------
# Property 5: Edit preserves identity and updates fields
# ---------------------------------------------------------------------------


class TestProfileEditPreservesIdentityAndUpdatesFields:
    """Feature: dna-tab-enhancements, Property 5: Edit preserves identity and updates fields

    For any DnaProfile and valid field modifications, saving an edit SHALL preserve
    the profile's id and person_id while updating other fields.

    **Validates: Requirements 3.4, 3.5**
    """

    @given(
        new_test_type=st.sampled_from(_DNA_TEST_TYPES),
        new_kit_name=_kit_name_strategy,
        new_kit_id=_kit_id_strategy,
        new_notes=_notes_strategy,
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_edit_preserves_id_and_person_id_updates_fields(
        self,
        qtbot,
        new_test_type: str,
        new_kit_name: str,
        new_kit_id: str,
        new_notes: str,
    ) -> None:
        """Saving an edit SHALL preserve profile.id and person_id, updating other fields.

        Feature: dna-tab-enhancements, Property 5: Edit preserves identity and updates fields
        **Validates: Requirements 3.4, 3.5**
        """
        person_id = "person_1"
        original_id = "profile_original_id_123"
        company = DnaCompany(id="company_1", name="TestDNA")

        existing_profile = DnaProfile(
            id=original_id,
            person_id=person_id,
            company_id="company_1",
            test_type="autosomal",
            kit_name="Original Kit",
            kit_id="OrigID",
            notes="original notes",
        )

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=[company],
            dna_profiles=[existing_profile],
        )

        dialog = DnaProfileDialog(
            project_data, person_id, existing_profile=existing_profile
        )
        qtbot.addWidget(dialog)

        # Modify fields
        # Company stays the same (only one available)
        test_type_index = dialog._combo_test_type.findData(new_test_type)
        if test_type_index >= 0:
            dialog._combo_test_type.setCurrentIndex(test_type_index)
        dialog._edit_kit_name.setText(new_kit_name)
        dialog._edit_kit_id.setText(new_kit_id)
        dialog._edit_notes.setPlainText(new_notes)

        # Accept the dialog
        dialog._on_accept()

        # Verify
        edited = dialog.edited_profile
        assert edited is not None, "Expected edited_profile to be set after accept"
        assert edited.id == original_id, "ID must be preserved on edit"
        assert edited.person_id == person_id, "person_id must be preserved on edit"
        assert edited.company_id == "company_1"
        assert edited.test_type == new_test_type
        assert edited.kit_name == new_kit_name.strip()
        assert edited.kit_id == new_kit_id.strip()
        assert edited.notes == new_notes.strip()


# ---------------------------------------------------------------------------
# Property 6: Edit dialog pre-population matches entity data
# ---------------------------------------------------------------------------


class TestProfileEditDialogPrePopulationMatchesEntityData:
    """Feature: dna-tab-enhancements, Property 6: Edit dialog pre-population matches entity data

    For any DnaProfile opened in edit mode, every field in the dialog SHALL display
    the exact current value of the corresponding entity attribute.

    **Validates: Requirements 3.5**
    """

    @given(
        test_type=st.sampled_from(_DNA_TEST_TYPES),
        kit_name=_kit_name_strategy,
        kit_id=_kit_id_strategy,
        notes=_notes_strategy,
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_edit_dialog_fields_match_profile(
        self,
        qtbot,
        test_type: str,
        kit_name: str,
        kit_id: str,
        notes: str,
    ) -> None:
        """All dialog fields SHALL match the existing_profile attributes when opened in edit mode.

        Feature: dna-tab-enhancements, Property 6: Edit dialog pre-population matches entity data
        **Validates: Requirements 3.5**
        """
        person_id = "person_1"
        company = DnaCompany(id="company_prepop", name="PrepopDNA")

        existing_profile = DnaProfile(
            id="profile_prepop_1",
            person_id=person_id,
            company_id=company.id,
            test_type=test_type,
            kit_name=kit_name,
            kit_id=kit_id,
            notes=notes,
        )

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=[company],
            dna_profiles=[existing_profile],
        )

        dialog = DnaProfileDialog(
            project_data, person_id, existing_profile=existing_profile
        )
        qtbot.addWidget(dialog)

        # Verify all fields are pre-populated correctly
        assert dialog._combo_company.currentData() == company.id
        assert dialog._combo_test_type.currentData() == test_type
        assert dialog._edit_kit_name.text() == (kit_name or "")
        assert dialog._edit_kit_id.text() == (kit_id or "")
        assert dialog._edit_notes.toPlainText() == (notes or "")


# ---------------------------------------------------------------------------
# Property 7: Invalid edits are rejected without data modification
# ---------------------------------------------------------------------------


class TestProfileInvalidEditsRejectedWithoutDataModification:
    """Feature: dna-tab-enhancements, Property 7: Invalid edits are rejected without data modification

    For any edit operation where validation fails (e.g., company cleared),
    the dialog SHALL remain open and the original entity data SHALL be unchanged.

    **Validates: Requirements 3.7**
    """

    @given(
        kit_name=_kit_name_strategy,
        kit_id=_kit_id_strategy,
        notes=_notes_strategy,
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
        deadline=None,
    )
    def test_clearing_company_rejects_edit(
        self,
        qtbot,
        kit_name: str,
        kit_id: str,
        notes: str,
    ) -> None:
        """Clearing the company selection SHALL cause rejection without data modification.

        Feature: dna-tab-enhancements, Property 7: Invalid edits are rejected without data modification
        **Validates: Requirements 3.7**
        """
        person_id = "person_1"
        company = DnaCompany(id="company_1", name="TestDNA")

        existing_profile = DnaProfile(
            id="profile_invalid_1",
            person_id=person_id,
            company_id="company_1",
            test_type="autosomal",
            kit_name=kit_name,
            kit_id=kit_id,
            notes=notes,
        )

        original_profile = copy.deepcopy(existing_profile)

        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=[company],
            dna_profiles=[existing_profile],
        )

        dialog = DnaProfileDialog(
            project_data, person_id, existing_profile=existing_profile
        )
        qtbot.addWidget(dialog)

        # Clear company selection (set to placeholder index 0)
        dialog._combo_company.setCurrentIndex(0)

        # Attempt accept
        dialog._on_accept()

        # Verify validation returns errors
        errors = dialog._validate()
        assert len(errors) >= 1, "Expected at least one validation error when company is cleared"

        # Verify edited_profile is None (rejection)
        assert dialog.edited_profile is None

        # Verify original data is unchanged
        assert existing_profile.id == original_profile.id
        assert existing_profile.person_id == original_profile.person_id
        assert existing_profile.company_id == original_profile.company_id
        assert existing_profile.test_type == original_profile.test_type
        assert existing_profile.kit_name == original_profile.kit_name
        assert existing_profile.kit_id == original_profile.kit_id
        assert existing_profile.notes == original_profile.notes
