"""Property-based tests for DnaProfileDialog.

Feature: dna-management-from-person-editor

Validates: Requirements 2.2, 2.3, 2.4
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from PySide6.QtWidgets import QApplication

from slaktbusken.model.dna import DnaCompany
from slaktbusken.model.project import ProjectData, ProjectMetadata
from slaktbusken.ui.dialogs.dna_profile_dialog import DnaProfileDialog
from tests.conftest import dna_company_strategy


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_DNA_TEST_TYPES = ["autosomal", "y-dna", "mtdna"]

_person_id_strategy = st.integers(min_value=1, max_value=9999).map(
    lambda n: f"person_{n}"
)

_kit_name_strategy = st.text(
    alphabet=st.characters(categories=("L", "N")),
    min_size=0,
    max_size=100,
)

_kit_id_strategy = st.text(
    alphabet=st.characters(categories=("L", "N")),
    min_size=0,
    max_size=50,
)

# Notes: avoid Unicode whitespace category "Z" (e.g. \xa0) since QPlainTextEdit
# may normalize them. Use letters, numbers, and basic punctuation instead.
_notes_strategy = st.text(
    alphabet=st.characters(
        categories=("L", "N", "P"),
        exclude_characters="\x00",
    ),
    min_size=0,
    max_size=200,
)

_optional_text = st.text(
    alphabet=st.characters(categories=("L", "N")),
    min_size=0,
    max_size=50,
)

# Which required field(s) to leave missing
_missing_field_strategy = st.sampled_from(["company", "test_type", "both"])


# ---------------------------------------------------------------------------
# Property 1: Profile creation round-trip
# ---------------------------------------------------------------------------


class TestDnaProfileCreationRoundTrip:
    """Feature: dna-management-from-person-editor, Property 1: Profile creation round-trip

    Generate random valid company ID, test type, kit name, kit ID, notes.
    Verify resulting DnaProfile has correct person_id, company_id, test_type,
    and optional fields.

    **Validates: Requirements 2.3, 2.4**
    """

    @given(
        company=dna_company_strategy(),
        person_id=_person_id_strategy,
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
    def test_profile_creation_round_trip(
        self,
        qtbot,
        company: DnaCompany,
        person_id: str,
        test_type: str,
        kit_name: str,
        kit_id: str,
        notes: str,
    ) -> None:
        """After programmatically filling a valid form and accepting,
        created_profile SHALL have correct person_id, company_id, test_type,
        kit_name, kit_id, and notes.

        Feature: dna-management-from-person-editor, Property 1: Profile creation round-trip
        **Validates: Requirements 2.3, 2.4**
        """
        # Build ProjectData with the generated company
        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=[company],
        )

        # Create the dialog
        dialog = DnaProfileDialog(project_data, person_id)
        qtbot.addWidget(dialog)

        # Select the company in the dropdown (index 0 is placeholder)
        company_index = dialog._combo_company.findData(company.id)
        assert company_index != -1, f"Company {company.id} not found in dropdown"
        dialog._combo_company.setCurrentIndex(company_index)

        # Select the test type in the dropdown
        test_type_index = dialog._combo_test_type.findData(test_type)
        assert test_type_index != -1, f"Test type {test_type} not found in dropdown"
        dialog._combo_test_type.setCurrentIndex(test_type_index)

        # Set optional fields
        dialog._edit_kit_name.setText(kit_name)
        dialog._edit_kit_id.setText(kit_id)
        dialog._edit_notes.setPlainText(notes)

        # Trigger accept
        dialog._on_accept()

        # Verify the created profile
        profile = dialog.created_profile
        assert profile is not None, "Expected created_profile to be set after accept"
        assert profile.person_id == person_id
        assert profile.company_id == company.id
        assert profile.test_type == test_type
        assert profile.kit_name == kit_name.strip()
        assert profile.kit_id == kit_id.strip()
        assert profile.notes == notes.strip()
        # Verify id is a valid UUID string (non-empty)
        assert len(profile.id) > 0


# ---------------------------------------------------------------------------
# Property 2: Profile validation rejects incomplete forms
# ---------------------------------------------------------------------------


class TestProfileValidationRejectsIncompleteForms:
    """Feature: dna-management-from-person-editor, Property 2: Profile validation rejects incomplete forms

    Generate random optional field values with missing company OR missing test type.
    Verify `_validate()` returns at least one error and `created_profile` is `None`.

    **Validates: Requirements 2.2**
    """

    @given(
        kit_name=_optional_text,
        kit_id=_optional_text,
        notes=_optional_text,
        missing_field=_missing_field_strategy,
    )
    @settings(max_examples=100)
    def test_incomplete_form_always_fails_validation(
        self,
        qapp: QApplication,
        kit_name: str,
        kit_id: str,
        notes: str,
        missing_field: str,
    ) -> None:
        """When a required field (company or test type) is not selected,
        _validate() SHALL return at least one error and created_profile
        SHALL be None.

        Feature: dna-management-from-person-editor, Property 2: Profile validation rejects incomplete forms
        **Validates: Requirements 2.2**
        """
        # Create project with at least one company so the dialog is usable
        project_data = ProjectData(
            project=ProjectMetadata(title="Test"),
            dna_companies=[
                DnaCompany(id="company_1", name="TestDNA"),
            ],
        )

        dialog = DnaProfileDialog(
            project_data=project_data,
            person_id="person_1",
        )

        try:
            # Set optional fields
            dialog._edit_kit_name.setText(kit_name)
            dialog._edit_kit_id.setText(kit_id)
            dialog._edit_notes.setPlainText(notes)

            # Configure required fields based on missing_field strategy
            if missing_field == "company":
                # Leave company at placeholder (index 0), select a valid test type
                dialog._combo_company.setCurrentIndex(0)
                dialog._combo_test_type.setCurrentIndex(1)  # "Autosomal"
            elif missing_field == "test_type":
                # Select a valid company, leave test type at placeholder (index 0)
                dialog._combo_company.setCurrentIndex(1)  # First real company
                dialog._combo_test_type.setCurrentIndex(0)
            else:  # "both"
                # Leave both at placeholder
                dialog._combo_company.setCurrentIndex(0)
                dialog._combo_test_type.setCurrentIndex(0)

            # Validate
            errors = dialog._validate()

            # Must have at least one error
            assert len(errors) >= 1, (
                f"Expected at least one validation error when '{missing_field}' "
                f"is missing, but got no errors."
            )

            # created_profile must be None (dialog was never accepted)
            assert dialog.created_profile is None, (
                "Expected created_profile to be None when form is incomplete, "
                f"but got {dialog.created_profile!r}."
            )
        finally:
            dialog.close()
            dialog.deleteLater()
